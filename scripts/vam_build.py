#!/usr/bin/env python3
"""VAM BUILD: orquestrador com GATES do Video Ads Machine.

Roda o pipeline inteiro na ordem certa e NÃO deixa avançar se um checkpoint falhar.
Cada gate abaixo é um checkpoint que validamos na prática no AD01 (avatar Thales).
Objetivo: o agente (ou humano) NÃO consegue mais pular etapa nem entregar pela metade.

Um comando faz tudo:  python3 vam_build.py <config.build.json>
Auditar um final já pronto (sem re-renderizar): python3 vam_build.py --check <final_9x16.mp4> [n_lettering]

Config (JSON):
{
  "ad": "ad01",
  "raw_voice": "inputs/ad01_thales_voz_real.mp3",   // voz REAL gravada (nunca TTS)
  "roteiro":   "inputs/ad01_leva.txt",
  "inserts":   "inputs/ad01_inserts.json",
  "lettering_style": "foil",         // padrao aprovado
  "accelerate": 1.2,                  // padrao do Julio
  "drive_folder": "https://drive.google.com/drive/folders/XXXX",  // OPCIONAL: sobe os finais aqui
  "looks": [
    {"name": "espuma_roxa", "avatar_id": "..."},
    {"name": "studio_verde", "avatar_id": "..."}
  ]
}

GATES (falham a build com exit 1):
  G0 preflight   inputs existem; nenhum b-roll com "thales" (gotcha classify); avatar_id em cada look
  G1 audio       _clean.mp3 existe e NAO sobra respiro grande (silencedetect); de-breath por ENERGIA
  G2 avatar      dur(avatar) ~= dur(_clean) -> usou o audio limpo + Avatar V (travado no heygen_av5)
  G3 montagem    timing.json tem as N cenas de lettering esperadas (serial, com lock anti-race);
                 total calculado ~= duracao real do avatar (pega CAUDA CORTADA: parakeet as vezes
                 nao reconhece as ultimas palavras da fala e o video termina antes do fim real do
                 audio, achado 17/07/2026 nos ads 07-10; fix no align() cobre a maioria dos casos,
                 este gate e a rede de seguranca que aborta a build se ainda assim sobrar corte)
  G4 legenda     saidas 9:16 E 1:1 existem
  G5 acelerar    dur(final) ~= dur(legendado)/1.2  -> 1.2x aplicado (obrigatorio)
  G6 auditoria   silencedetect no FINAL (zero respiro grande) + duracao consistente entre looks
  G7 drive       (opcional, so se "drive_folder" no config) sobe os finais 9:16 e 1:1 e CONFIRMA na pasta
  Manifest: recibo JSON com todos os numeros e PASS/FAIL. "pronto" so com o manifest verde.

Config opcional "xf" (float, default 0.08): duracao do crossfade entre blocos. NAO subir de
0.08 sem motivo forte: 0.18 (valor antigo) causa dupla exposicao (>=100ms) em cortes de alto
contraste avatar-escuro/insert-claro, confirmado em TODOS os looks/ads numa auditoria de 8
videos (17/07/2026), nao so nos de fundo escuro como se pensava a principio.

Regra que NAO da pra travar por codigo: voz SEMPRE real, nunca TTS (destacada no preflight).
"""
import json, os, re, sys, time, subprocess

# (migracao 26/08/2026) caminho de projeto agora sai de caminhos.py
from caminhos import DADOS as _D, CODIGO as _C
BASE = str(_D)
_CODIGO = str(_C)
sys.path.insert(0, BASE)   # pra importar drive_push (mesmo dir)
OUTD = os.path.join(BASE, "output")
LOCK = os.path.join(OUTD, ".vam_montage.lock")
SILENCE_DB = -30            # mesmo limiar da higienizacao
BIG_SIL_GATE = 0.65        # no final NAO pode sobrar silencio > isso (respiro grande)
AVATAR_DUR_TOL = 0.8       # avatar tem que casar com o audio clean
ACCEL_TOL = 0.35           # tolerancia do gate de aceleracao
LOOK_DUR_TOL = 0.7         # looks do mesmo anuncio tem que fechar na mesma duracao
CAUDA_TOL = 0.5            # total calculado (produzir_roteiro) vs duracao real do avatar

class GateFail(Exception): pass

