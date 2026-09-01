#!/usr/bin/env python3
"""Corta TEMPO MORTO de um vídeo JÁ PRONTO, sem regerar avatar nem remontar.

Pergunta do Julio (17/08/2026): "nao era mais facil vc so cortar o video q vc ja fez?
ao inves de gastar credito do heygen pra gerar outro e ter um PUTA trabalho de refazer".
Ele estava certo, e o caminho caro custou US$ 5 de HeyGen mais 13 min de render por
uma pausa de 0,3s a mais.

QUANDO ESTE CAMINHO SERVE (barato: segundos, zero credito):
  ajuste de TEMPO em trecho onde ninguem fala e nada se move, tipo pausa longa demais.
  Cortando video e audio JUNTOS, tudo depois desliza igual: a legenda ja esta queimada
  no quadro, entao ela desliza junto e a sincronia se mantem sozinha.

QUANDO NAO SERVE (aí regerar e inevitavel):
  a fala mudou (palavra comida pelo higienizador, texto novo, ordem diferente). O
  lipsync foi construido em cima daquele audio; nao da pra costurar fala que nao existe.

Uso:
  python3 aparar_pausa.py <video.mp4> --em 11.5 --cortar 0.3 [--saida <out.mp4>]
  python3 aparar_pausa.py <video.mp4> --listar          # so mostra as pausas
"""
import subprocess
import sys
import re
from pathlib import Path

MARGEM = 0.10   # nunca cortar colado na borda da pausa, igual ao higienizador


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def dur(p):
    o = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", str(p)]).stdout.strip()
    return float(o) if o else 0.0


def pausas(video, db=-36, d=0.30):
    r = sh(["ffmpeg", "-v", "info", "-i", str(video), "-af",
            f"silencedetect=noise={db}dB:d={d}", "-f", "null", "-"]).stderr
    ini = [float(x) for x in re.findall(r"silence_start: ([\d.-]+)", r)]
    dus = [float(x) for x in re.findall(r"silence_duration: ([\d.]+)", r)]
    return list(zip(ini, dus))


def aparar(video, em, cortar, saida):
    """Remove `cortar` segundos a partir de `em`, do video E do audio juntos.

    Reencoda so porque corte exato em GOP exige; o custo e de segundos, nao de minutos.
    """
    d = dur(video)
    fim = em + cortar
    if fim >= d:
        sys.exit("APARAR: o corte passa do fim do video")
    fc = (f"[0:v]trim=0:{em},setpts=PTS-STARTPTS[v0];"
          f"[0:v]trim={fim},setpts=PTS-STARTPTS[v1];"
          f"[0:a]atrim=0:{em},asetpts=PTS-STARTPTS[a0];"
          f"[0:a]atrim={fim},asetpts=PTS-STARTPTS[a1];"
          f"[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]")
    r = sh(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-filter_complex", fc,
            "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18",
            "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(saida)])
    if r.returncode != 0:
        sys.exit("APARAR: ffmpeg falhou\n" + r.stderr[-500:])
    return dur(saida)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    video = Path(sys.argv[1]).expanduser()
    if not video.exists():
        sys.exit(f"APARAR: video nao existe: {video}")

    if "--listar" in sys.argv:
        print(f"pausas de {video.name} (duracao {dur(video):.1f}s):")
        for s, x in pausas(video):
            print(f"  {s:6.2f}s  dura {x:.2f}s")
        return

    if "--em" not in sys.argv or "--cortar" not in sys.argv:
        sys.exit("uso: aparar_pausa.py <video> --em <segundo> --cortar <segundos>")
    em = float(sys.argv[sys.argv.index("--em") + 1])
    cortar = float(sys.argv[sys.argv.index("--cortar") + 1])
    saida = (Path(sys.argv[sys.argv.index("--saida") + 1]).expanduser()
             if "--saida" in sys.argv else video.with_name(video.stem + "_aparado.mp4"))

    # so corta DENTRO de uma pausa, com margem: cortar em cima de fala emenda palavra
    dentro = [(s, x) for s, x in pausas(video, d=0.15)
              if s + MARGEM <= em and em + cortar <= s + x - MARGEM]
    if not dentro:
        print("APARAR: o trecho pedido NAO esta inteiramente dentro de uma pausa.")
        print("        Pausas disponiveis perto:")
        for s, x in pausas(video, d=0.15):
            if abs(s - em) < 3:
                print(f"          {s:.2f}s dura {x:.2f}s (pode cortar ate "
                      f"{max(0, x - 2*MARGEM):.2f}s a partir de {s + MARGEM:.2f}s)")
        sys.exit(1)

    antes = dur(video)
    depois = aparar(video, em, cortar, saida)
    print(f"OK {saida.name}: {antes:.2f}s -> {depois:.2f}s (cortou {antes-depois:.2f}s "
          f"em {em:.2f}s, dentro de uma pausa)")


if __name__ == "__main__":
    main()
