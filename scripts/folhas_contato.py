#!/usr/bin/env python3
"""Folhas de contato: prova de que alguem viu o filme inteiro, nao so 8 quadros soltos.

Por que existe (29/08/2026): um anuncio foi avaliado olhando 8 quadros isolados do
roteiro e passou. So quando alguem assistiu a folha do video inteiro o diagnostico
mudou: o que parecia bom em quadros separados nao segurava em movimento. E a tira de
0,05s em volta de cada corte achou 4 quadros rasgados que ninguem tinha visto, porque
ninguem tinha olhado o instante exato da troca de plano, so o antes e o depois.

Este modulo gera dois PNGs por build, obrigatorios, pra ninguem mais avaliar um
anuncio sem ter visto o filme inteiro:

  folha_inteira   um quadro a cada `passo` segundos, grade de 5 colunas: mostra o
                  anuncio do inicio ao fim numa imagem so.
  tiras_de_corte  8 quadros a 0,05s de intervalo, centrados em cada corte medido por
                  `medir_ritmo.cortes_de`: mostra o instante exato da troca de plano,
                  onde mora o quadro rasgado que a folha inteira nao resolve (os
                  quadros ali estao 1,5s afastados, longe demais pra pegar 0,05s de
                  falha).

Uso:
    python3 folhas_contato.py <video.mp4> [pasta_saida]
"""
import math
import subprocess
from pathlib import Path

import medir_ritmo

LARGURA_MINIATURA = 216
ALTURA_MINIATURA = 384
COLUNAS_FOLHA_INTEIRA = 5

LARGURA_TIRA = 132
ALTURA_TIRA = 234
QUADROS_POR_CORTE = 8


def _duracao(video):
    """Duracao do video em segundos, via ffprobe."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def folha_inteira(video, destino, passo=1.5):
    """Um quadro a cada `passo` segundos do video inteiro, em grade de 5 colunas.

    Um UNICO comando ffmpeg (fps -> scale -> tile), de proposito: e a mesma leitura
    que um humano faria assistindo o anuncio, so que compacta o filme inteiro numa
    imagem so. `math.ceil(duracao/passo)` da o TETO de quadros que o filtro `fps` vai
    entregar (medido: nunca entrega mais que isso, entao a grade nunca fica pequena
    demais); quando a grade sobra, o `tile` preenche o resto de preto sozinho, entao
    superestimar e seguro e subestimar nao e.
    """
    video = Path(video)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    duracao = _duracao(video)
    n_quadros = max(1, math.ceil(duracao / passo))
    linhas = max(1, math.ceil(n_quadros / COLUNAS_FOLHA_INTEIRA))

    filtro = (f"fps=1/{passo},scale={LARGURA_MINIATURA}:{ALTURA_MINIATURA},"
              f"tile={COLUNAS_FOLHA_INTEIRA}x{linhas}")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vf", filtro,
         "-frames:v", "1", str(destino)], check=True)
    return destino


def _linha_do_corte(video, instante, passo, n, destino_linha):
    """Extrai os `n` quadros de `passo` em `passo` centrados em `instante` e monta
    UMA linha de miniaturas lado a lado (tile Nx1)."""
    inicio = max(0.0, instante - (n / 2 - 0.5) * passo)
    filtro = (f"fps=1/{passo},scale={LARGURA_TIRA}:{ALTURA_TIRA},"
              f"tile={n}x1")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{inicio:.3f}", "-i", str(video),
         "-vf", filtro, "-frames:v", "1", str(destino_linha)], check=True)
    return destino_linha


def tiras_de_corte(video, destino, cortes, passo=0.05, n=QUADROS_POR_CORTE):
    """Uma linha por corte, cada linha com `n` quadros a `passo`s de intervalo
    centrados no instante do corte, todas empilhadas verticalmente numa imagem so.

    Os cortes vem de `medir_ritmo.cortes_de(video)`: e o mesmo instante que o resto da
    fabrica usa pra falar de "corte", entao a tira mostra exatamente o que o gate de
    ritmo mediu, nao uma adivinhacao.

    Sem corte medido (ad estatico ou deteccao vazia) ainda assim gera uma linha, no
    meio do video: uma folha sem nenhuma linha nao prova nada, e o compromisso e
    sempre mostrar pelo menos um instante em detalhe.
    """
    from PIL import Image

    video = Path(video)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    instantes = list(cortes) if cortes else [_duracao(video) / 2.0]

    linhas_tmp = []
    try:
        for i, instante in enumerate(instantes):
            tmp = destino.parent / f"_tmp_linha_corte_{i}.png"
            _linha_do_corte(video, instante, passo, n, tmp)
            linhas_tmp.append(tmp)

        imagens = [Image.open(p) for p in linhas_tmp]
        largura = max(im.width for im in imagens)
        altura_total = sum(im.height for im in imagens)
        composta = Image.new("RGB", (largura, altura_total), "black")
        y = 0
        for im in imagens:
            composta.paste(im, (0, y))
            y += im.height
            im.close()
        composta.save(destino)
    finally:
        for p in linhas_tmp:
            p.unlink(missing_ok=True)

    return destino


def gerar_folhas(video, pasta_saida):
    """Gera as duas folhas de contato do video e devolve os dois caminhos.

    MOTIVO (31/08/2026): em 29/08/2026 um anuncio foi avaliado olhando 8 quadros
    isolados do roteiro e o veredito passou; so quando alguem assistiu a folha do
    video inteiro o diagnostico mudou. E a tira a 0,05s em volta dos cortes achou 4
    quadros rasgados que ninguem tinha visto olhando quadro a quadro. Por isso este
    par de imagens passa a ser artefato obrigatorio de todo build: ninguem avalia um
    anuncio sem ter visto o filme inteiro.
    """
    video = Path(video)
    pasta_saida = Path(pasta_saida)
    stem = video.stem

    p_inteira = pasta_saida / f"{stem}_folha_inteira.png"
    p_tiras = pasta_saida / f"{stem}_tiras_corte.png"

    folha_inteira(video, p_inteira)
    cortes = medir_ritmo.cortes_de(video)
    tiras_de_corte(video, p_tiras, cortes)

    return p_inteira, p_tiras


if __name__ == "__main__":
    import sys

    _video = Path(sys.argv[1])
    _pasta = Path(sys.argv[2]) if len(sys.argv) > 2 else _video.parent
    _p1, _p2 = gerar_folhas(_video, _pasta)
    print(_p1)
    print(_p2)
