#!/usr/bin/env python3
"""Contrato da MIXAGEM de som. Escrito antes do mixer.

As regras vem do banco de referencias, secao Principios: "whoosh na entrada de insert,
tick na numeracao, riser antes da virada. Sutil, NUNCA em todo corte." Mais o teto que
eu mesmo escrevi no plano: no maximo 1 efeito a cada 2,5s, e nunca na volta pro avatar.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import som_cortes as S


def _plano(pares):
    """pares: [(inicio, tipo)] -> segmentos no formato do ritmo.plano_de_ritmo."""
    segs = []
    for i, (s, t) in enumerate(pares):
        e = pares[i + 1][0] if i + 1 < len(pares) else s + 3.0
        segs.append({"bloco": i, "tipo": t, "s": s, "e": e})
    return segs


class TesteMixDeSom(unittest.TestCase):

    # WHOOSH DESLIGADO POR PADRAO (31/08/2026, Julio: "tem um som nas transicoes que ta
    # me irritando"). Os testes de POSICAO do whoosh continuam valendo pro mecanismo,
    # entao ligam a chave so dentro deles; o padrao de fabrica e testado a parte.
    def _com_whoosh(self):
        S.WHOOSH_LIGADO = True
        self.addCleanup(setattr, S, "WHOOSH_LIGADO", False)

    def test_whoosh_desligado_por_padrao(self):
        self.assertFalse(S.WHOOSH_LIGADO)
        segs = _plano([(0.0, "orig"), (5.0, "insert"), (9.0, "orig")])
        self.assertEqual([e for e in S.plano_de_som(segs, accel=1.0)
                          if e["efeito"] == "whoosh.wav"], [])

    def test_whoosh_so_na_entrada_de_insert(self):
        self._com_whoosh()
        segs = _plano([(0.0, "orig"), (5.0, "insert"), (9.0, "orig"), (14.0, "insert")])
        ev = S.plano_de_som(segs, accel=1.0)
        tipos_em = {round(e["t"], 2): e["efeito"] for e in ev}
        self.assertIn(5.0, tipos_em, "faltou whoosh na entrada de insert")
        self.assertIn(14.0, tipos_em)
        self.assertNotIn(9.0, tipos_em, "som na VOLTA pro avatar: o banco proibe")

    def test_nunca_em_todo_corte(self):
        # 12 cortes de 1s: sem teto viraria metralhadora
        segs = _plano([(float(i), "insert" if i % 2 else "orig") for i in range(12)])
        ev = S.plano_de_som(segs, accel=1.0)
        self.assertLess(len(ev), 6, f"{len(ev)} efeitos em 12s: virou metralhadora")

    def test_teto_de_um_a_cada_2s(self):
        segs = _plano([(0.0, "orig"), (2.0, "insert"), (3.0, "orig"), (4.0, "insert"),
                       (5.0, "orig"), (6.0, "insert")])
        ev = S.plano_de_som(segs, accel=1.0)
        ts = sorted(e["t"] for e in ev)
        for a, b in zip(ts, ts[1:]):
            self.assertGreaterEqual(round(b - a, 2), S.INTERVALO_MIN,
                                    f"dois efeitos a {b-a:.2f}s um do outro")

    def test_tempo_sai_em_escala_do_arquivo_entregue(self):
        self._com_whoosh()
        segs = _plano([(0.0, "orig"), (13.5, "insert")])
        ev = S.plano_de_som(segs, accel=1.35)
        self.assertAlmostEqual(ev[0]["t"], 10.0, places=2,
                               msg="o efeito tem que cair no tempo do arquivo ACELERADO")

    def test_riser_antes_do_cta(self):
        segs = _plano([(0.0, "orig"), (5.0, "insert"), (20.0, "orig")])
        ev = S.plano_de_som(segs, accel=1.0, cta=20.0)
        risers = [e for e in ev if e["efeito"] == "riser.wav"]
        self.assertEqual(len(risers), 1, "o CTA e a virada: pede riser")
        self.assertLess(risers[0]["t"], 20.0, "o riser sobe ANTES da virada, nao depois")

    def test_arquivos_existem(self):
        for nome in S.EFEITOS:
            self.assertTrue((S.SOM / nome).exists(), f"faltou {nome}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
