"""W4.A: gate_camera (capacidade C3). Mede a câmera no vídeo ENTREGUE, nunca no plano.

Reprova quando (limiares do plano, seção 3):
  - a caixa do rosto varia menos de 8% num plano de avatar de 2 s ou mais (câmera parada);
  - um punch não cresce +15% de escala MEDIDA (o punch declarado não existe na imagem);
  - passam mais de 20 s sem movimento de câmera.
Mais: punch declarado em insert ou em janela de split reprova (o C3 proíbe).

O gate devolve um dict no formato de gate do laudo (`contratos/laudo.schema.json`): PASS com saída 0,
REPROVA com saída 1 e motivo, ERRO com saída 2 quando o insumo é inválido.

Os testes rápidos usam um "render virtual": o leitor devolve, para cada instante ENTREGUE, a caixa do rosto
que o filtro de verdade produziria (o zoom do `filtros_avatar` multiplicado pelo fator do punch, avaliado
pelo mesmo avaliador). Sem ffmpeg e sem rosto. Os testes `lento` renderizam o filtro de verdade num
quadrado sintético e medem o vídeo.
"""
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from cinema import camera
from contratos import validar
from footage import filtros_avatar as FA
from gates import gate_camera

RAIZ = Path(__file__).resolve().parents[2]
LAUDO_VALIDO = RAIZ / "contratos" / "exemplos" / "laudo.valido.json"
ALTURA_ROSTO = 400.0


# =================================================================================== insumos sintéticos

def relogio(aceleracao=1.0, a0=0.0):
    return {"base": "footage_1x", "fps": 30, "aceleracao": aceleracao, "cauda_s": 0.0, "a0": a0}


def seg_avatar(s, e, bloco, base=1.0):
    return {"bloco": bloco, "tipo": "apresentador", "s": s, "e": e, "sub": 0, "de": 1, "base": base}


def seg_insert(s, e, bloco, layout="cheio"):
    return {"bloco": bloco, "tipo": "insert", "s": s, "e": e, "sub": 0, "de": 1, "layout": layout}


def timeline(segmentos, camera_=None, aceleracao=1.0, a0=0.0, janelas_split=()):
    dur = segmentos[-1]["e"]
    return {"relogio": relogio(aceleracao, a0), "duracao_s": dur, "segmentos": segmentos,
            "camera": list(camera_ or []), "janelas_split": list(janelas_split),
            "blocos": [{"i": sg["bloco"], "tipo": "insert" if sg["tipo"] == "insert" else "apresentador",
                        "insert": "x" if sg["tipo"] == "insert" else None, "s": sg["s"], "e": sg["e"]}
                       for sg in segmentos],
            "letterings": []}


def tl_padrao(aceleracao=1.0, a0=0.0):
    """Insert, avatar de 6 s, insert, avatar de 6 s. Zoom contínuo nos dois avatares e um punch no segundo."""
    segs = [seg_insert(0.0, 3.0, 0), seg_avatar(3.0, 9.0, 1), seg_insert(9.0, 14.0, 2, "split"),
            seg_avatar(14.0, 20.0, 3, 1.14)]
    cam = [{"t": 3.0, "tipo": "zoom", "de": 1.16, "para": 1.0, "dur": 6.0},
           {"t": 14.0, "tipo": "zoom", "de": 1.30, "para": 1.14, "dur": 6.0},
           camera.evento_punch(16.0, 1.5)]
    return timeline(segs, cam, aceleracao, a0, janelas_split=[{"s": 9.0, "e": 14.0}])


