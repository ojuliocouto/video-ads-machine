"""One-shot: o enquadramento 9:16 centrado no rosto MEDIDO (W5.D).

O take de câmera horizontal vira 9:16 recortando uma janela centrada no rosto, não no meio do
quadro (o `look_b` é um close mais fechado: a mesma fração que acerta um look corta as
sobrancelhas de outro). O rosto é o que precisa estar no quadro, então é nele que se ancora, e o
detector entra por parâmetro: nos testes ele devolve um rosto conhecido, e o recorte tem que cair
no centro dele com até 10 px de erro.

Também aqui: o tamanho que o aluno VÊ (a matriz de rotação do celular troca largura e altura) e a
medição do rosto em quadros amostrados do vídeo.
"""
import pytest

from oneshot import enquadrar
from tests.fixtures import sinteticos as fx

TOL_PX = 10


def _centro_x(j):
    return j["x"] + j["w"] / 2.0


# --- a janela ------------------------------------------------------------------------------------

def test_crop_de_um_take_horizontal_fica_centrado_no_rosto_com_ate_10_px_de_erro():
    for fx_rosto in (1210, 960, 700, 1500):
        rosto = (fx_rosto - 110, 300, 220, 220)
        j = enquadrar.janela_9x16(1920, 1080, rosto)
        assert (j["w"], j["h"], j["y"]) == (608, 1080, 0)
        assert abs(_centro_x(j) - fx_rosto) <= TOL_PX, (fx_rosto, j)
        assert j["centrado_no_rosto"] is True and j["rosto"] == rosto and j["precisa_crop"] is True


