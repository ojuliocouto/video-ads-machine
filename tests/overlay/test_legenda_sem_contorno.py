"""W7.Y, refeito em 10/10/2026: a legenda não tem contorno por palavra, nem caixa, nem faixa (dono: "tava com um contorno em
cada palavra, não tava legal"; "Sim pros 2": texto branco com halo escuro delicado, na base do quadro).

Vale nos dois caminhos: o avatar (templates/_parciais/legenda.css) e o gravado (estilo ASS, campo Outline). Os testes do
padrão novo inteiro (base, CTA, halo forte, 3 a 4 palavras, ASS) moram em test_legenda_halo_na_base.py; aqui fica o que
a correção original do contorno tinha que segurar.
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


def test_legenda_do_avatar_tem_halo_difuso_sem_deslocamento_duro():
    base = re.search(r"#caps \.cw \.base \{ text-shadow:([^;]*);", sem_comentarios(CSS)).group(1)
    raios = [float(x) for x in re.findall(r"\d+px\s+\d+px\s+(\d+)px\s+rgba", base.replace("0 0 ", "0px 0px ").replace("0 2px", "0px 2px"))]
    assert len(raios) >= 3 and min(raios) >= 4, base       # desfoque a partir de 4 px: nada de sombra dura de 1 a 3 px


def test_nao_ha_mais_faixa_nem_placa_na_legenda_so_o_halo():
    regras = sem_comentarios(CSS)
    assert ".cplaca" not in regras and ".cgrp-placa" not in regras and ".cgrp-claro" not in regras
    assert ".cgrp-halo" in regras


def test_estilo_ass_do_gravado_tem_outline_e_sombra_zero():
    linha = [l for l in legendar.cabecalho().splitlines() if l.startswith("Style: Base")][0]
    formato = [l for l in legendar.cabecalho().splitlines() if l.startswith("Format: Name, Fontname")][0]
    nomes = [c.strip() for c in formato.replace("Format:", "").split(",")]
    estilo = dict(zip(nomes, [c.strip() for c in linha.replace("Style:", "").split(",")]))
    assert float(estilo["Outline"]) == 0.0, estilo
    assert float(estilo["Shadow"]) == 0.0, estilo          # o halo é um evento borrado e translúcido, não a sombra dura
    assert estilo["BorderStyle"] == "1"                    # BorderStyle 3 seria a caixa opaca atrás do texto
