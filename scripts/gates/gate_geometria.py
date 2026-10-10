#!/usr/bin/env python3
"""GATE DA GEOMETRIA (W3.D, capacidade C6): o texto de tela nunca cai no rosto do apresentador.

    python3 scripts/gates/gate_geometria.py antes  --timeline render/timeline.json --avatar inputs/avatar.mp4
                                                   [--bias B] [--rosto TOPO:ALTURA] [--rosto-split Y0:Y1] [--json]
    python3 scripts/gates/gate_geometria.py depois --timeline render/timeline.json --video entrega/final_9x16.mp4
                                                   --overlay render/overlay.mov [--avatar A | --rosto-split Y0:Y1]
                                                   [--instantes N] [--json]
    exit 0 passa (ou pulado) · 1 reprova · 2 insumo inválido (arquivo ausente, ilegível ou rosto não medido)

A geometria se verifica no PLANO antes de renderizar: o AD4 gastou 5 versões (18/09) por texto que caía no rosto e só
se via depois do render. Por isso o gate roda em duas etapas, com dois nomes de laudo (o laudo não aceita nome repetido):

  antes   `gate_geometria`         sobre a timeline, sem render (etapa 6 da ordem dos gates do `vam montar`).
  depois  `gate_geometria_depois`  sobre o render (etapa 17): a tinta REAL do overlay (alfa) contra o rosto.

## antes: o que se confere (limiares do plano, seção 3, C6)

A FAIXA de cada posição de legenda vem de `overlay.layout_texto.FAIXA_LEGENDA` (fonte única: importada, lida na hora da
chamada, nunca copiada). Desde 10/10/2026 há uma posição só, a BASE do quadro (y 1554 a 1682, centro da linha perto de
y 1650), e não há legenda durante o CTA: a posição não depende mais do layout, então o gate não escolhe
entre posições, só confere que a faixa que a legenda usa não cai no NÚCLEO do rosto. Para cada legenda não suprimida,
em cada pedaço de tempo com layout constante (avatar cheio, tela dividida, insert):

  avatar cheio    a faixa é cruzada com o NÚCLEO do rosto do avatar (a interseção em pixels vai para o laudo); tem que
                  dar interseção ZERO. Se não der, NENHUMA posição serve (a posição é única): o gate declara
                  `acao: suprimir_legenda` (dentro de `medido`, com a lista) e reprova. `aplicar_supressao` marca essas
                  legendas como suprimidas e a segunda rodada passa. Sem rosto não há resultado inventado: sem a
                  medição do rosto o gate dá ERRO;
  tela dividida   o apresentador mora no painel de baixo (a partir de y 1150) e a base do quadro é a base desse painel:
                  a faixa é cruzada com o NÚCLEO do rosto do painel, interseção ZERO, e a mesma supressão vale;
  insert          sem rosto do apresentador, nada a colidir.

O rosto do avatar cheio é o do avatar bruto (queixo = topo + altura sobre 1920, sem o reframe e o zoom do plano); a posição real no quadro entregue é medida no `depois`. O rosto do
painel do split vem do mesmo avatar pelo corte do motor (`filtros_avatar`: topo do painel, janela, escala e
`corte_y_split` do bias), ou direto de `rosto_split=(y0, y1)`.

## depois: o que complementa o `gate-colisao-texto`

O `gate-colisao-texto` amostra o vídeo todo a cada 1,5 s com o Haar. Este gate usa os MESMOS limiares e a MESMA
definição de núcleo (inset de 12%, 78% da altura) e de tinta (alfa acima de 120 e cor acima de 150), e acrescenta
duas coisas: (1) a mesma amostra de 6 instantes da zona segura, para o laudo ler os dois gates no mesmo quadro;
(2) a geometria do PLANO quando o detector fica cego em tela dividida (texto em cima da cara quebra o Haar, e o gate
aprovava o pior caso: anúncio de referência, 27/08). No split o apresentador mora no painel de baixo por construção; com `rosto_split`
a tinta ali é colisão mesmo sem detecção. Sem `rosto_split` e sem detecção o instante não é medido e vira relato.
O detector padrão é o do `gate-colisao-texto` (carregado do arquivo dele: o nome tem hífen), com o filtro de pele;
no split só vale o rosto cujo centro está no painel de baixo (rosto no painel de cima é conteúdo do insert).
O overlay vive no relógio da timeline (W3.A); o vídeo entregue, em `(t - a0) / aceleração`.

## Formato do resultado

Dict no formato de gate do laudo (`contratos/laudo.schema.json`). `acao` e `avisos` moram em `medido`: o schema do
laudo proíbe chave extra no gate. Timeline 1x1 sai PULADO. Não há exceção por projeto.
"""
import argparse
import copy
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

