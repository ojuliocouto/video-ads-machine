#!/usr/bin/env python3
"""Fonte unica de verdade dos caminhos da fabrica de video.

## Por que existe

Ate 26/08/2026 o projeto vivia em dois diretorios e a linha
`V1 = Path.home() / "video-ads-machine"` estava copiada em 10 arquivos. Dois
problemas nasciam disso:

1. O CODIGO ficava fora do git. O motor todo morava em `_local/`, que e
   gitignorado porque guarda asset real de cliente. O ignore e por diretorio,
   entao levou o codigo junto: `produzir_ad.py`, `build_composite.py`,
   `auditar_audio.py`, nada disso tinha versao.
2. Mover qualquer coisa exigia editar 10 arquivos, e esquecer um so aparecia
   no meio de um render de 25 minutos.

Agora o caminho fisico e config, nao constante espalhada. Todo modulo importa
daqui, e qualquer um pode ser sobrescrito por variavel de ambiente.

## O desenho

    CODIGO   <repo>/scripts          codigo e gates (scripts/gates/), VERSIONADO
    ESTADO   <repo>/_local           configs, roteiros, mapas de insercao, logo, meta.json,
                                     _status.json, render-*   IGNORADO (e SEU, nao do repo)
    DADOS    <repo>/_local/dados     inputs/ e output/, a midia pesada   IGNORADO
    ASSETS   <repo>/assets           arte real (logo, wordmark)          IGNORADO

Primeira vez: `python3 scripts/init_local.py` cria o _local/ com a estrutura e exemplos.

Quem ja tinha o motor instalado antes mantem tudo como era: se `~/video-ads-machine`
existe, ele continua sendo o DADOS; se `~/video-ads-machine-2/_local` existe e o do repo
nao, continua sendo o ESTADO.

## Gates

Os gates (gate-ad.py, gate-colisao-texto.py, gate-contraste-legenda.py,
revisor-copy-ad.py, auditar_ad.py) vivem em scripts/gates/. `gate_script(nome)` acha o
script: primeiro no repo, depois (so por compatibilidade) em ~/.claude/scripts/.

## Sobrescrever

    VAM_DADOS=/outro/lugar python3 produzir_ad.py 25
    VAM_ESTADO=/outro/_local python3 produzir_ad.py 25
"""
import os
from pathlib import Path


def _env(nome, padrao):
    v = os.environ.get(nome)
    return Path(v).expanduser() if v else padrao


# --- codigo (este diretorio) -------------------------------------------------
CODIGO = Path(__file__).resolve().parent
RAIZ = CODIGO.parent                       # ~/video-ads-machine-2

# --- estado e renders (ignorado pelo git) ------------------------------------
# Compat: instalacao antiga do dono do motor (~/video-ads-machine-2/_local).
_ESTADO_LEGADO = Path.home() / "video-ads-machine-2" / "_local"
_ESTADO_PADRAO = RAIZ / "_local"
if not _ESTADO_PADRAO.exists() and _ESTADO_LEGADO.exists():
    _ESTADO_PADRAO = _ESTADO_LEGADO
ESTADO = _env("VAM_ESTADO", _ESTADO_PADRAO)
CONFIGS = ESTADO / "configs"
ROTEIROS = _env("VAM_ROTEIROS", ESTADO / "roteiros")

# --- midia pesada: roteiros, avatares, saidas --------------------------------
# VAM_V1_HOME e o nome antigo, aceito pra nao quebrar quem ja usava.
# Sem nada configurado, a midia mora DENTRO do _local do repo (gitignorado). O caminho
# antigo ~/video-ads-machine so vale se ele existir (instalacao antiga).
_DADOS_LEGADO = Path.home() / "video-ads-machine"
_DADOS_PADRAO = _DADOS_LEGADO if _DADOS_LEGADO.exists() else ESTADO / "dados"
DADOS = _env("VAM_DADOS", _env("VAM_V1_HOME", _DADOS_PADRAO))
INPUTS = _env("VAM_INPUTS", DADOS / "inputs")
OUTPUT = _env("VAM_OUTPUT", DADOS / "output")

# --- arte e tipografia -------------------------------------------------------
ASSETS = _env("VAM_ASSETS", RAIZ / "assets")
ASSETS_V1 = DADOS / "assets"               # som/, logos antigos
FONTS = _env("VAM_FONTS", RAIZ / "fonts")
FONTS_V1 = DADOS / "fonts"
TEMPLATES = RAIZ / "templates"

# Compatibilidade com o codigo que ainda fala "V1" e "V2L" internamente.
# Manter os nomes evitou reescrever 10 arquivos linha por linha na migracao:
# so a ORIGEM do valor mudou, o uso continua identico.
V1 = DADOS
V2 = RAIZ
V2L = ESTADO


# --- gates --------------------------------------------------------------------
GATES = CODIGO / "gates"


def gate_script(nome):
    """Caminho do script de gate `nome`, ou None se nao existir em lugar nenhum.

    Ordem: 1) scripts/gates/<nome> no repo; 2) ~/.claude/scripts/<nome> (so
    compatibilidade com quem ja tinha os gates la). O HOME e lido na hora da chamada,
    entao da pra testar com HOME falso.
    """
    for base in (GATES, Path.home() / ".claude" / "scripts"):
        p = base / nome
        if p.is_file():
            return p
    return None


def gate_excecoes():
    """Caminho do gate-excecoes.json: o do usuario (_local) manda, depois o do repo."""
    for base in (ESTADO, GATES, Path.home() / ".claude" / "scripts"):
        p = base / "gate-excecoes.json"
        if p.is_file():
            return p
    return None


# --- material do anuncio (e do usuario, vive em _local/) ------------------------
RENDER_MODELO = ESTADO / "render-reel-editorial"      # logo e meta.json do reel


def achar_logo():
    """Logo do anuncio: _local/render-reel-editorial/logo.png (ou *wordmark*.png ali)."""
    antigos = sorted(RENDER_MODELO.glob("*wordmark*.png")) if RENDER_MODELO.is_dir() else []
    return achar(RENDER_MODELO / "logo.png", *antigos, ASSETS / "logo.png")


def achar_meta():
    """meta.json do render: o do usuario em _local, senao o do template do repo."""
    return achar(RENDER_MODELO / "meta.json", TEMPLATES / "reel-editorial" / "meta.json")


def achar(*candidatos):
    """Primeiro caminho que existe, ou None. Pra asset que mudou de lugar."""
    for c in candidatos:
        if c and Path(c).expanduser().exists():
            return Path(c).expanduser()
    return None


if __name__ == "__main__":
    for nome in ("CODIGO", "GATES", "RAIZ", "ESTADO", "CONFIGS", "ROTEIROS", "DADOS",
                 "INPUTS", "OUTPUT", "ASSETS", "FONTS", "TEMPLATES"):
        p = globals()[nome]
        print(f"  {nome:10s} {'ok ' if Path(p).exists() else 'AUSENTE'} {p}")
