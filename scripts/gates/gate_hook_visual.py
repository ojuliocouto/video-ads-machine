#!/usr/bin/env python3
"""GATE DO GANCHO VISUAL (W4.A, capacidade C1): os 3 primeiros segundos, medidos no render.

    python3 scripts/gates/gate_hook_visual.py <video> --timeline render/timeline.json --overlay render/overlay.mov
    exit 0 passa · 1 reprova · 2 insumo inválido (vídeo, overlay ou timeline ausente ou ilegível)

COMPLEMENTA o `gate-ad.checar_hook` (que segue dono de "1º texto até 1,0 s" e de "até 1,0 s sem texto em
0 a 3 s", medidos a cada 0,25 s). Este mede mais fino, a cada 0,05 s, e acrescenta o que ele não olha.
Reprova quando:
  - o 1º texto aparece depois de 0,25 s (o texto cheio nasce no quadro 0; o gancho que abre mudo perde o
    espectador antes de ler a promessa) ou não aparece nunca nos 3 s;
  - passa de 1,0 s o tempo SEM texto dentro dos 3 s;
  - não há nenhum evento visual (corte confirmado, punch ou insert) em 0 a 3 s: texto sobre imagem parada
    é slide, não gancho;
  - o quadro 0 tem luminância média abaixo de 0,6x a MEDIANA dos quadros (a abertura escura: medida em
    57% mais escura que o resto do anúncio; é a janela que decide a retenção no Reels).

## Como mede

O texto é medido no OVERLAY com alfa (todo pixel opaco é texto nosso), pelo critério do gate-ad: mais de
0,2% do quadro com alfa acima de 190. Sem o overlay não há como separar texto de imagem, e o gate recusa
(ERRO) em vez de adivinhar por luminância. O instante `t` do entregue está no instante `t x aceleração + a0`
do overlay, que roda na velocidade da footage. A luminância é a média do quadro em cinza.

Os eventos vêm da timeline (insert que entra, punch) e o corte só conta se o plano e a imagem concordam
(`medir_ritmo.cortes_confirmados`, a mesma conta do medidor de ritmo): corte que o plano pediu e a imagem
não entregou não é gancho.

Todos os tempos da timeline estão no relógio da footage a 1x; o entregue é (t - a0) / aceleração.

## Formato do resultado

`rodar` devolve um dict no formato de gate do laudo (`contratos/laudo.schema.json`), como o `gate_camera`.
"""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

if __name__ == "__main__":      # rodado direto: scripts/gates/gate_hook_visual.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinema import camera  # noqa: E402

NOME = "gate_hook_visual"
ETAPA = "depois"

JANELA_S = 3.0                   # a janela do gancho, no entregue
PASSO_S = 0.05                   # amostragem do texto (o gate-ad usa 0,25)
PRIMEIRO_TEXTO_MAX_S = 0.25
SEM_TEXTO_MAX_S = 1.0
QUADRO0_RAZAO_MIN = 0.6
ALFA_MIN = 190                   # pixel opaco, o critério do gate-ad
TEXTO_AREA_MIN = 0.002           # fração do quadro com alfa acima de ALFA_MIN
LARGURA_AMOSTRA = 270
LUM_FPS = 4                      # quadros por segundo para a mediana da luminância
FORMATOS_COM_ALFA = ("yuva", "rgba", "bgra", "argb", "abgr", "gbrap", "ya8", "ya16", "pal8")
_EPS = 1e-9


class InsumoInvalido(Exception):
    """Vídeo, overlay ou timeline ausente ou ilegível: não dá nem para reprovar (exit 2)."""


# --- leitura dos arquivos ------------------------------------------------------------------------------------

