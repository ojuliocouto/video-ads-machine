"""W3.D: gate_safezone. A zona segura é RÍGIDA: nenhuma tinta abaixo de y 1690 nem à direita de x 940.

Os números são os que o dono aprovou nas levas (plano, seção 1.5): y 1690 é o teto da UI do Reels (botões e
descrição) e x 940 é onde o app desenha a coluna de curtir e comentar. A faixa de 1250 a 1690, da máscara de
anúncio da Meta, só vira RELATO (`avisos`): nunca reprova.

O gate roda em duas etapas, com dois nomes de laudo (o laudo não aceita nome repetido):

  antes   `gate_safezone`          sobre o plano (timeline): a geometria das faixas, sem render. As faixas de
                                   legenda vêm de `overlay.layout_texto.FAIXA_LEGENDA` (fonte única, lida na hora
                                   da chamada, nunca copiada). Lettering e CTA não têm faixa em `layout_texto`
                                   (moram no CSS do template): quem as conhece passa `faixas_extra`.
  depois  `gate_safezone_depois`   sobre o render: a tinta REAL, pelo alfa do overlay, em 6 instantes espaçados.

Os testes rápidos usam um overlay sintético desenhado com PIL (nenhum ffmpeg, nenhuma mídia). Os `lento`
geram um .mov com alfa de verdade e passam pelo leitor padrão (ffmpeg).

Mutantes que TÊM que reprovar: lettering com tinta em y 1700, CTA com tinta em x 960, FAIXA_LEGENDA adulterada.
Resultado no formato do laudo (`contratos/laudo.schema.json`): `avisos` e `acao` moram dentro de `medido`,
porque o schema do laudo proíbe chave extra no gate.
"""
import copy
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from contratos import validar
from gates import gate_safezone
from overlay import layout_texto as OL

RAIZ = Path(__file__).resolve().parents[2]
LAUDO_VALIDO = RAIZ / "contratos" / "exemplos" / "laudo.valido.json"
TIMELINE_VALIDA = RAIZ / "contratos" / "exemplos" / "timeline.valido.json"

LARGURA, ALTURA = 1080, 1920


# =================================================================================== insumos sintéticos

def timeline():
    """A timeline válida do contrato (27,5 s, 9 legendas, 5 letterings, hook e CTA), para o teste mexer."""
    return copy.deepcopy(json.loads(TIMELINE_VALIDA.read_text(encoding="utf-8")))


def tl_curta():
    """2 s: hook de 0 a 1 s e uma legenda de 1,0 a 1,8 s. Para o render de verdade."""
    return {"versao": 1, "projeto": "curta", "formato": "9x16", "duracao_s": 2.0,
            "relogio": {"base": "footage_1x", "fps": 30, "aceleracao": 1.0, "cauda_s": 0.0, "a0": 0.0},
            "segmentos": [{"bloco": 0, "tipo": "apresentador", "s": 0.0, "e": 2.0, "sub": 0, "de": 1}],
            "janelas_split": [], "letterings": [],
            "legendas": [{"s": 1.0, "e": 1.8, "texto": "uma legenda", "posicao": "padrao", "suprimida": False,
                          "palavras": [{"t": "uma", "s": 1.0, "e": 1.4}, {"t": "legenda", "s": 1.4, "e": 1.8}]}],
            "hook": {"s": 0.0, "e": 1.0, "eyebrow": "A", "linha": "B", "destaque": "C", "estilo": "editorial"},
            "cta": {"inicio": 1.9, "logo": 1.9, "label": "saiba mais", "sem_lead": False}}


