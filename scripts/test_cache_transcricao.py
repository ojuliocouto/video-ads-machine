#!/usr/bin/env python3
"""Contrato do cache de transcricao entre builds.

Motivo (31/08/2026): 8 builds seguidos do mesmo ad, mesmo avatar.mp4, geraram
8 transcricoes parakeet identicas porque cada build cai num out_dir novo. Este
teste garante que o cache reaproveita entre out_dirs diferentes (mesmo audio)
e invalida quando o audio muda de fato.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

import cache_transcricao


class TesteCacheTranscricao(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self._tmp.name)
        self.pasta_cache = self.raiz / "cache"
        self.audio = self.raiz / "avatar.mp4"
        self.audio.write_bytes(os.urandom(4096))

    def tearDown(self):
        self._tmp.cleanup()

    def test_obter_devolve_none_antes_de_guardar(self):
        self.assertIsNone(cache_transcricao.obter(self.audio, self.pasta_cache))

    def test_guardar_e_depois_obter_encontra(self):
        origem = self.raiz / "transcript.json"
        origem.write_text(json.dumps({"words": ["oi"]}))

        salvo = cache_transcricao.guardar(self.audio, origem, self.pasta_cache)
        self.assertTrue(salvo.exists())

        achado = cache_transcricao.obter(self.audio, self.pasta_cache)
        self.assertIsNotNone(achado)
        self.assertEqual(json.loads(achado.read_text()), {"words": ["oi"]})

    def test_um_byte_diferente_muda_a_chave(self):
        chave_antes = cache_transcricao.chave(self.audio)

        dados = bytearray(self.audio.read_bytes())
        dados[0] = (dados[0] + 1) % 256
        self.audio.write_bytes(bytes(dados))

        chave_depois = cache_transcricao.chave(self.audio)
        self.assertNotEqual(chave_antes, chave_depois)

    def test_audio_diferente_nao_acerta_cache_de_outro(self):
        origem = self.raiz / "transcript.json"
        origem.write_text(json.dumps({"words": ["oi"]}))
        cache_transcricao.guardar(self.audio, origem, self.pasta_cache)

        outro_audio = self.raiz / "avatar2.mp4"
        outro_audio.write_bytes(os.urandom(4096))
        self.assertIsNone(cache_transcricao.obter(outro_audio, self.pasta_cache))


if __name__ == "__main__":
    unittest.main(verbosity=2)
