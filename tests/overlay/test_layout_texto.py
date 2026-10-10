"""overlay.layout_texto: a faixa da legenda (uma posição só) e as janelas de layout (avatar cheio, split, insert).

É a fonte única da faixa de legenda. Desde 10/10/2026 (dono, "Sim pros 2") a legenda mora na BASE do quadro em todo
layout, e no CTA logo acima da pílula: acabaram as regras que quebravam o grupo na fronteira de uma troca de layout,
desciam a legenda sobre card com texto, subiam para a costura do split e baixavam no look fechado (testes apagados junto
com as funções). Ficaram as janelas por visita de insert e o relógio da footage:

  - o relógio da footage manda no tempo; o layout (split x cheio/pip) é do overlay.
"""
import json

from pathlib import Path

import pytest

from overlay import layout_texto as LT
from overlay.brolls import Visita


def pal(texto, a, b):
    return {"text": texto, "start": a, "end": b}


def grupo(*palavras, **extra):
    g = {"start": palavras[0]["start"], "end": palavras[-1]["end"], "words": list(palavras)}
    g.update(extra)
    return g


# --- constantes e classe -------------------------------------------------------------------

def test_faixas_de_cada_classe_de_legenda():
    assert LT.FAIXA_LEGENDA == {"base": (1554, 1682), "acima_cta": (972, 1100)}


def test_so_ha_duas_classes_a_base_e_acima_do_cta():
    assert LT.classe_do_grupo({}) == "base"
    assert LT.classe_do_grupo({"acima_cta": True}) == "acima_cta"
    assert LT.classe_do_grupo({"baixa": True, "costura": True}) == "base"      # as flags de layout morreram


def test_as_regras_de_posicao_por_layout_morreram_com_a_posicao_unica():
    for morta in ("cortar_na_fronteira", "marcar_costura", "empurrar_pos_split", "descer_para_rodape_em_texto",
                  "baixar_no_look_fechado", "look_fechado", "GUARDA_POS_SPLIT", "PISO_FATIA", "QUEIXO_FECHADO"):
        assert not hasattr(LT, morta), morta


def test_a_faixa_da_base_bate_com_a_caixa_do_template_e_fica_dentro_da_zona_segura():
    """A faixa do layout e o CSS são a mesma medida: a caixa termina em y 1682 (bottom 238 px), o teto da UI é 1690."""
    css = (Path(__file__).resolve().parents[2] / "templates" / "reel-editorial" / "index.html").read_text(encoding="utf-8")
    assert "#caps .cgrp { bottom:238px;" in css and LT.FAIXA_LEGENDA["base"][1] == 1920 - 238 <= 1690
    assert "#caps .cgrp.cgrp-acima-cta { bottom:820px; }" in css and LT.FAIXA_LEGENDA["acima_cta"][1] == 1920 - 820


# --- janelas por visita -----------------------------------------------------------------------

def visita(i=0, icfg=None, s=0.0, e=10.0, s2=None, meus=None, cheias=None):
    s2 = s if s2 is None else s2
    return Visita(i=i, key="k", icfg=icfg or {"file": "a.mp4"}, s=s, e=e, s2=s2, dur=e - s2,
                  meus=meus if meus is not None else [(s2, e)], cheias=cheias or set())


def test_insert_de_tela_cheia_vai_para_janelas_de_texto_e_a_legenda_desce_pro_rodape():
    split, texto, mapa = LT.janelas_por_visita([visita(meus=[(2.0, 4.0), (6.0, 12.0)], e=10.0)])
    assert split == []
    # o fim e cortado no fim do bloco (min(b2, e))
    assert texto == [(2.0, 4.0), (6.0, 10.0)]


def test_insert_com_split_vai_para_janelas_de_split():
    split, texto, _ = LT.janelas_por_visita(
        [visita(icfg={"file": "a.mp4", "split": True}, meus=[(2.0, 4.0)], e=10.0)])
    assert split == [(2.0, 4.0)] and texto == []


def test_fatia_cheia_de_um_insert_split_conta_como_tela_cheia():
    # LAYOUT POR FATIA, NAO POR BLOCO (27/08/2026): a fatia `cheio` nao tem apresentador embaixo
    split, texto, _ = LT.janelas_por_visita(
        [visita(icfg={"file": "a.mp4", "split": True}, meus=[(2.0, 4.0), (6.0, 8.0)], e=10.0,
                cheias={(6.0, 8.0)})])
    assert split == [(2.0, 4.0)]
    assert texto == [(6.0, 8.0)]


def test_texto_proprio_acrescenta_a_janela_inteira_do_insert():
    _, texto, _ = LT.janelas_por_visita(
        [visita(icfg={"file": "a.mp4", "split": True, "texto_proprio": True}, s=1.0, e=9.0, s2=1.0,
                meus=[(1.0, 5.0)])])
    assert texto == [(1.0, 9.0)]


