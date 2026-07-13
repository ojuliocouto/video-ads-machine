"""Scene assembly: avatar reframe + inserts + serif lettering + logo + PiP.

This is the heart of the pipeline, ported from the production-validated
engine. It takes the annotated script, the avatar video and a user map of
insert clips, and renders the 9:16 base video (captions are burned later
by `vam.captions`, so lettering scene ranges are recorded in the timing
dict for the caption pass to blank).

Flow (assemble):
  1. parse the script into scene blocks (vam.parser)
  2. transcribe the avatar audio to word timestamps and align the script
     narration to it (each scene boundary lands on a real word end)
  3. render each scene:
       orig            full-screen presenter, reframe + slow zoom-in
       insert          b-roll full screen, fit over a blurred fill
       lettering(_logo) presenter + giant serif lettering (foil default)
       logo            brand card: dark bg + radial glow + logo scale-in
  4. chain scenes with short dissolves (xfade 0.18s)
  5. reattach the CONTINUOUS avatar audio (zero lip-sync drift) and add a
     subtle film treatment (grain + contrast + vignette)
  6. write timing.json into cfg.workdir — one timing per build, never a
     shared global path (this removes the original engine's race condition
     between concurrent builds by design)

Word alignment backend: `faster-whisper` (pip install faster-whisper), the
portable default. Performance note: the first run downloads the model
(~500 MB for "small"); on CPU with int8 it transcribes roughly at real
time, and much faster with a GPU. Pick another size via the
VAM_WHISPER_MODEL env var ("base" is faster, "medium" more accurate).

Circular PiP: the presenter floats in a small circle over the b-roll
inserts. Mask, ring and shadow are generated programmatically (Pillow),
tinted with the brand key color — no binary assets shipped. Apply it with
`overlay_pip` AFTER captions are burned, so caption zoom effects never
drag the circle around.
"""
import difflib
import json
import os
import re
import subprocess
import unicodedata

from .ffutil import run_ffmpeg
from .parser import parse

# ---------------------------------------------------------------- constants
W, H, FPS = 1080, 1920, 30

# Reframe: upscale then crop pulls the face UP in the 9:16 frame, leaving
# the lower third free for captions (validated numbers, do not eyeball).
REFRAME = "scale=2376:4224:force_original_aspect_ratio=increase,crop=2160:3840:108:652"

XF = 0.18          # dissolve duration between scenes (short = precise cuts)
DARK = "0x141210"  # near-black warm background of the logo card

# Circular PiP geometry: 300px avatar circle, 420px frame (ring + shadow),
# top-center — away from the platform UI at the very top.
PIP = 300
PIPX = (W - PIP) // 2   # 390
PIPY = 150
PIPF = (420 - PIP) // 2  # 60

# Validated pop-in animations (scale overshoot then settle).
POP_L = r"\fscx74\fscy74\t(0,150,\fscx104\fscy104)\t(150,260,\fscx100\fscy100)"
POP_K = r"\fscx44\fscy44\t(0,160,\fscx114\fscy114)\t(160,300,\fscx100\fscy100)"

# Phonetic spellings writers use to steer the voice actor; cleaned before
# any text reaches the screen.
DISPLAY_FIXES = [
    ("Cláude", "Claude"), ("Côde", "Code"),
    ("IÁ", "IA"), ("IÃ", "IA"), ("I.A", "IA"), ("I.Á", "IA"),
]


# ------------------------------------------------------------- small utils
def _ts(x):
    return f"{int(x // 3600)}:{int((x % 3600) // 60):02d}:{x % 60:05.2f}"


def _norm(w):
    """Accent/punctuation-insensitive lowercase form used for word matching."""
    w = unicodedata.normalize("NFD", w.lower())
    return re.sub(r"[^\w]", "", "".join(c for c in w if unicodedata.category(c) != "Mn"))


def clean_display(text):
    """Clean script text for on-screen display (phonetic guides, ellipses)."""
    for a, b in DISPLAY_FIXES:
        text = text.replace(a, b)
    text = text.replace("…", "").replace("..", "")
    return re.sub(r"\s{2,}", " ", text).strip()


def nframes(d):
    return max(1, round(d * FPS))


