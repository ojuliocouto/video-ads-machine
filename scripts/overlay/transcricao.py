"""O avatar acelerado, a transcrição com cache por conteúdo e as palavras do roteiro com tempo.

Tudo o que o overlay sabe sobre TEMPO nasce aqui: o avatar é pré-acelerado ANTES de transcrever,
então spans, brolls, legendas, letterings e CTA nascem no tempo acelerado sozinhos. Não regera
nada no HeyGen: é só re-timing local (vídeo com `setpts`, áudio com `atempo`, tom preservado).

Com a timeline.json (W3.A, relógio único), o overlay NÃO transcreve: as palavras vêm do alinhamento
único que a timeline cita (`palavras_da_timeline`), o mesmo que a footage usa, transcrito uma vez só
pelo `audio.transcrever`. Sem timeline segue o caminho antigo, até a W5.A ligar a timeline no build:
o `hyperframes transcribe` com o motor parakeet, no diretório de saída, mais o cache por conteúdo em
`<dados>/output/_cache/transcricao`, e o `gerar` avisa no fim (`AVISO_SEM_TIMELINE`).
"""
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

import build_timeline
from caminhos import V1, V2

SPEED = 1.15         # aceleração global do vídeo (o motor antigo fazia 1.2x); pré-acelera o avatar
TAIL_PAD = 0.65      # folga de cauda: garante root/audio >= duração real do áudio (sem corte)
HF = str(V2 / "node_modules" / ".bin" / "hyperframes")
AVISO_SEM_TIMELINE = ("   [relogio] AVISO: overlay sem timeline.json: transcreveu e alinhou por conta propria "
                      "(caminho antigo, relogio diferente do da footage). Passe \"timeline\" no config "
                      "(timeline/construir.py gera).")


def run(cmd, **kw):
    """subprocess.run que para o motor com o comando e o fim do stderr quando algo falha."""
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.exit(f"ERRO: {' '.join(str(c) for c in cmd)}\n{r.stderr[-800:]}")
    return r


def vdur(f):
    """Duração do arquivo em segundos (ffprobe); 0.0 quando não dá para medir."""
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(f)], capture_output=True, text=True).stdout.strip()
    return float(o) if o else 0.0


def norm(w):
    """Forma de comparação de uma palavra: sem acento, sem pontuação, minúscula."""
    w = unicodedata.normalize("NFKD", w)
    w = "".join(c for c in w if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", w.lower())


def preparar_avatar(avatar_src, out, speed):
    """Põe `out/avatar.mp4` na velocidade pedida e devolve (caminho, duração total do clipe).

    Aceleração (D6): pré-acelera o avatar (vídeo `setpts`, áudio `atempo`) antes de transcrever.
    Ao (re)acelerar, invalida os derivados que dependem do avatar (transcript e brolls).
    O total soma TAIL_PAD e arredonda para cima no centésimo: a cauda nunca é cortada (D5).
    """
    avatar_src = Path(avatar_src)
    dst = Path(out) / "avatar.mp4"
    target = round(vdur(avatar_src) / speed, 2)
    if not dst.exists() or abs(vdur(dst) - target) > 0.05:
        for old in [Path(out) / "transcript.json", *Path(out).glob("broll*.mp4")]:
            old.unlink(missing_ok=True)
        if abs(speed - 1.0) < 1e-3:
            shutil.copy(avatar_src, dst)
        else:
            run(["ffmpeg", "-y", "-i", str(avatar_src),
                 "-filter_complex", f"[0:v]setpts=PTS/{speed}[v];[0:a]atempo={speed}[a]",
                 "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p",
                 "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                 "-c:a", "aac", "-b:a", "192k", str(dst)])
    _real = vdur(dst)
    total = math.ceil((_real + TAIL_PAD) * 100) / 100
    return dst, total


def chave_do_conteudo(caminho):
    """sha256 do conteúdo INTEIRO do arquivo: nem caminho, nem tamanho, nem mtime."""
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def transcrever(dst, out):
    """Lista de palavras `{text, start, end}` do avatar, vinda do cache por CONTEÚDO se existir.

    Cache entre builds (31/08/2026): 8 builds do mesmo anúncio no mesmo dia rodaram o parakeet 8
    vezes para o MESMO avatar, cerca de 2,5 min cada, porque cada build cai num out_dir novo e a
    checagem do `transcript.json` local nunca acerta entre eles. A chave é o sha256 do conteúdo do
    `avatar.mp4`, então qualquer out_dir com o mesmo áudio reaproveita sem chamar o parakeet.

    W3.X L5: a chave antiga (`cache_transcricao`) misturava os primeiros 8 MB com tamanho e MTIME, e a cópia
    do mesmo avatar em outra pasta (mtime novo) nunca acertava. Agora é o conteúdo, como este docstring dizia.
    """
    dst, out = Path(dst), Path(out)
    pasta_cache = V1 / "output" / "_cache" / "transcricao"
    if not (out / "transcript.json").exists():
        chave = chave_do_conteudo(dst)
        guardado = pasta_cache / f"{chave}.json"
        if guardado.is_file():
            shutil.copy(guardado, out / "transcript.json")
            print(f"   [cache] transcricao reaproveitada ({chave[:16]})")
        else:
            run([HF, "transcribe", "avatar.mp4", "--engine", "parakeet", "--json", "-d", "."], cwd=out)
            pasta_cache.mkdir(parents=True, exist_ok=True)
            shutil.copy(out / "transcript.json", guardado)
    return json.loads((out / "transcript.json").read_text(encoding="utf-8"))


def palavras_da_timeline(palavras):
    """As palavras do alinhamento único, `[(início, fim, palavra do roteiro)]`, no formato do overlay:
    `{text, start, end, kw}`, como o `build_timeline.align_words` devolvia (ênfase `*...*` vira `kw`)."""
    textos, kws = build_timeline._strip_kw_markers([t for _s, _e, t in palavras])
    return [{"text": tx, "start": s, "end": e, "kw": kw}
            for (s, e, _t), tx, kw in zip(palavras, textos, kws)]


def alinhar_palavras(blocks, transcript):
    """Casa a fala do roteiro (grafia certa) com os tempos do transcript: uma palavra por palavra."""
    narr_words = []
    for b in blocks:
        narr_words += b["narr"].split()
    return build_timeline.align_words(narr_words, transcript)


def marcar_kw(words, frases):
    """Palavra-chave por frase (autoria por anúncio): marca `kw` em toda ocorrência da frase."""
    for phrase in frases:
        p_norm = [norm(t) for t in phrase.split()]
        w_norm = [norm(w["text"]) for w in words]
        for i in range(len(w_norm) - len(p_norm) + 1):
            if w_norm[i:i + len(p_norm)] == p_norm:
                for k in range(len(p_norm)):
                    words[i + k]["kw"] = True
