"""Onboarding doctor: check the environment and the user's accounts BEFORE a build.

``vam doctor`` runs every check a first-time user trips on and, for each one,
prints [OK]/[WARN]/[FAIL] plus a concrete fix. The goal is that a non-technical
user can go from a fresh machine to a green doctor without outside help.

Checks:
  * python deps         pyyaml importable (the package was installed correctly)
  * ffmpeg              present AND functional: a tiny real render through the
                        ``subtitles`` filter proves libass is compiled in and no
                        shared library is broken (the classic macOS ``dyld:
                        Library not loaded`` after a Homebrew upgrade)
  * ffprobe             present (duration probing)
  * fonts               bundled fonts/ directory has the .ttf files
  * caption alignment   a word-alignment backend is available (WARN only)
  * HEYGEN_API_KEY      set AND accepted by the API; reports the remaining API
                        credit, which is SEPARATE from the HeyGen plan credit
  * avatar_id           exists in the user's HeyGen account; warns when the
                        avatar look appears to be landscape (the pipeline
                        renders 9:16 vertical; the preview aspect is a gotcha)
  * Drive token         GOOGLE_OAUTH_TOKEN_FILE is a usable OAuth token file,
                        checked only when ``drive_folder`` is configured

Exit code: 0 when nothing FAILed (WARNs allowed), 1 otherwise.
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass

from . import heygen
from .config import _DEFAULT_FONTS_DIR

AVATARS_URL = "https://api.heygen.com/v2/avatars"

# Smallest valid ASS file: enough to force libass to load and shape one glyph.
_PROBE_ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 64
PlayResY: 64

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, Alignment
Style: Default,Arial,20,&H00FFFFFF,2

[Events]
Format: Layer, Start, End, Style, Text
Dialogue: 0,0:00:00.00,0:00:00.20,Default,doctor
"""

_FFMPEG_INSTALL = ("macOS: brew install ffmpeg | Debian/Ubuntu: sudo apt install "
                   "ffmpeg | Windows: choco install ffmpeg (or winget install ffmpeg)")


@dataclass
class CheckResult:
    """One doctor check: a status plus a human fix when it is not OK."""
    name: str
    status: str  # "OK" | "WARN" | "FAIL"
    detail: str = ""
    fix: str = ""


def _importable(name):
    try:
        __import__(name)
        return True
    except Exception:
        return False


# --------------------------------------------------------------- environment

def check_python_deps():
    """The package's own Python dependencies (pyyaml is the load-bearing one)."""
    if not _importable("yaml"):
        return CheckResult(
            "python deps", "FAIL",
            "the 'pyyaml' package is not importable in this Python",
            "Run: pip install -e .  (from the repo root), or: pip install pyyaml")
    return CheckResult("python deps", "OK", "pyyaml importable")


