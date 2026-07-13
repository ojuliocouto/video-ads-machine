"""Shared ffmpeg/ffprobe helpers used by every module in the pipeline.

One place for the three things everyone needs:
- run an ffmpeg command with a readable error when it fails
- measure media duration
- detect silence regions (energy-based ground truth via silencedetect)
"""
import re
import subprocess

# How many trailing chars of ffmpeg stderr to include in error messages.
_STDERR_TAIL = 800

_RE_SILENCE_START = re.compile(r"silence_start:\s*(-?\d+\.?\d*)")
_RE_SILENCE_END = re.compile(r"silence_end:\s*(-?\d+\.?\d*)")


def run_ffmpeg(cmd, label=""):
    """Run an ffmpeg/ffprobe command, raising RuntimeError on failure.

    Args:
        cmd: full argv list (e.g. ["ffmpeg", "-y", ...]).
        label: short step name shown in the error message (e.g. "accelerate").

    Returns:
        The CompletedProcess (stdout/stderr captured as text) on success.
    """
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        step = label or cmd[0]
        raise RuntimeError(
            f"ffmpeg step '{step}' failed (exit {r.returncode}):\n"
            f"{r.stderr[-_STDERR_TAIL:]}"
        )
    return r


def duration(path):
    """Return media duration in seconds via ffprobe."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True,
    )
    out = (r.stdout or "").strip()
    if r.returncode != 0 or not out:
        raise RuntimeError(
            f"ffprobe could not read duration of '{path}':\n"
            f"{(r.stderr or '')[-_STDERR_TAIL:]}"
        )
    return float(out)


def silence_regions(path, noise_db=-30, min_dur=0.28):
    """Detect silence regions as (start, end) pairs, in seconds.

    Uses ffmpeg silencedetect (energy-based, the ground truth for real
    pauses). Only silences longer than `min_dur` below `noise_db` dBFS are
    reported. Negative starts (decoder padding) are clamped to 0.
    """
    r = subprocess.run(
        ["ffmpeg", "-i", path,
         "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    regions = []
    start = None
    for line in r.stderr.splitlines():
        m = _RE_SILENCE_START.search(line)
        if m:
            start = float(m.group(1))
            continue
        m = _RE_SILENCE_END.search(line)
        if m and start is not None:
            regions.append((max(0.0, start), float(m.group(1))))
            start = None
    return regions


def big_silences(path, noise_db=-30, min_dur=0.28):
    """Return the durations (seconds) of every silence region detected.

    Convenience wrapper over silence_regions() for quality gates that only
    care whether long pauses remain (e.g. after voice cleanup).
    """
    return [end - start for start, end in silence_regions(path, noise_db, min_dur)]