if __name__ == "__main__":      # rodado direto: scripts/gates/gate_geometria.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from footage import filtros_avatar as FA  # noqa: E402
from gates import gate_safezone  # noqa: E402
from gates.gate_safezone import InsumoInvalido  # noqa: E402
from overlay import layout_texto as OL  # noqa: E402

NOME_ANTES = "gate_geometria"
ETAPA_ANTES = "antes"
NOME_DEPOIS = "gate_geometria_depois"
ETAPA_DEPOIS = "depois"

TETO_UI_Y = gate_safezone.LIMITE_Y
INSTANTES = gate_safezone.INSTANTES
# Do gate-colisao-texto.py (um teste confere cada número contra o texto dele, sem importá-lo):
INSET_NUCLEO = 0.12             # a caixa do Haar encolhe 12% de cada lado até o núcleo do rosto
FRACAO_ALTURA_NUCLEO = 0.78     # e o quarto de baixo (queixo e barba) sai da conta
LIMIAR_COLISAO_PCT = 1.5        # tinta cobrindo mais que isso do núcleo reprova
TINTA_ALFA_ROSTO = 120          # tinta = alfa acima disso ...
TINTA_LUM_ROSTO = 150           # ... e cor acima disso (letra clara e opaca; o scrim é escuro)
PELE_MIN = 0.12                 # fração de pele mínima numa caixa para ela valer como rosto
_EPS = 1e-9


# --- a conta do rosto ----------------------------------------------------------------------------------------

def nucleo_y(y, altura):
    """(y0, y1) do núcleo do rosto de uma caixa que começa em `y` e tem `altura`: a mesma conta do gate-colisao-texto."""
    dy = int(altura * INSET_NUCLEO)
    y0 = y + dy
    return y0, y0 + int((altura - 2 * dy) * FRACAO_ALTURA_NUCLEO)


def intersecao_px(a, b):
    """Pixels de altura em comum entre as faixas verticais `a` e `b` (y0, y1)."""
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def rosto_no_split(topo, altura, bias):
    """(y0, y1) da caixa do rosto no painel de baixo do split, em y de tela, a partir da caixa no avatar (topo,
    altura) e do bias do corte. É o filtro do motor: janela do avatar (`SPLIT_AV_SRC`) levada à largura cheia,
    cortada em `corte_y_split(bias)` e posta a partir de `SPLIT_TOP_H`."""
    _x, y_janela, w_janela, _h = FA.SPLIT_AV_SRC
    escala = FA.W / float(w_janela)
    corte = FA.corte_y_split(bias, FA.altura_util_split())
    y0 = FA.SPLIT_TOP_H + int(round((topo - y_janela) * escala)) - corte
    return y0, y0 + int(round(altura * escala))


