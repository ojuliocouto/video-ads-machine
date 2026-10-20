"""setup.sh no Git Bash do Windows (W1.A): venv em .venv/Scripts, Python que não é o atalho da Microsoft Store,
dicas com winget (nunca brew nem apt) e transcritor faster-whisper.

O setup roda no Mac, mas com um `uname` falso que responde como o Git Bash (MINGW64_NT) e com executáveis falsos no PATH.
As funções de detecção são testadas por `source` do setup.sh (ele não roda os passos quando é carregado por `source`).
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import plataforma
from tests.fixtures.plataforma import exe_falso
from tests.onboarding import test_setup as base

RAIZ_REAL = base.RAIZ_REAL
SETUP_REAL = base.SETUP_REAL
BASH = base.BASH
MINGW = ("MINGW64_NT-10.0-26100", "x86_64")
FERRAMENTAS = ("dirname", "sed", "head", "tr", "cat", "cut", "wc", "grep", "cksum", "mkdir", "cp", "ls", "rm", "mv")

pytestmark = pytest.mark.skipif(plataforma.eh_windows(), reason="usa executáveis falsos em sh; o Windows real roda o job de CI")


class Ambiente(object):
    """Um repo falso com o setup.sh dentro, um PATH só com executáveis falsos e as ferramentas básicas do sistema."""

    def __init__(self, tmp_path, uname=MINGW):
        self.base = tmp_path.resolve()
        self.repo = self.base / "meu repo"
        (self.repo / "scripts").mkdir(parents=True)
        shutil.copy(str(SETUP_REAL), str(self.repo / "scripts" / "setup.sh"))
        (self.repo / "package.json").write_text('{"dependencies": {"hyperframes": "0.7.56"}}\n')
        (self.repo / "requirements.txt").write_text("numpy\n")
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.ferramentas = self.base / "ferramentas"
        self.ferramentas.mkdir()
        for nome in FERRAMENTAS:
            origem = shutil.which(nome)
            if origem:
                (self.ferramentas / nome).symlink_to(origem)
        uname_falso = self.bin / "uname"
        uname_falso.write_text(base.UNAME)
        uname_falso.chmod(0o755)
        self.uname = uname

    def python_bom(self, pasta=None, nome="python.exe"):
        return exe_falso(pasta or (self.base / "Python312"), nome, "Python 3.12.0", 0)

    def fonte(self, comando, path_extra=()):
        """Carrega o setup.sh com `source` e roda `comando`. Devolve (stdout, código)."""
        env = {"PATH": os.pathsep.join([str(self.bin)] + [str(p) for p in path_extra] + [str(self.ferramentas)]),
               "HOME": str(self.base), "STUB_UNAME_S": self.uname[0], "STUB_UNAME_M": self.uname[1], "LC_ALL": "C"}
        r = subprocess.run([BASH, "-c", 'source "%s/scripts/setup.sh"; %s' % (self.repo, comando)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, env=env, timeout=60)
        return r.stdout.strip(), r.returncode


@pytest.fixture
def amb(tmp_path):
    return Ambiente(tmp_path)


# --- qual Python cria o .venv ---------------------------------------------------------------------------------------

def test_windows_usa_o_python3_quando_ele_e_de_verdade(amb):
    python3 = exe_falso(amb.bin, "python3", "", 0)
    saida, _ = amb.fonte("escolher_python")
    assert saida == str(python3)


def test_windows_rejeita_o_atalho_da_microsoft_store_e_cai_no_py_launcher(amb):
    loja = exe_falso(amb.base / "AppData" / "Local" / "Microsoft" / "WindowsApps", "python3", "", 0)
    bom = amb.python_bom()
    exe_falso(amb.bin, "py", str(bom), 0)
    saida, _ = amb.fonte("escolher_python", path_extra=[loja.parent])
    assert saida == str(bom)


def test_windows_rejeita_python3_que_falha_no_import_sys(amb):
    exe_falso(amb.bin, "python3", "Python was not found", 49)
    bom = amb.python_bom()
    exe_falso(amb.bin, "py", str(bom), 0)
    saida, _ = amb.fonte("escolher_python")
    assert saida == str(bom)


def test_windows_sem_py_cai_no_python_do_path(amb):
    exe_falso(amb.bin, "python3", "", 49)
    exe_falso(amb.bin, "py", "", 1)
    python = exe_falso(amb.bin, "python", "", 0)
    saida, _ = amb.fonte("escolher_python")
    assert saida == str(python)


def test_windows_o_atalho_da_store_em_python_tambem_e_rejeitado(amb):
    loja = exe_falso(amb.base / "WindowsApps", "python", "", 0)
    saida, _ = amb.fonte("escolher_python", path_extra=[loja.parent])
    assert saida == ""


def test_windows_sem_nenhum_python_devolve_vazio(amb):
    saida, _ = amb.fonte("escolher_python")
    assert saida == ""


def test_o_py_launcher_que_devolve_caminho_inexistente_e_ignorado(amb):
    exe_falso(amb.bin, "py", str(amb.base / "nao existe" / "python.exe"), 0)
    saida, _ = amb.fonte("escolher_python")
    assert saida == ""


# --- o Python do .venv -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("subpasta,nome", [("Scripts", "python.exe"), ("bin", "python")])
def test_acha_o_python_do_venv_nos_dois_layouts(amb, subpasta, nome):
    alvo = exe_falso(amb.repo / ".venv" / subpasta, nome, "", 0)
    saida, _ = amb.fonte('venv_ok && echo "$VENV_PY"')
    assert saida == str(alvo)


def test_sem_venv_o_venv_ok_falha(amb):
    _, codigo = amb.fonte("venv_ok")
    assert codigo != 0


# --- dicas de instalação ---------------------------------------------------------------------------------------------

def test_dicas_do_windows_usam_winget_e_nunca_brew_nem_apt(amb):
    saida, _ = amb.fonte("dica_python; dica_node; dica_ffmpeg; dica_venv")
    for cmd in ("winget install -e --id Python.Python.3.12", "winget install -e --id OpenJS.NodeJS.LTS",
                "winget install -e --id Gyan.FFmpeg"):
        assert cmd in saida
    assert "brew" not in saida and "apt" not in saida


def test_dicas_do_mac_continuam_com_brew(tmp_path):
    amb = Ambiente(tmp_path, uname=("Darwin", "arm64"))
    saida, _ = amb.fonte("dica_python; dica_node; dica_ffmpeg")
    assert "brew install python@3.12" in saida and "brew install node@22" in saida and "brew install ffmpeg" in saida
    assert "winget" not in saida


# --- a execução inteira no "Windows" ---------------------------------------------------------------------------------------

PY_SISTEMA_WIN = base.PY_SISTEMA.replace('mkdir -p "$3/bin"; cp "$STUB_DIR/venv-python" "$3/bin/python"; chmod +x "$3/bin/python"',
                                         'mkdir -p "$3/Scripts"; cp "$STUB_DIR/venv-python" "$3/Scripts/python.exe"; chmod +x "$3/Scripts/python.exe"')
PY_VENV_WIN = '#!/bin/bash\nif [ "$1" = "-c" ]; then cat "$STUB_DIR/hfcli" 2>/dev/null; exit 0; fi\n' + base.PY_VENV.split("\n", 1)[1]


def mundo_windows(tmp_path, cli_do_hyperframes=None):
    m = base.Mundo(tmp_path.resolve() / "meu repo")
    assert PY_SISTEMA_WIN != base.PY_SISTEMA
    (m.bin / "python3").write_text(PY_SISTEMA_WIN)
    (m.bin / "venv-python").write_text(PY_VENV_WIN)
    (m.bin / "hfcli").write_text(cli_do_hyperframes or "")
    return m


def test_windows_cria_o_venv_em_scripts_e_fecha_o_setup_sem_brew(tmp_path):
    m = mundo_windows(tmp_path)
    r = m.rodar(uname=MINGW)
    assert r.returncode == 0, r.stdout
    assert (m.repo / ".venv" / "Scripts" / "python.exe").is_file()
    assert not (m.repo / ".venv" / "bin").exists()
    assert m.n_pip("faster-whisper") == 0, "a transcrição é a Groq: o setup não instala transcritor"
    assert "brew" not in r.stdout and "tudo pronto" in r.stdout


def test_windows_segunda_execucao_nao_reinstala_nada(tmp_path):
    m = mundo_windows(tmp_path)
    assert m.rodar(uname=MINGW).returncode == 0
    antes = {k: m.n(k) for k in ("python3 -m venv", "venv-python -m pip install", "npm ", "curl")}
    r = m.rodar(uname=MINGW)
    assert r.returncode == 0, r.stdout
    assert {k: m.n(k) for k in antes} == antes


def test_windows_roda_o_browser_ensure_pelo_node_e_pelo_cli_do_pacote(tmp_path):
    m = mundo_windows(tmp_path, cli_do_hyperframes="C:\\Dados\\repo\\node_modules\\hyperframes\\dist\\cli.js\r\n")
    r = m.rodar(uname=MINGW)
    assert r.returncode == 0, r.stdout
    assert m.chamadas("node C:\\Dados\\repo\\node_modules\\hyperframes\\dist\\cli.js browser ensure"), m.log.read_text()
    assert m.n("hyperframes browser ensure") == 0, "no Windows o .bin é um script de shell: não é ele que roda"


def test_windows_sem_cli_do_pacote_cai_no_bin_do_npm(tmp_path):
    m = mundo_windows(tmp_path)
    assert m.rodar(uname=MINGW).returncode == 0
    assert m.n("hyperframes browser ensure") == 1


def test_windows_node_velho_aponta_o_winget_do_node(tmp_path):
    m = mundo_windows(tmp_path)
    r = m.rodar(uname=MINGW, node="v20.1.0")
    assert r.returncode == 1
    fim = base.resumo(r.stdout)
    assert "winget install -e --id OpenJS.NodeJS.LTS" in fim and "brew" not in fim


def test_windows_sem_python_aponta_o_winget_do_python(tmp_path):
    m = mundo_windows(tmp_path)
    (m.bin / "python3").unlink()
    ferramentas = tmp_path / "so-sistema"
    ferramentas.mkdir()
    for nome in FERRAMENTAS:
        origem = shutil.which(nome)
        if origem:
            (ferramentas / nome).symlink_to(origem)
    env = {"PATH": "%s:%s" % (m.bin, ferramentas), "HOME": str(m.home), "STUB_LOG": str(m.log), "STUB_DIR": str(m.bin),
           "STUB_UNAME_S": MINGW[0], "STUB_UNAME_M": MINGW[1], "LC_ALL": "C"}
    r = subprocess.run([BASH, str(m.repo / "scripts" / "setup.sh")], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       universal_newlines=True, env=env, timeout=60)
    assert r.returncode == 1
    assert "winget install -e --id Python.Python.3.12" in base.resumo(r.stdout) and "brew" not in r.stdout


def test_checar_no_windows_nao_cria_nada(tmp_path):
    m = mundo_windows(tmp_path)
    r = m.rodar("--checar", uname=MINGW)
    assert r.returncode == 1
    assert not (m.repo / ".venv").exists() and "brew" not in r.stdout


# --- o arquivo em si -------------------------------------------------------------------------------------------------------

def test_setup_sh_tem_so_fim_de_linha_lf_e_sintaxe_valida():
    dados = SETUP_REAL.read_bytes()
    assert b"\r" not in dados
    r = subprocess.run([BASH, "-n", str(SETUP_REAL)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    assert r.returncode == 0, r.stdout
