"""Tests for vam.drive: folder id parsing, resumable upload flow, token refresh.

All HTTP is mocked via vam.drive._request; no real Google API calls are made.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from vam import drive  # noqa: E402


# ---------------------------------------------------------------- folder_id

def test_folder_id_from_url():
    url = "https://drive.google.com/drive/folders/1AbC_dEf-9xYz?usp=sharing"
    assert drive.folder_id(url) == "1AbC_dEf-9xYz"


def test_folder_id_from_url_u0_path():
    url = "https://drive.google.com/drive/u/0/folders/1AbC_dEf-9xYz"
    assert drive.folder_id(url) == "1AbC_dEf-9xYz"


def test_folder_id_from_plain_id():
    assert drive.folder_id("  1AbC_dEf-9xYz ") == "1AbC_dEf-9xYz"


def test_folder_id_empty():
    assert drive.folder_id("") == ""
    assert drive.folder_id(None) == ""


# ------------------------------------------------------------- test helpers

def _write_tokens(tmp_path, access="tok-old"):
    tf = tmp_path / "google-tokens.json"
    tf.write_text(json.dumps({
        "access_token": access,
        "refresh_token": "rt-1",
        "client_id": "cid-1",
        "client_secret": "cs-1",
    }))
    return tf


def _write_file(tmp_path, name="video.mp4", data=b"fake-mp4-bytes"):
    f = tmp_path / name
    f.write_bytes(data)
    return f


class FakeHTTP:
    """Records calls and replays canned (status, headers, body) responses."""

    def __init__(self, script):
        # script: list of callables(method, url, headers, data) -> (status, headers, body)
        self.script = list(script)
        self.calls = []

    def __call__(self, method, url, headers=None, data=None, timeout=120):
        self.calls.append({"method": method, "url": url,
                           "headers": dict(headers or {}), "data": data})
        handler = self.script.pop(0)
        return handler(method, url, headers or {}, data)


def _ok_init(location="https://upload.example/session-1"):
    def h(method, url, headers, data):
        assert method == "POST" and "uploadType=resumable" in url
        return 200, {"location": location}, ""
    return h


def _ok_put(file_id="FILE1"):
    def h(method, url, headers, data):
        assert method == "PUT"
        return 200, {}, json.dumps({"id": file_id, "name": "x"})
    return h


def _ok_list(names_sizes):
    def h(method, url, headers, data):
        assert method == "GET" and "/drive/v3/files?q=" in url
        files = [{"name": n, "size": str(s)} for n, s in names_sizes]
        return 200, {}, json.dumps({"files": files})
    return h


# ------------------------------------------------------------ push happy path

def test_push_uploads_and_verifies(tmp_path, monkeypatch):
    tf = _write_tokens(tmp_path)
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_FILE", str(tf))
    src = _write_file(tmp_path)

    fake = FakeHTTP([
        _ok_init(),
        _ok_put("FILE1"),
        _ok_list([("final.mp4", len(b"fake-mp4-bytes"))]),
    ])
    monkeypatch.setattr(drive, "_request", fake)

    out = drive.push("https://drive.google.com/drive/folders/1Fold", [(str(src), "final.mp4")])

    assert out["folder_link"] == "https://drive.google.com/drive/folders/1Fold"
    assert out["all_ok"] is True
    r = out["results"][0]
    assert r["ok"] and r["verified"]
    assert r["id"] == "FILE1"
    assert r["link"] == "https://drive.google.com/file/d/FILE1/view"

    # init call carries the access token and resumable metadata
    init_call = fake.calls[0]
    assert init_call["headers"]["Authorization"] == "Bearer tok-old"
    meta = json.loads(init_call["data"])
    assert meta["name"] == "final.mp4"
    assert meta["parents"] == ["1Fold"]
    assert meta["mimeType"] == "video/mp4"


def test_push_not_verified_when_missing_from_folder(tmp_path, monkeypatch):
    tf = _write_tokens(tmp_path)
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_FILE", str(tf))
    src = _write_file(tmp_path)

    fake = FakeHTTP([
        _ok_init(),
        _ok_put("FILE1"),
        _ok_list([]),  # folder listing does NOT contain the file
    ])
    monkeypatch.setattr(drive, "_request", fake)

    out = drive.push("1Fold", [(str(src), "final.mp4")])
    assert out["results"][0]["ok"] is True
    assert out["results"][0]["verified"] is False
    assert out["all_ok"] is False


# ------------------------------------------------------------- refresh on 401

def test_push_refreshes_token_on_401_and_retries(tmp_path, monkeypatch):
    tf = _write_tokens(tmp_path, access="tok-old")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_FILE", str(tf))
    src = _write_file(tmp_path)

    def _expired(method, url, headers, data):
        assert headers["Authorization"] == "Bearer tok-old"
        return 401, {}, json.dumps({"error": {"code": 401}})

    def _refresh(method, url, headers, data):
        assert url == "https://oauth2.googleapis.com/token"
        body = data.decode() if isinstance(data, bytes) else str(data)
        assert "grant_type=refresh_token" in body
        assert "refresh_token=rt-1" in body
        assert "client_id=cid-1" in body
        assert "client_secret=cs-1" in body
        return 200, {}, json.dumps({"access_token": "tok-new", "expires_in": 3599})

    def _init_new_token(method, url, headers, data):
        assert headers["Authorization"] == "Bearer tok-new"
        return 200, {"location": "https://upload.example/session-2"}, ""

    fake = FakeHTTP([
        _expired,          # init -> 401
        _refresh,          # token refresh
        _init_new_token,   # init retry with new token
        _ok_put("FILE2"),
        _ok_list([("final.mp4", len(b"fake-mp4-bytes"))]),
    ])
    monkeypatch.setattr(drive, "_request", fake)

    out = drive.push("1Fold", [(str(src), "final.mp4")])
    assert out["all_ok"] is True
    assert out["results"][0]["id"] == "FILE2"
    # refreshed token was persisted back to the token file
    assert json.loads(tf.read_text())["access_token"] == "tok-new"


def test_upload_failure_is_reported_not_raised(tmp_path, monkeypatch):
    tf = _write_tokens(tmp_path)
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_FILE", str(tf))
    src = _write_file(tmp_path)

    def _forbidden(method, url, headers, data):
        return 403, {}, json.dumps({"error": {"code": 403, "message": "quota"}})

    fake = FakeHTTP([
        _forbidden,
        _ok_list([]),
    ])
    monkeypatch.setattr(drive, "_request", fake)

    out = drive.push("1Fold", [(str(src), "final.mp4")])
    r = out["results"][0]
    assert r["ok"] is False and r["id"] is None
    assert r["error"]
    assert out["all_ok"] is False


# ------------------------------------------------------------ env validation

def test_missing_token_file_env_raises_clear_error(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_TOKEN_FILE", raising=False)
    src = _write_file(tmp_path)
    try:
        drive.push("1Fold", [(str(src), "final.mp4")])
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "GOOGLE_OAUTH_TOKEN_FILE" in str(e)


def test_mime_detection():
    assert drive._mime_for("a.mp4") == "video/mp4"
    assert drive._mime_for("a.PNG") == "image/png"
    assert drive._mime_for("a.bin") == "application/octet-stream"
