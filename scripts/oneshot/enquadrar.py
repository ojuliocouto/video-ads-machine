"""Enquadre 9:16 do take real, ancorado no ROSTO medido.

Calibrar o recorte por fração do quadro não funciona: cada câmera, cada distância e cada look tem
enquadramento próprio, e a mesma fração que acerta um corta as sobrancelhas de outro. O rosto é o que
precisa estar no quadro, então é nele que se ancora: o detector mede, a janela centra.

  dimensoes_exibidas(video)             (largura, altura) que o aluno VÊ: a matriz de rotação do celular
                                        troca os dois (o vídeo gravado em pé chega guardado deitado)
  instantes_de_amostra(dur, n)          onde amostrar o take
  medir_rosto(video, amostras, detector) (x, y, w, h) mediano do maior rosto, ou None se nunca achou
  janela_9x16(largura, altura, rosto)   a janela de recorte 9:16, centrada no rosto
  filtro(janela)                        o trecho do ffmpeg: crop + scale 1080x1920

## A janela

9:16 exato, medidas pares (o libx264 em yuv420p não aceita ímpar), sempre dentro do quadro. Um take
horizontal (1920x1080) vira uma janela de 608x1080 centrada no centro do rosto; encostada na borda
quando o rosto está perto dela (o rosto fica fora do centro, mas dentro do quadro: nunca se inventa
imagem). Um take vertical mais largo que 9:16 (3:4) corta só a largura; um mais alto (a tela
de um celular de 19,5:9) corta só a altura, centrado na altura do rosto. Um take já 9:16 não leva recorte.

Sem rosto medido a janela centra no quadro e `centrado_no_rosto` vem False: o plano mostra o aviso, não
finge que mediu (`medir_rosto` devolve None, nunca um número de reserva).
"""
import json
import subprocess

import numpy as np

from gravado.veredito import InsumoInvalido

LARGURA, ALTURA = 1080, 1920
AMOSTRAS = 8
TIMEOUT_S = 120


def _sondar(caminho):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height:stream_side_data=rotation:stream_tags=rotate",
                            "-of", "json", str(caminho)], capture_output=True, text=True, timeout=TIMEOUT_S)
    except FileNotFoundError:
        raise InsumoInvalido("ffprobe não encontrado: instale o ffmpeg com `brew install ffmpeg`")
    if r.returncode != 0:
        raise InsumoInvalido("não consegui ler %s: %s" % (caminho, r.stderr.strip()[-200:] or "ffprobe falhou"))
    try:
        v = json.loads(r.stdout)["streams"][0]
        return int(v["width"]), int(v["height"]), v
    except (KeyError, IndexError, ValueError, TypeError):
        raise InsumoInvalido("%s não tem faixa de vídeo legível" % caminho)


def _rotacao(stream):
    graus = None
    for d in stream.get("side_data_list") or []:
        if "rotation" in d:
            graus = float(d["rotation"])
    if graus is None and (stream.get("tags") or {}).get("rotate") is not None:
        graus = float(stream["tags"]["rotate"])
    return int(round(graus or 0.0)) % 360


def dimensoes_exibidas(caminho):
    """(largura, altura) do vídeo como se vê: a rotação de 90 ou 270 graus do contêiner troca os dois."""
    larg, alt, stream = _sondar(caminho)
    if _rotacao(stream) in (90, 270):
        return alt, larg
    return larg, alt


def instantes_de_amostra(duracao, n=AMOSTRAS):
    """`n` instantes espalhados entre 5% e 95% do take (longe das pontas, onde se liga e se desliga)."""
    return [float(t) for t in np.linspace(0.05 * duracao, 0.95 * duracao, n)]


def _quadro(video, t, larg, alt):
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-ss", "%.3f" % t, "-i", str(video), "-frames:v", "1",
                        "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True, timeout=TIMEOUT_S)
    if r.returncode != 0 or len(r.stdout) != larg * alt * 3:
        return None
    return np.frombuffer(r.stdout, dtype=np.uint8).reshape(alt, larg, 3)


