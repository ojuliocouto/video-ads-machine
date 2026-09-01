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

    CODIGO   ~/video-ads-machine-2/scripts     codigo, VERSIONADO
    ESTADO   ~/video-ads-machine-2/_local      _status.json, configs, render-*  IGNORADO
    DADOS    ~/video-ads-machine               inputs/ e output/, a midia pesada
    ASSETS   ~/video-ads-machine-2/assets      arte real de cliente  IGNORADO

DADOS continua apontando pro diretorio antigo de proposito: sao 12GB de midia
e os scripts do Claude (gate-ad.py, revisor-copy-ad.py, auditar_ad.py) leem
`~/video-ads-machine/inputs` e `/output` direto. Mover isso quebraria eles sem
ganho nenhum: midia nao entra em git de qualquer forma. O que precisava sair
de la era o CODIGO, e esse saiu.

## Sobrescrever

    VAM_DADOS=/outro/lugar python3 produzir_ad.py 25
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
ESTADO = _env("VAM_ESTADO", RAIZ / "_local")
CONFIGS = ESTADO / "configs"

# --- midia pesada: roteiros, avatares, saidas --------------------------------
# VAM_V1_HOME e o nome antigo, aceito pra nao quebrar quem ja usava.
DADOS = _env("VAM_DADOS", _env("VAM_V1_HOME", Path.home() / "video-ads-machine"))
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


def achar(*candidatos):
    """Primeiro caminho que existe, ou None. Pra asset que mudou de lugar."""
    for c in candidatos:
        if c and Path(c).expanduser().exists():
            return Path(c).expanduser()
    return None


if __name__ == "__main__":
    for nome in ("CODIGO", "RAIZ", "ESTADO", "CONFIGS", "DADOS", "INPUTS",
                 "OUTPUT", "ASSETS", "FONTS", "TEMPLATES"):
        p = globals()[nome]
        print(f"  {nome:10s} {'ok ' if Path(p).exists() else 'AUSENTE'} {p}")
