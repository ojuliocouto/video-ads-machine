"""Testes de projeto/modelo (W1.A): projeto.json, padrões por modo e erros que nomeiam o campo."""
import sys
from pathlib import Path

_SCRIPTS = str(Path(__file__).resolve().parents[2] / "scripts")
if _SCRIPTS not in sys.path:  # roda também no unittest puro (sem o pythonpath do pytest.ini)
    sys.path.insert(0, _SCRIPTS)

import copy
import json
import tempfile
import unittest

from projeto import modelo

RAIZ = Path(__file__).resolve().parents[2]
EXEMPLOS = RAIZ / "contratos" / "exemplos"

TRILHA_OFF = {"desligada": True, "motivo": "anúncio de teste, sem trilha licenciada ainda"}


def minimo(modo="avatar", **extra):
    d = {"versao": 1, "slug": "tres-horas", "modo": modo, "trilha": dict(TRILHA_OFF)}
    if modo == "avatar":
        d["look"] = "laranja"
    d.update(extra)
    return d


class PadroesPorModo(unittest.TestCase):
    def test_minimo_avatar_recebe_135(self):
        p = modelo.normalizar(minimo("avatar"))
        self.assertEqual(p["aceleracao"], 1.35)

    def test_minimo_gravado_recebe_12(self):
        self.assertEqual(modelo.normalizar(minimo("gravado"))["aceleracao"], 1.2)

    def test_minimo_oneshot_recebe_12(self):
        self.assertEqual(modelo.normalizar(minimo("oneshot"))["aceleracao"], 1.2)

    def test_outros_padroes(self):
        p = modelo.normalizar(minimo("avatar"))
        self.assertEqual(p["formato"], "9x16")
        self.assertEqual(p["cta"]["label"], "saiba mais")

    def test_cta_sem_label_recebe_o_padrao_e_guarda_o_resto(self):
        p = modelo.normalizar(minimo("avatar", cta={"sem_lead": True}))
        self.assertEqual(p["cta"], {"label": "saiba mais", "sem_lead": True})

    def test_valor_explicito_vence_o_padrao(self):
        p = modelo.normalizar(minimo("avatar", aceleracao=1.5, formato="1x1",
                                     cta={"label": "cadastre-se"}))
        self.assertEqual((p["aceleracao"], p["formato"], p["cta"]["label"]), (1.5, "1x1", "cadastre-se"))

    def test_nao_muda_a_entrada(self):
        d = minimo("avatar")
        antes = copy.deepcopy(d)
        modelo.normalizar(d)
        self.assertEqual(d, antes)

    def test_tabela_de_padroes_publica(self):
        self.assertEqual(modelo.PADRAO_ACELERACAO, {"avatar": 1.35, "gravado": 1.2, "oneshot": 1.2})


class Reprovacoes(unittest.TestCase):
    def erro(self, dados):
        with self.assertRaises(modelo.ContratoInvalido) as c:
            modelo.normalizar(dados)
        return c.exception

    def test_campo_desconhecido_cita_o_nome(self):
        e = self.erro(minimo("avatar", planilha="1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"))
        self.assertIn("planilha", str(e))
        self.assertIn("planilha", [x.campo for x in e.erros])

    def test_campo_desconhecido_aninhado_cita_o_nome(self):
        e = self.erro(minimo("avatar", estilo={"cor_magica": "rosa"}))
        self.assertIn("cor_magica", str(e))

    def test_trilha_ausente(self):
        d = minimo("gravado")
        del d["trilha"]
        e = self.erro(d)
        self.assertIn("trilha", [x.campo for x in e.erros])

    def test_trilha_desligada_sem_motivo(self):
        e = self.erro(minimo("avatar", trilha={"desligada": True}))
        self.assertIn("motivo", str(e))

    def test_trilha_desligada_com_motivo_curto_demais(self):
        self.erro(minimo("avatar", trilha={"desligada": True, "motivo": "x"}))

    def test_trilha_desligada_com_motivo_passa(self):
        modelo.normalizar(minimo("avatar", trilha={"desligada": True, "motivo": "take com som bom"}))

    def test_trilha_com_arquivo_passa_e_com_pasta_reprova(self):
        modelo.normalizar(minimo("gravado", trilha={"arquivo": "leve.mp3"}))
        self.erro(minimo("gravado", trilha={"arquivo": "/home/fulano/musicas/trilha.mp3"}))
        self.erro(minimo("gravado", trilha={"arquivo": "../leve.mp3"}))

    def test_avatar_sem_look(self):
        d = minimo("avatar")
        del d["look"]
        self.assertIn("look", [x.campo for x in self.erro(d).erros])

    def test_gravado_sem_look_passa(self):
        modelo.normalizar(minimo("gravado"))

    def test_doc_google_sem_doc_id(self):
        e = self.erro(minimo("gravado", origem={"tipo": "doc_google"}))
        self.assertIn("doc_id", str(e))

    def test_modo_desconhecido_e_aceleracao_fora_da_faixa(self):
        d = minimo("avatar")
        d["modo"] = "vsl"
        self.erro(d)
        self.erro(minimo("avatar", aceleracao=0.8))
        self.erro(minimo("avatar", aceleracao=2.0))

    def test_versao_errada(self):
        self.erro(minimo("avatar", versao=2))

    def test_nao_e_objeto(self):
        self.erro([1, 2])

    def test_mensagem_lista_todos_os_erros(self):
        e = self.erro(minimo("avatar", planilha="x", aceleracao=0.1))
        texto = str(e)
        self.assertIn("planilha", texto)
        self.assertIn("aceleracao", texto)
        self.assertGreaterEqual(len(e.erros), 2)


