"""Testes de entrada/doc_google (W1.B): o Google Doc do PRÓPRIO aluno, com comentários.

Opcional. Só liga o gate de fidelidade ao doc quando o projeto nasce de um Doc. Todo HTTP é
simulado: nenhum teste abre socket. O token OAuth vem de variável de ambiente, nunca de um
arquivo da máquina.
"""
import json
import socket
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from entrada import doc_google, roteiro_md

RAIZ = Path(__file__).resolve().parents[2]
ENTRADA = RAIZ / "scripts" / "entrada"
DOC_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
TOKEN = "ya29.TOKEN-SECRETO-DE-TESTE"


class FakeHttp:
    """Respostas em fila por trecho de URL; cada rota é consumida uma vez."""

    def __init__(self, *rotas):
        self.rotas = list(rotas)
        self.chamadas = []

    def __call__(self, url, headers):
        self.chamadas.append((url, dict(headers)))
        for i, (trecho, status, corpo) in enumerate(self.rotas):
            if trecho in url:
                self.rotas.pop(i)
                dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode("utf-8")
                return status, dados
        raise AssertionError(f"chamada HTTP inesperada: {url}")


def cliente(*rotas, dormidas=None):
    http = FakeHttp(*rotas)
    esperas = dormidas if dormidas is not None else []
    return doc_google.Cliente(token=TOKEN, http=http, dormir=esperas.append), http, esperas


def comentario(i, ancora, content, replies=(), resolved=False, criado="2026-10-08T10:00:00.000Z", deleted=False):
    return {"id": f"c{i}", "content": content, "createdTime": criado, "resolved": resolved,
            "deleted": deleted, "quotedFileContent": {"value": ancora},
            "author": {"displayName": "Ana"},
            "replies": [{"id": f"c{i}r{j}", "content": r if isinstance(r, str) else r[0],
                         "deleted": False if isinstance(r, str) else r[1],
                         "createdTime": f"2026-10-08T11:0{j}:00.000Z", "author": {"displayName": "Beto"}}
                        for j, r in enumerate(replies)]}


def paragrafo(texto):
    return {"paragraph": {"elements": [{"textRun": {"content": texto + "\n"}}]}}


def documento_simples(*textos, titulo="Roteiro de teste"):
    return {"title": titulo, "tabs": [{"tabProperties": {"title": "Aba 1"},
                                       "documentTab": {"body": {"content": [paragrafo(t) for t in textos]}}}]}


G1 = "https://drive.google.com/file/d/1AAAAAAAAAAAAAAAAAAAAA/view?usp=sharing"
G2 = "https://drive.google.com/file/d/1BBBBBBBBBBBBBBBBBBBBB/view"
G3 = "https://drive.google.com/open?id=1CCCCCCCCCCCCCCCCCCCCC"


