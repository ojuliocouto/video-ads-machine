"""Filtros do insert: o painel de cima do split, a tela cheia com moldura, a imagem estática e o PiP.

Funções que devolvem STRINGS de filtro (e os poucos PNG que o filtro precisa). Quem roda o ffmpeg é
`render_segmentos`. As medições (aspecto, largura, foco do conteúdo) entram por `enquadramento` e
`push_in`, sempre chamadas pelo módulo (`enq.aspecto`, não uma cópia local), para o teste fixar
cada uma sem ffmpeg.

## O asset entra INTEIRO numa moldura de navegador

Ordem do diretor depois de reprovar um anúncio e de me ver teorizando sobre onde recortar: "é só
colocar ele dentro de algum mockup que caiba na tela. O vídeo todo que aparece no vídeo é o que
precisa". Acabou a decisão de enquadramento: não existe janela a escolher, o quadro inteiro entra, e
a moldura faz o formato horizontal parecer intencional em vez de sobra. A moldura nasce no ASPECTO
DO ASSET (`moldura.py`), então o vídeo preenche a janela exatamente e não há vão morto lá dentro. O
`crop` declarado no inserts.json é IGNORADO aqui: era ele que derrubava a medição do arquivo e
jogava o motor em `preencher`, ampliando 1,5x a 2,4x e decapitando linhas (crops de aspecto 1,10 e
até 0,72 sobre fontes 16:9, descartando de 31% a 60% da área).

MOCKUP SÓ EM ASSET HORIZONTAL (aspecto de 1,05 em diante). A moldura dá forma a um quadro DEITADO
dentro de um painel quase quadrado. Num asset em pé ela faz o oposto: com a janela fixa em 1008 px,
um 9:16 gera card de 1854 px de altura dentro de um painel de 1150, decapitado em cima e embaixo,
exatamente o defeito que a moldura existe para acabar. Asset em pé já preenche o painel sozinho.

## Tela cheia: fundo CONGELADO e desfocado

O fundo rodando ao vivo piscava: a gravação de tela por baixo variava de 35 a 150 de luminância em
2 s, o medidor de ritmo contava isso como 10 cortes em 4,4 s e o olho via estroboscopia, não corte.
Congelar num quadro matou o estrobo, mas a manchete do asset aparecia GIGANTE e fora de foco atrás
da cópia nítida dentro do card (a mesma manchete duas vezes). Fundo chapado resolveu a duplicação e
virou "tela vazia com um cardzinho no meio" (65% a 69% do quadro em preto liso). O terceiro caminho
tem as duas coisas: o asset CONGELADO num quadro (sem estrobo) e desfocado a 60 com brilho medido
(sem a manchete duplicada nem buraco preto). `shortest=1` é OBRIGATÓRIO na composição: o fundo
congelado é um `loop` infinito e, sem isso, só o `trim` lá na frente termina o fluxo e o ffmpeg mói
quadro à toa.

## Degradê da emenda do split

Sempre degradê, nunca linha dura. Piso de 0,62 na última parada: com 0,85 a emenda chegava em preto
quase puro e, quando o pé do insert já é escuro, degradê e asset somam e a emenda vira régua preta
(faixa de 25 px com luminância 0,3 contra 39 no painel do avatar logo abaixo). 0,62 deixa a linha
mais escura em ~14, que é o próprio preto do avatar.

## Elementos gráficos gerados por código

O PiP precisava de uma sombra e o card de logo de um brilho e de um anel, três PNG que ficavam numa
pasta fora do repositório (e não existiam no clone de quem instala). Agora saem do código, com a
mesma geometria e o mesmo perfil de alfa que os arquivos antigos tinham (disco r=158 com desfoque
de 24 e alfa 175; gaussiana de 518 px a 149; anel em r=158 com arco de destaque). São
determinísticos e o nome leva a versão do desenho.
"""
import os
import threading

import push_in

from . import enquadramento as enq
from . import filtros_avatar as FA
from .filtros_avatar import FPS, H, W, cap, nframes

DARK = "0x141210"

