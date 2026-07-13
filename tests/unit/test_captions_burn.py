"""Tests for the caption timing engine and burn() integration.

Covers the validated behaviors ported from the original engine:
- sequential layout with HOLD_MAX (captions never freeze on a pause)
- blanking of lettering scenes from montage timing (including the
  opening scene special case, where reel-time can be negative)
- verbatim script words (never the raw transcription)
- the 1x1 square composite helper (blur-pad recipe), subprocess mocked
"""
import json
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from vam import captions as caps  # noqa: E402


def _cfg(tmp_path):
    return types.SimpleNamespace(
        workdir=str(tmp_path / "build"),
        fonts_dir=str(tmp_path / "fonts"),
    )


# ---------------------------------------------------------------- layout

def test_hold_max_caps_display_after_speech_ends():
    # Long pause before the next word: the word must disappear at most
    # HOLD_MAX after its spoken end, never stay frozen until next word.
    raws = [("word", 0.0, 0.3), ("next", 3.0, 3.4)]
    out = caps.sequential_layout(raws)
    assert out[0][2] == pytest.approx(0.3 + caps.HOLD_MAX, abs=1e-3)
    assert out[0][2] < 3.0  # gap stays blank until the next word


def test_hold_max_constant_is_validated_value():
    assert caps.HOLD_MAX == 0.45


def test_min_duration_floor():
    raws = [("a", 0.0, 0.05), ("b", 0.05, 0.5)]
    out = caps.sequential_layout(raws)
    assert out[0][2] - out[0][1] >= caps.MIN_DUR - 1e-6


def test_zero_overlap_even_with_messy_input_times():
    # Non-monotonic aligner glitch: layout must still emit ordered,
    # non-overlapping windows.
    raws = [("um", 0.0, 0.9), ("dois", 0.2, 0.5), ("tres", 0.4, 1.4)]
    out = caps.sequential_layout(raws)
    for cur, nxt in zip(out, out[1:]):
        assert cur[2] <= nxt[1] + 1e-6
    for w, s, e in out:
        assert e > s


# ---------------------------------------------------------------- blanking

A0 = 2.0  # avatar audio starts 2s into the reel


def test_blank_opening_lettering_covers_negative_reel_times():
    # Opening scene: lettering range starts at reel ~0; the first spoken
    # words can land at NEGATIVE reel-time (aligned before a0). All of
    # them must be blanked, up to the end of the opening range.
    letterings = [{"s": A0 + 0.0, "e": A0 + 2.0}]  # reel 0.0 .. 2.0
    raws = [("early", -0.5, -0.2), ("inside", 1.0, 1.3),
            ("after", 2.2, 2.5)]
    out = caps.blank_letterings(raws, letterings, A0)
    assert [w for w, _, _ in out] == ["after"]


def test_blank_mid_lettering_uses_tight_margin():
    # Mid-video lettering: only words starting inside the range (with a
    # tight margin) are blanked; neighbors survive.
    letterings = [{"s": A0 + 5.0, "e": A0 + 7.0}]  # reel 5.0 .. 7.0
    raws = [("before", 4.8, 5.0), ("inside", 5.5, 5.8),
            ("edge", 6.99, 7.2), ("after", 7.2, 7.5)]
    out = caps.blank_letterings(raws, letterings, A0)
    assert [w for w, _, _ in out] == ["before", "after"]


def test_blank_noop_without_letterings():
    raws = [("a", 0.0, 0.3), ("b", 0.4, 0.7)]
    assert caps.blank_letterings(raws, [], A0) == raws


# ---------------------------------------------------------------- 1x1 helper

