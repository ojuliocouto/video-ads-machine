#!/usr/bin/env python3
"""CLI do Video Ads Machine.

Comandos:
  vam doctor / vam setup       preflight: checa e guia instalacao de deps/MCPs/plugins
  vam caption <base> <out>     queima legenda num video (engine validado)
  vam version
  vam build <roteiro>          (roadmap) pipeline completo roteiro->video
"""
import argparse
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
        print("erro ffmpeg:\n", r.stderr[-1200:]); sys.exit(1)


def cmd_caption(a):
    # align: JSON com [[palavra, start, end], ...] (reel-time, em segundos)
    words = [tuple(w) for w in json.load(open(a.align))]
    if a.style not in caps.STYLES:
        print(f"estilo '{a.style}' nao existe: {', '.join(caps.STYLES)}"); sys.exit(1)
    ass = caps.build_ass(words, a.style, "/tmp/vam_cap.ass", fmt=a.format)
    _burn(a.base, a.out, ass)
    print("OK", a.out, f"(estilo={a.style} formato={a.format} palavras={len(words)})")


def main():
    p = argparse.ArgumentParser(prog="vam", description="Video Ads Machine")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("doctor", help="preflight: checa e guia instalacao")
    sub.add_parser("setup", help="alias de doctor")
    sub.add_parser("version", help="versao")

    c = sub.add_parser("caption", help="queima legenda num video")
    c.add_argument("base"); c.add_argument("out")
    c.add_argument("--align", required=True, help="JSON [[palavra,start,end],...]")
    c.add_argument("--style", default=caps.DEFAULT)
    c.add_argument("--format", default="9x16", choices=list(caps.FORMATS))

    b = sub.add_parser("build", help="(roadmap) pipeline completo")
    b.add_argument("roteiro", nargs="?")

    a = p.parse_args()
    if a.cmd in ("doctor", "setup"):
        sys.exit(doctor.run())
    if a.cmd == "version":
        print(f"video-ads-machine {__version__}"); return
    if a.cmd == "caption":
        return cmd_caption(a)
    if a.cmd == "build":
        print("build (pipeline completo roteiro->video) esta no roadmap. Veja README/ROADMAP.")
        print("Por enquanto: rode `vam doctor` e use `vam caption`. Modulos avatar/align/compose em construcao.")
        return
    p.print_help()


if __name__ == "__main__":
    main()
