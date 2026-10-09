"""Testes dos contratos (W0.2): schemas, exemplos, gramática do roteiro, CLI e pacotes.

O validador é carregado pelo CAMINHO do arquivo, não por `import contratos`: os testes
têm pacotes com o mesmo nome dos de `scripts/` (tests/contratos x scripts/contratos), e
dependendo do modo de import do executor o nome curto apontaria para o pacote errado.
O import pelo nome curto é testado à parte, num subprocesso isolado.
"""
import ast
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SCRIPTS = RAIZ / "scripts"
CONTRATOS = RAIZ / "contratos"
EXEMPLOS = CONTRATOS / "exemplos"
VALIDAR = SCRIPTS / "contratos" / "validar.py"
CONVENCAO = CONTRATOS / "roteiro-convencao.md"

NOMES = ("projeto", "looks", "glossario", "plano", "timeline", "laudo", "aprovacao", "nota")
EXEMPLOS_ROTEIRO = ("completo", "so-fala", "texto-colado", "lista", "layouts", "cta-logo")

PACOTES_SCRIPTS = (
    "contratos", "projeto", "entrada", "audio", "audio/backends", "avatar", "timeline",
    "overlay", "footage", "cinema", "plano", "entrega", "oneshot", "onboarding",
    "onboarding/checks", "cli", "dev", "gravado/nucleo",
)
PACOTES_TESTS = (
    "contratos", "projeto", "entrada", "audio", "avatar", "timeline", "overlay", "footage",
    "cinema", "plano", "gates", "cli", "gravado", "oneshot", "onboarding", "dev", "paridade",
)
STDLIB_PERMITIDA = {"__future__", "json", "os", "pathlib", "re", "sys", "unicodedata", "typing"}

_CACHE = {}


def V():
    """O módulo validar.py, carregado pelo caminho (uma vez)."""
    if "m" not in _CACHE:
        spec = importlib.util.spec_from_file_location("vam_contratos_validar_teste", VALIDAR)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _CACHE["m"] = mod
    return _CACHE["m"]


def rodar_cli(*args, env=None, cwd=None):
    return subprocess.run([sys.executable, str(VALIDAR), *map(str, args)],
                          capture_output=True, text=True, env=env, cwd=cwd)


def exemplos():
    return sorted(p for p in EXEMPLOS.iterdir() if p.is_file())


def campo_esperado(caminho):
    """`<contrato>.invalido.<campo>[-detalhe].<ext>` -> `<campo>`."""
    partes = caminho.name.split(".")
    return partes[partes.index("invalido") + 1].split("-")[0]


def contrato_de(caminho):
    return caminho.name.split(".")[0]


class TestSchemas(unittest.TestCase):

    def test_os_oito_schemas_existem_e_usam_so_o_que_o_validador_suporta(self):
        for nome in NOMES:
            with self.subTest(schema=nome):
                p = CONTRATOS / f"{nome}.schema.json"
                self.assertTrue(p.exists(), f"falta {p}")
                s = json.loads(p.read_text(encoding="utf-8"))
                self.assertEqual(s.get("$schema"), "https://json-schema.org/draft/2020-12/schema")
                self.assertTrue(s.get("title"))
                self.assertEqual(s.get("type"), "object")
                self.assertIs(s.get("additionalProperties"), False,
                              "campo desconhecido tem que reprovar na raiz de todo contrato")
                self.assertIn("versao", s.get("required", []))
                V().conferir_schema(s, nome)  # levanta SchemaInvalido se houver problema

    def test_palavra_chave_nao_suportada_e_recusada(self):
        with self.assertRaises(V().SchemaInvalido) as ctx:
            V().conferir_schema({"type": "string", "format": "email"}, "t")
        self.assertIn("format", str(ctx.exception))

    def test_ref_quebrado_e_recusado(self):
        with self.assertRaises(V().SchemaInvalido) as ctx:
            V().conferir_schema({"$ref": "#/$defs/nao_existe"}, "t")
        self.assertIn("nao_existe", str(ctx.exception))

    def test_regex_invalida_e_recusada(self):
        with self.assertRaises(V().SchemaInvalido):
            V().conferir_schema({"type": "string", "pattern": "([a-z"}, "t")

    def test_tipo_inexistente_e_recusado(self):
        with self.assertRaises(V().SchemaInvalido):
            V().conferir_schema({"type": "float"}, "t")


