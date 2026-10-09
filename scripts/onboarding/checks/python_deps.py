"""Check: Python 3.9+ e as bibliotecas do motor, no interpretador que o motor vai usar.

Se o repo tem `.venv`, é o Python dele que se confere (o `setup.sh` cria o .venv porque o
Python do Homebrew recusa `pip install` fora de um ambiente virtual, PEP 668). Sem `.venv`,
vale o Python que está rodando o doctor.
"""
import re

from ..doctor import FAIL, OK, Resultado

NOME = "python_deps"
PYTHON_MINIMO = (3, 9)
SETUP = "bash scripts/setup.sh"

# módulo importável -> pacote do pip
MODULOS = (("numpy", "numpy"), ("cv2", "opencv-python-headless"), ("PIL", "pillow"),
           ("scipy", "scipy"))

SONDA = (
    "import sys, importlib.util\n"
    "print(sys.version_info[0], sys.version_info[1])\n"
    "print(','.join(m for m in %r if importlib.util.find_spec(m) is None))\n"
) % (tuple(m for m, _ in MODULOS),)


def checar(amb):
    venv = amb.venv_python
    python = str(venv) if venv else amb.python
    onde = ".venv" if venv else "Python do sistema"
    rc, saida = amb.executar([python, "-c", SONDA], timeout=60)
    linhas = (saida or "").splitlines()
    versao = None
    for i, linha in enumerate(linhas):
        m = re.match(r"^(\d+) (\d+)$", linha.strip())
        if m:
            versao = (int(m.group(1)), int(m.group(2)))
            faltando = linhas[i + 1].strip() if i + 1 < len(linhas) else ""
            break
    if rc != 0 or versao is None:
        return Resultado(NOME, FAIL, "não consegui rodar o Python (%s): %s"
                         % (onde, (saida or "").strip()[-200:] or "sem saída"), SETUP)
    ver = "%d.%d" % versao
    if versao < PYTHON_MINIMO:
        return Resultado(NOME, FAIL, "Python %s (%s): o motor pede 3.9 ou superior" % (ver, onde),
                         "instale o Python 3.9 ou superior (macOS: brew install python@3.12) e "
                         "rode " + SETUP)
    ausentes = [m for m in faltando.split(",") if m]
    if ausentes:
        pacotes = dict(MODULOS)
        return Resultado(NOME, FAIL, "faltam no Python %s (%s): %s"
                         % (ver, onde, ", ".join(pacotes.get(m, m) for m in ausentes)), SETUP)
    return Resultado(NOME, OK, "Python %s (%s) com %s" % (ver, onde,
                                                         ", ".join(p for _, p in MODULOS)))