def _cap(n):
    """Trim a scene to exactly n frames (frame-accurate scene lengths)."""
    return f"trim=end_frame={n},setpts=N/{FPS}/TB"


def _video_duration_frames(path):
    """Real video duration by counting frames (ignores audio padding)."""
    r = run_ffmpeg(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-count_frames",
         "-show_entries", "stream=nb_read_frames", "-of", "default=nw=1:nk=1", path],
        label="count frames")
    return int(r.stdout.strip()) / FPS


def _sub(ass, fonts_dir):
    return f",subtitles={ass}:fontsdir={fonts_dir}" if ass else ""


# ----------------------------------------------------- brand color derivation
def _bgr_to_rgb(bgr_hex):
    return (int(bgr_hex[4:6], 16), int(bgr_hex[2:4], 16), int(bgr_hex[0:2], 16))


def _rgb_to_bgr(rgb):
    r, g, b = (max(0, min(255, round(c))) for c in rgb)
    return f"{b:02X}{g:02X}{r:02X}"


def _tint(rgb, t):
    """Blend toward white by factor t (0..1)."""
    return tuple(c + (255 - c) * t for c in rgb)


def _shade(rgb, t):
    """Blend toward black by factor t (0..1)."""
    return tuple(c * (1 - t) for c in rgb)


# Foil ramp formula (derives the validated hand-tuned warm ramp from any
# brand color): five horizontal bands from crest to bronze —
#   band 1: tint 55%  (crest, near-white highlight)
#   band 2: tint 30%
#   band 3: the key color itself, untouched
#   band 4: shade 18%
#   band 5: shade 35%  (bronze base)
# Rim light = tint 85% (almost-white sheen); glow outline = shade 50%.
_FOIL_STEPS = (("t", 0.55), ("t", 0.30), (None, 0.0), ("s", 0.18), ("s", 0.35))


def derive_foil_bands(key_color_bgr):
    """Five BGR hex colors for the foil gradient, crest -> bronze."""
    rgb = _bgr_to_rgb(key_color_bgr)
    out = []
    for op, t in _FOIL_STEPS:
        if op == "t":
            out.append(_rgb_to_bgr(_tint(rgb, t)))
        elif op == "s":
            out.append(_rgb_to_bgr(_shade(rgb, t)))
        else:
            out.append(key_color_bgr.upper())
    return out


def rim_color(key_color_bgr):
    """Near-white sheen on the crest of the foil (tint 85%)."""
    return _rgb_to_bgr(_tint(_bgr_to_rgb(key_color_bgr), 0.85))


def glow_outline_color(key_color_bgr):
    """Dark halo behind the key word (shade 50%)."""
    return _rgb_to_bgr(_shade(_bgr_to_rgb(key_color_bgr), 0.50))


# ------------------------------------------------------------ serif lettering
def fit_key_size(key, fonts_dir, base=176, maxw=960):
    """Largest DM Serif size (from `base` down) whose width fits `maxw` px."""
    font_path = os.path.join(fonts_dir, "DMSerifDisplay.ttf")
    try:
        from PIL import ImageFont
        for sz in range(base, 84, -6):
            f = ImageFont.truetype(font_path, sz)
            if f.getbbox(key)[2] <= maxw:
                return sz
        return 96
    except Exception:
        return base if len(key) <= 7 else 120


