"""Cortador de ar morto por ENERGIA no áudio já higienizado.

Por que não pelo token do ASR: o word-level infla o token ("Mas" de 7,3 s) e o detector antigo
lia isso como fala contínua e não cortava; uma pausa de 5,4 s passou para uma peça entregue.
Depois do Voice Isolator a fala fica uns 30 dB acima do silêncio, sem zona cinzenta, então a
energia decide sozinha. No bruto isso não valeria: o ruído do evento cobria tudo.

As constantes abaixo são a fonte do limiar do `gate_ar_morto`: o gate fiscaliza este passo, então
o teto dele sai daqui (`PAUSA_RESIDUAL` mais um quadro), nunca de um número redondo.

  MARGEM    não encostar na fala: cada ponta da pausa fica com esta folga
  RESPIRO   a pausa que SOBRA no miolo depois do corte
  MINIMO    o excesso abaixo disso é ritmo e não se mexe
  QUEDA     dB abaixo do pico da própria peça = silêncio

Ao cortar, a pausa que sobra é MARGEM + RESPIRO + MARGEM (`PAUSA_RESIDUAL`).
"""
import sys
from pathlib import Path

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado.nucleo import energia, segmentos  # noqa: E402

JAN = energia.JANELA_S
MARGEM = 0.12
RESPIRO = 0.18
MINIMO = 0.45
QUEDA = 38.0
PERCENTIL = 0.98
PAUSA_RESIDUAL = RESPIRO + 2 * MARGEM


def silencios(caminho):
    """([(início, fim)] de cada corrida de silêncio da peça, duração total)."""
    db, dur = energia.curva(caminho, jan=JAN)
    return segmentos.silencios(db, JAN, percentil_q=PERCENTIL, queda_db=QUEDA), dur


def manter(caminho, janelas=None):
    """Segmentos a MANTER: tudo menos o excesso de cada pausa longa.

    `janelas` limita a análise aos trechos escolhidos do take: a saída é a interseção.
    """
    sils, dur = silencios(caminho)
    remover = []
    for a, b in sils:
        a2, b2 = a + MARGEM, b - MARGEM          # encolhe pelas margens: nunca encostar na fala
        if b2 - a2 <= MINIMO:
            continue
        sobra = (b2 - a2) - RESPIRO              # deixa RESPIRO no meio da pausa, tira o resto
        if sobra <= 0:
            continue
        meio = (a2 + b2) / 2
        remover.append((meio - sobra / 2, meio + sobra / 2))
    segs, pos = [], 0.0
    for a, b in remover:
        if a > pos:
            segs.append((pos, a))
        pos = b
    if pos < dur:
        segs.append((pos, dur))
    if janelas is None:
        return segs
    saida = []
    for ja, jb in janelas:
        for s, e in segs:
            i, f = max(ja, s), min(jb, e)
            if f - i > 0.08:
                saida.append((i, f))
    return saida


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("uso: ar_morto_energia.py ARQUIVO...   (lista as pausas longas de cada arquivo)", file=sys.stderr)
        return 2
    for arq in argv:
        try:
            sils, dur = silencios(arq)
        except energia.ErroDeAudio as e:
            print(str(e), file=sys.stderr)
            return 2
        longos = [(a, b) for a, b in sils if b - a >= MINIMO]
        maior = max((b - a for a, b in longos), default=0.0)
        print("%s: %.1fs, %d pausas >= %.2fs, maior %.2fs" % (Path(arq).name, dur, len(longos), MINIMO, maior))
    return 0


if __name__ == "__main__":
    sys.exit(main())
