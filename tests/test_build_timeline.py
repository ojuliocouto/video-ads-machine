"""Testes TDD do motor build_timeline (Video Ads Machine 2.0, Wave 1 Task 1.3).

Roda com: pytest tests/test_build_timeline.py -v
"""
import os
import sys

# scripts/ nao e um pacote instalado: adiciona ao sys.path pra importar direto.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import build_timeline  # noqa: E402


# ---------------------------------------------------------------------------
# align_words
# ---------------------------------------------------------------------------

def test_align_words_exact_match():
    """Sem erro de grafia: texto e tempos batem direto por ordem."""
    roteiro_words = ["Ninguem", "te", "contou", "isso"]
    transcript_words = [
        {"text": "ninguem", "start": 0.0, "end": 0.4},
        {"text": "te", "start": 0.4, "end": 0.6},
        {"text": "contou", "start": 0.6, "end": 1.0},
        {"text": "isso", "start": 1.0, "end": 1.3},
    ]

    result = build_timeline.align_words(roteiro_words, transcript_words)

    assert result == [
        {"text": "Ninguem", "start": 0.0, "end": 0.4, "kw": False},
        {"text": "te", "start": 0.4, "end": 0.6, "kw": False},
        {"text": "contou", "start": 0.6, "end": 1.0, "kw": False},
        {"text": "isso", "start": 1.0, "end": 1.3, "kw": False},
    ]


def test_align_words_typo_correction():
    """Grafia SEMPRE do roteiro, mesmo quando a transcricao erra a palavra."""
    roteiro_words = ["voce", "usa", "só", "1%"]
    transcript_words = [
        {"text": "voce", "start": 28.72, "end": 28.88},
        {"text": "uza", "start": 28.88, "end": 29.04},  # erro de grafia
        {"text": "so", "start": 29.04, "end": 29.2},  # sem acento
        {"text": "um por cento", "start": 29.2, "end": 29.52},  # transcricao diferente
    ]

    result = build_timeline.align_words(roteiro_words, transcript_words)

    textos = [w["text"] for w in result]
    assert textos == ["voce", "usa", "só", "1%"]
    # tempos vem do transcript, alinhados por ordem (mesma contagem de palavras)
    assert result[0]["start"] == 28.72
    assert result[3]["end"] == 29.52


def test_align_words_keyword_single_asterisk():
    """Palavra sozinha entre asteriscos vira kw=True, sem os asteriscos no texto."""
    roteiro_words = ["seu", "dia", "*muda*", "completamente"]
    transcript_words = [
        {"text": "seu", "start": 1.9, "end": 2.1},
        {"text": "dia", "start": 2.1, "end": 2.4},
        {"text": "muda", "start": 2.4, "end": 2.8},
        {"text": "completamente", "start": 2.8, "end": 3.3},
    ]

    result = build_timeline.align_words(roteiro_words, transcript_words)

    assert [w["kw"] for w in result] == [False, False, True, False]
    assert result[2]["text"] == "muda"


def test_align_words_keyword_multiword_span():
    """Asteriscos podem abrir numa palavra e fechar em outra (frase-chave)."""
    roteiro_words = ["isso", "e", "*oportunidade", "de", "ouro*", "real"]
    transcript_words = [
        {"text": "isso", "start": 0.0, "end": 0.2},
        {"text": "e", "start": 0.2, "end": 0.3},
        {"text": "oportunidade", "start": 0.3, "end": 0.8},
        {"text": "de", "start": 0.8, "end": 0.9},
        {"text": "ouro", "start": 0.9, "end": 1.2},
        {"text": "real", "start": 1.2, "end": 1.5},
    ]

    result = build_timeline.align_words(roteiro_words, transcript_words)

    assert [w["text"] for w in result] == ["isso", "e", "oportunidade", "de", "ouro", "real"]
    assert [w["kw"] for w in result] == [False, False, True, True, True, False]


def test_align_words_transcript_missing_word():
    """Roteiro tem uma palavra que a transcricao nao capturou: interpola o tempo."""
    roteiro_words = ["ola", "mundo", "bom", "dia"]
    transcript_words = [
        {"text": "ola", "start": 0.0, "end": 0.3},
        # "mundo" nao foi reconhecido pelo transcript
        {"text": "bom", "start": 0.6, "end": 0.9},
        {"text": "dia", "start": 0.9, "end": 1.2},
    ]

    result = build_timeline.align_words(roteiro_words, transcript_words)

    assert [w["text"] for w in result] == ["ola", "mundo", "bom", "dia"]
    # "mundo" ganha um tempo interpolado entre "ola" (end 0.3) e "bom" (start 0.6)
    assert 0.3 <= result[1]["start"] < result[1]["end"] <= 0.6


# ---------------------------------------------------------------------------
# group_captions
# ---------------------------------------------------------------------------

def _w(text, start, end, kw=False):
    return {"text": text, "start": start, "end": end, "kw": kw}


