#!/usr/bin/env python3
"""Pipeline composite v2-real: footage do v1 (avatar+inserts+wipes+grade, SEM texto) +
camada de texto REAL do v2 (caption/lettering/hook/cta em HTML/CSS) renderizada com alpha
e composta por cima. Resolve o conflito v1(wipe certo)/v2(texto certo). Validado no ad08 neon.

Uso: python3 build_composite.py <ad> <look> <fmt>
  ad   = ad07|ad08|ad09|ad10
  look = selfie_neon|espuma_roxa
  fmt  = 9x16 ou 1x1

1x1: o v1 nao tem canvas quadrado proprio e a gravacao do Thales e fechada demais no
rosto (feita pra 9:16): um crop reto 1080x1920->1080x1080 sempre deixa o queixo em
~40-45% do quadro (proporcao natural da gravacao, testado com varios offsets/alturas de
crop, nao da pra fugir disso so cropando), entao o CTA final colidia com a boca.
Fix (decisao do Julio, 20/07): ZOOM-OUT com fundo desfocado nas laterais. Recorta uma
janela ALTA (CROP_H_1X1 px) do footage 1080x1920 partindo de CROP_Y_1X1, ai ENCOLHE essa
janela pra caber nos 1080x1080 (da mais folga vertical: mais peito/camisa visivel abaixo
do queixo) e centraliza sobre um fundo desfocado (mesmo frame, blur+cover) que preenche
as laterais. O #cta do template reel-editorial-1x1 tambem foi recalibrado (bottom:300px
-> 180px) pra descer mais perto do logo, ja que mesmo com a folga extra do zoom-out o
queixo natural da gravacao nao sobe de ~40-45%.

Saidas em ~/video-ads-machine/output/:
  <ad>_<look>_v2composite_<fmt>.mp4  (final acelerado 1.2x)
  <ad>_<look>_v2composite_<fmt>_whatsapp.mp4  (720p ~4MB)
"""
import json, os, subprocess, sys, math
from pathlib import Path

from caminhos import V1, CODIGO  # noqa: E402
from caminhos import V2  # noqa: E402
from caminhos import V2L  # noqa: E402
HF = str(V2 / "node_modules" / ".bin" / "hyperframes")
# Historico da aceleracao (04/08/2026): 1.2 -> 1.3 (Julio) -> 1.56 (Jhenifer pediu
# "mais uma aceleradinha de 1.2x" EM CIMA do 1.3, e multiplicou) -> 1.25 (Julio,
# achando que estava em 1.3). Em 1.25 o video vai pra ~78s: mais longo que os 75s
# que a Jhenifer tinha achado grande. Avisado a ele; 1.25 e a decisao dele.
ACCEL = 1.35
# cauda do arquivo final, DEPOIS da aceleracao (por isso nao e o TAIL_PAD do overlay,
# que o `shortest=1` do composite descartava): segura o ultimo quadro com o CTA na
# tela em vez de cortar na ultima silaba.
# CAUDA CONGELADA no fim do entregue, aplicada DEPOIS da aceleracao. Consequencia que
# ja enganou uma auditoria inteira (19/08/2026): a duracao do entregue NAO e
# footage/ACCEL, e sim footage/ACCEL + TAIL_FINAL. Dividir a duracao total pela duracao
# do footage da 1,3421 e parece que ACCEL esta errado. Nao esta: pareando os 27 cortes
# do footage com os do entregue, o fator 1,35 alinha com erro medio de 0,087s e o
# 1,3421 com 0,190s. Para converter INSTANTE de footage para entregue use ACCEL; a
# cauda so afeta a duracao TOTAL.
TAIL_FINAL = 0.45
# zoom-out+blur pro 1x1 (calibrado visualmente no ad08 neon, 20/07): janela alta cropada
# do footage 1080x1920, encolhida pra caber em 1080x1080 (mantem full altura), centralizada
# sobre fundo desfocado. CROP_H=1500 mantem cabelo/testa inteiros com folga boa pro peito.
CROP_Y_1X1 = 250
CROP_H_1X1 = 1500

