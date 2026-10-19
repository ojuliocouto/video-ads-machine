"""Check: Node 22 ou superior e o HyperFrames do repo, rodado do jeito que o motor o roda.

O motor chama o HyperFrames por `plataforma.hf_cmd` (`node <cli.js do pacote>`), igual nos três sistemas: o script
`node_modules/.bin/hyperframes` do npm é de shell e no Windows dá o erro 193. Se o pacote não está instalado, o render
quebra no meio, então a ausência BARRA aqui, com o comando que resolve. Uma versão diferente da pinada no package.json
só avisa.
"""
import json
import re
from pathlib import Path

import plataforma

from ..doctor import FAIL, OK, WARN, Resultado

NOME = "node_hyperframes"
NODE_MINIMO = 22
SETUP = "bash scripts/setup.sh"
INSTALAR_NODE_MAC_LINUX = "macOS: brew install node@22 | outros: https://nodejs.org (versão 22 ou superior)"
INSTALAR_NODE_WINDOWS = "Windows: winget install -e --id OpenJS.NodeJS.LTS"


def instalar_node():
    """O comando que instala o Node LTS no sistema de quem roda."""
    return INSTALAR_NODE_WINDOWS if plataforma.eh_windows() else INSTALAR_NODE_MAC_LINUX


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
                         % (NODE_MINIMO, instalar_node()))
    rc, saida = amb.executar([node, "--version"], timeout=15)
    m = re.search(r"v?(\d+)\.\d+", saida or "") if rc == 0 else None
    if not m:
        return Resultado(NOME, FAIL, "não consegui ler a versão do Node",
                         "reinstale o Node %d (%s)" % (NODE_MINIMO, instalar_node()))
    if int(m.group(1)) < NODE_MINIMO:
        return Resultado(NOME, FAIL, "Node %s: o HyperFrames pede o %d ou superior"
                         % (m.group(0), NODE_MINIMO),
                         "atualize para o Node %d (%s)" % (NODE_MINIMO, instalar_node()))
    try:
        comando = plataforma.hf_cmd(amb.raiz)
    except plataforma.ErroHyperFrames as erro:
        return Resultado(NOME, FAIL, "HyperFrames: %s (o motor não renderiza sem ele)" % erro, SETUP)
    rc, saida = amb.executar([node] + comando[1:] + ["--version"], timeout=60)
    if rc != 0:
        return Resultado(NOME, FAIL, "o HyperFrames não executa: "
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
