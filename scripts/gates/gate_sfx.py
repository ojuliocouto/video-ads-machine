#!/usr/bin/env python3
"""GATE DE SFX (C11): o som tem função, cabe no teto e não cai onde o diretor já reprovou.

    python3 scripts/gates/gate_sfx.py <slug> [--estado _local] [--biblioteca pasta-de-wavs]
    exit 0 passa · 1 reprova · 2 insumo inválido (sem timeline.json, timeline fora do contrato, wav ausente)

Lê a seção `sfx` do render/timeline.json (e os letterings, segmentos, CTA e relógio dele) e reprova quando:

  efeito          o efeito não é riser, tick ou boom. O WHOOSH está desligado por ordem do diretor (31/08);
  nivel           evento ou wav fora de -38 a -31 dBFS RMS. As duas âncoras humanas: -40,2 é inaudível
                  (20/08) e -27,2 "parece um tiro" (27/08);
  densidade       dois eventos a menos de 4 s no arquivo ENTREGUE. A pilha de ticks conta como um evento só
                  (ela é um gesto) e dentro dela os ticks ficam a 0,5 s ou mais um do outro;
  volta_ao_avatar tick ou boom a menos de 0,25 s da volta de um insert para o apresentador. O riser não
                  entra nesta regra: quem manda nele é o CTA;
  funcao          o efeito não serve à função que declara: o riser tem que cair 1,0 s (entregue) antes do
                  CTA, o tick tem que cair numa linha de pilha, o boom na entrada de uma KEY gigante-atrás;
  biblioteca      (com `--biblioteca`) algum dos três wavs fora da faixa de nível.

Peça sem nenhum som PASSA: vazio é melhor que inventar efeito.

As regras de plano e de gate vêm do mesmo módulo (`cinema.sfx_plano`): toda lista que o `plano_de_sfx`
produz passa aqui, por construção, e um teste confere em 40 timelines. O que reprova é timeline editado à
mão, plano velho depois de o lettering mudar e biblioteca regravada com nível errado.

Resultado: `Resultado(ok, motivo, detalhes)`. `detalhes["estado"]` é PASS ou REPROVA; `falhas` traz
{regra, motivo} de cada reprovação (o motivo junta todas); `medido` e `limiar` vão para o laudo. A CLI
grava em status.json (etapa `gate_sfx`).
"""
import argparse
import os
import sys
from collections import namedtuple
from pathlib import Path

if __name__ == "__main__":      # rodado direto: scripts/gates/gate_sfx.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cinema import sfx_plano  # noqa: E402
from contratos.validar import validar  # noqa: E402
from projeto import pastas, status  # noqa: E402

NOME = "gate_sfx"
ETAPA = "gate_sfx"
Resultado = namedtuple("Resultado", "ok motivo detalhes")

TOLERANCIA_RISER_S = 0.1        # o riser cai 1,0 s antes do CTA, com folga de 0,1 s para o arredondamento
TOLERANCIA_LETTERING_S = 0.002  # tick e boom caem NA entrada do lettering (o plano grava com 3 casas)
EPS = 1e-9


class InsumoInvalido(Exception):
    """Falta arquivo ou ele não cumpre o contrato: não dá nem para reprovar (exit 2)."""


