"""Check: HEYGEN_API_KEY e o saldo da conta, em US$.

Sem a chave é WARN, não FAIL: o avatar fica desligado, mas o modo gravado (a voz e o rosto do
próprio aluno) e o one-shot não precisam de HeyGen. O saldo vem de `GET /v3/users/me` (o
`/v2/user/remaining_quota` é legado e sai do ar em 31/10/2026). Conta pré-paga ("wallet") é
em dólar; o que decide se um job passa é `wallet.remaining_balance`. A chave nunca aparece
na saída.
"""
import json

from ..doctor import FAIL, OK, WARN, ErroRede, Resultado

NOME = "heygen"
URL = "https://api.heygen.com/v3/users/me"
# Um anúncio de cerca de 42 s custa de US$ 3,2 a US$ 4,4 (medido). Abaixo disso, sem recarga
# automática, o job pode parar no meio.
SALDO_MINIMO = 5.0
ONDE_CONSEGUIR = "app.heygen.com, Settings, API"


def dolar(valor):
    return "US$ " + ("%.2f" % valor).replace(".", ",")


def _numero(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def checar(amb):
    chave = (amb.env.get("HEYGEN_API_KEY") or "").strip()
    if not chave:
        return Resultado(NOME, WARN,
                         "sem HEYGEN_API_KEY: o avatar fica desligado (o modo gravado e o "
                         "one-shot seguem sem HeyGen)",
                         "para usar avatar, crie a chave em %s e ponha HEYGEN_API_KEY=... no "
                         "arquivo .env" % ONDE_CONSEGUIR)
    try:
        status, corpo = amb.http_get(URL, headers={"X-Api-Key": chave, "Accept": "application/json"},
                                     timeout=15)
    except ErroRede as erro:
        return Resultado(NOME, WARN, "não consegui falar com a HeyGen para conferir a chave (%s)"
                         % erro, "confira a internet e rode o doctor de novo")
    if status in (401, 403):
        return Resultado(NOME, FAIL, "a HeyGen recusou a chave (HTTP %d)" % status,
                         "gere uma chave nova em %s e atualize o .env (chave de API, não "
                         "senha de login)" % ONDE_CONSEGUIR)
    try:
        dados = json.loads(corpo)
    except (TypeError, ValueError):
        dados = None
    if status != 200 or not isinstance(dados, dict):
        return Resultado(NOME, WARN, "não consegui ler o saldo da HeyGen (HTTP %s)" % status,
                         "tente de novo em alguns minutos; o build confere o saldo antes de gerar")
    conta = dados.get("data") if isinstance(dados.get("data"), dict) else dados
    carteira = conta.get("wallet") if isinstance(conta.get("wallet"), dict) else None
    saldo = _numero(carteira.get("remaining_balance")) if carteira else None
    if saldo is None:
        return Resultado(NOME, OK, "chave válida; a conta não é pré-paga em dólar (cobrança por "
                                   "plano), então não há saldo em dólar para mostrar")
    recarga = carteira.get("auto_reload")
    recarga = recarga if isinstance(recarga, dict) and recarga.get("enabled") else None
    if recarga:
        extra = "recarga automática ligada"
        valor = _numero(recarga.get("amount_usd"))
        if valor is not None:
            extra += " (repõe %s)" % dolar(valor)
        return Resultado(NOME, OK, "chave válida; saldo %s; %s" % (dolar(saldo), extra))
    if saldo < SALDO_MINIMO:
        return Resultado(NOME, WARN, "saldo %s, sem recarga automática: um anúncio custa de "
                         "US$ 3,2 a US$ 4,4" % dolar(saldo),
                         "recarregue em app.heygen.com (Settings, Billing) ou ligue a recarga "
                         "automática")
    return Resultado(NOME, OK, "chave válida; saldo %s" % dolar(saldo))
