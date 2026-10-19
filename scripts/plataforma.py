"""plataforma: o que muda de um sistema operacional para outro, em funções puras e sem efeito colateral no import.

O motor roda em macOS, Linux e Windows (Git Bash, Python e Node do Windows, sem WSL). Cada diferença de sistema mora aqui,
numa função só, em vez de um `if sys.platform` espalhado por 50 arquivos:

  eh_windows() / eh_mac()   em que sistema roda (os testes trocam `_sistema` para exercitar os dois ramos)
  venv_python(raiz)         o Python do `.venv` do repo (.venv/Scripts/python.exe no Windows, .venv/bin/python nos outros)
  hf_cmd(raiz)              o comando que roda o HyperFrames em qualquer sistema: ["node", <cli.js do pacote>]
  escapar_filtro(caminho)   um caminho que cabe dentro de um filtro do ffmpeg, em qualquer sistema
  abrir_pasta(caminho)      mostra a pasta no gerenciador de arquivos (Explorer, Finder, xdg-open)

POR QUE `node <cli.js>` E NÃO `node_modules/.bin/hyperframes`: o npm cria em `.bin` um script de shell sem extensão
(e um `.cmd`). No Windows, executar o de shell dá "%1 não é um aplicativo Win32 válido" (erro 193). Rodar o JS do pacote
pelo `node` funciona igual nos três sistemas, sem shell no meio e sem depender do que o npm gerou em `.bin`.

Só biblioteca padrão, Python 3.9.
"""
import json
import os
import subprocess
import sys
from pathlib import Path, PurePath, PureWindowsPath


class ErroHyperFrames(RuntimeError):
    """O HyperFrames do repo não está instalado, ou o pacote tem um formato que o motor não reconhece."""


def _sistema():
    """O identificador do sistema (`sys.platform`). Os testes trocam esta função para exercitar o outro ramo."""
    return sys.platform


def eh_windows():
    return _sistema().startswith("win")


def eh_mac():
    return _sistema() == "darwin"


def venv_python(raiz):
    """O Python do `.venv` de `raiz`. Não confere se existe: quem chama decide o que fazer sem ele."""
    venv = Path(raiz) / ".venv"
    if eh_windows():
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def hf_cmd(raiz):
    """O argv que roda o HyperFrames do repo: `["node", <o arquivo que o `bin` do pacote aponta>]`.

    O arquivo vem do `bin` do `node_modules/hyperframes/package.json` (a versão pinada usa `dist/cli.js`; versões
    novas usam `bin/hyperframes.mjs`), então a troca de layout do pacote não quebra o motor. Use assim:
    `subprocess.run(hf_cmd(raiz) + ["render", ...])`.

    Levanta ErroHyperFrames, com o conserto na mensagem, se o pacote não está instalado ou não tem um `bin` utilizável.
    """
    pacote = Path(raiz) / "node_modules" / "hyperframes"
    manifesto = pacote / "package.json"
    conserto = "rode `bash scripts/setup.sh` na raiz do repo"
    if not manifesto.is_file():
        raise ErroHyperFrames("o HyperFrames não está instalado: falta %s (%s)" % (manifesto, conserto))
    try:
        dados = json.loads(manifesto.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        raise ErroHyperFrames("não consegui ler %s (%s): %s" % (manifesto, erro, conserto))
    bin_ = dados.get("bin") if isinstance(dados, dict) else None
    if isinstance(bin_, dict):
        bin_ = bin_.get("hyperframes")
    if not isinstance(bin_, str) or not bin_.strip():
        raise ErroHyperFrames("o package.json do HyperFrames (%s) não declara o `bin` hyperframes: %s"
                              % (manifesto, conserto))
    cli = pacote / bin_.strip()
    if not cli.is_file():
        raise ErroHyperFrames("o arquivo que o `bin` do HyperFrames aponta não existe: %s (%s)" % (cli, conserto))
    return ["node", str(cli)]


# O ffmpeg lê o filtro em DUAS camadas, e cada uma tem os seus especiais (medido com o ffmpeg 8.1 em arquivos com cada
# um destes caracteres no nome; escapar numa camada só falha em `:`, `=`, `'` e `\`):
#   1. a opção do filtro (`movie=ARQUIVO`, `ass=ARQUIVO:fontsdir=PASTA`): `:` separa opções e `=` separa chave de valor;
#   2. o grafo de filtros: `,` encadeia filtros, `;` separa cadeias e `[` `]` envolvem os rótulos.
# `\` e `'` valem nas duas. Escapa-se a camada 1 e, no resultado, a camada 2 (a barra do primeiro escape também é escapada).
_ESPECIAIS_DA_OPCAO = ("\\", "'", ":", "=")
_ESPECIAIS_DO_GRAFO = ("\\", "'", "[", "]", ",", ";")


def _como_posix(caminho):
    """O caminho com `/` como separador. No Windows `\\` separa pastas; nos outros é uma letra legítima do nome."""
    if isinstance(caminho, PurePath):
        return caminho.as_posix()
    if eh_windows():
        return PureWindowsPath(str(caminho)).as_posix()
    return str(caminho)


def escapar_filtro(caminho):
    """O caminho pronto para ir dentro de um filtro do ffmpeg, SEM aspas em volta, em qualquer sistema.

    `C:\\Users\\João Silva\\a.ass` vira `C\\\\:/Users/João Silva/a.ass`: separador `/` (o ffmpeg aceita nos dois
    sistemas e a barra invertida do Windows seria lida como escape) e cada especial escapado nas duas camadas.

        vf = "ass=%s:fontsdir=%s" % (escapar_filtro(ass), escapar_filtro(pasta_de_fontes))

    Não usa aspas: aspas simples em volta mudam como o ffmpeg lê o escape. Não toca no disco."""
    texto = _como_posix(caminho)
    for especiais in (_ESPECIAIS_DA_OPCAO, _ESPECIAIS_DO_GRAFO):
        for c in especiais:
            texto = texto.replace(c, "\\" + c)
    return texto


def abrir_pasta(caminho):
    """Mostra a pasta no gerenciador de arquivos do sistema. True se abriu; False se não deu (sem erro, sem traceback).

    Abrir a pasta é conveniência: em servidor, CI ou terminal sem interface a falha não pode derrubar o fluxo."""
    try:
        if eh_windows():
            os.startfile(str(caminho))      # só existe no Windows
            return True
        ferramenta = "open" if eh_mac() else "xdg-open"
        r = subprocess.run([ferramenta, str(caminho)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        return r.returncode == 0
    except (OSError, AttributeError, subprocess.SubprocessError):
        return False
