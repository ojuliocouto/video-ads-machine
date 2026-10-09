"""loudness (W1.C): C12, -14 LUFS (mais ou menos 1,2), true peak até -1,5 dBTP, 48 kHz."""
import subprocess

import pytest

from audio import loudness
from tests.fixtures import sinteticos as fx


def _seno(destino, pico_dbfs=-20.0, dur=5.0, freq=1000):
    """Seno com PICO exato em `pico_dbfs`. (O `sine` do ffmpeg nasce em -18 dBFS: não serve.)"""
    amp = 10 ** (pico_dbfs / 20)
    return fx._ffmpeg(["-f", "lavfi", "-i",
                       f"aevalsrc={amp}*sin(2*PI*{freq}*t):s=48000:d={dur}",
                       "-c:a", "pcm_s16le", "-ac", "1"], destino)


def test_medir_um_seno_de_menos_20_dbfs(tmp_path):
    m = loudness.medir(_seno(tmp_path / "s.wav"))
    # seno de pico -20 dBFS: RMS -23,0 dBFS e K-weighting neutro a 1 kHz, logo cerca de -23 LUFS
    assert m.integrado_lufs == pytest.approx(-23.0, abs=0.5)
    assert m.true_peak_dbtp == pytest.approx(-20.0, abs=0.3)


def test_seno_de_menos_20_dbfs_vai_a_menos_14_lufs_com_true_peak_ate_menos_1_5(tmp_path):
    entrada = _seno(tmp_path / "entrada.wav")
    saida = loudness.normalizar(entrada, tmp_path / "saida.wav")
    m = loudness.medir(saida)
    assert m.integrado_lufs == pytest.approx(-14.0, abs=0.5)
    assert m.true_peak_dbtp <= -1.5


def test_a_saida_fica_em_48_khz(tmp_path):
    entrada = _seno(tmp_path / "entrada.wav")
    saida = loudness.normalizar(entrada, tmp_path / "saida.wav")
    sr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                         "stream=sample_rate", "-of", "csv=p=0", str(saida)],
                        capture_output=True, text=True).stdout.strip()
    assert sr == "48000"


def test_pico_alto_e_limitado_pelo_true_peak_e_nao_estoura(tmp_path):
    # ruído rosa forte: para chegar a -14 LUFS o pico passaria de -1,5; o loudnorm segura
    entrada = fx.ruido_rosa(tmp_path / "rosa.wav", dur=6.0, amplitude=0.9)
    saida = loudness.normalizar(entrada, tmp_path / "saida.wav")
    m = loudness.medir(saida)
    assert m.true_peak_dbtp <= -1.5 + 0.05


def test_video_sai_com_o_video_copiado_e_audio_normalizado(tmp_path):
    video = fx.video_com_tom(tmp_path / "v.mp4", dur=6.0, volume_db=-24.0)
    saida = loudness.normalizar(video, tmp_path / "v_norm.mp4")
    m = loudness.medir(saida)
    assert m.integrado_lufs == pytest.approx(-14.0, abs=1.2)
    codec = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=codec_name", "-of", "csv=p=0", str(saida)],
                           capture_output=True, text=True).stdout.strip()
    assert codec == "h264"


def test_dentro_da_faixa_usa_mais_ou_menos_1_2_e_o_teto_de_true_peak():
    M = loudness.Medicao
    assert loudness.dentro_da_faixa(M(-14.0, -1.6, 3.0))
    assert loudness.dentro_da_faixa(M(-15.2, -2.0, 3.0))
    assert loudness.dentro_da_faixa(M(-12.8, -1.5, 3.0))
    assert not loudness.dentro_da_faixa(M(-15.3, -3.0, 3.0))
    assert not loudness.dentro_da_faixa(M(-12.7, -3.0, 3.0))
    assert not loudness.dentro_da_faixa(M(-14.0, -1.0, 3.0))


def test_audio_mudo_da_erro_claro_em_vez_de_inventar_um_ganho(tmp_path):
    mudo = fx._ffmpeg(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "2",
                       "-c:a", "pcm_s16le"], tmp_path / "mudo.wav")
    with pytest.raises(loudness.ErroDeLoudness):
        loudness.normalizar(mudo, tmp_path / "saida.wav")


def test_constantes_do_gate_c12():
    assert loudness.LUFS_ALVO == -14.0
    assert loudness.TP_ALVO == -1.5
    assert loudness.TOLERANCIA_LUFS == 1.2
    assert loudness.SR == 48000
