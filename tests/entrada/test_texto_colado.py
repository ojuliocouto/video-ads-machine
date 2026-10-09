"""Testes de entrada/texto_colado (W1.B): a normalização do texto colado no chat.

A regra (contratos/roteiro-convencao.md, "Normalização do texto colado"): só mexe em aspas,
espaços, quebras de linha e rótulos de chat. A sequência de palavras de quem fala sai igual.
"""
import random
import unittest
from pathlib import Path

from entrada import roteiro_md, texto_colado

RAIZ = Path(__file__).resolve().parents[2]
EXEMPLOS = RAIZ / "contratos" / "exemplos"
CONVENCAO = RAIZ / "contratos" / "roteiro-convencao.md"
NOMES = ("completo", "so-fala", "texto-colado", "lista", "layouts", "cta-logo")

N = texto_colado.normalizar


def exemplo(nome):
    return (EXEMPLOS / f"roteiro.valido.{nome}.md").read_text(encoding="utf-8")


def blocos_esperados(nome):
    import json
    return json.loads((EXEMPLOS / f"roteiro.valido.{nome}.blocos.json").read_text(encoding="utf-8"))


class TestRegrasUmaPorUma(unittest.TestCase):

    def test_quebras_de_linha_viram_barra_n(self):
        self.assertEqual(N("a\r\nb\rc\n"), "a\nb\nc\n")

    def test_invisiveis_do_contrato_saem(self):
        for cp in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF):
            with self.subTest(codigo=hex(cp)):
                self.assertEqual(N("ca" + chr(cp) + "sa\n"), "casa\n")

    def test_marcas_de_direcao_do_whatsapp_tambem_saem(self):
        # extensão do contrato: o iPhone prefixa linhas com U+200E, e ela faz a linha
        # "não começar com [" para o leitor.
        self.assertEqual(N(chr(0x200E) + "[apresentador] Oi" + chr(0x200F) + ".\n"), "[apresentador] Oi.\n")

    def test_aspas_curvas_duplas_viram_retas(self):
        self.assertEqual(N("“ola” „oi‟\n"), '"ola" "oi"\n')

    def test_aspas_curvas_simples_viram_retas(self):
        self.assertEqual(N("‘a’ ‚b‛\n"), "'a' 'b'\n")

    def test_apostrofo_curvo_vira_reto(self):
        self.assertEqual(N("d’água\n"), "d'água\n")

    def test_espaco_especial_e_tabulacao_viram_espaco(self):
        self.assertEqual(N("a b c d\te\n"), "a b c d e\n")

    def test_espacos_repetidos_e_das_pontas(self):
        self.assertEqual(N("   a   b   \n"), "a b\n")

    def test_linhas_vazias_seguidas_viram_uma(self):
        self.assertEqual(N("a\n\n\n\nb\n"), "a\n\nb\n")

    def test_linha_so_de_espacos_conta_como_vazia(self):
        self.assertEqual(N("a\n   \n \t \nb\n"), "a\n\nb\n")

    def test_termina_com_exatamente_uma_quebra(self):
        self.assertEqual(N("a"), "a\n")
        self.assertEqual(N("a\n\n\n"), "a\n")

    def test_comeco_nao_tem_linha_vazia(self):
        self.assertEqual(N("\n\n a\n"), "a\n")

    def test_vazio_continua_vazio(self):
        self.assertEqual(N(""), "")
        self.assertEqual(N(" \n\n \t"), "")

    def test_separador_de_linha_do_google_docs_vira_quebra(self):
        self.assertEqual(N("a\u000bb c d\n"), "a\nb\nc\nd\n")

    def test_nao_mexe_em_acento_nem_em_forma_de_unicode(self):
        # NFD continua NFD: a fala é byte a byte, só aspas e espaços mudam
        texto = "Café com água\n"
        self.assertEqual(N(texto), texto)

    def test_nao_mexe_em_variacao_de_emoji(self):
        texto = "❌️ a proposta atrasa\n"
        self.assertEqual(N(texto), texto)


