"""Testes de projeto/looks (W1.A): looks do HeyGen do aluno, só verticais, aprovação amarrada ao sha."""
import sys
from pathlib import Path

_SCRIPTS = str(Path(__file__).resolve().parents[2] / "scripts")
if _SCRIPTS not in sys.path:  # roda também no unittest puro (sem o pythonpath do pytest.ini)
    sys.path.insert(0, _SCRIPTS)

import hashlib
import json
import tempfile
import unittest

from contratos.validar import validar_arquivo
from projeto import looks

AVATAR_ID = "a1b2c3d4e5f6a7b8c9d0"
AGORA = "2026-10-09T10:00:00-03:00"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.estado = Path(self.tmp.name) / "_local"
        (self.estado / "projetos" / "tres-horas" / "avatar").mkdir(parents=True)
        self.conf = self.estado / "projetos" / "tres-horas" / "avatar" / "conferencia.json"
        self.conf.write_text('{"largura": 1080, "altura": 1920}\n', encoding="utf-8")
        self.rel = "projetos/tres-horas/avatar/conferencia.json"

    def tearDown(self):
        self.tmp.cleanup()

    @property
    def arquivo(self):
        return self.estado / "looks.json"

    def lido(self):
        return json.loads(self.arquivo.read_text(encoding="utf-8"))

    def sha(self):
        return hashlib.sha256(self.conf.read_bytes()).hexdigest()

    def contrato_ok(self):
        self.assertEqual([str(e) for e in validar_arquivo(self.arquivo)], [])


class Cadastro(Base):
    def test_sem_arquivo_devolve_vazio(self):
        self.assertEqual(looks.carregar(self.estado), {"versao": 1, "looks": {}})

    def test_adicionar_vertical(self):
        l = looks.adicionar("laranja", AVATAR_ID, "medio", estado=self.estado)
        self.assertEqual(l, {"avatar_id": AVATAR_ID, "orientacao": "vertical", "plano": "medio", "aprovado": False})
        self.assertEqual(self.lido()["looks"]["laranja"], l)
        self.contrato_ok()

    def test_look_horizontal_reprova(self):
        with self.assertRaises(looks.LookInvalido) as c:
            looks.adicionar("largo", AVATAR_ID, "medio", orientacao="horizontal", estado=self.estado)
        self.assertIn("orientacao", str(c.exception))
        self.assertIn("vertical", str(c.exception))
        self.assertFalse(self.arquivo.exists())

    def test_arquivo_com_look_horizontal_reprova_ao_carregar(self):
        self.arquivo.write_text(json.dumps({"versao": 1, "looks": {"largo": {
            "avatar_id": AVATAR_ID, "orientacao": "horizontal", "plano": "medio", "aprovado": False}}}),
            encoding="utf-8")
        with self.assertRaises(looks.LookInvalido) as c:
            looks.carregar(self.estado)
        self.assertIn("orientacao", str(c.exception))

    def test_dados_invalidos(self):
        for kw in ({"avatar_id": "id com espaço"}, {"plano": "bem-aberto"}, {"nome": "Nome Ruim"}):
            args = dict(nome="x1", avatar_id=AVATAR_ID, plano="medio")
            args.update(kw)
            with self.assertRaises(looks.LookInvalido, msg=str(kw)):
                looks.adicionar(estado=self.estado, **args)
        self.assertFalse(self.arquivo.exists())

    def test_nao_sobrescreve_look_existente(self):
        looks.adicionar("laranja", AVATAR_ID, "medio", estado=self.estado)
        antes = self.arquivo.read_bytes()
        with self.assertRaises(looks.LookInvalido) as c:
            looks.adicionar("laranja", "outro_id_qualquer_123", "fechado", estado=self.estado)
        self.assertIn("laranja", str(c.exception))
        self.assertEqual(self.arquivo.read_bytes(), antes)

    def test_nota_opcional_e_obter_e_nomes(self):
        looks.adicionar("b-um", AVATAR_ID, "fechado", nota="boca ainda não conferida", estado=self.estado)
        looks.adicionar("a-dois", AVATAR_ID, "aberto", estado=self.estado)
        self.assertEqual(looks.nomes(self.estado), ["a-dois", "b-um"])
        self.assertEqual(looks.obter("b-um", self.estado)["nota"], "boca ainda não conferida")
        self.assertIsNone(looks.obter("nao-existe", self.estado))
        self.contrato_ok()