def tl_seis_eventos():
    """Hook, legenda, lettering, legenda, lettering e CTA: exatamente 6 eventos, então os 6 instantes medidos
    são todos eles (os mutantes não dependem de o sorteio espaçado cair num lettering)."""
    leg = lambda s, e, pos: {"s": s, "e": e, "texto": "uma legenda", "posicao": pos, "suprimida": False,
                             "palavras": [{"t": "uma", "s": s, "e": (s + e) / 2}, {"t": "legenda", "s": (s + e) / 2, "e": e}]}
    lett = lambda i, s, d: {"id": "lett" + i, "bloco": 0, "key": "CHAVE", "s": s, "d": d, "estilo": "serif_editorial",
                            "split": False, "baixo": False, "pilha": None, "cta": False}
    return {"versao": 1, "projeto": "seis", "formato": "9x16", "duracao_s": 15.0,
            "relogio": {"base": "footage_1x", "fps": 30, "aceleracao": 1.0, "cauda_s": 0.0, "a0": 0.0},
            "segmentos": [{"bloco": 0, "tipo": "apresentador", "s": 0.0, "e": 15.0, "sub": 0, "de": 1}],
            "janelas_split": [], "legendas": [leg(2.5, 4.0, "padrao"), leg(7.0, 8.5, "rodape")],
            "letterings": [lett("A", 4.5, 2.0), lett("B", 9.0, 2.0)],
            "hook": {"s": 0.0, "e": 2.0, "eyebrow": "A", "linha": "B", "destaque": "C", "estilo": "editorial"},
            "cta": {"inicio": 12.0, "logo": 12.2, "label": "saiba mais", "sem_lead": False}}


