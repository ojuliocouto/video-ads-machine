"""Orchestrator tests: every gate has a PASS and a BLOCK path, deps mocked.

No real ffmpeg, no real HTTP: every pipeline stage (audio, avatar, montage,
captions, accelerate, drive) is monkeypatched, and media durations come from
a fake ffprobe keyed by path substring.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from vam import build as bmod  # noqa: E402
from vam.build import GateFail, build  # noqa: E402
from vam.config import ConfigError  # noqa: E402


SCRIPT_OK = (
    "[presenter talking to camera] hello this is the hook\n"
    "[product screen recording] here is the product working\n"
    "[lettering | KEY: TODAY] and it opens today\n"
    "[lettering with logo | LEAD: join us | KEY: NOW] join right now\n"
)
# An insert instruction that mentions the presenter word is misclassified
# as a presenter scene (validated parser gotcha) -> G0 must block it.
SCRIPT_GOTCHA = SCRIPT_OK + "[insert b-roll with the avatar smiling] final call\n"

DRIVE = "https://drive.google.com/drive/folders/FOLDER_ID"
AVATARS = [{"name": "a", "avatar_id": "AV_A"},
           {"name": "b", "avatar_id": "AV_B"}]


def _touch(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"\x00")


def write_config(tmp_path, *, avatars=None, drive_folder=None,
                 script=SCRIPT_OK, expected=None, accelerate=None):
    """Create a full fake project (voice, script, inserts) + build YAML."""
    (tmp_path / "voice.mp3").write_bytes(b"v")
    (tmp_path / "script.txt").write_text(script, encoding="utf-8")
    (tmp_path / "clip.mp4").write_bytes(b"c")
    (tmp_path / "inserts.json").write_text(
        json.dumps({"product": {"file": "clip.mp4"}}), encoding="utf-8")
    lines = []
    if avatars is None:
        lines.append('avatar_id: "AV_ONE"')
    else:
        lines.append("avatars:")
        for v in avatars:
            lines.append(f"  - name: {v['name']}")
            if v.get("avatar_id"):
                lines.append(f"    avatar_id: {v['avatar_id']}")
    if drive_folder:
        lines.append(f"drive_folder: {drive_folder}")
    if accelerate is not None:
        lines.append(f"accelerate: {accelerate}")
    lines.append(f"workdir: '{tmp_path / 'build'}'")
    lines += [
        "project:",
        "  name: ad",
        "  raw_voice: voice.mp3",
        "  script: script.txt",
        "  inserts: inserts.json",
    ]
    if expected is not None:
        lines.append(f"  expected_lettering_scenes: {expected}")
    cfg = tmp_path / "build.yaml"
    cfg.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(cfg)


@pytest.fixture
def pipe(monkeypatch):
    """Mock every pipeline stage; the returned dict steers pass/fail."""
    state = {
        # duration by path substring; FIRST match wins, fallback 28.8
        "durs": {"final_9x16": 24.0, "final_1x1": 24.0},
        "residual": [],          # G1: big silences left in the clean voice
        "letterings": 2,         # G3: lettering scenes in the fake timing
        "final_sil": [],         # G6: big silences in the final video
        "push_ok": True,         # G7: drive upload verified?
        "burn_formats": ("9x16", "1x1"),  # which burns produce a file
        "calls": [],
    }

    def duration(path):
        for key, val in state["durs"].items():
            if key in path:
                return float(val)
        return 28.8

    def big_silences(path, *a, **k):
        return list(state["final_sil"])

    def clean_voice(src, dst, cfg):
        state["calls"].append(("clean", src))
        _touch(dst)
        return {"cuts": 3, "removed_s": 1.4, "src_dur": 30.2, "dst_dur": 28.8,
                "residual_big": list(state["residual"]), "notes": []}

    def generate_avatar(audio_path, out_path, cfg, engine=None):
        state["calls"].append(("avatar", cfg.avatar_id))
        _touch(out_path)
        return out_path

    def assemble(roteiro, avatar, inserts_map, out, cfg):
        state["calls"].append(("assemble", out))
        _touch(out)
        lets = [{"s": 5.0 + i, "e": 6.0 + i}
                for i in range(state["letterings"])]
        return {"a0": 0.4, "total": 29.2, "avatar": avatar,
                "letterings": lets, "inserts": [{"s": 8.0, "e": 9.5}]}

    def overlay_pip(src, dst, avatar, timing, cfg):
        state["calls"].append(("pip", dst))
        _touch(dst)
        return dst

    def burn(src, dst, roteiro, fmt, cfg, timing, **kw):
        state["calls"].append(("burn", fmt))
        if fmt in state["burn_formats"]:
            _touch(dst)

    def make_square(src, dst):
        state["calls"].append(("square", dst))
        _touch(dst)

    def accelerate(src, dst, factor=1.2):
        state["calls"].append(("accel", float(factor)))
        _touch(dst)

    def push(folder, items):
        state["calls"].append(("push", folder, [n for _, n in items]))
        ok = state["push_ok"]
        results = [{"name": n, "ok": ok, "id": "1" if ok else None,
                    "link": "https://drive.google.com/file/d/1/view" if ok else None,
                    "error": None if ok else "upload failed", "verified": ok}
                   for _, n in items]
        return {"folder": "F",
                "folder_link": "https://drive.google.com/drive/folders/F",
                "results": results, "all_ok": ok}

    monkeypatch.setattr(bmod.ffutil, "duration", duration)
    monkeypatch.setattr(bmod.ffutil, "big_silences", big_silences)
    monkeypatch.setattr(bmod.audio, "clean_voice", clean_voice)
    monkeypatch.setattr(bmod.heygen, "generate_avatar", generate_avatar)
    monkeypatch.setattr(bmod.montage, "assemble", assemble)
    monkeypatch.setattr(bmod.montage, "overlay_pip", overlay_pip)
    monkeypatch.setattr(bmod.captions, "burn", burn)
    monkeypatch.setattr(bmod.captions, "make_square", make_square)
    monkeypatch.setattr(bmod.accel, "accelerate", accelerate)
    monkeypatch.setattr(bmod.drive, "push", push)
    return state


def _called(state, kind):
    return [c for c in state["calls"] if c[0] == kind]


# ------------------------------------------------------------ happy path

def test_happy_path_manifest_complete(tmp_path, pipe):
    m = build(write_config(tmp_path))
    assert m["all_pass"] is True
    assert m["name"] == "ad"
    assert [v["name"] for v in m["variants"]] == ["default"]
    v = m["variants"][0]
    assert os.path.exists(v["final_9x16"]) and os.path.exists(v["final_1x1"])
    assert v["duration_s"] == pytest.approx(24.0)
    gate_names = {g["gate"] for g in m["gates"]}
    for name in ("input:raw_voice", "input:script",
                 "no_presenter_word_in_insert_instructions",
                 "variants_have_avatar_id", "voice_clean_exists",
                 "no_big_silence_left", "avatar_matches_clean_audio",
                 "lettering_scenes", "captions_9x16_and_1x1", "accelerated",
                 "final_no_big_silence", "final_lettering_scenes"):
        assert name in gate_names, name
    assert all(g["ok"] for g in m["gates"])
    assert m["drive"] is None
    # manifest persisted next to the build artifacts
    mpath = os.path.join(str(tmp_path / "build"), "ad_manifest.json")
    with open(mpath, encoding="utf-8") as fh:
        assert json.load(fh)["all_pass"] is True


def test_manifest_gate_metrics_present(tmp_path, pipe):
    m = build(write_config(tmp_path))
    g = {x["gate"]: x for x in m["gates"]}
    assert g["no_big_silence_left"]["metrics"]["clean_dur"] == pytest.approx(28.8)
    assert g["no_big_silence_left"]["metrics"]["residual_big"] == []
    assert g["lettering_scenes"]["metrics"] == {
        "lettering_scenes": 2, "expected": 2}
    assert g["accelerated"]["metrics"]["factor"] == pytest.approx(1.2)


# ------------------------------------------------------------------- G0

def test_g0_blocks_on_missing_voice(tmp_path, pipe):
    cfg = write_config(tmp_path)
    os.remove(tmp_path / "voice.mp3")
    with pytest.raises(GateFail) as e:
        build(cfg)
    assert "voice.mp3" in str(e.value)
    assert not _called(pipe, "clean") and not _called(pipe, "avatar")


def test_g0_blocks_insert_instruction_with_presenter_word(tmp_path, pipe):
    with pytest.raises(GateFail) as e:
        build(write_config(tmp_path, script=SCRIPT_GOTCHA))
    msg = str(e.value)
    assert "5" in msg                       # offending line number
    assert "presenter" in msg.lower()       # says WHAT is wrong
    assert not _called(pipe, "clean")


def test_g0_blocks_variant_without_avatar_id(tmp_path, pipe):
    avs = [{"name": "a", "avatar_id": "AV_A"}, {"name": "b"}]
    with pytest.raises(GateFail) as e:
        build(write_config(tmp_path, avatars=avs))
    assert "avatar_id" in str(e.value)
    assert not _called(pipe, "avatar")


def test_g0_records_real_voice_reminder(tmp_path, pipe):
    m = build(write_config(tmp_path))
    assert any("TTS" in g["detail"] for g in m["gates"])


# ------------------------------------------------------------------- G1

def test_g1_blocks_on_residual_big_silence(tmp_path, pipe):
    pipe["residual"] = [(3.1, 4.0)]
    with pytest.raises(GateFail) as e:
        build(write_config(tmp_path))
    msg = str(e.value).lower()
    assert "silence" in msg
    assert "sil_db" in msg                  # says HOW to fix
    assert _called(pipe, "clean") and not _called(pipe, "avatar")


# ------------------------------------------------------------------- G2

def test_g2_blocks_on_avatar_duration_mismatch(tmp_path, pipe):
    pipe["durs"]["avatar.mp4"] = 26.0       # clean voice is 28.8
    with pytest.raises(GateFail) as e:
        build(write_config(tmp_path))
    assert "avatar" in str(e.value).lower()
    assert _called(pipe, "avatar") and not _called(pipe, "assemble")


def test_g2_pass_within_tolerance(tmp_path, pipe):
    pipe["durs"]["avatar.mp4"] = 28.3       # 0.5s diff <= 0.8 tolerance
    assert build(write_config(tmp_path))["all_pass"]


# ------------------------------------------------------------------- G3

def test_g3_blocks_on_missing_lettering_scene(tmp_path, pipe):
    pipe["letterings"] = 1                  # script announces 2
    with pytest.raises(GateFail) as e:
        build(write_config(tmp_path))
    assert "lettering" in str(e.value).lower()
    assert not _called(pipe, "burn")


def test_g3_expected_override_in_project(tmp_path, pipe):
    pipe["letterings"] = 1
    assert build(write_config(tmp_path, expected=1))["all_pass"]


# ------------------------------------------------------------------- G4

def test_g4_blocks_when_a_caption_output_is_missing(tmp_path, pipe):
    pipe["burn_formats"] = ("9x16",)        # the 1x1 burn produces nothing
    with pytest.raises(GateFail) as e:
        build(write_config(tmp_path))
    assert "1x1" in str(e.value)
    assert not _called(pipe, "accel")


def test_g4_pass_calls_both_formats(tmp_path, pipe):
    build(write_config(tmp_path))
    assert [c[1] for c in _called(pipe, "burn")] == ["9x16", "1x1"]
    assert len(_called(pipe, "square")) == 1


# ------------------------------------------------------------------- G5

def test_g5_blocks_when_final_not_accelerated(tmp_path, pipe):
    pipe["durs"]["final_9x16"] = 28.8       # same as captioned: no speed-up
    with pytest.raises(GateFail) as e:
        build(write_config(tmp_path))
    assert "1.2" in str(e.value)


def test_g5_uses_config_factor(tmp_path, pipe):
    pipe["durs"]["final_9x16"] = 19.2       # 28.8 / 1.5
    pipe["durs"]["final_1x1"] = 19.2
    m = build(write_config(tmp_path, accelerate=1.5))
    assert m["all_pass"]
    assert all(c[1] == pytest.approx(1.5) for c in _called(pipe, "accel"))


# ------------------------------------------------------------------- G6

def test_g6_blocks_on_big_silence_in_final(tmp_path, pipe):
    pipe["final_sil"] = [0.9]
    with pytest.raises(GateFail) as e:
        build(write_config(tmp_path))
    assert "silence" in str(e.value).lower()


def test_g6_blocks_on_variant_duration_mismatch(tmp_path, pipe):
    # variant b passes ITS OWN accelerate gate (30.0 / 1.2 = 25.0) but its
    # final duration disagrees with variant a's by 1.0s > 0.7 tolerance
    pipe["durs"] = {os.path.join("b", "captions_9x16"): 30.0,
                    "ad_b_final_9x16": 25.0,
                    "final_9x16": 24.0, "final_1x1": 24.0}
    with pytest.raises(GateFail) as e:
        build(write_config(tmp_path, avatars=AVATARS))
    assert "variant_duration_consistent" in str(e.value)


# ------------------------------------------------------- variants (serial)

def test_variants_run_sequentially_and_are_listed(tmp_path, pipe):
    m = build(write_config(tmp_path, avatars=AVATARS))
    assert [c[1] for c in _called(pipe, "avatar")] == ["AV_A", "AV_B"]
    assert [v["name"] for v in m["variants"]] == ["a", "b"]
    assert m["all_pass"]


# ------------------------------------------------------------------- G7

def test_g7_skipped_without_drive_folder(tmp_path, pipe):
    m = build(write_config(tmp_path))
    assert not _called(pipe, "push")
    assert m["drive"] is None


def test_g7_uploads_and_records_folder_link(tmp_path, pipe):
    m = build(write_config(tmp_path, drive_folder=DRIVE))
    (call,) = _called(pipe, "push")
    assert call[1] == DRIVE
    assert "ad_default_9x16.mp4" in call[2]
    assert "ad_default_1x1.mp4" in call[2]
    assert m["drive"]["folder_link"].endswith("/F")
    assert m["all_pass"]


def test_g7_blocks_when_upload_not_verified(tmp_path, pipe):
    pipe["push_ok"] = False
    with pytest.raises(GateFail) as e:
        build(write_config(tmp_path, drive_folder=DRIVE))
    assert "drive" in str(e.value).lower()


# ----------------------------------------------------------- config & CLI

def test_missing_project_section_is_friendly_config_error(tmp_path, pipe):
    p = tmp_path / "build.yaml"
    p.write_text('avatar_id: "AV_ONE"\n', encoding="utf-8")
    with pytest.raises(ConfigError) as e:
        build(str(p))
    assert "project" in str(e.value)


def test_cli_main_returns_0_on_success(tmp_path, pipe):
    assert bmod.main([write_config(tmp_path)]) == 0


def test_cli_main_exits_1_on_gate_fail(tmp_path, pipe):
    cfg = write_config(tmp_path)
    os.remove(tmp_path / "voice.mp3")
    assert bmod.main([cfg]) == 1
