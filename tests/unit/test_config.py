"""Config loader tests: validated defaults, friendly validation, partial YAML."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from vam import config  # noqa: E402
from vam.config import Config, ConfigError, load  # noqa: E402


def _write(tmp_path, text, name="config.yaml"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


MINIMAL = 'avatar_id: "YOUR_AVATAR_ID"\n'


# ---------------------------------------------------------------- defaults

def test_minimal_config_gets_validated_defaults(tmp_path):
    cfg = load(_write(tmp_path, MINIMAL))
    assert isinstance(cfg, Config)
    assert cfg.avatar_id == "YOUR_AVATAR_ID"
    # brand
    assert cfg.brand.key_color_bgr == "4AA6FF"
    assert cfg.brand.logo_path is None
    # lettering (validated positions)
    assert cfg.lettering.style == "foil"
    assert cfg.lettering.y_key == 1690
    assert cfg.lettering.y_key_with_logo == 1500
    # audio hygiene thresholds (validated)
    assert cfg.audio.big_sil == pytest.approx(0.55)
    assert cfg.audio.keep_pause == pytest.approx(0.26)
    assert cfg.audio.sil_db == -30
    # pipeline
    assert cfg.accelerate == pytest.approx(1.2)
    assert cfg.drive_folder is None
    assert cfg.language == "pt"
    assert cfg.workdir == "./build"
    assert os.path.isdir(cfg.fonts_dir)


def test_fonts_dir_default_contains_bundled_fonts(tmp_path):
    cfg = load(_write(tmp_path, MINIMAL))
    names = os.listdir(cfg.fonts_dir)
    assert any(n.endswith(".ttf") for n in names)


# ---------------------------------------------------------------- overrides

def test_partial_yaml_overrides_merge_with_defaults(tmp_path):
    cfg = load(_write(tmp_path, (
        "avatar_id: abc123\n"
        "brand:\n"
        "  key_color_bgr: '00FF88'\n"
        "lettering:\n"
        "  style: solid\n"
        "audio:\n"
        "  big_sil: 0.7\n"
        "accelerate: 1.35\n"
        "language: en\n"
    )))
    assert cfg.avatar_id == "abc123"
    assert cfg.brand.key_color_bgr == "00FF88"
    assert cfg.brand.logo_path is None            # untouched default
    assert cfg.lettering.style == "solid"
    assert cfg.lettering.y_key == 1690            # untouched default
    assert cfg.audio.big_sil == pytest.approx(0.7)
    assert cfg.audio.keep_pause == pytest.approx(0.26)
    assert cfg.accelerate == pytest.approx(1.35)
    assert cfg.language == "en"


def test_full_yaml_all_fields(tmp_path):
    cfg = load(_write(tmp_path, (
        "avatar_id: abc123\n"
        "brand:\n"
        "  key_color_bgr: 'FA4E04'\n"
        "  logo_path: ./assets/logo.png\n"
        "lettering:\n"
        "  style: foil\n"
        "  y_key: 1600\n"
        "  y_key_with_logo: 1400\n"
        "audio:\n"
        "  big_sil: 0.6\n"
        "  keep_pause: 0.3\n"
        "  sil_db: -35\n"
        "accelerate: 1.1\n"
        "drive_folder: https://drive.google.com/drive/folders/FOLDER_ID\n"
        "fonts_dir: ./myfonts\n"
        "language: es\n"
        "workdir: ./out\n"
    )))
    assert cfg.brand.logo_path == "./assets/logo.png"
    assert cfg.lettering.y_key == 1600
    assert cfg.lettering.y_key_with_logo == 1400
    assert cfg.audio.sil_db == -35
    assert cfg.drive_folder.endswith("FOLDER_ID")
    assert cfg.fonts_dir == "./myfonts"
    assert cfg.workdir == "./out"


def test_int_accelerate_is_coerced_to_float(tmp_path):
    cfg = load(_write(tmp_path, MINIMAL + "accelerate: 2\n"))
    assert isinstance(cfg.accelerate, float) and cfg.accelerate == 2.0


# ---------------------------------------------------------------- validation

def test_missing_avatar_id_is_a_friendly_error(tmp_path):
    with pytest.raises(ConfigError) as e:
        load(_write(tmp_path, "language: pt\n"))
    msg = str(e.value)
    assert "avatar_id" in msg
    assert "heygen" in msg.lower()  # tells the user where to get it


def test_missing_file_is_a_friendly_error(tmp_path):
    with pytest.raises(ConfigError) as e:
        load(str(tmp_path / "nope.yaml"))
    assert "nope.yaml" in str(e.value)
    assert "config.example.yaml" in str(e.value)


def test_invalid_lettering_style_lists_valid_options(tmp_path):
    with pytest.raises(ConfigError) as e:
        load(_write(tmp_path, MINIMAL + "lettering:\n  style: neon\n"))
    msg = str(e.value)
    assert "neon" in msg and "foil" in msg and "solid" in msg


def test_invalid_key_color_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load(_write(tmp_path, MINIMAL + "brand:\n  key_color_bgr: 'blue'\n"))
    assert "key_color_bgr" in str(e.value)


def test_key_color_accepts_leading_hash_and_normalizes(tmp_path):
    cfg = load(_write(tmp_path, MINIMAL + "brand:\n  key_color_bgr: '#4aa6ff'\n"))
    assert cfg.brand.key_color_bgr == "4AA6FF"


def test_nonpositive_accelerate_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load(_write(tmp_path, MINIMAL + "accelerate: 0\n"))
    assert "accelerate" in str(e.value)


def test_unknown_top_level_key_is_reported(tmp_path):
    with pytest.raises(ConfigError) as e:
        load(_write(tmp_path, MINIMAL + "avatr_id_typo: x\n"))
    assert "avatr_id_typo" in str(e.value)


def test_unknown_nested_key_is_reported(tmp_path):
    with pytest.raises(ConfigError) as e:
        load(_write(tmp_path, MINIMAL + "audio:\n  big_silence: 0.5\n"))
    assert "big_silence" in str(e.value)


def test_non_mapping_yaml_rejected(tmp_path):
    with pytest.raises(ConfigError):
        load(_write(tmp_path, "- just\n- a list\n"))


def test_example_config_in_repo_loads(tmp_path):
    example = os.path.join(os.path.dirname(__file__), "..", "..",
                           "config.example.yaml")
    cfg = load(example)
    assert cfg.lettering.style == "foil"
    assert cfg.accelerate == pytest.approx(1.2)


def test_module_still_exposes_load():
    assert callable(config.load)
