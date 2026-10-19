"""A cadeia HDR -> SDR do one-shot com o ffmpeg de verdade, com a LUT em arquivo de nome esquisito (W1.D)."""
import shutil
import subprocess

import pytest

import plataforma
from oneshot import luz
from tests.fixtures.nome_esquisito import NOME_ESQUISITO

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg ausente")


def test_a_cadeia_usa_o_escape_das_duas_camadas_da_plataforma(tmp_path):
    lut = tmp_path / "a:b=c.cube"
    assert "lut3d=file=%s:interp=tetrahedral" % plataforma.escapar_filtro(lut) in luz.cadeia_hdr_para_sdr(lut)
    assert not hasattr(luz, "_escapar")


def test_o_ffmpeg_le_a_lut_de_nome_esquisito(tmp_path):
    pasta = tmp_path / NOME_ESQUISITO
    pasta.mkdir()
    lut = luz.gerar_lut(pasta / ("lut " + NOME_ESQUISITO + ".cube"), tamanho=5)
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i", "color=c=gray:s=64x64:d=0.2:r=10",
                        "-vf", luz.cadeia_hdr_para_sdr(lut), "-frames:v", "1", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, r.stderr
