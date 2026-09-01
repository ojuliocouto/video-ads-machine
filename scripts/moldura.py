#!/usr/bin/env python3
"""Moldura de navegador em PNG, pro insert entrar INTEIRO dentro dela.

Ordem do Julio (26/08/2026), depois de reprovar o jh13:

    "o insert ta no formato horizontal, da pra colocar dentro de algum mockup"
    "e so colocar ele dentro de algum mockup que caiba na tela, e muito simples.
     E melhor do que voce ficar raciocinando 'aonde que eu posiciono o video pra
     aparecer o que precisa', sendo que O VIDEO TODO QUE APARECE NO VIDEO E O QUE
     PRECISA."

Isso encerra a questao de recorte: nao existe janela a escolher, o quadro inteiro
entra. O que faltava era a moldura que faz o formato horizontal parecer intencional
em vez de sobra.

## Por que a moldura nasce no ASPECTO DO ASSET

Uma moldura de tamanho fixo obrigaria o video a encaixar dentro dela, e sobraria vao
morto la dentro (um 16:9 numa janela 1,44 deixa 134px vazios). Gerando a janela no
aspecto do proprio asset, o video preenche exatamente e nao existe vao: a moldura
veste o video, nao o contrario. Mesma logica do badge de logo em `caixa_lettering.py`.

## Geometria

Herdada do `.broll-vid` que ja existe no template (`templates/reel-editorial/
index.html:69-79`) e nunca chegou ao ar, porque `build_composite.strip_overlay()`
apaga aquelas linhas antes do render: cantos de 24px, borda de 1,5px em branco a 16%,
sombra grande, fundo escuro.

    largura da janela   1008px   (o painel do split tem 1080; sobra 36 de cada lado)
    barra do navegador  62px     (3 pontos + pilula de URL)
    altura da janela    1008 / aspecto_do_asset
    raio                24px
"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

LARGURA_JANELA = 1008
BARRA_H = 62
RAIO = 24
BORDA = (255, 255, 255, 41)          # rgba(255,255,255,.16)
FUNDO_BARRA = (18, 20, 28, 255)
FUNDO_JANELA = (11, 13, 20, 255)     # so aparece se o video nao cobrir 100%
PAD_SOMBRA = 60                      # respiro no canvas pra sombra caber

PONTOS = [((255, 95, 86), 28), ((255, 189, 46), 54), ((39, 201, 63), 80)]


def medidas(aspecto):
    """Janela e card, no aspecto do asset. Devolve dict com tudo em px."""
    jw = LARGURA_JANELA
    jh = int(round(jw / aspecto)) // 2 * 2
    return {"janela_w": jw, "janela_h": jh,
            "card_w": jw, "card_h": jh + BARRA_H,
            "barra_h": BARRA_H,
            "video_x": PAD_SOMBRA, "video_y": PAD_SOMBRA + BARRA_H,
            "canvas_w": jw + PAD_SOMBRA * 2,
            "canvas_h": jh + BARRA_H + PAD_SOMBRA * 2}


def png_navegador(aspecto, destino, rotulo=None):
    """Gera o PNG da moldura pro aspecto dado. Devolve o dict de medidas.

    O PNG ja traz a barra do navegador OPACA e a borda; o miolo da janela fica
    transparente, pra o video aparecer por baixo. A borda e desenhada por DENTRO,
    entao ela cobre os 3px de canto do video e os cantos arredondados saem de graca,
    sem o video precisar de mascara alpha propria.
    """
    m = medidas(aspecto)
    W, H = m["canvas_w"], m["canvas_h"]
    x0, y0 = PAD_SOMBRA, PAD_SOMBRA
    x1, y1 = x0 + m["card_w"], y0 + m["card_h"]

    # --- sombra: sutil, so pra descolar do fundo --------------------------------
    # ERA alpha 153 com blur 30 e deslocamento de 18px (26/08/2026). Sobre o fundo
    # desfocado do proprio asset isso virava uma MANCHA PRETA em volta do card, e foi a
    # primeira coisa que o Julio viu: "os assets ficaram com uma sombra preta sobre eles
    # quando a tela ta dividida". O card ja se separa do fundo pela borda clara e pelo
    # fundo estar borrado e escurecido: a sombra pesada so sujava.
    som = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(som).rounded_rectangle([x0, y0 + 6, x1, y1 + 6],
                                          radius=RAIO, fill=(0, 0, 0, 64))
    som = som.filter(ImageFilter.GaussianBlur(14))
    # A SOMBRA NAO PODE FICAR EMBAIXO DO VIDEO (28/08/2026). Ela e composta no canvas
    # ANTES do card, e o "buraco" que o card abre na janela (alpha 0) NAO apaga o que ja
    # esta embaixo: `alpha_composite` compoe, nao substitui. Resultado: preto com alpha
    # 64 por cima da area do video, ou seja 255*(1-64/255) = 191. Era o "filtro cinza"
    # que o Julio viu duas vezes e que eu procurei no lugar errado nas duas (mexi em
    # exposicao, contraste e teto; a causa estava no PNG da moldura).
    # Aqui a area da janela e zerada na propria sombra: ela so existe FORA do card.
    _jan = Image.new("L", (W, H), 255)
    ImageDraw.Draw(_jan).rounded_rectangle([x0, y0, x1, y1], radius=RAIO, fill=0)
    som.putalpha(Image.fromarray(
        (np.array(som.split()[3]).astype(np.uint16) * np.array(_jan) // 255).astype(np.uint8)))

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img.alpha_composite(som)

    # --- card: fundo inteiro, depois a janela vira buraco -----------------------
    card = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([x0, y0, x1, y1], radius=RAIO, fill=FUNDO_JANELA)
    d.rounded_rectangle([x0, y0, x1, y0 + BARRA_H * 2], radius=RAIO, fill=FUNDO_BARRA)
    d.rectangle([x0, y0 + BARRA_H, x1, y0 + BARRA_H * 2], fill=FUNDO_JANELA)
    d.rectangle([x0, y0 + BARRA_H - 1, x1, y0 + BARRA_H], fill=(255, 255, 255, 20))

    for cor, dx in PONTOS:
        cx, cy, r = x0 + dx, y0 + BARRA_H // 2, 8
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=cor + (255,))

    pw, ph = 420, 30
    px = x0 + (m["card_w"] - pw) // 2
    py = y0 + (BARRA_H - ph) // 2
    d.rounded_rectangle([px, py, px + pw, py + ph], radius=ph // 2,
                        fill=(255, 255, 255, 18))

    # miolo transparente: o video aparece por baixo
    d.rectangle([x0, y0 + BARRA_H, x1, y1], fill=(0, 0, 0, 0))
    d.rounded_rectangle([x0, y0, x1, y1], radius=RAIO, outline=BORDA, width=2)
    # cantos de baixo: reforca por dentro pra o video nao vazar no arredondado
    d.rounded_rectangle([x0 + 1, y0 + 1, x1 - 1, y1 - 1], radius=RAIO - 1,
                        outline=(11, 13, 20, 255), width=1)

    img.alpha_composite(card)
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    img.save(destino)
    m["png"] = destino
    return m


if __name__ == "__main__":
    import sys
    asp = float(sys.argv[1]) if len(sys.argv) > 1 else 16 / 9
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/moldura.png"
    m = png_navegador(asp, out)
    print(f"  aspecto {asp:.3f} -> janela {m['janela_w']}x{m['janela_h']}  "
          f"card {m['card_w']}x{m['card_h']}  canvas {m['canvas_w']}x{m['canvas_h']}")
    print(f"  video em ({m['video_x']}, {m['video_y']})  ->  {out}")