# looks da leva 2: os 3 de PLANO MEDIO. O Avatar V deforma a boca em close
# (o antigo espuma_roxa era close: "o Thales ta igual o coringa"), entao a leva 2
# so usa plano medio. Ver reference-avatares-heygen-thales.
# FONTE UNICA: o mesmo dicionario que nomeia o config no ads_v2_configs. Antes era uma
# copia aqui, e look novo precisava ser escrito nos dois lugares. Nao foi, e o jh15
# quebrou com KeyError 'neon_creme' DEPOIS de gastar o avatar do HeyGen e passar no gate
# de fidelidade. A geracao de config la esta protegida por __main__, entao importar e
# so leitura de dado.
from ads_v2_configs import LOOKS as LK
import cache_overlay
SUFFIX = {"9x16": "", "1x1": "_1x1"}


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.exit(f"ERRO em: {' '.join(str(c) for c in cmd)}\n{r.stderr[-1500:]}")
    return r


def vdur(f):
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(f)], capture_output=True, text=True).stdout.strip()
    return float(o) if o else 0.0


LUFS_ALVO, TP_ALVO, LRA_ALVO = -14.0, -1.5, 11.0


def normalizar_loudness(video: Path) -> Path:
    """Normaliza o audio pra -14 LUFS (alvo das plataformas) sem reencodar o video.

    Dois passes: o 1o MEDE (loudnorm print_format=json), o 2o APLICA os valores
    medidos. Single-pass so estima e erra o alvo em varios LU; somar ganho puro
    estouraria o pico. O video vai com -c:v copy, entao nao ha perda de qualidade
    nem custo de re-encode.
    """
    import re as _re
    p1 = subprocess.run(
        ["ffmpeg", "-i", str(video), "-af",
         f"loudnorm=I={LUFS_ALVO}:TP={TP_ALVO}:LRA={LRA_ALVO}:print_format=json",
         "-f", "null", "-"],
        capture_output=True, text=True)
    m = _re.search(r"\{[^{}]*\"input_i\"[\s\S]*?\}", p1.stderr)
    if not m:
        print("   [loudness] AVISO: nao consegui medir, mantendo audio original")
        return video
    d = json.loads(m.group(0))
    medido = float(d["input_i"])
    out = video.with_name(video.stem + "_norm.mp4")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-af",
         f"loudnorm=I={LUFS_ALVO}:TP={TP_ALVO}:LRA={LRA_ALVO}:"
         f"measured_I={d['input_i']}:measured_TP={d['input_tp']}:"
         f"measured_LRA={d['input_lra']}:measured_thresh={d['input_thresh']}:"
         f"offset={d['target_offset']}:linear=true",
         "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-b:a", "192k",
         "-movflags", "+faststart", str(out)])
    out.replace(video)
    print(f"   [loudness] {medido:.1f} LUFS -> {LUFS_ALVO} LUFS")
    return video


def strip_overlay(idx_html: Path) -> Path:
    """Remove avatar/brolls/grade/vignette; fundo transparente; celulas do wipe transparentes.
    Mantem hook, caption(#caps), letterings(.lett), cta, logo. Retorna o path do overlay."""
    src = idx_html.read_text()
    kill = ['id="a-roll"', 'id="a-roll-audio"', 'id="grade"', 'id="vignette"',
            'class="broll-scrim', 'class="broll-tag', 'class="broll-vid']
    out = [ln for ln in src.split("\n") if not any(s in ln for s in kill)]
    html = "\n".join(out)
    html = html.replace("html, body { width:1080px; height:1920px; overflow:hidden; background:#05060a; }",
                        "html, body { width:1080px; height:1920px; overflow:hidden; background:transparent; }")
    html = html.replace("html, body { width:1080px; height:1080px; overflow:hidden; background:#05060a; }",
                        "html, body { width:1080px; height:1080px; overflow:hidden; background:transparent; }")
    # WIPE DE GRADE FICA VIVO (18/08/2026, Wave 1c do plano do ritmo): as celulas so
    # aparecem durante a animacao (GSAP arma scale:0 no repouso), entao deixa-las na cor
    # do tema nao cobre nada fora do wipe. Torna-las transparentes, como era antes,
    # matava o efeito em TODO build: 4 wipes calculados por ad ficavam invisiveis.
    dst = idx_html.parent / "index_overlay.html"
    dst.write_text(html)
    return dst



