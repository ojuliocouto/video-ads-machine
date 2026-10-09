"""Pausa de verdade sai do ÁUDIO, nunca do buraco da transcrição.

Fonte única da pausa: o mix usa para decidir quando a cama de música sobe (ducking por
automação) e o gate de mix usa para decidir onde cobrar a subida. Os dois lendo a mesma
função não podem discordar.

Por que não a transcrição: o alinhamento por palavra PERDE palavra, e cada palavra perdida
vira um buraco que o motor lê como silêncio. Medindo a voz nas maiores dessas "pausas",
todas tinham voz no mesmo nível da fala contínua: a cama subia 17,7 dB no MEIO da frase,
61 vezes em 311 s, e o diretor reprovou ("a música fica aumentando e diminuindo do nada").

Mais duro: medindo o envelope daquela peça, ela NÃO TINHA nenhum vale de 0,5 s. Monólogo de
TTS acelerado não tem pausa. A resposta certa não é afinar o limiar: é a cama ficar PARADA.
`pausas` devolve lista vazia nesse caso, e a automação vira uma constante. Peça que tenha
pausa de verdade continua respirando, sem mudar nada.

O limiar é RELATIVO de propósito (mediana da voz menos `queda_db`): peça gravada e peça de
TTS têm pisos diferentes, e um limiar absoluto acerta numa e erra na outra.

Precisão: o envelope tem uma janela de 50 ms. Uma borda que cai no meio de uma janela só
conta na janela seguinte, então cada borda erra no máximo 50 ms (para dentro da pausa).

Uso:
  from audio import pausas_reais
  pausas_reais.pausas("voz.wav")                       -> [(1.5, 2.1), (4.0, 4.8)]
  pausas_reais.pausas("voz.wav", dur_min_s=0.8)
"""
import subprocess

import numpy as np

SR, JAN = 8000, 0.05
DUR_MIN_S = 0.5      # vale mais curto que isso é respiro, não pausa
QUEDA_DB = 12.0      # quanto abaixo da MEDIANA da voz o vale precisa ficar


class ErroDeAudio(RuntimeError):
    """O ffmpeg não conseguiu decodificar o arquivo. Nunca vira 'sem pausa' em silêncio."""


def envelope_db(arq, sr=SR, jan=JAN):
    """RMS em dB por janela de `jan` segundos. Devolve (array de dB, jan)."""
    p = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(arq), "-vn", "-ac", "1",
                        "-ar", str(sr), "-f", "s16le", "-"], capture_output=True)
    if p.returncode != 0:
        detalhe = p.stderr.decode("utf-8", "replace").strip()[-300:]
        raise ErroDeAudio(f"não consegui ler o áudio de {arq}: {detalhe or 'ffmpeg falhou'}")
    x = np.frombuffer(p.stdout, dtype=np.int16).astype(np.float64) / 32768.0
    n = int(sr * jan)
    m = len(x) // n * n
    if m == 0:
        return np.array([]), jan
    rms = np.sqrt((x[:m].reshape(-1, n) ** 2).mean(axis=1) + 1e-12)
    return 20 * np.log10(rms), jan


def pausas_do_envelope(db, jan=JAN, dur_min_s=DUR_MIN_S, queda_db=QUEDA_DB):
    """(início, fim) dos vales de um envelope: a voz fica `queda_db` abaixo da MEDIANA dela
    por pelo menos `dur_min_s`. Pura: não chama ffmpeg."""
    db = np.asarray(db, dtype=np.float64)
    if not len(db):
        return []
    limiar = float(np.median(db)) - queda_db
    baixo = db < limiar
    saida, ini = [], None
    for i, b in enumerate(baixo):
        if b and ini is None:
            ini = i
        elif not b and ini is not None:
            if (i - ini) * jan >= dur_min_s - 1e-9:
                saida.append((round(ini * jan, 3), round(i * jan, 3)))
            ini = None
    if ini is not None and (len(baixo) - ini) * jan >= dur_min_s - 1e-9:
        saida.append((round(ini * jan, 3), round(len(baixo) * jan, 3)))
    return saida


def pausas(arq, dur_min_s=DUR_MIN_S, queda_db=QUEDA_DB):
    """Lista de (início, fim) em segundos das pausas reais do áudio. Vazia se não houver."""
    db, jan = envelope_db(arq)
    return pausas_do_envelope(db, jan, dur_min_s, queda_db)
