#!/usr/bin/env python3
"""Gate de FASES da video-ads-machine, por leva (pedido do diretor, 17/08/2026; simplificado em 01/09 e na W3.B).

UMA verdade só para a cadeia: o build só anda com o PLANO DE EDIÇÃO APROVADO e a entrega só sai com
nota de auditoria. São as duas cerimônias humanas. O resto o gate de entrada do build MEDE direto do disco
(áudio limpo, respiro, duração do avatar contra o limpo): `scripts/gates/gate_entrada.py`. Por isso
`aprovar-plano` NÃO exige mais `marcar fase0` nem `marcar fase1`; uma leva só com `iniciar` aprova o plano.

Este comando é o caminho LEGADO por leva (anúncios numerados). A aprovação por projeto, amarrada por sha256 a
roteiro.md, projeto.json, plano.json e inserts.json, é `scripts/plano/aprovacao.py` (e o gate
`scripts/gates/gate_aprovacao.py`); as 6 seções do plano e o tamanho mínimo são conferidos pelo mesmo módulo
(`plano.escrever_md`), e o plano aprovado por aqui também guarda o sha256: plano editado depois do ok vence
("aprovação vencida"). O estado da leva fica em `_fase_status_<leva>.json`.

Uso:
  python3 fase_gate.py iniciar <leva> --ads 25,26,27
  python3 fase_gate.py aprovar-plano <leva> --plano <md>   # SÓ depois do ok do diretor no chat
  python3 fase_gate.py check-build <AD>                    # exit 0 libera, 1 bloqueia
  python3 fase_gate.py registrar-nota <leva> <AD> --nota N --evidencia <arquivo>
  python3 fase_gate.py check-entrega <AD>                  # exit 0 libera, 1 bloqueia
  python3 fase_gate.py status <leva>

Contabilidade opcional (não bloqueia nada):
  python3 fase_gate.py marcar <leva> fase0 --comentarios <json> --clean 25=<mp3> 26=<mp3> ...
  python3 fase_gate.py marcar <leva> fase1 --avatar 25=<mp4> 26=<mp4> ...
  python3 fase_gate.py registrar-edicao <leva> <AD> --tecnicas a,b,c --fundo <look>

Escape hatch (barulhento, só com ordem explícita do diretor):
  FASE_GATE=0 desliga o check no produzir_ad.py.
  FASE_GATE_LEGADO=1 libera build de ad que não pertence a nenhuma leva registrada
  (ads antigos, anteriores ao gate).
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from caminhos import V2L  # noqa: E402  (era o proprio dir; agora e o _local, que guarda o estado)
from plano import aprovacao as _aprovacao  # noqa: E402
from plano import escrever_md  # noqa: E402

TOL_DUR = 1.0  # mesmo critério do gate_entrada do produzir_ad.py


def _status_path(leva):
    return V2L / f"_fase_status_{leva}.json"


def _load(leva):
    p = _status_path(leva)
    if not p.exists():
        sys.exit(f"FASE_GATE: leva '{leva}' não iniciada. Rode: python3 fase_gate.py iniciar {leva} --ads ...")
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
            sys.exit(f"FASE_GATE: evidência não existe: {p}")
        pares[ad.zfill(2)] = str(p)
    return pares


def cmd_iniciar(leva, ads):
    st = {"leva": leva, "ads": sorted(a.zfill(2) for a in ads),
          "criado": datetime.now().isoformat(timespec="seconds"),
          "fase0": None, "fase1": None, "plano": None}
    _save(leva, st)
    print(f"OK leva {leva} iniciada com ads {st['ads']}")


def cmd_marcar(leva, fase, opts):
    """Contabilidade opcional da ingestão (fase0) e dos avatares (fase1). NÃO bloqueia o build nem a
    aprovação do plano: o gate de entrada (gates/gate_entrada.py) mede a mesma evidência direto do disco."""
    st = _load(leva)
    if fase == "fase0":
        com = opts.get("--comentarios")
        if not com or not Path(com).expanduser().exists():
            sys.exit("FASE_GATE: fase0 exige --comentarios <json existente> (dump do ler-comentarios-doc.py)")
        # EVIDÊNCIA TEM QUE SER EVIDÊNCIA: antes bastava o arquivo existir, então um
        # json vazio ou de outra leva passava e a fase0 ficava "cumprida" sem ninguém
        # ter lido comentário nenhum.
        try:
            dados = json.loads(Path(com).expanduser().read_text())
        except Exception as e:
            sys.exit(f"FASE_GATE: --comentarios não é json válido: {e}")
        if not isinstance(dados, list) or not dados:
            sys.exit("FASE_GATE: dump de comentários vazio. Rode ler-comentarios-doc.py de verdade.")
        com_ancora = [c for c in dados if isinstance(c, dict) and c.get("ancora")]
        com_link = [c for c in com_ancora if c.get("links")]
        if not com_ancora:
            sys.exit("FASE_GATE: nenhum comentário com âncora no dump. Sem âncora não dá "
                     "pra casar asset com bloco, que é o motivo da fase0 existir.")
        if not com_link:
            sys.exit("FASE_GATE: nenhum comentário com link no dump. Confirme que leu o "
                     "doc certo (os assets moram nos links dos comentários).")
        print(f"  evidência: {len(dados)} comentários, {len(com_ancora)} com âncora, "
              f"{len(com_link)} com link")
        cleans = _parse_pairs(opts.get("--clean", []), "--clean")
        faltam = set(st["ads"]) - set(cleans)
        if faltam:
            sys.exit(f"FASE_GATE: fase0 sem áudio clean dos ads {sorted(faltam)}")
        st["fase0"] = {"comentarios": com, "clean": cleans,
                       "em": datetime.now().isoformat(timespec="seconds")}
    elif fase == "fase1":
        if not st.get("fase0"):
            sys.exit("FASE_GATE: o registro da fase1 usa o áudio limpo da fase0 como referência de duração: "
                     "registre a fase0 antes (ou deixe os dois para o gate de entrada, que mede sem registro).")
        avatares = _parse_pairs(opts.get("--avatar", []), "--avatar")
        faltam = set(st["ads"]) - set(avatares)
        if faltam:
            sys.exit(f"FASE_GATE: fase1 sem avatar dos ads {sorted(faltam)}")
        for ad, av in avatares.items():
            d_av, d_cl = _dur(av), _dur(st["fase0"]["clean"][ad])
            if abs(d_av - d_cl) > TOL_DUR:
                sys.exit(f"FASE_GATE: AD{ad} avatar {d_av:.1f}s vs clean {d_cl:.1f}s "
                         f"(tolerância {TOL_DUR}s). Avatar gerado do áudio errado? Regerar.")
        st["fase1"] = {"avatar": avatares, "em": datetime.now().isoformat(timespec="seconds")}
    else:
        sys.exit(f"FASE_GATE: fase desconhecida '{fase}' (fase0|fase1)")
    _save(leva, st)
    print(f"OK {fase} da leva {leva} registrada com evidência (contabilidade: não bloqueia o build)")


def cmd_aprovar_plano(leva, plano):
    """Registra o ok do diretor ao plano de edição da leva. Não exige fase0 nem fase1 (uma verdade só: o que
    essas fases comprovam o gate de entrada mede). Confere CONTEÚDO, não só existência: as 6 seções e o tamanho
    (plano.escrever_md), e guarda o sha256 do plano para a aprovação vencer se ele mudar."""
    st = _load(leva)
    p = Path(plano).expanduser()
    if not p.exists():
        sys.exit(f"FASE_GATE: plano não existe: {p}")
    bruto = p.read_text(encoding="utf-8")
    faltando = escrever_md.secoes_ausentes(bruto)
    if faltando:
        sys.exit(f"FASE_GATE: plano incompleto, faltam seções: {faltando}. "
                 "Um plano sem essas respostas não guia edição nenhuma.")
    if len(bruto) < escrever_md.TAMANHO_MIN:
        sys.exit(f"FASE_GATE: plano com {len(bruto)} chars é curto demais pra ser plano "
                 f"(mínimo {escrever_md.TAMANHO_MIN}).")
    st["plano"] = {"arquivo": os.path.abspath(str(p)), "chars": len(bruto),
                   "sha256": _aprovacao.sha256_arquivo(p),
                   "aprovado_em": datetime.now().isoformat(timespec="seconds")}
    _save(leva, st)
    print(f"OK plano da leva {leva} marcado como APROVADO ({len(bruto)} chars, "
          f"{len(escrever_md.SECOES)} seções presentes, sha256 {st['plano']['sha256'][:12]}).")
    print("  (Este comando só pode ser rodado DEPOIS do ok do diretor no chat.)")


def cmd_registrar_nota(leva, ad, nota, evidencia):
    """Nota da auditoria 0-10. Abaixo de NOTA_MINIMA o ad não pode ser entregue."""
    st = _load(leva)
    ad = ad.zfill(2)
    if ad not in st["ads"]:
        sys.exit(f"FASE_GATE: ad '{ad}' não pertence à leva {leva}")
    ev = Path(evidencia).expanduser()
    if not ev.exists():
        sys.exit(f"FASE_GATE: evidência da auditoria não existe: {ev}. "
                 "Nota sem relatório é opinião, não auditoria.")
    st.setdefault("notas", {})[ad] = {
        "nota": float(nota), "evidencia": str(ev),
        "em": datetime.now().isoformat(timespec="seconds")}
    _save(leva, st)
    print(f"OK nota {nota} registrada pro AD{ad} (evidência: {ev.name})")


# NOTA MÍNIMA 8, UMA RODADA SÓ (01/09/2026, ordem do diretor). A regra anterior era 9
# com ciclo "abaixo de 9 refaz", e o ciclo virou o problema: rodadas de auditoria
# completas se empilhando por horas, e o diretor revisando tudo no fim de qualquer jeito
# ("não tá adiantando nada ter 14913921 auditorias, eu sempre acabo revisando").
# O dado que sustenta a troca: na semana de 25-31/08 o ciclo de nota não rodou NENHUMA
# vez (11 builds do anúncio de referência, nota null) e quem pegou defeito real foram os
# gates MEDIDOS e o próprio diretor. Auditoria LLM vira UMA passada: audita, corrige o que
# ela apontou, registra a nota e entrega. Reprovou (<8)? Corrige os achados e reconfere OS
# MESMOS achados, nunca uma varredura completa nova. Os gates medidos continuam intocados.
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
                         "--nota N --evidencia <relatório>")
            if n["nota"] < NOTA_MINIMA:
                sys.exit(f"ENTREGA BLOQUEADA: AD{ad} com nota {n['nota']} "
                         f"(mínimo {NOTA_MINIMA}). Corrija os achados DESSA auditoria "
                         "e reconfira os mesmos pontos; varredura nova, não.")
            print(f"OK AD{ad}: nota {n['nota']}, entrega liberada")
            return
    sys.exit(f"ENTREGA BLOQUEADA: AD{ad} não pertence a nenhuma leva registrada.")


def cmd_registrar_edicao(leva, ad, tecnicas, fundo):
    """Registra o mix de técnicas e o fundo, e recusa repetir o do ad anterior."""
    st = _load(leva)
    ad = ad.zfill(2)
    if ad not in st["ads"]:
        sys.exit(f"FASE_GATE: ad '{ad}' não pertence à leva {leva}")
    tec = sorted({t.strip() for t in tecnicas.split(",") if t.strip()})
    if not tec:
        sys.exit("FASE_GATE: --tecnicas vazio")
    reg = st.setdefault("edicao", {})
    anteriores = [(a, v) for a, v in reg.items() if a != ad]
    for a, v in anteriores:
        if sorted(v["tecnicas"]) == tec and v.get("fundo") == fundo:
            sys.exit(f"FASE_GATE: AD{ad} usaria o MESMO mix e o MESMO fundo do AD{a} "
                     f"({tec}, {fundo}). Dois ads iguais na mesma leva é o que a skill "
                     "existe pra evitar. Varie pelo banco de referências.")
    reg[ad] = {"tecnicas": tec, "fundo": fundo,
               "em": datetime.now().isoformat(timespec="seconds")}
    _save(leva, st)
    print(f"OK edição do AD{ad} registrada: {tec} | fundo {fundo}")


def _conferir_plano_aprovado(st, ad):
    """Plano aprovado por esta versão do comando guarda o sha256: se o arquivo mudou (ou sumiu) depois do ok, a
    aprovação venceu. Aprovação registrada antes da amarração (sem sha256) segue valendo, com aviso."""
    plano = st["plano"]
    arquivo, sha = plano.get("arquivo"), plano.get("sha256")
    if not (arquivo and sha):
        print(f"AVISO AD{ad}: a aprovação do plano está sem sha256 (registrada antes da amarração): "
              f"reaprove com aprovar-plano {st['leva']} depois do ok do diretor no chat para amarrar o plano.")
        return
    p = Path(arquivo)
    if not p.is_file():
        sys.exit(f"FASE_GATE: AD{ad} (leva {st['leva']}) aprovação vencida: o plano aprovado ({arquivo}) sumiu. "
                 f"Refaça o plano e rode aprovar-plano {st['leva']} --plano <md> DEPOIS do novo ok do diretor no chat.")
    if _aprovacao.sha256_arquivo(p) != sha:
        sys.exit(f"FASE_GATE: AD{ad} (leva {st['leva']}) aprovação vencida: o plano {p.name} mudou depois do ok. "
                 f"Mostre o plano novo ao diretor e rode aprovar-plano {st['leva']} --plano {arquivo} "
                 "DEPOIS do novo ok dele no chat.")


def cmd_check_build(ad):
    ad = ad.zfill(2)
    for p in sorted(V2L.glob("_fase_status_*.json")):
        st = json.loads(p.read_text())
        if ad in st.get("ads", []):
            # DUAS CERIMÔNIAS, NÃO CINCO (01/09/2026, ordem do diretor: "a skill tá
            # burocrática?"). Este check exigia fase0 e fase1 REGISTRADAS à mão, e o
            # critério de burocracia excessiva é o fluxo real contornar o oficial: na
            # semana de 25-31/08 foram 11 builds e nenhum registro novo, porque o
            # gate_entrada do produzir_ad já MEDE a mesma evidência direto do disco
            # (clean existe, respiro por energia, duração do avatar vs clean por
            # ffprobe), e medir é mais forte que registrar. Cerimônia humana que sobra:
            # `aprovar-plano` (o ok do diretor, aqui) e `check-entrega` (nota mínima 8).
            # Os comandos `marcar`/`registrar-edicao` continuam existindo como
            # contabilidade opcional, mas não bloqueiam mais.
            if not st.get("plano"):
                sys.exit(f"FASE_GATE: AD{ad} (leva {st['leva']}) bloqueado: plano de "
                         "edição sem o ok do diretor no chat. Rode fase_gate.py aprovar-plano "
                         "DEPOIS do ok explícito dele no chat; sem isso não se monta.")
            _conferir_plano_aprovado(st, ad)
            print(f"OK AD{ad}: plano da leva {st['leva']} aprovado, build liberado "
                  "(fase0/fase1 são medidas pelo gate de entrada do build)")
            return
    if os.environ.get("FASE_GATE_LEGADO") == "1":
        print(f"AVISO AD{ad}: fora de qualquer leva registrada, liberado por FASE_GATE_LEGADO=1")
        return
    sys.exit(f"FASE_GATE: AD{ad} não pertence a nenhuma leva registrada. "
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
