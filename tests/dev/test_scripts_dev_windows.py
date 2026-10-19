"""testar_limpo.sh e como_aluno.sh no Git Bash do Windows (W1.A), com `uname` e executáveis falsos rodando no Mac.

testar_limpo.sh roda com `--dry-run`: ele monta o ambiente, escolhe o Python e imprime o que faria, sem rodar a suíte.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import plataforma
from tests.fixtures.plataforma import exe_falso

RAIZ_REAL = Path(__file__).resolve().parent.parent.parent
TESTAR = RAIZ_REAL / "scripts" / "dev" / "testar_limpo.sh"
COMO_ALUNO = RAIZ_REAL / "scripts" / "dev" / "como_aluno.sh"
BASH = "/bin/bash" if Path("/bin/bash").exists() else shutil.which("bash")
UNAME = '#!/bin/bash\ncase "$1" in -s) echo "$STUB_UNAME_S" ;; -m) echo "$STUB_UNAME_M" ;; *) echo "$STUB_UNAME_S" ;; esac\n'
MINGW = "MINGW64_NT-10.0-26100"

pytestmark = pytest.mark.skipif(plataforma.eh_windows(), reason="usa executáveis falsos em sh; o Windows real roda o job de CI")


class Cenario(object):
    def __init__(self, tmp_path, sistema=MINGW):
        self.base = tmp_path.resolve()
        self.repo = self.base / "meu repo"
        (self.repo / "scripts" / "dev").mkdir(parents=True)
        shutil.copy(str(TESTAR), str(self.repo / "scripts" / "dev" / "testar_limpo.sh"))
        self.bin = self.base / "bin"
        self.bin.mkdir()
        (self.bin / "uname").write_text(UNAME)
        (self.bin / "uname").chmod(0o755)
        self.sistema = sistema

    def venv(self, subpasta, nome):
        return exe_falso(self.repo / ".venv" / subpasta, nome, "Python 3.12.0", 0)

    def dry_run(self, *args, extra_env=None, path_extra=()):
        env = {"PATH": os.pathsep.join([str(self.bin)] + [str(p) for p in path_extra] + ["/usr/bin", "/bin"]),
               "HOME": str(self.base), "LC_ALL": "C", "STUB_UNAME_S": self.sistema, "STUB_UNAME_M": "x86_64",
               "TMPDIR": str(self.base)}
        env.update(extra_env or {})
        r = subprocess.run([BASH, str(self.repo / "scripts" / "dev" / "testar_limpo.sh"), "--dry-run"] + list(args),
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, env=env, timeout=60)
        return r

    @staticmethod
    def campo(saida, prefixo):
        for linha in saida.splitlines():
            if linha.startswith(prefixo):
                return linha[len(prefixo):].strip()
        raise AssertionError("sem a linha %r em:\n%s" % (prefixo, saida))


@pytest.fixture
def cen(tmp_path):
    return Cenario(tmp_path)


# --- qual Python -------------------------------------------------------------------------------------------------------------

def test_windows_acha_o_python_do_venv_em_scripts(cen):
    py = cen.venv("Scripts", "python.exe")
    r = cen.dry_run()
    assert r.returncode == 0, r.stdout
    assert str(py) in cen.campo(r.stdout, "[testar_limpo] python:")


def test_mac_acha_o_python_do_venv_em_bin(tmp_path):
    c = Cenario(tmp_path, sistema="Darwin")
    py = c.venv("bin", "python")
    r = c.dry_run()
    assert r.returncode == 0, r.stdout
    assert str(py) in c.campo(r.stdout, "[testar_limpo] python:")


def test_a_variavel_vam_python_teste_manda_no_python(cen):
    cen.venv("Scripts", "python.exe")
    outro = exe_falso(cen.base / "outro", "meu-python", "Python 3.11.0", 0)
    r = cen.dry_run(extra_env={"VAM_PYTHON_TESTE": str(outro)})
    assert str(outro) in cen.campo(r.stdout, "[testar_limpo] python:")


def test_windows_sem_venv_rejeita_o_atalho_da_store_e_usa_o_py(cen):
    loja = exe_falso(cen.base / "AppData" / "WindowsApps", "python3", "", 0)
    bom = exe_falso(cen.base / "Py312", "python.exe", "Python 3.12.0", 0)
    exe_falso(cen.bin, "py", str(bom), 0)
    r = cen.dry_run(path_extra=[loja.parent])
    assert r.returncode == 0, r.stdout
    assert str(bom) in cen.campo(r.stdout, "[testar_limpo] python:")


def test_sem_venv_usa_o_python_do_path_que_tem_as_dependencias_nao_um_caminho_fixo(tmp_path):
    """Causa do CI do Linux vermelho: o script usava /usr/bin/python3, que não tinha numpy nem pytest."""
    c = Cenario(tmp_path, sistema="Linux")
    sem_deps = c.bin / "python3"
    sem_deps.write_text('#!/bin/sh\ncase "$*" in *numpy*) exit 1;; esac\necho "Python 3.9.0"\n')
    sem_deps.chmod(0o755)
    com_deps = c.bin / "python"
    com_deps.write_text('#!/bin/sh\necho "Python 3.12.0"\n')
    com_deps.chmod(0o755)
    r = c.dry_run()
    assert r.returncode == 0, r.stdout
    assert str(com_deps) in c.campo(r.stdout, "[testar_limpo] python:"), r.stdout
    assert "AVISO: sem pytest" not in r.stdout


def test_sem_python_nenhum_o_script_diz_o_que_instalar(tmp_path):
    c = Cenario(tmp_path, sistema=MINGW)
    ferramentas = c.base / "ferramentas"
    ferramentas.mkdir()
    for nome in ("dirname", "sed", "head", "tr", "cat", "cut", "grep", "env", "id", "mktemp", "rm"):
        if shutil.which(nome):
            (ferramentas / nome).symlink_to(shutil.which(nome))
    env = {"PATH": "%s:%s" % (c.bin, ferramentas), "HOME": str(c.base), "STUB_UNAME_S": MINGW, "STUB_UNAME_M": "x86_64"}
    r = subprocess.run([BASH, str(c.repo / "scripts" / "dev" / "testar_limpo.sh"), "--dry-run"], stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, universal_newlines=True, env=env, timeout=60)
    assert r.returncode == 1 and "winget install -e --id Python.Python.3.12" in r.stdout and "brew" not in r.stdout


# --- ambiente hermético -----------------------------------------------------------------------------------------------------------

def test_home_e_userprofile_apontam_para_a_mesma_pasta_temporaria_e_o_python_vai_em_utf8(cen):
    cen.venv("Scripts", "python.exe")
    r = cen.dry_run()
    home, perfil = cen.campo(r.stdout, "HOME="), cen.campo(r.stdout, "USERPROFILE=")
    assert home and home == perfil
    assert "vam-home." in home and home != str(cen.base)
    assert cen.campo(r.stdout, "PYTHONUTF8=") == "1"
    assert not Path(home).exists(), "a pasta temporária some ao fim"


def test_sem_tmpdir_valido_a_pasta_temporaria_cai_no_temp(cen):
    cen.venv("Scripts", "python.exe")
    temp = cen.base / "meu temp"
    temp.mkdir()
    # um mktemp que só funciona dentro do TEMP: o mktemp -d puro e o do TMPDIR falham, como numa máquina sem /tmp
    (cen.bin / "mktemp").write_text('#!/bin/sh\ncase "$*" in *"meu temp"*) exec /usr/bin/mktemp "$@";; esac\nexit 1\n')
    (cen.bin / "mktemp").chmod(0o755)
    r = cen.dry_run(extra_env={"TMPDIR": str(cen.base / "nao-existe" / "x"), "TEMP": str(temp)})
    assert r.returncode == 0, r.stdout
    assert cen.campo(r.stdout, "HOME=").startswith(str(temp))


def test_nao_usa_pwd_nem_getuid():
    codigo = TESTAR.read_text(encoding="utf-8")
    assert "import pwd" not in codigo and "getuid" not in codigo


def test_o_user_site_vem_da_home_real_mesmo_com_home_falso_exportado(cen):
    """O user site (onde o pytest costuma morar) é calculado antes de trocar o HOME."""
    cen.venv("bin", "python")
    r = cen.dry_run(extra_env={"HOME": str(cen.base / "home falsa de quem chamou")})
    assert "PYTHONUSERBASE=" in r.stdout


# --- como_aluno.sh -----------------------------------------------------------------------------------------------------------------

def _como_aluno(tmp_path, sistema, comando, extra_env=None):
    base = tmp_path.resolve()
    (base / "bin").mkdir(exist_ok=True)
    (base / "bin" / "uname").write_text(UNAME)
    (base / "bin" / "uname").chmod(0o755)
    aluno = base / "aluno"
    aluno.mkdir(exist_ok=True)
    env = {"PATH": "%s:%s:/usr/bin:/bin" % (base / "bin", base / "dono" / ".local" / "bin"), "HOME": str(base / "dono"),
           "STUB_UNAME_S": sistema, "STUB_UNAME_M": "x86_64", "VAM_HOME_ALUNO": str(aluno), "LANG": "C",
           "CLAUDE_CONFIG_DIR": "X", "VAM_ESTADO": "Y", "OPENAI_API_KEY": "k", "HEYGEN_API_KEY": "h", "GROQ_API_KEY": "g",
           "HF_HOME": "hf", "SystemRoot": "C:\\Windows"}
    env.update(extra_env or {})
    r = subprocess.run([BASH, str(COMO_ALUNO), "bash", "-c", comando], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       universal_newlines=True, env=env, timeout=60)
    return r, aluno


def test_como_aluno_no_windows_nao_zera_o_ambiente_nem_forca_o_path_do_homebrew(tmp_path):
    r, aluno = _como_aluno(tmp_path, MINGW, 'echo "PATH=$PATH"; echo "SR=$SystemRoot"')
    assert r.returncode == 0, r.stdout
    assert "/opt/homebrew" not in r.stdout
    assert "SR=C:\\Windows" in r.stdout, "o Windows precisa de SystemRoot e afins"
    assert ".local/bin" not in r.stdout, "ferramenta do dono fica fora do PATH do aluno"


def test_como_aluno_no_windows_aponta_home_e_userprofile_e_limpa_o_que_e_do_dono(tmp_path):
    r, aluno = _como_aluno(tmp_path, MINGW,
                           'echo "H=$HOME"; echo "U=$USERPROFILE"; echo "C=${CLAUDE_CONFIG_DIR-vazio}"; '
                           'echo "V=${VAM_ESTADO-vazio}"; echo "O=${OPENAI_API_KEY-vazio}"; echo "HG=$HEYGEN_API_KEY"; '
                           'echo "GQ=$GROQ_API_KEY"; echo "HF=$HF_HOME"; echo "A=$VAM_HOME_ALUNO"')
    linhas = dict(l.split("=", 1) for l in r.stdout.splitlines() if "=" in l)
    assert linhas["H"] == str(aluno) and linhas["U"] == str(aluno)
    assert linhas["C"] == "vazio" and linhas["V"] == "vazio" and linhas["O"] == "vazio"
    assert (linhas["HG"], linhas["GQ"], linhas["HF"]) == ("h", "g", "hf")


def test_como_aluno_no_mac_continua_com_env_i_e_path_do_homebrew(tmp_path):
    r, aluno = _como_aluno(tmp_path, "Darwin", 'echo "PATH=$PATH"; echo "SR=${SystemRoot-vazio}"; echo "O=${OPENAI_API_KEY-vazio}"; '
                                               'echo "H=$HOME"; echo "HG=$HEYGEN_API_KEY"')
    assert "PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/local/bin" in r.stdout
    assert "SR=vazio" in r.stdout and "O=vazio" in r.stdout and "HG=h" in r.stdout and "H=%s" % aluno in r.stdout


def test_como_aluno_sem_home_do_aluno_recusa_com_2(tmp_path):
    r = subprocess.run([BASH, str(COMO_ALUNO), "true"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       universal_newlines=True, env={"PATH": "/usr/bin:/bin"})
    assert r.returncode == 2


@pytest.mark.parametrize("arquivo", [TESTAR, COMO_ALUNO])
def test_os_scripts_dev_tem_lf_sintaxe_valida_e_sem_travessao(arquivo):
    dados = arquivo.read_bytes()
    assert b"\r" not in dados
    texto = dados.decode("utf-8")
    assert "\u2014" not in texto and "\u2013" not in texto
    assert subprocess.run([BASH, "-n", str(arquivo)]).returncode == 0
