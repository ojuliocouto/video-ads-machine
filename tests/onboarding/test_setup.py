"""setup.sh (W1.D): idempotente, resiliente, com .venv e sem instalar nada de verdade.

O setup roda de verdade (bash), mas num repo falso e com um PATH falso: `python3`, `npm`,
`node`, `curl` e o `hyperframes` são stubs que só gravam a chamada num log. Assim dá para
provar, sem rede e sem instalar nada, que:

  - a segunda execução não reinstala nada;
  - o Python do sistema (PEP 668, "externally-managed-environment") nunca recebe `pip install`;
  - um passo que falha não derruba os seguintes, e o resumo no fim lista o conserto de cada um.
"""
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

RAIZ_REAL = Path(__file__).resolve().parent.parent.parent
SETUP_REAL = RAIZ_REAL / "scripts" / "setup.sh"
BASH = "/bin/bash" if Path("/bin/bash").exists() else shutil.which("bash")

PY_SISTEMA = r'''#!/bin/bash
echo "python3 $*" >> "$STUB_LOG"
falha() { case ",$STUB_FAIL," in *,"$1",*) return 0;; esac; return 1; }
case "$1" in
  -c) if [ -n "$STUB_PYOLD" ]; then exit 1; fi; exit 0 ;;
  -m)
    case "$2" in
      venv)
        if falha venv; then echo "venv indisponível" >&2; exit 1; fi
        mkdir -p "$3/bin"; cp "$STUB_DIR/venv-python" "$3/bin/python"; chmod +x "$3/bin/python"
        exit 0 ;;
      pip)
        echo "error: externally-managed-environment" >&2; exit 1 ;;
    esac ;;
  *init_local.py) if falha init; then exit 1; fi; mkdir -p _local; exit 0 ;;
  *som_cortes.py) if falha sons; then exit 1; fi
                  mkdir -p _local/dados/assets/som; touch _local/dados/assets/som/whoosh.wav; exit 0 ;;
esac
exit 0
'''

PY_VENV = r'''#!/bin/bash
echo "venv-python $*" >> "$STUB_LOG"
falha() { case ",$STUB_FAIL," in *,"$1",*) return 0;; esac; return 1; }
case "$1" in
  -m) case "$2" in pip) if falha pip; then echo "pip falhou" >&2; exit 1; fi; exit 0 ;; esac ;;
  *init_local.py) if falha init; then exit 1; fi; mkdir -p _local; exit 0 ;;
  *som_cortes.py) if falha sons; then exit 1; fi
                  mkdir -p _local/dados/assets/som; touch _local/dados/assets/som/whoosh.wav; exit 0 ;;
esac
exit 0
'''

NPM = r'''#!/bin/bash
echo "npm $*" >> "$STUB_LOG"
case ",$STUB_FAIL," in *,npm,*) echo "npm ERR! rede" >&2; exit 1;; esac
mkdir -p node_modules/.bin node_modules/hyperframes
cp "$STUB_DIR/hyperframes" node_modules/.bin/hyperframes; chmod +x node_modules/.bin/hyperframes
echo '{"name":"hyperframes","version":"0.7.56"}' > node_modules/hyperframes/package.json
exit 0
'''

HYPERFRAMES = r'''#!/bin/bash
echo "hyperframes $*" >> "$STUB_LOG"
case "$1" in
  --version) echo "0.7.56"; exit 0 ;;
  browser) case ",$STUB_FAIL," in *,ensure,*) exit 1;; esac ;;
esac
exit 0
'''

NODE = r'''#!/bin/bash
echo "node $*" >> "$STUB_LOG"
echo "${STUB_NODE:-v22.11.0}"
'''

CURL = r'''#!/bin/bash
echo "curl $*" >> "$STUB_LOG"
case ",$STUB_FAIL," in *,curl,*) exit 6;; esac
saida=""; prev=""
for a in "$@"; do if [ "$prev" = "-o" ]; then saida="$a"; fi; prev="$a"; done
[ -n "$saida" ] && { echo "/* gsap stub */"; head -c 1500 /dev/zero | tr '\0' 'x'; } > "$saida"
exit 0
'''


@pytest.fixture
def mundo(tmp_path):
    """Repo falso + PATH falso. Devolve um objeto com `rodar(...)` e acesso ao log."""
    return Mundo(tmp_path.resolve() / "meu repo")      # com espaço no caminho, de propósito


