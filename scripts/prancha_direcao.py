#!/usr/bin/env python3
"""Prancha de direcao: o anuncio inteiro em quadro parado, ANTES de renderizar.

Por que existe (ordem do Julio, 18/08/2026): "se ele e um diretor, ele dirige, nao apenas
audita no final". Eu classifiquei item por item a auditoria que reprovou o jh13 com 6,3:
os 12 defeitos eram julgaveis sem o video pronto. Enquadramento ilegivel, texto decepado,
lista que nao empilha, faixa preta na costura, legenda dentro da area de UI do Reels,
exposicao, vao sem texto, cauda: tudo isso vive em quadro parado e em linha do tempo.
Gastei quatro renders de 25 minutos pra descobrir o que cabia numa prancha.

O que ela monta, SEM renderizar o video:
  1. HOOK        - os primeiros segundos, quadro a quadro
  2. INSERTS     - cada bloco no enquadramento final, em 4 pontos da JANELA que ele usa
                   (recorte fixo com conteudo que se move e o defeito que mais me pegou)
  3. LETTERINGS  - cada card em cima do quadro exato onde ele pousa
  4. FECHAMENTO  - CTA e logo
  5. REGUA       - insert x avatar por tempo, vaos sem texto, densidade

Custo: ~4 min por ad, contra ~25 do render.

O truque: o quadro final e footage (motor v1) + overlay (HTML). O overlay sai do
`hyperframes snapshot`, que da PNG com alpha em timestamps escolhidos sem render de
video. A footage sai do proprio produzir_roteiro. Composto, e o quadro que vai ao ar.

Uso:  python3 prancha_direcao.py jh13 [espuma_roxa]
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from caminhos import V2  # noqa: E402
from caminhos import V2L  # noqa: E402
from caminhos import V1, CODIGO  # noqa: E402
HF = str(V2 / "node_modules" / ".bin" / "hyperframes")

# (migracao 26/08/2026) codigo agora vizinho; import direto resolve
from ads_v2_configs import LOOKS as LK          # noqa: E402
import build_composite as BC                     # noqa: E402
import analise_inserts as AI                     # noqa: E402

SUFFIX = {"9x16": "", "1x1": "_1x1"}
W, H = 1080, 1920
# safe zones do Reels/Stories, medidas em fracao da altura
SAFE_TOPO, SAFE_BASE = 0.14, 0.20


def sh(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"falhou: {' '.join(str(c) for c in cmd[:4])}\n{r.stderr[-1500:]}")
    return r.stdout


def fonte(tam):
    for p in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
              "/System/Library/Fonts/Helvetica.ttc"):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, tam)
            except Exception:
                pass
    return ImageFont.load_default()


def luminancia_faixa(im, y0_frac, y1_frac):
    """Luminancia media da faixa horizontal onde o texto mora.

    Buraco 2 do diretor (20/08): sem numero, texto branco sobre fundo claro so aparece
    quando alguem repara. Ele teve que medir na mao pra provar o hook do AD15, que pousa
    sobre L=231 num instante e sobre L=31 no seguinte.
    """
    a = np.asarray(im.convert("L"), dtype=np.float32)
    y0, y1 = int(a.shape[0] * y0_frac), int(a.shape[0] * y1_frac)
    faixa = a[max(y0, 0):min(y1, a.shape[0])]
    return float(faixa.mean()) if faixa.size else 0.0


def rotular(im, texto, sub=""):
    """Faixa de rotulo em cima do quadro. Sem rotulo a prancha vira adivinhacao."""
    im = im.convert("RGB")
    dr = ImageDraw.Draw(im)
    f1, f2 = fonte(max(16, im.width // 26)), fonte(max(13, im.width // 34))
    alt = f1.size + (f2.size + 6 if sub else 0) + 14
    dr.rectangle([0, 0, im.width, alt], fill=(0, 0, 0))
    dr.text((8, 5), texto, fill=(255, 214, 0), font=f1)
    if sub:
        dr.text((8, 7 + f1.size), sub, fill=(190, 190, 190), font=f2)
    return im


def marcar_safe(im):
    """Risca as safe zones do Reels: o que cai nelas some atras da UI do app."""
    dr = ImageDraw.Draw(im, "RGBA")
    t, b = int(im.height * SAFE_TOPO), int(im.height * (1 - SAFE_BASE))
    dr.rectangle([0, 0, im.width, t], fill=(255, 0, 0, 34))
    dr.rectangle([0, b, im.width, im.height], fill=(255, 0, 0, 34))
    dr.line([(0, t), (im.width, t)], fill=(255, 60, 60, 200), width=2)
    dr.line([(0, b), (im.width, b)], fill=(255, 60, 60, 200), width=2)
    return im


def folha(ims, dst, cols=6, alt=430):
    if not ims:
        return None
    red = []
    for im in ims:
        red.append(im.resize((max(1, int(im.width * alt / im.height)), alt)))
    cw = max(i.width for i in red)
    cols = min(cols, len(red))
    linhas = (len(red) + cols - 1) // cols
    sh_im = Image.new("RGB", (cw * cols, alt * linhas), (17, 17, 17))
    for i, im in enumerate(red):
        sh_im.paste(im, ((i % cols) * cw, (i // cols) * alt))
    sh_im.save(dst)
    return dst


# ----------------------------------------------------------------- etapas baratas
def preparar(ad, look, fmt="9x16"):
    """Roda so as etapas que NAO renderizam video: config -> gen_ad_v2 -> overlay."""
    lk, sfx = LK[look], SUFFIX[fmt]
    base = json.loads((V2L / "configs" / f"{ad}_{lk}{sfx}.json").read_text())
    workdir = V2L / f"render-{ad}-{lk}{sfx}-ovl"
    workdir.mkdir(parents=True, exist_ok=True)
    cfg = dict(base)
    cfg["speed"] = 1.0
    cfg["out_dir"] = str(workdir)
    cfg_path = workdir.parent / f"_cfg_{ad}_{lk}{sfx}.json"
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False))
    print("[1/5] gen_ad_v2 (transcreve + monta html + prancha.json)...", flush=True)
    sh([sys.executable, str(V2L / "gen_ad_v2.py"), str(cfg_path)])
    print("[2/5] strip -> overlay transparente", flush=True)
    ovl = BC.strip_overlay(workdir / "index.html")
    only = V2L / f"render-{ad}-{lk}{sfx}-ovlonly"
    if only.exists():
        shutil.rmtree(only)
    only.mkdir(parents=True)
    (only / "index.html").write_text(ovl.read_text())
    if not (only / "fonts").exists():
        os.symlink(workdir / "fonts", only / "fonts")
    shutil.copy(workdir / "logo.png", only / "logo.png")
    if (workdir / "meta.json").exists():
        shutil.copy(workdir / "meta.json", only / "meta.json")
    pr = json.loads((workdir / "prancha.json").read_text())
    return pr, workdir, only, base


def footage(ad, look, base, reaproveitar=False):
    """Monta a footage (motor v1). E o unico passo pesado da prancha, ~1-2 min."""
    out = V1 / "output" / f"prancha_{ad}_{look}_footage.mp4"
    if reaproveitar and out.exists():
        print("[3/5] footage: reaproveitando a existente", flush=True)
        return out
    print("[3/5] footage v1 (sem texto)...", flush=True)
    env = dict(os.environ)
    env.update({"VAM_AVATAR": base["avatar"],
                "VAM_ROTEIRO": str(V1 / "inputs" / f"{ad}_leva.txt"),
                "VAM_INSERTS_JSON": str(V1 / "inputs" / f"{ad}_inserts.json"),
                "VAM_BAKE_LETTERING": "0", "CAP": "0", "VAM_OUT": out.name})
    sh([sys.executable, str(CODIGO / "produzir_roteiro.py")], env=env, cwd=str(V1))
    return out


def _variante_fundo(only, cor, nome):
    """Copia do projeto de overlay com o fundo forcado numa cor chapada."""
    dst = only.parent / f"{only.name}-{nome}"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(only, dst, symlinks=True,
                    ignore=shutil.ignore_patterns("snaps", "renders"))
    h = (dst / "index.html").read_text()
    h = h.replace("</head>",
                  f"<style>html,body{{background:{cor} !important;}}</style></head>", 1)
    (dst / "index.html").write_text(h)
    return dst


def _idx(p):
    m = re.search(r"frame-(\d+)", p.name)
    return int(m.group(1)) if m else 10 ** 9


def _variante_fundo(only, cor, nome):
    """Copia do projeto de overlay com o fundo forcado numa cor chapada."""
    dst = only.parent / f"{only.name}-{nome}"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(only, dst, symlinks=True,
                    ignore=shutil.ignore_patterns("snaps", "renders"))
    h = (dst / "index.html").read_text()
    h = h.replace("</head>",
                  f"<style>html,body{{background:{cor} !important;}}</style></head>", 1)
    (dst / "index.html").write_text(h)
    return dst


def snapshots(only, tempos, reaproveitar=False):
    """Overlay nos tempos pedidos, com ALPHA, sem renderizar video.

    `hyperframes snapshot` escreve PNG opaco (fundo branco), sem canal alpha. Composto
    direto, o branco tapava a footage e a prancha mostrava texto sobre nada: parecia
    conferida e nao estava. Recupero o alpha exato com dois passes:

        sobre preto : Cb = C*a
        sobre branco: Cw = C*a + (1-a)
        logo        : (Cw - Cb) = 1 - a  e  composto sobre F = Cb + F*(Cw - Cb)

    Por canal, o que ainda respeita o antialias de subpixel do texto.
    """
    dst = only / "snaps"
    pr_, br_ = dst / "preto", dst / "branco"
    if reaproveitar and pr_.exists() and br_.exists():
        a = sorted(pr_.glob("frame-*.png"), key=_idx)
        b = sorted(br_.glob("frame-*.png"), key=_idx)
        if len(a) == len(b) == len(tempos):
            print("[4/5] snapshot: reaproveitando os dois passes existentes", flush=True)
            return list(zip(a, b))
    print(f"[4/5] snapshot do overlay em {len(tempos)} tempos "
          f"(dois passes, preto e branco, pra recuperar o alpha)...", flush=True)
    if dst.exists():
        shutil.rmtree(dst)
    at = ",".join(f"{t:.2f}" for t in tempos)
    pares = []
    for cor, nome in (("#000000", "preto"), ("#ffffff", "branco")):
        proj = _variante_fundo(only, cor, nome)
        saida = dst / nome
        sh([HF, "snapshot", ".", "--at", at, "--no-end", "-o", str(saida),
            "--describe", "false"], cwd=str(proj))
        pares.append(sorted(saida.glob("frame-*.png"), key=_idx))
        shutil.rmtree(proj, ignore_errors=True)
    if len(pares[0]) != len(pares[1]):
        print(f"   [AVISO] passes desiguais: {len(pares[0])} x {len(pares[1])}", flush=True)
    return list(zip(pares[0], pares[1]))


def dur_video(p):
    return float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "csv=p=0", str(p)]).strip())


def quadro(foot, t, dst, limite=None):
    """Extrai um quadro. Seek alem do fim devolve rc=0 e NAO escreve nada: sem a guarda
    o script morre la na frente, abrindo um arquivo que nunca existiu, e some com a
    prancha inteira depois de 4 minutos de trabalho."""
    if limite is not None:
        t = min(t, max(limite - 0.08, 0.0))
    sh(["ffmpeg", "-v", "error", "-y", "-i", str(foot), "-ss", f"{t:.3f}",
        "-frames:v", "1", str(dst)])
    if not dst.exists():
        print(f"   [sem quadro] footage nao tem {t:.2f}s", flush=True)
        return None
    return dst


def compor(foot_png, par):
    """Quadro final = footage + overlay, com o alpha recuperado dos dois passes."""
    pre, bra = par
    F = np.asarray(Image.open(foot_png).convert("RGB"), dtype=np.float32) / 255.0
    Cb = np.asarray(Image.open(pre).convert("RGB"), dtype=np.float32) / 255.0
    Cw = np.asarray(Image.open(bra).convert("RGB"), dtype=np.float32) / 255.0
    if Cb.shape != F.shape:
        F = np.asarray(Image.open(foot_png).convert("RGB").resize(
            (Cb.shape[1], Cb.shape[0])), dtype=np.float32) / 255.0
    inv_a = np.clip(Cw - Cb, 0.0, 1.0)      # 1 - alpha, por canal
    out = np.clip(Cb + F * inv_a, 0.0, 1.0)
    return Image.fromarray((out * 255).astype(np.uint8), "RGB")


def regua(pr, dst):
    """Regua de tempo: insert x avatar, letterings, legendas e vaos sem texto."""
    L, alt_l = 1600, 34
    total = pr["total"]
    im = Image.new("RGB", (L + 40, 480), (17, 17, 17))
    dr = ImageDraw.Draw(im)
    f = fonte(15)

    def x(t):
        return 20 + int(L * t / total)

    faixas = [
        ("blocos", [(b["s"], b["e"], (70, 70, 78) if b["tipo"] != "insert" else (232, 122, 44))
                    for b in pr["blocos"]]),
        ("inserts", [(i["s"], i["s"] + i["d"], (232, 122, 44)) for i in pr["inserts"]]),
        ("letterings", [(l["s"], l["s"] + l["d"], (90, 190, 255)) for l in pr["letterings"]]),
        ("legendas", [(g["s"], g["e"], (120, 200, 120)) for g in pr["legendas"]]),
        # faixa nova: o que o espectador REALMENTE ve trocar. Cada risco e um corte.
        ("planos (o corte real)",
         [(x["s"], x["e"], (232, 122, 44) if x.get("tipo") == "insert" else (90, 90, 100))
          for x in (pr.get("_planos_ritmo") or [])]),
    ]
    y = 30
    for nome, itens in faixas:
        dr.text((20, y - 18), nome, fill=(200, 200, 200), font=f)
        dr.rectangle([20, y, 20 + L, y + alt_l], fill=(34, 34, 38))
        for a, b, cor in itens:
            dr.rectangle([x(a), y, max(x(b), x(a) + 2), y + alt_l], fill=cor)
        y += alt_l + 26

    # marcas de tempo a cada 10s do arquivo ENTREGUE (ja acelerado)
    ac = pr.get("accel", 1.35)
    dr.text((20, y + 4), f"total {total:.1f}s de audio  =  {total / ac:.1f}s no arquivo "
                         f"(accel {ac}x)   |   maior vao sem texto: "
                         f"{pr['vao_sem_texto']['maior']:.2f}s em "
                         f"{pr['vao_sem_texto']['em']:.2f}s",
            fill=(255, 214, 0), font=fonte(17))
    # buraco 3 do diretor: a regua media vao sem TEXTO (1,76s, parece otimo) e escondia
    # os trechos de 15,7s e 16,0s sem TROCAR DE IMAGEM, que era o problema real.
    # PELO PLANO, nao pelo bloco: o ritmo.py subdivide bloco longo em planos curtos, e
    # medir por fronteira de bloco reporta um vao que nao existe mais na tela.
    _plan = pr.get("_planos_ritmo") or [{"s": b["s"]} for b in pr["blocos"]]
    _cortes = sorted({0.0} | {x["s"] for x in _plan} | {total})
    _vao_img, _vao_img_em = 0.0, 0.0
    for a, b in zip(_cortes, _cortes[1:]):
        if b - a > _vao_img:
            _vao_img, _vao_img_em = b - a, a
    dr.text((20, y + 52), f"maior vao SEM CORTE DE IMAGEM: {_vao_img:.2f}s em "
                          f"{_vao_img_em:.2f}s", fill=(255, 140, 60), font=fonte(17))
    t_ins = sum(i["d"] for i in pr["inserts"])
    _np = len(pr.get("_planos_ritmo") or [])
    if _np:
        _ac = pr.get("accel", 1.35)
        _dur_ent = total / _ac
        dr.text((20, y + 76), f"RITMO: {_np} planos = "
                              f"{(_np - 1) / (_dur_ent / 60):.1f} cortes/min, plano medio "
                              f"{_dur_ent / _np:.2f}s   (referencia: 18,9 a 27,8 cortes/min, "
                              f"plano 2,16 a 3,17s)", fill=(120, 220, 140), font=fonte(17))
    dr.text((20, y + 28), f"densidade de insert: {t_ins / total:.0%} do tempo "
                          f"({t_ins:.1f}s de {total:.1f}s)",
            fill=(200, 200, 200), font=fonte(17))
    im.save(dst)
    return dst


def _plano_de_ritmo_do_ad(ad, pr):
    """O plano que os dois motores vao usar. A regua mostra ELE, nao os blocos crus."""
    try:
        # (migracao 26/08/2026) codigo agora vizinho; import direto resolve
        import ritmo as _R
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
                           "crop": cfg.get("crop"), "dur_max": cfg.get("dur_max")})
        return _R.plano_de_ritmo(blocos)
    except Exception as ex:
        print(f"  [AVISO] plano de ritmo nao calculado ({ex}); regua sai pelos blocos",
              flush=True)
        return []


def emendas_pipoca(pr):
    """Instantes do ANUNCIO onde um arquivo 'pipoca' troca de asset interno.

    Pipoca e N assets colados num arquivo so. Cada parte tem enquadramento proprio, entao
    um `crop` unico conserta uma e quebra a outra. Acho os cortes por deteccao de cena na
    FONTE e converto pro tempo do anuncio.
    """
    import json as _json
    ins_p = V1 / "inputs" / f"{pr['ad']}_inserts.json"
    cfgs = _json.loads(ins_p.read_text())
    por_i = {f"broll{i + 1:02d}.mp4": c for i, c in enumerate(cfgs.values())}
    out = {}
    for ins in pr["inserts"]:
        cfg = por_i.get(ins["src"])
        if not cfg or "pipoca" not in os.path.basename(cfg["file"]):
            continue
        try:
            txt = subprocess.run(
                ["ffprobe", "-v", "error", "-show_frames", "-of", "csv=p=0",
                 "-f", "lavfi", f"movie={cfg['file']},select=gt(scene\,0.4)",
                 "-show_entries", "frame=pkt_pts_time"],
                capture_output=True, text=True, timeout=180).stdout
        except Exception:
            continue
        sp = float(cfg.get("speed", 1.0) or 1.0)
        st = float(cfg.get("start", 0) or 0)
        tempos = []
        for ln in txt.strip().splitlines():
            try:
                tsrc = float(ln.split(",")[0])
            except (ValueError, IndexError):
                continue
            if tsrc <= st:
                continue
            tad = ins["s"] + (tsrc - st) / sp
            if ins["s"] < tad < ins["s"] + ins["d"]:
                tempos += [round(max(tad - 0.3, ins["s"] + 0.05), 2),
                           round(min(tad + 0.3, ins["s"] + ins["d"] - 0.05), 2)]
        if tempos:
            out[ins["src"]] = tempos[:6]
            print(f"  [emenda] {ins['src']}: troca de asset em {tempos}", flush=True)
    return out


def pontos(pr):
    """Os tempos que a prancha amostra. Saem da REGRA, nao da minha escolha:

    hook fixo, insert em 4 pontos da propria janela, lettering na entrada e no fim,
    CTA na subida e no fecho. Assim eu nao consigo montar uma prancha so com os quadros
    que me favorecem.
    """
    ts = []
    marcas = []
    for t in (0.0, 0.6, 1.4, 2.6):
        if t < pr["total"]:
            ts.append(t); marcas.append(("HOOK", f"{t:.1f}s", ""))
    # FATIA, nao bloco (buraco 3): o ritmo devolve o rosto no meio do bloco, entao
    # amostrar 1/4, 2/4, 3/4 do BLOCO caia em avatar e escondia a tela. No AD14 b01,
    # 2 dos 4 quadros eram cara do Thales.
    for _f in pr.get("_planos_ritmo") or []:
        if _f.get("tipo") != "insert":
            continue
        _dur = _f["e"] - _f["s"]
        for _q, _fr in (("entrada", 0.12), ("meio", 0.55)):
            t = _f["s"] + _dur * _fr
            ts.append(t)
            _off = _f.get("fonte_off")
            _extra = f", fonte +{_off:.1f}s" if _off else ""
            marcas.append(("FATIA", f"bloco {_f['bloco']} fatia {_f.get('sub', 0) + 1}",
                           f"{t:.1f}s ({_q} de {_dur:.1f}s{_extra})"))

    for ins in pr["inserts"]:
        s, d = ins["s"], ins["d"]
        for k, frac in enumerate((0.05, 0.35, 0.68, 0.95)):
            t = s + d * frac
            ts.append(t)
            marcas.append(("INSERT", f"{ins['label'] or ins['src']}",
                           f"{t:.1f}s ({k + 1}/4 da janela de {d:.1f}s)"))
    for l in pr["letterings"]:
        for t, q in ((l["s"] + 0.45, "entrada"), (l["s"] + max(l["d"] - 0.25, 0.6), "fim")):
            ts.append(t)
            marcas.append(("LETTERING", f"{l['lead']} | {l['key']}"[:52],
                           f"{t:.1f}s ({q}{', pilha' if l['pilha'] else ''}"
                           f"{', baixo' if l['baixo'] else ''}"
                           f"{', split' if l['split'] else ''})"))
    # BLOCO DE AVATAR LONGO (buraco 1 do diretor): a folha pulava 16,4s do anuncio,
    # justamente o trecho mais longo de avatar puro, onde entram letterings novos. Sem
    # quadro nao da pra saber se o enquadramento e peito ou close, e isso muda a classe
    # do card. Todo bloco `orig` acima de 5s ganha 2 quadros.
    for b in pr["blocos"]:
        if b["tipo"] != "insert" and b["dur"] > 5.0:
            for frac in (0.3, 0.7):
                t = b["s"] + b["dur"] * frac
                ts.append(t)
                marcas.append(("AVATAR", b["instr"][:52],
                               f"{t:.1f}s (bloco {b['i']}, {b['dur']:.1f}s de avatar)"))

    # SAIDA DO HOOK (buraco 4): a folha parava em 2,6s e o hook morre depois, com a
    # primeira legenda entrando quase junto. Ninguem sabia se os dois se cruzam.
    for t in (pr["hook"]["fim"] - 0.2, pr["hook"]["fim"] + 0.15):
        if 0 < t < pr["total"]:
            ts.append(t)
            marcas.append(("HOOK", "saida do hook", f"{t:.1f}s (fim {pr['hook']['fim']:.1f}s)"))

    # CONGELAMENTO (buraco 2, o mais valioso): quadro parado NUNCA denuncia quadro
    # congelado, porque congelado e um quadro normal repetido. A aritmetica denuncia:
    # amostro exatamente o instante em que a fonte do insert acaba.
    for l in pr.get("_congelamento", []):
        if l.get("congela_em"):
            t = l["congela_em"]
            ts.append(min(t + 0.25, pr["total"] - 0.1))
            marcas.append(("CONGELAMENTO", f"{l['chave']} {l['arquivo'][:26]}",
                           f"{t:.1f}s: a fonte acaba aqui e congela {l['congela']:.2f}s"))

    # EMENDA DA PIPOCA (buraco 6): arquivo com N assets colados tem enquadramentos
    # diferentes em cada parte, e um crop unico conserta uma e quebra a outra.
    for ins in pr["inserts"]:
        for t in pr.get("_emendas", {}).get(ins["src"], []):
            ts.append(t)
            marcas.append(("EMENDA", ins["label"][:52], f"{t:.1f}s (troca de asset dentro do arquivo)"))

    # FECHAMENTO: um quadro por PLANO na janela do CTA (buraco 1). Amostrar so "subida"
    # e "ultimo quadro" escondeu que o CTA do AD14 passa 5,5s por cima de pagina BRANCA.
    cta = pr["cta"]["inicio"]
    for x in [p for p in (pr.get("_planos_ritmo") or [])
              if p["e"] > cta and p["s"] < pr["total"]]:
        t = max(x["s"], cta) + min(0.5, (x["e"] - max(x["s"], cta)) / 2)
        ts.append(t)
        marcas.append(("FECHAMENTO", f"{pr['cta']['label']} sobre {x['tipo']}",
                       f"{t:.1f}s (plano {x['s']:.1f}-{x['e']:.1f}s)"))
    for t, q in ((cta + 0.6, "subida"), (pr["total"] - 0.35, "ultimo quadro")):
        ts.append(t)
        marcas.append(("FECHAMENTO", pr["cta"]["label"], f"{t:.1f}s ({q})"))
    return ts, marcas


def main():
    ad = sys.argv[1]
    # produzir_ad aceita "jh13"; os configs e inputs moram como "jh13v2". Normalizo aqui
    # pra prancha e build falarem do mesmo ad sem eu ter que lembrar do sufixo.
    if not list((V2L / "configs").glob(f"{ad}_*.json")) and \
            list((V2L / "configs").glob(f"{ad}v2_*.json")):
        ad = f"{ad}v2"
    look = sys.argv[2] if len(sys.argv) > 2 else None
    if not look:
        cfgs = list((V2L / "configs").glob(f"{ad}_*.json"))
        inv = {v: k for k, v in LK.items()}
        look = inv.get(cfgs[0].stem.split("_", 1)[1]) if cfgs else None
        if not look:
            sys.exit("informe o look")
    out = V2L / "prancha" / ad
    out.mkdir(parents=True, exist_ok=True)

    rap = "--rapido" in sys.argv        # reaproveita footage e snapshots ja feitos
    pr, workdir, only, base = preparar(ad, look)
    # aritmetica de fonte ANTES de escolher os pontos: e ela que diz onde congela
    pr["_congelamento"] = AI.analisar(ad, pr)
    print("  congelamento por insert (fonte x consumo):", flush=True)
    AI.imprimir(pr["_congelamento"])
    pr["_emendas"] = emendas_pipoca(pr)
    pr["_planos_ritmo"] = _plano_de_ritmo_do_ad(ad, pr)
    foot = footage(ad, look, base, rap)
    ts, marcas = pontos(pr)
    pngs = snapshots(only, ts, rap)
    if len(pngs) != len(ts):
        print(f"   [AVISO] pedi {len(ts)} snapshots e vieram {len(pngs)}; "
              f"a prancha sai incompleta", flush=True)

    dfoot = dur_video(foot)
    print(f"[5/5] compondo os quadros (footage {dfoot:.2f}s)...", flush=True)
    tmp = out / "_tmp"
    tmp.mkdir(exist_ok=True)
    grupos = {}
    for i, (t, (sec, tit, sub)) in enumerate(zip(ts, marcas)):
        if i >= len(pngs):
            break
        fp = quadro(foot, t, tmp / f"f{i}.png", limite=dfoot)
        if fp is None:
            continue
        im = compor(fp, pngs[i])
        im = marcar_safe(im.convert("RGB"))
        # luminancia das duas faixas onde texto mora: hook (14-42%) e legenda/lettering
        # (62-88%). Acima de 180, texto branco some. Buraco 2 do diretor: ele teve que
        # medir na mao pra provar o hook do AD15 (L=231 contra L=31).
        _lh = luminancia_faixa(im, 0.14, 0.42)
        _ll = luminancia_faixa(im, 0.62, 0.88)
        _alerta = "  <<< FUNDO CLARO: texto branco some" if (_lh > 180 or _ll > 180) else ""
        im = rotular(im, tit, f"{sub}  |  L topo {_lh:.0f} / L baixo {_ll:.0f}{_alerta}")
        grupos.setdefault(sec, []).append(im)

    feitas = []
    for sec, ims in grupos.items():
        d = out / f"{sec.lower()}.png"
        folha(ims, d, cols=4 if sec == "HOOK" else 6)
        feitas.append(d)
    feitas.append(regua(pr, out / "regua.png"))
    (out / "prancha.json").write_text(json.dumps(pr, ensure_ascii=False, indent=2))
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nPRANCHA {ad} [{look}] pronta em {out}")
    for f in feitas:
        print(f"  {f}")


if __name__ == "__main__":
    main()
