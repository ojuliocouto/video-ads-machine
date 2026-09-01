#!/usr/bin/env python3
"""Contrato de `fundo_claro`: onde a legenda BRANCA nao le e precisa de placa.

Nasceu de defeito medido no build 26 do jh13. O insert `pip` (tela cheia com o
apresentador num circulo) e um mockup de pagina BRANCA. A legenda branca pousou em cima
dele e o contraste no quadro entregue deu 1,52:1, contra 11,7 e 14,3 nos trechos escuros
do MESMO anuncio. O perfil de luminancia do quadro inteiro nao tem uma faixa acima de
3,6:1 fora da zona morta da UI, entao mudar a legenda de posicao nao resolve: precisa de
fundo atras do texto.

O contrato e sobre o LIMIAR, e o limiar sai da medicao, nao de gosto:
  - fonte branca (mediana ~255) -> claro
  - mockup claro (mediana ~200) -> claro
  - cinza acima do piso (mediana ~130) -> claro (contraste 3,8:1, abaixo de 4,5)
  - cinza abaixo do piso (mediana ~100) -> nao (contraste 5,6:1, le sozinha)
  - pagina de app escura (mediana ~30) -> nao

VERMELHO ANTES DE VERDE: este arquivo existe antes de `fundo_claro` ter corpo.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

from gen_ad_v2 import LIMIAR_FUNDO_CLARO, fundo_claro


def _cor(caminho, nivel, dur=2.0):
    """Gera um mp4 de cor solida com a luminancia pedida."""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", f"color=c=0x{nivel:02x}{nivel:02x}{nivel:02x}:s=640x360:d={dur}:r=25",
         "-pix_fmt", "yuv420p", str(caminho)], check=True)


class TesteFundoClaro(unittest.TestCase):

    def test_limiar_esta_onde_a_legenda_branca_para_de_ler(self):
        # contraste WCAG de tinta branca contra o fundo, na luminancia do limiar.
        # Abaixo de 4,5:1 a legenda branca precisa de placa; e ali que o limiar mora.
        lim = LIMIAR_FUNDO_CLARO / 255.0
        lin = lim / 12.92 if lim <= 0.03928 else ((lim + 0.055) / 1.055) ** 2.4
        razao = 1.05 / (lin + 0.05)
        # O limiar tem que POUSAR no piso de 4,5:1, nao perto dele: acima disso deixa
        # passar fundo que apaga a legenda, abaixo poe placa onde ela ja lia.
        self.assertAlmostEqual(razao, 4.5, delta=0.15,
                               msg=f"limiar em {LIMIAR_FUNDO_CLARO} da contraste "
                                   f"{razao:.2f}:1, e o piso de legibilidade e 4,5:1")

    def test_classifica_pelos_extremos_reais(self):
        casos = [(255, True, "pagina branca"), (200, True, "mockup claro"),
                 (130, True, "cinza acima do piso"), (100, False, "cinza abaixo do piso"),
                 (30, False, "app escuro")]
        with tempfile.TemporaryDirectory() as td:
            for nivel, esperado, nome in casos:
                p = Path(td) / f"c{nivel}.mp4"
                _cor(p, nivel)
                with self.subTest(fundo=nome):
                    self.assertEqual(fundo_claro(str(p), 0.0), esperado,
                                     f"{nome} (luminancia {nivel}) classificado errado")

    def test_arquivo_que_nao_da_pra_medir_nao_vira_placa(self):
        # falha de medicao nao pode INVENTAR placa: sem numero, mantem o visual padrao
        self.assertFalse(fundo_claro("/caminho/que/nao/existe.mp4", 0.0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
