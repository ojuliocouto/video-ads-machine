#!/usr/bin/env python3
"""CONTRASTE DE TODO TEXTO NA TELA contra o fundo LOCAL, medido no quadro composto (W5.X).

O INVARIANTE (um só, para hook, legenda inclusive a camada apagada do karaokê, lettering e CTA):

    em toda amostra (PASSO_S = 0,2 s: 5 por segundo, acima do mínimo de 4), cada pedaço de texto na tela tem
    contraste WCAG >= 4,5:1 entre a TINTA (o miolo da letra) e o FUNDO LOCAL (o anel de pixels logo fora da letra),
    os dois lidos no QUADRO ENTREGUE. Só fica de fora o texto que está a menos de TRANSICAO_S de entrar ou de sair
    da tela (a dissolução de entrada ou de saída), e só esse.

Nasceu de dois defeitos que 28 gates aprovaram no primeiro render ponta a ponta (W5.A): o gancho em branco fino sobre
um insert de navegador CLARO (0 a 2,1 s) e a legenda invertida cuja camada apagada (0,62 de opacidade) virou cinza
sobre o insert claro (9,21 s). O gate antigo de contraste não via nenhum dos dois, por quatro causas medidas:

  1. tinta = alfa >= 250: a camada apagada do karaokê (alfa 158 a 178) nunca era tinta;
  2. fundo = a MÉDIA da faixa horizontal inteira onde o alfa é zero: longe da letra (não local), e quando um scrim
     cobre a largura toda (o gancho) não sobra pixel de alfa zero, a faixa é PULADA em silêncio: o gancho nunca foi
     medido;
  3. aprovação pela MEDIANA (reprovava só com mediana abaixo do piso ou mais de 30% das faixas): 3 faixas a 2,0 e
     3,0:1 sobre o insert claro saíram como AVISO e o gate passou;
  4. uma amostra a cada 0,5 s e corte no CTA (`--ate`): o CTA nunca era medido.

## Como mede

O overlay (MOV com alfa) diz onde está o TEXTO; o quadro entregue diz o que o espectador vê.

  - texto: pixel do overlay com alfa >= ALFA_TINTA (0,59: a camada apagada entra) que é ESTRUTURA FINA, e não um
    scrim, um dim ou uma placa (lisos e largos). Estrutura fina = top-hat de JANELA_PX: o alfa acima da abertura do
    alfa (texto sobre nada ou sobre um scrim), ou a luminância própria do overlay acima da abertura dela (texto claro
    sobre a pílula ou a placa), ou, dentro de uma caixa opaca e clara, a luminância abaixo do fechamento (texto
    escuro na caixa nativa ou no marcador). Contorno e sombra perto da letra fazem parte do texto;
  - tinta: a CRISTA da letra, os pixels mais longe da borda dela (60% ou mais da maior distância, em cada
    ladrilho). Não supõe cor: o contorno mora na borda e fica de fora, sobra o preenchimento, claro ou escuro, da
    haste de 4 px do sobretítulo à de 48 px do lettering gigante. Uma erosão fixa de 4 px apagava a letra fina e,
    na ponta de uma descendente, sobrava só contorno;
  - fundo local: o anel de ANEL_PX fora do texto, sem nenhum outro texto dentro. O scrim do gancho e a sombra da
    letra estão no anel (são o que fica atrás dela); o contorno não está (contorno de 3 px sozinho não segura letra
    clara sobre página branca: a letra fica oca);
  - por ladrilho: cada palavra é medida em quadrados de LADRILHO_PX (meia palavra sobre o claro reprova, mesmo que
    a outra metade esteja sobre o escuro);
  - transição: o pedaço que reprova numa amostra e que, TRANSICAO_S antes ou depois, não está mais na tela (menos de
    metade dos pixels) está entrando ou saindo: é a dissolução, fica de fora e é contado à parte.

A TROCA SECA E A DESSINCRONIA DE UM QUADRO (W7.Z): o overlay e o quadro entregue não se alinham ao quadro exato (com a
aceleração de 1,35 o quadro entregue vem de um quadro do overlay a até 1/30 s do que o relógio calcula). Com a legenda em
fade isso se escondia na dissolução; com a troca seca (um grupo substitui o outro no mesmo quadro) a amostra que cai no
quadro da troca mede o texto NOVO do overlay contra o quadro entregue que ainda mostra o VELHO (1,0:1 na prova, com o vídeo
limpo nos quadros vizinhos). O pedaço que reprova só reprova de verdade se também não lê com o overlay UM quadro antes nem
UM quadro depois (`le_com_quadro_vizinho`); lido num dos vizinhos, é troca seca e entra em `transicoes` (`troca_seca`).

O relógio: o quadro de `-ss t` no entregue mostra o instante `(t - deslocamento) * aceleração + a0` do overlay, com
`deslocamento` o start_time do fluxo de vídeo menos o do arquivo (ver `info_video`).
"""
import json
import subprocess
import sys

