"""W5.X: o gate_camera media o punch rastreando pontos de textura no arquivo ENTREGUE, e o punch cai na KEY, com o
lettering na tela. As letras paradas do overlay são os cantos mais fortes do quadro: o rastreador seguia o texto e
media escala 1,0 (\"cresceu -0,0%\") num punch que a footage tem (o rosto vai de 481 a 587 px, +22%, medido no
segundo render da W5.X). Invariante: o ganho do punch se mede só na IMAGEM, com o texto do overlay mascarado."""
import numpy as np

from gates import gate_camera
from tests.fixtures import texto_tela as T


def test_mascara_tira_o_texto_do_overlay(tmp_path):
    ov = T.texto(T.vazio(360, 1080), "O MELHOR", (540, 180), corpo=104, cor=(255, 255, 255))
    o = T.gravar_overlay([ov] * 10, tmp_path / "ov.mov", 10)
    rel = {"aceleracao": 1.0, "a0": 0.0}
    m = gate_camera.mascaras_sem_texto(str(o), [0.2, 0.5], rel, (36, 120))
    assert len(m) == 2 and m[0].shape == (36, 120) and m[0].dtype == np.uint8
    assert m[0][18, 60] == 0              # o miolo do texto está fora
    assert m[0][2, 2] == 255              # o canto vazio fica


def test_rodar_aceita_o_overlay():
    import inspect
    assert "overlay" in inspect.signature(gate_camera.rodar).parameters
