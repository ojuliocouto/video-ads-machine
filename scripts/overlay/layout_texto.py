"""Onde o texto de tela pousa em cada layout (avatar cheio, tela dividida, insert).

É a FONTE ÚNICA da faixa da legenda. Padrão do dono (10/10/2026, "Sim pros 2"; antes, 23/09: "mais delicada e mais
abaixo, tá muito em cima"): a legenda mora sempre na BASE do quadro, o centro da linha perto de y 1660 (1650 medido: o
halo forte desce 17 px abaixo da letra e a tinta inteira tem que ficar dentro da zona segura, y até 1690, acima dos
controles do app), nunca sobre o peito nem as mãos do apresentador. Uma posição só para os três layouts: em avatar cheio e em insert cheio ela está na base; em tela
dividida está na base do painel de baixo, que é a base do quadro.

    base       toda a fala: a caixa termina em y 1682 e a linha, de um corpo de 56 px, tem o centro em y ~1650;
               grupo que quebra em duas linhas sobe e ocupa y 1554 a 1682, nunca desce
    acima_cta  durante o CTA: a legenda sobe para logo ACIMA do bloco lead + pílula + logo (a pílula começa em
               y ~1219 e o lead em ~1150), sem tocar nenhum dos dois; assim as palavras finais da fala,
               ditas com o botão na tela, continuam legendadas

A posição não depende mais do que está embaixo da legenda, então acabaram as regras de fronteira que quebravam
um grupo em dois quando ele atravessava uma troca de layout (costura do split, rodapé sobre card, look fechado):
com uma posição só, partir o grupo só criava dois flashes. Sobraram aqui as janelas de split, que o lettering e o
CTA ainda consultam, e o relógio da footage.

O RELÓGIO é o da footage (28/08/2026). Os dois motores derivam os spans por caminhos diferentes e
não batem (o overlay fechava o split do bloco 2 em 14,37 e a footage só saía dele em 14,45, com
a deriva crescendo até 1,07 s no fim de um anúncio de 2 min). Toda decisão de POSIÇÃO de texto é
sobre o que está NA TELA, e quem põe na tela é a footage: quando o json dela existe, as janelas de
split vêm de lá.
"""
import json

from caminhos import V1

# faixa (y0, y1) de cada classe de legenda no quadro 1080x1920. Bate com o CSS (`#caps .cgrp` bottom 238 e
# `.cgrp-acima-cta` bottom 820, corpo de 56 px, linha de 64 px, até duas linhas) e com a faixa que o gate de
# contraste mede no arquivo entregue.
FAIXA_LEGENDA = {"base": (1554, 1682), "acima_cta": (972, 1100)}
Y_CENTRO_BASE = 1650          # o centro da linha única da base (1682 menos meia linha de 64 px)

SOBREPOSICAO_RELOGIO = 0.05   # janela da footage só vale se encostar mais que isso numa do overlay


def classe_do_grupo(g):
    """A classe de legenda do grupo: `acima_cta` durante o CTA, `base` no resto do anúncio."""
    return "acima_cta" if g.get("acima_cta") else "base"


def janelas_por_visita(visitas):
    """(janelas_split, janelas_texto, mapa_insert) a partir das visitas de insert.

    - split: só as fatias que continuam em tela dividida (o resto do bloco voltou para o avatar e
      tem que ser tratado como avatar);
    - texto: insert de tela cheia, fatia `cheio` de um insert split, e insert com texto próprio. A
      posição padrão da legenda é calibrada para o AVATAR, onde cai no peito; sobre um insert cai no
      MEIO do conteúdo. Insert existe para ser visto, então a legenda desce para o rodapé;
    - mapa_insert: janela -> fonte, start e velocidade, para medir o fundo NO INSTANTE de cada grupo
      (um insert de gravação de tela que abre numa página branca rola para uma área escura no meio).
    """
    janelas_split, janelas_texto, mapa_insert = [], [], []
    for v in visitas:
        icfg = v.icfg
        if icfg.get("split"):
            for _a, _b2 in v.meus:
                _par = (round(_a, 2), round(min(_b2, v.e), 2))
                # fatia sem o apresentador embaixo se comporta como insert de tela cheia
                (janelas_texto if (round(_a, 2), round(_b2, 2)) in v.cheias
                 else janelas_split).append(_par)
        else:
            for _a, _b2 in v.meus:
                janelas_texto.append((round(_a, 2), round(min(_b2, v.e), 2)))
        if icfg.get("texto_proprio"):
            janelas_texto.append((round(v.s2, 2), round(v.s2 + v.dur, 2)))
        mapa_insert.extend(
            {"a": round(_a, 2), "b": round(min(_b2, v.e), 2), "file": icfg["file"],
             "start": float(icfg.get("start", 0) or 0), "speed": float(icfg.get("speed", 1.0)),
             "s2": float(v.s2)}
            for _a, _b2 in v.meus)
    return janelas_split, janelas_texto, mapa_insert


def aplicar_relogio_footage(ad, look, janelas_split):
    """As janelas de split de VERDADE, com o tempo da footage e o layout do overlay.

    Pegar as janelas da footage INTEIRAS trouxe junto o julgamento dela de layout, e o plano de
    ritmo marca `split` em TODA fatia de insert, inclusive nas que a footage renderiza em tela cheia
    (`cheio` e `pip`, o insert cheio com o apresentador num círculo). Quem sabe se há DOIS painéis é
    o overlay, que lê o config (`split: true`); da footage vem só o TEMPO. Então: janela da footage
    que não encosta em nenhuma do overlay não é split, e sai. Medido num anúncio longo: o insert
    `pip` de 24,48 a 30,40 entrou como split e a legenda foi para a costura de uma emenda que
    naquele layout não existe, pousando no meio de um mockup de página branca (contraste 1,52:1,
    contra 11,7 e 14,3 nos outros trechos).

    Primeira rodada de um anúncio novo (sem o json da footage): segue com o plano do overlay; o
    build seguinte converge.
    """
    try:
        _fj = V1 / "output" / f"{ad}_{look}_footage_1x_ritmo.json"
        if _fj.exists():
            _fsegs = json.loads(_fj.read_text(encoding="utf-8")).get("segs", [])
            _jf = [(round(x["s"], 2), round(x["e"], 2))
                   for x in _fsegs if x.get("layout") == "split"]
            if _jf and janelas_split:
                _int = [(a, b) for a, b in _jf
                        if any(min(b, d) - max(a, c) > SOBREPOSICAO_RELOGIO for c, d in janelas_split)]
                _fora = len(_jf) - len(_int)
                print(f"   [relogio] janelas de split da FOOTAGE ({_fj.name}): "
                      f"{len(_int)} no lugar das {len(janelas_split)} do overlay"
                      + (f"; {_fora} descartada(s): tela cheia (cheio/pip), nao split"
                         if _fora else ""), flush=True)
                if _int:
                    janelas_split = _int
            elif _jf:
                print(f"   [relogio] janelas de split da FOOTAGE ({_fj.name}): "
                      f"{len(_jf)} janelas (overlay nao marcou nenhuma)", flush=True)
                janelas_split = _jf
    except Exception as _e:
        print(f"   [relogio] footage json ilegivel ({_e}); seguindo com o do overlay",
              flush=True)
    return janelas_split
