"""Ouve o ponto que o gate de envelope acusou: lê a MESMA janela do bruto e do limpo, lado a lado.

A janela ganha 2 s de contexto dos dois lados (janela curta faz o ASR completar o que falta).

    python3 scripts/gravado/conferir_buracos.py IMG_0001:10.0:10.5 [IMG_0002:52.8:53.2 ...] [--projeto DIR]
"""
import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado import projeto as gp  # noqa: E402
from gravado import veredito  # noqa: E402

MARGEM_S = 2.0


def conferir(proj, take, ini, fim, leitor, margem=MARGEM_S):
    """(texto do bruto, texto do limpo) na janela [ini - margem, fim + margem]."""
    a, b = max(0.0, ini - margem), fim + margem
    bruto = veredito.exigir_arquivo(proj.wav(take), "o wav do bruto %s" % take)
    limpo = veredito.exigir_arquivo(proj.limpo(take), "o áudio limpo do take %s" % take)
    return leitor.texto(bruto, a, b), leitor.texto(limpo, a, b)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Bruto e limpo lado a lado numa janela.")
    ap.add_argument("pontos", nargs="+", help="TAKE:INI:FIM")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    a = ap.parse_args(argv)

    def fazer():
        proj = gp.carregar(a.projeto)
        leitor = proj.leitor()
        for ponto in a.pontos:
            try:
                take, ini, fim = ponto.split(":")
                ini, fim = float(ini), float(fim)
            except ValueError:
                raise veredito.InsumoInvalido("ponto inválido %r: use TAKE:INI:FIM, como IMG_0001:10.0:10.5" % ponto)
            bruto, limpo = conferir(proj, take, ini, fim, leitor)
            print("\n=== %s %.1f-%.1fs (janela %.1f-%.1fs) ===" % (take, ini, fim, max(0.0, ini - MARGEM_S), fim + MARGEM_S))
            print("  BRUTO: %r\n  LIMPO: %r" % (bruto, limpo))
    return veredito.ferramenta(fazer)


if __name__ == "__main__":
    sys.exit(main())
