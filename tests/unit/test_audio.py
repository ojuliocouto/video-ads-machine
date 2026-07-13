"""Tests for vam.audio (energy-based de-breath / silence shortening).

Two layers:
  1. Pure parsing/planning tests with a fake ffmpeg silencedetect stderr (no ffmpeg needed).
  2. End-to-end test with a synthetic wav (tone 1s + silence 1.2s + tone 1s), skipped
     when ffmpeg is not available. No real API, no real recordings.
"""
import os
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from vam import audio  # noqa: E402

FFMPEG = shutil.which("ffmpeg")


def make_cfg(big_sil=0.55, keep_pause=0.26, sil_db=-30):
    return SimpleNamespace(
        audio=SimpleNamespace(big_sil=big_sil, keep_pause=keep_pause, sil_db=sil_db)
    )


# ---------------------------------------------------------------- parsing

FAKE_STDERR = """\
[silencedetect @ 0x7f8] silence_start: 1.001
[silencedetect @ 0x7f8] silence_end: 2.203 | silence_duration: 1.202
frame= 1 fps=0.0
[silencedetect @ 0x7f8] silence_start: 4.5
[silencedetect @ 0x7f8] silence_end: 4.9 | silence_duration: 0.4
"""


def test_parse_silences_from_fake_stderr():
    sils = audio.parse_silences(FAKE_STDERR)
    assert sils == [(1.001, 2.203), (4.5, 4.9)]


def test_parse_silences_clamps_negative_start():
    sils = audio.parse_silences(
        "silence_start: -0.01\nsilence_end: 0.5 | silence_duration: 0.51\n"
    )
    assert sils == [(0.0, 0.5)]


def test_parse_silences_ignores_end_without_start():
    assert audio.parse_silences("silence_end: 3.0 | silence_duration: 1.0\n") == []


# ---------------------------------------------------------------- planning

def test_plan_cuts_shortens_only_big_silences():
    # one big silence (1.2s) in the middle, one small (0.4s): only the big is cut
    sils = [(1.0, 2.2), (4.5, 4.9)]
    cuts, _ = audio.plan_cuts(sils, total=6.0, big_sil=0.55, keep_pause=0.26)
    assert len(cuts) == 1
    a, b = cuts[0]
    # cut is centered inside the silence and leaves ~keep_pause behind
    assert 1.0 < a < b < 2.2
    assert (b - a) == pytest.approx(1.2 - 0.26, abs=0.01)


def test_plan_cuts_never_cuts_words():
    # every cut interval must live strictly inside a detected silence region
    sils = [(0.8, 2.0), (3.0, 4.4)]
    cuts, _ = audio.plan_cuts(sils, total=6.0, big_sil=0.55, keep_pause=0.26)
    for a, b in cuts:
        assert any(s <= a and b <= e for s, e in sils)


def test_plan_cuts_trims_edges():
    # leading silence 0..0.8 and trailing silence 5.0..6.0
    sils = [(0.0, 0.8), (5.0, 6.0)]
    cuts, _ = audio.plan_cuts(sils, total=6.0, big_sil=0.55, keep_pause=0.26)
    assert (0.0, pytest.approx(0.8 - audio.LEAD_KEEP, abs=0.01)) == cuts[0]
    assert cuts[1][0] == pytest.approx(5.0 + audio.TRAIL_KEEP, abs=0.01)
    assert cuts[1][1] == 6.0


def test_plan_cuts_no_big_silence_means_no_cuts():
    cuts, _ = audio.plan_cuts([(2.0, 2.4)], total=6.0, big_sil=0.55, keep_pause=0.26)
    assert cuts == []


# ---------------------------------------------------------------- end-to-end

@pytest.fixture
def synthetic_wav(tmp_path):
    """tone 1s + silence 1.2s + tone 1s, mono 44.1kHz."""
    wav = str(tmp_path / "voice.wav")
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=1.2",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1[o]",
         "-map", "[o]", "-ar", "44100", "-ac", "1", wav],
        capture_output=True, check=True,
    )
    return wav


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not available")
def test_clean_voice_shortens_big_pause(tmp_path, synthetic_wav):
    dst = str(tmp_path / "clean.wav")
    cfg = make_cfg()
    m = audio.clean_voice(synthetic_wav, dst, cfg)

    assert os.path.exists(dst)
    assert m["cuts"] == 1
    # 1.2s pause shrinks to ~keep_pause (0.26s): about 0.94s removed
    assert m["removed_s"] == pytest.approx(1.2 - 0.26, abs=0.25)
    assert m["dst_dur"] == pytest.approx(m["src_dur"] - m["removed_s"], abs=0.15)
    # both 1s tones are still there: output can't be shorter than tones + kept pause
    assert m["dst_dur"] >= 2.0
    # nothing above big_sil should remain
    assert m["residual_big"] == []


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not available")
def test_clean_voice_keeps_short_pauses(tmp_path):
    # tone 1s + silence 0.4s (< big_sil) + tone 1s: nothing to cut
    wav = str(tmp_path / "short.wav")
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=0.4",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1[o]",
         "-map", "[o]", "-ar", "44100", "-ac", "1", wav],
        capture_output=True, check=True,
    )
    dst = str(tmp_path / "clean.wav")
    m = audio.clean_voice(wav, dst, make_cfg())
    assert m["cuts"] == 0
    assert m["dst_dur"] == pytest.approx(m["src_dur"], abs=0.1)


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not available")
def test_clean_voice_accepts_dict_style_cfg(tmp_path, synthetic_wav):
    dst = str(tmp_path / "clean_dict.wav")
    cfg = {"audio": {"big_sil": 0.55, "keep_pause": 0.26, "sil_db": -30}}
    m = audio.clean_voice(synthetic_wav, dst, cfg)
    assert m["cuts"] == 1
