"""Enquadramento (W2.B): medir, nunca chutar.

Defeito 2 do plano: o motor procurava `medir_enquadramento.py` na pasta de DADOS (no clone
limpo ela não existe lá), a medição falhava calada e o split caía em 0,30, o centro do
recorte em 0,5 e o recorte da bolinha em y=640. Chute com cara de medição. Aqui o script é
achado pelo CÓDIGO (`caminhos.CODIGO`) e qualquer falha de medição dá ERRO ALTO.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import caminhos
from footage import enquadramento as ENQ


class Saida(object):
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


def medicao(**troca):
    """JSON do `medir_enquadramento.py avatar --json` de um avatar comum (pessoa de y 384 até o fim do quadro,
    rosto de y 488 a 913), com os campos que o teste trocar. `None` tira o campo."""
    dados = {"arquivo": "a.mp4", "pessoa_topo": 0.2, "pessoa_base": 0.998, "topo_px": 384, "base_px": 1916,
             "VAM_SPLIT_BIAS": 0.207}
    dados.update(troca)
    return Saida(json.dumps({k: v for k, v in dados.items() if v is not None}))


@pytest.fixture(autouse=True)
def caches_limpos():
    for nome in ("_CACHE_CONTEUDO", "_CACHE_ASPECTO", "_CACHE_LARG", "_PRETO_CACHE", "_PIP_CROP_CACHE"):
        getattr(ENQ, nome).clear()
    yield


# ------------------------------------------------------------------ onde o script mora

def test_o_script_de_medicao_e_achado_pelo_codigo_nao_por_dados():
    p = ENQ.script_de_medicao()
    assert Path(p) == caminhos.CODIGO / "medir_enquadramento.py"
    assert Path(p).is_file()


def test_o_script_nao_e_procurado_na_pasta_de_dados(monkeypatch, tmp_path):
    """Mesmo com DADOS apontando pra uma pasta sem o script, a medição o encontra no código."""
    monkeypatch.setattr(caminhos, "DADOS", tmp_path / "dados_vazio")
    chamadas = []

    def falso(cmd, **kw):
        chamadas.append(cmd)
        return medicao(VAM_SPLIT_BIAS=0.31)

    assert ENQ.medir_bias_split("/AV/a.mp4", env={}, executar=falso) == 0.31
    assert chamadas[0] == [sys.executable, str(caminhos.CODIGO / "medir_enquadramento.py"),
                           "avatar", "/AV/a.mp4", "--json"]


def test_script_ausente_do_codigo_da_erro_alto(monkeypatch, tmp_path):
    monkeypatch.setattr(caminhos, "CODIGO", tmp_path)
    with pytest.raises(ENQ.ErroEnquadramento) as e:
        ENQ.medir_bias_split("/AV/a.mp4", env={}, executar=lambda c, **k: Saida("{}"))
    assert "medir_enquadramento.py" in str(e.value)
    assert str(tmp_path) in str(e.value)


# ------------------------------------------------------------------ bias do split

def test_variavel_de_ambiente_vale_e_dispensa_a_medicao():
    def proibido(*a, **k):
        raise AssertionError("não devia medir quando VAM_SPLIT_BIAS está definida")

    assert ENQ.medir_bias_split("/AV/a.mp4", env={"VAM_SPLIT_BIAS": "0.42"}, executar=proibido) == 0.42


def test_variavel_vazia_conta_como_nao_definida():
    saida = medicao(VAM_SPLIT_BIAS=0.18)
    assert ENQ.medir_bias_split("/AV/a.mp4", env={"VAM_SPLIT_BIAS": ""}, executar=lambda c, **k: saida) == 0.18


def test_variavel_invalida_da_erro_alto_citando_o_valor():
    with pytest.raises(ENQ.ErroEnquadramento) as e:
        ENQ.medir_bias_split("/AV/a.mp4", env={"VAM_SPLIT_BIAS": "muito"})
    assert "VAM_SPLIT_BIAS" in str(e.value) and "muito" in str(e.value)


@pytest.mark.parametrize("saida", [
    Saida("", "Traceback...", 1),                       # o script quebrou
    Saida("não é json"),                                # saída inválida
    Saida(json.dumps({"outra_chave": 1})),              # sem o campo
    medicao(VAM_SPLIT_BIAS="abc"),                     # valor que não é número
])
def test_medicao_que_falha_da_erro_alto_e_nunca_030(saida):
    with pytest.raises(ENQ.ErroEnquadramento) as e:
        ENQ.medir_bias_split("/AV/a.mp4", env={}, executar=lambda c, **k: saida)
    msg = str(e.value)
    assert "enquadramento" in msg.lower()
    assert "VAM_SPLIT_BIAS" in msg                      # diz como fixar na mão
    assert "0.30" not in msg and "0,30" not in msg


def test_excecao_ao_rodar_o_script_vira_erro_alto():
    def quebra(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 180)

    with pytest.raises(ENQ.ErroEnquadramento):
        ENQ.medir_bias_split("/AV/a.mp4", env={}, executar=quebra)


def test_nao_existe_mais_o_fallback_030_no_codigo():
    fonte = Path(ENQ.__file__).read_text(encoding="utf-8")
    assert "bias = 0.30" not in fonte and "bias=0.30" not in fonte


# ------------------------------------------------------------------ conteúdo do asset

def test_medir_conteudo_devolve_centro_e_modo_e_cacheia():
    n = []

    def falso(cmd, **kw):
        n.append(cmd)
        return Saida(json.dumps({"centro_conteudo_x": 0.4, "centro_conteudo_y": 0.6,
                                 "modo": "encaixar", "perda_ao_preencher": 0.3}))

    a = ENQ.medir_conteudo("/m/a.mp4", 1080, 1150, executar=falso)
    b = ENQ.medir_conteudo("/m/a.mp4", 1080, 1150, executar=falso)
    assert a == b == (0.4, 0.6, "encaixar")
    assert len(n) == 1
    assert n[0][2:] == ["asset", "/m/a.mp4", "--painel", "1080x1150", "--json"]


def test_medir_conteudo_sem_modo_assume_preencher():
    falso = lambda c, **k: Saida(json.dumps({"centro_conteudo_x": 0.5, "centro_conteudo_y": 0.5}))  # noqa: E731
    assert ENQ.medir_conteudo("/m/b.mp4", 1080, 1150, executar=falso)[2] == "preencher"


def test_medir_conteudo_que_falha_da_erro_alto_nao_usa_o_meio():
    with pytest.raises(ENQ.ErroEnquadramento) as e:
        ENQ.medir_conteudo("/m/c.mp4", 1080, 1150, executar=lambda c, **k: Saida("", "boom", 2))
    assert "/m/c.mp4" in str(e.value)
    assert "/m/c.mp4" not in ENQ._CACHE_CONTEUDO         # o erro não vira cache


def test_crop_conteudo_usa_a_fracao_medida_e_prende_nas_bordas():
    ENQ._CACHE_CONTEUDO["/m/d.mp4"] = (0.4231, 0.6, "preencher")
    expr = ENQ.crop_conteudo("/m/d.mp4", 1080, 1150)
    assert expr == ("'clip((in_w*0.4231)-(out_w/2),0,in_w-out_w)'"
                    ":'clip((in_h*0.6000)-(out_h/2),0,in_h-out_h)'")


def test_crop_conteudo_com_recorte_declarado_centraliza_sem_medir():
    def proibido(*a, **k):
        raise AssertionError("recorte declarado dispensa medir")

    assert ENQ.crop_conteudo("/m/e.mp4", 1080, 1150, crop_dims=(800, 600), executar=proibido) == \
        "'(in_w-out_w)/2':'(in_h-out_h)/2'"


def test_crop_fonte_aceita_o_nome_antigo_do_campo():
    assert ENQ.crop_fonte({"crop": "800:600:10:20"}) == ("crop=800:600:10:20,", (800, 600))
    assert ENQ.crop_fonte({"split_crop": "640:480:0:0"}) == ("crop=640:480:0:0,", (640, 480))
    assert ENQ.crop_fonte({}) == ("", None)
    assert ENQ.crop_fonte({"crop": ""}) == ("", None)


def test_modo_do_painel_com_recorte_declarado_vem_da_perda_calculada():
    # recorte 1000x500 (aspecto 2) num painel 1080x1150 (0,94): perda 1 - 0,94/2 > 0,22 -> encaixar
    assert ENQ.modo_do_painel("/m/f.mp4", 1080, 1150, crop_dims=(1000, 500)) == "encaixar"
    # recorte quase do aspecto do painel: preencher
    assert ENQ.modo_do_painel("/m/f.mp4", 1080, 1150, crop_dims=(1000, 1060)) == "preencher"


# ------------------------------------------------------------------ recorte da bolinha

def test_recorte_da_bolinha_vem_do_topo_medido_menos_60():
    falso = lambda c, **k: medicao(topo_px=693, pessoa_topo=0.361)  # noqa: E731
    assert ENQ.pip_crop("/AV/a.mp4", executar=falso) == "720:720:180:633"


def test_recorte_da_bolinha_nunca_passa_do_fim_da_fonte():
    falso = lambda c, **k: medicao(topo_px=1900, pessoa_topo=0.99)  # noqa: E731
    assert ENQ.pip_crop("/AV/b.mp4", executar=falso) == "720:720:180:1200"


def test_recorte_da_bolinha_que_falha_da_erro_alto_nao_usa_640():
    with pytest.raises(ENQ.ErroEnquadramento) as e:
        ENQ.pip_crop("/AV/c.mp4", executar=lambda c, **k: Saida("", "sem rosto", 1))
    assert "/AV/c.mp4" in str(e.value)


def test_recorte_da_bolinha_e_cacheado_por_avatar():
    n = []

    def falso(cmd, **kw):
        n.append(1)
        return medicao(topo_px=700)

    ENQ.pip_crop("/AV/d.mp4", executar=falso)
    ENQ.pip_crop("/AV/d.mp4", executar=falso)
    assert len(n) == 1


# ------------------------------------------------------------------ sondas do arquivo

def test_aspecto_e_medido_por_ffprobe_e_cacheado():
    n = []

    def falso(cmd, **kw):
        n.append(cmd)
        return Saida("1920x1080\n")

    assert ENQ.aspecto("/m/g.mp4", executar=falso) == pytest.approx(1920 / 1080)
    assert ENQ.aspecto("/m/g.mp4", executar=falso) == pytest.approx(1920 / 1080)
    assert len(n) == 1
    assert n[0][:2] == ["ffprobe", "-v"] and "stream=width,height" in n[0]


def test_aspecto_ilegivel_avisa_alto_e_cai_em_16_9(capsys):
    assert ENQ.aspecto("/m/h.mp4", executar=lambda c, **k: Saida("")) == pytest.approx(16 / 9)
    assert "AVISO" in capsys.readouterr().out


def test_largura_da_fonte_e_cacheada_e_none_quando_ilegivel():
    assert ENQ.largura_fonte("/m/i.mp4", executar=lambda c, **k: Saida("1920\n")) == 1920
    assert ENQ.largura_fonte("/m/j.mp4", executar=lambda c, **k: Saida("")) is None


def test_pular_preto_desloca_ate_o_primeiro_quadro_claro():
    erro = "[blackdetect @ 0x] black_start:0 black_end:0.4 black_duration:0.4"
    novo = ENQ.pular_preto("/m/k.mp4", 2.0, 3.0, executar=lambda c, **k: Saida("", erro))
    assert novo == pytest.approx(2.45)


def test_pular_preto_nunca_desloca_mais_de_1_2s():
    erro = "black_start:0 black_end:5.0"
    assert ENQ.pular_preto("/m/l.mp4", 0.0, 3.0, executar=lambda c, **k: Saida("", erro)) == pytest.approx(1.2)


def test_fonte_escura_legitima_nao_e_tocada():
    erro = "black_start:0.3 black_end:0.9"
    assert ENQ.pular_preto("/m/m.mp4", 1.0, 3.0, executar=lambda c, **k: Saida("", erro)) == 1.0
    assert ENQ.pular_preto("/m/n.mp4", 1.0, 3.0, executar=lambda c, **k: Saida("", "")) == 1.0


def test_pular_preto_usa_o_comando_do_original():
    cmds = []

    def falso(cmd, **kw):
        cmds.append(cmd)
        return Saida("", "")

    ENQ.pular_preto("/m/o.mp4", 3.0, 2.0, executar=falso)
    assert cmds[0] == ["ffmpeg", "-v", "info", "-ss", "3.0", "-t", "1.5", "-i", "/m/o.mp4",
                       "-vf", "blackdetect=d=0.1:pix_th=0.06", "-an", "-f", "null", "-"]


# ------------------------------------------------------------------ W3.X B1: medição degenerada e ancoragem no rosto
# Invariante: nenhuma decisão de enquadramento se apoia numa medição que não separou a pessoa do fundo. Uma
# "pessoa" que ocupa o quadro inteiro (topo 0,0 e base acima de 0,99, ou topo_px 0) não é medida, é o detector
# cego: o avatar do fixture da paridade devolvia 0,0/0,998 e a bolinha ficava com 55% do rosto (boca e queixo
# fora). E a bolinha e o painel do split existem para mostrar o ROSTO: com o rosto medido, é nele que ancoram.

DEGENERADAS = [
    {"pessoa_topo": 0.0, "pessoa_base": 0.998, "topo_px": 0},      # o caso do fixture
    {"pessoa_topo": 0.0, "pessoa_base": 0.995, "topo_px": 0},
    {"topo_px": 0, "pessoa_topo": 0.0004},                         # topo_px 0 basta
]


@pytest.mark.parametrize("campos", DEGENERADAS)
def test_medicao_degenerada_do_split_e_erro_alto_com_os_numeros(campos):
    with pytest.raises(ENQ.ErroEnquadramento) as e:
        ENQ.medir_bias_split("/AV/a.mp4", env={}, executar=lambda c, **k: medicao(**campos))
    msg = str(e.value)
    assert "degenerada" in msg and "/AV/a.mp4" in msg
    assert "topo_px 0" in msg or "topo_px=0" in msg


@pytest.mark.parametrize("campos", DEGENERADAS)
def test_medicao_degenerada_da_bolinha_e_erro_alto(campos):
    with pytest.raises(ENQ.ErroEnquadramento) as e:
        ENQ.pip_crop("/AV/b.mp4", executar=lambda c, **k: medicao(**campos))
    assert "degenerada" in str(e.value)
    assert "/AV/b.mp4" not in ENQ._PIP_CROP_CACHE           # o erro não vira cache


def test_medicao_sem_a_caixa_da_pessoa_nao_e_aceita():
    """Sem pessoa_topo/pessoa_base não há como saber se a medição viu a pessoa: erro, não número."""
    with pytest.raises(ENQ.ErroEnquadramento):
        ENQ.medir_bias_split("/AV/c.mp4", env={}, executar=lambda c, **k: medicao(pessoa_topo=None))


def test_pessoa_que_encosta_no_fim_do_quadro_com_topo_medido_e_normal():
    """Base em 0,998 é o normal de um apresentador com microfone; o defeito é o topo em zero junto."""
    assert ENQ.medir_bias_split("/AV/d.mp4", env={}, executar=lambda c, **k: medicao()) == 0.207


def test_bolinha_ancora_no_centro_do_rosto_medido():
    """Rosto de y 488 a 913 (centro 700): o quadrado de 720 vai de 340 a 1060, o rosto inteiro dentro."""
    falso = lambda c, **k: medicao(rosto_y=488, rosto_h=425)  # noqa: E731
    assert ENQ.pip_crop("/AV/e.mp4", executar=falso) == "720:720:180:340"


def test_bolinha_ancorada_no_rosto_nunca_sai_do_quadro():
    assert ENQ.pip_crop("/AV/f.mp4", executar=lambda c, **k: medicao(rosto_y=10, rosto_h=200)) == "720:720:180:0"
    assert ENQ.pip_crop("/AV/g.mp4", executar=lambda c, **k: medicao(rosto_y=1700, rosto_h=200)) == \
        "720:720:180:1200"


def test_mensagens_de_erro_em_portugues_correto():
    """L2: "de o avatar" não existe em português ("do avatar")."""
    with pytest.raises(ENQ.ErroEnquadramento) as e:
        ENQ.medir_bias_split("/AV/h.mp4", env={}, executar=lambda c, **k: Saida("", "boom", 1))
    assert " de o " not in str(e.value) and "do avatar" in str(e.value)
    with pytest.raises(ENQ.ErroEnquadramento) as e:
        ENQ.medir_conteudo("/m/p.mp4", 1080, 1150, executar=lambda c, **k: Saida("", "boom", 1))
    assert " de o " not in str(e.value) and "do asset" in str(e.value)


# ------------------------------------------------------------------ W3.X B1: a causa (vinheta no fundo)

def _quadro_com_vinheta(caminho, topo_pessoa=96, w=270, h=480):
    """Fundo com luz central (faixa do meio 18 níveis mais clara que as laterais, como no fixture) e uma pessoa
    escura do `topo_pessoa` até o fim do quadro, no meio. Sem descontar a vinheta, toda linha 'tem pessoa'."""
    from PIL import Image

    im = Image.new("L", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            fundo = 78 if 0.2 * w <= x < 0.8 * w else 60
            px[x, y] = 30 if (y >= topo_pessoa and 0.35 * w <= x < 0.65 * w) else fundo
    im.save(caminho)
    return str(caminho)


def test_medir_avatar_desconta_a_luz_do_fundo_e_acha_o_topo_da_pessoa(tmp_path, monkeypatch):
    import types

    import medir_enquadramento as M

    quadros = [_quadro_com_vinheta(tmp_path / f"q{i}.png") for i in range(5)]
    monkeypatch.setattr(M, "_frames", lambda video, n=M.AMOSTRAS: (list(quadros), 18.0))
    rosto = types.ModuleType("medir_rosto")
    rosto.caixa_rosto = lambda video, *a, **k: (480, 400)       # rosto de y 480 a 880 na fonte de 1920
    monkeypatch.setitem(sys.modules, "medir_rosto", rosto)
    topo, base = M.medir_avatar("/AV/vinheta.mp4")
    assert topo == pytest.approx(96 / 480, abs=2 / 480), "o topo é onde a pessoa começa, não a linha 0"
    assert base > 0.99


def test_medir_avatar_sem_vinheta_continua_como_antes(tmp_path, monkeypatch):
    """Fundo uniforme: a diferença do fundo é zero e o resultado é o de sempre."""
    import types

    from PIL import Image

    import medir_enquadramento as M

    p = tmp_path / "u.png"
    im = Image.new("L", (270, 480), 60)
    px = im.load()
    for y in range(120, 480):
        for x in range(95, 175):
            px[x, y] = 30
    im.save(p)
    monkeypatch.setattr(M, "_frames", lambda video, n=M.AMOSTRAS: ([str(p)] * 5, 18.0))
    rosto = types.ModuleType("medir_rosto")
    rosto.caixa_rosto = lambda video, *a, **k: (560, 400)
    monkeypatch.setitem(sys.modules, "medir_rosto", rosto)
    topo, _base = M.medir_avatar("/AV/uniforme.mp4")
    assert topo == pytest.approx(120 / 480, abs=1 / 480)


# ------------------------------------------------------------------ W3.X B1: o avatar do fixture (mídia real)

def _caixas_do_rosto_com_x(avatar):
    """(x, y, w, h) do maior rosto em cada instante que o `medir_rosto` amostra, com os mesmos parâmetros dele.
    O `medir_rosto.caixa_rosto` devolve só (y, h); o x é medido aqui para saber o quanto da caixa cabe no círculo."""
    import tempfile

    import cv2

    import medir_rosto

    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    pasta = tempfile.mkdtemp()
    caixas = []
    for t in (6, 14, 22, 30):          # os instantes do medir_rosto
        p = os.path.join(pasta, f"f{t}.png")
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", avatar, "-frames:v", "1", p],
                           capture_output=True)
        if r.returncode != 0 or not os.path.exists(p):
            continue
        cinza = cv2.cvtColor(cv2.imread(p), cv2.COLOR_BGR2GRAY)
        achados = casc.detectMultiScale(cinza, 1.1, 5, minSize=(120, 120))
        if len(achados):
            caixas.append(tuple(int(v) for v in max(achados, key=lambda b: b[2] * b[3])))
    y, h = medir_rosto.caixa_rosto(avatar)
    xs = sorted(c[0] for c in caixas)
    ws = sorted(c[2] for c in caixas)
    return (xs[len(xs) // 2], y, ws[len(ws) // 2], h), caixas


def _fracao_no_circulo(caixa, cx, cy, r, passos=120):
    x, y, w, h = caixa
    dentro = 0
    for i in range(passos):
        for j in range(passos):
            px = x + (i + 0.5) * w / passos
            py = y + (j + 0.5) * h / passos
            dentro += (px - cx) ** 2 + (py - cy) ** 2 <= r * r
    return dentro / (passos * passos)


@pytest.mark.midia_real
@pytest.mark.lento
def test_fixture_a_bolinha_e_o_painel_do_split_mostram_o_rosto():
    """No avatar do fixture da paridade: medição não degenerada, a bolinha contém pelo menos 90% da caixa do rosto
    do `medir_rosto` e o painel de baixo do split contém o rosto inteiro (da testa ao queixo)."""
    from footage import filtros_avatar as FA
    from tests.paridade import capturar as C

    avatar = str(C.exigir_midia() / "fixture" / "midia" / "avatar_18s.mp4")
    dados = json.loads(subprocess.run([sys.executable, str(ENQ.script_de_medicao()), "avatar", avatar, "--json"],
                                      capture_output=True, text=True, check=True).stdout)
    assert dados["topo_px"] > 0 and not (dados["pessoa_topo"] <= 0.0 and dados["pessoa_base"] > 0.99), dados

    caixa, por_quadro = _caixas_do_rosto_com_x(avatar)
    lado, _alt, x, y0 = [int(v) for v in ENQ.pip_crop(avatar).split(":")]       # crop=w:h:x:y
    fracao = _fracao_no_circulo(caixa, x + lado / 2, y0 + lado / 2, lado / 2)
    assert fracao >= 0.90, f"a bolinha {ENQ.pip_crop(avatar)} mostra {fracao:.0%} do rosto {caixa}"

    bias = ENQ.medir_bias_split(avatar, env={})
    _sx, sy, _sw, _sh = FA.SPLIT_AV_SRC
    corte = FA.corte_y_split(bias, FA.altura_util_split())
    ini, fim = sy + corte, sy + corte + FA.SPLIT_BOT_H
    _x, ry, _w, rh = caixa
    assert ini <= ry and ry + rh <= fim, f"painel do split de y {ini} a {fim}, rosto de {ry} a {ry + rh}"
