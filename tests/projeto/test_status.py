"""Testes de projeto/status (W1.A): status.json atômico (temporário + rename) com histórico."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from projeto import pastas, status


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.estado = Path(self.tmp.name) / "_local"
        self.estado.mkdir()
        self.p = pastas.projeto("tres-horas", self.estado)
        self.p.criar()

    def tearDown(self):
        self.tmp.cleanup()

    def lido(self):
        return json.loads(self.p.status_json.read_text(encoding="utf-8"))


class Registro(Base):
    def test_sem_arquivo_devolve_vazio(self):
        s = status.ler(self.p)
        self.assertEqual(s, {"versao": 1, "atual": None, "historico": []})

    def test_primeiro_registro(self):
        s = status.registrar(self.p, "novo", "ok", agora="2026-10-09T10:00:00-03:00")
        self.assertEqual(s["atual"]["etapa"], "novo")
        self.assertEqual(s["atual"]["estado"], "ok")
        self.assertEqual(s["atual"]["em"], "2026-10-09T10:00:00-03:00")
        self.assertEqual(len(s["historico"]), 1)
        self.assertEqual(self.lido(), s)

    def test_historico_acumula_na_ordem(self):
        for etapa, est in (("voz", "em_andamento"), ("voz", "ok"), ("avatar", "em_andamento")):
            status.registrar(self.p, etapa, est)
        h = self.lido()["historico"]
        self.assertEqual([(x["etapa"], x["estado"]) for x in h],
                         [("voz", "em_andamento"), ("voz", "ok"), ("avatar", "em_andamento")])
        self.assertEqual(self.lido()["atual"]["etapa"], "avatar")

    def test_falhou_e_bloqueado_exigem_motivo(self):
        for est in ("falhou", "bloqueado"):
            with self.assertRaises(ValueError) as c:
                status.registrar(self.p, "gate_look", est)
            self.assertIn("motivo", str(c.exception))
            with self.assertRaises(ValueError):
                status.registrar(self.p, "gate_look", est, motivo="   ")
        self.assertFalse(self.p.status_json.exists())

    def test_motivo_gravado(self):
        s = status.registrar(self.p, "gate_look", "falhou", motivo="look sem aprovação")
        self.assertEqual(s["atual"]["motivo"], "look sem aprovação")

    def test_estado_e_etapa_invalidos(self):
        with self.assertRaises(ValueError):
            status.registrar(self.p, "voz", "quase")
        for ruim in ("", "Voz Limpa", "../x", None):
            with self.assertRaises(ValueError, msg=repr(ruim)):
                status.registrar(self.p, ruim, "ok")

    def test_detalhes_entram_no_registro(self):
        s = status.registrar(self.p, "montar", "ok", detalhes={"duracao_s": 41.9, "gates": 18})
        self.assertEqual(s["atual"]["detalhes"], {"duracao_s": 41.9, "gates": 18})

    def test_limite_do_historico_mantem_os_mais_novos(self):
        for i in range(status.LIMITE_HISTORICO + 25):
            status.registrar(self.p, "etapa-%d" % i, "ok")
        h = self.lido()["historico"]
        self.assertEqual(len(h), status.LIMITE_HISTORICO)
        self.assertEqual(h[-1]["etapa"], "etapa-%d" % (status.LIMITE_HISTORICO + 24))

    def test_aceita_o_caminho_do_arquivo(self):
        status.registrar(self.p.status_json, "voz", "ok")
        self.assertEqual(status.ler(self.p.status_json)["atual"]["etapa"], "voz")

    def test_arquivo_corrompido_vai_para_o_lado_e_recomeca(self):
        self.p.status_json.write_text("{isso não é json", encoding="utf-8")
        s = status.registrar(self.p, "voz", "ok")
        self.assertEqual(len(s["historico"]), 1)
        sobra = self.p.status_json.with_name("status.json.corrompido")
        self.assertEqual(sobra.read_text(encoding="utf-8"), "{isso não é json")

    def test_estrutura_estranha_tambem_recomeca(self):
        self.p.status_json.write_text('["não", "é", "objeto"]', encoding="utf-8")
        s = status.registrar(self.p, "voz", "ok")
        self.assertEqual(len(s["historico"]), 1)
        self.assertTrue(self.p.status_json.with_name("status.json.corrompido").exists())


class EscritaAtomica(Base):
    def test_usa_temporario_na_mesma_pasta_e_rename(self):
        chamadas = []
        real = os.replace

        def espia(origem, destino):
            chamadas.append((Path(origem), Path(destino), Path(origem).exists()))
            return real(origem, destino)

        with mock.patch("os.replace", side_effect=espia):
            status.registrar(self.p, "voz", "ok")
        self.assertEqual(len(chamadas), 1)
        origem, destino, existia = chamadas[0]
        self.assertEqual(destino, self.p.status_json)
        self.assertEqual(origem.parent, destino.parent)
        self.assertNotEqual(origem.name, destino.name)
        self.assertTrue(existia)
        self.assertFalse(origem.exists())  # o temporário virou o arquivo

    def test_falha_no_rename_preserva_o_original_e_nao_deixa_lixo(self):
        status.registrar(self.p, "voz", "ok")
        antes = self.p.status_json.read_bytes()
        with mock.patch("os.replace", side_effect=OSError("disco cheio")):
            with self.assertRaises(OSError):
                status.registrar(self.p, "avatar", "ok")
        self.assertEqual(self.p.status_json.read_bytes(), antes)
        self.assertEqual(sorted(x.name for x in self.p.raiz.iterdir() if x.is_file()), ["status.json"])

    def test_falha_ao_serializar_nao_toca_no_arquivo(self):
        status.registrar(self.p, "voz", "ok")
        antes = self.p.status_json.read_bytes()
        with self.assertRaises(TypeError):
            status.registrar(self.p, "avatar", "ok", detalhes={"x": object()})
        self.assertEqual(self.p.status_json.read_bytes(), antes)
        self.assertEqual(sorted(x.name for x in self.p.raiz.iterdir() if x.is_file()), ["status.json"])

    def test_nenhum_temporario_sobra(self):
        for i in range(5):
            status.registrar(self.p, "voz", "ok")
        self.assertEqual(sorted(x.name for x in self.p.raiz.iterdir() if x.is_file()), ["status.json"])

    def test_escrever_json_atomico_generico(self):
        alvo = Path(self.tmp.name) / "novo" / "dado.json"
        status.escrever_json_atomico(alvo, {"acento": "anúncio", "n": 1})
        txt = alvo.read_text(encoding="utf-8")
        self.assertIn("anúncio", txt)
        self.assertTrue(txt.endswith("\n"))
        self.assertEqual(json.loads(txt), {"acento": "anúncio", "n": 1})
        self.assertEqual(oct(alvo.stat().st_mode & 0o777), oct(0o644))

    def test_ler_json_recusa_chave_repetida_e_nan(self):
        f = Path(self.tmp.name) / "x.json"
        f.write_text('{"a": 1, "a": 2}', encoding="utf-8")
        with self.assertRaises(ValueError):
            status.ler_json(f)
        f.write_text('{"a": NaN}', encoding="utf-8")
        with self.assertRaises(ValueError):
            status.ler_json(f)
        f.write_text('{"a": 1}', encoding="utf-8")
        self.assertEqual(status.ler_json(f), {"a": 1})


if __name__ == "__main__":
    unittest.main()
