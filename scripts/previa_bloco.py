#!/usr/bin/env python3
"""PREVIA RAPIDA de blocos (17/08/2026, "nao posso esperar 1h pra um render").

Renderiza SO os blocos pedidos, em resolucao reduzida, pra decidir enquadramento,
split, crop e lettering sem pagar o render inteiro. Um build completo leva 10 a 13
minutos; uma previa de dois blocos leva menos de um minuto.

NAO substitui o build: nao tem overlay de texto do v2, nao tem legenda nem gate.
Serve pra responder "esse split ficou bom?" antes de gastar o render de verdade.

Uso:
  python3 previa_bloco.py <ad> <look> --blocos 0,6
  python3 previa_bloco.py jh13 espuma_roxa --blocos 0,3,5 --escala 0.4
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from caminhos import V1, CODIGO  # noqa: E402
from caminhos import V2L  # noqa: E402  (era o proprio dir; agora e o _local, que guarda o estado)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    ad, look = sys.argv[1], sys.argv[2]
    blocos = []
    if "--blocos" in sys.argv:
        blocos = [int(x) for x in sys.argv[sys.argv.index("--blocos") + 1].split(",")]
    if not blocos:
        sys.exit("informe --blocos 0,6")
    escala = float(sys.argv[sys.argv.index("--escala") + 1]) if "--escala" in sys.argv else 0.5

    pref = "" if str(ad).startswith("jh") else "ad"
    avatar = V1 / "inputs" / f"{pref}{ad}v2_{look}_avatar.mp4"
    roteiro = V1 / "inputs" / f"{pref}{ad}v2_leva.txt"
    inserts = V1 / "inputs" / f"{pref}{ad}v2_inserts.json"
    for p in (avatar, roteiro, inserts):
        if not p.exists():
            sys.exit(f"PREVIA: falta {p}")

    saida = V2L / f"_previa_{ad}"
    saida.mkdir(exist_ok=True)

    env = dict(os.environ)
    env.update({
        "VAM_AVATAR": str(avatar), "VAM_ROTEIRO": str(roteiro),
        "VAM_INSERTS_JSON": str(inserts), "VAM_BAKE_LETTERING": "0", "CAP": "0",
        "VAM_OUT": str(saida / "previa.mp4"),
        # o motor imprime os spans em diagnostico; a previa reusa a mesma montagem
        "VAM_SO_BLOCOS": ",".join(str(b) for b in blocos),
        "VAM_ESCALA_PREVIA": str(escala),
    })
    print(f"previa dos blocos {blocos} a {int(escala*100)}% de escala...")
    r = subprocess.run([sys.executable, str(CODIGO / "produzir_roteiro.py")],
                       capture_output=True, text=True, env=env)
    saida_txt = (r.stdout or "") + (r.stderr or "")
    # o motor ainda nao le VAM_SO_BLOCOS: enquanto isso, extrai os blocos do render
    # completo de diagnostico. Mesmo assim evita overlay, legenda, aceleracao e gate.
    spans = []
    for linha in saida_txt.split("\n"):
        partes = linha.split()
        if len(partes) >= 4 and partes[0].isdigit():
            try:
                ini, fim = partes[2].replace("s", "").split("-")
                spans.append((int(partes[0]), float(ini), float(fim)))
            except ValueError:
                continue
    prev = saida / "previa.mp4"
    if not prev.exists():
        print(saida_txt[-800:])
        sys.exit("PREVIA: motor nao gerou arquivo")
    for b in blocos:
        alvo = [s for s in spans if s[0] == b]
        if not alvo:
            print(f"  bloco {b}: span nao encontrado")
            continue
        _, ini, fim = alvo[0]
        out = saida / f"bloco_{b:02d}.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(ini),
                        "-t", str(fim - ini), "-i", str(prev),
                        "-vf", f"scale=iw*{escala}:-2", "-c:v", "libx264", "-crf", "26",
                        str(out)], check=False)
        print(f"  bloco {b}: {out}")
    print(f"\nprevias em {saida}")


if __name__ == "__main__":
    main()
