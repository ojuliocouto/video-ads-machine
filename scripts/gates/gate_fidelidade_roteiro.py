#!/usr/bin/env python3
"""GATE FIDELIDADE AO ROTEIRO (W3.C): o que o roteiro.md marca chega inteiro ao plano e aos arquivos.

    python3 scripts/gates/gate_fidelidade_roteiro.py <slug> [--estado _local]
    exit 0 passa · 1 reprova · 2 insumo inválido (sem roteiro, sem plano, roteiro fora da convenção)

O roteiro.md é a fonte da verdade da direção. Este gate confere, ANTES do build, o que ele marca
contra os dois lugares onde a marcação pode se perder:

  1. inserts/: cada chave `[insert: <chave>]` distinta tem o seu arquivo `inserts/<chave>.*`, nenhuma
     chave tem mais de um arquivo e nenhum arquivo sobra sem chave no roteiro. Duas visitas à mesma
     chave pedem um arquivo só (N chaves DISTINTAS = N arquivos). `inserts/<chave>.partes.json`
     (a lista das peças de uma pipoca) não conta como arquivo de insert.
  2. plano/plano.json:
     - letterings: cada KEY marcada (apresentador, insert, cta) e cada item de `[lista]` vira um
       lettering no plano, com o mesmo texto, o mesmo LEAD e a mesma âncora (palavra e ocorrência);
       e o plano não inventa lettering que o roteiro não marcou;
     - blocos: mesmo número, mesma fala (norma de `contratos.validar.palavras`), mesmo tipo e
       mesma chave de insert;
     - hook: eyebrow, linha e destaque iguais ao do roteiro.
     Bloco que o PLANO propôs (`proposto: true`, ou qualquer bloco de insert num roteiro livre)
     pode ter direção própria e traz as chaves dele para a conferência dos arquivos.
  3. âncora ambígua: `âncora: dia` numa fala em que "dia" aparece mais de uma vez, sem `#n`, reprova
     (o leitor do roteiro já acusa; aqui ela vira reprovação em vez de erro de leitura).

O que NÃO é conferido aqui: a validade do plano.json inteiro (é do gate de aprovação), a fala contra
o áudio (gate_fala_roteiro) e o Doc do aluno (gate_fidelidade_doc).

Resultado: `Resultado(ok, motivo, detalhes)`; a CLI grava em status.json (etapa `gate_fidelidade_roteiro`).
"""
import argparse
import os
import re
import sys
from collections import namedtuple

if __name__ == "__main__":      # rodado direto: scripts/gates/gate_fidelidade_roteiro.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contratos.validar import normalizar_palavra, palavras  # noqa: E402
from entrada import roteiro_md  # noqa: E402
from projeto import pastas, status  # noqa: E402

ETAPA = "gate_fidelidade_roteiro"
Resultado = namedtuple("Resultado", "ok motivo detalhes")

SUFIXO_PARTES = ".partes.json"
_RE_AMBIGUA = re.compile(r"'([^']+)' aparece (\d+) vezes na fala do bloco")


class InsumoInvalido(Exception):
    """Falta arquivo ou o arquivo não pôde ser lido: não dá nem para reprovar (exit 2)."""


# --- leitura dos insumos -----------------------------------------------------------------------------

def _roteiro(pj):
    """(leitura, [mensagem de âncora ambígua]). Qualquer outro erro de gramática é insumo inválido."""
    if not pj.roteiro.is_file():
        raise InsumoInvalido("roteiro.md não existe em %s: cole o roteiro e grave o projeto antes" % pj.raiz)
    try:
        lei = roteiro_md.ler_arquivo(pj.roteiro)
    except ValueError as e:
        raise InsumoInvalido(str(e))
    ambiguas = [e for e in lei.erros if e.campo == "ancora" and _RE_AMBIGUA.search(e.mensagem)]
    outros = [e for e in lei.erros if e not in ambiguas]
    if outros:
        raise InsumoInvalido("o roteiro.md está fora da convenção:\n%s" % roteiro_md.formatar_erros(outros))
    return lei, ambiguas


def _plano(pj):
    if not pj.plano_json.is_file():
        raise InsumoInvalido("plano/plano.json não existe em %s: gere o plano antes de conferir a fidelidade"
                             % pj.raiz)
    try:
        plano = status.ler_json(pj.plano_json)
    except ValueError as e:
        raise InsumoInvalido("plano/plano.json ilegível: %s" % e)
    return _plano_valido(plano)