def leitor_virtual(tl, zoom=True, punch=True, tremido=0.0, seed=1):
    """Para cada instante entregue, a caixa do rosto que o filtro produziria. Insert: sem rosto (None)."""
    rel = tl["relogio"]
    acel, a0, fps = rel["aceleracao"], rel["a0"], rel["fps"]
    rng = np.random.RandomState(seed)
    segs = tl["segmentos"]
    punches = [e for e in tl["camera"] if e["tipo"] == "punch"] if punch else []

    def leitor(video, fps_amostra):
        dur_entregue = (tl["duracao_s"] - a0) / acel
        n = int(dur_entregue * fps_amostra)
        for i in range(n):
            td = i / float(fps_amostra)
            tf = td * acel + a0
            k = next((j for j, sg in enumerate(segs) if sg["s"] <= tf < sg["e"]), None)
            if k is None or segs[k]["tipo"] != "apresentador":
                yield td, None
                continue
            sg = segs[k]
            N = FA.nframes(sg["e"] - sg["s"])
            on = (tf - sg["s"]) * fps
            z = camera.avaliar(FA.expr_zoom(N, k, sg.get("base", 1.0)), on=on) if zoom else sg.get("base", 1.0)
            if punches:
                rel_ev = camera.eventos_do_segmento(punches, sg["s"], sg["e"])
                z *= camera.fator_total(rel_ev, tf - sg["s"], fps)
            h = ALTURA_ROSTO * z + (rng.uniform(-1, 1) * tremido * ALTURA_ROSTO)
            yield td, (100.0, 100.0, 0.7 * h, h)
    return leitor


def detector_identidade(quadro):
    return quadro


def rodar(tl, tmp_path, **kw):
    video = tmp_path / "final_9x16.mp4"
    video.write_bytes(b"x")                      # o leitor é injetado: o arquivo só precisa existir
    kw.setdefault("detector", detector_identidade)
    return gate_camera.rodar(video, tl, **kw)


def formato_do_laudo(g):
    """Os erros do contrato que dizem respeito a este gate (o resto do laudo não é assunto daqui)."""
    laudo = json.loads(LAUDO_VALIDO.read_text(encoding="utf-8"))
    laudo["gates"] = [x for x in laudo["gates"] if x["nome"] != g["nome"]] + [g]
    k = len(laudo["gates"]) - 1
    return [e for e in validar.validar("laudo", laudo) if ("gates[%d]" % k) in e.caminho]


# =================================================================================== passa

def test_camera_viva_passa_e_o_resultado_esta_no_formato_do_laudo(tmp_path):
    tl = tl_padrao()
    g = rodar(tl, tmp_path, leitor=leitor_virtual(tl))
    assert g["nome"] == "gate_camera" and g["etapa"] == "depois"
    assert g["resultado"] == "PASS" and g["saida"] == 0, g.get("motivo")
    assert "motivo" not in g or not g["motivo"]
    assert formato_do_laudo(g) == []
    m = g["medido"]
    assert [p["ok"] for p in m["planos"]] == [True, True]
    assert all(p["variacao"] >= camera.CAIXA_VARIACAO_MIN for p in m["planos"])
    (p,) = m["punches"]
    assert p["ok"] and 0.17 <= p["ganho"] <= 0.30           # 22% pedidos; o zoom contínuo mexe uns pontos
    assert m["parado"]["maior_s"] < camera.PARADO_MAX_S
    assert g["limiar"]["punch_ganho_min"] == 0.15 and g["limiar"]["caixa_variacao_min"] == 0.08
    assert g["limiar"]["parado_max_s"] == 20.0


def test_com_aceleracao_e_a0_o_punch_e_medido_no_instante_entregue(tmp_path):
    """O relógio da timeline é o da footage a 1x: o entregue é (t - a0) / aceleração."""
    tl = tl_padrao(aceleracao=1.35, a0=0.24)
    g = rodar(tl, tmp_path, leitor=leitor_virtual(tl))
    assert g["resultado"] == "PASS", g.get("motivo")
    (p,) = g["medido"]["punches"]
    assert p["t_entregue"] == pytest.approx((16.0 - 0.24) / 1.35, abs=0.01)
    assert p["ganho"] > 0.15


def test_tremido_pequeno_do_detector_nao_reprova_um_zoom_de_verdade(tmp_path):
    tl = tl_padrao()
    g = rodar(tl, tmp_path, leitor=leitor_virtual(tl, tremido=0.015))
    assert g["resultado"] == "PASS", g.get("motivo")


