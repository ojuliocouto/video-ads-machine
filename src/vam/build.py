"""Gated pipeline orchestrator: one command runs everything, gates block it.

Runs the whole ad pipeline in the right order and REFUSES to move on when a
checkpoint fails. Every gate below was validated in production; the goal is
that neither an agent nor a human can skip a step or ship a half-done video.

Usage
-----
    python3 -m vam.build <build.yaml>          # or: vam build <build.yaml>

The build file is the regular pipeline config (see ``config.example.yaml``)
plus a ``project`` section and, optionally, an ``avatars`` list::

    avatar_id: "YOUR_AVATAR_ID"        # single-variant build
    accelerate: 1.2
    drive_folder: https://drive.google.com/drive/folders/YOUR_FOLDER_ID  # optional
    workdir: ./build

    project:
      name: my-ad
      raw_voice: inputs/voice.mp3      # REAL recorded voice (never TTS)
      script: inputs/script.txt        # annotated script (see vam.parser)
      inserts: inputs/inserts.json     # optional {keyword: {file, ...}} map
      expected_lettering_scenes: 2     # optional; default: counted in script

    avatars:                           # optional: several avatar variants,
      - name: studio                   # rendered SEQUENTIALLY, one full
        avatar_id: "YOUR_AVATAR_ID"    # pipeline each, same cleaned voice
      - name: casual
        avatar_id: "YOUR_OTHER_AVATAR_ID"

Relative paths in the file resolve against the build file's directory.

Gates (each one fails the build with a clear fix-it message; CLI exits 1):
    G0 preflight   inputs exist; no insert instruction contains a presenter
                   word (parser gotcha); every variant has an avatar_id;
                   reminder that the voice must be REAL, never TTS
    G1 audio       cleaned voice exists and has NO big silence left
    G2 avatar      dur(avatar) ~= dur(clean) -> the avatar really used the
                   cleaned audio (engine already locked in vam.heygen)
    G3 montage     the timing has the N lettering scenes the script announces
                   (timing is per build, in the variant workdir: no global
                   state, no lock needed)
    G4 captions    both the 9:16 and the 1:1 captioned outputs exist
    G5 accelerate  dur(final) ~= dur(captioned) / factor
    G6 final audit zero big silences in the final + duration consistent
                   across variants
    G7 drive       only if ``drive_folder`` is set: uploads the finals and
                   VERIFIES them in the folder listing

The manifest (JSON receipt with every gate's metrics and PASS/FAIL) is
written to ``<workdir>/<name>_manifest.json``; "done" means a green manifest.
"""
import dataclasses
import json
import os
import sys

from . import accelerate as accel
from . import audio
from . import captions
from . import config
from . import drive
from . import ffutil
from . import heygen
from . import montage
from . import parser

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only without pyyaml
    yaml = None

# Gate tolerances (validated in production; not user-facing config).
BIG_SIL_GATE = 0.65      # the final video may not contain silences > this (s)
AVATAR_DUR_TOL = 0.8     # avatar duration must match the cleaned voice (s)
ACCEL_TOL = 0.35         # tolerance of the acceleration gate (s)
VARIANT_DUR_TOL = 0.7    # variants of the same ad must land on the same length (s)

# Words that hint an instruction is meant as an insert (b-roll) scene.
_INSERT_HINTS = ("insert", "b-roll", "broll", "footage", "inser")

_PROJECT_KEYS = {"name", "raw_voice", "script", "inserts",
                 "expected_lettering_scenes"}


class GateFail(Exception):
    """A quality gate failed; the message says what is wrong and how to fix it."""


# --------------------------------------------------------------------- utils

def _resolve(base_dir, path):
    """Resolve a config-relative path against the build file's directory."""
    if not path:
        return path
    return path if os.path.isabs(path) else os.path.normpath(
        os.path.join(base_dir, path))


def count_lettering_scenes(script_path):
    """Number of lettering scenes the annotated script announces."""
    return sum(1 for b in parser.parse(script_path)
               if b["tipo"] in ("lettering", "lettering_logo"))


