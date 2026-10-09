"""overlay.hook: quanto tempo o gancho fica na tela e como ele entra no HTML.

Cada teste é um comentário de defeito do `gen_ad_v2.py` original:
  - o hook cobre o insert de abertura e dissolve no retorno do AVATAR, não em spans[1];
  - teto de 3,2 s (um anúncio com 3 inserts de abertura ficou 15,5 s com o hook parado e
    sem legenda nenhuma);
  - a legenda só começa depois do hook (cap_gate);
  - emoji sai do texto de tela; o estilo "punch" é variante, não troca global.
"""
from pathlib import Path

import pytest

from overlay import hook as K

RAIZ = Path(__file__).resolve().parents[2]


def bl(*tipos):
    return [{"type": t, "instr": f"b{i}", "narr": "x"} for i, t in enumerate(tipos)]


# --- constantes ------------------------------------------------------------------------------

def test_constantes_do_hook():
    assert K.HOOK_MAX == 3.2
    assert K.HOOK_END == 2.174          # round(2.5 / 1.15, 3): o hook encolhe com a fala acelerada


# --- calcular_hook ---------------------------------------------------------------------------

def test_abertura_no_avatar_segura_3s_e_a_legenda_espera_o_hook():
    h = K.calcular_hook(bl("orig", "insert", "orig"), [(0, 4), (4, 8), (8, 12)])
    assert not h.opening_insert
    assert (h.hook_gone, h.hook_fade, h.hook_dur, h.cap_gate) == (3.0, 2.6, 3.1, 3.0)


def test_abertura_em_insert_dissolve_no_retorno_do_avatar_mais_0_1():
    h = K.calcular_hook(bl("insert", "orig", "insert"), [(0, 2.0), (2.0, 9.0), (9.0, 12.0)])
    assert h.opening_insert
    assert h.hook_gone == 2.1                      # round(min(2.0 + 0.1, 3.2), 2)
    assert h.hook_fade == 1.7                      # comeca a dissolver 0,4 s antes
    assert h.hook_dur == 2.2                       # a janela do clip cobre ate depois do fade
    assert h.cap_gate == 2.05                      # sem legenda ate 0,05 antes do hook sumir


def test_teto_de_3_2s_no_hook_com_insert_longo_na_abertura():
    # o avatar so volta aos 15,5 s: sem teto o hook ficaria parado 15,6 s e tapava o payoff
    sp = [(0, 5), (5, 10), (10, 15.5), (15.5, 20)]
    h = K.calcular_hook(bl("insert", "insert", "insert", "orig"), sp)
    assert h.hook_gone == 3.2
    assert (h.hook_fade, h.hook_dur, h.cap_gate) == (2.8, 3.3, 3.15)


def test_o_retorno_do_avatar_e_o_primeiro_bloco_que_nao_e_insert_nao_spans_1():
    # com 3 inserts de abertura, usar spans[1] fazia o hook sumir cedo e deixava zona morta
    sp = [(0, 0.8), (0.8, 1.6), (1.6, 2.4), (2.4, 9.0)]
    h = K.calcular_hook(bl("insert", "insert", "insert", "orig"), sp)
    assert h.hook_gone == 2.5                      # spans[3][0] + 0,1, nao spans[1][0] + 0,1 = 0,9


def test_so_inserts_cai_no_bloco_1_como_retorno():
    h = K.calcular_hook(bl("insert", "insert"), [(0, 1.0), (1.0, 2.0)])
    assert h.opening_insert
    assert h.hook_gone == 1.1                      # first_avatar_i cai no default 1


def test_roteiro_de_um_bloco_so_nao_tem_insert_de_abertura():
    h = K.calcular_hook(bl("insert"), [(0, 6.0)])
    assert not h.opening_insert and h.hook_gone == 3.0


# --- aplicar_html ----------------------------------------------------------------------------

TEMPLATE = (
    '<style>\n'
    '#hook .l1 { font-family:"Inter"; font-weight:300; color:#fff;\n'
    '#hook .accent { font-family:"Playfair Display", serif; font-weight:600; font-style:italic;\n'
    '</style>\n'
    '<div data-hf-id="hf-niga" id="hook" class="clip" data-start="0" data-duration="2.5" data-track-index="44">\n'
    '<div data-hf-id="hf-bc1a" class="eyebrow">uma skill de</div>\n'
    '<div data-hf-id="hf-8q5w" class="l1">criação de</div>\n'
    '<div data-hf-id="hf-ons9" class="accent">páginas</div>\n'
    '</div>\n'
    '<script>\n'
    '      tl.to("#hook .hook-inner", { scale: 1.04, duration: 1.7, ease: "sine.inOut" }, 0.8);\n'
    '</script>\n')


