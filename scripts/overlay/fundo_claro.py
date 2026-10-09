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
        n = 0
        for g in groups:
            _r = fundo_claro_footage(_fmp4, g["start"] - a0, g["end"] - a0, classe_do_grupo(g))
            if _r:
                g["claro"] = True
                n += 1
        print(f"   [fundo claro] {n} de {len(groups)} grupo(s) com tinta INVERTIDA, "
              f"medidos na footage ({_fmp4.name})", flush=True)
    elif mapa_insert:
        n = 0
        for g in groups:
            _meio = (g["start"] + g["end"]) / 2.0
            _jan = next((w for w in mapa_insert if w["a"] <= _meio <= w["b"]), None)
            if not _jan:
                continue
            _tsrc = _jan["start"] + max(0.0, _meio - _jan["s2"]) * _jan["speed"]
            if fundo_claro(_jan["file"], round(_tsrc, 1)):
                g["claro"] = True
                n += 1
        if n:
            print(f"   [fundo claro] {n} grupo(s) com tinta INVERTIDA pelo ARQUIVO-FONTE "
                  f"(sem footage ainda; o proximo build mede na footage)", flush=True)
