"""Testes de entrada/roteiro_md (W1.B): o leitor do roteiro.md sobre o validador do contrato.

O parser da gramática é UM só, `ler_roteiro` em scripts/contratos/validar.py. Este módulo
lê arquivo, normaliza e devolve uma leitura com as perguntas que o resto do produto faz
(tem erro? precisa de plano? qual é a sequência de palavras?).
"""
import ast
import json
import socket
import tempfile
import unittest
from pathlib import Path

from entrada import roteiro_md

RAIZ = Path(__file__).resolve().parents[2]
EXEMPLOS = RAIZ / "contratos" / "exemplos"
ENTRADA = RAIZ / "scripts" / "entrada"
NOMES = ("completo", "so-fala", "texto-colado", "lista", "layouts", "cta-logo")
MODULOS = ("roteiro_md", "texto_colado", "roteiro_livre", "para_motor", "doc_google")


def exemplo(nome):
    return (EXEMPLOS / f"roteiro.valido.{nome}.md").read_text(encoding="utf-8")


def blocos_esperados(nome):
    return json.loads((EXEMPLOS / f"roteiro.valido.{nome}.blocos.json").read_text(encoding="utf-8"))


def falas_do_arquivo(texto):
    """Extração independente (sem usar o parser) da fala de cada bloco."""
    linhas = [l.strip() for l in texto.split("\n")]
    if any(l.startswith("[") for l in linhas):
        falas = []
        for l in linhas:
            if not l or l.startswith("#"):
                continue
            if l.startswith("["):
                falas.append(l[l.index("]") + 1:].strip())
            else:
                falas[-1] += " " + l
        return [f.replace("*", "") for f in falas]
    falas, atual = [], None
    for l in linhas:
        if l.startswith("#"):
            continue
        if not l:
            atual = None
        elif atual is None:
            falas.append(l)
            atual = len(falas) - 1
        else:
            falas[atual] += " " + l
    return falas


class TestSeisExemplos(unittest.TestCase):

    def test_cada_exemplo_vira_exatamente_os_blocos_esperados(self):
        for nome in NOMES:
            with self.subTest(exemplo=nome):
                lei = roteiro_md.ler(exemplo(nome))
                self.assertEqual([str(e) for e in lei.erros], [])
                self.assertTrue(lei.ok)
                self.assertEqual(lei.como_dict(), blocos_esperados(nome))

    def test_fala_preservada_byte_a_byte(self):
        for nome in NOMES:
            lei = roteiro_md.ler(exemplo(nome))
            falas = falas_do_arquivo(exemplo(nome))
            self.assertEqual(len(falas), len(lei.blocos))
            for b, esperada in zip(lei.blocos, falas):
                with self.subTest(exemplo=nome, fala=b["fala"][:24]):
                    if b["tipo"] == "lista" and any(i["marcador"] for i in b["itens"]):
                        # na lista com marcadores os marcadores saem da fala, e só eles:
                        # as palavras ficam iguais e nenhum marcador sobra
                        palavras = roteiro_md.contrato().palavras
                        self.assertEqual(palavras(b["fala"]), palavras(esperada))
                        for marcador in roteiro_md.contrato().MARCADORES:
                            self.assertNotIn(marcador, b["fala"])
                    else:
                        self.assertEqual(b["fala"], esperada)

    def test_bytes_estranhos_da_fala_ficam_como_estao(self):
        # espaço duplo, NBSP, aspas curvas e acento decomposto: o leitor não normaliza nada
        fala = "Café  com leite “curvo” e\ttab."
        lei = roteiro_md.ler(f"[apresentador] {fala}\n[cta | KEY: SAIBA MAIS] Toque.\n")
        self.assertTrue(lei.ok, lei.erros)
        self.assertEqual(lei.blocos[0]["fala"], fala)

    def test_ler_nao_normaliza_por_padrao_e_ler_normalizando_sim(self):
        sujo = "[08/10/2026, 10:32] Ana: [apresentador] Oi.\n[cta | KEY: SAIBA MAIS] Toque.\n"
        self.assertFalse(roteiro_md.ler(sujo).ok)
        lei = roteiro_md.ler(sujo, normalizar=True)
        self.assertTrue(lei.ok, lei.erros)
        self.assertEqual(lei.texto, "[apresentador] Oi.\n[cta | KEY: SAIBA MAIS] Toque.\n")