# PiP circular do apresentador (fora da safe zone do topo). PIPY 150 -> 290: com 150 o círculo ia
# de y150 a y450 e a safe zone do Reels começa em y269, ou seja 40% do círculo ficava ATRÁS da UI
# do app; pior, a sombra de 420 px começava em y=90. Com 290 sobra 21 px de folga.
PIP = 300
PIPX = (W - 300) // 2
PIPY = 290
PIPF = (420 - 300) // 2          # offset da moldura (sombra/anel 420) para centralizar no PiP de 300

SOMBRA_PIP = "sombra_pip_v1.png"
BRILHO_LOGO = "brilho_logo_v1.png"
ANEL_LOGO = "anel_logo_v1.png"

# `moldura.LARGURA_JANELA` é um global do módulo que a tela cheia troca por um instante. Com o pool
# de threads do render, um split lendo a largura durante essa janela pegava a largura errada.
_TRAVA_MOLDURA = threading.Lock()
_TRAVA_ATIVOS = threading.Lock()


# ------------------------------------------------------------------ painel de cima do split

def painel_encaixado(expo, alvo_w, alvo_h):
    """Asset inteiro a 96% da largura (em número par); o fundo desfocado do próprio asset preenche a
    sobra. Sem tarja chapada: 654 px de preto puro em cima foi reprovado."""
    card_w = int(alvo_w * 0.96) // 2 * 2
    return (f"[t2]{expo}scale={card_w}:{alvo_h}:force_original_aspect_ratio=decrease,"
            f"setsar=1[tfg];")


def painel_preenchido(expo, alvo_w, alvo_h, crop_expr):
    return (f"[t2]{expo}scale={alvo_w}:{alvo_h}:force_original_aspect_ratio=increase,"
            f"crop={alvo_w}:{alvo_h}:{crop_expr},setsar=1[tfg];")


def painel_vertical(src, alvo_w, alvo_h, expo, crop_dims=None):
    """Painel de cima para asset em pé: preenche ou encaixa, conforme a perda MEDIDA."""
    modo = enq.modo_do_painel(src, alvo_w, alvo_h, crop_dims)
    if modo == "encaixar":
        return painel_encaixado(expo, alvo_w, alvo_h)
    return painel_preenchido(expo, alvo_w, alvo_h, enq.crop_conteudo(src, alvo_w, alvo_h, crop_dims))


def _png_da_moldura(asp, dir_molduras, prefixo, largura_janela=None):
    """Gera (uma vez por aspecto) o PNG da moldura e devolve (medidas, caminho para o filtro)."""
    import moldura

    nome = f"{prefixo}_{asp:.4f}.png".replace(".", "_", 1)
    destino = os.path.join(dir_molduras, nome)
    with _TRAVA_MOLDURA:
        antes = moldura.LARGURA_JANELA
        if largura_janela:
            moldura.LARGURA_JANELA = largura_janela
        try:
            if not os.path.exists(destino):
                moldura.png_navegador(asp, destino)
            m = moldura.medidas(asp)
        finally:
            moldura.LARGURA_JANELA = antes
    return m, destino.replace("\\", "/").replace(":", "\\:")


def _push_in(src, jw, jh, dur, start, rotulo):
    """Trecho de filtro do push-in, ou "" quando o asset já entra grande.

    O asset entra INTEIRO em t=0 e a câmera avança depois, só o quanto ele encolheu para caber. Toda
    a regra, com os números e o porquê, mora em `push_in.py` (módulo com teste). Sem avanço a string
    vem vazia e o filtro fica idêntico ao de antes."""
    _lf = enq.largura_fonte(src)
    if not _lf:
        return ""
    mov = push_in.filtro(jw / _lf, dur, FPS, jw, jh, push_in.foco_do_conteudo(src, start))
    if mov:
        print(f"  [{rotulo}] {os.path.basename(src)}: fonte {_lf}px entra a {jw / _lf:.3f} da "
              f"largura, avanca ate {push_in.fator_push_in(jw / _lf):.2f}x", flush=True)
    return mov


