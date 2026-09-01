#!/usr/bin/env python3
"""Push-in nas gravacoes de tela: o asset entra INTEIRO e a camera avanca depois.

Excecao NOMEADA, autorizada pelo Julio em 28/08/2026, a ordem de 26/08 ("o video todo que
aparece no video e o que precisa"). Vale so para gravacao de tela, e existe porque a
medicao mostrou que sem ela nao ha caminho:

    esc_max = 1080 / largura_da_fonte

Um asset 16:9 entrando inteiro num quadro 9:16 nao passa de 1080x607, ou seja 31,6% do
quadro. O motor ja entrega 32,2%, isto e 96% do teto FISICO. Alargar a moldura de 1008
para 1080 renderia +7% de altura de letra, meio pixel num glifo de 7px. Os outros dois
caminhos eram gravar de novo com zoom de interface maior (o Julio recusou) ou mover a
informacao do print para o lettering (que continua valendo, e outra correcao).

Por que push-in nao e recorte: em t=0 o zoom e 1,0 e o quadro inteiro do asset esta na
tela. O que muda e o TEMPO, nao o enquadramento inicial. Recorte esconde desde o comeco;
push-in mostra tudo e depois aproxima.

Este arquivo e modulo, nao script, de proposito: `produzir_roteiro.py` nao e importavel
(rodar o import dispara o build), entao a regra que precisa de teste mora aqui.
"""
import os
import subprocess

# ALVO E TETO, TIRADOS DA MEDICAO DA LEVA, NAO DE GOSTO.
# `esc` e a escala que o motor aplica sobre a fonte para caber na janela do card
# (1008/largura no split, 1036/largura no cheio). Medidas reais dos 8 assets deitados do
# jh13: 0,438 / 0,525 / 0,526 / 0,733 / 0,787.
#
# ZOOM_ALVO=0,75: leva os dois piores (0,438 e 0,525) para perto de tres quartos do
# tamanho nativo, que e onde a diferenca de leitura aparece, e deixa 0,787 intocado
# (0,787 ja passa de 0,75, entao fator 1,0). Push-in em asset que ja entra grande seria
# movimento decorativo, e movimento sem motivo e justamente o que faz peca parecer
# gerada.
#
# ZOOM_MAX=1,70: teto. Acima disso o avanco esconde tanto do asset que vira recorte com
# outro nome, e recorte continua proibido. 1,70 sobre a janela de 1008px deixa 593px de
# fonte visiveis no fim, ou seja mais da metade do asset continua em quadro.
ZOOM_ALVO = 0.75
ZOOM_MAX = 1.70


def fator_push_in(esc):
    """Quanto a camera avanca, dado o quanto o asset encolheu para caber.

    Devolve 1,0 (sem avanco) quando o asset ja entra em `ZOOM_ALVO` ou maior.
    """
    if esc is None or esc <= 0:
        return 1.0
    return max(1.0, min(ZOOM_ALVO / esc, ZOOM_MAX))


def foco_do_conteudo(src, start=0.0):
    """Centroide do CONTEUDO do asset, normalizado em (0..1, 0..1).

    Avancar no centro geometrico avanca no vazio: pagina de site tem o conteudo em cima e
    margem embaixo, e gravacao de tela tem barra e sidebar. O centroide de energia de
    borda acha onde o material realmente esta.

    Sobel horizontal em cinza, reduzido para 64x64 por custo. Devolve (0.5, 0.5) quando
    nao conseguir medir: sem numero, o comportamento cai no centro, que e o padrao antigo
    e conhecido, nunca num palpite novo.
    """
    try:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            q = os.path.join(td, "b.pgm")
            r = subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-ss", f"{max(float(start or 0), 0):.3f}",
                 "-i", str(src), "-frames:v", "1",
                 "-vf", "format=gray,sobel,scale=64:64", q],
                capture_output=True, text=True)
            if r.returncode != 0 or not os.path.exists(q):
                return 0.5, 0.5
            dados = open(q, "rb").read()
            corte, campos = 0, 0
            while campos < 4 and corte < len(dados):
                if dados[corte:corte + 1].isspace():
                    campos += 1
                corte += 1
            px = dados[corte:]
            if len(px) < 64 * 64:
                return 0.5, 0.5
            total = sx = sy = 0
            for i in range(64 * 64):
                v = px[i]
                if v < 24:          # ruido de compressao, nao conteudo
                    continue
                total += v
                sx += v * (i % 64)
                sy += v * (i // 64)
            if total == 0:
                return 0.5, 0.5
            fx, fy = (sx / total) / 63.0, (sy / total) / 63.0
            # nao deixa o foco encostar na borda: avancar na quina mostra margem, nao
            # conteudo, e ainda arrisca sobrar area vazia dentro da janela
            fx = min(max(fx, 0.30), 0.70)
            fy = min(max(fy, 0.30), 0.70)
            return fx, fy
    except Exception:
        return 0.5, 0.5


def filtro(esc, dur, fps, larg, alt, foco=(0.5, 0.5)):
    """Trecho de filtro ffmpeg que faz o avanco, ou string vazia se nao houver avanco.

    Entra DEPOIS do scale para a janela do card, entao trabalha em larg x alt.
    `zoompan` com d=1 gera um quadro de saida por quadro de entrada; a rampa usa `on`
    (indice do quadro de saida), que e o unico contador que anda por quadro aqui.
    """
    z = fator_push_in(esc)
    if z <= 1.0001:
        return ""
    n = max(int(round(dur * fps)) - 1, 1)
    fx, fy = foco
    return (f",zoompan=z='min(1+{z - 1:.5f}*on/{n},{z:.5f})'"
            f":x='iw*{fx:.4f}-(iw/zoom/2)'"
            f":y='ih*{fy:.4f}-(ih/zoom/2)'"
            f":d=1:s={larg}x{alt}:fps={fps}")
