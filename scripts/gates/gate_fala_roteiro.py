#!/usr/bin/env python3
"""GATE FALA x ROTEIRO (W3.C): o que foi dito no áudio limpo cobre o roteiro.md?

    python3 scripts/gates/gate_fala_roteiro.py <slug> [--estado _local]
    exit 0 passa · 1 reprova · 2 insumo inválido (sem roteiro, sem voz/limpo.mp3, sem transcritor)

A voz limpa (`voz/limpo.mp3`) é transcrita de novo (backend e cache do `audio.transcrever`, com o
glossário do aluno) e a transcrição é alinhada, palavra a palavra, com a fala do roteiro.md. Uma
palavra do roteiro que não aparece na fala conta como FALTANDO. Reprova quando:
  - mais de 2% das palavras do roteiro estão faltando;
  - uma sequência de 3 palavras seguidas ou mais sumiu (a fala perdeu um pedaço de frase).

Palavra a mais na fala (improviso) não reprova: o gate cobra o que SUMIU do roteiro, e o número de
palavras extras vai no relatório.

Troca de palavra: só o que o aluno DECLAROU em `_local/glossario.json`.
  - `variantes` de um termo corrigem o que o ASR escreve errado (a variante vira a grafia declarada);
  - `equivalencias` aceitam uma diferença de fala do roteiro para a fala (roteiro "para", fala "pra").
Nada mais é aceito e nada é reescrito em disco: o revisor de copy antigo trocava o nome de um
produto por outro em qualquer anúncio e estragava a legenda de quem fala de computação em nuvem.
Maiúscula, acento e pontuação não contam (mesma norma de palavra de `contratos.validar.palavras`).

Resultado: `Resultado(ok, motivo, detalhes)`; `detalhes["estado"]` é PASS ou REPROVA. A CLI grava em
status.json (etapa `gate_fala_roteiro`).
"""
import argparse
import difflib
import os
import sys
from collections import namedtuple

if __name__ == "__main__":      # rodado direto: scripts/gates/gate_fala_roteiro.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contratos.validar import normalizar_palavra, palavras  # noqa: E402
from entrada import roteiro_md  # noqa: E402
from projeto import glossario, pastas, status  # noqa: E402

ETAPA = "gate_fala_roteiro"
Resultado = namedtuple("Resultado", "ok motivo detalhes")

# Mais que isso das palavras do roteiro faltando na fala reprova. Origem: PLANO-VAM W3.C ("mais de
# 2% das palavras faltando"). O caso que motivou o gate: o corte de áudio comeu 4 palavras de um
# anúncio real e só apareceu no vídeo pronto (produzir_ad.py:261, agosto/2026).
FALTANDO_MAX = 0.02
# Uma sequência assim de palavras sumidas reprova mesmo abaixo de FALTANDO_MAX. Origem: PLANO-VAM
# W3.C ("sequência de 3 palavras ou mais"); "uma campanha" virando "panha" foi o menor dano que
# apareceu só no vídeo pronto (agosto/2026).
SEQUENCIA_MAX = 3
MAX_TRECHOS_NO_RELATORIO = 10

Comparacao = namedtuple("Comparacao", "faltando_idx maior_sequencia extras")


class InsumoInvalido(Exception):
    """Falta arquivo ou o arquivo não pôde ser lido: não dá nem para reprovar (exit 2)."""


# --- alinhamento (puro) ----------------------------------------------------------------------------

def _resolver_troca(r, f, equivalencias):
    """Dentro de um trecho que difere (roteiro `r`, fala `f`): casa as equivalências declaradas e as
    palavras iguais que sobram. Devolve (índices de `r` que faltaram, palavras extras de `f`)."""
    faltando, i, j = [], 0, 0
    while i < len(r):
        for rt, ft in equivalencias:
            if r[i:i + len(rt)] == rt and f[j:j + len(ft)] == ft:
                i, j = i + len(rt), j + len(ft)
                break
        else:
            if j < len(f) and r[i] == f[j]:
                i, j = i + 1, j + 1
            else:
                faltando.append(i)
                i += 1
    return faltando, len(f) - j


def _maior_sequencia(indices):
    maior = atual = 0
    anterior = None
    for k in indices:
        atual = atual + 1 if anterior is not None and k == anterior + 1 else 1
        maior = max(maior, atual)
        anterior = k
    return maior


def comparar(roteiro, fala, equivalencias=()):
    """Alinha duas listas de palavras NORMALIZADAS. `equivalencias`: [(palavras do roteiro, palavras
    da fala)], cada lado uma lista, valendo só do roteiro para a fala."""
    eqs = sorted(((list(a), list(b)) for a, b in equivalencias if a and b), key=lambda e: -len(e[0]))
    faltando, extras = [], 0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, roteiro, fala, autojunk=False).get_opcodes():
        if op == "delete":
            faltando.extend(range(i1, i2))
        elif op == "insert":
            extras += j2 - j1
        elif op == "replace":
            perdidas, sobra = _resolver_troca(roteiro[i1:i2], fala[j1:j2], eqs)
            faltando.extend(i1 + k for k in perdidas)
            extras += sobra
    return Comparacao(faltando, _maior_sequencia(faltando), extras)


# --- insumos -----------------------------------------------------------------------------------------

def _roteiro(pj):
    if not pj.roteiro.is_file():
        raise InsumoInvalido("roteiro.md não existe em %s: cole o roteiro e grave o projeto antes" % pj.raiz)
    try:
        lei = roteiro_md.ler_arquivo(pj.roteiro)
    except ValueError as e:
        raise InsumoInvalido(str(e))
    if lei.erros:
        raise InsumoInvalido("o roteiro.md está fora da convenção:\n%s" % roteiro_md.formatar_erros(lei.erros))
    return lei


