"""nucleo/segmentos (W2.D): blocos de fala por energia, em dois passes.

O separador de 0,38 s serve para achar FRASES; ele sozinho funde uma retomada com pausa de
0,32 s num bloco só, e o ASR ainda deduplica a frase ao ler o bloco inteiro. O segundo passe,
com separador de 0,14 s, é o que expõe essa retomada.
"""
import numpy as np
import pytest

from gravado.nucleo import energia, segmentos
from tests.gravado import sintese as sx


def _db(tmp_path, trechos, jan=0.02):
    arq = sx.audio_por_blocos(tmp_path / "a.wav", trechos)
    db, _ = energia.curva(arq, jan=jan)
    return arq, db


def test_separador_de_0_38_mais_segundo_passe_de_0_14_acham_retomada_de_0_32(tmp_path):
    arq = sx.audio_por_blocos(tmp_path / "r.wav", [(0.8, -12.0), (0.32, None), (0.8, -12.0),
                                                   (1.0, None), (0.8, -12.0)])
    frases = segmentos.frases(arq)
    assert len(frases) == 2                    # a retomada de 0,32 s ficou DENTRO da 1a frase
    assert frases[0][1] - frases[0][0] == pytest.approx(1.92, abs=0.05)
    subs = segmentos.subblocos(arq, 0.0, 3.72)
    assert len(subs) == 3                      # o segundo passe separa as duas partes
    escondidas = segmentos.pausas_escondidas(frases, subs)
    assert len(escondidas) == 1
    ini, fim = escondidas[0]
    assert ini == pytest.approx(0.8, abs=0.04)
    assert fim - ini == pytest.approx(0.32, abs=0.04)


def test_pausa_de_0_50_separa_as_frases_nos_dois_passes(tmp_path):
    arq = sx.audio_por_blocos(tmp_path / "p.wav", [(1.0, -12.0), (0.5, None), (1.0, -12.0)])
    assert len(segmentos.frases(arq)) == 2
    assert len(segmentos.subblocos(arq, 0.0, 2.5)) == 2
    assert segmentos.pausas_escondidas(segmentos.frases(arq), segmentos.subblocos(arq, 0.0, 2.5)) == []


def test_clique_curto_nao_vira_bloco(tmp_path):
    arq = sx.audio_por_blocos(tmp_path / "c.wav", [(0.5, None), (0.04, -12.0), (0.5, None),
                                                   (1.0, -12.0)])
    assert len(segmentos.frases(arq)) == 1     # só o tom de 1,0 s


def test_limiar_e_relativo_ao_proprio_audio(tmp_path):
    forte = sx.audio_por_blocos(tmp_path / "f.wav", [(1.0, -10.0), (0.6, None), (1.0, -10.0)])
    fraco = sx.audio_por_blocos(tmp_path / "q.wav", [(1.0, -40.0), (0.6, None), (1.0, -40.0)])
    a, b = segmentos.frases(forte), segmentos.frases(fraco)
    assert len(a) == len(b) == 2
    for (i1, f1), (i2, f2) in zip(a, b):
        assert i1 == pytest.approx(i2, abs=0.05) and f1 == pytest.approx(f2, abs=0.05)


def test_bloco_aberto_no_fim_do_arquivo_fecha_no_fim(tmp_path):
    arq, db = _db(tmp_path, [(0.5, None), (1.0, -12.0)])
    blocos = segmentos.blocos_de_fala(db, 0.02, percentil_q=0.97, queda_db=38.0,
                                      min_bloco=0.1, gap=0.38, min_final=0.25)
    assert len(blocos) == 1
    assert blocos[0][0] == pytest.approx(0.5, abs=0.03)
    assert blocos[0][1] == pytest.approx(1.5, abs=0.03)


def test_fundir_so_junta_o_que_esta_mais_perto_que_o_gap():
    blocos = [(0.0, 1.0), (1.2, 2.0), (2.6, 3.0)]
    assert segmentos.fundir(blocos, 0.38) == [(0.0, 2.0), (2.6, 3.0)]
    assert segmentos.fundir(blocos, 0.0) == blocos             # gap 0 = não funde nada
    assert segmentos.fundir([], 0.38) == []


def test_corridas_converte_indices_em_segundos_e_respeita_o_minimo():
    mascara = np.array([0, 1, 1, 0, 0, 1, 0, 1, 1, 1], dtype=bool)
    assert segmentos.corridas(mascara, 0.1) == [(0.1, 0.3), (0.5, 0.6), (0.7, 1.0)]
    assert segmentos.corridas(mascara, 0.1, dur_min=0.2) == [(0.1, 0.3), (0.7, 1.0)]


def test_silencios_acham_as_corridas_abaixo_do_limiar(tmp_path):
    arq, db = _db(tmp_path, [(1.0, -12.0), (0.9, None), (1.0, -12.0)])
    sil = segmentos.silencios(db, 0.02)
    assert len(sil) == 1
    assert sil[0][0] == pytest.approx(1.0, abs=0.03) and sil[0][1] == pytest.approx(1.9, abs=0.03)
    assert segmentos.silencios(db, 0.02, dur_min=1.0) == []


def test_subblocos_devolvem_tempo_no_eixo_do_arquivo_inteiro(tmp_path):
    arq = sx.audio_por_blocos(tmp_path / "s.wav", [(2.0, None), (0.8, -12.0), (0.5, None),
                                                   (0.8, -12.0), (2.0, None)])
    subs = segmentos.subblocos(arq, 1.5, 5.0)
    assert len(subs) == 2
    assert subs[0][0] == pytest.approx(2.0, abs=0.04)
    assert subs[1][1] == pytest.approx(4.1, abs=0.04)


def test_picos_por_bloco_medem_o_maximo_de_cada_bloco(tmp_path):
    arq, db = _db(tmp_path, [(1.0, -10.0), (0.5, None), (1.0, -20.0)], jan=0.05)
    blocos = segmentos.blocos_de_fala(db, 0.05, percentil_q=0.97, queda_db=38.0, min_bloco=0.12)
    picos = segmentos.picos_por_bloco(db, 0.05, blocos)
    assert len(picos) == 2
    assert picos[0] == pytest.approx(-10.0, abs=0.2)
    assert picos[1] == pytest.approx(-20.0, abs=0.2)


def test_blocos_com_pico_une_bloco_e_pico_pelo_preset_de_voz(tmp_path):
    arq = sx.audio_por_blocos(tmp_path / "v.wav", [(1.0, -10.0), (0.3, None), (1.0, -18.0)])
    blocos = segmentos.blocos_com_pico(arq)
    assert len(blocos) == 2                    # preset de voz NÃO funde pausa curta
    assert blocos[0][2] > blocos[1][2] + 6.0


def test_audio_mudo_nao_tem_fala_nem_o_limiar_relativo_o_transforma_em_um_bloco_so(tmp_path):
    arq, db = _db(tmp_path, [(2.0, None)])
    assert segmentos.blocos_de_fala(db, 0.02, percentil_q=0.97, queda_db=38.0, min_bloco=0.1) == []
    assert segmentos.frases(arq) == []
    assert segmentos.silencios(db, 0.02) == [(0.0, 2.0)]
