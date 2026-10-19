"""O job `windows` do CI (W0, port nativo para Windows): a prova de que o motor roda no Windows do aluno.

O job fica vermelho enquanto o port não termina, e o que importa é ele estar CERTO: a ordem dos passos, o Git configurado
como o do aluno ANTES do checkout, um passo por critério de pronto e os jobs do Linux intactos. Leitura por texto, porque o
PyYAML não faz parte das dependências do repo.
"""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
CI = RAIZ / ".github" / "workflows" / "ci.yml"


def _texto():
    return CI.read_text(encoding="utf-8")


def _bloco(texto, job):
    """O texto do job (da linha `  <job>:` até o próximo job de dois espaços, ou o fim)."""
    m = re.search(r"^  %s:\n(.*?)(?=^  [a-z][\w-]*:\n|\Z)" % re.escape(job), texto, re.S | re.M)
    assert m, "job %s ausente do ci.yml" % job
    return m.group(1)


def _passos(bloco):
    """Cada passo do job: o texto entre um `      - ` e o próximo."""
    partes = re.split(r"^      - ", bloco.split("    steps:\n", 1)[1], flags=re.M)
    return partes[1:]                      # o que vem antes do primeiro `- ` é só comentário


def test_o_job_windows_existe_e_roda_em_windows_latest_com_bash_e_utf8():
    job = _bloco(_texto(), "windows")
    assert "runs-on: windows-latest" in job
    assert "timeout-minutes: 45" in job
    assert re.search(r"defaults:\n\s+run:\n\s+shell: bash", job)
    assert re.search(r'env:\n\s+PYTHONUTF8: "1"', job)


def test_o_git_do_aluno_e_configurado_antes_do_checkout():
    passos = _passos(_bloco(_texto(), "windows"))
    assert "core.autocrlf true" in passos[0] and "core.symlinks false" in passos[0]
    assert passos[1].startswith("uses: actions/checkout@v4")


def test_python_312_node_22_e_ffmpeg_pelo_chocolatey():
    job = _bloco(_texto(), "windows")
    assert re.search(r'actions/setup-python@v5\n\s+with:\n\s+python-version: "3\.12"', job)
    assert re.search(r'actions/setup-node@v4\n\s+with:\n\s+node-version: "22"', job)
    assert "choco install ffmpeg -y --no-progress" in job


def test_o_cache_do_chromium_do_hyperframes():
    job = _bloco(_texto(), "windows")
    assert "actions/cache@v4" in job and "~/.cache/hyperframes/chrome" in job


def test_um_passo_por_criterio_de_pronto_na_ordem_certa_e_nenhum_tolera_falha():
    passos = _passos(_bloco(_texto(), "windows"))
    comandos = ["bash scripts/setup.sh", "python scripts/vam.py doctor", "bash scripts/dev/testar_limpo.sh",
                "python scripts/vam.py fumaca --saida fumaca.mp4"]
    posicoes = []
    for cmd in comandos:
        achados = [i for i, p in enumerate(passos) if re.search(r"^\s+run: %s\s*$" % re.escape(cmd), p, re.M)]
        assert len(achados) == 1, "o comando `%s` tem que ser um passo só (achei %d)" % (cmd, len(achados))
        assert "continue-on-error: false" in passos[achados[0]], cmd
        posicoes.append(achados[0])
    assert posicoes == sorted(posicoes)
    assert not re.search(r"continue-on-error:\s*true", _bloco(_texto(), "windows"))


def test_o_passo_de_diagnostico_so_roda_na_falha_e_mostra_versoes_e_o_venv():
    passos = _passos(_bloco(_texto(), "windows"))
    diag = passos[-1]
    assert re.search(r"^\s+if: failure\(\)\s*$", diag, re.M)
    for esperado in ("python --version", "node --version", "ffmpeg -version", "ls -la .venv"):
        assert esperado in diag, esperado


def test_os_jobs_do_linux_seguem_como_estavam():
    texto = _texto()
    for job in ("testes", "higiene", "gitleaks"):
        assert "runs-on: ubuntu-latest" in _bloco(texto, job), job
    assert 'python: ["3.9", "3.12"]' in _bloco(texto, "testes")
    assert "bash scripts/dev/testar_limpo.sh" in _bloco(texto, "testes")
