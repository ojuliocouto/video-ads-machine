"""O gancho (hook): quanto tempo fica na tela e como entra no HTML.

Timing. Abertura em insert: o hook cobre o insert inteiro e dissolve no RETORNO DO AVATAR (o
primeiro bloco que não é insert, não `spans[1]`: com 2 ou mais inserts de abertura, usar
`spans[1]` fazia o hook sumir cedo e deixava zona morta, com o rosto ainda coberto por b-roll,
que dá sensação de corte). Abertura no avatar: segura 3 s por cima.

Teto de 3,2 s. Com 3 inserts de abertura seguidos, "segurar até o rosto voltar" deu 15,5 s de hook
congelado: ele tapava o payoff dos inserts E, como a legenda espera o hook, o anúncio ficava 15 s
SEM LEGENDA NENHUMA (fatal em Reels com som desligado). O pedido original era hook de cerca de
4 s; 5,0 s deixava 4 s sem legenda na abertura (o gate reprova vão acima de 2,5 s). 3,2 s mantém o
gancho legível e libera a legenda quase junto com a fala.

HTML. O texto de tela perde emoji. O estilo `punch` é VARIANTE (sans condensado pesado, caixa alta,
entrelinha apertada, palavra de ênfase bem maior, sombra dura), não troca global: o editorial
continua o padrão.
"""
from collections import namedtuple

from overlay.html_injecao import sem_emoji
from overlay.transcricao import SPEED

HOOK_MAX = 3.2
HOOK_END = round(2.5 / SPEED, 3)   # 2.174 s: o hook encolhe junto com a fala acelerada

# W5.Y: GANCHO SEM FANTASMA. A dissolução de 0,4 s terminava em `hook_gone`, e a primeira legenda entra a partir de
# `cap_gate - AVANCO_LEGENDA` (a antecipação de 0,12 s do timeline.js): aos 2,08 s as duas estavam na tela, o gancho
# esmaecido por cima da frase. Regra: o gancho termina de sair ANTES da primeira legenda entrar. A saída dura
# FADE_GANCHO e acaba FOLGA_GANCHO antes de `hook_gone`; com `cap_gate` até 0,05 s antes de `hook_gone` e a legenda
# entrando 0,12 s antes do próprio início, sobra 0,03 s livres (menos de um quadro a 30 fps) entre os dois textos.
FADE_GANCHO = 0.15
FOLGA_GANCHO = 0.20
AVANCO_LEGENDA = 0.12              # o mesmo número de `Math.max(0, gStart - 0.12)` em templates/_parciais/timeline.js

Hook = namedtuple("Hook", "opening_insert hook_gone hook_fade hook_dur cap_gate")

CSS_PUNCH = """
      /* variante PUNCH do hook */
      /* justify-content:flex-start + margin-top pequeno sobe o bloco pro TERCO SUPERIOR. No bloco
         de tela dividida o padrao (centro, margin-top 150px) caia exatamente em cima do rosto do
         apresentador no painel de baixo. */
      /* SCRIM PROPRIO: com o painel de cima PREENCHIDO, o texto da propria pagina colidia com o hook
         e os dois ficavam ilegiveis. Faixa escura atras do bloco resolve sem escurecer o quadro
         inteiro. */
      /* 70px punha a linha 3 do gancho ate x993, dentro da coluna de curtir/comentar do Reels, nos
         2,4s que decidem o scroll. O padding foi subido no TEMPLATE sem ver que este `!important`
         inline vence: dois lugares definem o hook. */
      #hook.punch { padding:0 140px; justify-content:flex-start !important;
        /* scrim mais leve: medido, um anuncio abria 57% e outro 59% mais escuros que o resto, e o
           quadro 0 e o poster no feed. O texto e caixa alta pesada com sombra tripla, entao aguenta
           bem menos fundo. */
        background:linear-gradient(180deg, rgba(4,5,10,0) 0%, rgba(4,5,10,.26) 12%,
          rgba(4,5,10,.56) 24%, rgba(4,5,10,.56) 44%,
          rgba(4,5,10,0) 66%) !important; }
      #hook.punch .hook-inner { align-items:center !important; gap:0 !important;
        margin-top:310px !important; }
      #hook.punch .eyebrow { font-family:"Inter"; font-weight:800; font-size:46px;
        letter-spacing:1px; margin-bottom:6px; color:#fff;
        text-shadow:0 4px 0 rgba(0,0,0,.55), 0 8px 30px rgba(0,0,0,.95); }
      #hook.punch .l1 { font-family:"Inter"; font-weight:800; font-size:64px;
        text-transform:uppercase; line-height:.98; letter-spacing:-1px; color:#fff;
        text-shadow:0 4px 0 rgba(0,0,0,.55), 0 8px 30px rgba(0,0,0,.95); }
      #hook.punch .accent { font-family:"Inter", sans-serif !important;
        font-style:normal !important; font-weight:900 !important; font-size:104px !important;
        text-transform:uppercase; line-height:.96 !important; letter-spacing:-2.5px !important;
        color:#fff; text-shadow:0 5px 0 rgba(0,0,0,.6), 0 10px 36px rgba(0,0,0,.95) !important; }
    </style>"""


