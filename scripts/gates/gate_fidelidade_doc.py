#!/usr/bin/env python3
"""GATE FIDELIDADE AO DOC (W3.C): o que o Google Doc do aluno manda nos comentários chega ao projeto.

    python3 scripts/gates/gate_fidelidade_doc.py <slug> [--estado _local] [--aba NOME]
                                                 [--importado importado.json]
    exit 0 passa (ou pulado) · 1 reprova · 2 insumo inválido (sem token do Google, doc fora da
    convenção, arquivo ilegível)

OPCIONAL: só vale para projeto que nasceu de um Doc (`origem.tipo = "doc_google"` no projeto.json).
Os outros caminhos de entrada (texto colado, .md, .txt) ficam PULADOS, e o gate nem chama o Google.
O Doc é lido por `entrada.doc_google`, com o token OAuth do PRÓPRIO aluno
(GOOGLE_OAUTH_ACCESS_TOKEN): nenhuma planilha, nenhum arquivo de token da máquina. `--importado`
lê o resultado de `doc_google.importar` já salvo em JSON (conferência sem rede).

Regras (cada uma reprova com o comentário e o bloco citados):
  - comentário com N links são N assets no bloco em que a âncora cai, nunca 1. "Pipoca" é uma
    sequência de peças: pipoca incompleta (N links, menos de N assets no projeto) reprova. Foi o que
    transformou um comentário de 17 links em UMA imagem parada em 3 anúncios e errou 6 de 10;
  - pipoca com menos de 2 links reprova (sequência precisa de pelo menos 2 peças);
  - a âncora tem que cair em UM bloco do roteiro. Âncora que cai em mais de um bloco é ambígua e
    reprova sem o número da ocorrência (`nth` no comentário, ou em `doc_ancoras.json` na pasta do
    projeto: {"<id do comentário>": 2}); sem lugar nenhum no roteiro também reprova;
  - o bloco do comentário tem que ser `insert`, e a chave dele tem que ter o arquivo em inserts/;
  - estrutura: o roteiro.md do projeto tem os mesmos blocos do doc (número, tipo e chave de insert).

Como o projeto declara as peças de uma pipoca: `inserts/<chave>.partes.json`, uma lista de textos
(id do Drive, URL ou nome do arquivo de cada peça). Com esse arquivo, TODO link do comentário tem que
aparecer em alguma peça. Sem ele, o arquivo da chave vale como 1 asset: comentário com 2 links ou
mais reprova. Comentário sem link é só nota e não é conferido.

Exceção declarada, sempre com motivo escrito, no `excecoes` do projeto.json (contrato do projeto):
  {"regra": "fidelidade_doc.<id do comentário em minúsculas>", "motivo": "..."}  libera aquele comentário
  {"regra": "fidelidade_doc.estrutura", "motivo": "..."}                         libera o desvio de estrutura

Resultado: `Resultado(ok, motivo, detalhes)`; a CLI grava em status.json (etapa `gate_fidelidade_doc`).
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from collections import namedtuple

if __name__ == "__main__":      # rodado direto: scripts/gates/gate_fidelidade_doc.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from entrada import doc_google, roteiro_md  # noqa: E402
from projeto import modelo, pastas, status  # noqa: E402

ETAPA = "gate_fidelidade_doc"
Resultado = namedtuple("Resultado", "ok motivo detalhes")

PREFIXO_EXCECAO = "fidelidade_doc."
EXCECAO_ESTRUTURA = "estrutura"
SUFIXO_PARTES = ".partes.json"
ARQUIVO_NTH = "doc_ancoras.json"
PIPOCA_MIN_PECAS = 2        # PLANO-VAM W3.C: pipoca é sequência de várias peças, nunca imagem parada


class InsumoInvalido(Exception):
    """Falta arquivo ou o arquivo não pôde ser lido: não dá nem para reprovar (exit 2)."""


# --- insumos ---------------------------------------------------------------------------------------

def _projeto(pj):
    try:
        return modelo.carregar(pj.projeto_json)
    except FileNotFoundError:
        raise InsumoInvalido("projeto.json não existe em %s: crie o projeto antes (vam novo)" % pj.raiz)
    except modelo.ContratoInvalido as e:
        raise InsumoInvalido(str(e))


def _excecoes(projeto):
    """{sufixo da regra em minúsculas: motivo} das exceções `fidelidade_doc.*` do projeto."""
    saida = {}
    for ex in projeto.get("excecoes", []):
        regra = ex["regra"].casefold()
        if regra.startswith(PREFIXO_EXCECAO):
            saida[regra[len(PREFIXO_EXCECAO):]] = ex["motivo"]
    return saida


def _ler_roteiro_do_projeto(pj):
    if not pj.roteiro.is_file():
        raise InsumoInvalido("roteiro.md não existe em %s" % pj.raiz)
    try:
        lei = roteiro_md.ler_arquivo(pj.roteiro)
    except ValueError as e:
        raise InsumoInvalido(str(e))
    if lei.erros:
        raise InsumoInvalido("o roteiro.md do projeto está fora da convenção:\n%s"
                             % roteiro_md.formatar_erros(lei.erros))
    return lei


def _ler_roteiro_do_doc(importado):
    texto = importado.get("roteiro_md") if isinstance(importado, dict) else None
    if not isinstance(texto, str) or not isinstance(importado.get("comentarios"), list):
        raise InsumoInvalido("o Doc importado não traz 'roteiro_md' e 'comentarios': use o resultado de "
                             "entrada.doc_google.importar")
    lei = roteiro_md.ler(texto)
    if lei.erros:
        raise InsumoInvalido("o roteiro do Doc está fora da convenção do roteiro.md:\n%s"
                             % roteiro_md.formatar_erros(lei.erros))
    return lei, texto


def _chave(texto):
    """Como a âncora é comparada: sem maiúscula, sem acento, só letras e números."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def _textos_dos_blocos(texto):
    """O texto de cada bloco do roteiro, na ordem, pela mesma regra de linhas do leitor do roteiro."""
    linhas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    dirigido = any(l.lstrip().startswith("[") for l in linhas)
    blocos = []
    if dirigido:
        for l in linhas:
            s = l.strip()
            if not s or s.startswith("#"):
                continue
            if s.startswith("[") or not blocos:
                blocos.append(s)
            else:
                blocos[-1] += " " + s
    else:
        atual = None
        for l in linhas:
            s = l.strip()
            if s.startswith("#"):
                continue
            if not s:
                atual = None
            elif atual is None:
                blocos.append(s)
                atual = len(blocos) - 1
            else:
                blocos[atual] += " " + s
    return [_chave(b) for b in blocos]


