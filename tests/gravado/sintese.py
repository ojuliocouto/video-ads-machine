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

    def __init__(self, textos=None, palavras_da_peca=None, falhar=None, texto_peca=None):
        self.textos = textos
        self.palavras_da_peca = palavras_da_peca or []
        self.falhar = falhar
        self.texto_peca = texto_peca
        self.chamadas = []

    def texto(self, audio, ini, fim, margem=0.1):
        self.chamadas.append((str(audio), round(ini, 2), round(fim, 2)))
        if self.falhar is not None:
            raise self.falhar
        if callable(self.textos):
            return self.textos(audio, ini, fim)
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
        if self.texto_peca is not None:
            return self.texto_peca(arquivo) if callable(self.texto_peca) else self.texto_peca
        return str(self.textos or "")

    def fala_ou_falha(self, arquivo):
        try:
            return self.texto_da_peca(arquivo)
        except Exception as e:                  # o contrato real devolve o marcador, nunca levanta
            return "FALHA: %s" % e


def projeto_minimo(base, ads, brutos=None, ignorar=()):
    """Escreve plano_gravado.json em `base` e devolve o dict. `ads` = {cod: {...}}."""
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    plano = {"versao": 1, "brutos": str(brutos if brutos is not None else base / "brutos"),
             "ignorar": list(ignorar), "ads": ads}
    (base / "plano_gravado.json").write_text(json.dumps(plano, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    return plano


ADS_DE_TESTE = {
    "A1": {"nome": "Primeiro", "tema": "primeiro",
           "corpo": [["T1", 0.0, 3.5]],
           "cta_normal": [["T1", 4.0, 5.0]],
           "cta_desconto": [["T1", 4.2, 5.0]]},
    "B2": {"nome": "Segundo", "corpo": [["T2", 0.5, 2.0]], "cta_normal": [["T1", 4.0, 5.0]]},
}
BLOCOS_DO_TAKE = [(1.0, -12.0), (1.5, None), (1.0, -12.0), (0.5, None), (1.0, -12.0)]   # 5,0 s

FRASES_DISTINTAS = [
    "você perde três horas por dia nisso", "com uma automação isso roda sozinho",
    "a proposta atrasa e o cliente esfria", "monte o seu fluxo em uma tarde",
    "toque em saiba mais para começar", "ninguém precisa de planilha para isso",
    "quem testa não volta atrás", "o resultado aparece na primeira semana"]


def textos_em_sequencia(frases=FRASES_DISTINTAS):
    """Função para LeitorFalso(textos=...): uma frase diferente a cada chamada, em ordem."""
    contador = {"n": 0}

    def proxima(audio, ini, fim):
        contador["n"] += 1
        return frases[(contador["n"] - 1) % len(frases)]
    return proxima


def projeto_de_teste(tmp_path, ads=None, com_limpo=True, estado=None):
    """Projeto de take gravado com o plano `ads` e o take limpo `BLOCOS_DO_TAKE` em T1 e T2."""
    from gravado import projeto as gp
    base = Path(tmp_path) / "leva"
    projeto_minimo(base, ads if ads is not None else ADS_DE_TESTE)
    if com_limpo:
        audio = audio_por_blocos(Path(tmp_path) / "t.wav", BLOCOS_DO_TAKE)
        (base / "limpo").mkdir(parents=True, exist_ok=True)
        for take in ("T1", "T2"):                   # wav: mp3 mexe 20 a 40 ms nas bordas
            (base / "limpo" / (take + ".wav")).write_bytes(audio.read_bytes())
    return gp.carregar(base, estado=estado)
