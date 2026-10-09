"""nucleo/energia e o cortador de ar morto (W2.D).

A curva de energia (dB por janela) estava copiada em 5 arquivos do gravado, cada cópia com o
seu pedaço de lógica por cima. Aqui ela vive uma vez só e é medida contra áudio de nível
conhecido. O cortador `ar_morto_energia` é o passo que o gate de ar morto fiscaliza: o teto
do gate sai das constantes dele.
"""
import numpy as np
import pytest

from gravado import ar_morto_energia
from gravado.nucleo import energia
from tests.gravado import sintese as sx


def test_silencio_digital_vale_menos_120_e_so_janelas_cheias_contam(tmp_path):
    arq = sx.audio_por_blocos(tmp_path / "s.wav", [(1.0, None)])
    db, dur = energia.curva(arq)
    assert len(db) == 50                      # 1,0 s / 0,02 s
    assert set(db.tolist()) == {-120.0}
    assert dur == pytest.approx(1.0)


def test_seno_de_rms_conhecido_sai_com_o_mesmo_nivel(tmp_path):
    arq = sx.audio_por_blocos(tmp_path / "t.wav", [(1.0, -18.0)])
    db, _ = energia.curva(arq)
    assert np.allclose(db, -18.0, atol=0.15)


def test_janela_do_arquivo_decodifica_so_o_trecho(tmp_path):
    arq = sx.audio_por_blocos(tmp_path / "j.wav", [(2.0, None), (1.0, -12.0), (2.0, None)])
    db, dur = energia.curva(arq, ini=2.0, dur=1.0)
    assert dur == pytest.approx(1.0, abs=0.01)
    assert db.min() > -20.0                   # só o tom
    antes, _ = energia.curva(arq, ini=0.0, dur=1.0)
    assert antes.max() == -120.0              # só o silêncio


def test_percentil_e_posto_mais_proximo_como_nos_scripts_antigos():
    db = np.arange(100, dtype=float)          # 0..99
    assert energia.percentil(db, 0.98) == 98.0
    assert energia.percentil(db, 0.97) == 97.0
    assert energia.percentil(np.array([5.0]), 0.98) == 5.0
    assert energia.limiar_relativo(db, 0.98, 38.0) == 60.0


def test_curva_de_audio_mais_curto_que_uma_janela_e_vazia(tmp_path):
    arq = sx.audio_por_blocos(tmp_path / "c.wav", [(0.01, -12.0)])
    db, _ = energia.curva(arq)
    assert len(db) == 0


def test_arquivo_inexistente_ou_que_nao_e_audio_levanta_erro_de_audio(tmp_path):
    with pytest.raises(energia.ErroDeAudio) as e:
        energia.curva(tmp_path / "nao_existe.wav")
    assert "nao_existe.wav" in str(e.value)
    lixo = tmp_path / "lixo.wav"
    lixo.write_bytes(b"isto nao e um wav")
    with pytest.raises(energia.ErroDeAudio):
        energia.curva(lixo)


# --- o cortador de ar morto -----------------------------------------------------------------

def test_constantes_do_cortador_sao_as_medidas_e_o_gate_depende_delas():
    assert ar_morto_energia.MARGEM == 0.12
    assert ar_morto_energia.RESPIRO == 0.18
    assert ar_morto_energia.MINIMO == 0.45
    assert ar_morto_energia.QUEDA == 38.0
    # a pausa que o cortador DEIXA ao cortar: margem + respiro + margem
    assert ar_morto_energia.PAUSA_RESIDUAL == pytest.approx(0.42)


def test_pausa_longa_vira_o_respiro_mais_as_duas_margens(tmp_path):
    arq = sx.audio_por_blocos(tmp_path / "p.wav", [(1.0, -12.0), (1.5, None), (1.0, -12.0)])
    segs = ar_morto_energia.manter(arq)
    assert len(segs) == 2
    mantido = sum(b - a for a, b in segs)
    assert mantido == pytest.approx(3.5 - (1.5 - 0.42), abs=0.05)      # tirou 1,08 s


def test_pausa_dentro_de_minimo_mais_margens_e_ritmo_e_fica_intacta(tmp_path):
    # 0,60 s: (0,60 - 2 x 0,12) = 0,36, abaixo do MINIMO de 0,45: o cortador não mexe
    arq = sx.audio_por_blocos(tmp_path / "r.wav", [(1.0, -12.0), (0.6, None), (1.0, -12.0)])
    segs = ar_morto_energia.manter(arq)
    assert len(segs) == 1
    assert sum(b - a for a, b in segs) == pytest.approx(2.6, abs=0.03)


def test_janelas_limitam_a_analise_aos_trechos_escolhidos(tmp_path):
    arq = sx.audio_por_blocos(tmp_path / "w.wav", [(1.0, -12.0), (1.5, None), (1.0, -12.0)])
    segs = ar_morto_energia.manter(arq, janelas=[(0.5, 1.2)])
    assert segs and all(0.5 - 1e-6 <= a and b <= 1.2 + 1e-6 for a, b in segs)