def painel_mockup(src, expo, dur, start, dir_molduras):
    """Painel de cima do split: o asset INTEIRO dentro de uma moldura no aspecto dele."""
    asp = enq.aspecto(src)
    if asp < 1.05:
        print(f"  [mockup] {os.path.basename(src)}: aspecto {asp:.2f} e vertical, "
              f"entra sem moldura (o card nao caberia no painel)", flush=True)
        return painel_vertical(src, W, FA.SPLIT_TOP_H, expo)
    m, png = _png_da_moldura(asp, dir_molduras, "moldura")
    jw, jh = m["janela_w"], m["janela_h"]
    cw, ch = m["canvas_w"], m["canvas_h"]
    vx, vy = m["video_x"], m["video_y"]
    print(f"  [mockup] {os.path.basename(src)}: aspecto {asp:.2f} -> janela {jw}x{jh}, "
          f"card {m['card_w']}x{m['card_h']} (asset INTEIRO, sem recorte)", flush=True)
    _mov = _push_in(src, jw, jh, dur, start, "push-in") if dur else ""
    return (f"[t2]{expo}scale={jw}:{jh},setsar=1{_mov}[tvid];"
            f"color=black@0:s={cw}x{ch}:r={FPS},format=rgba,setsar=1[tcv];"
            f"[tcv][tvid]overlay={vx}:{vy}:shortest=1[tcard];"
            f"movie={png},format=rgba,setsar=1[tmold];"
            f"[tcard][tmold]overlay=0:0[tfg];")


def fc_split_tela(sp, expo_bg, painel, avatar_split, N, top_h=None, grad=None):
    """Tela dividida: insert em cima, apresentador embaixo, degradê escuro na emenda.

    `expo_bg` é o ganho de exposição do FUNDO do painel de cima: clarear só o card deixava o painel em
    23,6 de luminância (medido), porque a maior parte do painel é este fundo desfocado, não o card.
    `painel` é o `[t2]...[tfg];` de `painel_mockup` e `avatar_split` o `[1:v]...[bot];` do avatar."""
    top_h = FA.SPLIT_TOP_H if top_h is None else top_h
    grad = FA.SPLIT_GRAD if grad is None else grad
    return (f"[0:v]setpts=PTS/{sp},tpad=stop_mode=clone:stop_duration=4,split=2[t1][t2];"
            f"[t1]scale={W}:{top_h}:force_original_aspect_ratio=increase,"
            f"crop={W}:{top_h},{expo_bg}boxblur=26:1,"
            f"eq=brightness=-0.12,setsar=1[tbg];"
            + painel +
            f"[tbg][tfg]overlay=(W-w)/2:(H-h)/2,setsar=1[top];"
            + avatar_split +
            f"color={DARK}:s={W}x{H}:r={FPS}[cv];"
            f"[cv][top]overlay=0:0:shortest=1[c1];"
            f"[c1][bot]overlay=0:{top_h}[c2];"
            f"color=black:s={W}x{grad}:r={FPS},format=rgba,"
            f"geq=r=0:g=0:b=0:a='255*0.62*pow(Y/{grad - 1},1.6)'[grad];"
            f"[c2][grad]overlay=0:{top_h - grad}:shortest=1,"
            f"fps={FPS},{cap(N)}[v]")


# ------------------------------------------------------------------ tela cheia com moldura

def moldura_cheia(asp, dir_molduras):
    """Moldura da tela cheia. O card pode ser mais largo que no split: 96% de 1080, a mesma margem do
    painel encaixado (com 92% ele dava 27,7% do quadro, MENOS que os 37,5% do próprio split)."""
    larg = int(W * 0.96) // 2 * 2
    return _png_da_moldura(asp, dir_molduras, "moldura_cheio", largura_janela=larg)


def push_in_cheio(src, jw, jh, dur, start):
    return _push_in(src, jw, jh, dur, start, "push-in cheio")


def fc_tela_cheia_moldura(sp, bg_offset, expo, m, png, mov, N):
    """Tela cheia: fundo congelado e desfocado, card com moldura no meio, composição com shortest=1."""
    jw, jh, cw, ch = m["janela_w"], m["janela_h"], m["canvas_w"], m["canvas_h"]
    vx, vy = m["video_x"], m["video_y"]
    return (f"[0:v]setpts=PTS/{sp},tpad=stop_mode=clone:stop_duration=4,split=2[t1][t2];"
            f"[t1]trim=end_frame=1,loop=loop=-1:size=1:start=0,setpts=N/{FPS}/TB,"
            f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"boxblur=60:2,eq=brightness={bg_offset:.3f}:saturation=0.7,"
            f"setsar=1[bg];"
            f"[t2]{expo}scale={jw}:{jh},setsar=1{mov}[vid];"
            f"color=black@0:s={cw}x{ch}:r={FPS},format=rgba,setsar=1[cv];"
            f"[cv][vid]overlay={vx}:{vy}:shortest=1[card];"
            f"movie={png},format=rgba,setsar=1[mold];"
            f"[card][mold]overlay=0:0[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,setsar=1,fps={FPS},{cap(N)}[v]")


