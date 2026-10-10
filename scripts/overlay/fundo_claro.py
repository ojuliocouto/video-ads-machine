"""Tinta invertida onde o fundo é claro (28/08/2026).

A legenda é BRANCA. O contraste WCAG de tinta branca contra um fundo de luminância L cruza 4,5:1 (o
piso de legibilidade) exatamente em L = 119/255. Acima disso ela precisa de placa; abaixo, lê
sozinha, e placa só sujaria o visual dos trechos escuros. O primeiro palpite foi 150, de cabeça, e o
teste derrubou: em 150 o contraste já é 2,96:1, ou seja o limiar "seguro" deixava passar fundo que
APAGA a legenda. Números do quadro entregue de um build de referência, no MESMO anúncio: 1,52:1 sobre
o mockup branco, 11,68:1 sobre o fundo escuro, 14,28:1 sobre a camiseta preta.

Mudar a legenda de posição não resolve: o perfil do quadro inteiro daquele trecho não tem faixa acima
de 3,6:1 fora da zona morta da UI. A saída é INVERTER a tinta (escura em vez de branca), que resolve
sem tarja (vetada em 19/08) e sem engrossar contorno (deixa a letra oca sobre branco).

Vale no split também: a legenda do split pousa sobre o INSERT (a costura fica em y 1030-1105 e o
painel de cima vai até 1150). Quem mostrou foi o gate de contraste no arquivo entregue: 57 de 120
faixas abaixo do piso, quase todas na costura.

POR INSTANTE, NÃO POR ARQUIVO. Classificar o insert inteiro por UM quadro apareceu como legenda
ESCURA sobre fundo ESCURO (tinta 0,005 e fundo 0,000): gravação de tela que abre numa página branca
rola para uma área escura no meio do mesmo insert. A decisão sai no instante de cada grupo.
"""
import json
import subprocess
import tempfile
from pathlib import Path

from caminhos import V1
from overlay.layout_texto import FAIXA_LEGENDA, classe_do_grupo

LIMIAR_FUNDO_CLARO = 119

_CACHE_FUNDO = {}

# --- W5.X: a tinta pelo fundo LOCAL, com as duas camadas da legenda acima de 4,5:1 ---------------------------------
# O render real da W5.A pôs a camada APAGADA do karaokê a 3,1:1 sobre o borrado de um insert (5,64 s) e a apagada
# da tinta invertida a 3,05 e 1,32:1 na costura de um split (9,21 s). O limiar de 119 na MEDIANA da faixa protegia
# só a camada acesa e só contra o fundo típico. A decisão agora usa o fundo CRÍTICO da caixa do texto (o percentil 90
# para a tinta clara, o 10 para a escura: a parte do fundo que apaga a letra) e as DUAS camadas, com folga.
META = 5.0                    # 4,5:1 com 10% de folga (sombra, compressão, a medida do gate no anel)
ACESA_CLARA, ACESA_ESCURA = 241, 19         # #F5EFE6 e #12141A, em cinza
APAGADA_CLARA_ALFA = 0.80                   # legenda.css: rgba(245,239,230,.80) (era .70: 3,6:1 sobre a placa, W7.Z)
APAGADA_ESCURA_ALFA = 0.75                  # legenda.css: rgba(18,20,26,.75) (era .62: 1,32:1 no v1)
PLACA_ALFA = 0.88                           # legenda.css: rgba(8,9,14,.88) (era .82; o gancho segue em .82 no hook.css)
PLACA_COR = 9
CAIXA_X = (130, 950)                        # a largura útil da legenda (o recuo do .cgrp)
FAIXA_HOOK = {"9x16": (880, 1190)}          # tinta do gancho medida no render da W5.A (y 910 a 1165)
CAIXA_X_HOOK = (160, 920)
LIMIAR_HOOK_P90 = LIMIAR_FUNDO_CLARO        # acima disso no p90, o branco fino do gancho apaga (4,1:1 no v1)


