#!/usr/bin/env python3
"""Teste de folhas_contato.py. ESCRITO ANTES do modulo, tem que falhar antes de passar.

Por que existe: em 29/08/2026 um anuncio foi avaliado olhando 8 quadros isolados e
passou; so quando alguem assistiu o video inteiro o diagnostico mudou. A folha de
contato existe pra ninguem mais avaliar anuncio sem ter visto o filme inteiro.

Rodar: python3 -m pytest test_folhas_contato.py -q
"""
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from PIL import Image

import folhas_contato as FC

SC = Path("/private/tmp/claude-501/-Users-ojuliocouto--claude-worktrees-video-editing-skill-optimization-6d0679/77358218-94e0-4420-8a73-b3c2ced0fd83/scratchpad")
SC.mkdir(parents=True, exist_ok=True)


def _gerar_video_sintetico(destino):
    """6s: vermelho 0-2s, verde 2-4s, azul 4-6s. Dois cortes nitidos, em 2s e 4s."""
    partes = []
    for i, cor in enumerate(("red", "green", "blue")):
        p = SC / f"_parte{i}.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
             f"color=c={cor}:s=320x240:d=2:r=25", "-c:v", "libx264",
             "-pix_fmt", "yuv420p", str(p)], check=True)
        partes.append(p)
    lista = SC / "_concat.txt"
    lista.write_text("".join(f"file '{p}'\n" for p in partes))
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i",
         str(lista), "-c", "copy", str(destino)], check=True)


class TesteFolhasContato(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.video = SC / "sintetico_6s.mp4"
        _gerar_video_sintetico(cls.video)
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
