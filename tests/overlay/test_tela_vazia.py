"""overlay.tela_vazia: o gate barato de tela vazia, antes do render.

O gate final mede o MOV com alpha e custava 13 minutos de render para reprovar um anúncio com
13 s de tela vazia (build de 17/08). Aqui a mesma conta sai de graça: a união das janelas de
texto (hook, legenda, lettering, CTA) e o maior buraco. Causa raiz que motivou o gate: cortar
a legenda num tempo e subir o CTA em outro.

Duas travas, nesta ordem (a do CTA vem primeiro, como no original):
  - a janela do CTA suprime a legenda do corpo: acima de 12 s de áudio o anúncio roda mudo;
  - o maior vão sem nenhum texto: acima de 3,3 s de áudio (cerca de 2,4 s de tela) aborta.
"""
import pytest

from overlay import tela_vazia as T


def g(a, b):
    return {"start": a, "end": b, "words": []}


def test_limites():
    assert T.MAX_JANELA_CTA == 12.0
    assert T.MAX_VAO == 3.3


# --- maior_vao ---------------------------------------------------------------------------------

def test_maior_vao_e_a_uniao_das_janelas_menos_o_total():
    janelas = [(0.0, 3.1), (3.0, 5.0), (8.0, 9.0), (12.0, 20.0)]
    assert T.maior_vao(janelas, 20.0) == (3.0, 5.0)


def test_empate_fica_com_o_primeiro_vao():
    assert T.maior_vao([(0.0, 1.0), (3.0, 4.0), (6.0, 7.0)], 7.0) == (2.0, 1.0)


def test_vao_no_comeco_conta():
    assert T.maior_vao([(1.5, 5.0)], 5.0) == (1.5, 0.0)


def test_vao_no_fim_conta():
    assert T.maior_vao([(0.0, 5.0)], 12.0) == (7.0, 5.0)


def test_janelas_fora_de_ordem_sao_ordenadas_e_sobrepostas_se_fundem():
    assert T.maior_vao([(6.0, 9.0), (0.0, 4.0), (3.0, 7.0)], 9.0) == (0.0, 0.0)


# --- checar -----------------------------------------------------------------------------------------

def test_anuncio_sem_buraco_passa_e_devolve_o_maior_vao(capsys):
    pior, quando = T.checar(2.0, [g(2.0, 6.0), g(7.0, 12.0)], [(12.5, 14.0)], 16.0, 20.0)
    assert (pior, quando) == (2.0, 14.0)
    saida = capsys.readouterr().out
    assert "[cta] janela do CTA: 4.00s de audio (2.96s de tela, teto 12.0s)" in saida
    assert "[tela] maior vao sem texto: 2.00s de audio em 14.00s (teto 3.3s)" in saida


def test_vao_de_3_25s_passa_e_de_3_5s_aborta():
    T.checar(2.0, [g(2.0, 3.0), g(6.25, 9.0)], [], 9.0, 10.0)
    with pytest.raises(SystemExit) as e:
        T.checar(2.0, [g(2.0, 3.0), g(6.5, 9.0)], [], 9.0, 10.0)
    assert str(e.value).startswith("TELA VAZIA: 3.50s sem nenhum texto a partir de 3.00s (audio). "
                                   "Quase sempre e o corte da legenda (cta_start) desencontrado")


def test_cta_a_16s_do_fim_aborta_com_a_porcentagem_do_anuncio_com_o_cta_na_tela():
    with pytest.raises(SystemExit) as e:
        T.checar(2.0, [g(2.0, 5.0)], [], 5.0, 20.0)
    msg = str(e.value)
    assert msg.startswith("JANELA DE CTA LONGA DEMAIS: 15.00s de audio a partir de 5.00s, "
                          "num total de 20.00s. O CTA fica na tela por 75% do anuncio.")
    assert "um insert com dur_max no MEIO do roteiro puxando o cta_start pra tras." in msg


def test_janela_de_cta_de_exatos_12s_ainda_passa():
    T.checar(2.0, [g(2.0, 8.0)], [], 8.0, 20.0)


def test_a_trava_do_cta_vem_antes_da_do_vao():
    # os dois estouram: o aviso que sai e o do CTA
    with pytest.raises(SystemExit) as e:
        T.checar(1.0, [], [], 2.0, 20.0)
    assert str(e.value).startswith("JANELA DE CTA LONGA DEMAIS")


def test_o_hook_e_o_cta_tambem_contam_como_texto():
    # sem legenda nenhuma, o hook ate 2,5 s e o CTA a partir de 4,0 s deixam 1,5 s de vao
    pior, quando = T.checar(2.5, [], [], 4.0, 6.0)
    assert (pior, quando) == (1.5, 2.5)


# --- W3.X M2: a janela do CTA no relógio em que o teto foi calibrado -----------------------------------------
# O teto de 12 s foi calibrado no relógio do overlay antigo, que ia até o fim do ÁUDIO mais a folga de cauda
# (TAIL_PAD). Com a timeline o total do overlay é o fim da fala, e a mesma janela media menos (no fixture, 3,13 s
# viraram 2,16 s): o teto ficava mais frouxo sem ninguém decidir. Com `fim_janela_cta` a conta é a de antes.

def test_m2_janela_do_cta_usa_o_fim_do_relogio_antigo_quando_dado():
    T.checar(2.0, [g(2.0, 9.0)], [], 9.0, 18.0)                       # 9,0 s no total da timeline: passa
    with pytest.raises(SystemExit) as e:
        T.checar(2.0, [g(2.0, 9.0)], [], 9.0, 18.0, fim_janela_cta=21.5)   # 12,5 s no relógio antigo: aborta
    assert str(e.value).startswith("JANELA DE CTA LONGA DEMAIS: 12.50s de audio a partir de 9.00s")


def test_m2_sem_fim_dado_a_conta_e_a_de_sempre():
    with pytest.raises(SystemExit):
        T.checar(2.0, [g(2.0, 5.0)], [], 5.0, 20.0, fim_janela_cta=None)


def test_m2_o_vao_continua_medido_no_total_da_tela():
    """O fim do relógio antigo só mede a janela do CTA; o vão sem texto é sobre o que a tela mostra."""
    pior, _ = T.checar(2.0, [g(2.0, 9.0)], [], 9.0, 18.0, fim_janela_cta=19.5)
    assert pior == pytest.approx(0.0)
