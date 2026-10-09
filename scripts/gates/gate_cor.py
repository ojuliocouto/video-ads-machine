#!/usr/bin/env python3
"""GATE DA COR (W4.C, capacidade C5): mede a grade no vídeo ENTREGUE, nunca no plano.

    python3 scripts/gates/gate_cor.py <video> [--projeto projeto.json] [--planos planos.json]
                                      [--rosto x,y,largura,altura]
    exit 0 passa · 1 reprova · 2 insumo inválido (vídeo inexistente ou ilegível)

Reprova quando (limiares do plano, seção 3, C5 e C1):
  - as tags de cor do arquivo não são as três bt709 (primárias, transferência e matriz). Sem a
    tag, ou com a tag HDR/HLG que o libx264 grava sozinho, o WhatsApp e o iPhone decodificam
    avermelhado (a causa está em `footage/grade_final.py`);
  - o quadro 0 tem luminância média abaixo de 0,6x a MEDIANA da luminância média dos quadros
    (abertura mais escura que o resto do anúncio: é a janela que decide a retenção no Reels);
  - algum plano tem mediana de luminância abaixo de 20 (de 255), a não ser que o projeto declare
    a exceção `gate_cor` com motivo escrito em `excecoes` do projeto.json. A exceção vale só
    para esta regra, nunca para as tags, o quadro 0 nem o rosto;
  - a razão R/G média na caixa do rosto passa de 1,6 (rosto vermelho demais).

## Como mede

Um ffmpeg decodifica o vídeo a 4 quadros por segundo, reduzido para cerca de 270 px de largura,
e cada quadro é medido assim que chega (nada fica na memória). Luminância é a de `PIL.convert("L")`
em 0 a 255, a mesma escala do `footage/exposicao`. A mediana do plano é a mediana, entre os quadros
do plano, da mediana de pixels de cada quadro. Plano mais curto que um quadro amostrado usa o
quadro mais próximo do seu meio.

## Planos

`planos` é uma lista de `{"inicio": s, "fim": s, "rosto": [x, y, largura, altura] | ausente}` no
relógio do arquivo entregue (`planos_da_timeline` converte os segmentos da timeline.json). A caixa
do rosto é em pixels do vídeo entregue. Sem `planos`, o vídeo inteiro é UM plano, com a
`caixa_rosto` se ela foi dada (e sem caixa não há razão R/G a medir).

## Formato do resultado

`rodar` devolve um dict no formato de gate do laudo (`contratos/laudo.schema.json`): `nome`,
`etapa`, `resultado` (PASS, REPROVA ou ERRO), `saida` (0, 1 ou 2), `medido`, `limiar` e, quando não
passa, `motivo`. O `medido` traz as tags lidas, o quadro 0 e cada plano, para o laudo mostrar o
número que fez o gate decidir.
"""
import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

if __name__ == "__main__":      # rodado direto: scripts/gates/gate_cor.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageStat  # noqa: E402

from projeto import modelo  # noqa: E402

NOME = "gate_cor"
ETAPA = "depois"
REGRA_EXCECAO = "gate_cor"

LIMIAR_QUADRO0 = 0.6        # quadro 0 abaixo de 0,6x a mediana dos quadros reprova (C1)
LIMIAR_MEDIANA_PLANO = 20   # plano com mediana de luminância abaixo disso reprova (C5)
LIMIAR_RG = 1.6             # razão R/G acima disso na caixa do rosto reprova (C5)
FPS_AMOSTRA = 4             # quadros medidos por segundo
LARGURA_AMOSTRA = 270       # largura do quadro medido (a caixa do rosto acompanha a redução)
TAGS_ESPERADAS = (("primarias", "color_primaries"), ("transferencia", "color_transfer"),
                  ("matriz", "color_space"))
TIMEOUT_S = 300


class InsumoInvalido(Exception):
    """Vídeo ausente ou ilegível: não dá nem para reprovar (exit 2)."""


# --- leitura do arquivo --------------------------------------------------------------------------

