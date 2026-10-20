"""Cauda do avatar: completa o fim do avatar que o HeyGen devolve mais curto que a voz.

    avatar.cauda.completar_cauda(pastas_projeto)   -> dict com o que fez, ou None se não precisou (ou não pôde)

Defeito de 20/10/2026 (ensaio da aula): o HeyGen entregou 27,56 s para uma voz de 27,58 s, e o transcritor deu 27,84 s
para o fim da última palavra, depois do fim do áudio. A footage pede o avatar até esse instante e a prancha quebrava
com `ERRO seg 08: duracao 2.77s != esperada 3.07s (fonte curta ou render quebrado)`. O aluno não tem como consertar:
quem completa é a skill, UMA vez, no instante em que recebe o avatar (download do HeyGen, `--retomar` e `--existente`).

A regra:
  - o avatar tem que cobrir a voz com folga de `FOLGA_S` (0,5 s). O alvo é `voz + FOLGA_S`;
  - falta de até `FALTA_MAX_S` (1,0 s) contra a voz: completa. O vídeo congela o último quadro; o áudio segue com a
    cauda da voz original (o que o HeyGen cortou) e depois silêncio. O ffmpeg recodifica o avatar em crf 14, com a
    mesma resolução, a mesma taxa de quadros e o mesmo pix_fmt do original;
  - falta de mais de 1,0 s: não mexe. O avatar está quebrado, não curto, e a conferência (`avatar.conferir`) reprova
    com a diferença escrita;
  - avatar que já cobre `voz + FOLGA_S` (com `TOLERANCIA_S` de um quadro): nada a fazer, o arquivo não muda.

Por que antes da conferência e nunca depois: a aprovação do look amarra o sha256 de `avatar/conferencia.json`, que
guarda o sha256 do avatar. A cauda entra ANTES de `conferir`, então a aprovação nasce já sobre o arquivo completo e
nada na skill volta a mexer no avatar depois dela.

Mídia que o ffprobe não lê fica para a conferência dizer (não é erro daqui). Tudo que toca o mundo é injetável
(`executar`), como no resto de `avatar/`: os testes não usam rede.
"""
import json
import os
from collections import namedtuple
from pathlib import Path

from avatar.heygen_cliente import executar_real

FOLGA_S = 0.5           # o avatar cobre a voz com esta folga: o transcritor dá o fim da última palavra até ~0,3 s depois do áudio
FALTA_MAX_S = 1.0       # avatar mais curto que a voz por mais que isto não se completa (a conferência reprova)
TOLERANCIA_S = 0.1      # um quadro a 10 fps: arredondar o encode para quadro inteiro não pede cauda de novo
CRF = "14"
AUDIO_HZ = "48000"
AUDIO_KBPS = "192k"

Medida = namedtuple("Medida", "video audio formato")
Plano = namedtuple("Plano", "alvo_s falta_s")


class CaudaFalhou(RuntimeError):
    """O ffmpeg não conseguiu completar o avatar. O arquivo do avatar ficou como estava."""


def _sonda(executar, caminho):
    """Medida(video, audio, formato) em segundos, ou None se o ffprobe não lê o arquivo."""
    rc, saida = executar(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration:format=duration",
                          "-of", "json", str(caminho)])
    try:
        d = json.loads(saida)
        formato = float(d["format"]["duration"])
    except (ValueError, KeyError, TypeError):
        return None
    if rc != 0 or formato <= 0:
        return None
    trilhas = {}
    for s in d.get("streams") or []:
        tipo = s.get("codec_type")
        if tipo in ("video", "audio") and tipo not in trilhas:
            try:
                trilhas[tipo] = float(s["duration"])
            except (KeyError, ValueError, TypeError):
                trilhas[tipo] = formato
    return Medida(trilhas.get("video"), trilhas.get("audio"), formato)


def planejar(avatar_s, voz_s):
    """Plano(alvo_s, falta_s) para completar, ou None (já cobre a voz, ou a falta passa de FALTA_MAX_S)."""
    falta = round(voz_s - avatar_s, 3)
    if falta > FALTA_MAX_S:
        return None
    alvo = round(voz_s + FOLGA_S, 3)
    if avatar_s >= alvo - TOLERANCIA_S:
        return None
    return Plano(alvo, falta)


