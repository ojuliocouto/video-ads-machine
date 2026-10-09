"""`vam plano <slug>`: o plano de edição MEDIDO (plano/plano.json) e o texto que o aluno lê (plano/plano_edicao.md).

    vam plano <slug> [--sugestoes sugestoes.json] [--prancha]

Mede da voz limpa e do roteiro: blocos, mapa de inserts (tamanho, orientação, congelamento previsto), hook,
letterings, densidade de insert, efeitos, referências, ritmo previsto no arquivo entregue e a checklist do padrão de
edição. Nada disso se declara: o diretor só acrescenta referências e propostas (--sugestoes). Com --prancha, monta a
prancha de direção (o anúncio em quadro parado, ANTES do render) em plano/prancha/.

Depois: mostre o plano_edicao.md ao aluno; com o ok dele no chat, `vam aprovar <slug> --ok "<o ok>"`.
"""
import argparse
import subprocess
import sys

from cli import _comum as C

NOME = "plano"


def registrar(subparsers):
    p = subparsers.add_parser(NOME, help="mede o plano de edição (e a prancha de direção, com --prancha)",
                              description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("slug")
    p.add_argument("--sugestoes", help="json com referências e propostas do diretor")
    p.add_argument("--palavras", help=argparse.SUPPRESS)
    p.add_argument("--prancha", action="store_true", help="monta a prancha de direção em plano/prancha/")
    C.opcao_estado(p)
    p.set_defaults(func=executar)
    return p


def _executar(args):
    from plano import medir
    pj, _projeto = C.projeto_existente(args)
    argv = ["--projeto", str(pj.raiz)]
    if args.sugestoes:
        argv += ["--sugestoes", args.sugestoes]
    if args.palavras:
        argv += ["--palavras", args.palavras]
    codigo = medir.main(argv)
    if codigo != 0 or not args.prancha:
        if codigo == 0:
            print("próximo: mostre %s ao aluno; com o ok dele: vam aprovar %s --ok \"<o ok>\"" % (pj.plano_md, pj.slug))
        return codigo
    from caminhos import CODIGO
    import build_composite as BC
    r = subprocess.run([sys.executable, str(CODIGO / "prancha_direcao.py"), pj.slug, "--estado", str(pj.estado)],
                       env=BC.Motor(pj).env_motor())
    return C.SAIDA_OK if r.returncode == 0 else C.SAIDA_USO


def executar(args):
    return C.rodar(NOME, _executar, args)
