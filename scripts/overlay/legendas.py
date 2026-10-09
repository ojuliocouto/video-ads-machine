"""Os grupos de legenda que sobram depois do hook, do CTA e dos letterings.

O agrupamento (até 3 palavras por grupo, fechando na pontuação, segurando a frase na pausa) é do
`build_timeline`. Este módulo decide o que FICA na tela:

  - nenhuma legenda enquanto o hook está na tela (`cap_gate`) nem a partir da janela do logo;
  - o grupo que atravessa a fronteira do logo é TRUNCADO, não descartado (a legenda vai até o último
    instante livre sem invadir o logo), e o piso de 0,20 s vale DEPOIS do truncamento: nenhum grupo sai
    invertido nem como um piscar;
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
PISO_GRUPO = 0.20       # legenda com menos que isso na tela não é lida: é um piscar
FOLGA_ECO_ADIADO = 0.40 # lettering ADIADO (não coube antes da troca de layout): só é eco o grupo que encosta nele


def agrupar(words):
    """Grupos de legenda de até MAX_PALAVRAS palavras (build_timeline)."""
    return build_timeline.group_captions(words, max_words=MAX_PALAVRAS)


def filtrar_corpo(groups, cap_gate, logo_start):
    """Os grupos depois do hook e antes da janela do logo.

    O logo entra `LOGO_LEAD` antes do pill e a legenda do corpo some a partir daí: um gate só até
    `cta_start` deixava a legenda do penúltimo bloco aparecer ATRÁS do logo já visível.

    O grupo que COMEÇA com o hook na tela e termina depois dele entra APARADO no fim do hook (W5.X, pendência d):
    descartado inteiro, ele deixava a tela vazia até o grupo seguinte (o gate-ad acusou 15% do anúncio sem texto num
    roteiro com a fala do gancho continuando depois dele). Só entra se sobrar o piso de PISO_GRUPO depois do hook.
    """
    saida = []
    for g in groups:
        if not g["start"] < logo_start - 0.05:
            continue
        if g["start"] > cap_gate:
            saida.append(g)
        elif g["end"] - cap_gate >= PISO_GRUPO:
            saida.append(dict(g, start=cap_gate))
    return saida




def fechar_grupos(groups, logo_start):
    """TRUNCA no início da janela do logo o que atravessa a fronteira (um grupo de 1 s que começa antes do logo
    continua na tela quando ele sobe: "o motor é mais." atrás do wordmark) e DEPOIS tira o grupo sem palavra ou com
    menos de PISO_GRUPO.

    A ordem é o conserto (W3.X A1). O original filtrava antes de truncar: o grupo que o `empurrar_pos_split` jogava
    para depois da fronteira e que o truncamento cortava no logo sobrava com 0,1 s, ou INVERTIDO (início 13,43 e fim
    13,25, medido num roteiro com o último insert em split com `dur_max` e o CTA logo depois). No overlay antigo ele
    não aparecia; na timeline o contrato o recusa e o anúncio inteiro parava. O piso é a última palavra sobre o grupo
    como ele vai para a tela."""
    for g in groups:
        if g["end"] > logo_start:
            g["end"] = logo_start
    return [g for g in groups if g["words"] and g["end"] - g["start"] >= PISO_GRUPO]


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


def eco_do_lettering(g, frases, adiados=None):
    """True se o texto INTEIRO do grupo faz parte da frase de um lettering, na janela retroativa. Com o lettering
    ADIADO a janela é só a folga de encosto (W5.X): a legenda da frase fica na tela enquanto ela é falada e o
    lettering entra depois da troca; descartar o eco a 2,6 s deixava a frase muda até o lettering chegar."""
    gw = [norm(w["text"]) for w in g["words"] if norm(w["text"])]
    for k, (ls, le, toks) in enumerate(frases):
        recuo = FOLGA_ECO_ADIADO if adiados and adiados[k] else LETT_LOOKBACK
        if g["start"] < le + 0.2 and g["end"] > ls - recuo and gw and all(x in toks for x in gw):
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
    adiados = [bool(l.get("adiado")) for l in letts]
    _aparados = []
    for g in groups:
        if eco_do_lettering(g, lett_phrases, adiados):
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


SUPRESSAO_TOL_S = 0.02     # a timeline e o overlay montam os mesmos grupos pelas mesmas funções; 2 centésimos
                           # cobrem o arredondamento do JSON


def filtrar_suprimidas(groups, legendas_da_timeline):
    """Tira os grupos que a timeline marcou como `suprimida` (o `gate_geometria` manda suprimir a legenda quando
    nenhuma posição cabe entre o queixo e a UI). Pendência 12.3: a timeline carregava a marca e ninguém a lia, então
    a supressão nascia inerte. O par é pelo tempo (início e fim do grupo), que a timeline copia do overlay."""
    sup = [(float(l["s"]), float(l["e"])) for l in (legendas_da_timeline or []) if l.get("suprimida")]
    if not sup:
        return groups
    return [g for g in groups
            if not any(abs(float(g["start"]) - s) <= SUPRESSAO_TOL_S and abs(float(g["end"]) - e) <= SUPRESSAO_TOL_S
                       for s, e in sup)]


def html(groups):
    """O HTML das legendas (build_timeline): duas camadas por palavra, o preenchimento linear acende
    a de cima da esquerda para a direita enquanto a palavra é falada."""
    return build_timeline._render_captions_html(groups)
