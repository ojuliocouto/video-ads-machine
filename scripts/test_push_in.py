#!/usr/bin/env python3
"""Contrato do PUSH-IN nas gravacoes de tela.

Autorizacao do Julio (28/08/2026), em resposta a pergunta fechada: o print entra INTEIRO
primeiro e depois a camera avanca para a regiao que a fala descreve. E excecao NOMEADA a
ordem de 26/08 ("o video todo que aparece e o que precisa"), valida so para gravacao de
tela, e existe por um motivo medido: um asset 16:9 entrando inteiro num quadro 9:16 nao
passa de 31,6% do quadro (teto fisico, `esc_max = 1080/largura`), e hoje ja entregamos
32,2%. Sem push-in, legibilidade so subiria com gravacao nova, que o Julio recusou.

O contrato:
  1. Em t=0 o zoom e 1,0. O asset aparece INTEIRO. Isso nao e negociavel: e o que separa
     push-in de recorte, e recorte continua proibido.
  2. O avanco e proporcional a quanto o asset ENCOLHEU na tela. Asset que ja entra
     grande quase nao avanca; asset esmagado avanca mais. O fator sai da escala medida,
     nao de gosto.
  3. Existe teto. Avanco demais vira recorte por outro nome.
  4. O foco e MEDIDO no asset (centroide do conteudo), nunca o centro por padrao: uma
     pagina tem o conteudo em cima, e avancar no centro geometrico avanca no vazio.
"""
import unittest

from push_in import ZOOM_ALVO, ZOOM_MAX, fator_push_in


class TestePushIn(unittest.TestCase):

    def test_comeca_inteiro(self):
        # o contrato de t=0 e do filtro; aqui garanto que o FATOR nunca e menor que 1,
        # senao o asset entraria ja recortado ou encolhendo
        for esc in (0.30, 0.438, 0.525, 0.787, 1.0):
            with self.subTest(escala=esc):
                self.assertGreaterEqual(fator_push_in(esc), 1.0)

    def test_avanco_proporcional_ao_esmagamento(self):
        # gal_3420092b entra a 0,438 (2304px de largura) e e o mais esmagado da leva;
        # rec_taste_skill entra a 0,787 e quase nao precisa
        self.assertGreater(fator_push_in(0.438), fator_push_in(0.525))
        self.assertGreater(fator_push_in(0.525), fator_push_in(0.787))

    def test_asset_que_ja_entra_grande_nao_avanca(self):
        # 0,787 * 1,0 ja passa do alvo, entao nao ha o que corrigir: push-in aqui seria
        # movimento decorativo, e movimento sem motivo e o que faz peca parecer gerada
        self.assertEqual(fator_push_in(0.787), 1.0)
        self.assertEqual(fator_push_in(0.95), 1.0)

    def test_respeita_o_teto(self):
        # asset absurdamente esmagado nao autoriza avanco infinito: acima do teto o
        # push-in vira recorte, que e justamente o que a ordem de 26/08 proibiu
        self.assertLessEqual(fator_push_in(0.05), ZOOM_MAX)
        self.assertLessEqual(fator_push_in(0.20), ZOOM_MAX)

    def test_o_alvo_e_o_que_governa_a_conta(self):
        # abaixo do teto, o fator leva a escala efetiva exatamente ao alvo
        esc = 0.50
        self.assertAlmostEqual(esc * fator_push_in(esc), ZOOM_ALVO, places=6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
