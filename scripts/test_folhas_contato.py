#!/usr/bin/env python3
"""Teste de folhas_contato.py. ESCRITO ANTES do modulo, tem que falhar antes de passar.

Por que existe: em 29/08/2026 um anuncio foi avaliado olhando 8 quadros isolados e
passou; so quando alguem assistiu o video inteiro o diagnostico mudou. A folha de
contato existe pra ninguem mais avaliar anuncio sem ter visto o filme inteiro.

Rodar: python3 -m pytest test_folhas_contato.py -q
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
for _p in (str(RAIZ / "scripts"), str(RAIZ)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PIL import Image

import folhas_contato as FC
from tests.fixtures import sinteticos as SIN  # noqa: E402


class TesteFolhasContato(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # 6s: vermelho 0-2s, verde 2-4s, azul 4-6s. Dois cortes nítidos, em 2s e 4s.
        SC = Path(tempfile.mkdtemp(prefix="vam_folhas_"))
        cls.addClassCleanup(shutil.rmtree, SC, True)
        cls.video = SIN.video_cores(SC / "sintetico_6s.mp4", cores=("red", "green", "blue"),
                                    dur_cada=2.0, tamanho="320x240", fps=25)
        cls.pasta_saida = SC / "folhas_out"

    def test_gerar_folhas_produz_os_dois_pngs_com_medidas_corretas(self):
        p_inteira, p_tiras = FC.gerar_folhas(self.video, self.pasta_saida)

        self.assertTrue(Path(p_inteira).exists(), f"faltou {p_inteira}")
        self.assertTrue(Path(p_tiras).exists(), f"faltou {p_tiras}")

        self.assertEqual(Path(p_inteira).name, "sintetico_6s_folha_inteira.png")
        self.assertEqual(Path(p_tiras).name, "sintetico_6s_tiras_corte.png")

        with Image.open(p_inteira) as im:
            w, h = im.size
        self.assertEqual(w, 1080, "5 colunas de 216px")
        self.assertEqual(h % 384, 0, f"altura {h} tem que ser multiplo de 384")
        self.assertGreaterEqual(h // 384, 1, "pelo menos uma linha")

        with Image.open(p_tiras) as im:
            w2, h2 = im.size
        self.assertEqual(h2 % 234, 0, f"altura {h2} tem que ser multiplo de 234")
        self.assertGreaterEqual(h2 // 234, 1, "pelo menos um corte medido")


if __name__ == "__main__":
    unittest.main(verbosity=2)
