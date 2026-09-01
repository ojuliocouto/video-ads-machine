#!/usr/bin/env python3
"""Mixa os efeitos sonoros no ad final (item 1 do brief: som estratégico).

Uso: python3 mixar_sfx.py <video.mp4> <plano_ritmo.json> <accel> <saida.mp4>

Entra DEPOIS da aceleração (por isso recebe `accel`: os tempos do plano são de footage
1x e viram t/accel no arquivo final). Regras do banco de referências:
  - whoosh na ENTRADA de insert (nunca na volta pro avatar)
  - riser terminando na entrada do último bloco (a virada pro CTA)
  - máximo 1 efeito a cada 2,5s; em conflito, o primeiro vence
  - sutil: os wavs já saem calibrados (-14 a -10 dB de pico) e a voz não é tocada
"""
import json
import subprocess
import sys
from pathlib import Path

# (migracao 26/08/2026) era relativo ao proprio arquivo; som e fonte sao DADOS
from caminhos import ASSETS_V1  # noqa: E402
SOM = ASSETS_V1 / "som"
GAP_MIN = 2.5
RISER_DUR = 1.2


def eventos_de(plano, accel):
    """Lista (tempo_final, efeito) a partir do plano de ritmo."""
    segs = plano["segs"]
    # RISER PRIMEIRO (18/08/2026): ele e o evento estrategico (tensao antes da
    # virada/CTA) e estava sendo engolido por um whoosh vizinho. Agora ele reserva
    # o lugar e os whooshes e que respeitam a folga em volta dele.
    ult_bloco = segs[-1]["bloco"]
    t_virada = min(x["s"] for x in segs if x["bloco"] == ult_bloco) / accel
    t_riser = max(0.0, t_virada - RISER_DUR)
    evs = [(t_riser, "riser.wav")]
    ultimo = -GAP_MIN
    for a, b in zip(segs, segs[1:]):
        if b["tipo"] == "insert" and a["tipo"] != "insert":
            t = b["s"] / accel
            if t - ultimo >= GAP_MIN and abs(t - t_riser) >= GAP_MIN:
                evs.append((t, "whoosh.wav"))
                ultimo = t
    return sorted(evs)


def main():
    if len(sys.argv) != 5:
        print(__doc__)
        return 2
    video, plano_p, accel, saida = sys.argv[1:]
    accel = float(accel)
    plano = json.loads(Path(plano_p).read_text())
    evs = eventos_de(plano, accel)
    if not evs:
        print("nenhum evento; copiando sem mix")
        subprocess.run(["cp", video, saida], check=True)
        return 0

    ins, fc = [], []
    for k, (t, nome) in enumerate(evs):
        ins += ["-i", str(SOM / nome)]
        ms = int(round(t * 1000))
        fc.append(f"[{k+1}:a]adelay={ms}|{ms}[s{k}]")
    rot = "[0:a]" + "".join(f"[s{k}]" for k in range(len(evs)))
    fc.append(f"{rot}amix=inputs={len(evs)+1}:normalize=0:duration=first,"
              f"alimiter=limit=0.98[aout]")
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", video, *ins,
         "-filter_complex", ";".join(fc),
         "-map", "0:v", "-map", "[aout]", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", saida],
        capture_output=True, text=True)
    if r.returncode != 0:
        print("ffmpeg falhou:", r.stderr[-300:])
        return 1
    print(f"mixados {len(evs)} eventos: " +
          ", ".join(f"{t:.1f}s {n.split('.')[0]}" for t, n in evs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
