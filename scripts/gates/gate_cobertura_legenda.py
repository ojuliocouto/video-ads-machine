#!/usr/bin/env python3
"""GATE DA COBERTURA DA LEGENDA (W7.W, A2): toda palavra falada tem texto na tela, fora de lettering e gancho.

    python3 scripts/gates/gate_cobertura_legenda.py --timeline render/timeline.json --alinhamento render/alinhamento.json
    exit 0 passa · 1 reprova · 2 insumo inválido (timeline ou alinhamento ausente, ilegível ou sem palavras)

O defeito que ele pega: o CTA entrou cerca de 3 s ANTES de a voz dizer o botão e levou a legenda do bloco anterior junto
(o CTA ocupa o lugar dela): 24 palavras faladas, 6,6 s, sem texto nenhum. Nenhum gate de janela viu, porque cada um olha
uma janela de cada vez; este olha a FALA. Reprova quando

  - mais de 3% (`MAX_SEM_TEXTO_PCT`) das palavras faladas fora das janelas isentas ficam sem texto na tela;
  - o CTA entra antes do início do bloco cta (a âncora do CTA nunca é anterior ao bloco: `overlay.cta`).

Janelas ISENTAS (a palavra ali não precisa de legenda, outro texto ocupa o lugar): o gancho e cada lettering com a folga em
que a legenda sai de propósito (`FOLGA_LETTERING_S`, a de `overlay.legendas`: legenda e lettering não dividem a tela). A
palavra falada SOB um lettering não é contada nem penalizada (regra mantida pelo dono em 10/10/2026: lettering e legenda
nunca juntos, a palavra sob o lettering fica sem legenda por design). O CTA NÃO é mais isento: desde 10/10/2026 a legenda
continua durante o CTA, acima da pílula, e as palavras finais da fala ("e se inscrever enquanto as vagas...") precisam
de texto como as outras. O CTA entrar antes do início do bloco cta segue sendo defeito (`cta_antes_do_bloco_s`).

Texto na tela, para a palavra que PRECISA de legenda, é a legenda declarada na timeline que não está `suprimida` (o CTA
não é a legenda da fala). Um vão entre duas legendas (ou entre uma
legenda e uma janela isenta) de até `VAO_PONTE_S` (o piscar da troca de layout e o piso de 0,2 s do grupo) não é palavra perdida: a
palavra dentro dele tem texto logo antes e logo depois. Todos os tempos estão no relógio da footage a 1x, o mesmo do
alinhamento: nenhuma conversão para o entregue.

`rodar` devolve um dict no formato de gate do laudo (`contratos/laudo.schema.json`).
"""
import argparse
import json
import sys
import time
from pathlib import Path

NOME = "gate_cobertura_legenda"
ETAPA = "depois"

MAX_SEM_TEXTO_PCT = 3.0
VAO_PONTE_S = 0.5
FOLGA_LETTERING_S = 0.35         # a de overlay.legendas.FOLGA_LETT (um teste confere que continuam iguais)
TOLERANCIA_S = 0.05              # arredondamento do JSON da timeline
MAIORES_VAOS = 5


class InsumoInvalido(Exception):
    pass


def _gate(resultado, saida, medido=None, motivo=None, duracao=None):
    g = {"nome": NOME, "etapa": ETAPA, "resultado": resultado, "saida": saida}
    if medido is not None:
        g["medido"] = medido
    g["limiar"] = {"max_sem_texto_pct": MAX_SEM_TEXTO_PCT, "vao_ponte_s": VAO_PONTE_S,
                   "folga_lettering_s": FOLGA_LETTERING_S}
    if motivo:
        g["motivo"] = motivo
    if duracao is not None:
        g["duracao_s"] = round(duracao, 2)
    return g


def _uniao(intervalos):
    """Os intervalos [(a, b)] fundidos e ordenados."""
    saida = []
    for a, b in sorted(i for i in intervalos if i[1] > i[0]):
        if saida and a <= saida[-1][1]:
            saida[-1][1] = max(saida[-1][1], b)
        else:
            saida.append([a, b])
    return [(a, b) for a, b in saida]


def _dentro(t, intervalos, tol=TOLERANCIA_S):
    return any(a - tol <= t <= b + tol for a, b in intervalos)


def _janelas(timeline):
    """(isentas, texto): as janelas em que a palavra não precisa de legenda e todo o texto declarado na tela."""
    try:
        total = float(timeline["duracao_s"])
        hook = timeline["hook"]
        gancho = (float(hook["s"]), float(hook["e"]))
        letterings = [(float(l["s"]), float(l["s"]) + float(l["d"])) for l in timeline.get("letterings") or []]
        legendas = [(float(l["s"]), float(l["e"])) for l in timeline["legendas"] if not l.get("suprimida")]
        cta = timeline["cta"]
        cta_inicio = float(cta["inicio"])
        bloco_cta = next((float(b["s"]) for b in reversed(timeline.get("blocos") or []) if b.get("tipo") == "cta"), None)
    except (KeyError, TypeError, ValueError) as e:
        raise InsumoInvalido("a timeline não tem o campo %s (use o render/timeline.json do projeto)" % e)
    isentas = _uniao([gancho] + [(a - FOLGA_LETTERING_S, b + FOLGA_LETTERING_S) for a, b in letterings])
    texto = _uniao(isentas + legendas)
    antes_do_bloco = round(bloco_cta - cta_inicio, 3) if bloco_cta is not None and cta_inicio < bloco_cta - TOLERANCIA_S \
        else 0.0
    return isentas, texto, antes_do_bloco


