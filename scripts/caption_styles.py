#!/usr/bin/env python3
"""Registro de PRESETS de legenda do Video Ads Machine + builder de ASS dirigido por preset.

A logica de TIMING (aligned_words, layout sequencial anti-overlap) fica no tay_captions.py
e e independente de estilo. Aqui mora so a APARENCIA: cada preset descreve fonte, cor, caixa,
halo, posicao e animacao. Adicionar um estilo novo = adicionar uma entrada em STYLES, nunca
reescrever codigo.

Cores em ASS sao &H00BBGGRR (alpha-blue-green-red). Use hex_ass("#RRGGBB") para converter.

Formatos: build_ass aceita fmt="9x16" (padrao validado) ou "1x1" (feed). O 9x16 e intocado.
No 1x1 o y e derivado proporcionalmente (a calibrar no 1o render real); largura e 1080 nos dois,
entao o x central (540) nao muda.
"""

# Formatos de saida. 9x16 = validado (NAO mexer). 1x1 = feed.
# caption_scale: o 1:1 usa composite com fill (video 9x16 escalado p/ altura 1080 = 56,25%),
# entao a legenda escala junto pra ficar proporcional ao 9x16 (senao sai gigante). 9x16 = 1.0.
FORMATS = {
    "9x16": {"w": 1080, "h": 1920, "caption_scale": 1.0},
    "1x1":  {"w": 1080, "h": 1080, "caption_scale": 0.5625},
}


def hex_ass(hexcolor, alpha=0):
    """#RRGGBB -> &HAABBGGRR (alpha 0 = opaco)."""
    h = hexcolor.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


# Cada preset:
#   label   : nome amigavel (aparece no comparativo)
#   font    : nome da fonte (precisa estar em ~/video-ads-machine/fonts)
#   fsz     : tamanho
#   primary : cor do texto (ASS) -> use hex_ass(...)
#   case    : 'lower' | 'upper' | 'keep'
#   y       : posicao vertical (PlayResY=1920); 1410 = sobre o peito
#   bold    : -1 (sim) / 0 (nao)  -> string ASS
#   halo    : lista de camadas de brilho escuro difuso [{'bord','blur','alpha'}]; [] = sem halo
#   outline : {'colour': ASS, 'width': px} ou None  (contorno fino, BorderStyle 1)
#   box     : {'colour': ASS, 'pad': px} ou None     (caixa solida atras, BorderStyle 3)
#   pop     : True/False  (anima escala na entrada da palavra)
#   fade    : [in_ms, out_ms]
#
# OBS: presets marcados como [PLACEHOLDER] sao chutes iniciais a serem calibrados quando
# chegarem os prints de referencia. O 'tay' e o unico ja VALIDADO (Jheni, v8).

STYLES = {
    # ---- VALIDADO (v8) ----
    "tay": {
        "label": "tay.ldantas (validado v8)",
        "font": "Nunito", "fsz": 122, "primary": "&H00FFFFFF",
        "case": "lower", "y": 1410, "bold": "-1",
        "halo": [
            {"bord": 26, "blur": 20, "alpha": 0x40},
            {"bord": 14, "blur": 12, "alpha": 0x20},
        ],
        "outline": None, "box": None, "pop": True, "fade": [40, 0],
    },

    # ---- PLACEHOLDERS (calibrar com os prints) ----
    "leon_box": {
        "label": "[PLACEHOLDER] Leon - caixa laranja",
        "font": "Montserrat", "fsz": 104, "primary": "&H00FFFFFF",
        "case": "upper", "y": 1410, "bold": "-1",
        "halo": [], "outline": None,
        "box": {"colour": hex_ass("#FA4E04"), "pad": 18},
        "pop": True, "fade": [40, 0],
    },
    "bold_white": {
        "label": "[PLACEHOLDER] Bold branca contorno",
        "font": "Montserrat", "fsz": 112, "primary": "&H00FFFFFF",
        "case": "upper", "y": 1410, "bold": "-1",
        "halo": [], "outline": {"colour": "&H00000000", "width": 6},
        "box": None, "pop": True, "fade": [40, 0],
    },
    "amarela_pop": {
        "label": "[PLACEHOLDER] Amarela MrBeast",
        "font": "Montserrat", "fsz": 118, "primary": hex_ass("#FFD400"),
        "case": "upper", "y": 1410, "bold": "-1",
        "halo": [], "outline": {"colour": "&H00000000", "width": 8},
        "box": None, "pop": True, "fade": [40, 0],
    },

    # ---- REF JHENI: @daianacacia (serif italico, glow) - app Captions ----
    "serif_italic": {
        "label": "Serif italico (ref @daianacacia)",
        "font": "PlayfairDisplay", "fsz": 116, "primary": "&H00FFFFFF",
        "case": "keep", "y": 1410, "bold": "0", "italic": "-1",
        "halo": [
            {"bord": 22, "blur": 18, "alpha": 0x55},
            {"bord": 10, "blur": 10, "alpha": 0x30},
        ],
        "outline": None, "box": None, "pop": False, "fade": [120, 80],
    },
}

