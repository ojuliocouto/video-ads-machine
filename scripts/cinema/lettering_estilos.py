#!/usr/bin/env python3
"""Os 8 estilos de lettering de pico (capacidade C7) como DADOS: de cada especificação sai o CSS do parcial e a
FAIXA que o `gate_safezone` confere antes do render.

    python3 scripts/cinema/lettering_estilos.py --escrever   # regrava templates/_parciais/lettering_*.css
    python3 scripts/cinema/lettering_estilos.py --conferir   # sai 1 se algum parcial não bate com a especificação

## Os estilos

| estilo | o que é | de onde veio a técnica |
|---|---|---|
| caixa_nativa | caixa sólida de canto reto (widget de texto nativo do app), PT Serif, 3 colorways | lettering-caixa-nativa |
| serif_editorial | o padrão: LEAD em Inter caixa alta, KEY em Playfair itálico, tela esmaecida | o template de sempre |
| punch | carimbo: Anton caixa alta enorme, sombra dura, entra com escala 1,25 em 0,10 s | variante punch do gancho |
| marcador | Montserrat 800 com a palavra marcada (`*palavra*`) num marca-texto que se desenha | overlay "b" da VSL |
| statement | afirmação grande sobre vinheta, LEAD em serif itálico | overlay "d" da VSL |
| lateral | coluna à esquerda com degradê lateral, entra deslizando | overlay "l" da VSL |
| seta_cta | caixa escura com a chamada e uma seta que quica apontando para baixo (C9) | overlay "a" da VSL |
| gigante_atras | uma palavra gigante no alto da cabeça (atrás da pessoa quando o recorte da W5.C existe) | overlay "t" da VSL |

As regras de ouro que valem para todos (diretor de arte e playbook da VSL): lettering é PICO, não decoração (2 a 3
no meio + 1 de CTA); a KEY é a palavra que a voz já enfatiza; nunca junto com a legenda; nunca atravessa a troca de
layout; a faixa é o peito, nunca o rosto; KEY com no máximo 2 linhas (3 linhas já é parágrafo). A entrada é SECA: a
KEY tem alfa cheio no primeiro quadro e o movimento é só de escala ou posição, então ela está legível em até
`ENTRADA_LEGIVEL_S` (o gate mede: tinta em +0,15 s de pelo menos `ALFA_LEGIVEL` da tinta assentada).

## Geometria

Tudo no quadro 9x16 (1080x1920), zona segura RÍGIDA: tinta até x 940 e até y 1690. Os estilos novos só existem em
avatar cheio: em tela dividida, em close (`baixo`) e na pilha o quadro não tem faixa para eles, e o lettering cai no
`serif_editorial` (o que já é calibrado para a costura, para o close e para a lista). `efetivo` decide isso, e o
`gate_lettering` relata quando acontece. O 1x1 (beta) herda o CSS como está.

As FAIXAS são o envelope da tinta de cada estilo (x0, x1, y0, y1), derivadas dos MESMOS números que geram o CSS:
o lado de baixo é o rodapé do bloco (1920 menos o recuo de baixo) e o de cima soma LEAD, KEY em 2 linhas e extras
(seta, logo). Medidas no render pelo mostruário (`cinema/mostruario_lettering`, teste `lento`).
"""
import argparse
import math
import re
import sys
from pathlib import Path

PARCIAIS = Path(__file__).resolve().parents[2] / "templates" / "_parciais"

ESTILOS = ("caixa_nativa", "serif_editorial", "punch", "marcador", "statement", "lateral", "seta_cta", "gigante_atras")
PADRAO = "serif_editorial"

LARGURA, ALTURA = 1080, 1920
LIMITE_X, LIMITE_Y = 940, 1690            # os mesmos do gate_safezone (um teste confere)
ENTRADA_LEGIVEL_S = 0.15                  # C7: a KEY é legível em até 0,15 s da entrada
ALFA_LEGIVEL = 0.90                       # ... com pelo menos 90% da tinta assentada
MAX_LINHAS = 2                            # 3 linhas já é parágrafo

