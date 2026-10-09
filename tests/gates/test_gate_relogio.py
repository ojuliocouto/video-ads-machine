"""gate_relogio (W3.A, capacidade C14): footage e overlay no MESMO relógio, a timeline.json.

Reprova quando as janelas de split, o plano, os blocos ou as durações divergem em mais de 1 quadro (o
limite sai do `fps` da própria timeline, não de número redondo), ou quando o alinhamento em disco não é o
que a timeline cita (outra transcrição). Saídas: 0 passa, 1 reprova, 2 insumo inválido.

O mutante pedido no plano: a timeline editada à mão com uma janela deslocada 2 quadros REPROVA, porque a
footage e o overlay que saíram dela não batem mais com o que ela diz.
"""
import copy
import json
from pathlib import Path

import pytest

from footage import blocos as BL
from gates import gate_relogio as G
from tests.timeline.test_construir import Mundo
from timeline import construir as TC

QUADRO = 1.0 / 30


class Artefatos(object):
    """Timeline + o que a footage e o overlay gravariam a partir dela (coerentes entre si)."""

    def __init__(self, base):
        self.m = Mundo(base)
        tl = self.m.timeline
        plano = TC.plano_do_motor(tl, self.m.blocks, self.m.inserts_map, BL.achar_insert)
        a0, total = tl["relogio"]["a0"], tl["duracao_s"]
        self.ritmo = {"segs": json.loads(json.dumps(plano)), "total": total}
        self.timing = {"a0": a0, "total": total, "xf": 0.08, "avatar": str(self.m.avatar), "inserts": [],
                       "letterings": []}
        self.prancha = {"total": round(total, 2),
                        "blocos": [{"i": b["i"], "s": round(b["s"], 2), "e": round(b["e"], 2)} for b in tl["blocos"]]}
        self.janelas = {"segs": [{"s": j["s"], "e": j["e"], "layout": "split"} for j in tl["janelas_split"]]}
        self.ovl = Path(base) / "ovl"
        self.ovl.mkdir()
        self.gravar()

    @property
    def tl(self):
        return json.loads(self.m.caminho_timeline.read_text(encoding="utf-8"))

    def gravar(self, tl=None):
        if tl is not None:
            self.m.caminho_timeline.write_text(json.dumps(tl), encoding="utf-8")
        (self.m.output / "f_ritmo.json").write_text(json.dumps(self.ritmo), encoding="utf-8")
        (self.m.output / "timing.json").write_text(json.dumps(self.timing), encoding="utf-8")
        (self.ovl / "prancha.json").write_text(json.dumps(self.prancha), encoding="utf-8")
        (self.ovl / "janelas_split.json").write_text(json.dumps(self.janelas), encoding="utf-8")

    def argv(self, *extra):
        return ["--timeline", str(self.m.caminho_timeline), "--footage-ritmo", str(self.m.output / "f_ritmo.json"),
                "--footage-timing", str(self.m.output / "timing.json"), "--overlay-dir", str(self.ovl), *extra]


@pytest.fixture
def art(tmp_path):
    return Artefatos(tmp_path)


def test_coerente_passa(art, capsys):
    assert G.main(art.argv()) == 0
    assert "RELOGIO OK" in capsys.readouterr().out


def test_o_fixture_tem_janela_de_split_para_o_mutante_mexer(art):
    assert art.tl["janelas_split"], "sem janela de split o mutante abaixo não prova nada"


@pytest.mark.parametrize("quadros", [2, -2])
def test_mutante_timeline_editada_com_janela_deslocada_2_quadros_reprova(art, capsys, quadros):
    tl = art.tl
    tl["janelas_split"][0]["s"] = round(tl["janelas_split"][0]["s"] + quadros * QUADRO, 4)
    tl["janelas_split"][0]["e"] = round(tl["janelas_split"][0]["e"] + quadros * QUADRO, 4)
    art.gravar(tl)
    assert TC.ler(art.m.caminho_timeline), "a timeline mutada continua válida no contrato: quem pega é o gate"
    assert G.main(art.argv()) == 1
    out = capsys.readouterr().out
    assert "RELOGIO REPROVA" in out and "janela" in out


def test_ate_1_quadro_de_diferenca_ainda_passa(art):
    tl = art.tl
    tl["janelas_split"][0]["s"] = round(tl["janelas_split"][0]["s"] + QUADRO * 0.99, 6)
    art.gravar(tl)
    assert G.main(art.argv()) == 0


def test_segmento_do_plano_deslocado_2_quadros_reprova(art, capsys):
    i = 2
    art.ritmo["segs"][i]["s"] = round(art.ritmo["segs"][i]["s"] + 2 * QUADRO, 4)
    art.ritmo["segs"][i - 1]["e"] = art.ritmo["segs"][i]["s"]
    art.gravar()
    assert G.main(art.argv()) == 1
    assert "plano" in capsys.readouterr().out