def _numero(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _rosto_ok(rosto):
    """(topo, altura) do rosto no avatar, validado: dois números, altura positiva."""
    if isinstance(rosto, dict):
        rosto = (rosto.get("topo"), rosto.get("altura"))
    if not isinstance(rosto, (list, tuple)) or len(rosto) != 2 or not all(_numero(v) for v in rosto):
        raise InsumoInvalido("a medição do rosto tem que ser (topo, altura) em pixels do avatar (veio %r)" % (rosto,))
    topo, altura = int(rosto[0]), int(rosto[1])
    if altura <= 0 or topo < 0:
        raise InsumoInvalido("a medição do rosto não faz sentido: topo %d, altura %d" % (topo, altura))
    return topo, altura


def _par_y(par, o_que):
    if not isinstance(par, (list, tuple)) or len(par) != 2 or not all(_numero(v) for v in par) or par[1] <= par[0]:
        raise InsumoInvalido("%s tem que ser (y0, y1) em pixels de tela, com y1 maior que y0 (veio %r)" % (o_que, par))
    return int(par[0]), int(par[1])


def _medir_padrao(avatar):
    """(topo, altura) do rosto no avatar, pelo Haar do `medir_rosto` (None se não acha)."""
    try:
        import medir_rosto
    except ImportError as e:
        raise InsumoInvalido("falta o OpenCV para medir o rosto do avatar (%s): rode `bash setup.sh`" % e)
    return medir_rosto.caixa_rosto(str(avatar))


def _bias_padrao(avatar):
    """O bias do corte do painel de baixo, medido no avatar pelo `medir_enquadramento` (mesma conta do motor)."""
    from footage import enquadramento
    try:
        return enquadramento.medir_bias_split(str(avatar))
    except enquadramento.ErroEnquadramento as e:
        raise InsumoInvalido("não consegui medir o enquadramento do split: %s" % e)


def _rosto_do_avatar(avatar, rosto, medir):
    if rosto is not None:
        return _rosto_ok(rosto)
    if avatar is None:
        raise InsumoInvalido("passe o avatar (o gate mede o rosto nele) ou a medição do rosto (topo, altura): sem "
                             "saber onde o queixo cai o gate não decide, e o plano não chuta")
    try:
        caixa = (medir or _medir_padrao)(str(avatar))
    except InsumoInvalido:
        raise
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, ImportError) as e:
        raise InsumoInvalido("falha ao medir o rosto do avatar %s: %s" % (avatar, e))
    if not caixa:
        raise InsumoInvalido("não achei rosto no avatar %s: sem a medição o gate não decide (confira o avatar, ou "
                             "passe a medição à mão com --rosto TOPO:ALTURA)" % avatar)
    return _rosto_ok(caixa)


def _painel_do_split(topo, altura, avatar, bias, rosto_split, medir_bias):
    """O rosto no painel do split: {y0, y1, nucleo_y0, nucleo_y1[, bias]}. Direto de `rosto_split` ou do avatar."""
    if rosto_split is not None:
        y0, y1 = _par_y(rosto_split, "o rosto do painel (rosto_split)")
        info = {}
    else:
        if bias is None:
            if avatar is None:
                raise InsumoInvalido("a timeline tem legenda em tela dividida e o gate não sabe onde o rosto cai no "
                                     "painel: passe o bias do corte (--bias, de `medir_enquadramento.py avatar`) ou "
                                     "o rosto do painel (rosto_split, y0 e y1)")
            bias = (medir_bias or _bias_padrao)(str(avatar))
        if not _numero(bias) or not 0 <= bias <= 1:
            raise InsumoInvalido("o bias do split tem que ser um número entre 0 e 1 (veio %r)" % (bias,))
        y0, y1 = rosto_no_split(topo, altura, bias)
        info = {"bias": bias}
    n0, n1 = nucleo_y(y0, y1 - y0)
    info.update(y0=y0, y1=y1, nucleo_y0=n0, nucleo_y1=n1)
    return info


# --- a timeline ----------------------------------------------------------------------------------------------

def _timeline_ok(tl, campos):
    gate_safezone.timeline_ok(tl, campos)
    for campo in ("segmentos", "janelas_split"):
        if campo in tl and not isinstance(tl[campo], list):
            raise InsumoInvalido("a timeline tem %r que não é uma lista" % campo)
    if "segmentos" in campos and not tl["segmentos"]:
        raise InsumoInvalido("a timeline não tem nenhum segmento (use o render/timeline.json do projeto)")


def _layout_em(tl, t):
    """split (janelas_split, a fonte única), insert (segmento de insert) ou cheio (avatar cheio)."""
    if any(j["s"] <= t < j["e"] for j in tl["janelas_split"]):
        return "split"
    sg = next((s for s in tl["segmentos"] if s["s"] <= t < s["e"]), None)
    return "insert" if sg is not None and sg["tipo"] == "insert" else "cheio"


