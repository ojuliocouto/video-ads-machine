"""Gerador do overlay do anúncio (motor v2). Wrapper fino: a lógica mora em `scripts/overlay/`.

Uso: python3 gen_ad_v2.py <config.json>
O formato do config e o pipeline estão em `overlay/gerar.py`.
"""
import sys

from overlay.fundo_claro import LIMIAR_FUNDO_CLARO, fundo_claro  # noqa: F401  (testes antigos importam daqui)
from overlay.gerar import main

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("uso: python3 gen_ad_v2.py <config.json>\n(o formato do config está em overlay/gerar.py)",
              file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1])
