#!/usr/bin/env python3
"""Posicao do ROSTO no avatar, por deteccao, nao por fracao.

Calibrar por fracao da pessoa ou do painel nao funciona porque cada look tem
enquadramento proprio: o `oficial_13` e um close mais fechado e a mesma fracao que
acerta o `neon_creme` corta as sobrancelhas dele. O rosto e o que precisa estar no
quadro, entao e nele que se ancora.
"""
import subprocess, sys, tempfile, os
import cv2
import numpy as np

def caixa_rosto(video, amostras=(6, 14, 22, 30)):
    casc = cv2.CascadeClassifier(cv2.data.haarcascades +
                                 "haarcascade_frontalface_default.xml")
    d = tempfile.mkdtemp()
    caixas = []
    for t in amostras:
        p = os.path.join(d, f"f{t}.png")
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", video,
                            "-frames:v", "1", p], capture_output=True)
        if r.returncode != 0 or not os.path.exists(p):
            continue
        img = cv2.imread(p)
        if img is None:
            continue
        cinza = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        achados = casc.detectMultiScale(cinza, 1.1, 5, minSize=(120, 120))
        if len(achados):
            x, y, w, h = max(achados, key=lambda b: b[2] * b[3])
            caixas.append((y, h))
    if not caixas:
        return None
    ys = [c[0] for c in caixas]; hs = [c[1] for c in caixas]
    return int(np.median(ys)), int(np.median(hs))

if __name__ == "__main__":
    for v in sys.argv[1:]:
        c = caixa_rosto(v)
        nome = os.path.basename(v).replace("_avatar.mp4", "")
        if not c:
            print(f"  {nome:24s} rosto NAO detectado"); continue
        y, h = c
        print(f"  {nome:24s} rosto y {y} a {y+h} (altura {h}, centro {y+h//2})")