class TestToken(unittest.TestCase):

    def test_sem_token_diz_a_variavel_e_nao_chama_a_rede(self):
        http = FakeHttp()
        with self.assertRaises(doc_google.ErroGoogle) as ctx:
            doc_google.Cliente(http=http, env={})
        self.assertIn("GOOGLE_OAUTH_ACCESS_TOKEN", str(ctx.exception))
        self.assertEqual(http.chamadas, [])

    def test_token_vem_do_ambiente_recebido(self):
        http = FakeHttp(("/comments", 200, {"comments": []}))
        c = doc_google.Cliente(http=http, env={"GOOGLE_OAUTH_ACCESS_TOKEN": "  abc123  "})
        c.comentarios(DOC_ID)
        self.assertEqual(http.chamadas[0][1]["Authorization"], "Bearer abc123")

    def test_variavel_vazia_conta_como_ausente(self):
        with self.assertRaises(doc_google.ErroGoogle):
            doc_google.Cliente(env={"GOOGLE_OAUTH_ACCESS_TOKEN": "   "})

    def test_token_com_espaco_no_meio_e_recusado(self):
        with self.assertRaises(doc_google.ErroGoogle):
            doc_google.Cliente(env={"GOOGLE_OAUTH_ACCESS_TOKEN": "abc def"})

    def test_o_token_nunca_aparece_em_erro_nem_em_repr(self):
        c, _, _ = cliente(("/comments", 401, {"error": {"message": "invalid"}}))
        with self.assertRaises(doc_google.ErroGoogle) as ctx:
            c.comentarios(DOC_ID)
        self.assertNotIn(TOKEN, str(ctx.exception))
        self.assertNotIn(TOKEN, repr(c))
        self.assertNotIn(TOKEN, str(c))

    def test_o_modulo_nao_le_arquivo_de_token_da_maquina(self):
        import ast
        src = (ENTRADA / "doc_google.py").read_text(encoding="utf-8")
        for proibido in ("google-tokens", "." + "clau" + "de", "expanduser", "refresh_token"):
            self.assertNotIn(proibido, src)
        leituras = {"open", "read_text", "read_bytes", "home", "expanduser", "getenv", "listdir", "glob"}
        chamadas = set()
        for no in ast.walk(ast.parse(src)):
            if isinstance(no, ast.Call):
                f = no.func
                chamadas.add(f.id if isinstance(f, ast.Name) else getattr(f, "attr", ""))
        self.assertEqual(chamadas & leituras, set())

    def test_sem_variavel_no_ambiente_real_tambem_falha_claro(self):
        import os
        guardado = os.environ.pop("GOOGLE_OAUTH_ACCESS_TOKEN", None)
        try:
            with self.assertRaises(doc_google.ErroGoogle):
                doc_google.Cliente(http=FakeHttp())
        finally:
            if guardado is not None:
                os.environ["GOOGLE_OAUTH_ACCESS_TOKEN"] = guardado


class TestIdDoDocumento(unittest.TestCase):

    def test_aceita_o_id_e_a_url(self):
        self.assertEqual(doc_google.id_do_documento(DOC_ID), DOC_ID)
        self.assertEqual(doc_google.id_do_documento(f"https://docs.google.com/document/d/{DOC_ID}/edit?tab=t.0"), DOC_ID)
        self.assertEqual(doc_google.id_do_documento(f"  https://docs.google.com/document/u/0/d/{DOC_ID}  "), DOC_ID)

    def test_recusa_o_que_nao_parece_id_antes_de_qualquer_chamada(self):
        for ruim in ("", "curto", "../../etc/passwd" + "x" * 20, "a b" * 20, "https://exemplo.com/d/" + DOC_ID,
                     DOC_ID + "?fields=*", DOC_ID + "/comments"):
            with self.subTest(valor=ruim):
                with self.assertRaises(doc_google.ErroGoogle):
                    doc_google.id_do_documento(ruim)

    def test_cliente_nao_chama_a_api_com_id_ruim(self):
        c, http, _ = cliente()
        with self.assertRaises(doc_google.ErroGoogle):
            c.comentarios("curto")
        with self.assertRaises(doc_google.ErroGoogle):
            c.documento("curto")
        self.assertEqual(http.chamadas, [])


