"""HeyGen avatar generation locked to the Avatar V engine.

Avatar V is the engine that delivers realistic lip-sync (far superior to the
legacy avatar engine). It is MANDATORY in this pipeline: any attempt to use a
different engine is blocked by :func:`resolve_engine`.

Flow: upload the voice audio as an asset -> POST /v3/videos (type=avatar,
engine avatar_v) -> poll status -> download the rendered MP4.

Credentials: the API key is read from the HEYGEN_API_KEY environment variable.
The avatar id comes from the user's config (``cfg.avatar_id``), never from code.

Escape hatch (rare, e.g. an avatar look that provably does not support
Avatar V): set HEYGEN_ENGINE_OVERRIDE=<engine> AND request that same engine
explicitly, accepting the loss of realism. Without both, the lock holds.
"""
import json
import os
import time
import urllib.error
import urllib.request
import warnings

MANDATORY_ENGINE = "avatar_v"  # the engine that brings realism (lip-sync) -> mandatory
POLL_INTERVAL = 10             # seconds between status checks
POLL_TIMEOUT = 30 * 60         # give up after 30 minutes of rendering

UPLOAD_URL = "https://upload.heygen.com/v1/asset"
SUBMIT_URL = "https://api.heygen.com/v3/videos"
STATUS_URL = "https://api.heygen.com/v1/video_status.get?video_id={vid}"
QUOTA_URL = "https://api.heygen.com/v2/user/remaining_quota"

_AUDIO_CTYPES = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4"}


class HeyGenError(RuntimeError):
    """Raised for any HeyGen API or configuration failure."""


class EngineBlockedError(HeyGenError):
    """Raised when a non Avatar V engine is requested without an explicit override."""


def resolve_engine(requested=None):
    """Lock the engine to avatar_v; only release another engine with a loud override.

    - ``requested`` is None or ``avatar_v``: returns ``avatar_v``.
    - ``requested`` is another engine: blocked, unless the environment variable
      HEYGEN_ENGINE_OVERRIDE equals that exact engine (then it is allowed with
      a UserWarning about the quality loss).
    """
    override = os.environ.get("HEYGEN_ENGINE_OVERRIDE")
    if requested and requested != MANDATORY_ENGINE:
        if override != requested:
            raise EngineBlockedError(
                f"BLOCKED: Avatar V (engine '{MANDATORY_ENGINE}') is MANDATORY here: "
                f"it is the engine that brings realism to the avatar (lip-sync). "
                f"You requested '{requested}'.\n"
                f"If it is REALLY necessary (e.g. an avatar look that does not support "
                f"Avatar V), run with HEYGEN_ENGINE_OVERRIDE={requested} and accept the "
                f"quality loss."
            )
        warnings.warn(
            f"Engine '{requested}' allowed via explicit override. "
            f"Avatar V is the mandatory default.",
            UserWarning,
        )
        return requested
    if override and override != MANDATORY_ENGINE:
        warnings.warn(
            f"HEYGEN_ENGINE_OVERRIDE={override} ignored "
            f"(no engine requested; using Avatar V).",
            UserWarning,
        )
    return MANDATORY_ENGINE


def _api_key():
    key = os.environ.get("HEYGEN_API_KEY")
    if not key:
        raise HeyGenError(
            "HEYGEN_API_KEY not set. Export your HeyGen API key "
            "(HeyGen dashboard > Settings > API) or put it in your .env file."
        )
    return key


def _avatar_id(cfg):
    """Accept the Config object from vam.config (attribute) or a plain dict."""
    avatar_id = getattr(cfg, "avatar_id", None)
    if avatar_id is None and isinstance(cfg, dict):
        avatar_id = cfg.get("avatar_id") or (cfg.get("avatar") or {}).get("avatar_id")
    if not avatar_id:
        raise HeyGenError(
            "avatar_id missing in config. Set avatar_id in your config.yaml "
            "(find yours in the HeyGen dashboard, e.g. avatar_id: YOUR_AVATAR_ID)."
        )
    return avatar_id


def _req(url, data=None, headers=None, method=None):
    """Small JSON HTTP helper (stdlib only, easy to mock in tests)."""
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return json.loads(body)
        except ValueError:
            raise HeyGenError(f"HTTP {e.code} error at {url}\n{body[:500]}") from e
    except urllib.error.URLError as e:
        raise HeyGenError(f"Network error reaching {url}: {e.reason}") from e


