"""W3.D: gate_geometria. A geometria se verifica no PLANO antes de renderizar (custou 5 versões do AD4, 18/09).

O texto de tela nunca pode cair no rosto do apresentador. Onde cada legenda pousa depende do layout daquele
instante (avatar cheio, tela dividida, insert), e as faixas são as de `overlay.layout_texto` (FONTE ÚNICA: este
gate importa e lê na hora da chamada, nunca copia). Duas etapas, dois nomes de laudo:

  antes   `gate_geometria`          sobre a timeline: a faixa de cada legenda contra o núcleo do rosto, os tempos
                                    contra a fronteira do split e a faixa livre abaixo do queixo. Sem render.
  depois  `gate_geometria_depois`   sobre o render: a tinta REAL do overlay (alfa) contra o rosto, em 6 instantes
                                    espaçados. Complementa o `gate-colisao-texto` (que amostra o vídeo todo a cada
                                    1,5 s): usa os mesmos limiares e a mesma definição de núcleo e de tinta, e
                                    acrescenta a geometria do plano quando o detector fica cego em tela dividida.

Os testes rápidos injetam o detector de rosto e desenham o overlay com PIL (sem ffmpeg, sem mídia). O `lento`
usa um .mov com alfa de verdade; o `lento` + `midia_real` usa o avatar real da fixture da paridade (Haar de
verdade), e só roda com VAM_PARIDADE_MIDIA.

Mutantes que TÊM que reprovar: legenda deslocada pro rosto, legenda padrão em look fechado, costura no avatar
cheio, tinta sobre o rosto no render.
Resultado no formato do laudo: `acao` e `avisos` moram dentro de `medido` (o schema do laudo proíbe chave
extra no gate).
"""
import contextlib
import hashlib
import io
import json
import os
import re
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from contratos import validar
from footage import filtros_avatar as FA
from gates import gate_geometria
from overlay import layout_texto as OL

RAIZ = Path(__file__).resolve().parents[2]
LAUDO_VALIDO = RAIZ / "contratos" / "exemplos" / "laudo.valido.json"
TIMELINE_VALIDA = RAIZ / "contratos" / "exemplos" / "timeline.valido.json"
GATE_COLISAO = RAIZ / "scripts" / "gates" / "gate-colisao-texto.py"

LARGURA, ALTURA = 1080, 1920

ROSTO_ABERTO = (300, 500)         # (topo, altura) no avatar: queixo em y 800 (41,7% da altura), folga de sobra
ROSTO_FECHADO = (900, 500)        # queixo em y 1400 (72,9%): acima de 60%, não sobra peito para a legenda padrão
ROSTO_SPLIT = (1258, 1832)        # o rosto no painel de baixo do split, em y de tela (plano, W3.D)


# =================================================================================== insumos sintéticos

def leg(s, e, posicao, suprimida=False):
    return {"s": s, "e": e, "texto": "uma legenda", "posicao": posicao, "suprimida": suprimida,
            "palavras": [{"t": "uma", "s": s, "e": round((s + e) / 2, 3)},
                         {"t": "legenda", "s": round((s + e) / 2, 3), "e": e}]}


def timeline(legendas, aceleracao=1.0, a0=0.0, letterings=()):
    """Avatar 0-6, split 6-10, avatar 10-12, insert cheio 12-14, avatar 14-16 (CTA a partir de 15)."""
    segs = [{"bloco": 0, "tipo": "apresentador", "s": 0.0, "e": 6.0, "sub": 0, "de": 1},
            {"bloco": 1, "tipo": "insert", "s": 6.0, "e": 10.0, "sub": 0, "de": 1, "layout": "split"},
            {"bloco": 2, "tipo": "apresentador", "s": 10.0, "e": 12.0, "sub": 0, "de": 1},
            {"bloco": 3, "tipo": "insert", "s": 12.0, "e": 14.0, "sub": 0, "de": 1, "layout": "cheio"},
            {"bloco": 4, "tipo": "apresentador", "s": 14.0, "e": 16.0, "sub": 0, "de": 1}]
    return {"versao": 1, "projeto": "geo", "formato": "9x16", "duracao_s": 16.0,
            "relogio": {"base": "footage_1x", "fps": 30, "aceleracao": aceleracao, "cauda_s": 0.0, "a0": a0},
            "segmentos": segs, "janelas_split": [{"s": 6.0, "e": 10.0}],
            "legendas": list(legendas), "letterings": list(letterings),
            "hook": {"s": 0.0, "e": 0.9, "eyebrow": "A", "linha": "B", "destaque": "C", "estilo": "editorial"},
            "cta": {"inicio": 15.0, "logo": 15.2, "label": "saiba mais", "sem_lead": False}}


def antes(tl, **kw):
    kw.setdefault("rosto", ROSTO_ABERTO)
    kw.setdefault("rosto_split", ROSTO_SPLIT)
    return gate_geometria.rodar_antes(tl, **kw)


def formato_do_laudo(g):
    """Os erros do contrato que dizem respeito a este gate (o resto do laudo não é assunto daqui)."""
    laudo = json.loads(LAUDO_VALIDO.read_text(encoding="utf-8"))
    laudo["gates"] = [x for x in laudo["gates"] if x["nome"] != g["nome"]] + [g]
    k = len(laudo["gates"]) - 1
    return [e for e in validar.validar("laudo", laudo) if ("gates[%d]" % k) in e.caminho]


# =================================================================================== constantes e origem

def test_as_faixas_e_o_look_fechado_sao_os_do_layout_texto():
    assert gate_geometria.OL is OL                                   # o módulo, não uma cópia dos números
    assert gate_geometria.FA is FA
    assert gate_geometria.ALTURA_LEGENDA_PX == 196