try:
    import numpy as np
    from scipy import ndimage as ndi
except ImportError as _e:       # dependência que o aluno ainda não instalou: mensagem, não traceback
    sys.exit("Falta uma dependência Python deste gate (%s). Instale com:\n"
             "  pip install -r scripts/gates/requirements.txt" % _e.name)

PISO = 4.5                 # WCAG AA para texto; o mesmo número que decide o halo da legenda no motor
PASSO_S = 0.2              # 5 amostras por segundo (o invariante pede pelo menos 4)
ALFA_TINTA = 100           # 0,39 de opacidade: a camada apagada (0,62 a 0,70) e o texto se dissolvendo são tinta
TOPHAT_ALFA = 40           # texto sobre nada ou sobre scrim: alfa acima da vizinhança lisa
TOPHAT_COR = 60            # texto claro sobre placa, ou escuro dentro de caixa clara: luminância própria do overlay
CAIXA_ALFA = 250           # caixa opaca (caixa nativa, marcador): abertura do alfa
CAIXA_CLARA = 120          # e clara (o texto escuro dentro dela é tinta; o vão escuro entre letras claras não)
JANELA_PX = 71             # maior que a haste mais grossa (Anton 230 px: ~48 px) e menor que scrim, dim e placa
ANEL_PX = (4, 12)          # o fundo local: de 4 a 12 px fora do preenchimento (o contorno de 3 px fica de fora)
POLARIDADE_DELTA = 20      # claro/escuro em relação à luminância própria do anel (a terracota da ênfase: 144 x 110)
PREENCHIMENTO_MIN = 20     # pixels para uma das partes (clara ou escura) existir
PERCENTIL_FUNDO = 90       # o fundo crítico: o percentil do anel do lado que apaga a letra (ver _fundo_critico)
LADRILHO_PX = 96           # meia palavra sobre o claro tem que aparecer: mede-se por quadrado, não pela palavra
NUCLEO_MIN = 30            # pixels de crista num ladrilho para ele valer
FRACAO_CRISTA = 0.6        # crista: o pixel a 60% ou mais da maior distância à borda da letra (no ladrilho)
ESPESSURA_MIN = 3.0        # px: traço mais fino que isso é filete (borda de pílula), não letra
INTRINSECO_MIN = 70        # letra difere do anel NO PRÓPRIO overlay, na luminância (a quina da pílula: 49)...
INTRINSECO_ALFA_MIN = 40   # ...ou na opacidade; forma da cor e da opacidade do entorno não é letra
EMBUTIDA_MAX = 0.2         # anel com mais que isso na opacidade da forma: é ponta de placa, não letra
ANEL_MIN = 40              # pixels de anel num ladrilho para ele valer
AREA_MIN = 150             # componente menor que isso é pingo solto, não texto
TRANSICAO_S = 0.15         # entrada ou saída: menos que isso até o texto sumir (ou depois de nascer)
PRESENCA_MIN = 0.5         # fração dos pixels do pedaço que precisa estar lá para ele "estar na tela"
TROCA_ALFA = 96            # mudança de opacidade que é troca de texto (o preenchimento do karaokê muda 77)
TROCA_FRACAO = 0.3         # fração do pedaço que muda assim: troca (contorno e sombra das duas se sobrepõem: 0,48)


# --- leitura ------------------------------------------------------------------------------------------------

