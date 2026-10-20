"""O relógio do gate erra até dois quadros do overlay, e texto em movimento rápido reprovava sem defeito (20/10/2026).

O ensaio da demo com avatar (demo1-avatar.mp4) reprovou nas 4 rodadas com o gancho legível a olho:
`t=0.20s x 384-505 y1051-1134 1.00:1 (tinta 0.981, fundo 0.982)` e uma legenda em t=7,80 s (troca seca). Medido no
mp4: o `-ss 0.20` do entregue mostra o gancho do overlay de cerca de 0,18 s, e o relógio lê o overlay em 0,2417 s, que o
`-ss` do overlay arredonda para o quadro de 0,2667 s. São dois quadros do overlay de atraso. O gancho entra subindo
15 px por quadro do overlay, com haste de 16 a 18 px: dois quadros de erro põem a máscara do overlay fora da letra do
entregue (tinta e fundo da mesma cor, 1,00:1). Com o overlay dois quadros antes, a mesma amostra mede 12,09:1.

O conserto mede o texto contra o fundo REAL: quando um pedaço reprova, o gate procura, até REALINHA_QUADROS quadros do
overlay para cada lado, o quadro cujo texto CASA com o quadro entregue (escolhe pelo casamento dos pixels de tinta,
nunca por quem passa) e mede de novo com ele. Texto claro sobre fundo claro de verdade continua reprovando: casado ou não,
a letra não se separa do fundo."""
import numpy as np
import pytest

from gates import contraste_texto as C
from tests.fixtures import texto_tela as T

ALT, LARG = 360, 1080
ESCURO = 22
CLARO = 236
QUADRO = 1.0 / 30.0
ATRASO = 2                 # quadros do overlay: o erro medido no demo1-avatar
REALINHA = 3               # a janela de busca do conserto (C.REALINHA_QUADROS)


def _indice(t):
    return int(np.floor(t * 30.0 + 1e-6))


# a subida medida da linha "FUNCIONÁRIO" no overlay do demo1-avatar, quadro a quadro (px acima da posição inicial):
# parada até o quadro 4, depois 12, 12, 27, 42, 42 (15 px por quadro no pico), e assenta em 62 px
SUBIDA = (0, 0, 0, 0, 0, 12, 12, 27, 42, 42, 47, 56, 56, 59, 62)


def gancho(indice, cor=(245, 239, 230)):
    """O gancho entrando como no demo1-avatar (SUBIDA), sem placa nem contorno, depois parado."""
    y = 420 - SUBIDA[min(max(indice, 0), len(SUBIDA) - 1)]
    return T.texto(T.vazio(ALT * 2, LARG), "FUNCIONÁRIO IA", (540, y), corpo=90, cor=cor)


@pytest.fixture
def leitura(monkeypatch):
    """Overlay: o gancho no quadro do relógio. Vídeo: o gancho `atraso` quadros antes, sobre `fundo`."""
    def instalar(fundo, atraso=ATRASO, cor=(245, 239, 230), sem_texto=False):
        img = T.fundo(ALT * 2, LARG, fundo)

        def ler_quadro(caminho, t, larg, alt, canais=3):
            if str(caminho) == "ov.mov":
                return gancho(_indice(max(0.0, t)), cor).copy()
            if sem_texto:
                return img[..., :canais].copy()
            return T.compor(img, gancho(_indice(max(0.0, t)) - atraso, cor))[..., :canais].copy()
        monkeypatch.setattr(C, "ler_quadro", ler_quadro)
        monkeypatch.setattr(C, "info_video", lambda caminho: (LARG, ALT * 2, 2.0, 0.0))
    return instalar


def medir():
    return C.medir_video("v.mp4", "ov.mov", 1.0, 0.0, passo=QUADRO, inicio=0.1, fim=0.45, paralelo=1)