DEFAULT = "tay"


def _ts(x):
    return f"{int(x//3600)}:{int((x%3600)//60):02d}:{x%60:05.2f}"


def _apply_case(w, case):
    return {"lower": w.lower, "upper": w.upper, "keep": lambda: w}[case]()


def build_ass(words, style_name="tay", path="/tmp/cap_track.ass", fmt="9x16"):
    """Gera o .ass para um preset. words = [(palavra, start, end)] em reel-time.
    fmt: "9x16" (validado) ou "1x1" (feed; y derivado proporcionalmente, a calibrar)."""
    st = STYLES[style_name]
    font, bold = st["font"], st["bold"]
    F = FORMATS[fmt]
    W, Hh = F["w"], F["h"]
    xc = W // 2
    sc = F.get("caption_scale", 1.0)          # escala fonte+halo p/ ficar proporcional ao formato
    fsz = round(st["fsz"] * sc)
    if fmt == "9x16":
        y = st["y"]
    else:
        # 1:1 usa COMPOSITE com fill borrado (frame 9x16 inteiro preservado, centralizado),
        # entao o "peito" fica na MESMA posicao proporcional do 9x16 -> y proporcional.
        # (Se algum dia usar crop em vez de fill, sobrescrever via y_<fmt> p/ rodape.)
        y = st.get("y_" + fmt, round(st["y"] * Hh / FORMATS["9x16"]["h"]))

    # BorderStyle: 3 se tiver caixa, senao 1 (contorno). Outline/BackColour no Style base.
    if st.get("box"):
        border_style, outline, back = 3, round(st["box"]["pad"] * sc), st["box"]["colour"]
        oc = st["box"]["colour"]
    elif st.get("outline"):
        border_style, outline, back = 1, round(st["outline"]["width"] * sc), "&H00000000"
        oc = st["outline"]["colour"]
    else:
        border_style, outline, back, oc = 1, 0, "&H00000000", "&H00000000"

    head = (
        f"[Script Info]\nScriptType: v4.00+\nPlayResX:{W}\nPlayResY:{Hh}\nWrapStyle:2\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,"
        "Bold,Italic,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV\n"
        f"Style: S, {font}, {fsz}, {st['primary']}, {oc}, {back}, "
        f"{bold},{st.get('italic','0')},{border_style},{outline},0,5,40,40,0\n"
        "\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,Effect,Text\n"
    )

    pop = r"\fscx88\fscy88\t(0,90,\fscx100\fscy100)" if st["pop"] else ""
    fin, fout = st["fade"]
    # 9x16 (validado): halo SEM fade (fica invisivel sobre a camiseta preta; byte-identico ao v8).
    # outros formatos: halo COM o mesmo fade do texto, senao o halo escuro aparece orfao
    # (tarja preta) sobre a pele durante o fade. Ver bug do 1:1.
    halo_fad = "" if fmt == "9x16" else f"\\fad({fin},{fout})"
    ev = []
    for w, s, e in words:
        txt = _apply_case(w, st["case"])
        # layer reinicia por palavra (palavras nao coexistem; halo sempre abaixo do texto)
        layer = 0
        # camadas de halo (brilho escuro difuso), desenhadas por baixo
        for h in st["halo"]:
            ev.append(
                f"Dialogue: {layer},{_ts(s)},{_ts(e)},S,,0,0,0,"
                f"{{\\an5\\pos({xc},{y}){halo_fad}\\1c&H000000&\\3c&H000000&"
                f"\\bord{round(h['bord']*sc)}\\blur{round(h['blur']*sc)}\\alpha&H{h['alpha']:02X}&}}{txt}"
            )
            layer += 1
        # texto principal
        ev.append(
            f"Dialogue: {layer},{_ts(s)},{_ts(e)},S,,0,0,0,"
            f"{{\\an5\\pos({xc},{y})\\fad({fin},{fout}){pop}}}{txt}"
        )
    open(path, "w").write(head + "\n".join(ev) + "\n")
    return path


