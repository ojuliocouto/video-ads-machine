#!/usr/bin/env python3
"""O painel de baixo do split TEM que mostrar a boca. Trava de defeito real (20/08/2026).

O split 60/40 deixou o painel do apresentador com 770px enquanto a pessoa ocupa ~1600.
A regra antiga ancorava no TOPO DA CABECA com 10% de folga, o que e aritmeticamente
impossivel nesse espaco: degradava pra "cabelo, testa e olhos" e o corte caia no NARIZ.
Um avatar de LIPSYNC sem boca, nos quatro splits do AD15 e provavelmente na leva toda.

Ninguem tinha medido a saida da regra: ela "funcionava" porque devolvia um numero.
"""
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import medir_rosto

# V1 aqui significava duas coisas: onde mora o SCRIPT e onde moram os inputs.
# Depois da migracao sao lugares diferentes, entao viraram dois nomes.
from caminhos import DADOS as V1, CODIGO  # noqa: E402
SRC_Y, SRC_H = 100, 1600
ALT_PAINEL = 770

LOOKS = ["jh13v2_espuma_roxa", "jh14v2_oficial_13",
         "jh15v2_neon_creme", "jh16v2_espuma_roxa"]


def bias_do(look):
    r = subprocess.run([sys.executable, str(CODIGO / "medir_enquadramento.py"), "avatar",
                        str(V1 / "inputs" / f"{look}_avatar.mp4"), "--json"],
                       capture_output=True, text=True)
    import json
    return json.loads(r.stdout)["VAM_SPLIT_BIAS"]


class TesteEnquadramentoSplit(unittest.TestCase):

    def test_o_rosto_inteiro_cabe_no_painel(self):
        for look in LOOKS:
            p = V1 / "inputs" / f"{look}_avatar.mp4"
            if not p.exists():
                continue
            with self.subTest(look=look):
                caixa = medir_rosto.caixa_rosto(str(p))
                self.assertIsNotNone(caixa, f"{look}: rosto nao detectado")
                fy, fh = caixa
                corte = int(bias_do(look) * SRC_H)
                jan_ini, jan_fim = SRC_Y + corte, SRC_Y + corte + ALT_PAINEL
                self.assertLessEqual(jan_ini, fy + int(fh * 0.18),
                    f"{look}: a janela comeca em {jan_ini} e o rosto em {fy}: "
                    f"corta acima da linha dos olhos")
                self.assertGreaterEqual(jan_fim, fy + fh,
                    f"{look}: a janela acaba em {jan_fim} e o rosto vai ate {fy+fh}: "
                    f"a BOCA fica fora do quadro (foi o defeito de 20/08)")

    def test_reproduz_o_valor_que_o_diretor_validou(self):
        p = V1 / "inputs" / "jh15v2_neon_creme_avatar.mp4"
        if not p.exists():
            self.skipTest("avatar ausente")
        self.assertAlmostEqual(bias_do("jh15v2_neon_creme"), 0.30, delta=0.02,
            msg="o diretor renderizou 0.049/0.18/0.225/0.30 e validou 0.30; "
                "a regra tem que cair nele sozinha")


if __name__ == "__main__":
    unittest.main(verbosity=2)
