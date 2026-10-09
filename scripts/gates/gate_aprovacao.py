#!/usr/bin/env python3
"""GATE APROVAÇÃO (W3.B): o plano tem um ok do aluno que continua valendo?

    python3 scripts/gates/gate_aprovacao.py <slug> [--estado _local]
    exit 0 passa · 1 reprova · 2 insumo inválido (slug inválido ou projeto que não existe)

É o primeiro gate do `vam montar`: sem aprovação vigente do plano, não se monta. Vigente quer dizer que
`plano/aprovacao.json` foi escrito por `plano.aprovacao` (emissor fixo), traz o ok do aluno e o sha256
dos quatro arquivos aprovados (roteiro.md, projeto.json, plano/plano.json e render/inserts.json) e os
quatro continuam byte a byte como estavam. Mudar 1 byte de qualquer um vence a aprovação:

    REPROVA: aprovação vencida: roteiro.md mudou depois do ok de 2026-10-08T22:30:00-03:00. Rode vam plano...

Reprova também quando:
  - não há aprovação (nunca houve ok, ou o arquivo está ilegível, inválido ou com emissor trocado);
  - a aprovação aponta um caminho que não é o do arquivo que o montar lê;
  - o plano.json aprovado não passa nas 6 seções, na checklist ou no contrato, ou foi medido de outra versão do
    roteiro ou do projeto (aprovação refeita à mão com sha novo não engana).

O gate só LÊ: quem escreve a aprovação é `plano/aprovacao.py`, e só ele.

Resultado: `Resultado(ok, motivo, detalhes)`; `detalhes["estado"]` é PASS ou REPROVA e `detalhes["arquivos"]` diz
quais dos quatro seguem vigentes (a W5.A copia para o laudo). A CLI grava o resultado em status.json
(etapa `gate_aprovacao`).
"""
import argparse
import os
import sys
from collections import namedtuple

if __name__ == "__main__":      # rodado direto: scripts/gates/gate_aprovacao.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plano import aprovacao  # noqa: E402
from projeto import pastas, status  # noqa: E402

ETAPA = "gate_aprovacao"
Resultado = namedtuple("Resultado", "ok motivo detalhes")


def rodar(pastas_projeto):
    """Confere a aprovação do plano do projeto. `pastas_projeto` é o `projeto.pastas.PastasProjeto`."""
    sit = aprovacao.verificar(pastas_projeto)
    detalhes = dict(sit.detalhes)
    if sit.vigente:
        detalhes["estado"] = "PASS"
        return Resultado(True, "", detalhes)
    detalhes["estado"] = "REPROVA"
    detalhes["mudados"] = list(sit.mudados)
    return Resultado(False, sit.motivo, detalhes)


def _registrar(pj, r):
    if r.ok:
        status.registrar(pj, ETAPA, "ok", motivo=r.motivo or None, detalhes=r.detalhes)
    else:
        status.registrar(pj, ETAPA, "falhou", motivo=r.motivo, detalhes=r.detalhes)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Confere se o plano tem aprovação vigente (sha256 dos 4 arquivos).")
    ap.add_argument("slug")
    ap.add_argument("--estado", help="pasta _local (padrão: a do repo)")
    args = ap.parse_args(argv)
    try:
        pj = pastas.projeto(args.slug, args.estado)
        if not pj.raiz.is_dir():
            raise ValueError("o projeto %r não existe em %s: crie com vam novo" % (pj.slug, pj.raiz))
    except ValueError as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        return 2
    r = rodar(pj)
    _registrar(pj, r)
    if r.ok:
        print("PASSA: plano aprovado em %s, os 4 arquivos como estavam" % r.detalhes["aprovado_em"])
        return 0
    print("REPROVA: %s" % r.motivo)
    return 1


if __name__ == "__main__":
    sys.exit(main())