class TestComentarios(unittest.TestCase):

    def ler(self, *comentarios, **kw):
        c, http, _ = cliente(("/comments", 200, {"comments": list(comentarios)}))
        return doc_google.ler_comentarios(DOC_ID, cliente=c, **kw), http

    def test_comentario_com_tres_links_vira_tres_assets_na_ancora(self):
        lidos, _ = self.ler(comentario(1, "[Inserir imagens]", f"Usa essas três: {G1} e {G2}, mais {G3}"))
        c = lidos[0]
        self.assertEqual(c["ancora"], "[Inserir imagens]")
        self.assertEqual([a["ordem"] for a in c["assets"]], [1, 2, 3])
        self.assertEqual([a["url"] for a in c["assets"]], [G1, G2, G3])
        self.assertEqual([a["id"] for a in c["assets"]],
                         ["1AAAAAAAAAAAAAAAAAAAAA", "1BBBBBBBBBBBBBBBBBBBBB", "1CCCCCCCCCCCCCCCCCCCCC"])
        self.assertEqual({a["tipo"] for a in c["assets"]}, {"drive"})
        self.assertEqual({a["de"] for a in c["assets"]}, {"comentario"})
        self.assertEqual(c["links"], [G1, G2, G3])
        self.assertEqual(c["texto"], "Usa essas três: e , mais")

    def test_pipoca_vira_sequencia_na_ordem_dos_links(self):
        lidos, _ = self.ler(comentario(1, "[Pipoca de telas]", f"{G2} depois {G1} depois {G3}"))
        c = lidos[0]
        self.assertTrue(c["pipoca"])
        self.assertEqual(c["sequencia"], [G2, G1, G3])
        self.assertEqual([a["url"] for a in c["assets"]], [G2, G1, G3])

    def test_pipoca_tambem_vale_quando_a_palavra_esta_no_comentario(self):
        lidos, _ = self.ler(comentario(1, "[Inserir telas]", f"Faz uma pipoca com {G1} e {G2}"))
        self.assertTrue(lidos[0]["pipoca"])

    def test_varios_links_sem_pipoca_sao_assets_mas_nao_sequencia(self):
        lidos, _ = self.ler(comentario(1, "[Inserir telas]", f"{G1} {G2}"))
        self.assertFalse(lidos[0]["pipoca"])
        self.assertEqual(lidos[0]["sequencia"], [])
        self.assertEqual(len(lidos[0]["assets"]), 2)

    def test_resolvido_e_lido(self):
        lidos, _ = self.ler(comentario(1, "[A]", "ok", resolved=True), comentario(2, "[B]", "x", resolved=False))
        self.assertEqual([c["resolvido"] for c in lidos], [True, False])

    def test_respostas_sao_lidas_com_autor_texto_e_links(self):
        lidos, _ = self.ler(comentario(1, "[A]", f"Use {G1}", replies=(f"Troquei por {G2}", "valeu")))
        c = lidos[0]
        self.assertEqual([r["autor"] for r in c["respostas"]], ["Beto", "Beto"])
        self.assertEqual([r["texto"] for r in c["respostas"]], ["Troquei por", "valeu"])
        self.assertEqual(c["respostas"][0]["links"], [G2])
        self.assertEqual([(a["url"], a["de"]) for a in c["assets"]], [(G1, "comentario"), (G2, "resposta")])
        self.assertEqual(c["links"], [G1, G2])

    def test_pipoca_pode_estar_na_resposta(self):
        lidos, _ = self.ler(comentario(1, "[A]", f"{G1}", replies=("é pipoca, junta com " + G2,)))
        self.assertTrue(lidos[0]["pipoca"])
        self.assertEqual(lidos[0]["sequencia"], [G1, G2])

    def test_comentario_e_resposta_apagados_nao_entram(self):
        lidos, _ = self.ler(comentario(1, "[A]", "x", deleted=True),
                            comentario(2, "[B]", f"{G1}", replies=(("apagada " + G2, True), "fica")))
        self.assertEqual([c["id"] for c in lidos], ["c2"])
        self.assertEqual([r["texto"] for r in lidos[0]["respostas"]], ["fica"])
        self.assertEqual(lidos[0]["links"], [G1])

    def test_ancora_sai_sem_entidade_html_e_sem_espaco_nas_pontas(self):
        lidos, _ = self.ler(comentario(1, "  [Inserir &amp; mostrar]\n", "x"))
        self.assertEqual(lidos[0]["ancora"], "[Inserir & mostrar]")

    def test_comentario_geral_sem_ancora(self):
        c = comentario(1, "", "tira esse trecho")
        del c["quotedFileContent"]
        lidos, _ = self.ler(c)
        self.assertEqual(lidos[0]["ancora"], "")

    def test_pontuacao_colada_no_link_nao_entra_na_url(self):
        lidos, _ = self.ler(comentario(1, "[A]", f"({G1}), depois {G2}."))
        self.assertEqual(lidos[0]["links"], [G1, G2])

    def test_link_fora_do_drive_e_asset_do_tipo_web(self):
        lidos, _ = self.ler(comentario(1, "[A]", "https://www.youtube.com/watch?v=abc123"))
        a = lidos[0]["assets"][0]
        self.assertEqual((a["tipo"], a["id"]), ("web", None))

    def test_ordem_cronologica(self):
        lidos, _ = self.ler(comentario(2, "[B]", "b", criado="2026-10-08T12:00:00.000Z"),
                            comentario(1, "[A]", "a", criado="2026-10-08T09:00:00.000Z"))
        self.assertEqual([c["id"] for c in lidos], ["c1", "c2"])

    def test_pede_so_os_campos_que_usa_e_100_por_pagina(self):
        _, http = self.ler(comentario(1, "[A]", "x"))
        url, headers = http.chamadas[0]
        partes = urlparse(url)
        self.assertEqual(partes.netloc, "www.googleapis.com")
        self.assertEqual(partes.path, f"/drive/v3/files/{DOC_ID}/comments")
        q = parse_qs(partes.query)
        self.assertEqual(q["pageSize"], ["100"])
        for campo in ("quotedFileContent", "resolved", "replies", "createdTime", "deleted"):
            self.assertIn(campo, q["fields"][0])
        self.assertEqual(headers["Authorization"], f"Bearer {TOKEN}")