def test_o_nucleo_e_os_limiares_sao_os_do_gate_de_colisao_que_ja_existe():
    """O nome do gate existente tem hífen (não importa): lê-se o texto dele, para as constantes não derivarem."""
    src = GATE_COLISAO.read_text(encoding="utf-8")
    achar = lambda padrao: [float(x) for x in re.findall(padrao, src)]
    assert achar(r"(?m)^INSET_NUCLEO = ([0-9.]+)") == [gate_geometria.INSET_NUCLEO]
    assert achar(r"(?m)^LIMIAR_COLISAO_PADRAO = ([0-9.]+)") == [gate_geometria.LIMIAR_COLISAO_PCT]
    assert achar(r"(?m)^LIMIAR_ALPHA_OVERLAY = ([0-9.]+)") == [gate_geometria.TINTA_ALFA_ROSTO]
    assert achar(r"(?m)^LIMIAR_LUM_TINTA = ([0-9.]+)") == [gate_geometria.TINTA_LUM_ROSTO]
    assert set(achar(r"fh = int\(fh \* ([0-9.]+)\)")) == {gate_geometria.FRACAO_ALTURA_NUCLEO}
    assert achar(r"(?m)^PELE_MIN_HERANCA = ([0-9.]+)") == [gate_geometria.PELE_MIN]
    assert gate_geometria.LIMIAR_COLISAO_PCT == 1.5


def test_a_altura_da_legenda_cabe_duas_linhas_da_fonte_de_80px():
    """196 px: o piso da faixa livre (plano, W3.D). Tem que acomodar a legenda de 2 linhas (80 px x 1,14)."""
    assert gate_geometria.ALTURA_LEGENDA_PX >= 2 * 80 * 1.14


def test_o_nucleo_e_a_caixa_do_rosto_sem_o_inset_e_sem_o_queixo():
    # 574 px de caixa: inset de 12% (68 px) em cima e embaixo, e 78% do que sobra (438 px) = 341 px
    assert gate_geometria.nucleo_y(1258, 574) == (1326, 1667)


def test_intersecao_em_pixels():
    assert gate_geometria.intersecao_px((100, 200), (150, 400)) == 50
    assert gate_geometria.intersecao_px((100, 200), (200, 400)) == 0
    assert gate_geometria.intersecao_px((100, 200), (300, 400)) == 0


# =================================================================================== antes: rosto x costura

def test_rosto_em_y_1258_a_1832_com_legenda_na_costura_da_intersecao_zero():
    nucleo = gate_geometria.nucleo_y(1258, 1832 - 1258)
    assert gate_geometria.intersecao_px((967, 1106), nucleo) == 0                  # a tinta da costura, medida
    assert gate_geometria.intersecao_px(OL.FAIXA_LEGENDA["costura"], nucleo) == 0  # e a faixa do layout_texto
    g = antes(timeline([leg(7.0, 8.5, "costura")]))
    assert g["nome"] == "gate_geometria" and g["etapa"] == "antes"
    assert g["resultado"] == "PASS" and g["saida"] == 0, g.get("motivo")
    assert formato_do_laudo(g) == []
    m = g["medido"]
    assert m["legendas"]["verificadas"] == 1 and m["legendas"]["com_problema"] == []
    assert m["rosto_split"]["y0"] == 1258 and m["rosto_split"]["y1"] == 1832
    assert m["rosto_split"]["nucleo_y0"] == 1326 and m["rosto_split"]["nucleo_y1"] == 1667
    assert "acao" not in m


def test_o_rosto_do_avatar_vira_o_rosto_do_painel_pelo_mesmo_corte_do_motor():
    """avatar (688, 574) com bias 0,3: corte de 480 px no avatar já reduzido ao painel, painel começa em 1150."""
    assert FA.SPLIT_TOP_H == 1150
    assert FA.corte_y_split(0.3, FA.altura_util_split()) == 480
    assert gate_geometria.rosto_no_split(688, 574, 0.3) == (1258, 1832)
    g = gate_geometria.rodar_antes(timeline([leg(7.0, 8.5, "costura")]), rosto=(688, 574), bias=0.3)
    assert g["resultado"] == "PASS", g.get("motivo")
    assert g["medido"]["rosto_split"]["y0"] == 1258 and g["medido"]["rosto_split"]["y1"] == 1832
    assert g["medido"]["rosto_split"]["bias"] == 0.3


def test_o_rosto_no_split_respeita_o_limite_do_corte():
    """O corte não passa do que sobra da altura útil: bias 1,0 corta 830 px (1600 - 770), não 1600."""
    assert FA.corte_y_split(1.0, FA.altura_util_split()) == 830
    y0, y1 = gate_geometria.rosto_no_split(1000, 400, 1.0)
    assert y0 == 1150 + (1000 - 100) - 830 and y1 - y0 == 400


def test_mutante_legenda_deslocada_pro_rosto_reprova_com_a_intersecao_em_pixels():
    """A legenda padrão (y 1290 a 1500) no painel do apresentador cai no núcleo do rosto (1326 a 1667)."""
    g = antes(timeline([leg(7.0, 8.5, "padrao")]))
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert "costura" in g["motivo"] and "split" in g["motivo"]
    (p,) = g["medido"]["legendas"]["com_problema"]
    (f,) = p["fatias"]
    assert f["layout"] == "split" and f["intersecao_px"] == OL.FAIXA_LEGENDA["padrao"][1] - 1326
    assert formato_do_laudo(g) == []
    assert "acao" not in g["medido"]                         # aqui há conserto (mover para a costura), não supressão


def test_mutante_rodape_no_split_tambem_reprova():
    g = antes(timeline([leg(7.0, 8.5, "rodape")]))
    assert g["resultado"] == "REPROVA"
    (f,) = g["medido"]["legendas"]["com_problema"][0]["fatias"]
    assert f["intersecao_px"] == OL.FAIXA_LEGENDA["baixa"][1] - 1326


def test_costura_no_avatar_cheio_reprova():
    """No avatar cheio a costura (y 1000 a 1130) cai na boca dele: é a posição do split, não a do rosto livre."""
    g = antes(timeline([leg(1.0, 2.5, "costura")]))
    assert g["resultado"] == "REPROVA" and "costura" in g["motivo"] and "avatar cheio" in g["motivo"]


