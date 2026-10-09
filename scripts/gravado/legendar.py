"""Legenda ASS a partir das palavras com tempo (borda real, não token inflado).

O TEXTO da legenda é o da transcrição JÁ corrigida pelo glossário do aluno (`nucleo.asr` aplica a
troca de grafia na saída). O pipeline de origem trazia um dicionário de correções do cliente
dentro deste arquivo; ele virou o glossário do projeto. Legenda errada é pior que legenda
nenhuma: o espectador lê e ouve ao mesmo tempo, e o ASR chegou a inserir um "não" que INVERTIA o
sentido. Por isso o texto nunca é inventado aqui: só se quebra em linhas, nunca se reescreve.

Regras de linha (medidas no material de origem):
  - no máximo MAX_CHARS caracteres e MAX_PALAVRAS palavras por linha;
  - quebra em pausa maior que QUEBRA_PAUSA_S e depois de fim de frase (. ! ?);
  - a linha fica na tela ATÉ a próxima entrar (teto de SEGURA_MAX_S de sobra), senão a tela fica
    sem texto na pausa entre frases e o gate de legenda reprova; a última segura CAUDA_S;
  - nenhuma legenda dura menos de DUR_MIN_S.

Destaque (cor de ênfase): números, preços e as palavras dos termos de MARCA e PRODUTO do
glossário do aluno. Nome de pessoa não ganha cor. `omitir` tira palavras só da legenda (o áudio
fica); por padrão nada é omitido.

    python3 scripts/gravado/legendar.py [PECA ...] [--projeto DIR] [--omitir PALAVRA ...]
"""
import argparse
import re
import sys
import unicodedata
from pathlib import Path

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado import projeto as gp  # noqa: E402
from gravado.nucleo.asr import ErroDeASR  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402

LARGURA, ALTURA = 1080, 1920
Y_LEGENDA = 1300               # baseline da legenda, acima da faixa de UI do Reels
MAX_CHARS = 30
MAX_PALAVRAS = 5
QUEBRA_PAUSA_S = 0.45
SEGURA_MAX_S = 1.6
CAUDA_S = 0.5
DUR_MIN_S = 0.3
FONTE = "Inter"
COR_ENFASE = r"&H4E7DE8&"      # terracota (BGR)
COR_BASE = r"&HFFFFFF&"
_RE_NUMERO = re.compile(r"r?\$?\d+[\d.,/]*")
_RE_TAG = re.compile(r"\{[^}]*\}")


def cabecalho():
    return (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\nWrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Base,%s,66,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0.6,0,1,5.5,1.5,2,70,70,%d,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        % (LARGURA, ALTURA, FONTE, ALTURA - Y_LEGENDA))


def tempo(t):
    """h:mm:ss.cc do ASS, em centésimos inteiros (59,996 s vira 0:01:00.00, nunca 0:00:60.00)."""
    cs = int(round(float(t) * 100))
    h, resto = divmod(cs, 360000)
    m, cs = divmod(resto, 6000)
    return "%d:%02d:%05.2f" % (h, m, cs / 100.0)


def sem_tags(texto):
    return _RE_TAG.sub("", texto)


def _nucleo(palavra):
    q = unicodedata.normalize("NFD", str(palavra).lower())
    q = "".join(c for c in q if unicodedata.category(c) != "Mn")
    return q.strip(".,!?;:")


def destaques_do_glossario(glossario):
    """Palavras (normalizadas) dos termos de marca e produto do glossário."""
    saida = set()
    for termo in (glossario or {}).get("termos", []):
        if termo.get("tipo") in ("marca", "produto"):
            for palavra in termo["grafia"].split():
                saida.add(_nucleo(palavra))
    return frozenset(x for x in saida if x)


def destaca(palavra, destacar=frozenset()):
    q = _nucleo(palavra)
    return q in destacar or bool(_RE_NUMERO.fullmatch(q))


def omitir_palavras(palavras, omitir):
    omitir = {_nucleo(x) for x in (omitir or ())}
    return [p for p in palavras if _nucleo(p["text"]) not in omitir] if omitir else list(palavras)


