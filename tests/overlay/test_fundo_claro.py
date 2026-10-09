"""overlay.fundo_claro: tinta invertida onde o fundo é claro (28/08/2026).

O limiar sai da conta (contraste WCAG de tinta branca cruza 4,5:1 em L = 119/255), a medição
é por instante e não pelo arquivo inteiro, e falha de medição NUNCA inventa placa. Estes
testes cobrem as três decisões do original:

  - mediana (não média) de um quadro do insert, e mediana das TRÊS amostras na footage;
  - a footage renderizada manda; sem ela (primeira rodada de um anúncio novo) mede a fonte
    no instante do grupo, com o tempo convertido por start e velocidade do insert;
  - o resultado da fonte é cacheado por (arquivo, start).
"""
import subprocess

import pytest

from overlay import fundo_claro as FC
from overlay import layout_texto as LT


def pgm(valor, lado=64):
    return b"P5\n%d %d\n255\n" % (lado, lado) + bytes([valor]) * (lado * lado)


@pytest.fixture(autouse=True)
def limpa_cache():
    FC._CACHE_FUNDO.clear()
    yield
    FC._CACHE_FUNDO.clear()


@pytest.fixture
def ffmpeg_falso(monkeypatch):
    """subprocess.run que grava um PGM de luminância fixa no arquivo de saída (último argv)."""
    estado = {"valor": 200, "chamadas": [], "rc": 0}

    def falso(cmd, **kw):
        estado["chamadas"].append(list(cmd))
        if estado["rc"] == 0:
            lado = 128 if "scale=128:32" in " ".join(cmd) else 64
            with open(cmd[-1], "wb") as f:
                f.write(pgm(estado["valor"], lado))
        return subprocess.CompletedProcess(cmd, estado["rc"], stdout="", stderr="")

    monkeypatch.setattr(FC.subprocess, "run", falso)
    return estado


# --- o limiar -------------------------------------------------------------------------------

def test_limiar_pousa_no_piso_de_legibilidade_de_4_5_para_1():
    assert FC.LIMIAR_FUNDO_CLARO == 119
    lim = FC.LIMIAR_FUNDO_CLARO / 255.0
    lin = lim / 12.92 if lim <= 0.03928 else ((lim + 0.055) / 1.055) ** 2.4
    assert abs(1.05 / (lin + 0.05) - 4.5) < 0.15


def test_limiar_de_150_deixaria_passar_fundo_que_apaga_a_legenda():
    # o primeiro palpite (150) dava contraste 2,96:1; o teste derrubou
    lim = 150 / 255.0
    lin = ((lim + 0.055) / 1.055) ** 2.4
    assert 1.05 / (lin + 0.05) < 3.0


# --- _mediana_banda e fundo_claro (um quadro) --------------------------------------------------

def test_mediana_da_banda_le_so_a_faixa_pedida(ffmpeg_falso):
    ffmpeg_falso["valor"] = 77
    assert FC._mediana_banda("v.mp4", 1.23456, 1290, 1500) == 77
    cmd = ffmpeg_falso["chamadas"][0]
    assert cmd[:10] == ["ffmpeg", "-v", "error", "-y", "-ss", "1.235", "-i", "v.mp4", "-frames:v", "1"]
    assert cmd[10:12] == ["-vf", "crop=1080:210:0:1290,format=gray,scale=128:32"]


def test_mediana_da_banda_nao_aceita_tempo_negativo_nem_faixa_de_menos_de_2px(ffmpeg_falso):
    FC._mediana_banda("v.mp4", -3.0, 100, 100)
    cmd = ffmpeg_falso["chamadas"][0]
    assert cmd[5] == "0.000"
    assert "crop=1080:2:0:100," in cmd[11]


def test_mediana_da_banda_sem_quadro_e_none(ffmpeg_falso):
    ffmpeg_falso["rc"] = 1
    assert FC._mediana_banda("v.mp4", 1.0, 0, 100) is None


