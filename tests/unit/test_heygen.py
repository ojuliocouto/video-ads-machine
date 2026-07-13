"""Tests for the HeyGen avatar generator: Avatar V engine lock + mocked HTTP flow."""
import json
import os
import sys
import types

import pytest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from vam import heygen  # noqa: E402


def make_cfg(avatar_id="YOUR_AVATAR_ID"):
    """Config per the interface contract: an object with an avatar_id attribute."""
    cfg = types.SimpleNamespace()
    cfg.avatar_id = avatar_id
    return cfg


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("HEYGEN_ENGINE_OVERRIDE", raising=False)
    monkeypatch.setenv("HEYGEN_API_KEY", "test-key")


# ---------------------------------------------------------------- engine lock

def test_resolve_engine_default_is_avatar_v():
    assert heygen.resolve_engine(None) == "avatar_v"
    assert heygen.resolve_engine("avatar_v") == "avatar_v"
    assert heygen.MANDATORY_ENGINE == "avatar_v"


def test_resolve_engine_blocks_other_engines():
    with pytest.raises(heygen.EngineBlockedError) as exc:
        heygen.resolve_engine("avatar_iii")
    msg = str(exc.value)
    assert "avatar_v" in msg
    assert "HEYGEN_ENGINE_OVERRIDE" in msg  # message must explain the escape hatch


def test_resolve_engine_override_releases_with_warning(monkeypatch):
    monkeypatch.setenv("HEYGEN_ENGINE_OVERRIDE", "avatar_iii")
    with pytest.warns(UserWarning):
        assert heygen.resolve_engine("avatar_iii") == "avatar_iii"


def test_resolve_engine_override_mismatch_still_blocks(monkeypatch):
    monkeypatch.setenv("HEYGEN_ENGINE_OVERRIDE", "something_else")
    with pytest.raises(heygen.EngineBlockedError):
        heygen.resolve_engine("avatar_iii")


def test_resolve_engine_override_ignored_when_nothing_requested(monkeypatch):
    monkeypatch.setenv("HEYGEN_ENGINE_OVERRIDE", "avatar_iii")
    with pytest.warns(UserWarning):
        assert heygen.resolve_engine(None) == "avatar_v"


# ------------------------------------------------------------- mocked HTTP flow

QUOTA_OK = {"error": None, "data": {"remaining_quota": 60}}
QUOTA_ZERO = {"error": None, "data": {"remaining_quota": 0}}
UPLOAD_OK = {"data": {"url": "https://resource.example.com/asset/abc"}}
SUBMIT_OK = {"data": {"video_id": "vid123"}}
STATUS_DONE = {"data": {"status": "completed",
                        "video_url": "https://files.example.com/vid123.mp4",
                        "duration": 12.3}}
STATUS_FAILED = {"data": {"status": "failed", "error": {"detail": "render blew up"}}}


def _router(responses):
    """Build a _req side effect that routes by URL substring and records calls."""
    calls = []

    def fake_req(url, data=None, headers=None, method=None):
        calls.append({"url": url, "data": data, "headers": headers, "method": method})
        for frag, resp in responses:
            if frag in url:
                return resp
        raise AssertionError("unexpected URL " + url)

    return fake_req, calls


def test_generate_avatar_happy_flow(tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"fake-mp3-bytes")
    out = str(tmp_path / "avatar.mp4")

    fake_req, calls = _router([
        ("remaining_quota", QUOTA_OK),
        ("upload.heygen.com", UPLOAD_OK),
        ("/v3/videos", SUBMIT_OK),
        ("video_status.get", STATUS_DONE),
    ])

    def fake_download(url, dst):
        assert url == "https://files.example.com/vid123.mp4"
        open(dst, "wb").write(b"video-bytes")

    with mock.patch.object(heygen, "_req", side_effect=fake_req), \
         mock.patch.object(heygen, "_download", side_effect=fake_download):
        result = heygen.generate_avatar(str(audio), out, make_cfg())

    assert result == out
    assert os.path.exists(out)

    # payload sent to /v3/videos must carry the cfg avatar_id and the locked engine
    submit = [c for c in calls if "/v3/videos" in c["url"]][0]
    payload = json.loads(submit["data"].decode())
    assert payload["avatar_id"] == "YOUR_AVATAR_ID"
    assert payload["engine"] == {"type": "avatar_v"}
    assert payload["audio_url"] == "https://resource.example.com/asset/abc"
    # API key travels in the X-Api-Key header, never in the payload
    assert submit["headers"]["X-Api-Key"] == "test-key"
    assert "test-key" not in json.dumps(payload)


