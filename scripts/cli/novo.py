"""`vam novo <slug>`: cria o projeto do aluno em _local/projetos/<slug> (pastas, projeto.json e status.json).

    vam novo <slug> --look <look> (--trilha <arquivo> | --sem-trilha "motivo") [--origem chat|arquivo]

O modo avatar (o deste comando) precisa do look do HeyGen: o nome dele em `_local/looks.json` (o `vam avatar` cadastra).
A trilha é um arquivo do aluno em `_local/trilhas/`, ou o motivo escrito de rodar sem trilha: o repo não embarca
música. Idempotente: rodar de novo com o mesmo pedido não muda nada; pedido diferente não toca no projeto (saída 2).
Take de câmera tem o comando dele: `vam gravado <slug> criar` e `vam oneshot <slug> ...`.
"""
import argparse

from cli import _comum as C

NOME = "novo"


def registrar(subparsers):
    p = subparsers.add_parser(NOME, help="cria o projeto do anúncio (modo avatar)",
                              description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("slug", help="nome do projeto: minúsculas, dígitos, - e _")
    p.add_argument("--look", help="o look do HeyGen (nome em _local/looks.json)")
    p.add_argument("--trilha", help="arquivo de trilha em _local/trilhas/ (só o nome)")
    p.add_argument("--sem-trilha", dest="sem_trilha", metavar="MOTIVO", help="motivo escrito de rodar sem trilha")
    p.add_argument("--origem", choices=("chat", "arquivo"), help="de onde vem o roteiro (Doc: vam roteiro --doc)")
    C.opcao_estado(p)
    p.set_defaults(func=executar)
    return p


def _executar(args):
    import init_local
    from projeto import modelo, novo
    if not args.look:
        raise C.PedidoInvalido("o modo avatar precisa do look do HeyGen: --look <nome do look em _local/looks.json> "
                               "(o vam avatar cadastra o look com --avatar-id)")
    if bool(args.trilha) == bool(args.sem_trilha):
        raise C.PedidoInvalido("diga a trilha (--trilha arquivo.mp3, em _local/trilhas/) ou o motivo de rodar sem ela "
                               "(--sem-trilha \"motivo\"): uma das duas, não as duas")
    estado = C.estado(args)
    init_local.criar(estado)                       # o _local do aluno com a estrutura (nada é sobrescrito)
    origem = {"tipo": args.origem} if args.origem else None
    try:
        r = novo.criar(args.slug, "avatar", look=args.look, trilha=args.trilha, sem_trilha=args.sem_trilha,
                       origem=origem, estado=estado)
    except novo.ProjetoJaExiste as e:
        raise C.PedidoInvalido(str(e))
    except modelo.ContratoInvalido as e:
        raise C.PedidoInvalido(str(e))
    except ValueError as e:
        raise C.PedidoInvalido(str(e))
    print("projeto %s %s em %s" % (args.slug, "criado" if r.criado else "já existia", r.pastas.raiz))
    print("  modo avatar | look %s | aceleração %sx | %s" % (r.projeto["look"], r.projeto["aceleracao"],
          "trilha " + r.projeto["trilha"]["arquivo"] if "arquivo" in r.projeto["trilha"] else "sem trilha"))
    for aviso in r.avisos:
        print("AVISO: %s" % aviso)
    print("próximo: vam roteiro %s --de roteiro.md   (convenção em contratos/roteiro-convencao.md)" % args.slug)
    return C.SAIDA_OK


def executar(args):
    return C.rodar(NOME, _executar, args)
