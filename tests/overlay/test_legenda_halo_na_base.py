"""10/10/2026 (dono, "Sim pros 2"): a legenda é texto BRANCO com halo escuro delicado, na BASE do quadro.

Testes vermelhos antes da mudança (a regra anterior: faixa e placa preta atrás da frase, legenda no peito, legenda
cortada no CTA):

  1. nenhuma regra de legenda com fundo, caixa, faixa ou placa (a placa do GANCHO fica);
  2. o y da legenda está na base: caixa em y 1682 e o centro da linha perto de y 1660, tudo dentro da zona segura (1690);
  3. a legenda está presente durante o CTA, acima da pílula;
  4. grupos de 3 a 4 palavras; o halo forte só entra em fundo claro, também sem caixa;
  5. o mesmo padrão no gravado (ASS): Outline 0, base do quadro, halo borrado e translúcido.
"""
import re
from pathlib import Path

import build_timeline
from gravado import legendar
from overlay import cta as OC
from overlay import fundo_claro as FC
from overlay import html_injecao as H
from overlay import layout_texto as LT
from overlay import legendas as LG

RAIZ = Path(__file__).resolve().parents[2]
CSS = (RAIZ / "templates" / "_parciais" / "legenda.css").read_text(encoding="utf-8")
JS = (RAIZ / "templates" / "_parciais" / "timeline.js").read_text(encoding="utf-8")
INDEX = H.ler_template(RAIZ / "templates" / "reel-editorial" / "index.html")
CTA_CSS = (RAIZ / "templates" / "_parciais" / "cta.css").read_text(encoding="utf-8")
TETO_UI_Y = 1690
PILULA_TOPO_Y = 1219        # o topo da pílula do CTA no 9x16 (cta.css e o comentário do index.html: y ~1219-1350)


