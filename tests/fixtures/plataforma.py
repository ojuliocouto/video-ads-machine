"""Executável falso para os testes, que roda no sistema de quem testa (W0, port nativo para Windows).

Vários testes montam uma "ferramenta" de mentira (um ffmpeg, um hyperframes, um parakeet) que imprime um texto e sai com
um código. Em macOS e Linux isso é um script `#!/bin/sh` com chmod; no Windows um script de shell não executa, então o
equivalente é um `.cmd`. `exe_falso` esconde a diferença:

    from tests.fixtures.plataforma import exe_falso
    exe = exe_falso(tmp_path / "bin", "ffmpeg", "versão falsa", 0)
    subprocess.run([str(exe)])                    # o caminho completo funciona nos dois sistemas
    monkeypatch.setenv("PATH", str(exe.parent) + os.pathsep + os.environ["PATH"])    # e pelo nome (shutil.which acha o .cmd)

O ramo (cmd ou sh) é o de `plataforma.eh_windows()`, então um teste troca o sistema com `monkeypatch.setattr(plataforma,
"_sistema", lambda: "win32")` para conferir o conteúdo do `.cmd` sem estar no Windows.
"""
from pathlib import Path

import plataforma


def _escapar_cmd(texto):
    """Um texto que o `echo(` do cmd imprime como está: `^` primeiro (para não escapar o escape), `%` dobrado."""
    for c in ("^", "&", "|", "<", ">"):
        texto = texto.replace(c, "^" + c)
    return texto.replace("%", "%%")


def _aspas_sh(texto):
    """O texto entre aspas simples para o sh (a aspa simples interna vira '\\'')."""
    return "'" + texto.replace("'", "'\\''") + "'"


def exe_falso(pasta, nome, saida, codigo):
    """Cria o executável falso `nome` em `pasta` e devolve o caminho dele.

    Ele imprime `saida` (uma linha por linha de texto) no stdout e sai com `codigo`. No Windows o arquivo é `nome.cmd`
    (CRLF, ASCII); nos outros é `nome`, `#!/bin/sh` com permissão de execução. `saida` precisa ser ASCII: o cmd lê o
    arquivo na página de código do console, e acento sairia diferente em cada máquina.
    """
    try:
        saida.encode("ascii")
    except UnicodeEncodeError:
        raise ValueError("exe_falso: a saída precisa ser ASCII (o .cmd do Windows não tem codificação estável): %r"
                         % saida)
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    linhas = saida.splitlines() if saida else []
    if plataforma.eh_windows():
        destino = pasta / (nome + ".cmd")
        corpo = ["@echo off"] + ["echo(" + _escapar_cmd(linha) for linha in linhas] + ["exit /b %d" % codigo]
        destino.write_bytes(("\r\n".join(corpo) + "\r\n").encode("ascii"))
        return destino
    destino = pasta / nome
    corpo = ["#!/bin/sh"] + ["printf '%%s\\n' %s" % _aspas_sh(linha) for linha in linhas] + ["exit %d" % codigo]
    destino.write_bytes(("\n".join(corpo) + "\n").encode("utf-8"))
    destino.chmod(0o755)
    return destino
