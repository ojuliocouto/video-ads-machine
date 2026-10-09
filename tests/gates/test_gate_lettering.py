"""W4.D: gate_lettering (capacidades C7 e C9). Cada limite reprova o seu mutante.

C7, lettering de pico: 2 a 3 KEYs no meio + 1 KEY de CTA; intervalo de pelo menos 8 s ENTREGUES entre letterings
(a pilha conta como um só); KEY sem conector no fim e com no máximo 2 linhas; nunca junto com legenda; tinta da KEY
em +0,15 s da entrada com pelo menos 90% da tinta assentada.
C9, elemento de atenção: a seta do CTA se mexe (movimento medido no overlay).

Duas etapas, dois nomes de laudo: `gate_lettering` (antes, sobre a timeline) e `gate_lettering_depois` (sobre o
overlay com alfa). Os testes rápidos desenham o overlay com numpy; nenhum ffmpeg.
"""
import copy
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from cinema import lettering_estilos as E
from contratos import validar
from gates import gate_lettering as G

RAIZ = Path(__file__).resolve().parents[2]
LAUDO_VALIDO = RAIZ / "contratos" / "exemplos" / "laudo.valido.json"
TIMELINE_VALIDA = RAIZ / "contratos" / "exemplos" / "timeline.valido.json"


def tl_boa():
    """A timeline válida do contrato, esticada para os intervalos passarem (aceleração 1,35: 8 s entregues são
    10,8 s de footage). Três letterings no meio (um deles é a pilha de 3 linhas) e o de CTA."""
    tl = copy.deepcopy(json.loads(TIMELINE_VALIDA.read_text(encoding="utf-8")))
    tl["duracao_s"] = 60.0
    tl["letterings"] = [
        {"id": "l0", "bloco": 2, "lead": "o problema não é", "key": "FALTA DE TEMPO", "s": 6.4, "d": 2.2,
         "estilo": "caixa_nativa", "split": False, "baixo": False, "pilha": None, "cta": False},
        {"id": "l1", "bloco": 4, "lead": "enquanto isso", "key": "a proposta atrasa", "s": 18.0, "d": 4.3,
         "estilo": "serif_editorial", "split": False, "baixo": False, "pilha": "b4", "cta": False},
        {"id": "l2", "bloco": 4, "lead": None, "key": "o cliente esfria", "s": 19.3, "d": 3.0,
         "estilo": "serif_editorial", "split": False, "baixo": False, "pilha": "b4", "cta": False},
        {"id": "l3", "bloco": 4, "lead": None, "key": "você perde a venda", "s": 20.5, "d": 1.8,
         "estilo": "serif_editorial", "split": False, "baixo": False, "pilha": "b4", "cta": False},
        {"id": "l4", "bloco": 5, "lead": "economiza", "key": "*20 HORAS* POR SEMANA", "s": 31.0, "d": 2.2,
         "estilo": "marcador", "split": False, "baixo": False, "pilha": None, "cta": False},
        {"id": "l5", "bloco": 6, "lead": "toque em", "key": "SAIBA MAIS", "s": 43.0, "d": 3.3,
         "estilo": "seta_cta", "split": False, "baixo": False, "pilha": None, "cta": True},
    ]
    janelas = [(l["s"], l["s"] + l["d"]) for l in tl["letterings"]]
    leg = []
    t = 0.5
    while t < 58.0:
        e = round(t + 1.5, 2)
        leg.append({"s": round(t, 2), "e": e, "texto": "fala", "posicao": "padrao",
                    "suprimida": any(a < e and t < b for a, b in janelas),
                    "palavras": [{"t": "fala", "s": round(t, 2), "e": e}]})
        t = e
    tl["legendas"] = leg
    tl["cta"] = {"inicio": 42.8, "logo": 43.0, "label": "saiba mais", "sem_lead": False}
    tl["janelas_split"] = []
    return tl


def _l(tl, i):
    return tl["letterings"][i]


def formato_do_laudo(g):
    laudo = json.loads(LAUDO_VALIDO.read_text(encoding="utf-8"))
    laudo["gates"] = [x for x in laudo["gates"] if x["nome"] != g["nome"]] + [g]
    k = len(laudo["gates"]) - 1
    return [e for e in validar.validar("laudo", laudo) if ("gates[%d]" % k) in e.caminho]


