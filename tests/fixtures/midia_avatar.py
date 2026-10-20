"""Mídia sintética de ffmpeg para os testes do avatar (cauda, CLI): segundos de duração, nenhuma chamada paga.

    criar_avatar(caminho, dur, fps=25, tamanho="160x284", audio=True)   mp4 animado (testsrc2) com tom de 440 Hz, aac estéreo
    criar_voz(caminho, dur)                                             mp3 mono de 44,1 kHz com o mesmo tom
    sonda(caminho)                                                      {video, audio, formato}: duração de cada trilha
    quadro(caminho, t) / distancia(a, b)                                o quadro em `t` (cinza) e a diferença média entre dois
    volume_medio(caminho, ini, fim)                                     mean_volume em dB de um trecho do áudio
    sha(caminho)                                                        sha256 do arquivo

Só biblioteca padrão, Python 3.9.
"""
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

TEM_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _ff(*args):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y"] + [str(a) for a in args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def criar_avatar(caminho, dur, fps=25, tamanho="160x284", audio=True):
    """Vídeo animado (testsrc2 muda a cada quadro) com tom de 440 Hz e áudio aac estéreo de 48 kHz, como o do HeyGen."""
    entradas = ["-f", "lavfi", "-i", "testsrc2=size=%s:rate=%d:duration=%s" % (tamanho, fps, dur)]
    saida = ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    if audio:
        entradas += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=%s" % dur]
        saida += ["-c:a", "aac", "-ac", "2"]
    _ff(*(entradas + saida + [caminho]))
    return Path(caminho)


def criar_voz(caminho, dur):
    """A voz limpa: mp3 mono de 44,1 kHz com o mesmo tom (a voz original não tem o formato do áudio do avatar)."""
    _ff("-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=%s" % dur, "-ac", "1",
        "-c:a", "libmp3lame", "-b:a", "64k", caminho)
    return Path(caminho)


def sonda(caminho):
    """{video, audio, formato}: duração em segundos de cada trilha (None se não há)."""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration:format=duration",
                        "-of", "json", str(caminho)], capture_output=True, text=True)
    d = json.loads(r.stdout)
    por_tipo = {s["codec_type"]: float(s["duration"]) for s in d.get("streams", []) if s.get("duration")}
    return {"video": por_tipo.get("video"), "audio": por_tipo.get("audio"), "formato": float(d["format"]["duration"])}


def quadro(caminho, t):
    """Os bytes do quadro em `t` segundos (cinza, 160x284): dois quadros iguais são o mesmo quadro."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.3f" % t, "-i", str(caminho), "-frames:v", "1",
                        "-vf", "format=gray", "-f", "rawvideo", "-"], capture_output=True)
    assert r.returncode == 0 and r.stdout, r.stderr
    return r.stdout


def distancia(a, b):
    """Diferença média, em níveis de cinza, entre dois quadros (o encode h264 deixa ruído de 1 ou 2 níveis)."""
    return sum(abs(x - y) for x, y in zip(a, b)) / float(len(a))


def volume_medio(caminho, ini, fim):
    """mean_volume em dB do trecho [ini, fim] do áudio (-91 e abaixo é silêncio digital)."""
    r = subprocess.run(["ffmpeg", "-v", "info", "-ss", "%.3f" % ini, "-t", "%.3f" % (fim - ini), "-i", str(caminho),
                        "-vn", "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"mean_volume:\s*(-?[0-9.]+|-inf) dB", r.stderr)
    assert m, r.stderr
    return -200.0 if m.group(1) == "-inf" else float(m.group(1))


def sha(caminho):
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()
