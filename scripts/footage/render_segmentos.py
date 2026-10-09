"""Renderização dos segmentos: um ffmpeg por bloco, em pool de threads, com cache por segmento.

Cada renderizador MEDE o que precisa (aspecto, luminância, largura, foco, preto de entrada), pede a
string de filtro aos módulos `filtros_*` e roda UM ffmpeg. A ordem das medições dentro de cada
renderizador é a do motor original: a paridade compara o argv de todo subprocesso na ordem.

## Quatro renderizadores, um por tipo de imagem

  - `r_orig`: apresentador (e o lettering, e o lettering com logo: o texto é do overlay).
  - `r_split_tela`: insert em cima, apresentador embaixo.
  - `r_insert_moldura`: insert em tela cheia com moldura de navegador.
  - `r_insert`: despacha para os dois acima e cuida do resto (imagem estática, vídeo em pé, PiP).
  - `r_logo`: card de logo.

## Render em paralelo por segmento

O loop antigo renderizava os segmentos um ffmpeg atrás do outro (~7 min de um build de ~20). Cada
segmento é independente (recebe bloco, span e destino e escreve um mp4), então vira pool de threads
(o ffmpeg roda em subprocess, o GIL não pesa). A única dependência entre vizinhos que se achou, o
jump cut de escala, é só decisão de número e foi para `blocos.decidir_bases`, antes do pool.

## Cache por segmento

Chave sha256 de tudo que decide o pixel final (`cache_segmento.chave_segmento`). A fonte (avatar,
arquivo do insert ou logo) entra por mtime e tamanho, não pelo caminho: o mesmo nome com conteúdo
trocado não pode devolver cache velho. `VERSAO_RENDER` entra na chave: mude o valor sempre que um
renderizador mudar o filtro de vídeo, senão o build seguinte reaproveita pixel velho. O card de logo
leva um sufixo na versão porque deixou de usar o arquivo de logo cravado.

## O que saiu

A legenda queimada (`caption_ass`), o lettering serif e foil queimados (`VAM_BAKE_LETTERING=1`), o
`hero`, o `r_split` (bloco "time de IA") e o `r_lettering`: o texto da footage é do overlay. A
`montar` recusa `CAP=1` e `VAM_BAKE_LETTERING=1` com uma mensagem, em vez de ignorar.
"""
import concurrent.futures
import os
import shutil
from dataclasses import dataclass
from typing import Optional

import cache_segmento

from . import blocos as BL
from . import cadeia as CA
from . import enquadramento as enq
from . import exposicao as exp
from . import filtros_avatar as FA
from . import filtros_insert as FI
from .cadeia import ErroFootage, run
from .filtros_avatar import FPS, H, W, nframes

# VERSAO do render por segmento (cache). Mude sempre que qualquer r_orig/r_insert/r_split_tela
# mudar o filtro de vídeo, senão o build próximo reaproveita cache velho (pixel errado).
VERSAO_RENDER = "v2"      # v2 (W3.X B1): a bolinha do pip ancora no rosto medido e a medição degenerada sai

_IMAGENS = (".jpg", ".jpeg", ".png", ".webp")
_ENCODE = ["-c:v", "libx264", "-pix_fmt", "yuv420p"]


@dataclass
class Contexto(object):
    """O que um render de segmentos precisa saber além dos blocos e dos spans."""
    avatar: str
    tmp: str
    tr: CA.Transicao
    inserts: dict
    dir_molduras: str
    dir_gerados: str
    logo: Optional[str] = None
    cache: bool = True
    paralelo: int = 4
    versao: str = VERSAO_RENDER
    split: Optional[enq.GeometriaSplit] = None    # a geometria do split do ambiente da montagem (L6)


def _e_imagem(src):
    return os.path.splitext(src)[1].lower() in _IMAGENS


# ------------------------------------------------------------------ apresentador

def r_orig(avatar, s, e, out, idx=0, base=1.0):
    """Bloco de avatar. O zoom ALTERNA de sentido a cada bloco (ver `filtros_avatar`)."""
    run(FA.cmd_orig(avatar, s, e, out, idx, base))


