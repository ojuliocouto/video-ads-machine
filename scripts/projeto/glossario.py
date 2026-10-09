"""Glossário do aluno (_local/glossario.json): corrige o que o ASR escreve errado e nada além disso.

Regra de ouro: só troca o que está DECLARADO. Cada variante vira a grafia do seu termo; palavra
que não está na lista fica como veio, e uma grafia sem variantes não altera nada. A troca é
por palavra inteira (não mexe no meio de outra palavra), sem diferenciar maiúscula na variante,
em uma passada só (a saída de uma troca nunca é reprocessada).

`equivalencias` são diferenças de fala que o gate fala x roteiro aceita (por exemplo
roteiro "para", fala "pra"); valem do roteiro para a fala, não ao contrário.
"""
import re

from contratos.validar import normalizar_palavra, palavras

from . import modelo, pastas, status

CONTRATO = "glossario"
_LETRA = r"[0-9A-Za-zÀ-ÖØ-öø-ÿ]"
_RE_PONTA = re.compile(r"^([^0-9A-Za-zÀ-ÖØ-öø-ÿ]*)(.*?)([^0-9A-Za-zÀ-ÖØ-öø-ÿ]*)$", re.S)


class GlossarioInvalido(modelo.ContratoInvalido):
    def __init__(self, erros, arquivo=None):
        super().__init__(CONTRATO, erros, arquivo)


def vazio():
    return {"versao": 1, "termos": []}


def carregar(estado=None):
    """glossario.json validado. Sem arquivo: glossário vazio."""
    arq = pastas.glossario_json(estado)
    if not arq.exists():
        return vazio()
    try:
        dados = status.ler_json(arq)
    except ValueError as e:
        raise GlossarioInvalido([modelo.ErroSimples(str(e))], arq)
    modelo.erros_do_contrato(CONTRATO, dados, GlossarioInvalido, arq)
    return dados


def salvar(dados, estado=None):
    arq = pastas.glossario_json(estado)
    modelo.erros_do_contrato(CONTRATO, dados, GlossarioInvalido, arq)
    status.escrever_json_atomico(arq, dados)
    return dados


def adicionar_termo(grafia, variantes=(), tipo=None, estado=None):
    """Declara um termo. Se a grafia já existe (sem diferenciar maiúscula), soma as variantes
    novas ao termo existente. Variante que já é de outro termo reprova e nada é gravado."""
    dados = carregar(estado)
    alvo = None
    for t in dados["termos"]:
        if t["grafia"].casefold() == str(grafia).casefold():
            alvo = t
            break
    if alvo is None:
        alvo = {"grafia": grafia}
        dados["termos"].append(alvo)
    if variantes:
        lista = alvo.setdefault("variantes", [])
        for v in variantes:
            if v not in lista:
                lista.append(v)
    if tipo is not None:
        alvo["tipo"] = tipo
    # reordena as chaves do termo (grafia, variantes, tipo) para o arquivo ficar legível
    ordem = {k: alvo[k] for k in ("grafia", "variantes", "tipo") if k in alvo}
    alvo.clear()
    alvo.update(ordem)
    return salvar(dados, estado)


def adicionar_equivalencia(roteiro, fala, estado=None):
    """Declara que o roteiro 'roteiro' pode ser falado como 'fala'. Idempotente."""
    dados = carregar(estado)
    eqs = dados.setdefault("equivalencias", [])
    if {"roteiro": roteiro, "fala": fala} not in eqs:
        eqs.append({"roteiro": roteiro, "fala": fala})
    return salvar(dados, estado)


def _variantes(g):
    """[(variante, grafia)] de todos os termos, da mais longa para a mais curta."""
    pares = [(v, t["grafia"]) for t in g.get("termos", []) for v in t.get("variantes", [])]
    return sorted(pares, key=lambda p: (-len(p[0]), p[0]))


def _padrao(variante):
    """Regex da variante: palavras separadas por espaço em branco qualquer, sem diferenciar
    maiúscula, só como palavra inteira."""
    partes = [re.escape(p) for p in variante.split()]
    return r"(?<!%s)(?:%s)(?!%s)" % (_LETRA, r"\s+".join(partes), _LETRA)


def aplicar(texto, g):
    """`texto` com cada variante declarada trocada pela grafia. O resto fica byte a byte."""
    pares = _variantes(g)
    if not pares or not texto:
        return texto
    por_variante = {" ".join(v.casefold().split()): graf for v, graf in pares}
    rx = re.compile("|".join("(?:%s)" % _padrao(v) for v, _ in pares), re.IGNORECASE)

    def troca(m):
        return por_variante[" ".join(m.group(0).casefold().split())]
    return rx.sub(troca, texto)


def _nucleo(texto):
    """(prefixo, núcleo, sufixo) de uma palavra: pontuação nas pontas separada do miolo."""
    return _RE_PONTA.match(texto).groups()


def corrigir_palavras(lista, g):
    """Troca variantes numa lista [{text,start,end}] (saída do ASR). Variante de várias palavras
    vira uma palavra só, do início da primeira ao fim da última; a pontuação da ponta é mantida.
    Devolve lista nova; a entrada não muda."""
    pares = [(tuple(v.casefold().split()), graf) for v, graf in _variantes(g)]
    out, i, n = [], 0, len(lista)
    while i < n:
        trocou = False
        for toks, graf in pares:  # já vem da mais longa para a mais curta
            k = len(toks)
            if i + k > n:
                continue
            nucleos = [_nucleo(lista[i + j]["text"]) for j in range(k)]
            # só a primeira e a última palavra podem carregar pontuação de ponta
            if all(nucleos[j][1].casefold() == toks[j] for j in range(k)) \
                    and all(not nucleos[j][0] for j in range(1, k)) \
                    and all(not nucleos[j][2] for j in range(k - 1)):
                nova = dict(lista[i])
                nova["text"] = nucleos[0][0] + graf + nucleos[-1][2]
                nova["end"] = lista[i + k - 1]["end"]
                out.append(nova)
                i += k
                trocou = True
                break
        if not trocou:
            out.append(dict(lista[i]))
            i += 1
    return out


def prompt_asr(g):
    """Texto para o prompt do ASR (Groq, Whisper): as grafias certas, separadas por vírgula."""
    return ", ".join(t["grafia"] for t in g.get("termos", []))


def equivalencias(g):
    """[(roteiro, fala)] declarados."""
    return [(e["roteiro"], e["fala"]) for e in g.get("equivalencias", [])]


def _canon(texto):
    return " ".join(palavras(texto))


def aceita_equivalencia(roteiro, fala, g):
    """True se `fala` é o mesmo que `roteiro` (ignorando acento, maiúscula e pontuação) ou se a
    diferença está declarada nas equivalências do glossário (do roteiro para a fala)."""
    r, f = _canon(roteiro), _canon(fala)
    if r == f:
        return True
    return any(_canon(a) == r and _canon(b) == f for a, b in equivalencias(g))
