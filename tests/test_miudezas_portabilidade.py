"""Miudezas de portabilidade (W1): pasta temporária, fonte do mostruário e abertura da pasta de entrega."""
import runpy
import sys
import tempfile
from pathlib import Path

import plataforma
from cinema import mostruario_grade
from entrega import pacote
from gravado import entregar

RAIZ = Path(__file__).resolve().parent.parent


def test_moldura_grava_na_pasta_temporaria_do_sistema(monkeypatch, tmp_path):
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["moldura.py"])
    runpy.run_path(str(RAIZ / "scripts" / "moldura.py"), run_name="__main__")  # bloco de linha de comando
    assert (tmp_path / "moldura.png").is_file()


def test_fonte_do_repo_vem_primeiro_e_windows_esta_na_lista():
    assert Path(mostruario_grade._FONTES[0]).parent == RAIZ / "fonts"
    assert Path(mostruario_grade._FONTES[0]).is_file()
    assert r"C:\Windows\Fonts\arialbd.ttf" in mostruario_grade._FONTES
    assert r"C:\Windows\Fonts\arial.ttf" in mostruario_grade._FONTES
    assert "/System/Library/Fonts/Helvetica.ttc" in mostruario_grade._FONTES


def test_pacote_abrir_delega_para_plataforma(monkeypatch, tmp_path):
    chamadas = []
    monkeypatch.setattr(plataforma, "abrir_pasta", lambda p: chamadas.append(p) or True)
    pacote.abrir(tmp_path)
    assert chamadas == [tmp_path]


def test_entregar_abrir_delega_para_plataforma(monkeypatch, tmp_path):
    chamadas = []
    monkeypatch.setattr(plataforma, "abrir_pasta", lambda p: chamadas.append(p) or True)
    entregar._abrir(tmp_path)
    assert chamadas == [tmp_path]
