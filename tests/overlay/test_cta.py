"""overlay.cta: quando o CTA sobe, quando o logo antecipa e como os dois entram no HTML.

Do `gen_ad_v2.py` original:

  - UMA fonte só: `cta_start`. O corte da legenda e a subida do CTA nascem do mesmo número
    (os dois desencontrados deixaram um anúncio 13 s com a tela vazia);
  - só o ÚLTIMO insert do roteiro manda no CTA: um cap no meio do anúncio não adianta o CTA;
  - a antecipação do logo é de 0,9 s e só vale quando o bloco anterior é avatar (sobre insert
    o logo entra junto com o corte, senão pousa em cima do wordmark da landing page);
  - o CTA que nasce em cima de tela dividida desce (senão pousa no rosto).
"""
import pytest

from overlay import cta as C


def blocos(*tipos):
    return [{"type": t, "instr": "x", "narr": "y"} for t in tipos]


SPANS = [(0.0, 5.0), (5.0, 10.0), (10.0, 16.0), (16.0, 20.0)]
TIPOS = blocos("insert", "orig", "insert", "orig")


# --- cta_start -------------------------------------------------------------------------------

def test_sem_cap_o_cta_sobe_no_inicio_do_ultimo_bloco():
    assert C.calcular_cta_start(TIPOS, SPANS, []) == 16.0


def test_cap_do_ultimo_insert_adianta_o_cta_pra_quando_a_imagem_volta(capsys):
    assert C.calcular_cta_start(TIPOS, SPANS, [(2, 14.0)]) == 14.0
    assert "[cta] imagem volta pro avatar em 14.00s: CTA fica 6.0s na tela" in capsys.readouterr().out


def test_cap_de_um_insert_do_meio_nao_adianta_o_cta():
    assert C.calcular_cta_start(TIPOS, SPANS, [(0, 3.0)]) == 16.0


def test_retorno_depois_do_inicio_do_ultimo_bloco_e_ignorado():
    assert C.calcular_cta_start(TIPOS, SPANS, [(2, 17.0)]) == 16.0
    assert C.calcular_cta_start(TIPOS, SPANS, [(2, 16.0)]) == 16.0       # estrito


def test_com_varios_retornos_do_mesmo_bloco_vale_o_ultimo():
    assert C.calcular_cta_start(TIPOS, SPANS, [(2, 12.0), (2, 14.5)]) == 14.5


def test_roteiro_sem_insert_nenhum_sobe_no_ultimo_bloco():
    assert C.calcular_cta_start(blocos("orig", "orig"), [(0, 5), (5, 9)], [(0, 1.0)]) == 5


# --- logo ----------------------------------------------------------------------------------------

def test_logo_antecipa_0_9s_quando_o_bloco_anterior_e_avatar():
    assert C.LOGO_LEAD == 0.9
    assert C.logo_lead(blocos("insert", "orig", "orig")) == 0.9


def test_logo_entra_junto_com_o_corte_quando_o_bloco_anterior_e_insert():
    # ad02v2: o logo caiu na landing que exibe o proprio wordmark ("Claude Codentre R$")
    assert C.logo_lead(blocos("orig", "insert", "orig")) == 0.0


def test_roteiro_de_um_bloco_so_antecipa():
    assert C.logo_lead(blocos("orig")) == 0.9


def test_inicio_do_logo_nunca_e_negativo_e_nao_e_arredondado():
    assert C.logo_start(12.3456, 0.9) == pytest.approx(11.4456)
    assert C.logo_start(0.5, 0.9) == 0.0


def test_cta_s_copia_cta_start_e_o_logo_acompanha():
    # "se mexer aqui, o cta_s acompanha sozinho"
    cta_s, logo_s = C.janela(12.3456, 0.9)
    assert cta_s == 12.35
    assert logo_s == 11.45
    assert C.janela(0.5, 0.9) == (0.5, 0.0)
    assert C.janela(14.0, 0.0) == (14.0, 14.0)


# --- aplicar_html ----------------------------------------------------------------------------------

MODELO = (
    '<div data-hf-id="hf-bi9a" id="cta" class="clip" data-start="50.4" data-duration="4.96" data-track-index="46">\n'
    '        <div data-hf-id="hf-laqu" class="lead">toca em</div>\n'
    '        <div data-hf-id="hf-wto1" class="pill" id="cta-pill">saiba mais</div>\n'
    '</div>\n'
    '<img data-hf-id="hf-zbg4" id="ev-logo" class="clip" src="logo.png" alt="x" '
    'data-start="46.7" data-duration="8.68" data-track-index="48">\n'
    '<script>\n'
    'tl.to("#cta", { opacity: 1, duration: 0.35 }, 50.5);\n'
    'tl.to("#cta .lead", { opacity: 1 }, 50.6);\n'
    'tl.to("#cta-pill", { opacity: 1 }, 50.75);\n'
    'tl.to("#cta .pill .arw", { y: 8 }, 51.0);\n'
    'tl.to("#ev-logo", { opacity: 1 }, 46.9);\n'
    '</script>\n')


