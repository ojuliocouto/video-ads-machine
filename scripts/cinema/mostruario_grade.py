#!/usr/bin/env python3
"""Mostruário dos presets de grade: UM quadro de um vídeo qualquer, quatro vezes lado a lado, um
painel por preset, com o nome escrito embaixo. É a prévia para o dono (ou o aluno) escolher a
grade olhando a própria imagem, em vez de adivinhar pelo nome.

    python3 scripts/cinema/mostruario_grade.py <video> <saida.png> [--t 3.2] [--altura 640]

O quadro passa pelo MESMO filtro que o `footage/grade_final` aplica (a cadeia do `cinema.grade`,
tags bt709 incluídas), então o painel é o que o vídeo final teria. Saída 0 gerou, 2 insumo
inválido (vídeo inexistente ou ilegível).
"""
import argparse
import json
import subprocess
import sys
from io import BytesIO
from pathlib import Path

if __name__ == "__main__":      # rodado direto: scripts/cinema/mostruario_grade.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from cinema import grade  # noqa: E402

PAINEL_ALTURA = 640         # altura do quadro de cada painel, em pixels
FAIXA_ALTURA = 56           # faixa escura com o nome do preset, embaixo de cada painel
FUNDO_FAIXA = (18, 18, 20)
TEXTO = (255, 255, 255)
_FONTES = ("/System/Library/Fonts/Helvetica.ttc",
           "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
           "/Library/Fonts/Arial.ttf",
           "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
           "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf")


class MostruarioFalhou(Exception):
    """O vídeo não existe ou o ffmpeg não conseguiu tirar o quadro."""


def legendas():
    """Os nomes escritos nos painéis, na ordem em que aparecem."""
    return list(grade.nomes())


def largura_do_painel(largura, altura, altura_painel=PAINEL_ALTURA):
    """Largura (par, o yuv420p exige) do painel para um vídeo `largura` x `altura`."""
    return max(2, int(round(largura * altura_painel / altura / 2.0)) * 2)


def _sonda(video):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height:format=duration", "-of", "json", str(video)],
                           capture_output=True, text=True)
    except FileNotFoundError:
        raise MostruarioFalhou("ffprobe ausente: instale o ffmpeg (brew install ffmpeg)")
    if r.returncode != 0:
        raise MostruarioFalhou("não consegui ler %s: %s" % (video, r.stderr.strip()[-200:] or "sem detalhe"))
    try:
        d = json.loads(r.stdout)
        v = d["streams"][0]
        return int(v["width"]), int(v["height"]), float(d["format"]["duration"])
    except (KeyError, IndexError, ValueError, TypeError):
        raise MostruarioFalhou("%s não tem faixa de vídeo legível" % video)


def _quadro(video, t, pw, altura, preset):
    vf = "scale=%d:%d,%s" % (pw, altura, grade.cadeia(preset))
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-ss", "%.3f" % t, "-i", str(video),
                        "-vf", vf, "-frames:v", "1", "-f", "image2pipe", "-c:v", "png", "pipe:1"],
                       capture_output=True)
    if r.returncode != 0 or not r.stdout:
        raise MostruarioFalhou("ffmpeg não tirou o quadro de %s em t=%.2f com o preset %s: %s"
                               % (video, t, preset, r.stderr.decode("utf-8", "replace").strip()[-200:]))
    return Image.open(BytesIO(r.stdout)).convert("RGB")


def _fonte(tamanho):
    for caminho in _FONTES:
        try:
            return ImageFont.truetype(caminho, tamanho)
        except (OSError, ValueError):
            continue
    try:
        return ImageFont.load_default(size=tamanho)         # Pillow 10.1 em diante
    except TypeError:
        return ImageFont.load_default()


def _escrever_nome(draw, caixa, texto):
    """Nome centrado na faixa; o corpo diminui até caber na largura do painel."""
    x0, y0, x1, y1 = caixa
    tamanho = max(8, int((y1 - y0) * 0.5))
    while True:
        fonte = _fonte(tamanho)
        e, c, d, b = draw.textbbox((0, 0), texto, font=fonte)
        if (d - e) <= (x1 - x0) - 8 or tamanho <= 8:
            break
        tamanho -= 1
    x = x0 + ((x1 - x0) - (d - e)) // 2 - e
    y = y0 + ((y1 - y0) - (b - c)) // 2 - c
    draw.text((x, y), texto, font=fonte, fill=TEXTO)


def gerar(video, saida, t=None, altura=PAINEL_ALTURA, presets=None):
    """Grava em `saida` (PNG) o quadro de `video` em `t` segundos (padrão: o meio) com cada preset
    de `presets` (padrão: todos), lado a lado, nome embaixo. Devolve o Path da saída."""
    video, saida = Path(video), Path(saida)
    if not video.is_file():
        raise MostruarioFalhou("vídeo não existe: %s" % video)
    nomes = [grade.validar(n) for n in (presets or grade.nomes())]
    larg, alt, dur = _sonda(video)
    if t is None:
        t = dur / 2.0
    t = max(0.0, min(float(t), max(0.0, dur - 0.1)))
    pw = largura_do_painel(larg, alt, altura)
    tela = Image.new("RGB", (pw * len(nomes), altura + FAIXA_ALTURA), FUNDO_FAIXA)
    draw = ImageDraw.Draw(tela)
    for k, nome in enumerate(nomes):
        tela.paste(_quadro(video, t, pw, altura, nome), (k * pw, 0))
        _escrever_nome(draw, (k * pw, altura, (k + 1) * pw, altura + FAIXA_ALTURA), nome)
    saida.parent.mkdir(parents=True, exist_ok=True)
    tela.save(saida, format="PNG")
    return saida


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mostruário dos presets de grade: um quadro, quatro looks.")
    ap.add_argument("video")
    ap.add_argument("saida", help="PNG de saída")
    ap.add_argument("--t", type=float, default=None, help="instante do quadro em segundos (padrão: o meio)")
    ap.add_argument("--altura", type=int, default=PAINEL_ALTURA, help="altura de cada painel (padrão %d)" % PAINEL_ALTURA)
    args = ap.parse_args(argv)
    try:
        saida = gerar(args.video, args.saida, t=args.t, altura=args.altura)
    except MostruarioFalhou as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        return 2
    print("Mostruário em %s" % saida)
    for nome in grade.nomes():
        print("  %-13s %s" % (nome, grade.descricao(nome)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
