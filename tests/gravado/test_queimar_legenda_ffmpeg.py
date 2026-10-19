"""A queima da legenda com o ffmpeg de verdade, em arquivos e pastas de nome esquisito (W1.D).

O caminho do `.ass` e o da pasta de fontes entram no filtro `ass=ARQ:fontsdir=PASTA`. O escape tem que ser o das DUAS
camadas do ffmpeg (`plataforma.escapar_filtro`); numa camada só ele falha em `:`, `=`, `'` e `\\`.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

import plataforma
from gravado import queimar_legenda as QL
from tests.fixtures.nome_esquisito import NOME_ESQUISITO

REPO = Path(__file__).resolve().parents[2]

SONDA_ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 64
PlayResY: 64

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, Alignment
Style: Default,Inter ExtraBold,20,&H00FFFFFF,2

[Events]
Format: Layer, Start, End, Style, Text
Dialogue: 0,0:00:00.00,0:00:00.40,Default,teste
"""


def _ffmpeg_tem_filtro(nome):
    if not shutil.which("ffmpeg"):
        return False
    r = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=60)
    return any((" %s " % nome) in linha for linha in r.stdout.splitlines())


pytestmark = pytest.mark.skipif(not _ffmpeg_tem_filtro("ass"), reason="ffmpeg ausente ou sem libass")


def _video(destino):
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.4:r=10",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(destino)], check=True, capture_output=True)
    return destino


def test_o_comando_usa_o_escape_das_duas_camadas_da_plataforma(tmp_path):
    ass, fontes = tmp_path / "a:b.ass", tmp_path / "pasta=x"
    cmd = QL.comando("in.mp4", ass, "out.mp4", fontes)
    vf = cmd[cmd.index("-vf") + 1]
    assert vf == "ass=%s:fontsdir=%s" % (plataforma.escapar_filtro(ass), plataforma.escapar_filtro(fontes))


def test_o_modulo_nao_guarda_mais_um_escape_proprio():
    assert not hasattr(QL, "escapar_filtro") and not hasattr(QL, "_ESPECIAIS_DO_FILTRO")


def test_queima_com_ass_e_pasta_de_fontes_de_nome_esquisito(tmp_path):
    pasta = tmp_path / NOME_ESQUISITO
    fontes = pasta / ("fontes " + NOME_ESQUISITO)
    fontes.mkdir(parents=True)
    shutil.copy(REPO / "fonts" / "inter-800.ttf", fontes / "inter-800.ttf")
    ass = pasta / ("legenda " + NOME_ESQUISITO + ".ass")
    ass.write_text(SONDA_ASS, encoding="utf-8")
    src = _video(tmp_path / "in.mp4")
    dest = tmp_path / "saida" / "out.mp4"
    assert QL.queimar(src, ass, dest, fontes) == dest
    assert dest.is_file() and dest.stat().st_size > 0
