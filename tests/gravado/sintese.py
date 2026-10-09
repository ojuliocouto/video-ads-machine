"""Material sintético do gravado (W2.D): áudio por blocos de nível conhecido e um projeto mínimo.

Nada aqui lê mídia real. Cada função cria, em tmp, um arquivo com propriedades CONHECIDAS (a
duração de cada bloco, o nível RMS em dBFS, o silêncio exato), e duas gerações dão os mesmos
bytes: a senoide é calculada em numpy e gravada com o módulo `wave`, sem relógio nem acaso.

A frequência é de 250 Hz de propósito: a janela de 20 ms do núcleo de energia cobre 5 ciclos
inteiros, então o RMS medido bate com o pedido sem erro de borda de ciclo.
"""
import json
import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 16000
FREQ = 250.0


def senoide(dur_s, rms_db, sr=SR, inicio=0):
    """Senoide de RMS `rms_db` (dBFS). `inicio` é o índice da primeira amostra (fase contínua)."""
    n = int(round(dur_s * sr))
    t = (np.arange(n) + inicio) / float(sr)
    amplitude = (10.0 ** (rms_db / 20.0)) * np.sqrt(2.0)
    return amplitude * np.sin(2.0 * np.pi * FREQ * t)


def sinal_por_blocos(trechos, sr=SR):
    """`trechos` = [(dur_s, rms_db)], com rms_db None para silêncio exato. Devolve float64."""
    partes, usadas = [], 0
    for dur, nivel in trechos:
        n = int(round(dur * sr))
        if nivel is None:
            partes.append(np.zeros(n))
        else:
            partes.append(senoide(dur, nivel, sr, inicio=usadas))
        usadas += n
    return np.concatenate(partes) if partes else np.zeros(0)


def escrever_wav(destino, sinal, sr=SR):
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(np.round(np.asarray(sinal) * 32767.0), -32768, 32767).astype("<i2")
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return destino


def audio_por_blocos(destino, trechos, sr=SR):
    """wav mono com os `trechos` em sequência. Devolve o Path."""
    return escrever_wav(destino, sinal_por_blocos(trechos, sr), sr)


def para_mp3(wav, destino, taxa="128k"):
    """mp3 a partir de um wav (o limpo do Voice Isolator chega em mp3)."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", str(wav), "-c:a",
                        "libmp3lame", "-b:a", taxa, str(destino)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return destino


def duracao_do_wav(caminho):
    with wave.open(str(caminho), "rb") as w:
        return w.getnframes() / float(w.getframerate())


class LeitorFalso(object):
    """O que os gates esperam de `nucleo.asr.Leitor`, sem ASR de verdade.

    `textos`: lista consumida em ordem por `texto()`, ou dict {(ini, fim): texto} (ini e fim
    arredondados a 2 casas). `palavras_da_peca`: lista devolvida por `palavras()`.
    """

    def __init__(self, textos=None, palavras_da_peca=None, falhar=None):
        self.textos = textos
        self.palavras_da_peca = palavras_da_peca or []
        self.falhar = falhar
        self.chamadas = []

    def texto(self, audio, ini, fim, margem=0.1):
        self.chamadas.append((str(audio), round(ini, 2), round(fim, 2)))
        if self.falhar is not None:
            raise self.falhar
        if isinstance(self.textos, dict):
            return self.textos.get((round(ini, 2), round(fim, 2)), "")
        if isinstance(self.textos, list):
            return self.textos[len(self.chamadas) - 1] if len(self.chamadas) <= len(self.textos) else ""
        return str(self.textos or "")

    def palavras(self, audio, exigir_borda=False):
        self.chamadas.append((str(audio), "palavras", bool(exigir_borda)))
        if self.falhar is not None:
            raise self.falhar
        return list(self.palavras_da_peca)

    def texto_da_peca(self, arquivo):
        self.chamadas.append((str(arquivo), "peca"))
        if self.falhar is not None:
            raise self.falhar
        return str(self.textos or "")


def projeto_minimo(base, ads, brutos=None, ignorar=()):
    """Escreve plano_gravado.json em `base` e devolve o dict. `ads` = {cod: {...}}."""
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    plano = {"versao": 1, "brutos": str(brutos if brutos is not None else base / "brutos"),
             "ignorar": list(ignorar), "ads": ads}
    (base / "plano_gravado.json").write_text(json.dumps(plano, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    return plano