class TestNucleoDoValidador(unittest.TestCase):
    """O subconjunto de JSON Schema que o validador implementa, com o campo no erro."""

    def erros(self, schema, inst):
        return V().Validador(schema, "t").erros(inst)

    def campos(self, schema, inst):
        return [e.campo for e in self.erros(schema, inst)]

    def test_booleano_nao_e_inteiro_nem_numero(self):
        s = {"type": "object", "properties": {"n": {"type": "integer"}, "x": {"type": "number"}}}
        self.assertEqual(self.campos(s, {"n": True, "x": False}), ["n", "x"])
        self.assertEqual(self.erros(s, {"n": 3, "x": 1.5}), [])

    def test_float_inteiro_conta_como_integer(self):
        self.assertEqual(self.erros({"type": "integer"}, 2.0), [])
        self.assertTrue(self.erros({"type": "integer"}, 2.5))

    def test_obrigatorio_ausente_nomeia_o_campo_ausente(self):
        s = {"type": "object", "required": ["modo"], "properties": {"modo": {"type": "string"}}}
        e = self.erros(s, {})
        self.assertEqual([x.campo for x in e], ["modo"])
        self.assertEqual(e[0].caminho, "$.modo")
        self.assertIn("obrigatório", e[0].mensagem)

    def test_campo_desconhecido_nomeia_o_campo(self):
        s = {"type": "object", "additionalProperties": False, "properties": {"a": {}}}
        e = self.erros(s, {"a": 1, "planilha": "x"})
        self.assertEqual([x.campo for x in e], ["planilha"])
        self.assertIn("desconhecido", e[0].mensagem)

    def test_caminho_de_item_de_lista(self):
        s = {"type": "object", "properties": {"gates": {"type": "array", "items": {
            "type": "object", "required": ["nome"], "properties": {"nome": {"type": "string"}}}}}}
        e = self.erros(s, {"gates": [{"nome": "a"}, {}]})
        self.assertEqual(e[0].caminho, "$.gates[1].nome")
        self.assertEqual(e[0].campo, "nome")

    def test_oneof_mostra_a_alternativa_mais_proxima(self):
        s = {"type": "object", "properties": {"trilha": {"oneOf": [
            {"type": "object", "required": ["arquivo"], "additionalProperties": False,
             "properties": {"arquivo": {"type": "string"}}},
            {"type": "object", "required": ["desligada", "motivo"], "additionalProperties": False,
             "properties": {"desligada": {"const": True}, "motivo": {"type": "string"}}},
        ]}}}
        self.assertIn("motivo", self.campos(s, {"trilha": {"desligada": True}}))
        self.assertEqual(self.erros(s, {"trilha": {"arquivo": "x.mp3"}}), [])

    def test_oneof_que_casa_com_duas_reprova(self):
        s = {"oneOf": [{"type": "number"}, {"type": "integer"}]}
        self.assertTrue(self.erros(s, 3))
        self.assertEqual(self.erros(s, 3.5), [])

    def test_if_then(self):
        s = {"type": "object", "if": {"properties": {"modo": {"const": "avatar"}}, "required": ["modo"]},
             "then": {"required": ["look"]}}
        self.assertEqual(self.campos(s, {"modo": "avatar"}), ["look"])
        self.assertEqual(self.erros(s, {"modo": "gravado"}), [])

    def test_const_e_enum_nao_confundem_true_com_1(self):
        self.assertTrue(self.erros({"const": True}, 1))
        self.assertTrue(self.erros({"enum": [1, 2]}, True))
        self.assertEqual(self.erros({"enum": [1, 2]}, 1.0), [])

    def test_unique_items(self):
        self.assertTrue(self.erros({"type": "array", "uniqueItems": True}, ["a", "a"]))
        self.assertEqual(self.erros({"type": "array", "uniqueItems": True}, [1, True]), [])

    def test_limites_numericos_e_de_texto(self):
        s = {"type": "object", "properties": {
            "a": {"type": "number", "minimum": 1, "maximum": 2},
            "b": {"type": "number", "exclusiveMinimum": 0},
            "c": {"type": "string", "minLength": 2, "pattern": "^[a-z]+$"}}}
        self.assertEqual(self.campos(s, {"a": 0.5, "b": 0, "c": "A"}), ["a", "b", "c", "c"])

    def test_property_names(self):
        s = {"type": "object", "propertyNames": {"pattern": "^[a-z]+$"}}
        self.assertEqual(self.campos(s, {"ok": 1, "Ruim": 2}), ["Ruim"])

    def test_json_com_chave_duplicada_e_recusado(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "nota.json"
            p.write_text('{"versao": 1, "versao": 1}', encoding="utf-8")
            e = V().validar_arquivo(p)
            self.assertTrue(e)
            self.assertIn("duplicada", e[0].mensagem)

    def test_json_com_nan_e_recusado(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "nota.json"
            p.write_text('{"versao": 1, "nota": NaN}', encoding="utf-8")
            self.assertTrue(V().validar_arquivo(p))


class TestExemplos(unittest.TestCase):

    def test_todo_arquivo_de_exemplo_tem_nome_reconhecido(self):
        for p in exemplos():
            with self.subTest(arquivo=p.name):
                self.assertIsNotNone(V().contrato_do_arquivo(p), "nome fora da convenção")

    def test_cada_contrato_tem_exemplo_valido_e_invalido(self):
        nomes = {p.name for p in exemplos()}
        for nome in NOMES:
            with self.subTest(contrato=nome):
                self.assertTrue(any(n.startswith(f"{nome}.valido.") and n.endswith(".json") for n in nomes))
                self.assertTrue(any(n.startswith(f"{nome}.invalido.") and n.endswith(".json") for n in nomes))
        self.assertTrue(any(n.startswith("roteiro.invalido.") and n.endswith(".md") for n in nomes))

    def test_todo_exemplo_valido_passa(self):
        validos = [p for p in exemplos() if ".valido." in p.name]
        self.assertGreaterEqual(len(validos), 8 + 6)
        for p in validos:
            with self.subTest(arquivo=p.name):
                self.assertEqual([str(e) for e in V().validar_arquivo(p)], [])

    def test_todo_exemplo_invalido_falha_nomeando_o_campo(self):
        invalidos = [p for p in exemplos() if ".invalido." in p.name]
        self.assertGreaterEqual(len(invalidos), 8)
        for p in invalidos:
            with self.subTest(arquivo=p.name):
                erros = V().validar_arquivo(p)
                self.assertTrue(erros, "exemplo inválido passou")
                esperado = campo_esperado(p)
                self.assertIn(esperado, [e.campo for e in erros],
                              f"nenhum erro nomeia '{esperado}': {[str(e) for e in erros]}")


class TestRoteiro(unittest.TestCase):

    def ler(self, texto):
        return V().ler_roteiro(texto)

    def test_os_seis_exemplos_existem(self):
        for nome in EXEMPLOS_ROTEIRO:
            with self.subTest(exemplo=nome):
                self.assertTrue((EXEMPLOS / f"roteiro.valido.{nome}.md").exists())
                self.assertTrue((EXEMPLOS / f"roteiro.valido.{nome}.blocos.json").exists())

    def test_cada_exemplo_vira_exatamente_os_blocos_esperados(self):
        for nome in EXEMPLOS_ROTEIRO:
            with self.subTest(exemplo=nome):
                md = (EXEMPLOS / f"roteiro.valido.{nome}.md").read_text(encoding="utf-8")
                esperado = json.loads((EXEMPLOS / f"roteiro.valido.{nome}.blocos.json").read_text(encoding="utf-8"))
                lido, erros = self.ler(md)
                self.assertEqual([str(e) for e in erros], [])
                self.assertEqual(lido, esperado)

    def test_exemplos_no_documento_sao_identicos_aos_arquivos(self):
        doc = CONVENCAO.read_text(encoding="utf-8")
        for nome in EXEMPLOS_ROTEIRO:
            with self.subTest(exemplo=nome):
                bloco = V().bloco_do_documento(doc, f"exemplo:{nome}")
                arquivo = (EXEMPLOS / f"roteiro.valido.{nome}.md").read_text(encoding="utf-8")
                self.assertEqual(bloco, arquivo)

    def test_documento_traz_a_entrada_suja_do_texto_colado(self):
        doc = CONVENCAO.read_text(encoding="utf-8")
        bruto = V().bloco_do_documento(doc, "exemplo:texto-colado:entrada")
        self.assertIn(chr(0x201C), bruto)        # aspas curvas
        self.assertRegex(bruto, r"\[\d{2}/\d{2}/\d{4}, \d{2}:\d{2}\] ")  # rótulo do WhatsApp
        self.assertIn("\n\n\n", bruto)        # linhas vazias sobrando

    def test_fala_nunca_carrega_direcao_nem_asterisco(self):
        for nome in EXEMPLOS_ROTEIRO:
            lido, _ = self.ler((EXEMPLOS / f"roteiro.valido.{nome}.md").read_text(encoding="utf-8"))
            for b in lido["blocos"]:
                with self.subTest(exemplo=nome, fala=b["fala"][:30]):
                    for c in "[]*":
                        self.assertNotIn(c, b["fala"])

    def test_fala_preserva_os_bytes_da_linha(self):
        md = (EXEMPLOS / "roteiro.valido.completo.md").read_text(encoding="utf-8")
        linhas = [l for l in md.splitlines() if l.startswith("[")]
        lido, _ = self.ler(md)
        for linha, b in zip(linhas, lido["blocos"]):
            if b["tipo"] == "lista":
                continue
            self.assertEqual(b["fala"], linha.split("]", 1)[1].strip().replace("*", ""))

    def test_sem_colchete_e_roteiro_livre_por_paragrafo(self):
        lido, erros = self.ler("Primeira frase\ncontinua aqui.\n\nSegundo parágrafo.\n")
        self.assertEqual(erros, [])
        self.assertTrue(lido["livre"])
        self.assertEqual([b["fala"] for b in lido["blocos"]],
                         ["Primeira frase continua aqui.", "Segundo parágrafo."])
        self.assertEqual({b["tipo"] for b in lido["blocos"]}, {"livre"})

    def test_titulo_com_cerquilha_e_ignorado_e_linha_sem_colchete_continua_o_bloco(self):
        lido, erros = self.ler("# Título\n[apresentador] Começa aqui\ne termina aqui.\n"
                               "[cta | KEY: SAIBA MAIS] Toque em saiba mais.\n")
        self.assertEqual(erros, [])
        self.assertFalse(lido["livre"])
        self.assertEqual(lido["blocos"][0]["fala"], "Começa aqui e termina aqui.")

    def test_texto_antes_do_primeiro_bloco_reprova(self):
        _, erros = self.ler("Oi, segue o roteiro:\n[cta | KEY: SAIBA MAIS] Toque em saiba mais.\n")
        self.assertIn("direcao", [e.campo for e in erros])

    def test_hook_tem_que_ser_o_ultimo_item_e_so_no_primeiro_bloco(self):
        _, e1 = self.ler("[insert: a | hook: A | B | C | split] Fala.\n[cta | KEY: X] Toque.\n")
        self.assertIn("hook", [e.campo for e in e1])
        _, e2 = self.ler("[apresentador] Oi.\n[insert: a | hook: A | B | C] Fala.\n[cta | KEY: X] Toque.\n")
        self.assertIn("hook", [e.campo for e in e2])

    def test_lista_por_virgula_separa_o_ultimo_e(self):
        lido, erros = self.ler("[lista] Enquanto isso: a proposta atrasa, o cliente esfria e você perde a venda.\n"
                               "[cta | KEY: SAIBA MAIS] Toque em saiba mais.\n")
        self.assertEqual(erros, [])
        self.assertEqual([i["texto"] for i in lido["blocos"][0]["itens"]],
                         ["a proposta atrasa", "o cliente esfria", "você perde a venda"])

    def test_lista_com_um_item_so_reprova(self):
        _, erros = self.ler("[lista] Enquanto isso: tudo atrasa e trava.\n[cta | KEY: X] Toque.\n")
        self.assertIn("lista", [e.campo for e in erros])

    def test_ancora_com_numero_maior_que_as_ocorrencias_reprova(self):
        _, erros = self.ler("[apresentador | KEY: DIA | âncora: dia#3] Um dia, outro dia.\n[cta | KEY: X] Toque.\n")
        self.assertIn("ancora", [e.campo for e in erros])

    def test_tipo_avatar_sugere_apresentador(self):
        _, erros = self.ler("[avatar] Oi.\n[cta | KEY: X] Toque.\n")
        self.assertIn("direcao", [e.campo for e in erros])
        self.assertIn("apresentador", " ".join(e.mensagem for e in erros))

    def test_roteiro_dirigido_sem_cta_reprova(self):
        _, erros = self.ler("[apresentador] Oi.\n")
        self.assertIn("cta", [e.campo for e in erros])


class TestCLI(unittest.TestCase):

    def test_pasta_de_exemplos_sai_zero(self):
        r = rodar_cli(EXEMPLOS)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_pasta_de_contratos_inteira_sai_zero(self):
        r = rodar_cli(CONTRATOS)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("projeto.schema.json", r.stdout)

    def test_arquivo_ruim_sai_um_e_nomeia_o_campo(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "projeto.json"
            p.write_text(json.dumps({"versao": 1, "slug": "x", "modo": "gravado"}), encoding="utf-8")
            r = rodar_cli(p)
            self.assertEqual(r.returncode, 1)
            self.assertIn("$.trilha", r.stdout)

    def test_pasta_com_arquivo_ruim_sai_um(self):
        with tempfile.TemporaryDirectory() as d:
            sub = Path(d) / "projetos" / "x"
            sub.mkdir(parents=True)
            (sub / "projeto.json").write_text("{}", encoding="utf-8")
            (sub / "outro.json").write_text("{}", encoding="utf-8")  # ignorado: não é contrato
            r = rodar_cli(d)
            self.assertEqual(r.returncode, 1)
            self.assertIn("$.versao", r.stdout)

    def test_invalido_que_passa_derruba_a_pasta(self):
        with tempfile.TemporaryDirectory() as d:
            valido = next(p for p in exemplos() if p.name.startswith("projeto.valido."))
            shutil.copy(valido, Path(d) / "projeto.invalido.trilha.json")
            r = rodar_cli(d)
            self.assertEqual(r.returncode, 1)
            self.assertIn("trilha", r.stdout)

    def test_invalido_que_falha_no_campo_errado_derruba_a_pasta(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "projeto.invalido.look.json"
            p.write_text(json.dumps({"versao": 1, "slug": "x", "modo": "gravado"}), encoding="utf-8")
            r = rodar_cli(d)
            self.assertEqual(r.returncode, 1)

    def test_caminho_inexistente_sai_dois(self):
        self.assertEqual(rodar_cli(RAIZ / "nao-existe-mesmo").returncode, 2)

    def test_pasta_sem_contrato_sai_dois(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "qualquer.json").write_text("{}", encoding="utf-8")
            self.assertEqual(rodar_cli(d).returncode, 2)

    def test_roda_com_home_falso_sem_escrever_nada(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as cwd:
            env = {"HOME": home, "PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
            r = rodar_cli(EXEMPLOS, env=env, cwd=cwd)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(os.listdir(home), [])
            self.assertEqual(os.listdir(cwd), [])

    @unittest.skipUnless(os.path.exists("/usr/bin/python3"), "sem /usr/bin/python3 nesta máquina")
    def test_roda_no_python_do_sistema(self):
        r = subprocess.run(["/usr/bin/python3", str(VALIDAR), str(EXEMPLOS)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_validador_so_usa_biblioteca_padrao(self):
        arvore = ast.parse(VALIDAR.read_text(encoding="utf-8"))
        modulos = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                modulos |= {a.name.split(".")[0] for a in no.names}
            elif isinstance(no, ast.ImportFrom):
                modulos.add((no.module or "").split(".")[0])
        self.assertLessEqual(modulos, STDLIB_PERMITIDA)


class TestPacotes(unittest.TestCase):

    def test_init_vazios_em_scripts(self):
        for p in PACOTES_SCRIPTS:
            with self.subTest(pacote=p):
                f = SCRIPTS / p / "__init__.py"
                self.assertTrue(f.exists(), f"falta {f}")
                self.assertEqual(f.stat().st_size, 0, f"{f} tem que ser vazio")

    def test_init_vazios_em_tests(self):
        for p in PACOTES_TESTS:
            with self.subTest(pacote=p):
                f = RAIZ / "tests" / p / "__init__.py"
                self.assertTrue(f.exists(), f"falta {f}")
                self.assertEqual(f.stat().st_size, 0, f"{f} tem que ser vazio")

    def test_pacotes_importam_sem_efeito_colateral(self):
        modulos = [p.replace("/", ".") for p in PACOTES_SCRIPTS] + ["contratos.validar"]
        codigo = (
            "import importlib, sys\n"
            f"sys.path.insert(0, {str(SCRIPTS)!r})\n"
            f"for m in {modulos!r}:\n"
            "    mod = importlib.import_module(m)\n"
            "    origem = getattr(mod, '__file__', None) or list(mod.__path__)[0]\n"
            f"    if not str(origem).startswith({str(SCRIPTS)!r}):\n"
            "        sys.stderr.write(m + ' veio de ' + str(origem)); sys.exit(3)\n"
        )
        antes = sorted(str(p) for p in SCRIPTS.rglob("*") if "node_modules" not in p.parts)
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as cwd:
            r = subprocess.run([sys.executable, "-I", "-B", "-c", codigo], capture_output=True,
                               text=True, cwd=cwd, env={"HOME": home, "PATH": "/usr/bin:/bin"})
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout, "")
            self.assertEqual(r.stderr, "")
            self.assertEqual(os.listdir(home), [])
            self.assertEqual(os.listdir(cwd), [])
        depois = sorted(str(p) for p in SCRIPTS.rglob("*") if "node_modules" not in p.parts)
        self.assertEqual(antes, depois)


class TestTexto(unittest.TestCase):

    def test_zero_travessao_nos_arquivos_da_unidade(self):
        arquivos = [p for base in (CONTRATOS, SCRIPTS / "contratos", RAIZ / "tests" / "contratos")
                    for p in base.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
        self.assertTrue(arquivos)
        for p in arquivos:
            with self.subTest(arquivo=p.name):
                texto = p.read_text(encoding="utf-8")
                for proibido in (chr(0x2014), chr(0x2013)):
                    self.assertFalse(proibido in texto, f"travessão U+{ord(proibido):04X} em {p}")


if __name__ == "__main__":
    unittest.main()
