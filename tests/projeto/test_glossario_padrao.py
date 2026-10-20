"""Glossário PADRÃO da skill: o aluno não monta nada à mão e o ASR de "Claude" e "IA" sai certo.

Os textos são do ensaio real da demo "Quanto custa por mês" (voz real de um apresentador, transcrita pela Mistral).
Regra de ouro mantida: o que o aluno declara em _local/glossario.json sempre ganha do padrão, e o
padrão nunca é gravado no arquivo do aluno.
"""
import json

import pytest

from audio import transcrever as T
from projeto import glossario, glossario_padrao

# O que a Mistral devolveu para a voz real do ensaio (palavra por palavra, sem retoque).
FALA_MISTRAL = (
    "Quanto custa por mês para ter um time de A na sua operação? Cara, com R$100 você já consegue criar ali "
    "o seu primeiro funcionário A. Por exemplo, um editor de vídeo, um social media, é o mínimo que você "
    "precisa. E com R$100 você consegue. E olha só, o que você precisa saber, na verdade, é a maneira certa "
    "de como criar isso daí. Para que ele funcione da melhor forma. E olha que interessante, eu te mostro "
    "exatamente como fazer isso no curso de Cloud Code. É só clicar aqui embaixo e vir comigo.")


def pal(texto):
    return [{"text": p, "start": i * 0.3, "end": i * 0.3 + 0.25} for i, p in enumerate(texto.split())]


def legenda(texto, g=None):
    return " ".join(p["text"] for p in T.aplicar_glossario(pal(texto), g))


# --- legenda: "Claude Code" e "Claude" -------------------------------------------------------------------

def test_cloud_code_sempre_vira_claude_code_sem_glossario_do_aluno():
    assert legenda("eu te mostro como fazer no curso de Cloud Code.") == \
        "eu te mostro como fazer no curso de Claude Code."


@pytest.mark.parametrize("texto,esperado", [
    ("o cloud code é ótimo", "o Claude Code é ótimo"),
    ("usa o CLOUD CODE aqui", "usa o Claude Code aqui"),
    ("abra o Cloud Code, depois", "abra o Claude Code, depois"),
    ("(Cloud Code)", "(Claude Code)"),
])
def test_cloud_code_em_qualquer_caixa_e_pontuacao(texto, esperado):
    assert legenda(texto) == esperado


@pytest.mark.parametrize("texto,esperado", [
    ("uma skill transformou meu Cloud em um web designer", "uma skill transformou meu Claude em um web designer"),
    ("o seu Cloud responde rápido", "o seu Claude responde rápido"),
    ("pergunta pro Cloud Opus", "pergunta pro Claude Opus"),
    ("eu uso o Cloud Sonnet hoje", "eu uso o Claude Sonnet hoje"),
])
def test_cloud_sozinho_vira_claude_so_com_vizinhanca_de_produto(texto, esperado):
    assert legenda(texto) == esperado


@pytest.mark.parametrize("texto", [
    "vamos migrar tudo para o Cloud da empresa",       # computação em nuvem: "o cloud" é ambíguo, fica
    "o custo no cloud sobe todo mês",
    "o armazenamento do Cloud é barato",
    "a AWS é um cloud provider",
    "Cloud computing é nuvem",
    "salvei o arquivo no Cloud.",
])
def test_cloud_de_nuvem_nao_e_tocado(texto):
    assert legenda(texto) == texto


# --- legenda: "IA" ----------------------------------------------------------------------------------------

def test_frases_reais_do_ensaio_time_de_ia_e_funcionario_ia():
    out = legenda(FALA_MISTRAL)
    assert "Quanto custa por mês para ter um time de IA na sua operação?" in out
    assert "criar ali o seu primeiro funcionário IA. Por exemplo" in out
    assert "curso de Claude Code. É só clicar" in out
    assert "é a maneira certa" in out                 # o artigo "a" fica como veio
    assert " Cloud" not in out


@pytest.mark.parametrize("texto,esperado", [
    ("um time de A na sua operação", "um time de IA na sua operação"),
    ("uma equipe de A resolve", "uma equipe de IA resolve"),
    ("o seu primeiro funcionário A.", "o seu primeiro funcionário IA."),
    ("contrate um funcionário A, agora", "contrate um funcionário IA, agora"),
    ("quem trabalha com uso de A?", "quem trabalha com uso de IA?"),
    ("o futuro é o agente de A!", "o futuro é o agente de IA!"),
])
def test_ia_so_nos_padroes_fechados(texto, esperado):
    assert legenda(texto) == esperado


