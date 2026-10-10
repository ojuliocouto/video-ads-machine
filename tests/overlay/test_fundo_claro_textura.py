"""W7.W (A4), refeito em 10/10/2026: a decisão do halo da legenda enxerga a textura CLARA esparsa atrás das letras.

O defeito original (anúncio da prova, 8,6 s): a legenda ficou sem proteção sobre a interface branca do Claude, mas as linhas
"Web" da tabela passavam atrás das letras. O fundo crítico era o p10/p90 da faixa e a estrutura que cruza a letra era só
~1% dos pixels: o percentil largo não a via. O fundo crítico da LEGENDA é o 1% mais crítico da faixa (p01 e p99); o do
gancho continua sendo o p90 (a regra dele é outra e mede a placa do gancho). Hoje a legenda é BRANCA com halo escuro: o que
a apaga é fundo CLARO atrás das letras, e o halo forte (`cgrp-halo`) entra quando o p99 da faixa passa de
`LIMIAR_HALO_FORTE`.
"""
import subprocess

import pytest

from overlay import fundo_claro as FC

FAIXA_BASE = FC.FAIXA_LEGENDA["base"]              # y 1554 a 1682, x 140 a 940 num quadro de 1080x1920


def video_9x16(destino, fundo, marcas=(), dur=1.0):
    """9x16 de fundo liso `fundo` (cinza 0 a 255) com tarjas finas de cinza `tom` ((y, altura, tom), ...) na faixa da base."""
    cor = "0x%02x%02x%02x" % (fundo, fundo, fundo)
    vf = ",".join("drawbox=x=100:y=%d:w=880:h=%d:color=0x%02x%02x%02x:t=fill" % (y, h, tom, tom, tom)
                  for y, h, tom in marcas) or "null"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
                    "color=c=%s:s=1080x1920:r=10:d=%s,%s,format=yuv420p" % (cor, dur, vf), "-c:v", "libx264", "-crf", "12",
                    str(destino)], check=True, capture_output=True)
    return destino


def test_fundo_branco_liso_pede_o_halo_forte(tmp_path):
    v = video_9x16(tmp_path / "liso.mp4", 215)
    assert FC.tinta_footage(v, 0.2, 0.8, "base") == "halo"
    assert FC.decisao_do_quadro(v, "base")["legenda"] == "halo"


def test_linhas_claras_atras_da_legenda_em_fundo_escuro_pedem_o_halo_forte(tmp_path):
    """Duas tarjas de 4 px claras (190) na faixa de 128 px: ~6% da área, bem acima do 1%. O p99 é 190: a letra branca
    some nelas, e o halo normal (16:1 sobre fundo escuro liso) não as cobre."""
    v = video_9x16(tmp_path / "linhas.mp4", 20, marcas=[(1580, 4, 190), (1630, 4, 190)])
    assert FC.tinta_footage(v, 0.2, 0.8, "base") == "halo"
    assert FC.decisao_do_quadro(v, "base")["legenda"] == "halo"


def test_um_risco_de_menos_de_1_por_cento_nao_pede_o_halo_forte(tmp_path):
    """Uma tarja de 1 px: 0,8% da área. Ruído de compressão e fio de UI não mudam o halo de um trecho inteiro."""
    v = video_9x16(tmp_path / "risco.mp4", 20, marcas=[(1600, 1, 190)])
    assert FC.tinta_footage(v, 0.2, 0.8, "base") == "clara"


def test_fundo_escuro_liso_fica_no_halo_normal(tmp_path):
    v = video_9x16(tmp_path / "escuro.mp4", 20)
    assert FC.tinta_footage(v, 0.2, 0.8, "base") == "clara"
    assert FC.decisao_do_quadro(v, "base")["legenda"] == "clara"


def test_p01_e_p99_so_valem_para_a_legenda_o_gancho_segue_no_p90(tmp_path, monkeypatch):
    chamadas = []
    real = FC._percentis_banda

    def espia(video, t, y0, y1, x0=FC.CAIXA_X[0], x1=FC.CAIXA_X[1], quantis=None):
        chamadas.append((y0, y1, quantis))
        return real(video, t, y0, y1, x0, x1) if quantis is None else real(video, t, y0, y1, x0, x1, quantis)

    monkeypatch.setattr(FC, "_percentis_banda", espia)
    v = video_9x16(tmp_path / "liso.mp4", 215)
    FC.tinta_footage(v, 0.2, 0.8, "base")
    FC.hook_pede_placa(v, 0.0, 1.0, "9x16")
    legenda = [q for y0, y1, q in chamadas if (y0, y1) == FAIXA_BASE]
    gancho = [q for y0, y1, q in chamadas if (y0, y1) == FC.FAIXA_HOOK["9x16"]]
    assert legenda and all(q == FC.QUANTIS_LEGENDA for q in legenda)
    assert gancho and all(q is None for q in gancho)