# MUSICA DE FUNDO (31/08/2026, pedido do Julio: "falta uma musiquinha de fundo").
# Faixa em V1/assets/som/musica_fundo.* (ou VAM_MUSICA). Entra DEPOIS do loudnorm da voz
# e da mixagem de efeitos, no nivel MUSICA_LUFS, com fade de entrada e de saida; se a
# faixa for mais curta que o video, repete. Sem faixa, segue sem musica e avisa.
MUSICA_LUFS = -31.0      # ~17 LU abaixo da voz (-14): presente, nunca disputando a fala
def mixar_musica(video):
    import glob as _g
    faixa = os.environ.get("VAM_MUSICA") or next(iter(sorted(
        _g.glob(str(V1 / "assets" / "som" / "musica_fundo.*")))), None)
    if not faixa or not Path(faixa).exists():
        print("   [musica] nenhuma faixa em assets/som/musica_fundo.*; seguindo sem musica",
              flush=True)
        return video
    dur = vdur(video)
    saida = video.with_name(video.stem + "_mus.mp4")
    fc = (f"[1:a]aloop=loop=-1:size=2e9,atrim=0:{dur:.3f},"
          f"loudnorm=I={MUSICA_LUFS}:TP=-6:LRA=7,"
          f"afade=t=in:st=0:d=1.2,afade=t=out:st={max(dur-2.5,0):.3f}:d=2.5[m];"
          f"[0:a][m]amix=inputs=2:duration=first:normalize=0[a]")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-stream_loop", "-1", "-i", faixa,
         "-filter_complex", fc, "-map", "0:v", "-map", "[a]", "-shortest",
         "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-b:a", "192k",
         "-movflags", "+faststart", str(saida)])
    saida.replace(video)
    print(f"   [musica] {Path(faixa).name} a {MUSICA_LUFS} LUFS", flush=True)
    return video

def mixar_som(video, ad, workdir):
    """Whoosh na entrada de insert e riser antes do CTA, no arquivo ja acelerado.

    Sem efeito nenhum se o plano vier vazio: e melhor ficar mudo do que inventar som.
    """
    try:
        # (migracao 26/08/2026) codigo agora vizinho; import direto resolve
        import som_cortes as SC
        import ritmo as RT
        pr = json.loads((workdir / "prancha.json").read_text())
        ins = json.loads((V1 / "inputs" / f"{ad}_inserts.json").read_text())
        vals = list(ins.values())
        n, blocos = 0, []
        for b in pr["blocos"]:
            cfg = {}
            if b["tipo"] == "insert":
                cfg = vals[n] if n < len(vals) else {}
                n += 1
            blocos.append({"tipo": "insert" if b["tipo"] == "insert" else "orig",
                           "s": b["s"], "e": b["e"],
                           "crop": cfg.get("crop"), "dur_max": cfg.get("dur_max"),
                           "texto": b.get("texto", "")})
        segs = RT.plano_de_ritmo(blocos)
        eventos = SC.plano_de_som(segs, ACCEL, cta=pr.get("cta", {}).get("inicio"))
    except Exception as ex:
        print(f"   [som] plano nao calculado ({ex}); seguindo sem efeito", flush=True)
        return video
    eventos = [e for e in eventos if (SC.SOM / e["efeito"]).exists()]
    if not eventos:
        print("   [som] nenhum efeito a aplicar", flush=True)
        return video

    entradas, filtros, rotulos = [], [], []
    for k, e in enumerate(eventos):
        entradas += ["-i", str(SC.SOM / e["efeito"])]
        ms = int(round(e["t"] * 1000))
        filtros.append(f"[{k+1}:a]adelay={ms}|{ms}[e{k}]")
        rotulos.append(f"[e{k}]")
    # normalize=0: o padrao do amix divide o ganho pelo numero de entradas e a VOZ
    # afundaria a cada efeito. duration=first: o comprimento e o do video, nao do efeito.
    filtros.append(f"[0:a]{''.join(rotulos)}amix=inputs={len(eventos)+1}:"
                   f"duration=first:normalize=0[a]")
    saida = video.with_name(video.stem + "_som.mp4")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(video), *entradas,
         "-filter_complex", "; ".join(filtros), "-map", "0:v", "-map", "[a]",
         "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-b:a", "192k",
         "-movflags", "+faststart", str(saida)])
    saida.replace(video)
    quais = ", ".join(f"{e['efeito'].split('.')[0]}@{e['t']:.1f}s" for e in eventos[:6])
    print(f"   [som] {len(eventos)} efeito(s): {quais}"
          f"{' ...' if len(eventos) > 6 else ''}", flush=True)
    return video


