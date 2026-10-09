"""Testes de projeto/glossario (W1.A): o glossário só troca grafia declarada."""
import json
import tempfile
import unittest
from pathlib import Path

from contratos.validar import validar_arquivo
from projeto import glossario

G = {
    "versao": 1,
    "termos": [
        {"grafia": "Fluxa", "variantes": ["Flucha", "Fluxá", "Flux a"], "tipo": "marca"},
        {"grafia": "Agenda Pro", "variantes": ["agenda pró", "agenda pro ia"], "tipo": "produto"},
        {"grafia": "WhatsApp", "variantes": ["whats app"], "tipo": "termo"},
        {"grafia": "Marina", "tipo": "nome"},
    ],
    "equivalencias": [
        {"roteiro": "vamos embora", "fala": "vambora"},
        {"roteiro": "para", "fala": "pra"},
    ],
}


def w(texto, ini, fim):
    return {"text": texto, "start": ini, "end": fim}


class Aplicar(unittest.TestCase):
    def test_variante_vira_a_grafia(self):
        self.assertEqual(glossario.aplicar("Eu uso a Flucha todo dia.", G), "Eu uso a Fluxa todo dia.")

    def test_variante_com_espaco_e_acento(self):
        self.assertEqual(glossario.aplicar("Abra o Flux a e o Fluxá.", G), "Abra o Fluxa e o Fluxa.")

    def test_caixa_da_variante_nao_importa(self):
        self.assertEqual(glossario.aplicar("flucha e FLUCHA", G), "Fluxa e Fluxa")

    def test_so_troca_o_que_foi_declarado(self):
        t = "Eu uso o Fluxo e o Marina's, mais o zapzap e a flux."
        self.assertEqual(glossario.aplicar(t, G), t)

    def test_grafia_sem_variante_nao_mexe_em_nada(self):
        t = "a marina falou com a MARINA."
        self.assertEqual(glossario.aplicar(t, G), t)

    def test_nao_troca_dentro_de_palavra_maior(self):
        t = "O fluchamento do whats apparatus e a agenda próxima."
        self.assertEqual(glossario.aplicar(t, G), t)

    def test_pontuacao_vizinha_fica(self):
        self.assertEqual(glossario.aplicar("Flucha, né? (whats app) \"Flux a\".", G),
                         "Fluxa, né? (WhatsApp) \"Fluxa\".")

    def test_variante_mais_longa_vence(self):
        self.assertEqual(glossario.aplicar("a agenda pro ia chegou", G), "a Agenda Pro chegou")

    def test_uma_passada_so(self):
        # a saída de uma troca nunca é reprocessada
        self.assertEqual(glossario.aplicar("Flux a Fluxa", G), "Fluxa Fluxa")

    def test_sem_termos_devolve_igual(self):
        t = "Nada para trocar aqui."
        self.assertEqual(glossario.aplicar(t, {"versao": 1, "termos": []}), t)
        self.assertEqual(glossario.aplicar("", G), "")

    def test_nao_trata_variante_como_regex(self):
        g = {"versao": 1, "termos": [{"grafia": "C++", "variantes": ["c mais mais", "c.+"]}]}
        self.assertEqual(glossario.aplicar("c mais mais e c.+ e cabana", g), "C++ e C++ e cabana")

    def test_quebra_de_linha_entre_palavras_da_variante(self):
        self.assertEqual(glossario.aplicar("o whats\napp novo", G), "o WhatsApp novo")


class AplicarNasPalavras(unittest.TestCase):
    def test_variante_de_uma_palavra(self):
        out = glossario.corrigir_palavras([w("Eu", 0.0, 0.2), w("Flucha,", 0.2, 0.7)], G)
        self.assertEqual(out, [w("Eu", 0.0, 0.2), w("Fluxa,", 0.2, 0.7)])

    def test_variante_de_duas_palavras_junta_os_tempos(self):
        palavras = [w("o", 0.0, 0.1), w("Flux", 0.1, 0.4), w("a.", 0.45, 0.8), w("abre", 0.9, 1.2)]
        out = glossario.corrigir_palavras(palavras, G)
        self.assertEqual(out, [w("o", 0.0, 0.1), w("Fluxa.", 0.1, 0.8), w("abre", 0.9, 1.2)])

    def test_sem_variante_devolve_o_mesmo(self):
        palavras = [w("oi", 0.0, 0.2), w("pessoal", 0.2, 0.6)]
        self.assertEqual(glossario.corrigir_palavras(palavras, G), palavras)

    def test_nao_muda_a_lista_de_entrada(self):
        palavras = [w("Flucha", 0.0, 0.5)]
        glossario.corrigir_palavras(palavras, G)
        self.assertEqual(palavras, [w("Flucha", 0.0, 0.5)])

    def test_tempos_continuam_em_ordem(self):
        palavras = [w("whats", 0.0, 0.3), w("app", 0.3, 0.6), w("e", 0.6, 0.7), w("agenda", 0.7, 1.0),
                    w("pró", 1.0, 1.3), w("Flux", 1.4, 1.6), w("a", 1.6, 1.8)]
        out = glossario.corrigir_palavras(palavras, G)
        self.assertEqual([p["text"] for p in out], ["WhatsApp", "e", "Agenda Pro", "Fluxa"])
        ini = [p["start"] for p in out]
        self.assertEqual(ini, sorted(ini))
        for p in out:
            self.assertLessEqual(p["start"], p["end"])


