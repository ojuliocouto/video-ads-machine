"""`vam avatar` estima o custo pela duração da voz ANTES de pedir o job e recusa antes de gastar.

Teto padrão US$ 9,00 (cobre 70 s), `--teto-usd` continua mandando. O HeyGen é falso e conta as chamadas: recusar
antes de gastar quer dizer ZERO chamada (nem upload, nem submit, nem leitura de saldo).
"""
import json

import pytest

import vam
from avatar import heygen_cliente as H
from avatar import job as J
from projeto import looks, pastas, status
from tests.fixtures.midia_avatar import TEM_FFMPEG, criar_voz

CHAVE = "hg_chave_de_teste_custo_123456"
URL_VIDEO = "https://cdn.heygen.test/video.mp4"

pytestmark = pytest.mark.skipif(not TEM_FFMPEG, reason="ffmpeg e ffprobe ausentes")


def resp(obj, status_http=200):
    return (status_http, {}, json.dumps(obj).encode("utf-8"))


class HeyGenFalso:
    def __init__(self):
        self.chamadas = []
        self.submits = 0

    def __call__(self, metodo, url, headers, corpo, timeout):
        self.chamadas.append((metodo, url))
        if url.endswith("/v3/assets"):
            return resp({"data": {"asset_id": "asset_1"}})
        if url.endswith("/v3/videos") and metodo == "POST":
            self.submits += 1
            return resp({"data": {"video_id": "vid_pago_%d" % self.submits}})
        if "/v3/videos/" in url:
            return resp({"data": {"status": "completed", "video_url": URL_VIDEO, "duration": 60}})
        if url.endswith("/v3/users/me"):
            return resp({"data": {"wallet": {"remaining_balance": 50.0, "currency": "usd"}}})
        if url == URL_VIDEO:
            return (200, {}, b"MP4-DO-AVATAR")
        raise AssertionError("chamada inesperada: %s %s" % (metodo, url))


@pytest.fixture
def amb(estado_vazio, monkeypatch, capsys):
    assert vam.main(["novo", "meu-ad", "--look", "estudio", "--sem-trilha", "teste do custo", "--estado",
                     str(estado_vazio)]) == 0
    looks.adicionar("estudio", "avatar_look_1", "medio", estado=estado_vazio)
    pj = pastas.projeto("meu-ad", estado_vazio)
    pj.voz_dir.mkdir(parents=True, exist_ok=True)
    from avatar import conferir
    monkeypatch.setattr(conferir, "conferir", lambda pj_, aspecto="9:16": {
        "resultado": "aprovada", "avatar": {"largura": 1080, "altura": 1920, "duracao_s": 60.0},
        "voz": {"duracao_s": 60.0}, "diferenca_duracao_s": 0.0, "fracao_util": 0.97})
    falso = HeyGenFalso()
    cli = H.ClienteHeyGen(CHAVE, http=falso, dormir=lambda s: None, agora=lambda: 0.0)
    monkeypatch.setattr(H.ClienteHeyGen, "do_ambiente", classmethod(lambda cls, *a, **k: cli))
    capsys.readouterr()

    def com_voz(segundos):
        criar_voz(pj.voz_limpo, segundos)

    def avatar(*extra):
        return vam.main(["avatar", "meu-ad", "--estado", str(estado_vazio)] + list(extra))

    return type("Amb", (), {"com_voz": staticmethod(com_voz), "avatar": staticmethod(avatar), "pj": pj,
                            "falso": falso})


def test_voz_de_90_s_com_o_teto_padrao_e_recusada_antes_de_qualquer_chamada(amb, capsys):
    amb.com_voz(90.0)
    assert amb.avatar() == 2
    cap = capsys.readouterr()
    assert amb.falso.chamadas == [], "recusar antes de gastar: nem upload, nem submit, nem saldo"
    assert "10,65" in cap.err and "9,00" in cap.err and "76 s" in cap.err and "Nada foi gasto" in cap.err
    assert not J.caminho(amb.pj).exists() and not amb.pj.avatar_mp4.exists()


def test_voz_de_60_s_cabe_no_teto_padrao_e_o_job_sai(amb):
    amb.com_voz(60.0)
    assert amb.avatar() == 0
    assert amb.falso.submits == 1


def test_voz_de_70_s_cabe_no_teto_padrao(amb):
    amb.com_voz(70.0)
    assert amb.avatar() == 0 and amb.falso.submits == 1


def test_voz_de_80_s_nao_cabe_no_teto_padrao(amb, capsys):
    amb.com_voz(80.0)
    assert amb.avatar() == 2 and amb.falso.chamadas == []
    assert "76 s" in capsys.readouterr().err


def test_o_override_do_teto_continua_mandando_para_baixo(amb, capsys):
    amb.com_voz(60.0)
    assert amb.avatar("--teto-usd", "5") == 2
    assert amb.falso.chamadas == [] and "42 s" in capsys.readouterr().err


def test_o_override_do_teto_continua_mandando_para_cima(amb):
    amb.com_voz(90.0)
    assert amb.avatar("--teto-usd", "12") == 0
    assert amb.falso.submits == 1


def test_voz_que_o_ffprobe_nao_le_avisa_que_nao_estimou_e_segue(amb, capsys):
    amb.pj.voz_limpo.write_bytes(b"VOZ-LIMPA")
    assert amb.avatar() == 0 and amb.falso.submits == 1
    assert "sem estimativa de custo" in capsys.readouterr().out


def test_existente_nao_gasta_e_nao_passa_pela_estimativa(amb, tmp_path):
    amb.com_voz(90.0)
    avatar = tmp_path / "avatar.mp4"
    avatar.write_bytes(b"MP4-DO-AVATAR")
    assert amb.avatar("--existente", str(avatar)) == 0
    assert amb.falso.chamadas == []


def test_retomar_o_job_ja_pago_nao_passa_pela_estimativa(amb):
    amb.com_voz(90.0)                                       # mais que o teto: o job já foi pago, retomar é de graça
    from avatar import job
    amb.pj.avatar_dir.mkdir(parents=True, exist_ok=True)
    job.gravar(amb.pj, "vid_pago_1", "avatar_v", "avatar_look_1", __import__("cli._comum", fromlist=["x"])
               .sha256_arquivo(amb.pj.voz_limpo))
    assert amb.avatar("--retomar") == 0
    assert amb.falso.submits == 0


def test_a_ajuda_mostra_o_teto_padrao_novo(capsys):
    try:
        vam.main(["avatar", "--help"])
    except SystemExit:
        pass
    assert "padrão 9.0" in " ".join(capsys.readouterr().out.split())
