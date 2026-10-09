#!/usr/bin/env python3
"""Mostruário dos 8 estilos de lettering: um vídeo 9:16 curto (cerca de 2 s por estilo, com o nome escrito) e uma
folha de quadros PNG (um quadro por estilo, no instante em que a KEY está inteira). É a prévia para o dono (ou o
aluno) escolher o estilo vendo, em vez de adivinhar pelo nome.

    python3 scripts/cinema/mostruario_lettering.py <pasta_saida> [--video lettering_previa.mp4] [--sem-video]

O fundo é gerado por código (degradê escuro neutro e uma silhueta lisa no lugar do apresentador, sem rosto real),
com as guias da zona segura (x 940 e y 1690) tracejadas. Os letterings saem do MESMO caminho do anúncio: o template
9x16 com os parciais resolvidos (`overlay.html_injecao.ler_template`) e o HTML do `overlay.letterings.html`; o que
aparece aqui é o que o overlay renderiza.

Também mede (modo `medida`: fundo preto, sem guia nem rótulo) a tinta de cada estilo em +0,15 s e em +0,60 s da
entrada, e a caixa da tinta assentada: é a prova `lento` de que a KEY é legível em até 0,15 s e cabe na FAIXA.

Render: `node_modules/.bin/hyperframes` do repo, ou o caminho em VAM_HYPERFRAMES. Saída 0 gerou, 2 insumo ausente.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":      # rodado direto: scripts/cinema/mostruario_lettering.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinema import lettering_estilos as LE  # noqa: E402
from overlay import html_injecao as H  # noqa: E402
from overlay import letterings as LT  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
TEMPLATE = RAIZ / "templates" / "reel-editorial" / "index.html"

INTRO_S = 1.2           # o gancho do próprio template abre o mostruário
SEGMENTO_S = 2.0        # cada estilo
ENTRADA_S = 0.25        # o lettering entra 0,25 s depois do rótulo
DURACAO_LETT = 1.6
T_INTEIRA = 0.60        # "KEY inteira": depois de toda entrada assentar
LIMIAR_TINTA = 60       # luminância acima disso, no fundo preto, é tinta (sombra e vinheta ficam abaixo)

# texto de exemplo por estilo (genérico, sem marca nem nome)
AMOSTRAS = {
    "caixa_nativa": {"lead": "o problema não é", "key": "FALTA DE TEMPO", "cor": "ambar"},
    "serif_editorial": {"lead": "sabe qual é", "key": "O MELHOR"},
    "punch": {"lead": "você perde", "key": "3 HORAS POR DIA"},
    "marcador": {"lead": "você economiza", "key": "*20 HORAS* POR SEMANA"},
    "statement": {"lead": "a verdade é que", "key": "NINGUÉM TE CONTOU ISSO"},
    "lateral": {"lead": "passo um", "key": "AUTOMATIZE O REPETIDO"},
    "seta_cta": {"lead": "toque em", "key": "SAIBA MAIS"},
    "gigante_atras": {"lead": "é", "key": "AGORA"},
}
NOME_CURTO = {e: e.replace("_", " ") for e in LE.ESTILOS}
DESCRICAO = {
    "caixa_nativa": "caixa nativa (ambar, branco, preto)",
    "serif_editorial": "serif editorial (padrão)",
    "punch": "punch",
    "marcador": "marcador",
    "statement": "statement",
    "lateral": "lateral",
    "seta_cta": "seta CTA",
    "gigante_atras": "gigante atrás",
}

_CSS_FUNDO = """
      #fundo { position:absolute; inset:0; z-index:0;
        background:radial-gradient(90% 60% at 50% 38%, #2b303b 0%, #161920 58%, #0b0c10 100%); }
      #fundo .ombros { position:absolute; left:170px; top:1010px; width:740px; height:1100px;
        border-radius:370px 370px 0 0; background:linear-gradient(180deg, #343a46, #23272f); }
      #fundo .cabeca { position:absolute; left:385px; top:560px; width:310px; height:400px; border-radius:50%;
        background:radial-gradient(60% 55% at 45% 40%, #4a515e, #353b46); }
      #fundo .guia-x { position:absolute; left:940px; top:0; bottom:0; border-left:3px dashed rgba(255,90,77,.65); }
      #fundo .guia-y { position:absolute; top:1690px; left:0; right:0; border-top:3px dashed rgba(255,90,77,.65); }
      #fundo .nota { position:absolute; left:70px; top:1708px; font-family:"Inter"; font-weight:600; font-size:24px;
        letter-spacing:3px; color:rgba(255,120,110,.85); text-transform:uppercase; }
      .rotulo { position:absolute; left:70px; top:96px; z-index:70; font-family:"Inter"; color:#fff; }
      .rotulo .nome { font-weight:800; font-size:46px; letter-spacing:-.5px; }
      .rotulo .sub { font-weight:400; font-size:26px; color:rgba(255,255,255,.72); margin-top:6px; }
"""
_HTML_FUNDO = ('      <div id="fundo"><div class="ombros"></div><div class="cabeca"></div>'
               '<div class="guia-x"></div><div class="guia-y"></div>'
               '<div class="nota">zona segura: tinta até x 940 e y 1690</div></div>\n')


class MostruarioFalhou(Exception):
    """Falta o hyperframes, o template ou o render não saiu."""


def janelas():
    """[(estilo, início do segmento, entrada do lettering)] na ordem de ESTILOS."""
    saida = []
    for i, e in enumerate(LE.ESTILOS):
        s = round(INTRO_S + i * SEGMENTO_S, 3)
        saida.append((e, s, round(s + ENTRADA_S, 3)))
    return saida


def duracao():
    return round(INTRO_S + len(LE.ESTILOS) * SEGMENTO_S, 3)


def _letterings():
    letts = []
    for i, (e, _s, t0) in enumerate(janelas()):
        a = AMOSTRAS[e]
        l = {"id": "lett%s" % chr(65 + i), "lead": a["lead"], "key": a["key"], "start": t0, "dur": DURACAO_LETT,
             "split": False, "logo": False, "baixo": False, "pilha": None, "estilo": e}
        if a.get("cor"):
            l["cor"] = a["cor"]
        letts.append(l)
    return letts


def montar_html(modo="mostruario"):
    """O index.html do mostruário (`mostruario`) ou da medida (`medida`: fundo preto, sem guia nem rótulo)."""
    if modo not in ("mostruario", "medida"):
        raise ValueError("modo desconhecido: %r" % modo)
    total = duracao()
    html = H.ler_template(TEMPLATE)
    html = H.injetar_marcadores(html, "", LT.html(_letterings()))
    html = H.injetar_chips(html, "")
    html = H.fixar_duracao(html, total)
    html = H.remover_beat_pb(html)
    html = H.remover_wipes(html)
    # sem imagem de fundo, sem CTA nem logo do anúncio: só o lettering
    html = "\n".join(ln for ln in html.split("\n") if 'id="a-roll' not in ln and 'id="ev-logo"' not in ln)
    html = re.sub(r'\s*<!-- CTA -->\s*<div data-hf-id="hf-bi9a" id="cta".*?</div>\s*</div>', "", html, flags=re.S)
    # o gancho do template abre o mostruário (só no modo de ver)
    gancho = ("mostruário", "8 estilos de", "lettering") if modo == "mostruario" else ("", "", "")
    html = html.replace('id="hook" class="clip" data-start="0" data-duration="2.5"',
                        'id="hook" class="clip" data-start="0" data-duration="%s"' % INTRO_S)
    for classe, texto in zip(("eyebrow", "l1", "accent"), gancho):
        html = re.sub(r'(class="%s">)[^<]*(</div>)' % classe, lambda m: m.group(1) + texto + m.group(2), html, count=1)
    if modo == "mostruario":
        html = html.replace("</style>", _CSS_FUNDO + "    </style>", 1)
        rotulos = "".join(
            '      <div class="rotulo clip" data-start="%s" data-duration="%s" data-track-index="%d">'
            '<div class="nome">%s</div><div class="sub">entrada seca: KEY legível em até 0,15 s</div></div>\n'
            % (s, SEGMENTO_S, 70 + i, DESCRICAO[e]) for i, (e, s, _t) in enumerate(janelas()))
        html = html.replace('<div data-hf-id="hf-9j86" id="grade"></div>',
                            _HTML_FUNDO + rotulos + '      <div data-hf-id="hf-9j86" id="grade"></div>', 1)
    else:
        html = html.replace("background:#05060a; }", "background:#000; }", 1)
        html = html.replace('<div data-hf-id="hf-9j86" id="grade"></div>', "", 1)
        html = html.replace('<div data-hf-id="hf-h7i3" id="vignette"></div>', "", 1)
    return html


def preparar_pasta(pasta, modo="mostruario"):
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "index.html").write_text(montar_html(modo), encoding="utf-8")
    if (pasta / "fonts").exists():
        shutil.rmtree(pasta / "fonts")
    shutil.copytree(TEMPLATE.parent / "fonts", pasta / "fonts")          # segue os symlinks das fontes OFL
    shutil.copy(TEMPLATE.parent / "meta.json", pasta / "meta.json")
    return pasta


def hyperframes():
    for c in (os.environ.get("VAM_HYPERFRAMES"), str(RAIZ / "node_modules" / ".bin" / "hyperframes")):
        if c and Path(c).exists():
            return c
    raise MostruarioFalhou("hyperframes ausente: rode `bash setup.sh` (ou defina VAM_HYPERFRAMES)")


def _snapshot(hf, pasta, instantes, destino):
    if Path(destino).exists():
        shutil.rmtree(destino)
    r = subprocess.run([hf, "snapshot", str(pasta), "--at", ",".join("%.3f" % t for t in instantes), "--no-end",
                        "--describe", "false", "--no-browser-gpu", "-o", str(destino)],
                       capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        raise MostruarioFalhou("snapshot falhou: %s" % (r.stderr or r.stdout).strip()[-400:])
    pngs = sorted(Path(destino).glob("frame-*.png"), key=lambda p: int(re.search(r"frame-(\d+)", p.name).group(1)))
    if len(pngs) != len(instantes):
        raise MostruarioFalhou("snapshot devolveu %d quadros, pedi %d" % (len(pngs), len(instantes)))
    return pngs


def renderizar_video(hf, pasta, saida):
    r = subprocess.run([hf, "render", str(pasta), "-o", str(saida), "--fps", "30", "--workers", "2", "--quiet"],
                       capture_output=True, text=True, timeout=1800)
    if r.returncode != 0 or not Path(saida).is_file():
        raise MostruarioFalhou("render falhou: %s" % (r.stderr or r.stdout).strip()[-400:])
    return Path(saida)


def quadros_key_inteira(hf, pasta, destino):
    """{estilo: png} no instante em que a KEY está inteira (entrada + 0,60 s)."""
    inst = [t0 + T_INTEIRA for _e, _s, t0 in janelas()]
    pngs = _snapshot(hf, pasta, inst, destino)
    return dict(zip(LE.ESTILOS, pngs))


def folha(quadros, saida, largura_painel=360):
    """Folha de quadros: 4 colunas x 2 linhas, nome do estilo embaixo de cada painel."""
    from PIL import Image, ImageDraw, ImageFont
    alt = int(round(largura_painel * 1920 / 1080))
    faixa = 54
    cols, linhas = 4, 2
    folha_img = Image.new("RGB", (cols * largura_painel + (cols + 1) * 12, linhas * (alt + faixa) + (linhas + 1) * 12),
                          (12, 12, 14))
    try:
        fonte = ImageFont.truetype(str(RAIZ / "fonts" / "montserrat-800.ttf"), 24)
    except (OSError, ValueError):
        fonte = ImageFont.load_default()
    d = ImageDraw.Draw(folha_img)
    for i, e in enumerate(LE.ESTILOS):
        c, li = i % cols, i // cols
        x = 12 + c * (largura_painel + 12)
        y = 12 + li * (alt + faixa + 12)
        im = Image.open(quadros[e]).convert("RGB").resize((largura_painel, alt), Image.LANCZOS)
        folha_img.paste(im, (x, y))
        d.text((x + 8, y + alt + 12), NOME_CURTO[e], fill=(255, 255, 255), font=fonte)
    folha_img.save(saida)
    return Path(saida)


def _tinta(png):
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(png).convert("L"))
    return a > LIMIAR_TINTA


def medir_legibilidade(pasta, hf=None):
    """Para cada estilo: tinta em +0,15 s, tinta assentada (+0,60 s), a fração e a caixa da tinta assentada
    (x0, y0, x1, y1). Modo `medida`: fundo preto, então tinta é luminância acima de LIMIAR_TINTA."""
    import numpy as np
    hf = hf or hyperframes()
    pasta = preparar_pasta(Path(pasta) / "medida", "medida")
    inst = []
    for _e, _s, t0 in janelas():
        inst += [t0 - 0.10, t0 + LE.ENTRADA_LEGIVEL_S, t0 + T_INTEIRA]
    pngs = _snapshot(hf, pasta, inst, pasta / "snaps")
    saida = []
    for i, e in enumerate(LE.ESTILOS):
        antes, cedo, inteira = (_tinta(p) for p in pngs[3 * i:3 * i + 3])
        n_cedo, n_int = int((cedo & ~antes).sum()), int((inteira & ~antes).sum())
        m = inteira & ~antes
        ys, xs = np.nonzero(m)
        caixa = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())) if n_int else None
        saida.append({"estilo": e, "tinta_015_px": n_cedo, "tinta_assentada_px": n_int,
                      "fracao_015": round(n_cedo / n_int, 4) if n_int else 0.0, "caixa_tinta": caixa,
                      "fundo_antes_px": int(antes.sum())})
    return saida


def gerar(pasta_saida, video="lettering_previa.mp4", com_video=True):
    """Gera o vídeo, os quadros, a folha e o relatório de medida em `pasta_saida`. Devolve o relatório."""
    hf = hyperframes()
    saida = Path(pasta_saida)
    saida.mkdir(parents=True, exist_ok=True)
    trabalho = saida / "_mostruario"
    proj = preparar_pasta(trabalho / "projeto", "mostruario")
    rel = {"duracao_s": duracao(), "estilos": []}
    if com_video:
        rel["video"] = str(renderizar_video(hf, proj, saida / video))
    quadros = quadros_key_inteira(hf, proj, trabalho / "quadros")
    pasta_q = saida / "lettering_quadros"
    pasta_q.mkdir(exist_ok=True)
    for i, e in enumerate(LE.ESTILOS):
        shutil.copy(quadros[e], pasta_q / ("%d_%s.png" % (i + 1, e)))
    rel["folha"] = str(folha({e: pasta_q / ("%d_%s.png" % (i + 1, e)) for i, e in enumerate(LE.ESTILOS)},
                             saida / "lettering_folha.png"))
    medidas = medir_legibilidade(trabalho, hf)
    for m in medidas:
        f = LE.FAIXAS[m["estilo"]]
        x0, y0, x1, y1 = m["caixa_tinta"] or (0, 0, 0, 0)
        m["faixa"] = f
        m["dentro_da_faixa"] = bool(m["caixa_tinta"]) and f["x0"] - 4 <= x0 and x1 <= f["x1"] + 4 \
            and f["y0"] - 4 <= y0 and y1 <= f["y1"] + 4
        m["legivel_015"] = m["fracao_015"] >= LE.ALFA_LEGIVEL
        rel["estilos"].append(m)
    (saida / "lettering_medida.json").write_text(json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
    return rel


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mostruário dos 8 estilos de lettering (vídeo 9:16 + folha de quadros).")
    ap.add_argument("saida", help="pasta de saída")
    ap.add_argument("--video", default="lettering_previa.mp4", help="nome do vídeo (padrão lettering_previa.mp4)")
    ap.add_argument("--sem-video", action="store_true", help="só os quadros, a folha e a medida")
    a = ap.parse_args(argv)
    try:
        rel = gerar(a.saida, a.video, not a.sem_video)
    except MostruarioFalhou as e:
        print("ERRO: %s" % e, file=sys.stderr)
        return 2
    for m in rel["estilos"]:
        print("%-16s tinta em 0,15 s: %5.1f%%  caixa %s  faixa %s" % (
            m["estilo"], 100 * m["fracao_015"], m["caixa_tinta"],
            "dentro" if m["dentro_da_faixa"] else "FORA"))
    print("folha: %s" % rel["folha"])
    if rel.get("video"):
        print("vídeo: %s" % rel["video"])
    ruins = [m["estilo"] for m in rel["estilos"] if not (m["legivel_015"] and m["dentro_da_faixa"])]
    return 1 if ruins else 0


if __name__ == "__main__":
    sys.exit(main())