def _filtros(alvo_s, video_s, audio_s, voz_s, com_voz_original):
    """(filter_complex, mapas). O vídeo congela o último quadro; o áudio segue com a voz original e depois silêncio."""
    fc = ["[0:v]tpad=stop_mode=clone:stop_duration=%.3f[v]" % (max(0.0, alvo_s - video_s) + 1.0)]
    mapas = ["[v]"]
    if audio_s is not None:
        formato = "aresample=%s,aformat=sample_fmts=fltp:channel_layouts=stereo" % AUDIO_HZ
        if com_voz_original and voz_s > audio_s:
            fc.append("[0:a]%s[a0]" % formato)
            fc.append("[1:a]atrim=start=%.3f,asetpts=PTS-STARTPTS,%s[a1]" % (audio_s, formato))
            fc.append("[a0][a1]concat=n=2:v=0:a=1,apad[a]")
        else:
            fc.append("[0:a]%s,apad[a]" % formato)
        mapas.append("[a]")
    return ";".join(fc), mapas


def _argv_ffmpeg(avatar, voz, saida, alvo_s, medida_avatar, voz_s):
    video_s = medida_avatar.video
    audio_s = medida_avatar.audio
    com_voz = audio_s is not None and voz_s > audio_s
    fc, mapas = _filtros(alvo_s, video_s, audio_s, voz_s, com_voz)
    argv = ["ffmpeg", "-v", "error", "-y", "-i", str(avatar)]
    if com_voz:
        argv += ["-i", str(voz)]
    argv += ["-filter_complex", fc]
    for m in mapas:
        argv += ["-map", m]
    argv += ["-t", "%.3f" % alvo_s, "-c:v", "libx264", "-preset", "medium", "-crf", CRF, "-pix_fmt", "yuv420p"]
    if audio_s is not None:
        argv += ["-c:a", "aac", "-b:a", AUDIO_KBPS]
    argv += ["-movflags", "+faststart", str(saida)]
    return argv


def _virgula(valor):
    return ("%.2f" % valor).replace(".", ",")


def linha(r):
    """Uma linha que o `vam avatar` imprime e o status guarda: o que foi feito e por quê."""
    return ("avatar completado: +%s s de cauda (último quadro congelado, áudio com a voz original e depois silêncio): "
            "o avatar tinha %s s para uma voz de %s s e agora vai a %s s"
            % (_virgula(r["cauda_s"]), _virgula(r["antes_s"]), _virgula(r["voz_s"]), _virgula(r["depois_s"])))


def completar_cauda(pastas_projeto, executar=None):
    """Completa avatar/avatar.mp4 no lugar (por temporário + troca). Devolve
    {"antes_s", "voz_s", "depois_s", "cauda_s"} se completou; None se não precisou ou se não pôde decidir
    (mídia ilegível, sem vídeo, falta de mais de FALTA_MAX_S). CaudaFalhou se o ffmpeg falha."""
    executar = executar or executar_real
    p = pastas_projeto
    avatar, voz = p.avatar_mp4, p.voz_limpo
    if not avatar.is_file() or not voz.is_file():
        return None
    m_avatar, m_voz = _sonda(executar, avatar), _sonda(executar, voz)
    if m_avatar is None or m_voz is None or m_avatar.video is None:
        return None
    avatar_s = min(x for x in (m_avatar.video, m_avatar.audio) if x is not None)
    plano = planejar(avatar_s, m_voz.formato)
    if plano is None:
        return None
    temporario = avatar.with_name("avatar.completando.mp4")
    try:
        rc, saida = executar(_argv_ffmpeg(avatar, voz, temporario, plano.alvo_s, m_avatar, m_voz.formato))
        if rc != 0 or not temporario.is_file():
            raise CaudaFalhou("não consegui completar a cauda do avatar (%.2f s para uma voz de %.2f s): %s"
                              % (avatar_s, m_voz.formato, (saida or "").strip()[-300:]))
        novo = _sonda(executar, temporario)
        medidas = [x for x in (novo.video, novo.audio) if x is not None] if novo and novo.video else []
        if not medidas or min(medidas) < plano.alvo_s - TOLERANCIA_S:
            raise CaudaFalhou("o avatar completado saiu com %s s e o alvo era %s s: o arquivo original foi mantido"
                              % (_virgula(min(medidas)) if medidas else "?", _virgula(plano.alvo_s)))
        os.replace(str(temporario), str(avatar))
    finally:
        if temporario.exists():
            temporario.unlink()
    return {"antes_s": round(avatar_s, 3), "voz_s": round(m_voz.formato, 3), "depois_s": plano.alvo_s,
            "cauda_s": round(plano.alvo_s - avatar_s, 3)}
