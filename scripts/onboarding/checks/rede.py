"""Check: o render não vai quebrar por falta de internet.

Os templates carregam o GSAP por CDN. O `setup.sh` guarda uma cópia em
`templates/_vendor/gsap.min.js`. Com a cópia, o render não depende de rede e este check nem
abre conexão. Sem a cópia, confere se a CDN responde: se responde, avisa (funciona hoje, pode
quebrar amanhã); se não, o render vai falhar e isso BARRA.
"""
import re
from pathlib import Path

from ..doctor import FAIL, OK, WARN, ErroRede, Resultado

NOME = "rede"
SETUP = "bash scripts/setup.sh"
GSAP_PADRAO = "https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"
TAMANHO_MINIMO = 1000       # o gsap.min.js de verdade tem dezenas de KB; menos que isso é lixo

_CDN = re.compile(r"https://cdn\.jsdelivr\.net/npm/gsap@[0-9.]+/dist/gsap\.min\.js")


def url_do_gsap(raiz):
    """A URL que os templates usam (a versão vem deles), ou a padrão."""
    for template in sorted((Path(raiz) / "templates").glob("*/index.html")):
        try:
            m = _CDN.search(template.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        if m:
            return m.group(0)
    return GSAP_PADRAO


def gsap_local(raiz):
    return Path(raiz) / "templates" / "_vendor" / "gsap.min.js"


def checar(amb):
    local = gsap_local(amb.raiz)
    try:
        tamanho = local.stat().st_size
    except OSError:
        tamanho = 0
    if tamanho >= TAMANHO_MINIMO:
        return Resultado(NOME, OK, "GSAP local em templates/_vendor: o render não depende de rede")
    url = url_do_gsap(amb.raiz)
    try:
        status, _ = amb.http_get(url, timeout=10, metodo="HEAD")
    except ErroRede as erro:
        return Resultado(NOME, FAIL, "sem cópia local do GSAP e a CDN não responde (%s): o "
                         "render vai falhar" % erro,
                         "conecte à internet e rode " + SETUP + " para guardar o GSAP local")
    if 200 <= status < 400:
        return Resultado(NOME, WARN, "sem cópia local do GSAP: o render depende da CDN (hoje "
                         "ela responde)", "rode " + SETUP + " (guarda o GSAP em templates/_vendor)")
    return Resultado(NOME, FAIL, "sem cópia local do GSAP e a CDN respondeu HTTP %d para %s"
                     % (status, url), "rode " + SETUP + " com internet para guardar o GSAP local")
