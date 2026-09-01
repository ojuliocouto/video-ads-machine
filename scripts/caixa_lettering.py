#!/usr/bin/env python3
"""Caixa de lettering estilo NATIVO do Instagram: bloco sólido de canto reto com
o texto dentro.

Ordem do Júlio (26/08/2026), depois do one-shot do Thales pra OCC:

    "essa caixa com o texto dentro funciona muito, muito, muito bem, porque ela
    parece muito com o formato nativo do Instagram. deixa isso salvo dentro da
    nossa skill, pra gente poder usar sempre que precisar colocar título,
    headline no vídeo. legenda não: só título e lettering."

## Onde usa e onde NÃO usa

| Uso | Vale? |
|---|---|
| título / headline fixo na tela | SIM, é pra isso |
| lettering de frase de peso | SIM |
| legenda (karaokê, fala palavra a palavra) | NÃO. Legenda segue o padrão sans do motor |

O motivo de funcionar é mimetizar o widget de texto nativo do Instagram: o olho
lê como "post", não como "anúncio editado". Por isso o canto é RETO (o widget
nativo é reto) e o fundo é sólido e opaco, sem sombra nem contorno.

## Os três colorways (rodiziar entre eles, nunca inventar um quarto)

    ambar   fundo #FEC64D  texto preto   <- o do one-shot, o mais forte
    branco  fundo #FFFFFF  texto preto
    preto   fundo #000000  texto branco

## Uso

    from caixa_lettering import montar_overlay
    img = montar_overlay("Esse desconto só vai aparecer pra você uma vez.",
                         colorway="ambar", centro_y=0.786)
    img.save("card.png")

    python3 caixa_lettering.py "Título aqui" --colorway branco --saida card.png

Depois é overlay estático de duração inteira:

    ffmpeg -i take.mp4 -loop 1 -i card.png \\
      -filter_complex "[0:v][1:v]overlay=0:0:shortest=1" saida.mp4
"""
import argparse, os
from PIL import Image, ImageDraw, ImageFont

COLORWAYS = {
    "ambar":  {"fundo": (254, 198, 77, 255), "texto": (10, 10, 10, 255)},
    "branco": {"fundo": (255, 255, 255, 255), "texto": (10, 10, 10, 255)},
    "preto":  {"fundo": (0, 0, 0, 255), "texto": (255, 255, 255, 255)},
}

# Serif com peso de texto de revista. Confirmado contra o mockup da Jheni por
# zoom 4x, letra a letra: era PT Serif, não Montserrat (que eu tinha chutado).
FONTES = [
    "/System/Library/Fonts/Supplemental/PTSerif.ttc",
    str(__import__("caminhos").FONTS_V1 / "PlayfairDisplay.ttf"),
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
]

# Medidas do one-shot aprovado, em fração do frame. Mexer aqui muda todo ad.
LARGURA_CAIXA = 0.748   # 0.129 a 0.877: sobra margem dos dois lados
ALTURA_CAIXA = 0.130    # trava a proporção; sem ela a caixa cresce e vira bloco
PAD_X, PAD_Y = 40, 26   # respiro interno em px de um canvas 1080 de largura
TAM_MIN, TAM_MAX = 20, 120
MAX_LINHAS = 2          # título é título: 3 linhas já é parágrafo dentro da caixa

# Só existe UMA arte do wordmark, e ela é clara (texto creme + sunburst
# terracota). Em badge de fundo claro ela some, então a versão escura é DERIVADA
# aqui, escurecendo só o texto e preservando o sunburst colorido.
# (`logo_occ_branca.png` / `logo_occ_preta.png` NÃO são o wordmark: são uma
# ilustração de laptop. Conferi abrindo os dois; o nome engana.)
# O arquivo é arte real de cliente e NÃO vive no repo (ver .gitignore). Procura
# nos lugares conhecidos da máquina; se não achar, exige --logo explícito.
LOGOS_CONHECIDAS = [
    "~/video-ads-machine-2/assets/logo_occ_wordmark.png",
    "~/video-ads-machine-2/_local/render-reel-editorial/logo_occ_wordmark.png",
    "~/video-ads-machine/_hyperframes_test/reelC/logo_occ_wordmark.png",
    "~/video-ads-machine/inputs/assets_jheni/occ_logo.png",
]