def test_gancho_subindo_com_o_video_dois_quadros_atras_nao_reprova(leitura):
    """O falso positivo do demo1-avatar: legível no vídeo, reprovado pelo relógio."""
    leitura(ESCURO)
    r = medir()
    assert r["reprovas"] == [], r["reprovas"]
    assert r.get("realinhados"), "o gate tem de dizer que realinhou, e quantos quadros"
    # o vídeo está atrás do relógio: o quadro que casa é sempre um quadro ANTERIOR do overlay (a subida tem quadros
    # repetidos, 12 12 e 42 42, então o empate pode cair em -1 ou -2; nunca à frente)
    assert all(-REALINHA <= p["realinhado_quadros"] < 0 for p in r["realinhados"]), r["realinhados"]


def test_sem_realinhar_o_mesmo_caso_reprovava(leitura, monkeypatch):
    """Prova de que o teste acima mede o defeito: sem a busca do quadro que casa, o caso reprova (1,0:1)."""
    leitura(ESCURO)
    monkeypatch.setattr(C, "REALINHA_QUADROS", 0)
    assert medir()["reprovas"], "sem realinhar o gancho em movimento precisa reprovar"


def test_gancho_claro_sobre_fundo_claro_continua_reprovando(leitura):
    """O lado de lá: texto claro sobre fundo claro de verdade, com o mesmo movimento e o mesmo atraso, reprova."""
    leitura(CLARO)
    r = medir()
    assert r["reprovas"], "texto claro sobre fundo claro não lê, realinhado ou não"


def test_gancho_claro_sobre_fundo_claro_alinhado_reprova(leitura):
    leitura(CLARO, atraso=0)
    assert medir()["reprovas"]


def test_texto_que_o_video_nao_mostra_reprova(leitura):
    """O overlay diz que há gancho e o vídeo não mostra texto nenhum: nenhum quadro da janela casa melhor que o do
    relógio, a medida fica a do relógio e reprova em toda amostra."""
    leitura(ESCURO, sem_texto=True)
    r = medir()
    assert {p["t"] for p in r["reprovas"]} == {t for t, _p in r["amostras"]}, r["reprovas"]
    assert not r["realinhados"]


def test_erro_de_alinhamento_casa_no_quadro_certo():
    """A escolha é pelo casamento dos pixels de tinta do overlay com o entregue, não pelo contraste."""
    img = T.fundo(ALT * 2, LARG, ESCURO)
    q = T.compor(img, gancho(5))
    caixa = (0, 0, LARG, ALT * 2)
    erros = {i: C.erro_alinhamento(gancho(i), q, caixa) for i in range(2, 9)}
    assert min(erros, key=erros.get) == 5, erros
    assert erros[5] < 0.5 * erros[7], erros


# =========================================================== a troca seca com dois quadros de atraso (7,80 s do ensaio)

CORTE = 10.0


def _grupo(texto):
    ov = T.retangulo(T.vazio(ALT, LARG), 120, 125, 960, 235, (6, 7, 12), 0.88, raio=16)
    return T.texto(ov, texto, (540, 180), corpo=60, cor=(245, 239, 230))


VELHA, NOVA = _grupo("um editor de vídeo,"), _grupo("um social media,")


@pytest.fixture
def troca(monkeypatch):
    """Overlay: VELHA até 10,0 s, NOVA depois (troca seca). Vídeo: troca `atraso` quadros depois, ou nunca."""
    def instalar(atraso, nunca=False):
        img = T.fundo(ALT, LARG, ESCURO)

        def ler_quadro(caminho, t, larg, alt, canais=3):
            if str(caminho) == "ov.mov":
                return (VELHA if t < CORTE else NOVA).copy()
            velha = nunca or t < CORTE + atraso * QUADRO
            return T.compor(img, VELHA if velha else NOVA)[..., :canais].copy()
        monkeypatch.setattr(C, "ler_quadro", ler_quadro)
        monkeypatch.setattr(C, "info_video", lambda caminho: (LARG, ALT, 20.0, 0.0))
    return instalar


def medir_troca():
    # amostras no MEIO dos quadros (9,9 + meio quadro, de quadro em quadro): nenhuma cai em cima do corte
    return C.medir_video("v.mp4", "ov.mov", 1.0, 0.0, passo=QUADRO, inicio=9.9 + QUADRO / 2, fim=10.25, paralelo=1)


