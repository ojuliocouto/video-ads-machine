"""`vam insert`: gera um insert de UI (mp4) a partir de um template e de um JSON de texto.

    vam insert <slug> <chave> --template whatsapp --dados dados.json --dur 4
    vam insert --exemplo whatsapp          imprime o JSON completo do template (ponto de partida)
    vam insert --templates                 lista os templates

Escreve `inserts/<chave>.mp4` no projeto: é o arquivo que a convenção `[insert: <chave>]` do roteiro
acha (`projeto.pastas.insert`). Os sete templates ficam em `templates/inserts_ui/` e a lógica em
`cinema/insert_ui.py`; aqui só mora o pedido do aluno e os códigos de saída.

    exit 0  escreveu o mp4 (ou listou o template ou o exemplo)
    exit 1  o render falhou: sem motor de render (uma linha com o comando que resolve) ou o motor caiu
    exit 2  pedido inválido: slug, chave, template, dados, duração, proporção, projeto que não existe,
            ou outro arquivo (ex.: um .mov do aluno) já usando a mesma chave

O render só começa depois que tudo isso foi conferido, e o mp4 que já existia nunca é tocado por um
render que falha.
"""
import argparse
import json
import math
import os
import sys

if __name__ == "__main__":      # rodado direto: scripts/cli/insert.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cinema import insert_ui  # noqa: E402
from projeto import pastas  # noqa: E402

NOME = "insert"
SAIDA_OK, SAIDA_FALHOU, SAIDA_USO = 0, 1, 2


def registrar(subparsers):
    """Cadastra o subcomando no `vam.py`."""
    p = subparsers.add_parser(
        NOME, help="gera um insert de UI (mp4) a partir de um template e de um JSON",
        description="Gera inserts/<chave>.mp4 no projeto a partir de um dos templates de UI "
                    "(%s) e de um JSON com os textos. `--exemplo <template>` imprime o JSON de partida."
                    % ", ".join(insert_ui.templates()))
    p.add_argument("slug", nargs="?", help="o projeto (pasta em _local/projetos/)")
    p.add_argument("chave", nargs="?", help="nome do insert: vira inserts/<chave>.mp4 e o [insert: <chave>] do roteiro")
    p.add_argument("--template", help="um de: %s" % ", ".join(insert_ui.templates()))
    p.add_argument("--dados", help="arquivo JSON com os textos do template")
    p.add_argument("--dur", type=float, default=insert_ui.DUR_PADRAO,
                   help="duração em segundos (de %g a %g; padrão %g)"
                        % (insert_ui.DUR_MIN, insert_ui.DUR_MAX, insert_ui.DUR_PADRAO))
    p.add_argument("--proporcao", default=insert_ui.PROPORCAO_PADRAO,
                   help="%s, 16:9, 4:5 ou 1080x1150 (padrão %s; painel é o painel de cima do split)"
                        % (", ".join(insert_ui.PROPORCOES), insert_ui.PROPORCAO_PADRAO))
    p.add_argument("--fps", type=int, default=insert_ui.FPS_PADRAO, help="quadros por segundo (padrão %(default)s)")
    p.add_argument("--exemplo", metavar="TEMPLATE", help="imprime o JSON completo do template e sai")
    p.add_argument("--templates", action="store_true", help="lista os templates e sai")
    p.add_argument("--estado", default=None, help=argparse.SUPPRESS)
    p.set_defaults(func=executar)
    return p


def _erro(texto):
    print("vam insert: %s" % texto, file=sys.stderr)


def _sem_repeticao(pares):
    d = {}
    for k, v in pares:
        if k in d:
            raise ValueError("chave repetida no JSON: %r" % k)
        d[k] = v
    return d


def _constante_invalida(nome):
    raise ValueError("%s não é JSON válido" % nome)


def _ler_dados(caminho):
    """(dados, None) ou (None, mensagem)."""
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f, object_pairs_hook=_sem_repeticao, parse_constant=_constante_invalida), None
    except FileNotFoundError:
        return None, "o arquivo de dados não existe: %s" % caminho
    except (OSError, UnicodeDecodeError) as e:
        return None, "não consegui ler %s: %s" % (caminho, e)
    except ValueError as e:
        return None, "o JSON de %s não é válido: %s" % (caminho, e)


def executar(args):
    """Roda o subcomando. Devolve o código de saída (0, 1 ou 2)."""
    if args.templates:
        for nome in insert_ui.templates():
            print(nome)
        return SAIDA_OK
    if args.exemplo is not None:
        try:
            exemplo = insert_ui.exemplo(args.exemplo)
        except insert_ui.TemplateInexistente as e:
            _erro(str(e))
            return SAIDA_USO
        print(json.dumps(exemplo, ensure_ascii=False, indent=2))
        return SAIDA_OK

    faltam = [nome for nome, valor in (("slug", args.slug), ("chave", args.chave),
                                       ("--template", args.template), ("--dados", args.dados)) if not valor]
    if faltam:
        _erro("faltou: %s. Uso: vam insert <slug> <chave> --template <%s> --dados dados.json [--dur 4]"
              % (", ".join(faltam), "|".join(insert_ui.templates())))
        return SAIDA_USO

    try:
        projeto = pastas.projeto(args.slug, args.estado)
    except ValueError as e:
        _erro("slug inválido: %s" % e)
        return SAIDA_USO
    if not projeto.raiz.is_dir():
        _erro("o projeto %r não existe em %s: crie antes com `vam novo`" % (args.slug, projeto.raiz.parent))
        return SAIDA_USO
    try:
        projeto.insert(args.chave)                  # valida a chave (e acha arquivo duplicado)
    except ValueError as e:
        _erro(str(e))
        return SAIDA_USO
    destino = projeto.inserts_dir / (args.chave + ".mp4")
    outros = [f for f in (projeto.inserts_dir.iterdir() if projeto.inserts_dir.is_dir() else [])
              if f.is_file() and f.stem == args.chave and f.suffix.lower() != ".mp4"
              and not f.name.startswith(".")]
    if outros:
        _erro("já existe inserts/%s e a chave %r não pode ter dois arquivos: apague esse arquivo ou use "
              "outra chave" % (outros[0].name, args.chave))
        return SAIDA_USO

    if args.template not in insert_ui.templates():
        _erro("template desconhecido: %r (existem: %s)" % (args.template, ", ".join(insert_ui.templates())))
        return SAIDA_USO
    dados, problema = _ler_dados(args.dados)
    if problema:
        _erro(problema)
        return SAIDA_USO
    if not math.isfinite(args.dur):
        _erro("duração inválida: %s" % args.dur)
        return SAIDA_USO

    try:
        resultado = insert_ui.renderizar(args.template, dados, destino, dur=args.dur,
                                         proporcao=args.proporcao, fps=args.fps)
    except (insert_ui.DadosInvalidos, insert_ui.ProporcaoInvalida, ValueError) as e:
        _erro(str(e))
        return SAIDA_USO
    except (insert_ui.SemMotorDeRender, insert_ui.RenderFalhou) as e:
        _erro(str(e))
        return SAIDA_FALHOU
    print("inserts/%s escrito em %s (%d quadros, %g s, %dx%d, %d fps, motor %s)"
          % (destino.name, destino, resultado.quadros, resultado.dur, resultado.largura, resultado.altura,
             resultado.fps, resultado.motor))
    return SAIDA_OK


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="insert")
    registrar(ap.add_subparsers(dest="comando"))
    sys.exit(executar(ap.parse_args(["insert"] + sys.argv[1:])))