def test_mapa_do_insert_guarda_janela_fonte_start_e_velocidade():
    _, _, mapa = LT.janelas_por_visita(
        [visita(icfg={"file": "a.mp4", "start": 1.5, "speed": 2.0}, s=3.0, e=9.0, s2=3.0,
                meus=[(3.0, 5.0), (7.0, 12.0)])])
    assert mapa == [
        {"a": 3.0, "b": 5.0, "file": "a.mp4", "start": 1.5, "speed": 2.0, "s2": 3.0},
        {"a": 7.0, "b": 9.0, "file": "a.mp4", "start": 1.5, "speed": 2.0, "s2": 3.0}]


def test_mapa_do_insert_tem_start_0_e_velocidade_1_por_padrao():
    _, _, mapa = LT.janelas_por_visita([visita(icfg={"file": "a.mp4", "start": None}, meus=[(0.0, 4.0)])])
    assert (mapa[0]["start"], mapa[0]["speed"]) == (0.0, 1.0)


# --- o relogio da footage (28/08/2026) -----------------------------------------------------------

@pytest.fixture
def footage_json(tmp_path, monkeypatch):
    monkeypatch.setattr(LT, "V1", tmp_path)
    (tmp_path / "output").mkdir()

    def gravar(segs, ad="ad1", look="lk"):
        (tmp_path / "output" / f"{ad}_{look}_footage_1x_ritmo.json").write_text(
            json.dumps({"segs": segs}), encoding="utf-8")
    return gravar


def test_janelas_de_split_vem_da_footage_mas_so_as_que_o_overlay_chama_de_split(footage_json, capsys):
    # o insert `pip`/`cheio` e `split` no plano de ritmo cru e tela cheia na tela
    footage_json([{"s": 2.1, "e": 6.14, "layout": "split"},
                  {"s": 20.0, "e": 24.0, "layout": "split"},         # sem janela do overlay por perto
                  {"s": 30.0, "e": 32.0, "layout": "cheio"}])
    novo = LT.aplicar_relogio_footage("ad1", "lk", [(2.0, 6.0)])
    assert novo == [(2.1, 6.14)]
    saida = capsys.readouterr().out
    assert "[relogio] janelas de split da FOOTAGE (ad1_lk_footage_1x_ritmo.json): 1 no lugar das 1 do overlay" in saida
    assert "1 descartada(s): tela cheia (cheio/pip), nao split" in saida


def test_interseccao_exige_mais_de_0_05s_de_sobreposicao(footage_json):
    footage_json([{"s": 6.04, "e": 8.0, "layout": "split"}])
    # sobrepoe 6.04 a 6.0? nao: a janela do overlay termina em 6.0; sobreposicao negativa
    assert LT.aplicar_relogio_footage("ad1", "lk", [(2.0, 6.0)]) == [(2.0, 6.0)]
    footage_json([{"s": 5.96, "e": 8.0, "layout": "split"}])
    assert LT.aplicar_relogio_footage("ad1", "lk", [(2.0, 6.0)]) == [(2.0, 6.0)]      # 0,04 s: pouco
    footage_json([{"s": 5.9, "e": 8.0, "layout": "split"}])
    assert LT.aplicar_relogio_footage("ad1", "lk", [(2.0, 6.0)]) == [(5.9, 8.0)]      # 0,10 s: passa


def test_overlay_sem_janela_de_split_aceita_as_da_footage(footage_json, capsys):
    footage_json([{"s": 4.0, "e": 7.0, "layout": "split"}])
    assert LT.aplicar_relogio_footage("ad1", "lk", []) == [(4.0, 7.0)]
    assert "1 janelas (overlay nao marcou nenhuma)" in capsys.readouterr().out


def test_nenhuma_janela_da_footage_encosta_nas_do_overlay_mantem_as_do_overlay(footage_json):
    footage_json([{"s": 40.0, "e": 45.0, "layout": "split"}])
    assert LT.aplicar_relogio_footage("ad1", "lk", [(2.0, 6.0)]) == [(2.0, 6.0)]


def test_sem_json_da_footage_ou_com_json_ilegivel_segue_com_o_do_overlay(tmp_path, footage_json, capsys):
    assert LT.aplicar_relogio_footage("ad1", "lk", [(2.0, 6.0)]) == [(2.0, 6.0)]     # primeira rodada
    (tmp_path / "output" / "ad1_lk_footage_1x_ritmo.json").write_text("{nao e json", encoding="utf-8")
    assert LT.aplicar_relogio_footage("ad1", "lk", [(2.0, 6.0)]) == [(2.0, 6.0)]
    assert "footage json ilegivel" in capsys.readouterr().out


def test_footage_sem_nenhum_split_nao_mexe(footage_json):
    footage_json([{"s": 0.0, "e": 5.0, "layout": "cheio"}])
    assert LT.aplicar_relogio_footage("ad1", "lk", [(2.0, 6.0)]) == [(2.0, 6.0)]
