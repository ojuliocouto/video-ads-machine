#!/usr/bin/env python3
"""GATE DA ZONA SEGURA (W3.D, capacidade C6): nenhuma tinta abaixo de y 1690 nem à direita de x 940.

    python3 scripts/gates/gate_safezone.py antes  --timeline render/timeline.json [--faixas faixas.json] [--json]
    python3 scripts/gates/gate_safezone.py depois --timeline render/timeline.json --overlay render/overlay.mov
                                                  [--instantes N] [--json]
    exit 0 passa (ou pulado) · 1 reprova · 2 insumo inválido (arquivo ausente, ilegível ou fora do contrato)

## A régua

A zona segura é RÍGIDA, nos números que o dono aprovou nas levas (plano, seção 1.5):

  y 1690   o teto da UI do Reels (botões e descrição). Tinta com y ACIMA dele, ou seja, abaixo na tela (y > 1690),
           reprova. A linha 1690 em si ainda é zona segura.
  x 940    onde o app desenha a coluna de curtir e comentar. Tinta com x > 940 reprova.

A faixa de 1250 a 1690, da máscara de anúncio da Meta, NÃO reprova: gera relato (`medido.avisos`). A legenda
padrão (y 1290 a 1500) e o rodapé (1370 a 1520) moram nela por desenho, então quase todo anúncio terá o relato.
Não há exceção por projeto: o C6 não admite tinta na UI do app declarada com motivo.

## Duas etapas, dois nomes de laudo (o laudo não aceita nome repetido)

  antes   `gate_safezone`         sobre a timeline, sem render (etapa 6 da ordem dos gates do `vam montar`).
                                  Confere a FAIXA de cada posição de legenda que a timeline usa. As faixas vêm de
                                  `overlay.layout_texto.FAIXA_LEGENDA` (fonte única; lida na hora da chamada, nunca
                                  copiada). O lettering, o CTA e o hook não têm faixa em `layout_texto` (moram no CSS
                                  do template): quem as conhece passa `faixas_extra`
                                  ([{elemento, id, y0, y1, x0, x1, s, e}]; qualquer limite pode faltar). A tinta
                                  HORIZONTAL (x) só se mede no `depois`: o plano não sabe a largura da frase.
  depois  `gate_safezone_depois`  sobre o render (etapa 17): a tinta REAL, pelo alfa do overlay (`.mov` com canal
                                  alfa), em 6 instantes espaçados. Os instantes saem da timeline (`instantes`).

## O que é TINTA no overlay

Pixel com alfa de 190 ou mais (de 255). Letra, contorno, botão e logo são opacos; o dim de tela inteira do lettering
(alfa 140, `rgba(2,3,6,.55)`) e o scrim do hook (alfa 168) ficam abaixo e NÃO são tinta (o comentário do CSS do
template registra os mesmos 190). Cor não entra: a legenda de tinta invertida (escura, sobre fundo claro) é tinta.

## Os instantes

6 instantes ESPAÇADOS entre os eventos de texto do plano (hook, cada legenda não suprimida, cada lettering que não é
o do CTA, e o CTA), em ordem de tempo: o primeiro e o último evento sempre entram. Cada instante é o MEIO da janela
do evento, e nunca antes de 0,6 s da entrada do lettering e do CTA (a animação de entrada precisa ter acabado).
Seis instantes não cobrem uma legenda a legenda: o `gate-colisao-texto` amostra o vídeo todo a cada 1,5 s para isso.
Quem quer mais passa `--instantes N`.

## Formato do resultado

`rodar_antes` e `rodar_depois` devolvem um dict no formato de gate do laudo (`contratos/laudo.schema.json`): nome,
etapa, resultado (PASS, REPROVA, ERRO ou PULADO), saida (0, 1 ou 2), medido, limiar e, fora do PASS, motivo. O schema
do laudo proíbe chave extra no gate: os relatos (`avisos`) moram em `medido`. Timeline 1x1 sai PULADO (a zona segura
é do 9x16).
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

if __name__ == "__main__":      # rodado direto: scripts/gates/gate_safezone.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from overlay import layout_texto as OL  # noqa: E402

NOME_ANTES = "gate_safezone"
ETAPA_ANTES = "antes"
NOME_DEPOIS = "gate_safezone_depois"
ETAPA_DEPOIS = "depois"

LARGURA, ALTURA = 1080, 1920
LIMITE_Y = 1690                 # teto da UI do Reels (template: "teto da UI da plataforma (y=1690)")
LIMITE_X = 940                  # coluna de curtir e comentar (template: "a coluna ... do Reels comeca em x940")
FAIXA_META = (1250, 1690)       # máscara de anúncio da Meta: só relato (plano, seção 1.5)
TINTA_ALFA_MIN = 190            # tinta = alfa de 190 a 255; o dim (140) e o scrim do hook (168) ficam de fora
INSTANTES = 6
ENTRADA_MIN_S = 0.6             # lettering e CTA: depois da animação de entrada
JANELA_MIN_S = 0.05             # evento mais curto que isto não entra na amostra
# O contrato fala `rodape`; o layout_texto fala `baixa`. A inversa de `timeline.construir.POSICAO` (um teste confere).
FAIXA_DA_POSICAO = {"padrao": "padrao", "rodape": "baixa", "costura": "costura"}
_EPS = 1e-9


class InsumoInvalido(Exception):
    """Timeline, overlay ou faixa ausente, ilegível ou fora do contrato: não dá nem para reprovar (exit 2)."""


# --- insumos -------------------------------------------------------------------------------------------------

def timeline_ok(tl, campos=("legendas",)):
    """Confere o que o gate lê da timeline; levanta InsumoInvalido dizendo o que falta."""
    if not isinstance(tl, dict):
        raise InsumoInvalido("a timeline não é um objeto JSON (use o render/timeline.json do projeto)")
    for campo in campos:
        if campo not in tl:
            raise InsumoInvalido("a timeline não tem o campo %r (use o render/timeline.json do projeto)" % campo)
    if not isinstance(tl["legendas"], list):
        raise InsumoInvalido("a timeline tem 'legendas' que não é uma lista")


def faixa_da_legenda(posicao):
    """(y0, y1) da posição de legenda da timeline, lida de `layout_texto.FAIXA_LEGENDA` NA HORA (fonte única)."""
    try:
        classe = FAIXA_DA_POSICAO[posicao]
    except (KeyError, TypeError):
        raise InsumoInvalido("posição de legenda desconhecida: %r (valem: %s)"
                             % (posicao, ", ".join(sorted(FAIXA_DA_POSICAO))))
    y0, y1 = OL.FAIXA_LEGENDA[classe]
    return y0, y1


def _numero(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _faixas_extra(faixas):
    saida = []
    for i, f in enumerate(faixas or []):
        if not isinstance(f, dict):
            raise InsumoInvalido("faixa extra #%d não é um objeto" % i)
        nome = str(f.get("elemento") or "elemento")
        for campo in ("y0", "y1", "x0", "x1", "s", "e"):
            if f.get(campo) is not None and not _numero(f[campo]):
                raise InsumoInvalido("faixa extra #%d (%s): o campo %s não é número (veio %r)"
                                     % (i, nome, campo, f[campo]))
        saida.append({"elemento": nome, "id": str(f.get("id") if f.get("id") is not None else i),
                      "y0": f.get("y0"), "y1": f.get("y1"), "x0": f.get("x0"), "x1": f.get("x1"),
                      "s": f.get("s"), "e": f.get("e"), "n": 1})
    return saida


def _faixas_das_legendas(tl):
    """Uma faixa por POSIÇÃO que alguma legenda não suprimida usa (legenda suprimida não é desenhada)."""
    por_posicao = {}
    for i, leg in enumerate(tl["legendas"]):
        if not isinstance(leg, dict) or "posicao" not in leg:
            raise InsumoInvalido("a legenda #%d não tem o campo 'posicao'" % i)
        if leg.get("suprimida"):
            continue
        por_posicao[leg["posicao"]] = por_posicao.get(leg["posicao"], 0) + 1
    saida = []
    for posicao in sorted(por_posicao):
        y0, y1 = faixa_da_legenda(posicao)
        saida.append({"elemento": "legenda", "id": posicao, "y0": y0, "y1": y1, "x0": None, "x1": None,
                      "s": None, "e": None, "n": por_posicao[posicao]})
    return saida


# --- o plano (antes) -----------------------------------------------------------------------------------------

def _avaliar_faixa(f):
    """(motivos, avisos) de uma faixa do plano."""
    quem = "%s %s" % (f["elemento"], f["id"])
    if f["n"] > 1:
        quem += " (%d ocorrências)" % f["n"]
    motivos, avisos = [], []
    if f["y1"] is not None and f["y1"] > LIMITE_Y:
        motivos.append("%s: a tinta desce até y %d, abaixo do teto de %d (a UI do Reels)" % (quem, f["y1"], LIMITE_Y))
    if f["x1"] is not None and f["x1"] > LIMITE_X:
        motivos.append("%s: a tinta vai até x %d, à direita do limite de %d (a coluna de curtir e comentar)"
                       % (quem, f["x1"], LIMITE_X))
    topo = f["y0"] if f["y0"] is not None else f["y1"]
    if f["y1"] is not None and topo is not None and f["y1"] >= FAIXA_META[0] and topo <= FAIXA_META[1]:
        avisos.append("%s: a faixa de y %d a %d cai na faixa de %d a %d da máscara de anúncio da Meta; só relato"
                      % (quem, topo, f["y1"], FAIXA_META[0], FAIXA_META[1]))
    return motivos, avisos


def _limiar():
    return {"y_max": LIMITE_Y, "x_max": LIMITE_X, "faixa_meta": list(FAIXA_META),
            "tinta_alfa_min": TINTA_ALFA_MIN, "instantes": INSTANTES}


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
                     motivo="formato 1x1: a zona segura (y 1690, x 940) é do 9x16; o quadrado é beta, sem gate")
    return None


def rodar_antes(timeline, projeto=None, *, faixas_extra=None, nome=NOME_ANTES, etapa=ETAPA_ANTES):
    """Confere as faixas do PLANO contra a zona segura. `projeto` é aceito por simetria com os outros gates: a zona
    segura não tem exceção. `faixas_extra`: as faixas de lettering, CTA e hook, quando quem chama as conhece.
    Insumo ruim vira ERRO (saída 2), nunca traceback."""
    t0 = time.time()
    try:
        timeline_ok(timeline)
        pulado = _pulado(timeline, etapa, nome)
        if pulado:
            return pulado
        faixas = _faixas_das_legendas(timeline) + _faixas_extra(faixas_extra)
        motivos, avisos = [], []
        for f in faixas:
            m, a = _avaliar_faixa(f)
            motivos += m
            avisos += a
        medido = {"faixas": [{k: v for k, v in f.items() if v is not None} for f in faixas], "avisos": avisos}
    except InsumoInvalido as e:
        return _gate("ERRO", 2, etapa, nome, motivo=str(e))
    except (OSError, ValueError, KeyError, TypeError) as e:
        return _gate("ERRO", 2, etapa, nome, motivo="falha ao conferir a timeline: %s" % e)
    dur = time.time() - t0
    if motivos:
        return _gate("REPROVA", 1, etapa, nome, medido, "; ".join(motivos), dur)
    return _gate("PASS", 0, etapa, nome, medido, duracao=dur)


# --- os instantes --------------------------------------------------------------------------------------------

def _meio(s, e, minimo=0.0):
    """O instante de medir uma janela [s, e]: o meio, nunca antes de `minimo` da entrada, nunca no último 0,05 s."""
    d = float(e) - float(s)
    return float(s) + min(max(d / 2.0, minimo), max(d - 0.05, 0.0))


def eventos(tl):
    """Os eventos de texto do plano com o instante de medir cada um, em ordem de tempo."""
    saida = []
    hook = tl.get("hook")
    if isinstance(hook, dict) and _numero(hook.get("s")) and _numero(hook.get("e")) and hook["e"] - hook["s"] >= JANELA_MIN_S:
        saida.append({"t": _meio(hook["s"], hook["e"]), "evento": "hook", "ref": str(hook.get("destaque") or "hook")})
    for leg in tl["legendas"]:
        if isinstance(leg, dict) and not leg.get("suprimida") and _numero(leg.get("s")) and _numero(leg.get("e")) \
                and leg["e"] - leg["s"] >= JANELA_MIN_S:
            saida.append({"t": _meio(leg["s"], leg["e"]), "evento": "legenda", "ref": str(leg.get("texto") or "")})
    for lett in tl.get("letterings") or []:
        if isinstance(lett, dict) and not lett.get("cta") and _numero(lett.get("s")) and _numero(lett.get("d")) \
                and lett["d"] >= JANELA_MIN_S:
            saida.append({"t": _meio(lett["s"], lett["s"] + lett["d"], ENTRADA_MIN_S), "evento": "lettering",
                          "ref": str(lett.get("key") or "")})
    cta, dur = tl.get("cta"), tl.get("duracao_s")
    if isinstance(cta, dict) and _numero(cta.get("inicio")) and _numero(dur) and dur - cta["inicio"] >= JANELA_MIN_S:
        saida.append({"t": _meio(cta["inicio"], dur, ENTRADA_MIN_S), "evento": "cta", "ref": str(cta.get("label") or "cta")})
    saida.sort(key=lambda x: x["t"])
    for x in saida:
        x["t"] = round(x["t"], 3)
    return saida


def instantes(tl, n=INSTANTES):
    """Os `n` instantes ESPAÇADOS entre os eventos de texto; o primeiro e o último evento sempre entram."""
    ev = eventos(tl)
    if n >= len(ev):
        return ev
    if n <= 1:
        return ev[:1]
    escolhidos = []
    for i in range(n):
        j = int(round(i * (len(ev) - 1) / float(n - 1)))
        if j not in escolhidos:
            escolhidos.append(j)
    return [ev[j] for j in escolhidos]


def pontos(tl, n, manuais=None):
    """Os instantes a medir: os pedidos à mão (números) ou os `n` espaçados do plano."""
    if manuais is None:
        escolhidos = instantes(tl, n)
        if not escolhidos:
            raise InsumoInvalido("a timeline não tem nenhum texto para medir (nem hook, nem legenda, nem CTA)")
        return escolhidos
    saida = []
    for t in manuais:
        if not _numero(t) or t < 0 or (_numero(tl.get("duracao_s")) and t > tl["duracao_s"] + _EPS):
            raise InsumoInvalido("instante inválido: %r (tem que estar entre 0 e a duração da timeline)" % (t,))
        saida.append({"t": round(float(t), 3), "evento": "manual", "ref": ""})
    return saida


# --- o render (depois) ---------------------------------------------------------------------------------------

def mascara_tinta(rgba):
    """Máscara booleana da tinta (alfa de TINTA_ALFA_MIN ou mais) de um quadro RGBA (ou só do canal alfa)."""
    import numpy as np
    a = np.asarray(rgba)
    if a.ndim == 3 and a.shape[2] >= 4:
        a = a[:, :, 3]
    elif a.ndim != 2:
        raise InsumoInvalido("o quadro do overlay não tem canal alfa (forma %s): o gate mede a tinta pelo alfa"
                             % (a.shape,))
    return a >= TINTA_ALFA_MIN


def quadro_valido(rgba, com_cor=False):
    """O quadro do overlay como array 1080x1920; levanta InsumoInvalido se o tamanho (ou, com `com_cor`, o RGBA)
    não for o esperado."""
    import numpy as np
    a = np.asarray(rgba)
    if a.ndim < 2:
        raise InsumoInvalido("o quadro do overlay não é uma imagem (forma %s)" % (a.shape,))
    alt, larg = a.shape[:2]
    if (larg, alt) != (LARGURA, ALTURA):
        raise InsumoInvalido("o quadro do overlay tem %dx%d: a zona segura é medida em %dx%d"
                             % (larg, alt, LARGURA, ALTURA))
    if com_cor and not (a.ndim == 3 and a.shape[2] >= 4):
        raise InsumoInvalido("o quadro do overlay não é RGBA (forma %s): a medida precisa da cor e do alfa" % (a.shape,))
    return a


def medir_quadro(rgba):
    """A tinta de um quadro 1080x1920: onde ela chega e quantos pixels passam de cada limite."""
    import numpy as np
    tinta = mascara_tinta(quadro_valido(rgba))
    n = int(tinta.sum())
    saida = {"tinta_px": n, "y_min": None, "y_max": None, "x_min": None, "x_max": None,
             "px_abaixo_de_%d" % LIMITE_Y: int(tinta[LIMITE_Y + 1:, :].sum()),
             "px_a_direita_de_%d" % LIMITE_X: int(tinta[:, LIMITE_X + 1:].sum()),
             "px_na_faixa_meta": int(tinta[FAIXA_META[0]:FAIXA_META[1] + 1, :].sum())}
    if n:
        linhas, colunas = np.flatnonzero(tinta.any(axis=1)), np.flatnonzero(tinta.any(axis=0))
        saida.update(y_min=int(linhas[0]), y_max=int(linhas[-1]), x_min=int(colunas[0]), x_max=int(colunas[-1]))
    return saida


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


def ler_overlay_padrao(overlay, t):
    """O quadro RGBA do overlay em `t` (relógio da timeline), pelo ffmpeg. Seek em duas etapas (grosso antes do
    -i, fino depois): o rótulo é o quadro de verdade, como no `gate-colisao-texto`."""
    import numpy as np
    larg, alt = _sondar(overlay)
    if (larg, alt) != (LARGURA, ALTURA):
        raise InsumoInvalido("o overlay %s tem %dx%d: a zona segura é medida em %dx%d"
                             % (Path(str(overlay)).name, larg, alt, LARGURA, ALTURA))
    grosso = max(0.0, t - 6.0)
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-ss", "%.6f" % grosso, "-i", str(overlay), "-ss", "%.6f" % (t - grosso),
           "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba", "pipe:1"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=180)
    except FileNotFoundError:
        raise InsumoInvalido("ffmpeg ausente: instale o ffmpeg (brew install ffmpeg)")
    if r.returncode != 0 or len(r.stdout) != larg * alt * 4:
        raise OSError("ffmpeg não devolveu o quadro de %.2f s do overlay %s: %s"
                      % (t, overlay, r.stderr.decode("utf-8", "replace").strip()[-200:] or "quadro fora do fim"))
    return np.frombuffer(r.stdout, dtype=np.uint8).reshape(alt, larg, 4)


def _numpy():
    try:
        import numpy  # noqa: F401
    except ImportError:
        raise InsumoInvalido("falta o numpy para medir a tinta: rode `bash setup.sh`")


def ler_quadros(overlay, pts, leitor_overlay):
    """[(ponto, quadro)] do overlay; erro de leitura vira InsumoInvalido com o instante."""
    saida = []
    for p in pts:
        try:
            quadro = leitor_overlay(overlay, p["t"])
        except InsumoInvalido:
            raise
        except (OSError, ValueError, RuntimeError, TypeError, subprocess.SubprocessError) as e:
            raise InsumoInvalido("falha ao ler o overlay em %.2f s: %s" % (p["t"], e))
        saida.append((p, quadro))
    return saida


def preparar_depois(overlay, timeline, leitor_overlay, n_instantes, manuais):
    """(leitor, pontos) validados, para os dois gates do `depois`."""
    timeline_ok(timeline, ("legendas", "duracao_s"))
    _numpy()
    if leitor_overlay is None:
        if not Path(str(overlay)).is_file():
            raise InsumoInvalido("o overlay não existe: %s" % overlay)
        leitor_overlay = ler_overlay_padrao                       # procurado AQUI: o teste e o CLI trocam o módulo
    return leitor_overlay, pontos(timeline, n_instantes, manuais)


def rodar_depois(overlay, timeline, projeto=None, *, leitor_overlay=None, n_instantes=INSTANTES, instantes=None,
                 nome=NOME_DEPOIS, etapa=ETAPA_DEPOIS):
    """Mede a tinta REAL do overlay em `n_instantes` instantes espaçados (ou em `instantes`, uma lista de tempos
    na timeline). `leitor_overlay(overlay, t)` devolve o quadro RGBA 1080x1920 (padrão: ffmpeg). Devolve o gate no
    formato do laudo; insumo ruim vira ERRO (saída 2), nunca traceback."""
    t0 = time.time()
    try:
        timeline_ok(timeline, ("legendas", "duracao_s"))
        pulado = _pulado(timeline, etapa, nome)
        if pulado:
            return pulado
        leitor, pts = preparar_depois(overlay, timeline, leitor_overlay, n_instantes, instantes)
        medidos, motivos, na_meta = [], [], 0
        for p, quadro in ler_quadros(overlay, pts, leitor):
            m = medir_quadro(quadro)
            baixo, direita = m["px_abaixo_de_%d" % LIMITE_Y], m["px_a_direita_de_%d" % LIMITE_X]
            m.update(t=p["t"], evento=p["evento"], ref=p["ref"], ok=not (baixo or direita))
            quem = "t=%.2f s (%s%s)" % (p["t"], p["evento"], " '%s'" % p["ref"] if p["ref"] else "")
            if baixo:
                motivos.append("%s: tinta até y %d, %d px abaixo do teto de %d (a UI do Reels)"
                               % (quem, m["y_max"], baixo, LIMITE_Y))
            if direita:
                motivos.append("%s: tinta até x %d, %d px à direita do limite de %d (a coluna de curtir e comentar)"
                               % (quem, m["x_max"], direita, LIMITE_X))
            na_meta += 1 if m["px_na_faixa_meta"] else 0
            medidos.append(m)
        avisos = []
        if na_meta:
            avisos.append("tinta na faixa de %d a %d da máscara de anúncio da Meta em %d de %d instantes; só relato"
                          % (FAIXA_META[0], FAIXA_META[1], na_meta, len(medidos)))
        medido = {"instantes": medidos, "avisos": avisos}
    except InsumoInvalido as e:
        return _gate("ERRO", 2, etapa, nome, motivo=str(e))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as e:
        return _gate("ERRO", 2, etapa, nome, motivo="falha ao medir o overlay %s: %s" % (overlay, e))
    dur = time.time() - t0
    if motivos:
        return _gate("REPROVA", 1, etapa, nome, medido, "; ".join(motivos), dur)
    return _gate("PASS", 0, etapa, nome, medido, duracao=dur)


# --- linha de comando ----------------------------------------------------------------------------------------

def _ler_json(caminho, o_que):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise InsumoInvalido("não consegui ler %s (%s): %s" % (o_que, caminho, e))


def imprimir(g, como_json):
    """Uma linha para quem lê; o gate inteiro em JSON para quem orquestra. Devolve o código de saída."""
    if como_json:
        print(json.dumps(g, ensure_ascii=False))
    elif g["resultado"] == "PASS":
        med = g["medido"]
        if "instantes" in med:
            print("PASSA: %d instante(s) com a tinta dentro de y %d e x %d" % (len(med["instantes"]), LIMITE_Y, LIMITE_X))
        else:
            print("PASSA: %d faixa(s) do plano dentro de y %d e x %d" % (len(med["faixas"]), LIMITE_Y, LIMITE_X))
        for a in med["avisos"]:
            print("  relato: %s" % a)
    elif g["resultado"] == "PULADO":
        print("PULADO: %s" % g["motivo"])
    elif g["resultado"] == "REPROVA":
        print("REPROVA: %s" % g["motivo"])
    else:
        print("ERRO de insumo: %s" % g["motivo"], file=sys.stderr)
    return g["saida"]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Zona segura: nenhuma tinta abaixo de y 1690 nem à direita de x 940.")
    sub = ap.add_subparsers(dest="etapa", required=True)
    a = sub.add_parser("antes", help="confere as faixas do plano (timeline), sem render")
    a.add_argument("--timeline", required=True, help="render/timeline.json do projeto")
    a.add_argument("--faixas", help="JSON com a lista de faixas extras (lettering, CTA, hook)")
    d = sub.add_parser("depois", help="mede a tinta real do overlay em 6 instantes")
    d.add_argument("--timeline", required=True)
    d.add_argument("--overlay", required=True, help="o overlay com canal alfa (.mov)")
    d.add_argument("--instantes", type=int, default=INSTANTES, help="quantos instantes espaçados (padrão %d)" % INSTANTES)
    for p in (a, d):
        p.add_argument("--json", action="store_true", help="imprime o gate no formato do laudo, em JSON")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0)
    try:
        tl = _ler_json(args.timeline, "a timeline")
        if args.etapa == "antes":
            extra = _ler_json(args.faixas, "as faixas extras") if args.faixas else None
            g = rodar_antes(tl, faixas_extra=extra)
        else:
            g = rodar_depois(args.overlay, tl, n_instantes=args.instantes)
    except InsumoInvalido as e:
        etapa, nome = (ETAPA_ANTES, NOME_ANTES) if args.etapa == "antes" else (ETAPA_DEPOIS, NOME_DEPOIS)
        g = _gate("ERRO", 2, etapa, nome, motivo=str(e))
    return imprimir(g, args.json)


if __name__ == "__main__":
    sys.exit(main())
