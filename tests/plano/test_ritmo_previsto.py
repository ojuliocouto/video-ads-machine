"""W5.X, pendência (a) da W5.A: o ritmo que o plano promete tem que bater com o que o render entrega.

No e2e da W5.A o plano previu 27,2 cortes/min e o medidor de ritmo mediu 18,1 no arquivo entregue (4 cortes em
13,3 s). O plano contava TODA fronteira de plano como corte, e duas não mudam a imagem (conferido com
medir_ritmo.cortes_confirmados no render real: confirmados 2,43, 5,27, 6,81 e 8,77 s; recusados 3,85 e 11,20 s):

  - apresentador -> apresentador: é salto de escala do mesmo plano (o zoom alterna a base), não corte;
  - insert em tela dividida -> apresentador: o apresentador já estava na tela, no painel de baixo.

Invariante: o plano conta como corte só a fronteira em que ENTRA na tela conteúdo que não estava nela, e a previsão
fica a até 15% do medido no render.
"""
import pytest

from plano import medir as M

ACEL = 1.35
A0 = 0.4
# os blocos e planos do e2e da W5.A (render real): insert, apresentador, apresentador, insert, apresentador,
# insert em split, cta (apresentador)
BLOCOS = [{"i": 0, "tipo": "insert", "layout": "cheio", "s": 0.4, "e": 3.68},
          {"i": 1, "tipo": "apresentador", "s": 3.68, "e": 5.6},
          {"i": 2, "tipo": "apresentador", "s": 5.6, "e": 7.52},
          {"i": 3, "tipo": "insert", "layout": "cheio", "s": 7.52, "e": 9.6},
          {"i": 4, "tipo": "apresentador", "s": 9.6, "e": 12.24},
          {"i": 5, "tipo": "insert", "layout": "split", "s": 12.24, "e": 15.52},
          {"i": 6, "tipo": "cta", "s": 15.52, "e": 17.68}]
SEGS = [{"tipo": "insert" if b["tipo"] == "insert" else "orig", "s": b["s"], "e": b["e"]} for b in BLOCOS]
MEDIDO_NO_RENDER = 18.1        # medir_ritmo no avatar_e2e.mp4 (4 cortes em 13,3 s)


def test_corte_e_so_onde_entra_conteudo_novo():
    assert M.cortes_previstos(SEGS, BLOCOS) == [3.68, 7.52, 9.6, 12.24]


def test_salto_de_escala_entre_apresentadores_nao_e_corte():
    blocos = [{"i": 0, "tipo": "apresentador", "s": 0.0, "e": 2.0}, {"i": 1, "tipo": "apresentador", "s": 2.0, "e": 4.0}]
    segs = [{"tipo": "orig", "s": 0.0, "e": 2.0}, {"tipo": "orig", "s": 2.0, "e": 4.0}]
    assert M.cortes_previstos(segs, blocos) == []


def test_previsao_do_plano_fica_a_ate_15_por_cento_do_render():
    r = M._ritmo_entregue(SEGS, 17.68 - A0, ACEL, BLOCOS)
    assert abs(r["cortes_min"] - MEDIDO_NO_RENDER) / MEDIDO_NO_RENDER <= 0.15, r
