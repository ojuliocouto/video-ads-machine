"""Tira o fundo de uma caixinha entregue sobre fundo chapado (preto, por padrão).

NÃO usa key por cor: isso comeria o texto escuro de dentro da caixinha. Usa preenchimento a
partir das BORDAS, porque o fundo é contíguo às bordas e o conteúdo escuro de dentro não é. Cantos
arredondados saem com alpha suave.

    python3 scripts/gravado/extrair_caixinha.py caixinha.png --saida caixinha_alpha.png [--recortar]
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import binary_fill_holes, gaussian_filter, label

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado import veredito  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402

TOLERANCIA = 34
SUAVIZAR = 1.2


def extrair(src, tol=TOLERANCIA, suavizar=SUAVIZAR):
    """(imagem RGBA com o fundo transparente, caixa (x0, y0, x1, y1), fração da imagem que é caixa)."""
    img = Image.open(src).convert("RGB")
    a = np.asarray(img).astype(np.int16)
    lum = a.max(axis=2)                          # canal mais claro: pega cor sobre preto
    rot, _ = label(lum <= tol)                   # componentes que parecem fundo
    bordas = set(rot[0, :]) | set(rot[-1, :]) | set(rot[:, 0]) | set(rot[:, -1])
    bordas.discard(0)
    fundo = np.isin(rot, list(bordas))           # só o que toca a borda é fundo
    conteudo = binary_fill_holes(~fundo)         # o texto escuro interno volta a ser conteúdo
    alpha = (conteudo * 255).astype(np.uint8)
    if suavizar:
        alpha = np.clip(gaussian_filter(alpha.astype(np.float32), suavizar), 0, 255).astype(np.uint8)
    ys, xs = np.where(conteudo)
    if not len(ys):
        raise InsumoInvalido("não achei conteúdo em %s: a imagem parece toda de fundo" % src)
    caixa = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    return (Image.fromarray(np.dstack([np.asarray(img), alpha]).astype(np.uint8), "RGBA"), caixa,
            float(conteudo.sum()) / conteudo.size)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Tira o fundo chapado de uma caixinha.")
    ap.add_argument("entrada")
    ap.add_argument("--saida", required=True)
    ap.add_argument("--tolerancia", type=int, default=TOLERANCIA)
    ap.add_argument("--recortar", action="store_true", help="salva só o retângulo da caixinha")
    a = ap.parse_args(argv)

    def fazer():
        veredito.exigir_arquivo(a.entrada, "a imagem da caixinha")
        img, caixa, frac = extrair(a.entrada, a.tolerancia)
        if a.recortar:
            img = img.crop(caixa)
        img.save(a.saida)
        x0, y0, x1, y1 = caixa
        print("%s -> %s" % (Path(a.entrada).name, Path(a.saida).name))
        print("  caixinha em x %d a %d, y %d a %d  (%d x %d px)" % (x0, x1, y0, y1, x1 - x0, y1 - y0))
        print("  ocupa %.1f%% da imagem; o resto virou transparente" % (frac * 100))
    return veredito.ferramenta(fazer)


if __name__ == "__main__":
    sys.exit(main())