def _plano_valido(plano):
    if not isinstance(plano, dict) or not isinstance(plano.get("blocos"), list) \
            or not isinstance(plano.get("letterings"), list):
        raise InsumoInvalido("plano.json sem as seções 'blocos' e 'letterings': gere o plano de novo")
    return plano


def _arquivos_de_insert(pj):
    """{chave: [nomes]} do que há em inserts/ (ignora oculto e o .partes.json)."""
    achados = {}
    if pj.inserts_dir.is_dir():
        for f in sorted(pj.inserts_dir.iterdir()):
            if f.is_file() and not f.name.startswith(".") and not f.name.endswith(SUFIXO_PARTES):
                achados.setdefault(f.stem, []).append(f.name)
    return achados


# --- as conferências ---------------------------------------------------------------------------------

def _norm(texto):
    return " ".join(str(texto or "").split()).casefold()


def _conferir_inserts(pj, chaves, falhas):
    arquivos = _arquivos_de_insert(pj)
    for c in chaves:
        achados = arquivos.get(c, [])
        if not achados:
            falhas.append("a chave %r do roteiro está sem arquivo: ponha inserts/%s.<extensão>" % (c, c))
        elif len(achados) > 1:
            falhas.append("a chave %r tem mais de um arquivo (%s): deixe só um" % (c, ", ".join(achados)))
    for stem, nomes in sorted(arquivos.items()):
        if stem not in chaves:
            falhas.append("inserts/%s não está no roteiro (nenhum bloco usa [insert: %s]): apague o arquivo "
                          "ou marque o bloco" % (nomes[0], stem))
    return arquivos


def _letterings_esperados(blocos):
    """Os letterings que o roteiro marca, por bloco: KEY, KEY do CTA e um por item de [lista]."""
    saida = []
    for i, b in enumerate(blocos):
        if b["tipo"] == "lista":
            for k, item in enumerate(b["itens"]):
                saida.append({"bloco": i, "key": item["texto"], "lead": b["lead"] if k == 0 else None,
                              "lista": True})
        elif b["key"]:
            anc = b["ancora"] or {}
            saida.append({"bloco": i, "key": b["key"], "lead": b["lead"], "lista": False,
                          "ancora": (normalizar_palavra(anc.get("palavra", "")), anc.get("n", 1))})
    return saida


def _conferir_letterings(esperados, letterings, falhas):
    por_bloco = {}
    for L in letterings:
        por_bloco.setdefault(L.get("bloco"), []).append(L)
    exp_por_bloco = {}
    for e in esperados:
        exp_por_bloco.setdefault(e["bloco"], []).append(e)
    for i in sorted(set(por_bloco) | set(exp_por_bloco), key=lambda x: (x is None, x)):
        exp, got = exp_por_bloco.get(i, []), por_bloco.get(i, [])
        if exp and exp[0]["lista"]:
            if len(exp) != len(got):
                falhas.append("bloco %s (lista): o roteiro tem %d itens e o plano tem %d letterings"
                              % (i, len(exp), len(got)))
                continue
        else:
            for e in exp[len(got):]:
                falhas.append("lettering %r do bloco %s falta no plano" % (e["key"], i))
            for g in got[len(exp):]:
                falhas.append("o plano tem lettering %r no bloco %s que o roteiro não marcou" % (g.get("key"), i))
        for e, g in zip(exp, got):
            if _norm(e["key"]) != _norm(g.get("key")):
                falhas.append("bloco %s: a KEY do roteiro é %r e a do plano é %r" % (i, e["key"], g.get("key")))
                continue
            if _norm(e["lead"]) != _norm(g.get("lead")):
                falhas.append("bloco %s: o LEAD de %r no roteiro é %r e no plano é %r"
                              % (i, e["key"], e["lead"], g.get("lead")))
            if not e["lista"]:
                anc = g.get("ancora") or {}
                lido = (normalizar_palavra(str(anc.get("palavra", ""))), anc.get("n", 1))
                if lido != e["ancora"]:
                    falhas.append("bloco %s: a âncora de %r no roteiro é %s#%s e no plano é %s#%s"
                                  % (i, e["key"], e["ancora"][0], e["ancora"][1], lido[0], lido[1]))


