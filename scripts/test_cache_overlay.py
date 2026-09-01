#!/usr/bin/env python3
"""Testes de cache_overlay.py: assinatura por conteudo e decisao de reaproveitar."""
import tempfile
import unittest
from pathlib import Path

import cache_overlay as CO


class TestAssinatura(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_conteudo_igual_da_mesma_assinatura(self):
        a = self.tmp / "a.html"
        b = self.tmp / "b.html"
        a.write_text("<html>overlay identico</html>")
        b.write_text("<html>overlay identico</html>")
        self.assertEqual(CO.assinatura([a]), CO.assinatura([b]))

    def test_um_byte_diferente_muda_assinatura(self):
        a = self.tmp / "a.html"
        b = self.tmp / "b.html"
        a.write_text("<html>overlay identicoX</html>")
        b.write_text("<html>overlay identicoY</html>")
        self.assertNotEqual(CO.assinatura([a]), CO.assinatura([b]))

    def test_assinatura_tem_16_chars_hex(self):
        a = self.tmp / "a.html"
        a.write_text("qualquer coisa")
        sig = CO.assinatura([a])
        self.assertEqual(len(sig), 16)
        int(sig, 16)  # nao levanta ValueError se for hex valido


class TestReaproveitavel(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.html = self.tmp / "index_overlay.html"
        self.html.write_text("<html>overlay v1</html>")
        self.mov = self.tmp / "overlay.mov"
        self.mov.write_bytes(b"conteudo-mov-fake")
        self.sig = self.tmp / ".assinatura_overlay"

    def tearDown(self):
        self._tmp.cleanup()

    def test_false_sem_mov(self):
        self.sig.write_text(CO.assinatura([self.html]))
        mov_ausente = self.tmp / "nao_existe.mov"
        self.assertFalse(CO.reaproveitavel(self.html, mov_ausente, self.sig))

    def test_false_com_assinatura_diferente(self):
        self.sig.write_text("0000000000000000")  # nao bate com o html atual
        self.assertFalse(CO.reaproveitavel(self.html, self.mov, self.sig))

    def test_false_sem_arquivo_de_assinatura(self):
        self.assertFalse(CO.reaproveitavel(self.html, self.mov, self.sig))

    def test_false_mov_vazio(self):
        self.sig.write_text(CO.assinatura([self.html]))
        mov_vazio = self.tmp / "vazio.mov"
        mov_vazio.write_bytes(b"")
        self.assertFalse(CO.reaproveitavel(self.html, mov_vazio, self.sig))

    def test_true_com_tudo_igual(self):
        self.sig.write_text(CO.assinatura([self.html]))
        self.assertTrue(CO.reaproveitavel(self.html, self.mov, self.sig))


if __name__ == "__main__":
    unittest.main()