class TestPerguntasDaLeitura(unittest.TestCase):

    def test_precisa_plano_so_no_roteiro_livre(self):
        self.assertTrue(roteiro_md.ler(exemplo("so-fala")).precisa_plano)
        for nome in ("completo", "texto-colado", "lista", "layouts", "cta-logo"):
            with self.subTest(exemplo=nome):
                self.assertFalse(roteiro_md.ler(exemplo(nome)).precisa_plano)

    def test_sequencia_de_palavras_e_a_da_fala_de_todos_os_blocos(self):
        palavras = roteiro_md.contrato().palavras
        for nome in NOMES:
            with self.subTest(exemplo=nome):
                lei = roteiro_md.ler(exemplo(nome))
                esperado = palavras(" ".join(b["fala"] for b in lei.blocos))
                self.assertEqual(lei.sequencia_de_palavras(), esperado)
                self.assertGreater(lei.n_palavras, 0)
                self.assertEqual(lei.n_palavras, len(esperado))

    def test_fala_completa_junta_com_espaco(self):
        lei = roteiro_md.ler(exemplo("layouts"))
        self.assertEqual(lei.fala_completa(), " ".join(b["fala"] for b in lei.blocos))

    def test_roteiro_vazio_nao_quebra_e_acusa_a_fala(self):
        lei = roteiro_md.ler("# so um titulo\n")
        self.assertFalse(lei.ok)
        self.assertEqual(lei.blocos, [])
        self.assertEqual(lei.n_palavras, 0)
        self.assertIn("fala", [e.campo for e in lei.erros])

    def test_exemplos_invalidos_do_contrato_reprovam_no_campo_do_nome(self):
        invalidos = sorted(EXEMPLOS.glob("roteiro.invalido.*.md"))
        self.assertGreaterEqual(len(invalidos), 12)
        for arq in invalidos:
            with self.subTest(arquivo=arq.name):
                campo = arq.name.split(".")[2].split("-")[0]
                lei = roteiro_md.ler(arq.read_text(encoding="utf-8"))
                self.assertFalse(lei.ok)
                self.assertIn(campo, [e.campo for e in lei.erros])

    def test_exigir_levanta_com_uma_linha_por_problema(self):
        lei = roteiro_md.ler("[apresentador] Oi.\n")
        with self.assertRaises(roteiro_md.RoteiroInvalido) as ctx:
            roteiro_md.exigir(lei)
        msg = str(ctx.exception)
        self.assertIn("linha 1 (cta)", msg)
        self.assertIs(ctx.exception.leitura, lei)

    def test_exigir_devolve_a_propria_leitura_quando_ok(self):
        lei = roteiro_md.ler(exemplo("completo"))
        self.assertIs(roteiro_md.exigir(lei), lei)

    def test_formatar_erros_cita_linha_e_campo(self):
        lei = roteiro_md.ler("[insert: X Y] Oi.\n[cta | KEY: A] Toque.\n")
        texto = roteiro_md.formatar_erros(lei.erros)
        self.assertIn("linha 1 (insert)", texto)


class TestUmParserSo(unittest.TestCase):

    def test_ler_delega_para_o_ler_roteiro_do_validador(self):
        mod = roteiro_md.contrato()
        original = mod.ler_roteiro
        chamadas = []

        def espiao(texto):
            chamadas.append(texto)
            return original(texto)

        mod.ler_roteiro = espiao
        try:
            roteiro_md.ler("[cta | KEY: SAIBA MAIS] Toque.\n")
        finally:
            mod.ler_roteiro = original
        self.assertEqual(chamadas, ["[cta | KEY: SAIBA MAIS] Toque.\n"])

    def test_contrato_e_o_arquivo_validar_do_repo(self):
        self.assertEqual(Path(roteiro_md.contrato().__file__).resolve(),
                         (RAIZ / "scripts" / "contratos" / "validar.py").resolve())

    def test_nenhum_modulo_da_entrada_define_outro_parser_de_direcao(self):
        # a gramática (colchete, KEY, LEAD, âncora) só é interpretada em validar.py
        for nome in MODULOS:
            src = (ENTRADA / f"{nome}.py").read_text(encoding="utf-8")
            with self.subTest(modulo=nome):
                self.assertNotIn('partition("|")', src)
                self.assertNotIn('split("|")', src)


