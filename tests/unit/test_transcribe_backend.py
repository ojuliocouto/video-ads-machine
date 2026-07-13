"""Tests for the parakeet-mlx token parsing and backend dispatch."""
import os
from unittest import mock

from vam.montage import _parse_parakeet_json, transcribe_words


def test_parse_parakeet_merges_subword_tokens():
    data = {"result": {"tokens": [
        {"start": 0.0, "end": 0.2, "text": " uma"},
        {"start": 0.2, "end": 0.4, "text": " ski"},
        {"start": 0.4, "end": 0.5, "text": "ll"},
        {"start": 0.6, "end": 0.9, "text": " de"},
    ]}}
    words = _parse_parakeet_json(data)
    assert words == [(0.0, 0.2, "uma"), (0.2, 0.5, "skill"), (0.6, 0.9, "de")]


def test_parse_parakeet_nested_and_unsorted():
    data = [{"a": {"tokens": [{"start": 1.0, "end": 1.2, "text": " b"}]}},
            {"tokens": [{"start": 0.0, "end": 0.3, "text": " a"}]}]
    words = _parse_parakeet_json(data)
    assert [w for _, _, w in words] == ["a", "b"]


def test_backend_env_whisper_skips_parakeet(monkeypatch):
    monkeypatch.setenv("VAM_TRANSCRIBE_BACKEND", "whisper")
    with mock.patch("vam.montage._transcribe_parakeet") as pk:
        try:
            transcribe_words("/nonexistent.wav")
        except RuntimeError:
            pass  # faster-whisper likely absent in CI; either way:
        except Exception:
            pass
        pk.assert_not_called()


def test_backend_auto_uses_parakeet_when_available(monkeypatch):
    monkeypatch.setenv("VAM_TRANSCRIBE_BACKEND", "auto")
    with mock.patch("shutil.which", return_value="/usr/local/bin/parakeet-mlx"), \
         mock.patch("vam.montage._transcribe_parakeet",
                    return_value=[(0.0, 0.1, "ok")]) as pk:
        assert transcribe_words("/x.wav") == [(0.0, 0.1, "ok")]
        pk.assert_called_once()
