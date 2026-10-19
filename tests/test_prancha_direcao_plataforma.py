"""A prancha de direção nos três sistemas (W1.D): HyperFrames por `node <cli.js>`, fontes do repo e `movie=` escapado."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import build_composite as BC
import plataforma
import prancha_direcao as PD
from tests.fixtures.nome_esquisito import NOME_ESQUISITO

REPO = Path(__file__).resolve().parents[1]


# --- HyperFrames -------------------------------------------------------------------------------------

def test_o_snapshot_chama_o_hyperframes_pelo_node_do_pacote(monkeypatch, tmp_path):
    only = tmp_path / "overlay"
    only.mkdir()
    (only / "index.html").write_text("<html><head></head><body></body></html>", encoding="utf-8")
    raizes, chamadas = [], []
    monkeypatch.setattr(plataforma, "hf_cmd", lambda raiz: raizes.append(raiz) or ["node", "cli.js"])
    monkeypatch.setattr(PD, "sh", lambda cmd, **kw: chamadas.append(cmd) or "")
    PD.snapshots(only, [0.5, 1.0])
    assert raizes and all(r == BC.RAIZ for r in raizes)
    assert len(chamadas) == 2                                    # os dois passes: fundo preto e fundo branco
    for cmd in chamadas:
        assert cmd[:3] == ["node", "cli.js", "snapshot"]


def test_o_modulo_nao_aponta_mais_para_node_modules_bin():
    texto = (REPO / "scripts" / "prancha_direcao.py").read_text(encoding="utf-8")
    assert "HF = str(BC.hyperframes())" not in texto


# --- fontes ------------------------------------------------------------------------------------------

def test_a_fonte_do_repo_vem_antes_da_do_sistema():
    candidatas = PD.candidatas_de_fonte()
    assert candidatas[0].endswith("inter-800.ttf")
    assert os.path.dirname(candidatas[0]) == str(REPO / "fonts")
    assert candidatas.index(candidatas[0]) < min(candidatas.index(p) for p in PD.FONTES_DO_SISTEMA)


def test_a_reserva_de_fonte_tem_o_arial_do_windows_e_o_do_mac():
    assert r"C:\Windows\Fonts\arialbd.ttf" in PD.FONTES_DO_SISTEMA
    assert r"C:\Windows\Fonts\arial.ttf" in PD.FONTES_DO_SISTEMA
    assert "/System/Library/Fonts/Supplemental/Arial Bold.ttf" in PD.FONTES_DO_SISTEMA


def test_fonte_carrega_a_inter_do_repo():
    assert PD.fonte(20).path.endswith("inter-800.ttf")


def test_sem_a_fonte_do_repo_usa_a_do_sistema_e_sem_nenhuma_cai_na_padrao(monkeypatch, tmp_path):
    reserva = tmp_path / "reserva.ttf"
    shutil.copy(REPO / "fonts" / "inter-800.ttf", reserva)
    monkeypatch.setattr(PD, "FONTES_DO_REPO", (str(tmp_path / "nao-existe.ttf"),))
    monkeypatch.setattr(PD, "FONTES_DO_SISTEMA", (str(tmp_path / "x.ttf"), str(reserva)))
    assert PD.fonte(20).path == str(reserva)
    monkeypatch.setattr(PD, "FONTES_DO_SISTEMA", (str(tmp_path / "x.ttf"),))
    monkeypatch.setattr(PD.ImageFont, "load_default", lambda *a, **k: "padrao-do-pillow")
    assert PD.fonte(20) == "padrao-do-pillow"


# --- cortes de cena (ffprobe + movie=) ---------------------------------------------------------------

@pytest.mark.skipif(not shutil.which("ffprobe"), reason="ffprobe ausente")
def test_os_cortes_de_cena_leem_um_video_de_nome_esquisito(tmp_path):
    pasta = tmp_path / NOME_ESQUISITO
    pasta.mkdir()
    video = pasta / ("pipoca " + NOME_ESQUISITO + ".mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", "color=red:s=64x64:d=1:r=10",
                    "-f", "lavfi", "-i", "color=blue:s=64x64:d=1:r=10", "-filter_complex",
                    "[0:v][1:v]concat=n=2:v=1:a=0", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
                   check=True, capture_output=True)
    r = PD.cortes_de_cena(video)
    assert r.returncode == 0, r.stderr
    tempos = [float(linha.split(",")[0]) for linha in r.stdout.strip().splitlines()]
    assert len(tempos) == 1 and abs(tempos[0] - 1.0) < 0.15, r.stdout          # o corte de vermelho para azul


def test_o_filtro_de_cena_escapa_o_caminho_nas_duas_camadas():
    arq = "/dados/a:b=c'd.mp4"
    assert PD.filtro_de_cena(arq) == "movie=" + plataforma.escapar_filtro(arq) + r",select=gt(scene\,0.4)"