class TestArquivo(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_le_md_e_txt(self):
        for ext in (".md", ".txt"):
            arq = self.pasta / f"roteiro{ext}"
            arq.write_text(exemplo("completo"), encoding="utf-8")
            with self.subTest(ext=ext):
                lei = roteiro_md.ler_arquivo(arq)
                self.assertTrue(lei.ok, lei.erros)
                self.assertEqual(lei.como_dict(), blocos_esperados("completo"))

    def test_outra_extensao_e_recusada_com_mensagem_clara(self):
        arq = self.pasta / "roteiro.docx"
        arq.write_bytes(b"PK")
        with self.assertRaises(ValueError) as ctx:
            roteiro_md.ler_arquivo(arq)
        self.assertIn(".md", str(ctx.exception))
        self.assertIn(".txt", str(ctx.exception))

    def test_arquivo_que_nao_existe(self):
        with self.assertRaises(FileNotFoundError):
            roteiro_md.ler_arquivo(self.pasta / "nao-existe.md")

    def test_arquivo_fora_de_utf8_e_recusado_sem_adivinhar(self):
        arq = self.pasta / "roteiro.txt"
        arq.write_bytes("[cta | KEY: A] Você.\n".encode("latin-1"))
        with self.assertRaises(ValueError) as ctx:
            roteiro_md.ler_arquivo(arq)
        self.assertIn("UTF-8", str(ctx.exception))

    def test_bom_do_notepad_e_aceito(self):
        arq = self.pasta / "roteiro.txt"
        arq.write_bytes(b"\xef\xbb\xbf" + exemplo("layouts").encode("utf-8"))
        lei = roteiro_md.ler_arquivo(arq)
        self.assertTrue(lei.ok, lei.erros)

    def test_arquivo_colado_do_whatsapp_e_normalizado_por_padrao(self):
        arq = self.pasta / "colado.txt"
        arq.write_text("[08/10/2026, 10:32] Ana: [apresentador]  Eu chamo isso de “trabalho”.\r\n"
                       "\r\n\r\n\r\n[08/10/2026, 10:33] Ana: [cta | KEY: SAIBA MAIS] Toque.\r\n", encoding="utf-8")
        lei = roteiro_md.ler_arquivo(arq)
        self.assertTrue(lei.ok, lei.erros)
        self.assertEqual(lei.blocos[0]["fala"], 'Eu chamo isso de "trabalho".')
        bruto = roteiro_md.ler_arquivo(arq, normalizar=False)
        self.assertFalse(bruto.ok)


class TestSalvar(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_grava_o_texto_normalizado_e_devolve_a_leitura(self):
        destino = self.pasta / "projetos" / "x" / "roteiro.md"
        lei = roteiro_md.salvar("[08/10/2026, 10:32] Ana: [apresentador] Oi.\n\n\n"
                                "[cta | KEY: SAIBA MAIS] Toque.", destino)
        self.assertTrue(lei.ok)
        self.assertEqual(destino.read_text(encoding="utf-8"),
                         "[apresentador] Oi.\n\n[cta | KEY: SAIBA MAIS] Toque.\n")

    def test_nao_grava_roteiro_invalido(self):
        destino = self.pasta / "roteiro.md"
        with self.assertRaises(roteiro_md.RoteiroInvalido):
            roteiro_md.salvar("[apresentador] sem cta no fim\n", destino)
        self.assertFalse(destino.exists())

    def test_nao_sobrescreve_sem_pedir(self):
        destino = self.pasta / "roteiro.md"
        destino.write_text("antigo\n", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            roteiro_md.salvar(exemplo("completo"), destino)
        self.assertEqual(destino.read_text(encoding="utf-8"), "antigo\n")
        roteiro_md.salvar(exemplo("completo"), destino, sobrescrever=True)
        self.assertEqual(destino.read_text(encoding="utf-8"), exemplo("completo"))

    def test_escrita_por_temporario_nao_deixa_resto(self):
        destino = self.pasta / "roteiro.md"
        roteiro_md.salvar(exemplo("lista"), destino)
        self.assertEqual(sorted(p.name for p in self.pasta.iterdir()), ["roteiro.md"])


class TestSemRedeSemPlanilha(unittest.TestCase):

    def test_com_a_rede_bloqueada_o_parser_funciona(self):
        original = socket.socket

        def bloqueado(*a, **k):
            raise AssertionError("o parser tentou abrir socket")

        socket.socket = bloqueado
        try:
            for nome in NOMES:
                lei = roteiro_md.ler(exemplo(nome), normalizar=True)
                self.assertTrue(lei.ok, lei.erros)
        finally:
            socket.socket = original

    def test_modulos_puros_nao_importam_biblioteca_de_rede(self):
        proibidos = {"urllib", "http", "socket", "requests", "ssl", "ftplib", "smtplib"}
        for nome in ("roteiro_md", "texto_colado", "roteiro_livre", "para_motor"):
            arvore = ast.parse((ENTRADA / f"{nome}.py").read_text(encoding="utf-8"))
            achados = set()
            for no in ast.walk(arvore):
                if isinstance(no, ast.Import):
                    achados |= {a.name.split(".")[0] for a in no.names}
                elif isinstance(no, ast.ImportFrom) and no.level == 0:
                    achados.add((no.module or "").split(".")[0])
            with self.subTest(modulo=nome):
                self.assertEqual(achados & proibidos, set())

    def test_nenhum_modulo_da_entrada_fala_com_planilha(self):
        for nome in MODULOS:
            src = (ENTRADA / f"{nome}.py").read_text(encoding="utf-8").lower()
            with self.subTest(modulo=nome):
                self.assertNotIn("sheets.googleapis", src)
                self.assertNotIn("spreadsheets", src)

    def test_todos_os_modulos_da_entrada_existem_e_sao_python_39(self):
        for nome in MODULOS:
            arq = ENTRADA / f"{nome}.py"
            with self.subTest(modulo=nome):
                self.assertTrue(arq.is_file())
                ast.parse(arq.read_text(encoding="utf-8"), feature_version=(3, 9))


if __name__ == "__main__":
    unittest.main()