class TestPaginacao(unittest.TestCase):

    def test_le_todas_as_paginas(self):
        c, http, _ = cliente(
            ("pageToken=p2", 200, {"comments": [comentario(3, "[C]", "c", criado="2026-10-08T12:00:00.000Z")]}),
            ("/comments", 200, {"nextPageToken": "p2",
                                "comments": [comentario(1, "[A]", "a", criado="2026-10-08T10:00:00.000Z"),
                                             comentario(2, "[B]", "b", criado="2026-10-08T11:00:00.000Z")]}),
        )
        lidos = doc_google.ler_comentarios(DOC_ID, cliente=c)
        self.assertEqual([x["id"] for x in lidos], ["c1", "c2", "c3"])
        self.assertEqual(len(http.chamadas), 2)
        self.assertEqual(parse_qs(urlparse(http.chamadas[1][0]).query)["pageToken"], ["p2"])

    def test_pagina_que_repete_o_token_nao_vira_laco_infinito(self):
        pagina = {"nextPageToken": "p2", "comments": [comentario(1, "[A]", "a")]}
        c, _, _ = cliente(("/comments", 200, pagina), ("pageToken=p2", 200, pagina), ("pageToken=p2", 200, pagina))
        with self.assertRaises(doc_google.ErroGoogle):
            doc_google.ler_comentarios(DOC_ID, cliente=c)


class TestRedeELimite(unittest.TestCase):

    def test_429_uma_vez_espera_e_tenta_de_novo(self):
        c, http, esperas = cliente(("/comments", 429, {}), ("/comments", 200, {"comments": []}))
        self.assertEqual(doc_google.ler_comentarios(DOC_ID, cliente=c), [])
        self.assertEqual(len(http.chamadas), 2)
        self.assertEqual(len(esperas), 1)
        self.assertGreater(esperas[0], 0)

    def test_429_duas_vezes_para_com_mensagem_clara(self):
        c, http, esperas = cliente(("/comments", 429, {}), ("/comments", 429, {}), ("/comments", 200, {"comments": []}))
        with self.assertRaises(doc_google.ErroGoogle) as ctx:
            doc_google.ler_comentarios(DOC_ID, cliente=c)
        self.assertEqual(len(http.chamadas), 2)       # no máximo 1 retry
        self.assertIn("429", str(ctx.exception))
        self.assertIn("duas vezes", str(ctx.exception))

    def test_503_tambem_tenta_so_uma_vez_a_mais(self):
        c, http, _ = cliente(("/comments", 503, {}), ("/comments", 200, {"comments": []}))
        doc_google.ler_comentarios(DOC_ID, cliente=c)
        self.assertEqual(len(http.chamadas), 2)

    def test_401_nao_repete_e_manda_gerar_outro_token(self):
        c, http, _ = cliente(("/comments", 401, {}), ("/comments", 200, {"comments": []}))
        with self.assertRaises(doc_google.ErroGoogle) as ctx:
            doc_google.ler_comentarios(DOC_ID, cliente=c)
        self.assertEqual(len(http.chamadas), 1)
        self.assertIn("GOOGLE_OAUTH_ACCESS_TOKEN", str(ctx.exception))

    def test_404_diz_que_pode_ser_falta_de_acesso(self):
        c, _, _ = cliente(("/documents/", 404, {}))
        with self.assertRaises(doc_google.ErroGoogle) as ctx:
            c.documento(DOC_ID)
        self.assertIn("acesso", str(ctx.exception))

    def test_resposta_que_nao_e_json_vira_erro_do_modulo(self):
        c, _, _ = cliente(("/comments", 200, b"<html>oops</html>"))
        with self.assertRaises(doc_google.ErroGoogle):
            c.comentarios(DOC_ID)

    def test_leitura_com_o_socket_bloqueado_usa_so_o_http_injetado(self):
        original = socket.socket

        def bloqueado(*a, **k):
            raise AssertionError("abriu socket de verdade")

        socket.socket = bloqueado
        try:
            c, _, _ = cliente(("/comments", 200, {"comments": [comentario(1, "[A]", f"{G1}")]}))
            self.assertEqual(len(doc_google.ler_comentarios(DOC_ID, cliente=c)), 1)
        finally:
            socket.socket = original