def test_mediana_da_banda_com_ffmpeg_real_distingue_branco_de_preto(tmp_path):
    def cor(nome, c):
        p = tmp_path / nome
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                        "-i", f"color=c={c}:s=1080x1920:d=1:r=2", "-pix_fmt", "yuv420p", str(p)], check=True)
        return str(p)

    assert FC._mediana_banda(cor("b.mp4", "white"), 0.0, 1290, 1500) > 200
    assert FC._mediana_banda(cor("p.mp4", "black"), 0.0, 1290, 1500) < 40


def test_fundo_claro_pela_mediana_da_fonte(ffmpeg_falso):
    ffmpeg_falso["valor"] = 120
    assert FC.fundo_claro("a.mp4", 3.0) is True
    ffmpeg_falso["valor"] = 118
    assert FC.fundo_claro("b.mp4", 3.0) is False
    # o quadro e medido 0,5 s depois do inicio do trecho
    assert ffmpeg_falso["chamadas"][0][4:6] == ["-ss", "3.5"]
    assert ffmpeg_falso["chamadas"][0][10:12] == ["-vf", "format=gray,scale=64:64"]


def test_fundo_claro_cacheia_por_arquivo_e_inicio(ffmpeg_falso):
    ffmpeg_falso["valor"] = 200
    assert FC.fundo_claro("a.mp4", 1.0) is True
    ffmpeg_falso["valor"] = 10
    assert FC.fundo_claro("a.mp4", 1.0) is True            # veio do cache
    assert FC.fundo_claro("a.mp4", 1.004) is True          # mesma chave: round(start, 2)
    assert len(ffmpeg_falso["chamadas"]) == 1
    assert FC.fundo_claro("a.mp4", 2.0) is False           # outro instante: mede de novo
    assert len(ffmpeg_falso["chamadas"]) == 2


def test_falha_de_medicao_nao_inventa_placa(ffmpeg_falso):
    ffmpeg_falso["rc"] = 1
    assert FC.fundo_claro("nao_existe.mp4", 0.0) is False


def test_excecao_na_medicao_tambem_vira_false(monkeypatch):
    def quebra(*a, **k):
        raise OSError("sem ffmpeg")

    monkeypatch.setattr(FC.subprocess, "run", quebra)
    assert FC.fundo_claro("a.mp4", 0.0) is False


# --- fundo_claro_footage: tres amostras, mediana ------------------------------------------------------

def test_footage_mede_tres_amostras_dentro_do_grupo_na_faixa_da_classe(monkeypatch):
    vistas = []
    monkeypatch.setattr(FC, "_mediana_banda", lambda v, t, y0, y1: vistas.append((t, y0, y1)) or 200)
    assert FC.fundo_claro_footage("f.mp4", 10.0, 12.0, "costura") is True
    assert vistas == [(10.5, 1000, 1130), (11.0, 1000, 1130), (11.5, 1000, 1130)]


@pytest.mark.parametrize("classe,faixa", [("baixa", (1370, 1520)), ("padrao", (1290, 1500)),
                                          ("qualquer", (1290, 1500))])
def test_footage_usa_a_faixa_da_classe_e_cai_na_padrao(monkeypatch, classe, faixa):
    vistas = []
    monkeypatch.setattr(FC, "_mediana_banda", lambda v, t, y0, y1: vistas.append((y0, y1)) or 50)
    FC.fundo_claro_footage("f.mp4", 0.0, 1.0, classe)
    assert set(vistas) == {faixa}
    assert faixa == LT.FAIXA_LEGENDA.get(classe, LT.FAIXA_LEGENDA["padrao"])


def test_footage_decide_pela_mediana_das_tres_amostras(monkeypatch):
    # perto de um corte uma amostra sozinha pode cair no plano vizinho
    for valores, esperado in (([100, 130, 200], True), ([10, 50, 200], False), ([255, 20, 30], False)):
        it = iter(valores)
        monkeypatch.setattr(FC, "_mediana_banda", lambda v, t, y0, y1: next(it))
        assert FC.fundo_claro_footage("f.mp4", 0.0, 4.0, "padrao") is esperado, valores


