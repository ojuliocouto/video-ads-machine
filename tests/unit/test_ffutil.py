"""Unit tests for vam.ffutil (ffmpeg helpers shared by all modules).

No real ffmpeg/ffprobe calls: subprocess is mocked everywhere.
"""
import subprocess
from unittest import mock

import pytest

from vam import ffutil


def _proc(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode,
                                       stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------- run_ffmpeg

def test_run_ffmpeg_returns_completed_process_on_success():
    with mock.patch.object(ffutil.subprocess, "run",
                           return_value=_proc(0, stderr="ok")) as m:
        r = ffutil.run_ffmpeg(["ffmpeg", "-y", "-i", "a.mp4", "b.mp4"], "test-step")
    assert r.returncode == 0
    m.assert_called_once()
    # capture_output + text mode so stderr parsing works downstream
    _, kwargs = m.call_args
    assert kwargs.get("capture_output") is True
    assert kwargs.get("text") is True


def test_run_ffmpeg_raises_with_label_and_stderr_tail_on_failure():
    err = "x" * 2000 + "REAL ERROR AT THE END"
    with mock.patch.object(ffutil.subprocess, "run",
                           return_value=_proc(1, stderr=err)):
        with pytest.raises(RuntimeError) as ei:
            ffutil.run_ffmpeg(["ffmpeg", "-i", "a.mp4"], "accelerate")
    msg = str(ei.value)
    assert "accelerate" in msg
    assert "REAL ERROR AT THE END" in msg
    # only the tail of stderr is included, not the whole 2KB blob
    assert len(msg) < 1500


# ------------------------------------------------------------------ duration

def test_duration_parses_ffprobe_stdout():
    with mock.patch.object(ffutil.subprocess, "run",
                           return_value=_proc(0, stdout="12.345\n")) as m:
        d = ffutil.duration("clip.mp4")
    assert d == pytest.approx(12.345)
    cmd = m.call_args[0][0]
    assert cmd[0] == "ffprobe"
    assert "clip.mp4" in cmd


def test_duration_raises_clear_error_when_ffprobe_fails():
    with mock.patch.object(ffutil.subprocess, "run",
                           return_value=_proc(1, stdout="", stderr="no such file")):
        with pytest.raises(RuntimeError) as ei:
            ffutil.duration("missing.mp4")
    assert "missing.mp4" in str(ei.value)


# ------------------------------------------------------- silencedetect parse

FAKE_SILENCEDETECT_STDERR = """\
Input #0, mp3, from 'voice.mp3':
  Duration: 00:00:30.00, start: 0.000000, bitrate: 192 kb/s
[silencedetect @ 0x600] silence_start: 3.25
[silencedetect @ 0x600] silence_end: 4.05 | silence_duration: 0.8
[silencedetect @ 0x600] silence_start: 10.5
[silencedetect @ 0x600] silence_end: 10.9 | silence_duration: 0.4
[silencedetect @ 0x600] silence_start: -0.011
[silencedetect @ 0x600] silence_end: 0.55 | silence_duration: 0.561
size=N/A time=00:00:30.00 bitrate=N/A speed= 500x
"""


def test_silence_regions_parses_start_end_pairs():
    with mock.patch.object(ffutil.subprocess, "run",
                           return_value=_proc(0, stderr=FAKE_SILENCEDETECT_STDERR)):
        regions = ffutil.silence_regions("voice.mp3", noise_db=-30, min_dur=0.28)
    assert regions == [
        (3.25, 4.05),
        (10.5, 10.9),
        (0.0, 0.55),  # negative start clamped to 0
    ]


def test_silence_regions_builds_silencedetect_filter():
    with mock.patch.object(ffutil.subprocess, "run",
                           return_value=_proc(0, stderr="")) as m:
        ffutil.silence_regions("voice.mp3", noise_db=-35, min_dur=0.5)
    cmd = m.call_args[0][0]
    af = cmd[cmd.index("-af") + 1]
    assert "silencedetect" in af
    assert "noise=-35dB" in af
    assert "d=0.5" in af


def test_big_silences_returns_durations_of_detected_silences():
    with mock.patch.object(ffutil.subprocess, "run",
                           return_value=_proc(0, stderr=FAKE_SILENCEDETECT_STDERR)):
        durs = ffutil.big_silences("voice.mp3", noise_db=-30, min_dur=0.28)
    assert durs == [
        pytest.approx(0.8),
        pytest.approx(0.4),
        pytest.approx(0.55),
    ]


def test_big_silences_empty_when_no_silence_lines():
    with mock.patch.object(ffutil.subprocess, "run",
                           return_value=_proc(0, stderr="frame=1 fps=0")):
        assert ffutil.big_silences("voice.mp3", -30, 0.28) == []


def test_silence_regions_ignores_unpaired_end():
    stderr = "[silencedetect @ 0x1] silence_end: 5.0 | silence_duration: 1.0\n"
    with mock.patch.object(ffutil.subprocess, "run",
                           return_value=_proc(0, stderr=stderr)):
        assert ffutil.silence_regions("voice.mp3", -30, 0.28) == []
