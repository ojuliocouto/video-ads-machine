"""W7.Z, item 3 da prova como aluno: a cama subia de +11 a +21 dB nas pausas (esperado de +1,5 a +8).

CAUSA (medida na prova): a automação dava à cama um nível ABSOLUTO nas pausas (0,42 sobre uma trilha a -20 dBFS: música a
-27,5 dBFS), e o gate mede a subida SOBRE A VOZ SOZINHA naquela pausa. A voz da prova, isolada, tem piso de -36 a -55 dBFS
nas pausas e a trilha tem a dinâmica dela (de -25 a -33 dBFS no mesmo ganho): a subida era a diferença entre dois números
que nada amarrava. A automação passa a fechar a conta pausa a pausa: o ganho de cada pausa sai do nível MEDIDO da voz ali e
do nível MEDIDO da trilha ali, para a subida cair no centro da faixa (+4,75 dB), com 0,42 como TETO. O piso de referência
da subida é o nível audível (-40 dBFS: abaixo dele a pausa já está mascarada pelo ambiente de quem ouve), e as pausas dentro
do fade de entrada e do fade de saída da trilha não entram na régua (a cama está sumindo ali, de propósito)."""
import math

import pytest

from cinema import musica


def lin(db):
    return 10.0 ** (db / 10.0)


# --- a expressão com um nível por pausa ------------------------------------------------------------------------

def test_pausa_com_cama_propria_vira_o_platoe_dela_na_expressao():
    expr = musica.expressao_volume([(5.0, 6.0, 0.20), (20.0, 21.0, 0.30)])
    assert "(0.2-0.055)" in expr and "(0.3-0.055)" in expr
    assert musica.ganho_no_instante(5.5, [(5.0, 6.0, 0.20)]) == pytest.approx(0.20)
    assert musica.ganho_no_instante(20.5, [(5.0, 6.0, 0.20), (20.0, 21.0, 0.30)]) == pytest.approx(0.30)


def test_pausa_sem_cama_propria_segue_com_a_cama_global():
    assert musica.ganho_no_instante(5.5, [(5.0, 6.0)]) == pytest.approx(musica.CAMA_PAUSA)
    assert musica.expressao_volume([(5.0, 6.0)]) == musica.expressao_volume([(5.0, 6.0)], 0.055, 0.42, 0.15)


def test_rampas_de_cada_pausa_vao_da_cama_fala_ate_o_platoe_proprio():
    pausas = [(5.0, 6.0, 0.20)]
    assert musica.ganho_no_instante(5.0, pausas) == pytest.approx(musica.CAMA_FALA)
    meia = musica.ganho_no_instante(5.075, pausas)
    assert musica.CAMA_FALA < meia < 0.20 and meia == pytest.approx((musica.CAMA_FALA + 0.20) / 2, abs=1e-6)


def test_as_pausas_da_expressao_continuam_legiveis_com_cama_propria():
    expr = musica.expressao_volume([(5.0, 6.0, 0.2), (20.0, 21.5, 0.3)])
    assert musica.pausas_da_expressao(expr) == [(5.0, 6.0), (20.0, 21.5)]


def test_o_timeline_grava_a_cama_de_cada_pausa_e_o_teto_global():
    d = musica.ducking_para_timeline([(5.0, 6.0, 0.2), (20.0, 21.0)])
    assert d["cama_pausa"] == musica.CAMA_PAUSA                                # o teto
    assert d["pausas"][0] == {"s": 5.0, "e": 6.0, "cama": 0.2}
    assert d["pausas"][1] == {"s": 20.0, "e": 21.0}


# --- a conta do ganho de cada pausa ------------------------------------------------------------------------------

def test_fator_de_rampa_pausa_curta_perde_a_janela_de_meio_segundo():
    # 0,5 s de pausa com rampas de 0,15 s: a janela de 0,5 s do gate pega as duas rampas (~60% da potência do platô)
    assert musica.fator_de_rampa(5.0, 5.5, 0.15) == pytest.approx(0.60, abs=0.03)
    assert musica.fator_de_rampa(5.0, 6.0, 0.15) == pytest.approx(1.0, abs=0.01)    # platô cobre a janela inteira
    assert 0.6 < musica.fator_de_rampa(5.0, 5.7, 0.15) < 1.0


@pytest.mark.parametrize("voz_db,trilha_db", [(-38.8, -23.0), (-36.3, -22.0), (-45.7, -22.5), (-33.0, -20.0),
                                              (-60.0, -21.0), (-28.0, -16.0)])
def test_ganho_da_pausa_leva_a_subida_ao_centro_da_faixa(voz_db, trilha_db):
    g = musica.cama_da_pausa(voz_db, trilha_db, fator_rampa=1.0)
    assert musica.CAMA_FALA <= g <= musica.CAMA_PAUSA
    assert musica.delta_previsto_db(voz_db, trilha_db, g, 1.0) == pytest.approx(musica.CAMA_ALVO_DB, abs=0.02)


def test_centro_da_faixa_e_o_meio_de_1_5_a_8():
    assert musica.CAMA_ALVO_DB == pytest.approx((1.5 + 8.0) / 2)
    assert musica.PAUSA_SOBE_DB == (1.5, 8.0)


def test_voz_mais_baixa_que_o_piso_audivel_mede_a_subida_contra_o_piso():
    """Voz a -55 dBFS na pausa (quase silêncio): a subida é medida contra -40 dBFS, o ambiente de quem ouve. Contra a voz
    sozinha qualquer música pareceria +15 dB."""
    g = musica.cama_da_pausa(-55.0, -22.0, fator_rampa=1.0)
    final_db = 10 * math.log10(lin(-55.0) + lin(-22.0) * g * g)
    assert final_db - musica.PISO_AUDIVEL_DB == pytest.approx(musica.CAMA_ALVO_DB, abs=0.02)
    assert musica.PISO_AUDIVEL_DB == -40.0


def test_ganho_nunca_passa_do_teto_nem_cai_abaixo_da_cama_sob_a_fala():
    assert musica.cama_da_pausa(-30.0, -70.0, fator_rampa=1.0) == pytest.approx(musica.CAMA_PAUSA)     # trilha sumindo
    assert musica.cama_da_pausa(-70.0, -10.0, fator_rampa=1.0) >= musica.CAMA_FALA                    # trilha altíssima


def test_pausa_curta_ganha_mais_ganho_para_compensar_a_rampa():
    cheio = musica.cama_da_pausa(-38.0, -22.0, fator_rampa=1.0)
    curto = musica.cama_da_pausa(-38.0, -22.0, fator_rampa=0.6)
    assert curto == pytest.approx(cheio / math.sqrt(0.6), rel=1e-6)


def test_cadeia_da_trilha_sem_automacao_para_medir_a_trilha_como_ela_chega():
    sem = musica.cadeia_da_trilha("[0:a]", "[m]", 40.0, 6.2, None)
    com = musica.cadeia_da_trilha("[0:a]", "[m]", 40.0, 6.2, "0.055")
    assert "volume=volume=" not in sem and "volume=volume=" in com
    assert sem.startswith("[0:a]atrim=0:40.000") and "afade=t=out" in sem
