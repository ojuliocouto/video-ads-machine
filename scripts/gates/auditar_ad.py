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

Duas leituras mudaram na W4.B (generalização do produto):

  - A ACELERAÇÃO não é mais um número cravado no código (era 1,30 aqui contra 1,35 no build, e o
    take real roda a 1,2). Ela é a do projeto (`--projeto`, lida do projeto.json com o padrão do modo),
    ou passada à mão (`--aceleracao`). Sem nenhuma das duas o script recusa (exit 2): chutar a
    aceleração desloca todos os cortes conferidos.
  - O SILÊNCIO é medido na faixa de VOZ (`--voz`, a voz pré-mix que o mixer grava), não no arquivo
    final: a música sobe nas pausas (cama de 0,42) e mascara o silêncio. O limiar sai do passo que
    ele fiscaliza: PAUSA_MAX_TELA do higienizador (0,60 s, na tela, depois da aceleração) mais 0,10 s
    de tolerância. Silêncio na ponta (antes da primeira palavra ou depois da última) não é pausa
    entre falas e não conta.

Uso:
  python3 auditar_ad.py <video.mp4> --projeto <slug> [--estado _local] [--voz voz_pre_mix.wav]
                        [--timing timing.json] [--sheets]
  python3 auditar_ad.py <video.mp4> --aceleracao 1.35 [--voz ...] [--timing ...] [--sheets]
  saída 0 passa · 1 reprova no automático · 2 insumo inválido
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Raiz de scripts/ no sys.path: caminhos.py e a fonte unica dos caminhos do repo.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from caminhos import OUTPUT  # noqa: E402
import higienizar_audio  # noqa: E402

SCRATCH = os.path.dirname(os.path.abspath(__file__))

# O silêncio que reprova é o do passo que o produz: o higienizador deixa no máximo PAUSA_MAX_TELA (0,60 s
# no tempo da TELA, depois da aceleração) de pausa entre falas. 0,10 s de tolerância para a medição.
TOLERANCIA_SILENCIO_S = 0.10
LIMIAR_SILENCIO_S = higienizar_audio.PAUSA_MAX_TELA + TOLERANCIA_SILENCIO_S
SILENCIO_DB = -40.0
PONTA_S = 0.05     # silêncio que encosta no começo ou no fim do arquivo é ponta, não pausa


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


def aceleracao_do_projeto(slug, estado=None):
    """A aceleração do projeto.json (padrão do modo: 1,35 no avatar, 1,2 no take real e no one-shot).
    FileNotFoundError se o projeto não existe: nada de aceleração chutada."""
    from projeto import modelo, pastas
    return float(modelo.carregar(pastas.projeto(slug, estado).projeto_json)["aceleracao"])


def cortes_da_timeline(timeline):
    """Os cortes no vídeo FINAL, em segundos, a partir do timeline.json do projeto: o começo e o fim de
    cada trecho de insert, no relógio da footage convertido com (t - a0) / aceleração do próprio timeline."""
    accel = float(timeline["relogio"]["aceleracao"])
    a0 = float(timeline["relogio"].get("a0", 0.0))
    marcas = set()
    for seg in timeline.get("segmentos", []):
        if seg.get("tipo") == "insert":
            marcas.add(round((seg["s"] - a0) / accel, 2))
            marcas.add(round((seg["e"] - a0) / accel, 2))
    return sorted(m for m in marcas if m > 0)


def cortes_do_timing(timing, accel):
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


def _duracao(arquivo):
    o = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1",
            str(arquivo)]).stdout.strip()
    return float(o) if o else 0.0


def silencios_da_voz(voz, dur_min=None):
    """[(início, duração)] das pausas entre falas acima de `dur_min` (padrão LIMIAR_SILENCIO_S) na faixa de VOZ.

    Medido na voz sozinha: no arquivo final a cama de música sobe nas pausas e o silêncio some. O
    silêncio na ponta (antes da primeira palavra, depois da última) é ignorado: o rabo do arquivo
    carrega a cauda congelada e a respiração final, que não são pausa de fala.
    """
    dur_min = LIMIAR_SILENCIO_S if dur_min is None else dur_min
    p = sh(["ffmpeg", "-v", "info", "-nostdin", "-i", str(voz), "-vn", "-af",
            f"silencedetect=n={SILENCIO_DB:g}dB:d={dur_min:.3f}", "-f", "null", "-"])
    total = _duracao(voz)
    achados, ini = [], None
    for l in p.stderr.splitlines():
        m = re.search(r"silence_start:\s*(-?[\d.]+)", l)
        if m:
            ini = max(float(m.group(1)), 0.0)
            continue
        m = re.search(r"silence_end:\s*(-?[\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)", l)
        if m and ini is not None:
            fim = float(m.group(1))
            if ini > PONTA_S and fim < total - PONTA_S:
                achados.append((ini, float(m.group(2))))
            ini = None
    return achados


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


