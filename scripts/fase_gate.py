#!/usr/bin/env python3
"""Gate de FASES da video-ads-machine (pedido do Julio, 17/08/2026).

Garante em CODIGO a ordem: fase0 (ingestao) -> fase1 (HeyGen em lote) ->
fase2 (plano de edicao APROVADO) -> build. O produzir_ad.py consulta este
gate antes de buildar; sem as fases aprovadas, o build recusa (exit 1).

Estado: _fase_status_<leva>.json neste diretorio. Evidencia e verificada
(arquivo existe, duracao bate), nao declarada.

Uso:
  python3 fase_gate.py iniciar <leva> --ads 25,26,27
  python3 fase_gate.py marcar <leva> fase0 --comentarios <json> --clean 25=<mp3> 26=<mp3> ...
  python3 fase_gate.py marcar <leva> fase1 --avatar 25=<mp4> 26=<mp4> ...
  python3 fase_gate.py aprovar-plano <leva> --plano <md>   # SO depois do OK do Julio no chat
  python3 fase_gate.py check-build <AD>                    # exit 0 libera, 1 bloqueia
  python3 fase_gate.py status <leva>

Escape hatch (barulhento, so com ordem explicita do Julio):
  FASE_GATE=0 desliga o check no produzir_ad.py.
  FASE_GATE_LEGADO=1 libera build de ad que nao pertence a nenhuma leva registrada
  (ads antigos, 01-21, anteriores ao gate).
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from caminhos import V2L  # noqa: E402  (era o proprio dir; agora e o _local, que guarda o estado)
TOL_DUR = 1.0  # mesmo criterio do gate_entrada do produzir_ad.py


def _status_path(leva):
    return V2L / f"_fase_status_{leva}.json"


def _load(leva):
    p = _status_path(leva)
    if not p.exists():
        sys.exit(f"FASE_GATE: leva '{leva}' nao iniciada. Rode: python3 fase_gate.py iniciar {leva} --ads ...")
    return json.loads(p.read_text())


def _save(leva, st):
    _status_path(leva).write_text(json.dumps(st, indent=2, ensure_ascii=False))


def _dur(path):
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        sys.exit(f"FASE_GATE: ffprobe falhou em {path}")


def _parse_pairs(args, flag):
    pares = {}
    for a in args:
        if "=" not in a:
            sys.exit(f"FASE_GATE: {flag} espera AD=caminho, recebi '{a}'")
        ad, path = a.split("=", 1)
        p = Path(path).expanduser()
        if not p.exists():
            sys.exit(f"FASE_GATE: evidencia nao existe: {p}")
        pares[ad.zfill(2)] = str(p)
    return pares


def cmd_iniciar(leva, ads):
    st = {"leva": leva, "ads": sorted(a.zfill(2) for a in ads),
          "criado": datetime.now().isoformat(timespec="seconds"),
          "fase0": None, "fase1": None, "plano": None}
    _save(leva, st)
    print(f"OK leva {leva} iniciada com ads {st['ads']}")


def cmd_marcar(leva, fase, opts):
    st = _load(leva)
    if fase == "fase0":
        com = opts.get("--comentarios")
        if not com or not Path(com).expanduser().exists():
            sys.exit("FASE_GATE: fase0 exige --comentarios <json existente> (dump do ler-comentarios-doc.py)")
        # EVIDENCIA TEM QUE SER EVIDENCIA: antes bastava o arquivo existir, entao um
        # json vazio ou de outra leva passava e a fase0 ficava "cumprida" sem ninguem
        # ter lido comentario nenhum.
        try:
            dados = json.loads(Path(com).expanduser().read_text())
        except Exception as e:
            sys.exit(f"FASE_GATE: --comentarios nao e json valido: {e}")
        if not isinstance(dados, list) or not dados:
            sys.exit("FASE_GATE: dump de comentarios vazio. Rode ler-comentarios-doc.py de verdade.")
        com_ancora = [c for c in dados if isinstance(c, dict) and c.get("ancora")]
        com_link = [c for c in com_ancora if c.get("links")]
        if not com_ancora:
            sys.exit("FASE_GATE: nenhum comentario com ancora no dump. Sem ancora nao da "
                     "pra casar asset com bloco, que e o motivo da fase0 existir.")
        if not com_link:
            sys.exit("FASE_GATE: nenhum comentario com link no dump. Confirme que leu o "
                     "doc certo (os assets moram nos links dos comentarios).")
        print(f"  evidencia: {len(dados)} comentarios, {len(com_ancora)} com ancora, "
              f"{len(com_link)} com link")
        cleans = _parse_pairs(opts.get("--clean", []), "--clean")
        faltam = set(st["ads"]) - set(cleans)
        if faltam:
            sys.exit(f"FASE_GATE: fase0 sem audio clean dos ads {sorted(faltam)}")
        st["fase0"] = {"comentarios": com, "clean": cleans,
                       "em": datetime.now().isoformat(timespec="seconds")}
    elif fase == "fase1":
        if not st.get("fase0"):
            sys.exit("FASE_GATE: fase1 antes da fase0. Ordem e ordem.")
        avatares = _parse_pairs(opts.get("--avatar", []), "--avatar")
        faltam = set(st["ads"]) - set(avatares)
        if faltam:
            sys.exit(f"FASE_GATE: fase1 sem avatar dos ads {sorted(faltam)}")
        for ad, av in avatares.items():
            d_av, d_cl = _dur(av), _dur(st["fase0"]["clean"][ad])
            if abs(d_av - d_cl) > TOL_DUR:
                sys.exit(f"FASE_GATE: AD{ad} avatar {d_av:.1f}s vs clean {d_cl:.1f}s "
                         f"(tolerancia {TOL_DUR}s). Avatar gerado do audio errado? Regerar.")
        st["fase1"] = {"avatar": avatares, "em": datetime.now().isoformat(timespec="seconds")}
    else:
        sys.exit(f"FASE_GATE: fase desconhecida '{fase}' (fase0|fase1)")
    _save(leva, st)
    print(f"OK {fase} da leva {leva} registrada com evidencia")


# Um plano de edicao so e um plano se responder a estas perguntas. Sem isso o
# "plano aprovado" vira carimbo num arquivo vazio.
SECOES_PLANO = {
    "mapa de inserts": ("insert", "asset"),
    "hook": ("hook",),
    "lettering": ("lettering",),
    "densidade": ("densidade",),
    "referencias": ("referenc",),
    "efeitos": ("efeito", "som"),
}


def cmd_aprovar_plano(leva, plano):
    st = _load(leva)
    if not st.get("fase1"):
        sys.exit("FASE_GATE: aprovar plano antes da fase1? Nao. Avatares primeiro.")
    p = Path(plano).expanduser()
    if not p.exists():
        sys.exit(f"FASE_GATE: plano nao existe: {p}")
    # CONTEUDO, nao so existencia (antes um arquivo vazio era aprovavel).
    import unicodedata
    bruto = p.read_text()
    txt = "".join(c for c in unicodedata.normalize("NFKD", bruto.lower())
                  if not unicodedata.combining(c))
    faltando = [nome for nome, chaves in SECOES_PLANO.items()
                if not any(k in txt for k in chaves)]
    if faltando:
        sys.exit(f"FASE_GATE: plano incompleto, faltam secoes: {faltando}. "
                 "Um plano sem essas respostas nao guia edicao nenhuma.")
    if len(bruto) < 800:
        sys.exit(f"FASE_GATE: plano com {len(bruto)} chars e curto demais pra ser plano.")
    st["plano"] = {"arquivo": str(p), "chars": len(bruto),
                   "aprovado_em": datetime.now().isoformat(timespec="seconds")}
    _save(leva, st)
    print(f"OK plano da leva {leva} marcado como APROVADO ({len(bruto)} chars, "
          f"{len(SECOES_PLANO)} secoes presentes).")
    print("  (Este comando so pode ser rodado DEPOIS do ok explicito do Julio no chat.)")


def cmd_registrar_nota(leva, ad, nota, evidencia):
    """Nota da auditoria 0-10. Abaixo de 9 o ad nao pode ser entregue."""
    st = _load(leva)
    ad = ad.zfill(2)
    if ad not in st["ads"]:
        sys.exit(f"FASE_GATE: ad '{ad}' nao pertence a leva {leva}")
    ev = Path(evidencia).expanduser()
    if not ev.exists():
        sys.exit(f"FASE_GATE: evidencia da auditoria nao existe: {ev}. "
                 "Nota sem relatorio e opiniao, nao auditoria.")
    st.setdefault("notas", {})[ad] = {
        "nota": float(nota), "evidencia": str(ev),
        "em": datetime.now().isoformat(timespec="seconds")}
    _save(leva, st)
    print(f"OK nota {nota} registrada pro AD{ad} (evidencia: {ev.name})")


# NOTA MINIMA 8, UMA RODADA SO (01/09/2026, ordem do Julio). A regra anterior era 9
# com ciclo "abaixo de 9 refaz", e o ciclo virou o problema: rodadas de auditoria
# completas se empilhando por horas, e ele revisando tudo no fim de qualquer jeito
# ("nao ta adiantando nada ter 14913921 auditorias, eu sempre acabo revisando").
# O dado que sustenta a troca: na semana de 25-31/08 o ciclo de nota nao rodou NENHUMA
# vez (11 builds do jh13, nota null) e quem pegou defeito real foram os gates MEDIDOS
# e o proprio Julio. Auditoria LLM vira UMA passada: audita, corrige o que ela apontou,
# registra a nota e entrega. Reprovou (<8)? Corrige os achados e reconfere OS MESMOS
# achados, nunca uma varredura completa nova. Os gates medidos continuam intocados.
NOTA_MINIMA = 8


def cmd_check_entrega(ad):
    """Bloqueia entrega sem auditoria com nota >= NOTA_MINIMA (uma rodada, ver acima)."""
    ad = ad.zfill(2)
    for p in sorted(V2L.glob("_fase_status_*.json")):
        st = json.loads(p.read_text())
        if ad in st.get("ads", []):
            n = (st.get("notas") or {}).get(ad)
            if not n:
                sys.exit(f"ENTREGA BLOQUEADA: AD{ad} sem nota de auditoria registrada. "
                         f"Rode: fase_gate.py registrar-nota {st['leva']} {ad} "
                         "--nota N --evidencia <relatorio>")
            if n["nota"] < NOTA_MINIMA:
                sys.exit(f"ENTREGA BLOQUEADA: AD{ad} com nota {n['nota']} "
                         f"(minimo {NOTA_MINIMA}). Corrija os achados DESSA auditoria "
                         "e reconfira os mesmos pontos; varredura nova, nao.")
            print(f"OK AD{ad}: nota {n['nota']}, entrega liberada")
            return
    sys.exit(f"ENTREGA BLOQUEADA: AD{ad} nao pertence a nenhuma leva registrada.")


def cmd_registrar_edicao(leva, ad, tecnicas, fundo):
    """Registra o mix de tecnicas e o fundo, e recusa repetir o do ad anterior."""
    st = _load(leva)
    ad = ad.zfill(2)
    if ad not in st["ads"]:
        sys.exit(f"FASE_GATE: ad '{ad}' nao pertence a leva {leva}")
    tec = sorted({t.strip() for t in tecnicas.split(",") if t.strip()})
    if not tec:
        sys.exit("FASE_GATE: --tecnicas vazio")
    reg = st.setdefault("edicao", {})
    anteriores = [(a, v) for a, v in reg.items() if a != ad]
    for a, v in anteriores:
        if sorted(v["tecnicas"]) == tec and v.get("fundo") == fundo:
            sys.exit(f"FASE_GATE: AD{ad} usaria o MESMO mix e o MESMO fundo do AD{a} "
                     f"({tec}, {fundo}). Dois ads iguais na mesma leva e o que a skill "
                     "existe pra evitar. Varie pelo banco de referencias.")
    reg[ad] = {"tecnicas": tec, "fundo": fundo,
               "em": datetime.now().isoformat(timespec="seconds")}
    _save(leva, st)
    print(f"OK edicao do AD{ad} registrada: {tec} | fundo {fundo}")


def cmd_check_build(ad):
    ad = ad.zfill(2)
    for p in sorted(V2L.glob("_fase_status_*.json")):
        st = json.loads(p.read_text())
        if ad in st.get("ads", []):
            # DUAS CERIMONIAS, NAO CINCO (01/09/2026, ordem do Julio: "a skill ta
            # burocratica?"). Este check exigia fase0 e fase1 REGISTRADAS a mao, e o
            # criterio de burocracia excessiva e o fluxo real contornar o oficial: na
            # semana de 25-31/08 foram 11 builds e nenhum registro novo, porque o
            # gate_entrada do produzir_ad ja MEDE a mesma evidencia direto do disco
            # (clean existe, respiro por energia, duracao do avatar vs clean por
            # ffprobe), e medir e mais forte que registrar. Cerimonia humana que sobra:
            # `aprovar-plano` (o ok do Julio, aqui) e `check-entrega` (nota minima 8).
            # Os comandos `marcar`/`registrar-edicao` continuam existindo como
            # contabilidade opcional, mas nao bloqueiam mais.
            if not st.get("plano"):
                sys.exit(f"FASE_GATE: AD{ad} (leva {st['leva']}) bloqueado: plano de "
                         "edicao sem o OK do Julio. Rode fase_gate.py aprovar-plano "
                         "DEPOIS do ok explicito dele no chat; sem isso nao se monta.")
            print(f"OK AD{ad}: plano da leva {st['leva']} aprovado, build liberado "
                  "(fase0/fase1 sao medidas pelo gate de entrada do build)")
            return
    import os
    if os.environ.get("FASE_GATE_LEGADO") == "1":
        print(f"AVISO AD{ad}: fora de qualquer leva registrada, liberado por FASE_GATE_LEGADO=1")
        return
    sys.exit(f"FASE_GATE: AD{ad} nao pertence a nenhuma leva registrada. "
             "Leva nova: fase_gate.py iniciar. Rebuild de ad antigo: FASE_GATE_LEGADO=1.")


def cmd_status(leva):
    st = _load(leva)
    print(json.dumps(st, indent=2, ensure_ascii=False))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "iniciar":
        ads = []
        if "--ads" in rest:
            ads = rest[rest.index("--ads") + 1].split(",")
        if not rest or not ads:
            sys.exit("uso: iniciar <leva> --ads 25,26,...")
        cmd_iniciar(rest[0], ads)
    elif cmd == "marcar":
        leva, fase = rest[0], rest[1]
        opts, key = {}, None
        for a in rest[2:]:
            if a.startswith("--"):
                key = a
                opts.setdefault(key, [] if key in ("--clean", "--avatar") else None)
            elif key in ("--clean", "--avatar"):
                opts[key].append(a)
            elif key:
                opts[key] = a
        cmd_marcar(leva, fase, opts)
    elif cmd == "aprovar-plano":
        leva = rest[0]
        plano = rest[rest.index("--plano") + 1] if "--plano" in rest else None
        if not plano:
            sys.exit("uso: aprovar-plano <leva> --plano <md>")
        cmd_aprovar_plano(leva, plano)
    elif cmd == "registrar-nota":
        if "--nota" not in rest or "--evidencia" not in rest:
            sys.exit("uso: registrar-nota <leva> <ad> --nota N --evidencia <arquivo>")
        cmd_registrar_nota(rest[0], rest[1], rest[rest.index("--nota") + 1],
                           rest[rest.index("--evidencia") + 1])
    elif cmd == "check-entrega":
        cmd_check_entrega(rest[0])
    elif cmd == "registrar-edicao":
        if "--tecnicas" not in rest or "--fundo" not in rest:
            sys.exit("uso: registrar-edicao <leva> <ad> --tecnicas a,b,c --fundo <look>")
        cmd_registrar_edicao(rest[0], rest[1], rest[rest.index("--tecnicas") + 1],
                             rest[rest.index("--fundo") + 1])
    elif cmd == "check-build":
        cmd_check_build(rest[0])
    elif cmd == "status":
        cmd_status(rest[0])
    else:
        sys.exit(f"comando desconhecido: {cmd}\n{__doc__}")


if __name__ == "__main__":
    main()