# ------------------------------------------------------------------ imagem estática e vídeo em pé

def fc_imagem(N, dur):
    """Insert de IMAGEM estática (screenshot sem gravação de tela): Ken Burns bem sutil (1,0 até 1,06)
    para não ficar morto na tela, sobre o fundo desfocado da própria imagem."""
    return (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=24:1,setsar=1[bg];"
            f"[0:v]scale={int(W * 1.08)}:-1,"
            f"zoompan=z='min(zoom+0.0007,1.06)':d={nframes(dur)}:s={W}x{H}:fps={FPS},setsar=1[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={FPS},{cap(N)}[v]")


def fg_video(zm, crop_expr=None):
    """Primeiro plano do insert em tela cheia sem moldura (vídeo em pé).

    `zoom` é opt-in por insert e amplia pelo CONTEÚDO medido, não pelo centro: o centro cortava a
    primeira letra de cada linha da gravação de tela. zoom <= 1,001 só encaixa na largura."""
    if zm > 1.001:
        return (f"[i2]scale={int(W * zm)}:{int(H * zm)}:force_original_aspect_ratio=decrease,"
                f"crop='min(iw,{W})':'min(ih,{H})':{crop_expr},"
                f"setsar=1[fg];")
    return f"[i2]scale={W}:{H}:force_original_aspect_ratio=decrease,setsar=1[fg];"


