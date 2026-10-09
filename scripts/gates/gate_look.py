#!/usr/bin/env python3
"""GATE DO LOOK (W3.C): o look do HeyGen do projeto existe, está aprovado e é vertical.

Substitui a lista cravada do motor antigo (LOOKS_OK_9X16 e LOOKS_VETADOS dentro do produzir_ad):
quem decide quais looks servem é o aluno, em `_local/looks.json`, e a prova é a conferência do
avatar gerado, não o nome do look.

    python3 scripts/gates/gate_look.py <slug> [--estado _local]
    exit 0 passa (ou pulado) · 1 reprova · 2 insumo inválido (falta arquivo, JSON quebrado)

Reprova quando:
  - o look do projeto.json não existe em looks.json;
  - o look não está aprovado, ou a aprovação venceu (o arquivo de conferência mudou ou sumiu:
    `projeto.looks` amarra a aprovação ao sha256 dele);
  - o look é horizontal: no cadastro (o contrato do looks.json recusa) ou no avatar que o HeyGen
    gerou (largura maior ou igual à altura na conferência). Look horizontal entra com tarja e o
    rosto fica com 35% do quadro (medido em agosto, produzir_ad.py);
  - a conferência do avatar foi gravada como `reprovada`.

Modos que não usam avatar (gravado, oneshot) ficam PULADOS: não há look para conferir.

Resultado: `Resultado(ok, motivo, detalhes)`. `detalhes["estado"]` é PASS, REPROVA ou PULADO e é
o que a W5.A copia para o laudo. A CLI grava o resultado em status.json (etapa `gate_look`).
"""
import argparse
import os
import sys
from collections import namedtuple

if __name__ == "__main__":      # rodado direto: scripts/gates/gate_look.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from projeto import looks, modelo, pastas, status  # noqa: E402

ETAPA = "gate_look"
Resultado = namedtuple("Resultado", "ok motivo detalhes")


class InsumoInvalido(Exception):
    """Falta arquivo ou o arquivo não pôde ser lido: não dá nem para reprovar (exit 2)."""


def _projeto(pj):
    try:
        return modelo.carregar(pj.projeto_json)
    except FileNotFoundError:
        raise InsumoInvalido("projeto.json não existe em %s: crie o projeto antes (vam novo)" % pj.raiz)
    except modelo.ContratoInvalido as e:
        raise InsumoInvalido(str(e))


def _reprova(motivo, **detalhes):
    detalhes["estado"] = "REPROVA"
    return Resultado(False, motivo, detalhes)


def _looks_do_aluno(pj, nome):
    """looks.json validado, ou o Resultado de reprovação se o PROBLEMA é o look do projeto ser horizontal."""
    try:
        return looks.carregar(pj.estado), None
    except looks.LookInvalido as e:
        horizontal = [x for x in e.erros if "orientacao" in str(x) and nome in str(x)]
        if horizontal:
            return None, _reprova("o look %r é horizontal e não entra: ele vira tarja no 9x16 e o rosto fica "
                                  "pequeno. Gere um look vertical no HeyGen (%s)" % (nome, horizontal[0]),
                                  look=nome)
        raise InsumoInvalido(str(e))


def _conferencia(pj, look):
    caminho = pj.estado / look["conferencia"]["arquivo"]
    try:
        return status.ler_json(caminho)
    except (OSError, ValueError) as e:
        raise InsumoInvalido("não consegui ler a conferência do look (%s): %s" % (caminho, e))


def rodar(pastas_projeto):
    """Confere o look do projeto. `pastas_projeto` é o `projeto.pastas.PastasProjeto`."""
    pj = pastas_projeto
    projeto = _projeto(pj)
    modo = projeto["modo"]
    if modo != "avatar":
        return Resultado(True, "pulado: o modo %s não usa look do HeyGen" % modo,
                         {"estado": "PULADO", "modo": modo})
    nome = projeto["look"]
    todos, reprovado = _looks_do_aluno(pj, nome)
    if reprovado:
        return reprovado
    sit = looks.verificar(nome, pj.estado)
    if not sit.aprovado:
        return _reprova(sit.motivo, look=nome)

    look = todos["looks"][nome]
    conf = _conferencia(pj, look)
    avatar = conf.get("avatar") or {}
    larg, alt = avatar.get("largura"), avatar.get("altura")
    if not (isinstance(larg, int) and isinstance(alt, int)):
        raise InsumoInvalido("a conferência do look %r não traz a largura e a altura do avatar: "
                             "rode a conferência do avatar de novo" % nome)
    if conf.get("resultado") == "reprovada":
        motivos = "; ".join(conf.get("reprovacoes") or []) or "sem motivo registrado"
        return _reprova("a conferência do avatar do look %r está reprovada (%s): regere o avatar e "
                        "aprove o look de novo" % (nome, motivos), look=nome)
    if alt <= larg:
        return _reprova("o avatar do look %r saiu horizontal (%dx%d): look horizontal não entra no 9x16"
                        % (nome, larg, alt), look=nome, avatar="%dx%d" % (larg, alt))
    return Resultado(True, "", {"estado": "PASS", "look": nome, "plano": look["plano"],
                                "avatar": "%dx%d" % (larg, alt), "conferencia": look["conferencia"]["arquivo"]})


def _registrar(pj, r):
    if r.ok:
        status.registrar(pj, ETAPA, "ok", motivo=r.motivo or None, detalhes=r.detalhes)
    else:
        status.registrar(pj, ETAPA, "falhou", motivo=r.motivo, detalhes=r.detalhes)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Confere o look do HeyGen do projeto.")
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
        print("PASSA: %s" % (r.motivo or "look %s aprovado e vertical" % r.detalhes.get("look")))
        return 0
    print("REPROVA: %s" % r.motivo)
    return 1


if __name__ == "__main__":
    sys.exit(main())