def build_lettering_ass(lead, key, dur, cfg, withlogo=False):
    """Build the serif lettering ASS (string) for one scene.

    Layout (validated): small Playfair italic LEAD line above + giant
    DM Serif KEY word in the brand color, lower third (clear of the face),
    with a pop-in. Two styles:

    'foil' (default): metallic gradient in 5 horizontal \\clip bands
    (colors derived from cfg.brand.key_color_bgr, see derive_foil_bands) +
    a near-white rim light on the crest + a subtle glow halo behind; the
    crisp base layer stays untouched underneath. The foil fades in at
    0.42s, AFTER the pop settles.

    'solid': just the crisp pop-in key word, no gradient layers.
    """
    lead = clean_display(lead or "").strip()
    key = clean_display(key or "").strip().upper()
    if not key:
        return None
    key_color = cfg.brand.key_color_bgr
    ksz = fit_key_size(key, cfg.fonts_dir)
    y_key = cfg.lettering.y_key_with_logo if withlogo else cfg.lettering.y_key
    y_lead = y_key - int(ksz * 0.58) - 40

    head = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n"
        "WrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, "
        "OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV\n"
        "Style: P, Playfair Display, 90, &H00FFFFFF, &H00202020, &H90000000, "
        "0, 1, 1, 2.4, 3, 5, 60, 60, 0\n"
        f"Style: D, DM Serif Display, {ksz}, &H00{key_color}, &H00101010, "
        "&H90000000, 0, 0, 1, 3.2, 4, 5, 40, 40, 0\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "Effect, Text\n")

    ev = []
    if lead:
        ev.append(
            f"Dialogue: 0,{_ts(0.0)},{_ts(dur)},P,,0,0,0,"
            f"{{\\an5\\move(540,{y_lead + 24},540,{y_lead},0,220)\\fad(110,0){POP_L}}}{lead}")

    if cfg.lettering.style == "foil":
        # Foil geometry (validated, do not retune): the gradient window
        # covers from 0.44*ksz above the baseline to 0.32*ksz below it,
        # split into 5 equal bands; the rim light is the top 16% of it.
        gs = 0.42  # foil fades in after the pop settles (0.12 + 0.30)
        gtop = round(y_key - 0.44 * ksz)
        gbot = round(y_key + 0.32 * ksz)
        span = gbot - gtop
        yb = [gtop + round(i * span / 5) for i in range(6)]
        rim_top, rim_bot = gtop, gtop + round(0.16 * span)
        # glow halo behind everything (soft, mostly transparent)
        ev.append(
            f"Dialogue: 3,{_ts(gs)},{_ts(dur)},D,,0,0,0,"
            f"{{\\an5\\pos(540,{y_key})\\bord5\\blur9\\shad0"
            f"\\1c&H{key_color}&\\3c&H{glow_outline_color(key_color)}&"
            f"\\1a&H86&\\3a&H4A&\\4a&HFF&\\fad(200,0)}}{key}")
        # crisp base with the pop-in (stays fully opaque under the foil)
        ev.append(
            f"Dialogue: 4,{_ts(0.12)},{_ts(dur)},D,,0,0,0,"
            f"{{\\an5\\move(540,{y_key + 38},540,{y_key},0,250)\\fad(130,0){POP_K}}}{key}")
        # 5 gradient bands, each clipped to its horizontal slice
        for i, c in enumerate(derive_foil_bands(key_color)):
            ev.append(
                f"Dialogue: 5,{_ts(gs)},{_ts(dur)},D,,0,0,0,"
                f"{{\\an5\\pos(540,{y_key})\\bord0\\shad0\\1c&H{c}&"
                f"\\fad(150,0)\\clip(30,{yb[i]},1050,{yb[i + 1]})}}{key}")
        # rim light on the crest
        ev.append(
            f"Dialogue: 6,{_ts(gs)},{_ts(dur)},D,,0,0,0,"
            f"{{\\an5\\pos(540,{y_key})\\bord0\\shad0\\blur0.6"
            f"\\1c&H{rim_color(key_color)}&\\fad(150,0)"
            f"\\clip(30,{rim_top},1050,{rim_bot})}}{key}")
    else:  # 'solid'
        ev.append(
            f"Dialogue: 0,{_ts(0.12)},{_ts(dur)},D,,0,0,0,"
            f"{{\\an5\\move(540,{y_key + 38},540,{y_key},0,250)\\fad(130,0){POP_K}}}{key}")

    return head + "\n".join(ev) + "\n"


def _write_lettering_ass(lead, key, dur, cfg, withlogo, tmp):
    content = build_lettering_ass(lead, key, dur, cfg, withlogo)
    if content is None:
        return None
    path = os.path.join(tmp, f"serif_{abs(hash(lead + key)) % 99999}.ass")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


# ------------------------------------------------------------ word alignment
def _parse_parakeet_json(data):
    """Merge parakeet-mlx subword tokens into words [(start, end, word)].

    parakeet-mlx emits tokens where a leading space marks a new word;
    other tokens are subword continuations that extend the current word.
    """
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
        clean = txt.strip()
        if not clean:
            continue
        if new_word:
            words.append([s, e, clean])
        else:
            words[-1][1] = e
            words[-1][2] += clean
    return [(s, e, w) for s, e, w in words]


