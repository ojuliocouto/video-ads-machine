"""O halo da legenda pelo fundo local (28/08/2026; reescrito em 10/10/2026, "Sim pros 2").

A legenda é BRANCA, sem caixa, sem faixa e sem contorno duro: legibilidade vem de um halo escuro em camadas, delicado,
que o CSS desenha (`legenda.css`). O contraste WCAG de tinta branca contra um fundo de luminância L cruza 4,5:1 (o
piso de legibilidade) exatamente em L = 119/255. Sobre fundo ESCURO o halo normal basta. Sobre fundo CLARO (um insert de
página branca na base do quadro) a legenda precisa de MAIS halo: o grupo ganha `cgrp-halo`, que adiciona camadas e
opacidade ao mesmo halo, ainda sem caixa, até a letra passar de 4,5:1 no `contraste_texto.py`. Antes a tinta invertia
(escura sobre fundo claro) ou ganhava uma placa preta atrás da frase; o dono vetou a caixa preta em 23/09 ("odiei o
estilo da legenda") e de novo em 10/10 (faixa atrás do peito), e a tinta invertida contradiz "texto branco com halo".

Números do quadro entregue de um build de referência, no MESMO anúncio: 1,52:1 sobre o mockup branco, 11,68:1 sobre
o fundo escuro, 14,28:1 sobre a camiseta preta. A posição não resolve (a base do quadro é fixa); o halo resolve.

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

# --- 10/10/2026: o halo pelo fundo LOCAL, medido no render real (o gate de contraste é a régua) ------------------------
# Medido com a legenda do repo renderizada em RGBA e passada pelo `contraste_texto.medir_quadro` sobre fundos lisos de
# 22 a 245 de cinza: o halo NORMAL (4 camadas de sombra difusa, `legenda.css`) lê 16:1 sobre 22, 5,0:1 sobre 110 e cruza 4,5:1
# perto de 118; acima disso o gate lê a letra contra o fundo claro que o halo não alcança e reprova. O halo FORTE (36 camadas
# de sombra de 8 px, `.cgrp-halo`) passa a ler a mancha escura contra o fundo: 4,3:1 sobre 116, 4,9:1 sobre 125, 17:1 sobre
# 245, e cruza 4,5:1 também perto de 118. Os dois se encontram em LIMIAR_HALO_FORTE: abaixo dele o halo normal, acima o forte.
# A conta antiga (as duas camadas do karaokê contra o p90 do fundo, WCAG) valia para a tinta invertida e a placa, que
# morreram; esta é a do gate e tem o número medido.
LIMIAR_HALO_FORTE = 118       # cinza (0 a 255) do fundo crítico da faixa da legenda: acima disso, `cgrp-halo`
META = 5.0                    # 4,5:1 com 10% de folga (sombra, compressão, a medida do gate no anel), para a cor do destaque
APAGADA_CLARA_ALFA = 0.88                   # legenda.css: rgba(245,239,230,.88) (era .70 e .80: 3,6:1 e 3,97:1, W7.Z)
CAIXA_X = (140, 940)                        # a largura útil da legenda (o recuo do .cgrp)
FAIXA_HOOK = {"9x16": (880, 1190)}          # tinta do gancho medida no render da W5.A (y 910 a 1165)
CAIXA_X_HOOK = (160, 920)
LIMIAR_HOOK_P90 = LIMIAR_FUNDO_CLARO        # acima disso no p90, o branco fino do gancho apaga (4,1:1 no v1)

# --- W7.W (A4): o fundo crítico da LEGENDA é o 1% mais crítico da faixa, não o p10/p90 -------------------------------
# Sobre a interface branca do Claude, as linhas "Web" da tabela passavam atrás das letras e a legenda saiu com tinta escura
# SEM proteção (8,6 s da prova): o p10 da faixa era 201 (papel) e as linhas, ~1% dos pixels, só aparecem no p01 (135 a 154;
# mínimo 50). Um fundo que tem estrutura clara em 1% da faixa já cruza as letras brancas: halo forte.
# O gancho NÃO usa isto: a regra dele é o p90 contra LIMIAR_HOOK_P90.
QUANTIS_LEGENDA = (0.01, 0.99)


# --- W7.Z: a cor do DESTAQUE (palavra de ênfase) também se decide pelo fundo local ---------------------------------------
# A terracota (#E87D4E, luminância 0,32) sobre a camisa laranja do avatar media 1,01:1, e a camada apagada dela (alfa .62)
# não passava de 4,5:1 nem sobre fundo escuro. Duas cores, as duas camadas (acesa e apagada do karaokê) em cada decisão,
# com a folga META: a MARCA (terracota), a alternativa CLARA (amarelo) e, se nenhuma passa, o destaque sai BRANCO.
KW_MARCA, KW_MARCA_ALFA = (232, 125, 78), 0.88          # legenda.css: #E87D4E e rgba(232,125,78,.88) (era .62: 3:1 até sobre fundo escuro)
KW_ALT, KW_ALT_ALFA = (255, 209, 102), 0.80             # legenda.css: #FFD166 e rgba(255,209,102,.80)


class Tinta(str):
    """A tinta ("clara": halo normal; "halo": halo forte) com a cor do destaque que combina com ela em `.enfase` ("marca",
    "clara" ou "branca"; None sem destaque). É uma `str`: quem compara com "halo" não nota a diferença."""

    def __new__(cls, valor, enfase=None):
        obj = super().__new__(cls, valor)
        obj.enfase = enfase
        return obj


def _lum(v):
    c = float(v) / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


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
    """A cor do destaque para uma tinta e um fundo (p10, p90): "marca" (a terracota), "clara" (o amarelo) ou "branca"
    (o destaque perde a cor e sai branco como o resto: nenhuma das duas lê no fundo, e uma legenda sem destaque é
    melhor que uma legenda ilegível). No halo forte a mancha escura segura qualquer cor: "marca"."""
    if tinta == "halo":
        return "marca"
    if _camadas_ok(KW_MARCA, KW_MARCA_ALFA, (p10, p90)):
        return "marca"
    if _camadas_ok(KW_ALT, KW_ALT_ALFA, (p10, p90)):
        return "clara"
    return "branca"


def decidir_tinta(p10, p90, kw=False):
    """"clara" (halo normal) ou "halo" (halo forte) para o fundo de percentis (p10, p90), em cinza 0 a 255: o forte
    quando o fundo crítico (`p90`, na prática o p99 da faixa) passa de LIMIAR_HALO_FORTE. Com `kw` (o grupo tem
    palavra de ênfase) o resultado é uma `Tinta` que leva a cor do destaque em `.enfase` (W7.Z)."""
    tinta = "halo" if p90 > LIMIAR_HALO_FORTE else "clara"
    if not kw:
        return tinta
    return Tinta(tinta, decidir_enfase(tinta, p10, p90))


def _percentis_banda(video, t, y0, y1, x0=CAIXA_X[0], x1=CAIXA_X[1], quantis=(0.10, 0.90)):
    """(p10, p90) da luminância (0 a 255) da caixa [x0, x1) x [y0, y1) do vídeo no instante `t`; None sem quadro.
    Com `quantis` ((baixo, alto), frações) devolve esses dois percentis no lugar do p10 e do p90."""
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
            return px[int(quantis[0] * (len(px) - 1))], px[int(quantis[1] * (len(px) - 1))]
    except Exception:
        return None


def _tinta_dos_percentis(percentis, kw=False):
    """A tinta ("clara" ou "halo") para as medidas (p10, p90) de um ou mais instantes, pelo pior fundo
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
    """A tinta do grupo ("clara" ou "halo") medida na footage, em 3 instantes dentro dele, com o pior
    fundo dos três (o maior p90 e o menor p10). None sem medida. `kw`: o grupo tem palavra de ênfase e a tinta leva a cor
    do destaque (`Tinta.enfase`)."""
    y0, y1 = FAIXA_LEGENDA.get(classe, FAIXA_LEGENDA["base"])
    return _tinta_dos_percentis([_percentis_banda(video, ini + (fim - ini) * f, y0, y1, quantis=QUANTIS_LEGENDA)
                                 for f in (0.2, 0.5, 0.8)], kw)


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


