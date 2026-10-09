"""W5.X: o invariante de legibilidade de TODO texto na tela.

    Todo texto na tela (gancho, legenda inclusive a camada apagada do karaokê, lettering e CTA) tem contraste
    >= 4,5:1 contra o fundo LOCAL, medido por pixel em volta das letras no quadro composto, em pelo menos 4
    amostras por segundo; só fica de fora o texto a menos de 0,15 s de entrar ou de sair da tela.

O render real da W5.A (avatar_e2e.mp4) teve dois defeitos que 28 gates aprovaram: o gancho branco e fino sobre o
insert claro e a camada apagada da legenda invertida, cinza sobre o insert claro (9,21 s). Cada causa de o gate antigo
não ver vira um teste aqui: tinta só com alfa >= 250, fundo pela média da faixa inteira (e faixa pulada quando um
scrim cobre a largura toda), aprovação pela mediana e uma amostra a cada 0,5 s.

Os quadros são desenhados com as fontes do repo (tests/fixtures/texto_tela.py) e compostos como o build compõe.
"""
from pathlib import Path

import pytest

from gates import contraste_texto as C
from tests.fixtures import texto_tela as T

RAIZ = Path(__file__).resolve().parents[2]
ALT, LARG = 360, 1080
ESCURO = 22              # fundo do avatar (parede escura)
MEIO = 110               # o borrado claro do insert, abaixo do limiar de inversão (119)


def medir(ov, imagem):
    return C.medir_quadro(ov, T.compor(imagem, ov))


def legenda(ov, texto="sem precisar pagar", alfa=1.0, cor=(245, 239, 230), y=180, contorno=3):
    return T.texto(ov, texto, (540, y), corpo=80, cor=cor, alfa=alfa, contorno=contorno, sombra=0.40)


def invertida(ov, texto="disponibilizado", alfa=1.0, y=180):
    return T.texto(ov, texto, (540, y), corpo=80, cor=(18, 20, 26), alfa=alfa, contorno=3,
                   cor_contorno=(255, 255, 255), alfa_contorno=0.90, sombra=0.55, cor_sombra=(255, 255, 255))


# =========================================================== o quadro: onde está o texto e contra o quê ele se lê

