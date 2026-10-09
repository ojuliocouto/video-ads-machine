"""Mede piso de ruído, pico e distribuição de energia de um áudio, por janela de 20 ms.

Depois do Voice Isolator o piso esperado cai de uns -33 dB para uns -90 dB; se não caiu, o
isolador não fez o trabalho e o cortador por energia não vai achar pausa.

    python3 scripts/gravado/medir_audio.py ARQUIVO...
"""
import sys
from pathlib import Path

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado import veredito  # noqa: E402
from gravado.nucleo import energia  # noqa: E402

SILENCIO_DB = -40.0


def relatorio(caminho):
    db, dur = energia.curva(caminho)
    if not len(db):
        raise veredito.InsumoInvalido("o áudio %s é curto demais para medir" % caminho)
    silencio = db[db < SILENCIO_DB]
    return {
        "arquivo": Path(str(caminho)).name,
        "dur": round(dur, 2),
        "pico": round(float(db.max()), 1),
        "p50": round(energia.percentil(db, 0.50), 1),
        "p10_piso": round(energia.percentil(db, 0.10), 1),
        "p05_piso": round(energia.percentil(db, 0.05), 1),
        "janelas<-40dB": "%.0f%%" % (100.0 * len(silencio) / len(db)),
        "piso_medio_silencio": round(float(silencio.mean()), 1) if len(silencio) else None,
    }


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("uso: medir_audio.py ARQUIVO...", file=sys.stderr)
        return 2

    def fazer():
        linhas = [relatorio(c) for c in argv]
        chaves = list(linhas[0])
        print(" | ".join("%19s" % k for k in chaves))
        for linha in linhas:
            print(" | ".join("%19s" % linha[k] for k in chaves))
    return veredito.ferramenta(fazer)


if __name__ == "__main__":
    sys.exit(main())