def test_html_agenda_cta_e_logo_nos_tempos_calculados():
    html = C.aplicar_html(MODELO, {}, 12.3, 11.4, 20.7, [])
    assert 'data-start="12.3" data-duration="8.4" data-track-index="46"' in html
    assert 'data-start="11.4" data-duration="9.3" data-track-index="48"' in html
    assert '}, 12.40);' in html and '}, 12.50);' in html and '}, 12.65);' in html and '}, 12.90);' in html
    assert '}, 11.60);' in html
    assert "50.4" not in html and "46.7" not in html and "46.9" not in html


def test_rotulo_do_cta_vem_da_config_e_o_padrao_e_saiba_mais():
    html = C.aplicar_html(MODELO, {"cta_label": "ver agora"}, 12.3, 11.4, 20.7, [])
    assert 'id="cta-pill">ver agora</div>' in html
    assert 'id="cta-pill">saiba mais</div>' in C.aplicar_html(MODELO, {}, 12.3, 11.4, 20.7, [])


def test_cta_sem_lead_tira_o_toca_em(capsys):
    html = C.aplicar_html(MODELO, {"cta_sem_lead": True}, 12.3, 11.4, 20.7, [])
    assert "toca em" not in html
    assert "[cta] sem o lead 'toca em': so pill + logo" in capsys.readouterr().out
    assert "toca em" in C.aplicar_html(MODELO, {}, 12.3, 11.4, 20.7, [])


def test_cta_em_tela_dividida_desce_o_cta_e_o_logo(capsys):
    html = C.aplicar_html(MODELO, {}, 12.3, 11.4, 20.7, [(10.0, 15.0)])
    assert 'id="cta" class="clip cta-split"' in html
    assert 'id="ev-logo" class="clip logo-split"' in html
    assert "[cta] 12.30s cai em tela dividida: descendo o CTA e o logo (senao pousam no rosto)" \
           in capsys.readouterr().out


def test_cta_fora_do_split_ou_na_borda_final_nao_desce():
    for janelas in ([(1.0, 5.0)], [(10.0, 12.3)], []):
        html = C.aplicar_html(MODELO, {}, 12.3, 11.4, 20.7, janelas)
        assert "cta-split" not in html and "logo-split" not in html, janelas


def test_cta_na_borda_inicial_do_split_desce():
    html = C.aplicar_html(MODELO, {}, 12.3, 11.4, 20.7, [(12.3, 15.0)])
    assert "cta-split" in html


@pytest.mark.parametrize("pasta", ["reel-editorial", "reel-editorial-1x1"])
def test_nos_templates_reais_nenhum_tempo_do_modelo_sobra(pasta):
    from pathlib import Path
    from overlay.html_injecao import ler_template   # W4.D: o template inclui parciais (o JS mora em _parciais/timeline.js)
    modelo = ler_template(Path(__file__).resolve().parents[2] / "templates" / pasta / "index.html")
    html = C.aplicar_html(modelo, {}, 12.3, 11.4, 20.7, [])
    assert 'data-start="50.4" data-duration="4.96"' not in html
    assert 'data-start="46.7" data-duration="8.68"' not in html
    assert "}, 50.5);" not in html and "}, 46.9);" not in html


# --- W3.X M5: o que a timeline registra é o que o overlay desenha, nos DOIS templates ----------------------------
# O rótulo do botão nunca entrava no 9x16 (o template tem `saiba mais<i class="arw"></i>` e a troca procurava
# `saiba mais</div>`), e o `cta_sem_lead` nunca funcionava no 1x1 (o template diz "toque em" e a troca procurava
# "toca em"). A troca agora acha os elementos pelo `data-hf-id`, não pelo texto que o template escreveu.

import re  # noqa: E402
from pathlib import Path  # noqa: E402

TEMPLATES = ["reel-editorial", "reel-editorial-1x1"]


def _template(pasta):
    return (Path(__file__).resolve().parents[2] / "templates" / pasta / "index.html").read_text(encoding="utf-8")


def _texto_do_botao(html):
    m = re.search(r'<div data-hf-id="hf-wto1" class="pill" id="cta-pill">([^<]*)', html)
    return m.group(1) if m else None


@pytest.mark.parametrize("pasta", TEMPLATES)
def test_m5_rotulo_do_cta_entra_nos_dois_templates_reais(pasta):
    html = C.aplicar_html(_template(pasta), {"cta_label": "ver agora"}, 12.3, 11.4, 20.7, [])
    assert _texto_do_botao(html) == "ver agora"


def test_m5_rotulo_no_9x16_mantem_a_seta_do_botao():
    html = C.aplicar_html(_template("reel-editorial"), {"cta_label": "ver agora"}, 12.3, 11.4, 20.7, [])
    assert 'id="cta-pill">ver agora<i class="arw"></i></div>' in html


@pytest.mark.parametrize("pasta", TEMPLATES)
def test_m5_cta_sem_lead_tira_o_lead_nos_dois_templates_reais(pasta):
    assert 'data-hf-id="hf-laqu"' in _template(pasta)
    html = C.aplicar_html(_template(pasta), {"cta_sem_lead": True}, 12.3, 11.4, 20.7, [])
    assert 'data-hf-id="hf-laqu"' not in html


def test_m5_template_sem_o_botao_avisa_que_o_rotulo_nao_entrou(capsys):
    html = C.aplicar_html("<div>sem cta</div>", {"cta_label": "ver agora"}, 12.3, 11.4, 20.7, [])
    assert "ver agora" not in html
    err = capsys.readouterr().err
    assert "ver agora" in err and "AVISO" in err