def _impressao_template(fmt):
    """Hash do template que o overlay usa. Ver `_conferir_template` logo abaixo."""
    import hashlib
    t = V2 / "templates" / ("reel-editorial-1x1" if fmt == "1x1" else "reel-editorial") / "index.html"
    return hashlib.sha256(t.read_bytes()).hexdigest()[:16] if t.exists() else "ausente"


def _conferir_template(fmt, antes):
    """GATE: o template nao pode mudar NO MEIO do build (defeito real, 26/08/2026).

    O jh13 ficou REPROVADO no gate de colisao por meses com a legenda na testa do
    Thales. Nao era calibragem: o passo [1/6] gerou o overlay as 00:15:36 e o
    template so foi corrigido as 00:16:37, com o build ainda rodando. Os passos
    seguintes usaram um overlay feito da versao ANTERIOR, e o log disse PRONTO.

    O build leva ~25 minutos e le o template uma vez so, no comeco: a janela pra
    isso acontecer e larga, e o sintoma (um grupo de legenda com a classe errada
    no meio de vizinhos certos) nao parece defeito de processo, parece defeito de
    calculo. Custou uma investigacao inteira. Agora reprova na hora.
    """
    depois = _impressao_template(fmt)
    if depois != antes:
        print("\n--- GATE DE TEMPLATE: REPROVA ---")
        print(f"   o template mudou durante o build ({antes} -> {depois}).")
        print("   o overlay foi gerado da versao ANTIGA, entao este render nao vale.")
        print("   conserto: rodar o build de novo, sem editar template no meio.")
        sys.exit(1)