class Mundo(object):
    def __init__(self, repo):
        self.repo = repo
        base = repo.parent
        self.bin = base / "bin"
        self.log = base / "chamadas.log"
        self.home = base / "home"
        self.home.mkdir(parents=True)
        self.bin.mkdir()
        self.log.write_text("")
        for nome, conteudo in (("python3", PY_SISTEMA), ("venv-python", PY_VENV), ("npm", NPM),
                               ("hyperframes", HYPERFRAMES), ("node", NODE), ("curl", CURL)):
            alvo = self.bin / nome
            alvo.write_text(conteudo)
            alvo.chmod(0o755)
        (repo / "scripts").mkdir(parents=True)
        shutil.copy(str(SETUP_REAL), str(repo / "scripts" / "setup.sh"))
        (repo / "scripts" / "init_local.py").write_text("")
        (repo / "scripts" / "som_cortes.py").write_text("")
        (repo / "package.json").write_text(
            '{\n  "dependencies": {\n    "hyperframes": "0.7.56"\n  }\n}\n')
        (repo / "requirements.txt").write_text("numpy\nopencv-python-headless\npillow\nscipy\n")
        (repo / ".env.example").write_text("# chave\nHEYGEN_API_KEY=\n")
        (repo / "templates" / "reel-editorial").mkdir(parents=True)
        (repo / "templates" / "reel-editorial" / "index.html").write_text(
            '<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>')

    def rodar(self, *args, falhas="", node=None, python_velho=False):
        env = {"PATH": "{}:/usr/bin:/bin".format(self.bin), "HOME": str(self.home),
               "STUB_LOG": str(self.log), "STUB_DIR": str(self.bin), "STUB_FAIL": falhas,
               "LC_ALL": "C"}
        if node:
            env["STUB_NODE"] = node
        if python_velho:
            env["STUB_PYOLD"] = "1"
        return subprocess.run([BASH, str(self.repo / "scripts" / "setup.sh")] + list(args),
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              universal_newlines=True, env=env, timeout=60)

    def chamadas(self, prefixo):
        return [l for l in self.log.read_text().splitlines() if l.startswith(prefixo)]

    def n(self, prefixo):
        return len(self.chamadas(prefixo))


def resumo(saida):
    return saida.split("[setup] resumo", 1)[-1]


# --- primeira execução -----------------------------------------------------------------------------

def test_primeira_execucao_cria_venv_instala_e_prepara_tudo(mundo):
    r = mundo.rodar()
    assert r.returncode == 0, r.stdout
    assert mundo.n("python3 -m venv") == 1
    assert (mundo.repo / ".venv" / "bin" / "python").is_file()
    pip = mundo.chamadas("venv-python -m pip install")
    assert len(pip) == 1 and "requirements.txt" in pip[0]
    assert mundo.n("npm ") == 1
    assert "install" in mundo.chamadas("npm ")[0] or " i" in mundo.chamadas("npm ")[0]
    assert (mundo.repo / "node_modules" / ".bin" / "hyperframes").is_file()
    assert mundo.n("hyperframes browser ensure") == 1
    curl = mundo.chamadas("curl")
    assert len(curl) == 1 and "gsap@3.14.2/dist/gsap.min.js" in curl[0]
    assert (mundo.repo / "templates" / "_vendor" / "gsap.min.js").read_text().strip() != ""
    assert mundo.n("venv-python " + str(mundo.repo / "scripts" / "init_local.py")) == 1
    assert mundo.n("venv-python " + str(mundo.repo / "scripts" / "som_cortes.py")) == 1
    assert (mundo.repo / ".env").is_file()
    assert "[setup] resumo" in r.stdout and "tudo pronto" in r.stdout


def test_o_npm_instala_so_o_que_o_package_json_pina_sem_pacote_global(mundo):
    mundo.rodar()
    linha = mundo.chamadas("npm ")[0]
    assert "-g" not in linha and "--global" not in linha


def test_o_gsap_baixa_para_um_arquivo_temporario_e_so_entao_vira_o_arquivo_final(mundo):
    mundo.rodar()
    curl = mundo.chamadas("curl")[0]
    destino = re.search(r" -o (.+) https://", curl).group(1)
    assert not destino.endswith("templates/_vendor/gsap.min.js"), \
        "download parcial não pode virar o arquivo final"
    assert not list((mundo.repo / "templates" / "_vendor").glob("*.tmp*"))


def test_o_que_o_setup_gera_fica_invisivel_para_o_git(mundo):
    """O .gitignore da raiz não cobre .venv nem templates/_vendor: o setup esconde os dois."""
    mundo.rodar()
    for pasta in (mundo.repo / ".venv", mundo.repo / "templates" / "_vendor"):
        assert (pasta / ".gitignore").read_text().strip() == "*", pasta


def test_env_do_aluno_nunca_e_sobrescrito(mundo):
    (mundo.repo / ".env").write_text("HEYGEN_API_KEY=minha\n")
    mundo.rodar()
    assert (mundo.repo / ".env").read_text() == "HEYGEN_API_KEY=minha\n"


# --- idempotência ----------------------------------------------------------------------------------