def _fatias(tl, s, e, tol):
    """[(a, b, layout)] de [s, e] com layout constante; lasca menor que `tol` (meio quadro) cai fora."""
    cortes = {float(s), float(e)}
    for faixa in list(tl["janelas_split"]) + list(tl["segmentos"]):
        for x in (faixa["s"], faixa["e"]):
            if s < x < e:
                cortes.add(float(x))
    pts = sorted(cortes)
    saida = []
    for a, b in zip(pts, pts[1:]):
        if b - a < tol:
            continue
        lay = _layout_em(tl, (a + b) / 2.0)
        if saida and saida[-1][2] == lay:
            saida[-1] = (saida[-1][0], b, lay)
        else:
            saida.append((a, b, lay))
    return saida


def _limiar():
    return {"teto_ui_y": TETO_UI_Y,
            "colisao_pct": LIMIAR_COLISAO_PCT, "inset_nucleo": INSET_NUCLEO, "fracao_altura_nucleo": FRACAO_ALTURA_NUCLEO,
            "split_top_h": FA.SPLIT_TOP_H,
            "faixas": {k: list(v) for k, v in OL.FAIXA_LEGENDA.items()}, "instantes": INSTANTES}


def _gate(resultado, saida, etapa, nome, medido=None, motivo=None, duracao=None):
    g = {"nome": nome, "etapa": etapa, "resultado": resultado, "saida": saida}
    if medido is not None:
        g["medido"] = medido
    g["limiar"] = _limiar()
    if motivo:
        g["motivo"] = motivo
    if duracao is not None:
        g["duracao_s"] = round(duracao, 2)
    return g


def _pulado(tl, etapa, nome):
    if tl.get("formato") == "1x1":
        return _gate("PULADO", 0, etapa, nome,
                     motivo="formato 1x1: a geometria do rosto (painéis, costura, zona segura) é do 9x16; o quadrado é "
                            "beta, sem gate")
    return None


# --- antes ---------------------------------------------------------------------------------------------------

def _problemas_da_fatia(lay, posicao, faixa, rosto, painel_fn):
    """(problemas, intersecao_px, sem_faixa) de um pedaço de legenda em `lay`. `painel_fn()` devolve o rosto do split.
    `sem_faixa` é True quando a faixa cai no núcleo do rosto: a posição é única, nenhuma outra serve, a legenda sai."""
    topo, altura = rosto
    a, b = faixa
    if lay == "cheio":
        n0, n1 = nucleo_y(topo, altura)
        inter = intersecao_px((a, b), (n0, n1))
        if inter > 0:
            return ["a legenda (%s, y %d a %d) cai %d px no núcleo do rosto do avatar (y %d a %d): a posição é única, "
                    "nenhuma outra serve, suprimir a legenda" % (posicao, a, b, inter, n0, n1)], inter, True
        return [], 0, False
    if lay == "split":
        painel = painel_fn()
        inter = intersecao_px((a, b), (painel["nucleo_y0"], painel["nucleo_y1"]))
        if inter > 0:
            return ["a legenda (%s, y %d a %d) cai %d px no núcleo do rosto do painel do apresentador (y %d a %d): a "
                    "posição é única, nenhuma outra serve, suprimir a legenda"
                    % (posicao, a, b, inter, painel["nucleo_y0"], painel["nucleo_y1"])], inter, True
        return [], 0, False
    return [], 0, False


def _quem(onde, ate=5):
    """'legenda #3 (2.00 a 4.00 s)' ou 'legendas #0, #1, #7 e mais 2': o motivo agrupa a mesma causa."""
    if len(onde) == 1:
        i, s, e = onde[0]
        return "legenda #%d, %.2f a %.2f s" % (i, s, e)
    nomes = ", ".join("#%d" % i for i, _s, _e in onde[:ate])
    return "legendas %s%s" % (nomes, " e mais %d" % (len(onde) - ate) if len(onde) > ate else "")


