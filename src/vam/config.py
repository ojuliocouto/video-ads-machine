"""Configuration loader for the video-ads-machine pipeline.

Everything that is brand/account specific (avatar id, colors, logo, Drive
folder, speed factor) lives in a user-owned YAML file, never in code.
Secrets (API keys) live in environment variables / .env, never in YAML.

Usage:
    from vam.config import load
    cfg = load("config.yaml")
    cfg.avatar_id, cfg.brand.key_color_bgr, cfg.audio.big_sil, ...

All defaults below are the production-validated numbers of the original
engine; only `avatar_id` is mandatory.
"""
import copy
import os
import re
from dataclasses import dataclass, field
from typing import Optional

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only without pyyaml
    yaml = None

# Fonts bundled with the repo (fonts/ at repo root, next to src/).
_DEFAULT_FONTS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "fonts"))

LETTERING_STYLES = ("foil", "solid")

_HEX_COLOR = re.compile(r"^#?[0-9a-fA-F]{6}$")


class ConfigError(Exception):
    """Raised when the config file is missing or invalid.

    Messages are written for end users: they say what is wrong and how
    to fix it, not just where the parser choked.
    """


@dataclass
class BrandConfig:
    """Brand look: lettering key color and optional logo overlay."""
    # Color of the highlighted "key" word in letterings, in ASS BGR hex
    # (BBGGRR). '4AA6FF' is just the shipped example; set your brand color.
    key_color_bgr: str = "4AA6FF"
    # Path to a PNG logo (transparent background) overlaid on logo blocks.
    logo_path: Optional[str] = None


@dataclass
class LetteringConfig:
    """On-screen lettering (big serif text blocks) settings."""
    style: str = "foil"          # 'foil' (metallic gradient) or 'solid'
    y_key: int = 1690            # baseline Y of the key line (9:16 canvas)
    y_key_with_logo: int = 1500  # key line Y when a logo block is above it


@dataclass
class AudioConfig:
    """Voice-track hygiene thresholds (silence trimming)."""
    big_sil: float = 0.55    # silences longer than this get shortened (s)
    keep_pause: float = 0.26  # natural pause left in place of each cut (s)
    sil_db: int = -30         # silence threshold in dBFS (breaths sit below)