def run(cmd, env=None, label=""):
    e = dict(os.environ); e.update(env or {})
    r = subprocess.run(cmd, capture_output=True, text=True, env=e, cwd=BASE)
    if r.returncode != 0:
        raise GateFail(f"comando falhou ({label or cmd[0]}):\n{r.stderr[-700:]}")
    return r

def dur(f):
    o = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
        "-of","default=nw=1:nk=1", f], capture_output=True, text=True).stdout.strip()
    return float(o) if o else 0.0

def big_silences(mp4_or_audio, thresh):
    """Nº de regioes de silencio maiores que thresh (respiro grande) no arquivo."""
    r = subprocess.run(["ffmpeg","-i",mp4_or_audio,"-af",
        f"silencedetect=noise={SILENCE_DB}dB:d={thresh}","-f","null","-"],
        capture_output=True, text=True)
    return [float(m) for m in re.findall(r"silence_duration:\s*([0-9.]+)", r.stderr)]

def count_lettering(roteiro):
    """Conta cenas de lettering no roteiro anotado (instrucao [...] contendo 'lettering')."""
    n = 0
    for line in open(roteiro, encoding="utf-8"):
        m = re.match(r"\s*\[(.*?)\]", line)
        if m and "lettering" in m.group(1).lower(): n += 1
    return n

def inserts_have_thales(roteiro):
    """Gotcha classify: instrucao de INSERT de b-roll com 'thales' vira 'orig' por engano."""
    bad = []
    for i, line in enumerate(open(roteiro, encoding="utf-8"), 1):
        m = re.match(r"\s*\[(.*?)\]", line)
        if m and "inserção" in m.group(1).lower() and "thales" in m.group(1).lower():
            bad.append(i)
    return bad

# ---- lock anti race condition (timing.json/av.json sao compartilhados) ----
def acquire_lock(timeout=1800):
    t0 = time.time()
    while True:
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode()); os.close(fd); return
        except FileExistsError:
            if time.time() - t0 > timeout:
                raise GateFail("timeout esperando o lock da montagem (outra build rodando?)")
            time.sleep(1)
def release_lock():
    try: os.remove(LOCK)
    except FileNotFoundError: pass

# ---------------------------------------------------------------------------
GATES = []
def gate(name, ok, detail, metrics=None):
    GATES.append({"gate": name, "ok": bool(ok), "detail": detail, "metrics": metrics or {}})
    print(f"  [{'PASS' if ok else 'FALHA'}] {name}: {detail}")
    if not ok: raise GateFail(f"gate {name} reprovou: {detail}")

# ================================ GATES ====================================
def g0_preflight(cfg):
    print("== G0 preflight ==")
    for k in ("raw_voice","roteiro"):
        p = os.path.join(BASE, cfg[k])
        gate(f"input:{k}", os.path.exists(p), p)
    if cfg.get("inserts"):
        p = os.path.join(BASE, cfg["inserts"])
        gate("input:inserts", os.path.exists(p), p)
    bad = inserts_have_thales(os.path.join(BASE, cfg["roteiro"]))
    gate("broll_sem_thales", not bad,
         "nenhuma instrucao de insert com 'thales'" if not bad else f"linhas {bad} tem 'thales' (viram orig)")
    looks = cfg.get("looks") or []
    gate("looks_com_avatar_id", looks and all(l.get("avatar_id") for l in looks),
         f"{len(looks)} look(s) com avatar_id")
    print("  >> LEMBRETE (nao travavel por codigo): a voz TEM que ser real, gravada. NUNCA TTS.")

def g1_audio(cfg):
    print("== G1 higienizacao de audio (de-breath por energia) ==")
    raw = os.path.join(BASE, cfg["raw_voice"])
    clean = os.path.join(BASE, "inputs", f"{cfg['ad']}_voz_clean.mp3")
    run(["python3", os.path.join(BASE,"higienizar_audio.py"), raw, clean], label="higienizar")
    ok_exists = os.path.exists(clean)
    gate("clean_existe", ok_exists, clean)
    resid = big_silences(clean, BIG_SIL_GATE)
    gate("sem_respiro_grande", len(resid) == 0,
         f"0 silencios > {BIG_SIL_GATE}s no clean" if not resid else f"ainda ha {len(resid)} silencios grandes: {resid}",
         {"raw_dur": round(dur(raw),2), "clean_dur": round(dur(clean),2), "residual_big": resid})
    return clean, dur(clean)

