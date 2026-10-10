"""W7.X item 1: a rede cai no poll e o job PAGO não se perde.

`vam avatar` grava avatar/job.json logo depois do submit; com job pendente, retoma o poll em vez de submeter outro
(rodar de novo pagaria de novo). O poll tem retry de rede (3 tentativas com backoff). HTTP, relógio e conferência
são falsos: zero rede, zero custo.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

import vam
from avatar import heygen_cliente as H
from avatar import job as J
from projeto import looks, pastas

RAIZ = Path(__file__).resolve().parent.parent.parent
CHAVE = "hg_chave_de_teste_w7x_123456"
URL_VIDEO = "https://cdn.heygen.test/video.mp4"


def resp(obj, status=200):
    return (status, {}, json.dumps(obj).encode("utf-8"))


class HeyGenFalso:
    """Um HeyGen de mentira com contadores. `consultas` é a fila de respostas do GET /v3/videos/{id}: cada item é
    uma tupla de resposta HTTP ou uma exceção a levantar (rede caída)."""

    def __init__(self, consultas):
        self.consultas = list(consultas)
        self.submits = 0
        self.uploads = 0
        self.gets_video = 0

    def __call__(self, metodo, url, headers, corpo, timeout):
        if url.endswith("/v3/assets"):
            self.uploads += 1
            return resp({"data": {"asset_id": "asset_1"}})
        if url.endswith("/v3/videos") and metodo == "POST":
            self.submits += 1
            return resp({"data": {"video_id": "vid_pago_%d" % self.submits}})
        if "/v3/videos/" in url:
            self.gets_video += 1
            r = self.consultas.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        if url.endswith("/v3/users/me"):
            return resp({"data": {"wallet": {"remaining_balance": 10.0, "currency": "usd"}}})
        if url == URL_VIDEO:
            return (200, {}, b"MP4-DO-AVATAR")
        raise AssertionError("chamada inesperada: %s %s" % (metodo, url))


PRONTO = resp({"data": {"status": "completed", "video_url": URL_VIDEO, "duration": 30}})
PROCESSANDO = resp({"data": {"status": "processing"}})
REDE_CAIU = H.HeyGenRede("sem rede ou HeyGen fora do ar (teste)")


@pytest.fixture
def ambiente(estado_vazio, monkeypatch, capsys):
    """Projeto de avatar pronto para `vam avatar`, o HeyGen falso plugado e a conferência aprovada."""
    dormidas = []

    def montar(consultas, falso=None):
        falso = falso or HeyGenFalso(consultas)
        cli = H.ClienteHeyGen(CHAVE, http=falso, dormir=dormidas.append, agora=lambda: 0.0)
        monkeypatch.setattr(H.ClienteHeyGen, "do_ambiente", classmethod(lambda cls, *a, **k: cli))
        return falso

    assert vam.main(["novo", "meu-ad", "--look", "estudio", "--sem-trilha", "teste do job", "--estado",
                     str(estado_vazio)]) == 0
    looks.adicionar("estudio", "avatar_look_1", "medio", estado=estado_vazio)
    pj = pastas.projeto("meu-ad", estado_vazio)
    pj.voz_dir.mkdir(parents=True, exist_ok=True)
    pj.voz_limpo.write_bytes(b"VOZ-LIMPA")
    from avatar import conferir
    monkeypatch.setattr(conferir, "conferir", lambda pj_, aspecto="9:16": {
        "resultado": "aprovada", "avatar": {"largura": 1080, "altura": 1920, "duracao_s": 30.0},
        "voz": {"duracao_s": 30.0}, "diferenca_duracao_s": 0.0, "fracao_util": 0.97})
    capsys.readouterr()

    def avatar(*extra):
        return vam.main(["avatar", "meu-ad", "--estado", str(estado_vazio)] + list(extra))

    return type("Amb", (), {"montar": staticmethod(montar), "avatar": staticmethod(avatar), "pj": pj,
                            "dormidas": dormidas})


def test_rede_cai_no_poll_guarda_o_job_pago_e_diz_como_retomar(ambiente, capsys):
    falso = ambiente.montar([REDE_CAIU, REDE_CAIU, REDE_CAIU])
    assert ambiente.avatar() == 2
    d = json.loads(J.caminho(ambiente.pj).read_text(encoding="utf-8"))
    assert d["video_id"] == "vid_pago_1" and d["engine"] == "avatar_v" and d["estado"] == "pendente"
    assert len(d["voz_sha256"]) == 64 and d["criado_em"]
    err = capsys.readouterr().err
    assert "--retomar" in err and "vid_pago_1" in err and "NÃO paga" in err
    assert falso.submits == 1 and falso.gets_video == 3          # 3 tentativas do poll, e só 1 submit
    assert not ambiente.pj.avatar_mp4.exists()


def test_vam_avatar_com_job_pendente_retoma_e_nao_submete_de_novo(ambiente, capsys):
    ambiente.montar([REDE_CAIU, REDE_CAIU, REDE_CAIU])
    assert ambiente.avatar() == 2
    falso2 = ambiente.montar([PRONTO])
    assert ambiente.avatar() == 0                                # SEM --retomar também retoma
    assert falso2.submits == 0 and falso2.uploads == 0           # nada pago de novo
    assert ambiente.pj.avatar_mp4.read_bytes() == b"MP4-DO-AVATAR"
    assert json.loads(J.caminho(ambiente.pj).read_text(encoding="utf-8"))["estado"] == "concluido"
    assert "nada é cobrado de novo" in capsys.readouterr().out


def test_retomar_explicito_segue_o_job(ambiente):
    ambiente.montar([REDE_CAIU, REDE_CAIU, REDE_CAIU])
    ambiente.avatar()
    falso2 = ambiente.montar([PROCESSANDO, PRONTO])
    assert ambiente.avatar("--retomar") == 0
    assert falso2.submits == 0 and ambiente.pj.avatar_mp4.is_file()


def test_retomar_sem_job_pendente_sai_com_dois(ambiente, capsys):
    ambiente.montar([])
    assert ambiente.avatar("--retomar") == 2
    assert "não há job" in capsys.readouterr().err


def test_poll_aguenta_um_tropeco_de_rede_sem_perder_o_job(ambiente):
    falso = ambiente.montar([REDE_CAIU, REDE_CAIU, PRONTO])      # a 3ª tentativa passa
    assert ambiente.avatar() == 0
    assert falso.submits == 1 and falso.gets_video == 3
    assert ambiente.dormidas[:2] == [H.BACKOFF_REDE_S, H.BACKOFF_REDE_S * 2]    # backoff 5 s e 10 s


def test_5xx_no_poll_tambem_tem_retry(ambiente):
    falso = ambiente.montar([resp({"error": {"message": "boom"}}, 503), PRONTO])
    assert ambiente.avatar() == 0 and falso.gets_video == 2 and falso.submits == 1


def test_erro_4xx_no_poll_nao_e_repetido(ambiente):
    falso = ambiente.montar([resp({"error": {"message": "nao achei", "code": "not_found"}}, 404)])
    assert ambiente.avatar() == 2
    assert falso.gets_video == 1


def test_job_que_o_heygen_falhou_libera_um_submit_novo(ambiente):
    ambiente.montar([resp({"data": {"status": "failed", "failure_code": "x", "failure_message": "y"}})])
    assert ambiente.avatar() == 2
    assert json.loads(J.caminho(ambiente.pj).read_text(encoding="utf-8"))["estado"] == "falhou"
    falso2 = ambiente.montar([PRONTO])
    assert ambiente.avatar() == 0 and falso2.submits == 1        # agora sim, um job novo


def test_job_de_outra_voz_nao_e_retomado(ambiente, capsys):
    ambiente.montar([REDE_CAIU, REDE_CAIU, REDE_CAIU])
    ambiente.avatar()
    ambiente.pj.voz_limpo.write_bytes(b"OUTRA-VOZ")
    falso2 = ambiente.montar([PRONTO])
    assert ambiente.avatar("--retomar") == 2                     # o pendente era da voz antiga
    assert falso2.submits == 0
    assert ambiente.avatar() == 0 and falso2.submits == 1        # sem --retomar vai job novo, com aviso
    assert "outra voz" in capsys.readouterr().out


def test_job_json_e_gravado_antes_do_poll(ambiente):
    visto = {}

    class Espiao(HeyGenFalso):
        def __call__(self, metodo, url, headers, corpo, timeout):
            if "/v3/videos/" in url and "job" not in visto:
                visto["job"] = J.ler(ambiente.pj)
            return super().__call__(metodo, url, headers, corpo, timeout)

    falso = ambiente.montar(None, falso=Espiao([PRONTO]))
    assert ambiente.avatar() == 0
    assert visto["job"] and visto["job"]["video_id"] == "vid_pago_1"


def test_heygen_cliente_roda_direto_e_mostra_o_uso():
    r = subprocess.run([sys.executable, str(RAIZ / "scripts" / "avatar" / "heygen_cliente.py")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 2 and "gerar" in r.stderr and "Traceback" not in r.stderr
