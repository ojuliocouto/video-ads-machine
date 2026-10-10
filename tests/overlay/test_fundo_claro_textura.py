"""W7.W (A4), refeito em 10/10/2026: a decisão do halo da legenda usa o p90 da faixa (o que o gate de contraste lê).

O defeito original (anúncio da prova, 8,6 s): a legenda ficou sem proteção sobre a interface branca do Claude, mas as linhas
"Web" da tabela passavam atrás das letras: a decisão precisava enxergar estrutura esparsa (era o p01/p99, para a letra
escura). Hoje a letra é BRANCA com halo escuro e o gate lê o p90 do fundo na vizinhança dela: o halo forte (`cgrp-halo`)
entra quando o p90 da faixa passa de `LIMIAR_HALO_FORTE`. Raros pontos claros (1 a 5% da faixa: a mão, a lâmpada) NÃO pedem
o halo forte: o 1º remontar da prova com o p99 achou 150 de cinza num fundo que o gate lia a 0,05 e o halo forte reprovou em
96 amostras (o gancho tem outra regra: p90 contra LIMIAR_HOOK_P90).
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


def test_fundo_misto_metade_clara_metade_escura_fica_no_halo_normal(tmp_path):
    """Metade da faixa de 128 px clara (190) e metade escura: o p10 é 20. O halo forte lê o decil mais escuro da vizinhança
    (1,1:1 contra o fundo escuro); o normal é o que mais se aproxima. Só o fundo INTEIRO claro pede o forte."""
    v = video_9x16(tmp_path / "faixa.mp4", 20, marcas=[(1554, 64, 190)])
    assert FC.tinta_footage(v, 0.2, 0.8, "base") == "clara"
    assert FC.decisao_do_quadro(v, "base")["legenda"] == "clara"


def test_a_caixa_do_texto_estreita_a_medida_e_acompanha_as_linhas_da_tinta(tmp_path):
    """Com o tamanho do grupo a medida é a caixa DELE (as linhas da tinta e a largura do texto): um faixa clara fora do texto
    não pede o halo forte nem derruba o normal."""
    v = video_9x16(tmp_path / "lados.mp4", 20, marcas=[(1604, 86, 230)])        # tudo claro nas linhas da tinta, mas...
    assert FC.tinta_footage(v, 0.2, 0.8, "base", nchars=10) == "halo"
    x0, x1, y0, y1 = FC._caixa_do_texto("base", 10)
    assert (x0, x1) == (540 - 181, 540 + 181) and (y0, y1) == FC.FAIXA_TINTA["base"]
    assert FC._caixa_do_texto("base", 99)[:2] == (140, 940)                       # nunca passa da faixa útil
    assert FC._caixa_do_texto("base")[:2] == FC.CAIXA_X


def test_linhas_claras_finas_de_ate_5_por_cento_nao_pedem_o_halo_forte(tmp_path):
    """Duas tarjas de 4 px (6% da faixa) e um risco de 1 px: o p99 da W7.W as via e pedia o halo forte, que sobre fundo
    escuro lê 1,1:1 no gate. O p90 não as vê, e o gate também não."""
    v = video_9x16(tmp_path / "linhas.mp4", 20, marcas=[(1580, 4, 190), (1630, 4, 190), (1600, 1, 190)])
    assert FC.tinta_footage(v, 0.2, 0.8, "base") == "clara"
    assert FC.decisao_do_quadro(v, "base")["legenda"] == "clara"


def test_fundo_escuro_liso_fica_no_halo_normal(tmp_path):
    v = video_9x16(tmp_path / "escuro.mp4", 20)
    assert FC.tinta_footage(v, 0.2, 0.8, "base") == "clara"
    assert FC.decisao_do_quadro(v, "base")["legenda"] == "clara"


def test_p10_e_p90_so_valem_para_a_legenda_o_gancho_segue_no_p90_proprio(tmp_path, monkeypatch):
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
