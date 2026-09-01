#!/usr/bin/env python3
"""Escolha da transicao entre dois blocos.

Saiu de dentro do `produzir_roteiro.py` (que e script e nao da pra importar) pra poder
ter teste. A regra que mora aqui nasceu de defeito real: o Julio viu o anuncio e mandou
"0:56, 0:58, tem uma falha visual na transicao". No quadro de t=56,03s aparece uma faixa
estreita do plano anterior colada na borda esquerda, com o novo ocupando o resto, ou seja
um deslize pego no meio.

O deslize nao estava quebrado. Ele estava no lugar errado: entre dois planos do MESMO
apresentador, no mesmo fundo e quase no mesmo enquadramento, nao ha nada que o movimento
explique, entao a faixa nao le como transicao e sim como a imagem rasgando. Entre insert
e apresentador o mesmo deslize funciona, porque a imagem inteira muda.
"""

# tipo usado quando o corte e seco: `fade` numa duracao curtissima nao empurra a imagem,
# entao nao existe faixa pra aparecer. Deslize com duracao curta so ESCONDE a faixa.
XF_SECO_TIPO = "fade"
# CORTE DE VERDADE E UM QUADRO (29/08/2026, terceira passada). Trocar o deslize por
# `fade` matou as quatro costuras, mas o gate de ritmo caiu de 16,7 para 14,1 cortes/min
# e o tempo parado subiu de 9,3% para 17,6%: exatamente os 4 cortes que eu tinha mexido.
# Motivo: XF_SECO e 0,04s, e um `fade` espalhado por mais de um quadro nao le como corte
# nem pro detector nem pro olho. Eu tinha trocado um rasgo por um borrao.
# Um quadro de duracao e o menor valor que o `xfade` aceita sem virar no-op, e nessa
# duracao ele E um corte: a troca acontece inteira entre dois quadros consecutivos.
XF_CORTE = 1.0 / 30.0


# tipos cuja footage NAO e o apresentador
_TIPOS_TELA = ("insert", "logo", "lettering_logo")


def _e_apresentador(bloco):
    """True quando a imagem daquele bloco e o apresentador.

    `lettering` conta como apresentador: o texto muda por cima, mas a footage por baixo
    continua sendo ele, entao um deslize ali rasga do mesmo jeito.
    """
    return (bloco or {}).get("type") not in _TIPOS_TELA


def corte_seco_entre(bloco_que_sai, bloco_que_entra):
    """True quando os dois lados sao o apresentador e a transicao tem que ser seca."""
    return _e_apresentador(bloco_que_sai) and _e_apresentador(bloco_que_entra)


def tipo_de_transicao(bloco_que_sai, bloco_que_entra, i, forcado=None):
    """Transicao do corte que ENTRA no bloco.

    Medido em material real do AD14 (`testar_transicoes.py`), no corte mais duro do ad:
    slide 30,2 de movimento e ZERO escurecimento; smooth 16,5 e zero. As descartadas e o
    porque: `fadeblack` apaga a tela (queda 68,8) e `zoomin` amplia tanto no meio do
    corte que vira borrao escuro. O zoomin passou no teste sintetico e falhou no material
    real: a regra e medir no material do proprio ad, nunca escolher pelo nome.
    """
    if forcado and forcado != "auto":
        return forcado
    # DURACAO SECA MANDA NO TIPO (29/08/2026, segunda passada, achado varrendo o filme).
    # Consertei o corte de 0:56 (apresentador -> apresentador) e depois varri o anuncio
    # inteiro atras da mesma assinatura: sobraram TRES quadros com meia tela de cada
    # plano, em t=11,93s, 17,93s e 28,70s. Todos entrada de INSERT, que eu tinha
    # deixado de fora dizendo que ali o deslize funciona porque a imagem toda muda.
    # Nao funciona, e o motivo e a duracao: entrada de insert corre em XF_SECO, 0,08s,
    # dois quadros a 30fps. Deslize em dois quadros nao le como MOVIMENTO, le como
    # quadro RASGADO: o espectador nao ve a tela deslizar, ve um quadro partido ao meio.
    # Entao a regra nao e sobre quem entra, e sobre quanto tempo dura: transicao seca usa
    # tipo que NAO desloca a imagem. Deslize so em transicao longa o bastante pra ser
    # lida como movimento, que hoje e so a volta macia pro apresentador.
    if corte_seco_entre(bloco_que_sai, bloco_que_entra):
        return XF_SECO_TIPO
    t = (bloco_que_entra or {}).get("type")
    if t in ("insert", "logo", "lettering_logo"):
        return XF_SECO_TIPO        # corre em XF_SECO: deslizar aqui rasga o quadro
    if t == "lettering":
        return "slideleft" if i % 2 else "slideright"
    return "smoothleft" if i % 2 else "smoothright"     # whip macio na volta pro avatar