# caixa nativa: três colorways, rodiziar entre eles, nunca inventar um quarto
COLORWAYS = {
    "ambar": {"fundo": "#FEC64D", "texto": "#0A0A0A"},
    "branco": {"fundo": "#FFFFFF", "texto": "#0A0A0A"},
    "preto": {"fundo": "#000000", "texto": "#FFFFFF"},
}
COR_PADRAO = "ambar"
COR_MARCADOR = "#E87D4E"                  # terracota: a mesma ênfase da legenda
COR_SETA = "#E87D4E"

# largura média de um caractere em em, medida no próprio arquivo de fonte (fontTools, frase de anúncio em
# caixa alta e em caixa mista). Serve para estimar linhas antes do render.
AVANCO = {
    "anton": (0.418, 0.412), "montserrat-800": (0.652, 0.548), "pt-serif": (0.570, 0.450),
    "playfair-italic": (0.606, 0.458), "inter": (0.601, 0.499),
}

# ---------------------------------------------------------------------------------------------------------------
# Especificação de cada estilo novo. x0 e x1: a caixa do conteúdo; base: o rodapé do bloco (y); key: fonte, corpo
# (px), entrelinha e se é caixa alta; lead: corpo e margem; extra: altura de elementos além de LEAD e KEY.
# ---------------------------------------------------------------------------------------------------------------
SPEC = {
    "caixa_nativa": {"x0": 160, "x1": 920, "base": 1634, "fonte": "pt-serif", "corpo": 64, "entrelinha": 1.12,
                     "caixa_alta": False, "lead_corpo": 34, "lead_altura": 61, "pad_x": 40, "pad_y": 26,
                     "extra": 0},
    "punch": {"x0": 160, "x1": 920, "base": 1660, "fonte": "anton", "corpo": 136, "entrelinha": 1.0,
              "caixa_alta": True, "lead_corpo": 34, "lead_altura": 47, "extra": 0},
    "marcador": {"x0": 160, "x1": 920, "base": 1650, "fonte": "montserrat-800", "corpo": 78, "entrelinha": 1.18,
                 "caixa_alta": True, "lead_corpo": 30, "lead_altura": 50, "pad_x": 18, "extra": 12},
    "statement": {"x0": 150, "x1": 930, "base": 1620, "fonte": "montserrat-800", "corpo": 96, "entrelinha": 1.04,
                  "caixa_alta": True, "lead_corpo": 40, "lead_altura": 66, "extra": 0},
    "lateral": {"x0": 70, "x1": 610, "base": 1620, "fonte": "montserrat-800", "corpo": 72, "entrelinha": 1.04,
                "caixa_alta": True, "lead_corpo": 36, "lead_altura": 53, "extra": 0},
    "seta_cta": {"x0": 150, "x1": 930, "base": 1620, "fonte": "montserrat-800", "corpo": 54, "entrelinha": 1.15,
                 "caixa_alta": True, "lead_corpo": 30, "lead_altura": 48, "pad_x": 34, "pad_y": 18,
                 "seta": 36, "seta_margem": 14, "quique": 14, "extra": 0},
    "gigante_atras": {"x0": 140, "x1": 940, "topo": 260, "fonte": "anton", "corpo": 230, "entrelinha": 0.95,
                      "caixa_alta": True, "lead_corpo": 30, "lead_altura": 40, "largura_alvo": 700,
                      "corpo_min": 120, "escala_entrada": 1.14, "extra": 0},
}
GAP = 6                                   # o gap do flex de `.lett`

_SOMBRA_DURA = "0 6px 0 rgba(0,0,0,.55), 0 12px 40px rgba(0,0,0,.9)"
_SOMBRA_MACIA = "0 6px 30px rgba(0,0,0,.7)"


def _altura_key(s, linhas=MAX_LINHAS):
    return linhas * s["corpo"] * s["entrelinha"]


def _faixa_nova(estilo):
    s = SPEC[estilo]
    if estilo == "gigante_atras":
        y0 = s["topo"] - 10
        y1 = s["topo"] + s["lead_altura"] + GAP + s["corpo"] * s["entrelinha"] + 20
        return {"x0": s["x0"], "x1": s["x1"], "y0": int(y0), "y1": int(math.ceil(y1))}
    altura = s["lead_altura"] + GAP + _altura_key(s) + s.get("extra", 0)
    if estilo == "caixa_nativa":
        altura += 2 * s["pad_y"]
    if estilo == "seta_cta":
        altura += 2 * s["pad_y"] + GAP + s["seta_margem"] + s["seta"]
    y1 = s["base"] + s.get("quique", 0)
    return {"x0": s["x0"], "x1": s["x1"], "y0": int(math.floor(s["base"] - altura)), "y1": int(y1)}