def achar_logo(caminho=None):
    for c in ([caminho] if caminho else []) + LOGOS_CONHECIDAS:
        c = os.path.expanduser(c)
        if os.path.exists(c):
            return c
    raise SystemExit("wordmark nao encontrado nesta maquina; passe --logo <arquivo>")
LUM_TEXTO = 200          # acima disso é o texto creme do wordmark
COR_TEXTO_ESCURO = (14, 14, 14)


def logo_para_fundo(logo, fundo_claro):
    """Devolve a arte legível sobre o fundo dado.

    Fundo escuro: a arte original já serve. Fundo claro: escurece os pixels
    claros (o texto) e deixa o sunburst como está, senão a marca vira fantasma.
    """
    if not fundo_claro:
        return logo
    logo = logo.copy()
    px = logo.load()
    for y in range(logo.height):
        for x in range(logo.width):
            r, g, b, a = px[x, y]
            if a and (r + g + b) / 3 >= LUM_TEXTO:
                px[x, y] = COR_TEXTO_ESCURO + (a,)
    return logo


def achar_fonte(caminho=None):
    for f in ([caminho] if caminho else []) + FONTES:
        if f and os.path.exists(f):
            return f
    raise SystemExit("nenhuma fonte serif encontrada; passe --fonte")


def quebrar_linhas(texto, fonte, largura_max):
    """Quebra por palavra. Palavra que não cabe sozinha fica na linha dela."""
    linhas, atual = [], ""
    for p in texto.split():
        teste = (atual + " " + p).strip()
        bb = fonte.getbbox(teste)
        if bb[2] - bb[0] <= largura_max or not atual:
            atual = teste
        else:
            linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    return linhas


def cabe(texto, tam, largura_util, altura_util, fonte_path, max_linhas=3):
    """O texto neste tamanho cabe na caixa? Devolve o layout, ou None.

    Existe separado de `ajustar` pra que o teste possa medir EXATAMENTE o mesmo
    critério que o código usa. Teste que reimplementa o critério por fora valida
    a própria cópia, não o código (foi o que aconteceu: eu conferia largura e
    número de linhas, mas quem estava mordendo era a altura).
    """
    f = ImageFont.truetype(fonte_path, tam)
    linhas = quebrar_linhas(texto, f, largura_util)
    if len(linhas) > max_linhas:
        return None
    larg = max((f.getbbox(l)[2] - f.getbbox(l)[0]) for l in linhas)
    alt = [f.getbbox(l)[3] - f.getbbox(l)[1] for l in linhas]
    gap = round(tam * 0.30)
    bloco = sum(alt) + gap * (len(linhas) - 1)
    if larg > largura_util or bloco > altura_util:
        return None
    return (tam, f, linhas, alt, gap, bloco)


def ajustar(texto, largura_util, altura_util, fonte_path, max_linhas=3):
    """MEDE o maior tamanho que cabe. Nunca chutar tamanho de fonte.

    Varre até TAM_MAX em vez de parar no primeiro que não cabe: com quebra
    automática, um corpo maior às vezes re-quebra em mais linhas e volta a caber.
    Parar no primeiro tropeço entregava fonte menor que a possível.
    """
    melhor = None
    for tam in range(TAM_MIN, TAM_MAX):
        r = cabe(texto, tam, largura_util, altura_util, fonte_path, max_linhas)
        if r:
            melhor = r
    if melhor is None:
        raise SystemExit(f"texto não cabe nem no menor tamanho: {texto!r}")
    return melhor