def rodar_antes(timeline, projeto=None, *, avatar=None, rosto=None, medir=None, bias=None, medir_bias=None,
                rosto_split=None, nome=NOME_ANTES, etapa=ETAPA_ANTES):
    """Confere a geometria das legendas do PLANO contra o rosto. O rosto vem de `rosto` ((topo, altura) no avatar),
    ou de `medir(avatar)` (padrão: o Haar do `medir_rosto`); o do painel do split, de `rosto_split` ((y0, y1) em y de
    tela), ou do `bias` (padrão: `medir_bias(avatar)`, o `medir_enquadramento`). `projeto` é aceito por simetria: a
    geometria não tem exceção. Devolve o gate no formato do laudo; insumo ruim vira ERRO (saída 2), nunca traceback."""
    t0 = time.time()
    try:
        _timeline_ok(timeline, ("legendas", "segmentos", "janelas_split"))
        pulado = _pulado(timeline, etapa, nome)
        if pulado:
            return pulado
        topo, altura = _rosto_do_avatar(avatar, rosto, medir)
        queixo = topo + altura
        fracao = queixo / float(FA.H)
        n0, n1 = nucleo_y(topo, altura)
        info_avatar = {"topo": topo, "altura": altura, "queixo_y": queixo, "queixo_fracao": round(fracao, 4),
                       "nucleo_y0": n0, "nucleo_y1": n1}
        cache = {}

        def painel_fn():
            if "p" not in cache:
                cache["p"] = _painel_do_split(topo, altura, avatar, bias, rosto_split, medir_bias)
            return cache["p"]

        tol = 0.5 / float((timeline.get("relogio") or {}).get("fps") or 30)
        verificadas = suprimidas = 0
        com_problema, suprimir, avisos = [], [], []
        por_problema = {}                           # texto do problema -> [(índice, s, e)]: o motivo agrupa
        for i, leg in enumerate(timeline["legendas"]):
            if not isinstance(leg, dict) or not all(k in leg for k in ("s", "e", "posicao")):
                raise InsumoInvalido("a legenda #%d não tem s, e e posicao" % i)
            if leg.get("suprimida"):
                suprimidas += 1
                continue
            verificadas += 1
            faixa = gate_safezone.faixa_da_legenda(leg["posicao"])
            fatias, problemas, sem_faixa = [], [], False
            for a, b, lay in _fatias(timeline, leg["s"], leg["e"], tol):
                probs, inter, sem = _problemas_da_fatia(lay, leg["posicao"], faixa,
                                                        (topo, altura), painel_fn)
                fatias.append({"layout": lay, "s": round(a, 3), "e": round(b, 3), "faixa": list(faixa),
                               "intersecao_px": inter, "problemas": probs})
                problemas += probs
                sem_faixa = sem_faixa or sem
            if not problemas:
                continue
            texto = str(leg.get("texto") or "")
            com_problema.append({"indice": i, "s": leg["s"], "e": leg["e"], "posicao": leg["posicao"], "texto": texto,
                                 "fatias": fatias, "problemas": problemas})
            for prob in dict.fromkeys(problemas):
                por_problema.setdefault(prob, []).append((i, leg["s"], leg["e"]))
            if sem_faixa:
                suprimir.append({"indice": i, "s": leg["s"], "e": leg["e"], "texto": texto})
        motivos = ["%s (%s)" % (prob, _quem(onde)) for prob, onde in por_problema.items()]
        medido = {"rosto_avatar": info_avatar, "rosto_split": cache.get("p"),
                  "legendas": {"verificadas": verificadas, "suprimidas": suprimidas, "com_problema": com_problema},
                  "avisos": avisos}
        if suprimir:
            medido["acao"] = "suprimir_legenda"
            medido["suprimir"] = suprimir
    except InsumoInvalido as e:
        return _gate("ERRO", 2, etapa, nome, motivo=str(e))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as e:
        return _gate("ERRO", 2, etapa, nome, motivo="falha ao conferir a geometria: %s" % e)
    dur = time.time() - t0
    if motivos:
        return _gate("REPROVA", 1, etapa, nome, medido, "; ".join(motivos), dur)
    return _gate("PASS", 0, etapa, nome, medido, duracao=dur)


def aplicar_supressao(timeline, gate):
    """Cópia da timeline com `suprimida: true` nas legendas que o gate mandou suprimir (`medido.acao`). Sem ação, a
    cópia sai igual. Para a orquestração: roda o gate, aplica, roda de novo (uma vez)."""
    nova = copy.deepcopy(timeline)
    medido = (gate or {}).get("medido") or {}
    if medido.get("acao") == "suprimir_legenda":
        for x in medido.get("suprimir") or []:
            i = x["indice"]
            if not 0 <= i < len(nova["legendas"]):
                raise ValueError("a timeline não é a do gate: não existe a legenda #%d" % i)
            nova["legendas"][i]["suprimida"] = True
    return nova