def insert_gotcha_lines(script_path,
                        presenter_words=parser.PRESENTER_WORDS):
    """Line numbers whose insert instruction contains a presenter word.

    Validated parser gotcha: the presenter check runs before the insert
    fallback, so an instruction like "[insert b-roll with the presenter]"
    silently becomes a full-screen presenter scene. Catch it in preflight.
    """
    bad = []
    with open(script_path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            m = parser._LINE.match(line.strip())
            if not m:
                continue
            instr = m.group(1).lower()
            if (any(h in instr for h in _INSERT_HINTS)
                    and any(w in instr for w in presenter_words)):
                bad.append(n)
    return bad


# ------------------------------------------------------------- build config

def _load_build_file(config_path):
    """Parse the build YAML into (cfg, project dict, variants list).

    The file is the regular pipeline config plus the build-only sections
    ``project`` (inputs) and ``avatars`` (variant list). Everything else is
    validated by vam.config, so typos get the same friendly errors.
    """
    if yaml is None:
        raise config.ConfigError(
            "The 'pyyaml' package is not installed. "
            "Install it with: pip install pyyaml")
    if not os.path.exists(config_path):
        raise config.ConfigError(
            f"Build file not found: {config_path}\n"
            "Pass the path to your build YAML (see the vam.build docstring "
            "for the schema).")
    with open(config_path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise config.ConfigError(
            f"{config_path} must contain a YAML mapping (key: value), "
            f"got {type(raw).__name__}.")

    project = raw.pop("project", None)
    if not isinstance(project, dict):
        raise config.ConfigError(
            "Missing 'project' section in the build file. Add:\n\n"
            "  project:\n"
            "    name: my-ad\n"
            "    raw_voice: inputs/voice.mp3\n"
            "    script: inputs/script.txt\n"
            "    inserts: inputs/inserts.json   # optional")
    unknown = sorted(set(project) - _PROJECT_KEYS)
    if unknown:
        raise config.ConfigError(
            f"Unknown key(s) {unknown} under 'project'. "
            f"Valid keys: {sorted(_PROJECT_KEYS)}.")
    for k in ("raw_voice", "script"):
        if not project.get(k):
            raise config.ConfigError(
                f"'project.{k}' is required in the build file "
                "(the pipeline cannot run without it).")
    project.setdefault("name", "ad")

    avatars = raw.pop("avatars", None) or []
    if avatars and not isinstance(avatars, list):
        raise config.ConfigError(
            "'avatars' must be a list of {name, avatar_id} mappings.")
    if avatars:
        # config requires a non-empty avatar_id; borrow the first variant's
        # (each variant is still individually validated in G0).
        first = next((str(v.get("avatar_id"))
                      for v in avatars if v.get("avatar_id")), "PENDING")
        raw.setdefault("avatar_id", first)

    cfg = config.from_dict(raw)

    if avatars:
        variants = [{"name": str(v.get("name") or f"look{i + 1}"),
                     "avatar_id": str(v.get("avatar_id") or "")}
                    for i, v in enumerate(avatars)]
    else:
        variants = [{"name": "default", "avatar_id": cfg.avatar_id}]
    return cfg, project, variants


def _load_inserts(path):
    """Load the inserts map ({keyword: {file, ...}}), resolving file paths."""
    if not path:
        return {}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    base = os.path.dirname(os.path.abspath(path))
    out = {}
    for key, val in data.items():
        if isinstance(val, str):        # shorthand: keyword -> file path
            val = {"file": val}
        val = dict(val)
        val["file"] = _resolve(base, val.get("file"))
        out[key] = val
    return out


# ---------------------------------------------------------------- gate log

class _GateLog:
    """Per-build gate recorder (no global state: builds never share it)."""

    def __init__(self):
        self.entries = []

    def check(self, name, ok, detail, metrics=None):
        self.entries.append({"gate": name, "ok": bool(ok), "detail": detail,
                             "metrics": metrics or {}})
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        if not ok:
            raise GateFail(f"gate {name} failed: {detail}")


# ------------------------------------------------------------------- gates

def _g0_preflight(gates, project, variants):
    print("== G0 preflight ==")
    for key in ("raw_voice", "script"):
        path = project[key]
        gates.check(f"input:{key}", os.path.exists(path),
                    path if os.path.exists(path) else
                    f"not found: {path} -- fix 'project.{key}' in the build "
                    "file (paths are relative to the build file).")
    if project.get("inserts"):
        path = project["inserts"]
        gates.check("input:inserts", os.path.exists(path),
                    path if os.path.exists(path) else
                    f"not found: {path} -- fix 'project.inserts' or remove it.")
        missing = [v["file"] for v in _load_inserts(path).values()
                   if not (v.get("file") and os.path.exists(v["file"]))]
        gates.check("insert_media_exists", not missing,
                    "all insert clips found" if not missing else
                    f"insert clip(s) not found: {missing} -- fix the 'file' "
                    "paths inside the inserts JSON.")

    scenes = len(parser.parse(project["script"]))
    gates.check("script_has_scenes", scenes > 0,
                f"{scenes} scene(s) parsed" if scenes else
                "no scenes found -- each script line must be "
                "'[visual instruction] narration...'.")

    bad = insert_gotcha_lines(project["script"])
    gates.check(
        "no_presenter_word_in_insert_instructions", not bad,
        "no insert instruction mentions the presenter" if not bad else
        f"line(s) {bad}: an insert instruction contains a presenter word "
        f"({', '.join(parser.PRESENTER_WORDS)}), so the parser classifies it "
        "as a full-screen presenter scene. Name the footage instead "
        "(e.g. 'product screen recording').")

    missing = [v["name"] for v in variants if not v["avatar_id"]]
    gates.check("variants_have_avatar_id", not missing,
                f"{len(variants)} variant(s) with avatar_id" if not missing
                else f"variant(s) {missing} have no avatar_id -- set it in "
                "the 'avatars' list (each entry needs its own avatar_id).")

    gates.check("real_voice_reminder", True,
                "REMINDER (cannot be enforced by code): the voice must be a "
                "REAL recording of a person. NEVER TTS.")


def _g1_audio(gates, project, cfg):
    print("== G1 voice hygiene (energy-based de-breath) ==")
    clean = os.path.join(cfg.workdir, "voice_clean.mp3")
    os.makedirs(cfg.workdir, exist_ok=True)
    metrics = audio.clean_voice(project["raw_voice"], clean, cfg)
    gates.check("voice_clean_exists", os.path.exists(clean), clean)
    resid = metrics.get("residual_big") or []
    clean_dur = ffutil.duration(clean)
    gates.check(
        "no_big_silence_left", not resid,
        f"0 silences > {cfg.audio.big_sil}s left in the cleaned voice"
        if not resid else
        f"{len(resid)} big silence(s) still in the cleaned voice: {resid}. "
        "Try raising audio.sil_db in your config (e.g. -25) or re-record in "
        "a quieter room (a high noise floor hides the pauses).",
        {"raw_dur": metrics.get("src_dur"), "clean_dur": round(clean_dur, 2),
         "cuts": metrics.get("cuts"), "removed_s": metrics.get("removed_s"),
         "residual_big": resid})
    return clean, clean_dur


def _g2_avatar(gates, variant, clean, clean_dur, cfg_v):
    print(f"== G2 avatar render [{variant['name']}] ==")
    out = os.path.join(cfg_v.workdir, "avatar.mp4")
    # vam.heygen already locks the engine; no engine is passed on purpose.
    heygen.generate_avatar(clean, out, cfg_v)
    ad = ffutil.duration(out)
    gates.check(
        "avatar_matches_clean_audio", abs(ad - clean_dur) <= AVATAR_DUR_TOL,
        f"avatar {ad:.2f}s ~= cleaned voice {clean_dur:.2f}s"
        if abs(ad - clean_dur) <= AVATAR_DUR_TOL else
        f"avatar duration {ad:.2f}s does not match the cleaned voice "
        f"{clean_dur:.2f}s (tolerance {AVATAR_DUR_TOL}s). The avatar must be "
        "generated from the CLEANED audio -- re-run and make sure no other "
        "audio was uploaded.",
        {"avatar_dur": round(ad, 2), "clean_dur": round(clean_dur, 2)})
    return out


def _g3_montage(gates, project, variant, avatar, inserts_map, cfg_v, expected):
    print(f"== G3 montage [{variant['name']}] ==")
    base = os.path.join(cfg_v.workdir, "base.mp4")
    timing = montage.assemble(project["script"], avatar, inserts_map,
                              base, cfg_v)
    lets = len(timing.get("letterings") or [])
    gates.check(
        "lettering_scenes", lets == expected,
        f"{lets} lettering scene(s) (expected {expected})" if lets == expected
        else f"montage produced {lets} lettering scene(s) but the script "
        f"announces {expected}. Check the [lettering ...] lines of the "
        "script (or set project.expected_lettering_scenes).",
        {"lettering_scenes": lets, "expected": expected})
    if timing.get("inserts"):
        pip = os.path.join(cfg_v.workdir, "pip.mp4")
        montage.overlay_pip(base, pip, avatar, timing, cfg_v)
    else:
        pip = base
    return pip, timing


def _g4_captions(gates, project, variant, pip, timing, cfg_v):
    print(f"== G4 captions 9:16 + 1:1 [{variant['name']}] ==")
    script = project["script"]
    cap9 = os.path.join(cfg_v.workdir, "captions_9x16.mp4")
    captions.burn(pip, cap9, script, "9x16", cfg_v, timing)
    square = os.path.join(cfg_v.workdir, "square.mp4")
    captions.make_square(pip, square)
    cap1 = os.path.join(cfg_v.workdir, "captions_1x1.mp4")
    captions.burn(square, cap1, script, "1x1", cfg_v, timing)
    missing = [p for p in (cap9, cap1) if not os.path.exists(p)]
    gates.check("captions_9x16_and_1x1", not missing,
                "9:16 and 1:1 captioned outputs generated" if not missing
                else f"missing captioned output(s): {missing}")
    return cap9, cap1


def _g5_accelerate(gates, name, variant, cap9, cap1, cfg, workdir):
    factor = cfg.accelerate
    print(f"== G5 accelerate {factor:g}x [{variant['name']}] ==")
    f9 = os.path.join(workdir, f"{name}_{variant['name']}_final_9x16.mp4")
    f1 = os.path.join(workdir, f"{name}_{variant['name']}_final_1x1.mp4")
    accel.accelerate(cap9, f9, factor)
    accel.accelerate(cap1, f1, factor)
    exp = ffutil.duration(cap9) / factor
    d = ffutil.duration(f9)
    gates.check(
        "accelerated", abs(d - exp) <= ACCEL_TOL,
        f"final {d:.2f}s ~= captioned/{factor:g} ({exp:.2f}s)",
        {"final_dur": round(d, 2), "expected": round(exp, 2),
         "factor": factor})
    return f9, f1


def _g6_audit(gates, variant, f9, timing, expected, ref_dur, cfg):
    print(f"== G6 final audit [{variant['name']}] ==")
    resid = [d for d in ffutil.big_silences(f9, cfg.audio.sil_db,
                                            BIG_SIL_GATE)
             if d > BIG_SIL_GATE]
    gates.check(
        "final_no_big_silence", not resid,
        "0 big silences in the final" if not resid else
        f"{len(resid)} big silence(s) in the FINAL video: {resid}. The "
        "cleaned voice regressed somewhere in the pipeline -- rebuild.",
        {"residual_big": resid})
    lets = len(timing.get("letterings") or [])
    gates.check("final_lettering_scenes", lets == expected,
                f"{lets} lettering scene(s) in the final (expected {expected})",
                {"lettering_scenes": lets, "expected": expected})
    d = ffutil.duration(f9)
    if ref_dur is not None:
        gates.check(
            "variant_duration_consistent", abs(d - ref_dur) <= VARIANT_DUR_TOL,
            f"{d:.2f}s ~= first variant {ref_dur:.2f}s"
            if abs(d - ref_dur) <= VARIANT_DUR_TOL else
            f"variant '{variant['name']}' final is {d:.2f}s but the first "
            f"variant is {ref_dur:.2f}s (tolerance {VARIANT_DUR_TOL}s). "
            "Variants of the same ad share one voice track and must land on "
            "the same duration -- inspect this variant's timing.",
            {"dur": round(d, 2), "ref": round(ref_dur, 2)})
    return d


def _g7_drive(gates, name, results, cfg):
    print("== G7 Drive delivery ==")
    items = []
    for r in results:
        for fmt, path in (("9x16", r["final_9x16"]), ("1x1", r["final_1x1"])):
            items.append((path, f"{name}_{r['name']}_{fmt}.mp4"))
    out = drive.push(cfg.drive_folder, items)
    confirmed = sum(1 for r in out["results"] if r.get("verified"))
    gates.check(
        "drive_upload", out["all_ok"],
        f"{confirmed}/{len(items)} finals confirmed in the folder -> "
        f"{out['folder_link']}" if out["all_ok"] else
        f"only {confirmed}/{len(items)} finals confirmed in the Drive "
        "folder. Check GOOGLE_OAUTH_TOKEN_FILE and that the folder is "
        "writable by your account, then rebuild (uploads are idempotent).",
        {"folder_link": out["folder_link"], "confirmed": confirmed})
    return out


# -------------------------------------------------------------------- build

def _build_variant(gates, project, variant, clean, clean_dur, inserts_map,
                   cfg, expected, ref_dur):
    """Run G2..G6 for ONE avatar variant (variants run sequentially)."""
    print(f"\n########## VARIANT: {variant['name']} ##########")
    wd_v = os.path.join(cfg.workdir, variant["name"])
    os.makedirs(wd_v, exist_ok=True)
    # Per-variant config: own avatar id and own workdir, so timing/alignment
    # files never collide between variants (no global state, no lock).
    cfg_v = dataclasses.replace(cfg, avatar_id=variant["avatar_id"],
                                workdir=wd_v)
    avatar = _g2_avatar(gates, variant, clean, clean_dur, cfg_v)
    pip, timing = _g3_montage(gates, project, variant, avatar, inserts_map,
                              cfg_v, expected)
    cap9, cap1 = _g4_captions(gates, project, variant, pip, timing, cfg_v)
    f9, f1 = _g5_accelerate(gates, project["name"], variant, cap9, cap1,
                            cfg, cfg.workdir)
    d = _g6_audit(gates, variant, f9, timing, expected, ref_dur, cfg)
    return {"name": variant["name"], "final_9x16": f9, "final_1x1": f1,
            "duration_s": round(d, 2)}


def build(config_path):
    """Run the full gated pipeline described by ``config_path``.

    Returns the manifest dict (also written to
    ``<workdir>/<name>_manifest.json``). Raises :class:`GateFail` on the
    FIRST failing gate, with a message that says what broke and how to fix it.
    """
    cfg, project, variants = _load_build_file(config_path)
    base_dir = os.path.dirname(os.path.abspath(config_path))
    for key in ("raw_voice", "script", "inserts"):
        if project.get(key):
            project[key] = _resolve(base_dir, project[key])
    cfg = dataclasses.replace(cfg, workdir=_resolve(base_dir, cfg.workdir))

    name = project["name"]
    print(f"===== BUILD: {name} ({len(variants)} variant/s) =====")
    gates = _GateLog()

    _g0_preflight(gates, project, variants)
    clean, clean_dur = _g1_audio(gates, project, cfg)

    inserts_map = _load_inserts(project.get("inserts"))
    expected = project.get("expected_lettering_scenes")
    if expected is None:
        expected = count_lettering_scenes(project["script"])
    expected = int(expected)

    results, ref_dur = [], None
    for variant in variants:  # SEQUENTIAL on purpose (predictable, auditable)
        r = _build_variant(gates, project, variant, clean, clean_dur,
                           inserts_map, cfg, expected, ref_dur)
        if ref_dur is None:
            ref_dur = r["duration_s"]
        results.append(r)

    drive_out = _g7_drive(gates, name, results, cfg) if cfg.drive_folder \
        else None

    manifest = {
        "name": name,
        "variants": results,
        "gates": gates.entries,
        "drive": ({"folder_link": drive_out["folder_link"],
                   "files": [{"name": r["name"],
                              "ok": bool(r["ok"] and r.get("verified")),
                              "link": r.get("link")}
                             for r in drive_out["results"]]}
                  if drive_out else None),
        "all_pass": all(g["ok"] for g in gates.entries),
    }
    mpath = os.path.join(cfg.workdir, f"{name}_manifest.json")
    with open(mpath, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    print(f"\n===== MANIFEST: {mpath} | all_pass={manifest['all_pass']} =====")
    for r in results:
        print(f"  {r['name']}: {r['duration_s']}s -> "
              f"{os.path.basename(r['final_9x16'])}")
    return manifest


# ---------------------------------------------------------------------- CLI

def main(argv=None):
    """CLI entry point: ``python3 -m vam.build <build.yaml>``. Exits 1 on GateFail."""
    args = sys.argv[1:] if argv is None else list(argv)
    if not args:
        print("usage: python3 -m vam.build <build.yaml>\n\n"
              "See the vam.build module docstring for the build file schema.",
              file=sys.stderr)
        return 2
    try:
        build(args[0])
    except GateFail as e:
        print(f"\n*** BUILD BLOCKED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
