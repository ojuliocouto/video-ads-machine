"""projeto.json do aluno: leitura, padrões por modo e validação contra contratos/projeto.schema.json.

A validação é do `scripts/contratos/validar.py` (nada é reimplementado aqui). Este módulo
acrescenta o que o schema não faz: preencher os padrões e transformar a lista de erros numa
exceção que cita o arquivo e o nome de cada campo.

Padrões (quando o campo falta): formato 9x16; aceleracao 1.35 no modo avatar e 1.2 em gravado
e oneshot; cta.label "saiba mais". O arquivo no disco não é reescrito para receber os padrões:
`normalizar` e `carregar` devolvem o dict completo.
"""
import copy

from contratos.validar import validar

from . import status

CONTRATO = "projeto"
MODOS = ("avatar", "gravado", "oneshot")
PADRAO_FORMATO = "9x16"
PADRAO_ACELERACAO = {"avatar": 1.35, "gravado": 1.2, "oneshot": 1.2}
PADRAO_CTA_LABEL = "saiba mais"


class ContratoInvalido(ValueError):
    """Um JSON do aluno não cumpre o contrato. `erros` é a lista de contratos.validar.Erro;
    `arquivo` é o caminho, quando se sabe qual é. A mensagem lista TODOS os erros com o caminho
    do campo (por exemplo `$.planilha: campo desconhecido`)."""

    def __init__(self, contrato, erros, arquivo=None):
        self.contrato = contrato
        self.erros = list(erros)
        self.arquivo = str(arquivo) if arquivo else None
        onde = " (%s)" % self.arquivo if self.arquivo else ""
        linhas = "\n".join("  %s" % e for e in self.erros)
        super().__init__("%s.json inválido%s:\n%s" % (contrato, onde, linhas))


class ProjetoInvalido(ContratoInvalido):
    def __init__(self, erros, arquivo=None):
        super().__init__(CONTRATO, erros, arquivo)


def erros_do_contrato(contrato, dados, excecao, arquivo=None):
    """Valida `dados` e levanta `excecao(erros, arquivo)` se algo reprovar. Uso comum dos módulos
    irmãos (looks, glossario)."""
    erros = validar(contrato, dados)
    if erros:
        raise excecao(erros, arquivo)


def aplicar_padroes(dados):
    """Cópia de `dados` com os padrões preenchidos. Não valida: chame depois de validar."""
    p = copy.deepcopy(dados)
    p.setdefault("formato", PADRAO_FORMATO)
    p.setdefault("aceleracao", PADRAO_ACELERACAO[p["modo"]])
    cta = p.setdefault("cta", {})
    cta.setdefault("label", PADRAO_CTA_LABEL)
    return p


def normalizar(dados):
    """Valida e devolve o projeto completo (padrões aplicados). Levanta ProjetoInvalido."""
    erros_do_contrato(CONTRATO, dados, ProjetoInvalido)
    return aplicar_padroes(dados)


def carregar(caminho):
    """Lê um projeto.json, valida e devolve o dict completo. FileNotFoundError se não existe;
    ProjetoInvalido se o JSON está quebrado, tem chave repetida ou não cumpre o contrato."""
    try:
        dados = status.ler_json(caminho)
    except FileNotFoundError:
        raise
    except ValueError as e:
        raise ProjetoInvalido([ErroSimples(str(e))], caminho)
    try:
        return normalizar(dados)
    except ProjetoInvalido as e:
        raise ProjetoInvalido(e.erros, caminho)


def escrever(caminho, dados):
    """Valida `dados` e grava o projeto completo (padrões aplicados) de forma atômica.
    Se não valida, nada é criado. Devolve o dict gravado."""
    p = normalizar(dados)
    status.escrever_json_atomico(caminho, p)
    return p


def motivo_excecao(projeto, regra):
    """Motivo escrito da exceção `regra` em projeto["excecoes"], ou None se não há."""
    for ex in projeto.get("excecoes", []):
        if ex.get("regra") == regra:
            return ex["motivo"]
    return None


def minimo(slug, modo, look=None, trilha=None, sem_trilha=None, origem=None, criado_em=None):
    """Monta o projeto.json mínimo (sem padrões, sem validar). `trilha` é o nome do arquivo em
    _local/trilhas/; `sem_trilha` é o motivo de rodar sem trilha. Os dois juntos são erro."""
    if trilha is not None and sem_trilha is not None:
        raise ValueError("trilha e sem_trilha são excludentes: ou há trilha, ou há motivo para não ter")
    p = {"versao": 1, "slug": slug, "modo": modo}
    if look is not None:
        p["look"] = look
    if trilha is not None:
        p["trilha"] = {"arquivo": trilha}
    elif sem_trilha is not None:
        p["trilha"] = {"desligada": True, "motivo": sem_trilha}
    if origem is not None:
        p["origem"] = origem
    if criado_em is not None:
        p["criado_em"] = criado_em
    return p


class ErroSimples:
    """Erro montado por este pacote (JSON quebrado, pedido inválido), no mesmo formato dos Erro
    do validador: caminho, mensagem e campo (último nome do caminho)."""

    def __init__(self, mensagem, caminho="$"):
        self.caminho = caminho
        self.mensagem = mensagem
        self.campo = caminho.rsplit(".", 1)[-1]

    def __str__(self):
        return "%s: %s" % (self.caminho, self.mensagem)

    def __repr__(self):
        return "ErroSimples(%r, %r)" % (self.caminho, self.mensagem)
