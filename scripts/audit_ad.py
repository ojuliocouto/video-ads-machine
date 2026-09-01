"""Auditoria pre-entrega de um ad v2: deriva os pontos criticos do index.html,
extrai os frames com ffmpeg e roda os checks numericos. A LEITURA dos frames com os
proprios olhos continua obrigatoria (o script so prepara e aponta o que conferir).

Uso: python3 audit_ad.py <render-dir>   (ex: render-ad03-espuma)
Gera <render-dir>/audit_out/ com os frames + um manifest.txt do que checar em cada um.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ADJ_GAP = 0.6


def vdur(f):
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(f)], capture_output=True, text=True).stdout.strip()
    return float(o) if o else 0.0


def frame(mp4, t, out):
    subprocess.run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(mp4), "-frames:v", "1",
                    str(out), "-v", "error"], check=False)


def main(render_dir):
    d = Path(render_dir)
    if not d.is_dir():
        d = Path.cwd() / render_dir
    html = (d / "index.html").read_text()
    mp4 = next(iter(d.glob("*_9x16.mp4")), None)
    if not mp4:
        sys.exit(f"sem mp4 9x16 em {d}")
    out = d / "audit_out"
    out.mkdir(exist_ok=True)

    total = vdur(mp4)
    # brolls (do array JS: start/dur em ordem cronologica)
    m = re.search(r"const BROLLS = (\[.*?\]);", html, re.S)
    brolls = json.loads(m.group(1)) if m else []
    # hook
    hm = re.search(r'id="hook" class="clip" data-start="0" data-duration="([0-9.]+)"', html)
    hook_dur = float(hm.group(1)) if hm else 2.5
    # wipes (tempos do fill da grade)
    wipes = sorted(set(float(x) for x in re.findall(
        r'grid-cell",\s*\{ scale: 1.*?\}, ([0-9.]+)\);', html)))
    # legendas
    grps = [(float(a), float(b)) for a, b, _ in re.findall(
        r'data-g-start="([0-9.]+)" data-g-end="([0-9.]+)">(.*?)</div>', html, re.S)]

    checks = []  # (timestamp, label, o_que_conferir)
    # 1) opening / hook
    checks.append((1.0, "opening_1.0", "insert de fundo (NAO avatar), hook legivel, SEM selo"))
    checks.append((min(2.5, hook_dur - 0.4), "opening_mid", "hook AINDA legivel sobre o insert"))
    checks.append((max(0.5, hook_dur - 0.5), "hook_late", "hook ainda visivel (fim dos ~4s)"))
    checks.append((round(hook_dur + 0.4, 2), "hook_gone", "hook dissolveu; avatar de volta"))
    # 2) fronteiras de inserts COLADOS (gap <= ADJ_GAP): risco de vazar avatar
    for i in range(1, len(brolls)):
        gap = brolls[i]["start"] - (brolls[i - 1]["start"] + brolls[i - 1]["dur"])
        if gap <= ADJ_GAP:
            t = round(brolls[i]["start"] + 0.05, 2)
            checks.append((t, f"insert_colado_{i}", "b-roll fullscreen, ZERO rosto do avatar entre inserts"))
    # 3) trocas de legenda (amostra: inicio de alguns grupos no meio do video)
    seen = 0
    for gs, ge in grps:
        if 11 < gs < total - 6 and seen < 4:
            checks.append((round(gs + 0.03, 2), f"troca_legenda_{seen+1}", "UMA legenda por vez, sem empilhar"))
            seen += 1
    # 4) wipes
    for i, w in enumerate(wipes):
        checks.append((round(w + 0.2, 2), f"wipe_{i+1}", "transicao unica e limpa, sem piscar 2x, sem preto preso"))
    # 5) fim / CTA
    checks.append((round(total - 1.5, 2), "cta", "pill + logo no rodape; cauda do audio inteira"))

    # extrair frames
    manifest = [f"AUDIT {d.name}  |  dur={total:.2f}s  |  hook_dur={hook_dur:.2f}s  |  {len(brolls)} brolls  |  wipes={wipes}", ""]
    for t, label, what in sorted(checks):
        fn = out / f"{label}_{t:.2f}.jpg"
        frame(mp4, t, fn)
        manifest.append(f"  t={t:6.2f}s  {label:20s} -> {what}")
    (out / "manifest.txt").write_text("\n".join(manifest))

    # checks numericos
    print("\n".join(manifest))
    print("\n=== checks numericos ===")
    ov = subprocess.run([sys.executable, str(__import__("caminhos").CODIGO / "check_overlap.py"), str(d)],
                        capture_output=True, text=True)
    print(ov.stdout.strip())
    print(f"duracao: {total:.2f}s")
    print(f"\nframes em {out} (LEIA cada um com os proprios olhos antes de aprovar)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