def _numero(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x


def avaliar(timeline, biblioteca=None, medir_wav=None):
    """Confere a seção `sfx` de um timeline (dict). `biblioteca` é a pasta dos wavs (opcional);
    `medir_wav(caminho) -> dBFS` troca a medição (os testes passam uma função simulada)."""
    accel, a0 = sfx_plano.relogio_de(timeline)
    eventos = sorted(timeline.get("sfx") or [], key=lambda e: e["t"])
    letterings = timeline.get("letterings") or []
    cta = timeline.get("cta") or {}
    voltas_ent = [(v, sfx_plano.para_entregue(v, accel, a0)) for v in sfx_plano.instantes_de_volta(timeline)]
    falhas = []

    def falha(regra, motivo):
        falhas.append({"regra": regra, "motivo": motivo})

    def quando(e):
        return "%.2f s da footage, %.2f s no arquivo entregue" % (e["t"], sfx_plano.para_entregue(e["t"], accel, a0))

    # 1. efeito
    for e in eventos:
        if e["efeito"] == "whoosh":
            falha("efeito", "whoosh em %s: o whoosh está DESLIGADO por ordem do diretor (reprovado em 27/08 e "
                  "de novo em 31/08). Som tem função: riser, tick ou boom" % quando(e))
        elif e["efeito"] not in sfx_plano.EFEITOS_LIGADOS:
            falha("efeito", "efeito %r em %s não existe no som com função (riser, tick e boom)" % (e["efeito"], quando(e)))
    validos = [e for e in eventos if e["efeito"] in sfx_plano.EFEITOS_LIGADOS]

    # 2. nível de cada evento
    for e in eventos:
        n = e.get("nivel_dbfs")
        if not _numero(n) or n < sfx_plano.NIVEL_MIN_DBFS - EPS or n > sfx_plano.NIVEL_MAX_DBFS + EPS:
            falha("nivel", "o %s em %s está em %s dBFS RMS, fora de %.0f a %.0f (-40,2 é inaudível; -27,2 'parece um "
                  "tiro')" % (e["efeito"], quando(e), "%.1f" % n if _numero(n) else "?",
                              sfx_plano.NIVEL_MIN_DBFS, sfx_plano.NIVEL_MAX_DBFS))

    # 3. função
    por_lettering = {}
    for l in letterings:
        por_lettering.setdefault("pilha" if l.get("pilha") else "outro", []).append(l)
    pilha_de = {}                                    # índice do evento -> id da pilha (para a densidade)
    n_risers = 0
    for i, e in enumerate(validos):
        ef, t = e["efeito"], e["t"]
        if e.get("funcao") != sfx_plano.FUNCAO[ef]:
            falha("funcao", "o %s em %s declara a função %r; o %s serve a %r" %
                  (ef, quando(e), e.get("funcao"), ef, sfx_plano.FUNCAO[ef]))
            continue
        if ef == "riser":
            n_risers += 1
            if cta.get("inicio") is None:
                falha("funcao", "riser em %s e o timeline não tem CTA" % quando(e))
                continue
            antes = (sfx_plano.para_entregue(cta["inicio"], accel, a0) - sfx_plano.para_entregue(t, accel, a0))
            if abs(antes - sfx_plano.RISER_ANTES_S) > TOLERANCIA_RISER_S + EPS:
                falha("funcao", "o riser em %s cai %.2f s antes do CTA; tem que cair 1,0 s (entregue) antes, para "
                      "chegar na virada" % (quando(e), antes))
        elif ef == "tick":
            casam = [l for l in por_lettering.get("pilha", []) if abs(l["s"] - t) <= TOLERANCIA_LETTERING_S]
            if not casam:
                falha("funcao", "o tick em %s não cai na entrada de nenhuma linha de pilha" % quando(e))
            else:
                pilha_de[i] = casam[0]["pilha"]
        elif ef == "boom":
            casam = [l for l in letterings if l.get("estilo") == "gigante_atras"
                     and abs(l["s"] - t) <= TOLERANCIA_LETTERING_S]
            if not casam:
                falha("funcao", "o boom em %s não cai na entrada de uma KEY gigante-atrás" % quando(e))
    if n_risers > 1:
        falha("funcao", "%d risers na peça: só o do CTA existe" % n_risers)

    # 4. densidade (no arquivo entregue)
    ent = [sfx_plano.para_entregue(e["t"], accel, a0) for e in validos]
    menor = None
    for i in range(len(validos)):
        for j in range(i + 1, len(validos)):
            mesma_pilha = i in pilha_de and j in pilha_de and pilha_de[i] == pilha_de[j]
            d = abs(ent[j] - ent[i])
            if mesma_pilha:
                if d < sfx_plano.INTERVALO_TICK_S - EPS:
                    falha("densidade", "dois ticks da mesma pilha a %.2f s um do outro (%s e %s): o mínimo é 0,5 s "
                          "entre dois ticks" % (d, quando(validos[i]), quando(validos[j])))
            elif d < sfx_plano.INTERVALO_MIN_S - EPS:
                falha("densidade", "o %s em %s e o %s em %s ficam a %.2f s um do outro: o teto é 1 evento a cada 4 s "
                      "(a pilha de ticks conta como um)" %
                      (validos[i]["efeito"], quando(validos[i]), validos[j]["efeito"], quando(validos[j]), d))
            if not mesma_pilha and (menor is None or d < menor):
                menor = d

    # 5. nunca na volta pro avatar (o riser é do CTA)
    for e, t_ent in zip(validos, ent):
        if e["efeito"] == "riser":
            continue
        for v, v_ent in voltas_ent:
            if abs(t_ent - v_ent) <= sfx_plano.TOLERANCIA_VOLTA_S + EPS:
                falha("volta_ao_avatar", "o %s em %s cai a %.2f s da volta pro avatar (footage %.2f s): a volta é "
                      "respiro, nunca som" % (e["efeito"], quando(e), abs(t_ent - v_ent), v))
                break

    # 6. a biblioteca
    medidos = {}
    if biblioteca is not None:
        for ef in sfx_plano.EFEITOS_LIGADOS:
            wav = Path(biblioteca) / sfx_plano.ARQUIVO[ef]
            if medir_wav is None:
                if not wav.is_file():
                    raise InsumoInvalido("falta %s em %s: rode python3 scripts/cinema/sfx_plano.py --gerar %s"
                                         % (wav.name, biblioteca, biblioteca))
                try:
                    nivel = sfx_plano.rms_dbfs(wav)
                except RuntimeError as err:
                    raise InsumoInvalido(str(err))
            else:
                nivel = medir_wav(wav)
            medidos[ef] = round(float(nivel), 2)
            if nivel < sfx_plano.NIVEL_MIN_DBFS - EPS or nivel > sfx_plano.NIVEL_MAX_DBFS + EPS:
                falha("biblioteca", "o wav %s está em %.1f dBFS RMS, fora de %.0f a %.0f: regere a biblioteca "
                      "(python3 scripts/cinema/sfx_plano.py --gerar --forcar)" %
                      (ef, nivel, sfx_plano.NIVEL_MIN_DBFS, sfx_plano.NIVEL_MAX_DBFS))

    detalhes = {
        "estado": "REPROVA" if falhas else "PASS",
        "falhas": falhas,
        "medido": {"eventos": len(eventos), "por_efeito": {ef: sum(1 for e in eventos if e["efeito"] == ef)
                                                            for ef in sfx_plano.EFEITOS_LIGADOS},
                   "menor_intervalo_entre_grupos_s": round(menor, 3) if menor is not None else None,
                   "biblioteca": medidos},
        "limiar": {"nivel_dbfs": [sfx_plano.NIVEL_MIN_DBFS, sfx_plano.NIVEL_MAX_DBFS],
                   "intervalo_s": sfx_plano.INTERVALO_MIN_S, "intervalo_tick_s": sfx_plano.INTERVALO_TICK_S,
                   "tolerancia_volta_s": sfx_plano.TOLERANCIA_VOLTA_S, "riser_antes_s": sfx_plano.RISER_ANTES_S},
    }
    return Resultado(not falhas, "; ".join(f["motivo"] for f in falhas), detalhes)


def rodar(pastas_projeto, biblioteca=None, medir_wav=None):
    """Confere o render/timeline.json do projeto. InsumoInvalido sem o arquivo ou fora do contrato."""
    pj = pastas_projeto
    if not pj.timeline.is_file():
        raise InsumoInvalido("o timeline.json não existe em %s: monte o timeline antes de conferir o som" % pj.render_dir)
    try:
        t = status.ler_json(pj.timeline)
    except (OSError, ValueError) as e:
        raise InsumoInvalido("não consegui ler %s: %s" % (pj.timeline, e))
    # O contrato também recusa efeito fora de riser/tick/boom e nível fora de -38 a -31. Estes dois são
    # DEFEITO DO MATERIAL, não ferramenta quebrada: o gate os reprova (exit 1) com a explicação própria.
    erros = [e for e in validar("timeline", t) if not (e.caminho.startswith("$.sfx[") and e.campo in ("efeito", "nivel_dbfs"))]
    if erros:
        raise InsumoInvalido("o timeline.json não cumpre o contrato:\n  " + "\n  ".join(str(e) for e in erros[:6]))
    return avaliar(t, biblioteca=biblioteca, medir_wav=medir_wav)


def _registrar(pj, r):
    if r.ok:
        status.registrar(pj, ETAPA, "ok", detalhes=r.detalhes)
    else:
        status.registrar(pj, ETAPA, "falhou", motivo=r.motivo[:600], detalhes=r.detalhes)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Confere o som com função do timeline do projeto.")
    ap.add_argument("slug")
    ap.add_argument("--estado", help="pasta _local (padrão: a do repo)")
    ap.add_argument("--biblioteca", help="pasta dos wavs (riser, tick, boom): confere o nível de cada um")
    args = ap.parse_args(argv)
    try:
        pj = pastas.projeto(args.slug, args.estado)
    except ValueError as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        return 2
    try:
        r = rodar(pj, biblioteca=args.biblioteca)
    except InsumoInvalido as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        if pj.raiz.is_dir():
            status.registrar(pj, ETAPA, "bloqueado", motivo=str(e)[:400])
        return 2
    _registrar(pj, r)
    if r.ok:
        print("PASSA: %d evento(s) de som com função, dentro de todas as regras" % r.detalhes["medido"]["eventos"])
        return 0
    for f in r.detalhes["falhas"]:
        print("REPROVA (%s): %s" % (f["regra"], f["motivo"]))
    return 1


if __name__ == "__main__":
    sys.exit(main())