def test_o_cli_devolve_o_codigo_de_saida_do_gate(tmp_path, capsys, monkeypatch):
    tl = tl_padrao()
    (tmp_path / "timeline.json").write_text(json.dumps(tl), encoding="utf-8")
    video = tmp_path / "final.mp4"
    video.write_bytes(b"x")
    monkeypatch.setattr(gate_camera, "_leitor_padrao", lambda: leitor_virtual(tl))
    monkeypatch.setattr(gate_camera, "_detector_padrao", lambda: detector_identidade)
    assert gate_camera.main([str(video), "--timeline", str(tmp_path / "timeline.json")]) == 0
    assert "PASSA" in capsys.readouterr().out
    tl2 = tl_padrao()
    monkeypatch.setattr(gate_camera, "_leitor_padrao", lambda: leitor_virtual(tl2, zoom=False, punch=False))
    assert gate_camera.main([str(video), "--timeline", str(tmp_path / "timeline.json")]) == 1
    assert "REPROVA" in capsys.readouterr().out


# =================================================================================== mutantes: tudo isto TEM que reprovar

def test_mutante_sem_zoom_reprova(tmp_path):
    tl = tl_padrao()
    g = rodar(tl, tmp_path, leitor=leitor_virtual(tl, zoom=False, punch=False))
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert "plano de avatar" in g["motivo"] and "8%" in g["motivo"]
    assert [p["ok"] for p in g["medido"]["planos"]] == [False, False]
    assert formato_do_laudo(g) == []


def test_mutante_punch_declarado_que_nao_existe_na_imagem_reprova(tmp_path):
    tl = tl_padrao()
    g = rodar(tl, tmp_path, leitor=leitor_virtual(tl, zoom=True, punch=False))
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert "punch" in g["motivo"] and "15%" in g["motivo"]
    (p,) = g["medido"]["punches"]
    assert p["ok"] is False and abs(p["ganho"]) < 0.10
    # os planos, esses sim, têm câmera
    assert all(x["ok"] for x in g["medido"]["planos"])


def test_mutante_punch_de_10_por_cento_reprova(tmp_path):
    tl = tl_padrao()
    tl["camera"] = [e for e in tl["camera"] if e["tipo"] != "punch"] + [
        {"t": 16.0, "tipo": "punch", "de": 1.0, "para": 1.10, "dur": 0.28, "segura": 1.5}]
    g = rodar(tl, tmp_path, leitor=leitor_virtual(tl))
    assert g["resultado"] == "REPROVA"
    assert g["medido"]["punches"][0]["ganho"] == pytest.approx(0.10, abs=0.03)


def test_mutante_trecho_de_mais_de_20s_parado_reprova(tmp_path):
    """Avatar com zoom, depois um insert de 26 s sem nenhum movimento de câmera declarado."""
    segs = [seg_avatar(0.0, 6.0, 0), seg_insert(6.0, 32.0, 1), seg_avatar(32.0, 38.0, 2)]
    cam = [{"t": 0.0, "tipo": "zoom", "de": 1.0, "para": 1.16, "dur": 6.0},
           {"t": 32.0, "tipo": "zoom", "de": 1.0, "para": 1.16, "dur": 6.0}]
    tl = timeline(segs, cam)
    g = rodar(tl, tmp_path, leitor=leitor_virtual(tl))
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert "20 s" in g["motivo"]
    assert g["medido"]["parado"]["maior_s"] == pytest.approx(26.0, abs=0.2)
    assert g["medido"]["parado"]["de"] == pytest.approx(6.0, abs=0.2)
    # com um push-in declarado no insert, o mesmo vídeo passa
    cam2 = cam + [{"t": 6.0, "tipo": "push_in", "de": 1.0, "para": 1.3, "dur": 26.0}]
    tl2 = timeline(segs, cam2)
    g2 = rodar(tl2, tmp_path, leitor=leitor_virtual(tl2))
    assert g2["resultado"] == "PASS", g2.get("motivo")


