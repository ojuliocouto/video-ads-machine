#!/usr/bin/env python3
"""Command-line interface of the Video Ads Machine.

Commands:
  vam doctor [--config X]       environment/account checks with fixes (run this first)
  vam setup                     alias of doctor
  vam build <config.yaml>       full pipeline (voice -> avatar -> montage -> captions)
  vam clean-audio <in> <out>    voice hygiene only (shorten the big silences)
  vam caption <base> <out>      burn a caption track on an existing video
  vam version
"""
import argparse
import importlib
import json
import os
import subprocess
import sys

from . import __version__
from . import doctor
from . import captions as caps

FONTS = os.path.join(os.path.dirname(__file__), "..", "..", "fonts")


def _burn(base_in, out, ass):
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", base_in, "-vf", f"subtitles={ass}:fontsdir={FONTS}",
         "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy",
         "-movflags", "+faststart", out],
        capture_output=True, text=True)
    if r.returncode != 0:
        print("ffmpeg error:\n", r.stderr[-1200:])
        sys.exit(1)


def cmd_caption(a):
    # align: JSON file with [[word, start, end], ...] (reel-time, seconds)
    words = [tuple(w) for w in json.load(open(a.align))]
    if a.style not in caps.STYLES:
        print(f"style '{a.style}' does not exist: {', '.join(caps.STYLES)}")
        sys.exit(1)
    ass = caps.build_ass(words, a.style, "/tmp/vam_cap.ass", fmt=a.format)
    _burn(a.base, a.out, ass)
    print("OK", a.out, f"(style={a.style} format={a.format} words={len(words)})")


def cmd_build(a):
    """Run the full pipeline; a failed gate exits with code 1 and a clear reason."""
    try:
        build_mod = importlib.import_module("vam.build")
    except ImportError as exc:
        print(f"the build module could not be loaded: {exc}", file=sys.stderr)
        sys.exit(1)
    gate_fail = getattr(build_mod, "GateFail", Exception)
    try:
        manifest = build_mod.build(a.config)
    except gate_fail as exc:
        print(f"BUILD BLOCKED: {exc}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(manifest, indent=2, ensure_ascii=False, default=str))


def cmd_clean_audio(a):
    """Voice hygiene standalone: useful to audition the cleaned take by itself."""
    from . import audio
    cfg = None
    if a.config:
        from .config import load as load_config
        cfg = load_config(a.config)
    metrics = audio.clean_voice(a.src, a.dst, cfg)
    print(json.dumps(metrics, indent=2, ensure_ascii=False, default=str))


def main():
    p = argparse.ArgumentParser(prog="vam", description="Video Ads Machine")
    sub = p.add_subparsers(dest="cmd")

    for name in ("doctor", "setup"):
        d = sub.add_parser(name, help="environment/account checks with fixes"
                           + (" (alias of doctor)" if name == "setup" else ""))
        d.add_argument("--config", default=None,
                       help="config YAML to validate avatar_id/Drive against "
                            "(default: ./config.yaml when present)")

    sub.add_parser("version", help="print the version")

    b = sub.add_parser("build", help="full pipeline: config + script + voice -> final videos")
    b.add_argument("config", help="path to your config.yaml")

    ca = sub.add_parser("clean-audio", help="shorten the big silences of a voice take")
    ca.add_argument("src", help="input audio (the raw voice recording)")
    ca.add_argument("dst", help="output audio (cleaned)")
    ca.add_argument("--config", default=None,
                    help="config YAML for custom audio thresholds (optional)")

    c = sub.add_parser("caption", help="burn a caption track on a video")
    c.add_argument("base")
    c.add_argument("out")
    c.add_argument("--align", required=True, help="JSON [[word,start,end],...]")
    c.add_argument("--style", default=caps.DEFAULT)
    c.add_argument("--format", default="9x16", choices=list(caps.FORMATS))

    a = p.parse_args()
    if a.cmd in ("doctor", "setup"):
        sys.exit(doctor.run(config_path=a.config))
    if a.cmd == "version":
        print(f"video-ads-machine {__version__}")
        return
    if a.cmd == "build":
        return cmd_build(a)
    if a.cmd == "clean-audio":
        return cmd_clean_audio(a)
    if a.cmd == "caption":
        return cmd_caption(a)
    p.print_help()


if __name__ == "__main__":
    main()
