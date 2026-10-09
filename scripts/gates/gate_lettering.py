#!/usr/bin/env python3
"""GATE DO LETTERING (W4.D, capacidades C7 e C9): lettering é pico, entra seco e legível, e o CTA tem seta que se mexe.

    python3 scripts/gates/gate_lettering.py antes  --timeline render/timeline.json [--projeto projeto.json] [--json]
    python3 scripts/gates/gate_lettering.py depois --timeline render/timeline.json --overlay render/overlay.mov
                                                   [--projeto projeto.json] [--json]
    exit 0 passa (ou pulado) · 1 reprova · 2 insumo inválido (arquivo ausente, ilegível ou fora do contrato)

## O que reprova (antes, sobre a timeline: etapa 7 da ordem dos gates do `vam montar`)

  contagem     KEYs no meio fora de 2 a 3 (a pilha conta como UMA), ou nenhuma KEY de CTA (`cta: true`).
               Regra de ouro 3 do diretor de arte: 1 KEY só desperdiça os claims fortes; 5 vira decoração.
  intervalo    menos de 8 s ENTREGUES entre o início de dois letterings (o tempo da timeline é o da footage a 1x,
               então divide pela aceleração do relógio). As linhas de uma mesma pilha não contam: é uma lista.
  conector     KEY terminada em conector (de, que, pra, com, e, o, a, um...): é frase cortada, não pico.
  linhas       KEY com mais de 2 linhas no estilo dela (estimativa pela largura média medida da fonte, de
               `cinema.lettering_estilos.linhas_estimadas`): 3 linhas já é parágrafo.
  legenda      qualquer legenda NÃO suprimida no tempo de um lettering: lettering e legenda nunca juntos (o
               lettering ganha, e a timeline marca `suprimida` na legenda).

Exceção só com motivo escrito, em `projeto.json` (`excecoes`): `lettering.contagem` e `lettering.intervalo` (um
anúncio de 15 s não comporta 3 KEYs a 8 s). Legenda, conector e linhas NÃO têm exceção.

Relatos (não reprovam, ficam em `medido.avisos`): estilo novo em split, close ou pilha (cai no editorial, o único
calibrado para essas faixas); lettering cuja faixa encosta na do CTA enquanto o CTA está na tela; KEY de número sem
o estilo `marcador` (o padrão do C9 para número e promessa); exceção usada.

## O que reprova (depois, sobre o overlay com alfa: etapa 17)

  legível      a tinta da KEY em +0,15 s da entrada é menos de 90% da tinta assentada (+0,60 s), medida na FAIXA
               do estilo; ou o lettering não tem tinta nenhuma na faixa ("sem tinta": não renderizou ou caiu
               fora da faixa declarada).
  seta         C9: a seta do CTA não se mexe. Mede a fileira da pílula (FAIXAS `cta_seta`) em 5 instantes a partir de
               0,6 s depois do CTA subir (a seta começa a quicar ali) e exige pelo menos SETA_MIN_PX pixels de tinta
               trocando entre dois instantes. A pílula é parada; só a seta muda.

Tinta é pixel com alfa de 190 ou mais (o mesmo critério do `gate_safezone`: o dim do lettering e o scrim ficam fora).

Resultado no formato do laudo (`contratos/laudo.schema.json`): nome, etapa, resultado, saida, medido, limiar e,
fora do PASS, motivo. Timeline 1x1 sai PULADO (o C7 é medido no 9x16; o quadrado é beta).
"""
import argparse
import json
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

if __name__ == "__main__":      # rodado direto: scripts/gates/gate_lettering.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cinema import lettering_estilos as LE  # noqa: E402

NOME_ANTES = "gate_lettering"
NOME_DEPOIS = "gate_lettering_depois"

KEYS_MIN, KEYS_MAX = 2, 3              # regra de ouro 3: 2 a 3 KEYs no meio + 1 de CTA
INTERVALO_MIN_S = 8.0                  # segundos ENTREGUES entre letterings
MAX_LINHAS = LE.MAX_LINHAS
TOLERANCIA_S = 0.02                    # menos que isto de encosto entre legenda e lettering é arredondamento
T_LEGIVEL = LE.ENTRADA_LEGIVEL_S       # 0,15 s
T_ASSENTADO = 0.60
FRACAO_LEGIVEL = LE.ALFA_LEGIVEL       # 0,90
TINTA_ALFA_MIN = 190
SETA_INICIO_S = 0.60                   # a seta começa a quicar 0,6 s depois do CTA subir (timeline.js)
SETA_PASSO_S = 0.225                   # um quarto do ciclo de 0,9 s: dois instantes vizinhos nunca coincidem
SETA_AMOSTRAS = 5
SETA_MIN_PX = 60                       # pixels de tinta que trocam entre dois instantes (a seta tem ~780 px)
EXCECOES_ACEITAS = ("lettering.contagem", "lettering.intervalo")