def _conferir_blocos(blocos, plano_blocos, falhas):
    if len(plano_blocos) != len(blocos):
        falhas.append("o plano tem %d blocos e o roteiro tem %d" % (len(plano_blocos), len(blocos)))
        return
    for i, (b, p) in enumerate(zip(blocos, plano_blocos)):
        if palavras(str(p.get("fala", ""))) != palavras(b["fala"]):
            falhas.append("bloco %d: a fala do plano difere da fala do roteiro" % i)
        if p.get("proposto"):
            continue
        if b["tipo"] != "livre" and p.get("tipo") != b["tipo"]:
            falhas.append("bloco %d: o roteiro marca %s e o plano tem %s" % (i, b["tipo"], p.get("tipo")))
        elif b["tipo"] == "insert" and p.get("insert") != b["insert"]:
            falhas.append("bloco %d: o roteiro marca insert %r e o plano tem %r" % (i, b["insert"], p.get("insert")))
        if b["layout"] and p.get("layout") != b["layout"]:
            falhas.append("bloco %d: o roteiro pede layout %s e o plano tem %s" % (i, b["layout"], p.get("layout")))


def _conferir_hook(blocos, plano, falhas):
    hook = blocos[0]["hook"] if blocos else None
    if not hook:
        return
    p = plano.get("hook") or {}
    for campo in ("eyebrow", "linha", "destaque"):
        if _norm(p.get(campo)) != _norm(hook[campo]):
            falhas.append("o hook do plano difere do roteiro no campo %s (roteiro %r, plano %r)"
                          % (campo, hook[campo], p.get(campo)))


def rodar(pastas_projeto, plano=None):
    """Confere o roteiro.md contra inserts/ e contra o plano (`plano`: dict já lido; senão lê
    plano/plano.json). Levanta InsumoInvalido quando não há o que conferir."""
    pj = pastas_projeto
    lei, ambiguas = _roteiro(pj)
    if ambiguas:
        palavras_amb = [_RE_AMBIGUA.search(e.mensagem).group(1) for e in ambiguas]
        motivo = "; ".join("âncora ambígua (%s): %s" % (e.caminho, e.mensagem) for e in ambiguas)
        return Resultado(False, motivo, {"estado": "REPROVA", "ancoras_ambiguas": palavras_amb})
    plano = _plano_valido(plano) if plano is not None else _plano(pj)

    blocos = lei.blocos
    chaves = []
    for b in blocos:
        if b["tipo"] == "insert" and b["insert"] not in chaves:
            chaves.append(b["insert"])
    for p in plano["blocos"]:
        c = p.get("insert")
        if c and (lei.livre or p.get("proposto")) and c not in chaves:
            chaves.append(c)
    chaves.sort()

    falhas = []
    _conferir_inserts(pj, chaves, falhas)
    esperados = [] if lei.livre else _letterings_esperados(blocos)
    if not lei.livre:
        _conferir_letterings(esperados, plano["letterings"], falhas)
        _conferir_hook(blocos, plano, falhas)
    _conferir_blocos(blocos, plano["blocos"], falhas)

    detalhes = {"estado": "REPROVA" if falhas else "PASS", "livre": lei.livre, "chaves_de_insert": chaves,
                "arquivos_em_inserts": len(_arquivos_de_insert(pj)),
                "letterings_no_roteiro": len(esperados), "letterings_no_plano": len(plano["letterings"]),
                "blocos": len(blocos), "falhas": falhas, "ancoras_ambiguas": []}
    return Resultado(not falhas, "; ".join(falhas), detalhes)


# --- CLI ---------------------------------------------------------------------------------------------

def _registrar(pj, r):
    if r.ok:
        status.registrar(pj, ETAPA, "ok", motivo=r.motivo or None, detalhes=r.detalhes)
    else:
        status.registrar(pj, ETAPA, "falhou", motivo=r.motivo, detalhes=r.detalhes)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Confere o roteiro.md contra inserts/ e o plano.")
    ap.add_argument("slug")
    ap.add_argument("--estado", help="pasta _local (padrão: a do repo)")
    args = ap.parse_args(argv)
    try:
        pj = pastas.projeto(args.slug, args.estado)
    except ValueError as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        return 2
    try:
        r = rodar(pj)
    except InsumoInvalido as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        if pj.raiz.is_dir():
            status.registrar(pj, ETAPA, "bloqueado", motivo=str(e)[:400])
        return 2
    _registrar(pj, r)
    if r.ok:
        print("PASSA: %d chave(s) de insert, %d letterings conferidos"
              % (len(r.detalhes["chaves_de_insert"]), r.detalhes["letterings_no_roteiro"]))
        return 0
    print("REPROVA: %s" % r.motivo)
    return 1


if __name__ == "__main__":
    sys.exit(main())