def test_plano_da_footage_com_outro_numero_de_planos_reprova(art, capsys):
    art.ritmo["segs"] = art.ritmo["segs"][:-1]
    art.gravar()
    assert G.main(art.argv()) == 1
    assert "plano" in capsys.readouterr().out


def test_layout_trocado_num_plano_reprova(art):
    seg = next(s for s in art.ritmo["segs"] if s.get("layout") == "split")
    seg["layout"] = "cheio"
    art.gravar()
    assert G.main(art.argv()) == 1


def test_duracao_do_overlay_2_quadros_alem_reprova(art, capsys):
    art.prancha["total"] = round(art.prancha["total"] + 2 * QUADRO, 3)
    art.gravar()
    assert G.main(art.argv()) == 1
    assert "dura" in capsys.readouterr().out


def test_bloco_do_overlay_deslocado_reprova(art, capsys):
    art.prancha["blocos"][2]["s"] = round(art.prancha["blocos"][2]["s"] + 0.1, 2)
    art.gravar()
    assert G.main(art.argv()) == 1
    assert "bloco" in capsys.readouterr().out


def test_a0_da_footage_diferente_reprova(art):
    art.timing["a0"] = round(art.timing["a0"] + 0.1, 3)
    art.gravar()
    assert G.main(art.argv()) == 1


def test_duracao_medida_da_footage_entra_quando_passada(art, monkeypatch):
    tl = art.tl
    dur = tl["duracao_s"] - tl["relogio"]["a0"]
    mp4 = art.m.output / "f.mp4"
    mp4.write_bytes(b"x")
    monkeypatch.setattr(G, "medir_duracao", lambda p: dur + 0.5 * QUADRO)
    assert G.main(art.argv("--footage-mp4", str(mp4))) == 0
    monkeypatch.setattr(G, "medir_duracao", lambda p: dur + 2 * QUADRO)
    assert G.main(art.argv("--footage-mp4", str(mp4))) == 1


def test_duracao_medida_do_overlay_entra_quando_passada(art, monkeypatch):
    tl = art.tl
    mov = art.ovl / "o.mov"
    mov.write_bytes(b"x")
    monkeypatch.setattr(G, "medir_duracao", lambda p: tl["duracao_s"])
    assert G.main(art.argv("--overlay-mov", str(mov))) == 0
    monkeypatch.setattr(G, "medir_duracao", lambda p: tl["duracao_s"] + 3 * QUADRO)
    assert G.main(art.argv("--overlay-mov", str(mov))) == 1


def test_alinhamento_trocado_em_disco_reprova(art, capsys):
    al = json.loads(art.m.caminho_alinhamento.read_text(encoding="utf-8"))
    al["palavras"][0]["s"] += 0.01
    art.m.caminho_alinhamento.write_text(json.dumps(al), encoding="utf-8")
    assert G.main(art.argv()) == 1
    assert "alinhamento" in capsys.readouterr().out


def test_o_limite_e_1_quadro_do_fps_da_timeline_nao_numero_redondo(art):
    """0,035 s passa a 25 quadros por segundo (limite 0,04) e reprova a 30 (limite 0,0333)."""
    base = art.tl
    for fps, esperado in ((30, 1), (25, 0)):
        tl = copy.deepcopy(base)
        tl["relogio"]["fps"] = fps
        tl["janelas_split"][0]["s"] = round(tl["janelas_split"][0]["s"] + 0.035, 4)
        art.gravar(tl)
        assert G.main(art.argv()) == esperado, fps
    assert G.limite_s({"relogio": {"fps": 25}}) == pytest.approx(0.04)


def test_insumo_ausente_sai_com_2_sem_traceback(art, capsys):
    (art.ovl / "prancha.json").unlink()
    assert G.main(art.argv()) == 2
    err = capsys.readouterr()
    assert "prancha.json" in err.out + err.err and "Traceback" not in err.out + err.err


def test_timeline_fora_do_contrato_sai_com_2(art):
    tl = art.tl
    tl["relogio"]["base"] = "overlay"
    art.gravar(tl)
    assert G.main(art.argv()) == 2


def test_json_quebrado_sai_com_2(art):
    (art.m.output / "f_ritmo.json").write_text("{", encoding="utf-8")
    assert G.main(art.argv()) == 2


def test_checar_devolve_a_lista_de_falhas_vazia_quando_coerente(art):
    falhas = G.checar(art.tl, ritmo=art.ritmo, timing=art.timing, prancha=art.prancha, janelas=art.janelas,
                      sha_alinhamento=art.tl["fontes"]["alinhamento_sha256"])
    assert falhas == []
