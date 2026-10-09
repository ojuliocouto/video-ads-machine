"""Mostra os quadros imediatamente antes e depois de cada emenda do render (folha de contato).

Para ver o defeito que o áudio não mostra: o quadro rasgado no instante da troca, a posição do
rosto que pula. `montar_folha` é a grade rotulada que `linha_tempo.py` também usa; o rótulo é
desenhado com PIL, sem depender do `drawtext` do ffmpeg (que precisa de fonte e fontconfig).

    python3 scripts/gravado/cortes_render.py PECA [PECA ...] [--projeto DIR]     como A1_normal
"""
import argparse
import io
import math
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado import montar, veredito  # noqa: E402
from gravado import projeto as gp  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402

ANTES_S = -0.10
DEPOIS_S = 0.033
ALTURA_PADRAO = 330


def quadro_em(video, t, altura=ALTURA_PADRAO):
    """O quadro de `video` em `t` segundos como imagem PIL, na `altura` pedida."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-ss", "%.3f" % max(0.0, t), "-i", str(video),
                        "-frames:v", "1", "-vf", "scale=-2:%d" % altura, "-f", "image2pipe", "-vcodec", "png", "-"],
                       capture_output=True)
    if r.returncode != 0 or not r.stdout:
        raise InsumoInvalido("não consegui tirar o quadro de %.2fs de %s: %s"
                             % (t, video, r.stderr.decode("utf-8", "replace").strip()[-200:]))
    return Image.open(io.BytesIO(r.stdout)).convert("RGB")


def _fonte(tamanho):
    try:
        return ImageFont.load_default(size=tamanho)
    except TypeError:                        # Pillow antigo: só a fonte fixa
        return ImageFont.load_default()


def montar_folha(quadros, rotulos, colunas=6, altura=ALTURA_PADRAO, margem=5):
    """Grade rotulada (imagem PIL) com um quadro por célula, em `colunas` colunas."""
    quadros = list(quadros)
    if len(quadros) != len(list(rotulos)):
        raise ValueError("um rótulo por quadro: %d quadros e %d rótulos" % (len(quadros), len(list(rotulos))))
    if not quadros:
        raise ValueError("nenhum quadro para a folha")
    miniaturas = []
    for img in quadros:
        largura = max(1, int(round(img.width * altura / float(img.height))))
        miniaturas.append(img.resize((largura, altura)))
    celula_w = max(m.width for m in miniaturas)
    linhas = int(math.ceil(len(miniaturas) / float(colunas)))
    folha = Image.new("RGB", (colunas * (celula_w + margem) + margem, linhas * (altura + margem) + margem), "white")
    fonte = _fonte(max(12, altura // 12))
    for i, (m, rotulo) in enumerate(zip(miniaturas, rotulos)):
        x = margem + (i % colunas) * (celula_w + margem)
        y = margem + (i // colunas) * (altura + margem)
        folha.paste(m, (x, y))
        d = ImageDraw.Draw(folha)
        caixa = d.textbbox((x + 8, y + 8), str(rotulo), font=fonte)
        d.rectangle([caixa[0] - 4, caixa[1] - 3, caixa[2] + 4, caixa[3] + 3], fill=(0, 0, 0))
        d.text((x + 8, y + 8), str(rotulo), fill=(255, 255, 0), font=fonte)
    return folha


def cortes(proj, nome):
    """Grava `emendas_<peça>.png` com o antes e o DEPOIS de cada emenda. Devolve o caminho."""
    cod, desconto = proj.versoes()[nome]
    pontos = montar.emendas(montar.segmentos_do_ad(proj, cod, desconto), proj.accel)
    if not pontos:
        raise InsumoInvalido("a peça %s não tem emenda (um segmento só)" % nome)
    video = veredito.exigir_arquivo(proj.montado(nome), "a peça montada")
    quadros, rotulos = [], []
    for p in pontos:
        for deslocamento, rotulo in ((ANTES_S, "antes"), (DEPOIS_S, "DEPOIS")):
            quadros.append(quadro_em(video, p + deslocamento))
            rotulos.append("%ss %s" % (p, rotulo))
    destino = proj.base / ("emendas_%s.png" % nome)
    montar_folha(quadros, rotulos, colunas=min(6, len(quadros))).save(str(destino))
    return destino


def main(argv=None):
    ap = argparse.ArgumentParser(description="Quadros antes e depois de cada emenda.")
    ap.add_argument("pecas", nargs="+", help="nomes das peças, como A1_normal")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    a = ap.parse_args(argv)

    def fazer():
        proj = gp.carregar(a.projeto)
        for nome in a.pecas:
            if nome not in proj.versoes():
                raise InsumoInvalido("a peça %s não está no plano (tem: %s)" % (nome, ", ".join(proj.versoes())))
            print("%s -> %s" % (nome, cortes(proj, nome)))
    return veredito.ferramenta(fazer)


if __name__ == "__main__":
    sys.exit(main())