def _download(url, dst):
    """Download a rendered video to disk (separate for easy mocking)."""
    urllib.request.urlretrieve(url, dst)


def check_credit(key):
    """Verify the account has API credit left; fail early with a clear message.

    HeyGen API credits are SEPARATE from the credits of your HeyGen plan:
    a paid plan with plenty of credits can still have 0 API credits.
    """
    d = _req(QUOTA_URL, headers={"X-Api-Key": key, "Accept": "application/json"})
    data = d.get("data") or {}
    quota = data.get("remaining_quota")
    if quota is not None and quota <= 0:
        raise HeyGenError(
            "HeyGen API credit is 0, cannot generate the avatar video.\n"
            "Note: API credits are SEPARATE from your HeyGen plan credits. Even on a "
            "paid plan you must have API credits (HeyGen dashboard > Settings > API / "
            "Subscriptions > API plan). Add API credits and try again."
        )
    return quota


def _upload_audio(path, key):
    if not os.path.exists(path):
        raise HeyGenError(f"Audio file not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    ctype = _AUDIO_CTYPES.get(ext, "audio/mpeg")
    with open(path, "rb") as f:
        data = f.read()
    print(f"[1/3] uploading audio ({len(data) // 1024} KB)...")
    d = _req(UPLOAD_URL, data=data,
             headers={"X-Api-Key": key, "Content-Type": ctype}, method="POST")
    url = (d.get("data") or {}).get("url")
    if not url:
        raise HeyGenError(f"Audio upload failed: {json.dumps(d)[:300]}")
    return url


def _submit_v3(audio_url, avatar_id, engine, key):
    payload = {
        "type": "avatar",
        "avatar_id": avatar_id,
        "audio_url": audio_url,
        "aspect_ratio": "9:16",
        "resolution": "1080p",
        "engine": {"type": engine},
    }
    print(f"[2/3] submitting /v3/videos (avatar {avatar_id}, engine {engine})...")
    d = _req(SUBMIT_URL, data=json.dumps(payload).encode(),
             headers={"X-Api-Key": key, "Content-Type": "application/json"},
             method="POST")
    if d.get("error"):
        raise HeyGenError(f"Submit to /v3/videos failed: {json.dumps(d['error'])}")
    data = d.get("data") or {}
    vid = data.get("video_id") or d.get("video_id") or data.get("id")
    if not vid:
        raise HeyGenError(f"No video_id in the API response: {json.dumps(d)[:400]}")
    print("      video_id =", vid)
    return vid


def _poll_download(vid, out, key):
    print(f"[3/3] waiting for render of {vid} (checking every {POLL_INTERVAL}s)...")
    t0 = time.time()
    while True:
        d = _req(STATUS_URL.format(vid=vid), headers={"X-Api-Key": key})
        data = d.get("data") or {}
        status = data.get("status")
        print("      status=", status, flush=True)
        if status == "completed":
            _download(data.get("video_url"), out)
            print(f"DOWNLOADED {out} (duration={data.get('duration')}s)")
            return out
        if status in ("failed", "error"):
            raise HeyGenError(
                f"HeyGen render failed: {json.dumps(data.get('error'))[:400]}"
            )
        if time.time() - t0 >= POLL_TIMEOUT:
            raise HeyGenError(
                f"Timed out after {POLL_TIMEOUT // 60} minutes waiting for the render "
                f"of video {vid}. Check it later in the HeyGen dashboard."
            )
        time.sleep(POLL_INTERVAL)


def generate_avatar(audio_path, out_path, cfg, engine=None):
    """Generate a lip-synced avatar video from a real voice recording.

    Uploads ``audio_path`` to HeyGen, renders it with the avatar from
    ``cfg.avatar_id`` using the mandatory Avatar V engine, downloads the
    result to ``out_path`` and returns ``out_path``.
    """
    key = _api_key()
    avatar_id = _avatar_id(cfg)
    if not os.path.exists(audio_path):
        raise HeyGenError(f"Audio file not found: {audio_path}")
    eng = resolve_engine(engine)
    check_credit(key)
    audio_url = _upload_audio(audio_path, key)
    vid = _submit_v3(audio_url, avatar_id, eng, key)
    return _poll_download(vid, out_path, key)