def _transcribe_parakeet(audio_path):
    """Word timestamps via the parakeet-mlx CLI (Apple Silicon, fast)."""
    import glob as _glob
    import shutil
    import tempfile
    binary = shutil.which("parakeet-mlx") or os.path.expanduser(
        "~/.local/bin/parakeet-mlx")
    tmp = tempfile.mkdtemp(prefix="vam_pk_")
    subprocess.run([binary, audio_path, "--output-format", "json",
                    "--output-dir", tmp], check=True, capture_output=True)
    out = _glob.glob(os.path.join(tmp, "*.json"))
    if not out:
        raise RuntimeError("parakeet-mlx produced no JSON output")
    with open(out[0], encoding="utf-8") as fh:
        return _parse_parakeet_json(json.load(fh))


def transcribe_words(audio_path, cfg=None):
    """Word-level timestamps [(start, end, word)].

    Backend selection (env VAM_TRANSCRIBE_BACKEND = auto|parakeet|whisper,
    default auto): "auto" uses parakeet-mlx when its CLI is on PATH (fast,
    Apple Silicon), otherwise falls back to faster-whisper (portable pip
    install; the first run downloads the model). Set VAM_WHISPER_MODEL to
    trade speed for accuracy ("base" / "small" / "medium").
    """
    import shutil
    backend = os.environ.get("VAM_TRANSCRIBE_BACKEND", "auto").lower()
    has_parakeet = bool(shutil.which("parakeet-mlx")) or os.path.exists(
        os.path.expanduser("~/.local/bin/parakeet-mlx"))
    if backend == "parakeet" or (backend == "auto" and has_parakeet):
        return _transcribe_parakeet(audio_path)
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError(
            "faster-whisper is not installed. It is the transcription "
            "backend used to align the script to the avatar audio.\n"
            "Install it with: pip install faster-whisper\n"
            "(On Apple Silicon you can instead install parakeet-mlx, "
            "which is much faster.)")
    model_size = os.environ.get("VAM_WHISPER_MODEL", "small")
    language = getattr(cfg, "language", "pt") if cfg else "pt"
    model = WhisperModel(model_size, compute_type="int8")
    segments, _info = model.transcribe(
        audio_path, language=language, word_timestamps=True)
    words = []
    for seg in segments:
        for w in seg.words or []:
            txt = w.word.strip()
            if txt:
                words.append((float(w.start), float(w.end), txt))
    return words


def align_words(recognized, narr_words):
    """Align script words to recognized word timestamps.

    PRECISE alignment (validated): match script word <-> recognized word
    with difflib on normalized forms (not by proportion), so every scene
    boundary (= end of the last word of a block) lands on a REAL word end
    and cuts/dissolves never chop the presenter mid-word. Unmatched words
    (script vs voice variations) are interpolated between matched
    neighbors.

    Args:
        recognized: [(start, end, text)] word-level transcription.
        narr_words: list of script words, in order.

    Returns: [(start, end, word)] one entry per script word.
    """
    rec_norm = [_norm(t) for _s, _e, t in recognized]
    scr_norm = [_norm(w) for w in narr_words]
    sm = difflib.SequenceMatcher(None, rec_norm, scr_norm, autojunk=False)
    times = [None] * len(narr_words)
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            times[b + k] = (recognized[a + k][0], recognized[a + k][1])
    last = None
    for i in range(len(times)):
        if times[i] is None:
            nxt = next((times[j] for j in range(i + 1, len(times)) if times[j]), None)
            if last and nxt and nxt[0] > last[1]:
                times[i] = (last[1], nxt[0])
            elif last:
                times[i] = (last[1], last[1] + 0.18)
            elif nxt:
                times[i] = (max(0.0, nxt[0] - 0.18), nxt[0])
            else:
                times[i] = (i * 0.3, i * 0.3 + 0.3)
        last = times[i]
    return [(times[i][0], times[i][1], narr_words[i]) for i in range(len(narr_words))]