# conectores que não fecham uma KEY (sem acento, minúsculas)
CONECTORES = frozenset((
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "da", "do", "das", "dos", "e", "ou", "mas", "que",
    "pra", "para", "pro", "com", "sem", "em", "no", "na", "nos", "nas", "por", "pelo", "pela", "ao", "aos", "se",
    "nem", "porque", "como", "quando", "num", "numa", "seu", "sua", "meu", "minha", "te", "me", "lhe",
))


class InsumoInvalido(Exception):
    """Timeline, projeto ou overlay fora do contrato: vira ERRO (saída 2), nunca traceback."""


def _limiar():
    return {"keys_no_meio": [KEYS_MIN, KEYS_MAX], "keys_cta_min": 1, "intervalo_min_entregue_s": INTERVALO_MIN_S,
            "max_linhas": MAX_LINHAS, "legivel_em_s": T_LEGIVEL, "fracao_legivel_min": FRACAO_LEGIVEL,
            "seta_min_px": SETA_MIN_PX, "tinta_alfa_min": TINTA_ALFA_MIN}


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


def _numero(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _conferir_timeline(tl):
    if not isinstance(tl, dict):
        raise InsumoInvalido("a timeline não é um objeto JSON (use o render/timeline.json do projeto)")
    for campo in ("letterings", "legendas", "relogio"):
        if campo not in tl:
            raise InsumoInvalido("a timeline não tem o campo %r (use o render/timeline.json do projeto)" % campo)
    if not isinstance(tl["letterings"], list) or not isinstance(tl["legendas"], list):
        raise InsumoInvalido("'letterings' e 'legendas' da timeline têm que ser listas")
    acel = (tl.get("relogio") or {}).get("aceleracao")
    if not _numero(acel) or acel <= 0:
        raise InsumoInvalido("o relógio da timeline não tem 'aceleracao' numérica positiva")
    for i, l in enumerate(tl["letterings"]):
        if not isinstance(l, dict):
            raise InsumoInvalido("lettering #%d não é um objeto" % i)
        for campo in ("s", "d"):
            if not _numero(l.get(campo)):
                raise InsumoInvalido("lettering #%d (%s): o campo %s não é número" % (i, l.get("id"), campo))
        if not isinstance(l.get("key"), str) or not l["key"].strip():
            raise InsumoInvalido("lettering #%d (%s) sem KEY" % (i, l.get("id")))
        try:
            LE.efetivo(l.get("estilo"))
        except ValueError as e:
            raise InsumoInvalido("lettering #%d (%s): %s" % (i, l.get("id"), e))


def excecoes_validas(projeto):
    """{regra: motivo} das exceções de lettering com motivo escrito."""
    saida = {}
    for x in (projeto or {}).get("excecoes") or []:
        if isinstance(x, dict) and x.get("regra") in EXCECOES_ACEITAS and str(x.get("motivo") or "").strip():
            saida[x["regra"]] = str(x["motivo"]).strip()
    return saida


def _pulado(tl, etapa, nome):
    if tl.get("formato") == "1x1":
        return _gate("PULADO", 0, etapa, nome,
                     motivo="formato 1x1: o C7 é medido no 9x16; o quadrado é beta, sem gate cinematográfico")
    return None


def _sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def ultima_palavra(key):
    palavras = re.findall(r"[^\W\d_]+|\d+", _sem_acento(str(key).replace("*", "")).lower())
    return palavras[-1] if palavras else ""


def grupos(letterings):
    """Letterings agrupados para contar e espaçar: a pilha (mesmo `pilha`) é um grupo só. [(início, [itens])]."""
    por_pilha, ordem = {}, []
    for l in sorted(letterings, key=lambda x: x["s"]):
        p = l.get("pilha")
        if p:
            if p not in por_pilha:
                por_pilha[p] = [l["s"], []]
                ordem.append(por_pilha[p])
            por_pilha[p][1].append(l)
        else:
            ordem.append([l["s"], [l]])
    return [(s, itens) for s, itens in ordem]


def _sobrepoe(a0, a1, b0, b1, tol=TOLERANCIA_S):
    return min(a1, b1) - max(a0, b0) > tol


def _faixas_encostam(f, g):
    return min(f["x1"], g["x1"]) > max(f["x0"], g["x0"]) and min(f["y1"], g["y1"]) > max(f["y0"], g["y0"])


def _no_split(tl, t):
    return any(_numero(j.get("s")) and j["s"] <= t < j.get("e", -1) for j in tl.get("janelas_split") or [])


def _faixa_cta(tl):
    cta = tl.get("cta")
    if not isinstance(cta, dict) or not _numero(cta.get("inicio")):
        return None, None
    return cta["inicio"], LE.FAIXAS["cta_split" if _no_split(tl, cta["inicio"]) else "cta"]


def avaliar_antes(tl, projeto=None):
    """(motivos, medido) da timeline. Função pura: a CLI e o orquestrador chamam `rodar_antes`."""
    acel = float(tl["relogio"]["aceleracao"])
    exc = excecoes_validas(projeto)
    motivos, avisos = [], []
    letts = tl["letterings"]
    meio = [l for l in letts if not l.get("cta")]
    ctas = [l for l in letts if l.get("cta")]
    gr = grupos(meio)

    # contagem
    if not (KEYS_MIN <= len(gr) <= KEYS_MAX):
        m = "contagem: %d KEY(s) no meio (a pilha conta como uma), o C7 pede de %d a %d" % (len(gr), KEYS_MIN, KEYS_MAX)
        if "lettering.contagem" in exc:
            avisos.append("exceção lettering.contagem usada: %s (%s)" % (exc["lettering.contagem"], m))
        else:
            motivos.append(m)
    if not ctas:
        m = "contagem: nenhuma KEY de CTA (o último bloco leva lettering com `cta: true`)"
        if "lettering.contagem" in exc:
            avisos.append("exceção lettering.contagem usada: %s (%s)" % (exc["lettering.contagem"], m))
        else:
            motivos.append(m)

    # intervalo (entregue), entre grupos, CTA incluído
    todos = grupos(letts)
    intervalos = []
    for (s0, i0), (s1, i1) in zip(todos, todos[1:]):
        entregue = (s1 - s0) / acel
        intervalos.append({"de": i0[0].get("id"), "ate": i1[0].get("id"), "entregue_s": round(entregue, 2)})
        if entregue < INTERVALO_MIN_S - 1e-9:
            m = ("intervalo: '%s' e '%s' a %.2f s entregues (%.2f s na timeline a %.2fx), o mínimo é %.0f s"
                 % (i0[0]["key"], i1[0]["key"], entregue, s1 - s0, acel, INTERVALO_MIN_S))
            if "lettering.intervalo" in exc:
                avisos.append("exceção lettering.intervalo usada: %s (%s)" % (exc["lettering.intervalo"], m))
            else:
                motivos.append(m)

    # KEY: conector e linhas
    linhas_medidas = []
    for l in letts:
        ult = ultima_palavra(l["key"])
        if ult in CONECTORES:
            motivos.append("conector: a KEY '%s' termina em '%s' (frase cortada não é pico)" % (l["key"], ult))
        n = LE.linhas_estimadas(l["key"], l.get("estilo") or LE.PADRAO, split=bool(l.get("split")))
        linhas_medidas.append({"id": l.get("id"), "linhas": n})
        if n > MAX_LINHAS:
            motivos.append("linhas: a KEY '%s' ocupa %d linhas no estilo %s (máximo %d)"
                           % (l["key"], n, LE.efetivo(l.get("estilo"), bool(l.get("split"))), MAX_LINHAS))

    # nunca junto com legenda
    for l in letts:
        a0, a1 = l["s"], l["s"] + l["d"]
        for leg in tl["legendas"]:
            if not isinstance(leg, dict) or leg.get("suprimida") or not (_numero(leg.get("s")) and _numero(leg.get("e"))):
                continue
            if _sobrepoe(a0, a1, leg["s"], leg["e"]):
                motivos.append("legenda: '%s' (%.2f a %.2f s) na tela junto com a legenda '%s' (%.2f a %.2f s);"
                               " lettering e legenda nunca juntos"
                               % (l["key"], a0, a1, str(leg.get("texto") or "")[:40], leg["s"], leg["e"]))
                break

    # relatos
    cta_ini, faixa_cta = _faixa_cta(tl)
    for l in letts:
        est = l.get("estilo") or LE.PADRAO
        quadro = [nome for nome, sim in (("split", l.get("split")), ("close", l.get("baixo")),
                                         ("pilha", l.get("pilha"))) if sim]
        if est != LE.PADRAO and quadro:
            avisos.append("'%s': estilo %s em %s vira serif_editorial (o único calibrado para essa faixa)"
                          % (l["key"], est, "/".join(quadro)))
        f = LE.faixa(est, split=bool(l.get("split")), pilha=bool(l.get("pilha")), baixo=bool(l.get("baixo")))
        if faixa_cta and l["s"] + l["d"] > cta_ini + TOLERANCIA_S and _faixas_encostam(f, faixa_cta):
            avisos.append("'%s' (%.2f a %.2f s) divide a faixa do CTA, que sobe em %.2f s: confira no quadro se a"
                          " pílula e o logo não ficam por cima do lettering" % (l["key"], l["s"], l["s"] + l["d"], cta_ini))
        if re.search(r"\d", l["key"]) and est != "marcador" and not l.get("cta"):
            avisos.append("'%s' é KEY de número: o padrão do C9 é o estilo marcador" % l["key"])
    if faixa_cta is None:
        motivos.append("seta: a timeline não tem CTA (o C9 pede a seta animada no CTA final)")

    medido = {"keys_no_meio": len(gr), "keys_cta": len(ctas), "intervalos": intervalos,
              "linhas": linhas_medidas, "avisos": avisos}
    return motivos, medido


def rodar_antes(timeline, projeto=None, *, nome=NOME_ANTES, etapa="antes"):
    """O gate sobre a timeline, no formato do laudo. Insumo ruim vira ERRO (saída 2)."""
    t0 = time.time()
    try:
        _conferir_timeline(timeline)
        pulado = _pulado(timeline, etapa, nome)
        if pulado:
            return pulado
        motivos, medido = avaliar_antes(timeline, projeto)
    except InsumoInvalido as e:
        return _gate("ERRO", 2, etapa, nome, motivo=str(e))
    except (KeyError, TypeError, ValueError) as e:
        return _gate("ERRO", 2, etapa, nome, motivo="falha ao ler a timeline: %s" % e)
    dur = time.time() - t0
    if motivos:
        return _gate("REPROVA", 1, etapa, nome, medido, "; ".join(motivos), dur)
    return _gate("PASS", 0, etapa, nome, medido, duracao=dur)


# --- depois: o overlay --------------------------------------------------------------------------------------------

def _tinta(quadro, f):
    import numpy as np
    a = np.asarray(quadro)
    if a.ndim == 3 and a.shape[2] >= 4:
        a = a[:, :, 3]
    elif a.ndim != 2:
        raise InsumoInvalido("o quadro do overlay não tem canal alfa (forma %s)" % (a.shape,))
    return a[f["y0"]:f["y1"] + 1, f["x0"]:f["x1"] + 1] >= TINTA_ALFA_MIN


def _leitor_padrao():
    from gates import gate_safezone as SZ
    return SZ.ler_overlay_padrao


def _ler(leitor, overlay, t):
    try:
        return leitor(overlay, t)
    except InsumoInvalido:
        raise
    except Exception as e:      # noqa: BLE001 - o leitor externo pode falhar de muitos jeitos; vira ERRO de insumo
        try:
            from gates.gate_safezone import InsumoInvalido as SZErro
            if isinstance(e, SZErro):
                raise InsumoInvalido(str(e))
        except ImportError:
            pass
        raise InsumoInvalido("falha ao ler o overlay em %.2f s: %s" % (t, e))


def avaliar_depois(overlay, tl, leitor):
    """(motivos, medido) do overlay: legibilidade de cada lettering em +0,15 s e o movimento da seta do CTA."""
    import numpy as np
    motivos, legib = [], []
    for l in tl["letterings"]:
        f = LE.faixa(l.get("estilo") or LE.PADRAO, split=bool(l.get("split")), pilha=bool(l.get("pilha")),
                     baixo=bool(l.get("baixo")))
        t_ass = l["s"] + min(T_ASSENTADO, max(l["d"] - 0.05, T_LEGIVEL))
        cedo = int(_tinta(_ler(leitor, overlay, l["s"] + T_LEGIVEL), f).sum())
        assentada = int(_tinta(_ler(leitor, overlay, t_ass), f).sum())
        fr = round(cedo / assentada, 4) if assentada else 0.0
        legib.append({"id": l.get("id"), "key": l["key"], "tinta_015_px": cedo, "tinta_assentada_px": assentada,
                      "fracao_015": fr})
        if not assentada:
            motivos.append("legível: '%s' sem tinta na faixa do estilo em %.2f s (não renderizou ou saiu da faixa)"
                           % (l["key"], t_ass))
        elif fr < FRACAO_LEGIVEL:
            motivos.append("legível: '%s' com %.0f%% da tinta em +0,15 s (mínimo %.0f%%): a entrada atrasa a leitura"
                           % (l["key"], 100 * fr, 100 * FRACAO_LEGIVEL))
    seta = {"movimento_px": 0, "instantes": []}
    cta_ini, _f = _faixa_cta(tl)
    if cta_ini is not None:
        fs = LE.FAIXAS["cta_seta_split" if _no_split(tl, cta_ini) else "cta_seta"]
        fim = float(tl.get("duracao_s") or cta_ini + 5)
        ts = [cta_ini + SETA_INICIO_S + k * SETA_PASSO_S for k in range(SETA_AMOSTRAS)]
        ts = [t for t in ts if t < fim - 0.04]
        mascaras = [_tinta(_ler(leitor, overlay, t), fs) for t in ts]
        mov = max([int(np.logical_xor(a, b).sum()) for a, b in zip(mascaras, mascaras[1:])] or [0])
        seta = {"movimento_px": mov, "instantes": [round(t, 3) for t in ts], "faixa": fs}
        if mov < SETA_MIN_PX:
            motivos.append("seta: a seta do CTA não se mexe (%d px de tinta trocando entre %d instantes, mínimo %d):"
                           " o C9 pede movimento medido" % (mov, len(ts), SETA_MIN_PX))
    return motivos, {"legibilidade": legib, "seta_cta": seta}


def rodar_depois(overlay, timeline, projeto=None, *, leitor_overlay=None, nome=NOME_DEPOIS, etapa="depois"):
    """O gate sobre o overlay (quadro RGBA 1080x1920 por `leitor_overlay(overlay, t)`; padrão: ffmpeg)."""
    t0 = time.time()
    try:
        _conferir_timeline(timeline)
        pulado = _pulado(timeline, etapa, nome)
        if pulado:
            return pulado
        try:
            import numpy  # noqa: F401
        except ImportError:
            raise InsumoInvalido("falta o numpy para medir a tinta: rode `bash setup.sh`")
        if leitor_overlay is None:
            if not Path(str(overlay)).is_file():
                raise InsumoInvalido("o overlay não existe: %s" % overlay)
            leitor_overlay = _leitor_padrao()
        motivos, medido = avaliar_depois(overlay, timeline, leitor_overlay)
    except InsumoInvalido as e:
        return _gate("ERRO", 2, etapa, nome, motivo=str(e))
    except (KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError) as e:
        return _gate("ERRO", 2, etapa, nome, motivo="falha ao medir o overlay %s: %s" % (overlay, e))
    dur = time.time() - t0
    if motivos:
        return _gate("REPROVA", 1, etapa, nome, medido, "; ".join(motivos), dur)
    return _gate("PASS", 0, etapa, nome, medido, duracao=dur)


# --- linha de comando ---------------------------------------------------------------------------------------------

def _ler_json(caminho, o_que):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise InsumoInvalido("não consegui ler %s (%s): %s" % (o_que, caminho, e))


def imprimir(g, como_json):
    if como_json:
        print(json.dumps(g, ensure_ascii=False))
    elif g["resultado"] == "PASS":
        med = g["medido"]
        if "legibilidade" in med:
            print("PASSA: %d lettering(s) legíveis em %.2f s e a seta do CTA se mexe (%d px)"
                  % (len(med["legibilidade"]), T_LEGIVEL, med["seta_cta"]["movimento_px"]))
        else:
            print("PASSA: %d KEY(s) no meio + %d de CTA, espaçadas e sem legenda junto" % (med["keys_no_meio"], med["keys_cta"]))
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
    ap = argparse.ArgumentParser(description="Lettering de pico (C7) e seta do CTA (C9).")
    sub = ap.add_subparsers(dest="etapa", required=True)
    a = sub.add_parser("antes", help="confere a timeline, sem render")
    d = sub.add_parser("depois", help="mede a tinta do overlay")
    d.add_argument("--overlay", required=True, help="o overlay com canal alfa (.mov)")
    for p in (a, d):
        p.add_argument("--timeline", required=True, help="render/timeline.json do projeto")
        p.add_argument("--projeto", help="projeto.json (exceções com motivo)")
        p.add_argument("--json", action="store_true", help="imprime o gate no formato do laudo, em JSON")
    args = ap.parse_args(argv)
    try:
        tl = _ler_json(args.timeline, "a timeline")
        proj = _ler_json(args.projeto, "o projeto") if args.projeto else None
    except InsumoInvalido as e:
        g = _gate("ERRO", 2, args.etapa, NOME_ANTES if args.etapa == "antes" else NOME_DEPOIS, motivo=str(e))
        return imprimir(g, args.json)
    if args.etapa == "antes":
        g = rodar_antes(tl, proj)
    else:
        g = rodar_depois(args.overlay, tl, proj)
    return imprimir(g, args.json)


if __name__ == "__main__":
    sys.exit(main())