def test_as_faixas_sao_lidas_do_layout_texto_na_hora_da_chamada(monkeypatch):
    """Mutante: alguém desce a costura para cima do painel do apresentador. O gate tem que ver."""
    novo = dict(OL.FAIXA_LEGENDA)
    novo["costura"] = (1100, 1400)
    monkeypatch.setattr(OL, "FAIXA_LEGENDA", novo)
    g = antes(timeline([leg(7.0, 8.5, "costura")]))
    assert g["resultado"] == "REPROVA"
    (f,) = g["medido"]["legendas"]["com_problema"][0]["fatias"]
    assert f["intersecao_px"] == 1400 - 1326


def test_split_sem_bias_nem_rosto_do_painel_e_erro_de_insumo():
    g = gate_geometria.rodar_antes(timeline([leg(7.0, 8.5, "costura")]), rosto=ROSTO_ABERTO)
    assert g["resultado"] == "ERRO" and g["saida"] == 2 and "bias" in g["motivo"]


def test_sem_legenda_no_split_nao_precisa_do_bias():
    g = gate_geometria.rodar_antes(timeline([leg(1.0, 2.5, "padrao")]), rosto=ROSTO_ABERTO)
    assert g["resultado"] == "PASS" and g["medido"]["rosto_split"] is None


# =================================================================================== antes: look fechado

def test_legenda_padrao_em_look_fechado_reprova_e_o_motivo_indica_o_rodape():
    g = antes(timeline([leg(1.0, 2.5, "padrao")]), rosto=ROSTO_FECHADO)
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    a, b = OL.FAIXA_LEGENDA["baixa"]
    assert "rodapé" in g["motivo"] and "fechado" in g["motivo"] and str(a) in g["motivo"] and str(b) in g["motivo"]
    assert "73%" in g["motivo"] and "60%" in g["motivo"]                      # o queixo e o limite, em % da altura
    assert g["medido"]["rosto_avatar"]["fechado"] is True
    assert "acao" not in g["medido"]
    assert formato_do_laudo(g) == []


def test_o_mesmo_look_fechado_com_a_legenda_no_rodape_passa():
    g = antes(timeline([leg(1.0, 2.5, "rodape")]), rosto=ROSTO_FECHADO)
    assert g["resultado"] == "PASS", g.get("motivo")
    assert g["medido"]["rosto_avatar"]["fechado"] is True


def test_look_aberto_aceita_a_legenda_padrao():
    g = antes(timeline([leg(1.0, 2.5, "padrao")]), rosto=ROSTO_ABERTO)
    assert g["resultado"] == "PASS"
    assert g["medido"]["rosto_avatar"]["fechado"] is False
    assert g["medido"]["rosto_avatar"]["queixo_fracao"] == pytest.approx(800 / 1920, abs=1e-3)


def test_o_limite_do_look_fechado_e_o_do_layout_texto():
    """60% da altura: queixo em y 1152 ainda é aberto; 1153 já é fechado."""
    topo = 1152 - 500
    assert OL.QUEIXO_FECHADO == 0.60
    aberto = antes(timeline([leg(1.0, 2.5, "padrao")]), rosto=(topo, 500))
    fechado = antes(timeline([leg(1.0, 2.5, "padrao")]), rosto=(topo + 1, 500))
    assert aberto["resultado"] == "PASS" and fechado["resultado"] == "REPROVA"


# =================================================================================== antes: faixa livre

def test_faixa_livre_abaixo_de_196_px_declara_supressao_da_legenda_e_nao_levanta():
    """Queixo em y 1495: sobram 195 px até o teto da UI (1690), menos que a legenda de duas linhas."""
    tl = timeline([leg(1.0, 2.5, "rodape"), leg(3.0, 4.5, "rodape"), leg(7.0, 8.5, "costura")])
    g = antes(tl, rosto=(1000, 495))
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    m = g["medido"]
    assert m["acao"] == "suprimir_legenda"
    assert [x["indice"] for x in m["suprimir"]] == [0, 1]                    # a costura (split) tem onde ficar
    assert m["rosto_avatar"]["faixa_livre_px"] == 195
    assert "196" in g["motivo"] and "suprimir" in g["motivo"]
    assert formato_do_laudo(g) == []
    assert any("12%" in a for a in m["avisos"])                              # o vão de texto é do gate-ad


def test_o_piso_da_faixa_livre_e_196_exatos():
    ok = antes(timeline([leg(1.0, 2.5, "rodape")]), rosto=(1000, 494))       # sobram 196: cabe
    sem = antes(timeline([leg(1.0, 2.5, "rodape")]), rosto=(1000, 495))      # sobram 195: não cabe
    assert ok["resultado"] == "PASS" and "acao" not in ok["medido"]
    assert ok["medido"]["rosto_avatar"]["faixa_livre_px"] == 196
    assert sem["medido"]["acao"] == "suprimir_legenda"


def test_sem_faixa_livre_a_supressao_vale_tambem_para_a_legenda_padrao():
    """O conserto 'vá para o rodapé' não existe quando não cabe nada: a ação é suprimir, não mudar de posição."""
    g = antes(timeline([leg(1.0, 2.5, "padrao")]), rosto=(1000, 495))
    assert g["medido"]["acao"] == "suprimir_legenda"
    assert "rodapé" not in g["motivo"]


def test_aplicar_a_supressao_e_rodar_de_novo_passa():
    tl = timeline([leg(1.0, 2.5, "rodape"), leg(7.0, 8.5, "costura")])
    g = antes(tl, rosto=(1000, 495))
    tl2 = gate_geometria.aplicar_supressao(tl, g)
    assert [l["suprimida"] for l in tl2["legendas"]] == [True, False]
    assert [l["suprimida"] for l in tl["legendas"]] == [False, False]         # a original não mexe
    g2 = antes(tl2, rosto=(1000, 495))
    assert g2["resultado"] == "PASS" and g2["saida"] == 0 and "acao" not in g2["medido"]
    assert g2["medido"]["legendas"]["suprimidas"] == 1


