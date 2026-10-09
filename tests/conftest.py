"""Fixtures compartilhados da esteira de testes (W0.1).

- `scripts/` e a raiz do repo entram no sys.path, porque o `--import-mode=importlib` do
  pytest.ini não mexe no path e os módulos do motor são importados pelo nome solto.
- `home_falso`: HOME numa pasta nova e vazia. `Path.home()`, `os.path.expanduser` e quem
  lê `$HOME` enxergam a pasta; nada do HOME real vaza para o teste (nem o contrário).
- `estado_vazio`: um `_local` novo e vazio, com `VAM_ESTADO` e `VAM_DADOS` apontando para
  ele e as demais `VAM_*` removidas. Vale para subprocessos e para módulos importados DEPOIS
  (o `caminhos.py` lê o ambiente no import: módulo já importado não muda).
"""
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
for _p in (str(RAIZ / "scripts"), str(RAIZ)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_VARIAVEIS_VAM = ("VAM_ESTADO", "VAM_DADOS", "VAM_V1_HOME", "VAM_INPUTS", "VAM_OUTPUT",
                  "VAM_ROTEIROS", "VAM_ASSETS", "VAM_FONTS")


@pytest.fixture
def home_falso(tmp_path, monkeypatch):
    """HOME novo e vazio. Devolve o Path."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for nome in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        monkeypatch.delenv(nome, raising=False)
    return home


@pytest.fixture
def estado_vazio(tmp_path, monkeypatch):
    """`_local` novo e vazio (ESTADO). VAM_DADOS aponta para ESTADO/dados, que não existe ainda."""
    for nome in _VARIAVEIS_VAM:
        monkeypatch.delenv(nome, raising=False)
    estado = tmp_path / "_local"
    estado.mkdir()
    monkeypatch.setenv("VAM_ESTADO", str(estado))
    monkeypatch.setenv("VAM_DADOS", str(estado / "dados"))
    return estado
