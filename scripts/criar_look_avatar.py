#!/usr/bin/env python3
"""Cria um LOOK novo de avatar HeyGen a partir de UMA foto, via Higgsfield.

Pipeline provado em 01/09/2026 (look "apartamento v3" do grupo oficial):

    foto -> N clipes de 10s no Higgsfield (Seedance 2.0), cada um com um trecho
    DIFERENTE da voz real como `audio_references` -> conferencia por medicao ->
    emenda com o audio de cada clipe -> treino digital_twin no HeyGen, DENTRO do
    grupo informado -> poll ate completed.

As tres licoes pagas que este script carrega, pra ninguem repagar:

1. CLIPE MUDO NAO SERVE. A primeira versao gerou os clipes sem audio; o modelo
   INVENTOU o movimento de boca e o HeyGen aprendeu lipsync de uma boca que nao
   falava nada. Resultado reprovado na hora ("achei uma merda"). Com a voz real
   guiando cada clipe, a nitidez da boca subiu de 89% pra 93% do video real.
2. TODA JANELA DE VOZ CONTEM UMA PAUSA LONGA (silencedetect -35dB/0,35s): ensina a
   boca a FECHAR no silencio e da o discriminador pra auditar sincronia depois.
3. O `avatar_group_id` NAO E OPCIONAL. Sem ele o HeyGen cria um grupo paralelo, e
   look fora do grupo oficial ja custou refazer dois anuncios (caso estudio_verde).

Requisitos:
    HEYGEN_API_KEY no ambiente (nunca no codigo)
    CLI `higgsfield` autenticada
    ffmpeg/ffprobe

Uso:
    export HEYGEN_API_KEY=...
    python3 criar_look_avatar.py FOTO.jpg VOZ_LIMPA.mp3 \
        --grupo <avatar_group_id> --nome "Fulano -- cenario" [--clipes 6]

Custo de referencia: ~90 creditos Higgsfield por clipe de 10s em 1080p.
"""
import argparse
import json
import mimetypes
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

import numpy as np

BASE = "https://api.heygen.com"
DUR_CLIPE = 10
PROMPT = (
    "Locked-off static camera, no zoom, no pan, no cut, no scene change. Same room, "
    "same lighting, same framing throughout. He speaks the provided audio directly to "
    "camera, lips and jaw articulating each syllable accurately, mouth fully closed "
    "during the silent pauses, teeth visible when speaking, natural blinking, small "
    "natural head movements. Identity unchanged, documentary realism.")


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.exit(f"ERRO: {' '.join(str(c) for c in cmd[:4])}...\n{r.stderr[-500:]}")
    return r


def _req(url, data=None, headers=None, metodo=None):
    h = {"X-Api-Key": os.environ["HEYGEN_API_KEY"], "Accept": "application/json"}
    h.update(headers or {})
    r = urllib.request.Request(url, data=data, headers=h, method=metodo)
    try:
        with urllib.request.urlopen(r, timeout=600) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        corpo = e.read().decode()
        try:
            return e.code, json.loads(corpo or "{}")
        except json.JSONDecodeError:
            return e.code, {"raw": corpo[:400]}


def pausas_da_voz(voz):
    """Inicios de pausa longa, pra toda janela de treino conter uma."""
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", voz, "-af", "silencedetect=noise=-35dB:d=0.35",
         "-f", "null", "-"], capture_output=True, text=True)
    ts = [float(l.split("silence_start:")[1]) for l in r.stderr.splitlines()
          if "silence_start:" in l]
    return ts


def janelas(voz, n):
    """N janelas de DUR_CLIPE, cada uma contendo uma pausa medida."""
    ps = pausas_da_voz(voz)
    if not ps:
        sys.exit("a voz nao tem pausa longa nenhuma; use um audio mais natural")
    dur = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "csv=p=0", voz]).stdout.strip())
    out, usado = [], -1e9
    for p in ps:
        ini = max(0.0, min(p - 3.0, dur - DUR_CLIPE))
        if ini - usado < DUR_CLIPE * 0.8:      # janelas nao podem se sobrepor demais
            continue
        out.append(round(ini, 2))
        usado = ini
        if len(out) == n:
            break
    if len(out) < n:
        sys.exit(f"so {len(out)} janelas com pausa cabem nesse audio; precisa de {n}")
    return out


def movimento(caminho):
    """Diff medio entre quadros em numpy. O filtro do ffmpeg que devolvia 0,00 em
    video vivo ja mordeu; ler os quadros e subtrair nao tem como mentir."""
    W, H = 96, 171
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", caminho, "-vf",
         f"fps=4,format=gray,scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True)
    tam = W * H
    n = len(r.stdout) // tam
    if n < 2:
        return 0.0
    qs = [np.frombuffer(r.stdout[i * tam:(i + 1) * tam], dtype=np.uint8).astype(np.int16)
          for i in range(n)]
    return sum(float(np.abs(qs[i + 1] - qs[i]).mean()) for i in range(n - 1)) / (n - 1)


