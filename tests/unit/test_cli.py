"""Tests for the vam CLI wiring: doctor, build (GateFail -> exit 1) and clean-audio."""
import json
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from vam import cli  # noqa: E402


def _argv(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["vam", *args])


# ------------------------------------------------------------------ doctor

def test_doctor_exits_with_doctor_run_code(monkeypatch):
    from vam import doctor
    monkeypatch.setattr(doctor, "run", lambda config_path=None: 0)
    _argv(monkeypatch, "doctor")
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0


def test_doctor_failure_exits_one_and_passes_config(monkeypatch):
    from vam import doctor
    seen = {}

    def fake_run(config_path=None):
        seen["config_path"] = config_path
        return 1

    monkeypatch.setattr(doctor, "run", fake_run)
    _argv(monkeypatch, "doctor", "--config", "my.yaml")
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    assert seen["config_path"] == "my.yaml"


# ------------------------------------------------------------------- build

def _fake_build_module(monkeypatch, build_fn):
    mod = types.ModuleType("vam.build")

    class GateFail(Exception):
        pass

    mod.GateFail = GateFail
    mod.build = build_fn
    monkeypatch.setitem(sys.modules, "vam.build", mod)
    return mod


def test_build_calls_vam_build_with_config_path(monkeypatch, capsys):
    seen = {}

    def build(config_path):
        seen["config_path"] = config_path
        return {"ok": True, "outputs": ["final_9x16.mp4"]}

    _fake_build_module(monkeypatch, build)
    _argv(monkeypatch, "build", "config.yaml")
    cli.main()
    assert seen["config_path"] == "config.yaml"
    out = capsys.readouterr().out
    assert "final_9x16.mp4" in out  # manifest is shown to the user


def test_build_gatefail_exits_one_with_message(monkeypatch, capsys):
    mod = _fake_build_module(monkeypatch, lambda p: None)

    def build(config_path):
        raise mod.GateFail("G2: cleaned audio still has big silences")

    mod.build = build
    _argv(monkeypatch, "build", "config.yaml")
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "G2" in err


# ------------------------------------------------------------- clean-audio

def test_clean_audio_calls_clean_voice(monkeypatch, capsys):
    import vam.audio as audio_mod
    seen = {}

    def fake_clean(src, dst, cfg):
        seen["args"] = (src, dst, cfg)
        return {"cuts": 3, "removed_s": 1.8, "src_dur": 30.0,
                "dst_dur": 28.2, "residual_big": []}

    monkeypatch.setattr(audio_mod, "clean_voice", fake_clean)
    _argv(monkeypatch, "clean-audio", "raw.mp3", "clean.mp3")
    cli.main()
    assert seen["args"][0] == "raw.mp3"
    assert seen["args"][1] == "clean.mp3"
    out = capsys.readouterr().out
    assert '"cuts": 3' in out


def test_clean_audio_with_config_loads_it(monkeypatch, tmp_path, capsys):
    import vam.audio as audio_mod
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("avatar_id: A1\naudio:\n  big_sil: 0.7\n")
    seen = {}

    def fake_clean(src, dst, cfg):
        seen["cfg"] = cfg
        return {"cuts": 0, "removed_s": 0.0, "src_dur": 1.0,
                "dst_dur": 1.0, "residual_big": []}

    monkeypatch.setattr(audio_mod, "clean_voice", fake_clean)
    _argv(monkeypatch, "clean-audio", "a.mp3", "b.mp3", "--config", str(cfg_file))
    cli.main()
    assert seen["cfg"].audio.big_sil == 0.7


# ----------------------------------------------------------------- version

def test_version_prints_version(monkeypatch, capsys):
    _argv(monkeypatch, "version")
    cli.main()
    assert "video-ads-machine" in capsys.readouterr().out
