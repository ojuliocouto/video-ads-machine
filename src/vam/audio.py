"""Voice hygiene (de-breath): shorten ONLY the big silences in a real voice recording.

This is the mandatory step between the raw voice take and the avatar generation.
People pause to breathe between sentences (0.5-2s gaps, breath noise included).
Those big pauses must shrink or the ad drags; the short natural pauses (< ~0.5s)
must stay untouched or the result sounds choppy and robotic.

How it works (energy-based, validated approach):
  1. ffmpeg ``silencedetect`` (noise=``sil_db``) finds the silence regions by ENERGY.
     This is the ground truth of the real pauses. Transcription word timestamps are
     NEVER used to drive cuts (they are too short and miss big silences).
  2. Only in pauses longer than ``big_sil`` the MIDDLE of the region is cut, leaving
     ``keep_pause`` behind. Cutting inside the silence means a word is never cut,
     and few cuts means zero choppiness.
  3. Dead silence at the head/tail of the file is trimmed.
  4. A micro-fade is applied at every splice point.

IMPORTANT: the default ``sil_db`` threshold of -30 dB assumes a CLEAN recording
(a decent microphone, no echo, low room noise). On a noisy or echoey take the
noise floor sits above -30 dB, silences are never detected and nothing is cut.
If that happens, raise ``audio.sil_db`` in your config (e.g. -25) or, better,
re-record in a quieter setup.

Public API:
    clean_voice(src, dst, cfg) -> dict with metrics
        {cuts, removed_s, src_dur, dst_dur, residual_big, notes}
"""
import os
import re
import subprocess

# Fixed tuning constants (validated; not user-facing config).
MIN_DETECT = 0.28   # minimum silence duration for the detector (s)
LEAD_KEEP = 0.12    # silence kept at the very start of the file (s)
TRAIL_KEEP = 0.30   # silence kept at the very end of the file (s)
FADE = 0.012        # micro cross-fade at each splice point (s)
_EDGE = 0.06        # tolerance to treat a silence as head/tail of the file (s)

_START_RE = re.compile(r"silence_start:\s*(-?\d+\.?\d*)")
_END_RE = re.compile(r"silence_end:\s*(-?\d+\.?\d*)")


class AudioError(RuntimeError):
    """Raised when ffmpeg/ffprobe fails while cleaning the voice track."""


