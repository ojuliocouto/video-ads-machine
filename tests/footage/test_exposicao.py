"""Exposição do insert (W2.B): piso, teto e contraste, do jeito que o motor original decidia.

As regras vêm de defeitos medidos: piso 105 levanta asset escuro, página branca (185 ou mais)
NUNCA escurece (o teto antigo virava "filtro cinza"), e o contraste acompanha o módulo do
ganho. Os goldens foram gerados pelo `_eq_exposicao` do `produzir_roteiro.py` original com a
luminância fixada. A luminância em si (ffmpeg + PIL) é medida aqui com `subprocess` falso.
"""
import subprocess

import pytest

from footage import exposicao as EX

# {"lum": ..., "declarada": ..., "eq": "eq=brightness=...,"} para 10 luminâncias x 5 declaradas
GOLDEN_EQ = [{'declarada': 0, 'eq': 'eq=brightness=0.412:contrast=1.247,', 'lum': 0.0},
 {'declarada': 0.06, 'eq': 'eq=brightness=0.412:contrast=1.247,', 'lum': 0.0},
 {'declarada': 0.3, 'eq': 'eq=brightness=0.412:contrast=1.247,', 'lum': 0.0},
 {'declarada': -0.1, 'eq': 'eq=brightness=0.412:contrast=1.247,', 'lum': 0.0},
 {'declarada': 0.9, 'eq': 'eq=brightness=0.900:contrast=1.540,', 'lum': 0.0},
 {'declarada': 0, 'eq': 'eq=brightness=0.294:contrast=1.176,', 'lum': 30.0},
 {'declarada': 0.06, 'eq': 'eq=brightness=0.294:contrast=1.176,', 'lum': 30.0},
 {'declarada': 0.3, 'eq': 'eq=brightness=0.300:contrast=1.180,', 'lum': 30.0},
 {'declarada': -0.1, 'eq': 'eq=brightness=0.294:contrast=1.176,', 'lum': 30.0},
 {'declarada': 0.9, 'eq': 'eq=brightness=0.900:contrast=1.540,', 'lum': 30.0},
 {'declarada': 0, 'eq': 'eq=brightness=0.255:contrast=1.153,', 'lum': 40.0},
 {'declarada': 0.06, 'eq': 'eq=brightness=0.255:contrast=1.153,', 'lum': 40.0},
 {'declarada': 0.3, 'eq': 'eq=brightness=0.300:contrast=1.180,', 'lum': 40.0},
 {'declarada': -0.1, 'eq': 'eq=brightness=0.255:contrast=1.153,', 'lum': 40.0},
 {'declarada': 0.9, 'eq': 'eq=brightness=0.900:contrast=1.540,', 'lum': 40.0},
 {'declarada': 0, 'eq': '', 'lum': 104.9},
 {'declarada': 0.06, 'eq': 'eq=brightness=0.060:contrast=1.036,', 'lum': 104.9},
 {'declarada': 0.3, 'eq': 'eq=brightness=0.300:contrast=1.180,', 'lum': 104.9},
 {'declarada': -0.1, 'eq': '', 'lum': 104.9},
 {'declarada': 0.9, 'eq': 'eq=brightness=0.900:contrast=1.540,', 'lum': 104.9},
 {'declarada': 0, 'eq': '', 'lum': 105.0},
 {'declarada': 0.06, 'eq': 'eq=brightness=0.060:contrast=1.036,', 'lum': 105.0},
 {'declarada': 0.3, 'eq': 'eq=brightness=0.300:contrast=1.180,', 'lum': 105.0},
 {'declarada': -0.1, 'eq': 'eq=brightness=-0.100:contrast=1.060,', 'lum': 105.0},
 {'declarada': 0.9, 'eq': 'eq=brightness=0.900:contrast=1.540,', 'lum': 105.0},
 {'declarada': 0, 'eq': '', 'lum': 150.0},
 {'declarada': 0.06, 'eq': 'eq=brightness=0.060:contrast=1.036,', 'lum': 150.0},
 {'declarada': 0.3, 'eq': 'eq=brightness=0.300:contrast=1.180,', 'lum': 150.0},
 {'declarada': -0.1, 'eq': 'eq=brightness=-0.100:contrast=1.060,', 'lum': 150.0},
 {'declarada': 0.9, 'eq': 'eq=brightness=0.900:contrast=1.540,', 'lum': 150.0},
 {'declarada': 0, 'eq': '', 'lum': 185.0},
 {'declarada': 0.06, 'eq': 'eq=brightness=0.060:contrast=1.036,', 'lum': 185.0},
 {'declarada': 0.3, 'eq': 'eq=brightness=0.300:contrast=1.180,', 'lum': 185.0},
 {'declarada': -0.1, 'eq': 'eq=brightness=-0.100:contrast=1.060,', 'lum': 185.0},
 {'declarada': 0.9, 'eq': 'eq=brightness=0.900:contrast=1.540,', 'lum': 185.0},
 {'declarada': 0, 'eq': '', 'lum': 185.1},
 {'declarada': 0.06, 'eq': '', 'lum': 185.1},
 {'declarada': 0.3, 'eq': '', 'lum': 185.1},
 {'declarada': -0.1, 'eq': 'eq=brightness=-0.100:contrast=1.060,', 'lum': 185.1},
 {'declarada': 0.9, 'eq': '', 'lum': 185.1},
 {'declarada': 0, 'eq': '', 'lum': 244.0},
 {'declarada': 0.06, 'eq': '', 'lum': 244.0},
 {'declarada': 0.3, 'eq': '', 'lum': 244.0},
 {'declarada': -0.1, 'eq': 'eq=brightness=-0.100:contrast=1.060,', 'lum': 244.0},
 {'declarada': 0.9, 'eq': '', 'lum': 244.0},
 {'declarada': 0, 'eq': '', 'lum': None},
 {'declarada': 0.06, 'eq': 'eq=brightness=0.060:contrast=1.036,', 'lum': None},
 {'declarada': 0.3, 'eq': 'eq=brightness=0.300:contrast=1.180,', 'lum': None},
 {'declarada': -0.1, 'eq': 'eq=brightness=-0.100:contrast=1.060,', 'lum': None},
 {'declarada': 0.9, 'eq': 'eq=brightness=0.900:contrast=1.540,', 'lum': None}]

