"""O que os subcomandos do `vam` dividem: saídas, `--estado`, o projeto existente e a mensagem de erro.

Saídas (as mesmas dos gates): 0 fez · 1 defeito medido · 2 pedido ou insumo inválido. Toda falha vira UMA mensagem
no stderr, com o comando que resolve; nunca traceback. Este módulo não é um subcomando (o `vam.py` só descobre os
módulos de `cli/` que têm `registrar`).
"""
import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path

SAIDA_OK, SAIDA_DEFEITO, SAIDA_USO = 0, 1, 2


class PedidoInvalido(Exception):
    """O pedido não dá para atender (saída 2). A mensagem diz o que fazer."""


def opcao_estado(p):
    """`--estado`: o `_local` (escondido; os testes passam o deles, o aluno usa o do repo)."""
    p.add_argument("--estado", default=None, help=argparse.SUPPRESS)


def estado(args):
    from projeto import pastas
    return Path(args.estado) if getattr(args, "estado", None) else pastas.estado_padrao()


def pastas_do(args):
    """PastasProjeto do slug pedido (PedidoInvalido se o slug é inválido)."""
    from projeto import pastas
    try:
        return pastas.projeto(args.slug, estado(args))
    except ValueError as e:
        raise PedidoInvalido("slug inválido: %s" % e)


def projeto_existente(args):
    """(PastasProjeto, projeto.json completo). PedidoInvalido se o projeto não existe ou o projeto.json é inválido."""
    from projeto import modelo
    pj = pastas_do(args)
    if not pj.projeto_json.is_file():
        raise PedidoInvalido("o projeto %r não existe em %s: crie com `vam novo %s --look <look> --sem-trilha \"motivo\"`"
                             % (pj.slug, pj.raiz, pj.slug))
    try:
        return pj, modelo.carregar(pj.projeto_json)
    except modelo.ContratoInvalido as e:
        raise PedidoInvalido(str(e))


def exigir_modo(pj, projeto, modo, comando):
    if projeto["modo"] != modo:
        raise PedidoInvalido("o projeto %r é do modo %s; `vam %s` serve o modo %s (o modo %s tem `vam %s`)"
                             % (pj.slug, projeto["modo"], comando, modo, projeto["modo"], projeto["modo"]))


def erro(comando, texto):
    print("vam %s: %s" % (comando, texto), file=sys.stderr)


def sha256_arquivo(caminho):
    h = hashlib.sha256()
    with open(str(caminho), "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def copiar_conferido(origem, destino, sobrescrever=False):
    """Copia `origem` para `destino` (nunca mexe na origem) e confere o sha256. Devolve True se copiou, False se o
    destino já era o mesmo arquivo. PedidoInvalido se o destino é outro e `sobrescrever` não foi pedido."""
    origem, destino = Path(origem).expanduser(), Path(destino)
    if not origem.is_file():
        raise PedidoInvalido("o arquivo não existe: %s" % origem)
    if destino.is_file():
        if sha256_arquivo(destino) == sha256_arquivo(origem):
            return False
        if not sobrescrever:
            raise PedidoInvalido("%s já existe e é outro arquivo: use --sobrescrever se é para trocar (isso vence a "
                                 "aprovação do plano)" % destino.name)
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".parcial")
    shutil.copy2(str(origem), str(parcial))
    if sha256_arquivo(parcial) != sha256_arquivo(origem):
        parcial.unlink()
        raise PedidoInvalido("a cópia de %s não confere com a origem (sha256): tente de novo" % origem.name)
    os.replace(str(parcial), str(destino))
    return True


def rodar(comando, funcao, args):
    """Chama `funcao(args)` convertendo PedidoInvalido em saída 2 com UMA mensagem."""
    try:
        return int(funcao(args) or 0)
    except PedidoInvalido as e:
        erro(comando, str(e))
        return SAIDA_USO
