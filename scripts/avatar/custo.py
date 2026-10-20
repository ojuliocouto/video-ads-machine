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
import json
import math
from collections import namedtuple
from pathlib import Path

from avatar.heygen_cliente import executar_real
from projeto import status

ETAPA = "custo_avatar"
Saldo = namedtuple("Saldo", "valor moeda recarga_automatica")

# Preço do avatar do HeyGen (Avatar V, 1080p, conta pré-paga em dólar) por minuto de VOZ, em US$. É a ÚNICA constante de
# preço da skill: a estimativa de `vam avatar`, a duração máxima que cabe no teto e os números da documentação (cerca de
# US$ 7 por minuto) saem daqui. Fonte: job real de 20/10/2026, o ensaio da aula: 27,6 s
# de voz (0,459 min) custaram US$ 3,25 (saldo de US$ 16,65 para US$ 13,40), ou US$ 7,08 por minuto, medidos por este
# módulo e gravados em avatar/custo.json. A doc antiga dizia US$ 3,20 a 4,40 por minuto (régua de 200 a 227 créditos por
# minuto, 60 créditos por dólar) e estava quase pela metade. Se o HeyGen mudar o preço, o custo REAL de cada job continua
# medido pela carteira; só esta constante e o texto dos documentos precisam acompanhar.
CUSTO_USD_POR_MINUTO = 7.10


class CustoAcimaDoTeto(Exception):
    """A estimativa do job passa do teto: recusa ANTES de gastar. `maxima_s` é a voz mais longa que cabe no teto."""

    def __init__(self, duracao_s, estimativa_usd, teto_usd):
        self.duracao_s, self.estimativa_usd, self.teto_usd = duracao_s, estimativa_usd, teto_usd
        self.maxima_s = duracao_maxima_s(teto_usd)
        sugerido = int(math.ceil(round(estimativa_usd, 2)))
        super().__init__("a voz tem %s s e o avatar custaria cerca de US$ %s (US$ %s por minuto), acima do teto de "
                         "US$ %s por job. Nada foi gasto. Neste teto a voz cabe até %d s: encurte a fala e rode "
                         "vam audio de novo, ou rode vam avatar com --teto-usd %d para pagar esta voz"
                         % (segundos(duracao_s), dolar(estimativa_usd), dolar(CUSTO_USD_POR_MINUTO), dolar(teto_usd),
                            int(self.maxima_s), sugerido))


def dolar(valor):
    """Valor em dólar como o aluno lê: duas casas e vírgula (7,10)."""
    return ("%.2f" % valor).replace(".", ",")


def segundos(valor):
    """Duração como o aluno lê: uma casa e vírgula (27,6)."""
    return ("%.1f" % valor).replace(".", ",")


def estimar_usd(duracao_s):
    """Custo estimado, em US$, de um avatar para uma voz de `duracao_s` segundos."""
    return duracao_s / 60.0 * CUSTO_USD_POR_MINUTO


def duracao_maxima_s(teto_usd):
    """A voz mais longa, em segundos, que cabe no teto."""
    return teto_usd / CUSTO_USD_POR_MINUTO * 60.0


def exigir_que_caiba(duracao_s, teto_usd):
    """Estimativa em US$ se cabe no teto (comparada em centavos); CustoAcimaDoTeto se não cabe."""
    estimativa = estimar_usd(duracao_s)
    if round(estimativa, 2) > teto_usd:
        raise CustoAcimaDoTeto(duracao_s, estimativa, teto_usd)
    return estimativa


def duracao_da_voz(voz, executar=None):
    """Duração da voz limpa em segundos (ffprobe), ou None se o arquivo não existe ou o ffprobe não lê."""
    executar = executar or executar_real
    voz = Path(voz)
    if not voz.is_file():
        return None
    rc, saida = executar(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(voz)])
    try:
        duracao = float(json.loads(saida)["format"]["duration"])
    except (ValueError, KeyError, TypeError):
        return None
    return duracao if rc == 0 and duracao > 0 else None


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