# Envelopes medidos no overlay 9x16 do fixture (snapshot, tinta acima de 110 de luminância) e conferidos contra o CSS
# do template: lettering editorial (padrão, split, pilha), CTA (LEAD + pílula + logo), a fileira da pílula onde a
# seta se mexe (C9) e o gancho (editorial e punch). Mudou o CSS do template, mede de novo.
FAIXAS = {
    "serif_editorial": {"x0": 170, "x1": 910, "y0": 1290, "y1": 1660},
    "serif_editorial_split": {"x0": 170, "x1": 910, "y0": 940, "y1": 1130},
    "serif_editorial_pilha": {"x0": 170, "x1": 910, "y0": 1380, "y1": 1670},
    "cta": {"x0": 140, "x1": 940, "y0": 1130, "y1": 1520},
    "cta_split": {"x0": 140, "x1": 940, "y0": 760, "y1": 1045},
    "cta_seta": {"x0": 140, "x1": 940, "y0": 1200, "y1": 1370},
    "cta_seta_split": {"x0": 140, "x1": 940, "y0": 830, "y1": 965},
    "hook": {"x0": 150, "x1": 930, "y0": 880, "y1": 1260},
    "hook_punch": {"x0": 140, "x1": 940, "y0": 300, "y1": 720},
}
for _e in SPEC:
    FAIXAS[_e] = _faixa_nova(_e)


# --- regras de uso ---------------------------------------------------------------------------------------------

def _conferir(estilo):
    if estilo not in ESTILOS:
        raise ValueError("estilo desconhecido: %r (use um de: %s)" % (estilo, ", ".join(ESTILOS)))


def efetivo(estilo, split=False, baixo=False, pilha=False):
    """O estilo que de fato vai para a tela. Sem estilo é o padrão; em split, close ou pilha só o editorial cabe."""
    if estilo is None:
        return PADRAO
    _conferir(estilo)
    if split or baixo or pilha:
        return PADRAO
    return estilo


def classe(estilo):
    """A classe CSS do estilo no `.lett` (o padrão não tem modificador: o HTML dele não muda)."""
    _conferir(estilo)
    return "" if estilo == PADRAO else "lett-%s" % estilo


def faixa(estilo, split=False, pilha=False, baixo=False):
    """A FAIXA da tinta de um lettering, já com o estilo efetivo."""
    e = efetivo(estilo, split=split, baixo=baixo, pilha=pilha)
    if e == PADRAO:
        if split:
            return FAIXAS["serif_editorial_split"]
        if pilha or baixo:
            return FAIXAS["serif_editorial_pilha"]
    return FAIXAS[e]


def _quebrar(texto, largura_px, px_por_char):
    """Linhas de um texto quebrado palavra a palavra numa largura (estimativa por avanço médio)."""
    linhas = 0
    for paragrafo in str(texto).split("\n"):
        palavras = paragrafo.split()
        if not palavras:
            continue
        linhas += 1
        atual = 0.0
        for p in palavras:
            w = len(p) * px_por_char
            if atual and atual + px_por_char + w > largura_px:
                linhas += 1
                atual = w
            else:
                atual += (px_por_char if atual else 0) + w
            while atual > largura_px:              # palavra que sozinha não cabe
                linhas += 1
                atual -= largura_px
    return linhas


def linhas_estimadas(texto, estilo, split=False):
    """Quantas linhas a KEY ocupa no estilo (estimativa pela largura média medida da fonte, antes do render).

    `gigante_atras` não quebra linha: encolhe até caber; se nem no corpo mínimo cabe, conta as linhas que
    precisaria (ou seja, reprova como KEY longa demais)."""
    texto = re.sub(r"\*", "", str(texto))
    e = efetivo(estilo, split=split)
    if e == PADRAO:
        corpo = 62 if split else (82 if len(texto) > 18 else 104)
        larg = FAIXAS["serif_editorial"]["x1"] - FAIXAS["serif_editorial"]["x0"]
        maiusc = texto.upper() == texto
        return _quebrar(texto, larg, corpo * AVANCO["playfair-italic"][0 if maiusc else 1])
    s = SPEC[e]
    maiusc = s["caixa_alta"] or texto.upper() == texto
    avanco = AVANCO[s["fonte"]][0 if maiusc else 1]
    if e == "gigante_atras":
        return _quebrar(texto, s["largura_alvo"], s["corpo_min"] * avanco) if "\n" not in texto else texto.count("\n") + 1
    larg = s["x1"] - s["x0"] - 2 * s.get("pad_x", 0)
    return _quebrar(texto, larg, s["corpo"] * avanco)


