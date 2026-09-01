#!/usr/bin/env python3
"""Gera avatar HeyGen com o ENGINE Avatar V (v3 /videos) a partir de VOZ REAL.

Avatar V = o engine que traz MAIS REALIDADE pro avatar (lip-sync muito superior ao
avatar comum). É REGRA OBRIGATÓRIA da skill: este gerador SÓ usa avatar_v. Não existe
caminho "avatar comum" aqui (o /v2 antigo foi aposentado, ver heygen_avatar.py).
Fluxo: sobe o audio -> POST /v3/videos (type=avatar, engine avatar_v) -> poll -> baixa.

Uso: python3 heygen_av5.py gerar <audio.mp3> <avatar_id> [saida.mp4]
     python3 heygen_av5.py status <video_id> [saida.mp4]
Chave: HEYGEN_API_KEY (env ou .env).

Escape hatch (raríssimo, ex: um look que comprovadamente não suporta Avatar V):
rodar com HEYGEN_ENGINE_OVERRIDE=<engine>, assumindo a PERDA de realismo. Sem isso,
qualquer tentativa de usar engine != avatar_v é BLOQUEADA.
"""
import json, os, sys, time, urllib.request, urllib.error

# (migracao 26/08/2026) caminho de projeto agora sai de caminhos.py: o .env e os avatares
# sao DADOS e ficam com os dados, nao junto do codigo.
from caminhos import DADOS as _D
BASE = str(_D)
POLL_INTERVAL, POLL_TIMEOUT = 10, 30*60
MANDATORY_ENGINE = "avatar_v"   # regra do Júlio: Avatar V é o que traz realidade -> OBRIGATÓRIO

def resolve_engine(requested):
    """Trava o engine em avatar_v. Só libera outro com override EXPLÍCITO e barulhento."""
    override = os.environ.get("HEYGEN_ENGINE_OVERRIDE")
    if requested and requested != MANDATORY_ENGINE:
        if override != requested:
            sys.exit(
                f"BLOQUEADO: Avatar V (engine '{MANDATORY_ENGINE}') é OBRIGATÓRIO nesta skill: "
                f"é o engine que traz realidade pro avatar (lip-sync). Você pediu '{requested}'.\n"
                f"Se for MESMO necessário (ex: look que não suporta Avatar V), rode com "
                f"HEYGEN_ENGINE_OVERRIDE={requested} e assuma a perda de qualidade.")
        print(f"*** AVISO: engine '{requested}' via override explícito. Avatar V é o padrão obrigatório. ***")
        return requested
    if override and override != MANDATORY_ENGINE:
        print(f"*** AVISO: HEYGEN_ENGINE_OVERRIDE={override} ignorado (nenhum engine pedido; usando Avatar V). ***")
    return MANDATORY_ENGINE

def api_key():
    k = os.environ.get("HEYGEN_API_KEY")
    if not k and os.path.exists(os.path.join(BASE, ".env")):
        for line in open(os.path.join(BASE, ".env")):
            if line.strip().startswith("HEYGEN_API_KEY="):
                k = line.strip().split("=", 1)[1]; break
    if not k: sys.exit("ERRO: HEYGEN_API_KEY nao encontrada.")
    return k

def _req(url, data=None, headers=None, method=None):
    r = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try: return json.loads(body)
        except ValueError: sys.exit(f"ERRO HTTP {e.code} em {url}\n{body[:500]}")

def upload_audio(path, key):
    if not os.path.exists(path): sys.exit(f"ERRO: audio nao existe: {path}")
    ext = os.path.splitext(path)[1].lower()
    ctype = {".mp3":"audio/mpeg", ".wav":"audio/wav", ".m4a":"audio/mp4"}.get(ext, "audio/mpeg")
    data = open(path, "rb").read()
    print(f"[1/3] subindo audio ({len(data)//1024} KB)...")
    d = _req("https://upload.heygen.com/v1/asset", data=data,
             headers={"X-Api-Key": key, "Content-Type": ctype}, method="POST")
    url = (d.get("data") or {}).get("url")
    if not url: sys.exit(f"ERRO upload: {json.dumps(d)[:300]}")
    return url

def submit_v3(audio_url, avatar_id, engine, key):
    payload = {
        "type": "avatar",
        "avatar_id": avatar_id,
        "audio_url": audio_url,
        "aspect_ratio": "9:16",
        "resolution": "1080p",
        "engine": {"type": engine},
    }
    print(f"[2/3] disparando /v3/videos (avatar {avatar_id}, engine {engine})...")
    d = _req("https://api.heygen.com/v3/videos", data=json.dumps(payload).encode(),
             headers={"X-Api-Key": key, "Content-Type": "application/json"}, method="POST")
    if d.get("error"):
        sys.exit(f"ERRO submit v3: {json.dumps(d['error'])}")
    vid = (d.get("data") or {}).get("video_id") or d.get("video_id") or (d.get("data") or {}).get("id")
    if not vid: sys.exit(f"ERRO: sem video_id na resposta: {json.dumps(d)[:400]}")
    print("      video_id =", vid)
    return vid

def poll_download(vid, out, key):
    print(f"[3/3] aguardando render do {vid} (checa a cada {POLL_INTERVAL}s)...")
    t0 = time.time()
    while time.time() - t0 < POLL_TIMEOUT:
        d = _req(f"https://api.heygen.com/v3/videos/{vid}",
                 headers={"X-Api-Key": key})
        data = d.get("data") or {}
        st = data.get("status")
        print("      status=", st, flush=True)
        if st == "completed":
            urllib.request.urlretrieve(data.get("video_url"), out)
            print(f"BAIXADO {out} (dur={data.get('duration')}s)")
            return out
        if st in ("failed", "error"):
            sys.exit(f"FALHOU: {data.get('failure_code')} {data.get('failure_message')}")
        time.sleep(POLL_INTERVAL)
    sys.exit("TIMEOUT render")

def main():
    a = sys.argv[1:]
    key = api_key()
    if a and a[0] == "gerar":
        audio, avatar_id = a[1], a[2]
        out = a[3] if len(a) > 3 else os.path.join(BASE, "inputs", "avatar_av5.mp4")
        engine = resolve_engine(a[4] if len(a) > 4 else None)   # trava em avatar_v (obrigatório)
        url = upload_audio(audio, key)
        vid = submit_v3(url, avatar_id, engine, key)
        poll_download(vid, out, key)
    elif a and a[0] == "status":
        vid = a[1]; out = a[2] if len(a) > 2 else os.path.join(BASE, "inputs", f"avatar_{vid[:8]}.mp4")
        poll_download(vid, out, key)
    else:
        sys.exit(__doc__)

if __name__ == "__main__":
    main()
