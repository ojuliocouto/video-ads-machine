"""Testes de entrada/para_motor (W1.B): roteiro.md + projeto.json -> os 3 arquivos que o motor
atual (gen_ad_v2, produzir_roteiro e quem lê o inserts.json) consome:

  <ad>_leva.txt        uma linha por bloco: [instrução] fala
  <ad>_inserts.json    UMA entrada por bloco de insert, na ordem dos blocos
  <ad>_<look>.json     config do overlay (hook, cta, kw_phrases, letterings, labels)

O formato é o deduzido do código (parser_roteiro.parse, find_insert, o laço de letterings do
gen_ad_v2 e as leituras posicionais de inserts.json em build_composite, medir_ritmo,
prancha_direcao e analise_inserts). Aqui o motor antigo é simulado com as MESMAS regras, não
com as do módulo testado.
"""
import copy
import hashlib
import json
import re
import socket
import tempfile
import unicodedata
import unittest
from pathlib import Path

from entrada import para_motor, roteiro_md

try:
    import parser_roteiro
except ImportError:  # pragma: no cover
    parser_roteiro = None

RAIZ = Path(__file__).resolve().parents[2]
EXEMPLOS = RAIZ / "contratos" / "exemplos"
ENTRADA = RAIZ / "scripts" / "entrada"


def exemplo(nome):
    return (EXEMPLOS / f"roteiro.valido.{nome}.md").read_text(encoding="utf-8")


def projeto_exemplo(nome):
    return json.loads((EXEMPLOS / f"projeto.valido.{nome}.json").read_text(encoding="utf-8"))


def projeto_base(**extra):
    p = {"versao": 1, "slug": "ad99v2", "modo": "avatar", "look": "laranja",
         "trilha": {"desligada": True, "motivo": "teste sem trilha licenciada"}}
    p.update(extra)
    return p


# --- o motor antigo, como o código dele faz --------------------------------------------------