def faixas_extra(timeline):
    """As faixas de lettering, CTA e hook da timeline no formato de `gate_safezone.rodar_antes(faixas_extra=...)`."""
    saida = []
    split = [(j["s"], j["e"]) for j in timeline.get("janelas_split") or []]
    no_split = lambda t: any(a <= t < b for a, b in split)              # noqa: E731
    for l in timeline.get("letterings") or []:
        f = faixa(l.get("estilo"), split=bool(l.get("split")), pilha=bool(l.get("pilha")), baixo=bool(l.get("baixo")))
        saida.append(dict(f, elemento="lettering", id=str(l.get("id")), s=l["s"], e=l["s"] + l["d"]))
    cta, dur = timeline.get("cta"), timeline.get("duracao_s")
    if isinstance(cta, dict) and cta.get("inicio") is not None and dur:
        f = FAIXAS["cta_split" if no_split(cta["inicio"]) else "cta"]
        saida.append(dict(f, elemento="cta", id="cta", s=cta["inicio"], e=dur))
    hook = timeline.get("hook")
    if isinstance(hook, dict) and hook.get("e") is not None:
        f = FAIXAS["hook_punch" if hook.get("estilo") == "punch" else "hook"]
        saida.append(dict(f, elemento="hook", id="hook", s=hook.get("s", 0.0), e=hook["e"]))
    return saida


# --- CSS -------------------------------------------------------------------------------------------------------

_CABECALHO = ("      /* ===== lettering_%s.css (gerado por scripts/cinema/lettering_estilos.py: não editar) =====\n"
              "%s */\n")

CSS_EDITORIAL = """      /* ===== lettering_serif_editorial.css (gerado por scripts/cinema/lettering_estilos.py: não editar) =====
         O lettering de pico padrão: LEAD em Inter caixa alta, KEY em Playfair itálico, a tela inteira
         esmaecida atrás (o pico é o único foco). É a classe `.lett` sem modificador. Os recuos e corpos por
         formato (e as variantes split, baixo e pilha) moram no index.html. */
      /* dim de tela cheia a .55 (abaixo de alfa 190: nem o gate de texto nem o de colisão contam como tinta);
         o radial localizado virava mancha órfã longe do texto. */
      .lett { position:absolute; inset:0; z-index:34; pointer-events:none;
        display:flex; flex-direction:column; align-items:center; justify-content:flex-end;
        gap:6px; background:rgba(2,3,6,.55); }
      /* PILHA: lista que acumula. Sans e alinhada à esquerda (item de lista centralizado não lê como lista),
         com o marcador de negação desenhado em tipografia (o emoji foi reprovado). */
      .lett.lett-pilha { align-items:flex-start; }
      .lett.lett-pilha .key { font-family:"Inter"; font-style:normal; font-weight:600;
        text-align:left; letter-spacing:-.2px;
        text-shadow:0 4px 22px rgba(0,0,0,.85);
        padding-left:44px; position:relative; }
      .lett.lett-pilha .key::before { content:""; position:absolute; left:0; top:26px;
        width:26px; height:5px; border-radius:3px; background:#ff5a4d;
        box-shadow:0 2px 10px rgba(0,0,0,.7); }
      .lett .lead { font-family:"Inter"; font-weight:700; letter-spacing:6px;
        color:rgba(255,255,255,.92); text-transform:uppercase;
        text-shadow:0 2px 16px rgba(0,0,0,.95); }
      /* peso 700 + corpo grande + tela esmaecida: o lettering é o pico e não pode pesar menos que a legenda */
      .lett .key { font-family:"Playfair Display", serif; font-variant-numeric:lining-nums; font-feature-settings:"lnum" 1; font-weight:700; font-style:italic;
        letter-spacing:-.5px; text-align:center; color:#fff;
        text-shadow:0 6px 30px rgba(0,0,0,.55); }
      /* logo DENTRO do lettering (bloco marcado com logo): assinatura, menor que o logo do CTA */
      .lett .lett-logo { display:block; width:240px; margin:18px auto 0;
        filter:drop-shadow(0 4px 10px rgba(0,0,0,.95)) drop-shadow(0 8px 30px rgba(0,0,0,.7)); }
"""


