"""O conferidor da skill (W6.D): link quebrado, comando `vam` que não existe e caminho da máquina do dono.

Os casos ruins são montados em pedaços para este arquivo não ser o primeiro a violar a regra.
"""
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "scripts" / "dev" / "checar_skill.py"
CONFIG_DO_DONO = "~/" + ".claude"

CLI_OK = "def registrar(sub):\n    pass\n"


def _rodar(raiz):
    return subprocess.run([sys.executable, str(SCRIPT), "--raiz", str(raiz)], capture_output=True, text=True)


def _skill(tmp_path, arquivos, comandos=("novo", "montar")):
    cli = tmp_path / "scripts" / "cli"
    cli.mkdir(parents=True, exist_ok=True)
    for c in comandos:
        (cli / (c + ".py")).write_text(CLI_OK, encoding="utf-8")
    (cli / "_comum.py").write_text("def registrar(sub):\n    pass\n", encoding="utf-8")        # helper não é comando
    for nome, texto in arquivos.items():
        p = tmp_path / nome
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")
    return tmp_path


def test_skill_limpa_sai_com_zero(tmp_path):
    raiz = _skill(tmp_path, {"SKILL.md": "Veja [[references/gates]] e [[gates|os gates]].\nRode `vam novo x`.\n",
                             "references/gates.md": "# gates\n```\nvam montar x\n```\n"})
    r = _rodar(raiz)
    assert r.returncode == 0, r.stdout


def test_link_quebrado_reprova_com_arquivo_e_linha(tmp_path):
    raiz = _skill(tmp_path, {"SKILL.md": "linha 1\nveja [[references/nao-existe]] agora\n"})
    r = _rodar(raiz)
    assert r.returncode == 1
    assert "SKILL.md:2" in r.stdout and "nao-existe" in r.stdout


def test_link_com_ancora_e_rotulo_resolve_o_arquivo(tmp_path):
    raiz = _skill(tmp_path, {"SKILL.md": "[[gates#nota]] e [[docs/guia|o guia]]\n", "references/gates.md": "x\n",
                             "docs/guia.md": "y\n"})
    assert _rodar(raiz).returncode == 0


def test_colchete_duplo_de_codigo_nao_e_link(tmp_path):
    raiz = _skill(tmp_path, {"SKILL.md": "No bash: `[[ -f x ]]`.\n```bash\nif [[ -f x ]]; then echo ok; fi\n```\n"})
    assert _rodar(raiz).returncode == 0


def test_comando_vam_que_nao_existe_reprova_no_bloco_e_na_crase(tmp_path):
    raiz = _skill(tmp_path, {"SKILL.md": "Rode `vam voar x`.\n", "references/a.md": "```\nvam sumir y\n```\n"})
    r = _rodar(raiz)
    assert r.returncode == 1
    assert "SKILL.md:1" in r.stdout and "vam voar" in r.stdout
    assert "references/a.md:2" in r.stdout and "vam sumir" in r.stdout


def test_vam_na_prosa_e_helper_nao_viram_comando(tmp_path):
    raiz = _skill(tmp_path, {"SKILL.md": "O vam monta tudo. Rode `vam montar x` e `vam comum`.\n"})
    r = _rodar(raiz)
    assert r.returncode == 1 and "vam comum" in r.stdout      # _comum.py não é comando
    assert "vam monta" not in r.stdout.replace("vam montar", "")


def test_config_do_dono_reprova_em_qualquer_arquivo_de_texto(tmp_path):
    raiz = _skill(tmp_path, {"SKILL.md": "ok\n", "scripts/x.py": "P = '" + CONFIG_DO_DONO + "/scripts'\n",
                             "references/b.md": "veja " + CONFIG_DO_DONO + "/skills\n"})
    r = _rodar(raiz)
    assert r.returncode == 1
    assert "scripts/x.py:1" in r.stdout and "references/b.md:1" in r.stdout


def test_isencao_declarada_do_resolvedor_de_gates(tmp_path):
    raiz = _skill(tmp_path, {"scripts/caminhos.py": "# " + CONFIG_DO_DONO + "/scripts por compatibilidade\n"})
    assert _rodar(raiz).returncode == 0


def test_o_repo_inteiro_esta_limpo():
    r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:]
