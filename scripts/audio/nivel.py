"""Nível de áudio por janela (W7.Z): o que o mixer precisa medir para fechar a cama de cada pausa.

A mesma conta do `gate_mix.Faixa.nivel_db` (RMS em dB de uma janela, em mono a 16 kHz), em módulo próprio para o mixer não
importar um gate. Decodifica com ffmpeg uma vez e mede em numpy.
"""
import math
import subprocess

import numpy as np

SR_MEDIDA = 16000          # 16 kHz cobre a fala e quase toda a energia da música; decodificar é barato


class ErroDeNivel(RuntimeError):
    """O ffmpeg não decodificou o áudio a medir."""


def carregar_mono(arquivo, *, filtro=None, em_loop=False, duracao_s=None, sr=SR_MEDIDA):
    """O áudio de `arquivo` em mono, float32, a `sr` Hz. `filtro` é um `-af` (a trilha com seus fades, por exemplo);
    `em_loop` repete a entrada (trilha mais curta que a peça) e então `duracao_s` corta."""
    cmd = ["ffmpeg", "-v", "error", "-nostdin"]
    if em_loop:
        cmd += ["-stream_loop", "-1"]
    cmd += ["-i", str(arquivo), "-vn"]
    if duracao_s is not None:
        cmd += ["-t", "%.3f" % duracao_s]
    if filtro:
        cmd += ["-af", filtro]
    cmd += ["-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0 or not r.stdout:
        raise ErroDeNivel("não consegui decodificar %s para medir o nível: %s"
                          % (arquivo, r.stderr.decode("utf-8", "replace").strip()[-200:] or "sem áudio"))
    return np.frombuffer(r.stdout, dtype=np.float32)


def nivel_db(x, t, d, sr=SR_MEDIDA):
    """RMS em dB da janela [t, t + d) s de `x`; -120 dB para janela vazia ou fora do áudio."""
    i, j = max(int(round(t * sr)), 0), min(int(round((t + d) * sr)), len(x))
    if j <= i:
        return -120.0
    seg = x[i:j].astype(np.float64)
    return float(10.0 * math.log10(float(np.mean(seg ** 2)) + 1e-12))