def build(ad, look, fmt):
    lk, sfx = LK[look], SUFFIX[fmt]
    base_cfg = json.loads((V2L / "configs" / f"{ad}_{lk}{sfx}.json").read_text())
    avatar = base_cfg["avatar"]
    workdir = V2L / f"render-{ad}-{lk}{sfx}-ovl"
    print(f"\n===== {ad} {look} {fmt} =====")

    # 1) config speed=1.0 + gen_ad_v2 -> index.html
    cfg = dict(base_cfg); cfg["speed"] = 1.0; cfg["out_dir"] = str(workdir)
    cfg_path = workdir.parent / f"_cfg_{ad}_{lk}{sfx}.json"
    workdir.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False))
    _tmpl_antes = _impressao_template(fmt)
    print("[1/6] gen_ad_v2 (transcreve + monta html)...")
    run([sys.executable, str(CODIGO / "gen_ad_v2.py"), str(cfg_path)])
    _conferir_template(fmt, _tmpl_antes)   # ja mudou enquanto o gen rodava?

    # 2) strip -> overlay transparente
    # GATE DE CONGELAMENTO (18/08/2026): insert que pede mais fonte do que o arquivo tem
    # sai com o ultimo quadro clonado. Aritmetica pura, e roda aqui porque aqui as
    # duracoes de bloco ja existem e o render ainda nao comecou.
    try:
        import analise_inserts as AI
        _pr = json.loads((workdir / "prancha.json").read_text())
        _lin = AI.analisar(ad, _pr)
        _ruim = [l for l in _lin if l["congela"] > AI.LIMITE_S]
        if _ruim:
            print("\n--- GATE DE CONGELAMENTO: REPROVA ---")
            AI.imprimir(_lin)
            print("   conserto: baixar `speed`, subir `start` menos, ou capar com "
                  "`dur_max` no <ad>_inserts.json")
            if os.environ.get("VAM_IGNORA_CONGELA") != "1":
                sys.exit(1)
            print("   [BYPASS] VAM_IGNORA_CONGELA=1: seguindo com congelamento")
    except FileNotFoundError:
        print("   [AVISO] sem prancha.json: gate de congelamento nao rodou")

    print("[2/6] strip -> index_overlay.html")
    ovl_html = strip_overlay(workdir / "index.html")

    # 3) render MOV alpha (dir dedicado com assets)
    only = V2L / f"render-{ad}-{lk}{sfx}-ovlonly"
    sig_arquivo = only / ".assinatura_overlay"

    # CACHE DO OVERLAY (31/08/2026): o passo 3 (~3min de Chromium) so depende do HTML
    # gerado no passo 2 (index_overlay.html), que ja incorpora roteiro, transcricao,
    # config, template e ritmo. Quando so a footage muda entre builds (troca de crop,
    # broll, look de video), o overlay sai IDENTICO e renderiza-lo nao muda nada no
    # resultado: era 8 renders de 3min jogados fora num dia so. A assinatura e o
    # sha256 do proprio HTML final: se ele nao mudou byte a byte, o MOV tambem nao
    # muda. Desligar com CACHE_OVERLAY=0.
    mov = None
    if os.environ.get("CACHE_OVERLAY") != "0" and only.exists() and (only / "renders").exists():
        candidatos = sorted((only / "renders").glob("*.mov"), key=lambda p: p.stat().st_mtime)
        mov_existente = candidatos[-1] if candidatos else None
        if mov_existente and cache_overlay.reaproveitavel(ovl_html, mov_existente, sig_arquivo):
            mov = mov_existente
            print(f"   [cache] overlay reaproveitado (assinatura {cache_overlay.assinatura([ovl_html])})")

    if mov is None:
        if only.exists():
            run(["rm", "-rf", str(only)])
        only.mkdir(parents=True)
        (only / "index.html").write_text(ovl_html.read_text())
        os.symlink(workdir / "fonts", only / "fonts")
        run(["cp", str(workdir / "logo.png"), str(only / "logo.png")])
        if (workdir / "meta.json").exists():
            run(["cp", str(workdir / "meta.json"), str(only / "meta.json")])
        print("[3/6] render overlay MOV (alpha)...")
        # --workers 1: o modo multi-worker (default "auto", 4 workers) tem race condition na
        # captura paralela de frame que MISTURA pixels de dois instantes diferentes do timeline
        # num mesmo frame de saida (ghosting/dupla-exposicao de texto, achado real no ad09,
        # 20/07/2026). --workers 1 elimina a corrida E nao fica mais lento (dedup de frame
        # estatico so verifica com seguranca em modo single-worker; com 4 workers o dedup
        # aborta por "verification budget exhausted" e cai no fallback de capturar tudo).
        # --experimental-fast-capture=false: o modo rapido (ligado por padrao no macOS) le
        # DOM paint records em vez de capturar a tela. Os grupos de legenda comecam com
        # visibility:hidden e sao revelados pelo GSAP, e o fast-capture NAO registra essa
        # mudanca: o overlay saia VAZIO por trechos longos (13s no ad03v2, 25% do anuncio)
        # mesmo com os grupos corretos no HTML. Foi o defeito que mais derrubou nota na leva.
        run([HF, "render", ".", "--format", "mov", "-f", "30", "--workers", "1",
             "--experimental-fast-capture=false"], cwd=str(only))
        movs = sorted((only / "renders").glob("*.mov"), key=lambda p: p.stat().st_mtime)
        mov = movs[-1]
        sig_arquivo.write_text(cache_overlay.assinatura([ovl_html]))
    print("   overlay:", mov.name)

    # 4) footage v1 (SEM texto): produzir_roteiro CAP=0 BAKE=0. Canvas nativo do v1 e
    # sempre 1080x1920 (9:16); pro 1x1 a gente reenquadra esse footage pra 1080x1080
    # (passo 4b, zoom-out+blur), porque o v1 nao tem um modo de montagem quadrado proprio
    # (so o v2/overlay tem).
    print("[4/6] footage v1 (produzir_roteiro CAP=0)...")
    foot = V1 / "output" / f"{ad}_{look}_footage_1x.mp4"
    env = dict(os.environ)
    env.update({"VAM_AVATAR": avatar, "VAM_ROTEIRO": str(V1 / "inputs" / f"{ad}_leva.txt"),
                "VAM_INSERTS_JSON": str(V1 / "inputs" / f"{ad}_inserts.json"),
                "VAM_BAKE_LETTERING": "0", "CAP": "0",
                # XF/XF_TIPO ficam com o default do motor (0.20 + transicao por corte).
                # Antes daqui saia um "VAM_XF": "0.08" fixo que ANULAVA o ajuste de
                # transicao feito no motor: o v2 continuou montando com corte de 0.08s
                # enquanto eu achava que estava usando 0.22. Nao voltar a fixar aqui.
                "VAM_OUT": f"{ad}_{look}_footage_1x.mp4"})
    run([sys.executable, str(CODIGO / "produzir_roteiro.py")], env=env, cwd=str(V1))
    a0 = json.loads((V1 / "output" / "timing.json").read_text())["a0"]
    print(f"   a0={a0}  footage={vdur(foot):.2f}s  overlay={vdur(mov):.2f}s")

    # 4b) zoom-out+blur 1080x1920 -> 1080x1080 pro 1x1 (ver nota no topo do arquivo).
    # janela CROP_H_1X1 alta cropada em CROP_Y_1X1, encolhida pra caber em 1080x1080
    # (fg), centralizada sobre uma versao desfocada/cover da MESMA janela (bg) que
    # preenche as laterais que sobram.
    if fmt == "1x1":
        foot_sq = V1 / "output" / f"{ad}_{look}_footage_1x_sq.mp4"
        fg_w = round(1080 * 1080 / CROP_H_1X1)
        run(["ffmpeg", "-y", "-v", "error", "-i", str(foot), "-filter_complex",
             f"[0:v]crop=1080:{CROP_H_1X1}:0:{CROP_Y_1X1},scale=1080:1080:force_original_aspect_ratio=increase,"
             f"crop=1080:1080,gblur=sigma=25[bg];"
             f"[0:v]crop=1080:{CROP_H_1X1}:0:{CROP_Y_1X1},scale={fg_w}:1080[fg];"
             f"[bg][fg]overlay=(1080-{fg_w})/2:0[v]",
             "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-crf", "16",
             "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "copy", str(foot_sq)])
        foot = foot_sq

    # 5) composite (overlay deslocado -a0) 1.0x
    print("[5/6] composite 1.0x...")
    comp = V1 / "output" / f"{ad}_{look}_composite_1x.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(foot), "-i", str(mov),
         "-filter_complex", f"[1:v]setpts=PTS-{a0}/TB[ov];[0:v][ov]overlay=0:0:eof_action=pass:shortest=1[v]",
         "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-crf", "16", "-preset", "medium",
         "-pix_fmt", "yuv420p", "-c:a", "copy", str(comp)])

    # 6) acelera (ACCEL) -> final + whatsapp
    print(f"[6/6] acelerar {ACCEL}x + exportar...")
    final = V1 / "output" / f"{ad}_{look}_v2composite_{fmt}.mp4"
    # LOUDNESS (04/08/2026): a voz gravada do Thales chega em ~-31 LUFS e o pipeline
    # nunca normalizava, entao o anuncio saia ~18 LU abaixo do alvo de plataforma
    # (-14 LUFS). No feed do Meta, ao lado de um video normalizado, soa quase mudo.
    # Achado numa auditoria de diretor de arte; o ad11 ja entregue esta em -28.5.
    # loudnorm em DOIS passes (measure -> apply): o single-pass so estima e erra o
    # alvo; e somar ganho puro estouraria (true peak ja estava em -9.1 dB).
    run(["ffmpeg", "-y", "-v", "error", "-i", str(comp),
         "-filter_complex",
         f"[0:v]setpts=PTS/{ACCEL},tpad=stop_mode=clone:stop_duration={TAIL_FINAL}[v];"
         f"[0:a]atempo={ACCEL},apad=pad_dur={TAIL_FINAL}[a]",
         "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
         "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
         "-c:a", "aac", "-ar", "48000", "-b:a", "192k", "-movflags", "+faststart", str(final)])
    _conferir_template(fmt, _tmpl_antes)   # e mudou durante os 25min de render?
    # ORDEM INVERTIDA (27/08/2026). Era `mixar_som` e depois `normalizar_loudness`, e
    # nessa ordem o loudnorm COME a calibragem do efeito: ele normaliza a faixa inteira
    # pra -14 LUFS, entao baixar o whoosh derruba o loudness total e o loudnorm sobe tudo
    # de volta junto. Medido: baixei o whoosh 6 dB no `som_cortes` e o efeito no arquivo
    # entregue caiu 1,0 dB. A calibragem descrevia um arquivo intermediario que ninguem
    # ouve.
    # Normalizando a VOZ primeiro e mixando depois, o efeito entra no nivel em que foi
    # calibrado e chega assim na entrega. O impacto no loudness final e desprezivel
    # (os efeitos estao ~20 dB abaixo da voz e sao curtos), e o gate de loudness confere.
    final = normalizar_loudness(final)
    final = mixar_som(final, ad, workdir)
    final = mixar_musica(final)
    # TIMESTAMP LIMPO NO FIM (31/08/2026, prints do Julio). Os tres remuxes em serie
    # com copia de video (loudness -> som -> musica) deixaram o PRIMEIRO quadro em
    # pts -0,067s e o DTS fora de ordem. ffprobe e QuickTime toleram; o player do
    # WhatsApp nao: mostrava 1:22 num video de 1:30 e o audio escorregava ao longo da
    # peca ("o audio ta des-sincronizado"). Um remux final zera a linha do tempo, e o
    # gate abaixo RECUSA entregar arquivo com timestamp negativo.
    _limpo = final.with_name(final.stem + "_ts.mp4")
    run(["ffmpeg", "-y", "-v", "error", "-fflags", "+genpts", "-i", str(final),
         "-c", "copy", "-avoid_negative_ts", "make_zero",
         "-muxpreload", "0", "-muxdelay", "0",
         "-movflags", "+faststart", str(_limpo)])
    _limpo.replace(final)
    _pts0 = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "packet=pts_time", "-of", "csv=p=0",
                            "-read_intervals", "%+0.2", str(final)],
                           capture_output=True, text=True).stdout.strip().splitlines()
    if _pts0 and min(float(x) for x in _pts0 if x) < -0.001:
        sys.exit(f"ERRO: timestamp de video negativo depois do remux ({_pts0[:3]}); "
                 "nao entregar arquivo que desincroniza no player")
    print(f"   [ts] primeiro pts de video: {_pts0[0] if _pts0 else '?'}", flush=True)
    wa = V1 / "output" / f"{ad}_{look}_v2composite_{fmt}_whatsapp.mp4"
    scale = "720:1280" if fmt == "9x16" else "720:720"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(final), "-vf", f"scale={scale}",
         "-c:v", "libx264", "-crf", "28", "-preset", "veryfast", "-pix_fmt", "yuv420p",
         "-avoid_negative_ts", "make_zero",
         "-c:a", "aac", "-ar", "48000", "-b:a", "128k", "-movflags", "+faststart", str(wa)])
    print(f"OK -> {final}  ({vdur(final):.2f}s)")
    return str(final)


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2], sys.argv[3])
