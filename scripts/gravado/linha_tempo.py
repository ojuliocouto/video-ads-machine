"""Folha de contato temporal de um take: N instantes, cada um rotulado com o segundo.

Ler o take INTEIRO antes do plano, inclusive a ação visual: o que o áudio condena (uma mochila
abrindo, uma mão na frente) pode estar no vídeo, e quadros espaçados demais pulam o trecho.

    python3 scripts/gravado/linha_tempo.py TAKE T1 T2 T3 ... [--projeto DIR]
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
from gravado.cortes_render import montar_folha, quadro_em  # noqa: E402


def folha(video, tempos, destino, colunas=4, altura=360):
    quadros = [quadro_em(video, t, altura) for t in tempos]
    montar_folha(quadros, ["%ss" % t for t in tempos], colunas=colunas, altura=altura).save(str(destino))
    return Path(destino)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Folha de contato temporal de um take.")
    ap.add_argument("take", help="o take, sem extensão")
    ap.add_argument("tempos", nargs="+", type=float, help="os instantes, em segundos")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    a = ap.parse_args(argv)

    def fazer():
        proj = gp.carregar(a.projeto)
        try:
            video = proj.bruto(a.take)
        except FileNotFoundError as e:
            raise veredito.InsumoInvalido(str(e))
        destino = folha(video, a.tempos, proj.base / ("tl_%s.png" % a.take))
        print("%s: %d quadros" % (destino.name, len(a.tempos)))
    return veredito.ferramenta(fazer)


if __name__ == "__main__":
    sys.exit(main())