# ------------------------------------------------------------------ tela dividida

def r_split_tela(cfg, s, e, out, avatar, dir_molduras, split=None):
    """Tela dividida: insert em cima, apresentador embaixo.

    Resolve a gravação de tela LARGA: encaixada num canvas 9:16 pela largura ela vira uma tira de
    ~600 px dentro de 1920 e sobra borrão (o "fora de enquadro" de um anúncio). Num painel largo e
    baixo ela cabe inteira, no tamanho natural; de quebra o apresentador fica na tela durante o insert,
    o que mata o vão de avatar sozinho. O `crop` declarado NÃO entra no filtro (ele decapitava a fonte
    antes de chegar na moldura: cinco inserts descartavam de 31% a 60% da largura).

    `split` é a geometria do ambiente da montagem (`enquadramento.GeometriaSplit`); sem ela, o ambiente é lido NA
    CHAMADA (nunca no import)."""
    geo = split or enq.GeometriaSplit.do_ambiente()
    d = e - s
    src = cfg["file"]
    sp = cfg.get("speed", 1.0)
    st = cfg.get("start", 0)
    st = enq.pular_preto(src, float(st), d * sp)      # entrada nunca preta
    take = d * sp
    N = nframes(d)
    cropf, cropd = enq.crop_fonte(cfg)
    if cropf:
        print(f"  [split] ignorando crop declarado {cropd}: no mockup o quadro entra INTEIRO", flush=True)
    # ordem das medições = ordem em que o filtro era montado no motor original
    expo_bg = exp.eq_exposicao(cfg)
    painel = FI.painel_mockup(src, exp.eq_exposicao(cfg), e - s, float(cfg.get("start", 0) or 0), dir_molduras)
    avatar_split = FA.filtro_avatar_split(enq.medir_bias_split(avatar, env=geo.env_do_bias()), bot_h=geo.bot_h)
    fc = FI.fc_split_tela(sp, expo_bg, painel, avatar_split, N, top_h=geo.top_h, grad=geo.grad)
    run(["ffmpeg", "-y", "-ss", str(st), "-t", str(take + 0.4), "-i", src,
         "-ss", str(s), "-t", str(d + 0.4), "-i", avatar,
         "-filter_complex", fc, "-r", str(FPS), "-map", "[v]", "-an", *_ENCODE, out])


# ------------------------------------------------------------------ tela cheia com moldura

def r_insert_moldura(cfg, s, e, out, dir_molduras):
    """Insert em TELA CHEIA com a mesma moldura de navegador do split. Mesma regra: o quadro entra
    INTEIRO, `crop` declarado não vale. A diferença é que o card ocupa o quadro todo e não há
    apresentador embaixo: isso troca ~60% dos pixels contra o plano vizinho, que é o que faz a detecção
    de cena registrar o corte (o split sozinho muda 0,144 contra limiar 0,30)."""
    d = e - s
    src = cfg["file"]
    sp = cfg.get("speed", 1.0)
    st = cfg.get("start", 0)
    st = enq.pular_preto(src, float(st), d * sp)
    N = nframes(d)
    asp = enq.aspecto(src)
    m, png = FI.moldura_cheia(asp, dir_molduras)
    jw, jh = m["janela_w"], m["janela_h"]
    print(f"  [mockup cheio] {os.path.basename(src)}: janela {jw}x{jh} no quadro inteiro", flush=True)
    mov = FI.push_in_cheio(src, jw, jh, d, st)
    fc = FI.fc_tela_cheia_moldura(sp, exp.bg_offset(src, cfg), exp.eq_exposicao(cfg), m, png, mov, N)
    run(["ffmpeg", "-y", "-ss", str(st), "-t", str(d * sp + 0.4), "-i", src,
         "-filter_complex", fc, "-r", str(FPS), "-map", "[v]", "-an", *_ENCODE, out])


# ------------------------------------------------------------------ despacho dos inserts

