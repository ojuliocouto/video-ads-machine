"""W5.X, pendência (b) da W5.A: o punch de câmera não estava ligado. A timeline saía com `camera` vazia e o
gate_camera passava só com o zoom contínuo; o `filtros_avatar.cmd_orig` já sabia desenhar o punch, ninguém pedia.

Invariantes:
  - a timeline do montar traz o plano de câmera (`cinema.camera.planejar`): a KEY "O MELHOR" do e2e, num bloco de
    apresentador, ganha o punch (no render real da W5.A: 10,4 s de footage, 7,41 s entregues);
  - o render do plano de apresentador recebe os punches dele, em tempo relativo ao plano;
  - a chave do cache do segmento muda com o punch (lição do cache com insumo fora da chave: um plano renderizado
    sem punch não pode voltar do cache quando o plano passa a ter punch), e sem punch ela é a mesma de antes.
"""
import json
from pathlib import Path

import cache_segmento
from footage import render_segmentos as RS
from timeline import construir as TC

RAIZ = Path(__file__).resolve().parents[2]
PUNCH = {"t": 10.4, "tipo": "punch", "de": 1.0, "para": 1.22, "dur": 0.28, "segura": 1.92}


def _chave(**extra):
    base = dict(tipo="orig", narr="sabe qual é", s=9.6, e=12.24, ee=12.32, base=1.0, layout=None, insert_cfg=None,
                fonte_stat=(1.0, 10), versao="v")
    base.update(extra)
    return cache_segmento.chave_segmento(**base)


def test_chave_do_cache_muda_com_o_punch_e_sem_punch_e_a_de_antes():
    assert _chave() == _chave(punches=None) == _chave(punches=[])
    assert _chave(punches=[dict(PUNCH, t=0.8)]) != _chave()


def test_render_do_plano_de_apresentador_recebe_o_punch_relativo(monkeypatch, tmp_path):
    vistos = []
    monkeypatch.setattr(RS, "r_orig", lambda avatar, s, e, out, idx=0, base=1.0, punches=None:
                        vistos.append((s, punches)))
    ctx = RS.Contexto(avatar="a.mp4", tmp=str(tmp_path), tr=None, inserts={}, dir_molduras="", dir_gerados="",
                      cache=False, camera=[PUNCH])
    blocks = [{"type": "orig", "_base": 1.0, "narr": "x", "instr": "apresentador"}]
    monkeypatch.setattr(RS.CA, "xf_dur", lambda *a: 0.0)
    RS._renderizar_um(0, blocks, [(9.6, 12.24)], ctx, str(tmp_path))
    assert vistos == [(9.6, [dict(PUNCH, t=0.8)])]


def test_timeline_do_montar_traz_o_punch_da_key():
    tl = json.loads((RAIZ / "contratos" / "exemplos" / "timeline.valido.json").read_text(encoding="utf-8"))
    tl["camera"] = []
    com = TC.com_camera(tl)
    assert any(e["tipo"] == "punch" for e in com["camera"])
    assert any(e["tipo"] == "zoom" for e in com["camera"])