# --- W7.Z: a cor do DESTAQUE (palavra de ênfase) também se decide pelo fundo local ---------------------------------------
# A terracota (#E87D4E, luminância 0,32) sobre a camisa laranja do avatar media 1,01:1, e a camada apagada dela (alfa .62)
# não passava de 4,5:1 nem sobre fundo escuro. Duas cores, as duas camadas (acesa e apagada do karaokê) em cada decisão,
# com a mesma folga (META) da tinta: a MARCA (terracota; sobre tinta invertida, a terracota escura), a alternativa CLARA
# (amarelo) e, se nenhuma passa, a placa escura.
KW_MARCA, KW_MARCA_ALFA = (232, 125, 78), 0.88          # legenda.css: #E87D4E e rgba(232,125,78,.88) (era .62: 3:1 até sobre fundo escuro)
KW_ESCURA, KW_ESCURA_ALFA = (178, 67, 26), 0.75         # legenda.css: #B2431A e rgba(178,67,26,.75) (sobre tinta invertida)
KW_ALT, KW_ALT_ALFA = (255, 209, 102), 0.80             # legenda.css: #FFD166 e rgba(255,209,102,.80)


class Tinta(str):
    """A tinta ("clara", "invertida" ou "placa") com a cor do destaque que combina com ela em `.enfase` ("marca" ou
    "clara"; None sem destaque). É uma `str`: quem compara com "placa" não nota a diferença."""

    def __new__(cls, valor, enfase=None):
        obj = super().__new__(cls, valor)
        obj.enfase = enfase
        return obj


def _lum(v):
    c = float(v) / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _razao(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def camada_clara(fundo, apagada=True):
    """O cinza que a tinta clara vira sobre `fundo` (a apagada é translúcida)."""
    return ACESA_CLARA * APAGADA_CLARA_ALFA + fundo * (1 - APAGADA_CLARA_ALFA) if apagada else ACESA_CLARA


def camada_escura(fundo, apagada=True):
    return ACESA_ESCURA * APAGADA_ESCURA_ALFA + fundo * (1 - APAGADA_ESCURA_ALFA) if apagada else ACESA_ESCURA


def sob_placa(fundo):
    """O cinza da placa sobre `fundo`."""
    return PLACA_COR * PLACA_ALFA + fundo * (1 - PLACA_ALFA)


def _lum_rgb(rgb):
    return 0.2126 * _lum(rgb[0]) + 0.7152 * _lum(rgb[1]) + 0.0722 * _lum(rgb[2])


def _razao_cor(rgb, fundo):
    """Contraste WCAG de uma cor RGB contra um fundo em cinza (0 a 255)."""
    a, b = _lum_rgb(rgb), _lum(fundo)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def _camadas_ok(cor, alfa_apagada, fundos):
    """As duas camadas de uma cor de destaque (acesa e apagada, esta misturada com o fundo) passam de META contra cada
    fundo da lista. Num fundo da mesma luminância da cor a razão cai para 1 e a cor não passa (o 1,01:1 da prova)."""
    for f in fundos:
        apagada = tuple(c * alfa_apagada + f * (1 - alfa_apagada) for c in cor)
        if _razao_cor(cor, f) < META or _razao_cor(apagada, f) < META:
            return False
    return True


def decidir_enfase(tinta, p10, p90):
    """A cor do destaque para uma tinta e um fundo (p10, p90): "marca" (a terracota; com a tinta invertida, a terracota
    escura), "clara" (o amarelo) ou None quando nenhuma das duas passa (quem chama sobe a tinta para a placa).
    O fundo crítico é a faixa inteira entre p10 e p90 (uma cor de meio-tom some em qualquer fundo perto dela); na placa,
    a placa escura sobre os dois extremos."""
    fundos = (sob_placa(p10), sob_placa(p90)) if tinta == "placa" else (p10, p90)
    marca, alfa_marca = (KW_ESCURA, KW_ESCURA_ALFA) if tinta == "invertida" else (KW_MARCA, KW_MARCA_ALFA)
    if _camadas_ok(marca, alfa_marca, fundos):
        return "marca"
    if tinta != "invertida" and _camadas_ok(KW_ALT, KW_ALT_ALFA, fundos):
        return "clara"
    return None


def decidir_tinta(p10, p90, kw=False):
    """"clara", "invertida" ou "placa" para o fundo de percentis (p10, p90), em cinza 0 a 255.

    Com `kw` (o grupo tem palavra de ênfase) a decisão também passa pelo destaque (W7.Z): a tinta só fica se a cor do
    destaque lê nela; senão sobe para a placa. O resultado é uma `Tinta` que leva a cor do destaque em `.enfase`."""
    if min(_razao(camada_clara(p90, True), p90), _razao(camada_clara(p90, False), p90)) >= META:
        tinta = "clara"
    elif min(_razao(camada_escura(p10, True), p10), _razao(camada_escura(p10, False), p10)) >= META:
        tinta = "invertida"
    else:
        tinta = "placa"
    if not kw:
        return tinta
    enfase = decidir_enfase(tinta, p10, p90)
    if enfase is None and tinta != "placa":
        tinta = "placa"
        enfase = decidir_enfase(tinta, p10, p90)
    return Tinta(tinta, enfase)


def _percentis_banda(video, t, y0, y1, x0=CAIXA_X[0], x1=CAIXA_X[1]):
    """(p10, p90) da luminância (0 a 255) da caixa [x0, x1) x [y0, y1) do vídeo no instante `t`; None sem quadro."""
    try:
        with tempfile.TemporaryDirectory() as td:
            q = str(Path(td) / "b.pgm")
            w, h = max(x1 - x0, 2), max(y1 - y0, 2)
            r = subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-ss", f"{max(t, 0):.3f}", "-i", str(video), "-frames:v", "1",
                 "-vf", f"crop={w}:{h}:{x0}:{y0},format=gray,scale={max(2, w // 4)}:{max(2, h // 4)}", q],
                capture_output=True, text=True)
            if r.returncode != 0 or not Path(q).exists():
                return None
            dados = Path(q).read_bytes()
            corte, campos = 0, 0
            while campos < 4 and corte < len(dados):
                if dados[corte:corte + 1].isspace():
                    campos += 1
                corte += 1
            px = sorted(dados[corte:])
            if not px:
                return None
            return px[int(0.10 * (len(px) - 1))], px[int(0.90 * (len(px) - 1))]
    except Exception:
        return None


