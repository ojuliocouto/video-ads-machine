"""As trocas de texto que o overlay faz no template HTML, uma por função.

Este módulo é uma folha: não importa nenhum outro módulo do pacote, para que gancho, lettering e
CTA possam usar `sem_emoji` sem ciclo. As funções são `str -> str` e preservam a ordem em que o
gerador original aplicava os `replace` (a ordem importa: o hook marca `class="clip punch"` depois
de trocar a duração, por exemplo).

O template é do usuário e tem marcadores fixos (`<!-- INJECT:captions -->`, `/* INJECT:wipes */`,
`data-duration="55.36"`). Marcador que falta no template não é erro: o `replace` não acha nada e
o resto segue. É o caso do `<!-- INJECT:chips -->` no template quadrado.
"""
import re


def sem_emoji(t):
    """Remove pictogramas do texto de tela (19/08/2026: "esses emojis deixam ainda mais com cara de
    pobre"). A COPY do doc não muda: o strip é só na renderização do overlay (hook, lettering, chip).

    Sai tudo de 0x1F000 em diante, a faixa 0x2600 a 0x27BF (que inclui ✓ e ❌), a estrela 2B50, o
    seletor de variação FE0F e o ZWJ 200D. Espaços repetidos viram um só.
    """
    out = []
    for ch in str(t):
        if ord(ch) >= 0x1F000 or (0x2600 <= ord(ch) <= 0x27BF) or ch in "⭐️‍":
            continue
        out.append(ch)
    return " ".join("".join(out).split())


def injetar_marcadores(html, caps_html, letts_html):
    """Legendas e letterings entram nos marcadores do template."""
    html = html.replace("<!-- INJECT:captions -->", caps_html)
    html = html.replace("<!-- INJECT:letterings -->", letts_html)
    return html


def injetar_chips(html, chips_html):
    """Chips no marcador, e os marcadores de preset (`INJECT:preset:<dimensão>`) saem."""
    html = html.replace("<!-- INJECT:chips -->", chips_html)
    html = re.sub(r"<!--\s*INJECT:preset:[a-z-]+\s*-->", "", html)
    return html


def fixar_duracao(html, total):
    """A duração do template (55.36) vira a do anúncio, em todo clipe que a repete."""
    return html.replace('data-start="0" data-duration="55.36"', f'data-start="0" data-duration="{total}"')


def suavizar_grade(html):
    """Grade quente a 50% (calibrada pro cenário colorido; validada no piloto)."""
    html = html.replace(
        "radial-gradient(130% 100% at 50% 22%, rgba(255,193,128,0.16), rgba(255,150,80,0.05) 45%, transparent 72%)",
        "radial-gradient(130% 100% at 50% 22%, rgba(255,193,128,0.08), rgba(255,150,80,0.025) 45%, transparent 72%)")
    html = html.replace(
        "linear-gradient(180deg, rgba(255,168,92,0.06) 0%, transparent 38%, rgba(28,14,4,0.16) 100%)",
        "linear-gradient(180deg, rgba(255,168,92,0.03) 0%, transparent 38%, rgba(28,14,4,0.16) 100%)")
    return html


def remover_beat_pb(html):
    """O beat preto e branco do reel de origem não é usado: o bloco inteiro vira um comentário."""
    return re.sub(r'// ===== BEAT PRETO E BRANCO.*?tl\.to\("#a-roll", \{ "--bw": 0[^;]*;\n',
                  "// (beat P&B do reelC nao usado)\n", html, flags=re.S)


def remover_wipes(html):
    """WIPE DE GRADE DESLIGADO (19/08/2026). Medido no arquivo entregue, quadro a quadro: pico de
    cobertura de 98,5% a 99,5%, com 5 a 7 quadros acima de 70% em cada um dos 4 surtos (0,17 a
    0,23 s de tela praticamente apagada). A maquinaria (agrupamento de brolls e o marcador no
    template) fica no lugar; se o wipe voltar, precisa de três mudanças juntas: z-index abaixo de
    lettering e legenda, saída em t+0,25 e stagger.amount 0,45, com o gate de cobertura chapada
    barrando qualquer quadro acima de 70%. O marcador sai e nada entra no lugar.
    """
    return html.replace("/* INJECT:wipes */", "")
