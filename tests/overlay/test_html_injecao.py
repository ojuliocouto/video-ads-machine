"""overlay.html_injecao: as trocas de texto que o gerador faz no template, uma por função.

Cada teste nasce de um defeito ou de uma decisão documentada em comentário no
`gen_ad_v2.py` original. O valor esperado foi lido do código original (as strings
exatas que ele passava para `str.replace` e `re.sub`).
"""
from pathlib import Path

import pytest

from overlay import html_injecao as H

RAIZ = Path(__file__).resolve().parents[2]
TEMPLATES = {
    "9x16": RAIZ / "templates" / "reel-editorial" / "index.html",
    "1x1": RAIZ / "templates" / "reel-editorial-1x1" / "index.html",
}


# --- sem_emoji (19/08/2026) ---------------------------------------------------------

def test_sem_emoji_tira_pictogramas_e_marcadores_de_variacao():
    # 0x1F000 em diante, 0x2600 a 0x27BF, a estrela 2B50, o seletor FE0F e o ZWJ 200D
    assert H.sem_emoji("sem \U0001F680 tempo") == "sem tempo"
    assert H.sem_emoji("❌ errado ✅") == "errado"
    assert H.sem_emoji("nota ⭐️") == "nota"
    assert H.sem_emoji("a‍b") == "ab"


def test_sem_emoji_tira_o_check_do_texto_de_tela():
    # o U+2713 cai na faixa 0x2600 a 0x27BF: "✓ em minutos" vira "em minutos" na tela
    assert H.sem_emoji("✓ em minutos") == "em minutos"


def test_sem_emoji_preserva_acento_e_colapsa_espacos():
    assert H.sem_emoji("  Ação   de   hoje \n") == "Ação de hoje"


def test_sem_emoji_aceita_o_que_nao_e_texto():
    assert H.sem_emoji(12) == "12"


# --- marcadores e duração ------------------------------------------------------------

def test_injetar_marcadores_troca_legendas_e_letterings():
    html = "a<!-- INJECT:captions -->b<!-- INJECT:letterings -->c"
    assert H.injetar_marcadores(html, "CAPS", "LETTS") == "aCAPSbLETTSc"


def test_injetar_chips_troca_o_marcador_e_remove_os_de_preset():
    html = "x<!-- INJECT:chips -->y<!-- INJECT:preset:cores -->z<!--INJECT:preset:ritmo-fino-->w"
    assert H.injetar_chips(html, "CHIPS") == "xCHIPSyzw"


def test_injetar_chips_sem_marcador_nao_mexe():
    # o template 1x1 nao tem <!-- INJECT:chips -->
    assert H.injetar_chips("<div></div>", "CHIPS") == "<div></div>"


def test_fixar_duracao_troca_toda_ocorrencia_da_duracao_do_template():
    # no template o root, o a-roll e o audio carregam o mesmo 55.36: os tres acompanham
    html = ('<div data-start="0" data-duration="55.36" id="root">'
            '<video data-start="0" data-duration="55.36"></video>'
            '<div data-start="0" data-duration="2.5"></div></div>')
    saida = H.fixar_duracao(html, 18.7)
    assert saida.count('data-start="0" data-duration="18.7"') == 2
    assert 'data-start="0" data-duration="2.5"' in saida
    assert "55.36" not in saida


# --- grade, beat P&B, wipes -----------------------------------------------------------

def test_suavizar_grade_corta_a_grade_quente_pela_metade():
    html = ("radial-gradient(130% 100% at 50% 22%, rgba(255,193,128,0.16), "
            "rgba(255,150,80,0.05) 45%, transparent 72%) "
            "linear-gradient(180deg, rgba(255,168,92,0.06) 0%, transparent 38%, "
            "rgba(28,14,4,0.16) 100%)")
    saida = H.suavizar_grade(html)
    assert "rgba(255,193,128,0.08), rgba(255,150,80,0.025) 45%" in saida
    assert "rgba(255,168,92,0.03) 0%, transparent 38%, rgba(28,14,4,0.16) 100%" in saida
    assert "0.16), rgba(255,150,80,0.05)" not in saida


@pytest.mark.parametrize("formato", ["9x16", "1x1"])
def test_suavizar_grade_acha_as_duas_strings_nos_templates_reais(formato):
    html = H.ler_template(TEMPLATES[formato])   # W4.D: o template inclui parciais
    assert H.suavizar_grade(html) != html


def test_remover_beat_pb_troca_o_bloco_inteiro_pelo_comentario():
    html = ("antes\n// ===== BEAT PRETO E BRANCO (manifesto x) =====\n"
            "tl.to(\"#a-roll\", { \"--bw\": 1 }, 3);\n"
            "tl.to(\"#a-roll\", { \"--bw\": 0, duration: 1 }, 4);\ndepois\n")
    saida = H.remover_beat_pb(html)
    assert saida == "antes\n// (beat P&B do reelC nao usado)\ndepois\n"


def test_remover_beat_pb_nos_templates_reais_deixa_so_o_comentario():
    for formato, caminho in TEMPLATES.items():
        saida = H.remover_beat_pb(H.ler_template(caminho))
        assert "// (beat P&B do reelC nao usado)" in saida, formato
        assert "BEAT PRETO E BRANCO" not in saida, formato


def test_remover_wipes_apaga_o_marcador_e_nao_injeta_nada():
    # WIPE DE GRADE DESLIGADO (19/08/2026): wipe_js = ""
    assert H.remover_wipes("a /* INJECT:wipes */ b") == "a  b"