def _tinta_dos_percentis(percentis, kw=False):
    """A tinta ("clara", "invertida" ou "placa") para as medidas (p10, p90) de um ou mais instantes, pelo pior fundo
    deles (o maior p90 e o menor p10). None sem medida. É a REGRA da tinta: o build (`tinta_footage`, no instante de
    cada grupo) e a prancha (`decisao_do_quadro`, num quadro) passam por aqui."""
    ps = [x for x in percentis if x is not None]
    if not ps:
        return None
    return decidir_tinta(min(p[0] for p in ps), max(p[1] for p in ps), kw)


def _gancho_pede_placa(p90s):
    """A REGRA da placa do gancho: o p90 do fundo atrás dele passa de LIMIAR_HOOK_P90 em algum instante medido."""
    return bool(p90s) and max(p90s) > LIMIAR_HOOK_P90


def tinta_footage(video, ini, fim, classe, kw=False):
    """A tinta do grupo ("clara", "invertida" ou "placa") medida na footage, em 3 instantes dentro dele, com o pior
    fundo dos três (o maior p90 e o menor p10). None sem medida. `kw`: o grupo tem palavra de ênfase e a tinta leva a cor
    do destaque (`Tinta.enfase`)."""
    y0, y1 = FAIXA_LEGENDA.get(classe, FAIXA_LEGENDA["padrao"])
    return _tinta_dos_percentis([_percentis_banda(video, ini + (fim - ini) * f, y0, y1) for f in (0.2, 0.5, 0.8)], kw)


def hook_pede_placa(video, a0, hook_gone, formato="9x16"):
    """True se a footage atrás do gancho é clara em algum instante da janela dele (relógio do overlay, t - a0 na
    footage): o branco fino sobre o scrim não passa e o gancho ganha placa. Formato sem faixa medida: False."""
    faixa = FAIXA_HOOK.get(formato)
    if not faixa:
        return False
    fim = max(0.0, float(hook_gone) - float(a0 or 0.0))
    p90s = []
    for k in range(6):
        p = _percentis_banda(video, fim * k / 5.0, faixa[0], faixa[1], CAIXA_X_HOOK[0], CAIXA_X_HOOK[1])
        if p is not None:
            p90s.append(p[1])
    return _gancho_pede_placa(p90s)


