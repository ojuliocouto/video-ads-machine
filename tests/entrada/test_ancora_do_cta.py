"""W7.X item 7: a âncora PADRÃO do bloco cta é a primeira palavra do KEY, quando ela aparece na fala do bloco.

A prova de aluno achou o CTA ancorado em "É" (a primeira palavra do bloco) em vez de "produzir" (a do KEY): o botão
entrava segundos antes de a palavra ser dita. Âncora explícita (`âncora: palavra#n`) continua mandando; fora do cta, a
âncora padrão continua sendo a primeira palavra da fala.
"""
from entrada import para_motor, roteiro_md

CTA = "[cta | LEAD: eu consigo não só | KEY: PRODUZIR AS PÁGINAS | logo] É isso, eu consigo não só produzir as páginas\n"
ABERTURA = "[insert: demo | hook: A | B | C] Começa aqui.\n"


def ancora(roteiro, i=-1):
    return roteiro_md.ler(roteiro).blocos[i]["ancora"]


def test_cta_ancora_na_primeira_palavra_do_key_nao_na_primeira_do_bloco():
    a = ancora(ABERTURA + CTA)
    assert (a["palavra"], a["n"]) == ("produzir", 1)
    assert a["explicita"] is False and a["da_key"] is True


def test_key_cuja_primeira_palavra_nao_esta_na_fala_cai_na_primeira_palavra_do_bloco():
    a = ancora(ABERTURA + "[cta | KEY: SAIBA MAIS | logo] Toque no botão aqui embaixo.\n")
    assert (a["palavra"], a["n"], a["explicita"]) == ("Toque", 1, False) and not a.get("da_key")


def test_primeira_palavra_repetida_pega_a_ocorrencia_onde_o_key_inteiro_comeca():
    a = ancora(ABERTURA + "[cta | KEY: PRODUZIR AS PÁGINAS | logo] Produzir é bom, mas produzir as páginas é o que importa.\n")
    assert (a["palavra"], a["n"]) == ("produzir", 2)           # só a 2ª ocorrência abre o KEY inteiro
    b = ancora(ABERTURA + "[cta | KEY: A GENTE FAZ | logo] Tudo bem? A conversa é longa, a gente faz junto.\n")
    assert (b["palavra"], b["n"]) == ("a", 2)                  # o 2º "a" é o que abre "a gente faz"
    c = ancora(ABERTURA + "[cta | KEY: PRODUZIR AS PÁGINAS | logo] Produzir é bom e produzir cansa.\n")
    assert (c["palavra"], c["n"]) == ("Produzir", 1)           # nenhuma abre o KEY inteiro: a 1ª ocorrência


def test_ancora_explicita_no_cta_continua_mandando():
    a = ancora(ABERTURA + "[cta | KEY: PRODUZIR AS PÁGINAS | âncora: isso | logo] É isso, produzir as páginas\n")
    assert (a["palavra"], a["explicita"]) == ("isso", True) and not a.get("da_key")


def test_fora_do_cta_a_ancora_padrao_segue_sendo_a_primeira_palavra():
    a = ancora(ABERTURA + "[apresentador | KEY: PRODUZIR AS PÁGINAS] É isso, eu consigo produzir as páginas.\n"
               "[cta | KEY: SAIBA MAIS | logo] Toque em saiba mais.\n", i=1)
    assert (a["palavra"], a["n"]) == ("É", 1) and not a.get("da_key")


def test_o_motor_recebe_a_palavra_do_key_no_cta(tmp_path):
    ins = tmp_path / "inserts"
    ins.mkdir()
    (ins / "demo.mp4").write_bytes(b"")
    motor = para_motor.gerar(ABERTURA + CTA, {"versao": 1, "slug": "x", "modo": "avatar", "look": "estudio",
                                              "trilha": {"desligada": True, "motivo": "teste sem trilha"}},
                             avatar=tmp_path / "avatar.mp4", out_dir=tmp_path / "render", inserts_dir=ins)
    L = motor.config["letterings"][-1]
    assert (L["anchor"], L["nth"]) == ("produzir", 1)
