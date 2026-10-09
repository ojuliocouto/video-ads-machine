"""Quanto de espaço livre há no TOPO do anúncio inteiro, para a caixinha de pergunta.

A caixinha fica FIXA o anúncio inteiro, então a área livre tem que valer o anúncio inteiro, não só
o gancho. Varre a peça de 1 em 1 segundo e acha o ponto em que a cabeça sobe MAIS; a caixinha pode
descer até 30 px acima dele. Entre os rostos de cada quadro vale o maior (a pessoa em primeiro
plano; gente do fundo não conta). Detector: Haar do OpenCV, que mede o rosto, não adivinha.

    python3 scripts/gravado/area_ad_inteiro.py PECA [PECA ...] [--projeto DIR]     como A1_normal
"""
import argparse
import functools
import subprocess
import sys
from pathlib import Path

import numpy as np

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado import montar, veredito  # noqa: E402
from gravado import projeto as gp  # noqa: E402
from gravado.nucleo import energia  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402

FOLGA_PX = 30
PASSO_S = 1.0
ALTURA = 1920


@functools.lru_cache(maxsize=1)
def _cv2_e_cascata():
    try:
        import cv2
    except ImportError:
        raise InsumoInvalido("falta o OpenCV: instale com `python3 -m pip install opencv-python-headless`")
    return cv2, cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def topo_da_cabeca(img_bgr):
    """O y do topo da cabeça do maior rosto do quadro (testa incluída), ou None se não há rosto."""
    cv2, casc = _cv2_e_cascata()
    cinza = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    rostos = casc.detectMultiScale(cinza, 1.1, 6, minSize=(120, 120))
    if not len(rostos):
        return None
    x, y, w, h = max(rostos, key=lambda f: f[2] * f[3])
    return max(0, int(y - 0.6 * h))


def y_ate_onde_a_caixinha_pode_ir(pior_topo, folga=FOLGA_PX):
    return max(0, pior_topo - folga)


def varrer(video, passo=PASSO_S):
    """(topo mais alto da cabeça em px, instante em que acontece) ao longo da peça."""
    cv2, _ = _cv2_e_cascata()
    dur = energia.duracao_s(video)
    pior, quando, t = 10 ** 9, None, 0.5
    while t < dur:
        r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-ss", "%.2f" % t, "-i", str(video), "-frames:v", "1",
                            "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
        img = cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_COLOR) if r.stdout else None
        if img is not None:
            y = topo_da_cabeca(img)
            if y is not None and y < pior:
                pior, quando = y, t
        t += passo
    if quando is None:
        raise InsumoInvalido("não achei rosto em %s: a caixinha não tem como ser medida" % video)
    return pior, quando


def main(argv=None):
    ap = argparse.ArgumentParser(description="Até onde a caixinha pode descer sem encostar na cabeça.")
    ap.add_argument("pecas", nargs="+", help="nomes das peças montadas, como A1_normal")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    a = ap.parse_args(argv)

    def fazer():
        proj = gp.carregar(a.projeto)
        print("%-14s %7s %10s %8s   caixinha pode ir até" % ("PEÇA", "DUR", "MAIS ALTO", "QUANDO"))
        for nome in a.pecas:
            video = veredito.exigir_arquivo(proj.montado(nome), "a peça montada %s" % nome)
            pior, quando = varrer(video)
            ate = y_ate_onde_a_caixinha_pode_ir(pior)
            print("%-14s %6.1fs %9d px %7.1fs   y até %d px (%.0f%% da altura)"
                  % (nome, montar.duracao(video), pior, quando, ate, ate / float(ALTURA) * 100))
    return veredito.ferramenta(fazer)


if __name__ == "__main__":
    sys.exit(main())