def _ident(asset):
    """O que identifica uma peça: o id do Drive, ou a URL quando não é do Drive."""
    return asset["id"] if asset.get("tipo") == "drive" and asset.get("id") else asset["url"]


def _descricao(bloco):
    return "%s: %s" % (bloco["tipo"], bloco["insert"]) if bloco["tipo"] == "insert" else bloco["tipo"]


def _arquivos(pj, chave):
    if not pj.inserts_dir.is_dir():
        return []
    return sorted(f.name for f in pj.inserts_dir.iterdir()
                  if f.is_file() and not f.name.startswith(".") and not f.name.endswith(SUFIXO_PARTES)
                  and f.stem == chave)


def _partes(pj, chave):
    """A lista de peças declarada em inserts/<chave>.partes.json, ou None se não há o arquivo."""
    arq = pj.inserts_dir / (chave + SUFIXO_PARTES)
    if not arq.is_file():
        return None
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise InsumoInvalido("não consegui ler %s: %s" % (arq.name, e))
    if not isinstance(dados, list) or not all(isinstance(x, str) for x in dados):
        raise InsumoInvalido("%s tem que ser uma lista de textos (id do Drive, URL ou nome do arquivo de "
                             "cada peça da pipoca)" % arq.name)
    return dados


# --- a conferência -----------------------------------------------------------------------------------

