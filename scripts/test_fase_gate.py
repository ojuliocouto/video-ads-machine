#!/usr/bin/env python3
"""Contrato do fase_gate depois do corte de burocracia (01/09/2026).

Ordem do Julio: duas cerimonias humanas e mais nada. `aprovar-plano` bloqueia o build;
`check-entrega` bloqueia a entrega (nota minima 8, UMA rodada). Fase0/fase1 deixaram de
bloquear porque o gate de entrada do produzir_ad mede a mesma evidencia direto do disco,
e na pratica ninguem registrava (11 builds na semana de 25-31/08, zero registro).
"""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import fase_gate


class TesteFaseGate(unittest.TestCase):

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._v2l_original = fase_gate.V2L
        fase_gate.V2L = Path(self._tmp.name)

    def tearDown(self):
        fase_gate.V2L = self._v2l_original
        self._tmp.cleanup()

    def _leva(self, **campos):
        st = {"leva": "teste", "ads": ["99"], **campos}
        (fase_gate.V2L / "_fase_status_teste.json").write_text(
            json.dumps(st, ensure_ascii=False))

    def test_sem_plano_bloqueia_mesmo_com_fases_marcadas(self):
        self._leva(fase0={"em": "x"}, fase1={"em": "x"})
        with self.assertRaises(SystemExit) as cm:
            fase_gate.cmd_check_build("99")
        self.assertIn("plano", str(cm.exception))

    def test_com_plano_libera_sem_exigir_fase0_fase1(self):
        # o contrato novo: registro de fase e contabilidade, nao trava. A evidencia
        # (clean, respiro, duracao do avatar) e medida pelo gate de entrada do build.
        self._leva(plano={"aprovado_em": "x"})
        fase_gate.cmd_check_build("99")   # nao pode levantar SystemExit

    def test_entrega_exige_nota_minima_8(self):
        self._leva(plano={"aprovado_em": "x"}, notas={"99": {"nota": 7, "evidencia": "r"}})
        with self.assertRaises(SystemExit) as cm:
            fase_gate.cmd_check_entrega("99")
        self.assertIn("minimo 8", str(cm.exception))

    def test_entrega_com_8_passa(self):
        self._leva(plano={"aprovado_em": "x"}, notas={"99": {"nota": 8, "evidencia": "r"}})
        fase_gate.cmd_check_entrega("99")

    def test_entrega_sem_nota_continua_bloqueada(self):
        # a rodada virou UMA, nao ZERO: entregar sem auditoria nenhuma segue proibido
        self._leva(plano={"aprovado_em": "x"})
        with self.assertRaises(SystemExit) as cm:
            fase_gate.cmd_check_entrega("99")
        self.assertIn("sem nota", str(cm.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