def linhas(ps):
    """Agrupa as palavras em linhas de legenda."""
    saida, atual = [], []
    for p in ps:
        cand = atual + [p]
        txt = " ".join(x["text"] for x in cand)
        quebra = (len(txt) > MAX_CHARS or len(cand) > MAX_PALAVRAS
                  or (atual and p["start"] - atual[-1]["end"] > QUEBRA_PAUSA_S)
                  or (atual and re.search(r"[.!?]$", atual[-1]["text"])))
        if quebra and atual:
            saida.append(atual)
            atual = [p]
        else:
            atual = cand
    if atual:
        saida.append(atual)
    return saida


def eventos(ls, destacar=frozenset()):
    """[(início, fim, texto com tags de cor)] de cada linha."""
    saida = []
    for i, ln in enumerate(ls):
        a = ln[0]["start"]
        if i + 1 < len(ls):
            b = min(ls[i + 1][0]["start"], ln[-1]["end"] + SEGURA_MAX_S)
        else:
            b = ln[-1]["end"] + CAUDA_S
        if b - a < DUR_MIN_S:
            b = a + DUR_MIN_S
        txt = " ".join(
            (r"{\c%s}" % COR_ENFASE + p["text"] + r"{\c%s}" % COR_BASE) if destaca(p["text"], destacar) else p["text"]
            for p in ln)
        saida.append((a, b, txt))
    return saida


def ass_texto(palavras, destacar=frozenset(), omitir=()):
    """(texto do arquivo ASS, linhas)."""
    ls = linhas(omitir_palavras(palavras, omitir))
    dialogos = ["Dialogue: 0,%s,%s,Base,,0,0,0,,%s" % (tempo(a), tempo(b), txt)
                for a, b, txt in eventos(ls, destacar)]
    return cabecalho() + "\n".join(dialogos) + "\n", ls


def gerar(palavras, destino, destacar=frozenset(), omitir=()):
    """Escreve o ASS em `destino`. Devolve (número de linhas, amostra das 4 primeiras)."""
    texto, ls = ass_texto(palavras, destacar, omitir)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    return len(ls), " | ".join(" ".join(p["text"] for p in ln) for ln in ls[:4])


def legendar_pecas(proj, nomes, leitor, omitir=(), relatorio=None):
    """Gera `legendas/<peça>.ass` de cada peça. Devolve {peça: número de linhas}.

    O tempo de palavra EXIGE backend de borda real (parakeet ou faster-whisper): o leitor recusa
    a Groq. A cor de destaque vem do glossário do aluno."""
    destacar = destaques_do_glossario(proj.glossario())
    feitos = {}
    for nome in nomes:
        origem = proj.fonte_da_peca(nome)
        if not Path(origem).is_file():
            raise InsumoInvalido("não achei a peça %s para legendar: %s (monte antes)" % (nome, origem))
        palavras = leitor.palavras(origem, exigir_borda=True)
        n, amostra = gerar(palavras, proj.legenda_ass(nome), destacar, omitir)
        feitos[nome] = n
        if relatorio:
            relatorio("%s: %d linhas | %s" % (nome, n, amostra))
    return feitos


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gera a legenda ASS das peças montadas.")
    ap.add_argument("pecas", nargs="*", help="nomes das peças, como A1_normal (padrão: todas do plano)")
    ap.add_argument("--projeto")
    ap.add_argument("--omitir", nargs="*", default=[], help="palavras que saem da legenda (o áudio fica)")
    a = ap.parse_args(argv)
    try:
        proj = gp.carregar(a.projeto)
        nomes = a.pecas or [n for n in proj.nomes_das_pecas() if Path(proj.fonte_da_peca(n)).is_file()]
        if not nomes:
            raise InsumoInvalido("nenhuma peça montada em %s: rode o montar antes" % proj.pasta("montados"))
        legendar_pecas(proj, nomes, proj.leitor(), omitir=a.omitir, relatorio=print)
    except InsumoInvalido as e:
        print(str(e), file=sys.stderr)
        return 2
    except ErroDeASR as e:
        print("ASR: %s" % e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
