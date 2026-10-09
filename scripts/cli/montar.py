"""`vam montar <slug>`: o build do anúncio com todos os gates, na ordem da seção 4 do plano.

Antes do build: aprovação vigente, fidelidade ao roteiro, fala x roteiro, entrada (voz e avatar) e look; depois de
montar a timeline (o relógio único): geometria, zona segura, lettering e congelamento sobre o plano. Durante: tela
vazia, congelamento real, relógio e template. A prévia de WhatsApp (entrega/final_whatsapp.mp4) sai assim que o render
termina; então os 15 gates de saída rodam sobre o arquivo final e o laudo (entrega/laudo.json) amarra tudo ao sha256
dele. O primeiro gate que reprova antes ou durante o build interrompe, com o motivo no status.json.

Saídas: 0 laudo PASS · 1 algum gate reprovou · 2 insumo inválido ou ferramenta que morreu.
"""
import argparse

from cli import _comum as C

NOME = "montar"


def registrar(subparsers):
    p = subparsers.add_parser(NOME, help="monta o anúncio com os gates na ordem (prévia, laudo)",
                              description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("slug")
    p.add_argument("--paralelo", type=int, default=None, help="gates de saída ao mesmo tempo (1 a 4; padrão 4)")
    C.opcao_estado(p)
    p.set_defaults(func=executar)
    return p


def _executar(args):
    import produzir_ad
    pj, projeto = C.projeto_existente(args)
    C.exigir_modo(pj, projeto, "avatar", NOME)
    return produzir_ad.montar(pj, paralelo=args.paralelo)


def executar(args):
    return C.rodar(NOME, _executar, args)
