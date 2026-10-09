"""Os letterings: onde cada um entra, a pilha da lista, a trava de layout e o HTML.

Autoria por anúncio: a âncora de cada lettering é a N-ésima ocorrência de uma palavra (normalizada).
Calculados ANTES das legendas para deconflitar: o lettering vira o texto principal do trecho, então
a legenda palavra a palavra é suprimida na janela dele (senão a mesma frase aparece 2x na tela).

Ordem do pipeline (a ordem importa): calcular, fundir a pilha, travar no layout, numerar.

ESTILOS (W4.D, C7). Cada lettering do config pode trazer `estilo` (um dos 8 de `cinema.lettering_estilos`) e, na
caixa nativa, `cor` (ambar, branco ou preto). Sem estilo, ou com `serif_editorial`, o HTML é exatamente o de antes
(é o que segura a paridade do overlay). Em tela dividida, em close e na pilha o estilo cai no editorial, o único
calibrado para essas faixas. No marcador, `*palavra*` vira `<span class="hi">`; nos outros estilos novos o
asterisco de ênfase sai; na seta de CTA entra a `<div class="seta">` que o GSAP faz quicar.
"""
import re
import sys

from cinema import lettering_estilos as LE
from overlay.html_injecao import sem_emoji
from overlay.transcricao import norm

PISO_DURACAO = 1.20     # menos que isso o lettering não é lido
FOLGA_TROCA = 0.10      # o lettering termina (ou recomeça) 0,10 s antes (depois) da troca de layout


def calcular(cfg_letterings, words, spans, blocks, janelas_split):
    """Os letterings do config com início, duração e flags (`split`, `logo`, `baixo`, `pilha`).

    - `split`: o lettering cai DENTRO de um bloco de tela dividida e desce para o peito do
      apresentador (no split ele mora na metade de baixo e o lettering centrado pousa no rosto);
    - `logo`: o bloco do roteiro marcado com "+ logo" põe o logo DENTRO do lettering, na mesma janela
      e com a mesma animação CSS+GSAP, sem timing novo para desencontrar.
    """
    letts = []
    for L in cfg_letterings:
        alvo, nth, n = norm(L["anchor"]), L.get("nth", 1), 0
        t0 = None
        for w in words:
            if norm(w["text"]) == alvo:
                n += 1
                if n == nth:
                    t0 = w["start"]
                    break
        if t0 is None:
            sys.exit(f"lettering sem ancora: {L}")
        dur_l = L.get("dur", 2.2)
        no_split = any(a <= t0 < b for a, b in janelas_split)
        _bloco_do_lett = next((bi for bi, (bs, be) in enumerate(spans)
                               if bs <= t0 < be), None)
        _tem_logo = (_bloco_do_lett is not None
                     and "logo" in blocks[_bloco_do_lett]["instr"].lower())
        if _tem_logo:
            print(f"   [logo] roteiro pede logo no bloco {_bloco_do_lett}: entra junto "
                  f"do lettering em {t0:.2f}s", flush=True)
        lett = {"id": f"lett{chr(65+len(letts))}", "lead": L["lead"], "key": L["key"],
                "start": round(t0, 2), "dur": dur_l, "split": no_split,
                "logo": _tem_logo, "baixo": bool(L.get("baixo")),
                "pilha": L.get("pilha")}
        for campo in ("estilo", "cor"):          # só quando o config pede: o config antigo gera o mesmo dict
            if L.get(campo):
                lett[campo] = L[campo]
        letts.append(lett)
    return letts


def fundir_pilhas(letts):
    """Letterings que declaram o mesmo `pilha` viram UM bloco com várias linhas.

    Cada linha entra na hora da própria palavra (delay relativo ao início do grupo) e NENHUMA sai
    antes do fim: é o quadro de recompensa da lista. A duração do bloco vai do início da primeira
    linha ao fim da última.
    """
    _grupos, _ordem = {}, []
    for l in letts:
        g = l.get("pilha")
        if not g:
            _ordem.append(l)
            continue
        if g not in _grupos:
            _grupos[g] = l
            l["linhas"] = []
            _ordem.append(l)
        base = _grupos[g]
        base["linhas"].append({"key": l["key"], "delay": round(l["start"] - base["start"], 2)})
        base["dur"] = round(max(base["start"] + base["dur"],
                                l["start"] + l["dur"]) - base["start"], 2)
    return _ordem


