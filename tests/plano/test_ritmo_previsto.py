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


# --- W7.Z: o layout é o do SEGMENTO, não só o do bloco --------------------------------------------------------------
# Com o split por padrão, todo insert horizontal é bloco `split`, mas o ritmo alterna as visitas entre split e cheio. A
# visita em tela cheia que volta ao apresentador É corte (o apresentador não estava na tela); a em split não é. Contar pelo
# bloco inteiro derrubou a previsão de 19,5 para 11,1 cortes/min e acendeu uma pendência de ritmo que o render não tem.

def _insert_alternado(layout_do_bloco, layout_da_visita):
    blocos = [{"i": 0, "tipo": "insert", "layout": layout_do_bloco, "s": 0.0, "e": 4.0},
              {"i": 1, "tipo": "apresentador", "s": 4.0, "e": 6.0}]
    segs = [{"tipo": "insert", "s": 0.0, "e": 4.0, "layout": layout_da_visita, "bloco": 0},
            {"tipo": "orig", "s": 4.0, "e": 6.0, "bloco": 1}]
    return segs, blocos


def test_visita_em_tela_cheia_de_um_bloco_split_conta_como_corte_ao_voltar_ao_apresentador():
    segs, blocos = _insert_alternado("split", "cheio")
    assert M.cortes_previstos(segs, blocos) == [4.0]


def test_visita_em_split_de_um_bloco_split_nao_conta():
    segs, blocos = _insert_alternado("split", "split")
    assert M.cortes_previstos(segs, blocos) == []


def test_bloco_cheio_escrito_conta_mesmo_que_o_ritmo_marque_split_na_visita():
    segs, blocos = _insert_alternado("cheio", "split")
    assert M.cortes_previstos(segs, blocos) == [4.0]


def test_visita_sem_layout_vale_o_do_bloco():
    segs, blocos = _insert_alternado("split", None)
    segs[0].pop("layout")
    assert M.cortes_previstos(segs, blocos) == []


def test_troca_de_layout_dentro_do_mesmo_insert_e_corte():
    """split -> cheio no mesmo bloco troca ~60% dos pixels e a detecção de cena registra (ritmo.LAYOUTS_INSERT): é corte.
    Mesmo layout nas duas fatias é a continuação do mesmo plano e não é."""
    blocos = [{"i": 0, "tipo": "insert", "layout": "split", "s": 0.0, "e": 5.0}]
    trocou = [{"tipo": "insert", "s": 0.0, "e": 3.0, "layout": "split", "bloco": 0},
              {"tipo": "insert", "s": 3.0, "e": 5.0, "layout": "cheio", "bloco": 0}]
    igual = [{"tipo": "insert", "s": 0.0, "e": 3.0, "layout": "split", "bloco": 0},
             {"tipo": "insert", "s": 3.0, "e": 5.0, "layout": "split", "bloco": 0}]
    assert M.cortes_previstos(trocou, blocos) == [3.0]
    assert M.cortes_previstos(igual, blocos) == []
