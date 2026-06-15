#!/usr/bin/env python3
"""Registro de PRESETS de legenda + builder de ASS dirigido por preset.

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
#   font    : nome da fonte (precisa estar em fonts/)
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
# chegarem os prints de referencia. O 'tay' e o preset de referencia (1 palavra, branca, halo).

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

    # ---- Serif italico com glow (estilo editorial elegante) ----
    "serif_italic": {
        "label": "Serif italico (serif italico)",
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