def _ffprobe(caminho, entradas, fluxo=True):
    cmd = ["ffprobe", "-v", "error"]
    if fluxo:
        cmd += ["-select_streams", "v:0"]
    cmd += ["-show_entries", entradas, "-of", "json", str(caminho)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        raise InsumoInvalido("ffprobe ausente: instale o ffmpeg (brew install ffmpeg)")
    if r.returncode != 0:
        raise InsumoInvalido("não consegui ler %s: %s" % (caminho, r.stderr.strip()[-200:] or "sem detalhe"))
    try:
        return json.loads(r.stdout)
    except ValueError:
        raise InsumoInvalido("%s não é um arquivo de mídia legível" % caminho)


def _dimensoes(caminho):
    d = _ffprobe(caminho, "stream=width,height,pix_fmt")
    try:
        v = d["streams"][0]
        return int(v["width"]), int(v["height"]), str(v.get("pix_fmt", ""))
    except (KeyError, IndexError, ValueError, TypeError):
        raise InsumoInvalido("%s não tem faixa de vídeo legível" % caminho)


def _duracao(caminho):
    d = _ffprobe(caminho, "format=duration", fluxo=False)
    try:
        return float(d["format"]["duration"])
    except (KeyError, ValueError, TypeError):
        raise InsumoInvalido("não consegui medir a duração de %s" % caminho)


def _quadros_raw(cmd, tamanho):
    """Gera os bytes de cada quadro de um rawvideo. Levanta OSError se o ffmpeg falhar sem entregar nada."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    n = 0
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
            n += 1
            yield buf
    finally:
        proc.stdout.close()
        erro = proc.stderr.read().decode("utf-8", "replace")
        proc.stderr.close()
        rc = proc.wait()
    if rc != 0 and n == 0:
        raise OSError("ffmpeg não decodificou: %s" % erro.strip()[-200:])


def _texto_por_instante(overlay, rel, janela_s):
    """Lista de `(t_entregue, tem_texto)` a cada PASSO_S em [0, janela_s)."""
    import numpy as np
    larg, alt, pix = _dimensoes(overlay)
    if not any(f in pix for f in FORMATOS_COM_ALFA):
        raise InsumoInvalido("o overlay %s não tem canal alfa (pix_fmt %s): sem ele não há como separar o texto "
                             "da imagem" % (overlay, pix or "desconhecido"))
    acel, a0 = float(rel["aceleracao"]), float(rel.get("a0", 0.0))
    pw = min(larg, LARGURA_AMOSTRA)
    ph = max(2, int(round(alt * pw / float(larg))) // 2 * 2)
    n = int(round(janela_s / PASSO_S))
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-ss", "%.6f" % a0, "-t", "%.6f" % (janela_s * acel + PASSO_S * acel),
           "-i", str(overlay), "-an", "-vf", "fps=%.6f,scale=%d:%d" % (1.0 / (PASSO_S * acel), pw, ph),
           "-f", "rawvideo", "-pix_fmt", "rgba", "pipe:1"]
    tem = []
    for buf in _quadros_raw(cmd, pw * ph * 4):
        if len(tem) >= n:
            break
        alfa = np.frombuffer(buf, dtype=np.uint8).reshape(ph, pw, 4)[:, :, 3]
        tem.append(float((alfa > ALFA_MIN).mean()) > TEXTO_AREA_MIN)
    tem += [False] * (n - len(tem))                  # overlay mais curto que a janela: sem texto o resto
    return [(round(i * PASSO_S, 6), tem[i]) for i in range(n)]


def _luminancias(video):
    """Luminância média (0 a 255) de cada quadro a LUM_FPS; o primeiro é o quadro 0."""
    import numpy as np
    larg, alt, _ = _dimensoes(video)
    pw = min(larg, 54)
    ph = max(2, int(round(alt * pw / float(larg))) // 2 * 2)
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-i", str(video), "-an", "-vf",
           "fps=%d,scale=%d:%d,format=gray" % (LUM_FPS, pw, ph), "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]
    return [float(np.frombuffer(b, dtype=np.uint8).mean()) for b in _quadros_raw(cmd, pw * ph)]


def _mediana(valores):
    v = sorted(valores)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def _cortes_confirmados(video, tl):
    """Instantes ENTREGUES dos cortes do plano que a imagem confirma (a conta do medidor de ritmo)."""
    import medir_ritmo
    rel = tl["relogio"]
    with tempfile.TemporaryDirectory() as td:
        plano = Path(td) / "plano.json"
        plano.write_text(json.dumps({"segs": [{"s": sg["s"]} for sg in tl["segmentos"]]}), encoding="utf-8")
        return medir_ritmo.cortes_confirmados(str(video), str(plano), accel=float(rel["aceleracao"]),
                                              a0=float(rel.get("a0", 0.0)))


# --- eventos visuais -------------------------------------------------------------------------------------------

def eventos_visuais(tl, cortes_confirmados=(), janela_s=JANELA_S):
    """Os eventos visuais de 0 a `janela_s` (entregue), em ordem de tempo: insert que está na tela (ou entra),
    punch e os cortes que a imagem confirmou. Os tempos saem em segundos ENTREGUES."""
    rel = tl["relogio"]
    saida = []
    for sg in tl["segmentos"]:
        if sg["tipo"] != "insert":
            continue
        s_d, e_d = camera.para_entregue(sg["s"], rel), camera.para_entregue(sg["e"], rel)
        if e_d > _EPS and s_d <= janela_s + _EPS:
            saida.append({"tipo": "insert", "t": round(max(0.0, s_d), 3)})
    for ev in tl.get("camera") or []:
        if ev.get("tipo") == "punch":
            t_d = camera.para_entregue(ev["t"], rel)
            if -_EPS <= t_d <= janela_s + _EPS:
                saida.append({"tipo": "punch", "t": round(t_d, 3)})
    for t in cortes_confirmados or ():
        if _EPS < t <= janela_s + _EPS:
            saida.append({"tipo": "corte", "t": round(float(t), 3)})
    return sorted(saida, key=lambda e: (e["t"], e["tipo"]))


# --- medição e decisão -------------------------------------------------------------------------------------------

def medir(video, tl, overlay, cortes_confirmados=None):
    rel = tl["relogio"]
    dur = _duracao(video)
    janela = min(JANELA_S, dur)
    texto = _texto_por_instante(overlay, rel, janela)
    primeiro = next((t for t, tem in texto if tem), None)
    sem = round(sum(PASSO_S for _t, tem in texto if not tem), 3)

    lum = _luminancias(video)
    if not lum:
        raise InsumoInvalido("o vídeo %s não tem quadros para medir" % video)
    mediana = _mediana(lum)
    razao = lum[0] / mediana if mediana > 0 else 1.0

    if cortes_confirmados is None:
        cortes_confirmados = _cortes_confirmados(video, tl)
    elif callable(cortes_confirmados):
        cortes_confirmados = cortes_confirmados(video, tl)
    eventos = eventos_visuais(tl, cortes_confirmados, janela)
    return {"janela_s": round(janela, 3), "primeiro_texto_s": None if primeiro is None else round(primeiro, 3),
            "sem_texto_s": sem,
            "quadro0": {"luminancia": round(lum[0], 2), "mediana_dos_quadros": round(mediana, 2),
                        "razao": round(razao, 3)},
            "eventos": eventos}


def _motivos(m):
    motivos = []
    p = m["primeiro_texto_s"]
    if p is None:
        motivos.append("nenhum texto nos primeiros %.0f s: o texto cheio tem que estar no quadro 0" % JANELA_S)
    elif p > PRIMEIRO_TEXTO_MAX_S + _EPS:
        motivos.append("primeiro texto em %.2f s, depois do limite de %.2f s: o texto cheio nasce no quadro 0"
                       % (p, PRIMEIRO_TEXTO_MAX_S))
    if m["sem_texto_s"] > SEM_TEXTO_MAX_S + _EPS:
        motivos.append("%.2f s sem texto em 0 a %.0f s, acima do limite de %.1f s"
                       % (m["sem_texto_s"], JANELA_S, SEM_TEXTO_MAX_S))
    if not m["eventos"]:
        motivos.append("nenhum evento visual (corte confirmado, punch ou insert) em 0 a %.0f s: texto sobre imagem "
                       "parada é slide, não gancho" % JANELA_S)
    q = m["quadro0"]
    if q["mediana_dos_quadros"] > 0 and q["razao"] < QUADRO0_RAZAO_MIN - _EPS:
        motivos.append("quadro 0 escuro: luminância %.1f contra %.1f de mediana dos quadros (%.2fx, mínimo %.1fx)"
                       % (q["luminancia"], q["mediana_dos_quadros"], q["razao"], QUADRO0_RAZAO_MIN))
    return motivos


def _gate(resultado, saida, etapa, medido=None, motivo=None, duracao=None):
    g = {"nome": NOME, "etapa": etapa, "resultado": resultado, "saida": saida}
    if medido is not None:
        g["medido"] = medido
    g["limiar"] = {"primeiro_texto_max_s": PRIMEIRO_TEXTO_MAX_S, "sem_texto_max_s": SEM_TEXTO_MAX_S,
                   "janela_s": JANELA_S, "quadro0_razao_min": QUADRO0_RAZAO_MIN}
    if motivo:
        g["motivo"] = motivo
    if duracao is not None:
        g["duracao_s"] = round(duracao, 2)
    return g


def rodar(video, timeline, overlay=None, projeto=None, *, cortes_confirmados=None, etapa=ETAPA):
    """Confere o gancho de `video` com o `overlay` (MOV com alfa) e a `timeline` (dict). `cortes_confirmados`:
    lista de instantes entregues, ou função `(video, timeline) -> lista`; o padrão mede na imagem. `projeto` é
    aceito por simetria: o C1 não tem exceção. Devolve o gate no formato do laudo; insumo ruim vira ERRO (2)."""
    t0 = time.time()
    try:
        if not Path(str(video)).is_file():
            raise InsumoInvalido("o vídeo não existe: %s" % video)
        if overlay is None:
            raise InsumoInvalido("passe o overlay (render/overlay.mov, o MOV com alfa): é nele que o texto se mede")
        if not Path(str(overlay)).is_file():
            raise InsumoInvalido("o overlay não existe: %s" % overlay)
        if not isinstance(timeline, dict):
            raise InsumoInvalido("a timeline não é um objeto JSON")
        for campo in ("relogio", "segmentos"):
            if campo not in timeline:
                raise InsumoInvalido("a timeline não tem o campo %r (use o render/timeline.json do projeto)" % campo)
        if "aceleracao" not in timeline["relogio"]:
            raise InsumoInvalido("a timeline não tem relogio.aceleracao")
        medido = medir(video, timeline, overlay, cortes_confirmados)
    except InsumoInvalido as e:
        return _gate("ERRO", 2, etapa, motivo=str(e))
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, ImportError) as e:
        return _gate("ERRO", 2, etapa, motivo="falha ao medir %s: %s" % (video, e))
    motivos = _motivos(medido)
    dur = time.time() - t0
    if motivos:
        return _gate("REPROVA", 1, etapa, medido, "; ".join(motivos), dur)
    return _gate("PASS", 0, etapa, medido, duracao=dur)


# --- linha de comando --------------------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="Confere o gancho visual dos 3 primeiros segundos do vídeo entregue.")
    ap.add_argument("video")
    ap.add_argument("--timeline", required=True, help="render/timeline.json do projeto")
    ap.add_argument("--overlay", required=True, help="o MOV com alfa do texto (render/overlay.mov)")
    args = ap.parse_args(argv)
    try:
        tl = json.loads(Path(args.timeline).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        return 2
    g = rodar(args.video, tl, overlay=args.overlay)
    if g["resultado"] == "PASS":
        m = g["medido"]
        print("PASSA: texto no quadro 0 (primeiro em %.2f s), %.2f s sem texto, quadro 0 em %.2fx a mediana, "
              "evento visual: %s" % (m["primeiro_texto_s"], m["sem_texto_s"], m["quadro0"]["razao"],
                                      ", ".join(e["tipo"] for e in m["eventos"])))
    elif g["resultado"] == "REPROVA":
        print("REPROVA: %s" % g["motivo"])
    else:
        print("ERRO de insumo: %s" % g["motivo"], file=sys.stderr)
    return g["saida"]


if __name__ == "__main__":
    sys.exit(main())