@dataclass
class Config:
    """Fully resolved pipeline configuration."""
    avatar_id: str
    brand: BrandConfig = field(default_factory=BrandConfig)
    lettering: LetteringConfig = field(default_factory=LetteringConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    accelerate: float = 1.2          # final speed-up factor (pitch preserved)
    drive_folder: Optional[str] = None  # Google Drive folder URL or id
    fonts_dir: str = _DEFAULT_FONTS_DIR
    language: str = "pt"             # caption/lettering language hint
    workdir: str = "./build"         # intermediate artifacts directory


def _load_env(path: str = ".env") -> None:
    """Populate os.environ from a simple KEY=VALUE .env file (if present)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _check_keys(section: str, data: dict, allowed) -> None:
    unknown = [k for k in data if k not in allowed]
    if unknown:
        where = f"'{section}'" if section else "the top level"
        raise ConfigError(
            f"Unknown key(s) {unknown} under {where} of the config file. "
            f"Valid keys here: {sorted(allowed)}. "
            "Check config.example.yaml for the full schema.")


def _section(data: dict, name: str) -> dict:
    val = data.get(name) or {}
    if not isinstance(val, dict):
        raise ConfigError(
            f"'{name}' must be a mapping (key: value lines), "
            f"got {type(val).__name__}. See config.example.yaml.")
    return val


def _normalize_color(value, key: str) -> str:
    value = str(value)
    if not _HEX_COLOR.match(value):
        raise ConfigError(
            f"'{key}' must be a 6-digit hex color in BGR order "
            f"(e.g. '4AA6FF'), got '{value}'. Note: ASS subtitles use "
            "BGR (blue-green-red), not RGB.")
    return value.lstrip("#").upper()


def load(config_path: str = "config.yaml", env_path: str = ".env") -> Config:
    """Load and validate a YAML config file, returning a Config object.

    Every field has a validated default except `avatar_id`, which the
    user must set to their own HeyGen avatar.
    """
    _load_env(env_path)

    if yaml is None:
        raise ConfigError(
            "The 'pyyaml' package is not installed. "
            "Install it with: pip install pyyaml")
    if not os.path.exists(config_path):
        raise ConfigError(
            f"Config file not found: {config_path}\n"
            "Copy config.example.yaml to config.yaml and fill in your "
            "avatar_id and brand settings.")

    with open(config_path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ConfigError(
            f"{config_path} must contain a YAML mapping (key: value), "
            f"got {type(raw).__name__}. See config.example.yaml.")
    return from_dict(raw)


def from_dict(raw: dict) -> Config:
    """Validate an already-parsed mapping and return a Config.

    Used by :func:`load` and by ``vam.build``, whose build file embeds the
    pipeline configuration alongside its own build-only sections.
    """
    if not isinstance(raw, dict):
        raise ConfigError(
            f"Config data must be a mapping (key: value), "
            f"got {type(raw).__name__}. See config.example.yaml.")
    raw = copy.deepcopy(raw)

    _check_keys("", raw, {
        "avatar_id", "brand", "lettering", "audio", "accelerate",
        "drive_folder", "fonts_dir", "language", "workdir"})

    # --- avatar_id (the only mandatory field) ---
    avatar_id = str(raw.get("avatar_id") or "").strip()
    if not avatar_id:
        raise ConfigError(
            "Missing 'avatar_id' in the config file. This is your HeyGen "
            "avatar id: open https://app.heygen.com, go to Avatars, open "
            "your avatar and copy its id (also visible via the "
            "GET /v2/avatars API). Then set:\n\n"
            "  avatar_id: \"YOUR_AVATAR_ID\"")

    # --- brand ---
    b = _section(raw, "brand")
    _check_keys("brand", b, {"key_color_bgr", "logo_path"})
    brand = BrandConfig()
    if "key_color_bgr" in b:
        brand.key_color_bgr = _normalize_color(
            b["key_color_bgr"], "brand.key_color_bgr")
    logo = b.get("logo_path")
    brand.logo_path = str(logo) if logo else None

    # --- lettering ---
    le = _section(raw, "lettering")
    _check_keys("lettering", le, {"style", "y_key", "y_key_with_logo"})
    lettering = LetteringConfig()
    if "style" in le:
        style = str(le["style"])
        if style not in LETTERING_STYLES:
            raise ConfigError(
                f"Unknown lettering.style '{style}'. "
                f"Valid styles: {', '.join(LETTERING_STYLES)} "
                "('foil' is the metallic-gradient default).")
        lettering.style = style
    for k in ("y_key", "y_key_with_logo"):
        if k in le:
            try:
                setattr(lettering, k, int(le[k]))
            except (TypeError, ValueError):
                raise ConfigError(
                    f"'lettering.{k}' must be an integer pixel Y position "
                    f"on the 1080x1920 canvas, got '{le[k]}'.")

    # --- audio ---
    au = _section(raw, "audio")
    _check_keys("audio", au, {"big_sil", "keep_pause", "sil_db"})
    audio = AudioConfig()
    for k, cast in (("big_sil", float), ("keep_pause", float),
                    ("sil_db", int)):
        if k in au:
            try:
                setattr(audio, k, cast(au[k]))
            except (TypeError, ValueError):
                raise ConfigError(
                    f"'audio.{k}' must be a number, got '{au[k]}'.")
    if audio.big_sil <= 0 or audio.keep_pause <= 0:
        raise ConfigError(
            "'audio.big_sil' and 'audio.keep_pause' must be positive "
            "durations in seconds (defaults: 0.55 and 0.26).")

    # --- scalars ---
    try:
        accelerate = float(raw.get("accelerate", 1.2))
    except (TypeError, ValueError):
        raise ConfigError(
            f"'accelerate' must be a number (e.g. 1.2), "
            f"got '{raw.get('accelerate')}'.")
    if accelerate <= 0:
        raise ConfigError(
            "'accelerate' must be > 0. Use 1.0 for no speed-up; "
            "the validated default is 1.2.")

    drive_folder = raw.get("drive_folder")
    drive_folder = str(drive_folder) if drive_folder else None

    fonts_dir = str(raw.get("fonts_dir") or _DEFAULT_FONTS_DIR)
    language = str(raw.get("language") or "pt")
    workdir = str(raw.get("workdir") or "./build")

    return Config(
        avatar_id=avatar_id, brand=brand, lettering=lettering, audio=audio,
        accelerate=accelerate, drive_folder=drive_folder,
        fonts_dir=fonts_dir, language=language, workdir=workdir)