# --- depois --------------------------------------------------------------------------------------------------

def tinta_clara(rgba):
    """Máscara da tinta que conta como 'texto no rosto': opaca (alfa acima de 120) e clara (cor acima de 150). O dim
    de tela inteira e o scrim do lettering são escuros e ficam de fora; é a definição do `gate-colisao-texto`."""
    a = gate_safezone.quadro_valido(rgba, com_cor=True)
    return (a[:, :, 3] > TINTA_ALFA_ROSTO) & (a[:, :, :3].max(axis=2) > TINTA_LUM_ROSTO)


def cobertura_pct(tinta, caixa):
    """% do núcleo da caixa do rosto (x, y, w, h) coberto por tinta (a conta do `cobertura_por_mascara` do gate-colisao)."""
    x, y, w, h = [int(v) for v in caixa]
    dx, dy = int(w * INSET_NUCLEO), int(h * INSET_NUCLEO)
    x, y, w, h = x + dx, y + dy, w - 2 * dx, h - 2 * dy
    h = int(h * FRACAO_ALTURA_NUCLEO)
    area = w * h
    if area <= 0:
        return 0.0
    alt, larg = tinta.shape
    x0, y0, x1, y1 = max(0, x), max(0, y), min(larg, x + w), min(alt, y + h)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return 100.0 * float(tinta[y0:y1, x0:x1].sum()) / area


_GATE_COLISAO = []


def _gate_colisao():
    """O módulo do `gate-colisao-texto.py` (o nome tem hífen, então carrega-se pelo arquivo), uma vez."""
    if not _GATE_COLISAO:
        caminho = Path(__file__).resolve().parent / "gate-colisao-texto.py"
        spec = importlib.util.spec_from_file_location("gate_colisao_texto", str(caminho))
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except SystemExit as e:                 # o gate sai com a mensagem quando falta o OpenCV
            raise InsumoInvalido(str(e.code))
        _GATE_COLISAO.append(mod)
    return _GATE_COLISAO[0]


def _quadro_do_video(video, t):
    """O quadro BGR do vídeo entregue em `t` (seek em duas etapas, como o gate-colisao-texto)."""
    import numpy as np
    larg, alt = gate_safezone._sondar(video)
    if (larg, alt) != (gate_safezone.LARGURA, gate_safezone.ALTURA):
        raise InsumoInvalido("o vídeo %s tem %dx%d: a geometria é medida em %dx%d"
                             % (Path(str(video)).name, larg, alt, gate_safezone.LARGURA, gate_safezone.ALTURA))
    grosso = max(0.0, t - 6.0)
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-ss", "%.6f" % grosso, "-i", str(video), "-ss", "%.6f" % (t - grosso),
           "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1"]
    r = subprocess.run(cmd, capture_output=True, timeout=180)
    if r.returncode != 0 or len(r.stdout) != larg * alt * 3:
        raise OSError("ffmpeg não devolveu o quadro de %.2f s do vídeo %s: %s"
                      % (t, video, r.stderr.decode("utf-8", "replace").strip()[-200:] or "quadro fora do fim"))
    return np.frombuffer(r.stdout, dtype=np.uint8).reshape(alt, larg, 3)


def _detector_padrao():
    """`detector(video, t_entregue) -> [(x, y, w, h)]`: o Haar do gate-colisao-texto com o filtro de pele dele."""
    gc = _gate_colisao()

    def detector(video, t):
        quadro = _quadro_do_video(video, t)
        return [tuple(int(v) for v in r) for r in gc.detectar_rostos(quadro) if gc.fracao_pele(quadro, r) >= PELE_MIN]
    return detector