def calcular_hook(blocks, spans):
    """Os quatro tempos do hook: quando some, quando começa a dissolver, até onde vai o clipe e a
    partir de quando a legenda pode aparecer (`cap_gate`)."""
    opening_insert = blocks[0]["type"] == "insert" and len(spans) > 1
    first_avatar_i = next((i for i, b in enumerate(blocks) if b["type"] != "insert"), 1)
    ref = (spans[first_avatar_i][0] if opening_insert and first_avatar_i < len(spans)
           else (spans[1][0] if len(spans) > 1 else spans[0][1]))
    hook_gone = round(min(ref + 0.1, HOOK_MAX), 2) if opening_insert else 3.0
    hook_fade = round(hook_gone - FOLGA_GANCHO - FADE_GANCHO, 2)    # começa a sair (acaba FOLGA_GANCHO antes do fim)
    hook_dur = round(hook_gone + 0.1, 2)     # janela do clipe cobre até depois do fade
    cap_gate = round(hook_gone - 0.05, 2) if opening_insert else hook_gone   # sem legenda com o hook na tela
    return Hook(opening_insert, hook_gone, hook_fade, hook_dur, cap_gate)


def aplicar_html(html, cfg_hook, h):
    """Textos, duração, fade e (se `style` for `punch`) a variante, na ordem do original."""
    hk = {k: sem_emoji(v) for k, v in cfg_hook.items() if isinstance(v, str)}
    html = html.replace('id="hook" class="clip" data-start="0" data-duration="2.5"',
                        f'id="hook" class="clip" data-start="0" data-duration="{h.hook_dur}"')
    html = html.replace('<div data-hf-id="hf-bc1a" class="eyebrow">uma skill de</div>',
                        f'<div data-hf-id="hf-bc1a" class="eyebrow">{hk["eyebrow"]}</div>')
    html = html.replace('<div data-hf-id="hf-8q5w" class="l1">criação de</div>',
                        f'<div data-hf-id="hf-8q5w" class="l1">{hk["l1"]}</div>')
    html = html.replace('<div data-hf-id="hf-ons9" class="accent">páginas</div>',
                        f'<div data-hf-id="hf-ons9" class="accent">{hk["accent"]}</div>')
    html = html.replace('#hook .l1 { font-family:"Inter"; font-weight:300; color:#fff;',
                        '#hook .l1 { font-family:"Inter"; font-weight:300; color:#fff; text-align:center;')
    html = html.replace('#hook .accent { font-family:"Playfair Display", serif; font-weight:600; font-style:italic;',
                        '#hook .accent { font-family:"Playfair Display", serif; font-weight:600; font-style:italic; '
                        'text-align:center;')
    if (cfg_hook or {}).get("placa"):            # W5.X: footage clara atrás do gancho
        html = html.replace('id="hook" class="clip"', 'id="hook" class="clip placa"')
    if (cfg_hook or {}).get("style") == "punch":
        html = html.replace("</style>", CSS_PUNCH)
        html = html.replace('id="hook" class="clip"', 'id="hook" class="clip punch"')
    html = html.replace(
        'tl.to("#hook .hook-inner", { scale: 1.04, duration: 1.7, ease: "sine.inOut" }, 0.8);',
        'tl.to("#hook .hook-inner", { scale: 1.04, duration: 1.7, ease: "sine.inOut" }, 0.8);\n'
        f'      tl.to("#hook", {{ opacity: 0, duration: {FADE_GANCHO}, ease: "power1.in" }}, {h.hook_fade});')
    return html
