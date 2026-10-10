"""W7.Y: a legenda não tem contorno por palavra (dono, 10/10/2026: "tava com um contorno em cada palavra, não tava
legal"). Texto limpo com sombra suave difusa, sem borda dura; sobre fundo claro segue a faixa escura única.

Vale nos dois caminhos: o avatar (templates/_parciais/legenda.css) e o gravado (estilo ASS, campo Outline).
"""
import re
from pathlib import Path

from gravado import legendar

RAIZ = Path(__file__).resolve().parents[2]
CSS = (RAIZ / "templates" / "_parciais" / "legenda.css").read_text(encoding="utf-8")


def sem_comentarios(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def test_nenhuma_regra_da_legenda_tem_text_stroke():
    regras = sem_comentarios(CSS)
    assert "text-stroke" not in regras, re.findall(r"[^;{}]*text-stroke[^;}]*", regras)
    assert "paint-order" not in regras


def test_legenda_do_avatar_tem_sombra_difusa_sem_deslocamento_duro():
    cw = re.search(r"#caps \.cw \{ font-family.*?\}", sem_comentarios(CSS), flags=re.S).group(0)
    assert "drop-shadow" in cw and "text-shadow" in cw
    raios = [float(x) for x in re.findall(r"shadow\([^)]*?\d+px\s+(\d+)px", cw)]
    assert raios and min(raios) >= 8, cw       # desfoque grande: nada de sombra dura de 2 a 4 px


def test_faixa_unica_sobre_fundo_medio_continua():
    regras = sem_comentarios(CSS)
    assert ".cplaca" in regras and ".cgrp-placa" in regras


def test_estilo_ass_do_gravado_tem_outline_zero():
    linha = [l for l in legendar.cabecalho().splitlines() if l.startswith("Style: Base")][0]
    campos = linha.split(",")
    formato = [l for l in legendar.cabecalho().splitlines() if l.startswith("Format: Name, Fontname")][0]
    nomes = [c.strip() for c in formato.replace("Format:", "").split(",")]
    estilo = dict(zip(nomes, [c.strip() for c in linha.replace("Style:", "").split(",")]))
    assert float(estilo["Outline"]) == 0.0, estilo
    assert float(estilo["Shadow"]) > 0.0, estilo