def test_footage_com_amostra_perdida_usa_o_valor_mais_alto_das_duas(monkeypatch):
    it = iter([None, 100, 130])
    monkeypatch.setattr(FC, "_mediana_banda", lambda v, t, y0, y1: next(it))
    assert FC.fundo_claro_footage("f.mp4", 0.0, 4.0, "padrao") is True        # vals[1] de [100, 130]


def test_footage_sem_nenhuma_amostra_devolve_none(monkeypatch):
    monkeypatch.setattr(FC, "_mediana_banda", lambda *a: None)
    assert FC.fundo_claro_footage("f.mp4", 0.0, 4.0, "padrao") is None


# --- marcar_grupos_claros: footage manda; sem footage, a fonte no instante do grupo ---------------------------

def g(a, b, **extra):
    d = {"start": a, "end": b, "words": []}
    d.update(extra)
    return d


@pytest.fixture
def v1(tmp_path, monkeypatch):
    monkeypatch.setattr(FC, "V1", tmp_path)
    (tmp_path / "output").mkdir()
    return tmp_path


def test_com_footage_mede_na_footage_na_classe_de_cada_grupo(v1, monkeypatch, capsys):
    (v1 / "output" / "ad1_lk_footage_1x.mp4").write_bytes(b"x")
    chamadas = []

    def falso(video, ini, fim, classe):
        chamadas.append((video.name, ini, fim, classe))
        return classe == "costura"

    monkeypatch.setattr(FC, "fundo_claro_footage", falso)
    grupos = [g(1.0, 2.0, costura=True), g(3.0, 4.0, baixa=True), g(5.0, 6.0)]
    FC.marcar_grupos_claros(grupos, "ad1", "lk", [], a0=0.0)
    assert [x.get("claro") for x in grupos] == [True, None, None]
    assert [c[3] for c in chamadas] == ["costura", "baixa", "padrao"]
    assert chamadas[0][0] == "ad1_lk_footage_1x.mp4"
    assert ("[fundo claro] 1 de 3 grupo(s) com tinta INVERTIDA, medidos na footage "
            "(ad1_lk_footage_1x.mp4)") in capsys.readouterr().out


def test_footage_none_nao_marca(v1, monkeypatch):
    (v1 / "output" / "ad1_lk_footage_1x.mp4").write_bytes(b"x")
    monkeypatch.setattr(FC, "fundo_claro_footage", lambda *a: None)
    grupos = [g(1.0, 2.0)]
    FC.marcar_grupos_claros(grupos, "ad1", "lk", [], a0=0.0)
    assert "claro" not in grupos[0]


def test_sem_footage_mede_o_arquivo_fonte_no_meio_do_grupo(v1, monkeypatch, capsys):
    vistas = []

    def falso(arquivo, t):
        vistas.append((arquivo, t))
        return True

    monkeypatch.setattr(FC, "fundo_claro", falso)
    mapa = [{"a": 10.0, "b": 14.0, "file": "ins.mp4", "start": 2.0, "speed": 1.5, "s2": 8.0}]
    grupos = [g(11.0, 13.0), g(20.0, 21.0)]
    FC.marcar_grupos_claros(grupos, "ad1", "lk", mapa)
    # meio = 12,0; tempo na fonte = start + (meio - s2) * speed = 2 + 4 * 1,5 = 8,0
    assert vistas == [("ins.mp4", 8.0)]
    assert grupos[0].get("claro") is True and "claro" not in grupos[1]
    assert "1 grupo(s) com tinta INVERTIDA pelo ARQUIVO-FONTE (sem footage ainda" in capsys.readouterr().out


