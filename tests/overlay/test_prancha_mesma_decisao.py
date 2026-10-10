"""W7.X item 5: a prancha de direção usa a MESMA decisão de tinta, placa e faixa que o overlay.

A prova de aluno achou a prancha desenhando legenda e gancho do jeito antigo (branco fino sobre insert claro): ela gerava
o overlay ANTES da footage, e o overlay só mede o fundo NA footage (tinta invertida, placa da legenda, placa do gancho).
Sem a footage ele cai no arquivo-fonte e decide errado. Além disso o rótulo da prancha tinha a própria regra
(luminância acima de 180), que não é a do motor (placa no gancho acima de 119 no p90, tinta pelo contraste de 4,5:1).

Agora: (1) a ordem é a do build, footage e só então overlay; (2) a decisão que o rótulo mostra é a função do overlay,
`fundo_claro.decisao_do_quadro`, a mesma que `tinta_footage` e `hook_pede_placa` aplicam no build.
"""
import subprocess
from pathlib import Path

import pytest

from overlay import fundo_claro as FC
import prancha_direcao as PD

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _ffmpeg(*args):
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin"] + [str(a) for a in args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-300:]


def _cinza(tmp_path, nivel):
    """(footage mp4 de 2 s, quadro png) de um cinza chapado de luminância `nivel` (0 a 255), 1080x1920."""
    cor = "0x%02x%02x%02x" % (nivel, nivel, nivel)
    mp4, png = tmp_path / ("c%d.mp4" % nivel), tmp_path / ("c%d.png" % nivel)
    _ffmpeg("-f", "lavfi", "-i", "color=c=%s:s=1080x1920:r=10:d=2" % cor, "-pix_fmt", "yuv420p", mp4)
    _ffmpeg("-i", mp4, "-frames:v", "1", png)
    return mp4, png


@pytest.mark.parametrize("nivel", [8, 60, 130, 200, 245])
def test_prancha_e_overlay_dao_a_mesma_decisao_no_mesmo_fundo(tmp_path, nivel):
    mp4, png = _cinza(tmp_path, nivel)
    quadro = PD.decisao_do_quadro(png)
    assert quadro["legenda"] == FC.tinta_footage(mp4, 0.2, 1.8, "padrao")
    assert (quadro["gancho"] == "placa") == FC.hook_pede_placa(mp4, 0.0, 1.5, "9x16")


def test_a_decisao_da_prancha_e_a_funcao_do_overlay_nao_uma_copia():
    assert PD.decisao_do_quadro is FC.decisao_do_quadro


def test_fundo_claro_ganha_tinta_invertida_e_o_gancho_ganha_placa_fundo_escuro_nao(tmp_path):
    _, claro = _cinza(tmp_path, 245)
    _, escuro = _cinza(tmp_path, 8)
    assert FC.decisao_do_quadro(claro) == {"legenda": "invertida", "gancho": "placa"}
    assert FC.decisao_do_quadro(escuro) == {"legenda": "clara", "gancho": "fino"}


def test_o_rotulo_da_prancha_nao_tem_mais_a_regra_propria_de_luminancia_180():
    fonte = (SCRIPTS / "prancha_direcao.py").read_text(encoding="utf-8")
    assert "> 180" not in fonte and "texto branco some" not in fonte


def test_o_rotulo_diz_a_decisao_do_motor(tmp_path):
    _, claro = _cinza(tmp_path, 245)
    texto = PD.texto_da_decisao(PD.decisao_do_quadro(claro))
    assert "legenda: tinta invertida" in texto and "gancho: placa" in texto


# --- a ordem: footage ANTES do overlay, como o build -------------------------------------------------------------

class MotorFalso(object):
    def __init__(self, tmp_path):
        self.chamadas = []
        self.footage = tmp_path / "foot.mp4"
        self.overlay_dir = tmp_path / "overlay"
        self.overlay_dir.mkdir()
        (self.overlay_dir / "prancha.json").write_text("{}")
        self.saida_overlay = (0, "")
        self.footage_existia_no_overlay = None

    def escrever_arquivos_do_motor(self):
        self.chamadas.append("arquivos")

    def construir_timeline(self):
        self.chamadas.append("timeline")

    def montar_footage(self):
        self.chamadas.append("footage")
        self.footage.write_bytes(b"x")
        return self.footage

    def gerar_overlay(self):
        self.chamadas.append("overlay")
        self.footage_existia_no_overlay = self.footage.exists()
        return self.overlay_dir / "index_overlay.html"

    def projeto_do_overlay(self):
        self.chamadas.append("projeto_do_overlay")
        return self.overlay_dir


def test_a_prancha_monta_a_footage_antes_do_overlay(tmp_path):
    m = MotorFalso(tmp_path)
    pr, only, foot = PD.construir(m)
    assert m.chamadas.index("footage") < m.chamadas.index("overlay")
    assert m.footage_existia_no_overlay is True, "o overlay mede o fundo NA footage: ela tem que existir antes"
    assert m.chamadas.index("timeline") < m.chamadas.index("footage")
    assert foot == m.footage and only == m.overlay_dir


def test_com_rapido_reaproveita_a_footage_e_continua_gerando_o_overlay_depois(tmp_path):
    m = MotorFalso(tmp_path)
    m.footage.write_bytes(b"x")
    PD.construir(m, reaproveitar=True)
    assert "footage" not in m.chamadas and m.footage_existia_no_overlay is True