def _sondar(video):
    """Largura, altura, duração e as tags de cor do primeiro fluxo de vídeo."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height,color_space,color_transfer,color_primaries:format=duration",
                            "-of", "json", str(video)], capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        raise InsumoInvalido("ffprobe ausente: instale o ffmpeg (brew install ffmpeg)")
    if r.returncode != 0:
        raise InsumoInvalido("não consegui ler %s: %s" % (video, r.stderr.strip()[-200:] or "sem detalhe"))
    try:
        d = json.loads(r.stdout)
        v = d["streams"][0]
        larg, alt = int(v["width"]), int(v["height"])
        dur = float(d["format"]["duration"])
    except (KeyError, IndexError, ValueError, TypeError):
        raise InsumoInvalido("%s não tem faixa de vídeo legível" % video)
    tags = {}
    for chave, campo in TAGS_ESPERADAS:
        valor = v.get(campo)
        tags[chave] = None if valor in (None, "", "unknown", "unspecified") else valor
    return larg, alt, dur, tags


def _quadros(video, larg, alt):
    """Gera (t, Image RGB) a FPS_AMOSTRA, já reduzida. Um quadro de cada vez."""
    pw = min(larg, LARGURA_AMOSTRA)
    ph = max(1, int(round(alt * pw / float(larg))))
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-i", str(video), "-an", "-vf",
           "fps=%d,scale=%d:%d" % (FPS_AMOSTRA, pw, ph), "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    tamanho = pw * ph * 3
    k = 0
    try:
        while True:
            buf = proc.stdout.read(tamanho)
            while buf and len(buf) < tamanho:
                mais = proc.stdout.read(tamanho - len(buf))
                if not mais:
                    break
                buf += mais
            if len(buf) < tamanho:
                break
            yield k / float(FPS_AMOSTRA), Image.frombytes("RGB", (pw, ph), buf), pw / float(larg)
            k += 1
    finally:
        proc.stdout.close()
        erro = proc.stderr.read().decode("utf-8", "replace")
        proc.stderr.close()
        rc = proc.wait()
    if rc != 0 and k == 0:
        raise InsumoInvalido("ffmpeg não decodificou %s: %s" % (video, erro.strip()[-200:]))


# --- medidas por quadro --------------------------------------------------------------------------

def _mediana_hist(hist):
    total, acum = sum(hist), 0
    for nivel, n in enumerate(hist):
        acum += n
        if acum * 2 >= total:
            return nivel
    return 0


def _razao_rg(im, caixa, escala):
    x, y, w, h = caixa
    x0, y0 = int(x * escala), int(y * escala)
    x1, y1 = max(x0 + 1, int((x + w) * escala)), max(y0 + 1, int((y + h) * escala))
    x1, y1 = min(x1, im.width), min(y1, im.height)
    if x1 <= x0 or y1 <= y0:
        return None
    r, g, _b = ImageStat.Stat(im.crop((x0, y0, x1, y1))).mean
    return r / g if g > 0 else None


def _mediana(valores):
    v = sorted(valores)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def _normalizar_planos(planos, duracao, caixa_rosto):
    if not planos:
        plano = {"inicio": 0.0, "fim": duracao}
        if caixa_rosto:
            plano["rosto"] = list(caixa_rosto)
        return [plano]
    saida = []
    for p in planos:
        if isinstance(p, dict):
            q = {"inicio": float(p["inicio"]), "fim": float(p["fim"])}
            if p.get("rosto"):
                q["rosto"] = list(p["rosto"])
        else:
            q = {"inicio": float(p[0]), "fim": float(p[1])}
        saida.append(q)
    return saida


def medir(video, planos=None, caixa_rosto=None):
    """Mede o vídeo. Devolve o dict `medido` do gate (tags, quadro 0 e planos)."""
    larg, alt, dur, tags = _sondar(video)
    planos = _normalizar_planos(planos, dur, caixa_rosto)
    por_plano = [{"lum": [], "rg": [], "meio": (p["inicio"] + p["fim"]) / 2.0, "perto": None}
                 for p in planos]
    lum_media, lum_quadro0, n = [], None, 0
    for t, im, escala in _quadros(video, larg, alt):
        gray = im.convert("L")
        media = ImageStat.Stat(gray).mean[0]
        if n == 0:
            lum_quadro0 = media
        lum_media.append(media)
        n += 1
        med = _mediana_hist(gray.histogram())
        for i, p in enumerate(planos):
            dono = por_plano[i]
            dist = abs(t - dono["meio"])
            if dist <= 0.5 / FPS_AMOSTRA + 1e-9 and (dono["perto"] is None or dist < dono["perto"][0]):
                rg = _razao_rg(im, p["rosto"], escala) if p.get("rosto") else None
                dono["perto"] = (dist, med, rg)
            if p["inicio"] <= t < p["fim"]:
                dono["lum"].append(med)
                if p.get("rosto"):
                    rg = _razao_rg(im, p["rosto"], escala)
                    if rg is not None:
                        dono["rg"].append(rg)
    if n == 0:
        raise InsumoInvalido("%s não tem quadros para medir" % video)
    med_quadros = _mediana(lum_media)
    medido_planos = []
    for i, p in enumerate(planos):
        dono = por_plano[i]
        if dono["lum"]:
            mediana, rg = _mediana(dono["lum"]), (_mediana(dono["rg"]) if dono["rg"] else None)
        else:                      # plano mais curto que um quadro amostrado: o quadro mais próximo do meio
            _d, mediana, rg = dono["perto"]
        medido_planos.append({"indice": i, "inicio": round(p["inicio"], 3), "fim": round(p["fim"], 3),
                              "mediana": round(float(mediana), 2),
                              "rg": None if rg is None else round(float(rg), 3)})
    return {
        "cor": {k: tags[k] for k, _ in TAGS_ESPERADAS},
        "quadro0": {"luminancia": round(lum_quadro0, 2), "mediana_dos_quadros": round(med_quadros, 2),
                    "razao": round(lum_quadro0 / med_quadros, 3) if med_quadros > 0 else 1.0},
        "planos": medido_planos,
        "quadros_medidos": n,
    }


# --- decisão -------------------------------------------------------------------------------------

def _motivos(medido, excecao):
    motivos = []
    faltam = [k for k, _ in TAGS_ESPERADAS if medido["cor"][k] != "bt709"]
    if faltam:
        lidas = ", ".join("%s=%s" % (k, medido["cor"][k] or "ausente") for k in faltam)
        motivos.append("tags de cor fora de bt709 (%s). Sem a tag o WhatsApp e o iPhone decodificam "
                       "avermelhado: reaplique a grade final (colorspace bt709 no filtro)" % lidas)
    q0 = medido["quadro0"]
    if q0["mediana_dos_quadros"] > 0 and q0["razao"] < LIMIAR_QUADRO0:
        motivos.append("quadro 0 escuro: luminância %.1f contra %.1f de mediana dos quadros (razão %.2f, "
                       "mínimo %.1f)" % (q0["luminancia"], q0["mediana_dos_quadros"], q0["razao"],
                                         LIMIAR_QUADRO0))
    for p in medido["planos"]:
        if p["mediana"] < LIMIAR_MEDIANA_PLANO:
            if excecao:
                p["excecao"] = True
            else:
                motivos.append("plano %d (%.2f a %.2f s) com mediana de luminância %.1f, abaixo de %d, "
                               "sem exceção declarada em excecoes (regra %s)"
                               % (p["indice"], p["inicio"], p["fim"], p["mediana"], LIMIAR_MEDIANA_PLANO,
                                  REGRA_EXCECAO))
        if p["rg"] is not None and p["rg"] > LIMIAR_RG:
            motivos.append("plano %d (%.2f a %.2f s) com razão R/G %.2f na caixa do rosto, acima de %.1f "
                           "(rosto vermelho demais)" % (p["indice"], p["inicio"], p["fim"], p["rg"], LIMIAR_RG))
    return motivos


def _gate(resultado, saida, medido=None, motivo=None, duracao=None):
    g = {"nome": NOME, "etapa": ETAPA, "resultado": resultado, "saida": saida}
    if medido is not None:
        g["medido"] = medido
    g["limiar"] = {"quadro0_razao_min": LIMIAR_QUADRO0, "mediana_plano_min": LIMIAR_MEDIANA_PLANO,
                   "razao_rg_max": LIMIAR_RG, "tags": "bt709"}
    if motivo:
        g["motivo"] = motivo
    if duracao is not None:
        g["duracao_s"] = round(duracao, 2)
    return g


def rodar(video, projeto=None, planos=None, caixa_rosto=None):
    """Confere a cor de `video`. `projeto` é o dict do projeto.json (só `excecoes` é lido).
    Devolve o gate no formato do laudo; nunca levanta por insumo ruim (vira ERRO, saída 2)."""
    t0 = time.time()
    video = Path(video)
    if not video.is_file():
        return _gate("ERRO", 2, motivo="vídeo não existe: %s" % video)
    try:
        medido = medir(video, planos=planos, caixa_rosto=caixa_rosto)
    except InsumoInvalido as e:
        return _gate("ERRO", 2, motivo=str(e))
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError) as e:
        return _gate("ERRO", 2, motivo="falha ao medir %s: %s" % (video, e))
    excecao = modelo.motivo_excecao(projeto, REGRA_EXCECAO) if projeto else None
    if excecao:
        medido["excecao"] = excecao
    motivos = _motivos(medido, excecao)
    dur = time.time() - t0
    if motivos:
        return _gate("REPROVA", 1, medido, "; ".join(motivos), dur)
    return _gate("PASS", 0, medido, duracao=dur)


def rodar_projeto(pj, caixa_rosto=None, planos=None):
    """Confere o `entrega/final_9x16.mp4` do projeto, com as exceções do projeto.json.
    `pj` é o `projeto.pastas.PastasProjeto`."""
    try:
        projeto = modelo.carregar(pj.projeto_json)
    except FileNotFoundError:
        return _gate("ERRO", 2, motivo="projeto.json não existe em %s: crie o projeto antes (vam novo)" % pj.raiz)
    except modelo.ContratoInvalido as e:
        return _gate("ERRO", 2, motivo=str(e))
    return rodar(pj.final_9x16, projeto=projeto, planos=planos, caixa_rosto=caixa_rosto)


def _detectar_rosto(video, t):
    """A maior caixa de rosto [x, y, largura, altura] (pixels do vídeo) no quadro `t`, pelo Haar do OpenCV; None se
    não achar ou se o OpenCV não estiver instalado."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-ss", "%.3f" % max(0.0, t), "-i", str(video),
                            "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
        if r.returncode != 0 or not r.stdout:
            return None
        img = cv2.imdecode(np.frombuffer(r.stdout, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None
        casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        achados = casc.detectMultiScale(img, 1.1, 5, minSize=(120, 120))
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if not len(achados):
        return None
    x, y, w, h = max(achados, key=lambda b: b[2] * b[3])
    return int(x), int(y), int(w), int(h)


def caixa_rosto_entregue(video, timeline):
    """A caixa do rosto MEDIDA no arquivo entregue (W5.X, pendência c): a mediana das caixas achadas no meio de cada
    plano de apresentador. Sem ela o C5 (R/G na caixa do rosto) nunca era medido no montar. None se não achar."""
    a0 = timeline["relogio"]["a0"]
    acel = timeline["relogio"]["aceleracao"]
    caixas = []
    for sg in timeline["segmentos"]:
        if sg["tipo"] != "apresentador":
            continue
        c = _detectar_rosto(video, ((sg["s"] + sg["e"]) / 2.0 - a0) / acel)
        if c:
            caixas.append(c)
    if not caixas:
        return None
    return [int(statistics.median(c[i] for c in caixas)) for i in range(4)]


def planos_da_timeline(timeline, rosto=None):
    """Planos no relógio do arquivo entregue, a partir dos `segmentos` da timeline.json.
    O relógio da timeline é o da footage a 1x: o entregue converte com (t - a0) / aceleracao.
    O plano de apresentador leva a `rosto` (caixa em pixels do entregue); o insert não."""
    a0 = timeline["relogio"]["a0"]
    acel = timeline["relogio"]["aceleracao"]
    planos = []
    for s in timeline["segmentos"]:
        p = {"inicio": round((s["s"] - a0) / acel, 6), "fim": round((s["e"] - a0) / acel, 6)}
        if rosto and s["tipo"] == "apresentador":
            p["rosto"] = list(rosto)
        planos.append(p)
    return planos


# --- linha de comando ------------------------------------------------------------------------------

def _caixa(texto):
    try:
        x, y, w, h = [int(v) for v in texto.split(",")]
    except ValueError:
        raise argparse.ArgumentTypeError("use x,y,largura,altura em pixels (por exemplo 400,300,280,320)")
    return (x, y, w, h)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Confere a cor do vídeo entregue (tags bt709, abertura, planos escuros, rosto).")
    ap.add_argument("video")
    ap.add_argument("--projeto", help="projeto.json (lê as exceções declaradas)")
    ap.add_argument("--planos", help="JSON com a lista de planos {inicio, fim, rosto?} no relógio do entregue")
    ap.add_argument("--rosto", type=_caixa, help="caixa do rosto x,y,largura,altura para o vídeo inteiro")
    args = ap.parse_args(argv)
    projeto, planos = None, None
    try:
        if args.projeto:
            projeto = modelo.carregar(args.projeto)
        if args.planos:
            planos = json.loads(Path(args.planos).read_text(encoding="utf-8"))
    except (OSError, ValueError, modelo.ContratoInvalido) as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        return 2
    g = rodar(args.video, projeto=projeto, planos=planos, caixa_rosto=args.rosto)
    if g["resultado"] == "PASS":
        q0 = g["medido"]["quadro0"]
        print("PASSA: tags bt709, quadro 0 em %.2fx a mediana, %d plano(s) acima de %d de luminância"
              % (q0["razao"], len(g["medido"]["planos"]), LIMIAR_MEDIANA_PLANO))
    elif g["resultado"] == "REPROVA":
        print("REPROVA: %s" % g["motivo"])
    else:
        print("ERRO de insumo: %s" % g["motivo"], file=sys.stderr)
    return g["saida"]


if __name__ == "__main__":
    sys.exit(main())
