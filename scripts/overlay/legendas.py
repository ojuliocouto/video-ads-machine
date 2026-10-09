"""Os grupos de legenda que sobram depois do hook, do CTA e dos letterings.

O agrupamento (até 3 palavras por grupo, fechando na pontuação, segurando a frase na pausa) é do
`build_timeline`. Este módulo decide o que FICA na tela:

  - nenhuma legenda enquanto o hook está na tela (`cap_gate`) nem a partir da janela do logo;
  - o grupo que atravessa a fronteira do logo é TRUNCADO, não descartado (a legenda vai até o último
    instante livre sem invadir o logo);
  - legenda e lettering NÃO dividem a tela: o lettering vira o texto principal do trecho. O ECO (a
    mesma frase nos dois) é descartado por inteiro, inclusive o grupo que só ENCOSTA no lettering
    (a legenda "o pulo do" fechava 0,05 s antes de "o pulo do gato" começar, e a mesma frase
    aparecia 2x: rodapé e depois peito); o resto é aparado com folga FOLGA_LETT de cada lado.

ECO PARCIAL: REVERTIDO (31/08/2026, terceira rodada de prints). Cortar da legenda só as palavras que
o lettering repete deixou a frase MUDA na tela (buraco de 5 a 7 s), e puxar o lettering para o
instante da fala o pousou NA TESTA do apresentador no painel do split (16,4% do rosto, t=62 s) e subiu
o tempo parado de 9% para 26%. O desenho que fica: a legenda acompanha a frase enquanto ela é falada
(fiel ao áudio), o lettering entra logo DEPOIS como carimbo, e a folga garante que os dois nunca
dividem a tela. Duas lições pagas em quatro builds.
"""
import build_timeline
from overlay.transcricao import norm

MAX_PALAVRAS = 3        # palavras por grupo de legenda
FOLGA_LETT = 0.35       # a folga de 0,05 s era menor que a animação do lettering: a legenda ainda
                        # estava na tela quando o lettering subia
PECA_MIN = 0.60         # sobra de legenda com menos que isso não entra: um piscar de duas palavras
                        # entre dois letterings é ruído, não informação
LETT_LOOKBACK = 2.6     # janela retroativa do eco: o grupo logo ANTES do lettering


def agrupar(words):
    """Grupos de legenda de até MAX_PALAVRAS palavras (build_timeline)."""
    return build_timeline.group_captions(words, max_words=MAX_PALAVRAS)


def filtrar_corpo(groups, cap_gate, logo_start):
    """Só os grupos que COMEÇAM depois do hook e antes da janela do logo.

    O logo entra `LOGO_LEAD` antes do pill e a legenda do corpo some a partir daí: um gate só até
    `cta_start` deixava a legenda do penúltimo bloco aparecer ATRÁS do logo já visível.
    """
    return [g for g in groups if cap_gate < g["start"] < logo_start - 0.05]


def fechar_grupos(groups, logo_start):
    """Tira grupo sem palavra ou com menos de 0,20 s, e TRUNCA no início da janela do logo o que
    atravessa a fronteira (um grupo de 1 s que começa antes do logo continua na tela quando ele sobe:
    "o motor é mais." atrás do wordmark)."""
    groups = [g for g in groups if g["words"] and g["end"] - g["start"] >= 0.20]
    for g in groups:
        if g["end"] > logo_start:
            g["end"] = logo_start
    return groups


def frases_dos_letterings(letts):
    """[(início, fim, {palavras normalizadas})] do texto de cada lettering (lead mais key; na pilha,
    as chaves das linhas)."""
    frases = []
    for l in letts:
        _txt = l["lead"] + " " + " ".join(
            [x["key"] for x in l.get("linhas", [])] or [l["key"]])
        toks = set(norm(t) for t in _txt.replace("<br>", " ").split() if norm(t))
        frases.append((l["start"], l["start"] + l["dur"], toks))
    return frases


def eco_do_lettering(g, frases):
    """True se o texto INTEIRO do grupo faz parte da frase de um lettering, na janela retroativa."""
    gw = [norm(w["text"]) for w in g["words"] if norm(w["text"])]
    for ls, le, toks in frases:
        if g["start"] < le + 0.2 and g["end"] > ls - LETT_LOOKBACK and gw and all(x in toks for x in gw):
            return True
    return False


def aparar_nos_letterings(groups, letts, lett_windows):
    """Descarta o eco e apara cada grupo fora da janela de cada lettering (folga de FOLGA_LETT).

    O filtro antigo jogava fora o grupo INTEIRO se ele encostasse em qualquer janela de lettering:
    entre dois letterings sobravam 1,54 s de fala sem nenhum texto na tela, e vãos assim somavam 12%
    (o teto do gate) com o estrategista apontando exatamente essa janela como a virada da dor
    rodando muda. Hoje só o eco sai por inteiro; o resto perde o miolo.
    """
    lett_phrases = frases_dos_letterings(letts)
    _aparados = []
    for g in groups:
        if eco_do_lettering(g, lett_phrases):
            continue
        fatias = [dict(g)]
        for ws, we in sorted(lett_windows):
            prox = []
            for f in fatias:
                if not (f["start"] < we + FOLGA_LETT and f["end"] > ws - FOLGA_LETT):
                    prox.append(f)
                    continue
                antes = {**f, "end": round(min(f["end"], ws - FOLGA_LETT), 3)}
                depois = {**f, "start": round(max(f["start"], we + FOLGA_LETT), 3)}
                for peca in (antes, depois):
                    peca["words"] = [w for w in f["words"]
                                     if peca["start"] <= (w["start"] + w["end"]) / 2
                                     <= peca["end"]]
                    if peca["end"] - peca["start"] >= PECA_MIN and peca["words"]:
                        prox.append(peca)
            fatias = prox
        _aparados.extend(fatias)
    return _aparados


def html(groups):
    """O HTML das legendas (build_timeline): duas camadas por palavra, o preenchimento linear acende
    a de cima da esquerda para a direita enquanto a palavra é falada."""
    return build_timeline._render_captions_html(groups)
