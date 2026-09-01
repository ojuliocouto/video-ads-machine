#!/usr/bin/env python3
"""Contrato da transicao entre dois planos do APRESENTADOR (29/08/2026).

Defeito que o Julio achou vendo o anuncio e mandou por WhatsApp: "0:56, 0:58, tem uma
falha visual na transicao". Extrai os quadros de 55,8s a 58,4s a cada 0,1s e o de
t=56,03s mostra uma FAIXA ESTREITA do plano anterior colada na borda esquerda, com o
plano novo ocupando o resto: um deslize pego no meio do caminho.

Deslize entre plano de insert e plano de apresentador funciona, porque a imagem muda
inteira e o movimento explica a troca. Entre DOIS planos do mesmo apresentador, no mesmo
fundo roxo e quase no mesmo enquadramento, nao ha o que o deslize explique: a tela parece
rasgar. Foi por isso que ele leu como falha e nao como transicao.

A regra: quando os dois lados sao imagem do apresentador (nenhum e insert, logo ou logo
de lettering), o corte e SECO. `lettering` conta como apresentador, porque a footage por
baixo continua sendo ele; so o texto por cima muda.
"""
import unittest

from produzir_transicao import XF_SECO_TIPO, corte_seco_entre, tipo_de_transicao


def _b(tipo):
    return {"type": tipo, "narr": ""}


class TesteTransicaoAvatar(unittest.TestCase):

    def test_avatar_para_avatar_e_seco(self):
        for saida in ("orig", "lettering"):
            for entrada in ("orig", "lettering"):
                with self.subTest(de=saida, para=entrada):
                    self.assertTrue(corte_seco_entre(_b(saida), _b(entrada)))

    def test_insert_de_qualquer_lado_mantem_a_transicao(self):
        self.assertFalse(corte_seco_entre(_b("orig"), _b("insert")))
        self.assertFalse(corte_seco_entre(_b("insert"), _b("orig")))
        self.assertFalse(corte_seco_entre(_b("insert"), _b("insert")))

    def test_logo_mantem_a_transicao(self):
        self.assertFalse(corte_seco_entre(_b("orig"), _b("logo")))
        self.assertFalse(corte_seco_entre(_b("lettering_logo"), _b("orig")))

    def test_o_tipo_no_corte_seco_nao_desliza(self):
        # deslize e o que produz a faixa; num corte seco o tipo tem que ser um que nao
        # empurre a imagem, senao a duracao curta so esconde o defeito em vez de tirar
        t = tipo_de_transicao(_b("orig"), _b("orig"), 3)
        self.assertEqual(t, XF_SECO_TIPO)
        self.assertNotIn("slide", t)
        self.assertNotIn("smooth", t)

    def test_entrada_de_insert_tambem_e_seca(self):
        # ESTE TESTE MUDOU DE LADO (29/08/2026). Ele exigia que a entrada de insert
        # ALTERNASSE o lado do deslize, pra dar ritmo. A varredura do anuncio inteiro
        # mostrou que essa regra era o defeito: entrada de insert corre em 0,08s, dois
        # quadros, e deslize em dois quadros nao le como movimento, le como quadro
        # rasgado. Sobraram tres assim, em t=11,93s, 17,93s e 28,70s, todos com meia
        # tela de cada plano. Ritmo nao justifica quadro partido.
        for i in (2, 3):
            with self.subTest(i=i):
                self.assertEqual(tipo_de_transicao(_b("orig"), _b("insert"), i),
                                 XF_SECO_TIPO)

    def test_alternancia_sobrevive_onde_ha_deslize_de_verdade(self):
        # a alternancia continua valendo onde a transicao dura o bastante pra ser lida
        # como movimento: volta pro apresentador vindo de um insert
        a = tipo_de_transicao(_b("insert"), _b("orig"), 2)
        b = tipo_de_transicao(_b("insert"), _b("orig"), 3)
        self.assertNotEqual(a, b)
        self.assertIn("smooth", a)


if __name__ == "__main__":
    unittest.main(verbosity=2)