# {"lum_med": ..., "offset": ...} do `_bg_offset` do original
GOLDEN_OFFSET = [{'lum_med': None, 'offset': -0.2},
 {'lum_med': 0.0, 'offset': 0.19607843137254902},            # W7.W: asset escuro levanta o fundo até 50 (era 30: 0,1176)
 {'lum_med': 10.0, 'offset': 0.1568627450980392},            # W7.W: 10 + 0,1569 x 255 = 50 (era 0,0784)
 {'lum_med': 30.0, 'offset': 0.0},
 {'lum_med': 33.0, 'offset': -0.011764705882352941},
 {'lum_med': 64.0, 'offset': -0.13333333333333333},
 {'lum_med': 150.0, 'offset': -0.4},
 {'lum_med': 244.0, 'offset': -0.4}]


def test_constantes_mantem_nomes_e_valores():
    assert EX.ALVO_LUM == 105.0
    assert EX.TETO_LUM == 185.0
    assert EX.EXPO_MIN == -0.22
    assert EX.EXPO_MAX == 0.45
    assert EX.ALVO_BG_CHEIO == 30.0


@pytest.mark.parametrize("caso", GOLDEN_EQ, ids=lambda c: f"lum{c['lum']}_dec{c['declarada']}")
def test_filtro_de_exposicao_bate_com_o_original(caso, monkeypatch):
    monkeypatch.setattr(EX, "luminancia_fonte", lambda src, start=0.0: caso["lum"])
    cfg = {"file": "/m/e.mp4", "exposicao": caso["declarada"], "start": 0}
    assert EX.eq_exposicao(cfg) == caso["eq"]


@pytest.mark.parametrize("caso", GOLDEN_OFFSET, ids=lambda c: f"lum{c['lum_med']}")
def test_offset_do_fundo_bate_com_o_original(caso, monkeypatch):
    monkeypatch.setattr(EX, "luminancia_mediana_fonte", lambda src, start=0.0: caso["lum_med"])
    assert EX.bg_offset("/m/o.mp4", {"start": 0}) == pytest.approx(caso["offset"], abs=1e-12)


def test_piso_de_105_levanta_o_asset_escuro():
    ex = EX.calcular_exposicao(40.0, 0)
    assert ex == pytest.approx((105.0 - 40.0) / 255.0)
    assert EX.calcular_exposicao(105.0, 0) == 0
    assert EX.calcular_exposicao(0.0, 0) <= EX.EXPO_MAX


def test_valor_declarado_vale_como_minimo():
    assert EX.calcular_exposicao(40.0, 0.30) == 0.30          # acima do piso: fica
    assert EX.calcular_exposicao(40.0, 0.05) == pytest.approx(65.0 / 255.0)   # abaixo do piso: sobe


