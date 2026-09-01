#!/usr/bin/env python3
"""Acelera o vídeo final (passo PADRÃO do pipeline, pedido recorrente do Júlio).

Anúncio fica mais dinâmico/retentivo acelerado. Fator padrão 1.2x (a legenda tay
é calibrada pra isso: MIN_DUR 0.22s -> ~0.18s no final). Acelera vídeo (setpts) e
áudio (atempo, preserva o pitch = voz natural, só mais rápida) em sincronia.

Uso: python3 acelerar.py <in.mp4> <out.mp4> [fator]
     fator default = env FATOR ou 1.2
"""
import os, sys, subprocess

def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, out = sys.argv[1], sys.argv[2]
    fator = float(sys.argv[3]) if len(sys.argv) > 3 else float(os.environ.get("FATOR", 1.2))
    # atempo aceita 0.5..2.0 direto; acima disso encadear. Aqui 1.2 ok.
    fc = f"[0:v]setpts=PTS/{fator},colorspace=all=bt709:iall=bt709:fast=1[v];[0:a]atempo={fator}[a]"
    r = subprocess.run(["ffmpeg","-y","-i",src,"-filter_complex",fc,
        "-map","[v]","-map","[a]","-c:v","libx264","-crf","18","-pix_fmt","yuv420p",
        "-colorspace","bt709","-color_primaries","bt709","-color_trc","bt709","-color_range","tv",
        "-c:a","aac","-b:a","160k","-movflags","+faststart",out],
        capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ERRO acelerar\n{r.stderr[-800:]}")
    def dur(f):
        o = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
            "-of","default=nw=1:nk=1",f], capture_output=True, text=True).stdout.strip()
        return float(o)
    print(f"acelerado {fator}x: {dur(src):.2f}s -> {dur(out):.2f}s  ({out})")

if __name__ == "__main__":
    main()
