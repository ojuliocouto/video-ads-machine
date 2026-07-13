"""Tests for vam.montage: foil lettering ASS, color derivation, filter graphs,
word alignment and timing persistence. No ffmpeg is executed here — we test
the generated ASS strings and filter_complex strings directly.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from vam import montage  # noqa: E402
from vam.config import AudioConfig, BrandConfig, Config, LetteringConfig  # noqa: E402

FONTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "fonts")


def make_cfg(**over):
    cfg = Config(
        avatar_id="YOUR_AVATAR_ID",
        brand=BrandConfig(),
        lettering=LetteringConfig(),
        audio=AudioConfig(),
        fonts_dir=FONTS_DIR,
    )
    for k, v in over.items():
        setattr(cfg, k, v)
    return cfg


def _ksz(ass):
    return int(re.search(r"Style: D, DM Serif Display, (\d+)", ass).group(1))


# ---------- foil color derivation ----------

def test_foil_bands_shape_and_base():
    bands = montage.derive_foil_bands("4AA6FF")
    assert len(bands) == 5
    assert bands[2] == "4AA6FF"          # middle band = untouched key color
    for b in bands:
        assert re.fullmatch(r"[0-9A-F]{6}", b)


def test_foil_bands_luminance_ramp_crest_to_bronze():
    def lum(bgr):  # rough luminance from a BGR hex
        b, g, r = int(bgr[0:2], 16), int(bgr[2:4], 16), int(bgr[4:6], 16)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    bands = montage.derive_foil_bands("4AA6FF")
    lums = [lum(b) for b in bands]
    assert lums == sorted(lums, reverse=True), "bands must go light -> dark"


def test_foil_bands_follow_custom_brand_color():
    assert montage.derive_foil_bands("2244AA")[2] == "2244AA"
    assert montage.derive_foil_bands("2244AA") != montage.derive_foil_bands("4AA6FF")


def test_rim_and_glow_outline_derived():
    rim = montage.rim_color("4AA6FF")
    glow = montage.glow_outline_color("4AA6FF")
    assert re.fullmatch(r"[0-9A-F]{6}", rim)
    assert re.fullmatch(r"[0-9A-F]{6}", glow)
    assert rim != glow != "4AA6FF"


# ---------- serif lettering ASS (foil default) ----------

def test_foil_ass_has_five_clip_bands_with_derived_colors():
    cfg = make_cfg()
    ass = montage.build_lettering_ass("uma skill de", "PAGINAS", 3.0, cfg)
    bands = montage.derive_foil_bands(cfg.brand.key_color_bgr)
    clip_lines = [l for l in ass.splitlines() if "\\clip(" in l and "\\blur0.6" not in l]
    assert len(clip_lines) == 5
    for c, line in zip(bands, clip_lines):
        assert f"\\1c&H{c}&" in line


def test_foil_ass_exact_validated_geometry():
    cfg = make_cfg()
    y = cfg.lettering.y_key  # 1690
    ass = montage.build_lettering_ass("", "PAGINAS", 3.0, cfg)
    ksz = _ksz(ass)
    gtop = round(y - 0.44 * ksz)
    gbot = round(y + 0.32 * ksz)
    span = gbot - gtop
    yb = [gtop + round(i * span / 5) for i in range(6)]
    for i in range(5):
        assert f"\\clip(30,{yb[i]},1050,{yb[i + 1]})" in ass
    # rim light on the crest: top 16% of the span, subtle blur
    rim_bot = gtop + round(0.16 * span)
    assert f"\\blur0.6\\1c&H{montage.rim_color(cfg.brand.key_color_bgr)}&" in ass
    assert f"\\clip(30,{gtop},1050,{rim_bot})" in ass


def test_foil_ass_every_foil_line_has_pos():
    cfg = make_cfg()
    y = cfg.lettering.y_key
    ass = montage.build_lettering_ass("", "PAGINAS", 3.0, cfg)
    foil_lines = [l for l in ass.splitlines()
                  if l.startswith("Dialogue") and ("\\clip(" in l or "\\blur9" in l)]
    assert len(foil_lines) == 7  # glow + 5 bands + rim
    for line in foil_lines:
        assert f"\\pos(540,{y})" in line


def test_foil_ass_glow_layer_subtle():
    cfg = make_cfg()
    ass = montage.build_lettering_ass("", "PAGINAS", 3.0, cfg)
    glow = [l for l in ass.splitlines() if "\\bord5\\blur9" in l]
    assert len(glow) == 1
    assert f"\\1c&H{cfg.brand.key_color_bgr}&" in glow[0]
    assert "\\1a&H86&" in glow[0] and "\\3a&H4A&" in glow[0] and "\\4a&HFF&" in glow[0]


def test_foil_ass_base_pop_line_crisp():
    cfg = make_cfg()
    y = cfg.lettering.y_key
    ass = montage.build_lettering_ass("", "PAGINAS", 3.0, cfg)
    base = [l for l in ass.splitlines() if "\\move(" in l and "PAGINAS" in l]
    assert base, "crisp base line with pop must exist"
    assert f"\\move(540,{y + 38},540,{y},0,250)" in base[0]
    assert "\\fscx44\\fscy44" in base[0]  # validated overshoot pop


def test_foil_starts_after_pop_settles():
    cfg = make_cfg()
    ass = montage.build_lettering_ass("", "PAGINAS", 3.0, cfg)
    clip_lines = [l for l in ass.splitlines() if "\\clip(" in l]
    for line in clip_lines:
        assert line.split(",")[1] == "0:00:00.42"  # gs = 0.42s


def test_lettering_y_with_logo():
    cfg = make_cfg()
    ass = montage.build_lettering_ass("", "PAGINAS", 3.0, cfg, withlogo=True)
    assert f"\\pos(540,{cfg.lettering.y_key_with_logo})" in ass
    assert f"\\pos(540,{cfg.lettering.y_key})" not in ass


def test_solid_style_has_no_foil_layers():
    cfg = make_cfg()
    cfg.lettering.style = "solid"
    ass = montage.build_lettering_ass("uma skill de", "PAGINAS", 3.0, cfg)
    assert "\\clip(" not in ass
    assert "\\blur9" not in ass
    assert "\\move(" in ass  # key still pops in


def test_lettering_key_uppercased_and_style_color():
    cfg = make_cfg()
    ass = montage.build_lettering_ass("", "paginas", 3.0, cfg)
    assert "PAGINAS" in ass
    assert f"&H00{cfg.brand.key_color_bgr}" in ass  # Style D primary colour


def test_lettering_lead_line_playfair_italic():
    cfg = make_cfg()
    ass = montage.build_lettering_ass("uma skill de", "PAGINAS", 3.0, cfg)
    assert "Style: P, Playfair Display, 90" in ass
    lead = [l for l in ass.splitlines() if "uma skill de" in l and l.startswith("Dialogue")]
    assert len(lead) == 1 and "\\move(" in lead[0]


def test_fit_key_longer_text_smaller_font():
    short = _ksz(montage.build_lettering_ass("", "SIM", 3.0, make_cfg()))
    long_ = _ksz(montage.build_lettering_ass("", "TRANSFORMACAO TOTAL", 3.0, make_cfg()))
    assert long_ < short


# ---------- word alignment (pure, no transcription backend) ----------

def test_align_words_exact_match():
    rec = [(0.0, 0.3, "olá"), (0.35, 0.6, "mundo"), (0.65, 1.0, "bom")]
    out = montage.align_words(rec, ["Olá", "mundo", "bom"])
    assert out == [(0.0, 0.3, "Olá"), (0.35, 0.6, "mundo"), (0.65, 1.0, "bom")]


def test_align_words_accent_and_punct_insensitive():
    rec = [(0.0, 0.3, "paginas"), (0.4, 0.8, "inteiras")]
    out = montage.align_words(rec, ["páginas", "inteiras!"])
    assert out[0][:2] == (0.0, 0.3)


def test_align_words_interpolates_unmatched():
    rec = [(0.0, 0.3, "um"), (1.0, 1.4, "tres")]
    out = montage.align_words(rec, ["um", "dois", "tres"])
    s, e, w = out[1]
    assert w == "dois"
    assert 0.3 <= s <= 1.0 and s <= e <= 1.0  # sits between its neighbors


# ---------- filter graphs (strings only) ----------

def test_orig_filter_reframe_and_soft_zoom():
    vf = montage.orig_filter(90)
    assert montage.REFRAME in vf
    assert "zoompan=z='min(zoom+0.0003,1.07)'" in vf
    assert "trim=end_frame=90" in vf


def test_insert_filter_fullscreen_fit_over_blur():
    fc = montage.insert_filter(1.5, 60)
    assert "setpts=PTS/1.5" in fc
    assert "boxblur=24:1" in fc
    assert "force_original_aspect_ratio=increase" in fc
    assert "force_original_aspect_ratio=decrease" in fc
    assert "overlay=(W-w)/2:(H-h)/2" in fc


def test_pip_filter_circular_windows():
    fc = montage.pip_filter([(1.0, 2.0), (3.0, 4.5)])
    assert "alphamerge" in fc
    assert "between(t,1.0,2.0)+between(t,3.0,4.5)" in fc
    assert f"overlay={montage.PIPX}:{montage.PIPY}" in fc
    # shadow floats 14px below the ring frame
    assert f"overlay={montage.PIPX - montage.PIPF}:{montage.PIPY - montage.PIPF + 14}" in fc


def test_find_insert_keyword_and_fallback():
    m = {"produto": {"file": "a.mp4"}, "depoimento": {"file": "b.mp4"}}
    assert montage.find_insert("tela do PRODUTO girando", m)["file"] == "a.mp4"
    assert montage.find_insert("nada casa aqui", m)["file"] == "a.mp4"  # first = fallback


# ---------- timing persisted per build (no shared global path) ----------

def test_timing_written_inside_workdir(tmp_path):
    cfg = make_cfg(workdir=str(tmp_path / "build"))
    timing = {"a0": 0.4, "total": 21.7, "letterings": [{"s": 3, "e": 5}],
              "inserts": [{"s": 8, "e": 11}]}
    path = montage.write_timing(timing, cfg)
    assert path == os.path.join(cfg.workdir, "timing.json")
    assert json.load(open(path)) == timing


def test_clean_display_strips_script_artifacts():
    assert montage.clean_display("veja…  isso..") == "veja isso"
