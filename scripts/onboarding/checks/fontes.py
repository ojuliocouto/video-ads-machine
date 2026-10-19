"""Check: as fontes que os templates pedem existem na pasta de fontes.

Os templates declaram `url("fonts/<arquivo>.woff2")`. Fonte ausente não dá erro no render: o
navegador cai numa fonte padrão e o anúncio sai com a tipografia errada. O doctor lê os
templates, junta os arquivos pedidos e confere um por um.

Existir não basta: as fontes dos templates são symlinks do git, e num clone no Windows sem `core.symlinks` o git grava
cada link como um arquivo de TEXTO pequeno com o caminho do alvo. O Chromium ignora esse arquivo sem erro e o anúncio
sai com a fonte do sistema. Por isso o check também exige que cada .woff2 seja um woff2 de verdade: mais de 1 KB e a
assinatura `wOF2` nos 4 primeiros bytes.
"""
import re
from pathlib import Path

from ..doctor import FAIL, OK, Resultado

NOME = "fontes"
RESTAURAR = "restaure a pasta fonts/ do repositório (git checkout -- fonts) ou clone de novo"
SYMLINKS = ("ative os symlinks do git (git config core.symlinks true; no Windows, ligue o Modo de Desenvolvedor) e "
            "faça o clone de novo do repositório")
MAGIA_WOFF2 = b"wOF2"
TAMANHO_MINIMO = 1024

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


def woff2_invalidos(amb, pasta):
    """Os .woff2 que não são woff2 de verdade (menores que 1 KB ou sem a assinatura `wOF2`), como `caminho (N bytes)`.

    Confere a pasta de fontes e a `fonts/` de cada template (`templates/*/fonts`, onde os links do git moram)."""
    pastas = [pasta] + sorted(p for p in (Path(amb.raiz) / "templates").glob("*/fonts") if p.is_dir())
    ruins = []
    for p in pastas:
        for arquivo in sorted(p.glob("*.woff2")):
            try:
                tamanho = arquivo.stat().st_size
                with open(str(arquivo), "rb") as f:
                    inicio = f.read(4)
            except OSError:
                tamanho, inicio = 0, b""
            if tamanho <= TAMANHO_MINIMO or inicio != MAGIA_WOFF2:
                ruins.append("%s (%d bytes)" % (_mostrar(arquivo, amb.raiz).replace("\\", "/"), tamanho))
    return ruins


def _reprovar_woff2(ruins):
    lista = ", ".join(ruins[:3]) + (" e mais %d" % (len(ruins) - 3) if len(ruins) > 3 else "")
    return Resultado(NOME, FAIL, "%d fonte(s) .woff2 não são woff2 de verdade (é o symlink do git que virou texto): %s"
                     % (len(ruins), lista), SYMLINKS)


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
        ruins = woff2_invalidos(amb, pasta)
        if ruins:
            return _reprovar_woff2(ruins)
        return Resultado(NOME, OK, "%d arquivo(s) em %s (os templates não declaram fontes)"
                         % (len(existentes), mostra))
    faltam = [f for f in pedidas if not (pasta / f).is_file()]
    if faltam:
        lista = ", ".join(faltam[:3]) + (" e mais %d" % (len(faltam) - 3) if len(faltam) > 3 else "")
        return Resultado(NOME, FAIL, "faltam %d de %d fontes que os templates pedem: %s"
                         % (len(faltam), len(pedidas), lista), RESTAURAR)
    ruins = woff2_invalidos(amb, pasta)
    if ruins:
        return _reprovar_woff2(ruins)
    return Resultado(NOME, OK, "%d fontes dos templates presentes em %s" % (len(pedidas), mostra))