def test_a_janela_e_9_por_16_com_dimensoes_pares():
    for larg, alt in ((1920, 1080), (1280, 720), (3840, 2160), (1440, 1080), (1080, 1440)):
        j = enquadrar.janela_9x16(larg, alt, (larg // 2 - 50, alt // 4, 100, 100))
        assert j["w"] % 2 == 0 and j["h"] % 2 == 0 and j["x"] % 2 == 0 and j["y"] % 2 == 0
        assert abs(j["w"] / float(j["h"]) - 9 / 16.0) < 0.004
        assert 0 <= j["x"] and j["x"] + j["w"] <= larg and 0 <= j["y"] and j["y"] + j["h"] <= alt


def test_rosto_perto_da_borda_encosta_a_janela_na_borda_sem_sair_do_quadro():
    esquerda = enquadrar.janela_9x16(1920, 1080, (20, 300, 160, 160))
    direita = enquadrar.janela_9x16(1920, 1080, (1740, 300, 160, 160))
    assert esquerda["x"] == 0 and direita["x"] + direita["w"] == 1920
    assert esquerda["centrado_no_rosto"] and direita["centrado_no_rosto"]


def test_sem_rosto_medido_a_janela_centra_no_quadro_e_o_plano_diz_que_nao_mediu():
    j = enquadrar.janela_9x16(1920, 1080, None)
    assert j["centrado_no_rosto"] is False and j["rosto"] is None
    assert abs(_centro_x(j) - 960) <= 2


def test_take_ja_vertical_9x16_nao_precisa_de_recorte():
    j = enquadrar.janela_9x16(1080, 1920, (400, 500, 200, 200))
    assert j["precisa_crop"] is False and (j["w"], j["h"], j["x"], j["y"]) == (1080, 1920, 0, 0)


def test_take_vertical_mais_largo_que_9x16_corta_so_a_largura_centrado_no_rosto():
    j = enquadrar.janela_9x16(1080, 1440, (460, 400, 200, 200))
    assert (j["w"], j["h"], j["y"]) == (810, 1440, 0)
    assert abs(_centro_x(j) - 560) <= TOL_PX


def test_take_mais_alto_que_9x16_corta_so_a_altura_centrado_no_rosto():
    j = enquadrar.janela_9x16(1080, 2340, (400, 900, 260, 260))
    assert (j["w"], j["h"], j["x"]) == (1080, 1920, 0)
    assert abs((j["y"] + j["h"] / 2.0) - 1030) <= TOL_PX
    sem = enquadrar.janela_9x16(1080, 2340, None)
    assert sem["y"] == 210 and sem["centrado_no_rosto"] is False


def test_o_filtro_recorta_e_escala_para_1080x1920():
    j = enquadrar.janela_9x16(1920, 1080, (1000, 300, 200, 200))
    f = enquadrar.filtro(j)
    assert f.startswith("crop=%d:%d:%d:%d," % (j["w"], j["h"], j["x"], j["y"]))
    assert "scale=1080:1920" in f and f.endswith("setsar=1")
    vertical = enquadrar.filtro(enquadrar.janela_9x16(1080, 1920, None))
    assert "crop" not in vertical and "scale=1080:1920" in vertical


def test_dimensoes_invalidas_sao_erro():
    with pytest.raises(ValueError):
        enquadrar.janela_9x16(0, 1080, None)
    with pytest.raises(ValueError):
        enquadrar.janela_9x16(1920, 1080, (10, 10, -5, 20))


# --- o que o aluno vê ----------------------------------------------------------------------------

def test_dimensoes_exibidas_aplicam_a_matriz_de_rotacao_do_celular(tmp_path):
    deitado = fx.video_rotacao_menos90(tmp_path / "deitado.mp4", dur=1.0, tamanho="320x180")
    assert enquadrar.dimensoes_exibidas(deitado) == (180, 320)
    normal = fx.testsrc_com_audio(tmp_path / "normal.mp4", dur=1.0, tamanho="320x180")
    assert enquadrar.dimensoes_exibidas(normal) == (320, 180)


def test_dimensoes_de_arquivo_que_nao_existe_ou_nao_e_video_e_erro_claro(tmp_path):
    from gravado.veredito import InsumoInvalido
    with pytest.raises(InsumoInvalido):
        enquadrar.dimensoes_exibidas(tmp_path / "nao-existe.mov")
    (tmp_path / "x.mov").write_bytes(b"nao e video")
    with pytest.raises(InsumoInvalido):
        enquadrar.dimensoes_exibidas(tmp_path / "x.mov")


# --- medir o rosto -------------------------------------------------------------------------------

def test_medir_rosto_usa_a_mediana_das_amostras_e_o_maior_rosto_de_cada_quadro(tmp_path):
    video = fx.testsrc_com_audio(tmp_path / "t.mp4", dur=4.0, tamanho="320x180")
    caixas = iter([[(10, 20, 30, 30)], [(100, 50, 60, 60), (5, 5, 20, 20)], [(110, 54, 60, 60)], [(104, 52, 60, 60)]])
    vistos = []

    def detector(imagem):
        vistos.append(imagem.shape)
        return next(caixas)
    r = enquadrar.medir_rosto(video, amostras=4, detector=detector)
    assert r == (102, 51, 60, 60)                                       # mediana de cada medida, do maior rosto
    assert all(s == (180, 320, 3) for s in vistos)                      # o quadro vem na orientação de exibição


def test_medir_rosto_sem_nenhuma_deteccao_devolve_none(tmp_path):
    video = fx.testsrc_com_audio(tmp_path / "t.mp4", dur=2.0, tamanho="320x180")
    assert enquadrar.medir_rosto(video, amostras=3, detector=lambda img: []) is None


def test_medir_rosto_recebe_o_quadro_ja_girado_quando_o_celular_gravou_deitado(tmp_path):
    video = fx.video_rotacao_menos90(tmp_path / "d.mp4", dur=2.0, tamanho="320x180")
    formas = []
    enquadrar.medir_rosto(video, amostras=2, detector=lambda img: formas.append(img.shape) or [])
    assert formas and all(s == (320, 180, 3) for s in formas)


def test_medir_rosto_de_arquivo_ausente_e_insumo_invalido(tmp_path):
    from gravado.veredito import InsumoInvalido
    with pytest.raises(InsumoInvalido):
        enquadrar.medir_rosto(tmp_path / "nada.mov", detector=lambda img: [])


def test_amostras_ficam_espalhadas_dentro_do_take_e_longe_das_pontas():
    ts = enquadrar.instantes_de_amostra(40.0, 8)
    assert len(ts) == 8 and ts == sorted(ts)
    assert ts[0] >= 0.05 * 40.0 and ts[-1] <= 0.95 * 40.0