# --- antes: a timeline ---------------------------------------------------------------------------

def test_timeline_boa_passa():
    g = G.rodar_antes(tl_boa())
    assert g["resultado"] == "PASS", g.get("motivo")
    assert g["saida"] == 0 and g["nome"] == "gate_lettering" and g["etapa"] == "antes"
    assert g["medido"]["keys_no_meio"] == 3 and g["medido"]["keys_cta"] == 1
    assert not formato_do_laudo(g)


def test_uma_key_so_reprova():
    tl = tl_boa()
    tl["letterings"] = [_l(tl, 0), _l(tl, 5)]
    g = G.rodar_antes(tl)
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert "contagem" in g["motivo"]


def test_quatro_keys_reprova():
    tl = tl_boa()
    extra = dict(_l(tl, 0), id="lx", s=55.0, d=2.0, key="MAIS UMA")
    tl["letterings"].insert(5, extra)
    tl["letterings"][-1]["s"] = 43.0
    g = G.rodar_antes(tl)
    assert g["resultado"] == "REPROVA" and "contagem" in g["motivo"]


def test_sem_key_de_cta_reprova():
    """Nem lettering de CTA nem texto no botão (W5.A: a KEY do cta pode ser o texto do botão)."""
    tl = tl_boa()
    tl["letterings"] = tl["letterings"][:5]
    tl["cta"]["label"] = " "
    g = G.rodar_antes(tl)
    assert g["resultado"] == "REPROVA" and "CTA" in g["motivo"]


def test_intervalo_abaixo_de_8s_entregues_reprova():
    tl = tl_boa()
    _l(tl, 4)["s"] = 20.5 + 10.0          # 18,0 -> 30,5: 12,5 s de footage = 9,26 s entregues, passa
    assert G.rodar_antes(tl)["resultado"] == "PASS"
    _l(tl, 4)["s"] = 18.0 + 10.5          # 10,5 s de footage = 7,78 s entregues: reprova
    g = G.rodar_antes(tl)
    assert g["resultado"] == "REPROVA" and "intervalo" in g["motivo"]


def test_linhas_da_pilha_nao_contam_como_intervalo():
    tl = tl_boa()
    assert _l(tl, 2)["s"] - _l(tl, 1)["s"] < 2.0     # 1,3 s entre linhas da mesma pilha
    assert G.rodar_antes(tl)["resultado"] == "PASS"


def test_key_terminada_em_conector_reprova():
    tl = tl_boa()
    _l(tl, 0)["key"] = "FALTA DE"
    g = G.rodar_antes(tl)
    assert g["resultado"] == "REPROVA" and "conector" in g["motivo"]


def test_key_com_mais_de_2_linhas_reprova():
    tl = tl_boa()
    _l(tl, 0)["key"] = "ISSO AQUI É UMA FRASE LONGA DEMAIS PARA UM LETTERING DE PICO NA TELA"
    g = G.rodar_antes(tl)
    assert g["resultado"] == "REPROVA" and "linhas" in g["motivo"]


def test_sobreposicao_com_legenda_reprova():
    tl = tl_boa()
    for leg in tl["legendas"]:
        if leg["s"] < 8.6 and 6.4 < leg["e"]:
            leg["suprimida"] = False
    g = G.rodar_antes(tl)
    assert g["resultado"] == "REPROVA" and "legenda" in g["motivo"]


def test_excecao_com_motivo_libera_contagem_e_intervalo_mas_nunca_a_legenda():
    tl = tl_boa()
    tl["letterings"] = [_l(tl, 0), _l(tl, 5)]
    proj = {"excecoes": [{"regra": "lettering.contagem", "motivo": "anúncio de 15 s, uma KEY só por decisão do diretor"}]}
    g = G.rodar_antes(tl, proj)
    assert g["resultado"] == "PASS", g.get("motivo")
    assert any("exceção" in a for a in g["medido"]["avisos"])
    for leg in tl["legendas"]:
        if leg["s"] < 8.6 and 6.4 < leg["e"]:
            leg["suprimida"] = False
    proj["excecoes"].append({"regra": "lettering.legenda", "motivo": "tentando liberar o que não se libera"})
    assert G.rodar_antes(tl, proj)["resultado"] == "REPROVA"


