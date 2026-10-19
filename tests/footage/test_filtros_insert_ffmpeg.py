"""Os filtros do insert com o ffmpeg de verdade: a moldura (PNG) entra por `movie=` e o nome da pasta é esquisito (W1.D)."""
import os
import shutil
import subprocess

import pytest

import plataforma
from footage import filtros_insert as FI
from tests.fixtures.nome_esquisito import NOME_ESQUISITO

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg ausente")


def _ff(*args):
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin"] + list(args), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    assert r.returncode == 0, r.stderr
    return r


def test_a_moldura_devolve_o_caminho_cru_e_o_filtro_escapa_nas_duas_camadas(tmp_path):
    pasta = tmp_path / NOME_ESQUISITO
    m, png = FI.moldura_cheia(16 / 9.0, str(pasta))
    assert png == os.path.join(str(pasta), "moldura_cheio_0_8081.png")
    fc = FI.fc_tela_cheia_moldura(1.0, 0.0, "", m, png, "", 15)
    assert "movie=%s," % plataforma.escapar_filtro(png) in fc


def test_tela_cheia_roda_com_a_moldura_em_pasta_de_nome_esquisito(tmp_path):
    asset = tmp_path / "asset.mp4"
    _ff("-f", "lavfi", "-i", "color=c=0xC8C8C8:s=1280x720:r=30:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(asset))
    m, png = FI.moldura_cheia(1280 / 720.0, str(tmp_path / NOME_ESQUISITO / "molduras"))
    fc = FI.fc_tela_cheia_moldura(1.0, 0.0, "", m, png, "", 15)
    quadro = tmp_path / "q.png"
    _ff("-i", str(asset), "-filter_complex", fc, "-map", "[v]", "-frames:v", "1", str(quadro))
    assert quadro.stat().st_size > 0


def test_split_roda_com_a_moldura_em_pasta_de_nome_esquisito(tmp_path):
    from footage import filtros_avatar as FA
    asset, avatar = tmp_path / "asset.mp4", tmp_path / "avatar.mp4"
    _ff("-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(asset))
    _ff("-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(avatar))
    painel = FI.painel_mockup(str(asset), "", 0, 0.0, str(tmp_path / NOME_ESQUISITO / "molduras"))
    assert "movie=" in painel
    fc = FI.fc_split_tela(1.0, "", painel, FA.filtro_avatar_split(0.30), 15)
    quadro = tmp_path / "q.png"
    _ff("-i", str(asset), "-i", str(avatar), "-filter_complex", fc, "-map", "[v]", "-frames:v", "1", str(quadro))
    assert quadro.stat().st_size > 0
