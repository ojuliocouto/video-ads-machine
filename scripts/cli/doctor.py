"""`vam doctor`: confere a máquina ANTES de gastar um render ou um crédito.

ffmpeg com libass, Node 22+ e o HyperFrames do repo, as dependências Python, o transcritor (parakeet, faster-whisper
ou Groq), as fontes, o GSAP local e a chave do HeyGen com o saldo. Cada item sai OK, WARN ou FAIL com UMA linha de
conserto. Saída 0 sem nenhum FAIL (WARN passa), 1 com FAIL.
"""
import argparse

NOME = "doctor"


def registrar(subparsers):
    p = subparsers.add_parser(NOME, help="confere o ambiente (ffmpeg, Node, HyperFrames, transcritor, HeyGen)",
                              description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.set_defaults(func=executar)
    return p


def executar(args):
    from onboarding import doctor
    return doctor.main([])
