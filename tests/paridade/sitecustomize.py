"""Grava o argv de todo subprocess em JSONL, sem mudar a execução (W0.3, paridade).

Como funciona: o harness (`capturar.py`) copia ESTE arquivo para uma pasta própria, a
põe no PYTHONPATH do interpretador que roda o motor e define `VAM_PARIDADE_LOG` com o
caminho do JSONL. O Python importa `sitecustomize` sozinho na partida; aqui, se a
variável existir, `subprocess.Popen.__init__` passa a anotar cada chamada antes de
executá-la. Sem a variável, importar este módulo não faz nada (é o caso do pytest).

Cada linha do JSONL é um objeto:

    {"argv": [...], "cwd": "<pasta ou null>", "shell": false}

`argv` é a lista exata passada ao subprocess (ou, com `shell=True`, a string inteira
numa lista de um item). `cwd` só aparece quando o chamador o passou: herdar o diretório
corrente é o padrão e não é decisão do motor. O harness também escreve linhas
`{"fase": "..."}` no mesmo arquivo, entre as etapas.

Garantias:
  - nunca levanta exceção para o chamador: falha ao gravar o log é engolida, o subprocess
    roda do mesmo jeito;
  - cada linha sai num único `os.write` com O_APPEND, então processos e threads
    diferentes não misturam linhas;
  - interpretadores filhos (o motor chama `python medir_enquadramento.py`, por exemplo)
    herdam o PYTHONPATH e também gravam.

Só cobre `subprocess`; o motor não usa `os.system` nem `os.popen` (conferido em W0.3).
"""
import json
import os


def _como_texto(item):
    if isinstance(item, (bytes, bytearray)):
        return bytes(item).decode("utf-8", "surrogateescape")
    return os.fspath(item) if hasattr(item, "__fspath__") else str(item)


def registro_de(args, kwargs):
    """Monta o objeto do log para uma chamada de Popen (função pura, testável)."""
    if isinstance(args, (list, tuple)):
        argv = [_como_texto(x) for x in args]
    else:
        argv = [_como_texto(args)]
    cwd = kwargs.get("cwd")
    return {
        "argv": argv,
        "cwd": _como_texto(cwd) if cwd is not None else None,
        "shell": bool(kwargs.get("shell")),
    }


def _gravar(caminho, registro):
    linha = (json.dumps(registro, ensure_ascii=False) + "\n").encode("utf-8", "surrogateescape")
    fd = os.open(caminho, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, linha)
    finally:
        os.close(fd)


def instalar(caminho=None):
    """Liga o registro. Devolve True se ligou (ou se já estava ligado)."""
    caminho = caminho or os.environ.get("VAM_PARIDADE_LOG")
    if not caminho:
        return False
    import subprocess

    if getattr(subprocess.Popen, "_paridade_instalado", False):
        return True
    original = subprocess.Popen.__init__

    def __init__(self, *args, **kwargs):
        try:
            alvo = args[0] if args else kwargs.get("args")
            _gravar(caminho, registro_de(alvo, kwargs))
        except Exception:
            pass  # o log nunca pode mudar a execução
        return original(self, *args, **kwargs)

    subprocess.Popen.__init__ = __init__
    subprocess.Popen._paridade_instalado = True
    return True


instalar()