def decisao_do_quadro(imagem, classe="base", formato="9x16", kw=False):
    """A decisão do overlay para UM quadro de footage (um PNG ou um vídeo, lido no instante 0):
    {"legenda": "clara" | "halo" | None, "gancho": "placa" | "fino"}.

    É a função que a PRANCHA de direção chama para dizer o que o motor faz naquele fundo: a mesma regra de
    `tinta_footage` (legenda) e `hook_pede_placa` (gancho), aplicadas a um quadro só. Uma regra, dois chamadores:
    a prancha nunca desenha legenda ou gancho por uma regra própria."""
    y0, y1 = FAIXA_LEGENDA.get(classe, FAIXA_LEGENDA["base"])
    legenda = _tinta_dos_percentis([_percentis_banda(imagem, 0.0, y0, y1, quantis=QUANTIS_LEGENDA)], kw)
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
    y0, y1 = FAIXA_LEGENDA.get(classe, FAIXA_LEGENDA["base"])
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
    de propósito: sem número, não inventa halo. Cacheado por (arquivo, start).
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


def marcar_grupos_claros(groups, ad, look, mapa_insert, a0=None, janelas_split=()):
    """Marca `halo` (halo forte) nos grupos de legenda sobre fundo claro, no instante em que cada um está na tela.

    Caminho bom: mede a footage renderizada, na faixa exata da classe do grupo. Primeira rodada de um
    anúncio novo (sem footage): cai no arquivo-fonte, no meio do grupo, com o tempo da fonte
    convertido por start e velocidade do insert. É aproximado (o painel mostra um recorte do asset),
    e o build seguinte converge para o caminho de cima. Em tela dividida a legenda está na base do painel do
    apresentador, não sobre o insert: o arquivo-fonte não diz nada ali (`janelas_split`) e o grupo fica de fora.

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
        n = 0
        for g in groups:
            _kw = any(w.get("kw") for w in g.get("words") or [])
            _r = (tinta_footage(_fmp4, g["start"] - a0, g["end"] - a0, classe_do_grupo(g), kw=True) if _kw
                  else tinta_footage(_fmp4, g["start"] - a0, g["end"] - a0, classe_do_grupo(g)))
            if _r == "halo":
                g["halo"] = True
                n += 1
            if _kw and getattr(_r, "enfase", None) == "clara":
                g["kw_alt"] = True
            elif _kw and getattr(_r, "enfase", None) == "branca":
                g["kw_branco"] = True
        print(f"   [fundo claro] {n} de {len(groups)} grupo(s) com HALO FORTE (fundo claro na base), "
              f"medidos na footage ({_fmp4.name})", flush=True)
    elif mapa_insert:
        n = 0
        for g in groups:
            _meio = (g["start"] + g["end"]) / 2.0
            _jan = next((w for w in mapa_insert if w["a"] <= _meio <= w["b"]), None)
            if not _jan:
                continue
            if any(a <= _meio < b for a, b in janelas_split or ()):
                continue       # tela dividida: a legenda esta sobre o apresentador, nao sobre o insert
            _tsrc = _jan["start"] + max(0.0, _meio - _jan["s2"]) * _jan["speed"]
            if fundo_claro(_jan["file"], round(_tsrc, 1)):
                g["halo"] = True
                n += 1
        if n:
            print(f"   [fundo claro] {n} grupo(s) com HALO FORTE pelo ARQUIVO-FONTE "
                  f"(sem footage ainda; o proximo build mede na footage)", flush=True)