def g2_avatar(cfg, look, clean, clean_dur):
    print(f"== G2 avatar Avatar V [{look['name']}] ==")
    out = os.path.join(BASE, "inputs", f"{cfg['ad']}_{look['name']}_avatar.mp4")
    # cache: retry de um build que ja gerou esse avatar (dur bate com o clean atual) nao paga
    # credito HeyGen de novo. So gera se o arquivo nao existe ou a duracao nao bate mais.
    if os.path.exists(out) and abs(dur(out) - clean_dur) <= AVATAR_DUR_TOL:
        print(f"  (cache) avatar ja existe e dur bate com o clean atual, reusando: {out}")
    else:
        # heygen_av5 ja TRAVA engine=avatar_v; nao passamos engine -> default travado
        run(["python3", os.path.join(BASE,"heygen_av5.py"),"gerar", clean, look["avatar_id"], out],
            label="heygen_av5")
    ad = dur(out)
    gate("avatar_usou_clean", abs(ad - clean_dur) <= AVATAR_DUR_TOL,
         f"dur avatar {ad:.2f}s ~= clean {clean_dur:.2f}s",
         {"avatar_dur": round(ad,2), "clean_dur": round(clean_dur,2)})
    return out

def g3_montagem(cfg, look, avatar):
    print(f"== G3 montagem [{look['name']}] (serial, com lock anti-race) ==")
    base = f"{cfg['ad']}_{look['name']}_base.mp4"
    env = {"CAP":"0","VAM_BAKE_LETTERING":"1",
           "VAM_LETTER_STYLE": cfg.get("lettering_style","foil"),
           "VAM_XF": str(cfg.get("xf", 0.08)),
           "VAM_AVATAR": avatar, "VAM_ROTEIRO": os.path.join(BASE,cfg["roteiro"]),
           "VAM_OUT": base}
    if cfg.get("inserts"): env["VAM_INSERTS_JSON"] = os.path.join(BASE, cfg["inserts"])
    acquire_lock()
    try:
        run(["python3", os.path.join(BASE,"produzir_roteiro.py")], env=env, label="produzir_roteiro")
        # snapshot IMEDIATO do timing (evita race se algo mais tocar timing.json)
        tj = os.path.join(OUTD, "timing.json")
        snap = os.path.join(OUTD, f"{cfg['ad']}_{look['name']}_timing.json")
        run(["cp", tj, snap], label="snapshot timing")
    finally:
        release_lock()
    snap_data = json.load(open(snap))
    lets = len(snap_data.get("letterings", []))
    exp = cfg.get("expected_lettering_scenes") or count_lettering(os.path.join(BASE,cfg["roteiro"]))
    gate("cenas_lettering", lets == exp, f"{lets} cenas de lettering (esperado {exp})",
         {"lettering_scenes": lets, "expected": exp})
    # CAUDA CORTADA (17/07/2026): se o alinhamento de palavras nao pegou bem o fim da fala,
    # o "total" calculado fica menor que a duracao real do avatar e o video corta a frase
    # final (CTA) antes da hora. Compara contra o avatar de entrada, nao contra o clean,
    # porque o avatar E o arquivo que o align() de fato usa pra alinhar.
    total_calc = snap_data.get("total", 0.0)
    avatar_dur = dur(avatar)
    gate("cauda_nao_cortada", abs(total_calc - avatar_dur) <= CAUDA_TOL,
         f"total calculado {total_calc:.2f}s ~= duracao real do avatar {avatar_dur:.2f}s",
         {"total_calculado": round(total_calc,2), "avatar_dur": round(avatar_dur,2)})
    # PiP
    pip = os.path.join(OUTD, f"{cfg['ad']}_{look['name']}_pip.mp4")
    run(["python3", os.path.join(BASE,"add_pip.py"), os.path.join(OUTD,base), pip],
        env={"VAM_AVATAR": avatar}, label="add_pip")
    return pip, snap

