"""Luz do take real: a luminância MEDIDA vira brightness e contraste, e o HDR do celular vira SDR.

Duas coisas que o take de câmera pede e o avatar nunca pediu, as duas medidas, nenhuma no olho.

## 1. A luz do one-shot

Sala escura (o evento) pede luz, sala clara não. O método do one-shot de origem media a luminância e
comparava lado a lado antes de aceitar: `eq=brightness=0.16:contrast=1.096` num take de luminância
média 70. A conta que reproduz aquele número, e vale para qualquer take:

    brilho   = (ALVO_LUMA - média) / 255, de 0 até BRILHO_MAX; média acima do alvo não mexe
    contraste = 1 + CONTRASTE_POR_BRILHO x brilho

Com ALVO_LUMA = 111: média 70 dá brilho 0,161 e contraste 1,096. Brilho puxado até o teto (muito
escuro) avisa que limitou: a luz do ambiente não se conserta só na pós.

  calcular(média)        dict {medida, alvo, brightness, contrast, limitado}
  filtro(luz)            "eq=brightness=...:contrast=..." ou "" quando a imagem já está clara
  medir(video, janela)   luminância média (0 a 255) dos quadros amostrados, já recortados na janela

## 2. HDR (o iPhone grava em HLG)

O vídeo de celular em HDR chega bt2020 com a curva HLG (`arib-std-b67`) de 10 bits. Reetiquetar isso como
bt709 (o que o `colorspace=all=bt709:iall=bt709` da grade faz) mantém o pixel e troca só a etiqueta: a matriz
de cor sai errada e o contraste fica chapado. A conversão certa passa pelo pixel:

    decodifica em bt2020 -> RGB 16 bits -> HLG para SDR (3D LUT) -> codifica em bt709 -> etiqueta bt709

O ffmpeg desta máquina não traz zscale nem libplacebo, então a curva vai numa LUT 3D `.cube` gerada aqui,
determinística (`gerar_lut`). A conta (BT.2100 e BT.2408): curva inversa do HLG, OOTF de gama 1,2 (pico
nominal de 1000 nits), branco de referência SDR em 203 nits, primárias bt2020 para bt709, joelho suave nas
altas luzes (sobre a luminância, para não virar a cor) e a curva de transferência do bt709. PQ (HDR10)
entra pela mesma saída, com a curva EOTF do ST 2084.

  eh_hdr(transferencia)                       True para HLG e PQ
  transferencia_do_video(arquivo)             a tag de transferência do primeiro vídeo
  hlg_para_sdr(rgb) / pq_para_sdr(rgb)        a conta, em numpy, de R'G'B' 0..1 para bt709 codificado 0..1
  gerar_lut(destino, tamanho, transferencia)  escreve a LUT .cube
  cadeia_hdr_para_sdr(lut)                    o trecho do filtro do ffmpeg, até a etiqueta bt709
"""
import subprocess
from pathlib import Path

import numpy as np

from gravado.veredito import InsumoInvalido

# --- a luz ------------------------------------------------------------------------------------------
ALVO_LUMA = 111.0               # (111 - 70) / 255 = 0,161: o brilho medido do one-shot de origem
CONTRASTE_POR_BRILHO = 0.6      # 1 + 0,6 x 0,161 = 1,096: o contraste medido do mesmo one-shot
BRILHO_MAX = 0.22               # além disso o `eq` estoura as altas luzes: avisa que limitou
AMOSTRAS = 6

# --- o HDR ------------------------------------------------------------------------------------------
HLG = "arib-std-b67"
PQ = "smpte2084"
TRANSFERENCIAS_HDR = (HLG, PQ)
_A, _B, _C = 0.17883277, 0.28466892, 0.55991073        # constantes do HLG (BT.2100)
GAMA_SISTEMA = 1.2                                      # OOTF do HLG para 1000 nits
BRANCO_SDR = 203.0 / 1000.0                             # branco de referência (BT.2408) no pico de 1000 nits
JOELHO = 0.75                                           # a partir daqui as altas luzes dobram suave para 1,0
_M2020_709 = np.array([[1.6605, -0.5876, -0.0728],
                       [-0.1246, 1.1329, -0.0083],
                       [-0.0182, -0.1006, 1.1187]])