def test_segunda_execucao_nao_reinstala_nada(mundo):
    assert mundo.rodar().returncode == 0
    antes = {k: mundo.n(k) for k in ("python3 -m venv", "venv-python -m pip install", "npm ",
                                     "curl")}
    r = mundo.rodar()
    assert r.returncode == 0, r.stdout
    depois = {k: mundo.n(k) for k in antes}
    assert depois == antes, (antes, depois)
    assert "já" in r.stdout


def test_requirements_alterado_reinstala_so_o_pip(mundo):
    mundo.rodar()
    (mundo.repo / "requirements.txt").write_text("numpy\nopencv-python-headless\npillow\nscipy\n"
                                                 "tqdm\n")
    mundo.rodar()
    assert mundo.n("venv-python -m pip install") == 2
    assert mundo.n("npm ") == 1 and mundo.n("python3 -m venv") == 1


def test_versao_do_hyperframes_mudou_no_package_json_reinstala(mundo):
    mundo.rodar()
    (mundo.repo / "package.json").write_text('{"dependencies": {"hyperframes": "0.7.57"}}')
    mundo.rodar()
    assert mundo.n("npm ") == 2


# --- PEP 668 ---------------------------------------------------------------------------------------

def test_python_do_sistema_recusa_pip_e_o_venv_resolve(mundo):
    r = mundo.rodar()
    assert r.returncode == 0, r.stdout
    assert mundo.n("python3 -m pip") == 0, "pip nunca pode ir para o Python do sistema"
    assert mundo.n("venv-python -m pip install") == 1
    assert "externally-managed" not in r.stdout


# --- um passo que falha não derruba os outros -----------------------------------------------------------

def test_npm_falhando_ainda_roda_pip_gsap_sons_e_init_local(mundo):
    r = mundo.rodar(falhas="npm")
    assert r.returncode == 1
    assert mundo.n("venv-python -m pip install") == 1
    assert mundo.n("curl") == 1
    assert mundo.n("venv-python " + str(mundo.repo / "scripts" / "init_local.py")) == 1
    assert mundo.n("venv-python " + str(mundo.repo / "scripts" / "som_cortes.py")) == 1
    assert mundo.n("hyperframes browser ensure") == 0, "sem o binário não há o que garantir"
    fim = resumo(r.stdout)
    assert "npm" in fim and "conserto:" in fim
    assert "bash scripts/setup.sh" in fim


def test_node_abaixo_de_22_pula_o_npm_e_o_resumo_diz_o_que_fazer(mundo):
    r = mundo.rodar(node="v20.1.0")
    assert r.returncode == 1
    assert mundo.n("npm ") == 0
    assert mundo.n("venv-python -m pip install") == 1
    fim = resumo(r.stdout)
    assert "Node" in fim and "22" in fim and "conserto:" in fim


def test_node_ausente_pula_o_npm_e_segue(mundo):
    (mundo.bin / "node").unlink()
    (mundo.bin / "npm").unlink()
    r = mundo.rodar()
    assert r.returncode == 1 and mundo.n("venv-python -m pip install") == 1
    assert "Node" in resumo(r.stdout)


def test_venv_falhando_ainda_roda_npm_gsap_sons_e_init_local_com_o_python_do_sistema(mundo):
    r = mundo.rodar(falhas="venv")
    assert r.returncode == 1
    assert mundo.n("npm ") == 1 and mundo.n("curl") == 1
    assert mundo.n("python3 " + str(mundo.repo / "scripts" / "init_local.py")) == 1
    assert mundo.n("python3 " + str(mundo.repo / "scripts" / "som_cortes.py")) == 1
    assert mundo.n("python3 -m pip") == 0
    assert ".venv" in resumo(r.stdout)


def test_python_do_sistema_velho_demais_nao_cria_o_venv(mundo):
    r = mundo.rodar(python_velho=True)
    assert r.returncode == 1 and mundo.n("python3 -m venv") == 0
    assert "3.9" in resumo(r.stdout)


def test_pip_falhando_nao_grava_a_marca_e_a_proxima_execucao_tenta_de_novo(mundo):
    r = mundo.rodar(falhas="pip")
    assert r.returncode == 1 and "pip" in resumo(r.stdout)
    assert mundo.n("npm ") == 1 and mundo.n("curl") == 1
    assert mundo.rodar().returncode == 0
    assert mundo.n("venv-python -m pip install") == 2


def test_browser_ensure_falhando_vira_falha_com_o_comando(mundo):
    r = mundo.rodar(falhas="ensure")
    assert r.returncode == 1
    assert "browser ensure" in resumo(r.stdout)


def test_init_local_e_sons_falhando_sao_listados_e_nao_se_travam_entre_si(mundo):
    r = mundo.rodar(falhas="init,sons")
    assert r.returncode == 1
    fim = resumo(r.stdout)
    assert "_local" in fim and "som" in fim.lower()