class TestRotulosDeChat(unittest.TestCase):

    def test_iphone_com_virgula(self):
        self.assertEqual(N("[08/10/2026, 10:32] Ana: oi\n"), "oi\n")

    def test_iphone_sem_virgula_e_com_segundos(self):
        self.assertEqual(N("[08/10/2026 10:32:15] Ana Souza: oi\n"), "oi\n")

    def test_android(self):
        self.assertEqual(N("08/10/2026 10:32 - Ana: oi\n"), "oi\n")
        self.assertEqual(N("08/10/2026, 10:32 - Ana: oi\n"), "oi\n")

    def test_relogio_de_12_horas(self):
        self.assertEqual(N("[10/8/26, 10:32:15 PM] Ana: oi\n"), "oi\n")
        self.assertEqual(N("[10/8/2026, 10:32 am] Ana: oi\n"), "oi\n")

    def test_nome_com_til_numero_e_emoji(self):
        for nome in ("~ Ana María", "+55 11 91234-5678", "Ju \U0001F642", "João da Silva"):
            with self.subTest(nome=nome):
                self.assertEqual(N(f"[08/10/2026, 10:32] {nome}: oi\n"), "oi\n")

    def test_rotulo_antes_de_direcao(self):
        self.assertEqual(N("[08/10/2026, 10:32] Ana: [apresentador] Oi.\n"), "[apresentador] Oi.\n")

    def test_marca_de_direcao_antes_do_rotulo(self):
        self.assertEqual(N(chr(0x200E) + "[08/10/2026, 10:32:15] Ana: oi\n"), "oi\n")

    def test_so_o_rotulo_do_comeco_da_linha_sai(self):
        linha = "[apresentador] Combinado 08/10/2026 10:32 - Ana: vem\n"
        self.assertEqual(N(linha), linha)

    def test_direcao_sem_rotulo_fica_igual(self):
        linha = "[insert: agenda | hook: A | B | C] Fala.\n"
        self.assertEqual(N(linha), linha)

    def test_hora_sem_data_nao_e_rotulo(self):
        self.assertEqual(N("10:32 - Ana: oi\n"), "10:32 - Ana: oi\n")

    def test_rotulo_sem_nome_nao_come_a_direcao(self):
        linha = "[08/10/2026, 10:32] [apresentador] Oi.\n"
        self.assertEqual(N(linha), linha)

    def test_dois_pontos_da_fala_ficam(self):
        self.assertEqual(N("[08/10/2026, 10:32] Ana: Enquanto isso: tudo atrasa\n"),
                         "Enquanto isso: tudo atrasa\n")


class TestExemplosDoContrato(unittest.TestCase):

    def test_entrada_suja_do_documento_vira_o_exemplo_limpo(self):
        doc = CONVENCAO.read_text(encoding="utf-8")
        bruto = roteiro_md.contrato().bloco_do_documento(doc, "exemplo:texto-colado:entrada")
        self.assertEqual(N(bruto), exemplo("texto-colado"))

    def test_saida_da_entrada_suja_le_os_blocos_esperados(self):
        doc = CONVENCAO.read_text(encoding="utf-8")
        bruto = roteiro_md.contrato().bloco_do_documento(doc, "exemplo:texto-colado:entrada")
        lido, erros = roteiro_md.contrato().ler_roteiro(N(bruto))
        self.assertEqual(erros, [])
        self.assertEqual(lido, blocos_esperados("texto-colado"))

    def test_os_seis_exemplos_limpos_sao_ponto_fixo(self):
        for nome in NOMES:
            with self.subTest(exemplo=nome):
                self.assertEqual(N(exemplo(nome)), exemplo(nome))

    def test_idempotente_sobre_a_entrada_suja(self):
        doc = CONVENCAO.read_text(encoding="utf-8")
        bruto = roteiro_md.contrato().bloco_do_documento(doc, "exemplo:texto-colado:entrada")
        uma = N(bruto)
        self.assertEqual(N(uma), uma)