def travar_no_layout(letts, janelas_split):
    """Lettering não atravessa a troca de layout (27/08/2026, segunda passada, DEPOIS da fusão).

    A primeira versão rodava dentro do laço de letterings, e a fusão da pilha logo abaixo recalculava
    `dur` a partir da última linha, apagando o corte: o "ENQUANTO ISSO" ficou 1,7 s em cima da cara do
    apresentador (9,2% a 13,1% do núcleo do rosto), e o gate não pegou porque o próprio texto em cima
    da cara quebra o detector. Aqui a trava roda uma vez só, no bloco que de fato vai para a tela.

    Cabe antes da troca (sobra PISO_DURACAO ou mais): ENCURTA. Não cabe: ADIA para depois da troca e
    mantém a duração PEDIDA. Dois bugs achados pelo diretor de arte: o adiamento descontava da
    duração o tempo que o lettering NÃO CHEGOU A FICAR na tela ("SABE / por que?" pedia 1,8 s e
    sobreviveu com 0,47 s, um flash na janela que decide o scroll), e o `start` era reatribuído ANTES
    do cálculo dos delays, então o reajuste da pilha era no-op. Só a primeira borda que atravessa conta.
    """
    for l in letts:
        for _a, _b in janelas_split:
            _borda = (_a if l["start"] < _a < l["start"] + l["dur"]
                      else (_b if l["start"] < _b < l["start"] + l["dur"] else None))
            if _borda is None:
                continue
            _novo = round(_borda - l["start"] - FOLGA_TROCA, 2)
            if _novo >= PISO_DURACAO:
                print(f"   [layout] lettering '{l['key'][:26]}' encurtado de "
                      f"{l['dur']:.2f}s pra {_novo:.2f}s: o quadro troca de layout em "
                      f"{_borda:.2f}s", flush=True)
                l["dur"] = _novo
            else:
                _novo_t0 = round(_borda + FOLGA_TROCA, 2)
                _desloc = round(_novo_t0 - l["start"], 2)
                print(f"   [layout] lettering '{l['key'][:26]}' adiado de {l['start']:.2f}s "
                      f"pra {_novo_t0:.2f}s: nao cabe antes da troca (duracao mantida em "
                      f"{max(l['dur'], PISO_DURACAO):.2f}s)", flush=True)
                l["dur"] = max(l["dur"], PISO_DURACAO)
                l["start"] = _novo_t0
                l["adiado"] = True        # W5.X: o eco dele só sai se encostar (legendas.FOLGA_ECO_ADIADO)
                if l.get("linhas"):
                    l["linhas"] = [{**x, "delay": max(0.0, round(x["delay"] - _desloc, 2))}
                                   for x in l["linhas"]]
            l["split"] = any(x <= l["start"] < y for x, y in janelas_split)
            break


def finalizar(letts):
    """Avisa as pilhas, devolve as janelas [(início, fim)] e renumera os ids (lettA, lettB...) depois
    da fusão."""
    for l in letts:
        if l.get("linhas"):
            print(f"   [pilha] {l['id']}: {len(l['linhas'])} linhas, "
                  f"{l['start']:.2f}s por {l['dur']:.2f}s "
                  f"(delays {[x['delay'] for x in l['linhas']]})", flush=True)
    lett_windows = [(l["start"], l["start"] + l["dur"]) for l in letts]
    for i, l in enumerate(letts):
        l["id"] = f"lett{chr(65 + i)}"
    return lett_windows


