"""O bash dos testes, em qualquer sistema (W2, port nativo para Windows).

Vários testes rodam um script `.sh` de verdade (`setup.sh`, `testar_limpo.sh`, `como_aluno.sh`). No macOS e no Linux o
`bash` do PATH serve. No Windows NÃO: `subprocess.run(["bash", ...])` acha primeiro `C:\\Windows\\System32\\bash.exe`
(o CreateProcess procura em System32 antes do PATH), que é o lançador do WSL: sem distribuição instalada ele responde
"Windows Subsystem for Linux has no installed distributions" em UTF-16 e sai com 1. O bash certo é o do Git for Windows.

    from tests.fixtures.git_bash import BASH, caminho_bash, caminho_msys

    subprocess.run([BASH, caminho_bash(script), "--dry-run"], ...)

  BASH                  o executável: /bin/bash (ou o do PATH) fora do Windows; o Git Bash no Windows
  achar_bash()          a mesma escolha, recalculada (os testes injetam o PATH e o sistema)
  caminho_bash(p)       o caminho como argumento do bash: `C:/pasta/x.sh` no Windows (a barra invertida não é separador
                        para o `dirname` do Git Bash), o texto de sempre nos outros
  caminho_msys(p)       o caminho como o Git Bash o escreve (`/c/pasta/x.sh`), para comparar com o que o script imprime

Só biblioteca padrão, Python 3.9.
"""
import os
import shutil
from pathlib import Path, PureWindowsPath

import plataforma

# Pastas onde mora o bash que NÃO serve: o lançador do WSL (System32, Sysnative) e o atalho da Store (WindowsApps).
_LANCADORES_DO_WSL = ("/windows/system32/", "/windows/sysnative/", "/windowsapps/")


def eh_lancador_do_wsl(caminho):
    """True se o `bash.exe` está numa pasta do Windows que guarda o lançador do WSL, não o Git Bash."""
    normal = "/" + str(caminho).replace("\\", "/").lower().lstrip("/")
    return any(pasta in normal for pasta in _LANCADORES_DO_WSL)


def _candidatos_windows(path, which):
    """Os `bash.exe` possíveis, do mais provável ao menos: o PATH, a pasta do git e as instalações padrão."""
    for pasta in (path or "").split(os.pathsep):
        if pasta:
            yield Path(pasta) / "bash.exe"
    git = which("git")
    if git:
        raiz = Path(git).parent
        for _ in range(3):      # Git\cmd\git.exe, Git\bin\git.exe e Git\mingw64\bin\git.exe
            yield raiz / "bin" / "bash.exe"
            yield raiz / "usr" / "bin" / "bash.exe"
            raiz = raiz.parent
    for variavel in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(variavel)
        if base:
            yield Path(base) / "Git" / "bin" / "bash.exe"
            yield Path(base) / "Programs" / "Git" / "bin" / "bash.exe"


def achar_bash(path=None, which=shutil.which):
    """O bash dos testes. Fora do Windows: `/bin/bash` se existe, senão o do PATH. No Windows: o primeiro `bash.exe`
    que existe e não é o lançador do WSL. Sem nenhum, devolve "bash" (o teste falha com a mensagem do sistema)."""
    if path is None:
        path = os.environ.get("PATH", "")
    if not plataforma.eh_windows():
        if Path("/bin/bash").exists():
            return "/bin/bash"
        return which("bash", path=path) or "bash"
    vistos = set()
    for candidato in _candidatos_windows(path, which):
        chave = os.path.normcase(str(candidato))
        if chave in vistos:
            continue
        vistos.add(chave)
        if candidato.is_file() and not eh_lancador_do_wsl(candidato):
            return str(candidato)
    return "bash"


def caminho_bash(caminho):
    """O caminho para passar ao bash como argumento. No Windows, `C:/Dados/x/a.sh`: o `dirname` do Git Bash só separa
    pastas pela barra normal, e a barra invertida faria o `BASH_SOURCE` apontar para o lugar errado."""
    if plataforma.eh_windows():
        return PureWindowsPath(str(caminho)).as_posix()
    return str(caminho)


def caminho_msys(caminho):
    """O caminho como o Git Bash o imprime: `C:\\Dados\\x\\a.sh` vira `/c/Dados/x/a.sh`. Fora do Windows, o texto de
    sempre. Serve para comparar o que um script de shell escreveu (`pwd`, `$0`) com um `Path` do teste."""
    if not plataforma.eh_windows():
        return str(caminho)
    puro = PureWindowsPath(str(caminho))
    unidade = puro.drive
    if len(unidade) == 2 and unidade[1] == ":":
        resto = puro.as_posix()[len(unidade):]
        return "/" + unidade[0].lower() + resto
    return puro.as_posix()


BASH = achar_bash()