# ============================ ESTILO EDITORIAL (reelC v7) ============================
# Porte fiel da legenda do HyperFrames (blocks/caption.html do video-ads-machine-2),
# VALIDADA pela Jheni no reelC: grupos de ~3 palavras, palavra acende com fade+slide,
# normal = Montserrat SemiBold 60px branca (sombra suave), palavra-chave = Playfair
# Display SemiBold ITALICO 66px. Posicao: bottom 330px do rodape (canvas 1080x1920).
import os as _os
import re as _re

from PIL import ImageFont as _ImageFont

# (migracao 26/08/2026) era relativo ao proprio arquivo; som e fonte sao DADOS
from caminhos import FONTS_V1 as _FV1  # noqa: E402
_FDIR = str(_FV1)
_ED = {
    "font_norm": "Montserrat SemiBold",
    "ttf_norm": _os.path.join(_FDIR, "Montserrat-SemiBold.ttf"),
    "fsz_norm": 74,        # 82 mostrava so 2 palavras/trecho (estourava e quebrava); Julio pediu
    "font_kw": "Playfair SemiBold",  # 3-4 palavras por trecho (18/07). 74 ainda bem maior que o 60 reprovado.
    "ttf_kw": _os.path.join(_FDIR, "PlayfairDisplay-SemiBoldItalic.ttf"),
    "fsz_kw": 82,
    "y_bottom": 330,      # distancia do rodape (CSS bottom:330px)
    "gap": 20,            # so pra ESTIMAR largura do trecho em _group_words (~espaco natural de fonte);
    "max_w": 980,         # o render usa espaco normal de fonte, nao esse gap. 1080 - 2*50 padding
    "group_max_words": 4, # 3->4: mais palavras por trecho, linha mais cheia (menos "2 palavras soltas")
}


def _is_kw(w):
    """Palavra-chave: numero/valor ou ALLCAPS no roteiro (enfase intencional)."""
    core = w.strip(".,!?…:;()")
    if any(c.isdigit() for c in core):
        return True
    letters = [c for c in core if c.isalpha()]
    return len(letters) >= 2 and all(c.isupper() for c in letters)


_font_norm_cache = None
_font_kw_cache = None
def _wpx(w, kw):
    """Largura em pixels de uma palavra na fonte real (usa PIL, mesma medida do render)."""
    global _font_norm_cache, _font_kw_cache
    if _font_norm_cache is None:
        _font_norm_cache = _ImageFont.truetype(_ED["ttf_norm"], _ED["fsz_norm"])
        _font_kw_cache = _ImageFont.truetype(_ED["ttf_kw"], _ED["fsz_kw"])
    f = _font_kw_cache if kw else _font_norm_cache
    box = f.getbbox(w)
    return box[2] - box[0]


def _group_words(words):
    """Agrupa [(w,s,e)] em grupos de ate group_max_words, quebrando em pontuacao forte
    OU quando a largura real (fonte+kw) do grupo estouraria max_w (17/07/2026: agrupar so
    por contagem deixava passar grupos de 3 palavras longas que estouravam a tela, ex.
    "integração e configuração" = 1084px > 960px de max_w)."""
    groups, cur, cur_w = [], [], 0
    for (w, s, e) in words:
        kw = _is_kw(w)
        ww = _wpx(w, kw)
        added_w = ww if not cur else ww + _ED["gap"]
        if cur and (len(cur) >= _ED["group_max_words"] or cur_w + added_w > _ED["max_w"]):
            groups.append(cur)
            cur, cur_w = [], 0
            added_w = ww
        cur.append((w, s, e))
        cur_w += added_w
        end_punct = bool(_re.search(r"[.!?…]$", w))
        if end_punct:
            groups.append(cur)
            cur, cur_w = [], 0
    if cur:
        groups.append(cur)
    return groups


