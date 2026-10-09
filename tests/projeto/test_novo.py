"""Testes de projeto/novo (W1.A): cria o projeto do aluno, idempotente, sem sobrescrever."""
import sys
from pathlib import Path

_SCRIPTS = str(Path(__file__).resolve().parents[2] / "scripts")
if _SCRIPTS not in sys.path:  # roda também no unittest puro (sem o pythonpath do pytest.ini)
    sys.path.insert(0, _SCRIPTS)

import json
import os
import tempfile
import unittest

from contratos.validar import validar_arquivo
from projeto import looks, modelo, novo, pastas, status

SEM_TRILHA = "anúncio de teste, sem trilha licenciada ainda"


def arvore(raiz):
    return sorted(str(p.relative_to(raiz)) for p in Path(raiz).rglob("*"))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.estado = self.base / "_local"
        self.estado.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def criar(self, slug="tres-horas", modo="avatar", **kw):
        kw.setdefault("sem_trilha", SEM_TRILHA)
        if modo == "avatar":
            kw.setdefault("look", "laranja")
        return novo.criar(slug, modo, estado=self.estado, **kw)


class Criacao(Base):
    def test_cria_o_projeto_valido(self):
        r = self.criar()
        self.assertTrue(r.criado)
        self.assertEqual(r.pastas.raiz, self.estado / "projetos" / "tres-horas")
        self.assertEqual([str(e) for e in validar_arquivo(r.pastas.projeto_json)], [])
        p = json.loads(r.pastas.projeto_json.read_text(encoding="utf-8"))
        self.assertEqual((p["slug"], p["modo"], p["look"]), ("tres-horas", "avatar", "laranja"))
        self.assertEqual(p["aceleracao"], 1.35)
        self.assertEqual(p["formato"], "9x16")
        self.assertIn("criado_em", p)
        self.assertEqual(r.projeto, p)

    def test_padroes_dos_outros_modos(self):
        self.assertEqual(self.criar("take-um", "gravado").projeto["aceleracao"], 1.2)
        self.assertEqual(self.criar("take-dois", "oneshot").projeto["aceleracao"], 1.2)

    def test_cria_as_pastas_e_o_status(self):
        r = self.criar()
        for sub in ("voz", "avatar", "inserts", "plano/prancha", "render", "entrega/folhas"):
            self.assertTrue((r.pastas.raiz / sub).is_dir(), sub)
        s = status.ler(r.pastas)
        self.assertEqual((s["atual"]["etapa"], s["atual"]["estado"]), ("novo", "ok"))
        self.assertEqual(len(s["historico"]), 1)

    def test_trilha_com_arquivo_e_origem(self):
        r = novo.criar("do-doc", "gravado", trilha="leve.mp3", estado=self.estado,
                       origem={"tipo": "doc_google", "doc_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"})
        self.assertEqual(r.projeto["trilha"], {"arquivo": "leve.mp3"})
        self.assertEqual(r.projeto["origem"]["tipo"], "doc_google")

    def test_zero_arquivo_fora_do_projeto(self):
        antes = set(arvore(self.base))
        self.criar()
        novos = set(arvore(self.base)) - antes
        raiz = "_local/projetos/tres-horas"
        self.assertTrue(novos)
        for n in novos:
            self.assertTrue(n == "_local/projetos" or n == raiz or n.startswith(raiz + "/"), n)

    def test_nao_cria_looks_glossario_nem_trilhas(self):
        self.criar()
        for nome in ("looks.json", "glossario.json", "trilhas", "marca"):
            self.assertFalse((self.estado / nome).exists(), nome)


class Reprovacoes(Base):
    def nada_criado(self):
        self.assertEqual(arvore(self.base), ["_local"])

    def test_slug_ruim(self):
        for ruim in ("../fora", "Três Horas", "", "a/b"):
            with self.assertRaises(ValueError, msg=ruim):
                self.criar(ruim)
        self.nada_criado()

    def test_trilha_ausente_nao_cria_nada(self):
        with self.assertRaises(modelo.ContratoInvalido) as c:
            novo.criar("tres-horas", "avatar", look="laranja", estado=self.estado)
        self.assertIn("trilha", [e.campo for e in c.exception.erros])
        self.nada_criado()

    def test_avatar_sem_look_nao_cria_nada(self):
        with self.assertRaises(modelo.ContratoInvalido) as c:
            novo.criar("tres-horas", "avatar", sem_trilha=SEM_TRILHA, estado=self.estado)
        self.assertIn("look", [e.campo for e in c.exception.erros])
        self.nada_criado()

    def test_modo_desconhecido(self):
        with self.assertRaises(modelo.ContratoInvalido):
            self.criar("x1", "vsl")
        self.nada_criado()

    def test_trilha_e_sem_trilha_juntas(self):
        with self.assertRaises(ValueError):
            novo.criar("x1", "gravado", trilha="a.mp3", sem_trilha=SEM_TRILHA, estado=self.estado)
        self.nada_criado()


