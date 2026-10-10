#!/usr/bin/env python3
"""Prancha de direcao: o anuncio inteiro em quadro parado, ANTES de renderizar.

Por que existe (ordem do diretor, 18/08/2026): "se ele e um diretor, ele dirige, nao apenas
audita no final". Eu classifiquei item por item a auditoria que reprovou o anúncio de referência com 6,3:
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

Uso (pelo vam, que monta o ambiente do projeto):  python3 scripts/vam.py plano <slug> --prancha
Direto:  VAM_DADOS=<projeto>/render/motor python3 scripts/prancha_direcao.py <slug> [--estado _local] [--rapido]

POR PROJETO (W5.A, defeito 1 do plano): a prancha procurava o gerador do overlay dentro do `_local` (onde ele não
existe) e quebrava no clone limpo. Agora ela usa os passos do build (`build_composite.Motor`: arquivos do motor,
timeline, overlay e footage) sobre o projeto do aluno, e escreve em `plano/prancha/` do projeto.
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

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import analise_inserts as AI                     # noqa: E402
import build_composite as BC                     # noqa: E402
from caminhos import V1                          # noqa: E402  (com VAM_DADOS do projeto: render/motor)
# A decisão de tinta, placa e faixa é a do overlay, uma função só (W7.X): a prancha não tem regra própria de fundo claro.
from overlay.fundo_claro import decisao_do_quadro   # noqa: E402,F401

HF = str(BC.hyperframes())

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


_TINTA = {"clara": "tinta clara", "invertida": "tinta invertida", "placa": "placa escura", None: "sem medida"}


def texto_da_decisao(decisao):
    """A decisão do overlay (fundo_claro.decisao_do_quadro) em uma linha para o rótulo do quadro."""
    return "legenda: %s | gancho: %s" % (_TINTA[decisao["legenda"]],
                                         "placa" if decisao["gancho"] == "placa" else "branco fino")


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
def pasta_de_saida(pj):
    """Onde a prancha do projeto sai: plano/prancha/."""
    return pj.prancha_dir


def preparar_arquivos(motor):
    """Arquivos do motor e timeline (relógio único). Não renderiza nada."""
    print("[1/5] arquivos do motor e timeline (relógio único)...", flush=True)
    motor.escrever_arquivos_do_motor()
    motor.construir_timeline()


def preparar_overlay(motor):
    """Overlay HTML (gen_ad_v2 com a timeline e a FOOTAGE) e o projeto do HyperFrames que o snapshot lê."""
    print("[3/5] overlay HTML (gen_ad_v2 com a timeline e a footage) e o transparente...", flush=True)
    if motor.gerar_overlay() is None:
        raise BC.ErroDoMotor("overlay", (motor.saida_overlay or (None, ""))[1].strip()[-600:])
    only = motor.projeto_do_overlay()
    pr = json.loads((motor.overlay_dir / "prancha.json").read_text())
    return pr, only


def footage(motor, reaproveitar=False):
    """A footage a 1x (o único passo pesado da prancha, de 1 a 2 min por anúncio)."""
    if reaproveitar and motor.footage.exists():
        print("[2/5] footage: reaproveitando a existente", flush=True)
        return motor.footage
    print("[2/5] footage (sem texto)...", flush=True)
    return motor.montar_footage()


def construir(motor, reaproveitar=False):
    """Timeline, footage e overlay, NESSA ordem (a do build, produzir_ad): o overlay decide a tinta invertida, a placa
    da legenda e a placa do gancho medindo o fundo NA footage; sem ela cai no arquivo-fonte e decide pelo fundo errado
    (a prancha desenhava legenda e gancho do jeito antigo). Devolve (prancha.json, projeto do overlay, footage)."""
    preparar_arquivos(motor)
    foot = footage(motor, reaproveitar)
    pr, only = preparar_overlay(motor)
    return pr, only, foot


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


def linhas_de_medida(plano):
    """As linhas de RITMO e DENSIDADE da régua, lidas do plano.json (plano.medir), nunca contadas de novo.

    O plano.medir é a fonte única: `cortes_previstos` foi calibrada contra o render real (W5.X), enquanto a régua
    antiga contava toda fronteira de plano como corte e media a densidade pela janela do insert (23,6 cortes/min e 49%
    onde o plano_edicao.md dizia 9,8 e 42,7%). Sem plano.json a régua não inventa número: manda rodar `vam plano`."""
    from plano.checklist import numero
    if not plano:
        return ["RITMO e densidade: sem plano/plano.json; rode vam plano <slug> (a medida vem de lá)"]
    r, d = plano["ritmo"], plano["densidade"]
    ritmo = "RITMO (plano.json): %s cortes por minuto no arquivo entregue" % numero(r["cortes_min"])
    if "plano_medio_s" in r:
        ritmo += ", plano médio %s s" % numero(r["plano_medio_s"])
    return [ritmo + "   (referência: 18,9 a 27,8 cortes/min, plano 2,16 a 3,17 s)",
            "densidade de insert (plano.json): %s%% do tempo" % numero(d["fracao_insert"] * 100)]


def ler_plano(pj):
    """O plano/plano.json do projeto, ou None se ainda não foi medido (vam plano)."""
    from projeto import status
    try:
        return status.ler_json(pj.plano_json)
    except (OSError, ValueError):
        return None


def regua(pr, dst, plano=None):
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
    linhas = linhas_de_medida(plano)
    dr.text((20, y + 76), linhas[0], fill=(120, 220, 140), font=fonte(17))
    if len(linhas) > 1:
        dr.text((20, y + 28), linhas[1], fill=(200, 200, 200), font=fonte(17))
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
                 "-f", "lavfi", f"movie={cfg['file']}," + r"select=gt(scene\,0.4)",
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
    # 2 dos 4 quadros eram o rosto do apresentador.
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


def main(argv=None):
    import argparse
    from projeto import pastas
    ap = argparse.ArgumentParser(prog="prancha_direcao", description="A prancha de direção do projeto, sem render.")
    ap.add_argument("slug")
    ap.add_argument("--estado", help="pasta _local (padrão: a do repo)")
    ap.add_argument("--rapido", action="store_true", help="reaproveita a footage e os snapshots já feitos")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0)
    try:
        pj = pastas.projeto(a.slug, a.estado)
    except ValueError as e:
        print("prancha: %s" % e, file=sys.stderr)
        return 2
    if not pj.projeto_json.is_file():
        print("prancha: o projeto %r não existe em %s: crie com vam novo %s" % (pj.slug, pj.raiz, pj.slug),
              file=sys.stderr)
        return 2
    try:
        return _montar(pj, a.rapido)
    except BC.ErroDoMotor as e:
        print("prancha: %s" % e, file=sys.stderr)
        return 2


def _montar(pj, rap):
    motor = BC.Motor(pj)
    ad = motor.slug
    out = pasta_de_saida(pj)
    out.mkdir(parents=True, exist_ok=True)
    pr, only, foot = construir(motor, rap)
    # aritmetica de fonte ANTES de escolher os pontos: e ela que diz onde congela
    pr["_congelamento"] = AI.analisar(ad, pr)
    print("  congelamento por insert (fonte x consumo):", flush=True)
    AI.imprimir(pr["_congelamento"])
    pr["_emendas"] = emendas_pipoca(pr)
    pr["_planos_ritmo"] = _plano_de_ritmo_do_ad(ad, pr)
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
        # luminancia das duas faixas onde texto mora: hook (14-42%) e legenda/lettering (62-88%), so como numero.
        # A DECISAO (tinta, placa) nao e da prancha: e a do overlay, medida no quadro da footage (W7.X).
        _lh = luminancia_faixa(im, 0.14, 0.42)
        _ll = luminancia_faixa(im, 0.62, 0.88)
        _dec = texto_da_decisao(decisao_do_quadro(fp))
        im = rotular(im, tit, f"{sub}  |  L topo {_lh:.0f} / L baixo {_ll:.0f}  |  o motor aplica: {_dec}")
        grupos.setdefault(sec, []).append(im)

    feitas = []
    for sec, ims in grupos.items():
        d = out / f"{sec.lower()}.png"
        folha(ims, d, cols=4 if sec == "HOOK" else 6)
        feitas.append(d)
    feitas.append(regua(pr, out / "regua.png", ler_plano(pj)))
    (out / "prancha.json").write_text(json.dumps(pr, ensure_ascii=False, indent=2))
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nPRANCHA de {ad} pronta em {out}")
    for f in feitas:
        print(f"  {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