def r_insert(cfg, s, e, out, avatar, dir_molduras, dir_gerados, split=None):
    """Despacha o insert. O layout marcado pelo ritmo VENCE o `split` do config: é ele que faz a
    visita seguinte ao mesmo asset parecer outra coisa. Asset em pé não ganha moldura (a guarda é a
    mesma de `painel_mockup`); imagem estática e asset em pé seguem pelo caminho de tela cheia."""
    if cfg.get("split"):
        if cfg.get("_layout") == "cheio":
            if enq.aspecto(cfg["file"]) >= 1.05:
                return r_insert_moldura(cfg, s, e, out, dir_molduras)
        else:
            return r_split_tela(cfg, s, e, out, avatar, dir_molduras, split=split)
    # INSERT HORIZONTAL EM TELA CHEIA TAMBÉM ENTRA INTEIRO: o veto ao `crop` pegou só as entradas com
    # `split: true`, e as sem a flag ainda recortavam (775x1080 de uma fonte 1916x1080 jogava fora
    # 59,5% da área e o quadro mostrava só a coluna do preview, sem a sidebar nem o chat).
    if (not cfg.get("split") and not _e_imagem(cfg["file"]) and enq.aspecto(cfg["file"]) >= 1.05):
        return r_insert_moldura(cfg, s, e, out, dir_molduras)
    d = e - s
    src = cfg["file"]
    sp = cfg.get("speed", 1.0)
    st = cfg.get("start", 0)
    take = d * sp
    st = enq.pular_preto(src, float(st), take)    # fade-from-black da fonte não entra no corte seco
    N = nframes(e - s)
    if _e_imagem(src):
        dur = take + 0.4
        run(["ffmpeg", "-y", "-loop", "1", "-t", str(dur), "-i", src,
             "-filter_complex", FI.fc_imagem(N, dur), "-r", str(FPS), "-map", "[v]", "-an", *_ENCODE, out])
        return
    cropf, cropd = enq.crop_fonte(cfg)
    zm = float(cfg.get("zoom", 1.0) or 1.0)
    # RECORTE NO CONTEÚDO, não no centro: o zoom cortava o meio do quadro, e em gravação de tela o que
    # interessa não está no meio (a PRIMEIRA LETRA de cada linha era comida na borda esquerda).
    crop_expr = enq.crop_conteudo(src, W, H, cropd) if zm > 1.001 else None
    fg = FI.fg_video(zm, crop_expr)
    expo = exp.eq_exposicao(cfg)
    if cfg.get("pip"):
        # bolinha do apresentador (opt-in por insert): ele segue presente durante a demo, num círculo
        # com sombra; a cabeça é MEDIDA no avatar
        pip = enq.pip_crop(avatar)
        sombra = FI.gerar_sombra_pip(os.path.join(dir_gerados, FI.SOMBRA_PIP))
        run(["ffmpeg", "-y", "-ss", str(st), "-t", str(take + 0.4), "-i", src,
             "-ss", str(s), "-t", str(d + 0.4), "-i", avatar,
             "-loop", "1", "-t", str(d + 0.4), "-i", sombra,
             "-filter_complex", FI.fc_video(sp, cropf, expo, fg, N, pip_crop=pip),
             "-r", str(FPS), "-map", "[v]", "-an", *_ENCODE, out])
        return
    run(["ffmpeg", "-y", "-ss", str(st), "-t", str(take + 0.4), "-i", src,
         "-filter_complex", FI.fc_video(sp, cropf, expo, fg, N),
         "-r", str(FPS), "-map", "[v]", "-an", *_ENCODE, out])


# ------------------------------------------------------------------ card de logo

def r_logo(s, e, out, logo, dir_gerados):
    """Card de logo em tela cheia. O logo vem do PROJETO (nunca de um arquivo cravado); o brilho e o
    anel são gerados por código."""
    if not logo:
        raise ErroFootage("ERRO: o bloco [logo] precisa do logo do projeto e ele não foi encontrado. "
                          "Salve o logo em _local/render-reel-editorial/logo.png (ou em assets/logo.png).")
    d = e - s
    N = nframes(e - s)
    brilho = FI.gerar_brilho_logo(os.path.join(dir_gerados, FI.BRILHO_LOGO))
    anel = FI.gerar_anel_logo(os.path.join(dir_gerados, FI.ANEL_LOGO))
    run(["ffmpeg", "-y", "-loop", "1", "-t", str(d + 0.4), "-i", logo,
         "-loop", "1", "-t", str(d + 0.4), "-i", brilho,
         "-loop", "1", "-t", str(d + 0.4), "-i", anel,
         "-filter_complex", FI.fc_logo(d, N), "-map", "[v]", "-r", str(FPS), "-an", *_ENCODE, out])