@pytest.mark.parametrize("lum", [185.5, 200.0, 244.0, 255.0])
def test_pagina_de_185_ou_mais_nunca_escurece(lum):
    """Fonte clara: zera ganho declarado pra cima, e nada automático desce de zero."""
    for declarada in (0, 0.06, 0.3, 0.9):
        ex = EX.calcular_exposicao(lum, declarada)
        assert ex == 0.0
        assert EX.filtro_eq(ex) == ""
        assert "-" not in EX.filtro_eq(ex)


def test_exatamente_185_ainda_aceita_o_valor_declarado():
    assert EX.calcular_exposicao(185.0, 0.06) == 0.06


def test_contraste_e_um_mais_modulo_do_ganho_vezes_0_6():
    assert EX.filtro_eq(0.2) == "eq=brightness=0.200:contrast=1.120,"
    assert EX.filtro_eq(-0.1) == "eq=brightness=-0.100:contrast=1.060,"      # declarado negativo: contraste sobe igual
    assert EX.filtro_eq(0.3) == "eq=brightness=0.300:contrast=1.180,"


def test_ganho_desprezivel_nao_gera_filtro():
    assert EX.filtro_eq(0.004) == ""
    assert EX.filtro_eq(0.0) == ""


def test_sem_luminancia_mantem_o_valor_declarado():
    assert EX.calcular_exposicao(None, 0.07) == 0.07


def test_offset_do_fundo_e_medido_nunca_fixo():
    assert EX.offset_fundo(None) == -0.20                       # sem medida: o valor antigo e conhecido
    assert EX.offset_fundo(30.0) == pytest.approx(0.0)
    assert EX.offset_fundo(255.0) == -0.40                      # teto de escurecimento
    assert EX.offset_fundo(0.0) == pytest.approx(50.0 / 255.0)  # W7.W: o asset escuro levanta o fundo até 50 e nunca passa disso
    assert EX.offset_fundo(0.0) <= 50.0 / 255.0


def test_w7w_asset_escuro_leva_o_fundo_a_50_e_o_caso_claro_nao_muda():
    for lum in (0.0, 5.0, 10.0, 16.0, 17.0):
        assert lum + EX.offset_fundo(lum) * 255.0 == pytest.approx(min(50.0, 30.0 + (30.0 - lum) * 2.0)), lum
    assert EX.offset_fundo(16.0) * 255.0 + 16.0 == pytest.approx(50.0)           # o terminal da prova
    for lum in (30.0, 33.0, 64.0, 150.0, 244.0):
        assert EX.offset_fundo(lum) == pytest.approx(max(-0.40, (30.0 - lum) / 255.0)), lum
    assert EX.offset_fundo(29.9) == pytest.approx((30.0 - 29.9) * 3.0 / 255.0, abs=1e-9)    # contínuo em 30


def test_luminancia_roda_o_ffmpeg_uma_vez_por_arquivo(monkeypatch, tmp_path):
    """A medição é cacheada pelo arquivo: o mesmo asset em 6 fatias custa 1 ffmpeg."""
    from PIL import Image

    chamadas = []

    def falso(cmd, **kw):
        chamadas.append(list(cmd))
        Image.new("L", (4, 4), 100).save(cmd[-1])
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(EX.subprocess, "run", falso)
    EX._CACHE_LUM.clear()
    a = EX.luminancia_fonte("/m/x.mp4", 2.0)
    b = EX.luminancia_fonte("/m/x.mp4", 9.0)
    assert a == b == 100.0
    assert len(chamadas) == 1
    assert chamadas[0][:7] == ["ffmpeg", "-v", "error", "-y", "-ss", "3.5", "-i"]


def test_mediana_e_media_divergem_em_asset_bimodal(monkeypatch):
    """Metade escura (20) e um quarto claro (240): a média engana, a mediana não."""
    from PIL import Image

    def falso(cmd, **kw):
        im = Image.new("L", (8, 8), 20)
        for x in range(8):
            for y in range(2):
                im.putpixel((x, y), 240)
        im.save(cmd[-1])
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(EX.subprocess, "run", falso)
    EX._CACHE_LUM.clear()
    EX._CACHE_LUM_MED.clear()
    media = EX.luminancia_fonte("/m/b.mp4")
    mediana = EX.luminancia_mediana_fonte("/m/b.mp4")
    assert media == pytest.approx(75.0)
    assert mediana == 20


def test_falha_de_medicao_devolve_none(monkeypatch):
    def falso(cmd, **kw):
        raise OSError("ffmpeg ausente")

    monkeypatch.setattr(EX.subprocess, "run", falso)
    EX._CACHE_LUM.clear()
    assert EX.luminancia_fonte("/m/nao.mp4") is None