class TestDocumento(unittest.TestCase):

    def test_le_abas_filhas_e_tabelas_na_ordem_do_documento(self):
        doc = {
            "title": "Roteiro",
            "tabs": [
                {"tabProperties": {"title": "Principal"},
                 "documentTab": {"body": {"content": [
                     paragrafo("Linha 1"),
                     {"table": {"tableRows": [{"tableCells": [{"content": [paragrafo("Célula A")]},
                                                               {"content": [paragrafo("Célula B")]}]}]}},
                     {"sectionBreak": {}},
                     paragrafo("Linha 2"),
                 ]}},
                 "childTabs": [{"tabProperties": {"title": "Filha"},
                                "documentTab": {"body": {"content": [paragrafo("Filha 1")]}}}]},
                {"tabProperties": {"title": "Outra"},
                 "documentTab": {"body": {"content": [paragrafo("Outra 1")]}}},
            ],
        }
        c, http, _ = cliente(("/documents/", 200, doc))
        lido = doc_google.ler_documento(DOC_ID, cliente=c)
        self.assertEqual([a["titulo"] for a in lido["abas"]], ["Principal", "Filha", "Outra"])
        self.assertEqual(lido["abas"][0]["paragrafos"], ["Linha 1", "Célula A", "Célula B", "Linha 2"])
        self.assertEqual(lido["paragrafos"], ["Linha 1", "Célula A", "Célula B", "Linha 2", "Filha 1", "Outra 1"])
        self.assertEqual(lido["titulo"], "Roteiro")
        url = http.chamadas[0][0]
        self.assertEqual(urlparse(url).netloc, "docs.googleapis.com")
        self.assertEqual(parse_qs(urlparse(url).query)["includeTabsContent"], ["true"])

    def test_documento_sem_abas_usa_o_corpo(self):
        doc = {"title": "Sem abas", "body": {"content": [paragrafo("Só corpo")]}}
        c, _, _ = cliente(("/documents/", 200, doc))
        lido = doc_google.ler_documento(DOC_ID, cliente=c)
        self.assertEqual(lido["paragrafos"], ["Só corpo"])
        self.assertEqual(lido["abas"][0]["titulo"], "Sem abas")

    def test_quebra_suave_do_docs_vira_quebra_de_linha_e_elementos_sem_texto_sao_ignorados(self):
        doc = {"title": "x", "tabs": [{"tabProperties": {"title": "A"}, "documentTab": {"body": {"content": [
            {"paragraph": {"elements": [{"textRun": {"content": "um\u000bdois"}},
                                        {"inlineObjectElement": {"inlineObjectId": "o1"}},
                                        {"textRun": {"content": " três\n"}}]}}]}}}]}
        c, _, _ = cliente(("/documents/", 200, doc))
        self.assertEqual(doc_google.ler_documento(DOC_ID, cliente=c)["paragrafos"], ["um\ndois três"])

    def test_paragrafo_vazio_e_mantido_como_separador(self):
        c, _, _ = cliente(("/documents/", 200, documento_simples("a", "", "b")))
        self.assertEqual(doc_google.ler_documento(DOC_ID, cliente=c)["paragrafos"], ["a", "", "b"])