def test_movimento_so_declarado_nao_basta_o_plano_de_avatar_precisa_se_mexer_na_imagem(tmp_path):
    """Zoom declarado na timeline, imagem parada: o gate mede a imagem."""
    tl = tl_padrao()
    g = rodar(tl, tmp_path, leitor=leitor_virtual(tl, zoom=False, punch=False))
    assert g["resultado"] == "REPROVA"
    assert g["medido"]["parado"]["maior_s"] >= 6.0          # os avatares parados não contam como movimento


def test_avatar_parado_por_mais_de_20s_reprova_pelas_duas_regras(tmp_path):
    segs = [seg_avatar(0.0, 25.0, 0)]
    tl = timeline(segs, [{"t": 0.0, "tipo": "zoom", "de": 1.0, "para": 1.16, "dur": 25.0}])
    g = rodar(tl, tmp_path, leitor=leitor_virtual(tl, zoom=False, punch=False))
    assert g["resultado"] == "REPROVA"
    assert "20 s" in g["motivo"] and "plano de avatar" in g["motivo"]


def test_punch_declarado_dentro_de_insert_ou_split_reprova(tmp_path):
    tl = tl_padrao()
    tl["camera"] = [e for e in tl["camera"] if e["tipo"] != "punch"] + [camera.evento_punch(10.0, 1.5)]
    g = rodar(tl, tmp_path, leitor=leitor_virtual(tl, punch=False))
    assert g["resultado"] == "REPROVA"
    assert "insert" in g["motivo"] or "split" in g["motivo"]
    assert "nunca" in g["motivo"]


def test_plano_curto_de_avatar_nao_e_cobrado_pelo_zoom(tmp_path):
    """Plano de avatar com menos de 2 s entregues não entra na regra dos 8%."""
    segs = [seg_avatar(0.0, 1.5, 0), seg_avatar(1.5, 8.0, 1)]
    cam = [{"t": 1.5, "tipo": "zoom", "de": 1.16, "para": 1.0, "dur": 6.5}]
    tl = timeline(segs, cam)
    leitor = leitor_virtual(tl)
    g = rodar(tl, tmp_path, leitor=leitor)
    planos = g["medido"]["planos"]
    assert len(planos) == 1 and planos[0]["inicio"] == pytest.approx(1.5)


# =================================================================================== insumo inválido: ERRO, nunca aprova

def test_video_ausente_e_erro_com_saida_2(tmp_path):
    tl = tl_padrao()
    g = gate_camera.rodar(tmp_path / "nao_existe.mp4", tl, leitor=leitor_virtual(tl), detector=detector_identidade)
    assert g["resultado"] == "ERRO" and g["saida"] == 2
    assert "não existe" in g["motivo"]
    assert formato_do_laudo(g) == []


def test_timeline_sem_campo_obrigatorio_e_erro(tmp_path):
    tl = tl_padrao()
    del tl["segmentos"]
    g = rodar(tl, tmp_path, leitor=leitor_virtual(tl_padrao()))
    assert g["resultado"] == "ERRO" and g["saida"] == 2 and "segmentos" in g["motivo"]


def test_rosto_nao_detectado_e_erro_e_pede_outro_detector(tmp_path):
    tl = tl_padrao()
    g = rodar(tl, tmp_path, leitor=leitor_virtual(tl), detector=lambda q: None)
    assert g["resultado"] == "ERRO" and g["saida"] == 2
    assert "rosto" in g["motivo"] and "detector" in g["motivo"]


def test_leitor_que_quebra_vira_erro_e_nao_traceback(tmp_path):
    def quebrado(video, fps):
        raise OSError("ffmpeg nao decodifica isso")
        yield  # pragma: no cover
    g = rodar(tl_padrao(), tmp_path, leitor=quebrado)
    assert g["resultado"] == "ERRO" and g["saida"] == 2 and "ffmpeg" in g["motivo"]