def write_alignment(words, cfg):
    """Persist recognized words as <workdir>/alignment.json.

    Format: {"tokens": [{start, end, text}]} in avatar-time, the shape
    vam.captions reads. Each text gets a leading space so the sub-word
    merge in captions keeps one token per word.
    """
    os.makedirs(cfg.workdir, exist_ok=True)
    path = os.path.join(cfg.workdir, "alignment.json")
    payload = {"tokens": [{"start": s, "end": e, "text": " " + w}
                          for s, e, w in words]}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    return path


def align(avatar, narr_words, cfg, tmp):
    """Extract the avatar audio, transcribe it and align the script to it.

    Also persists the raw recognized words as <workdir>/alignment.json,
    which vam.captions consumes to time the captions word by word.
    """
    wav = os.path.join(tmp, "avatar_16k.wav")
    run_ffmpeg(["ffmpeg", "-y", "-i", avatar, "-vn", "-ac", "1", "-ar", "16000", wav],
               label="extract avatar audio")
    recognized = transcribe_words(wav, cfg)
    write_alignment(recognized, cfg)
    return align_words(recognized, narr_words)


# ------------------------------------------------------------------- inserts
def find_insert(instr, inserts_map):
    """Pick the insert clip whose keyword appears in the instruction.

    Falls back to the FIRST clip of the map when nothing matches (validated
    behavior — a script typo never crashes a long render; check the printed
    scene plan if an insert looks wrong).
    """
    if not inserts_map:
        raise ValueError(
            "This script has insert scenes but no inserts were provided. "
            "Pass a map like {'product screen': {'file': 'clips/screen.mp4', "
            "'start': 0, 'speed': 1.0}}.")
    s = instr.lower()
    for k, v in inserts_map.items():
        if k.lower() in s:
            return v
    return next(iter(inserts_map.values()))


# ------------------------------------------------------------- filter graphs
def orig_filter(n_frames, ass=None, fonts_dir=None, max_zoom=1.07):
    """Full-screen presenter: reframe + very slow zoom-in (validated)."""
    return (f"fps={FPS},{REFRAME},"
            f"zoompan=z='min(zoom+0.0003,{max_zoom})':d=1:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H},setsar=1,"
            f"{_cap(n_frames)}{_sub(ass, fonts_dir)}")


def insert_filter(speed, n_frames, ass=None, fonts_dir=None):
    """B-roll FULL SCREEN: fit over a blurred fill of itself (no crop)."""
    return (f"[0:v]setpts=PTS/{speed},split=2[i1][i2];"
            f"[i1]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},boxblur=24:1,setsar=1[bg];"
            f"[i2]scale={W}:{H}:force_original_aspect_ratio=decrease,setsar=1[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={FPS},"
            f"{_cap(n_frames)}{_sub(ass, fonts_dir)}[v]")


def logo_filter(dur, n_frames):
    """Brand logo reveal: dark bg + radial glow fade-in + logo scale-in.

    Inputs: [0:v] logo PNG (looped), [1:v] generated glow PNG (looped).
    The logo sits in the upper third so captions stay clear below it.
    """
    fade_d = min(0.5, max(0.25, dur * 0.4))
    sc_d = min(0.7, max(0.35, dur * 0.55))
    return (
        f"color={DARK}:s={W}x{H}:r={FPS}[bg0];"
        f"[1:v]format=rgba,fade=t=in:st=0:d={fade_d}:alpha=1[gl];"
        f"[bg0][gl]overlay=0:0:format=auto[bg1];"
        f"[0:v]fps={FPS},setpts=PTS-STARTPTS,format=yuva420p,scale=940:-1,"
        f"scale=w='trunc(iw*(0.84+0.16*min(t/{sc_d},1))/2)*2':"
        f"h='trunc(ih*(0.84+0.16*min(t/{sc_d},1))/2)*2':eval=frame,"
        f"fade=t=in:st=0:d={fade_d}:alpha=1[lg];"
        f"[bg1][lg]overlay=x='(W-w)/2':y='(H-h)/2-300':eval=frame,{_cap(n_frames)}[v]")


def pip_enable_expr(windows):
    """ffmpeg enable expression: union of (start, end) reel-time windows."""
    return "+".join(f"between(t,{rs},{re})" for rs, re in windows)