def test_group_captions_windows_of_max_words():
    words = [
        _w("transformou", 2.4, 2.96),
        _w("meu", 3.04, 3.2),
        _w("claude", 3.2, 3.68),
        _w("em", 3.68, 3.84),
        _w("um", 3.84, 4.08),
        _w("web", 4.08, 4.32),
    ]

    groups = build_timeline.group_captions(words, max_words=3)

    assert len(groups) == 2
    assert [w["text"] for w in groups[0]["words"]] == ["transformou", "meu", "claude"]
    assert groups[0]["start"] == 2.4
    assert groups[0]["end"] == 3.68
    assert [w["text"] for w in groups[1]["words"]] == ["em", "um", "web"]
    assert groups[1]["start"] == 3.68
    assert groups[1]["end"] == 4.32


def test_group_captions_breaks_on_punctuation():
    """Grupo fecha na pontuacao mesmo sem atingir max_words."""
    words = [
        _w("designer", 4.32, 4.88, kw=True),
        _w("profissional.", 4.88, 5.44, kw=True),
        _w("e", 5.44, 5.6),
        _w("agora", 5.6, 5.84),
    ]

    groups = build_timeline.group_captions(words, max_words=3)

    assert [w["text"] for w in groups[0]["words"]] == ["designer", "profissional."]
    assert [w["text"] for w in groups[1]["words"]] == ["e", "agora"]


def test_group_captions_leftover_words_form_last_group():
    words = [_w("ola", 0.0, 0.2), _w("mundo", 0.2, 0.4)]

    groups = build_timeline.group_captions(words, max_words=3)

    assert len(groups) == 1
    assert [w["text"] for w in groups[0]["words"]] == ["ola", "mundo"]


# ---------------------------------------------------------------------------
# place_letterings
# ---------------------------------------------------------------------------

ROTEIRO_1_LETT = (
    "Ninguem te contou isso ainda\n"
    "[LEAD: ROTINA MATINAL]\n"
    "[KEY: o cafe some]\n"
    "mas seu dia *muda* completamente.\n"
)

# palavras faladas (sem os marcadores): Ninguem te contou isso ainda mas seu
# dia *muda* completamente. -> indice 5 ("mas") e a proxima falada apos o
# marcador LEAD/KEY.
WORDS_1_LETT = [
    _w("Ninguem", 0.0, 0.4),
    _w("te", 0.4, 0.6),
    _w("contou", 0.6, 1.0),
    _w("isso", 1.0, 1.3),
    _w("ainda", 1.3, 1.7),
    _w("mas", 1.7, 1.9),
    _w("seu", 1.9, 2.1),
    _w("dia", 2.1, 2.4),
    _w("muda", 2.4, 2.8, kw=True),
    _w("completamente.", 2.8, 3.3),
]


def test_place_letterings_basic():
    result = build_timeline.place_letterings(ROTEIRO_1_LETT, WORDS_1_LETT)

    assert len(result) == 1
    lett = result[0]
    assert lett["id"] == "lettA"
    assert lett["lead"] == "ROTINA MATINAL"
    assert lett["key"] == "o cafe some"
    assert lett["start"] == 1.7  # timestamp de "mas", primeira palavra apos o marcador
    assert lett["dur"] == build_timeline.DEFAULT_LETT_DUR


def test_place_letterings_custom_duration():
    roteiro = (
        "Ninguem te contou isso ainda\n"
        "[LEAD: ROTINA MATINAL]\n"
        "[KEY: o cafe some]\n"
        "[DUR: 3.2]\n"
        "mas seu dia muda completamente.\n"
    )

    result = build_timeline.place_letterings(roteiro, WORDS_1_LETT)

    assert result[0]["dur"] == 3.2


def test_place_letterings_multiple_sequential_ids():
    roteiro = (
        "voce usa so\n"
        "[LEAD: voce usa so]\n"
        "[KEY: 1%]\n"
        "da capacidade dessa ferramenta e perdendo uma\n"
        "[LEAD: colocar o claude pra]\n"
        "[KEY: trabalhar por voce]\n"
        "oportunidade de ouro\n"
    )
    words = [
        _w("voce", 28.72, 28.88),
        _w("usa", 28.88, 29.04),
        _w("so", 29.04, 29.2),
        _w("da", 29.2, 29.4),
        _w("capacidade", 29.4, 29.8),
        _w("dessa", 29.8, 30.0),
        _w("ferramenta", 30.0, 30.4),
        _w("e", 30.4, 30.5),
        _w("perdendo", 30.5, 30.9),
        _w("uma", 30.9, 31.0),
        _w("oportunidade", 31.0, 31.5),
        _w("de", 31.5, 31.6),
        _w("ouro", 31.6, 31.9),
    ]

    result = build_timeline.place_letterings(roteiro, words)

    assert [lett["id"] for lett in result] == ["lettA", "lettB"]
    assert result[0]["start"] == 29.2  # "da", primeira palavra apos 1o par LEAD/KEY
    assert result[1]["start"] == 31.0  # "oportunidade", apos 2o par LEAD/KEY


