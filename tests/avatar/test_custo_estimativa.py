"""Estimativa de custo ANTES do job do HeyGen e o teto padrão de US$ 9,00.

Ensaio de 20/10/2026: o job real custou US$ 3,25 para 27,6 s de voz (US$ 7,08 por minuto) e a doc dizia US$ 3,20 a
4,40 por minuto. O teto antigo (US$ 5,00) barrava um anúncio de 60 s DEPOIS de pago. Agora a skill estima pela duração
da voz, com UMA constante (US$ 7,10 por minuto), e recusa antes de gastar, dizendo a duração máxima que cabe.
"""
import json
import re
from pathlib import Path

import pytest

from avatar import custo as K
from cli import avatar as CLI

RAIZ = Path(__file__).resolve().parent.parent.parent


def test_a_constante_unica_e_a_do_ensaio_com_fonte_e_data_no_comentario():
    assert K.CUSTO_USD_POR_MINUTO == 7.10
    fonte = (RAIZ / "scripts" / "avatar" / "custo.py").read_text(encoding="utf-8")
    ancora = fonte.index("CUSTO_USD_POR_MINUTO =")
    comentario = fonte[max(0, ancora - 900):ancora]
    for pedaco in ("20/10/2026", "3,25", "27,6 s", "7,08", "avatar/custo.json"):
        assert pedaco in comentario, "o comentário da constante precisa citar %s" % pedaco


def test_so_custo_py_conhece_o_preco_por_minuto():
    """Os outros arquivos de código importam a constante; nenhum repete o número."""
    repetidos = []
    for arq in (RAIZ / "scripts").rglob("*.py"):
        if arq.name == "custo.py" and arq.parent.name == "avatar":
            continue
        texto = arq.read_text(encoding="utf-8", errors="replace")
        if re.search(r"(?<![0-9.,])7[.,]10(?![0-9])", texto):
            repetidos.append(str(arq.relative_to(RAIZ)))
    assert repetidos == []


def test_estimar_usd_e_linear_na_duracao_da_voz():
    assert K.estimar_usd(60.0) == pytest.approx(7.10)
    assert K.estimar_usd(30.0) == pytest.approx(3.55)
    assert K.estimar_usd(27.6) == pytest.approx(3.266, abs=0.001)       # o job real custou 3,25
    assert K.estimar_usd(0.0) == 0.0


def test_a_estimativa_do_job_do_ensaio_erra_menos_de_2_por_cento():
    real = 3.25
    assert abs(K.estimar_usd(27.561) - real) / real < 0.02


def test_duracao_maxima_pelo_teto():
    assert K.duracao_maxima_s(9.0) == pytest.approx(76.06, abs=0.01)
    assert K.duracao_maxima_s(5.0) == pytest.approx(42.25, abs=0.01)


def test_o_teto_padrao_e_9_dolares_e_cobre_70_s():
    assert CLI.TETO_USD == 9.0
    assert K.estimar_usd(70.0) <= CLI.TETO_USD
    assert K.estimar_usd(60.0) <= CLI.TETO_USD
    assert K.estimar_usd(80.0) > CLI.TETO_USD


def test_cabe_no_teto_devolve_a_estimativa():
    assert K.exigir_que_caiba(60.0, 9.0) == pytest.approx(7.10)
    assert K.exigir_que_caiba(70.0, 9.0) == pytest.approx(8.2833, abs=0.001)


def test_no_limite_exato_do_teto_ainda_cabe():
    assert K.exigir_que_caiba(K.duracao_maxima_s(9.0), 9.0) == pytest.approx(9.0)


def test_passou_do_teto_levanta_antes_de_gastar_com_a_duracao_maxima_na_mensagem():
    with pytest.raises(K.CustoAcimaDoTeto) as e:
        K.exigir_que_caiba(90.0, 9.0)
    msg = str(e.value)
    assert e.value.maxima_s == pytest.approx(76.06, abs=0.01)
    assert e.value.estimativa_usd == pytest.approx(10.65, abs=0.01)
    assert "90,0 s" in msg and "10,65" in msg and "9,00" in msg
    assert "76 s" in msg, "diz a duração máxima que cabe"
    assert "--teto-usd 11" in msg, "diz o teto que cobre esta voz"
    assert "Nada foi gasto" in msg
    assert "\u2014" not in msg and "\u2013" not in msg


def test_a_mensagem_escreve_a_duracao_com_virgula_e_uma_casa():
    with pytest.raises(K.CustoAcimaDoTeto) as e:
        K.exigir_que_caiba(27.584, 3.0)
    assert "27,6 s" in str(e.value) and "3,26" in str(e.value) and "25 s" in str(e.value)


def test_a_mensagem_usa_o_teto_pedido_e_nao_o_padrao():
    with pytest.raises(K.CustoAcimaDoTeto) as e:
        K.exigir_que_caiba(60.0, 5.0)
    assert "42 s" in str(e.value) and "5,00" in str(e.value) and "--teto-usd 8" in str(e.value)


class Executor:
    def __init__(self, formato, rc=0):
        self.formato, self.rc, self.chamadas = formato, rc, []

    def __call__(self, argv, **kw):
        self.chamadas.append([str(a) for a in argv])
        if self.rc != 0:
            return self.rc, "Invalid data found when processing input"
        return 0, json.dumps({"format": {"duration": "%.3f" % self.formato}})


def test_duracao_da_voz_mede_pelo_ffprobe(tmp_path):
    voz = tmp_path / "limpo.mp3"
    voz.write_bytes(b"x")
    ex = Executor(27.584)
    assert K.duracao_da_voz(voz, executar=ex) == pytest.approx(27.584)
    assert ex.chamadas[0][0] == "ffprobe" and ex.chamadas[0][-1] == str(voz)


def test_voz_que_o_ffprobe_nao_le_devolve_none(tmp_path):
    voz = tmp_path / "limpo.mp3"
    voz.write_bytes(b"x")
    assert K.duracao_da_voz(voz, executar=Executor(0, rc=1)) is None
    assert K.duracao_da_voz(tmp_path / "nao-existe.mp3", executar=Executor(1.0)) is None
