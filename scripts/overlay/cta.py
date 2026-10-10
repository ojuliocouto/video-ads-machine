"""O CTA e o logo: quando sobem e como entram no HTML.

UMA FONTE SÓ para o corte da legenda e a subida do CTA: `cta_start`. As duas desencontradas deixaram
um anúncio de 13 s com a tela literalmente vazia (o gate acusou 17% sem texto): a legenda do corpo
é cortada a partir do logo e o CTA é o que ocupa o lugar dela. O `cta_s` do HTML copia o `cta_start`;
se mexer aqui, o resto acompanha sozinho.

O CTA entra na ÂNCORA do bloco cta e NUNCA antes do início dele (W7.W, A2). A regra antiga subia o CTA quando a imagem
VOLTAVA ao apresentador depois do último insert com `dur_max`: no anúncio da prova isso foi 36,6 s, cerca de 3 s antes da
voz dizer "tocar aqui em Saiba Mais" (39,5 s), e a legenda do bloco anterior sumiu por 6,6 s com 24 palavras faladas sem
texto (o CTA ocupa o lugar da legenda). Um `dur_max` no último insert só devolve a imagem ao avatar: não adianta o CTA.
A âncora é a palavra em que o bloco cta VERBALIZA o botão: o lead ("toque aqui em") ou, sem lead, a primeira palavra do
rótulo ("Saiba Mais"). Sem a palavra na fala, o início do bloco.

O logo antecipa o pill em LOGO_LEAD (0,9 s: ainda anima, e perde só 0,9 s de legenda em vez de 3 s),
mas SÓ quando o bloco anterior ao CTA é avatar. Se for insert, o logo sobe por cima do b-roll: caiu
sobre a landing page que exibe o PRÓPRIO wordmark, dando dois wordmarks empilhados (medido no
quadro 1352, t=45,07 s). Sobre insert o logo entra junto com o corte para o avatar.
"""

import re
import sys

LOGO_LEAD = 0.9      # segundos que o logo antecipa o CTA (quando o bloco anterior é avatar)

# Os elementos do CTA nos templates, achados pelo `data-hf-id` e não pelo texto que o template escreveu (W3.X M5): o
# 9x16 tem "toca em" e `saiba mais<i class="arw"></i>`, o 1x1 tem "toque em" e `saiba mais`. Procurar o texto fazia
# o rótulo nunca entrar no 9x16 e o `cta_sem_lead` nunca funcionar no 1x1, com a timeline registrando os dois.
_LEAD = re.compile(r'<div data-hf-id="hf-laqu" class="lead">([^<]*)</div>\n?[ \t]*')
_TEXTO_DO_BOTAO = re.compile(r'(<div data-hf-id="hf-wto1" class="pill" id="cta-pill">)[^<]*')


def _norm(texto):
    from overlay.transcricao import norm
    return norm(texto)


def _palavra_do_lead(palavras, lead):
    """Índice da palavra falada que abre o lead. O lead é escrito como o botão ("toque aqui em") e falado como o
    apresentador fala ("tocar aqui em"): o verbo muda e o resto da frase não. Com 2 palavras ou mais, a frase falada tem
    que repetir o RESTO do lead e a âncora é a palavra logo antes dela; com 1, a palavra tem que ser a mesma."""
    toks = [_norm(t) for t in str(lead).split() if _norm(t)]
    if not toks:
        return None
    normas = [_norm(w["text"]) for w in palavras]
    resto = toks[1:] if len(toks) > 1 else toks
    desloc = 1 if len(toks) > 1 else 0
    for i in range(desloc, len(normas) - len(resto) + 1):
        if normas[i:i + len(resto)] == resto:
            return i - desloc
    return None


def _palavra_do_rotulo(palavras, rotulo):
    toks = [_norm(t) for t in str(rotulo).split() if _norm(t)]
    if not toks:
        return None
    return next((i for i, w in enumerate(palavras) if _norm(w["text"]) == toks[0]), None)


def calcular_cta_start(blocks, spans, retorno_avatar=None, words=None, cfg=None):
    """O instante em que o CTA entra: a âncora do último bloco (a palavra do lead, ou do rótulo) e, sem ela na fala,
    o início do bloco. Nunca antes do início do bloco. `retorno_avatar` é aceito e IGNORADO (a regra antiga que o
    usava sumiu: ver o topo do módulo)."""
    inicio, fim = spans[-1]
    cta_start = inicio
    palavras = [w for w in (words or []) if inicio - 1e-6 <= float(w["start"]) < fim]
    cfg = cfg or {}
    if palavras:
        i = _palavra_do_lead(palavras, cfg["cta_lead"]) if cfg.get("cta_lead") and not cfg.get("cta_sem_lead") else None
        if i is None and cfg.get("cta_label"):
            i = _palavra_do_rotulo(palavras, cfg["cta_label"])
        if i is not None:
            cta_start = max(inicio, float(palavras[i]["start"]))
    if cta_start > inicio:
        print(f"   [cta] entra na ancora do bloco, em {cta_start:.2f}s (o bloco comeca em {inicio:.2f}s)", flush=True)
    return cta_start