def rodar_depois(video, overlay, timeline, projeto=None, *, detector=None, leitor_overlay=None, rosto_split=None,
                 n_instantes=INSTANTES, instantes=None, nome=NOME_DEPOIS, etapa=ETAPA_DEPOIS):
    """Mede a tinta REAL do overlay contra o rosto, em `n_instantes` instantes espaçados (ou em `instantes`, tempos
    da timeline). `detector(video, t_entregue)` devolve as caixas de rosto (padrão: Haar, ver o docstring);
    `leitor_overlay(overlay, t)` devolve o quadro RGBA 1080x1920 (padrão: ffmpeg); `rosto_split` = (y0, y1) do rosto
    no painel de baixo, para o instante em que o detector fica cego no split. Devolve o gate no formato do laudo;
    insumo ruim vira ERRO (saída 2), nunca traceback."""
    t0 = time.time()
    try:
        _timeline_ok(timeline, ("legendas", "duracao_s", "segmentos", "janelas_split", "relogio"))
        pulado = _pulado(timeline, etapa, nome)
        if pulado:
            return pulado
        if detector is None:
            if not Path(str(video)).is_file():
                raise InsumoInvalido("o vídeo não existe: %s" % video)
            detector = _detector_padrao()
        leitor, pts = gate_safezone.preparar_depois(overlay, timeline, leitor_overlay, n_instantes, instantes)
        plano = _par_y(rosto_split, "o rosto do painel (rosto_split)") if rosto_split is not None else None
        rel = timeline["relogio"]
        a0, acel = float(rel.get("a0", 0.0)), float(rel["aceleracao"])
        medidos, motivos, avisos = [], [], []
        for p, quadro in gate_safezone.ler_quadros(overlay, pts, leitor):
            tinta = tinta_clara(quadro)
            lay = _layout_em(timeline, p["t"])
            try:
                caixas = [tuple(c) for c in detector(video, (p["t"] - a0) / acel)]
            except InsumoInvalido:
                raise
            except (OSError, ValueError, RuntimeError, TypeError, subprocess.SubprocessError) as e:
                raise InsumoInvalido("falha ao detectar o rosto em %.2f s do vídeo: %s" % (p["t"], e))
            if lay == "split":                      # no painel de cima o 'rosto' é conteúdo do insert, não o apresentador
                caixas = [c for c in caixas if c[1] + c[3] / 2.0 >= FA.SPLIT_TOP_H]
            if caixas:
                fonte, pct = "detector", max(cobertura_pct(tinta, c) for c in caixas)
            elif lay == "split" and plano is not None:
                n0, n1 = nucleo_y(plano[0], plano[1] - plano[0])
                area = gate_safezone.LARGURA * max(n1 - n0, 1)
                fonte, pct = "plano", 100.0 * float(tinta[n0:n1, :].sum()) / area
            else:
                fonte, pct = None, 0.0
                if lay in ("cheio", "split"):
                    avisos.append("t=%.2f s (%s): sem rosto detectado e sem rosto do plano; a colisão não foi medida"
                                  % (p["t"], lay))
            linhas = tinta.any(axis=1)
            ys = [int(v) for v in linhas.nonzero()[0][[0, -1]]] if linhas.any() else None
            ok = pct <= LIMIAR_COLISAO_PCT
            medidos.append({"t": p["t"], "evento": p["evento"], "ref": p["ref"], "layout": lay, "rostos": len(caixas),
                            "fonte_do_rosto": fonte, "maior_cobertura_pct": round(pct, 2), "tinta_px": int(tinta.sum()),
                            "tinta_y": ys, "ok": ok})
            if not ok:
                quem = "%s%s" % (p["evento"], " '%s'" % p["ref"] if p["ref"] else "")
                motivos.append("t=%.2f s (%s, %s): a tinta cobre %.1f%% do núcleo do rosto (%s), acima do limite de %.1f%%"
                               % (p["t"], quem, lay, pct, "rosto do plano" if fonte == "plano" else "detector",
                                  LIMIAR_COLISAO_PCT))
        medido = {"instantes": medidos, "avisos": avisos}
    except InsumoInvalido as e:
        return _gate("ERRO", 2, etapa, nome, motivo=str(e))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as e:
        return _gate("ERRO", 2, etapa, nome, motivo="falha ao medir a geometria do render: %s" % e)
    dur = time.time() - t0
    if motivos:
        return _gate("REPROVA", 1, etapa, nome, medido, "; ".join(motivos), dur)
    return _gate("PASS", 0, etapa, nome, medido, duracao=dur)


# --- linha de comando ----------------------------------------------------------------------------------------

def _par(texto, o_que):
    try:
        a, b = texto.split(":")
        return int(a), int(b)
    except (ValueError, AttributeError):
        raise InsumoInvalido("%s tem que ser dois inteiros separados por ':' (veio %r)" % (o_que, texto))


