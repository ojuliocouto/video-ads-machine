"""Gate de REPETIÇÃO: n-grama que aparece duas vezes PERTO um do outro na peça entregue.

É o defeito clássico de costura de take com retomada: a frase dita duas vezes e as duas ficaram.
Um n-grama de 5 palavras repetido a até 40 palavras de distância (a costura), não no anúncio
inteiro. Lê o `falas_entregues.json`; JSON vazio, ilegível ou com `FALHA` do ASR sai com 2.

    python3 scripts/gravado/gate_repeticao.py [FALAS.json] [--projeto DIR]
Saída: 0 sem repetição, 1 achou, 2 insumo inválido.
"""
import argparse
import re
import sys
import unicodedata
from pathlib import Path

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado import projeto as gp  # noqa: E402
from gravado import veredito  # noqa: E402
from gravado.nucleo import asr  # noqa: E402

NOME = "gate_repeticao"
N = 5            # tamanho do n-grama
JANELA = 40      # só acusa se a repetição estiver perto (a costura), não no anúncio inteiro


def palavras(texto):
    t = unicodedata.normalize("NFD", texto.lower())
    return re.findall(r"[a-z0-9]+", "".join(c for c in t if unicodedata.category(c) != "Mn"))


def repeticoes(texto, n=N, janela=JANELA):
    """[(n-grama, posição da 1ª vez, posição da 2ª)], com os n-gramas sobrepostos do mesmo trecho
    colapsados numa ocorrência só."""
    ws = palavras(texto)
    vistos, achadas = {}, []
    for i in range(len(ws) - n + 1):
        g = tuple(ws[i:i + n])
        if g in vistos and i - vistos[g] <= janela:
            achadas.append((" ".join(g), vistos[g], i))
        vistos[g] = i
    limpas, ultimo = [], -99
    for g, a, b in achadas:
        if a - ultimo > n:
            limpas.append((g, a, b))
        ultimo = a
    return limpas


def verificar(falas, n=N, janela=JANELA):
    """(ok, motivo). `falas`: {peça: texto}."""
    linhas = []
    for peca in sorted(falas):
        for g, a, b in repeticoes(falas[peca], n, janela):
            linhas.append('%s: repetiu "%s" (palavra %d e %d)' % (peca, g, a, b))
    if linhas:
        return False, "%d repetição(ões) de costura:\n  %s" % (len(linhas), "\n  ".join(linhas))
    return True, "nenhuma repetição de costura nas %d peça(s)" % len(falas)


def verificar_projeto(proj, leitor=None, pecas=None):
    falas = asr.carregar_falas(proj.falas_json)
    if pecas:
        falas = {k: v for k, v in falas.items() if k in pecas}
    return verificar(falas)


def _parser():
    ap = argparse.ArgumentParser(prog=NOME, description="Acha n-grama repetido perto na peça entregue.")
    ap.add_argument("falas", nargs="?", help="falas_entregues.json (padrão: o do projeto)")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    return ap


def _verificar(args):
    caminho = Path(args.falas) if args.falas else gp.resolver_base(args.projeto) / "falas_entregues.json"
    return verificar(asr.carregar_falas(caminho))


def main(argv=None):
    return veredito.cli(NOME, _parser(), _verificar, argv)


if __name__ == "__main__":
    sys.exit(main())
