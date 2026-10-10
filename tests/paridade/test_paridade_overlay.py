"""Paridade do OVERLAY (W0.3): o gen_ad_v2 sobre a fixture tem que dar o que o golden guardou.

A W2.A quebra `gen_ad_v2.py` em 14 módulos. Estes testes dizem se o resultado ainda é o
mesmo: sha256 do `index.html` e do `index_overlay.html` (o que o `strip_overlay` do
build_composite faz do primeiro), da `prancha.json`, das `janelas_split.json` e o argv de
todo subprocess do overlay. Três rodadas:

  overlay/             1a rodada de um anúncio novo (a footage ainda não existe)
  overlay_1x1/         o mesmo no template quadrado
  overlay_convergido/  2a rodada: o overlay lê o `_ritmo.json` que a footage deixou
                       (o "relógio da footage"; a W3.A troca isso de propósito e rebaseia)

O golden mora em $VAM_PARIDADE_GOLDEN (padrão $VAM_PARIDADE_MIDIA/golden) e nasce do commit base.
Fora do repo. Sem a variável da mídia, tudo aqui pula dizendo por quê.

W3.A (relógio único): `overlay/` e `overlay_1x1/` agora leem a timeline.json (uma transcrição só, o relógio
da footage): o golden deles muda DE PROPÓSITO, só em tempo. `overlay_convergido/` continua no caminho antigo
(sem timeline, lendo o `_ritmo.json` da footage) e prova que ele segue funcionando até a W5.A.

Não coberto (ver fixture/MANIFESTO.json): o render MOV do `hyperframes render` (sem
Chromium aqui); o `hyperframes transcribe` real (um stub devolve a saída real gravada);
pip, imagem estática, insert vertical, fala deitica e dur_max.
"""
import json
import re

import pytest

from tests.paridade import capturar as C

pytestmark = pytest.mark.midia_real


@pytest.fixture(scope="module")
def midia():
    return C.exigir_midia()


@pytest.fixture(scope="module")
def golden(midia):
    arquivos, _hashes, _manifesto = C.ler_golden(midia)
    return arquivos


@pytest.fixture(scope="module")
def atual(midia):
    """A captura do motor DESTE working tree (uma vez só; a footage divide o mesmo run)."""
    return C.capturar_memo(C.raiz_do_repo(), midia).arquivos


def _confere(atual, golden, prefixos):
    diffs = C.comparar(atual, golden, prefixos=prefixos)
    assert not diffs, "paridade do overlay quebrada:\n" + "\n\n".join(diffs)


# --- a fixture em si ----------------------------------------------------------------------

def test_fixture_intacta(midia):
    """sha256 de cada arquivo da fixture contra o MANIFESTO: mídia trocada vira erro claro."""
    C.conferir_fixture(midia)


def _blocos(texto):
    """[(instrução, fala)] de um roteiro em `[instrução] fala` por linha."""
    saida = []
    for linha in texto.splitlines():
        m = re.match(r"\[(.+?)\]\s*(.*)$", linha.strip())
        if m:
            saida.append((m.group(1), m.group(2).strip()))
    return saida


def _marcador(instrucao, nome):
    m = re.search(rf"{nome}:\s*([^|]+)", instrucao)
    return m.group(1).strip() if m else None


def test_as_duas_representacoes_dizem_o_mesmo(midia):
    """antigo/ (leva + config) e novo/ (roteiro.md + projeto.json) são o MESMO conteúdo.

    A W1.B vai exigir que `para_motor` gere o antigo a partir do novo; se as duas
    divergirem aqui, a exigência dela seria impossível.
    """
    fx = midia / "fixture"
    antigo = _blocos((fx / "antigo" / "ad99v2_leva.txt").read_text(encoding="utf-8"))
    novo = _blocos((fx / "novo" / "roteiro.md").read_text(encoding="utf-8"))
    assert len(antigo) == len(novo) == 5
    for i, ((ia, fa), (inov, fn)) in enumerate(zip(antigo, novo)):
        assert fa == fn, f"bloco {i}: a fala difere entre as duas representações"
        assert _marcador(ia, "LEAD") == _marcador(inov, "LEAD"), f"bloco {i}: LEAD"
        assert _marcador(ia, "KEY") == _marcador(inov, "KEY"), f"bloco {i}: KEY"
        assert ("logo" in ia.lower()) == ("logo" in inov.lower()), f"bloco {i}: logo"

    cfg = json.loads((fx / "antigo" / "ad99v2_look_a.json").read_text(encoding="utf-8"))
    proj = json.loads((fx / "novo" / "projeto.json").read_text(encoding="utf-8"))
    assert cfg["hook"] == {"eyebrow": proj["hook"]["eyebrow"], "l1": proj["hook"]["linha"],
                           "accent": proj["hook"]["destaque"]}
    assert cfg["cta_label"] == proj["cta"]["rotulo"]
    assert cfg["kw_phrases"] == proj["palavras_chave"]
    assert len(cfg["letterings"]) == len(proj["letterings"])
    for a, n in zip(cfg["letterings"], proj["letterings"]):
        palavra, nth = n["ancora"].split("#")
        assert (a["lead"], a["key"], a["anchor"], a["nth"], a["dur"], a.get("pilha")) == \
               (n["lead"], n["key"], palavra, int(nth), n["dur"], n.get("pilha"))

    ins = json.loads((fx / "antigo" / "ad99v2_inserts.json").read_text(encoding="utf-8"))
    assert sorted(ins) == sorted(proj["inserts"])
    for chave, a in ins.items():
        n = proj["inserts"][chave]
        assert a["file"].endswith("/" + n["arquivo"])
        assert (a["start"], a["speed"], bool(a.get("split"))) == \
               (n["inicio"], n["velocidade"], n.get("layout") == "split")