def build_ass_editorial(words, path="/tmp/cap_track.ass", fmt="9x16",
                        hook_text=None, hook_end=0.0):
    """Builder do estilo editorial. words = [(palavra, start, end)] reel-time (sem overlap).
    hook_text: texto FIXADO nos primeiros segundos (ate hook_end), multi-linha com '\\n'."""
    F = FORMATS[fmt]
    W, Hh = F["w"], F["h"]
    sc = F.get("caption_scale", 1.0)
    _S = float(_os.environ.get("VAM_ED_SCALE", "1.0"))  # 1.0 = fiel ao reelC (canvas 1080x1920 identico)
    fsz_n = round(_ED["fsz_norm"] * _S * sc)
    fsz_k = round(_ED["fsz_kw"] * _S * sc)
    gap = round(_ED["gap"] * _S * sc)
    y_base = round((1920 - _ED["y_bottom"]) * Hh / 1920)   # linha de base (an2 = bottom-center)
    max_w = round(_ED["max_w"] * _S * sc)

    f_norm = _ImageFont.truetype(_ED["ttf_norm"], fsz_n)
    f_kw = _ImageFont.truetype(_ED["ttf_kw"], fsz_k)

    def _wpx(w, kw):
        f = f_kw if kw else f_norm
        box = f.getbbox(w)
        return box[2] - box[0]

    head = (
        f"[Script Info]\nScriptType: v4.00+\nPlayResX:{W}\nPlayResY:{Hh}\nWrapStyle:2\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,"
        "Bold,Italic,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV\n"
        f"Style: N, {_ED['font_norm']}, {fsz_n}, &H00FFFFFF, &H00000000, &H00000000, 0,0,1,0,0,2,40,40,0\n"
        f"Style: K, {_ED['font_kw']}, {fsz_k}, &H00FFFFFF, &H00000000, &H00000000, 0,-1,1,0,0,2,40,40,0\n"
        f"Style: H, Archivo ExtraBold, {round(64*_S*sc*1.2)}, &H00FFFFFF, &H00000000, &H00000000, 0,0,1,{round(8*sc)},0,5,40,40,0\n"
        "\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,Effect,Text\n"
    )
    ev = []

    # hook fixado (estilo referencia: bold branca, contorno preto grosso, terco superior)
    if hook_text and hook_end > 0.2:
        y_hook = round(560 * Hh / 1920)
        txt = hook_text.replace("\\n", "\\N")
        ev.append(
            f"Dialogue: 6,{_ts(0)},{_ts(hook_end)},H,,0,0,0,"
            f"{{\\an5\\pos({W//2},{y_hook})\\bord{round(8*sc)}\\3c&H000000&\\fad(150,150)}}{txt}"
        )

    # LINHA NATURAL POR TRECHO (18/07/2026): antes cada palavra era posicionada individualmente
    # com largura medida no PIL + gap, o que ESPALHAVA as palavras (espacamento "esticado", reclamado
    # pelo Julio 3x). Agora o trecho inteiro e UMA linha ASS com espaco normal de fonte entre as
    # palavras, centralizada. Palavra-chave vira override inline (Playfair italico, corpo maior).
    for g in _group_words(words):
        g_start = g[0][1]
        g_end = g[-1][2]
        parts = []
        for (w, _s, _e) in g:
            if _is_kw(w):
                parts.append(f"{{\\fn{_ED['font_kw']}\\i1\\fs{fsz_k}}}{w}{{\\r}}")
            else:
                parts.append(w)
        line = " ".join(parts)
        # sombra (camada preta borrada) por baixo + linha branca por cima, ambas com fade+slide
        ev.append(
            f"Dialogue: 4,{_ts(g_start)},{_ts(g_end)},N,,0,0,0,"
            f"{{\\an2\\bord{round(3*sc)}\\blur{round(6*sc)}\\1c&H000000&\\3c&H000000&\\alpha&H88&"
            f"\\move({W//2},{y_base+2+round(8*sc)},{W//2},{y_base+2},0,160)\\fad(150,110)}}{line}"
        )
        ev.append(
            f"Dialogue: 5,{_ts(g_start)},{_ts(g_end)},N,,0,0,0,"
            f"{{\\an2\\move({W//2},{y_base+round(8*sc)},{W//2},{y_base},0,160)\\fad(150,110)}}{line}"
        )
    open(path, "w").write(head + "\n".join(ev) + "\n")
    return path
