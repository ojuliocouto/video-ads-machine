"""W7.Z: a troca SECA de legenda e a dessincronia de um quadro entre o overlay e o vídeo.

O gate lê o overlay num instante e o quadro entregue no mesmo instante. A composição não é exata ao quadro: com a aceleração
de 1,35 o quadro entregue vem de um quadro do overlay a até um quadro de distância do que o relógio calcula (0,033 s).
Com a troca de legenda em fade isso se escondia na dissolução; com a troca SECA (um grupo substitui o outro no mesmo
quadro) a amostra que cai no quadro da troca mede o texto NOVO do overlay contra o quadro entregue que ainda mostra o
VELHO (1,0:1 na prova: 25,40 s, 28,00 s e 29,80 s, com o vídeo limpo nos três quadros vizinhos). A leitura que vale é a de
quem lê bem num dos quadros vizinhos do overlay (mais ou menos um quadro); texto que não lê em nenhum dos três reprova."""
import numpy as np
import pytest

from gates import contraste_texto as C
from tests.fixtures import texto_tela as T

ALT, LARG = 360, 1080
ESCURO = 22
CORTE = 10.0
QUADRO = 1.0 / 30.0


def grupo(y, texto, dx=0):
    ov = T.retangulo(T.vazio(ALT, LARG), 120 + dx, y - 55, 960 + dx, y + 55, (6, 7, 12), 0.88, raio=16)
    return T.texto(ov, texto, (540 + dx, y), corpo=60, cor=(245, 239, 230))


# o texto novo cai em cima do velho, deslocado de poucos px: no quadro da troca as letras de um sobre as do outro
A, B = grupo(180, "ouro de colocar"), grupo(180, "ouro de colocar", dx=11)
FUNDO = T.fundo(ALT, LARG, ESCURO)


@pytest.fixture
def leitura(monkeypatch):
    """Overlay: A até 10,0 s, B depois (troca seca). Vídeo: o que `video_mostra(t)` disser."""
    def instalar(video_mostra):
        def ler_quadro(caminho, t, larg, alt, canais=3):
            if str(caminho) == "ov.mov":
                return (A if t < CORTE else B).copy()
            return T.compor(FUNDO, video_mostra(t))[..., :canais].copy()
        monkeypatch.setattr(C, "ler_quadro", ler_quadro)
        monkeypatch.setattr(C, "info_video", lambda caminho: (LARG, ALT, 20.0, 0.0))
    return instalar


def medir():
    return C.medir_video("v.mp4", "ov.mov", 1.0, 0.0, passo=0.1, inicio=9.8, fim=10.3, paralelo=1)


def test_quadro_entregue_um_quadro_atrasado_na_troca_seca_nao_reprova(leitura):
    leitura(lambda t: A if t < CORTE + QUADRO else B)               # o vídeo troca um quadro depois do overlay
    r = medir()
    assert r["reprovas"] == [], r["reprovas"]
    assert any(p.get("troca_seca") for p in r["transicoes"]), r["transicoes"]


def test_quadro_entregue_um_quadro_adiantado_tambem_nao_reprova(leitura):
    leitura(lambda t: A if t < CORTE - QUADRO else B)
    assert medir()["reprovas"] == []


def test_texto_que_nunca_aparece_no_video_reprova_em_todos_os_quadros(leitura):
    """O defeito de verdade: o overlay diz B depois de 10,0 s e o vídeo nunca mostra B. Fora do quadro da troca (10,0 s,
    que o vizinho anterior lê) nenhuma amostra lê."""
    leitura(lambda t: A)
    r = medir()
    assert r["reprovas"], "o texto que não aparece no vídeo precisa reprovar"
    assert {round(p["t"], 1) for p in r["reprovas"]} >= {10.1, 10.2}


def test_dessincronia_de_dois_quadros_ainda_reprova(leitura):
    """A tolerância é de UM quadro: com o vídeo dois quadros atrasado a amostra do quadro da troca mede o velho."""
    leitura(lambda t: A if t < CORTE + 2.5 * QUADRO else B)
    r = medir()
    assert r["reprovas"] == [] or all(p["t"] < CORTE + 0.12 for p in r["reprovas"])