def _ffprobe_json(caminho, entradas, fluxo=True):
    cmd = ["ffprobe", "-v", "error"] + (["-select_streams", "v:0"] if fluxo else []) + [
        "-show_entries", entradas, "-of", "json", str(caminho)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise OSError("não consegui ler %s: %s" % (caminho, r.stderr.strip()[-200:]))
    return json.loads(r.stdout or "{}")


def _f(v, padrao=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return padrao


def info_video(caminho):
    """(largura, altura, duração, deslocamento) de um arquivo.

    `deslocamento` = start_time do fluxo de vídeo menos o start_time do arquivo. O `-ss` do ffmpeg conta a partir
    do início do ARQUIVO (o menor start_time entre os fluxos), e o conteúdo do vídeo começa no start_time do fluxo
    dele: o quadro de `-ss t` é o quadro `t - deslocamento` do conteúdo. No entregue do e2e o vídeo começa em 0,066
    e o áudio em 0,045: 0,021 s."""
    d = _ffprobe_json(caminho, "stream=width,height,start_time:format=duration,start_time", fluxo=False)
    v = next((s for s in d.get("streams", []) if "width" in s), None)
    if v is None:
        raise OSError("%s não tem fluxo de vídeo" % caminho)
    fmt = d.get("format") or {}
    return (int(v["width"]), int(v["height"]), _f(fmt.get("duration")),
            _f(v.get("start_time")) - _f(fmt.get("start_time")))


def ler_quadro(caminho, t, larg, alt, canais=3):
    """Um quadro por SEEK (nunca fluxo contínuo: dois fluxos derivam um contra o outro), em rgb24 ou rgba."""
    fmt = "rgba" if canais == 4 else "rgb24"
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-ss", "%.4f" % max(0.0, t), "-i", str(caminho),
                        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", fmt, "-"], capture_output=True)
    n = larg * alt * canais
    if len(r.stdout) < n:
        return None
    return np.frombuffer(r.stdout[:n], dtype=np.uint8).reshape(alt, larg, canais)


# --- luminância e contraste ------------------------------------------------------------------------------------

def luminancia_relativa(rgb):
    """Luminância relativa WCAG (0 a 1) de um array uint8 [..., 3]."""
    c = rgb.astype(np.float64) / 255.0
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722


def razao(l1, l2):
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)


# --- onde está o texto -------------------------------------------------------------------------------------------

def _faixa_de_linhas(cand, margem):
    linhas = np.flatnonzero(cand.any(axis=1))
    if linhas.size == 0:
        return None
    return max(0, int(linhas[0]) - margem), min(cand.shape[0], int(linhas[-1]) + margem + 1)


def mascara_texto(ov):
    """Máscara booleana do TEXTO num quadro RGBA do overlay (ver o docstring do módulo)."""
    a = ov[..., 3]
    cand = a >= ALFA_TINTA
    m = np.zeros(a.shape, dtype=bool)
    faixa = _faixa_de_linhas(cand, JANELA_PX)
    if faixa is None:
        return m
    y0, y1 = faixa
    af = a[y0:y1].astype(np.float32)
    rgb = ov[y0:y1, :, :3].astype(np.float32)
    luma = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    k = af / 255.0
    yov = k * luma + (1.0 - k) * 128.0            # a cor própria do overlay, sobre cinza médio
    tam = (JANELA_PX, JANELA_PX)
    ab_a = ndi.grey_opening(af, size=tam)
    ab_y = ndi.grey_opening(yov, size=tam)
    fino_alfa = (af - ab_a) >= TOPHAT_ALFA
    claro_sobre_placa = (yov - ab_y) >= TOPHAT_COR
    caixa_clara = (ab_a >= CAIXA_ALFA) & (ab_y >= CAIXA_CLARA)
    escuro_na_caixa = caixa_clara & ((ndi.grey_closing(yov, size=tam) - yov) >= TOPHAT_COR)
    m[y0:y1] = cand[y0:y1] & (fino_alfa | claro_sobre_placa | escuro_na_caixa)
    return m


def componentes(mascara):
    """[(fatia, máscara local)] das palavras: letras ligadas na horizontal (vão de letra) viram um pedaço só."""
    if not mascara.any():
        return []
    ligada = ndi.binary_dilation(mascara, structure=np.ones((1, 13), dtype=bool))
    rot, n = ndi.label(ligada)
    saida = []
    for i, fat in enumerate(ndi.find_objects(rot), start=1):
        if fat is None:
            continue
        local = mascara[fat] & (rot[fat] == i)
        if local.sum() >= AREA_MIN:
            saida.append((fat, local))
    return saida


def _fundo_critico(tinta, fundo):
    """O fundo contra o qual a letra se mede: a parte do anel que dá o MENOR contraste (a orientação da WCAG para
    texto sobre imagem), em percentil para não depender de um pixel de compressão. Tinta mais clara que o anel:
    o percentil claro dele (a página branca que encosta na letra branca); mais escura: o percentil escuro."""
    med = float(np.median(fundo))
    if tinta >= med:
        return float(np.percentile(fundo, PERCENTIL_FUNDO))
    return float(np.percentile(fundo, 100 - PERCENTIL_FUNDO))


def _luma_propria(ov):
    """A luminância (0 a 255) do próprio overlay, composto sobre cinza médio: o que a tinta é, sem a imagem."""
    k = ov[..., 3].astype(np.float32) / 255.0
    rgb = ov[..., :3].astype(np.float32)
    luma = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    return k * luma + (1.0 - k) * 128.0


def _e_letra(dentro, anel, yov, alfa):
    """A forma achada é letra, e não um pedaço de placa? Letra difere do que está em volta NO PRÓPRIO overlay: na
    luminância (texto claro na pílula escura) ou, pela opacidade, sem ser a ponta de uma forma maior da mesma
    opacidade. A quina arredondada da pílula sobre o scrim difere do scrim na opacidade (214 contra 108), mas o anel
    dela encosta no resto da pílula, de opacidade igual: é placa."""
    crista = dentro >= max(1.0, FRACAO_CRISTA * float(dentro.max()))
    if abs(float(np.median(yov[crista])) - float(np.median(yov[anel]))) >= INTRINSECO_MIN:
        return True
    a_crista = float(np.median(alfa[crista]))
    if a_crista - float(np.median(alfa[anel])) < INTRINSECO_ALFA_MIN:
        return False
    return float(np.mean(alfa[anel] >= a_crista - 20)) < EMBUTIDA_MAX


# --- a medida de um quadro ----------------------------------------------------------------------------------------

def _preenchimento(comp, yov, yanel):
    """O PREENCHIMENTO da letra dentro do pedaço achado (que pode trazer junto o contorno e a sombra densa).

    Separa o pedaço pela luminância própria do overlay em relação ao anel (a parte mais clara e a mais escura) e
    fica com a MAIOR: o preenchimento é a letra inteira, o contorno é um anel de 3 px e a sombra densa só o vão.
    Medido no v1: "Agora" (legenda) 6.513 px claros contra 3.855 escuros; tinta invertida 10.372 escuros contra
    7.422 claros; "TOQUE" (sobretítulo do CTA com sombra de 0,95) 1.313 contra 283. Pelos critérios "quem está
    cercado" e "quem faz a borda de fora", a sombra que enche o vão entre as letras virava o preenchimento e o "EM"
    de "TOQUE EM" media 1,05:1 numa letra que lê a 14:1."""
    claro = comp & (yov > yanel + POLARIDADE_DELTA)
    escuro = comp & (yov < yanel - POLARIDADE_DELTA)
    nc, ne = int(claro.sum()), int(escuro.sum())
    if nc < PREENCHIMENTO_MIN and ne < PREENCHIMENTO_MIN:
        return None
    return claro if nc >= ne else escuro


def _pedacos(ov, masc, yov):
    """[(caixa (y0, y1, x0, x1), preenchimento local, máscara do pedaço local)] dos pedaços que são letra."""
    alt, larg = masc.shape
    d1 = ANEL_PX[1]
    saida = []
    for fat, local in componentes(masc):
        ys, xs = fat
        y0, y1 = max(0, ys.start - d1 - 1), min(alt, ys.stop + d1 + 1)
        x0, x1 = max(0, xs.start - d1 - 1), min(larg, xs.stop + d1 + 1)
        comp = np.zeros((y1 - y0, x1 - x0), dtype=bool)
        comp[ys.start - y0:ys.stop - y0, xs.start - x0:xs.stop - x0] = local
        dentro = ndi.distance_transform_edt(comp)
        if dentro.max() < ESPESSURA_MIN / 2.0:   # filete (borda de pílula, traço de 1 a 2 px): não é letra
            continue
        fora = ndi.distance_transform_edt(~comp)
        anel = (fora > 2) & (fora <= d1) & ~masc[y0:y1, x0:x1]
        if anel.sum() < ANEL_MIN:
            continue
        yov_c = yov[y0:y1, x0:x1]
        if not _e_letra(dentro, anel, yov_c, ov[y0:y1, x0:x1, 3].astype(np.float32)):
            continue
        preench = _preenchimento(comp, yov_c, float(np.median(yov_c[anel])))
        if preench is None:
            continue
        saida.append(((y0, y1, x0, x1), preench, comp))
    return saida


def medir_quadro(ov, quadro, piso=PISO):
    """Mede cada pedaço de texto do quadro: [{x0, y0, x1, y1, tinta, fundo, razao, ok, espessura, area}].

    `ov` é o quadro RGBA do overlay; `quadro`, o RGB entregue no mesmo instante. Um pedaço é uma palavra, e a razão
    dele é a do PIOR ladrilho. Em cada ladrilho a tinta é a CRISTA do preenchimento (os pixels mais longe da borda
    dele) e o fundo é o fundo crítico do anel de ANEL_PX em volta do preenchimento: o contorno de 3 px fica de fora
    (ele não segura letra clara sobre página branca), a sombra e o scrim ficam dentro (é o que está atrás da letra)."""
    alt, larg = quadro.shape[:2]
    masc = mascara_texto(ov)
    if not masc.any():
        return []
    yov = _luma_propria(ov)
    pedacos = _pedacos(ov, masc, yov)
    if not pedacos:
        return []
    todos = np.zeros((alt, larg), dtype=bool)               # o preenchimento de TODAS as letras: nunca é fundo
    for (y0, y1, x0, x1), preench, _c in pedacos:
        todos[y0:y1, x0:x1] |= preench
    lum = luminancia_relativa(quadro)
    d0, d1 = ANEL_PX
    saida = []
    for (y0, y1, x0, x1), preench, comp in pedacos:
        dentro = ndi.distance_transform_edt(preench)
        if dentro.max() < ESPESSURA_MIN / 2.0:
            continue
        fora = ndi.distance_transform_edt(~preench)
        # LETRA, GRANDE OU PEQUENA, NUNCA É FUNDO (W7.Z): o pingo do "?" e os acentos são componentes de menos de AREA_MIN, não
        # viram pedaço e ficavam fora de `todos`; o anel da letra vizinha os contava como fundo (0,85) e o percentil 90 do anel
        # subia de 0,014 para 0,19 (18,0 s da prova: 2,97:1 numa legenda que lê a 12:1). A máscara de texto inteira sai do anel.
        anel = (fora > d0) & (fora <= d1) & ~todos[y0:y1, x0:x1] & ~masc[y0:y1, x0:x1]
        lum_c = lum[y0:y1, x0:x1]
        pior = None
        for ty in range(0, y1 - y0, LADRILHO_PX):
            for tx in range(0, x1 - x0, LADRILHO_PX):
                dl = dentro[ty:ty + LADRILHO_PX, tx:tx + LADRILHO_PX]
                dmax = float(dl.max()) if dl.size else 0.0
                if dmax < ESPESSURA_MIN / 2.0:
                    continue
                n = dl >= max(1.0, FRACAO_CRISTA * dmax)
                if n.sum() < NUCLEO_MIN:
                    continue
                ay0, ax0 = max(0, ty - d1), max(0, tx - d1)
                an = anel[ay0:ty + LADRILHO_PX + d1, ax0:tx + LADRILHO_PX + d1]
                if an.sum() < ANEL_MIN:
                    continue
                li = float(np.median(lum_c[ty:ty + LADRILHO_PX, tx:tx + LADRILHO_PX][n]))
                fundo = lum_c[ay0:ty + LADRILHO_PX + d1, ax0:tx + LADRILHO_PX + d1][an]
                lb = _fundo_critico(li, fundo)
                r = razao(li, lb)
                if pior is None or r < pior["razao"]:
                    pior = {"tx0": x0 + tx, "ty0": y0 + ty, "tinta": li, "fundo": lb, "razao": r}
        if pior is None:
            continue
        ys, xs = np.nonzero(comp)
        saida.append({"x0": int(x0 + xs.min()), "y0": int(y0 + ys.min()), "x1": int(x0 + xs.max() + 1),
                      "y1": int(y0 + ys.max() + 1), "area": int(preench.sum()),
                      "espessura": round(2.0 * float(dentro.max()), 1),
                      "tinta": round(pior["tinta"], 4), "fundo": round(pior["fundo"], 4),
                      "razao": round(pior["razao"], 2), "ladrilho": [int(pior["tx0"]), int(pior["ty0"])],
                      "ok": pior["razao"] >= piso})
    return saida


def presenca(ov, caixa):
    """Fração da máscara de texto dentro de `caixa` (x0, y0, x1, y1) num quadro do overlay: quanto do pedaço está lá."""
    x0, y0, x1, y1 = caixa
    m = mascara_texto(ov)[y0:y1, x0:x1]
    return float(m.sum())


# --- a medida do vídeo inteiro ------------------------------------------------------------------------------------

class Relogio(object):
    """Converte o `-ss` do entregue no instante do overlay: (t - deslocamento) x aceleração + a0."""

    def __init__(self, aceleracao=1.0, a0=0.0, inicio=0.0):
        self.aceleracao, self.a0, self.inicio = float(aceleracao), float(a0), float(inicio)

    def overlay(self, t):
        return max(0.0, (t - self.inicio) * self.aceleracao + self.a0)


def medir_instante(video, overlay, t, relogio, dims, piso=PISO):
    """Mede o instante `t` (pts do entregue). Devolve (pedaços, quadro do overlay) ou ([], None) sem quadro."""
    larg, alt = dims
    ov = ler_quadro(overlay, relogio.overlay(t), larg, alt, canais=4)
    if ov is None:
        return [], None
    if not (ov[..., 3] >= ALFA_TINTA).any():
        return [], ov
    q = ler_quadro(video, t, larg, alt, canais=3)
    if q is None:
        return [], ov
    return medir_quadro(ov, q, piso), ov


def em_transicao(video, overlay, t, relogio, dims, pedaco, piso=PISO, transicao_s=TRANSICAO_S):
    """True se o pedaço que reprova em `t` está ENTRANDO ou SAINDO, e só isso.

    Entrando ou saindo: num dos lados (`t - transicao_s` ou `t + transicao_s`) menos da metade dele está na tela. E do
    outro lado ele LIA: a dissolução de um texto que já era ilegível não desculpa nada (o gancho do v1 se dissolvia
    sobre a página clara depois de 1,8 s abaixo do piso). Texto que fica mais que `transicao_s` se dissolvendo também
    não é desculpado: no meio da dissolução lenta, os dois lados ainda têm o texto."""
    larg, alt = dims
    caixa = (pedaco["x0"], pedaco["y0"], pedaco["x1"], pedaco["y1"])
    x0, y0, x1, y1 = caixa

    def le_em(tt):
        pedacos, _ = medir_instante(video, overlay, tt, relogio, dims, piso)
        meus = [p for p in pedacos if min(x1, p["x1"]) > max(x0, p["x0"]) and min(y1, p["y1"]) > max(y0, p["y0"])]
        return bool(meus) and all(p["ok"] for p in meus)

    antes = ler_quadro(overlay, relogio.overlay(t - transicao_s), larg, alt, canais=4)
    depois = ler_quadro(overlay, relogio.overlay(t + transicao_s), larg, alt, canais=4)
    if antes is not None and depois is not None:
        # TROCA no mesmo lugar (a legenda nova entra antes de a velha sair): 30% ou mais do pedaço muda de
        # opacidade em mais de 96 níveis entre um lado e outro. O preenchimento do karaokê muda 77 (de .70 a 1).
        aa = antes[y0:y1, x0:x1, 3].astype(np.int16)
        ad = depois[y0:y1, x0:x1, 3].astype(np.int16)
        tinta = np.maximum(aa, ad) >= ALFA_TINTA
        if tinta.any() and float((np.abs(ad - aa)[tinta] > TROCA_ALFA).mean()) >= TROCA_FRACAO:
            return le_em(t - transicao_s) or le_em(t + transicao_s)
    agora = ler_quadro(overlay, relogio.overlay(t), larg, alt, canais=4)
    if agora is None:
        return False
    base = presenca(agora, caixa)
    if base <= 0:
        return True
    for dt in (-transicao_s, transicao_s):
        lado = ler_quadro(overlay, relogio.overlay(t + dt), larg, alt, canais=4)
        if lado is not None and presenca(lado, caixa) >= PRESENCA_MIN * base:
            continue
        # some (ou ainda não nasceu) deste lado: do outro lado ele tem que ler
        return le_em(t - dt)
    return False


QUADRO_OVERLAY_S = 1.0 / 30.0     # o quadro do overlay (a footage roda a 30 fps)


def le_com_quadro_vizinho(video, overlay, t, relogio, dims, pedaco, piso=PISO):
    """True se o pedaço que reprova em `t` lê (todos os pedaços que o tocam passam) com o overlay UM quadro antes ou UM
    quadro depois do que o relógio calcula: a dessincronia de um quadro na troca seca (ver o docstring do módulo)."""
    x0, y0, x1, y1 = pedaco["x0"], pedaco["y0"], pedaco["x1"], pedaco["y1"]
    for d in (QUADRO_OVERLAY_S, -QUADRO_OVERLAY_S):
        vizinho = Relogio(relogio.aceleracao, relogio.a0 + d, relogio.inicio)
        pedacos, _ = medir_instante(video, overlay, t, vizinho, dims, piso)
        meus = [p for p in pedacos if min(x1, p["x1"]) > max(x0, p["x0"]) and min(y1, p["y1"]) > max(y0, p["y0"])]
        if meus and all(p["ok"] for p in meus):
            return True
    return False


def medir_video(video, overlay, aceleracao, a0, passo=PASSO_S, piso=PISO, inicio=None, fim=None,
                transicao_s=TRANSICAO_S, paralelo=4):
    """Todas as amostras de `video` (de `inicio` a `fim`, no relógio do entregue) a cada `passo`.

    Devolve {"amostras": [(t, [pedaços])], "reprovas": [...], "transicoes": [...], "medidos": n}. Cada reprova e
    cada transição é um pedaço com `t`."""
    larg, alt, dur, desloc = info_video(video)
    ol, oa, _, _ = info_video(overlay)
    if (ol, oa) != (larg, alt):
        raise OSError("overlay %dx%d e vídeo %dx%d não batem" % (ol, oa, larg, alt))
    rel = Relogio(aceleracao, a0, desloc)
    t_ini = 0.0 if inicio is None else float(inicio)
    t_fim = dur if fim is None else min(dur, float(fim))
    alvos = []
    t = t_ini
    while t < t_fim - 1e-6:
        alvos.append(round(t, 4))
        t += passo
    dims = (larg, alt)

    def um(tt):
        pedacos, _ = medir_instante(video, overlay, tt, rel, dims, piso)
        return tt, pedacos

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max(1, int(paralelo))) as ex:
        amostras = list(ex.map(um, alvos))
    reprovas, transicoes, medidos = [], [], 0
    for tt, pedacos in amostras:
        for p in pedacos:
            medidos += 1
            if p["ok"]:
                continue
            item = dict(p, t=round(tt, 3))
            if em_transicao(video, overlay, tt, rel, dims, p, piso, transicao_s):
                transicoes.append(item)
            elif le_com_quadro_vizinho(video, overlay, tt, rel, dims, p, piso):
                transicoes.append(dict(item, troca_seca=True))
            else:
                reprovas.append(item)
    return {"amostras": [(round(tt, 3), p) for tt, p in amostras], "reprovas": reprovas,
            "transicoes": transicoes, "medidos": medidos, "passo_s": passo, "deslocamento_s": round(desloc, 4)}


def main(argv=None):
    """Diagnóstico: `contraste_texto.py <video> --overlay <mov> --accel 1.35 --a0 0.4 [--em 0.30 9.21]`."""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--overlay", required=True)
    ap.add_argument("--accel", type=float, default=1.0)
    ap.add_argument("--a0", type=float, default=0.0)
    ap.add_argument("--em", type=float, nargs="*", help="instantes do entregue, no pts (o -ss do ffmpeg)")
    a = ap.parse_args(argv)
    larg, alt, _dur, desloc = info_video(a.video)
    rel = Relogio(a.accel, a.a0, desloc)
    for t in a.em or []:
        pedacos, _ = medir_instante(a.video, a.overlay, t, rel, (larg, alt))
        print("t=%.2f s: %d pedaço(s)" % (t, len(pedacos)))
        for p in pedacos:
            print("   x%4d-%4d y%4d-%4d  %5.2f:1  tinta %.3f  fundo %.3f  traço %4.1f px  %s"
                  % (p["x0"], p["x1"], p["y0"], p["y1"], p["razao"], p["tinta"], p["fundo"], p["espessura"],
                     "ok" if p["ok"] else "REPROVA"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