class TestAncorar(unittest.TestCase):

    PARAGRAFOS = [
        "[insert: painel | hook: A | B | C] Você perde três horas.",
        "[apresentador] E eu sei porque eu fazia igual.",
        "[insert: planilha | split] É que cada tarefa repetida.",
        "[insert: painel] Olha o painel de novo.",
    ]

    def base(self, ancora, i=1):
        return {"id": f"c{i}", "ancora": ancora, "assets": [], "links": [], "respostas": [], "resolvido": False,
                "pipoca": False, "sequencia": [], "texto": "", "autor": "", "criado_em": ""}

    def test_acha_o_paragrafo_pelo_texto_da_ancora_sem_ligar_para_acento_nem_caixa(self):
        [c] = doc_google.ancorar(self.PARAGRAFOS, [self.base("INSERT: Planilha")])
        self.assertEqual(c["paragrafo"], 2)
        self.assertFalse(c["ambigua"])
        self.assertEqual(c["candidatos"], [2])

    def test_ancora_que_aparece_em_dois_lugares_e_ambigua_e_a_ordem_dos_comentarios_decide(self):
        a = self.base("insert: painel", 1)
        b = self.base("insert: painel", 2)
        ra, rb = doc_google.ancorar(self.PARAGRAFOS, [a, b])
        self.assertEqual((ra["paragrafo"], rb["paragrafo"]), (0, 3))
        self.assertTrue(ra["ambigua"] and rb["ambigua"])
        self.assertEqual(ra["candidatos"], [0, 3])

    def test_terceiro_comentario_da_mesma_ancora_cai_no_ultimo_candidato(self):
        cs = [self.base("insert: painel", i) for i in (1, 2, 3)]
        self.assertEqual([c["paragrafo"] for c in doc_google.ancorar(self.PARAGRAFOS, cs)], [0, 3, 3])

    def test_comentario_sem_ancora_ou_com_ancora_que_nao_existe(self):
        a, b = doc_google.ancorar(self.PARAGRAFOS, [self.base("", 1), self.base("texto que nao existe", 2)])
        self.assertIsNone(a["paragrafo"])
        self.assertIsNone(b["paragrafo"])
        self.assertEqual(a["candidatos"], [])
        self.assertFalse(a["ambigua"])

    def test_ancora_de_varias_linhas_usa_a_primeira(self):
        [c] = doc_google.ancorar(self.PARAGRAFOS, [self.base("[apresentador]\nE eu sei")])
        self.assertEqual(c["paragrafo"], 1)

    def test_nao_muda_os_comentarios_recebidos(self):
        original = self.base("insert: planilha")
        doc_google.ancorar(self.PARAGRAFOS, [original])
        self.assertNotIn("paragrafo", original)


