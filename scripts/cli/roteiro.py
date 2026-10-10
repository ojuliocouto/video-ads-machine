"""`vam roteiro <slug>`: grava e valida o roteiro.md, a FONTE DA VERDADE da fala.

    vam roteiro <slug> --de roteiro.md       (ou .txt; `--de -` lê do stdin)
    vam roteiro <slug> --texto "..."         o texto colado no chat, verbatim
    vam roteiro <slug> --de-audio voz.m4a    transcreve a gravação (com o seu glossário) e grava um RASCUNHO do roteiro.md
    vam roteiro <slug>                       só confere o roteiro.md que já está no projeto

O `--de-audio` serve a quem grava a voz antes de escrever: a transcrição sai verbatim (só o glossário corrige o que o
transcritor erra), em parágrafos nas pausas de 0,60 s ou mais, como roteiro livre. É um RASCUNHO: revise contra a
gravação e, se quiser direção (insert, KEY, hook), ponha os colchetes; o `vam audio` e o plano vêm depois.

A normalização só mexe em aspas, espaços, quebras de linha e rótulos de chat: nenhuma palavra da fala muda. Roteiro
fora da convenção (contratos/roteiro-convencao.md) não é gravado (saída 1, uma linha por problema). Trocar um roteiro
que já existe pede --sobrescrever: a fala nova vence a aprovação do plano.
"""
import argparse
import sys
from pathlib import Path

from cli import _comum as C

NOME = "roteiro"
AUDIOS = (".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".mp4", ".mov")
PAUSA_PARAGRAFO_S = 0.60        # a mesma "pausa longa" do gate de entrada: pausa de fim de ideia abre parágrafo


def registrar(subparsers):
    p = subparsers.add_parser(NOME, help="grava e valida o roteiro.md do projeto",
                              description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("slug")
    p.add_argument("--de", help="arquivo .md ou .txt com o roteiro (- = stdin)")
    p.add_argument("--texto", help="o roteiro como texto (o que foi colado no chat)")
    p.add_argument("--de-audio", dest="de_audio", metavar="VOZ",
                   help="a gravação da voz (m4a, mp3, wav...): transcreve e grava um rascunho do roteiro.md")
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


def paragrafos_da_fala(palavras):
    """A transcrição em parágrafos: um novo parágrafo onde a pausa entre duas palavras passa de PAUSA_PARAGRAFO_S.
    Verbatim: as palavras são as do transcritor (já com o glossário), unidas por espaço."""
    paragrafos, atual, fim = [], [], None
    for p in palavras:
        texto = str(p.get("text", "")).strip()
        if not texto:
            continue
        if atual and fim is not None and float(p.get("start", 0.0)) - fim > PAUSA_PARAGRAFO_S:
            paragrafos.append(" ".join(atual))
            atual = []
        atual.append(texto)
        fim = float(p.get("end", p.get("start", 0.0)))
    if atual:
        paragrafos.append(" ".join(atual))
    return paragrafos


def _de_audio(args, pj):
    """Transcreve a gravação e grava o rascunho do roteiro.md (roteiro livre, um bloco por parágrafo)."""
    from audio import transcrever as T
    from entrada import roteiro_md
    from projeto import glossario, status
    if args.de is not None or args.texto is not None:
        raise C.PedidoInvalido("--de-audio não anda junto com --de nem com --texto: um transcreve a gravação, os "
                               "outros trazem o texto pronto")
    audio = Path(args.de_audio).expanduser()
    if not audio.is_file():
        raise C.PedidoInvalido("a gravação não existe: %s" % audio)
    if audio.suffix.lower() not in AUDIOS:
        raise C.PedidoInvalido("formato de áudio não aceito: %s (aceitos: %s)" % (audio.suffix, ", ".join(AUDIOS)))
    if pj.roteiro.is_file() and not args.sobrescrever:
        raise C.PedidoInvalido("o projeto já tem um roteiro.md: use --sobrescrever para trocar pelo rascunho da gravação "
                               "(a fala nova vence a aprovação do plano)")
    print("transcrevendo %s (pode levar alguns minutos na primeira vez)..." % audio.name, flush=True)
    try:
        palavras = T.transcrever(audio, cache_dir=pj.render_dir / "cache_asr", glossario=glossario.carregar(pj.estado))
    except T.SemTranscritor as e:
        raise C.PedidoInvalido(str(e))
    paragrafos = paragrafos_da_fala(palavras)
    if not paragrafos:
        raise C.PedidoInvalido("a transcrição de %s não tem nenhuma palavra: o transcritor não ouviu fala (áudio mudo, "
                               "corrompido ou em outro idioma)" % audio.name)
    texto = "\n\n".join(paragrafos) + "\n"
    lei = roteiro_md.ler(texto, normalizar=True)
    if lei.erros:
        C.erro(NOME, "a transcrição não passa na convenção (nada foi gravado):\n" + roteiro_md.formatar_erros(lei.erros))
        return C.SAIDA_DEFEITO
    roteiro_md.salvar(texto, pj.roteiro, sobrescrever=True)
    status.registrar(pj, "roteiro", "ok", detalhes={"blocos": len(lei.blocos), "palavras": lei.n_palavras,
                                                     "origem": "audio"})
    print("rascunho do roteiro.md gravado em %s\n  %s" % (pj.roteiro, resumo(lei)))
    print("revise o rascunho contra a gravação (nome próprio e termo técnico o transcritor erra: declare no glossário) e "
          "ponha a direção entre colchetes onde quiser insert, KEY ou hook;\npróximo: vam roteiro %s   (confere a "
          "convenção) e vam audio %s --bruto %s" % (pj.slug, pj.slug, audio.name))
    return C.SAIDA_OK


def _executar(args):
    from entrada import roteiro_md
    pj, _projeto = C.projeto_existente(args)
    if args.de_audio is not None:
        return _de_audio(args, pj)
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