def _glossario(pj):
    try:
        return glossario.carregar(pj.estado)
    except ValueError as e:
        raise InsumoInvalido(str(e))


def _asr_padrao(pj, g):
    """Transcreve com o backend da máquina; o cache fica na pasta de render DO PROJETO."""
    def asr(caminho):
        from audio import transcrever as T
        try:
            return T.transcrever(caminho, cache_dir=pj.render_dir / "cache_asr", glossario=g)
        except T.SemTranscritor as e:
            raise InsumoInvalido(str(e))
    return asr


def _tokens_da_fala(brutas, g):
    """Palavras normalizadas da transcrição, com as variantes do glossário já trocadas."""
    lista = [p if isinstance(p, dict) else {"text": str(p), "start": 0.0, "end": 0.0} for p in brutas]
    corrigidas = glossario.corrigir_palavras(lista, g)
    return palavras(" ".join(str(p["text"]) for p in corrigidas))


def _trechos(originais, indices):
    """Os trechos faltando como texto, na ordem ('uma campanha', 'tempo')."""
    saida, atual, anterior = [], [], None
    for k in indices:
        if anterior is not None and k != anterior + 1:
            saida.append(" ".join(atual))
            atual = []
        atual.append(originais[k])
        anterior = k
    if atual:
        saida.append(" ".join(atual))
    return saida


def rodar(pastas_projeto, asr=None):
    """Confere a fala contra o roteiro. `asr(caminho) -> [{text, start, end}]` troca o transcritor
    (os testes passam uma função simulada). Levanta InsumoInvalido quando não há o que conferir."""
    pj = pastas_projeto
    lei = _roteiro(pj)
    if not pj.voz_limpo.is_file():
        raise InsumoInvalido("voz/limpo.mp3 não existe em %s: higienize a voz antes de conferir a fala" % pj.raiz)
    g = _glossario(pj)
    asr = asr or _asr_padrao(pj, g)
    brutas = list(asr(pj.voz_limpo))
    fala = _tokens_da_fala(brutas, g)
    if not fala:
        raise InsumoInvalido("transcrição vazia: o transcritor não ouviu nenhuma palavra em voz/limpo.mp3 "
                             "(áudio mudo, corrompido ou idioma errado)")

    originais = [w for w in lei.fala_completa().split() if normalizar_palavra(w)]
    roteiro = lei.sequencia_de_palavras()
    eqs = [(palavras(a), palavras(b)) for a, b in glossario.equivalencias(g)]
    cmp = comparar(roteiro, fala, eqs)
    n, perdidas = len(roteiro), len(cmp.faltando_idx)
    fracao = perdidas / float(n) if n else 0.0
    trechos = _trechos(originais, cmp.faltando_idx)

    motivos = []
    if fracao > FALTANDO_MAX:
        motivos.append("faltam %d de %d palavras do roteiro na fala (%.1f%%, o limite é %d%%): %s"
                       % (perdidas, n, fracao * 100, round(FALTANDO_MAX * 100), "; ".join(trechos[:5])))
    if cmp.maior_sequencia >= SEQUENCIA_MAX:
        motivos.append("sumiram %d palavras seguidas (%d ou mais reprova): %s"
                       % (cmp.maior_sequencia, SEQUENCIA_MAX,
                          "; ".join(t for t in trechos if len(t.split()) >= SEQUENCIA_MAX)[:200]))
    detalhes = {"estado": "REPROVA" if motivos else "PASS", "palavras_roteiro": n,
                "palavras_fala": len(fala), "faltando": perdidas, "fracao_faltando": round(fracao, 4),
                "maior_sequencia": cmp.maior_sequencia, "extras": cmp.extras,
                "trechos_faltando": trechos[:MAX_TRECHOS_NO_RELATORIO],
                "limiares": {"faltando_max": FALTANDO_MAX, "sequencia_max": SEQUENCIA_MAX}}
    return Resultado(not motivos, "; ".join(motivos), detalhes)


# --- CLI ---------------------------------------------------------------------------------------------

def _registrar(pj, r):
    if r.ok:
        status.registrar(pj, ETAPA, "ok", motivo=r.motivo or None, detalhes=r.detalhes)
    else:
        status.registrar(pj, ETAPA, "falhou", motivo=r.motivo, detalhes=r.detalhes)


def main(argv=None, asr=None):
    ap = argparse.ArgumentParser(description="Confere a fala do áudio limpo contra o roteiro.md.")
    ap.add_argument("slug")
    ap.add_argument("--estado", help="pasta _local (padrão: a do repo)")
    args = ap.parse_args(argv)
    try:
        pj = pastas.projeto(args.slug, args.estado)
    except ValueError as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        return 2
    try:
        r = rodar(pj, asr=asr)
    except InsumoInvalido as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        if pj.raiz.is_dir():
            status.registrar(pj, ETAPA, "bloqueado", motivo=str(e)[:400])
        return 2
    _registrar(pj, r)
    if r.ok:
        print("PASSA: %d palavras do roteiro, %d faltando, %d a mais na fala"
              % (r.detalhes["palavras_roteiro"], r.detalhes["faltando"], r.detalhes["extras"]))
        return 0
    print("REPROVA: %s" % r.motivo)
    return 1


if __name__ == "__main__":
    sys.exit(main())