def test_place_letterings_marker_at_end_uses_last_word_end():
    roteiro = (
        "isso muda tudo\n"
        "[LEAD: fim de papo]\n"
        "[KEY: e so comecar]\n"
    )
    words = [
        _w("isso", 0.0, 0.3),
        _w("muda", 0.3, 0.6),
        _w("tudo", 0.6, 1.0),
    ]

    result = build_timeline.place_letterings(roteiro, words)

    assert result[0]["start"] == 1.0  # sem palavra depois: usa o fim da ultima


# ---------------------------------------------------------------------------
# build (integracao)
# ---------------------------------------------------------------------------

ROTEIRO_BUILD = (
    "Ninguem te contou isso ainda\n"
    "[LEAD: ROTINA MATINAL]\n"
    "[KEY: o cafe some]\n"
    "mas seu dia *muda* completamente.\n"
)

# transcript mock: mesma contagem de palavras faladas do roteiro acima
# (10 palavras), com uma grafia errada ("Ningen") pra provar que o HTML
# final usa o texto do roteiro, nao o do transcript.
TRANSCRIPT_MOCK = [
    {"text": "Ningen", "start": 0.0, "end": 0.4},
    {"text": "te", "start": 0.4, "end": 0.6},
    {"text": "contou", "start": 0.6, "end": 1.0},
    {"text": "isso", "start": 1.0, "end": 1.3},
    {"text": "ainda", "start": 1.3, "end": 1.7},
    {"text": "mas", "start": 1.7, "end": 1.9},
    {"text": "seu", "start": 1.9, "end": 2.1},
    {"text": "dia", "start": 2.1, "end": 2.4},
    {"text": "muda", "start": 2.4, "end": 2.8},
    {"text": "completamente", "start": 2.8, "end": 3.3},
]

TEMPLATE_HTML = """<!doctype html>
<html><body>
<div id="root">
<!-- INJECT:captions -->
<!-- INJECT:letterings -->
<!-- INJECT:preset:grade -->
</div>
</body></html>
"""

BRIEF = {"format": "reel-editorial", "styles": {"grade": "quente"}}


def test_build_integration(tmp_path, monkeypatch):
    roteiro_path = tmp_path / "roteiro.txt"
    roteiro_path.write_text(ROTEIRO_BUILD, encoding="utf-8")
    template_path = tmp_path / "index.html"
    template_path.write_text(TEMPLATE_HTML, encoding="utf-8")
    voz_path = tmp_path / "voz.mp3"
    voz_path.write_bytes(b"")  # nao usado de verdade: get_transcript e mockado

    monkeypatch.setattr(build_timeline, "get_transcript", lambda voz: TRANSCRIPT_MOCK)

    html = build_timeline.build(str(roteiro_path), str(voz_path), str(template_path), BRIEF)

    # nenhum marcador de injecao deve sobrar
    assert "INJECT:captions" not in html
    assert "INJECT:letterings" not in html
    assert "INJECT:preset:grade" not in html

    # legenda usa a grafia do roteiro (Ninguem, com acento certo), nunca a
    # grafia errada do transcript ("Ningen").
    assert "Ninguem" in html
    assert "Ningen" not in html

    # palavra-chave marcada com asterisco vira span com classe "kw", sem asteriscos
    assert 'class="cw kw"' in html
    assert "*muda*" not in html
    assert ">muda<" in html

    # lettering: id sequencial, lead e key do roteiro
    assert 'id="lettA"' in html
    assert "ROTINA MATINAL" in html
    assert "o cafe some" in html


def test_build_returns_string(tmp_path, monkeypatch):
    roteiro_path = tmp_path / "roteiro.txt"
    roteiro_path.write_text("ola mundo\n", encoding="utf-8")
    template_path = tmp_path / "index.html"
    template_path.write_text(TEMPLATE_HTML, encoding="utf-8")
    voz_path = tmp_path / "voz.mp3"
    voz_path.write_bytes(b"")

    mock_transcript = [
        {"text": "ola", "start": 0.0, "end": 0.3},
        {"text": "mundo", "start": 0.3, "end": 0.6},
    ]
    monkeypatch.setattr(build_timeline, "get_transcript", lambda voz: mock_transcript)

    html = build_timeline.build(str(roteiro_path), str(voz_path), str(template_path), {})

    assert isinstance(html, str)
    assert "ola" in html and "mundo" in html


def test_get_transcript_is_a_documented_stub():
    """get_transcript ainda nao integra com o HyperFrames: deve levantar erro claro."""
    import pytest

    with pytest.raises(NotImplementedError):
        build_timeline.get_transcript("qualquer_voz.mp3")
