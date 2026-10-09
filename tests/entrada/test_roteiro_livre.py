"""Testes de entrada/roteiro_livre (W1.B): texto sem nenhum colchete.

Roteiro livre não tem direção: cada parágrafo é um bloco `livre` e o plano propõe as
direções para o aluno aprovar. Este módulo reconhece o caso e entrega o ponto de partida,
sem inventar fala.
"""
import unittest
from pathlib import Path

from entrada import roteiro_livre, roteiro_md

RAIZ = Path(__file__).resolve().parents[2]
EXEMPLOS = RAIZ / "contratos" / "exemplos"

LIVRE = (
    "Você perde três horas por dia nisso aqui. E eu sei porque eu fazia igual,\n"
    "todo santo dia.\n"
    "\n"
    "O problema não é falta de tempo. Com uma automação simples, isso roda sozinho\n"
    "enquanto você atende.\n"
    "\n"
    "Toque em saiba mais e veja como montar a sua.\n"
)


def exemplo(nome):
    return (EXEMPLOS / f"roteiro.valido.{nome}.md").read_text(encoding="utf-8")


class TestAnalisar(unittest.TestCase):

    def test_roteiro_sem_colchete_sai_precisa_plano(self):
        info = roteiro_livre.analisar(LIVRE)
        self.assertTrue(info["precisa_plano"])
        self.assertTrue(info["ok"])

    def test_cada_paragrafo_vira_um_bloco_livre(self):
        info = roteiro_livre.analisar(LIVRE)
        self.assertEqual([b["tipo"] for b in info["blocos"]], ["livre"] * 3)
        self.assertEqual(info["blocos"][0]["fala"],
                         "Você perde três horas por dia nisso aqui. E eu sei porque eu fazia igual, todo santo dia.")

    def test_conta_palavras_por_bloco_e_no_total(self):
        info = roteiro_livre.analisar(LIVRE)
        self.assertEqual(info["palavras_por_bloco"], [18, 17, 10])
        self.assertEqual(info["n_palavras"], 45)

    def test_exemplo_so_fala_do_contrato(self):
        info = roteiro_livre.analisar(exemplo("so-fala"))
        self.assertTrue(info["precisa_plano"])
        self.assertEqual(len(info["blocos"]), 2)

    def test_roteiro_dirigido_nao_precisa_plano(self):
        for nome in ("completo", "lista", "layouts", "cta-logo", "texto-colado"):
            with self.subTest(exemplo=nome):
                self.assertFalse(roteiro_livre.analisar(exemplo(nome))["precisa_plano"])

    def test_texto_colado_do_chat_e_normalizado_antes(self):
        sujo = ("[08/10/2026, 10:32] Ana: Sua agenda está cheia.\r\n\r\n\r\n"
                "[08/10/2026, 10:33] Ana: Toque em saiba mais.\r\n")
        info = roteiro_livre.analisar(sujo)
        self.assertTrue(info["precisa_plano"])
        self.assertEqual([b["fala"] for b in info["blocos"]],
                         ["Sua agenda está cheia.", "Toque em saiba mais."])

    def test_titulo_com_cerquilha_nao_vira_bloco(self):
        info = roteiro_livre.analisar("# Anúncio de teste\n\nPrimeira fala.\n\nSegunda fala.\n")
        self.assertEqual(len(info["blocos"]), 2)

    def test_texto_vazio_nao_e_roteiro(self):
        info = roteiro_livre.analisar("  \n\n")
        self.assertFalse(info["ok"])
        self.assertEqual(info["blocos"], [])
        self.assertEqual(info["n_palavras"], 0)

    def test_erro_de_roteiro_dirigido_aparece_no_resultado(self):
        info = roteiro_livre.analisar("[apresentador] Oi.\n")
        self.assertFalse(info["ok"])
        self.assertIn("cta", [e.campo for e in info["erros"]])


class TestEsqueletoDirigido(unittest.TestCase):

    def test_o_esqueleto_passa_na_gramatica(self):
        texto = roteiro_livre.esqueleto_dirigido(LIVRE)
        lei = roteiro_md.ler(texto)
        self.assertTrue(lei.ok, lei.erros)
        self.assertFalse(lei.precisa_plano)

    def test_a_fala_sai_igual_palavra_por_palavra(self):
        lei = roteiro_md.ler(roteiro_livre.esqueleto_dirigido(LIVRE))
        original = roteiro_md.ler(LIVRE)
        self.assertEqual(lei.sequencia_de_palavras(), original.sequencia_de_palavras())
        self.assertEqual([b["fala"] for b in lei.blocos], [b["fala"] for b in original.blocos])

    def test_blocos_sao_apresentador_e_o_ultimo_e_cta(self):
        lei = roteiro_md.ler(roteiro_livre.esqueleto_dirigido(LIVRE))
        self.assertEqual([b["tipo"] for b in lei.blocos], ["apresentador", "apresentador", "cta"])

    def test_texto_do_botao_e_o_padrao_do_projeto_e_pode_ser_trocado(self):
        padrao = roteiro_md.ler(roteiro_livre.esqueleto_dirigido(LIVRE))
        self.assertEqual(padrao.blocos[-1]["key"], "SAIBA MAIS")
        outro = roteiro_md.ler(roteiro_livre.esqueleto_dirigido(LIVRE, key_cta="QUERO ENTRAR"))
        self.assertEqual(outro.blocos[-1]["key"], "QUERO ENTRAR")

    def test_um_paragrafo_so_vira_so_o_cta(self):
        lei = roteiro_md.ler(roteiro_livre.esqueleto_dirigido("Toque em saiba mais.\n"))
        self.assertTrue(lei.ok, lei.erros)
        self.assertEqual([b["tipo"] for b in lei.blocos], ["cta"])

    def test_o_esqueleto_avisa_que_e_proposta_com_comentario_que_o_leitor_ignora(self):
        texto = roteiro_livre.esqueleto_dirigido(LIVRE)
        primeira = texto.splitlines()[0]
        self.assertTrue(primeira.startswith("#"))
        self.assertIn("aprov", primeira.lower())

    def test_nao_inventa_hook_nem_insert_nem_lettering_alem_do_cta(self):
        lei = roteiro_md.ler(roteiro_livre.esqueleto_dirigido(LIVRE))
        for b in lei.blocos:
            self.assertIsNone(b["hook"])
            self.assertIsNone(b["insert"])
        self.assertEqual([b["key"] for b in lei.blocos[:-1]], [None, None])

    def test_roteiro_que_ja_e_dirigido_e_recusado(self):
        with self.assertRaises(ValueError):
            roteiro_livre.esqueleto_dirigido(exemplo("completo"))

    def test_texto_vazio_e_recusado(self):
        with self.assertRaises(ValueError):
            roteiro_livre.esqueleto_dirigido("\n\n")

    def test_fala_com_colchete_no_meio_e_recusada_em_vez_de_virar_direcao(self):
        with self.assertRaises(ValueError):
            roteiro_livre.esqueleto_dirigido("Oi [pausa] tudo bem.\n\nToque aqui.\n")

    def test_asterisco_de_enfase_passa_para_o_esqueleto(self):
        lei = roteiro_md.ler(roteiro_livre.esqueleto_dirigido("Isso é *muito* bom.\n\nToque aqui.\n"))
        self.assertTrue(lei.ok, lei.erros)
        self.assertEqual(lei.blocos[0]["enfase"], ["muito"])


if __name__ == "__main__":
    unittest.main()