def fc_video(sp, cropf, expo, fg, N, pip_crop=None):
    """Insert em tela cheia (fit sobre fundo desfocado). Com `pip_crop`, o apresentador segue presente
    num círculo com sombra; sem ele, só o insert. `tpad` clona o último quadro se a fonte for mais
    curta que o segmento (segmento curto desloca TODOS os seguintes na cadeia)."""
    entrada = (f"[0:v]{cropf}{expo}setpts=PTS/{sp},"
               f"tpad=stop_mode=clone:stop_duration=4,split=2[i1][i2];")
    base = (f"[i1]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=24:1,setsar=1[bg];"
            + fg +
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={FPS},{cap(N)}")
    if pip_crop is None:
        return entrada + base + "[v]"
    return (entrada + base + "[base];"
            f"[1:v]crop={pip_crop},scale={PIP}:{PIP},format=yuva420p,"
            f"geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':"
            f"a='if(lte(pow(X-{PIP // 2},2)+pow(Y-{PIP // 2},2),{(PIP // 2) * (PIP // 2)}),255,0)'[pipv];"
            # shortest=1 nos dois: a sombra em -loop e o avatar (d+0.4) são mais longos que o [base]
            # capado em N quadros, e sem isso o overlay estende o segmento em +0,4 s (o gate de
            # duração pegou: 3,13 s contra 2,72 s esperados)
            f"[2:v]scale=420:420[sh];"
            f"[base][sh]overlay={PIPX - PIPF}:{PIPY - PIPF}:shortest=1[b1];"
            f"[b1][pipv]overlay={PIPX}:{PIPY}:shortest=1[v]")


# ------------------------------------------------------------------ card de logo

def fc_logo(d, N):
    """Revelação do logo: anel girando atrás, brilho radial com fade-in e logo com scale-in + fade.

    O logo fica no terço superior (a legenda cai livre embaixo). Entradas do ffmpeg, nesta ordem:
    0 = logo do projeto, 1 = brilho, 2 = anel."""
    fade_d = min(0.5, max(0.25, d * 0.4))
    sc_d = min(0.7, max(0.35, d * 0.55))
    cy = H // 2 - 300
    return (f"color={DARK}:s={W}x{H}:r={FPS}[bg0];"
            f"[2:v]format=rgba,scale=1180:1180,rotate='0.3*t':c=none:ow=1180:oh=1180,"
            f"colorchannelmixer=aa=0.28[rays];"
            f"[bg0][rays]overlay=x=(W-1180)/2:y={cy}-590:format=auto[bg1];"
            f"[1:v]format=rgba,fade=t=in:st=0:d={fade_d}:alpha=1[gl];"
            f"[bg1][gl]overlay=0:0:format=auto[bg2];"
            f"[0:v]fps={FPS},setpts=PTS-STARTPTS,format=yuva420p,scale=940:-1,"
            f"scale=w='trunc(iw*(0.84+0.16*min(t/{sc_d},1))/2)*2':"
            f"h='trunc(ih*(0.84+0.16*min(t/{sc_d},1))/2)*2':eval=frame,"
            f"fade=t=in:st=0:d={fade_d}:alpha=1[lg];"
            f"[bg2][lg]overlay=x='(W-w)/2':y='(H-h)/2-300':eval=frame,{cap(N)}[v]")


# ------------------------------------------------------------------ ativos gerados por código

def _salvar_uma_vez(destino, desenhar):
    """Gera o PNG se ainda não existe. Escreve num temporário e renomeia: outra thread (ou o ffmpeg)
    nunca lê um arquivo pela metade."""
    destino = str(destino)
    with _TRAVA_ATIVOS:
        if not os.path.exists(destino):
            os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
            tmp = destino + ".parcial.png"
            desenhar().save(tmp)
            os.replace(tmp, destino)
    return destino


def gerar_sombra_pip(destino):
    """Disco preto suave de 420x420: raio 158, alfa 175, desfoque 24 (o perfil do arquivo antigo)."""
    from PIL import Image, ImageDraw, ImageFilter

    def desenhar():
        im = Image.new("RGBA", (420, 420), (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse([210 - 158, 210 - 158, 210 + 158, 210 + 158], fill=(0, 0, 0, 175))
        return im.filter(ImageFilter.GaussianBlur(24))

    return _salvar_uma_vez(destino, desenhar)


def gerar_brilho_logo(destino):
    """Brilho radial do quadro inteiro (1080x1920): gaussiana de 518 px centrada em (540, 960), alfa de
    pico 149, cor quente escura."""
    from PIL import Image
    import numpy as np

    def desenhar():
        yy, xx = np.mgrid[0:H, 0:W]
        alfa = 149.0 * np.exp(-0.5 * (((xx - 540.0) ** 2 + (yy - 960.0) ** 2) / 518.0 ** 2))
        rgba = np.zeros((H, W, 4), dtype=np.uint8)
        rgba[:, :, 0], rgba[:, :, 1], rgba[:, :, 2] = 74, 58, 42
        rgba[:, :, 3] = np.round(alfa).astype(np.uint8)
        return Image.fromarray(rgba)

    return _salvar_uma_vez(destino, desenhar)


def gerar_anel_logo(destino):
    """Anel de 460x460: faixa macia em r=158 (alfa 37) com um arco de destaque no topo (alfa 145,
    de -110 a -46 graus). Gira atrás do logo com opacidade 0,28."""
    from PIL import Image
    import numpy as np

    def desenhar():
        yy, xx = np.mgrid[0:460, 0:460]
        dx, dy = xx - 229.5, yy - 229.5
        r = np.hypot(dx, dy)
        ang = np.degrees(np.arctan2(dy, dx))
        anel = 37.0 * np.exp(-0.5 * ((r - 158.0) / 18.0) ** 2)
        janela = (1.0 / (1.0 + np.exp(-(ang + 110.0) / 4.0))) * (1.0 / (1.0 + np.exp((ang + 46.0) / 4.0)))
        arco = 145.0 * np.exp(-0.5 * ((r - 164.0) / 11.0) ** 2)
        alfa = np.maximum(anel, anel + (arco - anel) * janela)
        peso = np.clip((alfa - anel) / 108.0, 0.0, 1.0)            # quanto do arco entra na cor
        rgba = np.zeros((460, 460, 4), dtype=np.uint8)
        for canal, (cor_anel, cor_arco) in enumerate(((96, 150), (52, 134), (39, 119))):
            rgba[:, :, canal] = np.round(cor_anel + (cor_arco - cor_anel) * peso).astype(np.uint8)
        rgba[:, :, 3] = np.round(alfa).astype(np.uint8)
        return Image.fromarray(rgba)

    return _salvar_uma_vez(destino, desenhar)