def imprimir(g, como_json):
    """Uma linha para quem lê; o gate inteiro em JSON para quem orquestra. Devolve o código de saída."""
    if como_json:
        print(json.dumps(g, ensure_ascii=False))
    elif g["resultado"] == "PASS":
        med = g["medido"]
        if "instantes" in med:
            pior = max([m["maior_cobertura_pct"] for m in med["instantes"]] or [0.0])
            print("PASSA: %d instante(s) medidos, maior cobertura do núcleo do rosto %.1f%% (limite %.1f%%)"
                  % (len(med["instantes"]), pior, LIMIAR_COLISAO_PCT))
        else:
            ra = med["rosto_avatar"]
            print("PASSA: %d legenda(s) verificadas (queixo em %d%% da altura, núcleo do rosto em y %d a %d)"
                  % (med["legendas"]["verificadas"], round(100 * ra["queixo_fracao"]), ra["nucleo_y0"], ra["nucleo_y1"]))
        for a in med["avisos"]:
            print("  relato: %s" % a)
    elif g["resultado"] == "PULADO":
        print("PULADO: %s" % g["motivo"])
    elif g["resultado"] == "REPROVA":
        print("REPROVA: %s" % g["motivo"])
        if g.get("medido", {}).get("acao"):
            print("  ação: %s (aplicar_supressao e rodar de novo)" % g["medido"]["acao"])
    else:
        print("ERRO de insumo: %s" % g["motivo"], file=sys.stderr)
    return g["saida"]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Geometria: o texto de tela nunca cai no rosto do apresentador.")
    sub = ap.add_subparsers(dest="etapa", required=True)
    a = sub.add_parser("antes", help="confere as legendas do plano (timeline) contra o rosto, sem render")
    a.add_argument("--timeline", required=True, help="render/timeline.json do projeto")
    a.add_argument("--avatar", help="o vídeo do apresentador: o gate mede o rosto e o enquadramento do split nele")
    a.add_argument("--rosto", help="o rosto já medido no avatar, TOPO:ALTURA (dispensa medir)")
    a.add_argument("--bias", type=float, help="o bias do corte do painel de baixo (dispensa medir o enquadramento)")
    d = sub.add_parser("depois", help="mede a tinta real do overlay contra o rosto, em 6 instantes")
    d.add_argument("--timeline", required=True)
    d.add_argument("--video", required=True, help="o vídeo entregue (1080x1920)")
    d.add_argument("--overlay", required=True, help="o overlay com canal alfa (.mov)")
    d.add_argument("--avatar", help="para achar o rosto do painel do split quando o detector fica cego")
    d.add_argument("--bias", type=float)
    d.add_argument("--instantes", type=int, default=INSTANTES, help="quantos instantes espaçados (padrão %d)" % INSTANTES)
    for p in (a, d):
        p.add_argument("--rosto-split", dest="rosto_split", help="o rosto no painel de baixo, em y de tela, Y0:Y1")
        p.add_argument("--json", action="store_true", help="imprime o gate no formato do laudo, em JSON")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0)
    etapa, nome = (ETAPA_ANTES, NOME_ANTES) if args.etapa == "antes" else (ETAPA_DEPOIS, NOME_DEPOIS)
    try:
        tl = gate_safezone._ler_json(args.timeline, "a timeline")
        split = _par(args.rosto_split, "--rosto-split") if args.rosto_split else None
        if args.etapa == "antes":
            g = rodar_antes(tl, avatar=args.avatar, rosto=_par(args.rosto, "--rosto") if args.rosto else None,
                            medir=_medir_padrao, bias=args.bias, rosto_split=split)
        else:
            if split is None and args.avatar and tl.get("janelas_split"):
                topo, altura = _rosto_do_avatar(args.avatar, None, _medir_padrao)
                split = _painel_do_split(topo, altura, args.avatar, args.bias, None, None)
                split = (split["y0"], split["y1"])
            g = rodar_depois(args.video, args.overlay, tl, detector=None, rosto_split=split,
                             n_instantes=args.instantes)
    except InsumoInvalido as e:
        g = _gate("ERRO", 2, etapa, nome, motivo=str(e))
    return imprimir(g, args.json)


if __name__ == "__main__":
    sys.exit(main())
