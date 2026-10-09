"""pausas_reais (W1.C): a pausa sai do ENVELOPE do áudio, nunca do buraco da transcrição.

Porte da detecção da esteira de VSL, sem nome de cliente. Os fixtures vêm de
tests/fixtures/sinteticos.py: tons com silêncio exato em intervalos conhecidos e ruído rosa.
"""
import numpy as np
import pytest

from audio import pausas_reais
from tests.fixtures import sinteticos as fx

TOLERANCIA = 0.05  # s, o tamanho da janela do envelope

# (início, fim) conhecidos: 0,6 s, 0,8 s, 1,2 s e 2,0 s
PAUSAS_CONHECIDAS = ((1.5, 2.1), (4.0, 4.8), (6.5, 7.7), (9.0, 11.0))


def _casar(achadas, esperadas):
    """Para cada pausa esperada, a achada mais próxima; devolve o maior erro de borda."""
    assert len(achadas) == len(esperadas), f"achei {achadas}, esperava {esperadas}"
    pior = 0.0
    for (ei, ef), (ai, af) in zip(sorted(esperadas), sorted(achadas)):
        pior = max(pior, abs(ai - ei), abs(af - ef))
    return pior


def test_acha_pausas_de_0_6_0_8_1_2_e_2_0_s_com_erro_ate_0_05(tmp_path):
    arq = fx.tom_com_pausas(tmp_path / "tom.wav", dur=14.0, pausas=PAUSAS_CONHECIDAS)
    achadas = pausas_reais.pausas(str(arq))
    assert _casar(achadas, PAUSAS_CONHECIDAS) <= TOLERANCIA + 1e-9


def test_pausas_com_borda_no_meio_da_janela_tambem_ficam_em_0_05(tmp_path):
    # as bordas caem no meio de uma janela de 50 ms: o pior caso do envelope
    desalinhadas = ((1.53, 2.14), (4.02, 4.83), (6.47, 7.71), (9.04, 11.01))
    arq = fx.tom_com_pausas(tmp_path / "tom.wav", dur=14.0, pausas=desalinhadas)
    achadas = pausas_reais.pausas(str(arq))
    assert _casar(achadas, desalinhadas) <= TOLERANCIA + 1e-9


def test_monologo_sem_vale_devolve_lista_vazia(tmp_path):
    tom = fx.tom_com_pausas(tmp_path / "tom.wav", dur=6.0, pausas=())
    ruido = fx.ruido_rosa(tmp_path / "rosa.wav", dur=6.0)
    assert pausas_reais.pausas(str(tom)) == []
    assert pausas_reais.pausas(str(ruido)) == []


def test_pausa_menor_que_o_minimo_nao_conta(tmp_path):
    arq = fx.tom_com_pausas(tmp_path / "tom.wav", dur=6.0, pausas=((2.0, 2.3),))
    assert pausas_reais.pausas(str(arq)) == []                    # 0,3 s < 0,5 s
    assert len(pausas_reais.pausas(str(arq), dur_min_s=0.25)) == 1


def test_limiar_e_relativo_a_mediana_da_voz(tmp_path):
    # a mesma pausa num tom 30 dB mais baixo é achada igual: nada de limiar absoluto
    alto = fx.tom_com_pausas(tmp_path / "alto.wav", dur=6.0, pausas=((2.0, 3.0),), volume_db=-6.0)
    baixo = fx.tom_com_pausas(tmp_path / "baixo.wav", dur=6.0, pausas=((2.0, 3.0),), volume_db=-36.0)
    assert _casar(pausas_reais.pausas(str(alto)), ((2.0, 3.0),)) <= TOLERANCIA + 1e-9
    assert _casar(pausas_reais.pausas(str(baixo)), ((2.0, 3.0),)) <= TOLERANCIA + 1e-9


def test_vale_que_nao_e_silencio_tambem_conta(tmp_path):
    # queda de 18 dB (não digital): é pausa relativa à voz
    ff = [
        "-f", "lavfi", "-i",
        "sine=frequency=220:sample_rate=48000:duration=6,"
        "volume=enable='between(t,2,3)':volume=0.125",
        "-c:a", "pcm_s16le", "-ac", "1",
    ]
    arq = fx._ffmpeg(ff, tmp_path / "vale.wav")
    assert _casar(pausas_reais.pausas(str(arq)), ((2.0, 3.0),)) <= TOLERANCIA + 1e-9


def test_envelope_db_tem_uma_janela_a_cada_50_ms(tmp_path):
    arq = fx.tom_com_pausas(tmp_path / "tom.wav", dur=2.0, pausas=())
    db, jan = pausas_reais.envelope_db(str(arq))
    assert jan == pytest.approx(0.05)
    assert len(db) == 40


def test_pausas_do_envelope_e_pura_e_nao_chama_ffmpeg():
    # 40 janelas de 50 ms: voz em -20 dB, vale de 1 s (janelas 10..29) em -60 dB
    db = np.full(40, -20.0)
    db[10:30] = -60.0
    assert pausas_reais.pausas_do_envelope(db, 0.05) == [(0.5, 1.5)]
    assert pausas_reais.pausas_do_envelope(np.array([]), 0.05) == []
    # vale no fim do arquivo também fecha
    db2 = np.full(30, -20.0)
    db2[18:] = -60.0
    assert pausas_reais.pausas_do_envelope(db2, 0.05) == [(0.9, 1.5)]


def test_arquivo_ilegivel_da_erro_claro_e_nao_lista_vazia(tmp_path):
    # um arquivo que o ffmpeg não decodifica NÃO pode virar "monólogo sem pausa" em silêncio
    lixo = tmp_path / "lixo.wav"
    lixo.write_bytes(b"isto nao e audio")
    with pytest.raises(pausas_reais.ErroDeAudio):
        pausas_reais.pausas(str(lixo))
