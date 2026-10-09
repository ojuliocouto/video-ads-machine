"""Blocos de fala por energia, em dois passes, e as pausas que o primeiro passe esconde.

Três presets, todos medidos no material de origem (take de evento, lapela, Voice Isolator):

  FRASE     janela 50 ms, separador 0,38 s    acha FRASES (a unidade do plano: uma frase por trecho)
  SUBBLOCO  janela 20 ms, separador 0,14 s    segundo passe: expõe a retomada de 0,32 s
  VOZ       janela 50 ms, sem fundir nada     nível de cada bloco, para separar quem fala

O separador de 0,38 s sozinho NÃO basta: uma retomada com pausa de 0,32 s vira um bloco só, e o
ASR ainda deduplica a frase ao ler o bloco inteiro ("E sabe o que aconteceu?" saiu duas vezes
numa peça entregue). `pausas_escondidas` devolve as pausas de 0,14 a 0,38 s que ficaram DENTRO
de uma frase: é onde se lê sub-bloco a sub-bloco.

Áudio sem sinal (silêncio digital) não tem fala: o limiar relativo ao próprio áudio transformaria
o arquivo mudo num bloco só, então ele devolve lista vazia.
"""
import numpy as np

from gravado.nucleo import energia

SEM_SINAL_DB = -100.0

FRASE = dict(jan=0.05, percentil_q=0.97, queda_db=38.0, min_bloco=0.12, gap=0.38, min_final=0.25)
SUBBLOCO = dict(jan=0.02, percentil_q=0.95, queda_db=32.0, min_bloco=0.10, gap=0.14, min_final=0.18)
VOZ = dict(jan=0.05, percentil_q=0.97, queda_db=38.0, min_bloco=0.12, gap=0.0, min_final=0.0)


def corridas(mascara, jan, dur_min=0.0):
    """(início, fim) em segundos de cada corrida de True, com pelo menos `dur_min`."""
    m = np.asarray(mascara, dtype=bool)
    if not m.size:
        return []
    bordas = np.diff(np.concatenate(([0], m.astype(np.int8), [0])))
    inicios = np.where(bordas == 1)[0]
    fins = np.where(bordas == -1)[0]
    saida = []
    for i, f in zip(inicios, fins):
        if (f - i) * jan >= dur_min - 1e-9:
            saida.append((round(i * jan, 6), round(f * jan, 6)))
    return saida


def fundir(blocos, gap):
    """Junta blocos separados por MENOS de `gap` segundos. `gap` 0 não funde nada."""
    saida = []
    for a, b in blocos:
        if saida and a - saida[-1][1] < gap:
            saida[-1] = (saida[-1][0], b)
        else:
            saida.append((a, b))
    return saida


def blocos_de_fala(db, jan, *, percentil_q, queda_db, min_bloco, gap=0.0, min_final=0.0):
    """Blocos de energia acima de (percentil `percentil_q` menos `queda_db`)."""
    db = np.asarray(db)
    if not db.size or energia.percentil(db, percentil_q) <= SEM_SINAL_DB:
        return []
    limiar = energia.limiar_relativo(db, percentil_q, queda_db)
    blocos = fundir(corridas(db >= limiar, jan, dur_min=min_bloco), gap)
    return [(a, b) for a, b in blocos if b - a >= min_final - 1e-9]


def silencios(db, jan, *, percentil_q=0.98, queda_db=38.0, dur_min=0.0):
    """Corridas de silêncio: energia abaixo de (percentil menos `queda_db`) do próprio áudio."""
    db = np.asarray(db)
    if not db.size:
        return []
    if energia.percentil(db, percentil_q) <= SEM_SINAL_DB:
        return [(0.0, round(len(db) * jan, 6))]
    limiar = energia.limiar_relativo(db, percentil_q, queda_db)
    return corridas(db < limiar, jan, dur_min=dur_min)


def picos_por_bloco(db, jan, blocos):
    """Maior nível (dB) dentro de cada bloco."""
    db = np.asarray(db)
    saida = []
    for a, b in blocos:
        trecho = db[int(round(a / jan)):int(round(b / jan))]
        saida.append(float(trecho.max()) if trecho.size else energia.PISO_DB)
    return saida


def _blocos(db, preset):
    p = dict(preset)
    jan = p.pop("jan")
    return blocos_de_fala(db, jan, **p)


def frases(caminho, ini=0.0, dur=None):
    """Frases (preset de 0,38 s), com o tempo no eixo do arquivo inteiro."""
    db, _ = energia.curva(caminho, ini=ini, dur=dur, jan=FRASE["jan"])
    return [(round(a + ini, 3), round(b + ini, 3)) for a, b in _blocos(db, FRASE)]


def subblocos(caminho, ini, fim):
    """Segundo passe (0,14 s) dentro da janela `ini`..`fim`, com o tempo no eixo do arquivo."""
    db, _ = energia.curva(caminho, ini=ini, dur=fim - ini, jan=SUBBLOCO["jan"])
    return [(round(a + ini, 3), round(b + ini, 3)) for a, b in _blocos(db, SUBBLOCO)]


def blocos_com_pico(caminho):
    """[(início, fim, pico_dB)] do take inteiro, sem fundir pausas curtas."""
    db, _ = energia.curva(caminho, jan=VOZ["jan"])
    blocos = _blocos(db, VOZ)
    return [(a, b, p) for (a, b), p in zip(blocos, picos_por_bloco(db, VOZ["jan"], blocos))]


def pausas_escondidas(frases_, subblocos_):
    """Pausas entre sub-blocos que o primeiro passe fundiu DENTRO de uma frase: [(ini, fim)]."""
    saida = []
    eps = 1e-6
    for a, b in frases_:
        dentro = [s for s in subblocos_ if s[0] >= a - eps and s[1] <= b + eps]
        for anterior, seguinte in zip(dentro, dentro[1:]):
            saida.append((anterior[1], seguinte[0]))
    return saida
