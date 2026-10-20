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


# --- take com LRA acima do alvo (ensaio de 20/10/2026: IMG_3751, LRA 11,1 contra alvo 11,0) -------------
# O loudnorm só aplica ganho puro (modo linear) quando o LRA do alvo cobre o LRA medido. Com o alvo fixo em
# 11 e o take em 11,1, ele caía no modo dinâmico, que mexe na dinâmica e errou o alvo: o one-shot quebrou com
# "-15.6 LUFS depois de 3 passes".

def _dinamico(destino, alto=0.3, baixo=0.03, dur=24):
    """Ruído que alterna 4 s alto e 4 s baixo: LRA bem acima de 11 LU."""
    return fx._ffmpeg(["-f", "lavfi", "-i",
                       f"aevalsrc='(random(0)*2-1)*if(lt(mod(t,8),4),{alto},{baixo})':s=48000:d={dur}",
                       "-ac", "1", "-c:a", "pcm_s16le"], destino)


def test_alvo_de_lra_acompanha_o_take_ate_o_teto():
    assert loudness.lra_do_alvo(5.0) == loudness.LRA_ALVO
    assert loudness.lra_do_alvo(11.0) == loudness.LRA_ALVO
    assert loudness.lra_do_alvo(11.1) >= 11.1
    assert loudness.lra_do_alvo(17.5) >= 17.5
    assert loudness.lra_do_alvo(35.0) == loudness.LRA_TETO


def test_take_com_lra_acima_do_alvo_recebe_so_ganho_e_mantem_a_dinamica(tmp_path):
    entrada = _dinamico(tmp_path / "dinamico.wav")
    antes = loudness.medir(entrada)
    assert loudness.LRA_ALVO < antes.lra <= loudness.LRA_TETO
    m = loudness.medir(loudness.normalizar(entrada, tmp_path / "saida.wav"))
    assert m.lra == pytest.approx(antes.lra, abs=0.5)        # ganho puro: a dinâmica do take não muda
    assert m.integrado_lufs == pytest.approx(-14.0, abs=0.5)
    assert m.true_peak_dbtp <= -1.5 + 0.05


def test_take_com_lra_acima_do_teto_passa_por_compressao_leve_e_cabe_na_regua(tmp_path):
    # ruído que decai 2,5 dB por segundo durante 36 s: LRA perto de 26 LU, acima do que o loudnorm aceita
    entrada = fx._ffmpeg(["-f", "lavfi", "-i", "aevalsrc='(random(0)*2-1)*0.3*exp(-t/6)':s=48000:d=36",
                          "-ac", "1", "-c:a", "pcm_s16le"], tmp_path / "muito_dinamico.wav")
    antes = loudness.medir(entrada)
    assert antes.lra > loudness.LRA_TETO
    m = loudness.medir(loudness.normalizar(entrada, tmp_path / "saida.wav"))
    assert m.lra < antes.lra - 2.0                            # a compressão leve encolheu a dinâmica
    assert loudness.dentro_da_faixa(m)


def test_take_com_pico_alto_passa_pelo_limitador_e_o_ganho_fica_linear(tmp_path):
    """Celular: pico de +0,5 dBFS. O ganho até -14 LUFS levaria o pico acima de -1,5 dBTP e o loudnorm caía no modo
    dinâmico (o take cortado do ensaio saiu em -15,0 LUFS). O limitador segura o pico antes e o ganho é linear."""
    entrada = fx._ffmpeg(["-f", "lavfi", "-i",
                          "aevalsrc='(random(0)*2-1)*0.08*(1+0.5*sin(2*PI*0.5*t))"
                          "+if(lt(mod(t,1.3),0.004),0.95*sin(2*PI*2000*t),0)':s=48000:d=20",
                          "-ac", "1", "-c:a", "pcm_s16le"], tmp_path / "picos.wav")
    antes = loudness.medir(entrada)
    assert antes.true_peak_dbtp + (-14.0 - antes.integrado_lufs) > -1.5      # o ganho puro estouraria o teto
    saida, modo = loudness.normalizar_detalhado(entrada, tmp_path / "saida.wav")
    m = loudness.medir(saida)
    assert modo == "linear"
    assert m.integrado_lufs == pytest.approx(-14.0, abs=0.5) and m.true_peak_dbtp <= -1.5 + 0.05


def test_take_com_lra_acima_do_alvo_fica_no_modo_linear(tmp_path):
    _, modo = loudness.normalizar_detalhado(_dinamico(tmp_path / "dinamico.wav"), tmp_path / "saida.wav")
    assert modo == "linear"