class Aprovacao(Base):
    def setUp(self):
        super().setUp()
        looks.adicionar("laranja", AVATAR_ID, "medio", estado=self.estado)

    def test_aprovar_grava_o_sha_do_arquivo(self):
        l = looks.aprovar("laranja", self.rel, estado=self.estado, agora=AGORA)
        self.assertTrue(l["aprovado"])
        self.assertEqual(l["conferencia"], {"arquivo": self.rel, "sha256": self.sha()})
        self.assertEqual(l["aprovado_em"], AGORA)
        self.assertEqual(self.lido()["looks"]["laranja"], l)
        self.contrato_ok()

    def test_verificar_aprovado(self):
        looks.aprovar("laranja", self.rel, estado=self.estado)
        s = looks.verificar("laranja", self.estado)
        self.assertTrue(s.aprovado)
        self.assertIsNone(s.motivo)

    def test_arquivo_mudou_invalida(self):
        looks.aprovar("laranja", self.rel, estado=self.estado)
        self.conf.write_text('{"largura": 1080, "altura": 1920, "boca": "torta"}\n', encoding="utf-8")
        s = looks.verificar("laranja", self.estado)
        self.assertFalse(s.aprovado)
        self.assertIn("mudou", s.motivo)
        self.assertIn(self.rel, s.motivo)

    def test_voltar_ao_conteudo_original_revalida(self):
        looks.aprovar("laranja", self.rel, estado=self.estado)
        original = self.conf.read_bytes()
        self.conf.write_bytes(original + b" ")
        self.assertFalse(looks.verificar("laranja", self.estado).aprovado)
        self.conf.write_bytes(original)
        self.assertTrue(looks.verificar("laranja", self.estado).aprovado)

    def test_arquivo_sumiu_invalida(self):
        looks.aprovar("laranja", self.rel, estado=self.estado)
        self.conf.unlink()
        s = looks.verificar("laranja", self.estado)
        self.assertFalse(s.aprovado)
        self.assertIn("sumiu", s.motivo)

    def test_nao_aprovado_e_inexistente(self):
        s = looks.verificar("laranja", self.estado)
        self.assertFalse(s.aprovado)
        self.assertIn("aprov", s.motivo)
        s2 = looks.verificar("nao-existe", self.estado)
        self.assertFalse(s2.aprovado)
        self.assertIn("nao-existe", s2.motivo)

    def test_exigir_aprovado(self):
        with self.assertRaises(looks.LookReprovado) as c:
            looks.exigir_aprovado("laranja", self.estado)
        self.assertIn("laranja", str(c.exception))
        looks.aprovar("laranja", self.rel, estado=self.estado)
        self.assertEqual(looks.exigir_aprovado("laranja", self.estado)["avatar_id"], AVATAR_ID)
        self.conf.write_text("mudou", encoding="utf-8")
        with self.assertRaises(looks.LookReprovado):
            looks.exigir_aprovado("laranja", self.estado)

    def test_aprovar_sem_arquivo_de_conferencia(self):
        with self.assertRaises(looks.LookInvalido) as c:
            looks.aprovar("laranja", "projetos/tres-horas/avatar/nao-tem.json", estado=self.estado)
        self.assertIn("nao-tem.json", str(c.exception))
        self.assertFalse(looks.obter("laranja", self.estado)["aprovado"])

    def test_aprovar_look_inexistente(self):
        with self.assertRaises(looks.LookInvalido) as c:
            looks.aprovar("fantasma", self.rel, estado=self.estado)
        self.assertIn("fantasma", str(c.exception))

    def test_conferencia_fora_do_estado_reprova(self):
        fora = Path(self.tmp.name) / "fora.json"
        fora.write_text("{}", encoding="utf-8")
        for ruim in ("../fora.json", str(fora), "/etc/hosts"):
            with self.assertRaises(looks.LookInvalido, msg=ruim):
                looks.aprovar("laranja", ruim, estado=self.estado)
        self.assertFalse(looks.obter("laranja", self.estado)["aprovado"])

    def test_symlink_que_escapa_do_estado_reprova(self):
        fora = Path(self.tmp.name) / "fora.json"
        fora.write_text("{}", encoding="utf-8")
        elo = self.estado / "elo.json"
        elo.symlink_to(fora)
        with self.assertRaises(looks.LookInvalido):
            looks.aprovar("laranja", "elo.json", estado=self.estado)

    def test_caminho_absoluto_dentro_do_estado_vira_relativo(self):
        l = looks.aprovar("laranja", self.conf, estado=self.estado)
        self.assertEqual(l["conferencia"]["arquivo"], self.rel)

    def test_reaprovar_depois_da_mudanca_grava_o_sha_novo(self):
        looks.aprovar("laranja", self.rel, estado=self.estado)
        velho = self.sha()
        self.conf.write_text("conferência nova\n", encoding="utf-8")
        looks.aprovar("laranja", self.rel, estado=self.estado)
        self.assertNotEqual(self.sha(), velho)
        self.assertEqual(looks.obter("laranja", self.estado)["conferencia"]["sha256"], self.sha())
        self.assertTrue(looks.verificar("laranja", self.estado).aprovado)


