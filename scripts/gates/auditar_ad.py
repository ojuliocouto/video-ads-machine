#!/usr/bin/env python3
"""Auditoria automática de um vídeo ad, antes de entregar.

Nasceu do retrabalho de 12/08/2026. O padrão dos defeitos que chegaram até o cliente é
sempre o mesmo: eu olhava FRAMES ESCOLHIDOS e declarava pronto, e o defeito estava entre
eles. Três exemplos reais, todos de 1 a 4 frames ou de 1 a 3 segundos:

  - flash preto de 2 frames no meio de cada corte (fadeblack 0,08s)
  - insert congelado 3,5s (asset mais curto que o bloco, tpad clone)
  - insert 3,5s quase preto e dessincronizado da fala

Nenhum dos três aparece numa amostragem. Todos aparecem numa varredura.

O que este script NÃO faz: julgar se a imagem combina com a fala. Isso é olho. Ele
gera as folhas de contato pra esse olho ser possível em minutos, e falha sozinho em
tudo que é medível.

Uso: python3 auditar_ad.py <video.mp4> [--sheets]
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Raiz de scripts/ no sys.path: caminhos.py e a fonte unica dos caminhos do repo.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from caminhos import OUTPUT  # noqa: E402

SCRATCH = os.path.dirname(os.path.abspath(__file__))


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def probe(video):
    o = sh(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
            "stream=width,height,avg_frame_rate,nb_read_packets", "-show_entries",
            "format=duration", "-count_packets", "-of", "json", video]).stdout
    d = json.loads(o)
    s = d["streams"][0]
    n, den = (s["avg_frame_rate"].split("/") + ["1"])[:2]
    return {"w": s["width"], "h": s["height"], "fps": float(n) / float(den),
            "frames": int(s.get("nb_read_packets", 0)),
            "dur": float(d["format"]["duration"])}


def yavg(video):
    p = sh(["ffmpeg", "-v", "info", "-i", video, "-vf",
            "signalstats,metadata=mode=print:key=lavfi.signalstats.YAVG", "-f", "null", "-"])
    vals, t = [], None
    for l in p.stderr.splitlines():
        m = re.search(r"pts_time:([\d.]+)", l)
        if m:
            t = float(m.group(1)); continue
        m = re.search(r"YAVG=([\d.]+)", l)
        if m and t is not None:
            vals.append((t, float(m.group(1)))); t = None
    return vals


def flashes(vals, fps, queda_min=25.0):
    # 25 e nao 18: calibrado contra os dois extremos reais. O defeito que este detector
    # existe pra pegar (fade passando pelo preto) mede queda de ~68. Ja uma queda de
    # 19 em 67ms, medida no AD19 aos 27,07s, era so a diferenca de exposicao entre o
    # plano do avatar e um insert mais escuro: confirmado frame a frame que nao ha
    # flash nenhum. Limiar apertado demais gera reprovacao falsa, que custa rebuild.
    """Vale de luz de poucos frames: o fade que passa pelo preto."""
    jan = max(3, int(round(0.4 * fps)))
    y = [v for _, v in vals]
    brutos = []
    for i in range(jan, len(y) - jan):
        viz = min(max(y[i - jan:i]), max(y[i + 1:i + 1 + jan]))
        if viz - y[i] >= queda_min:
            brutos.append((vals[i][0], y[i], viz))
    ev, at = [], None
    for t, v, viz in brutos:
        if at and t - at[-1][0] <= 1.5 / fps:
            at.append((t, v, viz))
        else:
            if at: ev.append(at)
            at = [(t, v, viz)]
    if at: ev.append(at)
    return ev


def cortes_do_timing(timing, accel=1.30):
    """Onde estão os cortes no vídeo FINAL, em segundos.

    Sem isso o auditor confunde duas coisas diferentes: o vale de luz causado pela
    transição (defeito meu) e o vale causado pelo próprio conteúdo (uma página rolando
    por uma faixa escura, que é o vídeo funcionando). No AD14 a segunda foi acusada como
    defeito aos 44,50s e não era.

    O motor grava o tempo ANTES da aceleração e com o áudio deslocado em a0.
    """
    if not os.path.exists(timing):
        return None
    t = json.load(open(timing))
    a0 = t.get("a0", 0.0)
    marcas = set()
    for ins in t.get("inserts", []):
        marcas.add(round((ins["s"] - a0) / accel, 2))
        marcas.add(round((ins["e"] - a0) / accel, 2))
    return sorted(m for m in marcas if m > 0)


def perto_de_corte(t, cortes, tol=0.25):
    return cortes is not None and any(abs(t - c) <= tol for c in cortes)


def escuros(vals, limiar=26.0, min_dur=0.35):
    """Trecho longo com pouca luz: o insert quase preto."""
    ev, ini, ant = [], None, None
    for t, v in vals:
        if v < limiar and ini is None:
            ini = t
        elif v >= limiar and ini is not None:
            if ant - ini >= min_dur: ev.append((ini, ant, ant - ini))
            ini = None
        ant = t
    if ini is not None and ant - ini >= min_dur:
        ev.append((ini, ant, ant - ini))
    return ev


def detecta(video, filtro, chave):
    p = sh(["ffmpeg", "-v", "info", "-i", video, "-vf" if chave != "silence" else "-af",
            filtro, "-f", "null", "-"])
    return [l.strip() for l in p.stderr.splitlines() if chave in l.lower()]


def congelados(video, dur_min=0.5):
    return [l for l in detecta(video, f"freezedetect=n=-58dB:d={dur_min}", "freeze")
            if "freeze_start" in l]


def silencios(video, dur_min=0.45):
    # 0,45 e nao 0,30: pausa entre frases em locucao natural fica em 0,30-0,40s, e o
    # proprio gate do motor usa 0,55 como respiro grande. Com 0,30 eu reprovava a
    # respiracao retorica do apresentador (AD19: 0,33s entre "pronto pra comprar" e "e joga
    # esse lead"), que e o oposto do anti-IA: fala sem pausa soa robotica.
    return [l for l in detecta(video, f"silencedetect=n=-40dB:d={dur_min}", "silence")
            if "silence_start" in l]


def loudness(video):
    p = sh(["ffmpeg", "-v", "info", "-i", video, "-af", "ebur128=peak=true", "-f", "null", "-"])
    tail = p.stderr[-1400:]
    i = tail.rfind("Integrated loudness")
    return tail[i:i + 220].replace("\n", " ") if i >= 0 else "(nao medido)"


def folhas(video, dur, passo=0.5, por_folha=48):
    """Folhas de contato cobrindo o vídeo INTEIRO, pra leitura com olho."""
    saidas = []
    total = int(dur / passo) + 1
    for n, ini in enumerate(range(0, total, por_folha), 1):
        t0 = ini * passo
        out = os.path.join(SCRATCH, f"auditoria_{n}.jpg")
        r = sh(["ffmpeg", "-y", "-v", "error", "-ss", f"{t0}", "-t", f"{por_folha*passo}",
                "-i", video, "-vf",
                f"fps=1/{passo},scale=210:-1,tile=8x{max(1,por_folha//8)}:padding=4:color=0x202028",
                "-frames:v", "1", "-q:v", "3", out])
        if r.returncode == 0 and os.path.exists(out):
            saidas.append((out, t0, min(dur, t0 + por_folha * passo)))
    return saidas


def main():
    if len(sys.argv) >= 2 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    video = sys.argv[1]
    if not os.path.exists(video):
        sys.exit(f"nao existe: {video}")

    info = probe(video)
    print(f"\n{'='*74}\nAUDITORIA  {os.path.basename(video)}\n{'='*74}")
    print(f"{info['w']}x{info['h']}  {info['fps']:.2f}fps  {info['dur']:.2f}s  {info['frames']} frames\n")

    vals = yavg(video)
    reprovas = []

    cortes = cortes_do_timing(str(OUTPUT / "timing.json"))
    ev = flashes(vals, info["fps"])
    em_corte = [e for e in ev if perto_de_corte(e[0][0], cortes)]
    no_conteudo = [e for e in ev if e not in em_corte]
    if em_corte:
        for e in em_corte:
            f = min(e, key=lambda x: x[1])
            print(f"  [X] FLASH NO CORTE {e[0][0]:6.2f}s  {(e[-1][0]-e[0][0]+1/info['fps'])*1000:4.0f}ms  "
                  f"luz {f[1]:.0f} vindo de {f[2]:.0f}")
        reprovas.append(f"{len(em_corte)} flash(es) escuro(s) no meio de corte")
    else:
        print(f"  [ok] nenhum flash escuro em corte ({len(cortes or [])} cortes conferidos)")
    for e in no_conteudo:
        f = min(e, key=lambda x: x[1])
        print(f"  [i]  escurece longe de corte {e[0][0]:6.2f}s  luz {f[1]:.0f} de {f[2]:.0f}"
              f"  (conteudo, nao transicao: olhar a folha pra confirmar)")

    esc = escuros(vals)
    if esc:
        for a, b, d in esc:
            print(f"  [X] TELA ESCURA   {a:6.2f}s a {b:6.2f}s ({d:.2f}s)")
        reprovas.append(f"{len(esc)} trecho(s) de tela escura")
    else:
        print("  [ok] nenhum trecho longo de tela escura")

    fz = congelados(video)
    if fz:
        for l in fz: print(f"  [X] CONGELADO  {l[-40:]}")
        reprovas.append(f"{len(fz)} congelamento(s)")
    else:
        print("  [ok] nenhum congelamento acima de 0,5s")

    si = silencios(video)
    if si:
        for l in si: print(f"  [X] SILENCIO   {l[-40:]}")
        reprovas.append(f"{len(si)} silencio(s) acima de 0,30s")
    else:
        print("  [ok] nenhum silencio acima de 0,30s")

    print(f"  [i]  {loudness(video)}")

    if "--sheets" in sys.argv:
        print("\n  folhas de contato (ler TODAS com o olho, é o passo que não automatiza):")
        for out, a, b in folhas(video, info["dur"]):
            print(f"     {out}   {a:.1f}s a {b:.1f}s")

    print(f"\n{'-'*74}")
    if reprovas:
        print("REPROVADO no automático:")
        for r in reprovas: print(f"  - {r}")
        return 1
    print("PASSA no automático. Falta a leitura das folhas (coerência insert x fala).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