def test_gsap_que_nao_baixa_e_aviso_nao_derruba_o_setup(mundo):
    r = mundo.rodar(falhas="curl")
    assert r.returncode == 0, r.stdout
    assert "AVISO" in r.stdout and "gsap" in resumo(r.stdout).lower()
    assert not (mundo.repo / "templates" / "_vendor" / "gsap.min.js").exists()


# --- --checar ---------------------------------------------------------------------------------------

def test_checar_em_repo_novo_nao_instala_nada_e_lista_o_que_falta(mundo):
    r = mundo.rodar("--checar")
    assert r.returncode == 1
    for mutante in ("python3 -m venv", "venv-python", "npm ", "curl", "hyperframes"):
        assert mundo.n(mutante) == 0, mutante
    assert not (mundo.repo / ".venv").exists()
    assert not (mundo.repo / "node_modules").exists()
    assert not (mundo.repo / ".env").exists()
    fim = resumo(r.stdout)
    assert "bash scripts/setup.sh" in fim and ".venv" in fim and "HyperFrames" in fim


def test_checar_depois_do_setup_sai_0(mundo):
    assert mundo.rodar().returncode == 0
    n_antes = mundo.n("")
    r = mundo.rodar("--checar")
    assert r.returncode == 0, r.stdout
    novas = mundo.log.read_text().splitlines()[n_antes:]
    assert not [l for l in novas if l.startswith(("npm", "curl", "python3 -m venv",
                                                   "venv-python -m pip"))]


def test_checar_acusa_requirements_alterado(mundo):
    mundo.rodar()
    (mundo.repo / "requirements.txt").write_text("numpy\n")
    r = mundo.rodar("--checar")
    assert r.returncode == 1 and "requirements" in resumo(r.stdout)


# --- --cinema-plus e argumentos --------------------------------------------------------------------------

def test_cinema_plus_e_reservado_e_nao_instala_nada_alem_do_normal(mundo):
    r = mundo.rodar("--cinema-plus")
    assert r.returncode == 0, r.stdout
    assert "--cinema-plus" in r.stdout and "reservado" in r.stdout
    assert mundo.n("venv-python -m pip install") == 1 and mundo.n("npm ") == 1


def test_argumento_desconhecido_sai_2_e_nao_faz_nada(mundo):
    r = mundo.rodar("--bobagem")
    assert r.returncode == 2 and "--checar" in r.stdout
    assert mundo.log.read_text() == ""


# --- o arquivo em si --------------------------------------------------------------------------------------

def test_setup_sh_tem_sintaxe_valida():
    r = subprocess.run([BASH, "-n", str(SETUP_REAL)], stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, universal_newlines=True)
    assert r.returncode == 0, r.stdout


def test_setup_sh_compativel_com_o_bash_3_2_do_macos():
    codigo = SETUP_REAL.read_text(encoding="utf-8")
    sem_comentarios = "\n".join(l for l in codigo.splitlines() if not l.strip().startswith("#"))
    for proibido in ("declare -A", "mapfile", "readarray", ",,}", "^^}"):
        assert proibido not in sem_comentarios, proibido
    assert not re.search(r"(^|\s)timeout\s", sem_comentarios)
    assert "set -e" not in sem_comentarios, "nenhum passo pode abortar os seguintes"


def test_setup_sh_sem_travessao_nem_nome_de_cliente():
    codigo = SETUP_REAL.read_text(encoding="utf-8")
    assert "\u2014" not in codigo and "\u2013" not in codigo


def test_setup_sh_nao_instala_pacote_global_nem_escreve_na_home():
    codigo = SETUP_REAL.read_text(encoding="utf-8")
    assert "npm i -g" not in codigo and "install -g" not in codigo and "--global" not in codigo
    assert "~/" not in codigo and "$HOME" not in codigo


# --- requirements ------------------------------------------------------------------------------------------

def test_requirements_da_raiz_tem_o_minimo_e_comenta_os_extras():
    linhas = (RAIZ_REAL / "requirements.txt").read_text(encoding="utf-8").splitlines()
    ativas = {l.strip().split("=")[0].split(">")[0].split("<")[0].lower()
              for l in linhas if l.strip() and not l.strip().startswith("#")}
    assert ativas == {"numpy", "opencv-python-headless", "pillow", "scipy"}
    comentadas = "\n".join(l for l in linhas if l.strip().startswith("#"))
    for extra in ("faster-whisper", "parakeet-mlx"):
        assert extra in comentadas


def test_requirements_dos_gates_aponta_para_o_da_raiz():
    texto = (RAIZ_REAL / "scripts" / "gates" / "requirements.txt").read_text(encoding="utf-8")
    ativas = [l.strip() for l in texto.splitlines() if l.strip() and not l.startswith("#")]
    assert ativas == ["-r ../../requirements.txt"]
