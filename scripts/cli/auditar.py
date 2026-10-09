"""`vam auditar <slug>`: a auditoria adversarial do arquivo final. Uma rodada, nota mínima 8.

    vam auditar <slug>                                        o pacote: o que o auditor lê e o sha256 que ele audita
    vam auditar <slug> --nota 8.5 --achados achados.json      o AUDITOR registra a nota (entrega/nota.json)
    vam auditar <slug> --nota 9 --rodada 2 --reconfere A1 A3  a rodada 2 reconfere OS MESMOS achados, nunca varre de novo

Quem é medido não assina: este é o ÚNICO comando que escreve entrega/nota.json, e quem o roda é o auditor (subagente
com contexto limpo, references/auditoria.md), nunca o montador. A nota é amarrada ao sha256 do arquivo final: montar
de novo vence a nota. Saída 2 para nota fora de 0 a 10, achados fora do contrato ou sem arquivo final.
"""
import argparse
import json
from pathlib import Path

from cli import _comum as C

NOME = "auditar"
PROMPT = "references/auditoria.md"


def registrar(subparsers):
    p = subparsers.add_parser(NOME, help="o pacote da auditoria; o auditor registra a nota (8 ou mais)",
                              description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("slug")
    p.add_argument("--nota", type=float, help="a nota do auditor, de 0 a 10")
    p.add_argument("--achados", help="json com a lista de achados [{id, gravidade, descricao, status, [instante_s]}]")
    p.add_argument("--rodada", type=int, choices=(1, 2), default=1)
    p.add_argument("--reconfere", nargs="*", default=None, help="rodada 2: os ids dos achados reconferidos")
    p.add_argument("--modelo", help="o modelo do auditor (vai para a nota)")
    p.add_argument("--esforco", help="o esforço do auditor (vai para a nota)")
    C.opcao_estado(p)
    p.set_defaults(func=executar)
    return p


def _pacote(pj, sha):
    from entrega import laudo as LD
    print("AUDITORIA de %s" % pj.slug)
    print("  arquivo   %s" % pj.final_9x16)
    print("  sha256    %s" % sha)
    if pj.final_whatsapp.is_file():
        print("  prévia    %s" % pj.final_whatsapp)
    if pj.folhas_dir.is_dir():
        for f in sorted(pj.folhas_dir.glob("*.png")):
            print("  folha     %s" % f)
    for rot, arq in (("roteiro", pj.roteiro), ("plano", pj.plano_md), ("laudo", pj.laudo)):
        if arq.is_file():
            print("  %-9s %s" % (rot, arq))
    try:
        d = LD.ler(pj)
    except ValueError:
        d = None
    if d:
        print("  laudo: %s%s" % (d["veredito"], "" if d["sha256"] == sha else " (DE OUTRO ARQUIVO: rode vam montar)"))
    print("\nO auditor segue %s: uma rodada, estrategista e diretor numa passada, refutar em vez de revisar, só o que "
          "se vê no celular. Para registrar: vam auditar %s --nota N --achados achados.json" % (PROMPT, pj.slug))


def _achados(caminho):
    if not caminho:
        return []
    try:
        dados = json.loads(Path(caminho).expanduser().read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise C.PedidoInvalido("achados ilegíveis (%s): %s" % (caminho, e))
    if not isinstance(dados, list):
        raise C.PedidoInvalido("os achados são uma lista JSON de {id, gravidade, descricao, status}")
    return dados


def _executar(args):
    from contratos.validar import validar
    from projeto import status
    pj, _projeto = C.projeto_existente(args)
    if not pj.final_9x16.is_file():
        raise C.PedidoInvalido("sem arquivo final para auditar: vam montar %s" % pj.slug)
    sha = C.sha256_arquivo(pj.final_9x16)
    if args.nota is None:
        _pacote(pj, sha)
        return C.SAIDA_OK
    if not 0 <= args.nota <= 10:
        raise C.PedidoInvalido("a nota vai de 0 a 10 (recebi %s)" % args.nota)
    nota = {"versao": 1, "projeto": pj.slug, "arquivo": pj.relativo(pj.final_9x16), "sha256": sha,
            "nota": args.nota, "rodada": args.rodada, "auditado_em": status.instante(),
            "achados": _achados(args.achados), "emissor": "auditor"}
    auditor = {k: v for k, v in (("modelo", args.modelo), ("esforco", args.esforco)) if v}
    if auditor:
        nota["auditor"] = auditor
    if args.reconfere is not None:
        nota["reconfere"] = list(args.reconfere)
    erros = validar("nota", nota)
    if erros:
        raise C.PedidoInvalido("a nota não passa no contrato (nada foi gravado): " + "; ".join(str(e) for e in erros[:4]))
    status.escrever_json_atomico(pj.nota, nota)
    status.registrar(pj, NOME, "ok", detalhes={"nota": args.nota, "rodada": args.rodada})
    print("nota %s registrada (rodada %d), amarrada ao sha256 %s... de %s" % (str(args.nota).replace(".", ","),
          args.rodada, sha[:12], pj.relativo(pj.final_9x16)))
    print("próximo: vam entregar %s" % pj.slug)
    return C.SAIDA_OK


def executar(args):
    return C.rodar(NOME, _executar, args)