def _px(v):
    return ("%.2f" % v).rstrip("0").rstrip(".") + "px"


def _caixa(e, s):
    """recuos do bloco: laterais pela caixa x0..x1, embaixo pela base."""
    return "padding:0 %s %s %s" % (_px(LARGURA - s["x1"]), _px(ALTURA - s["base"]), _px(s["x0"]))


def _css_caixa_nativa(s):
    c = ".lett.lett-caixa_nativa"
    linhas = [
        "      %s { %s; gap:0; background:none; }" % (c, _caixa("caixa_nativa", s)),
        "      %s .lead { font-family:\"PT Serif\", serif; font-weight:400; font-style:normal; font-size:%s;"
        " line-height:1.2; letter-spacing:0; text-transform:none; text-shadow:none; margin:0;"
        " padding:10px 22px; border-radius:0; }" % (c, _px(s["lead_corpo"])),
        "      %s .key { font-family:\"PT Serif\", serif; font-weight:400; font-style:normal; font-size:%s;"
        " line-height:%s; letter-spacing:0; text-align:center; text-wrap:balance; text-shadow:none; max-width:%s;"
        " padding:%s %s; border-radius:0; }"
        % (c, _px(s["corpo"]), s["entrelinha"], _px(s["x1"] - s["x0"]), _px(s["pad_y"]), _px(s["pad_x"])),
    ]
    for nome, cw in COLORWAYS.items():
        linhas.append("      %s.cor-%s .lead, %s.cor-%s .key { background:%s; color:%s; }"
                      % (c, nome, c, nome, cw["fundo"], cw["texto"]))
    return linhas


def _css_punch(s):
    c = ".lett.lett-punch"
    return [
        "      %s { %s; }" % (c, _caixa("punch", s)),
        "      %s .lead { font-family:\"Inter\"; font-weight:800; font-size:%s; letter-spacing:2px;"
        " color:#fff; margin-bottom:6px; text-shadow:%s; }" % (c, _px(s["lead_corpo"]), _SOMBRA_DURA),
        "      %s .key { font-family:\"Anton\", sans-serif; font-weight:400; font-style:normal; font-size:%s;"
        " line-height:%s; letter-spacing:1px; text-transform:uppercase; text-align:center; text-wrap:balance; color:#fff;"
        " text-shadow:%s; }" % (c, _px(s["corpo"]), s["entrelinha"], _SOMBRA_DURA),
    ]


def _css_marcador(s):
    c = ".lett.lett-marcador"
    return [
        "      %s { %s; }" % (c, _caixa("marcador", s)),
        "      %s .lead { font-size:%s; letter-spacing:5px; margin-bottom:14px; }" % (c, _px(s["lead_corpo"])),
        "      %s .key { font-family:\"Montserrat\", sans-serif; font-weight:800; font-style:normal; font-size:%s;"
        " line-height:%s; letter-spacing:.01em; text-transform:uppercase; text-align:center; text-wrap:balance; color:#fff;"
        " text-shadow:%s; }" % (c, _px(s["corpo"]), s["entrelinha"], _SOMBRA_MACIA),
        # marca-texto: o texto marcado fica escuro e a barra desenha da esquerda para a direita pela --hx
        "      %s .key .hi { position:relative; display:inline-block; isolation:isolate; padding:0 %s;"
        " color:#0B0B0B; text-shadow:none; white-space:nowrap; }" % (c, _px(s["pad_x"])),
        "      %s .key .hi::before { content:\"\"; position:absolute; inset:0; z-index:-1; border-radius:12px;"
        " background:%s; transform:rotate(-1.6deg) scaleX(var(--hx, 1)); transform-origin:left center;"
        " box-shadow:0 8px 26px rgba(0,0,0,.35); }" % (c, COR_MARCADOR),
    ]


