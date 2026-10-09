"""Exposição do insert: o piso que levanta asset escuro, a página branca que nunca escurece e o
offset do fundo desfocado da tela cheia. Tudo MEDIDO na fonte, nunca digitado.

## Por que existe

Os assets de abertura de um anúncio eram páginas escuras e cinematográficas (luminância média 50
e 36 numa escala de 255), e os primeiros 11,5 s ficavam quase pretos, que é exatamente a janela
que decide retenção no Reels. Depender de alguém acertar o campo `exposicao` na mão não funcionou:
o estrategista reprovou um anúncio com dois inserts ilegíveis, e o painel de cima medido no
arquivo entregue dava luminância 17,5 e 2,1. Agora o motor MEDE a fonte e calcula o piso para o
painel cair na faixa em que os inserts bons já caem (83 a 100 de média). O valor declarado no JSON
continua valendo como MÍNIMO: quem quiser clarear mais, clareia.

## A página branca nunca escurece

O teto antigo escurecia página branca PERMANENTEMENTE (244 virava 188 = cinza) e o resultado seguia
"um filtro cinza em cima dos inserts, tudo meio pálido". Consertei o contraste acoplado e mantive a
causa (brilho negativo). Hoje o teto (185) só ZERA a exposição declarada pra cima (clarear o que já
é branco continua errado) e nunca escurece. O flash de brilho no corte, que era o motivo do teto,
ficou como custo aceito: se um dia incomodar, o caminho é rampa por `sendcmd`, nunca filtro
permanente (o `eq` não avalia expressão por quadro: `if(lt(t,...))` congela em t=0).

## O contraste acompanha o módulo do ganho

A fórmula era `1 + ex*0,6`, escrita quando `ex` só podia ser positivo (clarear lava a imagem, então
subir o contraste junto compensa). Com o teto, `ex` passou a poder ser negativo e a mesma fórmula
virou REDUÇÃO de contraste: asset claro saía escurecido E lavado ao mesmo tempo. `abs(ex)` faz
clarear e escurecer preservarem contraste por igual.

## Média x mediana

A MÉDIA mente em asset bimodal: um insert deu média 64 e mediana 33 (p10=16, p90=245), ou seja, a
maior parte do quadro é fundo escuro e uma área pequena é página bem clara. O offset do fundo
desfocado mira a MEDIANA, porque o desfoque preserva a média mas não a mediana. A luminância usada
pelo piso/teto do card segue sendo a média, já calibrada e testada.
"""
import os
import subprocess
import tempfile

from PIL import Image

ALVO_LUM = 105.0
TETO_LUM = 185.0
EXPO_MIN = -0.22     # luminância média alvo do painel; os inserts bons caem entre 83 e 100
EXPO_MAX = 0.45      # teto: acima disso a fonte escura vira cinza lavado
ALVO_BG_CHEIO = 30.0     # luminância alvo do fundo desfocado da tela cheia, de 0 a 255

_CACHE_LUM = {}
_CACHE_LUM_MED = {}


def _quadro(src, start):
    """Imagem em cinza de um quadro da fonte (1,5 s depois do início), ou None se não der."""
    with tempfile.TemporaryDirectory() as td:
        q = os.path.join(td, "l.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(start + 1.5),
                        "-i", src, "-frames:v", "1", q], capture_output=True, timeout=60)
        if os.path.exists(q):
            return Image.open(q).convert("L")
    return None


def luminancia_mediana_fonte(src, start=0.0):
    """Mediana de luminância da fonte, medida no mesmo quadro que `luminancia_fonte`. Só para o
    `bg_offset`. Cacheada por arquivo; None se a medição falhar."""
    if src in _CACHE_LUM_MED:
        return _CACHE_LUM_MED[src]
    val = None
    try:
        im = _quadro(src, start)
        if im is not None:
            px = sorted(im.getdata())
            val = px[len(px) // 2]
    except Exception:
        val = None
    _CACHE_LUM_MED[src] = val
    return val


def luminancia_fonte(src, start=0.0):
    """Luminância MÉDIA da fonte, medida num quadro. Cacheada por arquivo; None se falhar."""
    if src in _CACHE_LUM:
        return _CACHE_LUM[src]
    val = None
    try:
        im = _quadro(src, start)
        if im is not None:
            val = sum(im.getdata()) / (im.width * im.height)
    except Exception:
        val = None
    _CACHE_LUM[src] = val
    return val


def calcular_exposicao(lum, declarada, nome=""):
    """Ganho de brilho final de um insert, dada a luminância medida e o valor declarado.

    Sem luminância medida, vale o declarado. Abaixo do alvo, sobe até o piso (se o piso passar do
    declarado). Acima do teto, zera ganho declarado pra cima e nunca escurece."""
    ex = float(declarada or 0)
    if lum is None:
        return ex
    if lum < ALVO_LUM:
        piso = min((ALVO_LUM - lum) / 255.0, EXPO_MAX)
        if piso > ex:
            print(f"  [exposicao] {nome}: fonte em {lum:.0f}/255, "
                  f"subindo de {ex:.2f} para {piso:.2f} (alvo {ALVO_LUM})", flush=True)
            ex = piso
    elif lum > TETO_LUM:
        if ex > 0:
            print(f"  [exposicao] {nome}: fonte em {lum:.0f}/255 "
                  f"já é clara, zerando exposição declarada de {ex:.2f}", flush=True)
            ex = 0.0
    return ex


def filtro_eq(ex):
    """Trecho `eq=...,` do ganho, ou "" quando o ganho é desprezível."""
    if abs(ex) < 0.005:
        return ""
    return f"eq=brightness={ex:.3f}:contrast={1 + abs(ex) * 0.6:.3f},"


def eq_exposicao(cfg):
    """Filtro de exposição de um insert a partir do campo `exposicao` do inserts.json e da fonte."""
    ex = float(cfg.get("exposicao", 0) or 0)
    src = cfg.get("file")
    if src:
        lum = luminancia_fonte(src, float(cfg.get("start", 0) or 0))
        ex = calcular_exposicao(lum, ex, os.path.basename(src))
    return filtro_eq(ex)


def offset_fundo(lum_mediana):
    """Quanto clarear ou escurecer o fundo desfocado da tela cheia, dada a mediana medida.

    Offset fixo ZERAVA o quadro: `brightness=-0.40` são -102 níveis, e num asset de luminância 33
    (cinco de dez de um anúncio estavam entre 33 e 64) isso não escurece, zera. Medido em
    um anúncio inteiro: 12,3% do tempo com 60% a 67% do quadro em preto absoluto, dentro da janela
    que decide o scroll. Aqui o fundo pousa em ~30/255: escuro o bastante pra não competir com o
    card e claro o bastante pra ler como cenário em vez de buraco. Sem medida, -0,20."""
    if lum_mediana is None:
        return -0.20
    return max(-0.40, min(0.16, (ALVO_BG_CHEIO - lum_mediana) / 255.0))


def bg_offset(src, cfg):
    lum = luminancia_mediana_fonte(src, float(cfg.get("start", 0) or 0))
    off = offset_fundo(lum)
    if lum is not None:
        print(f"  [fundo cheio] {os.path.basename(src)}: fonte em {lum:.0f}/255, "
              f"offset {off:+.3f} (alvo {ALVO_BG_CHEIO:.0f})", flush=True)
    return off
