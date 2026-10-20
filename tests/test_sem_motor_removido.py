"""O motor de transcrição removido (decisão do dono, 20/10/2026) não volta pela porta dos fundos.

A palavra é montada em partes para este arquivo não casar consigo mesmo.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PALAVRA = "para" + "keet"
PASTAS = ("scripts", "tests", "docs", "references", "contratos", "templates")
ARQUIVOS = ("SKILL.md", "README.md", "requirements.txt", ".env.example", "NOTICE", "LICENSE")
SUFIXOS = {".py", ".sh", ".md", ".txt", ".json", ".example", ".cmd", ".ps1", ".toml", ".yml", ".yaml", ".html"}


def _arquivos():
    for nome in ARQUIVOS:
        if (RAIZ / nome).is_file():
            yield RAIZ / nome
    for pasta in PASTAS:
        for p in (RAIZ / pasta).rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts and "node_modules" not in p.parts \
                    and (p.suffix in SUFIXOS or p.name.startswith(".env")):
                yield p


def test_nenhum_arquivo_do_repo_cita_o_motor_removido():
    achados = [str(p.relative_to(RAIZ)) for p in _arquivos()
               if PALAVRA in p.read_text(encoding="utf-8", errors="ignore").lower()]
    assert not achados, achados


def test_nenhum_arquivo_tem_o_nome_do_motor_removido():
    achados = [str(p.relative_to(RAIZ)) for p in _arquivos() if PALAVRA in p.name.lower()]
    assert not achados, achados