def render_caixa(texto, largura_px, altura_px=None, colorway="ambar",
                 fonte_path=None, max_linhas=MAX_LINHAS):
    """A caixa sozinha, em RGBA. Altura automática se não vier fixa."""
    if colorway not in COLORWAYS:
        raise SystemExit(f"colorway deve ser um de {list(COLORWAYS)}")
    cor = COLORWAYS[colorway]
    fp = achar_fonte(fonte_path)

    largura_util = largura_px - PAD_X * 2
    altura_util = (altura_px - PAD_Y * 2) if altura_px else 10 ** 6
    tam, f, linhas, alt, gap, bloco = ajustar(texto, largura_util, altura_util,
                                              fp, max_linhas)
    if altura_px is None:
        altura_px = bloco + PAD_Y * 2

    img = Image.new("RGBA", (largura_px, altura_px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, largura_px, altura_px], fill=cor["fundo"])  # canto RETO

    y = (altura_px - bloco) // 2
    for ln, a in zip(linhas, alt):
        bb = f.getbbox(ln)
        x = (largura_px - (bb[2] - bb[0])) / 2 - bb[0]
        d.text((x, y - bb[1]), ln, font=f, fill=cor["texto"])
        y += a + gap
    return img


def montar_overlay(texto, canvas=(1080, 1920), centro_y=0.786, colorway="ambar",
                   fonte_path=None, altura_px=None, max_linhas=MAX_LINHAS, extras=None):
    """Overlay do tamanho do frame, com a caixa posicionada.

    `centro_y` em fração da altura. `extras` = lista de (imagem_rgba, centro_y)
    pra empilhar embaixo, tipo o badge de logo.
    """
    W, H = canvas
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cx = round(LARGURA_CAIXA * W)
    if altura_px is None:
        altura_px = round(ALTURA_CAIXA * H)   # proporção travada, senão vira bloco
    caixa = render_caixa(texto, cx, altura_px, colorway, fonte_path, max_linhas)
    x = (W - cx) // 2
    y = round(centro_y * H) - caixa.height // 2
    over.alpha_composite(caixa, (x, y))
    for extra, cy in (extras or []):
        over.alpha_composite(extra, ((W - extra.width) // 2,
                                     round(cy * H) - extra.height // 2))
    return over


def badge_logo(logo_path=None, largura_px=380, pad_h=22, pad_v=18, colorway="preto"):
    """Badge sólido JUSTO em volta da logo, canto reto, mesma família da caixa.

    O erro que gerou isto: caixa de tamanho fixo com a logo pequena no meio
    sobrava preto vazio em cima e embaixo. O Júlio: "a logo tá escrota, jogada de
    qualquer jeito". A caixa tem que sair DA logo, não a logo caber na caixa.
    """
    cor = COLORWAYS[colorway]["fundo"]
    logo = Image.open(achar_logo(logo_path)).convert("RGBA")
    logo = logo.crop(logo.getbbox())          # tira margem transparente do arquivo
    logo = logo_para_fundo(logo, fundo_claro=sum(cor[:3]) / 3 >= 128)
    lw = largura_px - pad_h * 2
    lh = round(logo.height * lw / logo.width)
    logo = logo.resize((lw, lh), Image.LANCZOS)
    img = Image.new("RGBA", (largura_px, lh + pad_v * 2), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle([0, 0, img.width, img.height], fill=cor)
    img.alpha_composite(logo, (pad_h, pad_v))
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("texto")
    ap.add_argument("--colorway", default="ambar", choices=list(COLORWAYS))
    ap.add_argument("--saida", default="caixa.png")
    ap.add_argument("--largura", type=int, default=1080)
    ap.add_argument("--altura", type=int, default=1920)
    ap.add_argument("--centro-y", type=float, default=0.786)
    ap.add_argument("--altura-caixa", type=int, default=None)
    ap.add_argument("--fonte", default=None)
    ap.add_argument("--logo", default=None, help="badge de logo abaixo da caixa")
    ap.add_argument("--logo-centro-y", type=float, default=0.898)
    ap.add_argument("--logo-largura", type=int, default=380)
    a = ap.parse_args()

    extras = []
    if a.logo:
        extras.append((badge_logo(a.logo, a.logo_largura), a.logo_centro_y))
    img = montar_overlay(a.texto, (a.largura, a.altura), a.centro_y, a.colorway,
                         a.fonte, a.altura_caixa, extras=extras)
    img.save(a.saida)
    print(f"{a.saida}  {a.largura}x{a.altura}  colorway={a.colorway}")


if __name__ == "__main__":
    main()