def gerar_clipes(foto, voz, inicios, td):
    saidas = []
    for k, ini in enumerate(inicios):
        ref = os.path.join(td, f"voz_{k:02d}.mp3")
        run(["ffmpeg", "-v", "error", "-ss", str(ini), "-t", str(DUR_CLIPE), "-i", voz,
             "-ac", "1", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "128k", "-y", ref])
        log = os.path.join(td, f"hf_{k:02d}.log")
        # DOIS POR VEZ: geracao pesada em paralelo ja derrubou rate limit
        with open(log, "w") as f:
            proc = subprocess.Popen(
                ["higgsfield", "generate", "create", "seedance_2_0",
                 "--start-image", foto, "--audio-references", ref,
                 "--prompt", PROMPT, "--duration", str(DUR_CLIPE),
                 "--resolution", "1080p", "--aspect_ratio", "9:16",
                 "--wait", "--wait-timeout", "25m"], stdout=f, stderr=f)
        saidas.append((proc, log, k))
        if k % 2 == 1:
            for p, _, _ in saidas[-2:]:
                p.wait()
    for p, _, _ in saidas:
        p.wait()

    clipes = []
    for _, log, k in saidas:
        url = next((l.strip() for l in reversed(open(log).read().splitlines())
                    if l.strip().startswith("https://") and l.strip().endswith(".mp4")), None)
        if not url:
            sys.exit(f"clipe {k}: geracao sem URL, ver {log}")
        alvo = os.path.join(td, f"clipe_{k:02d}.mp4")
        run(["curl", "-sS", "-o", alvo, url])
        mov = movimento(alvo)
        tem_audio = "audio" in run(["ffprobe", "-v", "error", "-show_entries",
                                    "stream=codec_type", "-of", "csv=p=0", alvo]).stdout
        if mov < 0.8 or not tem_audio:
            sys.exit(f"clipe {k} fora do contrato (mov={mov:.2f}, audio={tem_audio})")
        print(f"  clipe {k}: ok (mov {mov:.2f})", flush=True)
        clipes.append(alvo)
    return clipes


def emendar(clipes, td):
    lista = os.path.join(td, "lista.txt")
    with open(lista, "w") as f:
        for c in clipes:
            f.write(f"file '{c}'\n")
    treino = os.path.join(td, "treino.mp4")
    run(["ffmpeg", "-v", "error", "-f", "concat", "-safe", "0", "-i", lista,
         "-c:v", "libx264", "-crf", "21", "-preset", "slow", "-pix_fmt", "yuv420p",
         "-r", "24", "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
         "-movflags", "+faststart", "-y", treino])
    mb = os.path.getsize(treino) / 1e6
    if mb >= 32:
        sys.exit(f"treino com {mb:.1f} MB; o teto de upload do HeyGen e 32")
    return treino


def subir(treino, grupo, nome):
    lim = "----" + uuid.uuid4().hex
    corpo = b"".join([
        f"--{lim}\r\n".encode(),
        b'Content-Disposition: form-data; name="file"; filename="treino.mp4"\r\n',
        b"Content-Type: video/mp4\r\n\r\n",
        open(treino, "rb").read(),
        f"\r\n--{lim}--\r\n".encode(),
    ])
    st, d = _req(f"{BASE}/v3/assets", data=corpo,
                 headers={"Content-Type": f"multipart/form-data; boundary={lim}"})
    asset = ((d.get("data") or {}).get("id") or (d.get("data") or {}).get("asset_id"))
    if st >= 400 or not asset:
        sys.exit(f"upload falhou: {st} {json.dumps(d)[:300]}")
    st, d = _req(f"{BASE}/v3/avatars",
                 data=json.dumps({"type": "digital_twin", "name": nome,
                                  "file": {"type": "asset_id", "asset_id": asset},
                                  "avatar_group_id": grupo}).encode(),
                 headers={"Content-Type": "application/json"})
    item = (d.get("data") or {}).get("avatar_item") or {}
    look = item.get("id")
    if st >= 400 or not look:
        sys.exit(f"criacao falhou: {st} {json.dumps(d)[:300]}")
    if item.get("group_id") != grupo:
        sys.exit(f"PERIGO: look nasceu fora do grupo pedido ({item.get('group_id')})")
    print(f"  look {look} criado DENTRO do grupo {grupo}", flush=True)
    for i in range(60):
        st, d = _req(f"{BASE}/v3/avatars/looks/{look}")
        s = ((d.get("data") or {}).get("status") or "?")
        print(f"  {i * 30:4d}s  {s}", flush=True)
        if s in ("completed", "ready"):
            return look
        if s in ("failed", "error"):
            sys.exit("treino falhou: "
                     + json.dumps((d.get("data") or {}).get("error"))[:200])
        time.sleep(30)
    sys.exit("treino nao terminou em 30min")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("foto")
    ap.add_argument("voz", help="audio LIMPO da voz real da pessoa")
    ap.add_argument("--grupo", required=True, help="avatar_group_id de destino")
    ap.add_argument("--nome", required=True)
    ap.add_argument("--clipes", type=int, default=6)
    a = ap.parse_args()
    if "HEYGEN_API_KEY" not in os.environ:
        sys.exit("defina HEYGEN_API_KEY no ambiente (a chave nunca mora em codigo)")
    with tempfile.TemporaryDirectory() as td:
        inicios = janelas(a.voz, a.clipes)
        print(f"[1/3] gerando {a.clipes} clipes (janelas com pausa: {inicios})...")
        clipes = gerar_clipes(a.foto, a.voz, inicios, td)
        print("[2/3] emendando...")
        treino = emendar(clipes, td)
        print("[3/3] treinando no HeyGen...")
        look = subir(treino, a.grupo, a.nome)
        print(f"\nPRONTO: look {look} ('{a.nome}') treinado no grupo {a.grupo}.")
        print("Confira a amostra ANTES de usar em anuncio: gere um video curto com a "
              "voz padrao do grupo e olhe a boca em movimento.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
