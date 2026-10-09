"""`vam aprovar <slug> --ok "<o ok do aluno>"`: o ok ao plano, amarrado por sha256 ao que foi aprovado.

Só depois do ok do aluno NO CHAT, com o texto que ele escreveu. A aprovação amarra roteiro.md, projeto.json,
plano/plano.json e render/inserts.json: mudar 1 byte de qualquer um vence a aprovação e o `vam montar` recusa. Recusa
plano sem as 6 seções, com pendência muda na checklist, medido de outra versão do roteiro, ou cujo plano_edicao.md não
é o do plano.json (o aluno tem que ter lido ESTE plano). Saída 1 se recusada (o motivo vai para o status.json).
"""
import argparse

from cli import _comum as C

NOME = "aprovar"


def registrar(subparsers):
    p = subparsers.add_parser(NOME, help="registra o ok do aluno ao plano (amarrado por sha256)",
                              description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("slug")
    p.add_argument("--ok", required=True, help="o texto do ok, como o aluno escreveu no chat")
    C.opcao_estado(p)
    p.set_defaults(func=executar)
    return p


def _executar(args):
    from plano import aprovacao
    pj, _projeto = C.projeto_existente(args)
    return aprovacao.main([pj.slug, "--estado", str(pj.estado), "--ok", args.ok])


def executar(args):
    return C.rodar(NOME, _executar, args)
