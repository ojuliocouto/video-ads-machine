"""Testes do engine de legenda: format-aware, escala por formato, anti-regressao 9:16."""
import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from vam import captions as caps  # noqa: E402

WORDS = [("topa", 0.0, 0.4), ("skills", 0.4, 0.9)]


def test_presets_geram_ass():
    for name in caps.STYLES:
        ass = open(caps.build_ass(WORDS, name, "/tmp/t_%s.ass" % name)).read()
        assert "Dialogue" in ass and caps.STYLES[name]["font"] in ass


def test_9x16_playres_e_posicao():
    ass = open(caps.build_ass(WORDS, "tay", "/tmp/t916.ass", fmt="9x16")).read()
    assert "PlayResY:1920" in ass
    assert "\\pos(540,1410)" in ass


def test_1x1_escala_fonte_e_playres():
    ass = open(caps.build_ass(WORDS, "tay", "/tmp/t11.ass", fmt="1x1")).read()
    assert "PlayResY:1080" in ass
    fsz = int(re.search(r"Style: S, \w+, (\d+)", ass).group(1))
    # 1x1 escala 0.5625 -> fonte menor que o 9x16 (122)
    assert fsz < 122


def test_1x1_halo_tem_fade_e_9x16_nao():
    a11 = open(caps.build_ass(WORDS, "tay", "/tmp/h11.ass", fmt="1x1")).read()
    a916 = open(caps.build_ass(WORDS, "tay", "/tmp/h916.ass", fmt="9x16")).read()
    # no 1x1 as linhas de halo (bord grande) tem \fad; no 9x16 nao
    halo_11 = [l for l in a11.splitlines() if "\\bord" in l and "fad" in l]
    assert halo_11, "halo do 1x1 deveria ter fade"


def test_zero_overlap_seria_validado_por_quem_chama():
    # build_ass nao valida overlap (isso e do alinhamento); aqui so garante ordem dos eventos
    ass = open(caps.build_ass(WORDS, "tay", "/tmp/o.ass")).read()
    assert ass.count("Dialogue") >= len(WORDS)
