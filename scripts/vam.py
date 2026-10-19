#!/usr/bin/env python3
"""vam: a CLI única do aluno, do roteiro ao anúncio entregue.

    python3 scripts/vam.py <comando> [...]          python3 scripts/vam.py <comando> --help

O fluxo do modo avatar, na ordem:

    doctor                         confere a máquina (ffmpeg com libass, Node e HyperFrames, transcritor, chaves)
    novo <slug> --look L ...       cria o projeto em _local/projetos/<slug>
    roteiro <slug> --de r.md       grava e valida o roteiro.md (a fonte da verdade da fala)
    audio <slug> --bruto voz.m4a   higieniza a voz e confere respiro, ritmo, fala preservada e fala x roteiro
    avatar <slug> [--existente A]  gera o avatar no HeyGen (ou usa um já gerado) e confere tamanho, boca e duração
    plano <slug> [--prancha]       mede o plano de edição (plano.json e plano_edicao.md) e, se pedido, a prancha
    aprovar <slug> --ok "..."      o ok do aluno ao plano, amarrado por sha256 (só depois do ok no chat)
    montar <slug>                  o build com todos os gates na ordem; prévia e laudo em entrega/
    auditar <slug> [--nota N]      o pacote da auditoria; o AUDITOR registra a nota (quem é medido não assina)
    entregar <slug>                libera só com laudo PASS, aprovação vigente e nota 8+ no mesmo sha256
    status [<slug>]                onde cada projeto parou e o próximo passo

Take de câmera: `vam gravado` (vários takes) e `vam oneshot` (um take). Inserts de UI: `vam insert`.
Prova de fumaça do render (o HyperFrames renderiza um overlay de 2 s nesta máquina): `vam fumaca --saida fumaca.mp4`.

Os subcomandos moram em scripts/cli/<nome>.py (cada um com `registrar(subparsers)` e `executar(args) -> int`) e são
descobertos sozinhos. Saídas: 0 fez · 1 defeito medido · 2 pedido ou insumo inválido.

Se o repo tem `.venv` (criado pelo `bash setup.sh`) e quem roda não é o Python dele, o vam roda o Python dele como
processo filho (PYTHONUTF8=1) e sai com o código de saída do filho: as dependências (numpy, opencv, pillow) moram lá.
VAM_SEM_VENV=1 desliga isso. (Não usa `os.execv`: no Windows ele perde o código de saída.)
"""
import argparse
import importlib
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
RAIZ = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import plataforma  # noqa: E402  (precisa do SCRIPTS no sys.path)


def python_do_venv(raiz, executavel, prefixo=None):
    """O Python do `.venv` do repo, se existe e não é ele que já está rodando; senão None (não reexecuta em laço)."""
    venv = Path(raiz) / ".venv"
    py = plataforma.venv_python(raiz)           # .venv/bin/python (Mac, Linux) ou .venv/Scripts/python.exe (Windows)
    if not py.exists():
        return None
    if os.path.abspath(str(executavel)) == os.path.abspath(str(py)):
        return None
    if prefixo is not None and os.path.realpath(str(prefixo)) == os.path.realpath(str(venv)):
        return None                             # realpath: um `.venv` que é link para outra pasta não vira laço
    return py


def _reexecutar_no_venv():
    """Roda este mesmo comando no Python do `.venv` e sai com o código de saída dele; sem `.venv` útil, não faz nada.

    `subprocess.run` e não `os.execv`: no Windows o execv não substitui o processo, o pai sai na hora com 0 e o código
    de saída do filho se perde. PYTHONUTF8=1 vai só para o filho (o console do Windows usa cp1252 e quebra o acento)."""
    if os.environ.get("VAM_SEM_VENV") == "1":
        return
    py = python_do_venv(RAIZ, sys.executable, sys.prefix)
    if py is None:
        return
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["VAM_SEM_VENV"] = "1"                   # o filho nunca se reexecuta de novo, aconteça o que acontecer
    try:
        codigo = subprocess.run([str(py), str(Path(__file__).resolve())] + sys.argv[1:], env=env).returncode
    except KeyboardInterrupt:                   # o Ctrl-C também chegou ao filho, que já encerrou
        sys.exit(130)
    sys.exit(codigo)


class _SemDependencia(object):
    """Subcomando cujo módulo não importa (dependência Python ausente): ele existe e diz UMA vez o que instalar, em vez
    de derrubar o `vam` inteiro (o `vam doctor` tem que rodar justamente quando falta coisa)."""

    def __init__(self, nome, erro):
        self.nome, self.erro = nome, erro

    def registrar(self, sub):
        p = sub.add_parser(self.nome, help="(indisponível: falta uma dependência Python)", add_help=False)
        p.add_argument("resto", nargs=argparse.REMAINDER)
        p.set_defaults(func=self.executar)

    def executar(self, args):
        print("vam %s: falta uma dependência Python (%s). Rode: bash setup.sh   (e depois: python3 scripts/vam.py "
              "doctor)" % (self.nome, self.erro), file=sys.stderr)
        return 2


def modulos():
    """Os módulos de scripts/cli/ que são subcomandos (têm `registrar`), em ordem alfabética."""
    saida = []
    for arq in sorted((SCRIPTS / "cli").glob("*.py")):
        if arq.stem.startswith("_"):
            continue
        try:
            mod = importlib.import_module("cli." + arq.stem)
        except ImportError as e:
            saida.append(_SemDependencia(arq.stem, e))
            continue
        if callable(getattr(mod, "registrar", None)):
            saida.append(mod)
    return saida


def construir_parser():
    ap = argparse.ArgumentParser(prog="vam", description=__doc__.split("\n\n")[0],
                                 epilog=__doc__.split("\n\n", 1)[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="comando", metavar="<comando>")
    for mod in modulos():
        mod.registrar(sub)
    return ap, sub


def comandos():
    """Os nomes dos subcomandos registrados."""
    _ap, sub = construir_parser()
    return sorted(sub.choices)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap, _sub = construir_parser()
    if not argv:
        ap.print_help()
        return 2
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:                       # --help (0) ou pedido que o argparse recusou (2)
        return int(e.code or 0)
    if not callable(getattr(args, "func", None)):
        ap.print_help()
        return 2
    return int(args.func(args) or 0)


if __name__ == "__main__":
    _reexecutar_no_venv()
    sys.exit(main())