def montar(cfg_letterings, words, spans, blocks, janelas_split):
    """(letterings, janelas): calcular, fundir a pilha, travar no layout e numerar, nessa ordem."""
    letts = calcular(cfg_letterings, words, spans, blocks, janelas_split)
    letts = fundir_pilhas(letts)
    travar_no_layout(letts, janelas_split)
    lett_windows = finalizar(letts)
    return letts, lett_windows


def _estilo_da_tela(l):
    """(estilo efetivo, cor) do lettering; colorway desconhecido é erro que nomeia o colorway."""
    e = LE.efetivo(l.get("estilo"), split=bool(l.get("split")), baixo=bool(l.get("baixo")),
                   pilha=bool(l.get("linhas")))
    cor = None
    if e == "caixa_nativa":
        cor = l.get("cor") or LE.COR_PADRAO
        if cor not in LE.COLORWAYS:
            raise ValueError("colorway desconhecido na caixa nativa: %r (use um de: %s)"
                             % (cor, ", ".join(LE.COLORWAYS)))
    return e, cor


def _key_html(texto, estilo):
    t = sem_emoji(texto)
    if estilo == LE.PADRAO:
        return t
    if estilo == "marcador":
        return re.sub(r"\*([^*]+)\*", r'<span class="hi">\1</span>', t).replace("*", "")
    return t.replace("*", "")


def _html_estilizado(i, l, estilo, cor):
    """O HTML de um lettering de estilo novo (só em avatar cheio: pilha, split e close ficam no editorial)."""
    classes = "lett clip %s" % LE.classe(estilo) + (" cor-%s" % cor if cor else "")
    return (f'<div class="{classes}" id="{l["id"]}" data-estilo="{estilo}" '
            f'data-start="{l["start"]}" data-duration="{l["dur"]}" data-track-index="{32+i}">\n'
            f'  <div class="lead">{sem_emoji(l["lead"])}</div>\n'
            f'  <div class="key">{_key_html(l["key"], estilo)}</div>\n'
            + ('  <div class="seta"></div>\n' if estilo == "seta_cta" else "")
            + ('  <img class="lett-logo" src="logo.png" alt="">\n' if l.get("logo") else "")
            + '</div>')


def html(letts):
    """O HTML dos letterings, uma faixa de trilha (32 + i) cada.

    ATENÇÃO: o HTML do lettering é montado AQUI, e não pelo `build_timeline` (a função equivalente
    de lá este fluxo não usa; um build inteiro foi perdido editando a errada e concluindo que o CSS
    estava errado). Emoji sai em todos os ramos, inclusive o da PILHA, que era o único que mandava o
    texto cru: o anúncio saiu com emoji na tela por 3,87 s depois de declarado "sem emoji". O
    marcador de negação agora é a barra vermelha do CSS (`.lett-pilha .key::before`), não pictograma.
    """
    saida = []
    for i, l in enumerate(letts):
        estilo, cor = _estilo_da_tela(l)
        saida.append(_html_estilizado(i, l, estilo, cor) if estilo != LE.PADRAO else _html_editorial(i, l))
    return "\n".join(saida)


def _html_editorial(i, l):
    """O HTML do lettering padrão (serif_editorial), byte a byte o de antes da W4.D."""
    return (
        f'<div class="lett clip{" lett-split" if l.get("split") else ""}'
        f'{" lett-baixo" if l.get("baixo") else ""}'
        f'{" lett-pilha" if l.get("linhas") else ""}" id="{l["id"]}" '
        f'data-start="{l["start"]}" data-duration="{l["dur"]}" data-track-index="{32+i}">\n'
        f'  <div class="lead">{sem_emoji(l["lead"])}</div>\n'
        + (
            "".join(f'  <div class="key" data-delay="{x["delay"]}">'
                    f'{sem_emoji(x["key"])}</div>\n'
                    for x in l["linhas"])
            if l.get("linhas") else
            f'  <div class="key{" key-longa" if len(l["key"]) > 18 else ""}">'
            f'{sem_emoji(l["key"])}</div>\n')
        + ('  <img class="lett-logo" src="logo.png" alt="">\n' if l.get("logo") else "")
        + '</div>')