def test_aplicar_a_supressao_sem_acao_devolve_a_mesma_timeline_copiada():
    tl = timeline([leg(1.0, 2.5, "padrao")])
    g = antes(tl)
    tl2 = gate_geometria.aplicar_supressao(tl, g)
    assert tl2 == tl and tl2 is not tl


# =================================================================================== antes: tempos

def test_legenda_que_atravessa_a_troca_de_layout_reprova_no_lado_errado():
    g = antes(timeline([leg(5.5, 6.5, "costura")]))              # 0,5 s no avatar cheio e 0,5 s no split
    assert g["resultado"] == "REPROVA"
    (p,) = g["medido"]["legendas"]["com_problema"]
    assert [f["layout"] for f in p["fatias"] if f["problemas"]] == ["cheio"]
    g = antes(timeline([leg(5.5, 6.5, "padrao")]))
    (p,) = g["medido"]["legendas"]["com_problema"]
    assert [f["layout"] for f in p["fatias"] if f["problemas"]] == ["split"]


def test_legenda_que_acaba_na_fronteira_nao_atravessa():
    assert antes(timeline([leg(4.0, 6.0, "padrao")]))["resultado"] == "PASS"
    assert antes(timeline([leg(10.0, 11.5, "padrao")]))["resultado"] == "PASS"


def test_uma_lasca_de_menos_de_meio_quadro_na_fronteira_e_ignorada():
    meio_quadro = 0.5 / 30
    assert antes(timeline([leg(4.0, 6.0 + meio_quadro / 2, "padrao")]))["resultado"] == "PASS"
    assert antes(timeline([leg(4.0, 6.0 + 2 * meio_quadro, "padrao")]))["resultado"] == "REPROVA"


def test_legenda_que_nasce_colada_no_fim_do_split_vira_relato_e_nao_reprova():
    g = antes(timeline([leg(10.05, 11.5, "padrao")]))
    assert g["resultado"] == "PASS"
    assert any("fim do split" in a and "0.18" in a.replace(",", ".") for a in g["medido"]["avisos"])
    g = antes(timeline([leg(10.0 + OL.GUARDA_POS_SPLIT, 11.5, "padrao")]))
    assert g["medido"]["avisos"] == []


def test_legenda_suprimida_nao_e_verificada():
    g = antes(timeline([leg(7.0, 8.5, "padrao", suprimida=True)]))
    assert g["resultado"] == "PASS" and g["medido"]["legendas"]["suprimidas"] == 1
    assert g["medido"]["legendas"]["verificadas"] == 0


def test_legenda_sobre_insert_cheio_nao_tem_rosto_para_colidir():
    for posicao in ("padrao", "rodape", "costura"):
        assert antes(timeline([leg(12.2, 13.5, posicao)]))["resultado"] == "PASS"


def test_a_timeline_de_exemplo_do_contrato_passa_com_look_aberto():
    tl = json.loads(TIMELINE_VALIDA.read_text(encoding="utf-8"))
    g = antes(tl)
    assert g["resultado"] == "PASS", g.get("motivo")
    assert g["medido"]["legendas"]["suprimidas"] == sum(1 for l in tl["legendas"] if l["suprimida"])


# =================================================================================== antes: insumos

def test_sem_medicao_do_rosto_e_erro_de_insumo_e_nao_chute():
    g = gate_geometria.rodar_antes(timeline([leg(1.0, 2.5, "padrao")]))
    assert g["resultado"] == "ERRO" and g["saida"] == 2 and "rosto" in g["motivo"]
    assert formato_do_laudo(g) == []


def test_o_medidor_injetado_recebe_o_avatar_e_o_resultado_vale():
    visto = []

    def medir(avatar):
        visto.append(avatar)
        return ROSTO_FECHADO
    g = gate_geometria.rodar_antes(timeline([leg(1.0, 2.5, "padrao")]), avatar="inputs/av.mp4", medir=medir,
                                   rosto_split=ROSTO_SPLIT)
    assert visto == ["inputs/av.mp4"] and g["resultado"] == "REPROVA" and "rodapé" in g["motivo"]


def test_medidor_que_nao_acha_rosto_e_erro_de_insumo():
    g = gate_geometria.rodar_antes(timeline([leg(1.0, 2.5, "padrao")]), avatar="av.mp4", medir=lambda a: None)
    assert g["resultado"] == "ERRO" and g["saida"] == 2 and "não achei" in g["motivo"]


def test_medidor_que_estoura_vira_erro_de_insumo():
    def quebra(avatar):
        raise OSError("ffmpeg não leu o avatar")
    g = gate_geometria.rodar_antes(timeline([leg(1.0, 2.5, "padrao")]), avatar="av.mp4", medir=quebra)
    assert g["resultado"] == "ERRO" and g["saida"] == 2 and "ffmpeg" in g["motivo"]


@pytest.mark.parametrize("ruim", [None, [], "texto", {}, {"legendas": "x"}, {"legendas": [], "segmentos": []}])
def test_timeline_invalida_vira_erro_de_insumo(ruim):
    g = gate_geometria.rodar_antes(ruim, rosto=ROSTO_ABERTO, rosto_split=ROSTO_SPLIT)
    assert g["resultado"] == "ERRO" and g["saida"] == 2 and g["motivo"]
    assert formato_do_laudo(g) == []


@pytest.mark.parametrize("rosto", [(300,), "alto", (300, -5), (300, 0), (None, 500), (300, 500, 7)])
def test_rosto_malformado_vira_erro_de_insumo(rosto):
    g = gate_geometria.rodar_antes(timeline([leg(1.0, 2.5, "padrao")]), rosto=rosto, rosto_split=ROSTO_SPLIT)
    assert g["resultado"] == "ERRO" and g["saida"] == 2


