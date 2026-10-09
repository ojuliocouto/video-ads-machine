"""Gate das EMENDAS: confere cada costura da peça montada, com tempo de palavra real.

A emenda é onde aparece a sobra: meia palavra da frase descartada colada no começo ou no fim do
trecho. Ouvir a peça inteira não pega (o ASR lê por cima) e ouvir o sub-bloco isolado também
não (ele completa o que falta); o tempo de palavra do transcritor local pega:

  - uma palavra que ATRAVESSA a emenda (começa antes e termina depois, com folga de TOL_S nas
    duas pontas) é uma palavra cortada ao meio;
  - a mesma palavra de um lado e do outro, colada, é o resto de uma retomada.

A folga de TOL_S (0,08 s) é a resolução do tempo de palavra do parakeet. A Groq não serve aqui:
infla o token. O leitor recusa e diz como instalar um transcritor local.

    python3 scripts/gravado/gate_emendas.py [PECA ...] [--projeto DIR]
Saída: 0 passou, 1 emenda ruim, 2 insumo inválido.
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

from gravado import montar, veredito  # noqa: E402
from gravado import projeto as gp  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402

NOME = "gate_emendas"
TOL_S = 0.08
CONTEXTO_S = 2.8
REPETIDA_GAP_S = 0.5


def _norm(texto):
    t = unicodedata.normalize("NFD", str(texto).lower())
    return "".join(re.findall(r"[a-z0-9]+", "".join(c for c in t if unicodedata.category(c) != "Mn")))


def _contexto(t, palavras, contexto_s):
    antes = " ".join(w["text"] for w in palavras if t - contexto_s <= w["end"] <= t + TOL_S)
    depois = " ".join(w["text"] for w in palavras if t - TOL_S <= w["start"] <= t + contexto_s)
    return "%s | %s" % (antes[-60:], depois[:60])


def verificar(emendas, palavras, tol_s=TOL_S, contexto_s=CONTEXTO_S):
    """(ok, motivo). `emendas`: instantes (s) das costuras na peça final. `palavras`: as palavras
    com tempo da peça final."""
    if not emendas:
        return True, "nenhuma emenda para conferir"
    if not palavras:
        raise InsumoInvalido("o ASR não devolveu nenhuma palavra da peça: não dá para conferir as emendas")
    problemas = []
    for t in emendas:
        cortadas = [w for w in palavras if w["start"] + tol_s < t < w["end"] - tol_s]
        if cortadas:
            w = cortadas[0]
            problemas.append("emenda em %.2fs corta a palavra %r (%.2f a %.2fs)  [%s]"
                             % (t, w["text"], w["start"], w["end"], _contexto(t, palavras, contexto_s)))
            continue
        antes = [w for w in palavras if w["end"] <= t + tol_s]
        depois = [w for w in palavras if w["start"] >= t - tol_s]
        if antes and depois:
            a, b = antes[-1], depois[0]
            igual = _norm(a["text"]) == _norm(b["text"]) and len(_norm(a["text"])) >= 2
            if a is not b and igual and b["start"] - a["end"] < REPETIDA_GAP_S:
                problemas.append("emenda em %.2fs: palavra repetida colada (%r e %r)  [%s]"
                                 % (t, a["text"], b["text"], _contexto(t, palavras, contexto_s)))
    if problemas:
        return False, "%d emenda(s) com defeito de %d:\n  %s" % (len(problemas), len(emendas), "\n  ".join(problemas))
    return True, "%d emenda(s) sem palavra cortada nem repetida" % len(emendas)


def verificar_projeto(proj, leitor=None, pecas=None):
    nomes = list(pecas or proj.nomes_das_pecas())
    if not nomes:
        raise InsumoInvalido("o plano não tem anúncios para conferir")
    versoes = proj.versoes()
    leitor = leitor or proj.leitor()
    resultados = []
    for nome in nomes:
        if nome not in versoes:
            raise InsumoInvalido("a peça %s não está no plano (tem: %s)" % (nome, ", ".join(versoes)))
        cod, desconto = versoes[nome]
        pontos = montar.emendas(montar.segmentos_do_ad(proj, cod, desconto), proj.accel)
        arquivo = veredito.exigir_arquivo(proj.montado(nome), "a peça montada")
        palavras = leitor.palavras(arquivo, exigir_borda=True) if pontos else []
        ok, motivo = verificar(pontos, palavras)
        resultados.append((ok, "%s: %s" % (nome, motivo)))
    return veredito.juntar(resultados)


def _parser():
    ap = argparse.ArgumentParser(prog=NOME, description="Confere cada costura da peça montada.")
    ap.add_argument("pecas", nargs="*", help="nomes das peças, como A1_normal (padrão: todas do plano)")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    return ap


def _verificar(args):
    return verificar_projeto(gp.carregar(args.projeto), pecas=args.pecas or None)


def main(argv=None):
    return veredito.cli(NOME, _parser(), _verificar, argv)


if __name__ == "__main__":
    sys.exit(main())
