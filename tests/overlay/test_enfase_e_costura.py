"""W7.Z, itens 1 e 2 da prova como aluno; refeito em 10/10/2026 para o halo na base.

1. A palavra de ênfase (terracota) sobre um fundo de matiz parecido (a camisa laranja do avatar) media 1,01:1. A cor do
   destaque é decidida pelo contraste contra o fundo LOCAL, com a mesma régua do gate: a cor da marca só fica se as duas
   camadas (a acesa e a apagada do karaokê) passam de 4,5:1 com folga; senão a alternativa CLARA (amarelo), e se nem ela
   passa o destaque sai BRANCO (`cgrp-kwbranco`: sem caixa e sem placa, a palavra perde a cor e lê como o resto). Nunca
   destaque com a luminância do fundo. No halo forte (fundo claro) a mancha escura segura a terracota.
2. Em tela dividida a legenda não está mais sobre o insert (nem na costura): ela mora na base do painel do apresentador.
   No caminho sem footage (primeira rodada, mede o ARQUIVO-FONTE pela mediana) um grupo em split nunca recebe o halo
   forte pela mediana do insert, que não está atrás dele; quem decide é a medição da footage."""
from pathlib import Path

import pytest

from overlay import fundo_claro as FC

PARCIAIS = Path(__file__).resolve().parents[2] / "templates" / "_parciais"


def _lum(v):
    c = v / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _lum_rgb(rgb):
    return 0.2126 * _lum(rgb[0]) + 0.7152 * _lum(rgb[1]) + 0.0722 * _lum(rgb[2])


def _razao_rgb(rgb, fundo_cinza):
    a, b = _lum_rgb(rgb), _lum(fundo_cinza)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def _mistura(rgb, alfa, fundo):
    return tuple(c * alfa + fundo * (1 - alfa) for c in rgb)


def test_a_cor_da_marca_nao_passa_no_meio_tom_laranja_e_o_destaque_perde_a_cor_em_vez_de_ficar_ilegivel():
    # a camisa laranja do avatar: cinza de luminância parecida com a da terracota
    assert FC.decidir_enfase("clara", 90, 118) == "branca"
    assert _razao_rgb(FC.KW_MARCA, 130) < 1.6                 # o 1,0:1 da prova: a cor da marca some sobre ela


def test_fundo_escuro_deixa_a_cor_da_marca():
    assert FC.decidir_enfase("clara", 3, 15) == "marca"


def test_fundo_que_derruba_a_marca_mas_deixa_o_creme_usa_a_alternativa_clara():
    achou = [(p10, p90) for p90 in range(0, 140, 5) for p10 in range(0, p90 + 1, 5)
             if FC.decidir_tinta(p10, p90) == "clara" and FC.decidir_enfase("clara", p10, p90) == "clara"]
    assert achou, "tem que existir fundo onde o creme lê e a marca não"


@pytest.mark.parametrize("p10", range(0, 256, 15))
@pytest.mark.parametrize("p90", range(0, 256, 15))
def test_toda_decisao_com_enfase_deixa_as_camadas_do_destaque_acima_do_piso(p10, p90):
    """Propriedade: na tinta e na cor decididas, a camada acesa E a apagada do destaque passam do piso (4,5:1) contra o
    fundo crítico (p10 e p90 da caixa); no halo forte e no destaque branco a conta é a do halo (medida no gate)."""
    if p10 > p90:
        return
    tinta = FC.decidir_tinta(p10, p90, kw=True)
    enfase = tinta.enfase
    assert enfase in ("marca", "clara", "branca")
    if tinta == "halo":
        assert enfase == "marca"
        return
    if enfase == "branca":                          # nenhuma das duas cores passa: foi por isso que ficou branco
        assert not FC._camadas_ok(FC.KW_MARCA, FC.KW_MARCA_ALFA, (p10, p90))
        assert not FC._camadas_ok(FC.KW_ALT, FC.KW_ALT_ALFA, (p10, p90))
        return
    cor = {"marca": (FC.KW_MARCA, FC.KW_MARCA_ALFA), "clara": (FC.KW_ALT, FC.KW_ALT_ALFA)}[enfase]
    for f in (p10, p90):
        assert _razao_rgb(cor[0], f) >= 4.5, (p10, p90, tinta, enfase, f)
        assert _razao_rgb(_mistura(cor[0], cor[1], f), f) >= 4.5, (p10, p90, tinta, enfase, f, "apagada")


def test_sem_destaque_a_decisao_e_a_de_antes_e_nao_carrega_enfase():
    for p10, p90 in ((10, 40), (200, 245), (60, 160)):
        assert FC.decidir_tinta(p10, p90) == FC.decidir_tinta(p10, p90, kw=False)
        assert getattr(FC.decidir_tinta(p10, p90), "enfase", None) is None


def test_destaque_num_fundo_claro_vai_para_o_halo_forte_com_a_marca():
    t = FC.decidir_tinta(60, 160, kw=True)
    assert t == "halo" and t.enfase == "marca"


