"""Glossário PADRÃO da skill: o que o ASR erra em todo anúncio sobre Claude e IA, já resolvido.

O aluno não precisa montar nada à mão. O padrão entra POR BAIXO do `_local/glossario.json` dele
(`mesclar`) e o que o aluno declara sempre ganha. O padrão nunca é gravado no arquivo do aluno.

O defeito de origem (ensaio de 20/10/2026, Mistral e Groq): "Claude" sai "Cloud" e "IA" sai "A".
  - `TERMOS` alimentam o prompt do transcritor com a grafia certa.
  - `EQUIVALENCIAS` valem na conferência fala x roteiro (roteiro "IA", fala "A"; "100 reais" x "R$100").
  - `corrigir_contexto` é a única troca de texto do padrão, e só em padrões fechados:
      * "Cloud Code" sempre vira "Claude Code"; "Cloud" sozinho só quando o produto está na vizinhança
        (antes: meu, seu, teu, nosso; depois: Opus, Sonnet, Haiku). "o Cloud" e "no Cloud" ficam, porque
        quem fala de computação em nuvem diz assim.
      * "A" maiúsculo vira "IA" em "time de A", "funcionário A" e "de A" no fim de frase. O artigo "a"
        (minúsculo) nunca é tocado e "de A a Z", "funcionário A e funcionário B" ficam como vieram.
"""
import copy
import re
import unicodedata

TERMOS = (
    {"grafia": "Claude Code"},
    {"grafia": "Claude"},
    {"grafia": "IA"},
)

EQUIVALENCIAS = (
    ("IA", "A"),                 # o roteiro diz "IA", o ASR ouve "A"
    ("100 reais", "R$100"),      # o roteiro escreve por extenso, o ASR põe o símbolo
    ("R$100", "100 reais"),      # e o contrário
)

_PADRAO_GRAFIAS = frozenset(t["grafia"] for t in TERMOS)
_POSSESSIVOS = frozenset({"meu", "seu", "teu", "nosso"})
_MODELOS = frozenset({"opus", "sonnet", "haiku"})
_EQUIPES = frozenset({"time", "times", "equipe", "equipes", "agente", "agentes", "exercito"})
_CARGOS = frozenset({"funcionario", "funcionaria", "colaborador", "colaboradora"})
_FIM_DE_FRASE = re.compile(r"[.,;:!?…]")
_PONTA = re.compile(r"^([^\w]*)(.*?)([^\w]*)$", re.S)


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _partes(palavra):
    return _PONTA.match(palavra["text"]).groups()


def _chave(palavra):
    return _sem_acento(_partes(palavra)[1]).casefold()


def mesclar(aluno):
    """Cópia do glossário do aluno com o padrão por baixo. O que o aluno declarou (grafia ou variante)
    nunca é repetido nem sobrescrito; as equivalências se somam, as do aluno primeiro."""
    g = copy.deepcopy(aluno or {"versao": 1, "termos": []})
    g.setdefault("termos", [])
    declarado = {t["grafia"].casefold() for t in g["termos"]}
    declarado |= {v.casefold() for t in g["termos"] for v in t.get("variantes", [])}
    for t in TERMOS:
        if t["grafia"].casefold() not in declarado:
            g["termos"].append(copy.deepcopy(t))
    eqs = g.setdefault("equivalencias", [])
    ja = {(e["roteiro"].casefold(), e["fala"].casefold()) for e in eqs}
    for roteiro, fala in EQUIVALENCIAS:
        if (roteiro.casefold(), fala.casefold()) not in ja:
            eqs.append({"roteiro": roteiro, "fala": fala})
    return g


def _aluno_declarou(g, palavra):
    """O aluno usa `palavra` numa grafia ou variante dele (como palavra inteira)? Então o padrão sai da frente."""
    for t in (g or {}).get("termos", []):
        if t["grafia"] in _PADRAO_GRAFIAS:
            continue
        for texto in [t["grafia"]] + list(t.get("variantes", [])):
            if palavra in texto.casefold().split():
                return True
    return False


def _com(palavra, nucleo):
    antes, _, depois = _partes(palavra)
    nova = dict(palavra)
    nova["text"] = antes + nucleo + depois
    return nova


def corrigir_contexto(palavras, glossario=None):
    """Lista nova de [{text,start,end}] com "Cloud"/"A" trocados nos padrões fechados. Tempo e pontuação
    ficam; a entrada não muda. Idempotente. `glossario` é o do aluno: quem usa "Cloud" numa grafia ou
    variante dele (ou "A" como variante) fica sem a troca correspondente; o aluno sempre ganha."""
    out = [dict(p) for p in palavras]
    n = len(out)
    cloud_livre = not _aluno_declarou(glossario, "cloud")     # o aluno que fala de "Cloud" cuida dele sozinho
    a_livre = not _aluno_declarou(glossario, "a")
    for i, p in enumerate(out):
        chave = _chave(p)
        seguinte = _chave(out[i + 1]) if i + 1 < n else ""
        if chave == "cloud" and cloud_livre:
            if seguinte == "code":
                out[i] = _com(p, "Claude")
                out[i + 1] = _com(out[i + 1], "Code")
            elif (seguinte in _MODELOS or (i > 0 and _chave(out[i - 1]) in _POSSESSIVOS)):
                out[i] = _com(p, "Claude")
        elif a_livre and _partes(p)[1] == "A" and _e_ia(out, i):
            out[i] = _com(p, "IA")
    return out


def _e_ia(out, i):
    """O "A" maiúsculo na posição i é a sigla IA? Só nos padrões fechados."""
    anterior = _chave(out[i - 1]) if i >= 1 else ""
    antes_de = _chave(out[i - 2]) if i >= 2 else ""
    if any(_chave(q) == "b" for q in out[i + 1:i + 4]):       # "A e B", "A, B": rótulos, não IA
        return False
    if anterior in _CARGOS:                                     # "primeiro funcionário A."
        return True
    if anterior == "de":
        if antes_de in _EQUIPES:                                # "time de A na sua operação"
            return True
        fim = i == len(out) - 1 or bool(_FIM_DE_FRASE.search(_partes(out[i])[2]))
        return fim                                              # "uso de A?"; "de A a Z" não passa
    return False
