#!/usr/bin/env python3
"""Editorial word-by-word captions: style presets, timing engine and burn.

Two independent halves live here:

APPEARANCE (STYLES + build_ass): each preset describes font, color, box,
halo, position and animation. Adding a new style = adding one STYLES
entry, never rewriting code. ASS colors are &H00BBGGRR
(alpha-blue-green-red); use hex_ass("#RRGGBB") to convert.

TIMING (align + layout + burn): word windows come from a word-level
alignment JSON of the avatar audio, matched against the VERBATIM script
words (the caption always shows what the script says, never the raw
transcription), then laid out sequentially so windows never overlap and
never freeze on a pause (HOLD_MAX). Lettering scenes from the montage
timing are blanked (the big serif text is already baked there).

Formats: "9x16" (1080x1920, the validated default) and "1x1"
(1080x1080 feed). IMPORTANT: for 1x1 the burn src must already be a
SQUARE composite; build it with make_square(), which applies the
validated blur-pad recipe (blurred cover background + the full 9:16
frame scaled to height 1080, centered). Captions scale down with the
frame (caption_scale) so they stay proportional to the 9x16 look.
"""
import difflib
import json
import os
import re
import unicodedata

from vam.ffutil import run_ffmpeg

# --- validated timing constants (reel-time, before final acceleration) ---
MIN_DUR = 0.22   # minimum on-screen duration per word (s)
MAX_LAG = 0.6    # if captions fall further behind speech, shrink to catch up
HOLD_MAX = 0.45  # max time a word stays after its spoken end: it must
                 # disappear in a pause, never freeze on screen (and never
                 # bleed over a lettering scene)

# Output formats. 9x16 = validated (do NOT touch). 1x1 = feed.
# caption_scale: the 1:1 uses a fill composite (the 9x16 video scaled to
# height 1080 = 56.25%), so captions scale along to stay proportional to
# the 9x16 look (otherwise they come out giant). 9x16 = 1.0.
FORMATS = {
    "9x16": {"w": 1080, "h": 1920, "caption_scale": 1.0},
    "1x1":  {"w": 1080, "h": 1080, "caption_scale": 0.5625},
}


def hex_ass(hexcolor, alpha=0):
    """#RRGGBB -> &HAABBGGRR (alpha 0 = opaque)."""
    h = hexcolor.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


# Each preset:
#   label   : friendly name (shown in style comparisons)
#   font    : font name (must exist in fonts/)
#   fsz     : font size
#   primary : text color (ASS) -> use hex_ass(...)
#   case    : 'lower' | 'upper' | 'keep'
#   y       : vertical position (PlayResY=1920); 1410 = over the chest
#   bold    : -1 (yes) / 0 (no)  -> ASS string
#   halo    : layers of diffuse dark glow [{'bord','blur','alpha'}]; [] = no halo
#   outline : {'colour': ASS, 'width': px} or None  (thin outline, BorderStyle 1)
#   box     : {'colour': ASS, 'pad': px} or None     (solid box behind, BorderStyle 3)
#   pop     : True/False  (scale-in animation on each word)
#   fade    : [in_ms, out_ms]
#
# NOTE: presets marked [PLACEHOLDER] are starting guesses to be calibrated
# against reference stills. 'tay' is the validated reference preset
# (one word at a time, white, dark halo).

STYLES = {
    # ---- VALIDATED (v8) ----
    "tay": {
        "label": "editorial word-by-word (validated v8)",
        "font": "Nunito", "fsz": 122, "primary": "&H00FFFFFF",
        "case": "lower", "y": 1410, "bold": "-1",
        "halo": [
            {"bord": 26, "blur": 20, "alpha": 0x40},
            {"bord": 14, "blur": 12, "alpha": 0x20},
        ],
        "outline": None, "box": None, "pop": True, "fade": [40, 0],
    },

    # ---- PLACEHOLDERS (calibrate against reference stills) ----
    "leon_box": {
        "label": "[PLACEHOLDER] orange box",
        "font": "Montserrat", "fsz": 104, "primary": "&H00FFFFFF",
        "case": "upper", "y": 1410, "bold": "-1",
        "halo": [], "outline": None,
        "box": {"colour": hex_ass("#FA4E04"), "pad": 18},
        "pop": True, "fade": [40, 0],
    },
    "bold_white": {
        "label": "[PLACEHOLDER] bold white with outline",
        "font": "Montserrat", "fsz": 112, "primary": "&H00FFFFFF",
        "case": "upper", "y": 1410, "bold": "-1",
        "halo": [], "outline": {"colour": "&H00000000", "width": 6},
        "box": None, "pop": True, "fade": [40, 0],
    },
    "amarela_pop": {
        "label": "[PLACEHOLDER] yellow pop",
        "font": "Montserrat", "fsz": 118, "primary": hex_ass("#FFD400"),
        "case": "upper", "y": 1410, "bold": "-1",
        "halo": [], "outline": {"colour": "&H00000000", "width": 8},
        "box": None, "pop": True, "fade": [40, 0],
    },

    # ---- Italic serif with glow (elegant editorial style) ----
    "serif_italic": {
        "label": "italic serif with glow",
        "font": "PlayfairDisplay", "fsz": 116, "primary": "&H00FFFFFF",
        "case": "keep", "y": 1410, "bold": "0", "italic": "-1",
        "halo": [
            {"bord": 22, "blur": 18, "alpha": 0x55},
            {"bord": 10, "blur": 10, "alpha": 0x30},
        ],
        "outline": None, "box": None, "pop": False, "fade": [120, 80],
    },
}

