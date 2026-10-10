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
    # 3ª linha: a versão do opencv SE ele não tem o que o motor usa (CascadeClassifier e o XML do rosto); vazia se ok.
    # O opencv 5.0.0 saiu sem CascadeClassifier e a medição do rosto quebrou na prova de aluno.
    "try:\n"
    "    import os, cv2\n"
    "    ok = hasattr(cv2, 'CascadeClassifier') and hasattr(cv2, 'data') and os.path.isfile(\n"
    "        cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')\n"
    "    print('' if ok else cv2.__version__)\n"
    "except ImportError:\n"
    "    print('')\n"
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
            cv2_ruim = linhas[i + 2].strip() if i + 2 < len(linhas) else ""
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
    if cv2_ruim:
        return Resultado(NOME, FAIL, "opencv %s (%s) sem cv2.CascadeClassifier: a medição do rosto falha"
                         % (cv2_ruim, onde),
                         'instale o opencv que o motor usa: %s -m pip install "opencv-python-headless>=4.13,<5"'
                         % ("`.venv/bin/python`" if venv else "python3"))
    return Resultado(NOME, OK, "Python %s (%s) com %s" % (ver, onde,
                                                         ", ".join(p for _, p in MODULOS)))
