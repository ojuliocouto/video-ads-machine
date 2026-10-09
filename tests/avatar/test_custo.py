"""W2.C: custo do job = saldo antes menos saldo depois (GET /v3/users/me). HTTP injetado."""
import json

import pytest

from avatar import custo as K
from avatar import heygen_cliente as H
from projeto import pastas, status

CHAVE = "hg_chave_secreta_de_teste_987654"


def usuario(saldo, moeda="usd", recarga=None, plano_wallet=True):
    wallet = {"remaining_balance": saldo, "currency": moeda, "auto_reload": recarga}
    corpo = {"data": {"billing_type": "wallet" if plano_wallet else "subscription",
                      "wallet": wallet if plano_wallet else None}}
    return (200, {}, json.dumps(corpo).encode("utf-8"))


class HttpFalso:
    def __init__(self, respostas):
        self.respostas, self.chamadas = list(respostas), []

    def __call__(self, metodo, url, headers, corpo, timeout):
        self.chamadas.append((metodo, url, dict(headers or {})))
        return self.respostas.pop(0)


def montar(tmp_path, saldos, **kw):
    http = HttpFalso([usuario(s, **kw) if not isinstance(s, tuple) else s for s in saldos])
    c = H.ClienteHeyGen(CHAVE, http=http, dormir=lambda s: None)
    proj = pastas.projeto("tres-horas", tmp_path / "_local")
    return c, http, proj


def test_ler_saldo_usa_v3_users_me():
    http = HttpFalso([usuario(12.43, recarga={"enabled": True, "threshold_usd": 5, "amount_usd": 12})])
    c = H.ClienteHeyGen(CHAVE, http=http, dormir=lambda s: None)
    s = K.ler_saldo(c)
    assert (s.valor, s.moeda, s.recarga_automatica) == (12.43, "usd", True)
    assert http.chamadas[0][:2] == ("GET", "https://api.heygen.com/v3/users/me")
    assert http.chamadas[0][2]["x-api-key"] == CHAVE


def test_conta_sem_carteira_devolve_saldo_none():
    http = HttpFalso([usuario(None, plano_wallet=False)])
    s = K.ler_saldo(H.ClienteHeyGen(CHAVE, http=http, dormir=lambda s: None))
    assert s.valor is None


def test_medir_job_calcula_dolar_por_minuto_e_registra_em_status(tmp_path):
    c, http, proj = montar(tmp_path, [12.00, 7.40])
    ordem = []

    def job():
        ordem.append("job")
        assert len(http.chamadas) == 1        # saldo lido ANTES do job
        return 60.0                           # duração do vídeo, em segundos

    r = K.medir_job(c, job, proj)
    assert len(http.chamadas) == 2 and ordem == ["job"]
    assert r["saldo_antes"] == 12.0 and r["saldo_depois"] == 7.4
    assert r["gasto"] == pytest.approx(4.6) and r["minutos"] == pytest.approx(1.0)
    assert r["por_minuto"] == pytest.approx(4.6) and r["moeda"] == "usd"
    assert r["confiavel"] is True and r["excedeu_teto"] is False
    s = status.ler(proj)
    assert s["atual"]["etapa"] == "custo_avatar" and s["atual"]["estado"] == "ok"
    d = s["atual"]["detalhes"]
    assert d["gasto"] == pytest.approx(4.6) and d["por_minuto"] == pytest.approx(4.6)
    assert d["saldo_antes"] == 12.0 and d["saldo_depois"] == 7.4


def test_minutos_vem_do_dict_do_job_ou_do_argumento(tmp_path):
    c, _, proj = montar(tmp_path, [10.0, 7.0])
    r = K.medir_job(c, lambda: {"duracao_s": 90.0, "video_id": "v"}, proj)
    assert r["minutos"] == pytest.approx(1.5) and r["por_minuto"] == pytest.approx(2.0)
    c, _, proj = montar(tmp_path, [10.0, 7.0])
    r = K.medir_job(c, lambda: None, proj, minutos=2.0)
    assert r["por_minuto"] == pytest.approx(1.5)


def test_teto_estourado_bloqueia_a_prova_e_diz_por_que(tmp_path):
    c, _, proj = montar(tmp_path, [20.0, 14.9])
    r = K.medir_job(c, lambda: 60.0, proj, teto_usd=5.0)
    assert r["excedeu_teto"] is True and r["gasto"] == pytest.approx(5.1)
    atual = status.ler(proj)["atual"]
    assert atual["estado"] == "bloqueado" and "teto" in atual["motivo"]


def test_gasto_igual_ao_teto_nao_estoura(tmp_path):
    c, _, proj = montar(tmp_path, [20.0, 15.0])
    assert K.medir_job(c, lambda: 60.0, proj, teto_usd=5.0)["excedeu_teto"] is False


def test_recarga_automatica_no_meio_torna_a_medida_nao_confiavel(tmp_path):
    c, _, proj = montar(tmp_path, [3.0, 10.5])           # o saldo SUBIU: recarregou durante o job
    r = K.medir_job(c, lambda: 60.0, proj)
    assert r["confiavel"] is False and r["por_minuto"] is None
    assert status.ler(proj)["atual"]["detalhes"]["confiavel"] is False


def test_conta_em_creditos_nao_inventa_dolar(tmp_path):
    c, _, proj = montar(tmp_path, [1000, 790], moeda="credits")
    r = K.medir_job(c, lambda: 60.0, proj)
    assert r["moeda"] == "credits" and r["gasto"] == 210 and r["por_minuto"] == pytest.approx(210)
    assert r["excedeu_teto"] is False


def test_sem_carteira_o_job_roda_e_o_custo_fica_desconhecido(tmp_path):
    http = HttpFalso([usuario(None, plano_wallet=False), usuario(None, plano_wallet=False)])
    c = H.ClienteHeyGen(CHAVE, http=http, dormir=lambda s: None)
    proj = pastas.projeto("tres-horas", tmp_path / "_local")
    r = K.medir_job(c, lambda: 60.0, proj)
    assert r["gasto"] is None and r["por_minuto"] is None
    assert status.ler(proj)["atual"]["estado"] == "ok"


def test_job_que_falha_ainda_mede_o_saldo_registra_falhou_e_repropaga(tmp_path):
    c, http, proj = montar(tmp_path, [9.0, 8.0])

    def job():
        raise H.HeyGenFalhou("render quebrou", codigo="X")

    with pytest.raises(H.HeyGenFalhou):
        K.medir_job(c, job, proj)
    assert len(http.chamadas) == 2
    atual = status.ler(proj)["atual"]
    assert atual["estado"] == "falhou" and "render quebrou" in atual["motivo"]
    assert atual["detalhes"]["gasto"] == pytest.approx(1.0)


def test_nada_do_custo_leva_a_chave(tmp_path):
    c, _, proj = montar(tmp_path, [12.0, 8.0])
    K.medir_job(c, lambda: 60.0, proj)
    texto = (proj.status_json).read_text(encoding="utf-8")
    assert CHAVE not in texto
