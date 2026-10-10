"""W7.Y: a cadeia da footage não deriva do relógio quando o anúncio tem muitos cortes.

Na prova como aluno, com 23 planos e 8 voltas pro apresentador (whip de 0,08 s), a footage saiu com 57,57 s e a
timeline dizia 57,76 s: `gate_relogio` reprovou ("duração medida da footage"). A conta: cada segmento arredonda para
quadros inteiros (perdeu 2,8 quadros no total) e cada whip sobrepõe 0,08 s (2,4 quadros) com uma cauda de 2 quadros
(perdeu 3,2). Antes eram poucos cortes e a soma ficava dentro de 1 quadro; com ritmo de 16+ cortes/min o erro acumula.

Invariante: em todo corte, a posição da cadeia fica a menos de 1 quadro da posição da timeline, e o total também.
"""
import pytest

from footage import cadeia as CA

FPS = CA.FPS
# os 23 planos do render da prova (tipo, início, fim), em segundos de footage 1x
PLANOS = [("insert", 0.4, 3.4), ("insert", 3.4, 5.44), ("insert", 5.44, 9.6), ("orig", 9.6, 10.88),
          ("insert", 10.88, 13.38), ("orig", 13.38, 15.6), ("insert", 15.6, 18.1), ("orig", 18.1, 19.64),
          ("insert", 19.64, 22.14), ("orig", 22.14, 23.68), ("insert", 23.68, 26.18), ("orig", 26.18, 28.08),
          ("orig", 28.08, 31.093), ("orig", 31.093, 34.107), ("orig", 34.107, 37.12), ("insert", 37.12, 41.12),
          ("orig", 41.12, 42.8), ("insert", 42.8, 45.3), ("orig", 45.3, 46.88), ("insert", 46.88, 49.38),
          ("orig", 49.38, 53.2), ("orig", 53.2, 55.68), ("orig", 55.68, 58.16)]


def montagem(planos):
    blocos = [{"type": t, "narr": "x"} for t, _, _ in planos]
    spans = [(s, e) for _, s, e in planos]
    return blocos, spans


def posicoes_da_cadeia(blocos, spans, tr):
    """Onde cada corte cai na cadeia (em segundos), pela aritmética do grafo: soma dos K menos as sobreposições."""
    kf = CA.contagem_de_quadros(blocos, spans, tr)
    pos, acc = [], 0.0
    for i, k in enumerate(kf[:-1]):
        acc += k / FPS - CA.xf_dur(blocos[i + 1], blocos[i], tr)
        pos.append(acc)
    return pos, acc + kf[-1] / FPS


def test_nenhum_corte_deriva_mais_de_um_quadro_do_relogio_da_timeline():
    blocos, spans = montagem(PLANOS)
    tr = CA.Transicao.do_ambiente({})
    pos, total = posicoes_da_cadeia(blocos, spans, tr)
    a0 = spans[0][0]
    for i, p in enumerate(pos):
        assert abs(p - (spans[i][1] - a0)) < 1.0 / FPS, (i, p, spans[i][1] - a0)
    assert abs(total - (spans[-1][1] - a0)) < 1.0 / FPS, total


def test_a_aritmetica_do_grafo_e_a_da_contagem():
    blocos, spans = montagem(PLANOS)
    tr = CA.Transicao.do_ambiente({})
    g = CA.montar_grafo(blocos, spans, tr, ini=[0] * len(blocos))
    _, total = posicoes_da_cadeia(blocos, spans, tr)
    assert sum(g["durs"]) - g["xf_total"] == pytest.approx(total)


@pytest.mark.parametrize("xf", ["0.08", "0.20"])
def test_sem_deriva_com_whip_longo_e_curto(xf):
    blocos, spans = montagem(PLANOS)
    tr = CA.Transicao.do_ambiente({"VAM_XF": xf})
    pos, total = posicoes_da_cadeia(blocos, spans, tr)
    assert abs(total - (spans[-1][1] - spans[0][0])) < 1.0 / FPS
