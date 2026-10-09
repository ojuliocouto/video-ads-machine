"""Normalização do texto colado no chat (W1.B).

Regra do contrato (contratos/roteiro-convencao.md, "Normalização do texto colado"): a
normalização só mexe em aspas, espaços, quebras de linha e rótulos de chat. Ela nunca troca,
junta ou apaga palavra da fala, então a sequência de palavras de quem fala sai igual.

  1. \\r\\n e \\r viram \\n.
  2. Caracteres invisíveis saem: U+200B, U+200C, U+200D, U+2060 e U+FEFF.
  3. Aspas curvas viram retas: “ ” „ ‟ viram " e ‘ ’ ‚ ‛ viram '.
  4. Espaço especial e tabulação viram espaço; espaços repetidos viram um; as pontas da linha saem.
  5. Rótulo de chat no começo da linha sai, com o nome de quem mandou:
       [dd/mm/aaaa, hh:mm] Nome:        [dd/mm/aaaa hh:mm:ss] Nome:        dd/mm/aaaa hh:mm - Nome:
  6. Duas ou mais linhas vazias seguidas viram uma.
  7. O arquivo termina com exatamente uma quebra de linha.

Além do contrato, só coisa que é invisível ou que o chat e o Google Docs produzem sem querer
e que impediria o leitor de reconhecer a linha:
  - as marcas de direção U+200E e U+200F, que o WhatsApp do iPhone põe no começo da linha;
  - os demais espaços Unicode (U+2000 a U+200A, U+205F, U+3000, U+1680), que viram espaço;
  - o separador de linha do Google Docs (U+000B) e os separadores U+000C, U+0085, U+2028 e
    U+2029, que viram quebra de linha.

Acentos, forma Unicode (NFC ou NFD), emoji, maiúscula e pontuação não são tocados.
Módulo puro: só biblioteca padrão, sem arquivo e sem rede.
"""
import re

_INVISIVEIS = "​‌‍⁠﻿‎‏"
_ESPACOS = ("             "
            "  　\t")
_ASPAS_DUPLAS = "“”„‟"
_ASPAS_SIMPLES = "‘’‚‛"

_TABELA = {}
for _c in _INVISIVEIS:
    _TABELA[ord(_c)] = None
for _c in _ESPACOS:
    _TABELA[ord(_c)] = " "
for _c in _ASPAS_DUPLAS:
    _TABELA[ord(_c)] = '"'
for _c in _ASPAS_SIMPLES:
    _TABELA[ord(_c)] = "'"

_QUEBRAS = re.compile("\r\n|[\r\x0b\x0c\x85  ]")
_ESPACOS_SEGUIDOS = re.compile(" {2,}")

_DATA = r"\d{1,2}[/.]\d{1,2}[/.]\d{2,4}"
_HORA = r"\d{1,2}:\d{2}(?::\d{2})?(?: ?[AaPp]\.?[Mm]\.?)?"
# O nome de quem mandou vai até o primeiro ":" e não pode ter colchete, para o rótulo sem
# nome nunca comer uma direção: "[08/10/2026, 10:32] [apresentador] Oi." fica como está.
_NOME = r"[^:\[\]\n]+?"
_ROTULO_COLCHETE = re.compile(r"^\[" + _DATA + r",? " + _HORA + r"\] ?" + _NOME + r": ?")
_ROTULO_TRACO = re.compile(r"^" + _DATA + r",? " + _HORA + r" - " + _NOME + r": ?")


def _tirar_rotulo(linha):
    for padrao in (_ROTULO_COLCHETE, _ROTULO_TRACO):
        achou = padrao.match(linha)
        if achou:
            return linha[achou.end():].strip()
    return linha


def normalizar(texto):
    """Devolve o texto colado pronto para virar roteiro.md (ou para o leitor).

    Texto sem nenhum conteúdo devolve "" (e não uma quebra de linha solta).
    """
    texto = _QUEBRAS.sub("\n", texto)
    texto = texto.translate(_TABELA)
    linhas = []
    for linha in texto.split("\n"):
        linha = _ESPACOS_SEGUIDOS.sub(" ", linha).strip()
        linhas.append(_tirar_rotulo(linha) if linha else linha)
    saida = []
    for linha in linhas:
        if not linha and (not saida or not saida[-1]):
            continue                      # sem linha vazia no começo e sem duas seguidas
        saida.append(linha)
    while saida and not saida[-1]:
        saida.pop()
    if not saida:
        return ""
    return "\n".join(saida) + "\n"
