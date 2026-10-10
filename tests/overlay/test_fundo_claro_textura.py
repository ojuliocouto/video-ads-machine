"""W7.W (A4): a decisão da tinta da legenda enxerga a textura escura esparsa atrás das letras.

O defeito (anúncio da prova, 8,6 s): a legenda ficou com tinta escura SEM placa sobre a interface branca do Claude, mas as
linhas "Web" da tabela passavam atrás das letras. O fundo crítico era o p10 da faixa (201, claro) e as linhas escuras eram
só ~1% dos pixels (p01 = 135 a 154, mínimo 50): o p10 não as via, a tinta escura "lia" no papel e o gate de contraste
(que mede o anel de fora do texto) também não. O fundo crítico da LEGENDA passa a ser o 1% mais crítico da faixa (p01 e p99);
o do gancho continua sendo o p90 (a regra dele é outra e mede a placa do gancho).
"""
import subprocess

import pytest

from overlay import fundo_claro as FC

FAIXA_BAIXA = FC.FAIXA_LEGENDA["baixa"]            # y 1370 a 1520, x 130 a 950 num quadro de 1080x1920


def video_9x16(destino, fundo, marcas=(), dur=1.0):
    """9x16 de fundo liso `fundo` (cinza 0 a 255) com tarjas finas de cinza `tom` ((y, altura, tom), ...) na faixa baixa."""
    cor = "0x%02x%02x%02x" % (fundo, fundo, fundo)
    vf = ",".join("drawbox=x=100:y=%d:w=880:h=%d:color=0x%02x%02x%02x:t=fill" % (y, h, tom, tom, tom)
                  for y, h, tom in marcas) or "null"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
                    "color=c=%s:s=1080x1920:r=10:d=%s,%s,format=yuv420p" % (cor, dur, vf), "-c:v", "libx264", "-crf", "12",
                    str(destino)], check=True, capture_output=True)
    return destino


def test_fundo_branco_liso_segue_com_tinta_invertida_sem_placa(tmp_path):
    v = video_9x16(tmp_path / "liso.mp4", 215)
    assert FC.tinta_footage(v, 0.2, 0.8, "baixa") == "invertida"
    assert FC.decisao_do_quadro(v, "baixa")["legenda"] == "invertida"


def test_linhas_escuras_atras_da_legenda_em_fundo_branco_pedem_placa(tmp_path):
    """Duas tarjas de 2 px cinza-médio (110) na faixa de 150 px: ~2,7% da área, 3,6:1 contra a tinta escura. O p10 é 215."""
    v = video_9x16(tmp_path / "linhas.mp4", 215, marcas=[(1400, 2, 110), (1450, 2, 110)])
    assert FC.tinta_footage(v, 0.2, 0.8, "baixa") == "placa"
    assert FC.decisao_do_quadro(v, "baixa")["legenda"] == "placa"


def test_um_risco_de_menos_de_1_por_cento_nao_vira_placa(tmp_path):
    """Uma tarja de 1 px: 0,7% da área. Ruído de compressão e fio de UI não derrubam a tinta de um trecho inteiro."""
    v = video_9x16(tmp_path / "risco.mp4", 215, marcas=[(1420, 1, 110)])
    assert FC.tinta_footage(v, 0.2, 0.8, "baixa") == "invertida"


def test_pontinhos_claros_em_fundo_escuro_nao_mudam_a_tinta_clara(tmp_path):
    v = video_9x16(tmp_path / "escuro.mp4", 20, marcas=[(1420, 1, 150)])
    assert FC.tinta_footage(v, 0.2, 0.8, "baixa") == "clara"


def test_p01_e_p99_so_valem_para_a_legenda_o_gancho_segue_no_p90(tmp_path, monkeypatch):
    chamadas = []
    real = FC._percentis_banda

    def espia(video, t, y0, y1, x0=FC.CAIXA_X[0], x1=FC.CAIXA_X[1], quantis=None):
        chamadas.append((y0, y1, quantis))
        return real(video, t, y0, y1, x0, x1) if quantis is None else real(video, t, y0, y1, x0, x1, quantis)

    monkeypatch.setattr(FC, "_percentis_banda", espia)
    v = video_9x16(tmp_path / "liso.mp4", 215)
    FC.tinta_footage(v, 0.2, 0.8, "baixa")
    FC.hook_pede_placa(v, 0.0, 1.0, "9x16")
    legenda = [q for y0, y1, q in chamadas if (y0, y1) == FAIXA_BAIXA]
    gancho = [q for y0, y1, q in chamadas if (y0, y1) == FC.FAIXA_HOOK["9x16"]]
    assert legenda and all(q == FC.QUANTIS_LEGENDA for q in legenda)
    assert gancho and all(q is None for q in gancho)
