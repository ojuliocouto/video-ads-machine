"""Enquadramento (W2.B): medir, nunca chutar.

Defeito 2 do plano: o motor procurava `medir_enquadramento.py` na pasta de DADOS (no clone
limpo ela não existe lá), a medição falhava calada e o split caía em 0,30, o centro do
recorte em 0,5 e o recorte da bolinha em y=640. Chute com cara de medição. Aqui o script é
achado pelo CÓDIGO (`caminhos.CODIGO`) e qualquer falha de medição dá ERRO ALTO.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

import caminhos
from footage import enquadramento as ENQ


class Saida(object):
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


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
        return Saida(json.dumps({"VAM_SPLIT_BIAS": 0.31}))

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
    saida = Saida(json.dumps({"VAM_SPLIT_BIAS": 0.18}))
    assert ENQ.medir_bias_split("/AV/a.mp4", env={"VAM_SPLIT_BIAS": ""}, executar=lambda c, **k: saida) == 0.18


def test_variavel_invalida_da_erro_alto_citando_o_valor():
    with pytest.raises(ENQ.ErroEnquadramento) as e:
        ENQ.medir_bias_split("/AV/a.mp4", env={"VAM_SPLIT_BIAS": "muito"})
    assert "VAM_SPLIT_BIAS" in str(e.value) and "muito" in str(e.value)


@pytest.mark.parametrize("saida", [
    Saida("", "Traceback...", 1),                       # o script quebrou
    Saida("não é json"),                                # saída inválida
    Saida(json.dumps({"outra_chave": 1})),              # sem o campo
    Saida(json.dumps({"VAM_SPLIT_BIAS": "abc"})),       # valor que não é número
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
    falso = lambda c, **k: Saida(json.dumps({"topo_px": 693}))  # noqa: E731
    assert ENQ.pip_crop("/AV/a.mp4", executar=falso) == "720:720:180:633"


def test_recorte_da_bolinha_nunca_passa_do_fim_da_fonte():
    falso = lambda c, **k: Saida(json.dumps({"topo_px": 1900}))  # noqa: E731
    assert ENQ.pip_crop("/AV/b.mp4", executar=falso) == "720:720:180:1200"


def test_recorte_da_bolinha_que_falha_da_erro_alto_nao_usa_640():
    with pytest.raises(ENQ.ErroEnquadramento) as e:
        ENQ.pip_crop("/AV/c.mp4", executar=lambda c, **k: Saida("", "sem rosto", 1))
    assert "/AV/c.mp4" in str(e.value)


def test_recorte_da_bolinha_e_cacheado_por_avatar():
    n = []

    def falso(cmd, **kw):
        n.append(1)
        return Saida(json.dumps({"topo_px": 700}))

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
