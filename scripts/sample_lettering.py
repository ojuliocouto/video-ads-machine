#!/usr/bin/env python3
"""Renderiza AMOSTRAS curtas do lettering KEY (laranja) sobre o avatar real, com PARIDADE
total ao pipeline (mesmo REFRAME/zoompan/fontes/logo do produzir_roteiro.py). Serve pra
testar VARIACOES do lettering laranja sem re-renderizar o video inteiro.

Uso:  python3 sample_lettering.py <variant> <lead> "<KEY>" <withlogo 0|1> <avatar_start> <dur> <out.mp4>
Variantes: atual | foil | relevo | sweep | fio
Env:  VAM_AVATAR (default inputs/avatar_ad01.mp4)
"""
import os, sys, subprocess
from PIL import ImageFont

# (migracao 26/08/2026) caminho de projeto agora sai de caminhos.py
from caminhos import DADOS as _D
BASE = str(_D)
TMP  = os.path.join(BASE, "_tmp_sample"); os.makedirs(TMP, exist_ok=True)
W, H, FPS = 1080, 1920, 30
FONTS = os.path.join(BASE, "fonts")
LOGO  = os.path.join(BASE, "assets", "logo_occ_branca.png")
AVATAR = os.path.expanduser(os.environ.get("VAM_AVATAR", os.path.join(BASE, "inputs", "avatar_ad01.mp4")))
REFRAME = "scale=2376:4224:force_original_aspect_ratio=increase,crop=2160:3840:108:652"
_DMFP = os.path.join(FONTS, "DMSerifDisplay.ttf")

def nframes(d): return max(1, round(d * FPS))
def cap(N): return f"trim=end_frame={N},setpts=N/{FPS}/TB"
def _sub(ass): return f",subtitles={ass}:fontsdir={FONTS}" if ass else ""
def run(c):
    r = subprocess.run(c, capture_output=True, text=True)
    if r.returncode != 0:
        print("ERRO:", " ".join(c[:6]), "\n", r.stderr[-900:]); sys.exit(1)
    return r
def ts(x): return f"{int(x//3600)}:{int((x%3600)//60):02d}:{x%60:05.2f}"

def fit_key(key, base=176, maxw=960):
    try:
        for sz in range(base, 84, -6):
            if ImageFont.truetype(_DMFP, sz).getbbox(key)[2] <= maxw: return sz
        return 96
    except Exception:
        return base if len(key) <= 7 else 120

def key_width(key, ksz):
    try: return ImageFont.truetype(_DMFP, ksz).getbbox(key)[2]
    except Exception: return int(ksz*len(key)*0.55)

HEAD = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV\n")
EVHEAD = "\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, Effect, Text\n"

POP_K = r"\fscx44\fscy44\t(0,160,\fscx114\fscy114)\t(160,300,\fscx100\fscy100)"
POP_L = r"\fscx74\fscy74\t(0,150,\fscx104\fscy104)\t(150,260,\fscx100\fscy100)"

def D(layer, s, e, ov, txt):
    return f"Dialogue: {layer},{ts(s)},{ts(e)},D,,0,0,0,{{{ov}}}{txt}"

def styles_pd(ksz):
    return ("Style: P, Playfair Display, 90, &H00FFFFFF, &H00202020, &H90000000, 0, 1, 1, 2.4, 3, 5, 60, 60, 0\n"
            f"Style: D, DM Serif Display, {ksz}, &H004AA6FF, &H00101010, &H90000000, 0, 0, 1, 3.2, 4, 5, 40, 40, 0\n")

def lead_event(lead, y_lead, d):
    ov = r"\an5\move(540,%d,540,%d,0,220)\fad(110,0)" % (y_lead+24, y_lead) + POP_L
    return f"Dialogue: 0,{ts(0.0)},{ts(d)},P,,0,0,0,{{{ov}}}{lead}"

# ---------------------------------------------------------------------------
# VARIANTES DA KEY. cada uma retorna a lista de eventos Dialogue (Style D).
# ---------------------------------------------------------------------------
def v_atual(y, ksz, d, kw, key):
    return [D(0, 0.12, d, r"\an5\move(540,%d,540,%d,0,250)\fad(130,0)" % (y+38, y) + POP_K, key)]

def v_foil(y, ksz, d, kw, key):
    gs = 0.42
    gtop = round(y - 0.44*ksz); gbot = round(y + 0.32*ksz); span = gbot - gtop
    yb = [gtop + round(i*span/5) for i in range(6)]
    rimTop = gtop; rimBot = gtop + round(0.16*span)
    cols = ["A8E0FF", "7AC6FF", "4AA6FF", "3084E2", "1C64BC"]
    ev = [
        D(3, gs, d, r"\an5\pos(540,%d)\bord5\blur9\shad0\1c&H4AA6FF&\3c&H145AB4&\1a&H86&\3a&H4A&\4a&HFF&\fad(200,0)" % y, key),
        D(4, 0.12, d, r"\an5\move(540,%d,540,%d,0,250)\fad(130,0)" % (y+38, y) + POP_K, key),
    ]
    for i, c in enumerate(cols):
        ev.append(D(5, gs, d, r"\an5\pos(540,%d)\bord0\shad0\1c&H%s&\fad(150,0)\clip(30,%d,1050,%d)" % (y, c, yb[i], yb[i+1]), key))
    ev.append(D(6, gs, d, r"\an5\pos(540,%d)\bord0\shad0\blur0.6\1c&HDCF5FF&\fad(150,0)\clip(30,%d,1050,%d)" % (y, rimTop, rimBot), key))
    return ev