def test_generate_avatar_zero_api_credit_gives_clear_error(tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"x")
    fake_req, _ = _router([("remaining_quota", QUOTA_ZERO)])

    with mock.patch.object(heygen, "_req", side_effect=fake_req):
        with pytest.raises(heygen.HeyGenError) as exc:
            heygen.generate_avatar(str(audio), str(tmp_path / "o.mp4"), make_cfg())
    msg = str(exc.value).lower()
    assert "credit" in msg
    assert "separate" in msg  # must explain API credit != plan credit


def test_generate_avatar_missing_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("HEYGEN_API_KEY", raising=False)
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"x")
    with pytest.raises(heygen.HeyGenError) as exc:
        heygen.generate_avatar(str(audio), str(tmp_path / "o.mp4"), make_cfg())
    assert "HEYGEN_API_KEY" in str(exc.value)


def test_generate_avatar_missing_avatar_id(tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"x")
    with pytest.raises(heygen.HeyGenError) as exc:
        heygen.generate_avatar(str(audio), str(tmp_path / "o.mp4"), make_cfg(avatar_id=""))
    assert "avatar_id" in str(exc.value)


def test_generate_avatar_missing_audio_file(tmp_path):
    with pytest.raises(heygen.HeyGenError) as exc:
        heygen.generate_avatar(str(tmp_path / "nope.mp3"), str(tmp_path / "o.mp4"), make_cfg())
    assert "audio" in str(exc.value).lower()


def test_generate_avatar_render_failure_raises(tmp_path, monkeypatch):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"x")
    fake_req, _ = _router([
        ("remaining_quota", QUOTA_OK),
        ("upload.heygen.com", UPLOAD_OK),
        ("/v3/videos", SUBMIT_OK),
        ("video_status.get", STATUS_FAILED),
    ])
    with mock.patch.object(heygen, "_req", side_effect=fake_req):
        with pytest.raises(heygen.HeyGenError) as exc:
            heygen.generate_avatar(str(audio), str(tmp_path / "o.mp4"), make_cfg())
    assert "render blew up" in str(exc.value)


def test_generate_avatar_polls_until_completed(tmp_path, monkeypatch):
    """Two 'processing' polls then 'completed'; sleep must be called between polls."""
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"x")
    out = str(tmp_path / "o.mp4")

    status_seq = iter([
        {"data": {"status": "processing"}},
        {"data": {"status": "processing"}},
        STATUS_DONE,
    ])
    calls = []

    def fake_req(url, data=None, headers=None, method=None):
        calls.append(url)
        if "remaining_quota" in url:
            return QUOTA_OK
        if "upload.heygen.com" in url:
            return UPLOAD_OK
        if "/v3/videos" in url:
            return SUBMIT_OK
        if "video_status.get" in url:
            return next(status_seq)
        raise AssertionError("unexpected URL " + url)

    sleeps = []
    monkeypatch.setattr(heygen.time, "sleep", lambda s: sleeps.append(s))

    with mock.patch.object(heygen, "_req", side_effect=fake_req), \
         mock.patch.object(heygen, "_download", side_effect=lambda u, d: open(d, "wb").write(b"v")):
        assert heygen.generate_avatar(str(audio), out, make_cfg()) == out

    assert len([u for u in calls if "video_status.get" in u]) == 3
    assert len(sleeps) == 2


def test_dict_config_also_accepted(tmp_path):
    """cfg may be a plain dict (e.g. loaded straight from YAML)."""
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"x")
    out = str(tmp_path / "o.mp4")
    fake_req, calls = _router([
        ("remaining_quota", QUOTA_OK),
        ("upload.heygen.com", UPLOAD_OK),
        ("/v3/videos", SUBMIT_OK),
        ("video_status.get", STATUS_DONE),
    ])
    with mock.patch.object(heygen, "_req", side_effect=fake_req), \
         mock.patch.object(heygen, "_download", side_effect=lambda u, d: open(d, "wb").write(b"v")):
        assert heygen.generate_avatar(str(audio), out, {"avatar_id": "YOUR_AVATAR_ID"}) == out