def test_excecao_sem_motivo_nao_vale():
    tl = tl_boa()
    tl["letterings"] = [_l(tl, 0), _l(tl, 5)]
    assert G.rodar_antes(tl, {"excecoes": [{"regra": "lettering.contagem", "motivo": ""}]})["resultado"] == "REPROVA"


def test_lettering_em_cima_do_cta_vira_relato():
    tl = tl_boa()
    _l(tl, 5)["s"] = 42.0       # o CTA sobe em 42,8: o lettering de CTA entra antes e fica por cima
    g = G.rodar_antes(tl)
    assert any("CTA" in a for a in g["medido"]["avisos"])


def test_estilo_novo_em_split_vira_relato():
    tl = tl_boa()
    _l(tl, 0)["split"] = True
    _l(tl, 0)["estilo"] = "punch"
    g = G.rodar_antes(tl)
    assert any("split" in a for a in g["medido"]["avisos"])


def test_timeline_sem_letterings_e_erro_de_insumo():
    tl = tl_boa()
    del tl["letterings"]
    g = G.rodar_antes(tl)
    assert g["resultado"] == "ERRO" and g["saida"] == 2


def test_timeline_1x1_sai_pulado():
    tl = tl_boa()
    tl["formato"] = "1x1"
    assert G.rodar_antes(tl)["resultado"] == "PULADO"


# --- depois: o overlay (tinta pelo alfa) ---------------------------------------------------------

def _leitor(tl, fracao_015=1.0, seta_move=True, faixa_seta=None):
    """Overlay sintético: cada lettering pinta um bloco de tinta na faixa do estilo; em +0,15 s ainda só
    `fracao_015` dele. O CTA pinta a pílula e a seta, que desce 8 px num ciclo de 0,9 s (ou fica parada)."""
    fs = faixa_seta or E.FAIXAS["cta_seta"]

    def ler(_overlay, t):
        q = np.zeros((1920, 1080, 4), dtype=np.uint8)
        for l in tl["letterings"]:
            s, e = l["s"], l["s"] + l["d"]
            if not (s <= t < e):
                continue
            f = E.faixa(l["estilo"], split=l["split"], pilha=bool(l["pilha"]))
            y0, y1 = f["y0"] + 20, f["y0"] + 120
            fr = fracao_015 if t - s < 0.3 else 1.0
            x1 = int(f["x0"] + 10 + (f["x1"] - f["x0"] - 20) * fr)
            q[y0:y1, f["x0"] + 10:x1, 3] = 255
        cta = tl["cta"]["inicio"]
        if t >= cta:
            q[fs["y0"] + 10:fs["y0"] + 60, fs["x0"] + 20:fs["x0"] + 300] = 255     # a pílula (branca), parada
            dy = int(round(8 * abs(np.sin((t - cta) * np.pi / 0.9)))) if seta_move else 0
            q[fs["y0"] + 20 + dy:fs["y0"] + 50 + dy, fs["x0"] + 320:fs["x0"] + 372] = 255
        return q
    return ler


def test_depois_overlay_bom_passa(tmp_path):
    tl = tl_boa()
    g = G.rodar_depois(tmp_path / "o.mov", tl, leitor_overlay=_leitor(tl))
    assert g["resultado"] == "PASS", g.get("motivo")
    assert g["nome"] == "gate_lettering_depois" and g["etapa"] == "depois"
    assert all(m["fracao_015"] >= 0.9 for m in g["medido"]["legibilidade"])
    assert g["medido"]["seta_cta"]["movimento_px"] >= G.SETA_MIN_PX
    assert not formato_do_laudo(g)


def test_depois_key_ainda_entrando_em_015s_reprova(tmp_path):
    tl = tl_boa()
    g = G.rodar_depois(tmp_path / "o.mov", tl, leitor_overlay=_leitor(tl, fracao_015=0.80))
    assert g["resultado"] == "REPROVA" and "0,15" in g["motivo"]


def test_depois_seta_parada_reprova(tmp_path):
    tl = tl_boa()
    g = G.rodar_depois(tmp_path / "o.mov", tl, leitor_overlay=_leitor(tl, seta_move=False))
    assert g["resultado"] == "REPROVA" and "seta" in g["motivo"]


