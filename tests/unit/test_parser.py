"""Tests for the annotated-script parser (vam.parser).

Line format: "[visual instruction | LEAD: small line | KEY: BIG WORD] spoken text".
Classification priority: lettering > logo > presenter > insert (fallback).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from vam.parser import classify, parse  # noqa: E402

SAMPLE = """\
[avatar com zoom-in] Se você cria conteúdo todo dia, presta atenção.
[inserção de video | tela do produto] a ferramenta monta tudo sozinha,

[avatar + lettering | LEAD: uma skill de | KEY: PAGINAS] e ela cria páginas inteiras.
[lettering + logo | KEY: GARANTIA] …com garantia total.
[logo]
linha sem colchete deve ser ignorada
[avatar] Clica no link e começa hoje.
"""


def _write(tmp_path, text=SAMPLE):
    p = tmp_path / "roteiro.txt"
    p.write_text(text, encoding="utf-8")
    return str(p)


# ---------- classify ----------

def test_classify_priority_lettering_beats_logo():
    assert classify("lettering + logo") == "lettering_logo"
    assert classify("avatar + lettering") == "lettering"


def test_classify_logo():
    assert classify("logo animada no final") == "logo"


def test_classify_presenter():
    assert classify("avatar com zoom-in") == "orig"
    assert classify("presenter close-up") == "orig"


def test_classify_insert_and_fallback():
    assert classify("inserção de video da tela") == "insert"
    assert classify("qualquer outra coisa") == "insert"


def test_gotcha_insert_instruction_with_presenter_word_becomes_orig():
    # DOCUMENTED GOTCHA (validated behavior kept): the presenter keyword is
    # checked BEFORE the insert fallback, so an insert instruction that
    # mentions the presenter word is (mis)classified as a presenter scene.
    # Insert instructions must NOT contain the presenter keyword.
    assert classify("inserção de video com o avatar na tela") == "orig"


def test_classify_custom_presenter_words():
    assert classify("cena do host falando", presenter_words=("host",)) == "orig"
    # default word list does not know "host"
    assert classify("cena do host falando") == "insert"


# ---------- parse ----------

def test_parse_returns_expected_blocks(tmp_path):
    blocks = parse(_write(tmp_path))
    assert [b["tipo"] for b in blocks] == [
        "orig", "insert", "lettering", "lettering_logo", "logo", "orig"]


def test_parse_fields_contract(tmp_path):
    b = parse(_write(tmp_path))[0]
    for k in ("tipo", "instr", "narr", "key", "lead"):
        assert k in b


def test_parse_key_and_lead_extraction(tmp_path):
    blocks = parse(_write(tmp_path))
    let = blocks[2]
    assert let["key"] == "PAGINAS"
    assert let["lead"] == "uma skill de"
    assert let["instr"].strip() == "avatar + lettering"
    # KEY without LEAD
    assert blocks[3]["key"] == "GARANTIA"
    assert blocks[3]["lead"] == ""


def test_parse_cleans_leading_punctuation_from_narr(tmp_path):
    blocks = parse(_write(tmp_path))
    assert blocks[3]["narr"].startswith("com garantia")


def test_parse_skips_blank_and_unbracketed_lines(tmp_path):
    blocks = parse(_write(tmp_path))
    assert len(blocks) == 6
    assert all("colchete" not in b["narr"] for b in blocks)


def test_parse_zoom_flag(tmp_path):
    blocks = parse(_write(tmp_path))
    assert blocks[0]["zoom"] is True
    assert blocks[-1]["zoom"] is False


def test_parse_logo_block_empty_narr(tmp_path):
    blocks = parse(_write(tmp_path))
    assert blocks[4]["tipo"] == "logo"
    assert blocks[4]["narr"] == ""
