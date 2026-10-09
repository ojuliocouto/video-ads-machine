#!/usr/bin/env python3
"""GATE DA ENTREGA (W5.A, passo 18 da seção 4): o arquivo que sai é o que os gates mediram e o auditor viu?

    python3 scripts/gates/gate_entrega.py <slug> [--estado _local]
    exit 0 libera · 1 bloqueia · 2 insumo inválido (sem arquivo final)

Quem é medido não assina: o montador escreve o laudo, o auditor escreve a nota (`vam auditar`), o aluno aprova o
plano (`vam aprovar`). Este gate só LÊ, e libera quando as três assinaturas apontam para o MESMO arquivo:

  laudo      entrega/laudo.json no contrato, veredito PASS e sha256 igual ao do arquivo final (o laudo de um build
             anterior não serve para o arquivo de agora)
  aprovação  o ok do plano continua vigente (`plano.aprovacao.verificar`): roteiro, projeto, plano e inserts
             não mudaram depois do ok. Entregar um build de um plano que já mudou é entregar o que ninguém aprovou
  nota       entrega/nota.json no contrato (emissor `auditor`), sha256 e caminho iguais aos do arquivo final, e nota
             de NOTA_MINIMA ou mais (a régua da casa, `fase_gate.NOTA_MINIMA`: nota 8, uma rodada)

Resultado no formato de gate do laudo: {nome, etapa: entrega, resultado, saida, medido, limiar, motivo}.
"""
import argparse
import hashlib
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contratos.validar import validar  # noqa: E402
from fase_gate import NOTA_MINIMA  # noqa: E402
from plano import aprovacao  # noqa: E402
from projeto import pastas, status  # noqa: E402

NOME = "gate_entrega"
ETAPA = "entrega"


def _sha(caminho):
    h = hashlib.sha256()
    with open(str(caminho), "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _num(x):
    return ("%.1f" % float(x)).replace(".", ",")


def _ler(caminho, contrato):
    """(dados, problema). Problema é texto quando o arquivo não existe, está quebrado ou fora do contrato."""
    if not caminho.is_file():
        return None, "ausente"
    try:
        dados = status.ler_json(caminho)
    except ValueError as e:
        return None, "ilegível (%s)" % e
    erros = validar(contrato, dados)
    if erros:
        return dados, "fora do contrato: " + "; ".join(str(e) for e in erros[:3])
    return dados, None


def rodar(pj, final=None):
    """Confere laudo, aprovação e nota contra o arquivo final do projeto. Devolve o gate no formato do laudo."""
    final = Path(final) if final else pj.final_9x16
    limiar = {"nota_minima": NOTA_MINIMA}
    if not final.is_file():
        return {"nome": NOME, "etapa": ETAPA, "resultado": "ERRO", "saida": 2, "limiar": limiar,
                "motivo": "o arquivo final não existe (%s): rode vam montar %s" % (pj.relativo(final) if
                                                                                   pj.dentro(final) else final, pj.slug)}
    sha = _sha(final)
    rel = pj.relativo(final)
    motivos = []
    medido = {"arquivo": rel, "sha256": sha}

    laudo, prob = _ler(pj.laudo, "laudo")
    if prob:
        motivos.append("laudo %s: rode vam montar %s" % (prob, pj.slug))
    else:
        medido["laudo"] = laudo["veredito"]
        if laudo["sha256"] != sha or laudo["arquivo"] != rel:
            motivos.append("o laudo é de outro arquivo (sha256 %s..., o final tem %s...): o final mudou depois do "
                           "laudo; rode vam montar de novo" % (laudo["sha256"][:12], sha[:12]))
        elif laudo["veredito"] != "PASS":
            reprovados = [g["nome"] for g in laudo["gates"] if g["resultado"] in ("REPROVA", "ERRO")]
            motivos.append("o laudo REPROVA (%s): corrija e rode vam montar" % ", ".join(reprovados[:6]))

    sit = aprovacao.verificar(pj)
    medido["aprovacao"] = "vigente" if sit.vigente else "vencida"
    if not sit.vigente:
        motivos.append("a aprovação do plano não está vigente: %s" % sit.motivo)

    nota, prob = _ler(pj.nota, "nota")
    if prob == "ausente":
        motivos.append("sem nota do auditor: a auditoria registra a nota com vam auditar %s --nota N" % pj.slug)
    elif prob:
        motivos.append("nota.json %s" % prob)
    else:
        medido["nota"] = nota["nota"]
        if nota["sha256"] != sha or nota["arquivo"] != rel:
            motivos.append("a nota é de outro arquivo (sha256 %s..., o final tem %s...): audite o final de agora"
                           % (nota["sha256"][:12], sha[:12]))
        if float(nota["nota"]) < NOTA_MINIMA:
            motivos.append("nota %s, abaixo do mínimo %d: corrija os achados DESSA auditoria e reconfira os mesmos "
                           "pontos (rodada 2)" % (_num(nota["nota"]), NOTA_MINIMA))
    if motivos:
        return {"nome": NOME, "etapa": ETAPA, "resultado": "REPROVA", "saida": 1, "medido": medido,
                "limiar": limiar, "motivo": "; ".join(motivos)}
    return {"nome": NOME, "etapa": ETAPA, "resultado": "PASS", "saida": 0, "medido": medido, "limiar": limiar}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Libera a entrega só com laudo PASS, aprovação vigente e nota 8+.")
    ap.add_argument("slug")
    ap.add_argument("--estado", help="pasta _local (padrão: a do repo)")
    a = ap.parse_args(argv)
    try:
        pj = pastas.projeto(a.slug, a.estado)
    except ValueError as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        return 2
    if not pj.projeto_json.is_file():
        print("ERRO de insumo: o projeto %r não existe em %s" % (pj.slug, pj.raiz), file=sys.stderr)
        return 2
    g = rodar(pj)
    if g["resultado"] == "PASS":
        status.registrar(pj, NOME, "ok", detalhes=g["medido"])
        print("ENTREGA LIBERADA: nota %s, laudo PASS, aprovação vigente (%s)" % (_num(g["medido"]["nota"]),
                                                                                g["medido"]["arquivo"]))
    else:
        status.registrar(pj, NOME, "falhou" if g["saida"] == 1 else "bloqueado", motivo=g["motivo"][:600])
        print("ENTREGA BLOQUEADA: %s" % g["motivo"], file=sys.stderr)
    return g["saida"]


if __name__ == "__main__":
    sys.exit(main())
