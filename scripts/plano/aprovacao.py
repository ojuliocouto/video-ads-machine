"""plano/aprovacao: o ok do aluno ao plano, amarrado por sha256 ao que foi aprovado.

    python3 scripts/plano/aprovacao.py <slug> --ok "<o texto do ok do aluno>" [--estado _local]
    from plano import aprovacao
    aprovacao.aprovar(pj, "aprovado, pode montar")        # grava plano/aprovacao.json
    aprovacao.verificar(pj)                               # Situacao(vigente, motivo, mudados, detalhes)

Este é o ÚNICO módulo que escreve `plano/aprovacao.json` (um teste varre os scripts atrás de quem mais
escreve): quem é medido não assina. O montador e os gates só LEEM, por `verificar`.

A aprovação grava o texto do ok, o instante e o sha256 de quatro arquivos:

  roteiro.md          a fala e a direção
  projeto.json        look, aceleração, trilha, estilo, ajuste dos inserts
  plano/plano.json    o plano medido que o aluno leu
  render/inserts.json o mapa de inserts que o motor consome (o `inserts.json` de `entrada.para_motor`, os mesmos
                      bytes; este módulo o escreve aqui para ter o que amarrar)

Mudar 1 byte em qualquer um dos quatro vence a aprovação ("aprovação vencida"): o plano volta para o
ok do aluno. Isso fecha o buraco do `fase_gate` antigo, em que o plano editado depois do ok continuava aprovado.

O que `aprovar` recusa (nada é gravado):
  - ok vazio;
  - plano sem as 6 seções, com checklist inválida (pendente sem motivo) ou fora do contrato;
  - plano medido de outra versão do roteiro.md ou do projeto.json (rode `vam plano` de novo);
  - plano_edicao.md que não é o do plano.json atual: o aluno tem que ter lido ESTE plano;
  - insert do roteiro sem arquivo, ou roteiro que o motor não aceita (livre, sem hook).

LIMITAÇÃO CONHECIDA: o `inserts.json` guarda o caminho absoluto de cada arquivo de insert (é o formato do motor),
então mover a pasta do projeto vence a aprovação. Trocar o CONTEÚDO de um arquivo de insert (mesmo nome) não vence
esta aprovação; quem pega é o gate de insert no render (duração, congelamento).
"""
import argparse
import hashlib
import json
import os
import sys
from collections import namedtuple
from pathlib import Path

if __name__ == "__main__":      # rodado direto: scripts/plano/aprovacao.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contratos.validar import validar  # noqa: E402
from entrada import para_motor, roteiro_md  # noqa: E402
from plano import checklist, escrever_md  # noqa: E402
from projeto import modelo, pastas, status  # noqa: E402

EMISSOR = "plano.aprovacao"
NOMES = ("roteiro", "projeto", "plano", "inserts")
ETAPA = "aprovacao"
OK_MIN, OK_MAX = 2, 2000          # contratos/aprovacao.schema.json

Situacao = namedtuple("Situacao", "vigente motivo mudados detalhes")


class AprovacaoRecusada(ValueError):
    """Não dá para aprovar este plano; a mensagem diz o que fazer. Nada foi gravado."""


# --- os quatro arquivos ----------------------------------------------------------------------------------