def hook_padrao():
    return K.calcular_hook(bl("insert", "orig"), [(0, 2.0), (2.0, 9.0)])


def test_aplicar_html_troca_textos_duracao_e_agenda_o_fade():
    h = hook_padrao()
    html = K.aplicar_html(TEMPLATE, {"eyebrow": "MEU CLAUDE", "l1": "virou um web designer",
                                     "accent": "PROFISSIONAL"}, h)
    assert 'class="eyebrow">MEU CLAUDE</div>' in html
    assert 'class="l1">virou um web designer</div>' in html
    assert 'class="accent">PROFISSIONAL</div>' in html
    assert 'id="hook" class="clip" data-start="0" data-duration="2.2"' in html
    # o fade entra logo depois do tween de escala, na posicao hook_fade
    assert ('{ scale: 1.04, duration: 1.7, ease: "sine.inOut" }, 0.8);\n'
            '      tl.to("#hook", { opacity: 0, duration: 0.4, ease: "power1.in" }, 1.7);') in html
    assert "punch" not in html


def test_aplicar_html_centraliza_o_texto_do_l1():
    html = K.aplicar_html(TEMPLATE, {"eyebrow": "a", "l1": "b", "accent": "c"}, hook_padrao())
    assert '#hook .l1 { font-family:"Inter"; font-weight:300; color:#fff; text-align:center;' in html
    assert ('#hook .accent { font-family:"Playfair Display", serif; font-weight:600; '
            'font-style:italic; text-align:center;') in html


def test_aplicar_html_tira_emoji_do_hook():
    html = K.aplicar_html(TEMPLATE, {"eyebrow": "\U0001F680 NOVO", "l1": "sem ❌ erro",
                                     "accent": "OK ✅"}, hook_padrao())
    assert 'class="eyebrow">NOVO</div>' in html
    assert 'class="l1">sem erro</div>' in html
    assert 'class="accent">OK</div>' in html


def test_variante_punch_so_liga_com_style_punch():
    h = hook_padrao()
    sem = K.aplicar_html(TEMPLATE, {"eyebrow": "a", "l1": "b", "accent": "c"}, h)
    com = K.aplicar_html(TEMPLATE, {"eyebrow": "a", "l1": "b", "accent": "c", "style": "punch"}, h)
    assert "#hook.punch" not in sem and 'id="hook" class="clip punch"' not in sem
    assert 'id="hook" class="clip punch"' in com
    assert "#hook.punch { padding:0 140px; justify-content:flex-start !important;" in com
    assert "margin-top:310px !important" in com
    assert "font-weight:900 !important; font-size:104px !important;" in com
    assert com.index("#hook.punch") < com.index("</style>")


def test_scrim_do_punch_e_leve():
    # o quadro 0 e o poster no feed: o scrim do punch tem que ser mais leve que o do template
    html = K.aplicar_html(TEMPLATE, {"eyebrow": "a", "l1": "b", "accent": "c", "style": "punch"}, hook_padrao())
    assert "rgba(4,5,10,.26) 12%" in html and "rgba(4,5,10,.56) 24%" in html


@pytest.mark.parametrize("formato,pasta", [("9x16", "reel-editorial"), ("1x1", "reel-editorial-1x1")])
def test_aplicar_html_nos_templates_reais(formato, pasta):
    from overlay.html_injecao import ler_template   # W4.D: o template inclui parciais (o JS mora em _parciais/timeline.js)
    modelo = ler_template(RAIZ / "templates" / pasta / "index.html")
    saida = K.aplicar_html(modelo, {"eyebrow": "MEU CLAUDE", "l1": "virou", "accent": "PRO"}, hook_padrao())
    assert 'class="eyebrow">MEU CLAUDE</div>' in saida
    assert 'class="accent">PRO</div>' in saida
    assert 'tl.to("#hook", { opacity: 0, duration: 0.4, ease: "power1.in" }, 1.7);' in saida
    assert 'id="hook" class="clip" data-start="0" data-duration="2.2"' in saida
