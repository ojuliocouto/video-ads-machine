"""Tests for vam.doctor: every environment/account check with mocked subprocess and HTTP."""
import json
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from vam import doctor  # noqa: E402
from vam import heygen  # noqa: E402


class FakeProc:
    def __init__(self, returncode=0, stderr="", stdout=""):
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("HEYGEN_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_TOKEN_FILE", raising=False)


# ------------------------------------------------------------------ ffmpeg

def test_ffmpeg_missing_is_fail_with_install_fix(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    r = doctor.check_ffmpeg()
    assert r.status == "FAIL"
    assert "brew install ffmpeg" in r.fix


def test_ffmpeg_functional_render_with_subtitles_filter_is_ok(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/local/bin/ffmpeg")
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return FakeProc(0)

    monkeypatch.setattr(doctor.subprocess, "run", fake_run)
    r = doctor.check_ffmpeg()
    assert r.status == "OK"
    # It must actually exercise the subtitles filter, not just -version.
    joined = " ".join(seen["cmd"])
    assert "subtitles=" in joined
    assert "lavfi" in joined


def test_ffmpeg_dyld_error_suggests_reinstall(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/opt/homebrew/bin/ffmpeg")
    stderr = ("dyld[4242]: Library not loaded: /opt/homebrew/opt/libass/lib/"
              "libass.9.dylib\n  Referenced from: /opt/homebrew/bin/ffmpeg")
    monkeypatch.setattr(doctor.subprocess, "run",
                        lambda cmd, **kw: FakeProc(134, stderr=stderr))
    r = doctor.check_ffmpeg()
    assert r.status == "FAIL"
    assert "reinstall" in r.fix.lower()
    assert "ffmpeg" in r.fix


def test_ffmpeg_built_without_libass_is_fail(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(doctor.subprocess, "run",
                        lambda cmd, **kw: FakeProc(1, stderr="No such filter: 'subtitles'"))
    r = doctor.check_ffmpeg()
    assert r.status == "FAIL"
    assert "libass" in (r.detail + r.fix)


# ----------------------------------------------------------------- ffprobe

def test_ffprobe_present_and_missing(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which",
                        lambda name: "/usr/bin/ffprobe" if name == "ffprobe" else None)
    assert doctor.check_ffprobe().status == "OK"
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    r = doctor.check_ffprobe()
    assert r.status == "FAIL"
    assert r.fix


# ------------------------------------------------------------------- fonts

def test_fonts_ok_and_missing(tmp_path):
    d = tmp_path / "fonts"
    d.mkdir()
    (d / "Some-Font.ttf").write_bytes(b"\x00")
    assert doctor.check_fonts(str(d)).status == "OK"
    empty = tmp_path / "empty"
    empty.mkdir()
    assert doctor.check_fonts(str(empty)).status == "FAIL"
    assert doctor.check_fonts(str(tmp_path / "nope")).status == "FAIL"


# ------------------------------------------------------------- python deps

def test_python_deps_ok_when_yaml_importable():
    r = doctor.check_python_deps()
    assert r.status == "OK"  # pyyaml is a test dependency of this repo


def test_python_deps_fail_without_yaml(monkeypatch):
    monkeypatch.setattr(doctor, "_importable", lambda name: False)
    r = doctor.check_python_deps()
    assert r.status == "FAIL"
    assert "pip install" in r.fix


# ------------------------------------------------------------- HeyGen key

def test_heygen_key_unset_is_fail():
    r = doctor.check_heygen_key()
    assert r.status == "FAIL"
    assert "HEYGEN_API_KEY" in r.detail + r.fix


def test_heygen_key_valid_reports_api_credit_separate_from_plan(monkeypatch):
    monkeypatch.setenv("HEYGEN_API_KEY", "k")
    monkeypatch.setattr(heygen, "_req",
                        lambda url, **kw: {"data": {"remaining_quota": 720}})
    r = doctor.check_heygen_key()
    assert r.status == "OK"
    assert "720" in r.detail
    assert "separate" in r.detail.lower()  # API credit != plan credit


def test_heygen_key_zero_api_credit_warns(monkeypatch):
    monkeypatch.setenv("HEYGEN_API_KEY", "k")
    monkeypatch.setattr(heygen, "_req",
                        lambda url, **kw: {"data": {"remaining_quota": 0}})
    r = doctor.check_heygen_key()
    assert r.status == "WARN"
    assert "separate" in (r.detail + r.fix).lower()


def test_heygen_key_rejected_is_fail(monkeypatch):
    monkeypatch.setenv("HEYGEN_API_KEY", "bad")
    monkeypatch.setattr(heygen, "_req",
                        lambda url, **kw: {"code": 401, "message": "unauthorized"})
    r = doctor.check_heygen_key()
    assert r.status == "FAIL"
    assert "unauthorized" in r.detail


def test_heygen_key_network_error_is_fail(monkeypatch):
    monkeypatch.setenv("HEYGEN_API_KEY", "k")

    def boom(url, **kw):
        raise heygen.HeyGenError("Network error reaching x")

    monkeypatch.setattr(heygen, "_req", boom)
    r = doctor.check_heygen_key()
    assert r.status == "FAIL"


# ---------------------------------------------------------------- avatar id

def _avatars_response(entries):
    return {"data": {"avatars": entries}}


def test_avatar_found_is_ok(monkeypatch):
    monkeypatch.setenv("HEYGEN_API_KEY", "k")
    monkeypatch.setattr(heygen, "_req", lambda url, **kw: _avatars_response(
        [{"avatar_id": "YOUR_AVATAR_ID", "avatar_name": "Me"}]))
    r = doctor.check_avatar("YOUR_AVATAR_ID")
    assert r.status == "OK"


def test_avatar_not_found_is_fail(monkeypatch):
    monkeypatch.setenv("HEYGEN_API_KEY", "k")
    monkeypatch.setattr(heygen, "_req", lambda url, **kw: _avatars_response(
        [{"avatar_id": "other"}]))
    r = doctor.check_avatar("YOUR_AVATAR_ID")
    assert r.status == "FAIL"
    assert "YOUR_AVATAR_ID" in r.detail
    assert "app.heygen.com" in r.fix


def test_avatar_landscape_preview_warns(monkeypatch):
    monkeypatch.setenv("HEYGEN_API_KEY", "k")
    monkeypatch.setattr(heygen, "_req", lambda url, **kw: _avatars_response(
        [{"avatar_id": "A1", "preview_image_url": "https://x/img_landscape.jpg"}]))
    r = doctor.check_avatar("A1")
    assert r.status == "WARN"
    assert "9:16" in r.detail + r.fix


def test_avatar_landscape_by_dimensions_warns(monkeypatch):
    monkeypatch.setenv("HEYGEN_API_KEY", "k")
    monkeypatch.setattr(heygen, "_req", lambda url, **kw: _avatars_response(
        [{"avatar_id": "A1", "preview_width": 1920, "preview_height": 1080}]))
    r = doctor.check_avatar("A1")
    assert r.status == "WARN"


def test_avatar_skipped_without_key():
    r = doctor.check_avatar("A1")
    assert r.status == "WARN"  # cannot verify, but not a hard fail on its own


# -------------------------------------------------------------- Drive token

def test_drive_not_configured_is_ok():
    r = doctor.check_drive(None)
    assert r.status == "OK"


def test_drive_configured_but_env_unset_is_fail():
    r = doctor.check_drive("https://drive.google.com/drive/folders/abc")
    assert r.status == "FAIL"
    assert "GOOGLE_OAUTH_TOKEN_FILE" in r.detail + r.fix


def test_drive_token_file_missing_is_fail(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_FILE", str(tmp_path / "nope.json"))
    assert doctor.check_drive("folder").status == "FAIL"


def test_drive_token_file_invalid_json_is_fail(monkeypatch, tmp_path):
    p = tmp_path / "tok.json"
    p.write_text("{not json")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_FILE", str(p))
    assert doctor.check_drive("folder").status == "FAIL"


def test_drive_token_file_without_usable_tokens_is_fail(monkeypatch, tmp_path):
    p = tmp_path / "tok.json"
    p.write_text(json.dumps({"scope": "drive"}))
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_FILE", str(p))
    r = doctor.check_drive("folder")
    assert r.status == "FAIL"


def test_drive_token_file_valid_is_ok(monkeypatch, tmp_path):
    p = tmp_path / "tok.json"
    p.write_text(json.dumps({
        "refresh_token": "r", "client_id": "c", "client_secret": "s"}))
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_FILE", str(p))
    assert doctor.check_drive("folder").status == "OK"


# ------------------------------------------------------------ run / report

def test_run_exit_zero_when_no_fail(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "run_checks", lambda config_path=None: [
        doctor.CheckResult("ffmpeg", "OK", "fine"),
        doctor.CheckResult("fonts", "WARN", "meh", "do something"),
    ])
    assert doctor.run() == 0
    out = capsys.readouterr().out
    assert "[OK]" in out and "[WARN]" in out
    assert "fix:" in out  # WARN/FAIL lines carry their fix


def test_run_exit_one_when_any_fail(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "run_checks", lambda config_path=None: [
        doctor.CheckResult("ffmpeg", "FAIL", "broken", "reinstall ffmpeg"),
    ])
    assert doctor.run() == 1
    out = capsys.readouterr().out
    assert "[FAIL]" in out
    assert "reinstall ffmpeg" in out


def test_run_checks_without_config_still_runs_env_checks(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # no config.yaml here
    monkeypatch.setattr(doctor, "check_ffmpeg",
                        lambda: doctor.CheckResult("ffmpeg", "OK"))
    monkeypatch.setattr(doctor, "check_ffprobe",
                        lambda: doctor.CheckResult("ffprobe", "OK"))
    results = doctor.run_checks()
    names = [r.name for r in results]
    assert "ffmpeg" in names and "HEYGEN_API_KEY" in names
    # avatar/drive need a config; a WARN must tell the user to create one
    assert any(r.status == "WARN" and "config" in r.name.lower() for r in results)


def test_run_checks_with_config_includes_avatar_and_drive(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("avatar_id: A1\n")
    monkeypatch.setenv("HEYGEN_API_KEY", "k")
    monkeypatch.setattr(doctor, "check_ffmpeg",
                        lambda: doctor.CheckResult("ffmpeg", "OK"))
    monkeypatch.setattr(doctor, "check_ffprobe",
                        lambda: doctor.CheckResult("ffprobe", "OK"))
    monkeypatch.setattr(heygen, "_req", lambda url, **kw:
                        {"data": {"remaining_quota": 9, "avatars": [{"avatar_id": "A1"}]}})
    results = doctor.run_checks(str(cfg))
    names = [r.name for r in results]
    assert "avatar_id" in names
    assert "drive" in names