class TestMedirQuadro:
    def test_legenda_branca_sobre_fundo_escuro_le(self):
        r = medir(legenda(T.vazio(ALT, LARG)), T.fundo(ALT, LARG, ESCURO))
        assert r and all(p["ok"] for p in r), r
        assert min(p["razao"] for p in r) > 8

    def test_camada_apagada_e_tinta_e_reprova_sobre_meio_tom(self):
        """Causa 1: tinta só com alfa >= 250. A camada apagada (0,70) nunca era medida."""
        ov = legenda(T.vazio(ALT, LARG), alfa=0.70)
        assert (ov[..., 3] < 250).any() and C.mascara_texto(ov).any()
        r = medir(ov, T.fundo(ALT, LARG, MEIO))
        assert r and not all(p["ok"] for p in r), r

    def test_camada_apagada_invertida_sobre_claro_reprova(self):
        """O defeito dos 9,21 s: a camada apagada da tinta invertida (0,62) vira cinza sobre o insert claro."""
        r = medir(invertida(T.vazio(ALT, LARG), alfa=0.62), T.fundo(ALT, LARG, 200))
        assert r and not all(p["ok"] for p in r), r

    def test_tinta_invertida_cheia_sobre_claro_le(self):
        r = medir(invertida(T.vazio(ALT, LARG)), T.fundo(ALT, LARG, 236))
        assert r and all(p["ok"] for p in r), r

    def test_gancho_fino_sobre_scrim_e_pagina_clara_reprova(self):
        """O defeito de 0 a 2,1 s. Causa 2: o scrim cobre a largura toda, não sobra pixel de alfa zero na faixa e o
        gate antigo PULAVA a faixa. Aqui o fundo é o anel em volta da letra, com o scrim dentro."""
        ov = T.scrim_radial(ALT, LARG, (540, 180), (700, 260), 0.55)
        assert (ov[140:220, :, 3] > 12).all()              # nenhum pixel "intocado" nas linhas do texto
        ov = T.texto(ov, "virou um web designer", (540, 180), fonte=T.FONTE_FINA, corpo=72, cor=(255, 255, 255))
        r = medir(ov, T.pagina(ALT, LARG))
        assert r and not all(p["ok"] for p in r), r

    def test_gancho_em_placa_sobre_pagina_clara_le(self):
        ov = T.retangulo(T.vazio(ALT, LARG), 120, 110, 960, 250, (6, 7, 12), 0.84, raio=24)
        ov = T.texto(ov, "virou um web designer", (540, 180), fonte=T.FONTE_FINA, corpo=72, cor=(255, 255, 255))
        r = medir(ov, T.pagina(ALT, LARG))
        assert r and all(p["ok"] for p in r), r

    def test_fundo_e_local_nao_a_faixa(self):
        """Causa 2: a média da faixa inteira. Letra branca sobre um retalho claro, com o resto da faixa escuro: a
        faixa dá contraste alto; o anel em volta das letras, não."""
        img = T.fundo(ALT, LARG, ESCURO)
        img[120:240, 300:780] = 225
        r = medir(legenda(T.vazio(ALT, LARG), texto="pagar", contorno=0), img)
        assert r and not all(p["ok"] for p in r), r

    def test_meia_palavra_sobre_o_claro_reprova(self):
        img = T.fundo(ALT, LARG, ESCURO)
        img[:, 540:] = 225
        r = medir(legenda(T.vazio(ALT, LARG), texto="disponibilizado", contorno=0), img)
        assert r and not all(p["ok"] for p in r), r

    def test_contorno_sozinho_nao_segura_letra_clara_sobre_branco(self):
        """O contorno é parte da letra, não o fundo dela: branca de contorno escuro sobre página branca fica oca."""
        r = medir(legenda(T.vazio(ALT, LARG)), T.fundo(ALT, LARG, 240))
        assert r and not all(p["ok"] for p in r), r

    def test_texto_claro_na_pilula_escura_le_e_a_pilula_nao_e_texto(self):
        ov = T.scrim_radial(ALT, LARG, (540, 180), (600, 300), 0.80)
        ov = T.retangulo(ov, 260, 120, 820, 240, (10, 11, 16), 0.72, raio=60)
        so_pilula = medir(ov, T.fundo(ALT, LARG, 200))
        assert so_pilula == [], so_pilula                  # forma lisa sem letra não é texto
        ov = T.texto(ov, "SAIBA MAIS", (540, 180), corpo=66, cor=(255, 255, 255))
        r = medir(ov, T.fundo(ALT, LARG, 200))
        assert r and all(p["ok"] for p in r), r

    def test_dim_e_scrim_sozinhos_nao_sao_texto(self):
        ov = T.vazio(ALT, LARG)
        ov[..., 3] = 140                                   # o dim de tela cheia do lettering (0,55)
        assert medir(ov, T.fundo(ALT, LARG, 120)) == []
        assert medir(T.scrim_radial(ALT, LARG, (540, 180), (700, 260), 0.66), T.pagina(ALT, LARG)) == []


# =========================================================== o relógio do entregue

class TestRelogio:
    def test_o_ss_conta_do_inicio_do_arquivo(self):
        """O entregue do e2e começa o vídeo em 0,066 s e o áudio em 0,045: o `-ss t` mostra o conteúdo t - 0,021."""
        r = C.Relogio(aceleracao=1.35, a0=0.4, inicio=0.021)
        assert r.overlay(3.86) == pytest.approx((3.86 - 0.021) * 1.35 + 0.4)
        assert C.Relogio(1.35, 0.4, 0.5).overlay(0.0) == 0.0



def test_amostragem_densa():
    """Pelo menos 4 amostras por segundo na janela em que o texto existe (o gate antigo usava 2)."""
    assert C.PASSO_S <= 0.25
