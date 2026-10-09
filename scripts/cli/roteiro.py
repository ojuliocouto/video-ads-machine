"""`vam roteiro <slug>`: grava e valida o roteiro.md, a FONTE DA VERDADE da fala.

    vam roteiro <slug> --de roteiro.md       (ou .txt; `--de -` lê do stdin)
    vam roteiro <slug> --texto "..."         o texto colado no chat, verbatim
    vam roteiro <slug>                       só confere o roteiro.md que já está no projeto

A normalização só mexe em aspas, espaços, quebras de linha e rótulos de chat: nenhuma palavra da fala muda. Roteiro
fora da convenção (contratos/roteiro-convencao.md) não é gravado (saída 1, uma linha por problema). Trocar um roteiro
que já existe pede --sobrescrever: a fala nova vence a aprovação do plano.
"""
import argparse
import sys
from pathlib import Path

from cli import _comum as C

NOME = "roteiro"


def registrar(subparsers):
    p = subparsers.add_parser(NOME, help="grava e valida o roteiro.md do projeto",
                              description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("slug")
    p.add_argument("--de", help="arquivo .md ou .txt com o roteiro (- = stdin)")
    p.add_argument("--texto", help="o roteiro como texto (o que foi colado no chat)")
    p.add_argument("--sobrescrever", action="store_true", help="troca um roteiro.md que já existe")
    C.opcao_estado(p)
    p.set_defaults(func=executar)
    return p


def resumo(lei):
    blocos = lei.blocos
    inserts = [b["insert"] for b in blocos if b["tipo"] == "insert"]
    keys = [b for b in blocos if b.get("key")]
    listas = [b for b in blocos if b["tipo"] == "lista"]
    linhas = ["%d blocos | %d insert(s) (%s) | %d KEY(s) | %d lista(s) | %d palavras%s"
              % (len(blocos), len(inserts), ", ".join(dict.fromkeys(inserts)) or "nenhum", len(keys), len(listas),
                 lei.n_palavras, " | roteiro LIVRE: o plano propõe as direções" if lei.precisa_plano else "")]
    return "\n".join(linhas)


def _texto_de_entrada(args):
    if args.texto is not None and args.de:
        raise C.PedidoInvalido("--de e --texto se excluem")
    if args.texto is not None:
        return args.texto
    if args.de == "-":
        return sys.stdin.read()
    arq = Path(args.de).expanduser()
    if not arq.is_file():
        raise C.PedidoInvalido("o arquivo do roteiro não existe: %s" % arq)
    if arq.suffix.lower() not in (".md", ".txt"):
        raise C.PedidoInvalido("o roteiro vem em .md ou .txt (recebi %s)" % arq.suffix)
    return arq.read_bytes().decode("utf-8-sig")


def _executar(args):
    from entrada import roteiro_md
    pj, _projeto = C.projeto_existente(args)
    if args.de is None and args.texto is None:
        if not pj.roteiro.is_file():
            raise C.PedidoInvalido("ainda não há roteiro.md em %s: vam roteiro %s --de roteiro.md" % (pj.raiz, pj.slug))
        lei = roteiro_md.ler_arquivo(pj.roteiro, normalizar=False)
        if lei.erros:
            C.erro(NOME, "o roteiro.md não passa na convenção:\n" + roteiro_md.formatar_erros(lei.erros))
            return C.SAIDA_DEFEITO
        print("roteiro.md ok: " + resumo(lei))
        return C.SAIDA_OK
    texto = _texto_de_entrada(args)
    lei = roteiro_md.ler(texto, normalizar=True)
    if lei.erros:
        C.erro(NOME, "o roteiro não passa na convenção (nada foi gravado):\n" + roteiro_md.formatar_erros(lei.erros))
        return C.SAIDA_DEFEITO
    if pj.roteiro.is_file() and not args.sobrescrever:
        if pj.roteiro.read_text(encoding="utf-8") == lei.texto:
            print("roteiro.md já é este: " + resumo(lei))
            return C.SAIDA_OK
        raise C.PedidoInvalido("o projeto já tem outro roteiro.md: use --sobrescrever para trocar (a fala nova vence a "
                               "aprovação do plano)")
    roteiro_md.salvar(texto, pj.roteiro, sobrescrever=True)
    from projeto import status
    status.registrar(pj, "roteiro", "ok", detalhes={"blocos": len(lei.blocos), "palavras": lei.n_palavras})
    print("roteiro.md gravado em %s\n  %s" % (pj.roteiro, resumo(lei)))
    faltam = [b["insert"] for b in lei.blocos if b["tipo"] == "insert" and pj.insert(b["insert"]) is None]
    if faltam:
        print("  inserts que ainda faltam em inserts/: %s" % ", ".join(dict.fromkeys(faltam)))
    print("próximo: vam audio %s --bruto voz.m4a" % pj.slug)
    return C.SAIDA_OK


def executar(args):
    return C.rodar(NOME, _executar, args)