_M2020_709 = _M2020_709 / _M2020_709.sum(axis=1, keepdims=True)    # linhas somam 1: neutro continua neutro
_Y2020 = np.array([0.2627, 0.6780, 0.0593])
_Y709 = np.array([0.2126, 0.7152, 0.0722])
LUT_TAMANHO = 65          # medido: com 33 pontos a interpolação erra até 2,4 códigos nas cores saturadas; com 65, 0,2


# --- luz medida -------------------------------------------------------------------------------------

def calcular(luma_media, alvo=ALVO_LUMA):
    """Brilho e contraste do `eq` para uma imagem de luminância média `luma_media` (0 a 255)."""
    bruto = max(0.0, float(alvo) - float(luma_media)) / 255.0
    brilho = min(bruto, BRILHO_MAX)
    contraste = 1.0 + CONTRASTE_POR_BRILHO * brilho
    return {"medida": round(float(luma_media), 1), "alvo": float(alvo), "brightness": round(brilho, 3),
            "contrast": round(contraste, 3), "limitado": bruto > BRILHO_MAX + 1e-12}


def filtro(luz):
    """O filtro `eq` da luz, ou "" quando não há o que corrigir."""
    if not luz or not luz.get("brightness"):
        return ""
    return "eq=brightness=%s:contrast=%s" % (luz["brightness"], luz["contrast"])


def _quadro_cinza(video, t, largura, altura, filtro_antes=""):
    vf = ",".join(x for x in (filtro_antes, "format=gray") if x)
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-ss", "%.3f" % t, "-i", str(video), "-frames:v", "1",
           "-vf", vf, "-f", "rawvideo", "-"]
    try:
        r = subprocess.run(cmd, capture_output=True)
    except FileNotFoundError:
        raise InsumoInvalido("ffmpeg não encontrado: instale com `brew install ffmpeg`")
    if r.returncode != 0 or len(r.stdout) != largura * altura:
        raise InsumoInvalido("não consegui amostrar o quadro de %.2fs de %s: %s"
                             % (t, video, r.stderr.decode("utf-8", "replace").strip()[-200:]))
    return np.frombuffer(r.stdout, dtype=np.uint8).reshape(altura, largura)


def medir(video, janela, amostras=AMOSTRAS, medidor=None, filtro_antes=""):
    """Luminância média (0 a 255) dos `amostras` quadros do take, recortados na `janela` (a de `enquadrar`).

    `filtro_antes`: filtros que rodam ANTES do recorte (a conversão HDR, para medir a luz que vai ao ar).
    `medidor(quadro)` troca a medida (os testes injetam; o padrão é a média do quadro)."""
    from gravado.nucleo import energia
    from oneshot import enquadrar
    medidor = medidor or (lambda quadro: float(quadro.mean()))
    recorte = "crop=%d:%d:%d:%d" % (janela["w"], janela["h"], janela["x"], janela["y"])
    cadeia = ",".join(x for x in (filtro_antes, recorte) if x)
    dur = energia.duracao_s(video)
    valores = [medidor(_quadro_cinza(video, t, janela["w"], janela["h"], cadeia))
               for t in enquadrar.instantes_de_amostra(dur, amostras)]
    return float(sum(valores) / len(valores))


# --- HDR --------------------------------------------------------------------------------------------

def eh_hdr(transferencia):
    return transferencia in TRANSFERENCIAS_HDR