@pytest.mark.parametrize("texto", [
    "é a maneira certa de criar",
    "eu vou a casa dele",
    "ela é a melhor",
    "vai de A a Z em dez minutos",                 # "de A a Z" não é IA
    "do plano A ao plano B",
    "funcionário A e funcionário B",                # rótulo, não IA
    "o funcionário A, o funcionário B",
    "se for a lista A, use a outra",
    "tem a gente",
    "time de a",                                   # minúscula: é artigo, nunca troca
])
def test_ia_nao_troca_artigo_nem_rotulo(texto):
    assert legenda(texto) == texto


def test_a_troca_mantem_o_tempo_e_a_pontuacao():
    antes = pal("seu primeiro funcionário A.")
    depois = T.aplicar_glossario(antes, None)
    assert [(p["start"], p["end"]) for p in depois] == [(p["start"], p["end"]) for p in antes]
    assert depois[-1]["text"] == "IA."


def test_aplicar_nao_muda_a_lista_de_entrada():
    antes = pal("operação Cloud Code e um time de A")
    copia = [dict(p) for p in antes]
    T.aplicar_glossario(antes, None)
    assert antes == copia


# --- o aluno sempre ganha ---------------------------------------------------------------------------------

def test_variante_do_aluno_para_cloud_code_vence_o_padrao():
    g = {"versao": 1, "termos": [{"grafia": "Cloud Code Pro", "variantes": ["Cloud Code"]}]}
    assert legenda("no curso de Cloud Code agora", g) == "no curso de Cloud Code Pro agora"


def test_aluno_que_usa_cloud_no_glossario_fica_sem_nenhuma_troca_de_cloud():
    g = {"versao": 1, "termos": [{"grafia": "Cloud"}]}
    assert legenda("no meu Cloud tem 3 servidores", g) == "no meu Cloud tem 3 servidores"
    assert legenda("no curso de Cloud Code", g) == "no curso de Cloud Code"


def test_o_padrao_e_idempotente_e_o_aluno_segue_ganhando_na_segunda_passada():
    g = {"versao": 1, "termos": [{"grafia": "Cloud Code Pro", "variantes": ["Cloud Code"]}]}
    uma = T.aplicar_glossario(pal("no curso de Cloud Code agora"), g)
    duas = glossario.corrigir_palavras(uma, g)                    # o gate passa por aqui depois do transcrever
    assert "Claude" not in " ".join(p["text"] for p in duas)
    assert " ".join(p["text"] for p in glossario.corrigir_palavras(pal("a Cloud Code e time de A"), glossario.vazio())) \
        == "a Claude Code e time de IA"


# --- mesclar / carregar ------------------------------------------------------------------------------------

def test_carregar_sem_arquivo_ja_traz_o_padrao(tmp_path):
    g = glossario.carregar(tmp_path)
    assert ("IA", "A") in glossario.equivalencias(g)
    assert ("100 reais", "R$100") in glossario.equivalencias(g)
    grafias = [t["grafia"] for t in g["termos"]]
    assert "Claude Code" in grafias and "Claude" in grafias
    # o prompt do ASR já leva as grafias certas
    assert "Claude Code" in T.prompt_do_glossario(g)


def test_carregar_do_aluno_continua_vazio(tmp_path):
    assert glossario.carregar_do_aluno(tmp_path) == {"versao": 1, "termos": []}


def test_padrao_nunca_e_gravado_no_arquivo_do_aluno(tmp_path):
    glossario.adicionar_termo("Fluxa", ["Flucha"], estado=tmp_path)
    glossario.adicionar_equivalencia("para", "pra", estado=tmp_path)
    gravado = json.loads((tmp_path / "glossario.json").read_text(encoding="utf-8"))
    assert [t["grafia"] for t in gravado["termos"]] == ["Fluxa"]
    assert gravado["equivalencias"] == [{"roteiro": "para", "fala": "pra"}]
    # e o carregado soma os dois, aluno primeiro
    g = glossario.carregar(tmp_path)
    assert g["termos"][0]["grafia"] == "Fluxa"
    assert ("para", "pra") in glossario.equivalencias(g) and ("IA", "A") in glossario.equivalencias(g)


def test_mesclar_nao_muda_o_dict_do_aluno_e_nao_repete_termo_declarado():
    aluno = {"versao": 1, "termos": [{"grafia": "claude", "variantes": ["clod"]}]}
    copia = json.loads(json.dumps(aluno))
    g = glossario_padrao.mesclar(aluno)
    assert aluno == copia
    assert [t["grafia"].casefold() for t in g["termos"]].count("claude") == 1
    assert g["termos"][0] == {"grafia": "claude", "variantes": ["clod"]}


def test_o_padrao_e_valido_pelo_contrato_do_glossario():
    from contratos.validar import validar
    assert [str(e) for e in validar("glossario", glossario_padrao.mesclar(glossario.vazio()))] == []
