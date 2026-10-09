"""Looks do HeyGen do aluno (_local/looks.json): só vertical, aprovação amarrada ao sha da conferência.

Regras:
- Look horizontal não entra (o contrato recusa: tarja, rosto pequeno).
- Aprovar um look grava o sha256 do arquivo de conferência (avatar/conferencia.json de um
  projeto, caminho relativo a _local/). Se o arquivo mudar ou sumir, a aprovação VENCE:
  `verificar` devolve não aprovado com o motivo. Quem usa o look (gate_look, vam montar) chama
  `exigir_aprovado`, que levanta LookReprovado.
- `invalidar_vencidos` persiste o vencimento em looks.json (aprovado=false, sem conferencia).
- Quem confere o avatar (largura, altura, boca) é scripts/avatar/conferir; aqui só se guarda
  que a conferência que o aluno aprovou continua sendo a mesma.
"""
import hashlib
from collections import namedtuple
from pathlib import Path

from . import modelo, pastas, status

CONTRATO = "looks"
Situacao = namedtuple("Situacao", "aprovado motivo")


class LookInvalido(modelo.ContratoInvalido):
    """looks.json (ou um pedido sobre ele) não cumpre o contrato."""

    def __init__(self, erros, arquivo=None):
        super().__init__(CONTRATO, erros, arquivo)


class LookReprovado(Exception):
    """O look existe mas não pode ser usado agora (sem aprovação, ou aprovação vencida)."""


def sha256_arquivo(caminho):
    h = hashlib.sha256()
    with open(str(caminho), "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def carregar(estado=None):
    """looks.json do aluno, validado. Sem arquivo: {"versao": 1, "looks": {}}."""
    arq = pastas.looks_json(estado)
    if not arq.exists():
        return {"versao": 1, "looks": {}}
    try:
        dados = status.ler_json(arq)
    except ValueError as e:
        raise LookInvalido([modelo.ErroSimples(str(e))], arq)
    modelo.erros_do_contrato(CONTRATO, dados, LookInvalido, arq)
    return dados


def salvar(dados, estado=None):
    """Valida e grava looks.json de forma atômica."""
    arq = pastas.looks_json(estado)
    modelo.erros_do_contrato(CONTRATO, dados, LookInvalido, arq)
    status.escrever_json_atomico(arq, dados)
    return dados


def nomes(estado=None):
    return sorted(carregar(estado)["looks"])


def obter(nome, estado=None):
    """O look `nome` (dict) ou None."""
    return carregar(estado)["looks"].get(nome)


def adicionar(nome, avatar_id, plano, orientacao="vertical", nota=None, estado=None):
    """Cadastra um look novo (não aprovado). Nunca sobrescreve: nome repetido é LookInvalido.
    Orientação diferente de vertical é recusada pelo contrato."""
    dados = carregar(estado)
    if nome in dados["looks"]:
        raise LookInvalido([modelo.ErroSimples("o look já existe; escolha outro nome", "$.looks.%s" % nome)],
                           pastas.looks_json(estado))
    look = {"avatar_id": avatar_id, "orientacao": orientacao, "plano": plano, "aprovado": False}
    if nota:
        look["nota"] = nota
    dados["looks"][nome] = look
    salvar(dados, estado)
    return look


def _conferencia_relativa(conferencia, estado):
    """Caminho da conferência relativo ao estado (com barras), garantindo que fica dentro dele
    mesmo com ../ ou link simbólico. Devolve (relativo, caminho_real)."""
    raiz = Path(pastas.resolver_estado(estado)).resolve()
    c = Path(conferencia)
    real = (c if c.is_absolute() else raiz / c).resolve()
    try:
        rel = real.relative_to(raiz)
    except ValueError:
        raise LookInvalido([modelo.ErroSimples(
            "o arquivo de conferência tem que ficar dentro de _local/: %s" % conferencia, "$.conferencia")],
            pastas.looks_json(estado))
    return rel.as_posix(), real


def aprovar(nome, conferencia, estado=None, agora=None):
    """Marca o look como aprovado, amarrado ao sha256 do arquivo `conferencia` (relativo a
    _local/, ou absoluto dentro dele). O arquivo tem que existir. Reaprovar grava o sha atual."""
    dados = carregar(estado)
    if nome not in dados["looks"]:
        raise LookInvalido([modelo.ErroSimples("look inexistente; cadastre com adicionar()", "$.looks.%s" % nome)],
                           pastas.looks_json(estado))
    rel, real = _conferencia_relativa(conferencia, estado)
    if not real.is_file():
        raise LookInvalido([modelo.ErroSimples("arquivo de conferência não existe: %s" % rel,
                                               "$.looks.%s.conferencia" % nome)], pastas.looks_json(estado))
    look = dados["looks"][nome]
    look["aprovado"] = True
    look["conferencia"] = {"arquivo": rel, "sha256": sha256_arquivo(real)}
    look["aprovado_em"] = agora if agora is not None else status.instante()
    salvar(dados, estado)
    return look


def _situacao(nome, look, estado):
    if look is None:
        return Situacao(False, "o look %r não existe em looks.json" % nome)
    if not look.get("aprovado"):
        return Situacao(False, "o look %r não está aprovado" % nome)
    conf = look["conferencia"]
    alvo = Path(pastas.resolver_estado(estado)) / conf["arquivo"]
    if not alvo.is_file():
        return Situacao(False, "o arquivo de conferência do look %r sumiu: %s" % (nome, conf["arquivo"]))
    if sha256_arquivo(alvo) != conf["sha256"]:
        return Situacao(False, "o arquivo de conferência do look %r mudou depois da aprovação "
                               "(sha256 diferente): %s; confira de novo e aprove" % (nome, conf["arquivo"]))
    return Situacao(True, None)


def verificar(nome, estado=None):
    """Situacao(aprovado, motivo). Aprovado só se está marcado E o sha da conferência confere."""
    return _situacao(nome, carregar(estado)["looks"].get(nome), estado)


def exigir_aprovado(nome, estado=None):
    """O look (dict) se estiver aprovado e vigente; senão LookReprovado com o motivo."""
    look = carregar(estado)["looks"].get(nome)
    s = _situacao(nome, look, estado)
    if not s.aprovado:
        raise LookReprovado(s.motivo)
    return look


def invalidar_vencidos(estado=None):
    """Persiste o vencimento dos looks cuja conferência mudou ou sumiu: aprovado=false, sem
    conferencia nem aprovado_em, com nota do motivo. Devolve os nomes invalidados."""
    arq = pastas.looks_json(estado)
    if not arq.exists():
        return []
    dados = carregar(estado)
    vencidos = []
    for nome, look in sorted(dados["looks"].items()):
        if not look.get("aprovado"):
            continue
        s = _situacao(nome, look, estado)
        if s.aprovado:
            continue
        look["aprovado"] = False
        look.pop("conferencia", None)
        look.pop("aprovado_em", None)
        look["nota"] = ("aprovação invalidada: " + s.motivo)[:300]
        vencidos.append(nome)
    if vencidos:
        salvar(dados, estado)
    return vencidos
