"""W5.X, refeito em 10/10/2026: o motor escolhe o HALO da legenda pelo fundo LOCAL, para que todo texto passe de 4,5:1.

O invariante do gate (gates/contraste_texto) vale para as duas camadas da legenda (a acesa e a apagada do karaokê) e
para o gancho. A legenda é BRANCA com halo escuro, sem caixa (dono, "Sim pros 2"). O motor decide, por grupo de legenda
e no instante dele, medindo a footage na caixa do texto (o 1% mais claro, p99):

  - halo NORMAL (`clara`) quando o fundo crítico é de até `LIMIAR_HALO_FORTE` (118 de cinza): medido no render real,
    o gate lê 16:1 sobre 22 e 5,0:1 sobre 110;
  - halo FORTE (`halo`, a classe `cgrp-halo`) acima disso: medido, 4,9:1 sobre 125 e 17:1 sobre 245. Nunca caixa,
    faixa, placa, nem tinta invertida (escura sobre fundo claro: contradiz "texto branco com halo");
  - a cor do destaque (a palavra de ênfase) cai para o amarelo e, se nem ele lê, sai BRANCA (`cgrp-kwbranco`).

E o gancho ganha placa quando a footage atrás dele é clara (o insert de navegador do v1): a placa do GANCHO fica.
"""
from pathlib import Path

import pytest

from overlay import fundo_claro as FC
from overlay import hook as hook_m

RAIZ = Path(__file__).resolve().parents[2]
PARCIAIS = RAIZ / "templates" / "_parciais"


@pytest.mark.parametrize("p10,p90,esperado", [
    (10, 40, "clara"),          # parede escura do avatar
    (60, 118, "clara"),         # o limite: ainda halo normal
    (60, 119, "halo"),          # um passo acima: halo forte
    (200, 245, "halo"),         # página branca do insert
    (60, 160, "halo"),          # meio-tom claro
    (90, 115, "clara"),         # o borrado do insert aos 5,64 s do v1 (a camada apagada a 3,1:1): o halo normal o segura
])
def test_decidir_tinta(p10, p90, esperado):
    assert FC.decidir_tinta(p10, p90) == esperado


@pytest.mark.parametrize("p10", range(0, 256, 5))
@pytest.mark.parametrize("p90", range(0, 256, 5))
def test_a_decisao_e_so_pelo_fundo_critico_e_nunca_inventa_tinta_antiga(p10, p90):
    """Propriedade: duas tintas só (clara e halo), a fronteira é o LIMIAR_HALO_FORTE, e o destaque nunca fica sem cor."""
    if p10 > p90:
        return
    d = FC.decidir_tinta(p10, p90)
    assert d == ("halo" if p90 > FC.LIMIAR_HALO_FORTE else "clara")
    assert d not in ("invertida", "placa")
    assert FC.decidir_tinta(p10, p90, kw=True).enfase in ("marca", "clara", "branca")


@pytest.mark.parametrize("tinta,p10,p90,esperado", [
    ("halo", 150, 250, "marca"),       # a mancha escura do halo forte segura qualquer cor
    ("clara", 5, 15, "marca"),         # fundo bem escuro: a terracota lê
    ("clara", 20, 60, "clara"),        # a terracota não lê (a camisa), o amarelo lê
    ("clara", 60, 110, "branca"),      # nem a terracota nem o amarelo: o destaque sai branco
])
def test_a_cor_do_destaque_pelo_fundo(tinta, p10, p90, esperado):
    assert FC.decidir_enfase(tinta, p10, p90) == esperado


def test_css_da_legenda_tem_a_camada_apagada_e_os_dois_halos_na_mesma_conta_do_motor():
    css = (PARCIAIS / "legenda.css").read_text(encoding="utf-8")
    def alfa(x):
        return ("%.2f" % x).lstrip("0")
    assert "rgba(245,239,230,%s)" % alfa(FC.APAGADA_CLARA_ALFA) in css.replace(" ", "")
    assert "#caps .cgrp-halo .cw .base" in css and "#caps .cgrp-kwbranco" in css
    assert "rgba(18,20,26" not in css.replace(" ", "")                  # a tinta escura da inversão morreu


def test_grupos_recebem_a_classe_do_halo_medido_na_footage(tmp_path, monkeypatch):
    monkeypatch.setattr(FC, "V1", tmp_path)
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "ad1_lk_footage_1x.mp4").write_bytes(b"x")
    decisoes = iter(["clara", "halo", "halo", None])
    monkeypatch.setattr(FC, "tinta_footage", lambda *a: next(decisoes))
    grupos = [{"start": i, "end": i + 1.0, "words": []} for i in range(4)]
    FC.marcar_grupos_claros(grupos, "ad1", "lk", [], a0=0.0)
    assert [x.get("halo") for x in grupos] == [None, True, True, None]
    assert not any("claro" in x or "placa" in x for x in grupos)


def test_html_da_legenda_leva_o_halo_forte():
    import build_timeline
    h = build_timeline._render_captions_html([{"start": 0.0, "end": 1.0, "halo": True,
                                               "words": [{"text": "oi", "start": 0.0, "end": 1.0}]}])
    assert "cgrp-halo" in h and "cplaca" not in h


# --- o gancho -----------------------------------------------------------------------------------------------------

def test_gancho_pede_placa_sobre_footage_clara(monkeypatch):
    monkeypatch.setattr(FC, "_percentis_banda", lambda v, t, y0, y1, x0, x1: (180, 240))
    assert FC.hook_pede_placa("f.mp4", 0.4, 3.2, "9x16") is True
    monkeypatch.setattr(FC, "_percentis_banda", lambda v, t, y0, y1, x0, x1: (10, 60))
    assert FC.hook_pede_placa("f.mp4", 0.4, 3.2, "9x16") is False


def test_gancho_mede_a_janela_inteira_no_relogio_da_footage(monkeypatch):
    vistas = []
    monkeypatch.setattr(FC, "_percentis_banda", lambda v, t, y0, y1, x0, x1: vistas.append(t) or (10, 60))
    FC.hook_pede_placa("f.mp4", 0.4, 3.2, "9x16")
    assert min(vistas) >= 0.0 and max(vistas) <= 3.2 - 0.4 + 1e-6 and len(vistas) >= 5


def test_aplicar_html_com_placa():
    h = hook_m.calcular_hook([{"type": "insert"}, {"type": "apresentador"}], [(0.0, 3.6), (3.6, 6.0)])
    base = ('<div data-hf-id="hf-niga" id="hook" class="clip" data-start="0" data-duration="2.5" '
            'data-track-index="44"></div>')
    sem = hook_m.aplicar_html(base, {"eyebrow": "a", "l1": "b", "accent": "c"}, h)
    com = hook_m.aplicar_html(base, {"eyebrow": "a", "l1": "b", "accent": "c", "placa": True}, h)
    assert 'class="clip placa"' in com and "placa" not in sem
    assert "#hook.placa" in (PARCIAIS / "hook.css").read_text(encoding="utf-8")


def test_ajuste_do_destaque_usa_a_largura_util_do_bloco():
    """2º render da W5.X: o destaque ajustado pelo clientWidth (que inclui a folga da placa) vazava dela e o gate
    mediu 1,7:1 no "NAL" de PROFISSIONAL sobre a página clara. O ajuste desconta a folga interna."""
    js = (PARCIAIS / "timeline.js").read_text(encoding="utf-8")
    assert "paddingLeft" in js and "paddingRight" in js
    assert "#hook.placa .hook-inner" in (PARCIAIS / "hook.css").read_text(encoding="utf-8")
