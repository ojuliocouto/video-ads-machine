"""Texto de tela sintético para os testes de contraste (W5.X): o overlay RGBA e o quadro composto.

Desenha com as fontes do repo (Inter 800 da legenda, PT Serif 400 como texto fino) e compõe como o build compõe:
overlay com alfa por cima da imagem. Tudo em numpy, sem ffmpeg: os testes do invariante rodam em milissegundos.
Quem precisa de vídeo (o gate pela CLI) usa `gravar_video` e `gravar_overlay`, que passam os quadros pelo ffmpeg.
"""
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

RAIZ = Path(__file__).resolve().parent.parent.parent
FONTE_LEGENDA = RAIZ / "fonts" / "inter-800.ttf"
FONTE_FINA = RAIZ / "fonts" / "pt-serif-400.ttf"


def fundo(alt, larg, cor):
    """Fundo liso RGB (cor: int cinza ou tupla)."""
    if isinstance(cor, int):
        cor = (cor, cor, cor)
    return np.tile(np.array(cor, dtype=np.uint8), (alt, larg, 1))


def pagina(alt, larg, papel=238, tinta=40, passo=18, espessura=4):
    """Página clara com linhas de texto escuras (a gravação de tela de um navegador)."""
    q = fundo(alt, larg, papel)
    for y in range(0, alt, passo):
        q[y:y + espessura, 40:larg - 40] = tinta
    return q


def vazio(alt, larg):
    return np.zeros((alt, larg, 4), dtype=np.uint8)


def _camada_texto(alt, larg, texto, xy, fonte, corpo, cor, alfa=1.0, contorno=0, cor_contorno=(6, 7, 12),
                  alfa_contorno=0.92, ancora="mm"):
    """Uma camada RGBA com o texto e o contorno como o CSS desenha (-webkit-text-stroke com paint-order stroke fill):
    o traço é um ANEL centrado na borda da letra, de `contorno` px para cada lado, e o preenchimento cobre a metade de
    dentro. O miolo da letra não tem traço embaixo (a camada apagada a 0,70 é 0,70 de verdade)."""
    from scipy import ndimage as ndi
    f = ImageFont.truetype(str(fonte), corpo)
    t = Image.new("RGBA", (larg, alt), (0, 0, 0, 0))
    ImageDraw.Draw(t).text(xy, texto, font=f, anchor=ancora, fill=tuple(cor) + (int(255 * alfa),))
    if not contorno:
        return t
    letra = np.array(t)[..., 3] > 127
    q = np.ones((3, 3), dtype=bool)
    anel = ndi.binary_dilation(letra, q, iterations=contorno) & ~ndi.binary_erosion(letra, q, iterations=contorno)
    c = np.zeros((alt, larg, 4), dtype=np.uint8)
    c[anel, :3] = cor_contorno
    c[anel, 3] = int(255 * alfa_contorno)
    return Image.alpha_composite(Image.fromarray(c, "RGBA"), t)


def texto(ov, texto_, xy, fonte=FONTE_LEGENDA, corpo=80, cor=(245, 239, 230), alfa=1.0, contorno=0,
          cor_contorno=(6, 7, 12), alfa_contorno=0.92, sombra=0.0, cor_sombra=(0, 0, 0)):
    """Desenha `texto_` no overlay `ov` (RGBA uint8), por cima do que já está nele. `sombra`: opacidade de uma
    sombra macia (desfoque de 10 px) atrás das letras."""
    alt, larg = ov.shape[:2]
    base = Image.fromarray(ov, "RGBA")
    if sombra:
        s = _camada_texto(alt, larg, texto_, xy, fonte, corpo, cor_sombra, alfa=sombra, contorno=contorno,
                          cor_contorno=cor_sombra, alfa_contorno=sombra).filter(ImageFilter.GaussianBlur(10))
        base = Image.alpha_composite(base, s)
    cam = _camada_texto(alt, larg, texto_, xy, fonte, corpo, cor, alfa, contorno, cor_contorno, alfa_contorno)
    return np.array(Image.alpha_composite(base, cam))


def retangulo(ov, x0, y0, x1, y1, cor, alfa, raio=0):
    """Placa (ou pílula) no overlay, por cima do que já está nele."""
    alt, larg = ov.shape[:2]
    base = Image.fromarray(ov, "RGBA")
    cam = Image.new("RGBA", (larg, alt), (0, 0, 0, 0))
    ImageDraw.Draw(cam).rounded_rectangle((x0, y0, x1, y1), radius=raio, fill=tuple(cor) + (int(255 * alfa),))
    return np.array(Image.alpha_composite(base, cam))


def scrim_radial(alt, larg, centro, raio, alfa_max, cor=(4, 5, 10)):
    """Scrim radial liso (o do gancho): alfa máximo no centro, zero em `raio`."""
    yy, xx = np.mgrid[0:alt, 0:larg]
    d = np.sqrt(((xx - centro[0]) / float(raio[0])) ** 2 + ((yy - centro[1]) / float(raio[1])) ** 2)
    a = np.clip(1.0 - d, 0.0, 1.0) * alfa_max
    ov = vazio(alt, larg)
    ov[..., 0], ov[..., 1], ov[..., 2] = cor
    ov[..., 3] = (a * 255).astype(np.uint8)
    return ov


def compor(imagem, ov):
    """O quadro entregue: overlay (alfa reto) por cima da imagem."""
    a = ov[..., 3:4].astype(np.float32) / 255.0
    out = ov[..., :3].astype(np.float32) * a + imagem.astype(np.float32) * (1.0 - a)
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


# --- vídeo, para os testes pela CLI ------------------------------------------------------------------------------

def _gravar(quadros, destino, fps, args_saida, pix_fmt_in):
    destino = Path(destino)
    alt, larg = quadros[0].shape[:2]
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "rawvideo", "-pix_fmt", pix_fmt_in,
                          "-s", "%dx%d" % (larg, alt), "-r", str(fps), "-i", "-"] + args_saida + [str(destino)],
                         stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    for q in quadros:
        p.stdin.write(np.ascontiguousarray(q).tobytes())
    p.stdin.close()
    erro = p.stderr.read().decode("utf-8", "replace")
    if p.wait() != 0:
        raise AssertionError("ffmpeg falhou ao gravar %s: %s" % (destino.name, erro[-300:]))
    return destino


def gravar_video(quadros, destino, fps=10):
    """MP4 (o entregue) a partir de quadros RGB."""
    return _gravar(quadros, destino, fps, ["-c:v", "libx264", "-preset", "veryfast", "-crf", "14",
                                           "-pix_fmt", "yuv444p"], "rgb24")


def gravar_overlay(quadros, destino, fps=10):
    """MOV com alfa (o overlay) a partir de quadros RGBA, sem perda (png)."""
    return _gravar(quadros, destino, fps, ["-c:v", "png", "-pix_fmt", "rgba"], "rgba")
