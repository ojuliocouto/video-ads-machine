"""W7.Z: a troca de legenda é SECA quando um grupo substitui outro no mesmo lugar.

O grupo novo entrava com opacidade 0 a 1 em 0,18 s e o velho saía em 0,1 s: nos quadros da troca os dois eram texto de
meia opacidade, um em cima do outro, sobre o fundo do vídeo (camisa laranja, costura do split). O gate de contraste achou
1,0:1 a 1,3:1 nessas amostras (25,40 s, 28,00 s e 29,80 s da prova) e reprovou o anúncio. Cada legenda lia bem antes e
depois; o defeito era a troca. A regra, no `timeline.js`:

  - grupo COLADO no anterior (a menos de 0,05 s): entra na hora, com opacidade cheia (só a escala faz o pop);
  - grupo que o PRÓXIMO substitui sem pausa: sai cortado em `gEnd`, sem esmaecer;
  - grupo que nasce depois de uma pausa e vai embora para uma pausa: mantém o fade (o gate perdoa a dissolução quando o
    texto não está do outro lado)."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
JS = (RAIZ / "templates" / "_parciais" / "timeline.js").read_text(encoding="utf-8")

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node não está instalado")


def decidir(**kw):
    """Roda a `transicaoDaLegenda` do timeline.js no node."""
    m = re.search(r"function transicaoDaLegenda\(.*?\n      \}\n", JS, re.S)
    assert m, "o timeline.js não tem a função transicaoDaLegenda"
    args = {"gStart": 10.0, "gEnd": 11.0, "fimAnterior": None, "inicioProximo": None, "semLead": False}
    args.update(kw)
    codigo = m.group(0) + "\nconsole.log(JSON.stringify(transicaoDaLegenda(%s)));" % json.dumps(args)
    r = subprocess.run(["node", "-e", codigo], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def test_grupo_colado_no_anterior_entra_seco_e_na_hora():
    t = decidir(fimAnterior=10.0)
    assert t["entradaSeca"] is True and t["gIn"] == 10.0


def test_grupo_colado_com_folga_de_ate_0_05_s_conta_como_colado():
    assert decidir(fimAnterior=9.96)["entradaSeca"] is True
    assert decidir(fimAnterior=9.90)["entradaSeca"] is False


def test_grupo_depois_de_pausa_antecipa_0_12_s_e_esmaece_como_antes():
    t = decidir(fimAnterior=9.0)
    assert t["entradaSeca"] is False and t["gIn"] == pytest.approx(9.88)


def test_primeiro_grupo_nao_e_colado():
    t = decidir(fimAnterior=None)
    assert t["entradaSeca"] is False and t["gIn"] == pytest.approx(9.88)


def test_grupo_sem_lead_entra_na_hora_com_fade_como_antes():
    t = decidir(fimAnterior=8.0, semLead=True)
    assert t["gIn"] == 10.0 and t["entradaSeca"] is False


def test_grupo_que_o_proximo_substitui_sem_pausa_sai_cortado():
    assert decidir(inicioProximo=11.0)["saidaSeca"] is True
    assert decidir(inicioProximo=11.04)["saidaSeca"] is True


def test_grupo_que_vai_para_uma_pausa_esmaece():
    assert decidir(inicioProximo=11.5)["saidaSeca"] is False
    assert decidir(inicioProximo=None)["saidaSeca"] is False


def test_o_agendamento_usa_a_decisao_nos_dois_lados():
    """A função só vale se o agendamento a usa: entrada seca = opacidade cheia no `gIn`; saída seca = corte em `gEnd`."""
    assert "transicaoDaLegenda(" in JS and "entradaSeca" in JS and "saidaSeca" in JS
    assert re.search(r"if \(\w+\.entradaSeca\)[^}]*opacity: 1", JS)
    assert re.search(r"if \(!?\w+\.saidaSeca\)", JS)
