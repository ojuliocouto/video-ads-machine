"""Gate de REDUNDÂNCIA NA EMENDA: o que vem ANTES da costura repete a IDEIA do que vem DEPOIS?

Diferente do gate de retomada. Retomada é defeito do expert (errou e repetiu na gravação).
Redundância é defeito da MONTAGEM: dois trechos que, cada um limpo, dizem a mesma coisa quando
colados. Aconteceu quando o corpo terminava nomeando o produto e o CTA abria nomeando o produto
de novo, em 4 segundos.

Mede pela interseção de TERMOS PORTADORES (palavra de 5 letras ou mais que não seja da lista de
funcionais) nos 6 s antes e nos 6 s depois da costura: dois ou mais em comum é redundância. O mesmo
take de CTA serve vários anúncios, mas o ponto de ENTRADA não é o mesmo em todos: depende do que
o corpo daquele anúncio acabou de dizer.

    python3 scripts/gravado/gate_redundancia.py [PECA ...] [--projeto DIR]
Saída: 0 passou, 1 achou redundância, 2 insumo inválido (ASR falhou).
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

NOME = "gate_redundancia"
JANELA_S = 6.0
MIN_EM_COMUM = 2
# Já sem acento: o texto é normalizado antes da comparação.
FUNCIONAIS = frozenset({
    "voce", "voces", "para", "porque", "quando", "aqui", "tambem", "muito", "mais", "isso", "esse",
    "essa", "aquilo", "entao", "depois", "agora", "assim", "onde", "como", "ainda", "nesse", "dessa",
    "desse", "minha", "meus", "seus", "suas", "tudo", "todo", "toda", "fazer", "dizer", "gente",
    "coisa", "sobre", "entre", "cada", "pode", "vamos"})


def termos(texto):
    """Os termos portadores do texto: palavras longas que não são funcionais."""
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return {w for w in re.findall(r"[a-z]{5,}", t) if w not in FUNCIONAIS}


def ler_lados(arquivo, emendas, leitor, janela_s=JANELA_S):
    """[(emenda, texto de `janela_s` antes, texto de `janela_s` depois)] pelo leitor de ASR."""
    pares = []
    for p in emendas:
        antes = leitor.texto(arquivo, max(0.0, p - janela_s), p)
        depois = leitor.texto(arquivo, p, p + janela_s)
        pares.append((p, antes, depois))
    return pares


def verificar(pares):
    """(ok, motivo). `pares`: [(rótulo da peça, instante da emenda, texto antes, texto depois)]."""
    achados = []
    for rotulo, t, antes, depois in pares:
        comum = termos(antes) & termos(depois)
        if len(comum) >= MIN_EM_COMUM:
            achados.append("%s emenda %.2fs: termos repetidos: %s\n    antes : ...%s\n    depois: %s..."
                           % (rotulo, t, ", ".join(sorted(comum)), antes[-90:], depois[:90]))
    if achados:
        return False, "%d emenda(s) com a mesma ideia dos dois lados:\n  %s" % (len(achados), "\n  ".join(achados))
    return True, "nenhuma redundância em %d emenda(s)" % len(pares)


def verificar_projeto(proj, leitor=None, pecas=None):
    nomes = list(pecas or proj.nomes_das_pecas())
    if not nomes:
        raise InsumoInvalido("o plano não tem anúncios para conferir")
    versoes = proj.versoes()
    leitor = leitor or proj.leitor()
    pares = []
    for nome in nomes:
        if nome not in versoes:
            raise InsumoInvalido("a peça %s não está no plano (tem: %s)" % (nome, ", ".join(versoes)))
        cod, desconto = versoes[nome]
        pontos = montar.emendas(montar.segmentos_do_ad(proj, cod, desconto), proj.accel)
        arquivo = veredito.exigir_arquivo(proj.montado(nome), "a peça montada")
        pares += [(nome, t, a, d) for t, a, d in ler_lados(arquivo, pontos, leitor)]
    return verificar(pares)


def _parser():
    ap = argparse.ArgumentParser(prog=NOME, description="A ideia antes da emenda se repete depois?")
    ap.add_argument("pecas", nargs="*", help="nomes das peças, como A1_normal (padrão: todas do plano)")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    return ap


def _verificar(args):
    return verificar_projeto(gp.carregar(args.projeto), pecas=args.pecas or None)


def main(argv=None):
    return veredito.cli(NOME, _parser(), _verificar, argv)


if __name__ == "__main__":
    sys.exit(main())
