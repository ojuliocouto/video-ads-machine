#!/usr/bin/env python3
"""Gera avatar HeyGen com o engine Avatar V (API v3) a partir de VOZ REAL.

Wrapper fino: a lógica mora em scripts/avatar/ (heygen_cliente, listar, conferir, custo).
Avatar V é obrigatório: outro engine só com HEYGEN_ENGINE_OVERRIDE=<engine>, com aviso.

Uso: python3 scripts/heygen_av5.py gerar <voz> <avatar_id> <saida> [engine]
     python3 scripts/heygen_av5.py status <video_id> [saida]
Chave: HEYGEN_API_KEY (variável de ambiente ou o .env da raiz do repo).
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

from avatar.heygen_cliente import main_cli  # noqa: E402

if __name__ == "__main__":
    sys.exit(main_cli(sys.argv[1:], raiz=RAIZ))
