"""Loudness de entrega (C12): -14 LUFS (mais ou menos 1,2), true peak até -1,5 dBTP, 48 kHz.

Por que dois passes: o loudnorm de um passe só ESTIMA e erra o alvo em vários LU; somar ganho
puro estouraria o pico. O primeiro passe MEDE (print_format=json), o segundo APLICA os
valores medidos em modo linear. O vídeo, se houver, vai com `-c:v copy`: sem perda de
qualidade e sem custo de re-encode.

Por que existe: a voz gravada chegava a cerca de -31 LUFS e o pipeline nunca normalizava,
então o anúncio saía uns 18 LU abaixo do alvo das plataformas e, no feed, ao lado de um
vídeo normalizado, soava quase mudo.

Ordem no pipeline (decisão de 27/08, medida): normalizar a VOZ primeiro e mixar efeitos e
música depois. Na ordem inversa o loudnorm "come" a calibragem dos efeitos.

  medir(arq)                 -> Medicao(integrado_lufs, true_peak_dbtp, lra)
  normalizar(entrada, saida) -> Path da saída
  dentro_da_faixa(medicao)   -> bool (o que o gate de entrega cobra)
"""
import json
import re
import subprocess
from collections import namedtuple
from pathlib import Path

LUFS_ALVO = -14.0
TP_ALVO = -1.5
LRA_ALVO = 11.0
TOLERANCIA_LUFS = 1.2     # faixa do gate: -14 mais ou menos 1,2
SR = 48000

Medicao = namedtuple("Medicao", "integrado_lufs true_peak_dbtp lra")


class ErroDeLoudness(RuntimeError):
    pass


def _ffmpeg(args):
    return subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", *args],
                          capture_output=True, text=True)


def _numero(texto):
    try:
        v = float(texto)
    except (TypeError, ValueError):
        return None
    return v if v == v and abs(v) != float("inf") else None


def medir(arq):
    """Mede com o ebur128 (true peak ligado). Lê o bloco 'Summary' do fim do log."""
    r = _ffmpeg(["-i", str(arq), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
    if r.returncode != 0:
        raise ErroDeLoudness(f"não consegui medir {arq}: {r.stderr.strip()[-300:]}")
    resumo = r.stderr.rsplit("Summary:", 1)
    if len(resumo) != 2:
        raise ErroDeLoudness(f"o ffmpeg não devolveu o resumo de loudness de {arq}")
    bloco = resumo[1]
    i = re.search(r"\bI:\s+(-?[\d.]+|-inf)\s+LUFS", bloco)
    lra = re.search(r"\bLRA:\s+(-?[\d.]+)\s+LU", bloco)
    tp = re.search(r"Peak:\s+(-?[\d.]+|-inf)\s+dBFS", bloco)
    integrado = _numero(i.group(1)) if i else None
    pico = _numero(tp.group(1)) if tp else None
    if integrado is None or pico is None:
        raise ErroDeLoudness(f"áudio sem sinal mensurável em {arq} (mudo?): não há o que normalizar")
    return Medicao(integrado, pico, _numero(lra.group(1)) if lra else 0.0)


def dentro_da_faixa(m, alvo=LUFS_ALVO, tolerancia=TOLERANCIA_LUFS, tp_max=TP_ALVO):
    """A régua do gate de entrega: LUFS na faixa e true peak até o teto."""
    return abs(m.integrado_lufs - alvo) <= tolerancia + 1e-9 and m.true_peak_dbtp <= tp_max + 1e-9


def _tem_video(arq):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=codec_type", "-of", "csv=p=0", str(arq)],
                       capture_output=True, text=True)
    return "video" in r.stdout


def _codec_de_audio(destino):
    ext = Path(destino).suffix.lower()
    if ext == ".wav":
        return ["-c:a", "pcm_s16le"]
    if ext == ".mp3":
        return ["-c:a", "libmp3lame", "-b:a", "192k"]
    if ext == ".flac":
        return ["-c:a", "flac"]
    return ["-c:a", "aac", "-b:a", "192k"]


def normalizar(entrada, saida, alvo=LUFS_ALVO, tp=TP_ALVO, lra=LRA_ALVO):
    """Normaliza o áudio de `entrada` para `alvo` LUFS e grava em `saida` (48 kHz).

    Vídeo: o quadro vai copiado. Nunca escreve por cima de `entrada`.
    """
    entrada, saida = Path(entrada), Path(saida)
    if entrada.resolve() == saida.resolve():
        raise ErroDeLoudness("a saída tem que ser outro arquivo: normalizar não sobrescreve a entrada")
    base = f"loudnorm=I={alvo}:TP={tp}:LRA={lra}"
    p1 = _ffmpeg(["-i", str(entrada), "-vn", "-af", f"{base}:print_format=json", "-f", "null", "-"])
    achado = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p1.stderr)
    if p1.returncode != 0 or not achado:
        raise ErroDeLoudness(f"não consegui medir {entrada}: {p1.stderr.strip()[-300:]}")
    d = json.loads(achado.group(0))
    if _numero(d.get("input_i")) is None or _numero(d.get("input_tp")) is None:
        raise ErroDeLoudness(f"áudio sem sinal mensurável em {entrada} (mudo?): não há o que normalizar")
    aplicar = (f"{base}:measured_I={d['input_i']}:measured_TP={d['input_tp']}:"
               f"measured_LRA={d['input_lra']}:measured_thresh={d['input_thresh']}:"
               f"offset={d['target_offset']}:linear=true")
    saida.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["-y", "-v", "error", "-i", str(entrada), "-af", aplicar, "-ar", str(SR)]
    if _tem_video(entrada):
        cmd += ["-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy", "-movflags", "+faststart"]
    else:
        cmd += ["-vn"]
    cmd += [*_codec_de_audio(saida), str(saida)]
    p2 = _ffmpeg(cmd)
    if p2.returncode != 0:
        raise ErroDeLoudness(f"o ffmpeg falhou ao normalizar {entrada}: {p2.stderr.strip()[-300:]}")
    return saida