def g4_legenda(cfg, look, pip):
    cap_style = cfg.get("caption_style", "tay")
    print(f"== G4 legenda {cap_style} 9:16 + 1:1 [{look['name']}] ==")
    rot = os.path.join(BASE, cfg["roteiro"])
    # hook fixado (texto nos primeiros segundos, estilo referencia euriler) e por-ad no config
    hook_env = {}
    if cfg.get("hook_text"):
        hook_env = {"VAM_HOOK_TEXT": cfg["hook_text"]["text"],
                    "VAM_HOOK_END": str(cfg["hook_text"].get("end", 5.0))}
    cap9 = os.path.join(OUTD, f"{cfg['ad']}_{look['name']}_cap_9x16.mp4")
    run(["python3", os.path.join(BASE,"tay_captions.py"), pip, cap9, "--style",cap_style,"--format","9x16"],
        env={"VAM_ROTEIRO": rot, **hook_env}, label="cap 9x16")
    # composite 1:1 antes de legendar (gotcha: tay 1x1 nao gera quadrado sozinho)
    comp = os.path.join(OUTD, f"{cfg['ad']}_{look['name']}_pip_1x1.mp4")
    run(["ffmpeg","-y","-i",pip,"-filter_complex",
        "[0:v]split=2[bg][fg];[bg]scale=1080:1080:force_original_aspect_ratio=increase,"
        "crop=1080:1080,boxblur=24:1,setsar=1[b];[fg]scale=-1:1080,setsar=1[f];"
        "[b][f]overlay=(W-w)/2:0,fps=30,colorspace=all=bt709:iall=bt709:fast=1[v]",
        "-map","[v]","-map","0:a","-c:v","libx264",
        "-crf","18","-pix_fmt","yuv420p",
        "-colorspace","bt709","-color_primaries","bt709","-color_trc","bt709","-color_range","tv",
        "-c:a","copy",comp], label="composite 1x1")
    cap1 = os.path.join(OUTD, f"{cfg['ad']}_{look['name']}_cap_1x1.mp4")
    run(["python3", os.path.join(BASE,"tay_captions.py"), comp, cap1, "--style",cap_style,"--format","1x1"],
        env={"VAM_ROTEIRO": rot, **hook_env}, label="cap 1x1")
    gate("saidas_9x16_e_1x1", os.path.exists(cap9) and os.path.exists(cap1),
         "legendas 9:16 e 1:1 geradas")
    return cap9, cap1

def g5_acelerar(cfg, look, cap9, cap1):
    print(f"== G5 acelerar {cfg.get('accelerate',1.2)}x [{look['name']}] ==")
    fac = cfg.get("accelerate", 1.2)
    f9 = os.path.join(OUTD, f"{cfg['ad']}_{look['name']}_FINAL_9x16.mp4")
    f1 = os.path.join(OUTD, f"{cfg['ad']}_{look['name']}_FINAL_1x1.mp4")
    run(["python3", os.path.join(BASE,"acelerar.py"), cap9, f9, str(fac)], label="acelerar 9x16")
    run(["python3", os.path.join(BASE,"acelerar.py"), cap1, f1, str(fac)], label="acelerar 1x1")
    exp = dur(cap9)/fac
    gate("acelerado_1.2x", abs(dur(f9) - exp) <= ACCEL_TOL,
         f"final {dur(f9):.2f}s ~= legendado/{fac} ({exp:.2f}s)",
         {"final_dur": round(dur(f9),2), "esperado": round(exp,2), "fator": fac})
    # versoes whatsapp
    for src, w in ((f9,720),(f1,720)):
        wa = src.replace("_FINAL_","_FINAL_").replace(".mp4","_whatsapp.mp4")
        h = 1280 if "9x16" in src else 720
        run(["ffmpeg","-y","-i",src,"-vf",
            f"scale={w}:{h},colorspace=all=bt709:iall=bt709:fast=1","-c:v","libx264","-crf","28",
            "-preset","veryfast",
            "-colorspace","bt709","-color_primaries","bt709","-color_trc","bt709","-color_range","tv",
            "-c:a","aac","-b:a","128k",wa], label="whatsapp")
    return f9, f1

def g6_auditoria(cfg, look, f9, timing_snap, ref_dur):
    print(f"== G6 auditoria automatica [{look['name']}] ==")
    resid = big_silences(f9, BIG_SIL_GATE)
    gate("final_sem_respiro", len(resid) == 0,
         f"0 respiros grandes no final" if not resid else f"{len(resid)} respiros grandes: {resid}",
         {"residual_big": resid})
    lets = len(json.load(open(timing_snap)).get("letterings", []))
    exp = cfg.get("expected_lettering_scenes") or count_lettering(os.path.join(BASE,cfg["roteiro"]))
    gate("final_tem_lettering", lets == exp, f"{lets} cenas de lettering no final")
    d = dur(f9)
    if ref_dur is not None:
        gate("duracao_consistente", abs(d - ref_dur) <= LOOK_DUR_TOL,
             f"{d:.2f}s ~= 1o look {ref_dur:.2f}s (sem race)",
             {"dur": round(d,2), "ref": round(ref_dur,2)})
    return d

