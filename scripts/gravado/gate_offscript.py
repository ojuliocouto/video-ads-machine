"""Gate de FALA FORA DO ROTEIRO: pergunta a quem dirige, hesitação, palavrão na peça entregue.

Casa por EXPRESSÃO INTEIRA e mostra o contexto: substring solta casa "pera" dentro de "operação".
O texto de cada peça vem do `falas_entregues.json` (gerado pelo auditar a partir do arquivo
entregue). Se esse JSON está vazio, ilegível ou traz `FALHA` do ASR em qualquer peça, o gate sai
com 2: não leu a fala, não pode aprovar nem reprovar.

    python3 scripts/gravado/gate_offscript.py [FALAS.json] [--projeto DIR]
Saída: 0 nenhuma fala de fora, 1 achou, 2 insumo inválido.
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

NOME = "gate_offscript"
CONTEXTO = 45
# Expressões inteiras, não pedaços de palavra. Direção de quem grava, hesitação e palavrão.
PADROES = [
    r"\bé isso\b", r"\bé isso\?", r"\btá bom\b", r"\bta bom\b", r"\bde novo\?",
    r"\bo que (é que )?(eu )?tenho que falar\b", r"\btem que falar\b",
    r"\bera qual( mesmo)?\b", r"\bcomo (é|e) que (é|e)\b", r"\bjá gravando\b",
    r"\bpode (falar|começar)\b", r"\bespera a[íi]\b", r"\bdeixa eu\b",
    r"\bporra\b", r"\bcaralho\b", r"\bmerda\b", r"\bputa que pariu\b", r"\bputz\b",
    r"\bcorta\b", r"\bde novo tudo\b", r"\btudo de novo\b",
]


def _normalizar(texto):
    """(texto sem acento e em minúsculas, mapa de cada caractere para o índice no original)."""
    saida, mapa = [], []
    for i, c in enumerate(texto):
        for d in unicodedata.normalize("NFD", c.lower()):
            if unicodedata.category(d) != "Mn":
                saida.append(d)
                mapa.append(i)
    return "".join(saida), mapa


def achados(texto, padroes=PADROES):
    """[(contexto, trecho dito)] com o texto ORIGINAL, achados em cima do texto sem acento."""
    norm, mapa = _normalizar(texto)
    saida = []
    for p in padroes:
        for m in re.finditer(_normalizar(p)[0], norm):
            if m.end() == m.start():
                continue
            ini, fim = mapa[m.start()], mapa[m.end() - 1] + 1
            saida.append((texto[max(0, ini - CONTEXTO):min(len(texto), fim + CONTEXTO)], texto[ini:fim]))
    return saida


def verificar(falas, padroes=PADROES):
    """(ok, motivo). `falas`: {peça: texto}."""
    linhas, total = [], 0
    for peca in sorted(falas):
        for contexto, trecho in achados(falas[peca], padroes):
            total += 1
            linhas.append('%s: "%s" em ...%s...' % (peca, trecho, contexto))
    if total:
        return False, "%d ocorrência(s) de fala fora do roteiro:\n  %s" % (total, "\n  ".join(linhas))
    return True, "nenhuma fala fora do roteiro em %d peça(s)" % len(falas)


def verificar_projeto(proj, leitor=None, pecas=None):
    falas = asr.carregar_falas(proj.falas_json)
    if pecas:
        falas = {k: v for k, v in falas.items() if k in pecas}
    return verificar(falas)


def _parser():
    ap = argparse.ArgumentParser(prog=NOME, description="Acha fala que não é do anúncio na peça entregue.")
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
