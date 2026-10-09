#!/usr/bin/env python3
"""Fixtures sintéticos e determinísticos para os testes (W0.1).

Por que existe: os testes liam mídia do dono (`_local/dados/refs`, anúncios renderizados)
e wav que só o setup gera, então o clone limpo falhava ou pulava. Aqui cada teste cria, em
tmp, o próprio material com propriedades CONHECIDAS (as pausas de um tom, os instantes de
corte de um vídeo, a rotação declarada), e duas gerações dão o mesmo md5.

Determinismo: o ffmpeg roda com `-fflags +bitexact`, `-flags:v/a +bitexact`, sem
metadados e com `-threads 1`. Ruído tem seed fixa. Nenhuma função lê relógio ou aleatório.

Só depende de ffmpeg e da biblioteca padrão. (A biblioteca de som da fábrica, que depende
de `scripts/som_cortes.py`, entra por `gerar_som`.)
"""
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent

# Flags que tiram do arquivo tudo que muda de uma geração para outra.
_DETERMINISTICO = ["-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
                   "-map_metadata", "-1", "-threads", "1"]
_X264 = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "20"]


def exigir_ffmpeg():
    """Falha com UMA mensagem que diz o que fazer, em vez de erro críptico mais adiante."""
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True)
    except FileNotFoundError:
        r = None
    if r is None or r.returncode != 0:
        raise AssertionError("ffmpeg ausente: instale com `brew install ffmpeg` "
                             "(o fixture sintético depende dele)")


def _ffmpeg(args, destino):
    exigir_ffmpeg()
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", *args, str(destino)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"ffmpeg falhou ao gerar {destino.name}: {r.stderr[-400:]}")
    return destino


# --- áudio --------------------------------------------------------------------------

def tom_com_pausas(destino, dur=6.0, pausas=((1.5, 2.1), (4.0, 4.8)), freq=220.0,
                   volume_db=-12.0, sr=48000):
    """Seno contínuo com silêncio EXATO nas `pausas` (segundos). Simula fala com respiros."""
    corte = ",".join(f"volume=enable='between(t,{a},{b})':volume=0" for a, b in pausas)
    cadeia = f"sine=frequency={freq}:sample_rate={sr}:duration={dur},volume={volume_db}dB"
    if corte:
        cadeia += "," + corte
    return _ffmpeg(["-f", "lavfi", "-i", cadeia, "-c:a", "pcm_s16le", "-ac", "1",
                    *_DETERMINISTICO], destino)


def ruido_rosa(destino, dur=3.0, amplitude=0.5, seed=7, sr=48000):
    """Ruído rosa com seed fixa: mesma entrada, mesmos bytes."""
    cadeia = (f"anoisesrc=color=pink:amplitude={amplitude}:seed={seed}:"
              f"sample_rate={sr}:duration={dur}")
    return _ffmpeg(["-f", "lavfi", "-i", cadeia, "-c:a", "pcm_s16le", "-ac", "1",
                    *_DETERMINISTICO], destino)


# --- vídeo --------------------------------------------------------------------------

def testsrc_com_audio(destino, dur=4.0, tamanho="320x568", fps=25, freq=440.0):
    """testsrc2 (contador e barras) com um seno: vídeo e áudio de duração conhecida."""
    return _ffmpeg(
        ["-f", "lavfi", "-i", f"testsrc2=size={tamanho}:rate={fps}:duration={dur}",
         "-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate=48000:duration={dur}",
         *_X264, "-c:a", "aac", "-b:a", "96k", "-shortest", *_DETERMINISTICO], destino)


def video_com_tom(destino, dur=12.0, tamanho="320x240", fps=30, freq=220.0, volume_db=-30.0,
                  cor="black"):
    """Quadro de cor única com um seno baixo (simula a voz). Base dos testes de mixagem."""
    return _ffmpeg(
        ["-f", "lavfi", "-i", f"color={cor}:s={tamanho}:r={fps}:d={dur}",
         "-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate=48000:duration={dur}",
         "-af", f"volume={volume_db}dB", *_X264, "-c:a", "aac", "-b:a", "96k",
         *_DETERMINISTICO], destino)


