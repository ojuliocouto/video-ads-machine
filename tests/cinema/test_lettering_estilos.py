"""W4.D: os 8 estilos de lettering (capacidade C7) como DADOS, CSS determinístico e faixas exportadas.

`cinema.lettering_estilos` é a fonte única: cada estilo tem a sua especificação (fonte, corpo, recuos, linhas,
entrada) e dela saem o CSS do parcial (`templates/_parciais/lettering_<estilo>.css`, gerado, nunca editado à mão)
e a FAIXA (x0, x1, y0, y1 no quadro 1080x1920) que o `gate_safezone` confere ANTES do render.

O `serif_editorial` é o lettering que já existia (a classe `.lett` sem modificador): o HTML dele não muda, e é isso
que mantém a paridade do overlay. Os outros sete entram por uma classe `lett-<estilo>`.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from cinema import lettering_estilos as E
from overlay import letterings as LT

RAIZ = Path(__file__).resolve().parents[2]
PARCIAIS = RAIZ / "templates" / "_parciais"
TIMELINE_VALIDA = RAIZ / "contratos" / "exemplos" / "timeline.valido.json"


def _lett(**kw):
    base = {"id": "lettA", "lead": "o problema não é", "key": "FALTA DE TEMPO", "start": 3.0, "dur": 2.2,
            "split": False, "logo": False, "baixo": False, "pilha": None}
    base.update(kw)
    return base


# --- os nomes ------------------------------------------------------------------------------------

def test_os_estilos_sao_os_do_contrato_da_timeline():
    schema = json.loads((RAIZ / "contratos" / "timeline.schema.json").read_text(encoding="utf-8"))
    enum = schema["properties"]["letterings"]["items"]["properties"]["estilo"]["enum"]
    assert list(E.ESTILOS) == enum
    assert E.PADRAO == "serif_editorial"


def test_tres_colorways_da_caixa_nativa_nunca_um_quarto():
    assert set(E.COLORWAYS) == {"ambar", "branco", "preto"}
    assert E.COLORWAYS["ambar"]["fundo"].lower() == "#fec64d"


# --- CSS determinístico --------------------------------------------------------------------------

@pytest.mark.parametrize("estilo", E.ESTILOS)
def test_css_de_cada_estilo_e_deterministico_e_e_o_parcial(estilo):
    a, b = E.css(estilo), E.css(estilo)
    assert a == b and a.strip()
    assert (PARCIAIS / ("lettering_%s.css" % estilo)).read_text(encoding="utf-8") == a


@pytest.mark.parametrize("estilo", [e for e in E.ESTILOS if e != "serif_editorial"])
def test_css_do_estilo_novo_so_mexe_na_propria_classe(estilo):
    # nenhuma regra solta: tudo debaixo de .lett.lett-<estilo> (o estilo novo não pode mudar o editorial)
    css = re.sub(r"/\*.*?\*/", "", E.css(estilo), flags=re.S)
    for bloco in re.findall(r"([^{}]+)\{", css):
        for seletor in bloco.split(","):
            assert seletor.strip().startswith(".lett.lett-%s" % estilo), seletor


def test_escrever_parciais_gera_os_8_arquivos(tmp_path):
    E.escrever_parciais(tmp_path)
    for e in E.ESTILOS:
        assert (tmp_path / ("lettering_%s.css" % e)).read_text(encoding="utf-8") == E.css(e)


def test_os_templates_incluem_os_8_parciais_de_lettering():
    for pasta in ("reel-editorial", "reel-editorial-1x1"):
        bruto = (RAIZ / "templates" / pasta / "index.html").read_text(encoding="utf-8")
        for e in E.ESTILOS:
            assert "/* PARCIAL:lettering_%s.css */" % e in bruto, (pasta, e)


# --- faixas --------------------------------------------------------------------------------------

def test_faixas_de_todo_estilo_dentro_da_zona_segura():
    assert E.LIMITE_X == 940 and E.LIMITE_Y == 1690
    for nome, f in E.FAIXAS.items():
        assert 0 <= f["x0"] < f["x1"] <= E.LIMITE_X, nome
        assert 0 <= f["y0"] < f["y1"] <= E.LIMITE_Y, nome


def test_faixas_cobrem_estilos_cta_e_hook():
    for e in E.ESTILOS:
        assert e in E.FAIXAS
    for extra in ("serif_editorial_split", "serif_editorial_pilha", "cta", "cta_split", "hook", "hook_punch"):
        assert extra in E.FAIXAS


def test_limites_iguais_aos_do_gate_safezone():
    from gates import gate_safezone as SZ
    assert (E.LIMITE_X, E.LIMITE_Y) == (SZ.LIMITE_X, SZ.LIMITE_Y)


def test_faixas_extra_da_timeline_passam_no_gate_safezone():
    from gates import gate_safezone as SZ
    tl = json.loads(TIMELINE_VALIDA.read_text(encoding="utf-8"))
    extra = E.faixas_extra(tl)
    elementos = {f["elemento"] for f in extra}
    assert {"lettering", "cta", "hook"} <= elementos
    assert all(f["s"] < f["e"] for f in extra)
    g = SZ.rodar_antes(tl, faixas_extra=extra)
    assert g["resultado"] == "PASS", g.get("motivo")


def test_faixa_adulterada_reprova_no_gate_safezone(monkeypatch):
    from gates import gate_safezone as SZ
    tl = json.loads(TIMELINE_VALIDA.read_text(encoding="utf-8"))
    monkeypatch.setitem(E.FAIXAS, "caixa_nativa", dict(E.FAIXAS["caixa_nativa"], y1=1700))
    g = SZ.rodar_antes(tl, faixas_extra=E.faixas_extra(tl))
    assert g["resultado"] == "REPROVA" and g["saida"] == 1


def test_faixa_de_um_lettering_em_split_e_a_do_editorial_em_split():
    assert E.faixa("punch", split=True) == E.FAIXAS["serif_editorial_split"]
    assert E.faixa("serif_editorial", pilha=True) == E.FAIXAS["serif_editorial_pilha"]
    assert E.faixa("punch") == E.FAIXAS["punch"]


# --- regras de uso -------------------------------------------------------------------------------

def test_estilo_efetivo():
    assert E.efetivo(None, False) == "serif_editorial"
    assert E.efetivo("punch", False) == "punch"
    assert E.efetivo("punch", True) == "serif_editorial"          # split mora na costura: só o editorial cabe
    with pytest.raises(ValueError, match="estilo desconhecido"):
        E.efetivo("neon", False)


def test_linhas_estimadas():
    assert E.linhas_estimadas("FALTA DE TEMPO", "caixa_nativa") <= 2
    assert E.linhas_estimadas("O MELHOR", "serif_editorial") == 1
    longa = "ISSO AQUI É UMA FRASE LONGA DEMAIS PARA UM LETTERING DE PICO NA TELA"
    for e in E.ESTILOS:
        assert E.linhas_estimadas(longa, e) > 2, e
    assert E.linhas_estimadas("UMA\nDUAS\nTRES", "punch") == 3


# --- o HTML do lettering (overlay.letterings.html) -----------------------------------------------

def test_html_do_editorial_nao_muda():
    # sem estilo e com serif_editorial: o mesmo HTML de antes (paridade do overlay)
    sem = LT.html([_lett()])
    com = LT.html([_lett(estilo="serif_editorial")])
    assert sem == com
    assert sem == ('<div class="lett clip" id="lettA" data-start="3.0" data-duration="2.2" data-track-index="32">\n'
                   '  <div class="lead">o problema não é</div>\n'
                   '  <div class="key">FALTA DE TEMPO</div>\n</div>')


@pytest.mark.parametrize("estilo", [e for e in E.ESTILOS if e != "serif_editorial"])
def test_html_do_estilo_novo_leva_a_classe(estilo):
    h = LT.html([_lett(estilo=estilo)])
    assert 'class="lett clip lett-%s' % estilo in h


def test_caixa_nativa_leva_o_colorway_ambar_por_padrao():
    assert "cor-ambar" in LT.html([_lett(estilo="caixa_nativa")])
    assert "cor-preto" in LT.html([_lett(estilo="caixa_nativa", cor="preto")])
    with pytest.raises(ValueError, match="colorway"):
        LT.html([_lett(estilo="caixa_nativa", cor="verde")])


def test_marcador_vira_span_hi():
    h = LT.html([_lett(estilo="marcador", key="*20 HORAS* POR SEMANA")])
    assert '<span class="hi">20 HORAS</span> POR SEMANA' in h
    assert "*" not in h


def test_estilo_novo_tira_o_asterisco_de_enfase_sem_marcador():
    h = LT.html([_lett(estilo="punch", key="TRES *HORAS*")])
    assert "*" not in h and "TRES HORAS" in h


def test_seta_cta_leva_a_seta():
    assert '<div class="seta"></div>' in LT.html([_lett(estilo="seta_cta", key="SAIBA MAIS")])


def test_estilo_novo_em_split_cai_no_editorial():
    h = LT.html([_lett(estilo="punch", split=True)])
    assert "lett-punch" not in h and "lett-split" in h


def test_key_longa_so_no_editorial():
    k = "UMA CHAVE BEM LONGA AQUI"
    assert "key-longa" in LT.html([_lett(key=k)])
    assert "key-longa" not in LT.html([_lett(key=k, estilo="punch")])


def test_calcular_leva_estilo_e_cor_do_config():
    words = [{"text": "falta", "start": 1.0, "end": 1.3}]
    blocks = [{"instr": "apresentador", "type": "orig"}]
    cfg = [{"lead": "a", "key": "B", "anchor": "falta", "estilo": "caixa_nativa", "cor": "branco"}]
    letts = LT.calcular(cfg, words, [(0.0, 5.0)], blocks, [])
    assert letts[0]["estilo"] == "caixa_nativa" and letts[0]["cor"] == "branco"
    letts = LT.calcular([{"lead": "a", "key": "B", "anchor": "falta"}], words, [(0.0, 5.0)], blocks, [])
    assert "estilo" not in letts[0]          # o config antigo continua gerando o mesmo dicionário


# --- render: a KEY é legível em até 0,15 s ---------------------------------------------------------

def _hyperframes():
    c = RAIZ / "node_modules" / ".bin" / "hyperframes"
    if c.exists():
        return str(c)
    pytest.skip("hyperframes ausente em node_modules/.bin (rode bash setup.sh)")


@pytest.mark.lento
def test_key_legivel_em_015s_e_dentro_da_faixa(tmp_path):
    """Para cada estilo, no modo de medida do mostruário (fundo preto, sem guia nem rótulo): a tinta em +0,15 s da
    entrada é pelo menos 90% da tinta assentada (+0,60 s), e a tinta inteira fica dentro da FAIXA do estilo."""
    from cinema import mostruario_lettering as M
    hf = _hyperframes()
    medidas = M.medir_legibilidade(tmp_path, hf)
    assert [m["estilo"] for m in medidas] == list(E.ESTILOS)
    for m in medidas:
        assert m["tinta_assentada_px"] > 500, m
        assert m["fracao_015"] >= E.ALFA_LEGIVEL, m
        f = E.FAIXAS[m["estilo"]]
        x0, y0, x1, y1 = m["caixa_tinta"]
        assert f["x0"] - 4 <= x0 and x1 <= f["x1"] + 4, m
        assert f["y0"] - 4 <= y0 and y1 <= f["y1"] + 4, m