class PromptEEquivalencias(unittest.TestCase):
    def test_prompt_do_asr_lista_as_grafias(self):
        p = glossario.prompt_asr(G)
        for g in ("Fluxa", "Agenda Pro", "WhatsApp", "Marina"):
            self.assertIn(g, p)
        self.assertNotIn("Flucha", p)
        self.assertEqual(glossario.prompt_asr({"versao": 1, "termos": []}), "")

    def test_equivalencia_declarada_vale_so_no_sentido_roteiro_para_fala(self):
        self.assertTrue(glossario.aceita_equivalencia("vamos embora", "vambora", G))
        self.assertTrue(glossario.aceita_equivalencia("Vamos embora!", "vambora", G))
        self.assertFalse(glossario.aceita_equivalencia("vambora", "vamos embora", G))

    def test_igual_apos_normalizar(self):
        self.assertTrue(glossario.aceita_equivalencia("Você, hoje!", "voce hoje", G))

    def test_diferente_nao_passa(self):
        self.assertFalse(glossario.aceita_equivalencia("vamos embora", "vamos ficar", G))
        self.assertFalse(glossario.aceita_equivalencia("para", "pro", G))

    def test_pares(self):
        self.assertEqual(glossario.equivalencias(G), [("vamos embora", "vambora"), ("para", "pra")])
        self.assertEqual(glossario.equivalencias({"versao": 1, "termos": []}), [])


class Arquivo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.estado = Path(self.tmp.name) / "_local"
        self.estado.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    @property
    def arquivo(self):
        return self.estado / "glossario.json"

    def test_sem_arquivo_e_vazio(self):
        self.assertEqual(glossario.carregar(self.estado), {"versao": 1, "termos": []})

    def test_exemplo_valido_carrega(self):
        ex = Path(__file__).resolve().parents[2] / "contratos" / "exemplos" / "glossario.valido.json"
        self.arquivo.write_bytes(ex.read_bytes())
        self.assertEqual(len(glossario.carregar(self.estado)["termos"]), 4)

    def test_exemplos_invalidos_reprovam(self):
        raiz = Path(__file__).resolve().parents[2] / "contratos" / "exemplos"
        invalidos = sorted(raiz.glob("glossario.invalido.*.json"))
        self.assertEqual(len(invalidos), 4)
        for f in invalidos:
            self.arquivo.write_bytes(f.read_bytes())
            with self.assertRaises(glossario.GlossarioInvalido, msg=f.name):
                glossario.carregar(self.estado)

    def test_adicionar_termo_grava_valido(self):
        glossario.adicionar_termo("Fluxa", ["Flucha"], tipo="marca", estado=self.estado)
        glossario.adicionar_termo("Marina", tipo="nome", estado=self.estado)
        d = json.loads(self.arquivo.read_text(encoding="utf-8"))
        self.assertEqual(d["termos"][0], {"grafia": "Fluxa", "variantes": ["Flucha"], "tipo": "marca"})
        self.assertEqual([t["grafia"] for t in d["termos"]], ["Fluxa", "Marina"])
        self.assertEqual([str(e) for e in validar_arquivo(self.arquivo)], [])

    def test_adicionar_a_termo_existente_soma_variantes_sem_repetir(self):
        glossario.adicionar_termo("Fluxa", ["Flucha"], estado=self.estado)
        glossario.adicionar_termo("fluxa", ["Flucha", "Fluxá"], estado=self.estado)
        d = glossario.carregar(self.estado)
        self.assertEqual(len(d["termos"]), 1)
        self.assertEqual(d["termos"][0]["variantes"], ["Flucha", "Fluxá"])
        self.assertEqual(d["termos"][0]["grafia"], "Fluxa")

    def test_variante_de_dois_termos_reprova_e_nao_grava(self):
        glossario.adicionar_termo("Fluxa", ["Fluxo"], estado=self.estado)
        antes = self.arquivo.read_bytes()
        with self.assertRaises(glossario.GlossarioInvalido) as c:
            glossario.adicionar_termo("Flux Pro", ["Fluxo"], estado=self.estado)
        self.assertIn("Fluxo", str(c.exception))
        self.assertEqual(self.arquivo.read_bytes(), antes)

    def test_adicionar_equivalencia(self):
        glossario.adicionar_equivalencia("vamos embora", "vambora", estado=self.estado)
        glossario.adicionar_equivalencia("vamos embora", "vambora", estado=self.estado)  # idempotente
        self.assertEqual(glossario.equivalencias(glossario.carregar(self.estado)), [("vamos embora", "vambora")])

    def test_carregar_aplicando_a_pasta_do_aluno(self):
        glossario.adicionar_termo("Fluxa", ["Flucha"], estado=self.estado)
        g = glossario.carregar(self.estado)
        self.assertEqual(glossario.aplicar("a Flucha", g), "a Fluxa")


if __name__ == "__main__":
    unittest.main()
