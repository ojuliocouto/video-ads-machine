#!/usr/bin/env python3
"""MEDE o enquadramento a partir do arquivo, em vez de alguem digitar o numero.

Ordem do Julio (17/08/2026): "a medicao precisa ser parte OBRIGATORIA do processo".
Nasceu de tres defeitos no mesmo dia, todos por valor chutado em vez de medido:
  1. corte do painel de baixo no split: peguei a parede acima da cabeca dele
  2. ancora de lettering: pousou no bloco errado porque nao contei as ocorrencias
  3. recorte do painel de cima: deixei faixa escura porque nao olhei a proporcao

O que ele mede:
  - `avatar <mp4>`: onde esta a pessoa no quadro (topo da cabeca, base do peito),
    por perfil de luminancia, e devolve o BIAS do recorte pro painel do split.
  - `asset <mp4> --painel <larg>x<alt>`: se o asset preenche o painel ou deixa tarja,
    e qual recorte usar.

Uso:
  python3 medir_enquadramento.py avatar inputs/jh13v2_espuma_roxa_avatar.mp4
  python3 medir_enquadramento.py asset inputs/assets_jheni/x.mp4 --painel 1080x980
  python3 medir_enquadramento.py avatar <mp4> --json
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

AMOSTRAS = 5          # quadros ao longo do video: pessoa se mexe, um frame so engana
# SILHUETA POR CONTRASTE COM O FUNDO (19/08/2026), no lugar de luminancia absoluta.
# O detector antigo marcava "linha com pessoa" quando a luminancia da faixa central
# passava de 45% do pico do quadro. Cabelo escuro contra fundo escuro NUNCA passa: no
# jh13v2_espuma_roxa, na altura do cabelo (624px), a faixa central mede 29 de luminancia
# contra 51 da lateral, ou seja, a pessoa e MAIS ESCURA que o fundo ali. O detector
# pulava a cabeca inteira e devolvia o topo em 720px, que e a testa. Erro de 192px, e e
# a causa mae da bolinha decepando o Thales e do split comecando no meio do cabelo.
# Agora: linha com pessoa = faixa central DIFERE da lateral (para mais ou para menos).
LIMIAR_DIF = 12       # diferenca minima de luminancia entre faixa central e lateral
CORRIDA_MIN = 0.012   # fracao da altura que a diferenca precisa durar, mata ruido pontual
LIMIAR_REL = 0.45     # mantido so para compatibilidade de chamadas antigas
PERDA_MAX = 0.22      # acima disso, preencher descarta conteudo demais: melhor encaixar


def _frames(video, n=AMOSTRAS):
    d = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(video)], capture_output=True, text=True).stdout.strip() or 0)
    tmp = tempfile.mkdtemp()
    saidas = []
    for i in range(n):
        t = d * (i + 1) / (n + 1)
        p = os.path.join(tmp, f"m{i}.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(video),
                        "-frames:v", "1", "-vf", "scale=270:-1", p], check=False)
        if os.path.exists(p):
            saidas.append(p)
    return saidas, d


def medir_avatar(video):
    """Devolve (topo, base) da pessoa em fracao da altura, e o bias sugerido."""
    from PIL import Image
    quadros, d = _frames(video)
    if not quadros:
        sys.exit("MEDICAO: nao consegui extrair quadro do avatar")
    topos, bases = [], []
    for p in quadros:
        im = Image.open(p).convert("L")
        w, h = im.size
        px = im.load()
        # faixa central (onde a pessoa esta) contra faixa lateral (cenario puro),
        # linha a linha. A pessoa e o que DIFERE do fundo, seja mais clara (pele) ou
        # mais escura (cabelo, camiseta preta).
        centro, lateral = [], []
        for y in range(h):
            c = [px[x, y] for x in range(int(w * 0.30), int(w * 0.70), 3)]
            lt = ([px[x, y] for x in range(0, int(w * 0.12), 2)] +
                  [px[x, y] for x in range(int(w * 0.88), w, 2)])
            centro.append(sum(c) / len(c))
            lateral.append(sum(lt) / len(lt) if lt else 0.0)
        dif = [abs(centro[y] - lateral[y]) for y in range(h)]
        limiar = max(LIMIAR_DIF, 0.15 * max(dif)) if max(dif) else LIMIAR_DIF
        # CORRIDA: exige N linhas seguidas acima do limiar antes de declarar a pessoa.
        # Sem isso um degrade de luz ou uma sombra isolada vira "topo da cabeca".
        n_corrida = max(3, int(h * CORRIDA_MIN))
        acima = [d >= limiar for d in dif]
        topo_y = base_y = None
        corr = 0
        for y in range(h):
            corr = corr + 1 if acima[y] else 0
            if corr >= n_corrida:
                topo_y = y - n_corrida + 1
                break
        corr = 0
        for y in range(h - 1, -1, -1):
            corr = corr + 1 if acima[y] else 0
            if corr >= n_corrida:
                base_y = y + n_corrida - 1
                break
        if topo_y is not None and base_y is not None and base_y > topo_y:
            topos.append(topo_y / h)
            bases.append(base_y / h)
    if not topos:
        sys.exit("MEDICAO: nao achei a pessoa no quadro")
    # MINIMO, nao media (19/08/2026): a pessoa se mexe entre as amostras, e o
    # enquadramento tem que caber no quadro em que ela esta MAIS ALTA. A media deixava
    # a cabeca sair do painel nos quadros em que ele levanta o queixo.
    topo, base = min(topos), max(bases)
    return topo, base


_VIDEO_ATUAL = []       # preenchido pelo main; o bias precisa do arquivo pra achar o rosto


def _centro_do_rosto(video):
    """Centro vertical do rosto no avatar, em pixel da fonte. None se nao achar."""
    try:
        import medir_rosto
        c = medir_rosto.caixa_rosto(video)
        return (c[0] + c[1] // 2) if c else None
    except Exception:
        return None


def bias_para_painel(topo, base, src_y, src_h, alt_fonte, alt_painel):
    """Converte a medida em BIAS de recorte do painel de baixo do split.

    Objetivo: cabeca inteira com uma folga em cima, peito embaixo. A janela do painel
    e menor que a regiao da pessoa, entao ancorar no TOPO da cabeca (com folga) e o
    que evita tanto cortar o cabelo quanto mostrar parede vazia.
    """
    topo_px = topo * alt_fonte           # topo da pessoa no arquivo original
    base_px = base * alt_fonte           # base da pessoa (ombro/peito)
    altura_pessoa = base_px - topo_px

    if altura_pessoa <= alt_painel:
        # cabe inteiro: ancora no topo com respiro, que era a regra original
        folga = alt_painel * 0.10
        inicio = max(0.0, topo_px - folga - src_y)
    else:
        # NAO CABE, e este e o caso real do split 60/40 (pessoa ~1020px num painel de
        # 770px). Ancorar no topo da cabeca era aritmeticamente impossivel: sobrava
        # cabelo e testa, e o corte caia no NARIZ, com a BOCA FORA DO QUADRO. Avatar de
        # lipsync sem boca (achado do diretor de arte, 20/08/2026).
        #
        # Enquadramento de retrato: quando a cabeca nao cabe, corta-se a COROA, nunca o
        # queixo. O fator 0.40 e CALIBRADO, nao chutado: o diretor renderizou o painel de
        # verdade com 0.049 / 0.18 / 0.225 / 0.30 e mediu os pontos do rosto; com o bias
        # que este fator produz pro neon_creme (0.30) os olhos sobem 400px e ficam 226px
        # ACIMA da safe zone, o nariz entra e a boca e o queixo aparecem.
        # Nao ancoro em `base` porque ela e a borda inferior da PESSOA, que encosta no fim
        # do quadro (1916 de 1920): ancorar nela jogaria a cabeca pra fora do painel.
        # ANCORA NO ROSTO, por deteccao. Calibrar por fracao (do painel ou da pessoa)
        # nao funciona porque cada look tem enquadramento proprio: o `oficial_13` e um
        # close mais fechado e a mesma fracao que acerta o `neon_creme` corta as
        # SOBRANCELHAS dele. O rosto e o que precisa aparecer, entao e nele que se ancora.
        #
        # 35% da altura do painel para o CENTRO do rosto: e onde ele cai no caso que o
        # diretor validou renderizando (neon_creme, rosto 521-1178, centro 849, bias
        # 0.300). Deixa testa em cima e queixo mais ombro embaixo.
        centro = _centro_do_rosto(_VIDEO_ATUAL[0]) if _VIDEO_ATUAL else None
        if centro:
            inicio = max(0.0, centro - alt_painel * 0.35 - src_y)
        else:
            # sem rosto detectado, cai na fracao da pessoa (pior, mas nunca pior que o
            # topo da cabeca, que punha a boca fora do quadro)
            inicio = max(0.0, (topo_px - src_y) + altura_pessoa * 0.187)
    return max(0.0, min(inicio / max(src_h, 1), 1.0))


def medir_centro_conteudo(video):
    """Onde está o CONTEÚDO do asset, em fração da largura e da altura.

    Gravação de tela e página não têm o assunto no centro geométrico: o repo do GitHub
    tem a lista de skills à ESQUERDA, o Claude Code tem a conversa à esquerda e a barra
    de arquivos à direita. Recortar pelo centro (o que o motor fazia) cortava justamente
    o que a fala estava descrevendo, e o Júlio mandou print de dois casos assim.

    Mede densidade de BORDA (variação local), que é alta onde há texto e interface e
    baixa em fundo liso, e devolve o centroide dessa densidade.
    """
    from PIL import Image, ImageFilter
    quadros, _ = _frames(video)
    if not quadros:
        return 0.5, 0.5
    cx, cy = [], []
    for p in quadros:
        im = Image.open(p).convert("L").filter(ImageFilter.FIND_EDGES)
        w, h = im.size
        px = im.load()
        col = [sum(px[x, y] for y in range(0, h, 2)) for x in range(w)]
        lin = [sum(px[x, y] for x in range(0, w, 2)) for y in range(h)]
        tot_c, tot_l = sum(col), sum(lin)
        if tot_c <= 0 or tot_l <= 0:
            continue
        cx.append(sum(x * v for x, v in enumerate(col)) / tot_c / w)
        cy.append(sum(y * v for y, v in enumerate(lin)) / tot_l / h)
    if not cx:
        return 0.5, 0.5
    return sum(cx) / len(cx), sum(cy) / len(cy)


def medir_asset(video, painel):
    o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height", "-of", "csv=p=0",
                        str(video)], capture_output=True, text=True).stdout.strip()
    w, h = [int(x) for x in o.split(",")[:2]]
    pw, ph = [int(x) for x in painel.lower().split("x")]
    ar_asset, ar_painel = w / h, pw / ph
    if abs(ar_asset - ar_painel) < 0.02:
        veredito = "encaixa"
    elif ar_asset > ar_painel:
        veredito = "mais LARGO que o painel: encaixar inteiro deixa tarja em cima e embaixo"
    else:
        veredito = "mais ALTO que o painel: encaixar inteiro deixa tarja nas laterais"
    fx, fy = medir_centro_conteudo(video)
    # PERDA POR PREENCHER: preencher (increase+crop) tapa a tarja, mas DESCARTA parte do
    # asset. Numa gravacao de tela isso corta justamente o que a fala descreve (o Julio
    # mandou dois prints: "nem da pra ver qual e a skill"). Entao a escolha entre encaixar
    # e preencher deixa de ser fixa e passa a sair da MEDIDA da perda.
    escala = max(pw / w, ph / h)
    nw, nh = w * escala, h * escala
    perda = max((nw - pw) / nw if nw > pw else 0.0, (nh - ph) / nh if nh > ph else 0.0)
    modo = "encaixar" if perda > PERDA_MAX else "preencher"
    return {"asset": f"{w}x{h}", "painel": f"{pw}x{ph}",
            "aspecto_asset": round(ar_asset, 3), "aspecto_painel": round(ar_painel, 3),
            "veredito": veredito,
            "centro_conteudo_x": round(fx, 3), "centro_conteudo_y": round(fy, 3),
            "perda_ao_preencher": round(perda, 3), "modo": modo,
            "recomendacao": ("encaixar inteiro sobre fundo desfocado: preencher "
                             f"descartaria {perda:.0%} do asset") if modo == "encaixar"
            else "preencher (increase+crop) no centro de conteudo medido"}


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    modo, alvo = sys.argv[1], sys.argv[2]
    como_json = "--json" in sys.argv

    if modo == "avatar":
        _VIDEO_ATUAL[:] = [alvo]
        topo, base = medir_avatar(alvo)
        # valores do split no produzir_roteiro
        SRC = (0, 100, 1080, 1600)
        # 770, nao 940: o split virou 60/40 (SPLIT_TOP_H=1150) e esta constante ficou pra
        # tras. Com 940 a medicao devolvia bias 0.049, que cortava o Thales no NARIZ,
        # com a boca fora do quadro. Avatar de lipsync sem boca (achado do diretor,
        # 20/08/2026). Ver produzir_roteiro.py:243-244.
        ALT_FONTE, ALT_PAINEL = 1920, 770
        bias = bias_para_painel(topo, base, SRC[1], SRC[3], ALT_FONTE, ALT_PAINEL)
        info = {"arquivo": os.path.basename(alvo),
                "pessoa_topo": round(topo, 3), "pessoa_base": round(base, 3),
                "topo_px": int(topo * ALT_FONTE), "base_px": int(base * ALT_FONTE),
                "VAM_SPLIT_BIAS": round(bias, 3)}
        if como_json:
            print(json.dumps(info, ensure_ascii=False, indent=2))
        else:
            print(f"\n=== ENQUADRAMENTO MEDIDO: {info['arquivo']} ===")
            print(f"  pessoa ocupa y {info['topo_px']} a {info['base_px']} de 1920")
            print(f"  bias do painel de baixo: {info['VAM_SPLIT_BIAS']}")
            print(f"\n  usar: VAM_SPLIT_BIAS={info['VAM_SPLIT_BIAS']}")
    elif modo == "asset":
        painel = sys.argv[sys.argv.index("--painel") + 1] if "--painel" in sys.argv else "1080x980"
        info = medir_asset(alvo, painel)
        print(json.dumps(info, ensure_ascii=False, indent=2) if como_json else
              f"\n=== ASSET x PAINEL ===\n" + "\n".join(f"  {k}: {v}" for k, v in info.items()))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
