"""Gate de AR MORTO: mede as pausas dentro da peça ENTREGUE, que é onde o espectador ouve.

Roda no arquivo final (não no take). O teto sai do passo que o gate fiscaliza, o cortador:

    teto = RESPIRO + 2 x MARGEM + 1 quadro      (ar_morto_energia.PAUSA_RESIDUAL + 1/FPS)

É a maior pausa que o cortador deixa quando corta (0,42 s) mais um quadro de folga: o cortador
passa sem falso positivo, e uma pausa de 0,9 s é acusada. A pausa do arquivo acelerado volta ao
tempo de FONTE (`x accel`) antes de comparar, porque o cortador trabalha na fonte.

Pausa entre o teto e o que o cortador deixa intacto (até MINIMO + 2 x MARGEM = 0,69 s) é pausa
natural DENTRO de um trecho: o cortador não mexe, então o conserto é do plano, não do cortador.
Dividir o trecho nessa pausa (uma frase por trecho) joga fora o vão.

    python3 scripts/gravado/gate_ar_morto.py ARQUIVO... [--accel 1.2]
    python3 scripts/gravado/gate_ar_morto.py --projeto DIR [PECA ...]
Saída: 0 passou, 1 pausa acima do teto, 2 insumo inválido.
"""
import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado import ar_morto_energia, montar, veredito  # noqa: E402
from gravado import projeto as gp  # noqa: E402
from gravado.nucleo import energia, segmentos  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402

NOME = "gate_ar_morto"
FPS = montar.FPS


def teto_s(fps=FPS):
    """O teto da pausa, em segundos de FONTE."""
    return ar_morto_energia.PAUSA_RESIDUAL + 1.0 / fps


def pausas_acima_do_teto(caminho, accel=1.0, fps=FPS):
    """([(início, duração no arquivo, duração na fonte)], duração do arquivo)."""
    db, dur = energia.curva(caminho, jan=ar_morto_energia.JAN)
    sils = segmentos.silencios(db, ar_morto_energia.JAN, percentil_q=ar_morto_energia.PERCENTIL,
                               queda_db=ar_morto_energia.QUEDA)
    teto = teto_s(fps)
    return [(a, b - a, (b - a) * accel) for a, b in sils if (b - a) * accel > teto + 1e-9], dur


def verificar(caminho, accel=1.0, fps=FPS):
    """(ok, motivo) de UMA peça."""
    veredito.exigir_arquivo(caminho, "a peça")
    ruins, dur = pausas_acima_do_teto(caminho, accel, fps)
    nome = Path(str(caminho)).name
    if not ruins:
        return True, "%s: nenhuma pausa acima de %.2fs (tempo de fonte), %.1fs de peça" % (nome, teto_s(fps), dur)
    partes = ["pausa de %.2fs em %.2fs" % (d, a) + (" (%.2fs na fonte)" % f if accel != 1.0 else "")
              for a, d, f in sorted(ruins, key=lambda x: -x[1])[:4]]
    return False, ("%s: ar morto: %s; teto %.2fs. Divida o trecho nessa pausa (uma frase por trecho) "
                   "ou deixe o cortador agir (ele corta acima de %.2fs)."
                   % (nome, ", ".join(partes), teto_s(fps),
                      ar_morto_energia.MINIMO + 2 * ar_morto_energia.MARGEM))


def verificar_projeto(proj, leitor=None, pecas=None):
    nomes = list(pecas or proj.nomes_das_pecas())
    if not nomes:
        raise InsumoInvalido("o plano não tem anúncios para conferir")
    return veredito.juntar(verificar(proj.montado(n), proj.accel) for n in nomes)


def _parser():
    ap = argparse.ArgumentParser(prog=NOME, description="Mede o ar morto dentro da peça entregue.")
    ap.add_argument("alvos", nargs="*", help="arquivos de vídeo/áudio (sem isso, usa o projeto)")
    ap.add_argument("--accel", type=float, default=None, help="aceleração da peça (padrão: 1.0 em arquivo, a do projeto)")
    ap.add_argument("--fps", type=int, default=FPS)
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    ap.add_argument("--pecas", nargs="*", help="nomes das peças do projeto, como A1_normal (padrão: todas)")
    return ap


def _verificar(args):
    if args.alvos:
        accel = args.accel if args.accel is not None else 1.0
        return veredito.juntar(verificar(a, accel, args.fps) for a in args.alvos)
    proj = gp.carregar(args.projeto)
    proj.accel_forcada = args.accel
    return verificar_projeto(proj, pecas=args.pecas or None)


def main(argv=None):
    return veredito.cli(NOME, _parser(), _verificar, argv)


if __name__ == "__main__":
    sys.exit(main())
