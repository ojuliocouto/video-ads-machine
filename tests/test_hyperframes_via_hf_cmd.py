"""Unidade W1-C: todo lugar que roda o HyperFrames passa por `plataforma.hf_cmd` (nada de `node_modules/.bin/hyperframes`,
que no Windows é um script de shell sem extensão), as fontes do overlay são copiadas (sem symlink) e o motor do insert
acha o Chrome/Edge do Windows."""
import json
import os
from pathlib import Path

import pytest

import build_composite as BC
import plataforma
from cinema import insert_ui, mostruario_lettering as ML


def _pacote(raiz):
    pasta = raiz / "node_modules" / "hyperframes"
    (pasta / "dist").mkdir(parents=True)
    (pasta / "package.json").write_text(json.dumps({"name": "hyperframes", "bin": {"hyperframes": "./dist/cli.js"}}),
                                        encoding="utf-8")
    (pasta / "dist" / "cli.js").write_text("// cli\n", encoding="utf-8")
    return ["node", str(pasta / "dist" / "cli.js")]


class _Resultado(object):
    returncode = 0
    stdout = ""
    stderr = ""


# --- build_composite -----------------------------------------------------------------------------------------

def _overlay_pronto(tmp_path):
    overlay = tmp_path / "overlay"
    (overlay / "fonts").mkdir(parents=True)
    (overlay / "fonts" / "a.woff2").write_bytes(b"fonte-a")
    (overlay / "fonts" / "sub").mkdir()
    (overlay / "fonts" / "sub" / "b.ttf").write_bytes(b"fonte-b")
    (overlay / "index_overlay.html").write_text("<html></html>", encoding="utf-8")
    (overlay / "logo.png").write_bytes(b"png")
    motor = BC.Motor.__new__(BC.Motor)
    motor.overlay_dir = overlay
    motor.overlay_render_dir = tmp_path / "overlay_render"
    return motor


def test_projeto_do_overlay_copia_as_fontes_em_vez_de_symlink(tmp_path):
    motor = _overlay_pronto(tmp_path)
    only = motor.projeto_do_overlay()
    fontes = only / "fonts"
    assert fontes.is_dir() and not fontes.is_symlink()
    assert (fontes / "a.woff2").read_bytes() == b"fonte-a"
    assert (fontes / "sub" / "b.ttf").read_bytes() == b"fonte-b"
    assert not (fontes / "a.woff2").is_symlink()


def test_projeto_do_overlay_chamado_de_novo_recria_sem_erro(tmp_path):
    motor = _overlay_pronto(tmp_path)
    motor.projeto_do_overlay()
    (motor.overlay_dir / "fonts" / "c.woff2").write_bytes(b"fonte-c")
    only = motor.projeto_do_overlay()
    assert (only / "fonts" / "c.woff2").read_bytes() == b"fonte-c"


def test_render_do_overlay_chama_o_hyperframes_pelo_hf_cmd(tmp_path, monkeypatch):
    cmd_hf = _pacote(tmp_path)
    motor = _overlay_pronto(tmp_path)
    monkeypatch.setattr(BC, "RAIZ", tmp_path)
    chamadas = []

    def falso(cmd, etapa, **kw):
        chamadas.append(cmd)
        renders = Path(kw["cwd"]) / "renders"
        renders.mkdir(parents=True, exist_ok=True)
        (renders / "x.mov").write_bytes(b"mov")
        return _Resultado()

    monkeypatch.setattr(BC, "_rodar", falso)
    monkeypatch.setenv("CACHE_OVERLAY", "0")
    motor.renderizar_overlay()
    (cmd,) = chamadas
    assert [str(c) for c in cmd[:2]] == cmd_hf
    assert cmd[2] == "render" and "--format" in cmd


def test_render_do_overlay_sem_hyperframes_instalado_vira_erro_do_motor(tmp_path, monkeypatch):
    motor = _overlay_pronto(tmp_path)
    monkeypatch.setattr(BC, "RAIZ", tmp_path)
    monkeypatch.setenv("CACHE_OVERLAY", "0")
    with pytest.raises(BC.ErroDoMotor) as e:
        motor.renderizar_overlay()
    assert "setup.sh" in str(e.value)


def test_hyperframes_cmd_do_build_vem_do_hf_cmd(tmp_path, monkeypatch):
    cmd_hf = _pacote(tmp_path)
    monkeypatch.setattr(BC, "RAIZ", tmp_path)
    assert BC.hyperframes_cmd() == cmd_hf


# --- mostruario_lettering ------------------------------------------------------------------------------------

def test_mostruario_hyperframes_devolve_o_argv_do_hf_cmd(tmp_path, monkeypatch):
    cmd_hf = _pacote(tmp_path)
    monkeypatch.setattr(ML, "RAIZ", tmp_path)
    assert ML.hyperframes() == cmd_hf


def test_mostruario_sem_hyperframes_levanta_mostruario_falhou(tmp_path, monkeypatch):
    monkeypatch.setattr(ML, "RAIZ", tmp_path)
    with pytest.raises(ML.MostruarioFalhou) as e:
        ML.hyperframes()
    assert "setup.sh" in str(e.value)