def transferencia_do_video(caminho):
    """A tag `color_transfer` do primeiro vídeo (ou None se não tem)."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=color_transfer", "-of", "default=nw=1:nk=1", str(caminho)],
                           capture_output=True, text=True)
    except FileNotFoundError:
        raise InsumoInvalido("ffprobe não encontrado: instale o ffmpeg com `brew install ffmpeg`")
    if r.returncode != 0:
        raise InsumoInvalido("não consegui ler %s: %s" % (caminho, r.stderr.strip()[-200:]))
    valor = r.stdout.strip()
    return valor if valor and valor != "unknown" else None


def _hlg_inversa(e):
    e = np.clip(e, 0.0, 1.0)
    return np.where(e <= 0.5, e * e / 3.0, (np.exp((e - _C) / _A) + _B) / 12.0)


def _pq_eotf(e):
    m1, m2 = 2610.0 / 16384, 2523.0 / 4096 * 128
    c1, c2, c3 = 3424.0 / 4096, 2413.0 / 4096 * 32, 2392.0 / 4096 * 32
    p = np.power(np.clip(e, 0.0, 1.0), 1.0 / m2)
    return np.power(np.maximum(p - c1, 0.0) / (c2 - c3 * p), 1.0 / m1)       # 1,0 = 10000 nits


def _oetf_bt709(v):
    v = np.clip(v, 0.0, 1.0)
    return np.where(v < 0.018, 4.5 * v, 1.099 * np.power(v, 0.45) - 0.099)


def _saida_sdr(relativo_2020):
    """Luz linear em bt2020 (1,0 = branco SDR) -> bt709 codificado 0..1, com joelho nas altas luzes."""
    rgb = relativo_2020 @ _M2020_709.T
    rgb = np.maximum(rgb, 0.0)
    y = rgb @ _Y709
    folga = 1.0 - JOELHO
    y_novo = np.where(y <= JOELHO, y, JOELHO + folga * (1.0 - np.exp(-(y - JOELHO) / folga)))
    escala = np.where(y > 1e-9, y_novo / np.maximum(y, 1e-9), 1.0)
    return _oetf_bt709(rgb * escala[:, None])


def hlg_para_sdr(rgb):
    """R'G'B' em HLG (0..1, shape Nx3, primárias bt2020) -> R'G'B' em bt709 (0..1)."""
    e = _hlg_inversa(np.asarray(rgb, dtype=np.float64).reshape(-1, 3))
    ys = e @ _Y2020
    exibida = e * np.power(ys, GAMA_SISTEMA - 1.0)[:, None]             # OOTF: 1,0 = 1000 nits
    return _saida_sdr(exibida / BRANCO_SDR)


def pq_para_sdr(rgb):
    """R'G'B' em PQ (0..1, shape Nx3, primárias bt2020) -> R'G'B' em bt709 (0..1)."""
    nits = _pq_eotf(np.asarray(rgb, dtype=np.float64).reshape(-1, 3)) * 10000.0
    return _saida_sdr(nits / (BRANCO_SDR * 1000.0))


def _conta_da(transferencia):
    if transferencia == HLG:
        return hlg_para_sdr
    if transferencia == PQ:
        return pq_para_sdr
    raise InsumoInvalido("transferência HDR desconhecida: %r (sei converter %s e %s)" % (transferencia, HLG, PQ))


def gerar_lut(destino, tamanho=LUT_TAMANHO, transferencia=HLG):
    """Escreve a LUT 3D .cube (R varia mais rápido) da conversão HDR -> SDR. Mesma entrada, mesmos bytes."""
    conta = _conta_da(transferencia)
    n = int(tamanho)
    eixo = np.linspace(0.0, 1.0, n)
    b, g, r = np.meshgrid(eixo, eixo, eixo, indexing="ij")             # índices [b][g][r]: r é o último (mais rápido)
    grade = np.stack([r.ravel(), g.ravel(), b.ravel()], axis=1)
    saida = np.clip(conta(grade), 0.0, 1.0)
    linhas = ['# conversão %s -> SDR bt709 (oneshot/luz.py)' % transferencia, 'TITLE "%s para sdr"' % transferencia,
              "LUT_3D_SIZE %d" % n, "DOMAIN_MIN 0.0 0.0 0.0", "DOMAIN_MAX 1.0 1.0 1.0"]
    linhas += ["%.6f %.6f %.6f" % (x, y, z) for x, y, z in saida]
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return destino


def _escapar(caminho):
    texto = str(caminho)
    for c in ("\\", ":", ",", "'", "[", "]", ";", "="):
        texto = texto.replace(c, "\\" + c)
    return texto


def cadeia_hdr_para_sdr(lut):
    """O trecho do filtro do ffmpeg que leva um vídeo HDR (HLG ou PQ, bt2020) para SDR bt709, até a etiqueta.

    O vídeo entra em qualquer formato de 10 bits e sai em yuv420p com as tags bt709 (a grade, que vem a
    seguir, não reetiqueta nada que já esteja certo)."""
    return ",".join([
        "scale=in_color_matrix=bt2020:in_range=tv:out_range=pc",
        "format=gbrp16le",
        "lut3d=file=%s:interp=tetrahedral" % _escapar(lut),
        "scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int",
        "format=yuv420p",
        "setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv"])
