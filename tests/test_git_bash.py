"""tests/fixtures/git_bash.py: o bash dos testes não pode ser o lançador do WSL (W2), simulado no Mac e no Linux."""
import os
from pathlib import Path

import pytest

import plataforma
from tests.fixtures import git_bash as G


@pytest.fixture
def windows(monkeypatch):
    monkeypatch.setattr(plataforma, "_sistema", lambda: "win32")


def _bash(pasta):
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / "bash.exe"
    arq.write_bytes(b"MZ")
    return arq


def _sem_git(nome, path=None):
    return None


@pytest.mark.parametrize("caminho", [
    r"C:\Windows\System32\bash.exe",
    r"c:\windows\system32\BASH.EXE",
    "C:/Windows/Sysnative/bash.exe",
    r"C:\Dados\ana\AppData\Local\Microsoft\WindowsApps\bash.exe",
])
def test_o_lancador_do_wsl_e_reconhecido(caminho):
    assert G.eh_lancador_do_wsl(caminho)


@pytest.mark.parametrize("caminho", [
    r"C:\Program Files\Git\bin\bash.exe",
    r"C:\Program Files\Git\usr\bin\bash.exe",
    "D:/tools/git/bin/bash.exe",
])
def test_o_git_bash_nao_e_confundido_com_o_wsl(caminho):
    assert not G.eh_lancador_do_wsl(caminho)


def test_no_windows_o_bash_do_system32_perde_para_o_do_git_mesmo_vindo_primeiro(tmp_path, windows):
    wsl = _bash(tmp_path / "Windows" / "System32")
    git = _bash(tmp_path / "Git" / "bin")
    path = os.pathsep.join([str(wsl.parent), str(git.parent)])
    assert G.achar_bash(path=path, which=_sem_git) == str(git)


def test_no_windows_acha_o_git_bash_pela_pasta_do_git_quando_o_path_so_tem_o_wsl(tmp_path, windows):
    wsl = _bash(tmp_path / "Windows" / "System32")
    git = _bash(tmp_path / "Programas" / "Git" / "bin")
    git_exe = tmp_path / "Programas" / "Git" / "cmd" / "git.exe"
    git_exe.parent.mkdir(parents=True)
    git_exe.write_bytes(b"MZ")

    def which(nome, path=None):
        return str(git_exe) if nome == "git" else None
    assert G.achar_bash(path=str(wsl.parent), which=which) == str(git)


def test_no_windows_sem_nenhum_bash_bom_devolve_bash_e_nunca_o_wsl(tmp_path, windows, monkeypatch):
    for variavel in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)", "LOCALAPPDATA"):
        monkeypatch.delenv(variavel, raising=False)
    wsl = _bash(tmp_path / "Windows" / "System32")
    assert G.achar_bash(path=str(wsl.parent), which=_sem_git) == "bash"


def test_fora_do_windows_o_bash_e_o_de_sempre(monkeypatch):
    monkeypatch.setattr(plataforma, "_sistema", lambda: "darwin")
    achado = G.achar_bash(path="")
    assert achado == "/bin/bash" or achado == "bash"


def test_o_bash_deste_sistema_roda(tmp_path):
    import subprocess
    r = subprocess.run([G.BASH, "-c", "echo ok"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       encoding="utf-8", errors="replace", timeout=60)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stdout


def test_caminho_bash_no_windows_usa_barra_normal_e_mantem_a_unidade(windows):
    assert G.caminho_bash(r"D:\a\repo\scripts\dev\x.sh") == "D:/a/repo/scripts/dev/x.sh"
    assert G.caminho_bash(r"C:\Dados\ana\meu repo\a.sh") == "C:/Dados/ana/meu repo/a.sh"


def test_caminho_bash_fora_do_windows_e_o_texto_de_sempre(monkeypatch):
    monkeypatch.setattr(plataforma, "_sistema", lambda: "linux")
    assert G.caminho_bash(Path("/tmp/x/a.sh")) == str(Path("/tmp/x/a.sh"))


def test_caminho_msys_traduz_a_unidade(windows):
    assert G.caminho_msys(r"C:\Dados\ana\meu repo\scripts") == "/c/Dados/ana/meu repo/scripts"
    assert G.caminho_msys("D:/a/repo") == "/d/a/repo"


def test_caminho_msys_fora_do_windows_e_o_texto_de_sempre(monkeypatch):
    monkeypatch.setattr(plataforma, "_sistema", lambda: "darwin")
    assert G.caminho_msys("/var/x/y") == "/var/x/y"