DEFAULT = "tay"


def _ts(x):
    return f"{int(x//3600)}:{int((x%3600)//60):02d}:{x%60:05.2f}"


def _apply_case(w, case):
    return {"lower": w.lower, "upper": w.upper, "keep": lambda: w}[case]()


def build_ass(words, style_name="tay", path="/tmp/cap_track.ass", fmt="9x16"):
    """Generate the .ass track for a preset. words = [(word, start, end)] in reel-time.
    fmt: "9x16" (validated) or "1x1" (feed; y derived proportionally)."""
    st = STYLES[style_name]
    font, bold = st["font"], st["bold"]
    F = FORMATS[fmt]
    W, Hh = F["w"], F["h"]
    xc = W // 2
    sc = F.get("caption_scale", 1.0)          # scales font+halo to stay proportional to the format
    fsz = round(st["fsz"] * sc)
    if fmt == "9x16":
        y = st["y"]
    else:
        # 1:1 uses a COMPOSITE with blurred fill (full 9x16 frame preserved,
        # centered), so the "chest" sits at the SAME proportional position
        # as in 9x16 -> proportional y. (If a crop ever replaces the fill,
        # override via a y_<fmt> key on the preset.)
        y = st.get("y_" + fmt, round(st["y"] * Hh / FORMATS["9x16"]["h"]))

    # BorderStyle: 3 when boxed, else 1 (outline). Outline/BackColour on the base Style.
    if st.get("box"):
        border_style, outline, back = 3, round(st["box"]["pad"] * sc), st["box"]["colour"]
        oc = st["box"]["colour"]
    elif st.get("outline"):
        border_style, outline, back = 1, round(st["outline"]["width"] * sc), "&H00000000"
        oc = st["outline"]["colour"]
    else:
        border_style, outline, back, oc = 1, 0, "&H00000000", "&H00000000"

    head = (
        f"[Script Info]\nScriptType: v4.00+\nPlayResX:{W}\nPlayResY:{Hh}\nWrapStyle:2\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,"
        "Bold,Italic,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV\n"
        f"Style: S, {font}, {fsz}, {st['primary']}, {oc}, {back}, "
        f"{bold},{st.get('italic','0')},{border_style},{outline},0,5,40,40,0\n"
        "\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,Effect,Text\n"
    )

    pop = r"\fscx88\fscy88\t(0,90,\fscx100\fscy100)" if st["pop"] else ""
    fin, fout = st["fade"]
    # 9x16 (validated): halo WITHOUT fade (invisible over dark clothing;
    # byte-identical to v8). Other formats: halo WITH the same fade as the
    # text, otherwise the dark halo shows up orphaned (a dark bar) over skin
    # during the fade. See the 1:1 bug notes.
    halo_fad = "" if fmt == "9x16" else f"\\fad({fin},{fout})"
    ev = []
    for w, s, e in words:
        txt = _apply_case(w, st["case"])
        # layers restart per word (words never coexist; halo always below the text)
        layer = 0
        # halo layers (diffuse dark glow), drawn underneath
        for h in st["halo"]:
            ev.append(
                f"Dialogue: {layer},{_ts(s)},{_ts(e)},S,,0,0,0,"
                f"{{\\an5\\pos({xc},{y}){halo_fad}\\1c&H000000&\\3c&H000000&"
                f"\\bord{round(h['bord']*sc)}\\blur{round(h['blur']*sc)}\\alpha&H{h['alpha']:02X}&}}{txt}"
            )
            layer += 1
        # main text
        ev.append(
            f"Dialogue: {layer},{_ts(s)},{_ts(e)},S,,0,0,0,"
            f"{{\\an5\\pos({xc},{y})\\fad({fin},{fout}){pop}}}{txt}"
        )
    open(path, "w").write(head + "\n".join(ev) + "\n")
    return path


# ====================================================================
# TIMING ENGINE (ported from the validated pipeline)
# ====================================================================

