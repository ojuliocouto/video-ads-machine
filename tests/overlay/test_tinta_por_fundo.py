"""W5.X: o motor escolhe a tinta do texto pelo fundo LOCAL, para que todo texto passe de 4,5:1.

O invariante do gate (gates/contraste_texto) vale para as duas camadas da legenda (a acesa e a apagada do karaokê) e
para o gancho. O motor decide, por grupo de legenda e no instante dele, medindo a footage na caixa do texto:

  - tinta CLARA quando o percentil 90 do fundo é escuro o bastante para a camada APAGADA clara passar com folga;
  - tinta INVERTIDA (escura) quando o percentil 10 é claro o bastante para a camada apagada ESCURA passar;
  - PLACA (tinta clara sobre uma placa escura por palavra) no resto: meio-tom e fundo misturado (a costura do
    split, o borrado do insert). Nunca branco ou cinza sobre claro.

E o gancho ganha placa quando a footage atrás dele é clara (o insert de navegador do v1).
"""
from pathlib import Path

import pytest

from overlay import fundo_claro as FC
from overlay import hook as hook_m

RAIZ = Path(__file__).resolve().parents[2]
PARCIAIS = RAIZ / "templates" / "_parciais"


def _lum(v):
    c = v / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _razao(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


@pytest.mark.parametrize("p10,p90,esperado", [
    (10, 40, "clara"),          # parede escura do avatar
    (200, 245, "invertida"),    # página branca do insert
    (60, 160, "placa"),         # costura: metade insert claro, metade avatar escuro
    (90, 115, "placa"),         # o borrado do insert aos 5,64 s do v1 (camada apagada a 3,1:1)
    (150, 230, "placa"),        # claro com mancha: a camada apagada escura não passa no p10
])
def test_decidir_tinta(p10, p90, esperado):
    assert FC.decidir_tinta(p10, p90) == esperado


@pytest.mark.parametrize("p10", range(0, 256, 5))
@pytest.mark.parametrize("p90", range(0, 256, 5))
def test_toda_decisao_deixa_as_duas_camadas_acima_do_piso(p10, p90):
    """Propriedade: na decisão tomada, a camada acesa E a apagada passam de 4,5:1 contra o fundo crítico."""
    if p10 > p90:
        return
    d = FC.decidir_tinta(p10, p90)
    if d == "clara":
        assert _razao(FC.camada_clara(p90, apagada=True), p90) >= 4.5
        assert _razao(FC.camada_clara(p90, apagada=False), p90) >= 4.5
    elif d == "invertida":
        assert _razao(FC.camada_escura(p10, apagada=True), p10) >= 4.5
        assert _razao(FC.camada_escura(p10, apagada=False), p10) >= 4.5
    else:
        assert d == "placa"
        fundo = FC.sob_placa(p90)
        assert _razao(FC.camada_clara(fundo, apagada=True), fundo) >= 4.5


def test_css_da_legenda_tem_a_camada_apagada_escura_e_a_placa_na_mesma_conta_do_motor():
    css = (PARCIAIS / "legenda.css").read_text(encoding="utf-8")
    def alfa(x):
        return ("%.2f" % x).lstrip("0")
    assert "rgba(18,20,26,%s)" % alfa(FC.APAGADA_ESCURA_ALFA) in css.replace(" ", "")
    assert "rgba(245,239,230,%s)" % alfa(FC.APAGADA_CLARA_ALFA) in css.replace(" ", "")
    assert ".cgrp-placa" in css
    assert "rgba(8,9,14,%s)" % alfa(FC.PLACA_ALFA) in css.replace(" ", "")


def test_grupos_recebem_a_classe_da_tinta_medida_na_footage(tmp_path, monkeypatch):
    monkeypatch.setattr(FC, "V1", tmp_path)
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "ad1_lk_footage_1x.mp4").write_bytes(b"x")
    decisoes = iter(["clara", "invertida", "placa", None])
    monkeypatch.setattr(FC, "tinta_footage", lambda *a: next(decisoes))
    grupos = [{"start": i, "end": i + 1.0, "words": []} for i in range(4)]
    FC.marcar_grupos_claros(grupos, "ad1", "lk", [], a0=0.0)
    assert [(x.get("claro"), x.get("placa")) for x in grupos] == [(None, None), (True, None), (None, True),
                                                                   (None, None)]


def test_html_da_legenda_leva_a_placa():
    import build_timeline
    h = build_timeline._render_captions_html([{"start": 0.0, "end": 1.0, "placa": True,
                                               "words": [{"text": "oi", "start": 0.0, "end": 1.0}]}])
    assert "cgrp-placa" in h


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
