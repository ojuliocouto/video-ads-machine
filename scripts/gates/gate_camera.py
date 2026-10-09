#!/usr/bin/env python3
"""GATE DA CÂMERA (W4.A, capacidade C3): mede o movimento no vídeo ENTREGUE, nunca no plano.

    python3 scripts/gates/gate_camera.py <video> --timeline render/timeline.json
    exit 0 passa · 1 reprova · 2 insumo inválido (vídeo ou timeline ilegível, imagem sem textura para medir)

Reprova quando (limiares do plano, seção 3, C3):
  - a escala da imagem (a "caixa do rosto" do plano, ver abaixo) varia menos de 8% num plano de avatar de
    2 s ou mais, entregues: a câmera está parada, e declarar `zoom` na timeline não muda isso, porque o gate
    mede a IMAGEM;
  - um punch não cresce +15% de escala medida (o pedido é 22%: a margem cobre o ruído da medida e o zoom
    contínuo que segue andando por baixo);
  - passam mais de 20 s sem movimento de câmera;
  - um punch declarado cai em insert ou em janela de split (o C3: nunca punch em insert, split ou
    lettering de split).

## O que é medido: a ESCALA DA IMAGEM, não a caixa do rosto

O plano diz "caixa do rosto varia menos de 8%". Medir a caixa do rosto (Haar do OpenCV) foi a primeira versão
deste gate, e a medição em avatar real a derrubou: num avatar HeyGen PARADO, de 18 s, a altura da caixa
balança 12% sozinha (a pessoa se inclina e o detector anda em degraus de escala de 10%). A tendência dessas
janelas deu mediana de 4% e p90 de 8 a 12%: com 8% de limiar, um anúncio SEM zoom passava em 12 a 23% das
janelas, e um anúncio correto, com dezenas de planos, reprovava quase sempre.

A escala da imagem sai de pontos de textura seguidos entre quadros vizinhos (Lucas-Kanade) e de uma
similaridade ajustada por RANSAC (`escala_entre`): é a mesma "câmera" que o plano quer ver, sem o balanço da
pessoa. No mesmo avatar real e parado o ruído caiu para p90 de 1,6% (2,3% com a grade final por cima); o zoom
de 16% mediu 16 a 17% e o punch de 22% mediu 23 a 24%.

## Como mede

O vídeo é decodificado UMA vez a 12 quadros por segundo, em cinza, a 270 px de largura. Cada plano de avatar
é medido sem 0,25 s em cada ponta: a transição do corte (volta macia de até 0,20 s) mistura dois quadros e
não é câmera.

  variação do plano  exp(|inclinação| x duração) - 1, do logaritmo da escala cumulativa (a partir do 1º
                     quadro do plano) contra o tempo (`camera.variacao_da_escala`). Em avatar real: zoom de 16%
                     mede 14,7% (16,0% com a grade final), parado mede 1,5% (1,1%).
                     PLANO COM PUNCH É DISPENSADO desta regra se o punch medido passa: o rastreador acumula erro
                     na subida e na volta do punch (22% em 3 quadros), e o mesmo plano real deu de 6,4% a 20,7%
                     conforme o arquivo e o método (sem a janela do punch, de 9,3% a 16,1%). O punch medido já prova
                     que o filtro de câmera rodou naquele plano; o zoom contínuo continua cobrado em todos os outros.
  ganho do punch     mediana da escala em [fim da subida + 0,03 s, + 0,30 s] sobre a mediana em
                     [t - 0,30 s, t - 0,03 s], menos 1 (`camera.ganho_do_punch`), as duas a partir do mesmo
                     quadro de referência, atravessando a subida do punch.
  movimento          plano de avatar: a janela inteira, SE a variação medida passa dos 8% (declarar não
                     basta). Insert, respiro e planos de avatar curtos demais para medir: o que a timeline
                     declara. Punch: a janela dele, se o ganho medido passa dos 15%. O maior vão sem nenhuma
                     dessas janelas é o "parado" (`camera.maior_trecho_parado`).

Todos os tempos da timeline estão no relógio da footage a 1x; o entregue é (t - a0) / aceleração.

## Formato do resultado

`rodar` devolve um dict no formato de gate do laudo (`contratos/laudo.schema.json`): `nome`, `etapa`,
`resultado` (PASS, REPROVA ou ERRO), `saida` (0, 1 ou 2), `medido`, `limiar` e, quando não passa, `motivo`.
O `medido` traz cada plano (variação), cada punch (ganho) e o maior trecho parado, para o laudo mostrar o
número que decidiu. Imagem sem textura para rastrear é ERRO e não aprova: sem a medida, o gate não tem o
que dizer. `estimador` e `leitor` são injetáveis (os testes rápidos usam uma câmera virtual).

Sem exceção por projeto: o C3 não admite câmera parada declarada com motivo.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

if __name__ == "__main__":      # rodado direto: scripts/gates/gate_camera.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinema import camera  # noqa: E402

NOME = "gate_camera"
ETAPA = "depois"

AMOSTRA_FPS = 12                 # quadros medidos por segundo do ENTREGUE
LARGURA_AMOSTRA = 270            # largura do quadro medido
APARA_S = 0.25                   # tirado de cada ponta do plano: é transição, não câmera
PRE_FORA_S, PRE_PERTO_S = 0.30, 0.03       # janela de antes do punch: [t - 0.30, t - 0.03]
POS_PERTO_S, POS_LONGE_S = 0.03, 0.30      # janela de depois: [fim da subida + 0.03, + 0.30]
AMOSTRAS_MIN = 2                 # quadros mínimos em cada janela do punch (e três para medir a variação do plano)
# Rastreador de textura (Lucas-Kanade + RANSAC). Hop de UM quadro: com 2 ou 3 o ruído sobe (medido).
LK_CANTOS, LK_QUALIDADE, LK_DIST_MIN = 300, 0.01, 7
LK_JANELA, LK_NIVEIS = 21, 3
RANSAC_PX = 1.5
RASTREADOS_MIN, INLIERS_MIN = 12, 10
_EPS = 1e-9


class InsumoInvalido(Exception):
    """Vídeo ou timeline ausente/ilegível, ou imagem sem textura para medir: não dá nem para reprovar (exit 2)."""


# --- insumos -----------------------------------------------------------------------------------------------

def _timeline_ok(tl):
    if not isinstance(tl, dict):
        raise InsumoInvalido("a timeline não é um objeto JSON")
    for campo in ("relogio", "segmentos", "duracao_s"):
        if campo not in tl:
            raise InsumoInvalido("a timeline não tem o campo %r (use o render/timeline.json do projeto)" % campo)
    rel = tl["relogio"]
    if "aceleracao" not in rel or float(rel["aceleracao"]) <= 0:
        raise InsumoInvalido("a timeline não tem relogio.aceleracao")
    if not tl["segmentos"]:
        raise InsumoInvalido("a timeline não tem nenhum segmento")


def _sondar(video):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "json", str(video)],
                           capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        raise InsumoInvalido("ffprobe ausente: instale o ffmpeg (brew install ffmpeg)")
    if r.returncode != 0:
        raise InsumoInvalido("não consegui ler %s: %s" % (video, r.stderr.strip()[-200:] or "sem detalhe"))
    try:
        v = json.loads(r.stdout)["streams"][0]
        return int(v["width"]), int(v["height"])
    except (KeyError, IndexError, ValueError, TypeError):
        raise InsumoInvalido("%s não tem faixa de vídeo legível" % video)


def _leitor_padrao():
    """Decodifica o vídeo a AMOSTRA_FPS e devolve `(t_entregue, quadro em cinza)`; um quadro de cada vez."""
    import numpy as np

    def leitor(video, fps):
        larg, alt = _sondar(video)
        pw = min(larg, LARGURA_AMOSTRA)
        ph = max(2, int(round(alt * pw / float(larg))) // 2 * 2)
        cmd = ["ffmpeg", "-v", "error", "-nostdin", "-i", str(video), "-an", "-vf",
               "fps=%s,scale=%d:%d,format=gray" % (fps, pw, ph), "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        tamanho, k = pw * ph, 0
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
                yield k / float(fps), np.frombuffer(buf, dtype=np.uint8).reshape(ph, pw)
                k += 1
        finally:
            proc.stdout.close()
            erro = proc.stderr.read().decode("utf-8", "replace")
            proc.stderr.close()
            rc = proc.wait()
        if rc != 0 and k == 0:
            raise OSError("ffmpeg não decodificou %s: %s" % (video, erro.strip()[-200:]))
    return leitor


def escala_entre(a, b, mascara=None):
    """Escala (similaridade) de um quadro cinza `a` para o seguinte `b`, por pontos de textura + Lucas-Kanade +
    RANSAC. `mascara` (uint8, 255 onde vale): os pontos só nascem nela. None quando não há textura para rastrear."""
    import cv2
    import numpy as np
    p0 = cv2.goodFeaturesToTrack(a, maxCorners=LK_CANTOS, qualityLevel=LK_QUALIDADE, minDistance=LK_DIST_MIN,
                                 mask=mascara)
    if p0 is None or len(p0) < RASTREADOS_MIN:
        return None
    p1, st, _err = cv2.calcOpticalFlowPyrLK(a, b, p0, None, winSize=(LK_JANELA, LK_JANELA), maxLevel=LK_NIVEIS)
    ok = st.ravel() == 1
    if int(ok.sum()) < RASTREADOS_MIN:
        return None
    m, inliers = cv2.estimateAffinePartial2D(p0[ok], p1[ok], method=cv2.RANSAC, ransacReprojThreshold=RANSAC_PX)
    if m is None or inliers is None or int(inliers.sum()) < INLIERS_MIN:
        return None
    return float(np.hypot(m[0, 0], m[0, 1]))


def _estimador_padrao():
    """`estimador(serie)`: a escala de cada quadro de `serie` ([(t, quadro cinza)]) relativa ao primeiro, pelo
    produto das escalas entre quadros vizinhos. None onde a corrente quebra (e dali em diante)."""
    try:
        import cv2  # noqa: F401
    except ImportError:
        raise InsumoInvalido("falta o OpenCV para medir a câmera: rode `bash setup.sh` (instala o "
                             "opencv-python-headless)")

    def estimador(serie):
        if not serie:
            return []
        saida, total = [1.0], 1.0
        for (_t0, q0), (_t1, q1) in zip(serie, serie[1:]):
            s = escala_entre(q0, q1) if total is not None else None
            total = None if (s is None or total is None) else total * s
            saida.append(total)
        return saida
    return estimador


def mascaras_sem_texto(overlay, tempos, rel, forma):
    """Para cada instante ENTREGUE de `tempos`, a máscara (uint8, 255 onde vale rastrear) do quadro de `forma`
    (altura, largura) sem o TEXTO do overlay (W5.X): as letras paradas da KEY eram os cantos mais fortes e o
    rastreador media escala 1,0 num punch de +22%. O texto é a régua do gate de contraste (`contraste_texto`), com
    folga de 8 px; o dim e o scrim do lettering ficam (a imagem por baixo deles ainda se rastreia)."""
    import cv2
    import numpy as np
    from scipy import ndimage as ndi

    from gates import contraste_texto as C
    larg, alt, _d, _desl = C.info_video(overlay)
    saida = []
    for t in tempos:
        ov = C.ler_quadro(overlay, float(t) * float(rel["aceleracao"]) + float(rel.get("a0", 0.0)), larg, alt, 4)
        if ov is None:
            saida.append(None)
            continue
        texto = ndi.binary_dilation(C.mascara_texto(ov), iterations=8)
        livre = (~texto).astype(np.uint8) * 255
        saida.append(cv2.resize(livre, (forma[1], forma[0]), interpolation=cv2.INTER_NEAREST))
    return saida


def _estimador_mascarado(mascaras):
    """O estimador padrão com uma máscara por quadro (a do quadro de onde os pontos partem)."""
    def estimador(serie):
        if not serie:
            return []
        saida, total = [1.0], 1.0
        for k, ((_t0, q0), (_t1, q1)) in enumerate(zip(serie, serie[1:])):
            s = escala_entre(q0, q1, mascaras[k]) if total is not None else None
            total = None if (s is None or total is None) else total * s
            saida.append(total)
        return saida
    return estimador


# --- a medição ---------------------------------------------------------------------------------------------

def _segmento_em(segmentos, t):
    for k, sg in enumerate(segmentos):
        if sg["s"] - _EPS <= t < sg["e"] - _EPS:
            return k, sg
    return None, None


def _dentro(t, janelas):
    return any(j["s"] - _EPS <= t < j["e"] - _EPS for j in janelas or [])


def _planos(tl):
    """Os planos de avatar a medir, no relógio do ENTREGUE: os de 2 s ou mais e os que levam um punch."""
    rel = tl["relogio"]
    punches = [e for e in tl.get("camera") or [] if e.get("tipo") == "punch"]
    saida = []
    for k, sg in enumerate(tl["segmentos"]):
        if sg["tipo"] != "apresentador":
            continue
        s_d, e_d = camera.para_entregue(sg["s"], rel), camera.para_entregue(sg["e"], rel)
        longo = e_d - s_d >= camera.PLANO_AVATAR_MIN_S - _EPS
        dele = [p for p in punches if sg["s"] - _EPS <= p["t"] < sg["e"] - _EPS]
        if longo or dele:
            saida.append({"segmento": k, "inicio": s_d, "fim": e_d, "longo": longo, "punches": dele,
                          "ini_util": s_d + APARA_S, "fim_util": e_d - APARA_S})
    return saida


def _escalas(estimador, serie, onde):
    """Escala de cada quadro da `serie`; ERRO de insumo quando o rastreador perde a imagem."""
    escalas = estimador(serie)
    if len(escalas) != len(serie) or any(e is None for e in escalas):
        raise InsumoInvalido("não consegui rastrear a imagem %s: poucos pontos de textura entre quadros vizinhos. O "
                             "gate mede a escala por pontos de textura; confira se o vídeo tem imagem "
                             "(ou passe outro `estimador` ao gate)" % onde)
    return escalas


def medir(video, timeline, estimador=None, leitor=None, overlay=None):
    """Mede planos, punches e movimento; levanta InsumoInvalido."""
    _timeline_ok(timeline)
    rel = timeline["relogio"]
    segs = timeline["segmentos"]
    cam = timeline.get("camera") or []
    janelas_split = timeline.get("janelas_split") or []
    planos = _planos(timeline)

    # 1. os quadros, só dentro do miolo dos planos que interessam
    leitor = leitor or _leitor_padrao()
    if planos:
        estimador = estimador or _estimador_padrao()
    series = {p["segmento"]: [] for p in planos}        # segmento -> [(t_entregue, quadro)]
    n_quadros = 0
    for td, quadro in leitor(video, AMOSTRA_FPS):
        n_quadros += 1
        if quadro is None:
            continue
        for p in planos:
            if p["ini_util"] - _EPS <= td <= p["fim_util"] + _EPS:
                series[p["segmento"]].append((td, quadro))
                break
    if n_quadros == 0:
        raise InsumoInvalido("o leitor não devolveu nenhum quadro de %s" % video)

    # 2. a variação de escala de cada plano de avatar longo SEM punch (o com punch é dispensado: ver o docstring)
    medido_planos = []
    for p in planos:
        if not p["longo"]:
            continue
        linha = {"segmento": p["segmento"], "inicio": round(p["inicio"], 3), "fim": round(p["fim"], 3),
                 "variacao": None, "amostras": len(series[p["segmento"]]), "ok": None}
        if p["punches"]:
            linha["dispensado"] = "plano com punch: o punch medido prova que o filtro de câmera rodou"
        else:
            serie = series[p["segmento"]]
            escalas = _escalas(estimador, serie, "no plano de avatar de %.2f a %.2f s" % (p["inicio"], p["fim"]))
            v = camera.variacao_da_escala(escalas, [t for t, _q in serie])
            if v is None:
                raise InsumoInvalido("poucos quadros para medir o plano de avatar de %.2f a %.2f s"
                                     % (p["inicio"], p["fim"]))
            linha["variacao"] = round(v, 4)
            linha["ok"] = v >= camera.ESCALA_VARIACAO_MIN
        medido_planos.append(linha)

    # 3. o ganho de cada punch
    medido_punches = []
    for ev in cam:
        if ev.get("tipo") == "punch":
            medido_punches.append(_medir_punch(ev, rel, segs, janelas_split, series, estimador, overlay))

    # o plano dispensado vale o que valem os punches dele
    ok_do_punch = {round(m["t"], 3): m["ok"] for m in medido_punches}
    for linha, p in zip([m for m in medido_planos], [q for q in planos if q["longo"]]):
        if linha["ok"] is None:
            linha["ok"] = all(ok_do_punch.get(round(float(e["t"]), 3), False) for e in p["punches"])

    # 4. o movimento (janelas no relógio do entregue) e o maior vão parado
    janelas = _janelas_de_movimento(timeline, medido_planos, medido_punches)
    dur_entregue = camera.para_entregue(timeline["duracao_s"], rel)
    maior, de, ate = camera.maior_trecho_parado(janelas, dur_entregue)
    return {"amostragem_fps": AMOSTRA_FPS, "quadros": n_quadros, "planos": medido_planos,
            "punches": medido_punches,
            "parado": {"maior_s": round(maior, 3), "de": round(de, 3), "ate": round(ate, 3)}}


def _medir_punch(ev, rel, segs, janelas_split, series, estimador, overlay=None):
    t_d = camera.para_entregue(ev["t"], rel)
    saida = {"t": round(float(ev["t"]), 3), "t_entregue": round(t_d, 3), "ganho": None, "ok": False}
    k, sg = _segmento_em(segs, ev["t"])
    if sg is None or sg["tipo"] != "apresentador" or _dentro(ev["t"], janelas_split):
        onde = "fora de qualquer plano" if sg is None else (
            "em insert" if sg["tipo"] != "apresentador" else "em janela de split")
        saida["motivo"] = ("punch em %.2f s cai %s: nunca punch em insert, split ou lettering de split"
                           % (float(ev["t"]), onde))
        return saida
    serie = series.get(k, [])
    sobe_fim = camera.para_entregue(ev["t"] + ev["dur"], rel)
    hold_fim = camera.para_entregue(ev["t"] + ev["dur"] + ev.get("segura", 0.0), rel)
    ini_pre, fim_pre = t_d - PRE_FORA_S, t_d - PRE_PERTO_S
    ini_pos, fim_pos = sobe_fim + POS_PERTO_S, min(sobe_fim + POS_LONGE_S, hold_fim)
    corrente = [(t, q) for t, q in serie if ini_pre - _EPS <= t <= fim_pos + _EPS]
    antes = [t for t, _q in corrente if ini_pre - _EPS <= t <= fim_pre + _EPS]
    depois = [t for t, _q in corrente if ini_pos - _EPS <= t <= fim_pos + _EPS]
    if len(antes) < AMOSTRAS_MIN or len(depois) < AMOSTRAS_MIN:
        saida["motivo"] = ("punch em %.2f s sem quadros suficientes para medir (%d antes, %d depois): ele nasce colado "
                           "no corte ou o hold é curto demais" % (float(ev["t"]), len(antes), len(depois)))
        return saida
    if overlay is not None:
        estimador = _estimador_mascarado(mascaras_sem_texto(overlay, [t for t, _q in corrente], rel,
                                                            corrente[0][1].shape))
    escalas = _escalas(estimador, corrente, "ao redor do punch de %.2f s" % float(ev["t"]))
    por_t = {t: e for (t, _q), e in zip(corrente, escalas)}
    g = camera.ganho_do_punch([por_t[t] for t in antes], [por_t[t] for t in depois])
    saida["ganho"] = round(g, 4)
    saida["ok"] = g >= camera.PUNCH_GANHO_MIN
    return saida


def _janelas_de_movimento(tl, medido_planos, medido_punches):
    rel = tl["relogio"]
    fps = rel.get("fps", camera.FPS)
    segs = tl["segmentos"]
    cam = tl.get("camera") or []
    var = {m["segmento"]: m for m in medido_planos}
    janelas = []
    for k, sg in enumerate(segs):
        ini, fim = camera.para_entregue(sg["s"], rel), camera.para_entregue(sg["e"], rel)
        if sg["tipo"] == "apresentador" and k in var:                 # medido: vale a imagem, não a declaração
            if var[k]["ok"]:
                janelas.append((ini, fim))
        elif sg["tipo"] == "apresentador":                            # curto demais para medir: vale o declarado
            if any(e.get("tipo") == "zoom" and sg["s"] - _EPS <= e["t"] < sg["e"] - _EPS for e in cam):
                janelas.append((ini, fim))
    medido_ok = {m["t"] for m in medido_punches if m["ok"]}
    for ev in cam:
        tipo = ev.get("tipo")
        a, b = camera.janela(ev, fps)
        a_d, b_d = camera.para_entregue(a, rel), camera.para_entregue(b, rel)
        if tipo == "punch":
            if round(float(ev["t"]), 3) in medido_ok:
                janelas.append((a_d, b_d))
        elif tipo in ("push_in", "respiro"):
            janelas.append((a_d, b_d))
        elif tipo == "zoom":
            k, sg = _segmento_em(segs, ev["t"])
            if sg is not None and sg["tipo"] == "insert":             # zoom em avatar vale pela medição
                janelas.append((a_d, b_d))
    return janelas


# --- decisão -----------------------------------------------------------------------------------------------

def _motivos(medido):
    motivos = []
    for p in medido["planos"]:
        if not p["ok"] and not p.get("dispensado"):
            motivos.append("plano de avatar de %.2f a %.2f s com a escala da imagem variando %.1f%%, abaixo de %d%%: "
                           "a câmera está parada (declarar zoom não basta, o gate mede a imagem)"
                           % (p["inicio"], p["fim"], 100 * p["variacao"], round(100 * camera.ESCALA_VARIACAO_MIN)))
    for p in medido["punches"]:
        if p.get("motivo"):
            motivos.append(p["motivo"])
        elif not p["ok"]:
            motivos.append("punch em %.2f s cresceu %+.1f%% medido, abaixo dos +%d%% exigidos (o pedido é %d%%): "
                           "o punch está na timeline mas não na imagem"
                           % (p["t"], 100 * p["ganho"], round(100 * camera.PUNCH_GANHO_MIN),
                              round(100 * (camera.PUNCH_PARA - 1))))
    pa = medido["parado"]
    if pa["maior_s"] > camera.PARADO_MAX_S + _EPS:
        motivos.append("%.1f s sem movimento de câmera (de %.1f a %.1f s), acima do teto de %d s"
                       % (pa["maior_s"], pa["de"], pa["ate"], round(camera.PARADO_MAX_S)))
    return motivos


def _limiar():
    return {"escala_variacao_min": camera.ESCALA_VARIACAO_MIN, "plano_avatar_min_s": camera.PLANO_AVATAR_MIN_S,
            "punch_ganho_min": camera.PUNCH_GANHO_MIN, "parado_max_s": camera.PARADO_MAX_S}


def _gate(resultado, saida, etapa, medido=None, motivo=None, duracao=None):
    g = {"nome": NOME, "etapa": etapa, "resultado": resultado, "saida": saida}
    if medido is not None:
        g["medido"] = medido
    g["limiar"] = _limiar()
    if motivo:
        g["motivo"] = motivo
    if duracao is not None:
        g["duracao_s"] = round(duracao, 2)
    return g


def rodar(video, timeline, projeto=None, *, estimador=None, leitor=None, etapa=ETAPA, overlay=None):
    """Confere a câmera de `video` contra a `timeline` (dict). `projeto` é aceito por simetria com os outros gates:
    o C3 não tem exceção. `leitor(video, fps)` e `estimador(serie)` são injetáveis (padrão: ffmpeg e rastreador de
    textura). Devolve o gate no formato do laudo; insumo ruim vira ERRO (saída 2), nunca traceback."""
    t0 = time.time()
    try:
        _timeline_ok(timeline)
        if leitor is None and not Path(str(video)).is_file():
            raise InsumoInvalido("o vídeo não existe: %s" % video)
        medido = medir(video, timeline, estimador=estimador, leitor=leitor, overlay=overlay)
    except InsumoInvalido as e:
        return _gate("ERRO", 2, etapa, motivo=str(e))
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as e:
        return _gate("ERRO", 2, etapa, motivo="falha ao medir %s: %s" % (video, e))
    motivos = _motivos(medido)
    dur = time.time() - t0
    if motivos:
        return _gate("REPROVA", 1, etapa, medido, "; ".join(motivos), dur)
    return _gate("PASS", 0, etapa, medido, duracao=dur)


# --- linha de comando --------------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="Confere a câmera do vídeo entregue (zoom, punch, trecho parado).")
    ap.add_argument("video")
    ap.add_argument("--timeline", required=True, help="render/timeline.json do projeto")
    args = ap.parse_args(argv)
    try:
        tl = json.loads(Path(args.timeline).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        return 2
    g = rodar(args.video, tl)
    if g["resultado"] == "PASS":
        m = g["medido"]
        print("PASSA: %d plano(s) de avatar com câmera viva, %d punch(es) medidos, maior trecho parado %.1f s"
              % (len(m["planos"]), len(m["punches"]), m["parado"]["maior_s"]))
    elif g["resultado"] == "REPROVA":
        print("REPROVA: %s" % g["motivo"])
    else:
        print("ERRO de insumo: %s" % g["motivo"], file=sys.stderr)
    return g["saida"]


if __name__ == "__main__":
    sys.exit(main())