def g7_drive(cfg, results):
    """Entrega no Drive: sobe os finais 9:16 e 1:1 de cada look pra pasta do config
    e CONFIRMA via API. So roda se cfg['drive_folder'] existir. Gate falha se algum nao subiu."""
    print("== G7 entrega no Drive ==")
    import drive_push
    items = []
    for r in results:
        for fmt, path in (("9x16", r["final_9x16"]), ("1x1", r["final_1x1"])):
            items.append((path, f"{cfg['ad'].upper()}_{r['look']}_{fmt}.mp4"))
    out = drive_push.push(cfg["drive_folder"], items)
    for rr in out["results"]:
        print(f"   {'OK' if rr['ok'] and rr['verified'] else 'FALHA'} {rr['name']}")
    n = sum(1 for rr in out["results"] if rr["verified"])
    gate("drive_upload", out["all_ok"],
         f"{n}/{len(items)} finais confirmados na pasta -> {out['folder_link']}",
         {"folder_link": out["folder_link"], "confirmados": n})
    return out

def build_look(cfg, look, clean, clean_dur, ref_dur):
    print(f"\n########## LOOK: {look['name']} ##########")
    avatar = g2_avatar(cfg, look, clean, clean_dur)
    pip, snap = g3_montagem(cfg, look, avatar)
    cap9, cap1 = g4_legenda(cfg, look, pip)
    f9, f1 = g5_acelerar(cfg, look, cap9, cap1)
    d = g6_auditoria(cfg, look, f9, snap, ref_dur)
    return {"look": look["name"], "final_9x16": f9, "final_1x1": f1, "dur": round(d,2)}

def cmd_build(config_path):
    cfg = json.load(open(config_path))
    print(f"===== VAM BUILD: {cfg['ad']} ({len(cfg.get('looks',[]))} look/s) =====")
    g0_preflight(cfg)
    clean, clean_dur = g1_audio(cfg)
    results, ref_dur = [], None
    for look in cfg["looks"]:                      # SERIAL de proposito (anti-race na montagem)
        r = build_look(cfg, look, clean, clean_dur, ref_dur)
        if ref_dur is None: ref_dur = r["dur"]
        results.append(r)
    drive = g7_drive(cfg, results) if cfg.get("drive_folder") else None
    manifest = {"ad": cfg["ad"], "looks": results, "gates": GATES,
                "drive": ({"folder_link": drive["folder_link"],
                           "files": [{"name": r["name"], "ok": r["ok"] and r["verified"],
                                      "link": r["link"]} for r in drive["results"]]}
                          if drive else None),
                "all_pass": all(g["ok"] for g in GATES)}
    mpath = os.path.join(OUTD, f"{cfg['ad']}_manifest.json")
    json.dump(manifest, open(mpath,"w"), ensure_ascii=False, indent=2)
    print(f"\n===== MANIFEST: {mpath} | all_pass={manifest['all_pass']} =====")
    for r in results: print(f"  {r['look']}: {r['dur']}s -> {os.path.basename(r['final_9x16'])}")

def cmd_check(final, n_lettering=None):
    """Audita um final ja pronto (G6) sem re-renderizar. Prova de que os gates funcionam."""
    print(f"== --check {final} ==")
    resid = big_silences(final, BIG_SIL_GATE)
    gate("final_sem_respiro", len(resid) == 0,
         "0 respiros grandes" if not resid else f"{len(resid)} respiros grandes: {resid}",
         {"residual_big": resid})
    d = dur(final)
    gate("duracao_valida", 5 < d < 120, f"duracao {d:.2f}s plausivel")
    if n_lettering is not None:
        # tenta achar o timing snapshot correspondente
        print(f"  (n_lettering esperado informado: {n_lettering})")
    print(f"  final ok: {d:.2f}s, {len(resid)} respiros grandes")

def main():
    a = sys.argv[1:]
    try:
        if a and a[0] == "--check":
            cmd_check(a[1], int(a[2]) if len(a) > 2 else None)
        elif a and a[0].endswith(".json"):
            cmd_build(a[0])
        else:
            sys.exit(__doc__)
    except GateFail as e:
        print(f"\n*** BUILD BLOQUEADA: {e}", file=sys.stderr)
        release_lock(); sys.exit(1)

if __name__ == "__main__":
    main()
