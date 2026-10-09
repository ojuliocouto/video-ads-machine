#!/usr/bin/env python3
"""Plano de SFX com FUNÇÃO (C11): som que informa, nunca som de transição.

    riser   1,0 s antes do CTA                      (funcao cta)
    tick    uma batida por linha de pilha           (funcao pilha)
    boom    na entrada da KEY gigante-atrás         (funcao key_gigante)

O WHOOSH ESTÁ DESLIGADO. O diretor reprovou duas vezes (27/08: "parece um tiro", RMS -27,2 dBFS; 31/08:
"tem um som nas transições que tá me irritando", depois de duas calibragens por medição). Efeito de
transição não é informação. Não existe whoosh neste módulo, nem na biblioteca, nem no plano.

Regras (cada uma nasce de um defeito ou de uma ordem do diretor, e o `gate_sfx` confere as mesmas):
  - nível de -38 a -31 dBFS RMS por wav. As duas âncoras humanas: -40,2 é inaudível (20/08) e -27,2 é
    "parece um tiro" (27/08), porque os efeitos caem em pausa de fala e aparecem SOZINHOS: o que vale é o
    nível absoluto tocando só, não a relação com a voz;
  - no máximo 1 evento a cada 4 s no arquivo ENTREGUE (o banco de referências: "sutil, nunca em todo corte");
  - nunca na volta de um insert para o apresentador: a volta é respiro.

Três decisões deste módulo (da unidade W4.B, registradas porque o texto do plano não as resolve):
  1. "tick por linha de pilha" e "1 evento a cada 4 s" não se anulam: a PILHA conta como UM evento para o
     teto (ela é um gesto só), e dentro dela os ticks seguem as linhas, com no mínimo 0,5 s entre dois.
     O exemplo válido do contrato (ticks a 14,6, 15,9 e 17,1 s da footage) só fecha com esta leitura.
  2. A pilha é ATÔMICA na disputa por espaço: ou entra inteira ou sai inteira. Meia pilha tocando é um
     ritmo que ninguém escolheu. Quem sai da volta pro avatar, ao contrário, é só o evento que caiu lá.
  3. O riser não obedece à regra da volta: quem manda nele é o CTA, e é normal o CTA vir logo depois de
     um insert (o exemplo do contrato tem o riser 0,15 s depois da volta). "Nunca na volta" vale para o
     tick e o boom.

Prioridade na disputa por espaço: riser (a virada importa mais), depois boom, depois a pilha de ticks.

Relógio: os tempos do timeline.json são da FOOTAGE a 1x. A distância de 1,0 s e o teto de 4 s valem no
arquivo ENTREGUE (o que o espectador ouve), então o plano converte com (t - a0) / aceleracao nos dois
sentidos. O som entra DEPOIS da aceleração, senão o efeito acelera junto e desafina.

Biblioteca: riser e tick vêm das receitas de `som_cortes.EFEITOS` (que não se toca); o boom nasce aqui.
Tudo sintetizado com ffmpeg, sem licença de terceiro, reproduzível. Gera o que faltar:
    python3 scripts/cinema/sfx_plano.py --gerar [pasta]
"""
import argparse
import os
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

if __name__ == "__main__":      # rodado direto: scripts/cinema/sfx_plano.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

import som_cortes  # noqa: E402

EFEITOS_LIGADOS = ("riser", "tick", "boom")
ARQUIVO = {"riser": "riser.wav", "tick": "tick.wav", "boom": "boom.wav"}
FUNCAO = {"riser": "cta", "tick": "pilha", "boom": "key_gigante"}
PRIORIDADE = {"riser": 3, "boom": 2, "tick": 1}

RISER_ANTES_S = som_cortes.RISER_ANTES        # 1,0 s: o riser sobe ANTES da virada, senão chega atrasado
INTERVALO_MIN_S = som_cortes.INTERVALO_MIN    # 4,0 s entre dois eventos (a pilha conta como um)
INTERVALO_TICK_S = 0.5                        # entre dois ticks da mesma pilha: nunca mais de 2 por segundo
TOLERANCIA_VOLTA_S = 0.25                     # a volta pro avatar é um respiro de um quarto de segundo
NIVEL_MIN_DBFS, NIVEL_MAX_DBFS = -38.0, -31.0
EPS = 1e-9

