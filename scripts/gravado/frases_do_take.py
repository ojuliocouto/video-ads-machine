"""FASE 2: ler o take. A transcrição inteira e, depois, frase a frase.

  - `transcrever_brutos`: o texto de cada bruto, para ler o que tem em cada take antes do plano
    (`transcricoes/<take>.json`). Lê o wav extraído.
  - `frases`: quebra o áudio higienizado em FRASES por energia (separador de 0,38 s, a unidade do
    plano) e lê cada uma. A borda de cada frase é medida na energia, não no tempo do ASR: o
    word-level infla o token neste material. O ASR só lê o que está DENTRO da borda.

A retomada de pausa curta (0,32 s) não aparece aqui: o primeiro passe funde. É o gate de retomada,
com o segundo passe de 0,14 s, que a pega.

    python3 scripts/gravado/frases_do_take.py TAKE... [--projeto DIR]     frases de cada take
    python3 scripts/gravado/frases_do_take.py --brutos [--projeto DIR]    transcrição de cada bruto
"""
import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado import projeto as gp  # noqa: E402
from gravado import veredito  # noqa: E402
from gravado.nucleo import segmentos  # noqa: E402
from projeto import status as _status  # noqa: E402


def frases(proj, take, leitor):
    """[(início, fim, texto)] de cada frase do take higienizado."""
    audio = veredito.exigir_arquivo(proj.limpo(take), "o áudio limpo do take %s (rode o isolar)" % take)
    return [(a, b, leitor.texto(audio, a, b)) for a, b in segmentos.frases(audio)]


def transcrever_brutos(proj, leitor, takes=None):
    """{take: texto} do wav de cada bruto; grava `transcricoes/<take>.json`."""
    pasta = proj.garantir("transcricoes")
    saida = {}
    for bruto in proj.takes_brutos():
        if takes and bruto.stem not in set(takes):
            continue
        wav = veredito.exigir_arquivo(proj.wav(bruto.stem), "o wav do bruto %s (rode o extrair_wav)" % bruto.stem)
        texto = leitor.texto_da_peca(wav)
        _status.escrever_json_atomico(pasta / (bruto.stem + ".json"), {"take": bruto.stem, "text": texto})
        saida[bruto.stem] = texto
    return saida


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lê os takes: transcrição inteira e frase a frase.")
    ap.add_argument("takes", nargs="*")
    ap.add_argument("--brutos", action="store_true", help="transcreve os brutos inteiros")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    a = ap.parse_args(argv)

    def fazer():
        proj = gp.carregar(a.projeto)
        leitor = proj.leitor()
        if a.brutos:
            for take, texto in transcrever_brutos(proj, leitor, a.takes or None).items():
                print("\n%s\n%s\n  %s" % ("=" * 78, take, texto))
            return
        if not a.takes:
            raise veredito.InsumoInvalido("passe os takes, como IMG_0001, ou --brutos")
        for take in a.takes:
            print("\n%s\n%s\n%s" % ("=" * 78, take, "=" * 78))
            for ini, fim, texto in frases(proj, take, leitor):
                print("  [%6.2f > %6.2f] %s" % (ini, fim, texto))
    return veredito.ferramenta(fazer)


if __name__ == "__main__":
    sys.exit(main())
