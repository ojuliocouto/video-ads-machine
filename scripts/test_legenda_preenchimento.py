#!/usr/bin/env python3
"""Contrato da legenda por PREENCHIMENTO linear (karaoke), 29/08/2026.

Pedido do Julio, por audio: "nao gosto desse estilo de legenda onde a legenda meio que
sobe, fica pulando. Eu gosto quando e uma cor, vai preenchendo ela, de forma linear".

O salto vertical saiu. No lugar entra o preenchimento: cada palavra tem DUAS camadas de
texto sobrepostas, a de baixo apagada e a de cima acesa, e a de cima e revelada da
esquerda para a direita enquanto a palavra e falada.

Por que duas camadas e nao `background-clip: text`: com background-clip a cor do texto
vira `transparent`, e se o recurso falhar no renderizador a palavra some. Aqui o pior
caso e a camada de cima aparecer inteira de uma vez, ou seja a legenda continua legivel.
Legenda que some e defeito grave; legenda sem animacao e so sem graca.

Este teste cobre a ESTRUTURA que o build_timeline gera. O movimento em si e do GSAP e se
confere no quadro, no MOV renderizado.
"""
import re
import unittest

from build_timeline import _render_captions_html

GRUPO = [{
    "start": 1.0, "end": 2.5,
    "words": [
        {"text": "pagina", "start": 1.0, "end": 1.6, "kw": False},
        {"text": "completamente", "start": 1.6, "end": 2.5, "kw": True},
    ],
}]


class TesteLegendaPreenchimento(unittest.TestCase):

    def setUp(self):
        self.html = _render_captions_html(GRUPO)

    def test_cada_palavra_tem_as_duas_camadas(self):
        for p in ("pagina", "completamente"):
            with self.subTest(palavra=p):
                self.assertIn(f'<span class="base">{p}</span>', self.html)
                self.assertIn(f'<span class="fill">{p}</span>', self.html)

    def test_o_texto_aparece_duas_vezes_por_palavra_e_so_duas(self):
        # tres vezes seria camada sobrando; uma vez seria a camada de cima faltando
        for p in ("pagina", "completamente"):
            with self.subTest(palavra=p):
                self.assertEqual(len(re.findall(f">{p}<", self.html)), 2)

    def test_tempo_da_palavra_fica_no_span_de_fora(self):
        # o GSAP le data-w-start/data-w-end no `.cw`; se o atributo descer para a camada
        # interna, o preenchimento nunca e animado e a legenda fica parada
        m = re.search(r'<span class="cw[^"]*" data-w-start="1\.000" data-w-end="1\.600">',
                      self.html)
        self.assertIsNotNone(m, "o .cw perdeu os atributos de tempo")

    def test_a_palavra_chave_continua_marcada(self):
        self.assertIn('class="cw kw"', self.html)

    def test_nao_sobrou_palavra_de_camada_unica(self):
        # qualquer `.cw` sem `.fill` dentro nao seria animado e ficaria apagado na tela
        for bloco in re.findall(r'<span class="cw[^"]*"[^>]*>(.*?)</span>\s*(?=<span class="cw|\s*</div>)',
                                self.html, re.S):
            self.assertIn('class="fill"', bloco)


if __name__ == "__main__":
    unittest.main(verbosity=2)