def _aceleracao(args):
    """(aceleração, de onde veio, projeto ou None). Levanta SystemExit(2) sem nenhuma fonte."""
    if args.aceleracao is not None:
        return args.aceleracao, "explícita", None
    if args.projeto:
        from projeto import pastas
        try:
            pj = pastas.projeto(args.projeto, args.estado)
            return aceleracao_do_projeto(args.projeto, args.estado), "projeto %s" % args.projeto, pj
        except FileNotFoundError:
            print(f"ERRO de insumo: o projeto {args.projeto} não tem projeto.json", file=sys.stderr)
        except ValueError as e:
            print(f"ERRO de insumo: {e}", file=sys.stderr)
        raise SystemExit(2)
    print("ERRO de insumo: sem a aceleração não há como localizar os cortes. Passe --projeto <slug> "
          "(lê do projeto.json) ou --aceleracao <fator>. O 1,30 que ficava cravado aqui estava errado.",
          file=sys.stderr)
    raise SystemExit(2)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Auditoria automática de um vídeo ad, antes de entregar.")
    ap.add_argument("video")
    ap.add_argument("--projeto", help="slug do projeto: a aceleração vem do projeto.json")
    ap.add_argument("--estado", help="pasta _local (padrão: a do repo)")
    ap.add_argument("--aceleracao", type=float, help="fator de aceleração da entrega, à mão")
    ap.add_argument("--voz", help="voz pré-mix, onde o silêncio é medido (padrão: a do projeto; "
                                  "sem ela, o áudio do próprio vídeo)")
    ap.add_argument("--timing", help="timing.json do motor antigo (padrão: o timeline.json do projeto, "
                                     "ou DADOS/output/timing.json)")
    ap.add_argument("--sheets", action="store_true", help="gera as folhas de contato para leitura com o olho")
    args = ap.parse_args(argv)
    video = args.video
    if not os.path.exists(video):
        print(f"ERRO de insumo: não existe: {video}", file=sys.stderr)
        return 2
    try:
        accel, origem, pj = _aceleracao(args)
    except SystemExit as e:
        return e.code

    info = probe(video)
    print(f"\n{'='*74}\nAUDITORIA  {os.path.basename(video)}\n{'='*74}")
    print(f"{info['w']}x{info['h']}  {info['fps']:.2f}fps  {info['dur']:.2f}s  {info['frames']} frames")
    print(f"aceleração {accel:g} ({origem})\n")

    vals = yavg(video)
    reprovas = []

    if args.timing:
        cortes = cortes_do_timing(args.timing, accel)
    elif pj is not None and pj.timeline.is_file():
        cortes = cortes_da_timeline(json.load(open(pj.timeline, encoding="utf-8")))
    else:
        cortes = cortes_do_timing(str(OUTPUT / "timing.json"), accel)
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

    voz = args.voz
    if voz is None and pj is not None:
        from audio import mix_final
        if mix_final.caminho_voz_ref(pj).is_file():
            voz = str(mix_final.caminho_voz_ref(pj))
    if voz is None:
        print("  [i]  sem faixa de voz separada (--voz): silêncio medido no áudio do próprio vídeo, "
              "onde a música pode mascarar a pausa")
    fonte_silencio = voz or video
    si = silencios_da_voz(fonte_silencio)
    limiar = f"{LIMIAR_SILENCIO_S:.2f}s".replace(".", ",")
    if si:
        for ini, dur in si:
            print(f"  [X] SILENCIO   em {ini:6.2f}s por {dur:.2f}s (limiar {limiar} = PAUSA_MAX_TELA "
                  f"{higienizar_audio.PAUSA_MAX_TELA:.2f} + {TOLERANCIA_SILENCIO_S:.2f})")
        reprovas.append(f"{len(si)} silencio(s) acima de {limiar} na faixa de voz")
    else:
        print(f"  [ok] nenhum silêncio acima de {limiar} entre as falas")

    print(f"  [i]  {loudness(video)}")

    if args.sheets:
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
