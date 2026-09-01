#!/usr/bin/env python3
"""Renderiza o quadro FINAL de cada insert (recorte + fundo desfocado) e monta uma folha.

Existe pra pegar erro de enquadramento ANTES do build de 25 minutos: o padrao dos meus
erros e mexer no recorte e so descobrir o estrago no video pronto.
"""
import io, json, os, subprocess, sys
from PIL import Image, ImageDraw

SC = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(SC, "conferencia")
os.makedirs(OUT, exist_ok=True)
W, H = 1080, 1920


def render(cfg, t, dst):
    src = cfg["file"]
    crop = cfg.get("crop") or cfg.get("split_crop")
    cropf = f"crop={crop}," if crop else ""
    zm = float(cfg.get("zoom", 1.0) or 1.0)
    ex = float(cfg.get("exposicao", 0) or 0)
    eqf = f"eq=brightness={ex:.3f}:contrast={1 + ex * 0.6:.3f}," if abs(ex) >= 0.005 else ""
    if cfg.get("split"):
        # painel de cima do split (1080x980), preenchendo
        fc = (f"[0:v]{cropf}{eqf}scale=1080:980:force_original_aspect_ratio=increase,"
              f"crop=1080:980")
        alvo = (1080, 980)
    else:
        sw, sh = int(W * zm), int(H * zm)
        fc = (f"[0:v]{cropf}{eqf}split=2[a][b];"
              f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=24:1[bg];"
              f"[b]scale={sw}:{sh}:force_original_aspect_ratio=decrease,"
              f"crop='min(iw,{W})':'min(ih,{H})'[fg];"
              f"[bg][fg]overlay=(W-w)/2:(H-h)/2")
        alvo = (W, H)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", src,
                        "-frames:v", "1", "-filter_complex", fc, dst],
                       capture_output=True, text=True)
    if r.returncode == 0 and not os.path.exists(dst):
        # seek alem do fim devolve rc=0 e nao escreve nada: sem esta guarda o script
        # morre depois, na hora de abrir o arquivo, e some com a folha inteira
        print(f"   [sem quadro] {os.path.basename(src)} em {t:.1f}s (fonte mais curta)")
        return None
    if r.returncode != 0:
        print(f"   [ERRO ffmpeg] {os.path.basename(src)}: {r.stderr.strip()[:180]}")
        return None
    return alvo


def main():
    for ad in sys.argv[1:]:
        from caminhos import INPUTS as _IN
        P = str(_IN / f"{ad}v2_inserts.json")
        d = json.load(io.open(P, encoding="utf-8"))
        cels = []
        for nome, cfg in d.items():
            st = float(cfg.get("start", 0) or 0)
            for dt in (0.5, 5.0):
                p = os.path.join(OUT, f"{ad}_{abs(hash(nome)) % 10**6}_{dt}.png")
                if render(cfg, st + dt, p):
                    cels.append((nome, st + dt, p))
        if not cels:
            continue
        TH = 430
        ims = []
        for nome, t, p in cels:
            im = Image.open(p).convert("RGB")
            im = im.resize((int(im.width * TH / im.height), TH))
            dr = ImageDraw.Draw(im)
            rot = f"{nome[:26]} {t:.0f}s"
            dr.rectangle([0, 0, 8 * len(rot) + 10, 22], fill="black")
            dr.text((5, 5), rot, fill="yellow")
            ims.append(im)
        cw = max(i.width for i in ims)
        cols = min(6, len(ims))
        rows = (len(ims) + cols - 1) // cols
        sh = Image.new("RGB", (cw * cols, TH * rows), "#111")
        for i, im in enumerate(ims):
            sh.paste(im, ((i % cols) * cw, (i // cols) * TH))
        dst = os.path.join(OUT, f"folha_{ad}.png")
        sh.save(dst)
        print(f"{ad}: {len(ims)} quadros -> {dst}")


if __name__ == "__main__":
    main()