def test_depois_lettering_sem_tinta_reprova(tmp_path):
    tl = tl_boa()
    vazio = lambda _o, _t: np.zeros((1920, 1080, 4), dtype=np.uint8)   # noqa: E731
    g = G.rodar_depois(tmp_path / "o.mov", tl, leitor_overlay=vazio)
    assert g["resultado"] == "REPROVA" and "sem tinta" in g["motivo"]


def test_depois_overlay_inexistente_e_erro(tmp_path):
    g = G.rodar_depois(tmp_path / "nao.mov", tl_boa())
    assert g["resultado"] == "ERRO" and g["saida"] == 2


# --- linha de comando ----------------------------------------------------------------------------

def test_cli_antes_json(tmp_path):
    p = tmp_path / "timeline.json"
    p.write_text(json.dumps(tl_boa()), encoding="utf-8")
    r = subprocess.run([sys.executable, str(RAIZ / "scripts" / "gates" / "gate_lettering.py"), "antes",
                        "--timeline", str(p), "--json"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["resultado"] == "PASS"


def test_cli_antes_reprova_sai_1(tmp_path):
    tl = tl_boa()
    _l(tl, 0)["key"] = "FALTA DE"
    p = tmp_path / "timeline.json"
    p.write_text(json.dumps(tl), encoding="utf-8")
    r = subprocess.run([sys.executable, str(RAIZ / "scripts" / "gates" / "gate_lettering.py"), "antes",
                        "--timeline", str(p)], capture_output=True, text=True)
    assert r.returncode == 1 and "REPROVA" in r.stdout


def test_cli_timeline_ilegivel_sai_2(tmp_path):
    p = tmp_path / "timeline.json"
    p.write_text("{nao é json", encoding="utf-8")
    r = subprocess.run([sys.executable, str(RAIZ / "scripts" / "gates" / "gate_lettering.py"), "antes",
                        "--timeline", str(p)], capture_output=True, text=True)
    assert r.returncode == 2


# --- W5.A: o CTA do template de verdade ------------------------------------------------------------------

def test_key_do_cta_pode_ser_o_texto_do_botao():
    """A KEY do cta é o texto do botão (contrato do roteiro): a timeline traz a pílula (`cta.label`) e nenhum lettering
    com `cta: true`. Isso não é "nenhuma KEY de CTA", e o intervalo segue contando até a subida do CTA."""
    tl = tl_boa()
    tl["letterings"] = tl["letterings"][:5]
    tl["cta"]["label"] = "SAIBA MAIS"
    g = G.rodar_antes(tl)
    assert g["resultado"] == "PASS", g.get("motivo")
    tl["cta"]["inicio"] = 33.0                       # 2 s depois da KEY de 31,0 s: intervalo curto
    g = G.rodar_antes(tl)
    assert g["resultado"] == "REPROVA" and "intervalo" in g["motivo"] and "SAIBA MAIS" in g["motivo"]


def _leitor_com_scrim(tl, seta_move=True):
    """O CTA do template: scrim radial ESCURO e opaco (alfa acima de 190 no centro) atrás da pílula, e a seta branca."""
    base = _leitor(tl, seta_move=seta_move)
    fs = E.FAIXAS["cta_seta"]

    def ler(o, t):
        q = base(o, t)
        if t >= tl["cta"]["inicio"]:
            escuro = q[fs["y0"]:fs["y1"], fs["x0"]:fs["x1"]]
            fundo = escuro[..., 3] < 190
            escuro[fundo] = (4, 5, 10, 230)              # o scrim conta como tinta pelo alfa, e é escuro
        return q
    return ler


def test_seta_que_quica_sobre_o_scrim_opaco_do_cta_e_medida_pela_tinta_clara(tmp_path):
    tl = tl_boa()
    g = G.rodar_depois(tmp_path / "o.mov", tl, leitor_overlay=_leitor_com_scrim(tl))
    assert g["medido"]["seta_cta"]["movimento_px"] >= G.SETA_MIN_PX, g.get("motivo")
    g = G.rodar_depois(tmp_path / "o.mov", tl, leitor_overlay=_leitor_com_scrim(tl, seta_move=False))
    assert g["resultado"] == "REPROVA" and "seta" in g["motivo"]

