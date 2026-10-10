#!/usr/bin/env python3
"""GATE DO INSERT (W4.A, capacidade C8): densidade, congelamento, faixa morta e moldura.

    python3 scripts/gates/gate_insert.py --timeline render/timeline.json --plano plano/plano.json \
        [--projeto projeto.json] [video]
    exit 0 passa · 1 reprova · 2 insumo inválido (arquivo ausente ou ilegível)

Reprova quando (limiares do plano, seção 3, C8):
  - a densidade (fração do tempo com insert na tela) está fora da faixa de 45 a 55%, a não ser que o
    `projeto.json` declare a exceção `densidade` com motivo (`excecoes`). Fora do PISO (40%) ou do TETO (65%)
    reprova até com exceção: a exceção alarga a faixa alvo, não apaga os limites;
  - o congelamento previsto de um insert passa de 0,20 s (o último quadro clonado fica visível);
  - há faixa morta contínua acima de 40 px no composto, em 6 instantes dentro dos inserts;
  - um insert horizontal entra recortado, sem a moldura de navegador (o C8: horizontal entra INTEIRO em
    moldura).

## O que é reaproveitado, não refeito

  densidade       `plano.medir` já mede (ALVO_MIN, ALVO_MAX, PISO, TETO são de lá). Aqui vem dos segmentos da
                  timeline (o que o render realizou) e, sem timeline, do `plano.densidade`.
  congelamento    `plano.mapa_inserts[].congela_s`, a conta do `analise_inserts` (consome = bloco x velocidade;
                  congela = consome - o que a fonte tem), com o mesmo limite (`analise_inserts.LIMITE_S`).
  tratamento      `plano.mapa_inserts[].tratamento`: horizontal só em `moldura` ou `split`.

## O que é medido no composto

  faixa morta   PRETO LISO: linhas lisas E escuras. Linha lisa = desvio horizontal de até 2,5 níveis (de 255)
                depois de uma média de 8 px (o grão da grade final, `noise=alls=7`, tem desvio ~4 e não pode
                enganar); escura = média de até 12 níveis. Faixa morta = linhas assim seguidas cuja média não deriva
                mais de 4 níveis. É o defeito que a regra quer pegar: a régua preta na emenda do split, o fundo
                da tela cheia que zera (preto absoluto em 60% do quadro, medido numa leva) e o canvas escuro que
                aparece quando um painel sai mais baixo que o layout. Fundo claro desfocado NÃO é faixa morta: é o
                desfoque do próprio asset, aprovado no VAM (a primeira versão do gate, que só olhava "liso",
                acusou 66 px num fundo claro desfocado de uma gravação de tela real: o motor reprovaria a si mesmo).
                Só se mede FORA do card do insert e FORA do painel do avatar: um terminal preto dentro da
                moldura é conteúdo, e o avatar embaixo do split não é insert. A geometria sai das constantes do
                motor (`moldura`, `filtros_avatar`, `filtros_insert.moldura_cheia`), e o teste a confere contra
                quadros desenhados pelo próprio motor.
  moldura       os 3 pontos coloridos da barra do navegador (vermelho, amarelo, verde) no lugar exato que o
                motor os desenha. Sem eles, o insert horizontal entrou recortado. Pelo MATIZ, não pela cor
                exata: a grade final escurece e esquenta o quadro (a vinheta deixa o vermelho de (255, 95, 86)
                em (176, 70, 48) na borda esquerda do split), e a cor nominal já não bate.
  instantes     6, espalhados pelo tempo total de insert, longe 0,25 s das transições.

Os limiares de linha lisa (2,5 níveis), de escuridão (12), de deriva (4), a margem de 8 px em volta do card e o
tom dos pontos foram conferidos em quadros do motor com gravações de tela reais e com faixas pintadas (com grão),
mas NÃO em anúncio graded de ponta a ponta; a prova (W7) é quem diz se precisam mudar.

## Formato do resultado

`rodar` devolve um dict no formato de gate do laudo (`contratos/laudo.schema.json`), como os outros gates da
W4. Sem vídeo, mede só o que o plano e a timeline dizem; com vídeo, mede também o composto.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

if __name__ == "__main__":      # rodado direto: scripts/gates/gate_insert.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import analise_inserts  # noqa: E402
from plano.medir import ALVO_MAX, ALVO_MIN, PISO, TETO  # noqa: E402
from projeto import modelo  # noqa: E402

NOME = "gate_insert"
ETAPA = "depois"
REGRA_EXCECAO = "densidade"

CONGELA_MAX_S = analise_inserts.LIMITE_S     # 0,20 s
FAIXA_MORTA_MAX_PX = 40
INSTANTES = 6
APARA_S = 0.25                               # os instantes ficam longe da transição de entrada e de saída
MOLDURA_ASPECTO_MIN = 1.05                   # abaixo disso o asset não ganha moldura (filtros_insert.painel_mockup)
TRATAMENTOS_COM_MOLDURA = ("moldura", "split")
LINHA_LISA_STD = 2.5                         # desvio horizontal máximo (0 a 255) de uma linha lisa, já sem o grão
LINHA_ESCURA_MAX = 12.0                      # luminância média máxima de uma linha morta: preto liso, não fundo claro
LINHA_LISA_DERIVA = 4.0                      # quanto a média pode derivar numa faixa morta
SUAVIZA_PX = 8                               # média horizontal (meia resolução) que tira o grão antes do desvio
MARGEM_CARD_PX = 8                           # folga em volta do card (a sombra dele não é lisa)
PONTO_MATIZ_TOL = 20.0                       # graus de matiz de diferença tolerados para um pixel valer como o ponto
PONTO_SATURACAO_MIN = 0.5                    # saturação mínima (a barra do navegador é quase cinza)
PONTO_VALOR_MIN = 40                         # brilho mínimo (0 a 255): a vinheta e o scrim do lettering escurecem (a ~45% do brilho
                                             # o verde de 201 vai a 66, W7.Z), mas não apagam o ponto; matiz e saturação decidem
PONTO_PIXELS_MIN = 10                        # pixels (em meia resolução) para o ponto existir
ESCALA = 2                                   # o gate mede em meia resolução (540x960): 1 linha = 2 px
_EPS = 1e-9


class InsumoInvalido(Exception):
    """Arquivo ausente ou ilegível: não dá nem para reprovar (exit 2)."""


# --- densidade ------------------------------------------------------------------------------------------------

def densidade_da_timeline(tl):
    """Fração do tempo da footage com insert na tela, pelos segmentos que o render realizou."""
    dur = float(tl["duracao_s"])
    if dur <= 0:
        raise InsumoInvalido("a timeline tem duração %s" % dur)
    return sum(sg["e"] - sg["s"] for sg in tl["segmentos"] if sg["tipo"] == "insert") / dur


def _avaliar_densidade(fracao, projeto):
    """(motivo_ou_None, medido). O motivo é a razão da reprovação."""
    medido = {"fracao_insert": round(fracao, 4)}
    pct = 100.0 * fracao
    if fracao < PISO - _EPS:
        medido["estado"] = "abaixo do piso"
        return ("densidade de %.1f%% abaixo do piso de %.0f%%: faltam inserts (nem exceção declarada cobre isso)"
                % (pct, 100 * PISO)), medido
    if fracao > TETO + _EPS:
        medido["estado"] = "acima do teto"
        return ("densidade de %.1f%% acima do teto de %.0f%%: inserts demais, o apresentador some (nem exceção "
                "declarada cobre isso)" % (pct, 100 * TETO)), medido
    if ALVO_MIN - _EPS <= fracao <= ALVO_MAX + _EPS:
        medido["estado"] = "no alvo"
        return None, medido
    motivo = modelo.motivo_excecao(projeto, REGRA_EXCECAO) if projeto else None
    if motivo:
        medido["estado"] = "fora do alvo, com exceção"
        medido["excecao"] = motivo
        return None, medido
    medido["estado"] = "fora do alvo"
    return ("densidade de %.1f%% fora da faixa de %.0f a %.0f%% (piso %.0f%%, teto %.0f%%): ajuste os inserts ou "
            "declare a exceção %r com motivo em projeto.json (excecoes)"
            % (pct, 100 * ALVO_MIN, 100 * ALVO_MAX, 100 * PISO, 100 * TETO, REGRA_EXCECAO)), medido


# --- congelamento e tratamento (do plano) ------------------------------------------------------------------------

def _aspecto(item):
    return float(item["largura"]) / float(item["altura"])


def _avaliar_congelamento(mapa):
    acima = [{"chave": m["chave"], "congela_s": round(float(m["congela_s"]), 3)}
             for m in mapa if float(m["congela_s"]) > CONGELA_MAX_S + _EPS]
    maior = max(({"chave": m["chave"], "congela_s": round(float(m["congela_s"]), 3)} for m in mapa),
                key=lambda x: x["congela_s"], default=None)
    medido = {"limite_s": CONGELA_MAX_S, "maior": maior, "acima": acima}
    motivos = ["insert %r congela %.2f s (limite %.2f s): o último quadro fica clonado e visível; corte o trecho "
               "ou use uma fonte mais longa" % (a["chave"], a["congela_s"], CONGELA_MAX_S) for a in acima]
    return motivos, medido


def _avaliar_tratamento(mapa):
    ruins = []
    for m in mapa:
        if _aspecto(m) >= MOLDURA_ASPECTO_MIN and m.get("tratamento") not in TRATAMENTOS_COM_MOLDURA:
            ruins.append({"chave": m["chave"], "tratamento": m.get("tratamento"),
                          "dimensoes": "%dx%d" % (m["largura"], m["altura"])})
    motivos = ["insert horizontal %r (%s) entra recortado, sem moldura (tratamento %r): o C8 manda o horizontal "
               "INTEIRO dentro da moldura de navegador" % (r["chave"], r["dimensoes"], r["tratamento"])
               for r in ruins]
    return motivos, ruins


# --- geometria do card e medidas no composto ----------------------------------------------------------------------

def geometria_do_card(layout, aspecto):
    """Onde o motor desenha o card de um insert horizontal, em px do quadro 1080x1920: `topo`, `base`,
    `esq`, `dir`, os 3 `pontos` da barra e as linhas de fundo (`regioes`) que sobram acima e abaixo dele.
    `layout` é "split" (painel de cima do split) ou "cheio"; outro layout não tem card: None."""
    import moldura
    from footage import filtros_avatar as FA
    if layout == "split":
        jw, painel_h, fundo_fim = moldura.LARGURA_JANELA, FA.SPLIT_TOP_H, FA.SPLIT_TOP_H - FA.SPLIT_GRAD
        jh = int(round(jw / float(aspecto))) // 2 * 2
    elif layout == "cheio":
        # a janela cheia ocupa a tela (W7.Z): a mesma conta do filtro, `moldura.janela_cheia`
        (jw, jh), painel_h, fundo_fim = moldura.janela_cheia(aspecto), FA.H, FA.H
    else:
        return None
    pad, barra = moldura.PAD_SOMBRA, moldura.BARRA_H
    cw, ch = jw + 2 * pad, jh + barra + 2 * pad
    cx, cy = int((FA.W - cw) / 2.0), int((painel_h - ch) / 2.0)
    topo, base = cy + pad, cy + pad + jh + barra
    pontos = [(cx + pad + dx, cy + pad + barra // 2, cor) for cor, dx in moldura.PONTOS]
    regioes = [(0, max(0, topo - MARGEM_CARD_PX)), (min(fundo_fim, base + MARGEM_CARD_PX), fundo_fim)]
    return {"layout": layout, "topo": topo, "base": base, "esq": cx + pad, "dir": cx + pad + jw,
            "pontos": pontos, "regioes": [(a, b) for a, b in regioes if b > a]}


def _matiz_e_saturacao(rgb):
    """Matiz (graus), saturação (0 a 1) e valor (0 a 255) de cada pixel de um array (..., 3)."""
    import numpy as np
    rgb = rgb.astype(np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(axis=-1), rgb.min(axis=-1)
    d = mx - mn
    seguro = np.where(d > 0, d, 1.0)
    matiz = np.zeros_like(mx)
    matiz = np.where(mx == r, 60.0 * (((g - b) / seguro) % 6.0), matiz)
    matiz = np.where((mx == g) & (mx != r), 60.0 * ((b - r) / seguro + 2.0), matiz)
    matiz = np.where((mx == b) & (mx != r) & (mx != g), 60.0 * ((r - g) / seguro + 4.0), matiz)
    matiz = np.where(d > 0, matiz, 0.0)
    sat = np.where(mx > 0, d / np.where(mx > 0, mx, 1.0), 0.0)
    return matiz, sat, mx


def _cor_do_ponto(cor, janela):
    """Quantos pixels da `janela` têm o matiz do ponto de cor nominal `cor` (saturados e não escuros)."""
    import numpy as np
    h0, _s0, _v0 = _matiz_e_saturacao(np.array(cor, dtype=np.float32))
    h, sat, val = _matiz_e_saturacao(janela)
    dif = np.abs((h - float(h0) + 180.0) % 360.0 - 180.0)
    return int(((dif <= PONTO_MATIZ_TOL) & (sat >= PONTO_SATURACAO_MIN) & (val >= PONTO_VALOR_MIN)).sum())


def moldura_presente(quadro, geo):
    """Os 3 pontos da barra do navegador estão onde o motor os desenha? `quadro` é RGB em meia resolução."""
    alt, larg = quadro.shape[0], quadro.shape[1]
    for x, y, cor in geo["pontos"]:
        cx, cy = int(round(x / float(ESCALA))), int(round(y / float(ESCALA)))
        x0, x1, y0, y1 = max(0, cx - 4), min(larg, cx + 5), max(0, cy - 4), min(alt, cy + 5)
        if x1 <= x0 or y1 <= y0:
            return False
        if _cor_do_ponto(cor, quadro[y0:y1, x0:x1, :]) < PONTO_PIXELS_MIN:
            return False
    return True


def faixa_morta_px(quadro, geo):
    """A maior faixa morta (px do quadro 1080x1920) nas regiões de fundo do insert: linhas lisas E escuras,
    seguidas. 0 se não há."""
    import numpy as np
    lum = quadro.astype(np.float32) @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    soma = np.cumsum(lum, axis=1)
    suave = (soma[:, SUAVIZA_PX:] - soma[:, :-SUAVIZA_PX]) / float(SUAVIZA_PX)    # média móvel por linha
    desvio, media = suave.std(axis=1), lum.mean(axis=1)
    melhor = 0
    for y0, y1 in geo["regioes"]:
        a, b = int(np.ceil(y0 / float(ESCALA))), min(lum.shape[0], int(y1 // ESCALA))
        ini, lo, hi = None, 0.0, 0.0
        for r in range(a, b):
            if desvio[r] > LINHA_LISA_STD or media[r] > LINHA_ESCURA_MAX:
                if ini is not None:
                    melhor = max(melhor, (r - ini) * ESCALA)
                ini = None
                continue
            m = float(media[r])
            if ini is None:
                ini, lo, hi = r, m, m
            elif max(hi, m) - min(lo, m) <= LINHA_LISA_DERIVA:
                lo, hi = min(lo, m), max(hi, m)
            else:                                     # a média derivou: era degradê; a faixa recomeça aqui
                melhor = max(melhor, (r - ini) * ESCALA)
                ini, lo, hi = r, m, m
        if ini is not None:
            melhor = max(melhor, (b - ini) * ESCALA)
    return int(melhor)


def instantes_de_amostra(tl, n=INSTANTES):
    """`n` instantes ENTREGUES espalhados pelo tempo total de insert, longe das transições:
    `[{"t", "segmento", "layout"}]` em ordem de tempo. Sem insert, lista vazia."""
    rel = tl["relogio"]
    acel, a0 = float(rel["aceleracao"]), float(rel.get("a0", 0.0))
    ins = [(k, sg, (sg["s"] - a0) / acel, (sg["e"] - a0) / acel) for k, sg in enumerate(tl["segmentos"])
           if sg["tipo"] == "insert" and sg["e"] - sg["s"] > _EPS]
    total = sum(e - s for _k, _sg, s, e in ins)
    if not ins or total <= _EPS:
        return []
    saida = []
    for i in range(n):
        alvo = (i + 0.5) * total / n
        acum = 0.0
        for k, sg, s, e in ins:
            if alvo < acum + (e - s) or (k, sg, s, e) == ins[-1]:
                apara = min(APARA_S, (e - s) / 2.0)
                t = min(max(s + (alvo - acum), s + apara), e - apara)
                saida.append({"t": round(t, 3), "segmento": k, "layout": sg.get("layout")})
                break
            acum += e - s
    return sorted(saida, key=lambda x: x["t"])


def _leitor_padrao():
    """Um quadro RGB em meia resolução (540x960) em cada instante entregue."""
    import numpy as np

    def leitor(video, instantes):
        quadros = []
        for t in instantes:
            r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-ss", "%.3f" % t, "-i", str(video), "-an",
                                "-frames:v", "1", "-vf", "scale=540:960", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                "pipe:1"], capture_output=True, timeout=120)
            if r.returncode != 0 or len(r.stdout) != 540 * 960 * 3:
                raise OSError("ffmpeg não leu o quadro de %.2f s de %s: %s"
                              % (t, video, r.stderr.decode("utf-8", "replace").strip()[-200:] or "sem quadro"))
            quadros.append(np.frombuffer(r.stdout, dtype=np.uint8).reshape(960, 540, 3))
        return quadros
    return leitor


def layout_efetivo(layout_do_segmento, tratamento, layout_do_bloco=None):
    """O layout que o MOTOR renderizou de verdade num segmento de insert. O ritmo marca `split` ou `cheio` em toda fatia,
    mas só o insert em `split` obedece (`render_segmentos.r_insert`): o que está em `moldura` (cheio) é tela cheia em toda
    visita, e o `split` do ritmo nele não vale; a visita única de um insert em split não traz layout e é split."""
    if tratamento == "split":
        # W7.W: o tratamento é da CHAVE (o 1º uso decide). O MESMO insert escrito `| cheio` em outro bloco não tem
        # `split: true` no inserts.json e o motor o desenha em tela cheia, qualquer que seja a fatia do ritmo.
        if layout_do_bloco == "cheio":
            return "cheio"
        return layout_do_segmento if layout_do_segmento in ("split", "cheio") else "split"
    if tratamento == "moldura":
        return "cheio"
    return None


def _insert_por_bloco(plano, tl):
    """{índice do bloco: chave do insert}. A chave vem do PLANO: a timeline real guarda no bloco o número do insert no
    inserts.json ("1", "2"...), que nunca casa com `mapa_inserts[].chave` (W7.Z: o gate media 0 quadros na prova e
    passava)."""
    por_bloco = {b["i"]: b.get("insert") for b in plano.get("blocos") or [] if b.get("tipo") == "insert"}
    if not por_bloco:
        por_bloco = {b["i"]: b.get("insert") for b in tl.get("blocos") or []}
    return por_bloco


def _avaliar_composto(video, tl, plano, leitor):
    """(motivos, medido) da faixa morta e da moldura nos 6 instantes."""
    mapa = {m["chave"]: m for m in plano["mapa_inserts"]}
    insert_do_bloco = _insert_por_bloco(plano, tl)
    layout_do_bloco = {b["i"]: b.get("layout") for b in plano.get("blocos") or [] if b.get("tipo") == "insert"}
    instantes = instantes_de_amostra(tl)
    medido = {"instantes": [], "maior_px": 0, "limite_px": FAIXA_MORTA_MAX_PX}
    if not instantes:
        medido["estado"] = "sem insert para medir"
        return [], medido
    quadros = leitor(video, [i["t"] for i in instantes])
    if len(quadros) != len(instantes):
        raise OSError("o leitor devolveu %d quadros para %d instantes" % (len(quadros), len(instantes)))
    por_bloco = {}
    motivos = []
    for inst, q in zip(instantes, quadros):
        sg = tl["segmentos"][inst["segmento"]]
        item = mapa.get(insert_do_bloco.get(sg["bloco"]))
        layout = (layout_efetivo(inst["layout"], item.get("tratamento"), layout_do_bloco.get(sg["bloco"]))
                  if item else inst["layout"])
        geo = None
        if item and _aspecto(item) >= MOLDURA_ASPECTO_MIN and layout in ("split", "cheio"):
            geo = geometria_do_card(layout, _aspecto(item))
        linha = {"t": inst["t"], "segmento": inst["segmento"], "layout": layout,
                 "faixa_morta_px": None, "moldura": None}
        if geo is not None:
            linha["faixa_morta_px"] = faixa_morta_px(q, geo)
            linha["moldura"] = moldura_presente(q, geo)
            por_bloco.setdefault(sg["bloco"], []).append(linha["moldura"])
            if linha["faixa_morta_px"] > FAIXA_MORTA_MAX_PX:
                motivos.append("faixa morta contínua de %d px no composto em %.2f s (limite %d px): fundo liso demais "
                               "em volta do insert" % (linha["faixa_morta_px"], inst["t"], FAIXA_MORTA_MAX_PX))
        medido["instantes"].append(linha)
    medido["maior_px"] = max([i["faixa_morta_px"] for i in medido["instantes"] if i["faixa_morta_px"] is not None] or [0])
    for bloco, achados in sorted(por_bloco.items()):
        if achados.count(False) * 2 > len(achados):
            chave = insert_do_bloco.get(bloco)
            motivos.append("insert horizontal %r recortado: sem a moldura de navegador em %d de %d instantes medidos"
                           % (chave, achados.count(False), len(achados)))
    return motivos, medido


# --- decisão e CLI ----------------------------------------------------------------------------------------------------

def _limiar():
    return {"densidade": {"alvo_min": ALVO_MIN, "alvo_max": ALVO_MAX, "piso": PISO, "teto": TETO},
            "congelamento_max_s": CONGELA_MAX_S, "faixa_morta_max_px": FAIXA_MORTA_MAX_PX, "instantes": INSTANTES}


def _gate(resultado, saida, etapa, nome, medido=None, motivo=None, duracao=None):
    g = {"nome": nome, "etapa": etapa, "resultado": resultado, "saida": saida}
    if medido is not None:
        g["medido"] = medido
    g["limiar"] = _limiar()
    if motivo:
        g["motivo"] = motivo
    if duracao is not None:
        g["duracao_s"] = round(duracao, 2)
    return g


def _validar_insumos(plano, timeline, video, leitor):
    if plano is None and timeline is None:
        raise InsumoInvalido("passe o plano (plano/plano.json) e/ou a timeline (render/timeline.json)")
    if plano is not None:
        if not isinstance(plano, dict) or "mapa_inserts" not in plano:
            raise InsumoInvalido("o plano não tem o campo 'mapa_inserts' (use o plano/plano.json medido)")
    if timeline is not None:
        if not isinstance(timeline, dict):
            raise InsumoInvalido("a timeline não é um objeto JSON")
        for campo in ("relogio", "segmentos", "duracao_s"):
            if campo not in timeline:
                raise InsumoInvalido("a timeline não tem o campo %r (use o render/timeline.json do projeto)" % campo)
    if timeline is None and plano is not None and "densidade" not in plano:
        raise InsumoInvalido("sem timeline, o plano precisa do campo 'densidade'")
    if video is not None:
        if plano is None or timeline is None:
            raise InsumoInvalido("para medir o composto o gate precisa do plano (o aspecto de cada insert) e da "
                                 "timeline (onde cada insert está)")
        if leitor is None and not Path(str(video)).is_file():
            raise InsumoInvalido("o vídeo não existe: %s" % video)


def rodar(plano=None, timeline=None, projeto=None, video=None, *, leitor=None, etapa=ETAPA, nome=NOME):
    """Confere os inserts. `plano` e `timeline` são dicts (plano.json e timeline.json); `projeto` é o dict do
    projeto.json (modo e `excecoes`); `video` é o entregue, para medir o composto. Devolve o gate no formato do
    laudo; insumo ruim vira ERRO (saída 2), nunca traceback. `nome` deixa a W5.A registrar a mesma checagem em
    duas etapas do laudo sem repetir o nome."""
    t0 = time.time()
    try:
        _validar_insumos(plano, timeline, video, leitor)
        medido, motivos = {}, []

        modo = (projeto or {}).get("modo", "avatar")
        if modo != "avatar":
            medido["densidade"] = {"estado": "PULADO",
                                   "motivo": "modo %s: a densidade de 45 a 55%% é do anúncio de avatar" % modo}
        else:
            if timeline is not None:
                fracao, fonte = densidade_da_timeline(timeline), "timeline"
            else:
                fracao, fonte = float(plano["densidade"]["fracao_insert"]), "plano"
            motivo, med = _avaliar_densidade(fracao, projeto)
            med["fonte"] = fonte
            medido["densidade"] = med
            if motivo:
                motivos.append(motivo)

        if plano is not None:
            m_congela, medido["congelamento"] = _avaliar_congelamento(plano["mapa_inserts"])
            m_trat, medido["horizontais_sem_moldura"] = _avaliar_tratamento(plano["mapa_inserts"])
            motivos += m_congela + m_trat

        if video is not None:
            m_comp, medido["faixa_morta"] = _avaliar_composto(video, timeline, plano, leitor or _leitor_padrao())
            motivos += m_comp
    except InsumoInvalido as e:
        return _gate("ERRO", 2, etapa, nome, motivo=str(e))
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, ZeroDivisionError) as e:
        return _gate("ERRO", 2, etapa, nome, motivo="falha ao medir os inserts: %s" % e)
    dur = time.time() - t0
    if motivos:
        return _gate("REPROVA", 1, etapa, nome, medido, "; ".join(motivos), dur)
    return _gate("PASS", 0, etapa, nome, medido, duracao=dur)


def _ler_json(caminho, o_que):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise InsumoInvalido("não consegui ler %s (%s): %s" % (o_que, caminho, e))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Confere densidade, congelamento, faixa morta e moldura dos inserts.")
    ap.add_argument("video", nargs="?", help="o vídeo entregue (sem ele, só mede o plano e a timeline)")
    ap.add_argument("--timeline", help="render/timeline.json do projeto")
    ap.add_argument("--plano", help="plano/plano.json do projeto")
    ap.add_argument("--projeto", help="projeto.json (lê o modo e as exceções declaradas)")
    args = ap.parse_args(argv)
    try:
        tl = _ler_json(args.timeline, "a timeline") if args.timeline else None
        pl = _ler_json(args.plano, "o plano") if args.plano else None
        pj = _ler_json(args.projeto, "o projeto.json") if args.projeto else None
    except InsumoInvalido as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        return 2
    g = rodar(plano=pl, timeline=tl, projeto=pj, video=args.video)
    if g["resultado"] == "PASS":
        d = g["medido"]["densidade"]
        print("PASSA: densidade %s, congelamento até %.2f s, %d instante(s) de composto sem faixa morta"
              % ("%.1f%%" % (100 * d["fracao_insert"]) if "fracao_insert" in d else d["estado"],
                 (g["medido"].get("congelamento", {}).get("maior") or {}).get("congela_s", 0.0),
                 len(g["medido"].get("faixa_morta", {}).get("instantes", []))))
    elif g["resultado"] == "REPROVA":
        print("REPROVA: %s" % g["motivo"])
    else:
        print("ERRO de insumo: %s" % g["motivo"], file=sys.stderr)
    return g["saida"]


if __name__ == "__main__":
    sys.exit(main())