def test_timeline_sem_nenhum_plano_de_avatar_so_mede_o_movimento(tmp_path):
    segs = [seg_insert(0.0, 10.0, 0)]
    tl = timeline(segs, [{"t": 0.0, "tipo": "push_in", "de": 1.0, "para": 1.2, "dur": 10.0}])
    g = rodar(tl, tmp_path, leitor=leitor_virtual(tl))
    assert g["resultado"] == "PASS" and g["medido"]["planos"] == []


# =================================================================================== render de verdade (lento)

def _render(tmp_path, nome, filtro_ou_punches):
    """Cena parada com um quadrado branco, passada pelo filtro do avatar de verdade."""
    fonte = tmp_path / "av.mp4"
    if not fonte.exists():
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
                        "color=c=0x141414:s=270x480:r=30:d=3.4,drawbox=x=95:y=200:w=80:h=80:color=white:t=fill",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "12", str(fonte)],
                       check=True, capture_output=True)
    saida = tmp_path / nome
    if isinstance(filtro_ou_punches, str):                     # câmera parada: só reenquadra, sem zoompan
        cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin", "-ss", "0", "-t", "3.4", "-i", str(fonte), "-vf",
               "fps=30,scale=1080:1920,setsar=1,trim=end_frame=90,setpts=N/30/TB", "-r", "30", "-an",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", str(saida)]
    else:
        cmd = FA.cmd_orig(str(fonte), 0.0, 3.0, str(saida), idx=0, base=1.0, punches=filtro_ou_punches)
    subprocess.run(cmd, check=True, capture_output=True)
    return saida


def caixa_do_quadrado_branco(quadro):
    """Detector sintético: a caixa dos pixels brancos. `quadro` é RGB (altura, largura, 3)."""
    cinza = quadro.astype(np.float32).mean(axis=2)
    ys, xs = np.where(cinza > 160)
    if len(xs) == 0:
        return None
    return (float(xs.min()), float(ys.min()), float(xs.max() - xs.min() + 1), float(ys.max() - ys.min() + 1))


def tl_do_render_sintetico(com_punch):
    cam = [{"t": 0.0, "tipo": "zoom", "de": 1.0, "para": 1.16, "dur": 3.0}]
    if com_punch:
        cam.append(camera.evento_punch(0.5, 1.0))
    return timeline([seg_avatar(0.0, 3.0, 0)], cam)


@pytest.mark.lento
def test_render_de_verdade_com_zoom_e_punch_passa(tmp_path):
    com = _render(tmp_path, "com.mp4", [camera.evento_punch(0.5, 1.0)])
    g = gate_camera.rodar(com, tl_do_render_sintetico(True), detector=caixa_do_quadrado_branco)
    assert g["resultado"] == "PASS", g.get("motivo")
    (p,) = g["medido"]["punches"]
    assert 0.17 <= p["ganho"] <= 0.30, p
    assert g["medido"]["planos"][0]["variacao"] >= 0.08


@pytest.mark.lento
def test_render_de_verdade_sem_zoom_reprova(tmp_path):
    parado = _render(tmp_path, "parado.mp4", "estatico")
    g = gate_camera.rodar(parado, tl_do_render_sintetico(False), detector=caixa_do_quadrado_branco)
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert g["medido"]["planos"][0]["variacao"] < 0.02


@pytest.mark.lento
def test_render_de_verdade_punch_declarado_e_nao_renderizado_reprova(tmp_path):
    """O filtro rodou só com o zoom contínuo: o punch está na timeline mas não na imagem."""
    sem_punch = _render(tmp_path, "sem_punch.mp4", [])
    g = gate_camera.rodar(sem_punch, tl_do_render_sintetico(True), detector=caixa_do_quadrado_branco)
    assert g["resultado"] == "REPROVA"
    assert "punch" in g["motivo"] and g["medido"]["punches"][0]["ok"] is False
