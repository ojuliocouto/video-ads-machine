#!/usr/bin/env python3
"""Sobe arquivos pro Google Drive por upload RESUMABLE (bytes direto do disco -> Google,
nao passam pelo contexto do agente). Reusa o token Google ja configurado
(~/.claude/google-tokens.json, escopo drive.file) + refresh via google-api.sh.

CLI:    python3 drive_push.py <folder_url_ou_id> <arquivo> [arquivo...]
Import: from drive_push import push
        push("<folder_url_ou_id>", [(local_path, nome_no_drive), ...])
Depois de subir, SEMPRE verifica via API que o arquivo caiu na pasta (nao confia so no POST).
"""
import json, os, re, subprocess, tempfile, urllib.parse, urllib.request

TOKENS = os.path.expanduser("~/.claude/google-tokens.json")
APISH  = os.path.expanduser("~/.claude/scripts/google-api.sh")

def folder_id(s):
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", s or "")
    return m.group(1) if m else (s or "").strip()

def _token():
    return json.load(open(TOKENS))["access_token"]

def refresh():
    subprocess.run(["bash", APISH, "refresh"], capture_output=True, text=True)

def _mime_for(path):
    return {".mp4":"video/mp4", ".mov":"video/quicktime", ".png":"image/png",
            ".jpg":"image/jpeg", ".jpeg":"image/jpeg", ".txt":"text/plain",
            ".pdf":"application/pdf"}.get(os.path.splitext(path)[1].lower(), "application/octet-stream")

def _init(name, size, folder, mime):
    meta = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump({"name": name, "parents": [folder], "mimeType": mime}, meta); meta.close()
    r = subprocess.run(["curl","-s","-D","-","-o","/dev/null","-X","POST",
        "-H", f"Authorization: Bearer {_token()}",
        "-H", "Content-Type: application/json; charset=UTF-8",
        "-H", f"X-Upload-Content-Type: {mime}",
        "-H", f"X-Upload-Content-Length: {size}",
        "--data", f"@{meta.name}",
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&supportsAllDrives=true"],
        capture_output=True, text=True)
    os.unlink(meta.name)
    status = r.stdout.split("\n", 1)[0] if r.stdout else ""
    loc = next((l.split(":",1)[1].strip() for l in r.stdout.splitlines()
                if l.lower().startswith("location:")), None)
    return loc, status

def _put(loc, local, mime):
    r = subprocess.run(["curl","-s","-X","PUT","-H",f"Content-Type: {mime}",
        "--upload-file", local, loc], capture_output=True, text=True)
    try: return json.loads(r.stdout)
    except ValueError: return {"_raw": (r.stdout or "")[:300]}

def upload_one(local, name, folder):
    mime = _mime_for(local); size = os.path.getsize(local)
    loc, status = _init(name, size, folder, mime)
    if not loc and "401" in status:          # token velho: refresh e tenta 1x
        refresh(); loc, status = _init(name, size, folder, mime)
    if not loc:
        return {"name": name, "ok": False, "id": None, "link": None, "error": status[:160]}
    res = _put(loc, local, mime); fid = res.get("id")
    return {"name": name, "ok": bool(fid), "id": fid,
            "link": f"https://drive.google.com/file/d/{fid}/view" if fid else None,
            "error": None if fid else json.dumps(res)[:200]}

def list_folder(folder):
    """{nome: tamanho} dos arquivos nao-lixo da pasta (via API)."""
    q = f"'{folder}' in parents and trashed=false"
    url = ("https://www.googleapis.com/drive/v3/files?q=" + urllib.parse.quote(q) +
           "&fields=files(name,size)&pageSize=1000&supportsAllDrives=true&includeItemsFromAllDrives=true")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {_token()}"})
    try:
        data = json.load(urllib.request.urlopen(req, timeout=60)).get("files", [])
    except Exception:
        return {}
    return {f["name"]: int(f.get("size", 0)) for f in data}

def delete(file_id):
    subprocess.run(["curl","-s","-X","DELETE","-H",f"Authorization: Bearer {_token()}",
        f"https://www.googleapis.com/drive/v3/files/{file_id}?supportsAllDrives=true"],
        capture_output=True, text=True)

def push(folder_or_url, items):
    """items = [(local_path, nome_no_drive), ...]. Sobe e CONFIRMA cada um na pasta."""
    folder = folder_id(folder_or_url)
    refresh()
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
    a = sys.argv[1:]
    if len(a) < 2: sys.exit(__doc__)
    out = push(a[0], [(f, os.path.basename(f)) for f in a[1:]])
    for r in out["results"]:
        print(f"  {'OK ' if r['ok'] and r['verified'] else 'ERRO'} {r['name']}  {r.get('link') or r.get('error')}")
    print(f"pasta: {out['folder_link']} | all_ok={out['all_ok']}")
