"""Backend faster-whisper: local, qualquer plataforma, mais lento que o parakeet.

Armadilhas medidas que este backend respeita:
  - `condition_on_previous_text=False` sempre. Com `initial_prompt` ligado ele REPETE um
    parágrafo anterior no lugar do trecho atual, o que é pior que perder palavra: sai
    plausível.
  - o modelo `small` erra nome próprio ("sharelock homos"). O glossário (prompt e correção
    de grafia) e o gate de fala x roteiro seguram isso; não é um defeito escondido.
"""
from pathlib import Path

from ..transcrever import monotonizar

NOME = "faster_whisper"
MODELO, COMPUTE = "small", "int8"


def disponivel(amb):
    return bool(amb.importavel("faster_whisper"))


def _fabrica_real():
    from faster_whisper import WhisperModel
    return WhisperModel(MODELO, device="cpu", compute_type=COMPUTE)


def _palavras(segmentos):
    brutas = []
    for seg in segmentos:
        com_tempo = [w for w in (getattr(seg, "words", None) or [])
                     if str(w.word).strip() and w.start is not None and w.end is not None]
        if com_tempo:
            brutas.extend({"text": w.word, "start": w.start, "end": w.end} for w in com_tempo)
            continue
        texto = str(seg.text).split()
        if not texto:
            continue
        passo = (seg.end - seg.start) / len(texto)
        brutas.extend({"text": w, "start": seg.start + k * passo, "end": seg.start + (k + 1) * passo}
                      for k, w in enumerate(texto))
    return monotonizar(brutas)


def transcrever(audio, *, amb, workdir, prompt="", idioma="pt", fabrica_modelo=None):
    modelo = (fabrica_modelo or _fabrica_real)()
    segmentos, _info = modelo.transcribe(
        str(Path(audio)), language=idioma, initial_prompt=prompt or None,
        condition_on_previous_text=False, word_timestamps=True, vad_filter=False)
    return _palavras(segmentos)
