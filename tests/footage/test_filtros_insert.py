"""Filtros do insert (W2.B): painel de cima do split, ativos gerados por código e geometria do PiP.

Os comandos completos (split, tela cheia, imagem, PiP) são comparados com o motor original em
`test_render_segmentos.py`. Aqui ficam as peças menores: as duas formas do painel, a decisão
horizontal x vertical (moldura só em asset deitado: um 9:16 numa moldura de 1008 px de largura
gera card de 1854 px de altura dentro de um painel de 1150) e os PNG que antes eram arquivos
externos e agora saem do código, de forma determinística.
"""
import hashlib
from pathlib import Path

import pytest

from footage import enquadramento as ENQ
from footage import filtros_insert as FI


def test_constantes_mantem_nomes_e_valores():
    assert FI.DARK == "0x141210"
    assert (FI.PIP, FI.PIPX, FI.PIPY, FI.PIPF) == (300, 390, 290, 60)
    assert FI.SOMBRA_PIP.endswith(".png") and FI.BRILHO_LOGO.endswith(".png") and FI.ANEL_LOGO.endswith(".png")


# ------------------------------------------------------------------ painel de cima

def test_painel_encaixado_reduz_a_96_por_cento_da_largura_em_numero_par():
    assert FI.painel_encaixado("", 1080, 1150) == (
        "[t2]scale=1036:1150:force_original_aspect_ratio=decrease,setsar=1[tfg];")


def test_painel_encaixado_carrega_o_ganho_de_exposicao():
    assert FI.painel_encaixado("eq=brightness=0.200:contrast=1.120,", 1080, 1150).startswith(
        "[t2]eq=brightness=0.200:contrast=1.120,scale=1036:1150")


def test_painel_preenchido_corta_pelo_centro_do_conteudo_medido():
    expr = "'clip((in_w*0.4231)-(out_w/2),0,in_w-out_w)':'clip((in_h*0.6000)-(out_h/2),0,in_h-out_h)'"
    assert FI.painel_preenchido("", 1080, 1150, expr) == (
        "[t2]scale=1080:1150:force_original_aspect_ratio=increase,"
        f"crop=1080:1150:{expr},setsar=1[tfg];")


@pytest.fixture
def sondas(monkeypatch):
    monkeypatch.setattr(ENQ, "medir_conteudo", lambda src, w, h, executar=None: (0.5, 0.5, "preencher"))
    return monkeypatch


def test_vertical_decide_pelo_modo_medido_encaixar_ou_preencher(monkeypatch):
    monkeypatch.setattr(ENQ, "medir_conteudo", lambda src, w, h, executar=None: (0.5, 0.5, "encaixar"))
    assert "force_original_aspect_ratio=decrease" in FI.painel_vertical("/m/v.mp4", 1080, 1150, "")
    monkeypatch.setattr(ENQ, "medir_conteudo", lambda src, w, h, executar=None: (0.4, 0.6, "preencher"))
    assert "force_original_aspect_ratio=increase" in FI.painel_vertical("/m/v.mp4", 1080, 1150, "")


def test_asset_vertical_nunca_ganha_moldura(sondas, tmp_path):
    sondas.setattr(ENQ, "aspecto", lambda src, executar=None: 0.5625)
    fg = FI.painel_mockup("/m/v.mp4", "", 3.0, 0.0, str(tmp_path / "molduras"))
    assert "movie=" not in fg
    assert not (tmp_path / "molduras").exists()


def test_asset_quase_quadrado_abaixo_de_1_05_tambem_entra_sem_moldura(sondas, tmp_path):
    sondas.setattr(ENQ, "aspecto", lambda src, executar=None: 1.04)
    assert "movie=" not in FI.painel_mockup("/m/q.mp4", "", 3.0, 0.0, str(tmp_path / "m"))


def test_asset_horizontal_ganha_moldura_no_proprio_aspecto(monkeypatch, tmp_path):
    import push_in

    monkeypatch.setattr(ENQ, "aspecto", lambda src, executar=None: 16 / 9)
    monkeypatch.setattr(ENQ, "largura_fonte", lambda src, executar=None: 800)
    monkeypatch.setattr(push_in, "foco_do_conteudo", lambda src, start=0.0: (0.5, 0.5))
    fg = FI.painel_mockup("/m/h.mp4", "", 3.0, 0.0, str(tmp_path / "molduras"))
    assert "scale=1008:566,setsar=1[tvid]" in fg
    assert (tmp_path / "molduras" / "moldura_1_7778.png").is_file()


def test_moldura_tem_um_png_por_aspecto_e_nao_regera(monkeypatch, tmp_path):
    import push_in

    monkeypatch.setattr(ENQ, "aspecto", lambda src, executar=None: 2.4)
    monkeypatch.setattr(ENQ, "largura_fonte", lambda src, executar=None: 3000)
    monkeypatch.setattr(push_in, "foco_do_conteudo", lambda src, start=0.0: (0.5, 0.5))
    FI.painel_mockup("/m/u.mp4", "", 3.0, 0.0, str(tmp_path / "m"))
    png = tmp_path / "m" / "moldura_2_4000.png"
    t0 = png.stat().st_mtime_ns
    FI.painel_mockup("/m/u.mp4", "", 3.0, 0.0, str(tmp_path / "m"))
    assert png.stat().st_mtime_ns == t0


# ------------------------------------------------------------------ ativos gerados por código

def test_sombra_do_pip_e_um_disco_preto_suave_de_420(tmp_path):
    from PIL import Image

    destino = FI.gerar_sombra_pip(str(tmp_path / "sombra.png"))
    im = Image.open(destino)
    assert im.size == (420, 420) and im.mode == "RGBA"
    assert im.getpixel((210, 210)) == (0, 0, 0, 175)                 # miolo: o alfa máximo do original
    assert im.getpixel((0, 0))[3] <= 2                               # canto transparente
    assert 20 <= im.getpixel((26, 210))[3] <= 90                     # borda macia


def test_brilho_do_logo_e_um_gradiente_radial_do_quadro_inteiro(tmp_path):
    from PIL import Image

    im = Image.open(FI.gerar_brilho_logo(str(tmp_path / "brilho.png")))
    assert im.size == (1080, 1920)
    centro, borda = im.getpixel((540, 960)), im.getpixel((0, 960))
    assert centro[3] > borda[3] > 0
    assert centro[:3] == (74, 58, 42)


def test_anel_do_logo_e_quadrado_e_tem_vazio_no_meio(tmp_path):
    from PIL import Image

    im = Image.open(FI.gerar_anel_logo(str(tmp_path / "anel.png")))
    assert im.size == (460, 460)
    assert im.getpixel((230, 230))[3] == 0
    assert max(im.getpixel((x, 230))[3] for x in range(40, 120)) > 0


def test_ativos_gerados_sao_deterministicos(tmp_path):
    import hashlib

    def sha(f):
        return hashlib.sha256(Path(f).read_bytes()).hexdigest()

    a = [sha(FI.gerar_sombra_pip(str(tmp_path / "a1.png"))), sha(FI.gerar_brilho_logo(str(tmp_path / "a2.png"))),
         sha(FI.gerar_anel_logo(str(tmp_path / "a3.png")))]
    b = [sha(FI.gerar_sombra_pip(str(tmp_path / "b1.png"))), sha(FI.gerar_brilho_logo(str(tmp_path / "b2.png"))),
         sha(FI.gerar_anel_logo(str(tmp_path / "b3.png")))]
    assert a == b