def sha256_arquivo(caminho):
    h = hashlib.sha256()
    with open(str(caminho), "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def caminhos(pj):
    """{nome: Path} dos quatro arquivos aprovados."""
    return {"roteiro": pj.roteiro, "projeto": pj.projeto_json, "plano": pj.plano_json,
            "inserts": pj.render_dir / "inserts.json"}


def relativos(pj):
    """{nome: caminho relativo à pasta do projeto, com barras}: o que o aprovacao.json guarda."""
    return dict((nome, pj.relativo(c)) for nome, c in caminhos(pj).items())


# --- aprovar -----------------------------------------------------------------------------------------------

def _ok(ok):
    if not isinstance(ok, str) or len(ok.strip()) < OK_MIN:
        raise AprovacaoRecusada("sem o ok do aluno não há aprovação: passe o texto do ok, como ele escreveu no "
                                "chat (pelo menos %d caracteres)" % OK_MIN)
    ok = ok.strip()
    if len(ok) > OK_MAX:
        raise AprovacaoRecusada("o texto do ok tem %d caracteres; o limite é %d" % (len(ok), OK_MAX))
    return ok


def _plano(pj):
    if not pj.plano_json.is_file():
        raise AprovacaoRecusada("plano/plano.json não existe: rode vam plano, mostre o plano_edicao.md ao aluno e "
                                "só então aprove")
    try:
        return status.ler_json(pj.plano_json)
    except ValueError as e:
        raise AprovacaoRecusada("plano/plano.json ilegível (%s): rode vam plano de novo" % e)


def _inserts_json(pj):
    """Os bytes do render/inserts.json, sem escrever nada. Avatar: os do para_motor. Gravado e one-shot não passam
    pelo motor de leva: o mapa mínimo chave -> arquivo, na ordem do roteiro."""
    try:
        lei = roteiro_md.exigir(roteiro_md.ler_arquivo(pj.roteiro))
        projeto = modelo.carregar(pj.projeto_json)
        if projeto["modo"] == "avatar":
            motor = para_motor.gerar(lei, pj.projeto_json, avatar=pj.avatar_mp4, out_dir=pj.render_dir,
                                     inserts_dir=pj.inserts_dir)
            return motor.inserts_json().encode("utf-8")
        mapa = {}
        for b in lei.blocos:
            if b["tipo"] == "insert" and b["insert"] not in mapa:
                achado = pj.insert(b["insert"])
                if achado is None:
                    raise AprovacaoRecusada("falta o arquivo do insert '%s': coloque inserts/%s.<extensão>"
                                            % (b["insert"], b["insert"]))
                mapa[b["insert"]] = {"file": str(achado)}
        return (json.dumps(mapa, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    except AprovacaoRecusada:
        raise
    except para_motor.ErroParaMotor as e:
        raise AprovacaoRecusada("o motor não aceita este roteiro com estes inserts: %s" % e)
    except (ValueError, OSError) as e:
        raise AprovacaoRecusada(str(e))


def _conferir_plano(pj, plano):
    probs = checklist.problemas(plano)
    if probs:
        raise AprovacaoRecusada("o plano não pode ser aprovado:\n  " + "\n  ".join(probs))
    if plano["projeto"] != pj.slug:
        raise AprovacaoRecusada("o plano.json é do projeto '%s', não de '%s': rode vam plano neste projeto"
                                % (plano["projeto"], pj.slug))
    fonte = plano["fonte"]
    for campo, nome, arq in (("roteiro_sha256", "roteiro.md", pj.roteiro), ("projeto_sha256", "projeto.json",
                                                                          pj.projeto_json)):
        if fonte[campo] != sha256_arquivo(arq):
            raise AprovacaoRecusada("o plano foi medido de outra versão do %s (ele mudou depois do plano): rode "
                                    "vam plano de novo e mostre o plano novo ao aluno" % nome)


def aprovar(pj, ok, agora=None):
    """Registra o ok do aluno ao plano e grava plano/aprovacao.json. Devolve o dict gravado.

    Levanta AprovacaoRecusada, sem gravar nada, se o ok é vazio ou se o plano não está em condições (ver o
    docstring do módulo). Aprovar de novo substitui a aprovação anterior.
    """
    ok = _ok(ok)
    for arq in (pj.roteiro, pj.projeto_json):
        if not arq.is_file():
            raise AprovacaoRecusada("%s não existe em %s" % (arq.name, pj.raiz))
    plano = _plano(pj)
    _conferir_plano(pj, plano)
    confere, motivo = escrever_md.confere(pj)
    if not confere:
        raise AprovacaoRecusada(motivo)
    inserts = _inserts_json(pj)

    destino = caminhos(pj)["inserts"]
    roteiro_md.escrever_atomico(destino, inserts)
    rel = relativos(pj)
    registro = {
        "versao": 1, "projeto": pj.slug,
        "aprovado_em": agora if agora is not None else status.instante(),
        "ok": ok,
        "arquivos": dict((nome, {"caminho": rel[nome], "sha256": sha256_arquivo(caminhos(pj)[nome])})
                         for nome in NOMES),
        "emissor": EMISSOR}
    erros = validar("aprovacao", registro)
    if erros:
        raise AprovacaoRecusada("a aprovação não passou no contrato: " + "; ".join(str(e) for e in erros))
    status.escrever_json_atomico(pj.aprovacao, registro)
    return registro


# --- verificar (só lê) -------------------------------------------------------------------------------------

def _invalida(motivo):
    return Situacao(False, motivo, [], {})


def verificar(pj):
    """Situação da aprovação do plano. Só lê. `vigente` é True quando o aluno deu o ok e os quatro arquivos estão
    como estavam; `mudados` lista os que não estão; `detalhes` = {aprovado_em, ok, arquivos: [{arquivo, vigente}]}."""
    if not pj.aprovacao.is_file():
        return _invalida("sem aprovação: o aluno ainda não deu o ok a este plano. Rode vam plano, mostre o "
                         "plano_edicao.md e, com o ok dele no chat, rode vam aprovar %s --ok \"<o ok>\"" % pj.slug)
    try:
        dados = status.ler_json(pj.aprovacao)
    except (OSError, ValueError) as e:
        return _invalida("aprovacao.json ilegível (%s): aprove de novo com vam aprovar" % e)
    erros = validar("aprovacao", dados)
    if erros:
        return _invalida("aprovacao.json inválido (o arquivo só vale se foi escrito por plano.aprovacao, emissor "
                         "'%s'): %s" % (EMISSOR, "; ".join(str(e) for e in erros[:3])))
    if dados["projeto"] != pj.slug:
        return _invalida("a aprovação é do projeto '%s', não de '%s': aprove este projeto com vam aprovar"
                         % (dados["projeto"], pj.slug))
    rel, abs_ = relativos(pj), caminhos(pj)
    for nome in NOMES:
        if dados["arquivos"][nome]["caminho"] != rel[nome]:
            return _invalida("aprovacao.json aponta '%s' para %s, mas o arquivo que o montar lê é %s: aprove de "
                             "novo com vam aprovar" % (nome, dados["arquivos"][nome]["caminho"], rel[nome]))

    arquivos, mudados, frases = [], [], []
    for nome in NOMES:
        c = abs_[nome]
        if not c.is_file():
            vigente, frase = False, "%s sumiu" % rel[nome]
        elif sha256_arquivo(c) != dados["arquivos"][nome]["sha256"]:
            vigente, frase = False, "%s mudou" % rel[nome]
        else:
            vigente, frase = True, ""
        arquivos.append({"arquivo": rel[nome], "vigente": vigente})
        if not vigente:
            mudados.append(rel[nome])
            frases.append(frase)
    detalhes = {"aprovado_em": dados["aprovado_em"], "ok": dados["ok"], "arquivos": arquivos}
    if mudados:
        return Situacao(False, "aprovação vencida: %s depois do ok de %s. Rode vam plano para medir de novo, "
                        "mostre o plano ao aluno e rode vam aprovar com o ok novo"
                        % ("; ".join(frases), dados["aprovado_em"]), mudados, detalhes)

    try:
        plano = status.ler_json(pj.plano_json)
    except (OSError, ValueError) as e:
        return Situacao(False, "o plano.json aprovado está ilegível (%s): rode vam plano de novo" % e, [], detalhes)
    probs = checklist.problemas(plano)
    if probs:
        return Situacao(False, "o plano.json aprovado não passa: " + "; ".join(probs), [], detalhes)
    for campo, nome in (("roteiro_sha256", "roteiro"), ("projeto_sha256", "projeto")):
        if plano["fonte"][campo] != dados["arquivos"][nome]["sha256"]:
            return Situacao(False, "o plano.json foi medido de outra versão do %s: rode vam plano de novo e "
                            "aprove o plano novo" % rel[nome], [], detalhes)
    return Situacao(True, "", [], detalhes)


# --- CLI ---------------------------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="Registra o ok do aluno ao plano e amarra os arquivos por sha256.")
    ap.add_argument("slug")
    ap.add_argument("--estado", help="pasta _local (padrão: a do repo)")
    ap.add_argument("--ok", required=True, help="o texto do ok, como o aluno escreveu no chat")
    args = ap.parse_args(argv)
    try:
        pj = pastas.projeto(args.slug, args.estado)
        if not pj.raiz.is_dir():
            raise ValueError("o projeto %r não existe em %s" % (pj.slug, pj.raiz))
    except ValueError as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        return 2
    try:
        registro = aprovar(pj, args.ok)
    except AprovacaoRecusada as e:
        print("RECUSADO: %s" % e, file=sys.stderr)
        status.registrar(pj, ETAPA, "falhou", motivo=str(e)[:400])
        return 1
    status.registrar(pj, ETAPA, "ok", detalhes={"aprovado_em": registro["aprovado_em"]})
    print("APROVADO: plano de %s, ok de %s.\n  %s" % (pj.slug, registro["aprovado_em"], Path(pj.aprovacao)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
