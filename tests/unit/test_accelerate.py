"""Unit tests for vam.accelerate (speed up final video, pitch preserved).

No real ffmpeg calls: run_ffmpeg is mocked.
"""
from unittest import mock

import pytest

from vam import accelerate as acc


def _call_and_capture(src="in.mp4", dst="out.mp4", **kwargs):
    with mock.patch.object(acc, "run_ffmpeg") as m:
        acc.accelerate(src, dst, **kwargs)
    return m.call_args[0][0]


def test_default_factor_is_validated_1_2x():
    cmd = _call_and_capture()
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert fc == "[0:v]setpts=PTS/1.2[v];[0:a]atempo=1.2[a]"


def test_filter_complex_for_explicit_factor():
    cmd = _call_and_capture(factor=1.5)
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert fc == "[0:v]setpts=PTS/1.5[v];[0:a]atempo=1.5[a]"


def test_output_encoding_flags_match_validated_engine():
    cmd = _call_and_capture()
    joined = " ".join(cmd)
    assert cmd[0] == "ffmpeg"
    assert "-y" in cmd
    assert "-map [v]" in joined and "-map [a]" in joined
    assert "-c:v libx264" in joined
    assert "-crf 18" in joined
    assert "-pix_fmt yuv420p" in joined
    assert "-c:a aac" in joined
    assert "-b:a 160k" in joined
    assert "-movflags +faststart" in joined
    assert cmd[-1] == "out.mp4"
    assert cmd[cmd.index("-i") + 1] == "in.mp4"


def test_factor_above_2_chains_atempo():
    # atempo only accepts 0.5..2.0 per stage; higher factors must chain
    cmd = _call_and_capture(factor=2.5)
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert fc == "[0:v]setpts=PTS/2.5[v];[0:a]atempo=2,atempo=1.25[a]"


def test_factor_below_half_chains_atempo():
    cmd = _call_and_capture(factor=0.25)
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert fc == "[0:v]setpts=PTS/0.25[v];[0:a]atempo=0.5,atempo=0.5[a]"


@pytest.mark.parametrize("bad", [0, -1.2])
def test_invalid_factor_raises_value_error(bad):
    with pytest.raises(ValueError):
        acc.accelerate("in.mp4", "out.mp4", factor=bad)


def test_factor_1_is_a_noop_remux_still_produces_output():
    # factor 1.0 is pointless but must not crash; command still valid
    cmd = _call_and_capture(factor=1.0)
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert fc == "[0:v]setpts=PTS/1[v];[0:a]atempo=1[a]"