def sem_comentarios(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def regras(css):
    """[(seletor, corpo)] das regras do CSS sem comentários."""
    return [(m.group(1).strip(), m.group(2)) for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", sem_comentarios(css))]


def por_seletor(css):
    """{seletor: corpos juntos} (o mesmo seletor pode ter mais de uma regra)."""
    saida = {}
    for seletor, corpo in regras(css):
        saida[seletor] = saida.get(seletor, "") + " " + corpo
    return saida


def pal(texto, a, b, **extra):
    d = {"text": texto, "start": a, "end": b}
    d.update(extra)
    return d


# --- 1. sem caixa, sem faixa, sem placa ------------------------------------------------------------------

def test_nenhuma_regra_da_legenda_tem_fundo_caixa_faixa_ou_placa():
    for seletor, corpo in regras(CSS) + regras(INDEX):
        if "#caps" not in seletor:
            continue
        for proibida in ("background", "border", "box-shadow", "outline", "backdrop-filter"):
            assert proibida not in corpo, (seletor, corpo)


def test_a_placa_e_a_tinta_invertida_da_legenda_acabaram_no_css_no_js_e_no_html():
    for nome, texto in (("css", sem_comentarios(CSS)), ("index", sem_comentarios(INDEX)), ("js", JS)):
        for morta in ("cplaca", "cgrp-placa", "cgrp-claro", "cgrp-baixa", "cgrp-costura"):
            assert morta not in texto, (nome, morta)
    grupo = {"start": 1.0, "end": 2.0, "words": [pal("oi", 1.0, 1.4)], "placa": True, "claro": True, "baixa": True,
             "costura": True}
    html = build_timeline._render_captions_html([grupo])
    assert "cplaca" not in html and "cgrp-placa" not in html and "cgrp-claro" not in html
    assert "cgrp-baixa" not in html and "cgrp-costura" not in html


def test_o_halo_e_sombra_difusa_em_camadas_sem_borda_dura_e_o_forte_soma_camadas():
    por = por_seletor(CSS)
    normal = por["#caps .cw .base"]
    assert "text-shadow" in normal
    sombras = re.findall(r"(\d+)(?:px)?\s+(\d+)(?:px)?\s+(\d+)px\s+rgba", normal)       # x, y e raio de cada camada
    assert len(sombras) >= 3, normal
    assert all(int(raio) >= 4 for _x, _y, raio in sombras), normal            # nada de sombra dura
    assert all(int(x) == 0 for x, _y, _r in sombras), normal                   # nenhum deslocamento lateral: halo, não sombra
    forte = por["#caps .cgrp-halo .cw .base"]
    assert forte.count("#000") + forte.count("rgba(0") > len(sombras)         # mais camadas que o halo normal
    assert "text-stroke" not in sem_comentarios(CSS) and "paint-order" not in sem_comentarios(CSS)


# --- 2. o y da legenda: a base do quadro -----------------------------------------------------------------

def _geometria_da_legenda():
    por = por_seletor(INDEX)
    cgrp = por["#caps .cgrp"]
    bottom = int(re.search(r"bottom:\s*(\d+)px", cgrp).group(1))
    corpo = int(re.search(r"font-size:\s*(\d+)px", por["#caps .cw"]).group(1))
    return bottom, corpo, por


def test_a_legenda_mora_na_base_do_quadro_centro_perto_de_y_1660_dentro_da_zona_segura():
    bottom, corpo, por = _geometria_da_legenda()
    fim_da_caixa = 1920 - bottom
    linha = corpo * 1.14                       # line-height de legenda.css
    centro = fim_da_caixa - linha / 2
    assert 1640 <= centro <= 1670, centro      # "centro da linha perto de y 1660"
    assert fim_da_caixa <= TETO_UI_Y           # tinta dentro da zona segura (a UI do Reels começa em 1690)
    assert LT.FAIXA_LEGENDA["base"][1] == fim_da_caixa
    assert LT.FAIXA_LEGENDA["base"][1] <= TETO_UI_Y
    assert LT.Y_CENTRO_BASE == round(centro)
    # uma linha de 56 px não quebra em x 140 a 940: o recuo lateral é o da coluna de curtir e comentar
    assert re.search(r"padding:\s*0\s+140px", por["#caps .cgrp"])


def test_uma_posicao_so_em_avatar_cheio_insert_e_split():
    assert LT.classe_do_grupo({}) == "base"
    assert LT.classe_do_grupo({"baixa": True, "costura": True}) == "base"      # as flags de layout morreram
    assert LT.classe_do_grupo({"acima_cta": True}) == "acima_cta"
    assert set(LT.FAIXA_LEGENDA) == {"base", "acima_cta"}


# --- 3. a legenda não some no CTA ------------------------------------------------------------------------

def test_a_legenda_continua_durante_o_cta_e_sobe_para_acima_da_pilula():
    palavras = [pal("e", 8.0, 8.2), pal("se", 8.2, 8.4), pal("inscrever", 8.4, 8.9), pal("enquanto", 8.9, 9.4),
                pal("as", 9.4, 9.6), pal("vagas", 9.6, 10.1), pal("estiverem", 10.1, 10.7), pal("abertas.", 10.7, 11.4)]
    logo_start = 9.0
    grupos = LG.agrupar(palavras)
    grupos = LG.filtrar_corpo(grupos, 0.0)
    grupos = LG.fechar_grupos(grupos, logo_start)
    cobertas = {w["text"] for g in grupos for w in g["words"]}
    assert cobertas == {w["text"] for w in palavras}, cobertas     # as 9 palavras finais ficam legendadas
    depois = [g for g in grupos if g["start"] >= logo_start - 1e-9]
    assert depois and all(g.get("acima_cta") for g in depois)
    assert not any(g.get("acima_cta") for g in grupos if g["end"] <= logo_start)
    assert all(g["start"] < g["end"] and g["end"] - g["start"] >= LG.PISO_GRUPO for g in grupos)
    assert all(LT.classe_do_grupo(g) == ("acima_cta" if g.get("acima_cta") else "base") for g in grupos)
    html = build_timeline._render_captions_html(grupos)
    assert "cgrp-acima-cta" in html


def test_o_grupo_que_atravessa_o_logo_e_partido_por_palavra_e_nao_perde_palavra():
    g = {"start": 8.0, "end": 10.0, "words": [pal("o", 8.0, 8.3), pal("motor", 8.3, 8.9), pal("e", 9.1, 9.3),
                                              pal("mais", 9.3, 10.0)]}
    saida = LG.fechar_grupos([g], 9.0)
    assert [[w["text"] for w in x["words"]] for x in saida] == [["o", "motor"], ["e", "mais"]]
    assert saida[0]["end"] == 9.0 and saida[1]["start"] == 9.0 and saida[1]["acima_cta"] and not saida[0].get("acima_cta")


def test_o_texto_da_legenda_do_cta_termina_acima_do_lead_e_da_pilula_e_abaixo_do_peito_do_queixo():
    por = por_seletor(INDEX)
    bottom = int(re.search(r"bottom:\s*(\d+)px", por["#caps .cgrp.cgrp-acima-cta"]).group(1))
    fim_da_caixa = 1920 - bottom
    cta_bottom = int(re.search(r"bottom:\s*(\d+)px", por["#cta"]).group(1))
    lead_topo = PILULA_TOPO_Y - 30 - 38 * 1.2          # o gap de 30 px do CTA e o lead de 38 px
    assert fim_da_caixa <= lead_topo - 20, (fim_da_caixa, lead_topo)       # sem encostar no lead nem na pílula
    assert LT.FAIXA_LEGENDA["acima_cta"][1] == fim_da_caixa
    assert cta_bottom == 570                                                # a conta acima parte do CTA de hoje
    html = OC.aplicar_html('<div id="caps" class="clip"></div><div id="cta" class="clip"></div>'
                           '<img id="ev-logo" class="clip">', {}, 40.0, 39.1, 45.0, [(38.0, 42.0)])
    assert "caps-cta-split" in html                                         # CTA em tela dividida: a legenda sobe junto


# --- 4. grupos de 3 a 4 palavras; halo forte só em fundo claro ----------------------------------------------

def test_grupos_de_3_a_4_palavras_sem_estourar_a_linha():
    fala = "e se inscrever enquanto as vagas estiverem abertas para quem quer aprender hoje mesmo sem pagar nada".split()
    words = [pal(w, i * 0.4, i * 0.4 + 0.35) for i, w in enumerate(fala)]
    grupos = LG.agrupar(words)
    tamanhos = [len(g["words"]) for g in grupos]
    assert LG.MAX_PALAVRAS == 4 and max(tamanhos) <= 4
    assert sum(1 for n in tamanhos if n >= 3) >= len(tamanhos) - 2, tamanhos      # a regra é 3 a 4, o resto é ponta
    for g in grupos:
        assert sum(len(w["text"]) for w in g["words"]) <= LG.MAX_CHARS, [w["text"] for w in g["words"]]


def test_halo_forte_so_em_fundo_claro_e_escuro_fica_no_halo_normal():
    assert FC.decidir_tinta(20, 60) == "clara"
    assert FC.decidir_tinta(40, FC.LIMIAR_HALO_FORTE) == "clara"
    assert FC.decidir_tinta(150, 250) == "halo"
    grupos = [{"start": 0.0, "end": 1.0, "words": [pal("a", 0.0, 0.5)], "halo": True},
              {"start": 1.0, "end": 2.0, "words": [pal("b", 1.0, 1.5)]}]
    html = build_timeline._render_captions_html(grupos)
    assert html.count("cgrp-halo") == 1
    assert "background" not in html and "cplaca" not in html


# --- 5. o gravado (ASS): o mesmo padrão ---------------------------------------------------------------------

def _estilo_base():
    cab = legendar.cabecalho()
    linha = [l for l in cab.splitlines() if l.startswith("Style: Base")][0]
    formato = [l for l in cab.splitlines() if l.startswith("Format: Name, Fontname")][0]
    nomes = [c.strip() for c in formato.replace("Format:", "").split(",")]
    return dict(zip(nomes, [c.strip() for c in linha.replace("Style:", "").split(",")]))


def test_gravado_legenda_na_base_sem_caixa_com_halo_borrado_e_translucido():
    e = _estilo_base()
    assert float(e["Outline"]) == 0.0 and float(e["Shadow"]) == 0.0, e         # nenhum contorno nem sombra dura
    assert e["BorderStyle"] == "1", e                                           # 3 seria a caixa opaca atrás do texto
    assert e["PrimaryColour"].upper().endswith("FFFFFF"), e                     # branca
    base = 1920 - int(e["MarginV"])
    assert legendar.Y_LEGENDA == base <= TETO_UI_Y
    assert 1640 <= base - int(e["Fontsize"]) * 1.2 / 2 <= 1670                  # centro da linha perto de y 1660
    assert int(e["MarginL"]) == int(e["MarginR"]) == 140
    assert legendar.MAX_PALAVRAS == 4
    texto, _ = legendar.ass_texto([pal("oi", 0.0, 0.3), pal("pessoal.", 0.3, 0.8)])
    dialogo = [l for l in texto.splitlines() if l.startswith("Dialogue")][0]
    bord = int(re.search(r"\\bord(\d+)", dialogo).group(1))
    blur = int(re.search(r"\\blur(\d+)", dialogo).group(1))
    alfa = int(re.search(r"\\3a&H([0-9A-F]{2})&", dialogo).group(1), 16)
    assert blur > bord > 0 and alfa >= 0x40, dialogo       # halo: mais borrado que largo e deixa o fundo passar
