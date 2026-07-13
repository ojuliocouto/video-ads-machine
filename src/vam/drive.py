"""Upload finished videos to the user's own Google Drive folder.

Files are sent with the Drive v3 RESUMABLE upload protocol in two steps:
1. POST metadata (name, parent folder, mime type) -> the response's Location
   header is the upload session URL.
2. PUT the file bytes to that session URL.

After uploading, the target folder is listed via the API to VERIFY that each
file actually landed there (the POST alone is not trusted).

Credentials belong to the USER: the GOOGLE_OAUTH_TOKEN_FILE environment
variable must point to a JSON file shaped like
    {"access_token": "...", "refresh_token": "...",
     "client_id": "...", "client_secret": "..."}
When the access token is expired (HTTP 401) it is refreshed natively against
https://oauth2.googleapis.com/token and the new token is persisted back to the
same file.

Minimum OAuth scope required: https://www.googleapis.com/auth/drive.file
(access only to files created by this app; no read access to the rest of the
user's Drive).

CLI:    python3 -m vam.drive <folder_url_or_id> <file> [file...]
Import: from vam.drive import push
        push("<folder_url_or_id>", [(local_path, name_on_drive), ...])
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
UPLOAD_ENDPOINT = ("https://www.googleapis.com/upload/drive/v3/files"
                   "?uploadType=resumable&supportsAllDrives=true")
FILES_ENDPOINT = "https://www.googleapis.com/drive/v3/files"

_MIME = {
    ".mp4": "video/mp4", ".mov": "video/quicktime", ".png": "image/png",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".txt": "text/plain",
    ".pdf": "application/pdf",
}


# --------------------------------------------------------------------- utils

def folder_id(s):
    """Extract the folder id from a Drive folder URL, or return the raw id."""
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", s or "")
    return m.group(1) if m else (s or "").strip()


def _mime_for(path):
    return _MIME.get(os.path.splitext(path)[1].lower(), "application/octet-stream")


def _token_file():
    path = os.environ.get("GOOGLE_OAUTH_TOKEN_FILE", "").strip()
    if not path:
        raise RuntimeError(
            "GOOGLE_OAUTH_TOKEN_FILE is not set. Point it to a JSON file with "
            "your Google OAuth credentials: {access_token, refresh_token, "
            "client_id, client_secret}. Scope needed: drive.file.")
    if not os.path.exists(path):
        raise RuntimeError(f"GOOGLE_OAUTH_TOKEN_FILE points to a missing file: {path}")
    return path


def _load_tokens():
    with open(_token_file()) as f:
        return json.load(f)


def _access_token():
    tok = _load_tokens().get("access_token", "")
    if not tok:
        raise RuntimeError("Token file has no access_token. Re-run your OAuth "
                           "setup to obtain one (scope: drive.file).")
    return tok


# ---------------------------------------------------------------------- HTTP

def _request(method, url, headers=None, data=None, timeout=300):
    """Do one HTTP request. Returns (status, lowercase-headers dict, body str).

    Isolated in a single function so tests can mock ALL network traffic here.
    `data` may be bytes or a readable binary file object (streams the upload).
    """
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, hdrs, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        hdrs = {k.lower(): v for k, v in (e.headers or {}).items()}
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        return e.code, hdrs, body


# ------------------------------------------------------------- token refresh

def refresh():
    """Refresh the access token via oauth2.googleapis.com and persist it.

    Returns the new access token. Raises RuntimeError with a clear message if
    the token file lacks refresh credentials or Google rejects the refresh.
    """
    path = _token_file()
    tokens = _load_tokens()
    missing = [k for k in ("refresh_token", "client_id", "client_secret")
               if not tokens.get(k)]
    if missing:
        raise RuntimeError(
            "Cannot refresh Google token: missing %s in %s. The token file "
            "must contain refresh_token, client_id and client_secret."
            % (", ".join(missing), path))
    form = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
        "client_id": tokens["client_id"],
        "client_secret": tokens["client_secret"],
    }).encode()
    status, _, body = _request(
        "POST", TOKEN_ENDPOINT,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=form, timeout=60)
    if status != 200:
        raise RuntimeError(f"Google token refresh failed (HTTP {status}): {body[:300]}")
    payload = json.loads(body)
    tokens["access_token"] = payload["access_token"]
    with open(path, "w") as f:
        json.dump(tokens, f)
    return tokens["access_token"]


# ------------------------------------------------------------- upload (2-step)

def _init_upload(name, size, folder, mime, token):
    """Step 1: POST metadata; returns (upload_session_url_or_None, http_status)."""
    meta = json.dumps({"name": name, "parents": [folder], "mimeType": mime}).encode()
    status, hdrs, _ = _request(
        "POST", UPLOAD_ENDPOINT,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": mime,
            "X-Upload-Content-Length": str(size),
        },
        data=meta, timeout=60)
    return hdrs.get("location"), status


def _put_bytes(session_url, local, mime, size):
    """Step 2: PUT the file bytes to the upload session URL. Returns parsed JSON."""
    with open(local, "rb") as f:
        status, _, body = _request(
            "PUT", session_url,
            headers={"Content-Type": mime, "Content-Length": str(size)},
            data=f)
    try:
        return json.loads(body)
    except ValueError:
        return {"_status": status, "_raw": (body or "")[:300]}


def upload_one(local, name, folder):
    """Upload a single file; refreshes the token once on HTTP 401."""
    mime = _mime_for(local)
    size = os.path.getsize(local)
    token = _access_token()
    session, status = _init_upload(name, size, folder, mime, token)
    if not session and status == 401:  # stale token: refresh and retry once
        token = refresh()
        session, status = _init_upload(name, size, folder, mime, token)
    if not session:
        return {"name": name, "ok": False, "id": None, "link": None,
                "error": f"resumable init failed (HTTP {status})"}
    res = _put_bytes(session, local, mime, size)
    fid = res.get("id")
    return {"name": name, "ok": bool(fid), "id": fid,
            "link": f"https://drive.google.com/file/d/{fid}/view" if fid else None,
            "error": None if fid else json.dumps(res)[:200]}


# --------------------------------------------------------------- verification

def list_folder(folder):
    """Return {name: size} of non-trashed files in the folder (via API)."""
    q = f"'{folder}' in parents and trashed=false"
    url = (FILES_ENDPOINT + "?q=" + urllib.parse.quote(q) +
           "&fields=files(name,size)&pageSize=1000"
           "&supportsAllDrives=true&includeItemsFromAllDrives=true")
    status, _, body = _request(
        "GET", url, headers={"Authorization": f"Bearer {_access_token()}"}, timeout=60)
    if status != 200:
        return {}
    try:
        files = json.loads(body).get("files", [])
    except ValueError:
        return {}
    return {f["name"]: int(f.get("size", 0) or 0) for f in files}


# ----------------------------------------------------------------------- push

def push(folder_or_url, items):
    """Upload items = [(local_path, name_on_drive), ...] and VERIFY each one.

    Returns {"folder", "folder_link", "results": [...], "all_ok": bool}.
    Each result: {name, ok, id, link, error, verified}. `verified` means the
    file was seen in the folder listing AFTER the upload.
    """
    folder = folder_id(folder_or_url)
    if not folder:
        raise RuntimeError("No Drive folder given: pass a folder URL or id.")
    results = [upload_one(local, name, folder) for local, name in items]
    present = list_folder(folder)
    for r in results:
        r["verified"] = r["name"] in present
    return {"folder": folder,
            "folder_link": f"https://drive.google.com/drive/folders/{folder}",
            "results": results,
            "all_ok": bool(results) and all(r["ok"] and r["verified"] for r in results)}


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if len(args) < 2:
        sys.exit(__doc__)
    out = push(args[0], [(f, os.path.basename(f)) for f in args[1:]])
    for r in out["results"]:
        mark = "OK " if r["ok"] and r["verified"] else "FAIL"
        print(f"  {mark} {r['name']}  {r.get('link') or r.get('error')}")
    print(f"folder: {out['folder_link']} | all_ok={out['all_ok']}")