# =================================================================================== antes: a timeline do construir

CFG = {"ad": "ad77v2", "look": "neutro", "format": "9x16", "speed": 1.0,
       "hook": {"eyebrow": "MEU CLAUDE", "l1": "virou um web designer", "accent": "PROFISSIONAL"},
       "cta_label": "saiba mais", "kw_phrases": ["web designer profissional", "em minutos"],
       "letterings": [{"lead": "sabe qual é", "key": "O MELHOR", "anchor": "melhor", "nth": 1, "dur": 1.6}]}
LEVA = """[inserção de vídeo: demo a] Minha skill de criação de páginas transformou meu Claude em um web designer profissional.
[apresentador de frente para a câmera] Agora eu construo minhas páginas em minutos, sem precisar pagar nada mais por isso.
[apresentador + lettering | LEAD: sabe qual é | KEY: O MELHOR] Sabe qual é o melhor?
[inserção de vídeo: demo b] Se eu usar um conector que é disponibilizado gratuitamente dentro do Claude,
[apresentador + lettering + logo | LEAD: eu consigo não só | KEY: PRODUZIR AS PÁGINAS] eu consigo não só produzir as páginas
"""


def construir_de_verdade(tmp_path, medir_rosto=None):
    """A timeline que o `timeline.construir` monta (as funções do overlay, de verdade), sem mídia."""
    from footage import blocos as BL
    from timeline import alinhar as AL
    from timeline import construir as TC
    dados = tmp_path / "dados"
    (dados / "inputs").mkdir(parents=True)
    (dados / "output").mkdir(parents=True)
    avatar = dados / "inputs" / "ad77v2_neutro_avatar.mp4"
    avatar.write_bytes(b"avatar sintetico")
    leva = dados / "inputs" / "ad77v2_leva.txt"
    leva.write_text(LEVA, encoding="utf-8")
    inserts_map = {"demo a": {"file": str(dados / "inputs" / "a.mp4"), "start": 0, "speed": 1.0},
                   "demo b": {"file": str(dados / "inputs" / "b.mp4"), "start": 1.0, "speed": 1.0, "split": True}}
    blocks = BL.ler_blocos(str(leva))
    t, palavras = 0.62, []
    for b in blocks:                                     # fala contínua, pausa de 0,3 s na troca de bloco
        for w in b["narr"].split():
            palavras.append({"t": w, "s": round(t, 3), "e": round(t + 0.3, 3)})
            t += 0.36
        t += 0.3
    al = {"versao": 1, "avatar": "inputs/" + avatar.name, "avatar_sha256": hashlib.sha256(avatar.read_bytes()).hexdigest(),
          "duracao_audio_s": round(palavras[-1]["e"] + 0.4, 3),
          "transcricao": [{"text": p["t"], "start": p["s"], "end": p["e"]} for p in palavras], "palavras": palavras}
    caminho = dados / "output" / "alinhamento.json"
    AL.gravar(al, caminho)
    return TC.construir(blocks, al, inserts_map=inserts_map, cfg=dict(CFG, avatar=str(avatar)),
                        caminho_alinhamento=caminho, raiz=dados, medir_rosto=medir_rosto)


def test_a_timeline_que_o_construir_monta_passa_no_gate_com_look_aberto(tmp_path):
    tl = construir_de_verdade(tmp_path)
    assert tl["janelas_split"], "a fixture precisa de um split para o teste valer"
    posicoes = {l["posicao"] for l in tl["legendas"]}
    assert "costura" in posicoes and "padrao" in posicoes
    g = antes(tl, rosto=ROSTO_ABERTO)
    assert g["resultado"] == "PASS", g.get("motivo")
    assert g["medido"]["legendas"]["verificadas"] >= 3


def test_a_timeline_do_construir_com_look_fechado_medido_vai_pro_rodape_e_passa(tmp_path):
    tl = construir_de_verdade(tmp_path, medir_rosto=lambda avatar: ROSTO_FECHADO)
    assert "rodape" in {l["posicao"] for l in tl["legendas"]}
    g = antes(tl, rosto=ROSTO_FECHADO)
    assert g["resultado"] == "PASS", g.get("motivo")


def test_timeline_montada_sem_medir_o_rosto_reprova_quando_o_look_e_fechado(tmp_path):
    """É o defeito de 27/08: o look fechado não foi medido na montagem e a legenda padrão raspou a barba."""
    tl = construir_de_verdade(tmp_path)
    g = antes(tl, rosto=ROSTO_FECHADO)
    assert g["resultado"] == "REPROVA" and "rodapé" in g["motivo"]


# =================================================================================== antes: linha de comando

def _gravar(tmp_path, tl):
    p = tmp_path / "timeline.json"
    p.write_text(json.dumps(tl), encoding="utf-8")
    return p


