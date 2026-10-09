"""`vam entregar <slug>`: libera a entrega só com o gate_entrega PASS, e monta o pacote em entrega/.

O gate_entrega exige o laudo PASS, a aprovação do plano vigente e a nota do auditor de 8 ou mais, os três amarrados
ao sha256 do arquivo final. Bloqueado: nada é montado, o motivo vai para o status.json e a saída é 1. Liberado:
entrega/entrega.json guarda o sha256 do final, da prévia, do laudo, da nota e das folhas de contato.

A entrega do produto é a pasta entrega/ (Drive e WhatsApp são decisão do aluno). --abrir mostra a pasta.
"""
import argparse
import sys

from cli import _comum as C

NOME = "entregar"


def registrar(subparsers):
    p = subparsers.add_parser(NOME, help="libera a entrega (laudo PASS, aprovação vigente, nota 8+, mesmo sha256)",
                              description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("slug")
    p.add_argument("--abrir", action="store_true", help="mostra a pasta entrega/ depois de montar o pacote")
    C.opcao_estado(p)
    p.set_defaults(func=executar)
    return p


def _executar(args):
    from entrega import pacote
    from gates import gate_entrega
    from projeto import status
    pj, projeto = C.projeto_existente(args)
    C.exigir_modo(pj, projeto, "avatar", NOME)
    g = gate_entrega.rodar(pj)
    if g["resultado"] != "PASS":
        status.registrar(pj, NOME, "falhou" if g["saida"] == 1 else "bloqueado", motivo=g["motivo"][:600])
        C.erro(NOME, "ENTREGA BLOQUEADA: %s" % g["motivo"])
        return g["saida"] or C.SAIDA_DEFEITO
    m = pacote.montar(pj, g)
    status.registrar(pj, NOME, "ok", detalhes={"sha256": m["final"]["sha256"], "nota": m["nota"]["nota"]})
    print("ENTREGUE: %s" % pj.final_9x16)
    print("  sha256 %s | nota %s | laudo %s" % (m["final"]["sha256"], str(m["nota"]["nota"]).replace(".", ","),
                                               m["laudo"]["veredito"]))
    if m["previa"]:
        print("  prévia %s" % pj.final_whatsapp)
    print("  manifesto %s" % pacote.manifesto(pj))
    if args.abrir:
        pacote.abrir(pj.entrega_dir)
    return C.SAIDA_OK


def executar(args):
    return C.rodar(NOME, _executar, args)