# O boom: pancada grave (78 Hz caindo) com decaimento exponencial. Pico em -22 dBFS, RMS -34 dBFS.
RECEITA_BOOM = (0.7,
                "aevalsrc=exprs='sin(2*PI*(78*t-60*t*t))*exp(-5.5*t)':sample_rate=48000:duration=0.7,"
                "lowpass=f=220,afade=t=in:st=0:d=0.004,afade=t=out:st=0.5:d=0.2:curve=qsin,"
                "volume=-22dB")
RECEITAS = {"riser": som_cortes.EFEITOS["riser.wav"], "tick": som_cortes.EFEITOS["tick.wav"], "boom": RECEITA_BOOM}

# RMS (dBFS) de cada wav como a receita o produz. É o valor que o plano grava em `nivel_dbfs`. Um teste
# mede a biblioteca gerada e reprova se a tabela descrever outro arquivo (tolerância de 0,3 dB).
NIVEIS_DBFS = {"riser": -34.3, "tick": -33.8, "boom": -34.0}


class BibliotecaIncompleta(RuntimeError):
    """Falta wav na pasta de efeitos."""


# --- relógio --------------------------------------------------------------------------------------

def relogio_de(timeline):
    """(aceleração, a0) do relógio do timeline."""
    r = timeline["relogio"]
    return float(r["aceleracao"]), float(r.get("a0", 0.0))


def para_entregue(t, aceleracao, a0=0.0):
    """Instante da footage a 1x -> instante no arquivo entregue."""
    return (float(t) - a0) / aceleracao


def para_footage(t_entregue, aceleracao, a0=0.0):
    """Instante no arquivo entregue -> instante da footage a 1x."""
    return a0 + float(t_entregue) * aceleracao


def instantes_de_volta(timeline):
    """Onde o apresentador volta depois de um insert, no relógio da footage: o começo de cada segmento
    `apresentador` que vem logo depois de um `insert`. Insert que passa para outro insert não conta."""
    segs = timeline.get("segmentos") or []
    return [float(b["s"]) for a, b in zip(segs, segs[1:])
            if a.get("tipo") == "insert" and b.get("tipo") == "apresentador"]


# --- o plano --------------------------------------------------------------------------------------

def _unidade(efeito, tempos_footage, aceleracao, a0):
    # O instante entregue sai do tempo JÁ ARREDONDADO (o que vai para o timeline e o gate lê): senão um par a
    # 4,00004 s passava aqui e o gate o via a 3,9997 s.
    arredondados = [round(t, 3) for t in tempos_footage]
    return {"efeito": efeito, "prioridade": PRIORIDADE[efeito],
            "eventos": [(t, para_entregue(t, aceleracao, a0)) for t in arredondados]}


def _longe_das_voltas(t_ent, voltas_ent):
    return all(abs(t_ent - v) > TOLERANCIA_VOLTA_S + EPS for v in voltas_ent)


