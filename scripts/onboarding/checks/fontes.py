"""Check: as fontes que os templates pedem existem na pasta de fontes.

Os templates declaram `url("fonts/<arquivo>.woff2")`. Fonte ausente não dá erro no render: o
navegador cai numa fonte padrão e o anúncio sai com a tipografia errada. O doctor lê os
templates, junta os arquivos pedidos e confere um por um.
"""
import re
from pathlib import Path

from ..doctor import FAIL, OK, Resultado

NOME = "fontes"
RESTAURAR = "restaure a pasta fonts/ do repositório (git checkout -- fonts) ou clone de novo"

_REFERENCIA = re.compile(r"fonts/([A-Za-z0-9_.\-]+\.(?:woff2|woff|ttf|otf))")


def pasta_de_fontes(amb):
    """VAM_FONTS manda (igual ao caminhos.py); senão <repo>/fonts."""
    outra = (amb.env.get("VAM_FONTS") or "").strip()
    return Path(outra).expanduser() if outra else Path(amb.raiz) / "fonts"


def _mostrar(pasta, raiz):
    """Caminho curto: relativo ao repo quando está dentro dele."""
    try:
        return str(Path(pasta).relative_to(raiz))
    except ValueError:
        return str(pasta)


def fontes_pedidas(raiz):
    pedidas = set()
    for template in sorted((Path(raiz) / "templates").glob("*/index.html")):
        try:
            pedidas.update(_REFERENCIA.findall(template.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    return sorted(pedidas)


def checar(amb):
    pasta = pasta_de_fontes(amb)
    if not pasta.is_dir():
        return Resultado(NOME, FAIL, "a pasta de fontes não existe: %s" % pasta, RESTAURAR)
    pedidas = fontes_pedidas(amb.raiz)
    mostra = _mostrar(pasta, amb.raiz)
    if not pedidas:
        existentes = [p for p in pasta.iterdir() if p.is_file()]
        if not existentes:
            return Resultado(NOME, FAIL, "a pasta de fontes está vazia: %s" % pasta, RESTAURAR)
        return Resultado(NOME, OK, "%d arquivo(s) em %s (os templates não declaram fontes)"
                         % (len(existentes), mostra))
    faltam = [f for f in pedidas if not (pasta / f).is_file()]
    if faltam:
        lista = ", ".join(faltam[:3]) + (" e mais %d" % (len(faltam) - 3) if len(faltam) > 3 else "")
        return Resultado(NOME, FAIL, "faltam %d de %d fontes que os templates pedem: %s"
                         % (len(faltam), len(pedidas), lista), RESTAURAR)
    return Resultado(NOME, OK, "%d fontes dos templates presentes em %s" % (len(pedidas), mostra))
