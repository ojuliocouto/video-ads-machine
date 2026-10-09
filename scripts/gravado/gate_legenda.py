"""Gate da LEGENDA: quanto tempo a peça fica SEM texto na tela e se alguma linha estoura.

Lê o ASS gerado (sem as tags de cor) e mede, contra a duração da peça:

  - fração da peça sem texto: reprova acima de 12% (o anúncio roda mudo no feed silencioso);
  - maior vão sem texto: reprova acima de 2,5 s;
  - linha mais longa: reprova acima de MAX_CHARS, o limite do próprio gerador de legenda (a caixinha
    come o topo e a UI do Reels come o rodapé, então a largura útil é curta).

Os 12% e os 2,5 s são os do gate de anúncio do motor (C6). O limite de linha sai de
`legendar.MAX_CHARS`: o gate fiscaliza o gerador.

    python3 scripts/gravado/gate_legenda.py LEGENDA.ass (--duracao S | --video MP4)
    python3 scripts/gravado/gate_legenda.py --projeto DIR [PECA ...]
Saída: 0 passou, 1 reprovou, 2 insumo inválido.
"""
import argparse
import re
import sys
from pathlib import Path

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado import legendar, montar, veredito  # noqa: E402
from gravado import projeto as gp  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402

NOME = "gate_legenda"
MAX_SEM_TEXTO_FRAC = 0.12
MAX_VAO_S = 2.5
MAX_CHARS = legendar.MAX_CHARS
VAO_MINIMO_RELATADO_S = 0.3


def _segundos(texto):
    h, m, s = texto.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def eventos_do_ass(texto):
    """[(início, fim, texto sem tags)] dos Dialogue do ASS, em ordem de início."""
    saida = []
    for linha in texto.splitlines():
        if not linha.startswith("Dialogue"):
            continue
        campos = linha.split(",", 9)
        if len(campos) < 10:
            raise InsumoInvalido("linha de legenda quebrada: %r" % linha[:80])
        try:
            saida.append((_segundos(campos[1]), _segundos(campos[2]), legendar.sem_tags(campos[9])))
        except ValueError:
            raise InsumoInvalido("tempo ilegível na legenda: %r" % linha[:80])
    return sorted(saida)


def medir(eventos, duracao_s):
    """{sem_texto_s, frac, maior_vao: (ini, fim), linhas, mais_longa}."""
    vazio, pos, maior = 0.0, 0.0, (0.0, 0.0)
    for a, b, _ in eventos:
        if a > pos:
            vazio += a - pos
            if a - pos > maior[1] - maior[0]:
                maior = (pos, a)
        pos = max(pos, b)
    if duracao_s > pos:
        vazio += duracao_s - pos
        if duracao_s - pos > maior[1] - maior[0]:
            maior = (pos, duracao_s)
    return {"sem_texto_s": vazio, "frac": vazio / duracao_s, "maior_vao": maior, "linhas": len(eventos),
            "mais_longa": max((len(t) for _, _, t in eventos), default=0)}


def verificar(ass, duracao_s, max_frac=MAX_SEM_TEXTO_FRAC, max_vao_s=MAX_VAO_S, max_chars=MAX_CHARS):
    veredito.exigir_arquivo(ass, "a legenda")
    if not duracao_s or duracao_s <= 0:
        raise InsumoInvalido("duração da peça inválida: %r" % (duracao_s,))
    eventos = eventos_do_ass(Path(str(ass)).read_text(encoding="utf-8"))
    if not eventos:
        raise InsumoInvalido("a legenda %s não tem nenhuma linha de diálogo" % Path(str(ass)).name)
    m = medir(eventos, duracao_s)
    problemas = []
    if m["frac"] > max_frac:
        problemas.append("%.0f%% da peça sem texto (teto %.0f%%)" % (100 * m["frac"], 100 * max_frac))
    a, b = m["maior_vao"]
    if b - a > max_vao_s:
        problemas.append("vão de %.1fs sem texto em %.1fs (teto %.1fs)" % (b - a, a, max_vao_s))
    if m["mais_longa"] > max_chars:
        problemas.append("linha de %d caracteres (máximo %d)" % (m["mais_longa"], max_chars))
    nome = Path(str(ass)).name
    if problemas:
        return False, "%s: %s" % (nome, "; ".join(problemas))
    maior = ("maior vão %.1fs" % (b - a)) if b - a > VAO_MINIMO_RELATADO_S else "sem vão"
    return True, "%s: %.0f%% sem texto, %s, %d linhas, a maior com %d caracteres" % (
        nome, 100 * m["frac"], maior, m["linhas"], m["mais_longa"])


def verificar_projeto(proj, leitor=None, pecas=None):
    nomes = list(pecas or proj.nomes_das_pecas())
    if not nomes:
        raise InsumoInvalido("o plano não tem anúncios para conferir")
    resultados = []
    for n in nomes:
        video = veredito.exigir_arquivo(proj.legendado(n), "a peça legendada")
        resultados.append(verificar(proj.legenda_ass(n), montar.duracao(video)))
    return veredito.juntar(resultados)


def _parser():
    ap = argparse.ArgumentParser(prog=NOME, description="Tempo sem texto e largura das linhas da legenda.")
    ap.add_argument("ass", nargs="?", help="arquivo .ass (sem isso, usa o projeto)")
    ap.add_argument("--duracao", type=float, help="duração da peça em segundos")
    ap.add_argument("--video", help="vídeo de onde ler a duração")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    ap.add_argument("--pecas", nargs="*", help="nomes das peças do projeto, como A1_normal (padrão: todas)")
    return ap


def _verificar(args):
    if args.ass:
        if args.duracao is None and not args.video:
            raise InsumoInvalido("passe --duracao SEGUNDOS ou --video ARQUIVO para saber a duração da peça")
        duracao = args.duracao if args.duracao is not None else montar.duracao(veredito.exigir_arquivo(args.video, "o vídeo"))
        return verificar(args.ass, duracao)
    return verificar_projeto(gp.carregar(args.projeto), pecas=args.pecas or None)


def main(argv=None):
    return veredito.cli(NOME, _parser(), _verificar, argv)


if __name__ == "__main__":
    sys.exit(main())
