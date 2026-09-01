#!/usr/bin/env python3
"""Teste da biblioteca de efeitos sonoros (item 1 do brief: som estratégico nos inserts).

Contrato ANTES do código, pra ver vermelho:
  - os três efeitos existem (whoosh, tick, riser) em assets/som/
  - duração na faixa combinada (whoosh curto, tick seco, riser mais longo)
  - nenhum é silêncio, e nenhum estoura (pico abaixo de -6 dBFS: "sutil, nunca
    dominante", regra do banco de referências)
  - sample rate 48k, o mesmo do pipeline (o composite trabalha em 48k; 44.1k
    misturado dessincroniza o mux)
"""
import re
import subprocess
import sys
import unittest
from pathlib import Path

# (migracao 26/08/2026) o teste tinha a PROPRIA copia deste caminho e por isso
# continuou apontando pro lugar errado depois da mudanca. Teste que reimplementa
# a constante valida a copia, nao o codigo: agora importa do modulo.
from som_cortes import SOM  # noqa: E402
ESPERADO = {
    "whoosh.wav": (0.25, 0.80),
    "tick.wav": (0.03, 0.15),
    "riser.wav": (0.80, 1.60),
}


def _probe(p):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=sample_rate:format=duration", "-of", "csv=p=0", str(p)],
        capture_output=True, text=True)
    linhas = [x for x in r.stdout.strip().splitlines() if x]
    sr = int(linhas[0]) if linhas else 0
    dur = float(linhas[-1]) if len(linhas) > 1 else 0.0
    return sr, dur


def _pico_db(p):
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(p), "-af", "astats=metadata=0",
         "-f", "null", "-"], capture_output=True, text=True)
    m = re.findall(r"Peak level dB:\s*(-?[0-9.]+)", r.stderr)
    return max(float(x) for x in m) if m else -120.0


class TesteSomCortes(unittest.TestCase):

    def test_biblioteca_existe_e_dentro_do_contrato(self):
        for nome, (dmin, dmax) in ESPERADO.items():
            p = SOM / nome
            with self.subTest(efeito=nome):
                self.assertTrue(p.exists(), f"{nome} não existe em {SOM}")
                sr, dur = _probe(p)
                self.assertEqual(sr, 48000, f"{nome}: sample rate {sr}, pipeline é 48k")
                self.assertTrue(dmin <= dur <= dmax,
                                f"{nome}: {dur:.2f}s fora de [{dmin}, {dmax}]")
                pico = _pico_db(p)
                self.assertGreater(pico, -50.0, f"{nome} é silêncio ({pico} dB)")
                self.assertLess(pico, -6.0,
                                f"{nome} estoura ({pico} dB): efeito é sutil, não solo")

    # O CONTRATO DE NIVEL MORA EM test_nivel_som.py, NAO AQUI (27/08/2026).
    # Cheguei a escrever um segundo teste de nivel neste arquivo, com faixa propria, e
    # so descobri o `test_nivel_som.py` quando os dois brigaram na suite. Dois testes
    # medindo a mesma coisa com faixas diferentes e pior que um so: o que passa vira
    # alibi pro que reprova. Este arquivo cuida de existencia, duracao, sample rate e
    # clipping; o nivel e la.

if __name__ == "__main__":
    unittest.main(verbosity=2)
