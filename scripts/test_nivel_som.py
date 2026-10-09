#!/usr/bin/env python3
"""Nivel do efeito sonoro: audivel, mas discreto. Duas travas, dois defeitos reais.

DEFEITO 1 (20/08/2026): whoosh a volume=-14dB, RMS -40,2 dBFS. A mixagem rodava, o log
dizia "6 efeitos", e nao se ouvia NADA. "Existia" so no arquivo.

DEFEITO 2 (27/08/2026): whoosh a volume=-1dB, RMS -27,2 dBFS. O Julio: "tem um som
ridiculo nas transicoes, parece um tiro".

A FAIXA ANTERIOR DESTE TESTE ERA -30 a -20 dBFS, E ELA PERMITIA O DEFEITO 2: os -27,2
que o Julio reprovou cabiam dentro dela com folga. Teste que passa verde no material
que o cliente reprova esta calibrado errado, nao "quase certo". A faixa velha tinha sido
escrita olhando so pro defeito 1, com o outro extremo chutado ("acima de -20 compete com
a voz") em vez de medido.

Faixa nova: -38 a -31 dBFS, ancorada nos DOIS vereditos humanos, com o alvo em -34.

E o raciocinio do extremo alto mudou junto: nao e "compete com a voz". O whoosh a -24,6
dBFS ja estava ABAIXO da voz (-17,9) e mesmo assim soava como tiro, porque os efeitos
caem nos CORTES e corte coincide com PAUSA de fala: eles aparecem sozinhos, no silencio.
O que importa e o nivel absoluto tocando so, nao a relacao com a fala.
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
for _p in (str(RAIZ / "scripts"), str(RAIZ)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import som_cortes as S  # noqa: E402
from tests.fixtures import sinteticos as SIN  # noqa: E402

MIN_DB, MAX_DB = -38.0, -31.0


def rms_db(p):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-map", "0:a",
                        "-f", "s16le", "-ac", "1", "-ar", "48000", "-"],
                       capture_output=True)
    a = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float64) / 32768.0
    if a.size == 0:
        return None
    return 20 * np.log10(max(float(np.sqrt((a ** 2).mean())), 1e-9))


class TesteNivelDeSom(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Mede a biblioteca que a RECEITA (som_cortes.EFEITOS) produz, gerada em tmp. Antes
        # o teste lia _local/dados/assets/som, que só existe depois do setup.
        cls.som = Path(tempfile.mkdtemp(prefix="vam_som_"))
        cls.addClassCleanup(shutil.rmtree, cls.som, True)
        SIN.gerar_som(cls.som)

    def test_todo_efeito_e_audivel_e_nao_compete(self):
        for nome in S.EFEITOS:
            with self.subTest(efeito=nome):
                db = rms_db(self.som / nome)
                self.assertIsNotNone(db, f"{nome} sem audio")
                self.assertGreaterEqual(db, MIN_DB,
                    f"{nome} em {db:.1f} dBFS: some na entrega (defeito de 20/08, -40,2)")
                self.assertLessEqual(db, MAX_DB,
                    f"{nome} em {db:.1f} dBFS: alto demais tocando numa pausa de fala "
                    f"(defeito de 27/08, -27,2: 'parece um tiro')")

    def test_nao_estoura(self):
        for nome in S.EFEITOS:
            with self.subTest(efeito=nome):
                r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(self.som / nome),
                                    "-map", "0:a", "-f", "s16le", "-ac", "1",
                                    "-ar", "48000", "-"], capture_output=True)
                a = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float64) / 32768.0
                self.assertLess(float(np.abs(a).max()), 0.99, f"{nome} clipa")


if __name__ == "__main__":
    unittest.main(verbosity=2)