def _cfg_get(obj, name, default):
    """Read ``name`` from an attribute-style or dict-style config node."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _audio_cfg(cfg):
    node = _cfg_get(cfg, "audio", None)
    return {
        "big_sil": float(_cfg_get(node, "big_sil", 0.55)),
        "keep_pause": float(_cfg_get(node, "keep_pause", 0.26)),
        "sil_db": int(_cfg_get(node, "sil_db", -30)),
    }


def _run(cmd, what):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise AudioError(f"ffmpeg failed while {what}:\n{r.stderr[-800:]}")
    return r


def _duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise AudioError(f"could not read duration of {path}:\n{r.stderr[-400:]}")


def parse_silences(stderr_text):
    """Parse ffmpeg silencedetect stderr into a list of (start, end) tuples."""
    out, start = [], None
    for line in stderr_text.splitlines():
        m = _START_RE.search(line)
        if m:
            start = float(m.group(1))
            continue
        m = _END_RE.search(line)
        if m and start is not None:
            out.append((max(0.0, start), float(m.group(1))))
            start = None
    return out


def detect_silences(path, sil_db, min_detect=MIN_DETECT):
    """Silence regions (start, end) via ffmpeg silencedetect (energy ground truth)."""
    r = subprocess.run(
        ["ffmpeg", "-i", path,
         "-af", f"silencedetect=noise={sil_db}dB:d={min_detect}",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    return parse_silences(r.stderr)


def plan_cuts(silences, total, big_sil, keep_pause):
    """Turn silence regions into cut intervals. Returns (cuts, notes).

    Head/tail silences are trimmed down to LEAD_KEEP/TRAIL_KEEP; interior
    silences longer than ``big_sil`` lose their middle, leaving ``keep_pause``.
    Every cut lives strictly inside a silence region, so words are never cut.
    """
    cuts, notes = [], []
    for s, e in silences:
        d = e - s
        if s <= _EDGE:  # leading silence
            if e - LEAD_KEEP > 0.05:
                cuts.append((0.0, round(e - LEAD_KEEP, 3)))
                notes.append(f"head trim {e - LEAD_KEEP:.2f}s")
            continue
        if e >= total - _EDGE:  # trailing silence
            if total - (s + TRAIL_KEEP) > 0.05:
                cuts.append((round(s + TRAIL_KEEP, 3), total))
                notes.append(f"tail trim {total - (s + TRAIL_KEEP):.2f}s")
            continue
        if d > big_sil:  # big silence (breath) -> shorten the middle
            cut_len = d - keep_pause
            mid = (s + e) / 2
            a = round(mid - cut_len / 2, 3)
            b = round(mid + cut_len / 2, 3)
            cuts.append((a, b))
            notes.append(
                f"big silence {d:.2f}s at {s:.2f}-{e:.2f}s -> "
                f"cut {b - a:.2f}s (pause left {d - (b - a):.2f}s)"
            )
    return cuts, notes


def _render(src, dst, cuts, total):
    """Concatenate the keep segments with a micro-fade at each splice."""
    keeps, cur = [], 0.0
    for a, b in sorted(cuts):
        if a > cur:
            keeps.append((cur, a))
        cur = max(cur, b)
    if cur < total:
        keeps.append((cur, total))

    parts, labels = [], []
    for idx, (a, b) in enumerate(keeps):
        d = b - a
        lbl = f"k{idx}"
        parts.append(
            f"[0:a]atrim={a}:{b},asetpts=N/SR/TB,"
            f"afade=t=in:st=0:d={FADE},"
            f"afade=t=out:st={max(0.0, d - FADE):.3f}:d={FADE}[{lbl}]"
        )
        labels.append(f"[{lbl}]")
    fc = ";".join(parts) + ";" + "".join(labels) + f"concat=n={len(keeps)}:v=0:a=1[o]"
    _run(["ffmpeg", "-y", "-i", src, "-filter_complex", fc, "-map", "[o]"]
         + _codec_args(dst) + [dst], "concatenating keep segments")


def _codec_args(dst):
    if dst.lower().endswith(".mp3"):
        return ["-c:a", "libmp3lame", "-b:a", "192k"]
    return []


def clean_voice(src, dst, cfg):
    """Shorten big silences in ``src`` and write the cleaned track to ``dst``.

    Thresholds come from ``cfg.audio`` (``big_sil``, ``keep_pause``, ``sil_db``).
    Returns a metrics dict:
        cuts          number of cut intervals applied
        removed_s     total seconds removed
        src_dur       input duration (s)
        dst_dur       output duration (s)
        residual_big  interior silences still > big_sil in the OUTPUT (should be [])
        notes         human-readable description of each cut
    """
    a = _audio_cfg(cfg)
    src = os.path.abspath(src)
    dst = os.path.abspath(dst)
    if not os.path.exists(src):
        raise AudioError(f"input audio not found: {src}")

    total = _duration(src)
    silences = detect_silences(src, a["sil_db"])
    cuts, notes = plan_cuts(silences, total, a["big_sil"], a["keep_pause"])

    if not cuts:
        if os.path.splitext(src)[1].lower() == os.path.splitext(dst)[1].lower():
            _run(["ffmpeg", "-y", "-i", src, "-c", "copy", dst], "copying (no cuts)")
        else:
            _run(["ffmpeg", "-y", "-i", src] + _codec_args(dst) + [dst],
                 "transcoding (no cuts)")
    else:
        _render(src, dst, cuts, total)

    dst_dur = _duration(dst)
    residual_big = [
        (round(s, 3), round(e, 3))
        for s, e in detect_silences(dst, a["sil_db"])
        if (e - s) > a["big_sil"] and s > _EDGE and e < dst_dur - _EDGE
    ]
    return {
        "cuts": len(cuts),
        "removed_s": round(sum(b - x for x, b in cuts), 3),
        "src_dur": round(total, 3),
        "dst_dur": round(dst_dur, 3),
        "residual_big": residual_big,
        "notes": notes,
    }