def _bloco_do_comentario(c, textos, nths, falhas, ambiguas):
    """Índice do bloco em que a âncora do comentário cai, ou None (e a falha já anotada)."""
    linhas = [l for l in (c.get("ancora") or "").splitlines() if _chave(l)]
    procurada = _chave(linhas[0]) if linhas else ""
    candidatos = [i for i, t in enumerate(textos) if procurada and procurada in t]
    if not candidatos:
        falhas.append("o comentário %s tem asset mas está sem âncora no roteiro (trecho %r): ancore o "
                      "comentário na linha do bloco" % (c["id"], (c.get("ancora") or "")[:60]))
        return None
    nth = c.get("nth", nths.get(c["id"]))
    if nth is not None and (not isinstance(nth, int) or isinstance(nth, bool) or nth < 1
                            or nth > len(candidatos)):
        falhas.append("o comentário %s pede a ocorrência %s, mas a âncora aparece %d vez(es) no roteiro"
                      % (c["id"], nth, len(candidatos)))
        return None
    if len(candidatos) > 1 and nth is None:
        ambiguas.append(c["id"])
        falhas.append("âncora ambígua no comentário %s: %r cai em %d blocos (%s); diga qual com o número da "
                      "ocorrência (nth)" % (c["id"], (c.get("ancora") or "")[:40], len(candidatos),
                                            ", ".join(str(i) for i in candidatos)))
        return None
    return candidatos[(nth or 1) - 1]


def _conferir_estrutura(lei_proj, lei_doc, falhas):
    if len(lei_proj.blocos) != len(lei_doc.blocos):
        falhas.append("o roteiro.md do projeto tem %d blocos e o doc tem %d"
                      % (len(lei_proj.blocos), len(lei_doc.blocos)))
        return
    for i, (p, d) in enumerate(zip(lei_proj.blocos, lei_doc.blocos)):
        if (p["tipo"], p["insert"]) != (d["tipo"], d["insert"]):
            falhas.append("bloco %d: o doc marca %s e o roteiro.md tem %s" % (i, _descricao(d), _descricao(p)))


def _conferir_bloco(pj, i, bloco, ags, falhas):
    """Confere as peças de UM bloco contra inserts/. `ags` = {"comentarios": [ids], "assets": [...]}"""
    ids = ", ".join(ags["comentarios"])
    n = len(ags["assets"])
    if bloco["tipo"] != "insert":
        falhas.append("o comentário %s marca %d asset(s) no bloco %d, que é %s e não é insert"
                      % (ids, n, i, bloco["tipo"]))
        return
    chave = bloco["insert"]
    arquivos = _arquivos(pj, chave)
    if not arquivos:
        falhas.append("o insert %r do bloco %d (comentário %s, %d link(s)) está sem arquivo em inserts/"
                      % (chave, i, ids, n))
        return
    if len(arquivos) > 1:
        falhas.append("o insert %r do bloco %d tem mais de um arquivo (%s)" % (chave, i, ", ".join(arquivos)))
        return
    declaradas = _partes(pj, chave)
    if declaradas is None:
        if n > 1:
            falhas.append("pipoca incompleta no bloco %d: o comentário %s marca %d links e o projeto tem 1 asset "
                          "(%s). Se esse arquivo junta as peças, liste-as em inserts/%s%s"
                          % (i, ids, n, arquivos[0], chave, SUFIXO_PARTES))
        return
    juntas = " ".join(x.casefold() for x in declaradas)
    faltam = [_ident(a) for a in ags["assets"] if _ident(a).casefold() not in juntas]
    if faltam:
        falhas.append("%s no bloco %d (comentário %s): faltam em inserts/%s%s %d de %d peça(s): %s"
                      % ("pipoca incompleta" if n > 1 else "asset ausente", i, ids, chave, SUFIXO_PARTES,
                         len(faltam), n, ", ".join(faltam)))