# ------------------------------------------------------------------ pool + cache

def _renderizar_um(i, blocks, spans, ctx, cache_dir):
    """Corpo do loop antigo para UM segmento. Só lê `b["_base"]` (já decidido); não escreve em bloco
    nenhum. Devolve `(i, out)`."""
    N = len(blocks)
    b, (s, e) = blocks[i], spans[i]
    # o handle deste bloco alimenta a transição que entra no bloco SEGUINTE, então tem que ser o XF
    # DAQUELA transição. Se divergir, o total muda e a footage deixa de casar com o overlay.
    h = CA.xf_dur(blocks[i + 1], blocks[i], ctx.tr) if i < N - 1 else 0.0
    ee = e + h
    out = os.path.join(ctx.tmp, f"s{i:02d}.mp4")
    tipo = b["type"]
    cfg = BL.preparar_insert_cfg(b, ctx.inserts) if tipo == "insert" else None

    def renderizar():
        if tipo in ("orig", "lettering"):
            r_orig(ctx.avatar, s, ee, out, idx=i, base=b["_base"])
        elif tipo == "insert":
            r_insert(cfg, s, ee, out, ctx.avatar, ctx.dir_molduras, ctx.dir_gerados, split=ctx.split)
        elif tipo == "logo":
            r_logo(s, ee, out, ctx.logo, ctx.dir_gerados)
        elif tipo == "lettering_logo":
            r_orig(ctx.avatar, s, ee, out, idx=i)
        else:
            raise ErroFootage(f"ERRO: tipo de bloco desconhecido no segmento {i:02d}: {tipo!r}")

    if not ctx.cache:
        renderizar()
        print(f"  {i:2d} {tipo:14} {s:5.1f}-{e:5.1f}s ok")
        return i, out

    fonte_path = cfg["file"] if cfg else (ctx.logo if (tipo == "logo" and ctx.logo) else ctx.avatar)
    try:
        st = os.stat(fonte_path)
        fonte_stat = (st.st_mtime, st.st_size)
    except OSError:
        fonte_stat = (0.0, 0)
    versao = ctx.versao + "+logo-gerado" if tipo == "logo" else ctx.versao
    chave = cache_segmento.chave_segmento(
        tipo=tipo, narr=b["narr"], s=s, e=e, ee=ee,
        base=b.get("_base", 1.0), layout=b.get("_layout"), insert_cfg=cfg,
        fonte_stat=fonte_stat, versao=versao)
    cache_path = os.path.join(cache_dir, chave + ".mp4")
    if os.path.exists(cache_path):
        shutil.copyfile(cache_path, out)
        print(f"  {i:2d} {tipo:14} cache")
        return i, out
    renderizar()
    try:
        shutil.copyfile(out, cache_path)
    except OSError as err:
        print(f"  [AVISO] nao gravou cache do segmento {i:02d}: {err}", flush=True)
    print(f"  {i:2d} {tipo:14} {s:5.1f}-{e:5.1f}s ok")
    return i, out


def renderizar_todos(blocks, spans, ctx):
    """Renderiza todos os segmentos e devolve os caminhos NA ORDEM DOS ÍNDICES (a cadeia, o
    timing.json e o resto do motor recebem os segmentos na mesma ordem de sempre)."""
    N = len(blocks)
    cache_dir = os.path.join(ctx.tmp, "cache")
    if ctx.cache:
        os.makedirs(cache_dir, exist_ok=True)
    segs = [None] * N
    with concurrent.futures.ThreadPoolExecutor(max_workers=ctx.paralelo) as pool:
        for i, out in pool.map(lambda k: _renderizar_um(k, blocks, spans, ctx, cache_dir), range(N)):
            segs[i] = out
    return segs