def _detector_haar():
    try:
        import cv2
    except ImportError:
        raise InsumoInvalido("falta o OpenCV para medir o rosto: instale com "
                             "`python3 -m pip install opencv-python-headless`")
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    def detectar(img_bgr):
        cinza = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        piso = max(40, min(img_bgr.shape[:2]) // 12)
        return [tuple(int(v) for v in c) for c in casc.detectMultiScale(cinza, 1.1, 5, minSize=(piso, piso))]
    return detectar


def medir_rosto(video, amostras=AMOSTRAS, detector=None):
    """(x, y, w, h), em pixels do quadro EXIBIDO, do rosto: a mediana, entre os quadros amostrados, do MAIOR
    rosto de cada quadro. None se nenhum quadro teve rosto. `detector(imagem_bgr) -> [(x, y, w, h)]` troca o
    OpenCV (os testes injetam; o padrão é o Haar)."""
    from gravado.nucleo import energia
    larg, alt = dimensoes_exibidas(video)                     # também recusa arquivo ausente ou que não é vídeo
    detectar = detector or _detector_haar()
    achados = []
    for t in instantes_de_amostra(energia.duracao_s(video), amostras):
        quadro = _quadro(video, t, larg, alt)
        if quadro is None:
            continue
        caixas = list(detectar(quadro))
        if caixas:
            achados.append(max(caixas, key=lambda c: c[2] * c[3]))
    if not achados:
        return None
    return tuple(int(round(float(np.median([c[i] for c in achados])))) for i in range(4))


def _par(v):
    return int(round(v / 2.0)) * 2


def _validar(largura, altura, rosto):
    if not (isinstance(largura, int) and isinstance(altura, int) and largura > 0 and altura > 0):
        raise ValueError("dimensões inválidas: %rx%r" % (largura, altura))
    if rosto is not None:
        if len(rosto) != 4 or rosto[2] <= 0 or rosto[3] <= 0:
            raise ValueError("rosto inválido (x, y, largura, altura): %r" % (rosto,))


def _centrar(centro, tamanho, limite):
    """Início (par) de uma janela de `tamanho` centrada em `centro`, dentro de [0, limite]."""
    inicio = _par(centro - tamanho / 2.0)
    return max(0, min(inicio, limite - tamanho))


def janela_9x16(largura, altura, rosto=None):
    """A janela de recorte 9:16 do quadro exibido `largura` x `altura`, centrada no `rosto` (x, y, w, h).

    Devolve {w, h, x, y, precisa_crop, centrado_no_rosto, rosto}. ValueError em dimensão ou rosto inválido."""
    _validar(largura, altura, rosto)
    alvo = 9.0 / 16.0
    cx = largura / 2.0 if rosto is None else rosto[0] + rosto[2] / 2.0
    cy = altura / 2.0 if rosto is None else rosto[1] + rosto[3] / 2.0
    if abs(largura / float(altura) - alvo) < 1e-3:                        # já é 9:16: só escala
        w, h, x, y, precisa = largura, altura, 0, 0, False
    elif largura / float(altura) > alvo:                      # largo demais: corta a largura
        h = altura - altura % 2
        w = min(_par(h * alvo), largura - largura % 2)
        x, y, precisa = _centrar(cx, w, largura), 0, True
    else:                                                     # alto demais: corta a altura
        w = largura - largura % 2
        h = min(_par(w / alvo), altura - altura % 2)
        x, y, precisa = 0, _centrar(cy, h, altura), True
    medido = rosto is not None
    return {"w": w, "h": h, "x": x, "y": y, "precisa_crop": precisa, "centrado_no_rosto": medido,
            "rosto": tuple(rosto) if medido else None}


def filtro(janela):
    """O filtro do ffmpeg: recorta a janela (se precisa) e entrega 1080x1920 com pixel quadrado."""
    partes = []
    if janela["precisa_crop"]:
        partes.append("crop=%d:%d:%d:%d" % (janela["w"], janela["h"], janela["x"], janela["y"]))
    partes += ["scale=%d:%d:flags=lanczos" % (LARGURA, ALTURA), "setsar=1"]
    return ",".join(partes)