def _css_statement(s):
    c = ".lett.lett-statement"
    return [
        # vinheta no lugar do dim chapado; alfa máximo .70 (179): abaixo dos 190 que contam como tinta
        "      %s { %s; background:radial-gradient(ellipse 80%% 70%% at 50%% 62%%, rgba(5,7,10,.30) 0%%,"
        " rgba(5,7,10,.62) 70%%, rgba(5,7,10,.70) 100%%); }" % (c, _caixa("statement", s)),
        "      %s .lead { font-family:\"Playfair Display\", serif; font-style:italic; font-weight:600; font-size:%s;"
        " letter-spacing:.02em; text-transform:none; color:#E8E2D6; margin-bottom:18px; }"
        % (c, _px(s["lead_corpo"])),
        "      %s .key { font-family:\"Montserrat\", sans-serif; font-weight:800; font-style:normal; font-size:%s;"
        " line-height:%s; letter-spacing:-.01em; text-transform:uppercase; text-align:center; text-wrap:balance; color:#fff;"
        " text-shadow:0 6px 40px rgba(0,0,0,.7); }" % (c, _px(s["corpo"]), s["entrelinha"]),
    ]


def _css_lateral(s):
    c = ".lett.lett-lateral"
    return [
        "      %s { %s; align-items:flex-start; background:linear-gradient(90deg, rgba(5,7,10,.70) 0%%,"
        " rgba(5,7,10,.40) 30%%, rgba(5,7,10,0) 55%%); }" % (c, _caixa("lateral", s)),
        "      %s .lead { font-family:\"Playfair Display\", serif; font-style:italic; font-weight:600; font-size:%s;"
        " letter-spacing:.02em; text-transform:none; text-align:left; color:#E8E2D6; margin-bottom:10px; }"
        % (c, _px(s["lead_corpo"])),
        "      %s .key { font-family:\"Montserrat\", sans-serif; font-weight:800; font-style:normal; font-size:%s;"
        " line-height:%s; letter-spacing:-.012em; text-transform:uppercase; text-align:left; text-wrap:balance; color:#fff;"
        " max-width:%s; text-shadow:0 6px 34px rgba(0,0,0,.75); }"
        % (c, _px(s["corpo"]), s["entrelinha"], _px(s["x1"] - s["x0"])),
    ]


def _css_seta_cta(s):
    c = ".lett.lett-seta_cta"
    meia = s["seta"] * 5 / 6
    return [
        "      %s { %s; background:none; }" % (c, _caixa("seta_cta", s)),
        "      %s .lead { font-size:%s; margin-bottom:12px; }" % (c, _px(s["lead_corpo"])),
        "      %s .key { font-family:\"Montserrat\", sans-serif; font-weight:800; font-style:normal; font-size:%s;"
        " line-height:%s; letter-spacing:.02em; text-transform:uppercase; text-align:center; text-wrap:balance; color:#fff;"
        " max-width:%s; padding:%s %s; border-radius:16px; background:rgba(12,17,22,.86);"
        " box-shadow:0 12px 40px rgba(0,0,0,.45); text-shadow:none; }"
        % (c, _px(s["corpo"]), s["entrelinha"], _px(s["x1"] - s["x0"]), _px(s["pad_y"]), _px(s["pad_x"])),
        # seta por borda (CSS puro), apontando para baixo; o GSAP faz ela quicar (C9)
        "      %s .seta { width:0; height:0; margin-top:%s; border-left:%s solid transparent;"
        " border-right:%s solid transparent; border-top:%s solid %s;"
        " filter:drop-shadow(0 6px 18px rgba(0,0,0,.6)); }"
        % (c, _px(s["seta_margem"]), _px(meia), _px(meia), _px(s["seta"]), COR_SETA),
    ]


def _css_gigante_atras(s):
    c = ".lett.lett-gigante_atras"
    return [
        "      %s { padding:%s %s 0 %s; justify-content:flex-start; background:none; }"
        % (c, _px(s["topo"]), _px(LARGURA - s["x1"]), _px(s["x0"])),
        "      %s .lead { font-size:%s; letter-spacing:8px; margin-bottom:4px; }" % (c, _px(s["lead_corpo"])),
        "      %s .key { font-family:\"Anton\", sans-serif; font-weight:400; font-style:normal; font-size:%s;"
        " line-height:%s; letter-spacing:.01em; text-transform:uppercase; text-align:center; white-space:nowrap;"
        " color:#fff; text-shadow:0 10px 60px rgba(0,0,0,.55); }" % (c, _px(s["corpo"]), s["entrelinha"]),
    ]


