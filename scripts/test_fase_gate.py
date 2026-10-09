#!/usr/bin/env python3
"""Contrato do fase_gate depois do corte de burocracia (01/09/2026) e da amarração da W3.B.

Ordem do diretor: duas cerimonias humanas e mais nada. `aprovar-plano` bloqueia o build;
`check-entrega` bloqueia a entrega (nota minima 8, UMA rodada). Fase0/fase1 deixaram de
bloquear porque o gate de entrada do produzir_ad mede a mesma evidencia direto do disco,
e na pratica ninguem registrava (11 builds na semana de 25-31/08, zero registro).

W3.B: `aprovar-plano` nao exige mais fase0/fase1 (uma verdade so: a cadeia de aprovacao nao pode
depender de registro que o proprio gate de entrada ja mede), a conferencia das 6 secoes e do tamanho
mora em plano/escrever_md.py, e a aprovacao guarda o sha256 do plano: plano editado depois do ok
vence ("aprovacao vencida").
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import fase_gate
from plano import checklist, escrever_md

CODIGO = Path(__file__).resolve().parent


def plano_md(omitir=(), tamanho=900):
    """Um plano de edição em texto com as 6 seções (menos as omitidas) e tamanho suficiente."""
    partes = ["# Plano de edição da leva", ""]
    for n, (chave, rotulo, _) in enumerate(checklist.SECOES, 1):
        if chave in omitir:
            continue
        partes += ["## %d. %s" % (n, rotulo), "texto da seção " * 12, ""]
    texto = "\n".join(partes)
    return texto + "\n" + "x " * max(0, (tamanho - len(texto)) // 2)


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
        with contextlib.redirect_stdout(io.StringIO()):
            fase_gate.cmd_check_build("99")   # nao pode levantar SystemExit

    def test_entrega_exige_nota_minima_8(self):
        self._leva(plano={"aprovado_em": "x"}, notas={"99": {"nota": 7, "evidencia": "r"}})
        with self.assertRaises(SystemExit) as cm:
            fase_gate.cmd_check_entrega("99")
        self.assertIn("minimo 8", str(cm.exception))

    def test_entrega_com_8_passa(self):
        self._leva(plano={"aprovado_em": "x"}, notas={"99": {"nota": 8, "evidencia": "r"}})
        with contextlib.redirect_stdout(io.StringIO()):
            fase_gate.cmd_check_entrega("99")

    def test_entrega_sem_nota_continua_bloqueada(self):
        # a rodada virou UMA, nao ZERO: entregar sem auditoria nenhuma segue proibido
        self._leva(plano={"aprovado_em": "x"})
        with self.assertRaises(SystemExit) as cm:
            fase_gate.cmd_check_entrega("99")
        self.assertIn("sem nota", str(cm.exception))


class TesteAprovarPlano(unittest.TestCase):
    """W3.B: a aprovação do plano tem UMA verdade e amarra o plano por sha256."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self._v2l_original = fase_gate.V2L
        fase_gate.V2L = self.dir
        self.md = self.dir / "plano.md"
        self.md.write_text(plano_md(), encoding="utf-8")

    def tearDown(self):
        fase_gate.V2L = self._v2l_original
        self._tmp.cleanup()

    def _iniciar(self):
        with contextlib.redirect_stdout(io.StringIO()):
            fase_gate.cmd_iniciar("teste", ["99"])

    def _aprovar(self):
        with contextlib.redirect_stdout(io.StringIO()):
            fase_gate.cmd_aprovar_plano("teste", str(self.md))

    def _estado(self):
        return json.loads((self.dir / "_fase_status_teste.json").read_text())

    def test_aprovar_plano_nao_pede_fase0_nem_fase1(self):
        self._iniciar()
        self.assertIsNone(self._estado()["fase0"])
        self.assertIsNone(self._estado()["fase1"])
        self._aprovar()                                   # antes: "aprovar plano antes da fase1? Nao."
        self.assertTrue(self._estado()["plano"])

    def test_numa_leva_so_com_iniciar_o_aprovar_plano_sai_0(self):
        """Seção 12, item 1: `aprovar-plano` numa leva só com `iniciar` sai 0 (processo de verdade)."""
        env = dict(os.environ, VAM_ESTADO=str(self.dir))
        for k in [k for k in env if k.startswith("VAM_") and k != "VAM_ESTADO"]:
            env.pop(k)
        base = [sys.executable, str(CODIGO / "fase_gate.py")]
        a = subprocess.run(base + ["iniciar", "teste", "--ads", "99"], capture_output=True, text=True, env=env)
        self.assertEqual(a.returncode, 0, a.stderr + a.stdout)
        b = subprocess.run(base + ["aprovar-plano", "teste", "--plano", str(self.md)],
                           capture_output=True, text=True, env=env)
        self.assertEqual(b.returncode, 0, b.stderr + b.stdout)
        c = subprocess.run(base + ["check-build", "99"], capture_output=True, text=True, env=env)
        self.assertEqual(c.returncode, 0, c.stderr + c.stdout)

    def test_aprovacao_guarda_o_sha256_do_plano(self):
        import hashlib
        self._iniciar()
        self._aprovar()
        p = self._estado()["plano"]
        self.assertEqual(p["sha256"], hashlib.sha256(self.md.read_bytes()).hexdigest())
        self.assertEqual(p["arquivo"], str(self.md))

    def test_plano_editado_depois_do_ok_vence_a_aprovacao(self):
        self._iniciar()
        self._aprovar()
        self.md.write_text(plano_md() + "\numa linha nova depois do ok\n", encoding="utf-8")
        with self.assertRaises(SystemExit) as cm:
            fase_gate.cmd_check_build("99")
        msg = str(cm.exception)
        self.assertIn("aprovação vencida", msg)
        self.assertIn("aprovar-plano", msg)

    def test_plano_que_sumiu_vence_a_aprovacao(self):
        self._iniciar()
        self._aprovar()
        self.md.unlink()
        with self.assertRaises(SystemExit) as cm:
            fase_gate.cmd_check_build("99")
        self.assertIn("aprovação vencida", str(cm.exception))

    def test_plano_igual_ao_aprovado_libera(self):
        self._iniciar()
        self._aprovar()
        with contextlib.redirect_stdout(io.StringIO()) as saida:
            fase_gate.cmd_check_build("99")
        self.assertIn("aprovado", saida.getvalue())

    def test_estado_antigo_sem_sha_continua_liberando_mas_avisa(self):
        # leva aprovada antes da amarração: não quebra, mas diz que a aprovação não está amarrada
        (self.dir / "_fase_status_teste.json").write_text(json.dumps(
            {"leva": "teste", "ads": ["99"], "plano": {"arquivo": str(self.md), "aprovado_em": "x"}}))
        with contextlib.redirect_stdout(io.StringIO()) as saida:
            fase_gate.cmd_check_build("99")
        self.assertIn("sem sha256", saida.getvalue())

    def test_plano_sem_uma_secao_cita_a_secao(self):
        self._iniciar()
        for chave, rotulo, _ in checklist.SECOES:
            self.md.write_text(plano_md(omitir=(chave,)), encoding="utf-8")
            with self.assertRaises(SystemExit) as cm:
                self._aprovar()
            self.assertIn(chave, str(cm.exception))
            self.assertIsNone(self._estado()["plano"])

    def test_plano_curto_demais_e_recusado(self):
        self._iniciar()
        # as seis palavras-chave estão lá, mas é uma linha só: seção citada não é seção respondida
        self.md.write_text("insert hook lettering densidade referencias efeitos", encoding="utf-8")
        with self.assertRaises(SystemExit) as cm:
            self._aprovar()
        self.assertIn("curto", str(cm.exception))

    def test_a_conferencia_das_secoes_e_delegada_ao_modulo_plano(self):
        self._iniciar()
        with mock.patch.object(escrever_md, "secoes_ausentes", return_value=["hook"]) as m:
            with self.assertRaises(SystemExit) as cm:
                self._aprovar()
        self.assertTrue(m.called)
        self.assertIn("hook", str(cm.exception))

    def test_plano_inexistente_e_recusado(self):
        self._iniciar()
        with self.assertRaises(SystemExit) as cm:
            fase_gate.cmd_aprovar_plano("teste", str(self.dir / "nao-existe.md"))
        self.assertIn("nao existe", str(cm.exception))

    def test_sem_aprovacao_a_mensagem_pede_o_ok_do_diretor_no_chat(self):
        self._iniciar()
        with self.assertRaises(SystemExit) as cm:
            fase_gate.cmd_check_build("99")
        self.assertIn("ok do diretor no chat", str(cm.exception))

    def test_aprovar_plano_avisa_que_so_vale_depois_do_ok_no_chat(self):
        self._iniciar()
        with contextlib.redirect_stdout(io.StringIO()) as saida:
            fase_gate.cmd_aprovar_plano("teste", str(self.md))
        self.assertIn("ok do diretor no chat", saida.getvalue())

    def test_fase_gate_nao_tem_nome_do_dono_em_lugar_nenhum(self):
        fonte = (CODIGO / "fase_gate.py").read_text(encoding="utf-8").lower()
        self.assertNotIn("julio", fonte)
        self.assertNotIn("júlio", fonte)
        self.assertNotIn("—", fonte)
        self.assertNotIn("–", fonte)

    def test_fase_gate_nao_escreve_aprovacao_json(self):
        # quem escreve plano/aprovacao.json é só plano/aprovacao.py; o estado da leva é outro arquivo
        self.assertNotIn("aprovacao.json", (CODIGO / "fase_gate.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
