"""Os documentos dizem o mesmo que o código sobre o custo do avatar (20/10/2026).

O ensaio mediu US$ 7,08 por minuto de voz; a doc dizia US$ 3,20 a 4,40 por minuto e o teto era US$ 5,00. Depois da
correção: cerca de US$ 7 por minuto, anúncio de 30 s cerca de US$ 3,50, de 60 s cerca de US$ 7, teto de US$ 9,00.
Este teste trava a volta dos números velhos em qualquer documento e confere os novos nos lugares onde o aluno lê custo.
"""
from pathlib import Path

import pytest

from avatar import custo as K
from cli import avatar as CLI

RAIZ = Path(__file__).resolve().parent.parent.parent
IGNORAR = {"node_modules", ".venv", ".git", "tests", "_local", "fonts"}

NUMEROS_VELHOS = (
    "US$ 3,2 a US$ 4,4", "US$ 3,2 a 4,4", "US$ 3,20 a US$ 4,40", "US$ 3.2 and US$ 4.4", "US$ 3,2 a 3,6",
    "200 a 227 créditos", "200 to 227 credits", "60 créditos valem", "60 credits per US$ 1",
    "US$ 5,00 por job", "padrão 5.0", "US$ 5.00 cap", "teto padrão é US$ 5,00",
)


def documentos():
    achados = []
    for arq in sorted(RAIZ.rglob("*.md")):
        if IGNORAR & set(arq.relative_to(RAIZ).parts):
            continue
        achados.append(arq)
    return achados


def texto(rel):
    return (RAIZ / rel).read_text(encoding="utf-8")


def test_ha_documentos_para_varrer():
    nomes = {a.name for a in documentos()}
    assert {"README.md", "SKILL.md", "GUIA-ALUNO.md", "onboarding.md", "fase1-avatar.md"} <= nomes


@pytest.mark.parametrize("arquivo", documentos(), ids=lambda a: str(a.relative_to(RAIZ)))
def test_nenhum_documento_repete_o_numero_velho_de_custo(arquivo):
    t = arquivo.read_text(encoding="utf-8")
    velhos = [n for n in NUMEROS_VELHOS if n in t]
    assert velhos == [], "%s ainda diz %s" % (arquivo.relative_to(RAIZ), velhos)


def test_o_doctor_nao_repete_o_numero_velho():
    t = (RAIZ / "scripts" / "onboarding" / "checks" / "heygen.py").read_text(encoding="utf-8")
    assert not [n for n in NUMEROS_VELHOS if n in t]
    assert "US$ 3,50" in t and "US$ 7" in t


@pytest.mark.parametrize("rel", ["README.md", "SKILL.md", "docs/GUIA-ALUNO.md", "references/onboarding.md",
                                 "references/fase1-avatar.md"])
def test_onde_o_aluno_le_custo_os_numeros_novos_estao(rel):
    t = texto(rel)
    assert "US$ 7" in t
    assert ("US$ 9,00" in t) or ("US$ 9.00" in t) or ("--teto-usd 9" in t)


def test_o_teto_dos_documentos_e_o_do_codigo():
    assert CLI.TETO_USD == 9.0
    assert "US$ 9,00 por job" in texto("SKILL.md")
    assert "US$ 9,00 por job" in texto("references/onboarding.md")
    assert "US$ 9.00 cap" in texto("README.md")


def test_os_exemplos_de_anuncio_batem_com_a_constante():
    """30 s ~ US$ 3,50 e 60 s ~ US$ 7 são arredondamentos da constante: a conta tem que fechar."""
    assert round(K.estimar_usd(30.0), 1) in (3.5, 3.6) and round(K.estimar_usd(60.0)) == 7
    for rel in ("docs/GUIA-ALUNO.md", "references/onboarding.md", "references/fase1-avatar.md"):
        t = texto(rel)
        assert "US$ 3,50" in t and "cerca de US$ 7" in t, rel
    assert "US$ 3.50" in texto("README.md")


def test_nenhum_documento_usa_travessao_nem_meia_risca_nas_linhas_de_custo():
    for rel in ("README.md", "SKILL.md", "docs/GUIA-ALUNO.md", "references/onboarding.md", "references/fase1-avatar.md"):
        for linha in texto(rel).splitlines():
            if "US$" in linha or "custo" in linha.lower():
                assert "\u2014" not in linha and "\u2013" not in linha, (rel, linha[:80])
