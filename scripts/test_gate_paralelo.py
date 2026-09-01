import sys
import time
import unittest

from gates_paralelo import rodar_em_paralelo


class TestGateParalelo(unittest.TestCase):
    def test_roda_em_paralelo_de_verdade(self):
        cmd = [sys.executable, "-c",
               "import time,sys; time.sleep(0.6); print('x')"]
        tarefas = [("a", cmd), ("b", cmd), ("c", cmd)]

        inicio = time.monotonic()
        resultados = rodar_em_paralelo(tarefas)
        duracao = time.monotonic() - inicio

        # 3 comandos de 0,6s: em serie dariam ~1,8s. Em paralelo de verdade
        # (max_workers>=3) ficam perto de 0,6s. 1,2s da folga sem deixar
        # passar uma implementacao que rodou em serie.
        self.assertLess(duracao, 1.2)

        self.assertEqual(set(resultados.keys()), {"a", "b", "c"})
        for nome, r in resultados.items():
            self.assertEqual(r.returncode, 0)
            self.assertEqual(r.stdout.strip(), "x")

    def test_lista_vazia(self):
        self.assertEqual(rodar_em_paralelo([]), {})


if __name__ == "__main__":
    unittest.main()
