"""Custo real de um job HeyGen: saldo da carteira antes e depois (GET /v3/users/me).

Doc (09/10/2026): https://developers.heygen.com/reference/get-current-user. A carteira vem em
data.wallet: remaining_balance (US$ numa conta pré-paga; créditos em Enterprise), currency
("usd" ou "credits") e auto_reload. Conta por plano (sem carteira) não tem saldo: o custo
fica desconhecido e o job roda do mesmo jeito.

`medir_job(cliente, job, pastas)` lê o saldo, roda `job()`, lê o saldo de novo e calcula:
    gasto = antes - depois;   por_minuto = gasto / minutos do vídeo (US$/min ou créditos/min)
`job()` devolve a duração em segundos (float) ou o dict de `gerar_avatar` (`duracao_s`).
O resultado é registrado em status.json do projeto (etapa `custo_avatar`):
  - ok          custo medido (ou desconhecido por falta de carteira)
  - bloqueado   o gasto passou do teto (`teto_usd`): a prova para e reporta
  - falhou      o job levantou erro; o saldo é medido do mesmo jeito (job falho também cobra) e o
                erro é repropagado
Se o saldo SUBIU (recarga automática no meio do job), a medida não é confiável: `por_minuto`
fica None e `confiavel` False. Pode haver defasagem de cobrança alguns segundos depois do fim do
job; a medida é o que a carteira mostrou na hora.
"""
from collections import namedtuple

from projeto import status

ETAPA = "custo_avatar"
Saldo = namedtuple("Saldo", "valor moeda recarga_automatica")


def _numero(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def ler_saldo(cliente):
    """Saldo atual: Saldo(valor|None, moeda, recarga_automatica)."""
    carteira = cliente.usuario().get("wallet")
    if not isinstance(carteira, dict):
        return Saldo(None, None, False)
    recarga = carteira.get("auto_reload")
    return Saldo(_numero(carteira.get("remaining_balance")), carteira.get("currency") or "usd",
                 bool(isinstance(recarga, dict) and recarga.get("enabled")))


def _duracao_s(retorno):
    if isinstance(retorno, dict):
        retorno = retorno.get("duracao_s")
    return _numero(retorno)


def _calcular(antes, depois, minutos, teto_usd):
    r = {"saldo_antes": antes.valor, "saldo_depois": depois.valor,
         "moeda": depois.moeda or antes.moeda, "minutos": minutos, "gasto": None,
         "por_minuto": None, "confiavel": True, "excedeu_teto": False, "teto": teto_usd}
    if antes.valor is None or depois.valor is None:
        return r
    gasto = round(antes.valor - depois.valor, 4)
    r["gasto"] = gasto
    if gasto < 0:
        r["confiavel"] = False        # o saldo subiu: recarga automática no meio do job
        return r
    if minutos and minutos > 0:
        r["por_minuto"] = round(gasto / minutos, 4)
    r["excedeu_teto"] = bool(teto_usd is not None and r["moeda"] == "usd" and gasto > teto_usd)
    return r


def medir_job(cliente, job, pastas, minutos=None, teto_usd=None, etapa=ETAPA):
    antes = ler_saldo(cliente)
    try:
        retorno = job()
    except Exception as erro:
        try:
            depois = ler_saldo(cliente)
        except Exception:      # a rede que derrubou o job pode derrubar a leitura: o erro original é o que vale
            depois = Saldo(None, None, False)
        r = _calcular(antes, depois, minutos, teto_usd)
        status.registrar(pastas, etapa, "falhou", "o job falhou: %s" % str(erro)[:200], detalhes=r)
        raise
    if minutos is None and _duracao_s(retorno) is not None:
        minutos = _duracao_s(retorno) / 60.0
    r = _calcular(antes, ler_saldo(cliente), minutos, teto_usd)
    if r["excedeu_teto"]:
        status.registrar(pastas, etapa, "bloqueado",
                         "o gasto de US$ %.2f passou do teto de US$ %.2f; a prova para aqui"
                         % (r["gasto"], teto_usd), detalhes=r)
    else:
        status.registrar(pastas, etapa, "ok", detalhes=r)
    return r