def test_a_fixture_exercita_os_ramos_do_overlay(atual):
    """Se alguém afinar a fixture, estes ramos não podem sumir sem ninguém notar."""
    prancha = json.loads(atual["overlay/prancha.json"])
    assert prancha["blocos"][0]["tipo"] == "insert", "abertura em insert (hook sobre o insert)"
    assert any(l["pilha"] for l in prancha["letterings"]), "ramo da pilha"
    assert any(l["split"] for l in prancha["letterings"]), "lettering dentro de tela dividida"
    assert json.loads(atual["overlay/janelas_split.json"])["segs"], "há janela de split"
    assert '<img class="lett-logo"' in atual["overlay/index.html"], "logo dentro do lettering"
    assert atual["overlay/index_overlay.html"] != atual["overlay/index.html"], "o strip fez algo"
    assert atual["overlay_convergido/index.html"] != atual["overlay/index.html"], \
        "a 2a rodada não leu a footage (o relógio da footage não foi exercitado)"
    if "timeline/timeline.json" in atual:
        assert '"<HF>", "transcribe"' not in atual["argv/overlay.jsonl"], "com timeline o overlay não transcreve"
        assert '"<HF>", "transcribe"' in atual["argv/overlay_convergido.jsonl"], "o caminho antigo ainda transcreve"


# --- a paridade --------------------------------------------------------------------------

def test_index_html_e_index_overlay_html(atual, golden):
    _confere(atual, golden, ("overlay/index.html", "overlay/index_overlay.html"))


def test_prancha_e_janelas_de_split(atual, golden):
    _confere(atual, golden, ("overlay/prancha.json", "overlay/janelas_split.json"))


def test_overlay_1x1(atual, golden):
    _confere(atual, golden, ("overlay_1x1/",))


def test_overlay_convergido_com_o_relogio_da_footage(atual, golden):
    _confere(atual, golden, ("overlay_convergido/",))


def test_argv_do_overlay_na_mesma_ordem(atual, golden):
    _confere(atual, golden, ("argv/overlay.jsonl", "argv/overlay_1x1.jsonl", "argv/overlay_convergido.jsonl"))


def test_overlay_e_deterministico_entre_sandboxes(midia):
    """Dois sandboxes novos dão a MESMA captura: caminho e nome de tempdir não vazam."""
    a = C.capturar(C.raiz_do_repo(), midia, etapas=("overlay",))
    b = C.capturar(C.raiz_do_repo(), midia, etapas=("overlay",))
    assert a.hashes() == b.hashes()


def test_o_golden_vem_de_vam_paridade_golden_quando_definida(tmp_path, monkeypatch):
    """O rebase da W3.A nasce em outra pasta e só vira o golden padrão depois da revisão do diff."""
    monkeypatch.delenv("VAM_PARIDADE_GOLDEN", raising=False)
    assert C.pasta_golden(tmp_path) == tmp_path / "golden"
    monkeypatch.setenv("VAM_PARIDADE_GOLDEN", str(tmp_path / "golden-w3a"))
    assert C.pasta_golden(tmp_path) == tmp_path / "golden-w3a"


def test_timeline_e_alinhamento_da_fixture(atual, golden):
    """W3.A: a timeline.json e o alinhamento único do fixture, e o argv da fase (uma transcrição só)."""
    _confere(atual, golden, ("timeline/timeline.json", "timeline/alinhamento.json", "argv/timeline.jsonl"))
