"""As trocas de texto que o overlay faz no template HTML, uma por função.

Este módulo é uma folha: não importa nenhum outro módulo do pacote, para que gancho, lettering e
CTA possam usar `sem_emoji` sem ciclo. As funções são `str -> str` e preservam a ordem em que o
gerador original aplicava os `replace` (a ordem importa: o hook marca `class="clip punch"` depois
de trocar a duração, por exemplo).

O template é do usuário e tem marcadores fixos (`<!-- INJECT:captions -->`, `/* INJECT:wipes */`,
`data-duration="55.36"`). Marcador que falta no template não é erro: o `replace` não acha nada e
o resto segue. É o caso do `<!-- INJECT:chips -->` no template quadrado.

PARCIAIS (W4.D). Os dois templates guardam só a geometria do formato e incluem o visual e a timeline
compartilhados por marcador: `/* PARCIAL:<arquivo> */`, dentro do `<style>` (CSS) e do `<script>` (o
`timeline.js`, o MESMO nos dois formatos). `resolver_parciais` troca cada marcador pelo arquivo de
`templates/_parciais/` e é o primeiro passo de `injetar_marcadores`: todas as trocas de texto que vêm
depois (hook, CTA, b-rolls, grade) enxergam o template inteiro, como antes. O GSAP sai da cópia local
(`templates/_vendor/gsap.min.js`, guardada pelo setup) quando ela existe, embutido no HTML; sem ela, ou com
`VAM_GSAP=cdn`, fica a tag da CDN (defeito 18: render dependia de rede).
"""
import hashlib
import os
import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
PARCIAIS = TEMPLATES / "_parciais"
VENDOR_GSAP = TEMPLATES / "_vendor" / "gsap.min.js"
TAG_GSAP_CDN = '<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>'
GSAP_MIN_BYTES = 10_000       # menos que isso não é o gsap.min.js (página de erro, download cortado)
_MARCA_PARCIAL = re.compile(r"/\* PARCIAL:([a-z0-9_]+\.(?:css|js)) \*/")


def _gsap_local(vendor):
    """O conteúdo da cópia local do GSAP, ou None (ausente, truncada ou VAM_GSAP=cdn)."""
    if os.environ.get("VAM_GSAP", "").strip().lower() == "cdn" or vendor is None:
        return None
    vendor = Path(vendor)
    if not vendor.is_file() or vendor.stat().st_size < GSAP_MIN_BYTES:
        return None
    texto = vendor.read_text(encoding="utf-8")
    return None if "</script" in texto.lower() else texto


def resolver_parciais(html, pasta=PARCIAIS, vendor=VENDOR_GSAP):
    """Troca cada `/* PARCIAL:<arquivo> */` pelo arquivo de `pasta` e a tag da CDN do GSAP pela cópia local.

    Parcial que falta é erro que nomeia o arquivo (FileNotFoundError): template quebrado não pode virar
    overlay sem CSS. HTML sem marcador passa intacto (idempotente)."""
    pasta = Path(pasta)

    def _parcial(m):
        arq = pasta / m.group(1)
        if not arq.is_file():
            raise FileNotFoundError("parcial do template ausente: %s (procurado em %s)" % (m.group(1), pasta))
        return arq.read_text(encoding="utf-8").rstrip("\n").lstrip(" ")

    html = _MARCA_PARCIAL.sub(_parcial, html)
    local = _gsap_local(vendor)
    if local is not None and TAG_GSAP_CDN in html:
        html = html.replace(TAG_GSAP_CDN, "<script>\n" + local.rstrip("\n") + "\n</script>", 1)
    return html


def ler_template(caminho, pasta=PARCIAIS, vendor=VENDOR_GSAP):
    """O `index.html` de um template com os parciais resolvidos (o que o gerador de fato usa)."""
    return resolver_parciais(Path(caminho).read_text(encoding="utf-8"), pasta=pasta, vendor=vendor)


def assinatura_template(caminho, pasta=PARCIAIS):
    """sha256 do template E de cada parcial que ele inclui, na ordem: o gate "template mudou no meio do
    build" (build_composite) precisa enxergar a mudança num parcial, não só no index.html."""
    h = hashlib.sha256()
    bruto = Path(caminho).read_bytes()
    h.update(bruto)
    for nome in _MARCA_PARCIAL.findall(bruto.decode("utf-8")):
        arq = Path(pasta) / nome
        h.update(nome.encode("utf-8"))
        h.update(arq.read_bytes() if arq.is_file() else b"<ausente>")
    return h.hexdigest()


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
    """Legendas e letterings entram nos marcadores do template, depois dos parciais resolvidos."""
    html = resolver_parciais(html)
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