class CaptionError(Exception):
    """Raised when caption timing cannot be built safely."""


def _norm(w):
    """Accent/punctuation-insensitive form used to match transcript words
    against script words."""
    w = unicodedata.normalize("NFD", w.lower())
    return re.sub(r"[^\w]", "",
                  "".join(c for c in w if unicodedata.category(c) != "Mn"))


def _clean(w):
    """Display form: strip trailing commas/periods/semicolons (keep ? and !)."""
    w = w.strip()
    w = re.sub(r"[,\.;:]+$", "", w)
    return w.lower()


def _alignment_tokens(alignment_path):
    """Read a word-level alignment JSON and return merged word tuples
    [(start, end, text)], sorted by time.

    The file is the aligner's output for the avatar AUDIO (times in
    avatar-time, seconds). Any JSON shape works as long as it contains
    'tokens' lists of {start, end, text} somewhere; sub-word tokens are
    merged into words (a token starting with a space starts a new word).
    """
    with open(alignment_path, encoding="utf-8") as fh:
        data = json.load(fh)
    raw = []

    def grab(obj):
        if isinstance(obj, dict):
            if isinstance(obj.get("tokens"), list):
                for t in obj["tokens"]:
                    raw.append((float(t["start"]), float(t["end"]),
                                t.get("text", "")))
            for v in obj.values():
                grab(v)
        elif isinstance(obj, list):
            for v in obj:
                grab(v)

    grab(data)
    raw.sort()
    words = []
    for s, e, txt in raw:
        new_word = txt.startswith(" ") or not words
        chunk = txt.strip()
        if not chunk:
            continue
        if new_word:
            words.append([s, e, chunk])
        else:
            words[-1][1] = e
            words[-1][2] += chunk
    return words


def _script_words(roteiro):
    """Verbatim script words from a script path or pre-parsed block list.

    Captions always render THESE words (what the script says), never the
    aligner's transcription: the alignment only provides the timing.
    """
    if isinstance(roteiro, str):
        from vam.parser import parse  # lazy: only needed for path input
        blocks = parse(roteiro)
    else:
        blocks = roteiro
    words = []
    for b in blocks:
        words += str(b.get("narr", "")).split()
    return words


def raw_word_windows(alignment_path, roteiro, a0):
    """Match script words to alignment times; return [(word, s, e)] in
    reel-time (avatar-time minus a0). Unmatched words are interpolated
    between their matched neighbors."""
    tokens = _alignment_tokens(alignment_path)
    narr = _script_words(roteiro)
    tok_norm = [_norm(c) for *_, c in tokens]
    scr_norm = [_norm(w) for w in narr]
    sm = difflib.SequenceMatcher(None, tok_norm, scr_norm, autojunk=False)
    times = [None] * len(narr)
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            times[b + k] = (tokens[a + k][0], tokens[a + k][1])
    last = None
    for i in range(len(times)):
        if times[i] is None:
            nxt = next((times[j] for j in range(i + 1, len(times))
                        if times[j]), None)
            if last and nxt and nxt[0] > last[1]:
                times[i] = (last[1], nxt[0])
            elif last:
                times[i] = (last[1], last[1] + 0.18)
            elif nxt:
                times[i] = (max(0, nxt[0] - 0.18), nxt[0])
            else:
                times[i] = (i * 0.3, i * 0.3 + 0.3)
        last = times[i]
    raws = [(_clean(w), times[i][0] - a0, times[i][1] - a0)
            for i, w in enumerate(narr)]
    return [(w, s, e) for (w, s, e) in raws if w]


def blank_letterings(raws, letterings, a0):
    """Drop words that fall inside lettering scenes (their text is baked
    on screen as big serif type; word captions there would double up).

    `letterings` come from the montage timing dict: [{'s':..,'e':..}, ...]
    in avatar-time; they are converted to reel-time with a0.

    Special case, OPENING scene (range starting at reel ~0): the first
    spoken words can carry NEGATIVE reel-time (aligned before a0), so
    everything up to the end of that range is blanked. Mid-video scenes
    use a tight margin so neighbor-scene words are not swallowed.
    """
    if not letterings:
        return raws
    ranges = [(let["s"] - a0, let["e"] - a0) for let in letterings]

    def _in_lettering(s):
        for ls, le in ranges:
            if ls <= 0.10:
                if s <= le + 0.05:
                    return True
            elif ls - 0.05 <= s <= le + 0.05:
                return True
        return False

    return [(w, s, e) for (w, s, e) in raws if not _in_lettering(s)]


