"""Speed up the final video, pitch preserved (standard last step of the pipeline).

An accelerated ad feels more dynamic and retains better. The validated default
factor is 1.2x (the caption timing is calibrated for it: min caption duration
0.22s becomes ~0.18s after acceleration). Video (setpts) and audio (atempo,
which preserves pitch so the voice stays natural, just faster) are sped up in
sync.
"""
from .ffutil import run_ffmpeg

DEFAULT_FACTOR = 1.2

# atempo accepts 0.5..2.0 per filter stage; outside that range we chain stages.
_ATEMPO_MIN = 0.5
_ATEMPO_MAX = 2.0


def _fmt(x):
    """Format a float without trailing zeros (1.2 -> '1.2', 2.0 -> '2')."""
    return f"{x:g}"


def _atempo_chain(factor):
    """Build the atempo filter expression, chaining stages when the factor
    falls outside atempo's supported 0.5..2.0 range."""
    stages = []
    remaining = float(factor)
    while remaining > _ATEMPO_MAX:
        stages.append(_ATEMPO_MAX)
        remaining /= _ATEMPO_MAX
    while remaining < _ATEMPO_MIN:
        stages.append(_ATEMPO_MIN)
        remaining /= _ATEMPO_MIN
    stages.append(remaining)
    return ",".join(f"atempo={_fmt(s)}" for s in stages)


def accelerate(src, dst, factor=DEFAULT_FACTOR):
    """Re-encode `src` to `dst` sped up by `factor`, audio pitch preserved.

    Args:
        src: input video path.
        dst: output video path (mp4, H.264 + AAC, faststart for web playback).
        factor: speed multiplier (> 0). Default 1.2 (validated).
    """
    factor = float(factor)
    if factor <= 0:
        raise ValueError(f"accelerate factor must be > 0, got {factor}")
    fc = f"[0:v]setpts=PTS/{_fmt(factor)}[v];[0:a]{_atempo_chain(factor)}[a]"
    run_ffmpeg(
        ["ffmpeg", "-y", "-i", src,
         "-filter_complex", fc,
         "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart",
         dst],
        label="accelerate",
    )