def logo_lead(blocks):
    """0,0 quando o bloco anterior ao último é insert; senão LOGO_LEAD."""
    prev_e_insert = len(blocks) > 1 and blocks[-2]["type"] == "insert"
    return 0.0 if prev_e_insert else LOGO_LEAD


def logo_start(cta_start, lead):
    """Início do logo, sem arredondar (é o corte da legenda do corpo)."""
    return max(cta_start - lead, 0.0)


def janela(cta_start, lead):
    """(cta_s, logo_s) do HTML: os mesmos números, arredondados no centésimo. O cta_s COPIA o
    cta_start; o logo_s usa o mesmo `lead` do corte da legenda, senão volta a sobreposição."""
    cta_s = round(cta_start, 2)
    logo_s = round(max(cta_s - lead, 0.0), 2)
    return cta_s, logo_s


def aplicar_html(html, cfg, cta_s, logo_s, total, janelas_split):
    """Rótulo, lead, tempos e a variante em tela dividida do CTA e do logo.

    `cta_sem_lead` tira o lead ("toca em" no 9x16, "toque em" no 1x1) quando o enquadramento não tem faixa livre
    para os três elementos (lead, pill e logo); a conta depende de onde o queixo cai naquele look. O rótulo troca o
    texto do botão nos dois templates (a seta do 9x16 fica). Template sem o elemento: aviso no stderr. O CTA que nasce em cima de
    tela dividida desce junto com o logo (`.cta-split`): `janelas_split` era consultado pela legenda e
    pelo lettering, e o CTA era o único dos três que não consultava, por isso pousava no rosto
    quando o último bloco era split.
    """
    if cfg.get("cta_lead") and not cfg.get("cta_sem_lead"):
        # o LEAD do bloco cta é o lead do botão (W5.A: a KEY é o texto do botão; nada de lettering em cima da pílula)
        html, n = _LEAD.subn(lambda m: m.group(0).replace(">%s</div>" % m.group(1), ">%s</div>" % cfg["cta_lead"], 1),
                             html, count=1)
        if not n:
            print("   [cta] AVISO: o template nao tem o lead do CTA (data-hf-id hf-laqu): o LEAD do cta nao entrou",
                  file=sys.stderr, flush=True)
    if cfg.get("cta_sem_lead"):
        m = _LEAD.search(html)
        if m:
            html = html[:m.start()] + html[m.end():]
            print(f"   [cta] sem o lead '{m.group(1)}': so pill + logo", flush=True)
        else:
            print("   [cta] AVISO: o template nao tem o lead do CTA (data-hf-id hf-laqu): cta_sem_lead nao mudou nada",
                  file=sys.stderr, flush=True)
    rotulo = cfg.get("cta_label", "saiba mais")
    html, n = _TEXTO_DO_BOTAO.subn(lambda m: m.group(1) + rotulo, html, count=1)
    if not n:
        print(f"   [cta] AVISO: o template nao tem o botao do CTA (id cta-pill): o rotulo {rotulo!r} nao entrou",
              file=sys.stderr, flush=True)
    _cta_no_split = any(a <= cta_s < b for a, b in janelas_split)
    if _cta_no_split:
        print(f"   [cta] {cta_s:.2f}s cai em tela dividida: descendo o CTA e o logo "
              f"(senao pousam no rosto)", flush=True)
        html = html.replace('id="cta" class="clip"', 'id="cta" class="clip cta-split"', 1)
        html = html.replace('id="ev-logo" class="clip"', 'id="ev-logo" class="clip logo-split"', 1)
        # a legenda que acompanha o CTA sobe junto: fica acima do bloco, onde quer que ele esteja
        html = html.replace('id="caps" class="clip"', 'id="caps" class="clip caps-cta-split"', 1)
    html = html.replace('data-start="50.4" data-duration="4.96" data-track-index="46"',
                        f'data-start="{cta_s}" data-duration="{round(total-cta_s,2)}" data-track-index="46"')
    html = html.replace('data-start="46.7" data-duration="8.68" data-track-index="48"',
                        f'data-start="{logo_s}" data-duration="{round(total-logo_s,2)}" data-track-index="48"')
    html = html.replace('}, 50.5);', f'}}, {cta_s + 0.1:.2f});')
    html = html.replace('}, 50.6);', f'}}, {cta_s + 0.2:.2f});')
    html = html.replace('}, 50.75);', f'}}, {cta_s + 0.35:.2f});')
    html = html.replace('}, 51.0);', f'}}, {cta_s + 0.6:.2f});')
    html = html.replace('}, 46.9);', f'}}, {logo_s + 0.2:.2f});')
    return html
