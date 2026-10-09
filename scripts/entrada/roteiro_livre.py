"""Roteiro livre (W1.B): texto sem nenhum colchete.

Roteiro livre não tem direção: cada parágrafo (linhas separadas por linha vazia) vira um bloco
do tipo `livre`, e o plano propõe as direções (insert, KEY, lista, hook) para o aluno aprovar
antes de qualquer montagem. Este módulo reconhece o caso e entrega o ponto de partida; ele
nunca inventa fala, hook, insert nem lettering.

    info = roteiro_livre.analisar(texto)            # normaliza e lê; info["precisa_plano"]
    rascunho = roteiro_livre.esqueleto_dirigido(texto)   # [apresentador] por parágrafo e um [cta] no fim

A leitura é a de `entrada.roteiro_md` (que usa o `ler_roteiro` do contrato). Só biblioteca
padrão, sem arquivo e sem rede.
"""
from . import roteiro_md, texto_colado

KEY_CTA_PADRAO = "SAIBA MAIS"
AVISO_RASCUNHO = ("# RASCUNHO de direções: proposta para o aluno aprovar no plano. "
                  "Troque o texto do botão (KEY) do último bloco pelo do seu anúncio.")


def analisar(texto):
    """Normaliza o texto colado, lê e responde o que o plano precisa saber.

    Devolve um dict com:
      precisa_plano       True quando não há nenhuma direção entre colchetes
      ok / erros          a leitura passou na gramática? (erros = lista de Erro do validador)
      blocos              os blocos do contrato (no livre, um por parágrafo, tipo 'livre')
      n_palavras          total de palavras da fala
      palavras_por_bloco  quantas palavras tem cada bloco
      texto               o texto depois da normalização
    """
    lei = roteiro_md.ler(texto, normalizar=True)
    palavras = roteiro_md.contrato().palavras
    return {
        "precisa_plano": lei.precisa_plano,
        "ok": lei.ok,
        "erros": lei.erros,
        "blocos": lei.blocos,
        "n_palavras": lei.n_palavras,
        "palavras_por_bloco": [len(palavras(b["fala"])) for b in lei.blocos],
        "texto": lei.texto,
    }


def _paragrafos(texto):
    """Os parágrafos do roteiro livre, com os asteriscos de ênfase, como a gramática os agrupa."""
    paragrafos, atual = [], None
    for linha in texto.split("\n"):
        s = linha.strip()
        if s.startswith("#"):
            continue
        if not s:
            atual = None
        elif atual is None:
            paragrafos.append(s)
            atual = len(paragrafos) - 1
        else:
            paragrafos[atual] += " " + s
    return paragrafos


def esqueleto_dirigido(texto, key_cta=KEY_CTA_PADRAO):
    """Rascunho dirigido de um roteiro livre: o ponto de partida do plano.

    Cada parágrafo vira `[apresentador] <parágrafo>` e o último vira `[cta | KEY: <key_cta>]`.
    A primeira linha é um comentário (`#`, que o leitor ignora) dizendo que é proposta. A fala
    sai idêntica, palavra por palavra; o resultado é lido de volta e conferido antes de voltar.

    Levanta ValueError se o texto já tem direção (use-o como está), se está vazio ou fora da
    gramática (por exemplo, colchete no meio da fala), ou se `key_cta` não serve de KEY.
    """
    key = (key_cta or "").strip()
    if not key or any(c in key for c in "|[]\n") or "KEY:" in key or "LEAD:" in key:
        raise ValueError(f"key_cta {key_cta!r} não serve: texto curto do botão, sem | [ ] nem quebra de linha")
    normalizado = texto_colado.normalizar(texto)
    original = roteiro_md.ler(normalizado)
    if original.erros:
        raise ValueError("o texto não é um roteiro livre válido:\n" + roteiro_md.formatar_erros(original.erros))
    if not original.livre:
        raise ValueError("o roteiro já tem direção entre colchetes: use-o como está, sem rascunho")
    paragrafos = _paragrafos(normalizado)
    linhas = [AVISO_RASCUNHO]
    for i, p in enumerate(paragrafos):
        ultimo = i == len(paragrafos) - 1
        linhas.append(f"[cta | KEY: {key}] {p}" if ultimo else f"[apresentador] {p}")
    rascunho = "\n".join(linhas) + "\n"
    volta = roteiro_md.ler(rascunho)
    if volta.erros or [b["fala"] for b in volta.blocos] != [b["fala"] for b in original.blocos]:
        raise RuntimeError("o rascunho não devolveu a mesma fala: " + roteiro_md.formatar_erros(volta.erros))
    return rascunho