def plano_de_sfx(timeline, niveis=None):
    """Eventos de som com função para um timeline: [{t, efeito, funcao, nivel_dbfs}], por tempo.

    `t` no relógio da footage (como o contrato). Só lê relogio, segmentos, letterings e cta."""
    niveis = niveis or NIVEIS_DBFS
    accel, a0 = relogio_de(timeline)
    voltas_ent = [para_entregue(v, accel, a0) for v in instantes_de_volta(timeline)]
    unidades = []

    cta = timeline.get("cta")
    if cta and cta.get("inicio") is not None:
        t_ent = para_entregue(cta["inicio"], accel, a0) - RISER_ANTES_S
        if t_ent >= 0:                                   # CTA no primeiro segundo: não há onde subir
            unidades.append(_unidade("riser", [para_footage(t_ent, accel, a0)], accel, a0))

    letterings = sorted(timeline.get("letterings") or [], key=lambda l: l["s"])
    for l in letterings:
        if l.get("estilo") == "gigante_atras":
            t = round(float(l["s"]), 3)
            if _longe_das_voltas(para_entregue(t, accel, a0), voltas_ent):
                unidades.append(_unidade("boom", [t], accel, a0))

    pilhas = OrderedDict()
    for l in letterings:
        if l.get("pilha"):
            pilhas.setdefault(l["pilha"], []).append(round(float(l["s"]), 3))
    for linhas in pilhas.values():
        mantidas, ultimo_ent = [], None
        for t in linhas:
            t_ent = para_entregue(t, accel, a0)
            if not _longe_das_voltas(t_ent, voltas_ent):
                continue
            if ultimo_ent is not None and t_ent - ultimo_ent < INTERVALO_TICK_S - EPS:
                continue
            mantidas.append(t)
            ultimo_ent = t_ent
        if mantidas:
            unidades.append(_unidade("tick", mantidas, accel, a0))

    aceitas = []
    for u in sorted(unidades, key=lambda u: (-u["prioridade"], u["eventos"][0][1])):
        conflito = any(abs(te - ta) < INTERVALO_MIN_S - EPS
                       for _, te in u["eventos"] for _, ta in (ev for o in aceitas for ev in o["eventos"]))
        if not conflito:
            aceitas.append(u)

    eventos = [{"t": t, "efeito": u["efeito"], "funcao": FUNCAO[u["efeito"]], "nivel_dbfs": niveis[u["efeito"]]}
               for u in aceitas for t, _ in u["eventos"]]
    return sorted(eventos, key=lambda e: e["t"])


def timeline_de_prancha(prancha, segs, aceleracao, a0=0.0):
    """Ponte para o motor antigo, que ainda não escreve timeline.json: monta o pedaço do timeline que o
    plano lê a partir da prancha.json (letterings, CTA) e do plano de ritmo (`ritmo.plano_de_ritmo`).

    O lettering de pilha da prancha é UM bloco com `linhas` (cada uma com `delay`); no timeline cada linha
    é um lettering com o id da pilha em `pilha`."""
    letterings = []
    for l in prancha.get("letterings") or []:
        base = {"bloco": 0, "d": l.get("d", 1.0), "estilo": l.get("estilo"), "split": bool(l.get("split")),
                "baixo": bool(l.get("baixo")), "cta": False}
        if l.get("pilha") and l.get("linhas"):
            for k, linha in enumerate(l["linhas"]):
                letterings.append(dict(base, id="%s_%d" % (l["id"], k), key=linha.get("key", l.get("key", "")),
                                       s=round(float(l["s"]) + float(linha.get("delay", 0.0)), 3), pilha=l["id"]))
        else:
            letterings.append(dict(base, id=str(l["id"]), key=l.get("key", ""), s=round(float(l["s"]), 3), pilha=None))
    cta = prancha.get("cta") or {}
    inicio = cta.get("inicio")
    return {"relogio": {"base": "footage_1x", "fps": 30, "aceleracao": aceleracao, "cauda_s": 0.45, "a0": a0},
            "segmentos": [{"bloco": s.get("bloco", 0), "tipo": "insert" if s["tipo"] == "insert" else "apresentador",
                           "s": s["s"], "e": s["e"], "sub": 0, "de": 1} for s in segs],
            "letterings": letterings,
            "cta": {"inicio": inicio, "logo": cta.get("logo", inicio), "label": cta.get("label", ""),
                    "sem_lead": False}}


def eventos_para_mix(sfx, relogio, caminhos):
    """[(t no arquivo entregue, wav)] para o mixer, a partir de `sfx` do timeline e do dict de
    `biblioteca()`. Recusa efeito fora de riser, tick e boom (o whoosh inclusive)."""
    accel, a0 = float(relogio["aceleracao"]), float(relogio.get("a0", 0.0))
    saida = []
    for e in sfx:
        efeito = e["efeito"]
        if efeito not in EFEITOS_LIGADOS:
            raise ValueError("efeito %r não existe no som com função (riser, tick e boom): o whoosh está "
                             "desligado por ordem do diretor" % (efeito,))
        if efeito not in caminhos:
            raise BibliotecaIncompleta("falta o wav do efeito %r na biblioteca" % (efeito,))
        saida.append((para_entregue(e["t"], accel, a0), Path(caminhos[efeito])))
    return saida


