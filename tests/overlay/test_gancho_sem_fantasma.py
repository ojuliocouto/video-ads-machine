"""W5.Y: o gancho sem fantasma (pedido do dono depois de ler a folha da W5.X). A metade da W5.Y sobre a placa única da
legenda acabou em 10/10/2026 com a placa: a legenda não tem mais faixa nem caixa (ver test_legenda_halo_na_base).

GANCHO SEM FANTASMA: o gancho dissolvia por cima da legenda que já tinha entrado (2,08 s). Regra: o gancho
termina de sair ANTES da primeira legenda entrar; nunca dois textos visíveis ao mesmo tempo.
"""
import re
from pathlib import Path

import pytest

from overlay import hook as K
from overlay import legendas as G

RAIZ = Path(__file__).resolve().parents[2]
PARCIAIS = RAIZ / "templates" / "_parciais"
JS = (PARCIAIS / "timeline.js").read_text(encoding="utf-8")


def _grupo(n_palavras, placa, start=1.0):
    ws = [{"text": f"p{i}", "start": start + i * 0.3, "end": start + i * 0.3 + 0.3} for i in range(n_palavras)]
    return {"start": start, "end": start + 0.3 * n_palavras, "words": ws}


# --- o gancho sai antes da legenda entrar ---------------------------------------------------------------------

def _fim_do_gancho(html):
    m = re.search(r'tl\.to\("#hook", \{ opacity: 0, duration: ([0-9.]+), ease: "[a-z0-9.]+" \}, ([0-9.]+)\);', html)
    assert m, "o fade do gancho não está no HTML"
    return float(m.group(2)) + float(m.group(1))


def _avanco_da_legenda():
    m = re.search(r"Math\.max\(0, gStart - ([0-9.]+)\)", JS)
    assert m, "timeline.js não antecipa a entrada da legenda"
    return float(m.group(1))


TEMPLATE_HOOK = ('<div data-hf-id="hf-niga" id="hook" class="clip" data-start="0" data-duration="2.5" '
                 'data-track-index="44"></div>\n'
                 'tl.to("#hook .hook-inner", { scale: 1.04, duration: 1.7, ease: "sine.inOut" }, 0.8);')

CASOS = [
    (["insert", "orig", "insert"], [(0, 2.0), (2.0, 9.0), (9.0, 12.0)]),     # abertura em insert: o caso do v2
    (["insert", "orig"], [(0, 2.174), (2.174, 9.0)]),
    (["insert", "insert", "insert", "orig"], [(0, 5), (5, 10), (10, 15.5), (15.5, 20)]),   # teto de 3,2 s
    (["insert", "insert", "insert", "orig"], [(0, 0.8), (0.8, 1.6), (1.6, 2.4), (2.4, 9.0)]),
    (["orig", "insert", "orig"], [(0, 4), (4, 8), (8, 12)]),                 # abertura no avatar: 3 s
]


@pytest.mark.parametrize("tipos,spans", CASOS)
def test_o_gancho_termina_de_sair_antes_da_primeira_legenda_entrar(tipos, spans):
    blocos = [{"type": t, "instr": f"b{i}", "narr": "x"} for i, t in enumerate(tipos)]
    h = K.calcular_hook(blocos, spans)
    html = K.aplicar_html(TEMPLATE_HOOK, {"eyebrow": "a", "l1": "b", "accent": "c"}, h)
    fim_gancho = _fim_do_gancho(html)
    # grupos de legenda do corpo, incluindo os que já começavam com o gancho na tela (entram aparados em cap_gate)
    grupos = [dict(_grupo(3, False, start=s), end=s + 0.9) for s in (0.0, h.cap_gate - 0.4, h.cap_gate, h.cap_gate + 0.5)]
    corpo = G.filtrar_corpo(grupos, h.cap_gate)
    assert corpo, "o caso precisa ter legenda depois do gancho"
    entra = min(max(0.0, g["start"] - _avanco_da_legenda()) for g in corpo)    # o grupo SÓ aparece a partir daqui
    assert fim_gancho < entra, (fim_gancho, entra)


@pytest.mark.parametrize("tipos,spans", CASOS)
def test_gancho_e_legenda_nunca_com_opacidade_acima_de_zero_no_mesmo_intervalo(tipos, spans):
    blocos = [{"type": t, "instr": f"b{i}", "narr": "x"} for i, t in enumerate(tipos)]
    h = K.calcular_hook(blocos, spans)
    html = K.aplicar_html(TEMPLATE_HOOK, {"eyebrow": "a", "l1": "b", "accent": "c"}, h)
    gancho = (0.0, _fim_do_gancho(html))
    grupos = [dict(_grupo(2, False, start=h.cap_gate), end=h.cap_gate + 1.0)]
    legenda = (max(0.0, grupos[0]["start"] - _avanco_da_legenda()), grupos[0]["end"])
    assert gancho[1] <= legenda[0] or legenda[1] <= gancho[0]


def test_a_dissolucao_do_gancho_e_curta():
    """Dissolver por 0,4 s empurrava o fim do gancho por cima da legenda: a saída é curta (<= 0,2 s)."""
    h = K.calcular_hook([{"type": "insert", "instr": "i", "narr": "x"}, {"type": "orig", "instr": "o", "narr": "y"}],
                        [(0, 2.0), (2.0, 9.0)])
    html = K.aplicar_html(TEMPLATE_HOOK, {"eyebrow": "a", "l1": "b", "accent": "c"}, h)
    dur = float(re.search(r'tl\.to\("#hook", \{ opacity: 0, duration: ([0-9.]+)', html).group(1))
    assert 0 < dur <= 0.2


def test_o_avanco_documentado_no_hook_e_o_do_timeline():
    assert K.AVANCO_LEGENDA == _avanco_da_legenda()
