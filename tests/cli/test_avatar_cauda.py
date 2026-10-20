"""`vam avatar` completa a cauda do avatar ao recebê-lo, e a aprovação do look nasce sobre o arquivo já completo.

O avatar do HeyGen veio 0,02 s mais curto que a voz e a prancha quebrou (`ERRO seg 08: duracao 2.77s != esperada
3.07s`). Os três caminhos de entrada do avatar (download, `--retomar`, `--existente`) passam pela mesma cauda, ANTES
da conferência. Falta de mais de 1 s segue erro claro. Mídia sintética de 1080x1920 (3 s) e o conferir de verdade:
nenhuma chamada paga. O HeyGen é falso.
"""
import json

import pytest

import vam
from avatar import heygen_cliente as H
from avatar import job as J
from gates import gate_look
from projeto import looks, pastas, status
from tests.fixtures.midia_avatar import TEM_FFMPEG, criar_avatar, criar_voz, sha, sonda

pytestmark = pytest.mark.skipif(not TEM_FFMPEG, reason="ffmpeg e ffprobe ausentes")

CHAVE = "hg_chave_de_teste_cauda_123456"
URL_VIDEO = "https://cdn.heygen.test/video-curto.mp4"
VOZ_S = 3.02          # a voz; o avatar do teste tem 3,00 s (0,02 s mais curto, como no ensaio)


def resp(obj, status_http=200):
    return (status_http, {}, json.dumps(obj).encode("utf-8"))


class HeyGenFalso:
    """Um HeyGen sem rede: o job fica pronto na 1ª consulta e o download devolve os bytes de `mp4`."""

    def __init__(self, mp4):
        self.mp4 = mp4
        self.submits = 0

    def __call__(self, metodo, url, headers, corpo, timeout):
        if url.endswith("/v3/assets"):
            return resp({"data": {"asset_id": "asset_1"}})
        if url.endswith("/v3/videos") and metodo == "POST":
            self.submits += 1
            return resp({"data": {"video_id": "vid_pago_%d" % self.submits}})
        if "/v3/videos/" in url:
            return resp({"data": {"status": "completed", "video_url": URL_VIDEO, "duration": 3}})
        if url.endswith("/v3/users/me"):
            return resp({"data": {"wallet": {"remaining_balance": 10.0, "currency": "usd"}}})
        if url == URL_VIDEO:
            return (200, {}, self.mp4.read_bytes())
        raise AssertionError("chamada inesperada: %s %s" % (metodo, url))


@pytest.fixture
def amb(estado_vazio, tmp_path, monkeypatch, capsys):
    """Projeto de avatar com voz limpa de 3,02 s, look cadastrado e a conferência de verdade."""
    assert vam.main(["novo", "meu-ad", "--look", "estudio", "--sem-trilha", "teste da cauda", "--estado",
                     str(estado_vazio)]) == 0
    looks.adicionar("estudio", "avatar_look_1", "medio", estado=estado_vazio)
    pj = pastas.projeto("meu-ad", estado_vazio)
    pj.voz_dir.mkdir(parents=True, exist_ok=True)
    criar_voz(pj.voz_limpo, VOZ_S)
    fontes = tmp_path / "fontes"
    fontes.mkdir()
    capsys.readouterr()

    def avatar(*extra):
        return vam.main(["avatar", "meu-ad", "--estado", str(estado_vazio)] + list(extra))

    def heygen(mp4):
        falso = HeyGenFalso(mp4)
        cli = H.ClienteHeyGen(CHAVE, http=falso, dormir=lambda s: None, agora=lambda: 0.0)
        monkeypatch.setattr(H.ClienteHeyGen, "do_ambiente", classmethod(lambda cls, *a, **k: cli))
        return falso

    def conferencia():
        return json.loads(pj.avatar_conferencia.read_text(encoding="utf-8"))

    return type("Amb", (), {"avatar": staticmethod(avatar), "heygen": staticmethod(heygen),
                            "conferencia": staticmethod(conferencia), "pj": pj, "fontes": fontes,
                            "estado": estado_vazio})


def curto(amb, dur=3.0, nome="curto.mp4"):
    return criar_avatar(amb.fontes / nome, dur, tamanho="1080x1920")


def test_existente_curto_ganha_cauda_antes_da_conferencia_e_a_origem_nao_muda(amb, capsys):
    origem = curto(amb)
    antes = sha(origem)
    assert amb.avatar("--existente", str(origem)) == 0
    out = capsys.readouterr().out
    linhas = [l for l in out.splitlines() if l.startswith("avatar completado")]
    assert len(linhas) == 1, out                      # registra em UMA linha
    d = sonda(amb.pj.avatar_mp4)
    assert d["video"] == pytest.approx(VOZ_S + 0.5, abs=0.08) and d["audio"] == pytest.approx(VOZ_S + 0.5, abs=0.08)
    c = amb.conferencia()
    assert c["resultado"] == "aprovada" and c["avatar"]["duracao_s"] == pytest.approx(VOZ_S + 0.5, abs=0.08)
    assert c["avatar"]["sha256"] == sha(amb.pj.avatar_mp4), "a conferência é do arquivo já completo"
    assert sha(origem) == antes, "o arquivo do aluno nunca é alterado"