# --- a biblioteca de wavs -------------------------------------------------------------------------

def pasta_padrao():
    """Onde a fábrica guarda os efeitos: a mesma pasta do `som_cortes` (DADOS/assets/som)."""
    return Path(som_cortes.SOM)


def rms_dbfs(wav):
    """RMS do arquivo inteiro em dBFS (48 kHz mono): a régua dos -38 a -31."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(wav), "-map", "0:a", "-f", "s16le",
                        "-ac", "1", "-ar", str(som_cortes.SR), "-"], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("não consegui ler %s: %s" % (wav, r.stderr.decode("utf-8", "replace").strip()[-200:]))
    a = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float64) / 32768.0
    if a.size == 0:
        raise RuntimeError("%s não tem áudio" % (wav,))
    return float(20 * np.log10(max(float(np.sqrt((a ** 2).mean())), 1e-9)))


def _sintetizar(efeito, destino):
    dur, cadeia = RECEITAS[efeito]
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "lavfi", "-i", cadeia, "-t", str(dur),
                        "-ar", str(som_cortes.SR), "-ac", "1", str(destino)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("não consegui sintetizar %s: %s" % (destino.name, r.stderr.strip()[-200:]))


def gerar_biblioteca(pasta, forcar=False):
    """Sintetiza riser, tick e boom em `pasta` (o que já existe fica, a não ser com `forcar`) e devolve o
    RMS medido de cada um: {efeito: dBFS}. Nunca gera whoosh."""
    pasta = Path(pasta)
    niveis = {}
    for efeito in EFEITOS_LIGADOS:
        alvo = pasta / ARQUIVO[efeito]
        if forcar or not alvo.exists():
            _sintetizar(efeito, alvo)
        niveis[efeito] = rms_dbfs(alvo)
    return niveis


def biblioteca(pasta=None, gerar_se_faltar=True):
    """{efeito: caminho do wav}. Gera só o que falta (o setup antigo não conhecia o boom). Com
    `gerar_se_faltar=False`, wav ausente é BibliotecaIncompleta com o comando que resolve."""
    pasta = Path(pasta) if pasta is not None else pasta_padrao()
    faltando = [ARQUIVO[e] for e in EFEITOS_LIGADOS if not (pasta / ARQUIVO[e]).exists()]
    if faltando and not gerar_se_faltar:
        raise BibliotecaIncompleta("faltam em %s: %s. Rode: python3 scripts/cinema/sfx_plano.py --gerar %s"
                                   % (pasta, ", ".join(faltando), pasta))
    for efeito in EFEITOS_LIGADOS:
        if ARQUIVO[efeito] in faltando:
            _sintetizar(efeito, pasta / ARQUIVO[efeito])
    return {e: pasta / ARQUIVO[e] for e in EFEITOS_LIGADOS}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gera a biblioteca de efeitos com função (riser, tick, boom).")
    ap.add_argument("--gerar", nargs="?", const="", metavar="PASTA",
                    help="sintetiza o que faltar na pasta (padrão: a de som da fábrica)")
    ap.add_argument("--forcar", action="store_true", help="regenera mesmo o que já existe")
    args = ap.parse_args(argv)
    if args.gerar is None:
        ap.print_help()
        return 2
    pasta = Path(args.gerar) if args.gerar else pasta_padrao()
    try:
        niveis = gerar_biblioteca(pasta, forcar=args.forcar)
    except RuntimeError as e:
        print("ERRO: %s" % e, file=sys.stderr)
        return 1
    for efeito, db in niveis.items():
        print("  %s: %.1f dBFS RMS" % (ARQUIVO[efeito], db))
    return 0


if __name__ == "__main__":
    sys.exit(main())
