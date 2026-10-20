"""Limpeza do take one-shot: falsa partida, fala de quem dirige e voz que não é do apresentador.

Nasceu do ensaio de 20/10/2026 (IMG_3751, 54,7 s, iPhone em sala barulhenta): o take tinha preâmbulo,
uma falsa partida, uma pergunta para quem dirige, a resposta dela ao fundo e duas repetições. O one-shot
não tirava nada disso. Por quê:

  - a transcrição do take INTEIRO deduplica: a nuvem lê "Cara, com 100 reais você já começa... Cara, com
    100 reais você já consegue" como UMA frase e estica o token "consegue" por 2,7 s. Pelo tempo de
    palavra do take inteiro a falsa partida some;
  - o piso de ruído da sala fica acima do limiar fixo de silêncio, então a energia não acha pausa.

O caminho que funciona: separar o take em SUB-BLOCOS pela energia (limiar acima do piso de ruído MEDIDO,
`ar_morto.piso_adaptativo`), transcrever cada sub-bloco SOZINHO (a nuvem não tem como deduplicar o que
não ouviu junto) e classificar:

  VOZ BAIXA    sub-bloco com pico `QUEDA_OUTRA_VOZ_DB` abaixo do pico típico do apresentador: outra pessoa
               ao fundo (quem dirige) ou ruído. Sai, com aviso no plano.
  DIREÇÃO      o texto casa uma pergunta de quem grava ("depois o que é que eu falo?") ou os padrões do
               `gravado.gate_offscript`, OU é uma pergunta respondida por voz baixa logo depois (a
               pergunta para quem dirige e a resposta dela ao fundo: a Mistral e a Groq leem a mesma
               pergunta com palavras diferentes, a estrutura não muda). Sai, com aviso no plano.
  RETOMADA     as últimas palavras antes de um sub-bloco começam igual a ele e se repetem nele (60% das
               palavras, na ordem). A primeira tentativa sai e fica a que foi até o fim.

Tudo o que sai vira uma RETIRADA com motivo e o texto ouvido, e aparece no plano para quem dirige
conferir. O gate de fala preservada compara o final com o bruto MENOS as retiradas declaradas: nenhuma
palavra fora delas pode sumir.

    subblocos(db_rel, jan, limiar)            [(ini, fim)] de fala pela energia
    classificar(blocos)                       o que sai, puro: recebe os blocos já lidos
    retiradas(blocos, palavras)               (retiradas alargadas e unidas, avisos para o plano)
    ler_blocos(take, leitor, db_rel, jan)     os sub-blocos com pico, palavras e texto (chama o ASR)
    palavras_fora(palavras, retiradas)        as palavras do bruto que o final tem que ter
"""
import difflib
import re
import unicodedata

import numpy as np

import ar_morto
from gravado import gate_offscript

JUNTA_S = 0.25              # pausa menor que isso não separa sub-bloco (pausa entre palavras da mesma frase)
CORRIDA_MIN_S = 0.06        # corrida de energia mais curta que isso é estalo, não fala
BLOCO_MIN_S = 0.18          # sub-bloco mais curto que isso não se lê sozinho
QUEDA_OUTRA_VOZ_DB = 10.0   # pico do sub-bloco tantos dB abaixo do pico típico: não é o apresentador
SIMIL_RETOMADA = 0.6        # fração das palavras da tentativa que se repetem, na ordem, no recomeço
MIN_PALAVRAS_RETOMADA = 2
JANELA_RETOMADA_S = 12.0    # a falsa partida fica até tantos segundos antes do recomeço
RESPOSTA_ATE_S = 1.5        # a voz baixa que responde começa até tantos segundos depois da pergunta
FOLGA_S = 0.12              # folga de cada lado do que sai, sem encostar na fala que fica
ALUCINACOES = ("transcricao em portugues do brasil", "obrigado", "obrigada", "legendas pela comunidade")

# Pergunta de quem grava para quem dirige (e o contrário). Expressão inteira, sem acento.
PADROES_DIRECAO = [
    r"\bo que (e que )?(eu|ele|ela|voce|a gente) (falo|fala|faco|faz|digo|diz|quer falar|vou falar)\b",
    r"\bdepois o que\b",
    r"\b(quer|queria|quiser) que eu (fale|faca|diga|fala|faz)\b",
    r"\bo que (e que )?(eu )?(falo|digo) agora\b",
    r"\bposso (falar|comecar|ir)\b",
    r"\bgravando ja\b",
]


