"""Põe a caixinha de pergunta FIXA sobre o anúncio, do primeiro ao último quadro.

Aceita a caixinha com fundo chapado (tira sozinho, pelas bordas) ou já com transparência. Se o PNG
vier em 1080x1920, respeita a posição que veio; se vier recortado, usa a posição padrão
(x=40, y=210: dentro das margens e abaixo da faixa de UI do Reels, que ocupa os 192 px do topo).

O TETO da caixinha é MEDIDO na peça, não fixo: `area_ad_inteiro` acha o ponto em que a cabeça
sobe mais, e a caixinha avisa se desce além dele. Passe `--teto-y` para usar um valor já medido.

## A caixa de lettering nativa (W5.D)

Sem arte pronta do diretor, a caixa nasce do TEXTO: `gerar_png` pede a `caixa_lettering` o bloco sólido de
canto reto que imita o widget de texto nativo do Instagram (PT Serif do REPO, três colorways, nunca um
quarto), no topo do quadro (abaixo da faixa de UI do Reels), e `compor_texto` a põe sobre a peça. O texto da
caixa é exatamente o que o apresentador lê; a caixa não leva legenda por baixo dela porque a legenda mora
mais abaixo (y 1300).

    python3 scripts/gravado/compor_caixinha.py PECA caixinha.png [--sombra] [--x 40] [--y 210]
                                               [--topo 200] [--teto-y 557] [--projeto DIR]
PECA é o nome da peça montada, como A1_normal (ou A1, que vale A1_normal).
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado import area_ad_inteiro, veredito  # noqa: E402
from gravado import projeto as gp  # noqa: E402
from gravado.extrair_caixinha import extrair  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402

W, H = 1080, 1920
POS_PADRAO = (40, 210)


def preparar(png, x, y, sombra, topo=None):
    """(PNG RGBA 1080x1920 pronto para sobrepor em 0:0, y do topo da caixinha, y da base).

    `topo` reposiciona a caixinha para começar naquele y, mantendo o x que veio: serve quando a arte
    foi desenhada mais embaixo do que a cabeça permite."""
    img = Image.open(png)
    if img.mode != "RGBA" or np.asarray(img)[..., 3].min() == 255:
        img, caixa, _ = extrair(png)                       # veio com fundo chapado
        veio_cheio = img.size == (W, H) or abs(img.width / float(img.height) - W / float(H)) < 0.01
        if veio_cheio and img.size != (W, H):
            img = img.resize((W, int(round(img.height * W / float(img.width)))), Image.LANCZOS)
            if img.height != H:
                ajuste = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ajuste.paste(img, (0, 0), img)
                img = ajuste
        elif not veio_cheio:
            img = img.crop(caixa)
    else:
        veio_cheio = img.size == (W, H)

    if veio_cheio:
        tela = img.convert("RGBA")
        if topo is not None:
            ys = np.where(np.asarray(tela)[..., 3].max(axis=1) > 8)[0]
            desloca = topo - int(ys.min())
            if desloca:
                nova = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                nova.paste(tela, (0, desloca), tela)
                tela = nova
    else:
        if img.width > W - 2 * x:
            nw = W - 2 * x
            img = img.resize((nw, int(round(img.height * nw / float(img.width)))), Image.LANCZOS)
        tela = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        tela.paste(img, (x, y), img)

    alpha = np.asarray(tela)[..., 3]
    ys = np.where(alpha.max(axis=1) > 8)[0]
    topo_real, base = int(ys.min()), int(ys.max())
    if sombra:
        s = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        m = Image.fromarray(alpha).filter(ImageFilter.GaussianBlur(16))
        s.putalpha(Image.fromarray((np.asarray(m) * 0.45).astype(np.uint8)))
        s = Image.composite(Image.new("RGBA", (W, H), (0, 0, 0, 255)), s, m)
        fundo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        fundo.paste(s, (6, 10), s)
        fundo.alpha_composite(tela)
        tela = fundo
    return tela, topo_real, base


def gerar_png(texto, colorway="ambar", topo=POS_PADRAO[1], centro_y=None):
    """A caixa de lettering nativa como PNG RGBA 1080x1920 (transparente fora da caixa). Pronta para
    `compor`. `topo`: o y onde a caixa COMEÇA (padrão 210, abaixo da UI do Reels); `centro_y` (fração da
    altura) manda no lugar de `topo` quando vem (a caixa do one-shot, mais embaixo). InsumoInvalido se o
    colorway não é um dos três, ou se o texto não cabe em 2 linhas."""
    import caixa_lettering as cl
    if colorway not in cl.COLORWAYS:
        raise InsumoInvalido("colorway %r não existe: use um dos três (%s), nunca um quarto"
                             % (colorway, ", ".join(cl.COLORWAYS)))
    if not str(texto or "").strip():
        raise InsumoInvalido("a caixa precisa do texto: o que o apresentador lê, palavra por palavra")
    if centro_y is None:
        centro_y = (int(topo) + round(cl.ALTURA_CAIXA * H) / 2.0) / float(H)
    try:
        return cl.montar_overlay(str(texto).strip(), canvas=(W, H), centro_y=centro_y, colorway=colorway)
    except SystemExit as e:                      # o caixa_lettering nasceu script: erro dele é SystemExit
        raise InsumoInvalido("não consegui desenhar a caixa: %s" % e)


def aviso_de_teto(base, teto_y):
    if base <= teto_y:
        return ""
    return ("ATENÇÃO: a caixinha desce até y=%d, abaixo do teto medido (%d). Pode encostar na cabeça no meio do "
            "anúncio." % (base, teto_y))


def compor(proj, nome, png, x=POS_PADRAO[0], y=POS_PADRAO[1], sombra=False, topo=None, teto_y=None):
    """Grava `com_caixinha/<peça>_caixinha.mp4`. Devolve (Path, aviso de teto ou "")."""
    nome = nome if nome.endswith(("normal", "desconto")) else nome + "_normal"
    mp4 = veredito.exigir_arquivo(proj.montado(nome), "a peça montada %s" % nome)
    if teto_y is None:
        pior, _ = area_ad_inteiro.varrer(mp4)
        teto_y = area_ad_inteiro.y_ate_onde_a_caixinha_pode_ir(pior)
    tela, topo_real, base = preparar(png, x, y, sombra, topo)
    destino = proj.garantir("com_caixinha") / ("%s_caixinha.mp4" % nome)
    with tempfile.TemporaryDirectory(prefix="vam-cx-") as pasta:
        overlay = Path(pasta) / "caixinha.png"
        tela.save(str(overlay))
        r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(mp4), "-i", str(overlay),
                            "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto[v]", "-map", "[v]", "-map", "0:a",
                            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                            "-c:a", "copy", str(destino)], capture_output=True, text=True)
    if r.returncode != 0:
        raise InsumoInvalido("o ffmpeg não conseguiu compor a caixinha: %s" % r.stderr.strip()[-300:])
    return destino, aviso_de_teto(base, teto_y)


def compor_texto(proj, nome, texto, colorway="ambar", topo=POS_PADRAO[1], teto_y=None):
    """Desenha a caixa nativa do `texto`, guarda o PNG em `caixinhas/<peça>.png` e a compõe sobre a peça
    montada. Devolve (Path do mp4 com caixinha, aviso de teto ou "")."""
    nome = nome if nome.endswith(("normal", "desconto")) else nome + "_normal"
    imagem = gerar_png(texto, colorway, topo)
    png = proj.garantir("caixinhas") / (nome + ".png")
    imagem.save(str(png))
    return compor(proj, nome, png, topo=topo, teto_y=teto_y)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Põe a caixinha de pergunta fixa sobre a peça montada.")
    ap.add_argument("peca")
    ap.add_argument("png")
    ap.add_argument("--x", type=int, default=POS_PADRAO[0])
    ap.add_argument("--y", type=int, default=POS_PADRAO[1])
    ap.add_argument("--sombra", action="store_true")
    ap.add_argument("--topo", type=int, default=None, help="reposiciona a caixinha para começar neste y (ex: 200)")
    ap.add_argument("--teto-y", type=int, default=None, help="até onde a caixinha pode descer (padrão: medido na peça)")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    a = ap.parse_args(argv)

    def fazer():
        veredito.exigir_arquivo(a.png, "a imagem da caixinha")
        destino, aviso = compor(gp.carregar(a.projeto), a.peca, a.png, a.x, a.y, a.sombra, a.topo, a.teto_y)
        print("%s pronto" % destino.name)
        if aviso:
            print("  " + aviso)
    return veredito.ferramenta(fazer)


if __name__ == "__main__":
    sys.exit(main())
