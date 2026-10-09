"""Testes de projeto/pastas (W1.A): caminhos de um projeto, sempre dentro de ESTADO/projetos/<slug>."""
import os
import tempfile
import unittest
from pathlib import Path

from projeto import pastas


def arvore(raiz):
    return sorted(str(p.relative_to(raiz)) for p in Path(raiz).rglob("*"))


class CaminhosDoProjeto(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.estado = Path(self.tmp.name) / "_local"
        self.estado.mkdir()
        self.p = pastas.projeto("tres-horas", self.estado)

    def tearDown(self):
        self.tmp.cleanup()

    def test_raiz(self):
        self.assertEqual(self.p.raiz, self.estado / "projetos" / "tres-horas")
        self.assertEqual(self.p.slug, "tres-horas")
        self.assertEqual(self.p.estado, self.estado)

    def test_layout_do_plano(self):
        r = self.p.raiz
        esperado = {
            "roteiro": r / "roteiro.md",
            "projeto_json": r / "projeto.json",
            "status_json": r / "status.json",
            "voz_limpo": r / "voz" / "limpo.mp3",
            "voz_auditoria": r / "voz" / "auditoria.json",
            "avatar_mp4": r / "avatar" / "avatar.mp4",
            "avatar_conferencia": r / "avatar" / "conferencia.json",
            "avatar_boca": r / "avatar" / "boca.png",
            "inserts_dir": r / "inserts",
            "plano_json": r / "plano" / "plano.json",
            "plano_md": r / "plano" / "plano_edicao.md",
            "prancha_dir": r / "plano" / "prancha",
            "aprovacao": r / "plano" / "aprovacao.json",
            "render_dir": r / "render",
            "alinhamento": r / "render" / "alinhamento.json",
            "timeline": r / "render" / "timeline.json",
            "final_9x16": r / "entrega" / "final_9x16.mp4",
            "final_whatsapp": r / "entrega" / "final_whatsapp.mp4",
            "laudo": r / "entrega" / "laudo.json",
            "nota": r / "entrega" / "nota.json",
            "folhas_dir": r / "entrega" / "folhas",
        }
        for nome, caminho in esperado.items():
            self.assertEqual(getattr(self.p, nome), caminho, nome)

    def test_tudo_fica_dentro_da_raiz(self):
        for nome in dir(self.p):
            v = getattr(self.p, nome)
            if isinstance(v, Path) and nome not in ("estado",):
                self.assertTrue(self.p.dentro(v), nome)

    def test_dentro_e_relativo(self):
        self.assertTrue(self.p.dentro(self.p.raiz / "voz" / "x.mp3"))
        self.assertFalse(self.p.dentro(self.estado / "looks.json"))
        self.assertFalse(self.p.dentro(self.p.raiz / ".." / "outro" / "x"))
        self.assertEqual(self.p.relativo(self.p.timeline), "render/timeline.json")
        with self.assertRaises(ValueError):
            self.p.relativo(self.estado / "looks.json")

    def test_dentro_nao_confunde_prefixo(self):
        irmao = self.estado / "projetos" / "tres-horas-2" / "x"
        self.assertFalse(self.p.dentro(irmao))

    def test_voz_bruto_acha_qualquer_extensao(self):
        self.assertIsNone(self.p.voz_bruto())
        (self.p.raiz / "voz").mkdir(parents=True)
        (self.p.raiz / "voz" / "bruto.m4a").write_bytes(b"x")
        (self.p.raiz / "voz" / "limpo.mp3").write_bytes(b"x")
        self.assertEqual(self.p.voz_bruto(), self.p.raiz / "voz" / "bruto.m4a")

    def test_voz_bruto_ambiguo(self):
        (self.p.raiz / "voz").mkdir(parents=True)
        (self.p.raiz / "voz" / "bruto.m4a").write_bytes(b"x")
        (self.p.raiz / "voz" / "bruto.wav").write_bytes(b"x")
        with self.assertRaises(ValueError) as c:
            self.p.voz_bruto()
        self.assertIn("bruto", str(c.exception))

    def test_insert_por_chave(self):
        self.assertIsNone(self.p.insert("painel"))
        self.p.inserts_dir.mkdir(parents=True)
        (self.p.inserts_dir / "painel.mp4").write_bytes(b"x")
        (self.p.inserts_dir / "painel.v2.mp4").write_bytes(b"x")  # outra chave, não conta
        (self.p.inserts_dir / "planilha.png").write_bytes(b"x")
        self.assertEqual(self.p.insert("painel"), self.p.inserts_dir / "painel.mp4")
        self.assertEqual(self.p.insert("planilha"), self.p.inserts_dir / "planilha.png")
        self.assertIsNone(self.p.insert("automacao"))

    def test_insert_ambiguo_e_chave_invalida(self):
        self.p.inserts_dir.mkdir(parents=True)
        (self.p.inserts_dir / "painel.mp4").write_bytes(b"x")
        (self.p.inserts_dir / "painel.png").write_bytes(b"x")
        with self.assertRaises(ValueError):
            self.p.insert("painel")
        for ruim in ("../x", "a/b", "", "Painel", "com espaço"):
            with self.assertRaises(ValueError, msg=ruim):
                self.p.insert(ruim)

    def test_lista_de_inserts(self):
        self.p.inserts_dir.mkdir(parents=True)
        (self.p.inserts_dir / "b.mp4").write_bytes(b"x")
        (self.p.inserts_dir / "a.png").write_bytes(b"x")
        (self.p.inserts_dir / ".DS_Store").write_bytes(b"x")
        self.assertEqual(self.p.inserts(), {"a": self.p.inserts_dir / "a.png", "b": self.p.inserts_dir / "b.mp4"})


class Slug(unittest.TestCase):
    def test_slugs_ruins(self):
        for ruim in ("../x", "A b", "", "x/y", "três", "-x", ".", "..", "a" * 64, "X", "a\\b", None, 3):
            with self.assertRaises(ValueError, msg=repr(ruim)):
                pastas.validar_slug(ruim)

    def test_slugs_bons(self):
        for bom in ("a", "tres-horas", "ad_07", "x" * 63, "0-um"):
            self.assertEqual(pastas.validar_slug(bom), bom)

    def test_projeto_recusa_slug_ruim(self):
        with self.assertRaises(ValueError):
            pastas.projeto("../fora", Path("/tmp/_local"))

    def test_slugificar(self):
        casos = {
            "Três Horas por Dia!": "tres-horas-por-dia",
            "  Quanto custa?  ": "quanto-custa",
            "AD 07 / versão B": "ad-07-versao-b",
            "ação_rápida": "acao_rapida",
        }
        for entrada, saida in casos.items():
            self.assertEqual(pastas.slugificar(entrada), saida)
        self.assertEqual(len(pastas.slugificar("a" * 200)), 63)
        for vazio in ("", "!!!", "   "):
            with self.assertRaises(ValueError):
                pastas.slugificar(vazio)


class CriarPastas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.estado = self.base / "_local"
        self.estado.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_criar_so_cria_dentro_do_projeto(self):
        antes = set(arvore(self.base))
        p = pastas.projeto("tres-horas", self.estado)
        p.criar()
        novos = set(arvore(self.base)) - antes
        self.assertTrue(novos)
        raiz = "_local/projetos/tres-horas"
        for n in novos:
            self.assertTrue(n == "_local/projetos" or n == raiz or n.startswith(raiz + "/"), n)
        for sub in ("voz", "avatar", "inserts", "plano/prancha", "render", "entrega/folhas"):
            self.assertTrue((p.raiz / sub).is_dir(), sub)

    def test_criar_e_idempotente_e_nao_apaga(self):
        p = pastas.projeto("tres-horas", self.estado)
        p.criar()
        p.roteiro.write_text("Oi.\n", encoding="utf-8")
        p.criar()
        self.assertEqual(p.roteiro.read_text(encoding="utf-8"), "Oi.\n")

    def test_listar_projetos(self):
        self.assertEqual(pastas.listar(self.estado), [])
        pastas.projeto("b-um", self.estado).criar()
        pastas.projeto("a-dois", self.estado).criar()
        (self.estado / "projetos" / "Nome Ruim").mkdir()
        (self.estado / "projetos" / "arquivo.txt").write_text("x")
        self.assertEqual(pastas.listar(self.estado), ["a-dois", "b-um"])

    def test_pastas_do_estado(self):
        self.assertEqual(pastas.looks_json(self.estado), self.estado / "looks.json")
        self.assertEqual(pastas.glossario_json(self.estado), self.estado / "glossario.json")
        self.assertEqual(pastas.trilhas_dir(self.estado), self.estado / "trilhas")
        self.assertEqual(pastas.logo(self.estado), self.estado / "marca" / "logo.png")
        self.assertEqual(pastas.projetos_dir(self.estado), self.estado / "projetos")

    def test_trilha_so_aceita_nome_de_arquivo(self):
        self.assertEqual(pastas.trilha("leve.mp3", self.estado), self.estado / "trilhas" / "leve.mp3")
        for ruim in ("../leve.mp3", "a/b.mp3", "/abs.mp3", ""):
            with self.assertRaises(ValueError, msg=ruim):
                pastas.trilha(ruim, self.estado)


class EstadoPadrao(unittest.TestCase):
    def test_usa_caminhos_estado_na_hora_da_chamada(self):
        import caminhos
        original = caminhos.ESTADO
        try:
            with tempfile.TemporaryDirectory() as t:
                caminhos.ESTADO = Path(t) / "_local"
                self.assertEqual(pastas.estado_padrao(), Path(t) / "_local")
                self.assertEqual(pastas.projeto("x1").raiz, Path(t) / "_local" / "projetos" / "x1")
        finally:
            caminhos.ESTADO = original


if __name__ == "__main__":
    unittest.main()