def test_make_square_builds_validated_blur_pad_filter(monkeypatch):
    calls = []
    monkeypatch.setattr(
        caps, "run_ffmpeg", lambda cmd, label="": calls.append(cmd))
    caps.make_square("in.mp4", "out.mp4")
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[0] == "ffmpeg" and "in.mp4" in cmd and cmd[-1] == "out.mp4"
    fc = cmd[cmd.index("-filter_complex") + 1]
    # validated recipe: blurred cover background + full 9:16 frame centered
    assert "scale=1080:1080:force_original_aspect_ratio=increase" in fc
    assert "crop=1080:1080" in fc
    assert "boxblur=24:1" in fc
    assert "scale=-1:1080" in fc
    assert "overlay=(W-w)/2:0" in fc


# ---------------------------------------------------------------- burn()

def _alignment(tmp_path, tokens):
    path = tmp_path / "alignment.json"
    path.write_text(json.dumps({"result": {"tokens": tokens}}))
    return str(path)


def _burn(tmp_path, monkeypatch, blocks, timing, tokens, fmt="9x16"):
    ap = _alignment(tmp_path, tokens)
    calls = []
    monkeypatch.setattr(
        caps, "run_ffmpeg", lambda cmd, label="": calls.append(cmd))
    cfg = _cfg(tmp_path)
    caps.burn("base.mp4", "out.mp4", blocks, fmt, cfg, timing,
              alignment_path=ap)
    cmd = calls[0]
    vf = cmd[cmd.index("-vf") + 1]
    ass_path = vf.split("subtitles=")[1].split(":fontsdir")[0]
    return cmd, open(ass_path).read()


def test_burn_uses_verbatim_script_words_not_transcription(
        tmp_path, monkeypatch):
    # The aligner transcribed "skils" (typo); the script says "skills".
    # Captions must show the script word, timed by the alignment.
    tokens = [{"start": 2.0, "end": 2.4, "text": " topa"},
              {"start": 2.5, "end": 3.0, "text": " skils"}]
    blocks = [{"narr": "topa skills", "instr": "", "tipo": "orig",
               "key": None, "lead": None}]
    timing = {"a0": 2.0, "total": 10.0, "letterings": [], "inserts": []}
    cmd, ass = _burn(tmp_path, monkeypatch, blocks, timing, tokens)
    assert "skills" in ass
    assert "skils," not in ass and ",skils" not in ass
    assert "}skils" not in ass  # transcription word never rendered
    # fonts dir from cfg is passed to ffmpeg so bundled fonts resolve
    assert "fontsdir=" in cmd[cmd.index("-vf") + 1]


def test_burn_blanks_opening_lettering_scene(tmp_path, monkeypatch):
    # Words spoken during the opening lettering (even at negative
    # reel-time) never appear in the ASS.
    tokens = [{"start": 1.5, "end": 1.9, "text": " oculto"},
              {"start": 4.5, "end": 4.9, "text": " visivel"}]
    blocks = [{"narr": "oculto visivel", "instr": "", "tipo": "orig",
               "key": None, "lead": None}]
    timing = {"a0": 2.0, "total": 10.0,
              "letterings": [{"s": 2.0, "e": 4.0}], "inserts": []}
    _, ass = _burn(tmp_path, monkeypatch, blocks, timing, tokens)
    assert "oculto" not in ass
    assert "visivel" in ass


def test_burn_1x1_produces_square_playres(tmp_path, monkeypatch):
    # 1x1 burn expects a SQUARE composite as src (see make_square);
    # the ASS canvas must be 1080x1080 with the scaled font.
    tokens = [{"start": 0.0, "end": 0.4, "text": " topa"}]
    blocks = [{"narr": "topa", "instr": "", "tipo": "orig",
               "key": None, "lead": None}]
    timing = {"a0": 0.0, "total": 5.0, "letterings": [], "inserts": []}
    _, ass = _burn(tmp_path, monkeypatch, blocks, timing, tokens,
                   fmt="1x1")
    assert "PlayResY:1080" in ass


def test_burn_rejects_unknown_format(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        caps.burn("a.mp4", "b.mp4", [], "16x9", _cfg(tmp_path),
                  {"a0": 0, "letterings": []})