def pip_filter(windows):
    """Circular presenter PiP over the b-roll windows.

    Inputs: [0:v] base video, [1:v] avatar (already trimmed to a0 so
    avatar-time == reel-time), [2:v] circle mask, [3:v] ring, [4:v] shadow.
    """
    en = pip_enable_expr(windows)
    return (
        f"[1:v]scale={PIP}:{PIP}:force_original_aspect_ratio=increase,"
        f"crop={PIP}:{PIP},setsar=1[sq];"
        f"[sq][2:v]alphamerge[pip];"
        f"[0:v][4:v]overlay={PIPX - PIPF}:{PIPY - PIPF + 14}:enable='{en}'[sh];"
        f"[sh][pip]overlay={PIPX}:{PIPY}:enable='{en}'[wp];"
        f"[wp][3:v]overlay={PIPX - PIPF}:{PIPY - PIPF}:enable='{en}'[v]")


# --------------------------------------------------- generated visual assets
def _make_circle_assets(tmp, key_color_bgr):
    """Generate the PiP mask/ring/shadow PNGs (Pillow, brand-tinted ring)."""
    from PIL import Image, ImageDraw, ImageFilter
    ss = 4  # supersampling for smooth edges

    mask = Image.new("L", (PIP * ss, PIP * ss), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, PIP * ss - 1, PIP * ss - 1), fill=255)
    mask_p = os.path.join(tmp, "circle_mask.png")
    mask.resize((PIP, PIP), Image.LANCZOS).save(mask_p)

    frame = PIP + 2 * PIPF  # 420
    ring = Image.new("RGBA", (frame * ss, frame * ss), (0, 0, 0, 0))
    rgb = _bgr_to_rgb(key_color_bgr)
    pad = (PIPF - 6) * ss
    ImageDraw.Draw(ring).ellipse(
        (pad, pad, frame * ss - pad - 1, frame * ss - pad - 1),
        outline=tuple(int(c) for c in rgb) + (255,), width=8 * ss)
    ring_p = os.path.join(tmp, "circle_ring.png")
    ring.resize((frame, frame), Image.LANCZOS).save(ring_p)

    shadow = Image.new("RGBA", (frame, frame), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse((30, 30, frame - 31, frame - 31), fill=(0, 0, 0, 130))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    shadow_p = os.path.join(tmp, "circle_shadow.png")
    shadow.save(shadow_p)
    return mask_p, ring_p, shadow_p


def _make_glow_asset(tmp, key_color_bgr):
    """Full-frame radial glow tinted with the brand color (for logo cards)."""
    from PIL import Image, ImageDraw, ImageFilter
    small = Image.new("RGBA", (W // 4, H // 4), (0, 0, 0, 0))
    rgb = tuple(int(c) for c in _tint(_bgr_to_rgb(key_color_bgr), 0.15))
    d = ImageDraw.Draw(small)
    cx, cy = W // 8, H // 8 - 75  # matches the logo center (H/2 - 300)
    for radius, alpha in ((190, 26), (140, 34), (95, 44), (55, 56)):
        d.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                  fill=rgb + (alpha,))
    small = small.filter(ImageFilter.GaussianBlur(28))
    path = os.path.join(tmp, "logo_glow.png")
    small.resize((W, H), Image.LANCZOS).save(path)
    return path


# ------------------------------------------------------------ scene renders
def _r_orig(avatar, s, e, out, fonts_dir):
    d = e - s
    vf = orig_filter(nframes(d))
    run_ffmpeg(["ffmpeg", "-y", "-ss", str(s), "-t", str(d + 0.4), "-i", avatar,
                "-vf", vf, "-r", str(FPS), "-an",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", out],
               label="presenter scene")


def _r_insert(ins, s, e, out):
    d = e - s
    speed = ins.get("speed", 1.0)
    start = ins.get("start", 0)
    take = d * speed
    fc = insert_filter(speed, nframes(d))
    run_ffmpeg(["ffmpeg", "-y", "-ss", str(start), "-t", str(take + 0.4),
                "-i", ins["file"], "-filter_complex", fc, "-r", str(FPS),
                "-map", "[v]", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", out],
               label="insert scene")


def _r_logo(s, e, out, cfg, tmp):
    if not cfg.brand.logo_path:
        raise ValueError(
            "The script has a logo scene but 'brand.logo_path' is not set in "
            "the config. Point it to a transparent-background PNG of your logo.")
    d = e - s
    glow = _make_glow_asset(tmp, cfg.brand.key_color_bgr)
    fc = logo_filter(d, nframes(d))
    run_ffmpeg(["ffmpeg", "-y",
                "-loop", "1", "-t", str(d + 0.4), "-i", cfg.brand.logo_path,
                "-loop", "1", "-t", str(d + 0.4), "-i", glow,
                "-filter_complex", fc, "-map", "[v]", "-r", str(FPS), "-an",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", out],
               label="logo scene")


def _r_lettering(avatar, lead, key, s, e, out, cfg, tmp, withlogo=False):
    """Presenter kept bright and sharp (no darkening/blur) + baked serif
    lettering; the scene range is recorded so the caption pass blanks it."""
    d = e - s
    ass = _write_lettering_ass(lead, key, d, cfg, withlogo, tmp)
    zp = orig_filter(nframes(d), max_zoom=1.06)
    inputs = ["-ss", str(s), "-t", str(d + 0.4), "-i", avatar]
    if withlogo:
        if not cfg.brand.logo_path:
            raise ValueError(
                "The script has a lettering+logo scene but 'brand.logo_path' "
                "is not set in the config.")
        inputs += ["-i", cfg.brand.logo_path]
        fc = (f"[0:v]{zp}[bg];[1:v]scale=430:-1[lg];"
              f"[bg][lg]overlay=(W-w)/2:H-h-46{_sub(ass, cfg.fonts_dir)}[v]")
    else:
        fc = f"[0:v]{zp}{_sub(ass, cfg.fonts_dir)}[v]"
    run_ffmpeg(["ffmpeg", "-y", *inputs, "-filter_complex", fc, "-map", "[v]",
                "-an", "-r", str(FPS), "-c:v", "libx264", "-pix_fmt", "yuv420p", out],
               label="lettering scene")


# ------------------------------------------------------------------- timing
def write_timing(timing, cfg):
    """Persist the timing dict inside cfg.workdir (one per build).

    Never a shared global path: concurrent builds each own their timing,
    which removes the original engine's race condition by design.
    """
    os.makedirs(cfg.workdir, exist_ok=True)
    path = os.path.join(cfg.workdir, "timing.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(timing, fh)
    return path


# ----------------------------------------------------------------- assemble
def assemble(roteiro, avatar, inserts_map, out, cfg):
    """Assemble the 9:16 base video from script + avatar + inserts.

    Args:
        roteiro: path to the annotated script (see vam.parser).
        avatar: path to the avatar mp4 (continuous narration, lip-synced).
        inserts_map: {keyword: {file, start, speed, zoom}} — keyword is
            matched against the insert instruction text.
        out: output mp4 path (clean base, captions burned separately).
        cfg: vam.config.Config.

    Returns the timing dict {a0, total, letterings, inserts} — also written
    to cfg.workdir/timing.json. All times are avatar-time seconds;
    reel-time t maps to avatar-time a0 + t.
    """
    tmp = os.path.join(cfg.workdir, "montage_tmp")
    os.makedirs(tmp, exist_ok=True)

    blocks = parse(roteiro)
    if not blocks:
        raise ValueError(f"No scenes found in '{roteiro}'. Each line must be "
                         "'[visual instruction] narration...'.")
    narr_words = []
    for b in blocks:
        narr_words += b["narr"].split()
    words = align(avatar, narr_words, cfg, tmp)

    # Assign each block its avatar-time span by word count.
    spans = []
    idx = 0
    for b in blocks:
        n = len(b["narr"].split())
        seg = words[idx:idx + n] if n else words[idx:idx + 1]
        idx += n
        s = seg[0][0] if seg else (spans[-1][1] if spans else 0.0)
        e = seg[-1][1] if seg else s + 0.8
        if e <= s:
            e = s + 0.6
        spans.append((s, e))
    total = words[-1][1]

    # Render every scene (each one except the last gets an XF handle so the
    # dissolve overlaps without eating narration).
    n = len(blocks)
    segs = []
    letter_ranges = []
    for i, (b, (s, e)) in enumerate(zip(blocks, spans)):
        ee = e + (XF if i < n - 1 else 0.0)
        scene = os.path.join(tmp, f"s{i:02d}.mp4")
        tipo = b["tipo"]
        if tipo == "orig":
            _r_orig(avatar, s, ee, scene, cfg.fonts_dir)
        elif tipo == "insert":
            _r_insert(find_insert(b["instr"], inserts_map), s, ee, scene)
        elif tipo == "logo":
            _r_logo(s, ee, scene, cfg, tmp)
        elif tipo in ("lettering", "lettering_logo"):
            _r_lettering(avatar, b.get("lead", ""), b.get("key") or b["narr"],
                         s, ee, scene, cfg, tmp, withlogo=(tipo == "lettering_logo"))
        else:  # pragma: no cover - parser only emits the types above
            raise ValueError(f"Unknown scene type '{tipo}'")
        segs.append(scene)

        if tipo in ("lettering", "lettering_logo"):
            letter_ranges.append((s, e))

    # Chain with pure dissolves (xfade=fade): nothing slides, so the PiP
    # circle never "travels" across a cut. Offsets use frame-counted
    # durations (audio padding would drift the chain otherwise).
    if n > 1:
        durs = [_video_duration_frames(p) for p in segs]
        inputs = []
        for p in segs:
            inputs += ["-i", p]
        fc = []
        prev = "0:v"
        acc = durs[0]
        for i in range(1, n):
            off = acc - XF
            fc.append(f"[{prev}][{i}:v]xfade=transition=fade:duration={XF}:offset={off:.4f}[v{i}]")
            prev = f"v{i}"
            acc = acc + durs[i] - XF
        vchain = os.path.join(tmp, "vchain.mp4")
        run_ffmpeg(["ffmpeg", "-y", *inputs, "-filter_complex", "; ".join(fc),
                    "-map", f"[{prev}]", "-r", str(FPS),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", vchain],
                   label="xfade chain")
    else:
        vchain = segs[0]

    # Reattach the CONTINUOUS avatar audio (lip-sync preserved, zero drift)
    # and apply the subtle film treatment (grain + contrast + vignette).
    a0 = spans[0][0]
    audlen = total - a0
    run_ffmpeg(["ffmpeg", "-y", "-i", vchain,
                "-ss", str(a0), "-t", str(audlen), "-i", avatar,
                "-filter_complex",
                "[0:v]noise=alls=7:allf=t+u,eq=contrast=1.03:saturation=0.97,"
                "vignette=PI/5.5[v]",
                "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-crf", "18",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", out],
               label="final mux")

    timing = {
        "a0": a0,
        "total": total,
        "avatar": avatar,
        "letterings": [{"s": s, "e": e} for s, e in letter_ranges],
        "inserts": [{"s": spans[i][0], "e": spans[i][1]}
                    for i, b in enumerate(blocks) if b["tipo"] == "insert"],
    }
    write_timing(timing, cfg)
    return timing


# ---------------------------------------------------------------- PiP layer
def overlay_pip(src, dst, avatar, timing, cfg):
    """Overlay the circular presenter PiP over the insert windows.

    Run this AFTER captions are burned (caption zoom effects would drag the
    circle otherwise). The avatar is trimmed to a0 so avatar-time aligns
    with reel-time; the circle only shows during insert windows.
    """
    wins = [(round(i["s"] - timing["a0"], 3), round(i["e"] - timing["a0"], 3))
            for i in timing["inserts"]]
    if not wins:
        raise ValueError("timing has no insert windows; nothing to overlay.")
    tmp = os.path.join(cfg.workdir, "montage_tmp")
    os.makedirs(tmp, exist_ok=True)
    mask, ring, shadow = _make_circle_assets(tmp, cfg.brand.key_color_bgr)
    fc = pip_filter(wins)
    run_ffmpeg(["ffmpeg", "-y", "-i", src, "-ss", str(timing["a0"]), "-i", avatar,
                "-i", mask, "-i", ring, "-i", shadow,
                "-filter_complex", fc, "-map", "[v]", "-map", "0:a", "-shortest",
                "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                "-c:a", "copy", "-movflags", "+faststart", dst],
               label="pip overlay")
    return dst