def test_grupo_com_palavra_de_enfase_mede_a_tinta_com_o_destaque(tmp_path, monkeypatch):
    monkeypatch.setattr(FC, "V1", tmp_path)
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "ad1_lk_footage_1x.mp4").write_bytes(b"x")
    vistos = []
    respostas = iter([FC.Tinta("clara", enfase="clara"), FC.Tinta("clara", enfase="branca"), "clara"])

    def falso(video, ini, fim, classe, kw=False):
        vistos.append(kw)
        return next(respostas)

    monkeypatch.setattr(FC, "tinta_footage", falso)
    grupos = [{"start": 1.0, "end": 2.0, "words": [{"text": "x", "kw": True}]},
              {"start": 3.0, "end": 4.0, "words": [{"text": "w", "kw": True}]},
              {"start": 5.0, "end": 6.0, "words": [{"text": "y"}]}]
    FC.marcar_grupos_claros(grupos, "ad1", "lk", [], a0=0.0)
    assert vistos == [True, True, False]
    assert grupos[0].get("kw_alt") is True and "kw_branco" not in grupos[0]
    assert grupos[1].get("kw_branco") is True and "kw_alt" not in grupos[1]
    assert "kw_alt" not in grupos[2] and "kw_branco" not in grupos[2]


def test_css_traz_a_cor_alternativa_e_o_destaque_branco_na_mesma_conta_do_motor():
    css = (PARCIAIS / "legenda.css").read_text(encoding="utf-8").replace(" ", "")

    def alfa(x):
        return ("%.2f" % x).lstrip("0")
    r, g_, b = FC.KW_ALT
    assert ".cgrp-kwalt.cw.kw.fill{color:#%02X%02X%02X;}" % (r, g_, b) in css or \
        "#caps.cgrp-kwalt.cw.kw.fill{color:#%02X%02X%02X;}" % (r, g_, b) in css
    assert "rgba(%d,%d,%d,%s)" % (r, g_, b, alfa(FC.KW_ALT_ALFA)) in css
    r, g_, b = FC.KW_MARCA
    assert "rgba(%d,%d,%d,%s)" % (r, g_, b, alfa(FC.KW_MARCA_ALFA)) in css
    assert "#caps.cgrp-kwbranco.cw.kw.fill{color:#F5EFE6;}" in css


def test_o_html_da_legenda_leva_a_classe_da_cor_alternativa_e_a_do_destaque_branco():
    import build_timeline
    g = {"start": 1.0, "end": 2.0, "kw_alt": True, "words": [{"text": "oi", "start": 1.0, "end": 1.5, "kw": True}]}
    assert "cgrp-kwalt" in build_timeline._render_captions_html([g])
    g2 = {"start": 1.0, "end": 2.0, "words": [{"text": "oi", "start": 1.0, "end": 1.5, "kw": True}]}
    assert "cgrp-kwalt" not in build_timeline._render_captions_html([g2])
    assert "cgrp-kwbranco" not in build_timeline._render_captions_html([g2])
    g3 = dict(g2, kw_branco=True)
    assert "cgrp-kwbranco" in build_timeline._render_captions_html([g3])


# --- item 2: o split não herda a mediana do insert -------------------------------------------------------------

def test_grupo_em_split_sem_footage_nao_recebe_o_halo_forte_pela_mediana_do_arquivo(tmp_path, monkeypatch):
    monkeypatch.setattr(FC, "V1", tmp_path)
    (tmp_path / "output").mkdir()
    monkeypatch.setattr(FC, "fundo_claro", lambda arquivo, t: True)
    mapa = [{"a": 10.0, "b": 14.0, "file": "ins.mp4", "start": 0.0, "speed": 1.0, "s2": 10.0}]
    grupos = [{"start": 11.0, "end": 12.0, "words": []},       # dentro do split
              {"start": 12.5, "end": 13.0, "words": []},       # dentro do split
              {"start": 13.2, "end": 13.8, "words": []}]       # insert cheio depois do split
    FC.marcar_grupos_claros(grupos, "ad1", "lk", mapa, janelas_split=[(10.0, 13.1)])
    assert "halo" not in grupos[0] and "halo" not in grupos[1]
    assert grupos[2].get("halo") is True


def test_com_footage_a_medicao_dela_manda_inclusive_no_split(tmp_path, monkeypatch):
    monkeypatch.setattr(FC, "V1", tmp_path)
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "ad1_lk_footage_1x.mp4").write_bytes(b"x")
    monkeypatch.setattr(FC, "tinta_footage", lambda *a, **k: "halo")
    grupos = [{"start": 1.0, "end": 2.0, "words": []}]
    FC.marcar_grupos_claros(grupos, "ad1", "lk", [], a0=0.0, janelas_split=[(0.0, 5.0)])
    assert grupos[0].get("halo") is True