def norm_motor(w):
    """Igual a gen_ad_v2.norm."""
    w = unicodedata.normalize("NFKD", w)
    w = "".join(c for c in w if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", w.lower())


def achar_insert(instr, inserts):
    """Igual a produzir_roteiro.find_insert e gen_ad_v2.find_insert_cfg: 1ª chave contida na instrução."""
    s = instr.lower()
    for k, v in inserts.items():
        if k in s:
            return k, v
    return None, None


def palavras_do_motor(blocos_antigos):
    """A lista `words` do gen_ad_v2: os tokens do narr de cada bloco, na ordem."""
    return [t for b in blocos_antigos for t in b["narr"].split()]


def posicao_do_motor(words, lettering):
    """O laço de letterings do gen_ad_v2: n-ésima ocorrência (no anúncio inteiro) da palavra."""
    alvo, n = norm_motor(lettering["anchor"]), 0
    for i, w in enumerate(words):
        if norm_motor(w) == alvo:
            n += 1
            if n == lettering.get("nth", 1):
                return i
    return None


class Base(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self._tmp.name)
        self.ins = self.pasta / "inserts"
        self.avatar = self.pasta / "avatar" / "avatar.mp4"
        self.out = self.pasta / "render"
        self.ins.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def criar_inserts(self, *chaves, ext=".mp4"):
        for c in chaves:
            (self.ins / f"{c}{ext}").write_bytes(b"")

    def gerar(self, roteiro, projeto=None, **kw):
        lei = roteiro if not isinstance(roteiro, str) else roteiro_md.ler(roteiro)
        for b in lei.blocos:
            if b["tipo"] == "insert" and not list(self.ins.glob(f"{b['insert']}.*")):
                self.criar_inserts(b["insert"])
        return para_motor.gerar(roteiro, projeto or projeto_base(), avatar=self.avatar,
                                out_dir=self.out, inserts_dir=self.ins, **kw)

    def leva_antiga(self, motor):
        """Grava a leva e passa pelo parser REAL do motor antigo."""
        if parser_roteiro is None:
            self.skipTest("scripts/parser_roteiro.py saiu do repo")
        arq = self.pasta / "x_leva.txt"
        arq.write_text(motor.leva, encoding="utf-8")
        return parser_roteiro.parse(str(arq))


# --- o exemplo completo do contrato ----------------------------------------------------------

LEVA_COMPLETO = [
    "[inserção de vídeo: #1#] Você perde três horas por dia nisso aqui.",
    "[apresentador de frente para a câmera] E eu sei porque eu fazia igual, todo santo dia.",
    "[apresentador + lettering | LEAD: o problema não é | KEY: FALTA DE TEMPO] O problema não é falta de tempo.",
    "[inserção de vídeo: #2#] É que cada tarefa repetida come um pedaço da sua agenda.",
    "[apresentador de frente para a câmera] Enquanto isso: a proposta atrasa, o cliente esfria e você perde a venda.",
    "[inserção de vídeo: #3#] Com uma automação simples, isso roda sozinho enquanto você atende.",
    "[apresentador + lettering + logo | LEAD: toque em | KEY: SAIBA MAIS] Toque em saiba mais e veja como montar a sua.",
]


class TestExemploCompleto(Base):

    def setUp(self):
        super().setUp()
        self.projeto = projeto_exemplo("completo")
        self.motor = self.gerar(exemplo("completo"), self.projeto)

    def test_o_nome_do_anuncio_padrao_e_o_slug_do_projeto(self):
        self.assertEqual(self.motor.ad, "tres-horas")

    def test_leva_uma_linha_por_bloco_exata(self):
        self.assertEqual(self.motor.leva.split("\n"), LEVA_COMPLETO + [""])

    def test_leva_sem_linha_vazia_nem_colchete_na_fala(self):
        for linha in self.motor.leva.splitlines():
            self.assertTrue(linha.startswith("["))
            self.assertEqual(linha.count("["), 1)
            self.assertEqual(linha.count("]"), 1)

    @unittest.skipIf(parser_roteiro is None, "scripts/parser_roteiro.py saiu do repo")
    def test_o_parser_antigo_le_tipos_key_e_lead(self):
        blocos = self.leva_antiga(self.motor)
        self.assertEqual([b["type"] for b in blocos],
                         ["insert", "orig", "lettering", "insert", "orig", "insert", "lettering_logo"])
        self.assertEqual((blocos[2]["lead"], blocos[2]["key"]), ("o problema não é", "FALTA DE TEMPO"))
        self.assertEqual((blocos[6]["lead"], blocos[6]["key"]), ("toque em", "SAIBA MAIS"))
        self.assertEqual(blocos[0]["key"], "")

    @unittest.skipIf(parser_roteiro is None, "scripts/parser_roteiro.py saiu do repo")
    def test_a_narracao_que_o_motor_le_e_a_fala_do_roteiro(self):
        lei = roteiro_md.ler(exemplo("completo"))
        blocos = self.leva_antiga(self.motor)
        self.assertEqual([b["narr"] for b in blocos],
                         [re.sub(r"^[\s,…\.]+", "", b["fala"]) for b in lei.blocos])

    def test_inserts_exatos_um_por_bloco_de_insert_na_ordem(self):
        i = str(self.ins)
        self.assertEqual(self.motor.inserts, {
            "#1#": {"file": f"{i}/painel.mp4", "start": 0, "speed": 1.0},
            "#2#": {"file": f"{i}/planilha.mp4", "start": 2.5, "speed": 1.2, "split": True,
                    "crop": "1280:720:0:0", "exposicao": 0.1, "texto_proprio": True},
            "#3#": {"file": f"{i}/automacao.mp4", "start": 0, "speed": 1.5, "zoom": 1.2, "dur_max": 4.0},
        })
        self.assertEqual(list(self.motor.inserts), ["#1#", "#2#", "#3#"])

    @unittest.skipIf(parser_roteiro is None, "scripts/parser_roteiro.py saiu do repo")
    def test_o_motor_antigo_acha_o_insert_certo_de_cada_bloco(self):
        blocos = self.leva_antiga(self.motor)
        chaves = list(self.motor.inserts)
        n = 0
        for b in blocos:
            if b["type"] != "insert":
                continue
            k, v = achar_insert(b["instr"], self.motor.inserts)
            self.assertEqual(k, chaves[n])           # e o n-ésimo valor é o que os leitores posicionais veem
            self.assertIs(v, list(self.motor.inserts.values())[n])
            n += 1
        self.assertEqual(n, len(chaves))

    def test_config_exata(self):
        esperado = {
            "ad": "tres-horas",
            "look": "laranja",
            "format": "9x16",
            "avatar": str(self.avatar),
            "out_dir": str(self.out),
            "hook": {"eyebrow": "VOCÊ PERDE", "l1": "3 horas por dia", "accent": "NISSO AQUI",
                     "style": "punch"},
            "cta_label": "saiba mais",
            "kw_phrases": ["tempo"],
            "letterings": [
                {"lead": "o problema não é", "key": "FALTA DE TEMPO", "anchor": "o", "nth": 1, "dur": 2.2},
                {"lead": "enquanto isso", "key": "a proposta atrasa", "anchor": "a", "nth": 1,
                 "dur": 1.4, "pilha": "lista1"},
                {"lead": "", "key": "o cliente esfria", "anchor": "o", "nth": 2, "dur": 1.4,
                 "pilha": "lista1"},
                {"lead": "", "key": "você perde a venda", "anchor": "você", "nth": 2, "dur": 2.2,
                 "pilha": "lista1"},
                {"lead": "toque em", "key": "SAIBA MAIS", "anchor": "saiba", "nth": 1, "dur": 2.6},
            ],
            "labels": {"#1#": "painel de tarefas", "#2#": "planilha", "#3#": "automacao"},
        }
        self.assertEqual(self.motor.config, esperado)
        self.assertEqual(list(self.motor.config),
                         ["ad", "look", "format", "avatar", "out_dir", "hook", "cta_label",
                          "kw_phrases", "letterings", "labels"])

    @unittest.skipIf(parser_roteiro is None, "scripts/parser_roteiro.py saiu do repo")
    def test_o_motor_antigo_pousa_cada_lettering_na_palavra_certa(self):
        blocos = self.leva_antiga(self.motor)
        words = palavras_do_motor(blocos)
        inicio, ini = [], 0
        for b in blocos:
            inicio.append(ini)
            ini += len(b["narr"].split())
        # dentro do bloco: o bloco 3 pousa em "O", a lista em "a", "o" e "você", o CTA em "saiba" (a primeira palavra do KEY, W7.X)
        esperado = [inicio[2] + 0, inicio[4] + 2, inicio[4] + 5, inicio[4] + 9, inicio[6] + 2]
        achado = [posicao_do_motor(words, L) for L in self.motor.config["letterings"]]
        self.assertEqual(achado, esperado)
        self.assertEqual([words[p] for p in achado], ["O", "a", "o", "você", "saiba"])

    def test_json_dos_arquivos_e_deterministico_e_sem_escape(self):
        outra = self.gerar(exemplo("completo"), copy.deepcopy(self.projeto))
        self.assertEqual(self.motor.leva, outra.leva)
        self.assertEqual(self.motor.inserts_json(), outra.inserts_json())
        self.assertEqual(self.motor.config_json(), outra.config_json())
        self.assertIn("VOCÊ PERDE", self.motor.config_json())
        self.assertTrue(self.motor.config_json().endswith("}\n"))
        self.assertEqual(json.loads(self.motor.config_json()), self.motor.config)
        self.assertEqual(self.motor.inserts_json(), json.dumps(self.motor.inserts, ensure_ascii=False, indent=2) + "\n")


# --- letterings e âncoras --------------------------------------------------------------------

class TestAncorasENth(Base):

    def test_nth_conta_o_anuncio_inteiro_e_nao_so_o_bloco(self):
        roteiro = ("[insert: demo | hook: UM | DOIS | TRES] A campanha não sobe.\n"
                   "[apresentador | KEY: DE NOVO | âncora: campanha] Outra campanha, outra história.\n"
                   "[cta | KEY: SAIBA MAIS] Toque em saiba mais.\n")
        motor = self.gerar(roteiro)
        self.assertEqual(motor.config["letterings"][0],
                         {"lead": "", "key": "DE NOVO", "anchor": "campanha", "nth": 2, "dur": 2.2})
        words = palavras_do_motor(self.leva_antiga(motor))
        self.assertEqual(words[posicao_do_motor(words, motor.config["letterings"][0])], "campanha,")
        self.assertEqual(posicao_do_motor(words, motor.config["letterings"][0]), 5)

    def test_ancora_com_numero_soma_as_ocorrencias_dos_blocos_anteriores(self):
        roteiro = ("[insert: demo | hook: A | B | C] Um dia chega.\n"
                   "[apresentador | KEY: OUTRO DIA | âncora: dia#2] Um dia eu fiz, no outro dia já rodava.\n"
                   "[cta | KEY: SAIBA MAIS] Toque.\n")
        motor = self.gerar(roteiro)
        L = motor.config["letterings"][0]
        self.assertEqual((L["anchor"], L["nth"]), ("dia", 3))
        words = palavras_do_motor(self.leva_antiga(motor))
        self.assertEqual(posicao_do_motor(words, L), 3 + 6)       # 2º "dia" do bloco 2

    def test_exemplo_cta_logo_do_contrato(self):
        # o exemplo do contrato não tem hook, e o motor antigo exige um
        linhas = exemplo("cta-logo").split("\n")
        linhas[0] = linhas[0].replace("| âncora: dia#2]", "| âncora: dia#2 | hook: UM | DOIS | TRES]")
        self.assertIn("hook:", linhas[0])
        motor = self.gerar("\n".join(linhas))
        self.assertEqual(motor.config["letterings"], [
            {"lead": "um dia na mão", "key": "NO OUTRO, SOZINHO", "anchor": "dia", "nth": 2, "dur": 2.2},
            {"lead": "tudo isso em", "key": "UMA TARDE", "anchor": "tarde", "nth": 1, "dur": 2.2},
            {"lead": "toque em", "key": "SAIBA MAIS", "anchor": "saiba", "nth": 1, "dur": 2.6},
        ])
        self.assertEqual(motor.config["kw_phrases"], ["saiba mais"])

    def test_lista_com_marcadores_pousa_cada_item_na_primeira_palavra_dele(self):
        roteiro = ("[insert: demo | hook: A | B | C] Começa aqui.\n"
                   "[apresentador | KEY: O DIA PASSA] O dia passa e nada anda.\n"
                   "[lista | LEAD: enquanto isso] Enquanto isso: ❌ a proposta atrasa ❌ o cliente esfria "
                   "❌ e você perde a venda.\n"
                   "[cta | KEY: SAIBA MAIS] Toque em saiba mais.\n")
        motor = self.gerar(roteiro)
        pilha = [L for L in motor.config["letterings"] if L.get("pilha")]
        self.assertEqual([(L["lead"], L["key"], L["anchor"]) for L in pilha], [
            ("enquanto isso", "❌ a proposta atrasa", "a"),
            ("", "❌ o cliente esfria", "o"),
            ("", "❌ e você perde a venda", "e"),
        ])
        words = palavras_do_motor(self.leva_antiga(motor))
        inicio = len(words) - len("Toque em saiba mais.".split()) - len(
            "Enquanto isso: a proposta atrasa o cliente esfria e você perde a venda.".split())
        achado = [posicao_do_motor(words, L) for L in pilha]
        self.assertEqual(achado, [inicio + 2, inicio + 5, inicio + 8])

    def test_lista_por_virgula_acha_o_item_pela_sequencia_e_nao_pela_primeira_palavra(self):
        roteiro = ("[insert: demo | hook: A | B | C] O dia passa.\n"
                   "[lista] Com a automação: a proposta sai na hora, o cliente recebe resposta e a venda fecha.\n"
                   "[cta | KEY: SAIBA MAIS] Toque.\n")
        motor = self.gerar(roteiro)
        pilha = [L for L in motor.config["letterings"] if L.get("pilha")]
        # o 1º "a" do bloco é o de "Com a automação": o item pousa no 2º
        self.assertEqual([(L["key"], L["anchor"], L["nth"]) for L in pilha], [
            ("a proposta sai na hora", "a", 2),
            ("o cliente recebe resposta", "o", 2),
            ("a venda fecha", "a", 3),
        ])
        words = palavras_do_motor(self.leva_antiga(motor))
        base = len("O dia passa.".split())
        # tokens do bloco 2: Com(0) a(1) automação:(2) a(3) proposta(4) ... o(8) ... a(13) venda(14)
        self.assertEqual([posicao_do_motor(words, L) for L in pilha], [base + 3, base + 8, base + 13])

    def test_lista_sem_lead_fica_com_lead_vazio_em_todas_as_linhas(self):
        roteiro = ("[insert: demo | hook: A | B | C] O dia passa.\n"
                   "[lista] Com a automação: a proposta sai na hora, o cliente recebe resposta e a venda fecha.\n"
                   "[cta | KEY: SAIBA MAIS] Toque.\n")
        pilha = [L for L in self.gerar(roteiro).config["letterings"] if L.get("pilha")]
        self.assertEqual([L["lead"] for L in pilha], ["", "", ""])

    def test_pilha_dura_1_4_nos_itens_do_meio_e_2_2_no_ultimo(self):
        roteiro = ("[insert: demo | hook: A | B | C] O dia passa.\n"
                   "[lista] Com a automação: a proposta sai na hora, o cliente recebe resposta e a venda fecha.\n"
                   "[cta | KEY: SAIBA MAIS] Toque.\n")
        pilha = [L for L in self.gerar(roteiro).config["letterings"] if L.get("pilha")]
        self.assertEqual([L["dur"] for L in pilha], [1.4, 1.4, 2.2])

    def test_cada_lista_tem_o_proprio_grupo_de_pilha(self):
        motor = self.gerar(self._lista_dupla())
        grupos = [L["pilha"] for L in motor.config["letterings"] if L.get("pilha")]
        self.assertEqual(grupos, ["lista1"] * 3 + ["lista2"] * 3)

    def _lista_dupla(self):
        return ("[insert: demo | hook: A | B | C] O dia passa.\n"
                "[lista | LEAD: antes] Antes: ❌ a proposta atrasa ❌ o cliente esfria ❌ e a venda cai.\n"
                "[lista] Agora: a proposta sai, o cliente responde e a venda fecha.\n"
                "[cta | KEY: SAIBA MAIS] Toque.\n")

    def test_ancora_explicita_na_lista_vale_para_a_primeira_linha(self):
        roteiro = ("[insert: demo | hook: A | B | C] O dia passa.\n"
                   "[lista | LEAD: antes | âncora: antes] Antes: ❌ a proposta atrasa ❌ o cliente esfria.\n"
                   "[cta | KEY: SAIBA MAIS] Toque.\n")
        pilha = [L for L in self.gerar(roteiro).config["letterings"] if L.get("pilha")]
        self.assertEqual([L["anchor"] for L in pilha], ["antes", "o"])

    def test_ancora_padrao_ignora_pontuacao_solta_no_comeco_da_fala(self):
        roteiro = ("[insert: demo | hook: A | B | C] Começa.\n"
                   "[apresentador | KEY: ISSO] ... e isso muda tudo.\n"
                   "[cta | KEY: SAIBA MAIS] Toque.\n")
        motor = self.gerar(roteiro)
        L = motor.config["letterings"][0]
        self.assertEqual(L["anchor"], "e")
        words = palavras_do_motor(self.leva_antiga(motor))
        self.assertEqual(words[posicao_do_motor(words, L)], "e")
        self.assertEqual(posicao_do_motor(words, L), 1)          # "Começa." tem 1 palavra, o "e" abre o bloco 2

    def test_acento_e_pontuacao_da_ancora_batem_com_a_norma_do_motor(self):
        roteiro = ("[insert: demo | hook: A | B | C] Começa.\n"
                   "[apresentador | KEY: VOCÊ | âncora: você] Olá, é você?\n"
                   "[cta | KEY: SAIBA MAIS] Toque.\n")
        motor = self.gerar(roteiro)
        words = palavras_do_motor(self.leva_antiga(motor))
        pos = posicao_do_motor(words, motor.config["letterings"][0])
        self.assertEqual(words[pos], "você?")

    def test_insert_com_key_vira_lettering_e_a_instrucao_leva_lead_e_key(self):
        roteiro = ("[insert: demo | LEAD: olha | KEY: ISSO | hook: A | B | C] Olha isso aqui.\n"
                   "[cta | KEY: SAIBA MAIS] Toque.\n")
        motor = self.gerar(roteiro)
        self.assertEqual(motor.leva.split("\n")[0],
                         "[inserção de vídeo: #1# | LEAD: olha | KEY: ISSO] Olha isso aqui.")
        blocos = self.leva_antiga(motor)
        self.assertEqual((blocos[0]["type"], blocos[0]["lead"], blocos[0]["key"]), ("insert", "olha", "ISSO"))
        k, _ = achar_insert(blocos[0]["instr"], motor.inserts)
        self.assertEqual(k, "#1#")
        self.assertEqual(motor.config["letterings"][0]["anchor"], "olha")


# --- hook, cta e ênfase ----------------------------------------------------------------------

class TestHookCtaEnfase(Base):

    ROTEIRO = ("[insert: demo | hook: VOCÊ PERDE | 3 horas | NISSO AQUI] Você perde três *horas* por dia.\n"
               "[apresentador] Isso é *muito* tempo, de *verdade*.\n"
               "[cta | KEY: SAIBA MAIS] Toque em *saiba mais* e veja *horas*.\n")

    def test_hook_vira_eyebrow_l1_accent(self):
        motor = self.gerar(self.ROTEIRO)
        self.assertEqual(motor.config["hook"], {"eyebrow": "VOCÊ PERDE", "l1": "3 horas", "accent": "NISSO AQUI"})

    def test_estilo_punch_do_projeto_entra_como_style(self):
        motor = self.gerar(self.ROTEIRO, projeto_base(estilo={"hook": "punch"}))
        self.assertEqual(motor.config["hook"]["style"], "punch")

    def test_estilo_editorial_nao_escreve_style(self):
        motor = self.gerar(self.ROTEIRO, projeto_base(estilo={"hook": "editorial"}))
        self.assertNotIn("style", motor.config["hook"])

    def test_roteiro_sem_hook_e_recusado_citando_hook(self):
        with self.assertRaises(para_motor.ErroParaMotor) as ctx:
            self.gerar("[apresentador] Oi.\n[cta | KEY: SAIBA MAIS] Toque.\n")
        self.assertIn("hook", str(ctx.exception))

    def test_enfase_vira_kw_phrases_na_ordem_e_sem_repetir(self):
        motor = self.gerar(self.ROTEIRO)
        self.assertEqual(motor.config["kw_phrases"], ["horas", "muito", "verdade", "saiba mais"])

    def test_sem_enfase_kw_phrases_e_lista_vazia(self):
        motor = self.gerar("[insert: demo | hook: A | B | C] Oi.\n[cta | KEY: SAIBA MAIS] Toque.\n")
        self.assertEqual(motor.config["kw_phrases"], [])

    def test_a_fala_vai_sem_asterisco_para_a_leva(self):
        motor = self.gerar(self.ROTEIRO)
        self.assertNotIn("*", motor.leva)

    def test_cta_label_padrao_e_do_projeto(self):
        self.assertEqual(self.gerar(self.ROTEIRO).config["cta_label"], "saiba mais")
        motor = self.gerar(self.ROTEIRO, projeto_base(cta={"label": "quero entrar"}))
        self.assertEqual(motor.config["cta_label"], "quero entrar")

    def test_cta_sem_lead_so_aparece_quando_verdadeiro(self):
        self.assertNotIn("cta_sem_lead", self.gerar(self.ROTEIRO).config)
        self.assertNotIn("cta_sem_lead", self.gerar(self.ROTEIRO, projeto_base(cta={"sem_lead": False})).config)
        self.assertIs(self.gerar(self.ROTEIRO, projeto_base(cta={"sem_lead": True})).config["cta_sem_lead"], True)

    def test_cta_sem_lead_no_roteiro_deixa_lead_vazio(self):
        L = self.gerar(self.ROTEIRO).config["letterings"][-1]
        self.assertEqual((L["lead"], L["key"], L["dur"]), ("", "SAIBA MAIS", 2.6))

    def test_formato_1x1_muda_o_format_e_o_nome_do_config(self):
        motor = self.gerar(self.ROTEIRO, projeto_base(formato="1x1"))
        self.assertEqual(motor.config["format"], "1x1")
        self.assertEqual(motor.nomes()["config"], "ad99v2_laranja_1x1.json")

    def test_formato_padrao_9x16(self):
        motor = self.gerar(self.ROTEIRO)
        self.assertEqual(motor.config["format"], "9x16")
        self.assertEqual(motor.nomes(), {"leva": "ad99v2_leva.txt", "inserts": "ad99v2_inserts.json",
                                          "config": "ad99v2_laranja.json"})

    def test_ad_pode_ser_passado(self):
        motor = self.gerar(self.ROTEIRO, ad="jh99v2")
        self.assertEqual(motor.config["ad"], "jh99v2")
        self.assertEqual(motor.nomes()["leva"], "jh99v2_leva.txt")


# --- inserts ---------------------------------------------------------------------------------

class TestInserts(Base):

    ROTEIRO = ("[insert: planilha | split | hook: ISSO | LEVA TEMPO | TODO DIA] É que cada tarefa repetida.\n"
               "[insert: pedidos | cheio] Olha o tamanho da fila de pedidos.\n"
               "[insert: tutorial | pip] E aqui eu te mostro o passo a passo.\n"
               "[apresentador] Parece muito, mas cabe numa tarde.\n"
               "[insert: planilha] Repara que é a mesma planilha.\n"
               "[cta | KEY: SAIBA MAIS] Toque em saiba mais.\n")

    def test_uma_entrada_por_bloco_de_insert_mesmo_com_a_mesma_chave_duas_vezes(self):
        motor = self.gerar(self.ROTEIRO)
        self.assertEqual(list(motor.inserts), ["#1#", "#2#", "#3#", "#4#"])
        self.assertEqual(motor.inserts["#1#"]["file"], motor.inserts["#4#"]["file"])

    def test_layout_split_pip_e_cheio(self):
        i = self.gerar(self.ROTEIRO).inserts
        self.assertIs(i["#1#"]["split"], True)
        self.assertNotIn("pip", i["#1#"])
        self.assertNotIn("split", i["#2#"])             # cheio é o padrão do motor antigo
        self.assertNotIn("pip", i["#2#"])
        self.assertIs(i["#3#"]["pip"], True)
        self.assertNotIn("split", i["#3#"])
        self.assertNotIn("split", i["#4#"])             # sem preferência: o plano decide depois
        self.assertNotIn("pip", i["#4#"])

    @unittest.skipIf(parser_roteiro is None, "scripts/parser_roteiro.py saiu do repo")
    def test_o_motor_antigo_casa_cada_bloco_com_a_propria_entrada(self):
        motor = self.gerar(self.ROTEIRO)
        blocos = self.leva_antiga(motor)
        chaves = list(motor.inserts)
        n = 0
        for b in blocos:
            if b["type"] == "insert":
                self.assertEqual(achar_insert(b["instr"], motor.inserts)[0], chaves[n])
                n += 1
        self.assertEqual(n, 4)

    @unittest.skipIf(parser_roteiro is None, "scripts/parser_roteiro.py saiu do repo")
    def test_chave_com_palavra_que_o_motor_classifica_nao_vira_logo_nem_lettering(self):
        roteiro = ("[insert: catalogo-logo | hook: A | B | C] Olha o catálogo.\n"
                   "[insert: tela-apresentador-lettering] Olha a tela.\n"
                   "[cta | KEY: SAIBA MAIS] Toque.\n")
        motor = self.gerar(roteiro)
        blocos = self.leva_antiga(motor)
        self.assertEqual([b["type"] for b in blocos], ["insert", "insert", "lettering_logo"])
        self.assertEqual([achar_insert(b["instr"], motor.inserts)[0] for b in blocos[:2]], ["#1#", "#2#"])

    @unittest.skipIf(parser_roteiro is None, "scripts/parser_roteiro.py saiu do repo")
    def test_chaves_aninhadas_nao_se_confundem(self):
        roteiro = ("[insert: foo | hook: A | B | C] Primeiro.\n"
                   "[insert: foo-2] Segundo.\n"
                   "[insert: foo] Terceiro.\n"
                   "[cta | KEY: SAIBA MAIS] Toque.\n")
        motor = self.gerar(roteiro)
        blocos = self.leva_antiga(motor)
        achou = [achar_insert(b["instr"], motor.inserts)[1]["file"] for b in blocos[:3]]
        self.assertEqual([Path(f).name for f in achou], ["foo.mp4", "foo-2.mp4", "foo.mp4"])

    def test_rotulo_vira_label_e_sem_rotulo_usa_a_chave_legivel(self):
        roteiro = ("[insert: dashboard-vendas | hook: A | B | C] Olha.\n"
                   "[insert: tela_inicial] Olha.\n"
                   "[insert: pagina] Olha.\n"
                   "[cta | KEY: SAIBA MAIS] Toque.\n")
        projeto = projeto_base(inserts={"pagina": {"rotulo": "página de vendas"}})
        motor = self.gerar(roteiro, projeto)
        self.assertEqual(motor.config["labels"], {"#1#": "dashboard vendas", "#2#": "tela inicial",
                                                  "#3#": "página de vendas"})

    def test_sem_insert_nao_escreve_labels(self):
        motor = self.gerar("[apresentador | hook: A | B | C] Oi.\n[cta | KEY: SAIBA MAIS] Toque.\n")
        self.assertEqual(motor.inserts, {})
        self.assertNotIn("labels", motor.config)

    def test_ajustes_do_projeto_so_valem_para_a_chave_dele(self):
        roteiro = ("[insert: a | hook: X | Y | Z] Um.\n[insert: b] Dois.\n[cta | KEY: SAIBA MAIS] Toque.\n")
        projeto = projeto_base(inserts={"a": {"velocidade": 2, "zoom": 1.5}})
        motor = self.gerar(roteiro, projeto)
        self.assertEqual(motor.inserts["#1#"]["speed"], 2)
        self.assertEqual(motor.inserts["#1#"]["zoom"], 1.5)
        self.assertEqual(motor.inserts["#2#"]["speed"], 1.0)
        self.assertNotIn("zoom", motor.inserts["#2#"])

    def test_imagem_estatica_e_aceita(self):
        self.criar_inserts("foto", ext=".png")
        motor = self.gerar("[insert: foto | hook: A | B | C] Olha.\n[cta | KEY: SAIBA MAIS] Toque.\n")
        self.assertTrue(motor.inserts["#1#"]["file"].endswith("foto.png"))

    def test_insert_sem_arquivo_diz_a_chave_e_onde_colocar(self):
        with self.assertRaises(para_motor.ErroParaMotor) as ctx:
            para_motor.gerar("[insert: sumiu | hook: A | B | C] Olha.\n[cta | KEY: SAIBA MAIS] Toque.\n",
                             projeto_base(), avatar=self.avatar, out_dir=self.out, inserts_dir=self.ins)
        msg = str(ctx.exception)
        self.assertIn("sumiu", msg)
        self.assertIn("inserts", msg)

    def test_dois_arquivos_para_a_mesma_chave_e_ambiguo(self):
        self.criar_inserts("dobro", ext=".mp4")
        self.criar_inserts("dobro", ext=".mov")
        with self.assertRaises(para_motor.ErroParaMotor) as ctx:
            self.gerar("[insert: dobro | hook: A | B | C] Olha.\n[cta | KEY: SAIBA MAIS] Toque.\n")
        self.assertIn("dobro.mp4", str(ctx.exception))
        self.assertIn("dobro.mov", str(ctx.exception))

    def test_arquivo_escondido_nao_conta(self):
        (self.ins / ".DS_Store").write_bytes(b"")
        self.criar_inserts("ok")
        motor = self.gerar("[insert: ok | hook: A | B | C] Olha.\n[cta | KEY: SAIBA MAIS] Toque.\n")
        self.assertEqual(len(motor.inserts), 1)


# --- recusas ---------------------------------------------------------------------------------

class TestRecusas(Base):

    BOM = "[insert: demo | hook: A | B | C] Oi.\n[cta | KEY: SAIBA MAIS] Toque.\n"

    def chamar(self, roteiro, projeto=None, **kw):
        base = dict(avatar=self.avatar, out_dir=self.out, inserts_dir=self.ins)
        base.update(kw)
        self.criar_inserts("demo")
        return para_motor.gerar(roteiro, projeto or projeto_base(), **base)

    def test_roteiro_livre_pede_plano_antes(self):
        with self.assertRaises(para_motor.ErroParaMotor) as ctx:
            self.chamar("Primeira fala.\n\nSegunda fala.\n")
        self.assertIn("plano", str(ctx.exception))

    def test_roteiro_com_erro_lista_as_linhas(self):
        with self.assertRaises(para_motor.ErroParaMotor) as ctx:
            self.chamar("[apresentador] Oi.\n")
        self.assertIn("linha 1 (cta)", str(ctx.exception))

    def test_modo_gravado_e_oneshot_nao_passam_por_aqui(self):
        for modo in ("gravado", "oneshot"):
            with self.subTest(modo=modo):
                p = projeto_base(modo=modo)
                del p["look"]
                with self.assertRaises(para_motor.ErroParaMotor) as ctx:
                    self.chamar(self.BOM, p)
                self.assertIn(modo, str(ctx.exception))

    def test_projeto_fora_do_contrato_cita_o_campo(self):
        p = projeto_base()
        p["aceleracao"] = 9
        with self.assertRaises(para_motor.ErroParaMotor) as ctx:
            self.chamar(self.BOM, p)
        self.assertIn("aceleracao", str(ctx.exception))

    def test_ad_invalido_nao_vira_nome_de_arquivo(self):
        for ruim in ("../fora", "a b", "", "x/y"):
            with self.subTest(ad=ruim):
                with self.assertRaises(para_motor.ErroParaMotor):
                    self.chamar(self.BOM, ad=ruim)

    def test_aceita_texto_leitura_ou_dict_de_leitura(self):
        lei = roteiro_md.ler(self.BOM)
        self.criar_inserts("demo")
        a = para_motor.gerar(self.BOM, projeto_base(), avatar=self.avatar, out_dir=self.out, inserts_dir=self.ins)
        b = para_motor.gerar(lei, projeto_base(), avatar=self.avatar, out_dir=self.out, inserts_dir=self.ins)
        c = para_motor.gerar(lei.como_dict(), projeto_base(), avatar=self.avatar, out_dir=self.out,
                             inserts_dir=self.ins)
        self.assertEqual(a.leva, b.leva)
        self.assertEqual(a.leva, c.leva)
        self.assertEqual(a.config, c.config)

    def test_aceita_o_caminho_do_projeto_json(self):
        arq = self.pasta / "projeto.json"
        arq.write_text(json.dumps(projeto_base()), encoding="utf-8")
        motor = self.chamar(self.BOM, arq)
        self.assertEqual(motor.config["look"], "laranja")

    def test_nao_muda_o_projeto_recebido(self):
        p = projeto_base(inserts={"demo": {"velocidade": 2}})
        antes = copy.deepcopy(p)
        self.chamar(self.BOM, p)
        self.assertEqual(p, antes)


# --- gravar ----------------------------------------------------------------------------------

class TestGravar(Base):

    def setUp(self):
        super().setUp()
        self.motor = self.gerar(exemplo("completo"), projeto_exemplo("completo"))
        self.inputs = self.pasta / "dados" / "inputs"
        self.configs = self.pasta / "configs"

    def test_escreve_os_tres_arquivos_com_os_nomes_do_motor(self):
        res = para_motor.gravar(self.motor, self.inputs, self.configs)
        self.assertEqual(sorted(res), ["config", "inserts", "leva"])
        self.assertEqual(Path(res["leva"]["caminho"]), self.inputs / "tres-horas_leva.txt")
        self.assertEqual(Path(res["inserts"]["caminho"]), self.inputs / "tres-horas_inserts.json")
        self.assertEqual(Path(res["config"]["caminho"]), self.configs / "tres-horas_laranja.json")

    def test_conteudo_e_igual_ao_gerado(self):
        res = para_motor.gravar(self.motor, self.inputs, self.configs)
        self.assertEqual(Path(res["leva"]["caminho"]).read_text(encoding="utf-8"), self.motor.leva)
        self.assertEqual(json.loads(Path(res["inserts"]["caminho"]).read_text(encoding="utf-8")),
                         self.motor.inserts)
        self.assertEqual(json.loads(Path(res["config"]["caminho"]).read_text(encoding="utf-8")),
                         self.motor.config)

    def test_sha256_e_o_do_arquivo_gravado(self):
        res = para_motor.gravar(self.motor, self.inputs, self.configs)
        for item in res.values():
            self.assertEqual(item["sha256"], hashlib.sha256(Path(item["caminho"]).read_bytes()).hexdigest())

    def test_regravar_gera_os_mesmos_bytes_e_nao_deixa_temporario(self):
        a = para_motor.gravar(self.motor, self.inputs, self.configs)
        b = para_motor.gravar(self.motor, self.inputs, self.configs)
        self.assertEqual({k: v["sha256"] for k, v in a.items()}, {k: v["sha256"] for k, v in b.items()})
        self.assertEqual(sorted(p.name for p in self.inputs.iterdir()),
                         ["tres-horas_inserts.json", "tres-horas_leva.txt"])
        self.assertEqual(sorted(p.name for p in self.configs.iterdir()), ["tres-horas_laranja.json"])

    def test_json_gravado_em_utf8_sem_escape_com_quebra_final(self):
        res = para_motor.gravar(self.motor, self.inputs, self.configs)
        texto = Path(res["config"]["caminho"]).read_text(encoding="utf-8")
        self.assertIn("VOCÊ PERDE", texto)
        self.assertTrue(texto.endswith("}\n"))
        self.assertTrue(Path(res["leva"]["caminho"]).read_bytes().endswith(b"\n"))

    def test_so_escreve_dentro_das_duas_pastas(self):
        antes = set(self.pasta.rglob("*"))
        para_motor.gravar(self.motor, self.inputs, self.configs)
        novos = {p for p in set(self.pasta.rglob("*")) - antes if p.is_file()}
        self.assertEqual({p.parent for p in novos}, {self.inputs, self.configs})


# --- sem rede, sem planilha, sem token de máquina --------------------------------------------

class TestIsolamento(Base):

    def test_gera_com_a_rede_bloqueada(self):
        original = socket.socket

        def bloqueado(*a, **k):
            raise AssertionError("para_motor tentou abrir socket")

        socket.socket = bloqueado
        try:
            motor = self.gerar(exemplo("completo"), projeto_exemplo("completo"))
        finally:
            socket.socket = original
        self.assertEqual(len(motor.leva.splitlines()), 7)

    def test_fonte_nao_cita_planilha_nem_token_de_maquina(self):
        src = (ENTRADA / "para_motor.py").read_text(encoding="utf-8").lower()
        # montados por pedaços: o teste não pode ser o primeiro a carregar o que proíbe
        casa = "~/." + "clau" + "de"
        for proibido in ("sheets.googleapis", "spreadsheets", "google-tokens", casa, "urllib"):
            self.assertNotIn(proibido, src)

    def test_grep_de_planilha_na_pasta_inteira_da_entrada_e_vazio(self):
        achados = []
        for arq in sorted(ENTRADA.glob("*.py")):
            if "sheets.googleapis" in arq.read_text(encoding="utf-8"):
                achados.append(arq.name)
        self.assertEqual(achados, [])


if __name__ == "__main__":
    unittest.main()