def _norm(texto):
    t = unicodedata.normalize("NFD", str(texto).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def palavras_norm(texto):
    return re.findall(r"[a-z0-9]+", _norm(texto))


# --- sub-blocos pela energia --------------------------------------------------------------------------

def subblocos(db_rel, jan, limiar, junta=JUNTA_S, corrida_min=CORRIDA_MIN_S, bloco_min=BLOCO_MIN_S):
    """[(ini, fim)] das corridas de energia acima de `limiar` (dB relativos ao pico), unidas quando a
    pausa entre elas é menor que `junta`. O limiar vem do piso de ruído medido, nunca de número fixo."""
    m = np.asarray(db_rel) >= limiar
    if not m.size:
        return []
    bordas = np.diff(np.concatenate(([0], m.astype(np.int8), [0])))
    corridas = [(i * jan, f * jan) for i, f in zip(np.where(bordas == 1)[0], np.where(bordas == -1)[0])
                if (f - i) * jan >= corrida_min - 1e-9]
    blocos = []
    for a, b in corridas:
        if blocos and a - blocos[-1][1] < junta:
            blocos[-1] = (blocos[-1][0], b)
        else:
            blocos.append((a, b))
    return [(round(a, 3), round(b, 3)) for a, b in blocos if b - a >= bloco_min - 1e-9]


def ler_blocos(take, leitor, db_rel, jan, limiar):
    """Os sub-blocos do take com pico (dB relativo), as palavras (tempo no eixo do take) e o texto."""
    db_rel = np.asarray(db_rel)
    saida = []
    for a, b in subblocos(db_rel, jan, limiar):
        trecho = db_rel[int(round(a / jan)):int(round(b / jan))]
        palavras = leitor.palavras_do_trecho(take, a, b)
        texto = " ".join(p["text"] for p in palavras).strip()
        saida.append({"ini": a, "fim": b, "pico": float(trecho.max()) if trecho.size else -120.0,
                      "palavras": palavras, "texto": texto})
    return saida


# --- classificação (pura) -----------------------------------------------------------------------------

def _alucinacao(texto):
    n = " ".join(palavras_norm(texto))
    return not n or n in ALUCINACOES


def eh_direcao(texto):
    """O padrão de direção que o texto casa, ou None."""
    n = " ".join(palavras_norm(texto))
    for p in PADROES_DIRECAO:
        if re.search(p, n):
            return p
    for frase in gate_offscript.achados(texto):
        return frase
    return None


def pico_tipico(blocos):
    """O pico típico do apresentador: a mediana dos picos dos sub-blocos que têm fala de verdade."""
    picos = [b["pico"] for b in blocos if not _alucinacao(b["texto"])]
    return float(np.median(picos)) if picos else None


def _palavras_com_tempo(bloco):
    return [(palavras_norm(p["text"]), p["start"], p["end"]) for p in bloco["palavras"]]


def _achatar(blocos):
    """[(palavra normalizada, início, fim, índice do bloco na lista, primeira do bloco?)] na ordem."""
    saida = []
    for nb, b in enumerate(blocos):
        primeira = True
        for ws, a, f in _palavras_com_tempo(b):
            for w in ws:
                saida.append((w, a, f, nb, primeira))
                primeira = False
    return saida


def falsa_partida(antes, recomeco):
    """A maior cauda de `antes` [(palavra, ...)] que é uma tentativa do `recomeco` [palavra]: começa com a mesma
    palavra e pelo menos `SIMIL_RETOMADA` das palavras dela aparecem, na ordem, no começo do recomeço.
    Devolve o índice em `antes` onde a tentativa começa, ou None."""
    if not recomeco:
        return None
    melhor = None
    for k in range(len(antes) - MIN_PALAVRAS_RETOMADA, -1, -1):
        cauda = [x[0] for x in antes[k:]]
        if cauda[0] != recomeco[0]:
            continue
        alvo = recomeco[:len(cauda) + 2]
        sm = difflib.SequenceMatcher(None, cauda, alvo, autojunk=False)
        iguais = sum(m.size for m in sm.get_matching_blocks())
        if iguais >= MIN_PALAVRAS_RETOMADA and iguais >= SIMIL_RETOMADA * len(cauda):
            melhor = k
    return melhor


def classificar(blocos, queda_outra_voz=QUEDA_OUTRA_VOZ_DB):
    """[{ini, fim, motivo, detalhe, texto}] do que sai do take, ANTES de alargar (`retiradas`).
    `blocos`: [{ini, fim, pico, palavras, texto}] na ordem do take. Na retomada sai da primeira palavra da
    tentativa até o começo do recomeço (o que fica no meio é a mesma tentativa abandonada)."""
    ref = pico_tipico(blocos)
    marca = [None] * len(blocos)
    for i, b in enumerate(blocos):
        baixo = ref is not None and b["pico"] < ref - queda_outra_voz
        if baixo:
            marca[i] = ("voz baixa", "outra voz ou ruído ao fundo (pico %.0f dB, o do apresentador %.0f dB)"
                        % (b["pico"], ref))
        elif eh_direcao(b["texto"]):
            marca[i] = ("direção", "fala de quem grava ou dirige, fora do roteiro")
    for i, b in enumerate(blocos[:-1]):          # pergunta respondida por outra voz: é conversa com quem dirige
        seguinte = blocos[i + 1]
        if (marca[i] is None and b["texto"].rstrip().endswith("?") and marca[i + 1] is not None
                and marca[i + 1][0] == "voz baixa" and seguinte["ini"] - b["fim"] <= RESPOSTA_ATE_S
                and not _alucinacao(seguinte["texto"])):
            marca[i] = ("direção", "pergunta respondida por outra voz logo depois (conversa com quem dirige)")
    saida = [{"ini": b["ini"], "fim": b["fim"], "motivo": m[0], "detalhe": m[1], "texto": b["texto"]}
             for b, m in zip(blocos, marca) if m is not None]
    for j, b in enumerate(blocos):
        if marca[j] is not None:
            continue
        recomeco = [w for ws, _, _ in _palavras_com_tempo(b) for w in ws]
        anteriores = [x for i, x in enumerate(blocos[:j])
                      if marca[i] is None and b["ini"] - x["fim"] <= JANELA_RETOMADA_S]
        antes = _achatar(anteriores)
        k = falsa_partida(antes, recomeco)
        if k is None:
            continue
        _, ini_palavra, _, nb, primeira = antes[k]
        ini = anteriores[nb]["ini"] if primeira else ini_palavra
        texto = " ".join(p["text"] for x in anteriores for p in x["palavras"] if p["start"] >= ini_palavra - 1e-6)
        saida.append({"ini": ini, "fim": b["ini"], "motivo": "retomada",
                      "detalhe": "primeira tentativa, repetida em %.2f s" % b["ini"], "texto": texto})
    return sorted(saida, key=lambda r: r["ini"])


def _dentro(r, a, f):
    return r["ini"] - 1e-6 <= a and f <= r["fim"] + 1e-6


def retiradas(blocos, palavras, folga=FOLGA_S, queda_outra_voz=QUEDA_OUTRA_VOZ_DB):
    """(retiradas, avisos). Cada retirada de `classificar` se alarga até perto da fala que fica dos dois lados
    (a pausa no meio sai junto) e nunca encosta nela: para a `folga` da borda de energia do sub-bloco vizinho que
    fica e nunca passa por cima de palavra lida num sub-bloco que fica. O tempo de palavra do take inteiro
    (`palavras`) NÃO segura a borda: ele deduplica a retomada e estica token por cima da outra voz. Retiradas que se
    tocam viram uma só. Retirada = {ini, fim, motivo, texto}, em segundos do take."""
    brutas = classificar(blocos, queda_outra_voz)
    if not brutas:
        return [], []
    fica = [(b["ini"], b["fim"]) for b in blocos if not any(_dentro(r, b["ini"], b["fim"]) for r in brutas)]
    palavras_que_ficam = []
    for b in blocos:                    # a palavra lida no sub-bloco que fica é a prova de fala (o take inteiro deduplica)
        if not any(_dentro(r, b["ini"], b["fim"]) for r in brutas):
            palavras_que_ficam += [(p["start"], p["end"]) for p in b["palavras"]]
    largas = []
    for r in brutas:
        if any(a < r["ini"] - 1e-6 < f for a, f in fica):          # começa no meio de um sub-bloco que fica
            ini = r["ini"] - folga
        else:
            antes = [f for a, f in fica if f <= r["ini"] + 1e-6]
            ini = (antes[-1] + folga) if antes else max(0.0, r["ini"] - folga)
        depois = [a for a, f in fica if a >= r["fim"] - 1e-6]
        fim = (depois[0] - folga) if depois else r["fim"] + folga
        for a, f in palavras_que_ficam:
            meio = (a + f) / 2.0
            if meio < r["ini"] - 1e-6 and f > ini:
                ini = f
            if meio > r["fim"] + 1e-6 and a < fim:
                fim = a
        if fim > ini + 0.05:
            largas.append(dict(r, ini=round(ini, 3), fim=round(fim, 3)))
    unidas = _unir(largas)
    avisos = ["trecho retirado de %.2f a %.2f s (%s): \"%s\", confira na prévia"
              % (r["ini"], r["fim"], r["motivo"], r["texto"] or "sem palavra transcrita") for r in unidas]
    return unidas, avisos


def _unir(retiradas_):
    saida = []
    for r in sorted(retiradas_, key=lambda x: x["ini"]):
        if saida and r["ini"] <= saida[-1]["fim"] + 1e-6:
            u = saida[-1]
            u["fim"] = max(u["fim"], r["fim"])
            if r["motivo"] not in u["motivo"].split(" + "):
                u["motivo"] += " + " + r["motivo"]
            u["texto"] = (u["texto"] + " | " + r["texto"]).strip(" |")
        else:
            saida.append(dict(r))
    return saida


def palavras_fora(palavras, retiradas):
    """As palavras do bruto (take inteiro) cujo meio fica FORA das retiradas: o que o final tem que ter."""
    def dentro(p):
        meio = (p["start"] + p["end"]) / 2.0
        return any(r["ini"] - 1e-6 <= meio <= r["fim"] + 1e-6 for r in retiradas)
    return [p for p in palavras if not dentro(p)]


def limiar_de_fala(db_rel):
    """O limiar de energia que separa fala de sala neste take (`ar_morto.piso_adaptativo`)."""
    return ar_morto.piso_adaptativo(db_rel)
