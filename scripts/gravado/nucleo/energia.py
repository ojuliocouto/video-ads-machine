"""Curva de energia (dB por janela) do áudio: a medida de que o gravado inteiro depende.

Esta conta estava copiada em cinco arquivos do pipeline (o cortador de ar morto, o gate de ar
morto, o gate de envelope, o separador de frases e o de voz distante), cada cópia com a sua
janela e o seu pedaço de lógica por cima. Agora vive aqui, uma vez.

Por que ENERGIA e não o tempo do ASR: o word-level do ASR em nuvem infla o token ("Mas" de 7,3 s
escondeu uma pausa de 5,4 s). Depois do Voice Isolator a fala fica uns 30 dB acima do silêncio,
sem zona cinzenta, e a energia decide sozinha. O limiar é sempre RELATIVO ao próprio áudio
(`limiar_relativo`): um limiar absoluto acerta num take e erra no outro.

  curva(arquivo) -> (db, duracao_s)         dB por janela de 20 ms, só janelas cheias
  percentil(db, q) -> float                 posto mais próximo, como nos scripts de origem
  limiar_relativo(db, q, queda_db) -> float percentil menos uma queda em dB
"""
import subprocess

import numpy as np

from gravado.veredito import InsumoInvalido

SR = 16000
JANELA_S = 0.02
PISO_DB = -120.0        # silêncio digital exato


class ErroDeAudio(InsumoInvalido, RuntimeError):
    """O ffmpeg não conseguiu decodificar o arquivo. Nunca vira "silêncio" calado, e num gate é
    insumo inválido (saída 2): não deu para medir."""


def amostras(caminho, ini=0.0, dur=None, sr=SR):
    """PCM mono de 16 bits (int16) de `caminho`, de `ini` por `dur` segundos (tudo se None)."""
    caminho = str(caminho)
    cmd = ["ffmpeg", "-v", "error", "-nostdin"]
    if ini:
        cmd += ["-ss", str(float(ini))]
    cmd += ["-i", caminho]
    if dur is not None:
        cmd += ["-t", str(float(dur))]
    cmd += ["-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"]
    try:
        p = subprocess.run(cmd, capture_output=True)
    except FileNotFoundError:
        raise ErroDeAudio("ffmpeg não encontrado: instale com `brew install ffmpeg`")
    if p.returncode != 0:
        detalhe = p.stderr.decode("utf-8", "replace").strip()[-300:]
        raise ErroDeAudio("não consegui ler o áudio de %s: %s" % (caminho, detalhe or "ffmpeg falhou"))
    bruto = p.stdout[: len(p.stdout) // 2 * 2]
    return np.frombuffer(bruto, dtype="<i2")


def duracao_s(caminho):
    """Duração do arquivo em segundos (ffprobe)."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                            "default=nw=1:nk=1", str(caminho)], capture_output=True, text=True)
    except FileNotFoundError:
        raise ErroDeAudio("ffprobe não encontrado: instale o ffmpeg com `brew install ffmpeg`")
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise ErroDeAudio("não consegui ler a duração de %s: %s" % (caminho, r.stderr.strip()[-200:] or "ffprobe falhou"))


def db_por_janela(pcm, sr=SR, jan=JANELA_S):
    """RMS em dBFS por janela de `jan` s. Só janelas CHEIAS; o resto do fim é descartado."""
    n = int(round(sr * jan))
    m = len(pcm) // n
    if m == 0:
        return np.zeros(0)
    blocos = np.asarray(pcm[: m * n], dtype=np.float64).reshape(m, n)
    rms = np.sqrt((blocos ** 2).mean(axis=1))
    db = np.full(m, PISO_DB)
    positivo = rms > 0
    db[positivo] = 20.0 * np.log10(rms[positivo] / 32768.0)
    return db


def curva(caminho, ini=0.0, dur=None, sr=SR, jan=JANELA_S):
    """(dB por janela, duração em segundos do trecho decodificado)."""
    pcm = amostras(caminho, ini=ini, dur=dur, sr=sr)
    return db_por_janela(pcm, sr, jan), len(pcm) / float(sr)


def percentil(db, q):
    """Posto mais próximo: `sorted(db)[int(len * q)]`. Vazio devolve o piso."""
    db = np.asarray(db)
    if not db.size:
        return PISO_DB
    ordenado = np.sort(db)
    return float(ordenado[min(len(ordenado) - 1, int(len(ordenado) * q))])


def limiar_relativo(db, q, queda_db):
    """O nível `queda_db` abaixo do percentil `q` do PRÓPRIO áudio."""
    return percentil(db, q) - queda_db