def rodar(pastas_projeto, importado, nths=None):
    """Confere o projeto contra o Doc importado (`entrada.doc_google.importar`). `nths`: {id do
    comentário: ocorrência da âncora}. Levanta InsumoInvalido quando não há o que conferir."""
    pj = pastas_projeto
    projeto = _projeto(pj)
    excecoes = _excecoes(projeto)
    lei_proj = _ler_roteiro_do_projeto(pj)
    lei_doc, texto_doc = _ler_roteiro_do_doc(importado)
    textos = _textos_dos_blocos(texto_doc)
    nths = nths or {}
    falhas, ambiguas, usadas = [], [], {}

    if EXCECAO_ESTRUTURA in excecoes:
        usadas[EXCECAO_ESTRUTURA] = excecoes[EXCECAO_ESTRUTURA]
    else:
        _conferir_estrutura(lei_proj, lei_doc, falhas)

    por_bloco, com_asset = {}, 0
    for c in importado["comentarios"]:
        assets = c.get("assets") or []
        if not assets:
            continue                    # comentário sem link é nota
        com_asset += 1
        cid = c["id"]
        if cid.casefold() in excecoes:
            usadas[cid] = excecoes[cid.casefold()]
            continue
        if c.get("pipoca") and len(assets) < PIPOCA_MIN_PECAS:
            falhas.append("o comentário %s é pipoca mas tem %d link: uma sequência precisa de pelo menos %d peças"
                          % (cid, len(assets), PIPOCA_MIN_PECAS))
            continue
        i = _bloco_do_comentario(c, textos, nths, falhas, ambiguas)
        if i is None:
            continue
        ags = por_bloco.setdefault(i, {"comentarios": [], "assets": [], "vistos": set()})
        ags["comentarios"].append(cid)
        for a in assets:
            if _ident(a) not in ags["vistos"]:
                ags["vistos"].add(_ident(a))
                ags["assets"].append(a)

    if len(lei_doc.blocos) == len(textos):
        for i in sorted(por_bloco):
            _conferir_bloco(pj, i, lei_doc.blocos[i], por_bloco[i], falhas)

    detalhes = {"estado": "REPROVA" if falhas else "PASS", "comentarios_com_asset": com_asset,
                "assets_esperados": sum(len(a["assets"]) for a in por_bloco.values()),
                "blocos_com_asset": sorted(por_bloco), "ancoras_ambiguas": ambiguas,
                "excecoes_usadas": usadas, "falhas": falhas}
    return Resultado(not falhas, "; ".join(falhas), detalhes)


# --- CLI ---------------------------------------------------------------------------------------------

def _nths_do_projeto(pj):
    arq = pj.raiz / ARQUIVO_NTH
    if not arq.is_file():
        return {}
    try:
        dados = status.ler_json(arq)
    except (OSError, ValueError) as e:
        raise InsumoInvalido("não consegui ler %s: %s" % (ARQUIVO_NTH, e))
    if not isinstance(dados, dict) or not all(isinstance(v, int) for v in dados.values()):
        raise InsumoInvalido("%s tem que ser {\"<id do comentário>\": <ocorrência>}" % ARQUIVO_NTH)
    return dados


def _importado(pj, projeto, args, importar):
    if args.importado:
        try:
            return status.ler_json(args.importado)
        except (OSError, ValueError) as e:
            raise InsumoInvalido("não consegui ler %s: %s" % (args.importado, e))
    importar = importar or doc_google.importar
    try:
        return importar(projeto["origem"]["doc_id"], aba=args.aba)
    except doc_google.ErroGoogle as e:
        raise InsumoInvalido(str(e))


def _registrar(pj, r):
    if r.ok:
        status.registrar(pj, ETAPA, "ok", motivo=r.motivo or None, detalhes=r.detalhes)
    else:
        status.registrar(pj, ETAPA, "falhou", motivo=r.motivo, detalhes=r.detalhes)


def main(argv=None, importar=None):
    ap = argparse.ArgumentParser(description="Confere o projeto contra os comentários do Google Doc do aluno.")
    ap.add_argument("slug")
    ap.add_argument("--estado", help="pasta _local (padrão: a do repo)")
    ap.add_argument("--aba", help="aba do Doc que traz o roteiro (obrigatório se o Doc tem mais de uma)")
    ap.add_argument("--importado", help="JSON do resultado de doc_google.importar (confere sem rede)")
    args = ap.parse_args(argv)
    try:
        pj = pastas.projeto(args.slug, args.estado)
    except ValueError as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        return 2
    try:
        projeto = _projeto(pj)
        origem = projeto.get("origem") or {}
        if origem.get("tipo") != "doc_google":
            r = Resultado(True, "pulado: o projeto não nasceu de um doc_google (origem %s), não há Doc para conferir"
                          % (origem.get("tipo") or "não declarada"), {"estado": "PULADO"})
        else:
            r = rodar(pj, _importado(pj, projeto, args, importar), nths=_nths_do_projeto(pj))
    except InsumoInvalido as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        if pj.raiz.is_dir():
            status.registrar(pj, ETAPA, "bloqueado", motivo=str(e)[:400])
        return 2
    _registrar(pj, r)
    if r.ok:
        print("PASSA: %s" % (r.motivo or "%d comentário(s) com asset conferidos contra o Doc"
                             % r.detalhes["comentarios_com_asset"]))
        return 0
    print("REPROVA: %s" % r.motivo)
    return 1


if __name__ == "__main__":
    sys.exit(main())