class InvalidarVencidos(Base):
    def test_persiste_so_os_vencidos(self):
        looks.adicionar("laranja", AVATAR_ID, "medio", estado=self.estado)
        looks.adicionar("azul", "b1b2c3d4e5f6a7b8c9d0", "fechado", estado=self.estado)
        looks.adicionar("rascunho", "c1b2c3d4e5f6a7b8c9d0", "aberto", estado=self.estado)
        looks.aprovar("laranja", self.rel, estado=self.estado)
        outra = self.estado / "projetos" / "tres-horas" / "avatar" / "conf-azul.json"
        outra.write_text("azul", encoding="utf-8")
        looks.aprovar("azul", "projetos/tres-horas/avatar/conf-azul.json", estado=self.estado)
        self.conf.write_text("mudou", encoding="utf-8")  # vence a do laranja
        vencidos = looks.invalidar_vencidos(self.estado)
        self.assertEqual(vencidos, ["laranja"])
        l = looks.obter("laranja", self.estado)
        self.assertFalse(l["aprovado"])
        self.assertNotIn("conferencia", l)
        self.assertNotIn("aprovado_em", l)
        self.assertIn("mudou", l["nota"])
        self.assertTrue(looks.obter("azul", self.estado)["aprovado"])
        self.assertFalse(looks.obter("rascunho", self.estado)["aprovado"])
        self.contrato_ok()
        self.assertEqual(looks.invalidar_vencidos(self.estado), [])

    def test_sem_arquivo_nao_cria_nada(self):
        self.assertEqual(looks.invalidar_vencidos(self.estado), [])
        self.assertFalse(self.arquivo.exists())


class ExemplosDoContrato(unittest.TestCase):
    def test_exemplo_valido_carrega(self):
        raiz = Path(__file__).resolve().parents[2] / "contratos" / "exemplos"
        with tempfile.TemporaryDirectory() as t:
            estado = Path(t)
            (estado / "looks.json").write_bytes((raiz / "looks.valido.json").read_bytes())
            d = looks.carregar(estado)
            self.assertEqual(sorted(d["looks"]), ["escritorio_claro", "laranja"])
            # a conferência do exemplo não existe nesta pasta: a aprovação não vale
            self.assertFalse(looks.verificar("laranja", estado).aprovado)


if __name__ == "__main__":
    unittest.main()
