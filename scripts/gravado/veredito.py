"""Protocolo de saída dos gates do gravado.

  0  o gate passou
  1  defeito MEDIDO na peça
  2  insumo inválido: não deu para medir (arquivo ausente, JSON vazio, ASR que falhou, plano
     quebrado, erro inesperado). Nunca é veredito: um gate que não mediu não aprova nem reprova.

Por que erro inesperado sai com 2: o Python devolve 1 numa exceção não tratada, e esse 1 seria
lido como "a peça tem defeito". Aqui o 1 só existe quando o gate mediu e reprovou.

Cada gate expõe uma função que devolve `(ok, motivo)` e levanta `InsumoInvalido` quando não
consegue medir; `cli()` traduz isso em código de saída e em texto.
"""
import sys

SAIDA_OK = 0
SAIDA_DEFEITO = 1
SAIDA_INSUMO = 2


class InsumoInvalido(Exception):
    """Não deu para MEDIR. A mensagem diz o que falta e como conseguir (um comando, uma linha)."""


def exigir_arquivo(caminho, o_que="o arquivo"):
    """Levanta InsumoInvalido se `caminho` não é um arquivo. Devolve o caminho."""
    if not caminho or not _eh_arquivo(caminho):
        raise InsumoInvalido("não achei %s: %s" % (o_que, caminho))
    return caminho


def _eh_arquivo(caminho):
    from pathlib import Path
    return Path(str(caminho)).is_file()


def cli(nome, parser, verificar, argv=None):
    """Roda `verificar(args) -> (ok, motivo)` e devolve o código de saída (0, 1 ou 2).

    `verificar` pode levantar InsumoInvalido; qualquer outra exceção também vira 2, com o nome
    do erro, e não 1.
    """
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:            # argparse: --help sai 0, argumento ruim sai 2
        return e.code if isinstance(e.code, int) else SAIDA_INSUMO
    try:
        ok, motivo = verificar(args)
    except InsumoInvalido as e:
        print("INSUMO INVÁLIDO %s: %s" % (nome, e), file=sys.stderr)
        return SAIDA_INSUMO
    except Exception as e:             # bug nosso ou ambiente quebrado: nunca confundir com defeito
        print("ERRO INESPERADO %s: %s: %s" % (nome, type(e).__name__, e), file=sys.stderr)
        return SAIDA_INSUMO
    print("%s %s: %s" % ("APROVADO" if ok else "REPROVADO", nome, motivo))
    return SAIDA_OK if ok else SAIDA_DEFEITO


def ferramenta(fazer):
    """Roda a ferramenta `fazer()` (extrair, isolar, montar...) e devolve 0; se ela levantar
    InsumoInvalido (ou o erro do ffmpeg, que também é "não deu para fazer"), imprime e devolve 2."""
    try:
        fazer()
    except InsumoInvalido as e:
        print(str(e), file=sys.stderr)
        return SAIDA_INSUMO
    return SAIDA_OK


def juntar(resultados):
    """Junta vários `(ok, motivo)` num só: ok se todos ok; o motivo lista um por linha."""
    resultados = list(resultados)
    ok = all(r[0] for r in resultados)
    return ok, "\n".join(r[1] for r in resultados)