def test_sem_footage_o_tempo_da_fonte_nunca_e_negativo(v1, monkeypatch):
    vistas = []
    monkeypatch.setattr(FC, "fundo_claro", lambda arquivo, t: vistas.append(t) or False)
    mapa = [{"a": 0.0, "b": 4.0, "file": "i.mp4", "start": 1.0, "speed": 1.0, "s2": 3.0}]
    FC.marcar_grupos_claros([g(0.0, 1.0)], "ad1", "lk", mapa)       # meio 0,5 < s2 3,0
    assert vistas == [1.0]


def test_sem_footage_e_sem_inserts_nao_mede_nada(v1, monkeypatch):
    monkeypatch.setattr(FC, "fundo_claro", lambda *a: pytest.fail("nao deveria medir"))
    monkeypatch.setattr(FC, "fundo_claro_footage", lambda *a: pytest.fail("nao deveria medir"))
    grupos = [g(1.0, 2.0)]
    FC.marcar_grupos_claros(grupos, "ad1", "lk", [])
    assert "claro" not in grupos[0]


def test_sem_footage_o_arquivo_fonte_e_arredondado_a_um_decimo(v1, monkeypatch):
    vistas = []
    monkeypatch.setattr(FC, "fundo_claro", lambda arquivo, t: vistas.append(t) or False)
    mapa = [{"a": 0.0, "b": 9.0, "file": "i.mp4", "start": 0.0, "speed": 1.0, "s2": 0.0}]
    FC.marcar_grupos_claros([g(1.0, 1.3)], "ad1", "lk", mapa)       # meio 1,15
    assert vistas == [1.1]                                            # round(1.15, 1) em float


# --- W3.X M4: a footage é amostrada no relógio DELA ------------------------------------------------------------
# O overlay é deslocado de -a0 no composite: o instante t do overlay é o instante t - a0 da footage. Amostrar a
# footage em t media outro quadro (0,62 s depois no fixture). Sem o a0 (nem passado nem no _ritmo.json da footage)
# a footage não é medida: cai no arquivo-fonte, que não depende do relógio da footage.

def test_m4_footage_e_amostrada_em_t_menos_a0(v1, monkeypatch):
    (v1 / "output" / "ad1_lk_footage_1x.mp4").write_bytes(b"x")
    vistas = []
    monkeypatch.setattr(FC, "fundo_claro_footage", lambda video, ini, fim, classe: vistas.append((ini, fim)))
    FC.marcar_grupos_claros([g(3.0, 4.0)], "ad1", "lk", [], a0=0.62)
    assert vistas == [(pytest.approx(2.38), pytest.approx(3.38))]


def test_m4_sem_a0_passado_le_o_a0_do_ritmo_da_footage(v1, monkeypatch):
    (v1 / "output" / "ad1_lk_footage_1x.mp4").write_bytes(b"x")
    (v1 / "output" / "ad1_lk_footage_1x_ritmo.json").write_text(
        '{"segs": [{"s": 0.4, "e": 5.0, "tipo": "orig"}], "total": 5.0}', encoding="utf-8")
    vistas = []
    monkeypatch.setattr(FC, "fundo_claro_footage", lambda video, ini, fim, classe: vistas.append((ini, fim)))
    FC.marcar_grupos_claros([g(3.0, 4.0)], "ad1", "lk", [])
    assert vistas == [(pytest.approx(2.6), pytest.approx(3.6))]


def test_m4_sem_a0_nenhum_a_footage_nao_e_medida_no_relogio_errado(v1, monkeypatch, capsys):
    (v1 / "output" / "ad1_lk_footage_1x.mp4").write_bytes(b"x")
    monkeypatch.setattr(FC, "fundo_claro_footage", lambda *a: pytest.fail("mediu a footage sem saber o a0"))
    vistas = []
    monkeypatch.setattr(FC, "fundo_claro", lambda arquivo, t: vistas.append(t) or False)
    mapa = [{"a": 0.0, "b": 9.0, "file": "i.mp4", "start": 0.0, "speed": 1.0, "s2": 0.0}]
    FC.marcar_grupos_claros([g(1.0, 2.0)], "ad1", "lk", mapa)
    assert vistas == [1.5]
    assert "a0" in capsys.readouterr().out