class Excecoes(unittest.TestCase):
    def test_motivo_da_excecao(self):
        p = modelo.normalizar(minimo("avatar", excecoes=[{"regra": "densidade", "motivo": "prova social precisa do rosto"}]))
        self.assertEqual(modelo.motivo_excecao(p, "densidade"), "prova social precisa do rosto")
        self.assertIsNone(modelo.motivo_excecao(p, "gate_cor"))

    def test_sem_excecoes(self):
        self.assertIsNone(modelo.motivo_excecao(modelo.normalizar(minimo("avatar")), "densidade"))

    def test_excecao_sem_motivo_reprova(self):
        with self.assertRaises(modelo.ContratoInvalido):
            modelo.normalizar(minimo("avatar", excecoes=[{"regra": "densidade"}]))


class Arquivo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_exemplos_validos_do_contrato_carregam(self):
        validos = sorted(EXEMPLOS.glob("projeto.valido.*.json"))
        self.assertGreaterEqual(len(validos), 4)
        for f in validos:
            p = modelo.carregar(f)
            self.assertIn("aceleracao", p, f.name)

    def test_exemplos_invalidos_do_contrato_reprovam(self):
        invalidos = sorted(EXEMPLOS.glob("projeto.invalido.*.json"))
        self.assertGreaterEqual(len(invalidos), 9)
        for f in invalidos:
            with self.assertRaises(modelo.ContratoInvalido, msg=f.name):
                modelo.carregar(f)

    def test_erro_cita_o_arquivo(self):
        f = EXEMPLOS / "projeto.invalido.planilha.json"
        with self.assertRaises(modelo.ContratoInvalido) as c:
            modelo.carregar(f)
        self.assertIn("projeto.invalido.planilha.json", str(c.exception))

    def test_json_quebrado(self):
        f = self.pasta / "projeto.json"
        f.write_text("{não é json", encoding="utf-8")
        with self.assertRaises(modelo.ContratoInvalido) as c:
            modelo.carregar(f)
        self.assertIn("projeto.json", str(c.exception))

    def test_chave_repetida_reprova(self):
        f = self.pasta / "projeto.json"
        f.write_text('{"versao": 1, "slug": "a", "slug": "b", "modo": "gravado", '
                     '"trilha": {"desligada": true, "motivo": "sem trilha hoje"}}', encoding="utf-8")
        with self.assertRaises(modelo.ContratoInvalido) as c:
            modelo.carregar(f)
        self.assertIn("slug", str(c.exception))

    def test_arquivo_ausente(self):
        with self.assertRaises(FileNotFoundError):
            modelo.carregar(self.pasta / "nao-existe.json")

    def test_escrever_e_reler(self):
        f = self.pasta / "x" / "projeto.json"
        modelo.escrever(f, minimo("avatar"))
        lido = json.loads(f.read_text(encoding="utf-8"))
        self.assertEqual(lido["aceleracao"], 1.35)
        self.assertEqual(modelo.carregar(f), lido)
        self.assertTrue(f.read_text(encoding="utf-8").endswith("\n"))
        self.assertIn("anúncio", f.read_text(encoding="utf-8"))  # sem ú

    def test_escrever_invalido_nao_cria_nada(self):
        f = self.pasta / "projeto.json"
        with self.assertRaises(modelo.ContratoInvalido):
            modelo.escrever(f, minimo("avatar", planilha="x"))
        self.assertFalse(f.exists())
        self.assertEqual(list(self.pasta.iterdir()), [])


class Construtor(unittest.TestCase):
    def test_minimo_monta_um_projeto_valido(self):
        p = modelo.minimo("tres-horas", "avatar", look="laranja", sem_trilha="anúncio de teste, sem trilha")
        self.assertEqual(p["versao"], 1)
        self.assertEqual(p["trilha"], {"desligada": True, "motivo": "anúncio de teste, sem trilha"})
        modelo.normalizar(p)

    def test_minimo_com_trilha_e_origem(self):
        p = modelo.minimo("x1", "gravado", trilha="leve.mp3", origem={"tipo": "arquivo"})
        self.assertEqual(p["trilha"], {"arquivo": "leve.mp3"})
        self.assertEqual(p["origem"], {"tipo": "arquivo"})

    def test_minimo_sem_trilha_nenhuma_reprova_ao_normalizar(self):
        with self.assertRaises(modelo.ContratoInvalido):
            modelo.normalizar(modelo.minimo("x1", "gravado"))

    def test_trilha_e_sem_trilha_juntas(self):
        with self.assertRaises(ValueError):
            modelo.minimo("x1", "gravado", trilha="a.mp3", sem_trilha="motivo qualquer")


if __name__ == "__main__":
    unittest.main()