_COMENTARIO = {
    "caixa_nativa": "         Caixa de canto RETO, fundo sólido sem sombra nem contorno: imita o widget de texto nativo do app,\n"
                    "         e o olho lê como post, não como anúncio editado. PT Serif. Cada linha na sua caixa (LEAD menor\n"
                    "         acima). Sem dim de tela: o nativo não escurece nada. Colorways: ambar, branco, preto.",
    "punch": "         Carimbo: Anton caixa alta enorme, sombra dura, tela esmaecida. Entra com escala 1,25 em 0,10 s\n"
             "         (o alfa é cheio desde o primeiro quadro).",
    "marcador": "         Montserrat 800 caixa alta; a palavra entre asteriscos no roteiro (`*20 HORAS*`) ganha um\n"
                "         marca-texto terracota que se desenha da esquerda para a direita em 0,12 s. Padrão do C9 para KEY\n"
                "         de número ou promessa.",
    "statement": "         Afirmação grande sobre vinheta (alfa máximo .70: não conta como tinta), LEAD em serif itálico.\n"
                 "         As linhas sobem 30 px em 0,14 s com alfa cheio.",
    "lateral": "         Coluna à esquerda com degradê lateral, texto alinhado à esquerda; entra deslizando 60 px em 0,14 s.",
    "seta_cta": "         Chamada numa caixa escura e uma seta terracota que quica apontando para baixo, para o botão do\n"
                "         app (C9: o gate mede o movimento). É o estilo da KEY de CTA.",
    "gigante_atras": "         Uma palavra gigante no alto da cabeça, sem dim. Encolhe até caber em 700 px (cabe inteira mesmo\n"
                     "         na escala 1,14 da entrada). Atrás da pessoa só com o recorte da W5.C; sem ele, fica por cima.",
}
_GERADOR = {"caixa_nativa": _css_caixa_nativa, "punch": _css_punch, "marcador": _css_marcador,
            "statement": _css_statement, "lateral": _css_lateral, "seta_cta": _css_seta_cta,
            "gigante_atras": _css_gigante_atras}


def css(estilo):
    """O CSS do parcial do estilo (determinístico: mesma especificação, mesmo texto)."""
    _conferir(estilo)
    if estilo == PADRAO:
        return CSS_EDITORIAL
    corpo = _GERADOR[estilo](SPEC[estilo])
    return _CABECALHO % (estilo, _COMENTARIO[estilo]) + "\n".join(corpo) + "\n"


def escrever_parciais(pasta=PARCIAIS):
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    for e in ESTILOS:
        (pasta / ("lettering_%s.css" % e)).write_text(css(e), encoding="utf-8")


def conferir_parciais(pasta=PARCIAIS):
    """[nomes dos parciais que não batem com a especificação]."""
    ruins = []
    for e in ESTILOS:
        p = Path(pasta) / ("lettering_%s.css" % e)
        if not p.is_file() or p.read_text(encoding="utf-8") != css(e):
            ruins.append(p.name)
    return ruins


def main(argv=None):
    ap = argparse.ArgumentParser(description="Estilos de lettering: gera e confere os parciais CSS.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--escrever", action="store_true", help="regrava templates/_parciais/lettering_*.css")
    g.add_argument("--conferir", action="store_true", help="sai 1 se algum parcial não bate")
    g.add_argument("--faixas", action="store_true", help="imprime as FAIXAS")
    a = ap.parse_args(argv)
    if a.escrever:
        escrever_parciais()
        print("8 parciais escritos em %s" % PARCIAIS)
        return 0
    if a.faixas:
        for nome, f in FAIXAS.items():
            print("%-22s x %4d a %4d  y %4d a %4d" % (nome, f["x0"], f["x1"], f["y0"], f["y1"]))
        return 0
    ruins = conferir_parciais()
    if ruins:
        print("parciais fora da especificação: %s (rode --escrever)" % ", ".join(ruins))
        return 1
    print("8 parciais batem com a especificação")
    return 0


if __name__ == "__main__":
    sys.exit(main())