def quadro(retangulos=(), dim=None):
    """Overlay RGBA 1080x1920 sintético: cada retângulo é (x0, y0, x1, y1, (r, g, b, a)), bordas incluídas.
    `dim` pinta a tela inteira (o dim do lettering, alfa 140, que NÃO é tinta)."""
    im = Image.new("RGBA", (LARGURA, ALTURA), dim or (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for x0, y0, x1, y1, cor in retangulos:
        d.rectangle([x0, y0, x1, y1], fill=cor)
    return np.array(im)


BRANCO = (255, 255, 255, 255)
ESCURO = (18, 20, 26, 255)

# onde cada elemento pousa quando está certo (todos dentro de y 1690 e x 940)
CERTO = {"hook": (160, 700, 900, 900), "legenda": (200, 1400, 880, 1480),
         "lettering": (170, 1420, 910, 1660), "cta": (170, 1450, 910, 1650)}


def evento_em(tl, t):
    """Que elemento do plano está na tela em `t` (o primeiro que casar): hook, lettering, cta ou legenda."""
    if tl["hook"]["s"] <= t < tl["hook"]["e"]:
        return "hook"
    if t >= tl["cta"]["inicio"]:
        return "cta"
    if any(l["s"] <= t < l["s"] + l["d"] for l in tl["letterings"]):
        return "lettering"
    return "legenda"


def leitor_do_plano(tl, desenho=None, tela_cheia=False):
    """`leitor_overlay(overlay, t)`: desenha o retângulo CERTO do elemento daquele instante. `desenho` troca
    o retângulo de um tipo de elemento (o mutante). Guarda os instantes pedidos em `.pedidos`."""
    desenho = desenho or {}

    def leitor(_overlay, t):
        leitor.pedidos.append(round(float(t), 3))
        tipo = evento_em(tl, t)
        ret = desenho.get(tipo, CERTO[tipo])
        cor = ret[4] if len(ret) > 4 else BRANCO
        return quadro([tuple(ret[:4]) + (cor,)], dim=(2, 3, 6, 140) if tela_cheia else None)
    leitor.pedidos = []
    return leitor


def formato_do_laudo(g):
    """Os erros do contrato que dizem respeito a este gate (o resto do laudo não é assunto daqui)."""
    laudo = json.loads(LAUDO_VALIDO.read_text(encoding="utf-8"))
    laudo["gates"] = [x for x in laudo["gates"] if x["nome"] != g["nome"]] + [g]
    k = len(laudo["gates"]) - 1
    return [e for e in validar.validar("laudo", laudo) if ("gates[%d]" % k) in e.caminho]


def depois(tl, tmp_path, leitor, **kw):
    ovl = tmp_path / "overlay.mov"
    ovl.write_bytes(b"x")                     # o leitor é injetado: o arquivo só precisa existir
    return gate_safezone.rodar_depois(ovl, tl, leitor_overlay=leitor, **kw)


# =================================================================================== constantes

def test_os_limites_sao_os_do_plano():
    assert gate_safezone.LIMITE_Y == 1690
    assert gate_safezone.LIMITE_X == 940
    assert gate_safezone.FAIXA_META == (1250, 1690)
    assert gate_safezone.INSTANTES == 6
    assert (gate_safezone.LARGURA, gate_safezone.ALTURA) == (LARGURA, ALTURA)


def test_a_posicao_da_timeline_aponta_para_a_faixa_certa_do_layout_texto():
    """O contrato fala `rodape`; o layout_texto fala `baixa`. A tabela é a inversa da do construir."""
    from timeline import construir as TC
    assert gate_safezone.FAIXA_DA_POSICAO == {v: k for k, v in TC.POSICAO.items()}
    for posicao in ("padrao", "rodape", "costura"):
        assert gate_safezone.faixa_da_legenda(posicao) == OL.FAIXA_LEGENDA[gate_safezone.FAIXA_DA_POSICAO[posicao]]


# =================================================================================== antes (o plano)

def test_o_plano_valido_passa_antes_e_o_resultado_esta_no_formato_do_laudo():
    g = gate_safezone.rodar_antes(timeline())
    assert g["nome"] == "gate_safezone" and g["etapa"] == "antes"
    assert g["resultado"] == "PASS" and g["saida"] == 0, g.get("motivo")
    assert formato_do_laudo(g) == []
    assert g["limiar"]["y_max"] == 1690 and g["limiar"]["x_max"] == 940
    assert g["limiar"]["faixa_meta"] == [1250, 1690]


def test_as_faixas_das_legendas_vem_do_layout_texto_na_hora_da_chamada(monkeypatch):
    """Mutante: o dono mexe na faixa do rodapé e ela passa do teto da UI. O gate não guarda cópia dela."""
    novo = dict(OL.FAIXA_LEGENDA)
    novo["baixa"] = (1370, 1700)
    monkeypatch.setattr(OL, "FAIXA_LEGENDA", novo)
    g = gate_safezone.rodar_antes(timeline())
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert "rodape" in g["motivo"] and "1700" in g["motivo"] and "1690" in g["motivo"]


def test_so_as_posicoes_que_a_timeline_usa_entram_na_conta(monkeypatch):
    """Uma faixa estourada que nenhuma legenda usa não reprova esta timeline."""
    tl = timeline()
    for leg in tl["legendas"]:
        if leg["posicao"] == "rodape":
            leg["posicao"] = "padrao"
    novo = dict(OL.FAIXA_LEGENDA)
    novo["baixa"] = (1370, 1700)
    monkeypatch.setattr(OL, "FAIXA_LEGENDA", novo)
    assert gate_safezone.rodar_antes(tl)["resultado"] == "PASS"


def test_legenda_suprimida_nao_entra_na_conta(monkeypatch):
    tl = timeline()
    for leg in tl["legendas"]:
        if leg["posicao"] == "rodape":
            leg["suprimida"] = True
    novo = dict(OL.FAIXA_LEGENDA)
    novo["baixa"] = (1370, 1700)
    monkeypatch.setattr(OL, "FAIXA_LEGENDA", novo)
    assert gate_safezone.rodar_antes(tl)["resultado"] == "PASS"


def test_a_faixa_de_1250_a_1690_so_gera_relato_e_nunca_reprova():
    """A legenda padrão (y 1290 a 1500) e o rodapé (1370 a 1520) moram na faixa da máscara da Meta."""
    g = gate_safezone.rodar_antes(timeline())
    assert g["resultado"] == "PASS"
    avisos = g["medido"]["avisos"]
    assert avisos and all("só relato" in a for a in avisos)
    assert any("padrao" in a for a in avisos) and any("rodape" in a for a in avisos)
    assert not any("costura" in a for a in avisos)               # a costura (1000 a 1130) está fora da faixa


def test_timeline_so_com_costura_nao_tem_relato():
    tl = timeline()
    for leg in tl["legendas"]:
        leg["posicao"] = "costura"
    g = gate_safezone.rodar_antes(tl)
    assert g["resultado"] == "PASS" and g["medido"]["avisos"] == []


@pytest.mark.parametrize("y1,x1,reprova", [
    (1690, 940, False),             # na linha: passa (reprova só quem passa dela)
    (1691, 940, True),
    (1690, 941, True),
    (1700, None, True),
    (None, 960, True),
])
def test_faixas_extra_o_limite_e_rigido_em_y_1690_e_x_940(y1, x1, reprova):
    extra = [{"elemento": "lettering", "id": "lettA", "s": 6.4, "e": 8.6, "y0": 1420, "y1": y1, "x0": 170, "x1": x1}]
    g = gate_safezone.rodar_antes(timeline(), faixas_extra=extra)
    assert (g["resultado"] == "REPROVA") is reprova, g.get("motivo")
    assert g["saida"] == (1 if reprova else 0)
    if reprova:
        assert "lettering" in g["motivo"] and "lettA" in g["motivo"]


def test_mutante_lettering_em_y_1700_e_cta_em_x_960_reprovam_no_plano():
    extra = [{"elemento": "lettering", "id": "lettB", "y0": 1650, "y1": 1700, "x0": 170, "x1": 900},
             {"elemento": "cta", "id": "pill", "y0": 1450, "y1": 1650, "x0": 600, "x1": 960}]
    g = gate_safezone.rodar_antes(timeline(), faixas_extra=extra)
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert "lettering" in g["motivo"] and "1700" in g["motivo"] and "1690" in g["motivo"]
    assert "cta" in g["motivo"] and "960" in g["motivo"] and "940" in g["motivo"]
    assert formato_do_laudo(g) == []


def test_faixa_extra_na_faixa_da_meta_so_vira_relato():
    extra = [{"elemento": "lettering", "id": "lettC", "y0": 1300, "y1": 1660, "x0": 170, "x1": 910}]
    g = gate_safezone.rodar_antes(timeline(), faixas_extra=extra)
    assert g["resultado"] == "PASS"
    assert any("lettering" in a and "lettC" in a for a in g["medido"]["avisos"])


def test_nao_ha_excecao_por_projeto():
    """A zona segura é rígida: um `excecoes` no projeto.json não afrouxa nada."""
    extra = [{"elemento": "cta", "id": "pill", "y0": 1450, "y1": 1650, "x0": 600, "x1": 960}]
    projeto = {"modo": "avatar", "excecoes": [{"regra": "safezone", "motivo": "quero assim mesmo"}]}
    g = gate_safezone.rodar_antes(timeline(), projeto, faixas_extra=extra)
    assert g["resultado"] == "REPROVA"


def test_formato_1x1_e_pulado_com_motivo():
    """A zona segura é do 9x16 (1080x1920); o quadrado é beta e fica sem gate cinematográfico."""
    tl = timeline()
    tl["formato"] = "1x1"
    g = gate_safezone.rodar_antes(tl)
    assert g["resultado"] == "PULADO" and g["saida"] == 0 and "1x1" in g["motivo"]
    assert formato_do_laudo(g) == []


@pytest.mark.parametrize("ruim", [None, [], "texto", {}, {"letterings": []}, {"legendas": "x"}])
def test_timeline_invalida_vira_erro_de_insumo_e_nao_excecao(ruim):
    g = gate_safezone.rodar_antes(ruim)
    assert g["resultado"] == "ERRO" and g["saida"] == 2 and g["motivo"]
    assert formato_do_laudo(g) == []


def test_faixa_extra_malformada_vira_erro_de_insumo():
    g = gate_safezone.rodar_antes(timeline(), faixas_extra=[{"elemento": "cta", "y1": "baixo"}])
    assert g["resultado"] == "ERRO" and g["saida"] == 2 and "cta" in g["motivo"]


# =================================================================================== os 6 instantes

def test_seis_instantes_espacados_incluem_o_primeiro_e_o_ultimo_evento():
    tl = timeline()
    ins = gate_safezone.instantes(tl, 6)
    assert len(ins) == 6
    ts = [i["t"] for i in ins]
    assert ts == sorted(ts) and len(set(ts)) == 6
    todos = gate_safezone.instantes(tl, 1000)
    assert len(todos) > 6
    assert ins[0] == todos[0] and ins[-1] == todos[-1]
    # espaçados: o passo, em índices dos eventos, é quase constante
    pos = [todos.index(i) for i in ins]
    passos = [b - a for a, b in zip(pos, pos[1:])]
    assert max(passos) - min(passos) <= 1
    assert {i["evento"] for i in todos} == {"hook", "legenda", "lettering", "cta"}


def test_instantes_nunca_pegam_legenda_suprimida_e_ficam_dentro_do_anuncio():
    tl = timeline()
    suprimidas = [(l["s"], l["e"]) for l in tl["legendas"] if l["suprimida"]]
    for i in gate_safezone.instantes(tl, 1000):
        if i["evento"] == "legenda":
            assert not any(s <= i["t"] < e for s, e in suprimidas)
        assert 0 <= i["t"] <= tl["duracao_s"]


def test_menos_eventos_que_instantes_mede_todos():
    tl = tl_curta()
    assert [i["evento"] for i in gate_safezone.instantes(tl, 6)] == ["hook", "legenda", "cta"]


# =================================================================================== depois (a tinta real)

def test_overlay_dentro_da_zona_segura_passa_em_6_instantes(tmp_path):
    tl = timeline()
    leitor = leitor_do_plano(tl)
    g = depois(tl, tmp_path, leitor)
    assert g["nome"] == "gate_safezone_depois" and g["etapa"] == "depois"
    assert g["resultado"] == "PASS" and g["saida"] == 0, g.get("motivo")
    assert formato_do_laudo(g) == []
    assert len(g["medido"]["instantes"]) == 6 and len(leitor.pedidos) == 6
    for m in g["medido"]["instantes"]:
        assert m["ok"] is True and m["y_max"] <= 1690 and m["x_max"] <= 940
        assert m["px_abaixo_de_1690"] == 0 and m["px_a_direita_de_940"] == 0


def test_mutante_lettering_com_tinta_em_y_1700_reprova(tmp_path):
    tl = tl_seis_eventos()
    g = depois(tl, tmp_path, leitor_do_plano(tl, {"lettering": (170, 1650, 910, 1700)}))
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert "lettering" in g["motivo"] and "1700" in g["motivo"] and "1690" in g["motivo"]
    ruins = [m for m in g["medido"]["instantes"] if not m["ok"]]
    assert ruins and all(m["evento"] == "lettering" and m["y_max"] == 1700 for m in ruins)
    assert formato_do_laudo(g) == []


def test_mutante_cta_com_tinta_em_x_960_reprova(tmp_path):
    tl = tl_seis_eventos()
    g = depois(tl, tmp_path, leitor_do_plano(tl, {"cta": (600, 1450, 960, 1650)}))
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert "cta" in g["motivo"] and "960" in g["motivo"] and "940" in g["motivo"]
    (ruim,) = [m for m in g["medido"]["instantes"] if not m["ok"]]
    assert ruim["x_max"] == 960 and ruim["px_a_direita_de_940"] > 0


@pytest.mark.parametrize("ret,ok", [
    ((170, 1620, 910, 1690), True),          # a última linha de tinta É a linha 1690: passa
    ((170, 1620, 910, 1691), False),
    ((170, 1500, 940, 1600), True),          # a última coluna de tinta É a coluna 940: passa
    ((170, 1500, 941, 1600), False),
])
def test_o_limite_e_na_linha_e_na_coluna_exatas(tmp_path, ret, ok):
    tl = tl_seis_eventos()
    g = depois(tl, tmp_path, leitor_do_plano(tl, {"lettering": ret, "cta": ret}))
    assert (g["resultado"] == "PASS") is ok, g.get("motivo")


def test_tinta_escura_conta_o_dim_de_tela_inteira_nao(tmp_path):
    """Legenda de tinta invertida é escura e OPACA: é tinta. O dim do lettering (alfa 140) cobre a tela toda
    e não é."""
    tl = tl_seis_eventos()
    g = depois(tl, tmp_path, leitor_do_plano(tl, tela_cheia=True))
    assert g["resultado"] == "PASS", g.get("motivo")                   # dim em toda a tela, tinta no lugar
    g = depois(tl, tmp_path, leitor_do_plano(tl, {"legenda": (200, 1700, 880, 1760, ESCURO)}, tela_cheia=True))
    assert g["resultado"] == "REPROVA" and "1760" in g["motivo"]


def test_tinta_na_faixa_da_meta_so_vira_relato(tmp_path):
    tl = tl_seis_eventos()
    g = depois(tl, tmp_path, leitor_do_plano(tl))            # lettering, CTA e legenda ficam entre 1400 e 1660
    assert g["resultado"] == "PASS"
    avisos = g["medido"]["avisos"]
    assert avisos and "1250" in avisos[0] and "1690" in avisos[0] and "só relato" in avisos[0]
    assert all(m["px_na_faixa_meta"] > 0 for m in g["medido"]["instantes"] if m["evento"] != "hook")


def test_sem_tinta_na_faixa_da_meta_nao_ha_relato(tmp_path):
    tl = tl_seis_eventos()
    tudo_alto = {k: (200, 700, 880, 800) for k in CERTO}
    g = depois(tl, tmp_path, leitor_do_plano(tl, tudo_alto))
    assert g["resultado"] == "PASS" and g["medido"]["avisos"] == []


def test_instantes_pedidos_a_mao_sao_os_medidos(tmp_path):
    tl = timeline()
    leitor = leitor_do_plano(tl)
    depois(tl, tmp_path, leitor, instantes=[1.0, 7.0, 25.0])
    assert leitor.pedidos == [1.0, 7.0, 25.0]


def test_numero_de_instantes_e_configuravel(tmp_path):
    tl = timeline()
    leitor = leitor_do_plano(tl)
    g = depois(tl, tmp_path, leitor, n_instantes=3)
    assert len(g["medido"]["instantes"]) == 3


def test_overlay_do_tamanho_errado_vira_erro_de_insumo(tmp_path):
    tl = timeline()
    g = depois(tl, tmp_path, lambda o, t: np.zeros((1080, 1080, 4), dtype=np.uint8))
    assert g["resultado"] == "ERRO" and g["saida"] == 2 and "1080x1920" in g["motivo"]
    assert formato_do_laudo(g) == []


def test_leitor_que_estoura_vira_erro_de_insumo_e_nao_traceback(tmp_path):
    def quebra(o, t):
        raise OSError("ffmpeg não decodificou o overlay")
    g = depois(timeline(), tmp_path, quebra)
    assert g["resultado"] == "ERRO" and g["saida"] == 2 and "ffmpeg" in g["motivo"]


def test_overlay_inexistente_vira_erro_de_insumo(tmp_path):
    g = gate_safezone.rodar_depois(tmp_path / "nao-existe.mov", timeline())
    assert g["resultado"] == "ERRO" and g["saida"] == 2 and "nao-existe.mov" in g["motivo"]


def test_formato_1x1_e_pulado_tambem_depois(tmp_path):
    tl = timeline()
    tl["formato"] = "1x1"
    g = depois(tl, tmp_path, leitor_do_plano(tl))
    assert g["resultado"] == "PULADO" and g["saida"] == 0


# =================================================================================== linha de comando

def _gravar(tmp_path, tl):
    p = tmp_path / "timeline.json"
    p.write_text(json.dumps(tl), encoding="utf-8")
    return p


def test_cli_antes_sai_0_1_ou_2(tmp_path, capsys):
    tl = _gravar(tmp_path, timeline())
    assert gate_safezone.main(["antes", "--timeline", str(tl)]) == 0
    assert "PASSA" in capsys.readouterr().out
    faixas = tmp_path / "faixas.json"
    faixas.write_text(json.dumps([{"elemento": "cta", "id": "pill", "x1": 960}]), encoding="utf-8")
    assert gate_safezone.main(["antes", "--timeline", str(tl), "--faixas", str(faixas)]) == 1
    assert "REPROVA" in capsys.readouterr().out
    assert gate_safezone.main(["antes", "--timeline", str(tmp_path / "nao-existe.json")]) == 2
    assert "ERRO de insumo" in capsys.readouterr().err


def test_cli_antes_json_imprime_o_gate_do_laudo(tmp_path, capsys):
    tl = _gravar(tmp_path, timeline())
    assert gate_safezone.main(["antes", "--timeline", str(tl), "--json"]) == 0
    g = json.loads(capsys.readouterr().out)
    assert g["nome"] == "gate_safezone" and g["resultado"] == "PASS"


def test_cli_depois_sai_0_1_ou_2(tmp_path, capsys, monkeypatch):
    tl_dict = timeline()
    tl = _gravar(tmp_path, tl_dict)
    ovl = tmp_path / "overlay.mov"
    ovl.write_bytes(b"x")
    monkeypatch.setattr(gate_safezone, "ler_overlay_padrao", leitor_do_plano(tl_dict))
    assert gate_safezone.main(["depois", "--timeline", str(tl), "--overlay", str(ovl)]) == 0
    monkeypatch.setattr(gate_safezone, "ler_overlay_padrao",
                        leitor_do_plano(tl_dict, {"cta": (600, 1450, 960, 1650)}))
    assert gate_safezone.main(["depois", "--timeline", str(tl), "--overlay", str(ovl)]) == 1
    assert "REPROVA" in capsys.readouterr().out
    assert gate_safezone.main(["depois", "--timeline", str(tl), "--overlay", str(tmp_path / "x.mov")]) == 2


# =================================================================================== render de verdade

def _overlay_mov(tmp_path, nome, caixas):
    """Um .mov com alfa (ProRes 4444), 1080x1920 a 10 quadros/s, 2 s; `caixas` = [(x, y, w, h, ate_o_segundo)]
    desenhadas em branco opaco sobre fundo transparente."""
    filtros = ["drawbox=x=%d:y=%d:w=%d:h=%d:color=white@1.0:t=fill:replace=1:enable='lt(t,%s)'" % (x, y, w, h, ate)
               for x, y, w, h, ate in caixas]
    saida = tmp_path / nome
    # `format=rgba` tem que estar DENTRO da entrada lavfi: depois dela o alfa do color já se perdeu (yuv420p)
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
           "color=c=black@0.0:s=1080x1920:r=10:d=2,format=rgba",
           "-vf", ",".join(filtros), "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
           str(saida)]
    subprocess.run(cmd, check=True, capture_output=True)
    return saida


@pytest.mark.lento
def test_render_de_verdade_o_leitor_padrao_acha_a_tinta_pelo_alfa(tmp_path):
    ovl = _overlay_mov(tmp_path, "certo.mov", [(200, 1400, 680, 80, 2.1)])
    tl = tl_curta()
    g = gate_safezone.rodar_depois(ovl, tl, instantes=[0.5, 1.4])
    assert g["resultado"] == "PASS", g.get("motivo")
    for m in g["medido"]["instantes"]:
        assert 1470 <= m["y_max"] <= 1480 and 870 <= m["x_max"] <= 880, m       # a caixa desenhada
        assert m["px_na_faixa_meta"] > 0


@pytest.mark.lento
def test_render_de_verdade_lettering_em_y_1700_reprova(tmp_path):
    ovl = _overlay_mov(tmp_path, "baixo.mov", [(200, 1650, 680, 60, 2.1)])
    g = gate_safezone.rodar_depois(ovl, tl_curta(), instantes=[1.4])
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert g["medido"]["instantes"][0]["y_max"] >= 1700


@pytest.mark.lento
def test_render_de_verdade_cta_em_x_960_reprova(tmp_path):
    ovl = _overlay_mov(tmp_path, "direita.mov", [(600, 1450, 361, 200, 2.1)])
    g = gate_safezone.rodar_depois(ovl, tl_curta(), instantes=[1.4])
    assert g["resultado"] == "REPROVA"
    assert g["medido"]["instantes"][0]["x_max"] >= 960


@pytest.mark.lento
def test_render_de_verdade_o_instante_vem_do_quadro_certo(tmp_path):
    """A tinta ruim só existe até 1,0 s: o instante de 0,5 s reprova e o de 1,4 s passa. Prova que o seek é
    no quadro do instante pedido (e não no primeiro nem no último)."""
    ovl = _overlay_mov(tmp_path, "so_no_comeco.mov", [(200, 1650, 680, 60, 1.0), (200, 1400, 680, 80, 2.1)])
    cedo = gate_safezone.rodar_depois(ovl, tl_curta(), instantes=[0.5])
    tarde = gate_safezone.rodar_depois(ovl, tl_curta(), instantes=[1.4])
    assert cedo["resultado"] == "REPROVA" and tarde["resultado"] == "PASS"