def check_ffmpeg():
    """ffmpeg present AND able to render through the subtitles (libass) filter.

    ``ffmpeg -version`` succeeding is not enough: a build without libass, or a
    binary whose shared libraries were removed by a package upgrade (macOS
    ``dyld: Library not loaded``), still passes -version style checks and then
    explodes mid-pipeline. So we run a real 1-frame render with the
    ``subtitles`` filter on a synthetic input.
    """
    if not shutil.which("ffmpeg"):
        return CheckResult(
            "ffmpeg", "FAIL", "ffmpeg not found on PATH", _FFMPEG_INSTALL)
    with tempfile.TemporaryDirectory() as td:
        ass_path = os.path.join(td, "probe.ass")
        with open(ass_path, "w", encoding="utf-8") as fh:
            fh.write(_PROBE_ASS)
        # Escape for the filter graph parser (Windows drive colon, backslashes).
        escaped = ass_path.replace("\\", "/").replace(":", r"\:")
        cmd = ["ffmpeg", "-v", "error", "-y",
               "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.2:r=10",
               "-vf", f"subtitles={escaped}",
               "-frames:v", "1", "-f", "null", "-"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return CheckResult(
                "ffmpeg", "FAIL", f"ffmpeg could not be executed: {exc}",
                "Reinstall ffmpeg. " + _FFMPEG_INSTALL)
    if proc.returncode == 0:
        return CheckResult(
            "ffmpeg", "OK", "functional (1-frame render through the "
            "subtitles/libass filter passed)")
    err = (proc.stderr or "") + (proc.stdout or "")
    if "dyld" in err or "Library not loaded" in err:
        return CheckResult(
            "ffmpeg", "FAIL",
            "ffmpeg is installed but a shared library it links against is "
            "missing (dyld 'Library not loaded'). This usually happens after "
            "a package-manager upgrade removed an old library version.",
            "Reinstall ffmpeg so it links against the current libraries: "
            "macOS: brew reinstall ffmpeg | Linux: reinstall the ffmpeg package")
    if "No such filter" in err or "libass" in err.lower():
        return CheckResult(
            "ffmpeg", "FAIL",
            "this ffmpeg build cannot use the subtitles filter (compiled "
            "without libass), so captions cannot be burned",
            "Install a full ffmpeg build (not a minimal/static one). " + _FFMPEG_INSTALL)
    return CheckResult(
        "ffmpeg", "FAIL",
        "test render failed: " + err.strip()[-400:],
        "Reinstall ffmpeg. " + _FFMPEG_INSTALL)


def check_ffprobe():
    if shutil.which("ffprobe"):
        return CheckResult("ffprobe", "OK", "found on PATH")
    return CheckResult(
        "ffprobe", "FAIL",
        "ffprobe not found on PATH (it normally ships together with ffmpeg)",
        "Install ffmpeg (ffprobe comes with it). " + _FFMPEG_INSTALL)


def check_fonts(fonts_dir=None):
    fonts_dir = fonts_dir or _DEFAULT_FONTS_DIR
    if os.path.isdir(fonts_dir):
        ttfs = [f for f in os.listdir(fonts_dir)
                if f.lower().endswith((".ttf", ".otf"))]
        if ttfs:
            return CheckResult(
                "fonts", "OK", f"{len(ttfs)} font file(s) in {fonts_dir}")
    return CheckResult(
        "fonts", "FAIL",
        f"no .ttf/.otf font files found in {fonts_dir}",
        "The repo ships its fonts in fonts/ at the repo root. Re-clone the "
        "repository (or restore the fonts/ directory), or point 'fonts_dir' "
        "in config.yaml to a directory that has the fonts.")


def check_alignment():
    """A word-alignment backend for verbatim captions (WARN only: optional)."""
    is_mac_arm = platform.system() == "Darwin" and platform.machine() == "arm64"
    pk_bin = shutil.which("parakeet-mlx") or os.path.expanduser(
        "~/.local/bin/parakeet-mlx")
    if is_mac_arm and (_importable("parakeet_mlx") or os.path.exists(pk_bin)):
        # Presence is not enough: a stale install (removed venv) leaves a
        # broken launcher behind ("bad interpreter"). Actually run it.
        try:
            probe = subprocess.run([pk_bin, "--help"], capture_output=True,
                                   text=True, timeout=30)
            if probe.returncode == 0:
                return CheckResult(
                    "caption alignment", "OK", "parakeet-mlx (Apple Silicon)")
            detail = (probe.stderr or probe.stdout or "").strip()[:160]
        except Exception as exc:
            detail = str(exc)[:160]
        return CheckResult(
            "caption alignment", "FAIL",
            f"parakeet-mlx is installed but does not run: {detail}",
            "Reinstall it: pip install --force-reinstall parakeet-mlx "
            "(or, if you use uv: uv tool install --force parakeet-mlx). "
            "Alternatively install the portable backend: "
            "pip install 'faster-whisper>=1.0'")
    if _importable("faster_whisper"):
        return CheckResult("caption alignment", "OK", "faster-whisper")
    hint = ("pip install parakeet-mlx  (Apple Silicon)" if is_mac_arm
            else "pip install 'faster-whisper>=1.0'  (or: pip install '.[whisper]')")
    return CheckResult(
        "caption alignment", "WARN",
        "no word-alignment backend found (needed to time the verbatim captions)",
        hint)


# ------------------------------------------------------------------ accounts

def check_heygen_key():
    """HEYGEN_API_KEY set AND accepted; report the remaining API credit.

    HeyGen API credits are SEPARATE from the plan credits: a paid plan with
    plenty of credits can still have 0 API credits, and then every render
    fails. The doctor surfaces that before the user records anything.
    """
    key = os.environ.get("HEYGEN_API_KEY", "").strip()
    if not key:
        return CheckResult(
            "HEYGEN_API_KEY", "FAIL",
            "the HEYGEN_API_KEY environment variable is not set",
            "Get your key at app.heygen.com > Space Settings > API, then put "
            "HEYGEN_API_KEY=<your key> in your .env file (or export it).")
    try:
        resp = heygen._req(
            heygen.QUOTA_URL,
            headers={"X-Api-Key": key, "Accept": "application/json"})
    except heygen.HeyGenError as exc:
        return CheckResult(
            "HEYGEN_API_KEY", "FAIL",
            f"could not validate the key against the HeyGen API: {exc}",
            "Check your internet connection and that the key was copied whole "
            "(no spaces or line breaks).")
    data = resp.get("data") if isinstance(resp, dict) else None
    if not isinstance(data, dict) or "remaining_quota" not in data:
        msg = ""
        if isinstance(resp, dict):
            msg = str(resp.get("message") or resp.get("error") or resp)[:200]
        return CheckResult(
            "HEYGEN_API_KEY", "FAIL",
            f"HeyGen rejected the key: {msg}",
            "Generate a fresh API key at app.heygen.com > Space Settings > API "
            "and update your .env. Make sure it is an API key, not a login token.")
    quota = data.get("remaining_quota")
    note = ("note: API credits are SEPARATE from your HeyGen plan credits; "
            "both live in the HeyGen dashboard but are billed independently")
    if quota is not None and quota <= 0:
        return CheckResult(
            "HEYGEN_API_KEY", "WARN",
            f"key is valid but the remaining API credit is {quota}: renders "
            f"will fail until you add API credit ({note})",
            "Add API credits at app.heygen.com > Space Settings > API / "
            "Subscriptions > API plan. Plan credits do NOT count as API credits.")
    return CheckResult(
        "HEYGEN_API_KEY", "OK",
        f"key valid; remaining API credit: {quota} ({note})")


def _looks_landscape(entry):
    """Heuristic: does this avatar look appear to be landscape?

    The HeyGen avatar list does not expose an explicit orientation field, so we
    read what is available: preview width/height when present, or a telltale
    'landscape' marker in the preview asset URLs. Only ever used for a WARN.
    """
    width = entry.get("preview_width") or entry.get("width")
    height = entry.get("preview_height") or entry.get("height")
    try:
        if width and height and float(width) > float(height):
            return True
    except (TypeError, ValueError):
        pass
    for key in ("preview_image_url", "preview_video_url"):
        if "landscape" in str(entry.get(key) or "").lower():
            return True
    return False


def check_avatar(avatar_id):
    """The configured avatar_id must exist in the account behind HEYGEN_API_KEY."""
    key = os.environ.get("HEYGEN_API_KEY", "").strip()
    if not key:
        return CheckResult(
            "avatar_id", "WARN",
            "skipped: HEYGEN_API_KEY is not set, so the avatar cannot be verified",
            "Fix the HEYGEN_API_KEY check first, then run `vam doctor` again.")
    try:
        resp = heygen._req(
            AVATARS_URL, headers={"X-Api-Key": key, "Accept": "application/json"})
    except heygen.HeyGenError as exc:
        return CheckResult(
            "avatar_id", "FAIL",
            f"could not list the account's avatars: {exc}",
            "Check your internet connection and the HEYGEN_API_KEY, then retry.")
    avatars = []
    if isinstance(resp, dict):
        avatars = (resp.get("data") or {}).get("avatars") or []
    entry = next(
        (a for a in avatars if a.get("avatar_id") == avatar_id), None)
    if entry is None:
        return CheckResult(
            "avatar_id", "FAIL",
            f"avatar_id '{avatar_id}' was not found in this HeyGen account "
            f"({len(avatars)} avatar look(s) visible to this API key)",
            "Open app.heygen.com > Avatars, open YOUR avatar and copy its id "
            "into config.yaml (avatar_id). The id must belong to the same "
            "account as the HEYGEN_API_KEY you configured.")
    if _looks_landscape(entry):
        return CheckResult(
            "avatar_id", "WARN",
            "avatar found, but its preview looks LANDSCAPE while this pipeline "
            "renders 9:16 vertical video",
            "The preview aspect can be misleading (known gotcha), but double-"
            "check in HeyGen that this avatar look supports portrait/9:16 "
            "before burning credits on a long render.")
    return CheckResult(
        "avatar_id", "OK",
        f"avatar '{entry.get('avatar_name') or avatar_id}' found in your account")


def check_drive(drive_folder):
    """GOOGLE_OAUTH_TOKEN_FILE must be usable when drive_folder is configured."""
    if not drive_folder:
        return CheckResult(
            "drive", "OK",
            "Drive upload disabled (no 'drive_folder' in config): nothing to check")
    path = os.environ.get("GOOGLE_OAUTH_TOKEN_FILE", "").strip()
    fix = ("Point the GOOGLE_OAUTH_TOKEN_FILE environment variable to a JSON "
           "file with your Google OAuth credentials: {access_token, "
           "refresh_token, client_id, client_secret}. See docs/accounts.md "
           "for how to create it, or remove 'drive_folder' from config.yaml "
           "to skip Drive upload.")
    if not path:
        return CheckResult(
            "drive", "FAIL",
            "'drive_folder' is set but GOOGLE_OAUTH_TOKEN_FILE is not", fix)
    if not os.path.exists(path):
        return CheckResult(
            "drive", "FAIL",
            f"GOOGLE_OAUTH_TOKEN_FILE points to a missing file: {path}", fix)
    try:
        with open(path, encoding="utf-8") as fh:
            tokens = json.load(fh)
    except (ValueError, OSError) as exc:
        return CheckResult(
            "drive", "FAIL",
            f"token file is not valid JSON ({exc})", fix)
    if not isinstance(tokens, dict):
        return CheckResult(
            "drive", "FAIL", "token file must contain a JSON object", fix)
    refreshable = all(tokens.get(k) for k in
                      ("refresh_token", "client_id", "client_secret"))
    if not tokens.get("access_token") and not refreshable:
        return CheckResult(
            "drive", "FAIL",
            "token file has neither an access_token nor the trio "
            "refresh_token + client_id + client_secret", fix)
    return CheckResult("drive", "OK", f"OAuth token file usable ({path})")


# ------------------------------------------------------------------- runner

def run_checks(config_path=None):
    """Run every check; config-dependent ones only when a config is loadable."""
    results = [check_python_deps(), check_ffmpeg(), check_ffprobe()]

    cfg = None
    path = config_path
    if path is None and os.path.exists("config.yaml"):
        path = "config.yaml"
    if path:
        try:
            # Build files carry extra sections ('project', 'avatars') on top
            # of the pipeline config; validate through the same loader the
            # build uses so doctor and build never disagree.
            from .build import _load_build_file
            try:
                cfg, _project, _variants = _load_build_file(path)
            except Exception:
                from .config import load as load_config
                cfg = load_config(path)
        except Exception as exc:  # ConfigError or anything else the file causes
            results.append(CheckResult(
                "config", "FAIL", str(exc),
                "Fix the config file (compare it with config.example.yaml)."))

    results.append(check_fonts(cfg.fonts_dir if cfg else None))
    results.append(check_alignment())
    results.append(check_heygen_key())

    if cfg:
        results.append(check_avatar(cfg.avatar_id))
        results.append(check_drive(cfg.drive_folder))
    elif not path:
        results.append(CheckResult(
            "config", "WARN",
            "no config.yaml found: skipped the avatar_id and Drive checks",
            "Copy config.example.yaml to config.yaml, set your avatar_id, "
            "then run `vam doctor` again (or `vam doctor --config <file>`)."))
    return results


def run(config_path=None):
    """Print the doctor report; return 0 when nothing FAILed, else 1."""
    print("vam doctor: environment and account checks\n")
    results = run_checks(config_path)
    for r in results:
        line = f"[{r.status}] {r.name}"
        if r.detail:
            line += f": {r.detail}"
        print(line)
        if r.fix and r.status != "OK":
            print(f"       fix: {r.fix}")
    failed = [r for r in results if r.status == "FAIL"]
    print()
    if failed:
        print(f"{len(failed)} check(s) FAILED. Apply the fixes above and run "
              "`vam doctor` again.")
        return 1
    print("All required checks passed. You are ready: run "
          "`vam build config.yaml`.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