def test_troca_seca_com_o_video_dois_quadros_atras_nao_reprova(troca):
    troca(2.2)
    r = medir_troca()
    assert r["reprovas"] == [], r["reprovas"]
    assert any(p["realinhado_quadros"] == -2 for p in r["realinhados"]), r["realinhados"]


def test_troca_seca_dois_quadros_atras_reprovava_sem_realinhar(troca, monkeypatch):
    troca(2.2)
    monkeypatch.setattr(C, "REALINHA_QUADROS", 0)
    assert medir_troca()["reprovas"]


def test_legenda_nova_que_o_video_nunca_mostra_reprova(troca):
    """O defeito de verdade continua: o vídeo nunca mostra a legenda nova. Depois da janela de busca nada casa."""
    troca(0, nunca=True)
    r = medir_troca()
    assert {round(p["t"], 2) for p in r["reprovas"]} >= {10.15, 10.18, 10.22}, sorted(p["t"] for p in r["reprovas"])


def _apagada(texto, placa=False):
    """A legenda nova do karaokê no primeiro quadro: a camada apagada (0,65 de opacidade), sem pixel opaco na letra.
    `placa`: sobre a pílula escura de 0,88 (a troca de uma legenda para a outra muda pouco o alfa: não é dissolução)."""
    ov = T.vazio(ALT, LARG)
    if placa:
        ov = T.retangulo(ov, 120, 125, 960, 235, (6, 7, 12), 0.88, raio=16)
    return T.texto(ov, texto, (540, 180), corpo=60, cor=(245, 239, 230), alfa=0.65)


def test_troca_seca_para_legenda_apagada_dois_quadros_atras_nao_reprova(monkeypatch):
    """O 7,80 s do ensaio: a legenda nova entra na camada apagada do karaokê (alfa 158 a 178). Medido no mp4: do
    quadro -1 em diante, a caixa da legenda tem 43 a 852 pixels opacos e 19.049 com alfa >= 100; casar só pelos opacos
    deixava o relógio (4,06) ganhar do quadro certo (2,98). O casamento usa todo pixel de tinta e o intervalo que o
    alfa permite: com alfa 0,65 a letra branca nunca fica mais escura que 0,65 x 245 no entregue, seja qual for o fundo."""
    velha, nova = _apagada("um editor de vídeo,", placa=True), _apagada("um social media,", placa=True)
    velha = T.texto(velha, "um editor de vídeo,", (540, 180), corpo=60, cor=(245, 239, 230))     # a velha já acesa
    assert not (nova[..., 3] >= C.CAIXA_ALFA).any(), "a legenda nova não pode ter pixel opaco (é o caso do ensaio)"
    img = T.fundo(ALT, LARG, ESCURO)

    def ler_quadro(caminho, t, larg, alt, canais=3):
        if str(caminho) == "ov.mov":
            return (velha if t < CORTE else nova).copy()
        return T.compor(img, velha if t < CORTE + 2.2 * QUADRO else nova)[..., :canais].copy()
    monkeypatch.setattr(C, "ler_quadro", ler_quadro)
    monkeypatch.setattr(C, "info_video", lambda caminho: (LARG, ALT, 20.0, 0.0))
    r = medir_troca()
    assert r["reprovas"] == [], r["reprovas"]
    monkeypatch.setattr(C, "REALINHA_QUADROS", 0)
    assert medir_troca()["reprovas"], "sem realinhar o caso precisa reprovar (é o 7,80 s do ensaio)"


def test_erro_de_alinhamento_usa_a_camada_apagada():
    """Sem pixel opaco nenhum, a camada apagada ainda casa: o quadro que o vídeo mostra tem erro perto de zero."""
    img = T.fundo(ALT, LARG, ESCURO)
    a, b = _apagada("um editor de vídeo,"), _apagada("um social media,")
    assert not (a[..., 3] >= C.CAIXA_ALFA).any()
    q = T.compor(img, a)
    caixa = (0, 0, LARG, ALT)
    ea, eb = C.erro_alinhamento(a, q, caixa), C.erro_alinhamento(b, q, caixa)
    assert ea is not None and eb is not None
    assert ea < 2.0 and eb > 10 * max(ea, 1.0), (ea, eb)