def video_cores(destino, cores=("red", "green", "blue"), dur_cada=2.0, tamanho="320x240",
                fps=25):
    """Cores chapadas em sequência: cortes nítidos em dur_cada, 2*dur_cada, ..."""
    entradas, rotulos = [], ""
    for i, cor in enumerate(cores):
        entradas += ["-f", "lavfi", "-i", f"color=c={cor}:s={tamanho}:d={dur_cada}:r={fps}"]
        rotulos += f"[{i}:v]"
    return _ffmpeg([*entradas, "-filter_complex", f"{rotulos}concat=n={len(cores)}:v=1:a=0[o]",
                    "-map", "[o]", *_X264, *_DETERMINISTICO], destino)


# (frequência em X, frequência em Y, fase): senoides estáticas bem afastadas entre si, para
# que o corte entre dois planos vizinhos seja grande mesmo depois de normalizar o quadro.
_PADROES = ((0.35, 0.05, 0.0), (0.05, 0.45, 1.0), (0.22, 0.22, 2.0),
            (0.50, 0.31, 0.5), (0.12, 0.60, 3.0), (0.28, -0.20, 1.5))


def video_por_planos(destino, duracoes, tamanho="180x320", fps=10):
    """Vídeo mudo cujo plano k dura `duracoes[k]` e tem um padrão estático diferente do vizinho.

    Entre planos o conteúdo muda por inteiro (corte nítido); dentro de um plano nada se
    mexe (zero corte falso). Os instantes de corte esperados saem de `instantes_de_corte`.
    """
    partes, rotulos = [], ""
    for i, d in enumerate(duracoes):
        fx, fy, ph = _PADROES[i % len(_PADROES)]
        partes.append(f"nullsrc=s={tamanho}:r={fps}:d={d},format=gray,"
                      f"geq=lum='128+110*sin(X*{fx}+Y*{fy}+{ph})'[v{i}]")
        rotulos += f"[v{i}]"
    fc = ";".join(partes) + f";{rotulos}concat=n={len(duracoes)}:v=1:a=0,format=yuv420p[o]"
    return _ffmpeg(["-filter_complex", fc, "-map", "[o]", "-c:v", "libx264", "-preset",
                    "veryfast", "-crf", "20", *_DETERMINISTICO], destino)


def instantes_de_corte(duracoes):
    """Os instantes (s) em que `video_por_planos(duracoes)` troca de plano."""
    acumulado, saida = 0.0, []
    for d in list(duracoes)[:-1]:
        acumulado += d
        saida.append(round(acumulado, 3))
    return saida


def video_rotacao_menos90(destino, dur=2.0, tamanho="320x180", fps=25):
    """Vídeo codificado deitado (320x180) com a matriz de rotação -90 no contêiner.

    O quadro armazenado e o quadro exibido têm orientações diferentes: é o caso em que o
    `ffprobe` de largura e altura mente sobre o que o aluno vê.
    """
    base = _ffmpeg(["-f", "lavfi", "-i", f"testsrc2=size={tamanho}:rate={fps}:duration={dur}",
                    *_X264, *_DETERMINISTICO], Path(destino).with_name(Path(destino).stem + "_base.mp4"))
    try:
        return _ffmpeg(["-display_rotation:v:0", "-90", "-i", str(base), "-c", "copy",
                        *_DETERMINISTICO], destino)
    finally:
        base.unlink()


# --- biblioteca de som da fábrica ------------------------------------------------------

def gerar_som(pasta):
    """Gera os efeitos (whoosh, tick, riser) em `pasta` pela receita de `som_cortes`.

    Não lê nem escreve em `_local`: aponta `som_cortes.SOM` para `pasta` só durante a geração.
    """
    import sys
    scripts = str(RAIZ / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import som_cortes
    pasta = Path(pasta)
    original = som_cortes.SOM
    som_cortes.SOM = pasta
    try:
        rc = som_cortes.gerar(forcar=True)
    finally:
        som_cortes.SOM = original
    if rc != 0:
        raise AssertionError(f"som_cortes.gerar falhou (rc={rc}) em {pasta}")
    return pasta


def dados_com_som(raiz):
    """Cria um DADOS temporário (`raiz`) com `assets/som` gerado; use com VAM_DADOS=raiz."""
    gerar_som(Path(raiz) / "assets" / "som")
    return Path(raiz)
