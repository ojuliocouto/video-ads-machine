"""Check: Node 22 ou superior e o binário do HyperFrames onde o motor o procura.

O motor chama `<repo>/node_modules/.bin/hyperframes` (build_composite, gen_ad_v2,
prancha_direcao). Se ele não existe, o render quebra no meio, então a ausência BARRA aqui,
com o comando que resolve. Uma versão diferente da pinada no package.json só avisa.
"""
import json
import os
import re
from pathlib import Path

from ..doctor import FAIL, OK, WARN, Resultado

NOME = "node_hyperframes"
NODE_MINIMO = 22
SETUP = "bash scripts/setup.sh"
INSTALAR_NODE = "macOS: brew install node@22 | outros: https://nodejs.org (versão 22 ou superior)"


def versao_pinada(raiz):
    """A versão do hyperframes que o package.json pina (sem ^ ou ~), ou None."""
    try:
        dados = json.loads((Path(raiz) / "package.json").read_text(encoding="utf-8"))
        bruta = (dados.get("dependencies") or {}).get("hyperframes")
    except (OSError, ValueError, AttributeError):
        return None
    if not bruta:
        return None
    m = re.search(r"\d+\.\d+\.\d+", str(bruta))
    return m.group(0) if m else None


def versao_instalada(raiz):
    try:
        dados = json.loads((Path(raiz) / "node_modules" / "hyperframes" / "package.json")
                           .read_text(encoding="utf-8"))
        return str(dados.get("version") or "") or None
    except (OSError, ValueError, AttributeError):
        return None


def checar(amb):
    node = amb.which("node")
    if not node:
        return Resultado(NOME, FAIL, "Node não encontrado no PATH (o HyperFrames pede Node %d "
                         "ou superior)" % NODE_MINIMO, "instale o Node %d (%s)"
                         % (NODE_MINIMO, INSTALAR_NODE))
    rc, saida = amb.executar([node, "--version"], timeout=15)
    m = re.search(r"v?(\d+)\.\d+", saida or "") if rc == 0 else None
    if not m:
        return Resultado(NOME, FAIL, "não consegui ler a versão do Node",
                         "reinstale o Node %d (%s)" % (NODE_MINIMO, INSTALAR_NODE))
    if int(m.group(1)) < NODE_MINIMO:
        return Resultado(NOME, FAIL, "Node %s: o HyperFrames pede o %d ou superior"
                         % (m.group(0), NODE_MINIMO),
                         "atualize para o Node %d (%s)" % (NODE_MINIMO, INSTALAR_NODE))
    binario = Path(amb.raiz) / "node_modules" / ".bin" / "hyperframes"
    if not binario.is_file() or not os.access(str(binario), os.X_OK):
        return Resultado(NOME, FAIL, "o binário do HyperFrames não está em "
                         "node_modules/.bin (o motor não renderiza sem ele)", SETUP)
    rc, saida = amb.executar([str(binario), "--version"], timeout=60)
    if rc != 0:
        return Resultado(NOME, FAIL, "o binário do HyperFrames não executa: "
                         + (saida or "").strip()[-200:], SETUP)
    instalada = versao_instalada(amb.raiz)
    if not instalada:
        achou = re.search(r"\d+\.\d+\.\d+", saida or "")
        instalada = achou.group(0) if achou else None
    pinada = versao_pinada(amb.raiz)
    if pinada and instalada and instalada != pinada:
        return Resultado(NOME, WARN, "HyperFrames %s instalado, mas o package.json pina %s"
                         % (instalada, pinada), SETUP)
    return Resultado(NOME, OK, "Node %s; HyperFrames %s" % (m.group(0), instalada or "instalado"))
