#!/usr/bin/env python3
"""Carrega config.yaml + .env. Tudo que e especifico de marca/avatar/chaves vive aqui,
nunca no codigo."""
import os

try:
    import yaml
except ImportError:
    yaml = None

DEFAULTS = {
    "brand": {
        "primary_color": "#FA4E04",
        "lettering_color": "#DE7A5C",
        "caption_font": "Nunito",
        "lettering_font_lead": "PlayfairDisplay",
        "lettering_font_key": "DMSerifDisplay",
    },
    "avatar": {"provider": "heygen", "avatar_id": ""},
    "voice": {"mode": "real"},
    "captions": {"preset": "tay"},
    "lettering": {"style": "serif_glow"},
    "music": {"file": "", "volume": 0.10, "ducking": True},
    "formats": ["9x16", "1x1"],
    "speed": 1.2,
    "output_dir": "output",
}


def _load_env(path=".env"):
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _deep_merge(base, over):
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def load(config_path="config.yaml", env_path=".env"):
    _load_env(env_path)
    import copy
    cfg = copy.deepcopy(DEFAULTS)
    if os.path.exists(config_path):
        if yaml is None:
            raise RuntimeError("pyyaml nao instalado: pip install pyyaml")
        _deep_merge(cfg, yaml.safe_load(open(config_path)) or {})
    cfg["_secrets"] = {
        "heygen_api_key": os.environ.get("HEYGEN_API_KEY", ""),
    }
    return cfg