def test_mostruario_snapshot_e_render_usam_o_argv_inteiro(tmp_path, monkeypatch):
    chamadas = []

    def falso(cmd, **kw):
        chamadas.append(list(cmd))
        saida = None
        if "-o" in cmd:
            saida = Path(cmd[cmd.index("-o") + 1])
        if cmd[2] == "render":
            saida.write_bytes(b"mp4")
        else:
            saida.mkdir(parents=True, exist_ok=True)
            (saida / "frame-01.png").write_bytes(b"png")
        return _Resultado()

    monkeypatch.setattr(ML.subprocess, "run", falso)
    hf = ["node", "C:\\Dados\\hf\\cli.js"]
    ML.renderizar_video(hf, tmp_path / "p", tmp_path / "v.mp4")
    ML._snapshot(hf, tmp_path / "p", [1.0], tmp_path / "snaps")
    assert chamadas[0][:3] == ["node", "C:\\Dados\\hf\\cli.js", "render"]
    assert chamadas[1][:3] == ["node", "C:\\Dados\\hf\\cli.js", "snapshot"]


def test_mostruario_ainda_aceita_hf_como_texto(tmp_path, monkeypatch):
    chamadas = []

    def falso(cmd, **kw):
        chamadas.append(list(cmd))
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"mp4")
        return _Resultado()

    monkeypatch.setattr(ML.subprocess, "run", falso)
    ML.renderizar_video("/x/hf", tmp_path / "p", tmp_path / "v.mp4")
    assert chamadas[0][:2] == ["/x/hf", "render"]


# --- insert_ui -----------------------------------------------------------------------------------------------

def test_motor_padrao_usa_o_hf_cmd(tmp_path):
    cmd_hf = _pacote(tmp_path)
    motor = insert_ui.motor_padrao(tmp_path)
    assert motor.nome == "hyperframes" and motor.comando == cmd_hf


def test_motor_hyperframes_monta_o_comando_com_o_argv_inteiro(tmp_path):
    pasta = tmp_path / "p"
    pasta.mkdir()
    pedido = insert_ui.PedidoRender(template="contador", html="<html></html>", pasta=pasta, saida=tmp_path / "s.mp4",
                                    largura=1920, altura=1080, fps=30, quadros=120, dur=4.0)
    chamadas = []

    def executar(cmd, **kw):
        chamadas.append(cmd)
        pedido.saida.write_bytes(b"x")
        return 0, ""

    insert_ui.MotorHyperframes(["node", "C:\\Dados\\hf\\cli.js"], executar=executar)(pedido)
    (cmd,) = chamadas
    assert cmd[:3] == ["node", "C:\\Dados\\hf\\cli.js", "render"]


# --- navegador do Windows ------------------------------------------------------------------------------------

def _como_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(plataforma, "_sistema", lambda: "win32")
    monkeypatch.setattr(insert_ui.Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.setattr(insert_ui.shutil, "which", lambda nome: None)


def test_achar_navegador_conhece_o_chrome_do_windows(tmp_path, monkeypatch):
    _como_windows(monkeypatch, tmp_path)
    pf = tmp_path / "Program Files"
    chrome = pf / "Google" / "Chrome" / "Application" / "chrome.exe"
    chrome.parent.mkdir(parents=True)
    chrome.write_bytes(b"")
    monkeypatch.setenv("PROGRAMFILES", str(pf))
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert insert_ui._achar_navegador() == chrome


def test_achar_navegador_conhece_o_edge_x86_e_o_localappdata(tmp_path, monkeypatch):
    _como_windows(monkeypatch, tmp_path)
    x86 = tmp_path / "Program Files (x86)"
    edge = x86 / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    edge.parent.mkdir(parents=True)
    edge.write_bytes(b"")
    monkeypatch.setenv("PROGRAMFILES(X86)", str(x86))
    monkeypatch.delenv("PROGRAMFILES", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert insert_ui._achar_navegador() == edge
    local = tmp_path / "Local"
    chrome = local / "Google" / "Chrome" / "Application" / "chrome.exe"
    chrome.parent.mkdir(parents=True)
    chrome.write_bytes(b"")
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    assert insert_ui._achar_navegador() == chrome


def test_achar_navegador_pelo_path_do_windows(tmp_path, monkeypatch):
    _como_windows(monkeypatch, tmp_path)
    for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(insert_ui.shutil, "which", lambda nome: "C:\\Dados\\bin\\msedge.exe" if nome == "msedge" else None)
    assert str(insert_ui._achar_navegador()) == "C:\\Dados\\bin\\msedge.exe"


def test_achar_navegador_fora_do_windows_nao_olha_as_pastas_do_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(plataforma, "_sistema", lambda: "linux")
    monkeypatch.setattr(insert_ui.Path, "home", classmethod(lambda cls: tmp_path / "home"))
    consultados = []
    monkeypatch.setattr(insert_ui.shutil, "which", lambda nome: consultados.append(nome))
    monkeypatch.setattr(insert_ui, "_navegadores_do_mac", lambda: [])
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
    assert insert_ui._achar_navegador() is None
    assert consultados[:2] == ["google-chrome", "google-chrome-stable"]     # a ordem de hoje no Linux
