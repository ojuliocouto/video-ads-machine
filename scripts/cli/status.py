"""`vam status [<slug>]`: onde cada projeto parou e qual é o próximo passo.

    vam status              todos os projetos, uma linha cada (a etapa atual e o estado)
    vam status <slug>       o projeto: a etapa atual com o motivo, as últimas etapas, os arquivos e o próximo comando

"Está pronto?" é uma leitura do status.json do projeto, nunca memória.
"""
import argparse

from cli import _comum as C

NOME = "status"
ULTIMAS = 12


def registrar(subparsers):
    p = subparsers.add_parser(NOME, help="onde cada projeto parou e o próximo passo",
                              description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("slug", nargs="?", help="o projeto (sem ele: todos)")
    C.opcao_estado(p)
    p.set_defaults(func=executar)
    return p


def proximo_passo(pj):
    """O próximo comando, lido dos arquivos do projeto (nunca de memória)."""
    s = pj.slug
    if not pj.roteiro.is_file():
        return "vam roteiro %s --de roteiro.md" % s
    if not pj.voz_limpo.is_file():
        return "vam audio %s --bruto voz.m4a" % s
    if not pj.avatar_mp4.is_file():
        return "vam avatar %s" % s
    if not pj.plano_json.is_file():
        return "vam plano %s" % s
    if not pj.aprovacao.is_file():
        return "mostre plano/plano_edicao.md ao aluno; com o ok dele: vam aprovar %s --ok \"<o ok>\"" % s
    if not pj.laudo.is_file():
        return "vam montar %s" % s
    if not pj.nota.is_file():
        return "vam auditar %s (a auditoria registra a nota)" % s
    return "vam entregar %s" % s


def _uma_linha(atual):
    if not atual:
        return "(sem etapa registrada)"
    m = (": " + atual["motivo"]) if atual.get("motivo") else ""
    return "%s %s em %s%s" % (atual["etapa"], atual["estado"], atual["em"], m)


def _executar(args):
    from projeto import modelo, pastas, status
    if not args.slug:
        estado = C.estado(args)
        nomes = pastas.listar(estado)
        if not nomes:
            print("nenhum projeto em %s: vam novo <slug> --look <look> --sem-trilha \"motivo\"" % pastas.projetos_dir(estado))
            return C.SAIDA_OK
        for n in nomes:
            pj = pastas.projeto(n, estado)
            try:
                atual = status.ler(pj)["atual"]
            except ValueError:
                atual = None
            print("  %-24s %s" % (n, _uma_linha(atual)[:150]))
        return C.SAIDA_OK
    pj, projeto = C.projeto_existente(args)
    s = status.ler(pj)
    print("projeto %s (%s, %s) em %s" % (pj.slug, projeto["modo"], projeto.get("look", "sem look"), pj.raiz))
    print("atual: " + _uma_linha(s["atual"]))
    if s["historico"]:
        print("últimas etapas:")
        for r in s["historico"][-ULTIMAS:]:
            print("  " + _uma_linha(r)[:170])
    for rot, caminho in (("roteiro.md", pj.roteiro), ("voz limpa", pj.voz_limpo), ("avatar", pj.avatar_mp4),
                         ("plano", pj.plano_json), ("aprovação", pj.aprovacao), ("final", pj.final_9x16),
                         ("prévia", pj.final_whatsapp), ("laudo", pj.laudo), ("nota", pj.nota)):
        print("  %-11s %s" % (rot, "ok" if caminho.is_file() else "-"))
    if projeto["modo"] == "avatar":
        print("próximo: " + proximo_passo(pj))
    return C.SAIDA_OK


def executar(args):
    return C.rodar(NOME, _executar, args)