ROTULOS = (
    "[08/10/2026, 10:32] {n}: ",
    "[08/10/2026 10:32:15] {n}: ",
    "08/10/2026 10:32 - {n}: ",
    "08/10/2026, 10:32 - {n}: ",
    "[10/8/26, 10:32:15 PM] {n}: ",
)
NOMES_DE_CHAT = ("Ana", "João Silva", "~ Maria Clara", "+55 11 91234-5678", "Ju \U0001F642")
ESPACOS_SUJOS = (" ", "  ", "\t", "  ", " ", "   ")
INVISIVEIS = (chr(0x200B), chr(0x200C), chr(0x200D), chr(0x2060), chr(0xFEFF), chr(0x200E))


def curvar_aspas(texto):
    """Inverso da regra 3, quando as aspas estão em pares."""
    for reta, (abre, fecha) in (('"', ("“", "”")), ("'", ("‘", "’"))):
        if texto.count(reta) % 2 == 0 and reta in texto:
            saida, aberta = [], True
            for ch in texto:
                if ch == reta:
                    saida.append(abre if aberta else fecha)
                    aberta = not aberta
                else:
                    saida.append(ch)
            texto = "".join(saida)
    return texto


def sujar(texto, rng):
    """Aplica ao texto limpo o inverso de cada regra, de forma que normalizar devolva o original."""
    texto = curvar_aspas(texto)
    linhas = texto.split("\n")[:-1]
    saida = []
    for linha in linhas:
        if not linha.strip():
            saida.extend([""] * rng.randint(1, 4))      # só onde já havia linha vazia
            continue
        pedacos = []
        for ch in linha:
            if ch == " " and rng.random() < 0.3:
                pedacos.append(rng.choice(ESPACOS_SUJOS))
            else:
                pedacos.append(ch)
            if rng.random() < 0.02:
                pedacos.append(rng.choice(INVISIVEIS))
        sujo = "".join(pedacos)
        if not linha.startswith("#") and rng.random() < 0.8:
            sujo = rng.choice(ROTULOS).format(n=rng.choice(NOMES_DE_CHAT)) + sujo
        saida.append(sujo + rng.choice(("", " ", "  ", "\t")))
    fim = rng.choice(("\r\n", "\r", "\n"))
    return fim * rng.randint(0, 2) + fim.join(saida) + fim * rng.randint(1, 3)


class TestSequenciaDePalavras(unittest.TestCase):

    def test_sujar_e_normalizar_devolve_o_original_exato(self):
        for nome in NOMES:
            for semente in range(25):
                with self.subTest(exemplo=nome, semente=semente):
                    limpo = exemplo(nome)
                    sujo = sujar(limpo, random.Random(f"{nome}-{semente}"))
                    self.assertNotEqual(sujo, limpo)
                    self.assertEqual(N(sujo), limpo)

    def test_a_sequencia_de_palavras_nao_muda(self):
        palavras = roteiro_md.contrato().palavras
        for nome in NOMES:
            for semente in range(10):
                with self.subTest(exemplo=nome, semente=semente):
                    limpo = exemplo(nome)
                    sujo = sujar(limpo, random.Random(f"w-{nome}-{semente}"))
                    self.assertEqual(palavras(N(sujo)), palavras(limpo))

    def test_o_sujo_normalizado_le_os_mesmos_blocos(self):
        for nome in NOMES:
            with self.subTest(exemplo=nome):
                sujo = sujar(exemplo(nome), random.Random(f"b-{nome}"))
                lido, erros = roteiro_md.contrato().ler_roteiro(N(sujo))
                self.assertEqual(erros, [])
                self.assertEqual(lido, blocos_esperados(nome))

    def test_rotulo_de_chat_sem_normalizar_reprova_na_direcao(self):
        # o motivo de a normalização existir (ver roteiro.invalido.direcao.md)
        sujo = "[08/10/2026, 10:32] Ana: [apresentador] Oi.\n[cta | KEY: SAIBA MAIS] Toque.\n"
        _, erros = roteiro_md.contrato().ler_roteiro(sujo)
        self.assertTrue(erros)
        _, erros = roteiro_md.contrato().ler_roteiro(N(sujo))
        self.assertEqual(erros, [])


if __name__ == "__main__":
    unittest.main()