class TestImportar(unittest.TestCase):

    def doc_do_aluno(self):
        return documento_simples(
            "# Anúncio de teste",
            "[08/10/2026, 10:32] Ana: [insert: painel | hook: VOCÊ PERDE | 3 horas | NISSO AQUI] Você perde “muito” tempo.",
            "",
            "",
            "[cta | KEY: SAIBA MAIS] Toque em saiba mais.",
        )

    def test_importa_roteiro_normalizado_comentarios_ancorados_e_origem(self):
        coms = {"comments": [comentario(1, "insert: painel", f"Usa {G1} e {G2}")]}
        c, _, _ = cliente(("/documents/", 200, self.doc_do_aluno()), ("/comments", 200, coms))
        res = doc_google.importar(DOC_ID, cliente=c)
        self.assertEqual(res["origem"], {"tipo": "doc_google", "doc_id": DOC_ID})
        self.assertEqual(res["titulo"], "Roteiro de teste")
        lei = roteiro_md.ler(res["roteiro_md"])
        self.assertTrue(lei.ok, lei.erros)
        self.assertEqual(lei.blocos[0]["fala"], 'Você perde "muito" tempo.')
        self.assertEqual(res["comentarios"][0]["paragrafo"], 1)
        self.assertEqual(len(res["comentarios"][0]["assets"]), 2)

    def test_origem_importada_passa_no_contrato_do_projeto(self):
        c, _, _ = cliente(("/documents/", 200, self.doc_do_aluno()), ("/comments", 200, {"comments": []}))
        res = doc_google.importar(DOC_ID, cliente=c)
        projeto = {"versao": 1, "slug": "x", "modo": "gravado",
                   "trilha": {"desligada": True, "motivo": "teste sem trilha"}, "origem": res["origem"]}
        self.assertEqual(roteiro_md.contrato().validar("projeto", projeto), [])

    def test_aceita_a_url_do_documento(self):
        c, http, _ = cliente(("/documents/", 200, self.doc_do_aluno()), ("/comments", 200, {"comments": []}))
        doc_google.importar(f"https://docs.google.com/document/d/{DOC_ID}/edit", cliente=c)
        self.assertIn(DOC_ID, http.chamadas[0][0])

    def test_documento_com_varias_abas_pede_qual(self):
        doc = {"title": "x", "tabs": [
            {"tabProperties": {"title": "AD 1"}, "documentTab": {"body": {"content": [paragrafo("[cta | KEY: A] Um.")]}}},
            {"tabProperties": {"title": "AD 2"}, "documentTab": {"body": {"content": [paragrafo("[cta | KEY: B] Dois.")]}}}]}
        c, _, _ = cliente(("/documents/", 200, doc), ("/comments", 200, {"comments": []}))
        with self.assertRaises(doc_google.ErroGoogle) as ctx:
            doc_google.importar(DOC_ID, cliente=c)
        self.assertIn("AD 1", str(ctx.exception))
        self.assertIn("AD 2", str(ctx.exception))
        c, _, _ = cliente(("/documents/", 200, doc), ("/comments", 200, {"comments": []}))
        res = doc_google.importar(DOC_ID, aba="ad 2", cliente=c)
        self.assertEqual(res["aba"], "AD 2")
        self.assertEqual(res["roteiro_md"], "[cta | KEY: B] Dois.\n")

    def test_aba_que_nao_existe_lista_as_que_existem(self):
        c, _, _ = cliente(("/documents/", 200, self.doc_do_aluno()), ("/comments", 200, {"comments": []}))
        with self.assertRaises(doc_google.ErroGoogle) as ctx:
            doc_google.importar(DOC_ID, aba="Inexistente", cliente=c)
        self.assertIn("Aba 1", str(ctx.exception))

    def test_avisos_de_comentario_sem_ancora_ancora_ambigua_e_pipoca_curta(self):
        sem = comentario(1, "", "geral")
        pipoca_curta = comentario(2, "insert: painel", f"pipoca {G1}")
        coms = {"comments": [sem, pipoca_curta]}
        doc = documento_simples("[insert: painel | hook: A | B | C] Um.", "[insert: painel] Dois.",
                                "[cta | KEY: SAIBA MAIS] Toque.")
        c, _, _ = cliente(("/documents/", 200, doc), ("/comments", 200, coms))
        res = doc_google.importar(DOC_ID, cliente=c)
        texto = " ".join(res["avisos"])
        self.assertIn("sem âncora", texto)
        self.assertIn("ambígua", texto)
        self.assertIn("pipoca", texto)


class TestSeguranca(unittest.TestCase):

    def test_so_fala_com_docs_e_drive_do_google(self):
        import re
        src = (ENTRADA / "doc_google.py").read_text(encoding="utf-8")
        hosts = set(re.findall(r"https?://([A-Za-z0-9.\-]+)", src))
        self.assertLessEqual(hosts, {"docs.googleapis.com", "www.googleapis.com", "docs.google.com",
                                     "drive.google.com"})
        self.assertNotIn("sheets", src.lower())
        self.assertNotIn("spreadsheets", src.lower())

    def test_so_leitura_nenhum_metodo_que_escreve_no_google(self):
        src = (ENTRADA / "doc_google.py").read_text(encoding="utf-8")
        for verbo in ('"POST"', '"PUT"', '"PATCH"', '"DELETE"', "method="):
            self.assertNotIn(verbo, src)


if __name__ == "__main__":
    unittest.main()