def test_a_cauda_fica_no_historico_do_status(amb):
    amb.avatar("--existente", str(curto(amb)))
    hist = status.ler_json(amb.pj.status_json)["historico"]
    reg = [h for h in hist if h["etapa"] == "cauda_avatar"]
    assert len(reg) == 1 and reg[0]["estado"] == "ok"
    # O AAC do ffmpeg acrescenta alguns quadros de enchimento conforme a versão (Linux do CI: +0,036 s).
    assert reg[0]["detalhes"]["voz_s"] == pytest.approx(VOZ_S, abs=0.06)
    assert reg[0]["detalhes"]["cauda_s"] > 0.4


def test_a_cauda_nao_invalida_a_aprovacao_do_look(amb):
    """O roteiro da aula: recebe o avatar, olha a boca, aprova. A cauda entrou antes da conferência que o aluno aprovou."""
    assert amb.avatar("--existente", str(curto(amb))) == 0
    assert amb.avatar("--aprovar-look") == 0
    sit = looks.verificar("estudio", amb.estado)
    assert sit.aprovado, sit.motivo
    assert gate_look.rodar(amb.pj).ok, "o gate do vam montar aceita o look aprovado sobre o avatar completado"
    assert amb.conferencia()["avatar"]["sha256"] == sha(amb.pj.avatar_mp4)


def test_conferir_de_novo_nao_completa_outra_vez_nem_muda_o_avatar(amb, capsys):
    assert amb.avatar("--existente", str(curto(amb))) == 0
    depois = sha(amb.pj.avatar_mp4)
    capsys.readouterr()
    assert amb.avatar() == 0
    assert sha(amb.pj.avatar_mp4) == depois and "avatar completado" not in capsys.readouterr().out


def test_avatar_que_ja_cobre_a_voz_nao_ganha_cauda_nem_linha(amb, capsys):
    longo = curto(amb, dur=3.8, nome="longo.mp4")                  # voz 3,02 s + folga 0,5 s = 3,52 s: cobre
    antes = sha(longo)
    assert amb.avatar("--existente", str(longo)) == 0
    assert "avatar completado" not in capsys.readouterr().out
    assert sha(amb.pj.avatar_mp4) == antes
    assert amb.conferencia()["resultado"] == "aprovada"


def test_download_do_heygen_tambem_completa_a_cauda(amb, capsys):
    falso = amb.heygen(curto(amb))
    assert amb.avatar() == 0
    out = capsys.readouterr().out
    assert falso.submits == 1 and out.count("avatar completado") == 1
    assert sonda(amb.pj.avatar_mp4)["video"] == pytest.approx(VOZ_S + 0.5, abs=0.08)
    assert amb.conferencia()["resultado"] == "aprovada"


def test_retomar_o_job_pago_tambem_completa_a_cauda(amb, capsys):
    amb.heygen(curto(amb))
    voz_sha = sha(amb.pj.voz_limpo)
    amb.pj.avatar_dir.mkdir(parents=True, exist_ok=True)
    J.gravar(amb.pj, "vid_pago_1", "avatar_v", "avatar_look_1", voz_sha)
    assert amb.avatar("--retomar") == 0
    assert "avatar completado" in capsys.readouterr().out
    assert sonda(amb.pj.avatar_mp4)["video"] == pytest.approx(VOZ_S + 0.5, abs=0.08)


def test_falta_de_mais_de_1_s_continua_erro_claro_e_o_avatar_nao_e_tocado(amb, capsys):
    origem = curto(amb, dur=1.5, nome="curtissimo.mp4")            # 1,52 s menor que a voz
    assert amb.avatar("--existente", str(origem)) == 1
    cap = capsys.readouterr()
    assert "avatar completado" not in cap.out
    assert "duração" in cap.err and "acima de 1.0 s" in cap.err
    assert sha(amb.pj.avatar_mp4) == sha(origem), "o avatar quebrado não é remendado"
    assert amb.conferencia()["resultado"] == "reprovada"


def test_avatar_curto_que_ja_estava_no_projeto_tambem_e_completado(amb, capsys):
    amb.pj.avatar_dir.mkdir(parents=True, exist_ok=True)
    criar_avatar(amb.pj.avatar_mp4, 3.0, tamanho="1080x1920")
    assert amb.avatar() == 0                                       # sem --existente: "o projeto já tem avatar"
    assert "avatar completado" in capsys.readouterr().out
    assert sonda(amb.pj.avatar_mp4)["video"] == pytest.approx(VOZ_S + 0.5, abs=0.08)


def test_o_look_aprovado_antes_de_um_avatar_novo_nao_vale_para_o_arquivo_completado_diferente(amb):
    """Trocar o avatar (com ou sem cauda) vence a aprovação: o look é do arquivo que o aluno OLHOU."""
    assert amb.avatar("--existente", str(curto(amb))) == 0
    assert amb.avatar("--aprovar-look") == 0
    outro = criar_avatar(amb.fontes / "outro.mp4", 2.9, tamanho="1080x1920")
    assert amb.avatar("--existente", str(outro), "--sobrescrever") == 0
    assert not looks.verificar("estudio", amb.estado).aprovado