def test_cli_antes_sai_0_1_ou_2(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(gate_geometria, "_medir_padrao", lambda avatar: ROSTO_ABERTO)
    tl = _gravar(tmp_path, timeline([leg(1.0, 2.5, "padrao"), leg(7.0, 8.5, "costura")]))
    base = ["antes", "--timeline", str(tl), "--avatar", "av.mp4", "--rosto-split", "1258:1832"]
    assert gate_geometria.main(base) == 0
    assert "PASSA" in capsys.readouterr().out
    monkeypatch.setattr(gate_geometria, "_medir_padrao", lambda avatar: ROSTO_FECHADO)
    assert gate_geometria.main(base) == 1
    assert "REPROVA" in capsys.readouterr().out
    assert gate_geometria.main(["antes", "--timeline", str(tmp_path / "nao-existe.json"), "--avatar", "a"]) == 2
    assert "ERRO de insumo" in capsys.readouterr().err
    assert gate_geometria.main(["antes", "--timeline", str(tl)]) == 2          # sem avatar nem --rosto


def test_cli_antes_json_imprime_o_gate_do_laudo(tmp_path, capsys):
    tl = _gravar(tmp_path, timeline([leg(1.0, 2.5, "padrao")]))
    assert gate_geometria.main(["antes", "--timeline", str(tl), "--rosto", "300:500", "--json"]) == 0
    g = json.loads(capsys.readouterr().out)
    assert g["nome"] == "gate_geometria" and g["resultado"] == "PASS"


# =================================================================================== depois: a tinta real

BRANCO = (255, 255, 255, 255)


def quadro(retangulos=(), dim=None):
    im = Image.new("RGBA", (LARGURA, ALTURA), dim or (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for x0, y0, x1, y1, cor in retangulos:
        d.rectangle([x0, y0, x1, y1], fill=cor)
    return np.array(im)


class Cena(object):
    """Um anúncio sintético: onde está o rosto em cada layout e onde a tinta pousa. O detector e o leitor do
    overlay respondem pelo instante, como o render de verdade responderia."""

    def __init__(self, tl, tinta, rosto_cheio=(300, 300, 480, 500), rosto_split=(300, 1258, 480, 574)):
        self.tl, self.tinta = tl, tinta                    # tinta: layout -> retângulo (x0, y0, x1, y1[, cor])
        self.rosto_cheio, self.rosto_split = rosto_cheio, rosto_split
        self.pedidos_overlay, self.pedidos_video = [], []

    def layout(self, t):
        if any(j["s"] <= t < j["e"] for j in self.tl["janelas_split"]):
            return "split"
        sg = next((s for s in self.tl["segmentos"] if s["s"] <= t < s["e"]), None)
        return "insert" if sg and sg["tipo"] == "insert" else "cheio"

    def leitor_overlay(self, _overlay, t):
        self.pedidos_overlay.append(round(float(t), 3))
        ret = self.tinta.get(self.layout(t))
        if ret is None:
            return quadro()
        cor = ret[4] if len(ret) > 4 else BRANCO
        return quadro([tuple(ret[:4]) + (cor,)])

    def detector(self, _video, t_entregue):
        rel = self.tl["relogio"]
        t = t_entregue * rel["aceleracao"] + rel["a0"]
        self.pedidos_video.append(round(float(t_entregue), 3))
        lay = self.layout(t)
        return [self.rosto_cheio] if lay == "cheio" else ([self.rosto_split] if lay == "split" else [])


# onde a tinta certa pousa em cada layout (nenhuma encosta no núcleo do rosto)
TINTA_CERTA = {"cheio": (200, 1400, 880, 1480), "split": (200, 967, 880, 1106), "insert": (200, 1400, 880, 1480)}


def tl_com_legendas():
    return timeline([leg(1.0, 2.5, "padrao"), leg(3.0, 4.5, "padrao"), leg(7.0, 8.5, "costura"),
                     leg(10.5, 11.8, "padrao"), leg(12.3, 13.7, "rodape")])


def depois(cena, tmp_path, **kw):
    ovl, vid = tmp_path / "overlay.mov", tmp_path / "final.mp4"
    ovl.write_bytes(b"x")
    vid.write_bytes(b"x")
    kw.setdefault("detector", cena.detector)
    kw.setdefault("leitor_overlay", cena.leitor_overlay)
    return gate_geometria.rodar_depois(vid, ovl, cena.tl, **kw)


def test_tinta_no_peito_e_na_costura_passa_em_6_instantes(tmp_path):
    cena = Cena(tl_com_legendas(), TINTA_CERTA)
    g = depois(cena, tmp_path)
    assert g["nome"] == "gate_geometria_depois" and g["etapa"] == "depois"
    assert g["resultado"] == "PASS" and g["saida"] == 0, g.get("motivo")
    assert formato_do_laudo(g) == []
    assert len(g["medido"]["instantes"]) == 6 and len(cena.pedidos_overlay) == 6
    assert g["limiar"]["colisao_pct"] == 1.5
    for m in g["medido"]["instantes"]:
        assert m["ok"] is True and m["maior_cobertura_pct"] <= 1.5


def test_mutante_legenda_deslocada_pro_rosto_reprova_no_render(tmp_path):
    cena = Cena(tl_com_legendas(), dict(TINTA_CERTA, cheio=(250, 450, 830, 560)))      # em cima da boca
    g = depois(cena, tmp_path)
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert "do núcleo do rosto" in g["motivo"] and "1.5%" in g["motivo"].replace(",", ".")
    ruins = [m for m in g["medido"]["instantes"] if not m["ok"]]
    assert ruins and all(m["layout"] == "cheio" and m["maior_cobertura_pct"] > 1.5 for m in ruins)


def test_no_split_a_tinta_padrao_cai_no_painel_do_apresentador_e_reprova(tmp_path):
    cena = Cena(tl_com_legendas(), dict(TINTA_CERTA, split=(200, 1290, 880, 1500)))
    g = depois(cena, tmp_path, instantes=[7.75])
    assert g["resultado"] == "REPROVA"
    (m,) = g["medido"]["instantes"]
    assert m["layout"] == "split" and m["maior_cobertura_pct"] > 1.5 and m["fonte_do_rosto"] == "detector"


def test_no_split_a_costura_passa_com_o_rosto_embaixo(tmp_path):
    cena = Cena(tl_com_legendas(), TINTA_CERTA)
    g = depois(cena, tmp_path, instantes=[7.75])
    assert g["resultado"] == "PASS"
    assert g["medido"]["instantes"][0]["tinta_y"] == [967, 1106]


def test_detector_cego_no_split_cai_na_geometria_do_plano(tmp_path):
    """Texto em cima da cara quebra o Haar, e o gate aprovava o pior caso (jh13, 27/08). No split o apresentador
    mora no painel de baixo por construção: com `rosto_split` do plano, a tinta ali é colisão mesmo sem detecção."""
    cena = Cena(tl_com_legendas(), dict(TINTA_CERTA, split=(200, 1290, 880, 1500)))
    cego = lambda v, t: []
    g = depois(cena, tmp_path, detector=cego, instantes=[7.75], rosto_split=ROSTO_SPLIT)
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    (m,) = g["medido"]["instantes"]
    assert m["fonte_do_rosto"] == "plano" and m["maior_cobertura_pct"] > 1.5
    # e a costura, com o mesmo detector cego, passa
    cena = Cena(tl_com_legendas(), TINTA_CERTA)
    assert depois(cena, tmp_path, detector=cego, instantes=[7.75], rosto_split=ROSTO_SPLIT)["resultado"] == "PASS"


def test_detector_cego_no_split_sem_rosto_do_plano_nao_mede_e_avisa(tmp_path):
    cena = Cena(tl_com_legendas(), dict(TINTA_CERTA, split=(200, 1290, 880, 1500)))
    g = depois(cena, tmp_path, detector=lambda v, t: [], instantes=[7.75])
    assert g["resultado"] == "PASS"
    assert g["medido"]["instantes"][0]["fonte_do_rosto"] is None
    assert any("sem rosto" in a for a in g["medido"]["avisos"])


def test_no_cheio_sem_rosto_detectado_nao_ha_o_que_colidir(tmp_path):
    cena = Cena(tl_com_legendas(), dict(TINTA_CERTA, cheio=(250, 450, 830, 560)))
    g = depois(cena, tmp_path, detector=lambda v, t: [], instantes=[1.75])
    assert g["resultado"] == "PASS"


def test_rosto_do_painel_de_cima_no_split_e_conteudo_do_insert_e_nao_conta(tmp_path):
    """O Haar acha 'rosto' numa foto dentro do insert; no split só vale o rosto do painel de baixo."""
    cena = Cena(tl_com_legendas(), dict(TINTA_CERTA, split=(200, 500, 880, 700)))
    no_insert = lambda v, t: [(300, 300, 480, 500)]                       # centro em y 550 < 1150
    g = depois(cena, tmp_path, detector=no_insert, instantes=[7.75])
    assert g["resultado"] == "PASS" and g["medido"]["instantes"][0]["rostos"] == 0


def test_so_a_tinta_clara_e_opaca_conta_como_no_gate_de_colisao(tmp_path):
    """O dim de tela inteira (alfa 140, escuro) do lettering não é tinta, nem a sombra translúcida."""
    cena = Cena(tl_com_legendas(), {})
    def leitor(o, t):
        cena.pedidos_overlay.append(t)
        return quadro([(250, 450, 830, 560, (2, 3, 6, 140))], dim=(2, 3, 6, 140))
    g = depois(cena, tmp_path, leitor_overlay=leitor, instantes=[1.75])
    assert g["resultado"] == "PASS"
    def leitor_claro(o, t):
        return quadro([(250, 450, 830, 560, (255, 255, 255, 255))])
    g = depois(cena, tmp_path, leitor_overlay=leitor_claro, instantes=[1.75])
    assert g["resultado"] == "REPROVA"


def test_o_instante_do_video_e_o_entregue_com_aceleracao_e_a0(tmp_path):
    tl = timeline([leg(7.0, 8.5, "costura")], aceleracao=1.35, a0=0.24)
    cena = Cena(tl, TINTA_CERTA)
    depois(cena, tmp_path, instantes=[7.75])
    assert cena.pedidos_overlay == [7.75]                                  # o overlay vive no relógio da timeline
    assert cena.pedidos_video == [pytest.approx((7.75 - 0.24) / 1.35, abs=1e-3)]


def test_seis_instantes_espacados_sao_os_da_zona_segura(tmp_path):
    from gates import gate_safezone
    tl = tl_com_legendas()
    cena = Cena(tl, TINTA_CERTA)
    g = depois(cena, tmp_path)
    esperados = [i["t"] for i in gate_safezone.instantes(tl, 6)]
    assert cena.pedidos_overlay == pytest.approx(esperados, abs=1e-3)
    assert [m["t"] for m in g["medido"]["instantes"]] == pytest.approx(esperados, abs=1e-3)


def test_depois_insumos_ruins_viram_erro_de_insumo(tmp_path):
    cena = Cena(tl_com_legendas(), TINTA_CERTA)
    g = gate_geometria.rodar_depois(tmp_path / "nao-existe.mp4", tmp_path / "nao-existe.mov", cena.tl)
    assert g["resultado"] == "ERRO" and g["saida"] == 2 and "nao-existe" in g["motivo"]
    g = depois(cena, tmp_path, leitor_overlay=lambda o, t: np.zeros((1080, 1080, 4), dtype=np.uint8))
    assert g["resultado"] == "ERRO" and "1080x1920" in g["motivo"]
    def quebra(v, t):
        raise OSError("ffmpeg não leu o quadro")
    g = depois(cena, tmp_path, detector=quebra)
    assert g["resultado"] == "ERRO" and g["saida"] == 2 and "ffmpeg" in g["motivo"]
    assert formato_do_laudo(g) == []


def test_formato_1x1_e_pulado_tambem_na_geometria_depois(tmp_path):
    tl = tl_com_legendas()
    tl["formato"] = "1x1"
    g = depois(Cena(tl, TINTA_CERTA), tmp_path)
    assert g["resultado"] == "PULADO" and g["saida"] == 0


def test_cli_depois_sai_0_1_ou_2(tmp_path, capsys, monkeypatch):
    tl_dict = tl_com_legendas()
    tl = _gravar(tmp_path, tl_dict)
    ovl, vid = tmp_path / "overlay.mov", tmp_path / "final.mp4"
    ovl.write_bytes(b"x")
    vid.write_bytes(b"x")
    cena = Cena(tl_dict, TINTA_CERTA)
    monkeypatch.setattr(gate_geometria, "_detector_padrao", lambda: cena.detector)
    monkeypatch.setattr(gate_geometria.gate_safezone, "ler_overlay_padrao", cena.leitor_overlay)
    base = ["depois", "--timeline", str(tl), "--video", str(vid), "--overlay", str(ovl)]
    assert gate_geometria.main(base) == 0
    cena.tinta = dict(TINTA_CERTA, cheio=(250, 450, 830, 560))
    assert gate_geometria.main(base) == 1
    assert "REPROVA" in capsys.readouterr().out
    assert gate_geometria.main(["depois", "--timeline", str(tl), "--video", str(vid),
                                "--overlay", str(tmp_path / "x.mov")]) == 2


# =================================================================================== render de verdade

def _overlay_mov(tmp_path, nome, caixas):
    """ProRes 4444 com alfa, 1080x1920 a 10 quadros/s, 2 s: `caixas` = [(x, y, w, h)] em branco opaco."""
    filtros = ["drawbox=x=%d:y=%d:w=%d:h=%d:color=white@1.0:t=fill:replace=1" % c for c in caixas]
    saida = tmp_path / nome
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
           "color=c=black@0.0:s=1080x1920:r=10:d=2,format=rgba",
           "-vf", ",".join(filtros), "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
           str(saida)]
    subprocess.run(cmd, check=True, capture_output=True)
    return saida


def _tl_curta():
    tl = timeline([leg(1.0, 1.8, "padrao")])
    tl.update({"duracao_s": 2.0, "janelas_split": [], "hook": dict(tl["hook"], e=0.9),
               "cta": {"inicio": 1.9, "logo": 1.9, "label": "saiba mais", "sem_lead": False},
               "segmentos": [{"bloco": 0, "tipo": "apresentador", "s": 0.0, "e": 2.0, "sub": 0, "de": 1}]})
    return tl


@pytest.mark.lento
def test_render_de_verdade_o_overlay_com_alfa_passa_pelo_leitor_padrao(tmp_path):
    """Overlay ProRes com alfa lido pelo ffmpeg; o detector é injetado (o rosto está em y 300 a 800)."""
    peito = _overlay_mov(tmp_path, "peito.mov", [(200, 1400, 680, 80)])
    rosto = _overlay_mov(tmp_path, "rosto.mov", [(250, 450, 580, 110)])
    vid = tmp_path / "final.mp4"
    vid.write_bytes(b"x")
    detector = lambda v, t: [(300, 300, 480, 500)]
    ok = gate_geometria.rodar_depois(vid, peito, _tl_curta(), detector=detector, instantes=[1.4])
    ruim = gate_geometria.rodar_depois(vid, rosto, _tl_curta(), detector=detector, instantes=[1.4])
    assert ok["resultado"] == "PASS", ok.get("motivo")
    assert ruim["resultado"] == "REPROVA" and ruim["medido"]["instantes"][0]["maior_cobertura_pct"] > 1.5


def _avatar_real():
    base = os.environ.get("VAM_PARIDADE_MIDIA")
    if not base or not Path(base).is_dir():
        pytest.skip("VAM_PARIDADE_MIDIA não definida: o teste usa o avatar real da fixture da paridade. Use: "
                    "VAM_PARIDADE_MIDIA=<pasta> bash scripts/dev/testar_limpo.sh --paridade -k gate_geometria")
    p = Path(base) / "fixture" / "midia" / "avatar_18s.mp4"
    if not p.is_file():
        pytest.skip("falta %s na pasta de mídia da paridade" % p)
    return str(p)


@pytest.mark.lento
@pytest.mark.midia_real
def test_avatar_real_o_rosto_medido_decide_a_posicao_da_legenda():
    """O Haar de verdade num avatar real: a legenda na posição que o próprio layout_texto escolhe passa; na outra,
    quando ela cai no rosto ou raspa o queixo, reprova."""
    avatar = _avatar_real()
    tl = timeline([leg(1.0, 2.5, "padrao")])
    with contextlib.redirect_stdout(io.StringIO()):
        fechado = OL.look_fechado(avatar)
    certa = "rodape" if fechado else "padrao"
    g = gate_geometria.rodar_antes(timeline([leg(1.0, 2.5, certa)]), avatar=avatar, rosto_split=ROSTO_SPLIT)
    assert g["resultado"] == "PASS", g.get("motivo")
    assert g["medido"]["rosto_avatar"]["fechado"] is fechado
    errada = gate_geometria.rodar_antes(tl if fechado else timeline([leg(1.0, 2.5, "costura")]),
                                        avatar=avatar, rosto_split=ROSTO_SPLIT)
    assert errada["resultado"] == "REPROVA"


@pytest.mark.lento
@pytest.mark.midia_real
def test_avatar_real_tinta_na_cara_reprova_e_tinta_no_peito_passa(tmp_path):
    """O avatar real como vídeo entregue (tela cheia o tempo todo); o overlay é sintético: ou no peito, ou na boca."""
    avatar = _avatar_real()
    from medir_rosto import caixa_rosto
    topo, altura = caixa_rosto(avatar)
    tl = timeline([leg(1.0, 2.5, "padrao"), leg(3.0, 4.5, "padrao")])
    tl["segmentos"] = [{"bloco": 0, "tipo": "apresentador", "s": 0.0, "e": 16.0, "sub": 0, "de": 1}]
    tl["janelas_split"] = []
    boca = _overlay_mov(tmp_path, "boca.mov", [(300, topo + altura // 2 - 40, 480, 90)])
    peito = _overlay_mov(tmp_path, "peito.mov", [(300, min(topo + altura + 80, 1800), 480, 90)])
    ruim = gate_geometria.rodar_depois(avatar, boca, tl, instantes=[1.5])
    ok = gate_geometria.rodar_depois(avatar, peito, tl, instantes=[1.5])
    assert ruim["resultado"] == "REPROVA", ruim
    assert ok["resultado"] == "PASS", ok
    assert ruim["medido"]["instantes"][0]["fonte_do_rosto"] == "detector"