def _vao_que_contem(t, texto, total):
    """(início, fim) do vão sem texto que contém `t`; None se `t` está sobre texto."""
    anterior = 0.0
    for a, b in texto:
        if t < a:
            return anterior, a
        if t <= b:
            return None
        anterior = b
    return anterior, max(total, t)


def medir(timeline, palavras):
    if not isinstance(timeline, dict):
        raise InsumoInvalido("a timeline não é um objeto JSON")
    if not isinstance(palavras, list) or not palavras:
        raise InsumoInvalido("o alinhamento não tem palavras (use o render/alinhamento.json do projeto)")
    isentas, texto, antes_do_bloco = _janelas(timeline)
    total = float(timeline["duracao_s"])
    avaliadas, sem_texto = 0, []
    for w in palavras:
        try:
            s, e = float(w["s"]), float(w["e"])
        except (KeyError, TypeError, ValueError):
            raise InsumoInvalido("palavra do alinhamento sem s e e: %r" % (w,))
        meio = (s + e) / 2.0
        if _dentro(meio, isentas):
            continue
        avaliadas += 1
        vao = _vao_que_contem(meio, texto, total)
        if vao is not None and vao[1] - vao[0] > VAO_PONTE_S + TOLERANCIA_S:
            sem_texto.append({"t": w.get("t"), "s": round(s, 2), "vao": [round(vao[0], 2), round(vao[1], 2)]})
    vaos = {}
    for p in sem_texto:
        vaos[tuple(p["vao"])] = vaos.get(tuple(p["vao"]), 0) + 1
    maiores = sorted(vaos.items(), key=lambda kv: kv[0][0] - kv[0][1])[:MAIORES_VAOS]
    return {"palavras": len(palavras), "palavras_avaliadas": avaliadas, "sem_texto": len(sem_texto),
            "percentual": round(100.0 * len(sem_texto) / avaliadas, 2) if avaliadas else 0.0,
            "vaos_com_fala": [{"de_s": a, "ate_s": b, "palavras": n} for (a, b), n in maiores],
            "exemplos": sem_texto[:8], "cta_antes_do_bloco_s": antes_do_bloco}


def _motivos(m):
    motivos = []
    if m["percentual"] > MAX_SEM_TEXTO_PCT:
        v = m["vaos_com_fala"][0] if m["vaos_com_fala"] else None
        motivos.append("%d de %d palavras faladas ficam sem texto na tela (%.1f%%, máximo %.1f%%)%s"
                       % (m["sem_texto"], m["palavras_avaliadas"], m["percentual"], MAX_SEM_TEXTO_PCT,
                          "; o maior vão vai de %.2f a %.2f s com %d palavras" % (v["de_s"], v["ate_s"], v["palavras"])
                          if v else ""))
    if m["cta_antes_do_bloco_s"] > 0:
        motivos.append("o CTA entra %.2f s antes do bloco cta (a âncora do CTA nunca é anterior ao início do bloco)"
                       % m["cta_antes_do_bloco_s"])
    return motivos


def rodar(timeline, palavras, projeto=None, etapa=ETAPA):
    """Confere a cobertura da fala pela `timeline` (dict) e pelas `palavras` do alinhamento ([{t, s, e}]). `projeto` é aceito
    por simetria com os outros gates: este não tem exceção. Insumo ruim vira ERRO (2), nunca PASS."""
    t0 = time.time()
    try:
        m = medir(timeline, palavras)
    except InsumoInvalido as e:
        return _gate("ERRO", 2, motivo=str(e))
    dur = time.time() - t0
    motivos = _motivos(m)
    if motivos:
        return _gate("REPROVA", 1, m, "; ".join(motivos), dur)
    return _gate("PASS", 0, m, duracao=dur)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Confere que toda palavra falada fora de lettering, gancho e CTA tem texto na tela.")
    ap.add_argument("--timeline", required=True, help="render/timeline.json do projeto")
    ap.add_argument("--alinhamento", required=True, help="render/alinhamento.json do projeto (as palavras da fala)")
    args = ap.parse_args(argv)
    try:
        tl = json.loads(Path(args.timeline).read_text(encoding="utf-8"))
        al = json.loads(Path(args.alinhamento).read_text(encoding="utf-8"))
        palavras = al.get("palavras") if isinstance(al, dict) else None
    except (OSError, ValueError) as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        return 2
    g = rodar(tl, palavras)
    if g["resultado"] == "PASS":
        m = g["medido"]
        print("PASSA: %d de %d palavras avaliadas sem texto (%.1f%%, máximo %.1f%%)"
              % (m["sem_texto"], m["palavras_avaliadas"], m["percentual"], MAX_SEM_TEXTO_PCT))
    elif g["resultado"] == "REPROVA":
        print("REPROVA: %s" % g["motivo"])
    else:
        print("ERRO de insumo: %s" % g["motivo"], file=sys.stderr)
    return g["saida"]


if __name__ == "__main__":
    sys.exit(main())