def sequential_layout(raws, min_dur=MIN_DUR, max_lag=MAX_LAG,
                      hold_max=HOLD_MAX):
    """Lay word windows out sequentially, guaranteeing zero overlap.

    Why: naive "fill until the next word" breaks when the aligner emits
    non-monotonic times (two words render at once, e.g. "p20r"). Here
    each start is clamped to the previous end (cursor), every word gets
    at least `min_dur` on screen, and the end is capped at
    `hold_max` after the spoken end so captions vanish during pauses
    instead of freezing (and never bleed into a lettering scene). If the
    captions drift more than `max_lag` behind speech, the minimum
    duration shrinks to catch back up.
    """
    out = []
    cursor = 0.0
    for idx, (w, s_raw, e_raw) in enumerate(raws):
        s = max(s_raw, cursor)
        nxt_raw = raws[idx + 1][1] if idx + 1 < len(raws) \
            else max(e_raw, s + min_dur)
        mind = min_dur
        if s - s_raw > max_lag:
            mind = 0.14  # running late: shrink to recover sync
        e = max(s + mind, min(nxt_raw, e_raw + hold_max))
        out.append((w, round(s, 3), round(e, 3)))
        cursor = e
    # hard validation: zero overlap, positive durations
    for cur, nxt in zip(out, out[1:]):
        if cur[2] > nxt[1] + 1e-6:
            raise CaptionError(f"caption windows overlap: {cur} x {nxt}")
    for item in out:
        if item[2] <= item[1]:
            raise CaptionError(f"non-positive caption duration: {item}")
    return out


def word_windows(alignment_path, roteiro, timing):
    """Full timing pipeline: align -> blank letterings -> sequential layout.

    `timing` is the montage timing dict ({'a0','total','letterings',...}).
    Returns [(word, start, end)] in reel-time, ready for build_ass().
    """
    a0 = timing["a0"]
    raws = raw_word_windows(alignment_path, roteiro, a0)
    raws = blank_letterings(raws, timing.get("letterings", []), a0)
    return sequential_layout(raws)


# ====================================================================
# OUTPUT: 1x1 composite helper + burn
# ====================================================================

def make_square(src, dst):
    """Build the 1080x1080 composite from a 9:16 master (validated recipe).

    The full 9:16 frame is preserved (scaled to height 1080, centered)
    over a blurred cover-fill of itself: no crop, no black bars. Burn the
    1x1 captions on THIS output; burn(fmt='1x1') assumes a square src.
    """
    run_ffmpeg([
        "ffmpeg", "-y", "-i", src, "-filter_complex",
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1080:force_original_aspect_ratio=increase,"
        "crop=1080:1080,boxblur=24:1,setsar=1[b];"
        "[fg]scale=-1:1080,setsar=1[f];"
        "[b][f]overlay=(W-w)/2:0,fps=30[v]",
        "-map", "[v]", "-map", "0:a", "-c:v", "libx264",
        "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", dst,
    ], label="make_square 1x1 composite")


def burn(src, dst, roteiro, fmt, cfg, timing, style=DEFAULT,
         alignment_path=None):
    """Burn word-by-word captions onto `src`, writing `dst`.

    Args:
        src: video to subtitle. For fmt='9x16' this is the 9:16 master;
            for fmt='1x1' it MUST already be the square composite
            produced by make_square() (captions do not squarify).
        dst: output mp4 path.
        roteiro: script path (parsed via vam.parser) or a pre-parsed
            list of block dicts. Captions show these words verbatim.
        fmt: '9x16' or '1x1'.
        cfg: Config (uses cfg.workdir for the .ass file and
            cfg.fonts_dir so the bundled fonts resolve in ffmpeg).
        timing: montage timing dict ({'a0','total','letterings',...});
            lettering ranges are blanked from the captions.
        style: STYLES preset name (default: the validated editorial one).
        alignment_path: word-level alignment JSON of the avatar audio;
            defaults to <cfg.workdir>/alignment.json.
    """
    if fmt not in FORMATS:
        raise ValueError(
            f"Unknown caption format '{fmt}'. "
            f"Valid formats: {', '.join(sorted(FORMATS))}.")
    if style not in STYLES:
        raise ValueError(
            f"Unknown caption style '{style}'. "
            f"Valid styles: {', '.join(sorted(STYLES))}.")
    if alignment_path is None:
        alignment_path = os.path.join(cfg.workdir, "alignment.json")

    words = word_windows(alignment_path, roteiro, timing)
    os.makedirs(cfg.workdir, exist_ok=True)
    ass = build_ass(words, style,
                    path=os.path.join(cfg.workdir, f"captions_{fmt}.ass"),
                    fmt=fmt)
    run_ffmpeg([
        "ffmpeg", "-y", "-i", src,
        "-vf", f"subtitles={ass}:fontsdir={cfg.fonts_dir}",
        "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "copy", "-movflags", "+faststart", dst,
    ], label=f"burn captions {fmt}")