def v_relevo(y, ksz, d, kw, key):
    return [
        D(0, 0.12, d, r"\an5\move(540,%d,540,%d,0,250)\fad(180,0)\bord0\shad0\blur7\1c&H121418&\1a&H80&" % (y+42, y+4) + POP_K, key),
        D(1, 0.12, d, r"\an5\move(540,%d,540,%d,0,250)\fad(130,0)\bord0\shad0\1c&H225896&" % (y+40, y+2) + POP_K, key),
        D(2, 0.12, d, r"\an5\move(540,%d,540,%d,0,250)\fad(130,0)\bord3.2\shad0\3c&H101010&\1c&H4AA6FF&" % (y+38, y) + POP_K, key),
    ]

def v_sweep(y, ksz, d, kw, key):
    ytop = round(y - 0.60*ksz); ybot = round(y + 0.60*ksz)
    return [
        D(0, 0.12, d, r"\an5\move(540,%d,540,%d,0,250)\fad(130,0)" % (y+38, y) + POP_K, key),
        D(1, 0.12, d, r"\an5\pos(540,%d)\bord0\shad0\blur6\1c&HEAF6FF&\3a&HFF&\4a&HFF&\1a&HFF&\clip(-210,%d,-40,%d)\t(270,320,\1a&H12&)\t(300,640,\clip(1160,%d,1330,%d))\t(600,700,\1a&HFF&)" % (y, ytop, ybot, ytop, ybot), key),
    ]

def v_fio(y, ksz, d, kw, key):
    yfio = y + round(ksz*0.42) + 22; yfioT = yfio-6; yfioB = yfio+6
    Wfio = max(34, min(120, round(kw*0.22))); xL = 540-Wfio; xR = 540+Wfio
    fio_ov = (r"\an5\pos(540,%d)\1c&H4AA6FF&\bord0\shad0\blur0.6\fad(140,120)\p1\clip(540,%d,540,%d)\t(300,600,\clip(%d,%d,%d,%d))"
              % (yfio, yfioT, yfioB, xL, yfioT, xR, yfioB))
    fio_txt = "m -%d -3 l %d -3 l %d 3 l -%d 3" % (Wfio, Wfio, Wfio, Wfio) + r"{\p0}"
    return [
        D(0, 0.12, d, r"\an5\move(544,%d,544,%d,0,250)\fad(130,0)\1c&H040C18&\3a&HFF&\4a&HFF&\1a&H82&\blur6" % (y+45, y+7) + POP_K, key),
        D(1, 0.12, d, fio_ov, fio_txt),
        D(2, 0.12, d, r"\an5\move(540,%d,540,%d,0,250)\fad(130,0)\fsp2\4c&H040C18&\shad2" % (y+38, y) + POP_K, key),
    ]

VARIANTS = {"atual": v_atual, "foil": v_foil, "relevo": v_relevo, "sweep": v_sweep, "fio": v_fio}

def build_ass(variant, lead, key, d, withlogo):
    key = key.upper()
    ksz = fit_key(key); kw = key_width(key, ksz)
    y_key = 1500 if withlogo else 1690
    y_lead = y_key - int(ksz*0.58) - 40
    ev = []
    if lead: ev.append(lead_event(lead, y_lead, d))
    ev += VARIANTS[variant](y_key, ksz, d, kw, key)
    ass = os.path.join(TMP, f"{variant}_{abs(hash(key))%9999}.ass")
    open(ass, "w").write(HEAD + styles_pd(ksz) + EVHEAD + "\n".join(ev) + "\n")
    return ass

def render(variant, lead, key, withlogo, s, dur, out):
    d = dur; N = nframes(dur)
    ass = build_ass(variant, lead, key, d, withlogo)
    zp = (f"fps={FPS},{REFRAME},"
          f"zoompan=z='min(zoom+0.0003,1.06)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H},"
          f"setsar=1,{cap(N)}")
    if withlogo:
        inputs = ["-ss", str(s), "-t", str(d+0.4), "-i", AVATAR, "-i", LOGO]
        fc = f"[0:v]{zp}[bg];[1:v]scale=430:-1[lg];[bg][lg]overlay=(W-w)/2:H-h-46{_sub(ass)}[v]"
    else:
        inputs = ["-ss", str(s), "-t", str(d+0.4), "-i", AVATAR]
        fc = f"[0:v]{zp}{_sub(ass)}[v]"
    run(["ffmpeg", "-y", *inputs, "-filter_complex", fc, "-map", "[v]", "-an",
         "-r", str(FPS), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", out])
    print(f"OK {variant} -> {out}")

if __name__ == "__main__":
    a = sys.argv
    if len(a) < 8: sys.exit(__doc__)
    render(a[1], a[2], a[3], a[4] == "1", float(a[5]), float(a[6]), a[7])