def decisao_do_quadro(imagem, classe="padrao", formato="9x16", kw=False):
    """A decisão do overlay para UM quadro de footage (um PNG ou um vídeo, lido no instante 0):
    {"legenda": "clara" | "invertida" | "placa" | None, "gancho": "placa" | "fino"}.

    É a função que a PRANCHA de direção chama para dizer o que o motor faz naquele fundo: a mesma regra de
    `tinta_footage` (legenda) e `hook_pede_placa` (gancho), aplicadas a um quadro só. Uma regra, dois chamadores:
    a prancha nunca desenha legenda ou gancho por uma regra própria."""
    y0, y1 = FAIXA_LEGENDA.get(classe, FAIXA_LEGENDA["padrao"])
    legenda = _tinta_dos_percentis([_percentis_banda(imagem, 0.0, y0, y1)], kw)
    faixa = FAIXA_HOOK.get(formato)
    p90s = []
    if faixa:
        p = _percentis_banda(imagem, 0.0, faixa[0], faixa[1], CAIXA_X_HOOK[0], CAIXA_X_HOOK[1])
        if p is not None:
            p90s.append(p[1])
    return {"legenda": legenda, "gancho": "placa" if _gancho_pede_placa(p90s) else "fino"}


def _mediana_banda(video, t, y0, y1):
    """Mediana de luminância (0-255) de uma faixa horizontal do vídeo, no instante `t`.

    Reduz a faixa antes de medir: o que importa é o tom que a MAIORIA da área tem, que é contra o que
    a letra compete, não o pixel individual. None quando não dá para extrair o quadro.
    """
    try:
        with tempfile.TemporaryDirectory() as td:
            q = str(Path(td) / "b.pgm")
            r = subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-ss", f"{max(t, 0):.3f}", "-i", str(video),
                 "-frames:v", "1",
                 "-vf", f"crop=1080:{max(y1 - y0, 2)}:0:{y0},format=gray,scale=128:32", q],
                capture_output=True, text=True)
            if r.returncode != 0 or not Path(q).exists():
                return None
            dados = Path(q).read_bytes()
            corte, campos = 0, 0
            while campos < 4 and corte < len(dados):
                if dados[corte:corte + 1].isspace():
                    campos += 1
                corte += 1
            px = sorted(dados[corte:])
            return px[len(px) // 2] if px else None
    except Exception:
        return None


def fundo_claro_footage(video, ini, fim, classe):
    """True quando a footage já renderizada é clara na faixa daquela legenda; None sem medida.

    Mede na FOOTAGE, não no asset: medir a mediana do arquivo-fonte inteiro errou nas duas direções
    (tinta branca sobre fundo 0,524 em t=15,5 s e tinta preta sobre fundo 0,013 em t=25,5 s), porque
    o painel mostra um RECORTE do asset, com escala e moldura por cima. A footage é determinística,
    então a do build anterior vale. Três amostras dentro do grupo: perto de um corte uma amostra
    sozinha pode cair no plano vizinho, e a mediana das três não se deixa levar por isso.
    """
    y0, y1 = FAIXA_LEGENDA.get(classe, FAIXA_LEGENDA["padrao"])
    vals = []
    for f in (0.25, 0.5, 0.75):
        v = _mediana_banda(video, ini + (fim - ini) * f, y0, y1)
        if v is not None:
            vals.append(v)
    if not vals:
        return None
    vals.sort()
    return vals[len(vals) // 2] >= LIMIAR_FUNDO_CLARO


def fundo_claro(src, start=0.0):
    """True quando o insert é claro o bastante para apagar a legenda branca.

    Mede a MEDIANA de um quadro da fonte, não a média: asset bimodal (fundo escuro com uma área de
    página clara) engana a média (um asset de média 64 e mediana 33). Falha de medição devolve False
    de propósito: sem número, não inventa placa. Cacheado por (arquivo, start).
    """
    chave = (src, round(float(start or 0), 2))
    if chave in _CACHE_FUNDO:
        return _CACHE_FUNDO[chave]
    val = False
    try:
        with tempfile.TemporaryDirectory() as td:
            q = str(Path(td) / "l.pgm")
            r = subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-ss", str(float(start or 0) + 0.5),
                 "-i", str(src), "-frames:v", "1",
                 "-vf", "format=gray,scale=64:64", q],
                capture_output=True, text=True)
            if r.returncode == 0 and Path(q).exists():
                dados = Path(q).read_bytes()
                # PGM binário: 3 campos de cabeçalho antes dos pixels
                corte, campos = 0, 0
                while campos < 4 and corte < len(dados):
                    if dados[corte:corte + 1].isspace():
                        campos += 1
                    corte += 1
                px = sorted(dados[corte:])
                if px:
                    med = px[len(px) // 2]
                    val = med >= LIMIAR_FUNDO_CLARO
    except Exception:
        val = False
    _CACHE_FUNDO[chave] = val
    return val


def a0_da_footage(ritmo_json):
    """O a0 da footage (início do 1º plano, no relógio do avatar) lido do `_ritmo.json` que ela gravou; None se o
    arquivo não existe ou não serve."""
    try:
        segs = json.loads(Path(ritmo_json).read_text(encoding="utf-8")).get("segs") or []
        return float(segs[0]["s"])
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
        return None


def marcar_grupos_claros(groups, ad, look, mapa_insert, a0=None):
    """Marca `claro` nos grupos de legenda sobre fundo claro, no instante em que cada um está na tela.

    Caminho bom: mede a footage renderizada, na faixa exata da classe do grupo. Primeira rodada de um
    anúncio novo (sem footage): cai no arquivo-fonte, no meio do grupo, com o tempo da fonte
    convertido por start e velocidade do insert. É aproximado (o painel mostra um recorte do asset),
    e o build seguinte converge para o caminho de cima.

    O RELÓGIO DA FOOTAGE (W3.X M4). O overlay é deslocado de -a0 no composite: o instante t do grupo é o instante
    t - a0 da footage. Amostrar em t media outro quadro (0,62 s depois no fixture). O `a0` vem do chamador (a
    timeline) ou do `_ritmo.json` que a footage gravou ao lado do mp4; sem nenhum dos dois a footage NÃO é medida
    (seria no relógio errado) e o caminho é o do arquivo-fonte.
    """
    _fmp4 = V1 / "output" / f"{ad}_{look}_footage_1x.mp4"
    if _fmp4.exists() and a0 is None:
        a0 = a0_da_footage(_fmp4.with_name(_fmp4.stem + "_ritmo.json"))
        if a0 is None:
            print(f"   [fundo claro] footage {_fmp4.name} sem a0 conhecido (nem timeline nem _ritmo.json): "
                  "medindo no arquivo-fonte, nao no relogio errado", flush=True)
    if _fmp4.exists() and a0 is not None:
        n = npl = 0
        for g in groups:
            _kw = any(w.get("kw") for w in g.get("words") or [])
            _r = (tinta_footage(_fmp4, g["start"] - a0, g["end"] - a0, classe_do_grupo(g), kw=True) if _kw
                  else tinta_footage(_fmp4, g["start"] - a0, g["end"] - a0, classe_do_grupo(g)))
            if _r == "invertida":
                g["claro"] = True
                n += 1
            elif _r == "placa":
                g["placa"] = True
                npl += 1
            if _kw and getattr(_r, "enfase", None) == "clara":
                g["kw_alt"] = True
        print(f"   [fundo claro] {n} de {len(groups)} grupo(s) com tinta INVERTIDA e {npl} com PLACA, "
              f"medidos na footage ({_fmp4.name})", flush=True)
    elif mapa_insert:
        n = 0
        for g in groups:
            _meio = (g["start"] + g["end"]) / 2.0
            _jan = next((w for w in mapa_insert if w["a"] <= _meio <= w["b"]), None)
            if not _jan:
                continue
            if classe_do_grupo(g) == "costura":
                continue       # a emenda do split tem um degradê escuro por construção: a mediana do arquivo-fonte não a vê
            _tsrc = _jan["start"] + max(0.0, _meio - _jan["s2"]) * _jan["speed"]
            if fundo_claro(_jan["file"], round(_tsrc, 1)):
                g["claro"] = True
                n += 1
        if n:
            print(f"   [fundo claro] {n} grupo(s) com tinta INVERTIDA pelo ARQUIVO-FONTE "
                  f"(sem footage ainda; o proximo build mede na footage)", flush=True)