class IdempotenteESemSobrescrever(Base):
    def test_segunda_chamada_nao_muda_nada(self):
        r1 = self.criar()
        pj, st = r1.pastas.projeto_json, r1.pastas.status_json
        b1, b2 = pj.read_bytes(), st.read_bytes()
        m1, m2 = pj.stat().st_mtime_ns, st.stat().st_mtime_ns
        arv = arvore(self.base)
        r2 = self.criar()
        self.assertFalse(r2.criado)
        self.assertEqual(pj.read_bytes(), b1)
        self.assertEqual(st.read_bytes(), b2)
        self.assertEqual((pj.stat().st_mtime_ns, st.stat().st_mtime_ns), (m1, m2))
        self.assertEqual(arvore(self.base), arv)
        self.assertEqual(r2.projeto, r1.projeto)

    def test_edicao_do_aluno_sobrevive(self):
        r = self.criar()
        p = json.loads(r.pastas.projeto_json.read_text(encoding="utf-8"))
        p["estilo"] = {"hook": "punch"}
        r.pastas.projeto_json.write_text(json.dumps(p, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        editado = r.pastas.projeto_json.read_bytes()
        r2 = self.criar()
        self.assertFalse(r2.criado)
        self.assertEqual(r.pastas.projeto_json.read_bytes(), editado)
        self.assertEqual(r2.projeto["estilo"], {"hook": "punch"})

    def test_roteiro_e_arquivos_do_aluno_nao_sao_tocados(self):
        r = self.criar()
        r.pastas.roteiro.write_text("Roteiro do aluno.\n", encoding="utf-8")
        (r.pastas.voz_dir / "bruto.m4a").write_bytes(b"audio")
        self.criar()
        self.assertEqual(r.pastas.roteiro.read_text(encoding="utf-8"), "Roteiro do aluno.\n")
        self.assertEqual((r.pastas.voz_dir / "bruto.m4a").read_bytes(), b"audio")

    def test_pedido_conflitante_reprova_e_nao_muda(self):
        r = self.criar()
        antes = r.pastas.projeto_json.read_bytes()
        with self.assertRaises(novo.ProjetoJaExiste) as c:
            self.criar(modo="gravado")
        self.assertIn("modo", str(c.exception))
        with self.assertRaises(novo.ProjetoJaExiste) as c2:
            self.criar(look="azul")
        self.assertIn("look", str(c2.exception))
        self.assertEqual(r.pastas.projeto_json.read_bytes(), antes)

    def test_projeto_json_quebrado_nao_e_sobrescrito(self):
        r = self.criar()
        r.pastas.projeto_json.write_text("{quebrado", encoding="utf-8")
        with self.assertRaises(modelo.ContratoInvalido):
            self.criar()
        self.assertEqual(r.pastas.projeto_json.read_text(encoding="utf-8"), "{quebrado")

    def test_pasta_existente_sem_projeto_json_recebe_o_projeto_sem_apagar(self):
        p = pastas.projeto("tres-horas", self.estado)
        p.voz_dir.mkdir(parents=True)
        (p.voz_dir / "bruto.m4a").write_bytes(b"audio")
        r = self.criar()
        self.assertTrue(r.criado)
        self.assertEqual((p.voz_dir / "bruto.m4a").read_bytes(), b"audio")


class Avisos(Base):
    def test_look_ainda_nao_cadastrado(self):
        r = self.criar()
        self.assertTrue(any("laranja" in a for a in r.avisos), r.avisos)

    def test_look_cadastrado_nao_avisa(self):
        looks.adicionar("laranja", "a1b2c3d4e5f6a7b8c9d0", "medio", estado=self.estado)
        r = self.criar()
        self.assertEqual([a for a in r.avisos if "laranja" in a], [])

    def test_trilha_que_nao_esta_em_trilhas(self):
        r = novo.criar("do-doc", "gravado", trilha="leve.mp3", estado=self.estado)
        self.assertTrue(any("leve.mp3" in a for a in r.avisos), r.avisos)
        pastas.trilhas_dir(self.estado).mkdir()
        (pastas.trilhas_dir(self.estado) / "leve.mp3").write_bytes(b"x")
        r2 = novo.criar("outro", "gravado", trilha="leve.mp3", estado=self.estado)
        self.assertEqual([a for a in r2.avisos if "leve.mp3" in a], [])


if __name__ == "__main__":
    unittest.main()
