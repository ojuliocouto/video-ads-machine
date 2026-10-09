#!/usr/bin/env python3
"""Gate de CONTRASTE de TODO texto na tela contra o fundo local, medido no arquivo entregue (W5.X).

O nome ficou (o laudo e a capacidade C6 citam este gate), mas desde a W5.X ele mede o gancho, a legenda inteira
(inclusive a camada apagada do karaokê), o lettering e o CTA, pela régua de `gates/contraste_texto.py`:

    em toda amostra (5 por segundo), cada pedaço de texto tem contraste >= 4,5:1 entre a crista da letra e o fundo
    local (o anel de 4 a 12 px em volta dela, no percentil que apaga a letra), no QUADRO ENTREGUE. Só a dissolução
    de entrada ou de saída (0,15 s) de um texto que lê do outro lado fica de fora.

Nasceu (28/08/2026) da legenda branca sobre um mockup de página branca (1,52:1). Foi refeito na W5.X porque o render
real da W5.A passou com o gancho e a camada apagada ilegíveis, por quatro causas medidas no v1 (ver o docstring do
`contraste_texto`): tinta só com alfa >= 250, fundo pela média da faixa inteira (faixa pulada sob scrim), aprovação
pela mediana e uma amostra a cada 0,5 s com o CTA cortado. Uma reprova sem desculpa reprova o anúncio: texto que não
lê é pior que texto ausente (ocupa o lugar e não entrega).

Uso:
  gate-contraste-legenda.py <entregue.mp4> --overlay <ovl.mov> [--accel 1.35] [--a0 0.4] [--intervalo 0.2]
Saída 0 passa, 1 reprova, 2 insumo inválido.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gates import contraste_texto as C  # noqa: E402

PISO = C.PISO
INTERVALO_MAX = 0.25        # pelo menos 4 amostras por segundo


def _linha(p):
    return ("   t=%6.2fs  x%4d-%4d y%4d-%4d  %5.2f:1  (tinta %.3f, fundo %.3f)"
            % (p["t"], p["x0"], p["x1"], p["y0"], p["y1"], p["razao"], p["tinta"], p["fundo"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("entregue")
    ap.add_argument("--overlay", required=True)
    ap.add_argument("--accel", type=float, default=1.35)
    ap.add_argument("--a0", type=float, default=0.0,
                    help="deslocamento do overlay (o relogio.a0 da timeline): overlay = entregue x accel + a0")
    ap.add_argument("--intervalo", type=float, default=C.PASSO_S)
    ap.add_argument("--piso", type=float, default=PISO)
    ap.add_argument("--json", help="grava as medidas (reprovas, transições e o pior por amostra) neste arquivo")
    a = ap.parse_args(argv)
    passo = min(a.intervalo, INTERVALO_MAX)
    try:
        r = C.medir_video(a.entregue, a.overlay, a.accel, a.a0, passo=passo, piso=a.piso)
    except (OSError, ValueError) as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        return 2
    piores = []
    for t, pedacos in r["amostras"]:
        if pedacos:
            p = min(pedacos, key=lambda x: x["razao"])
            piores.append((t, p["razao"]))
    print("Entregue : %s" % Path(a.entregue).name)
    print("Amostras : %d (a cada %.2f s), %d pedaço(s) de texto medidos, deslocamento do vídeo %.3f s"
          % (len(r["amostras"]), passo, r["medidos"], r["deslocamento_s"]))
    if a.json:
        Path(a.json).write_text(json.dumps({"reprovas": r["reprovas"], "transicoes": r["transicoes"],
                                            "pior_por_amostra": piores, "passo_s": passo}, indent=1),
                                encoding="utf-8")
    if not r["medidos"]:
        print("\nREPROVA: nenhum texto medido. Ou o anúncio está sem texto, ou a régua ficou cega (confira o alfa "
              "do overlay e o relógio --accel/--a0).")
        return 1
    rz = sorted(x for _t, x in piores)
    print("Contraste: pior %.2f:1  mediana %.2f:1  (piso %.1f:1, o pior pedaço de cada amostra)"
          % (rz[0], rz[len(rz) // 2], a.piso))
    if r["transicoes"]:
        print("Dissolução (fora da conta): %d pedaço(s), de %.2f a %.2f s"
              % (len(r["transicoes"]), min(p["t"] for p in r["transicoes"]), max(p["t"] for p in r["transicoes"])))
    if r["reprovas"]:
        ts = sorted(set(p["t"] for p in r["reprovas"]))
        print("\nREPROVA: %d pedaço(s) de texto abaixo de %.1f:1 em %d amostra(s) (%.2f a %.2f s)"
              % (len(r["reprovas"]), a.piso, len(ts), ts[0], ts[-1]))
        for p in sorted(r["reprovas"], key=lambda x: (x["t"], x["razao"]))[:24]:
            print(_linha(p))
        return 1
    print("\nPASSA: todo texto lê contra o fundo em volta dele.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
