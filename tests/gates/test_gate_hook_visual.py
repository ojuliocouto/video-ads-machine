"""W4.A: gate_hook_visual (capacidade C1). O gancho visual dos 3 primeiros segundos, medido no render.

Complementa o `gate-ad.checar_hook` (que continua dono de "1º texto até 1,0 s" e "até 1,0 s sem texto
em 0 a 3 s") com o que ele não olha:

  - o texto cheio no QUADRO 0: o 1º texto depois de 0,25 s reprova;
  - mais de 1,0 s sem texto em 0 a 3 s reprova;
  - nenhum evento visual (corte confirmado, punch ou insert) em 0 a 3 s reprova;
  - quadro 0 com luminância abaixo de 0,6x a mediana dos quadros reprova (a abertura escura).

O texto é medido no OVERLAY com alfa (todo pixel opaco é texto nosso), como o gate-ad. O corte só conta
se o plano e a imagem concordam (`medir_ritmo.cortes_confirmados`). Os arquivos de teste são vídeos
minúsculos feitos em tmp com o ffmpeg.
"""
import json
import subprocess
from pathlib import Path

import pytest

from cinema import camera
from contratos import validar
from gates import gate_hook_visual
from tests.fixtures import sinteticos

RAIZ = Path(__file__).resolve().parents[2]
LAUDO_VALIDO = RAIZ / "contratos" / "exemplos" / "laudo.valido.json"
TAMANHO = "108x192"


# =================================================================================== arquivos sintéticos

def video_cinza(destino, dur=5.0, fade_in=0.0, tamanho=TAMANHO, fps=10, cor="0x303030"):
    """Quadro cinza escuro liso (o texto branco do overlay LÊ sobre ele: W5.X mede a legibilidade). Com `fade_in` o
    quadro 0 nasce preto. `cor` clara faz o texto branco virar ilegível."""
    vf = "fade=t=in:st=0:d=%s," % fade_in if fade_in else ""
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
           "color=c=%s:s=%s:r=%d:d=%s,%sformat=yuv420p" % (cor, tamanho, fps, dur, vf),
           "-c:v", "libx264", "-crf", "16", str(destino)]
    subprocess.run(cmd, check=True, capture_output=True)
    return Path(destino)


def overlay_com_texto(destino, janelas, dur=5.0, tamanho=TAMANHO, fps=20):
    """MOV com alfa: um bloco branco opaco (o 'texto') só dentro de `janelas` [(s, e), ...]."""
    enable = "+".join("between(t,%s,%s)" % (a, b) for a, b in janelas) or "0"
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
           "color=c=black@0:s=%s:r=%d:d=%s,format=rgba,drawbox=x=10:y=80:w=88:h=20:color=white@1:t=fill"
           ":replace=1:enable='%s'" % (tamanho, fps, dur, enable), "-c:v", "png", str(destino)]
    subprocess.run(cmd, check=True, capture_output=True)
    return Path(destino)


def tl(segmentos, camera_=None, aceleracao=1.0, a0=0.0):
    dur = segmentos[-1]["e"]
    return {"relogio": {"base": "footage_1x", "fps": 30, "aceleracao": aceleracao, "cauda_s": 0.0, "a0": a0},
            "duracao_s": dur, "segmentos": segmentos, "camera": list(camera_ or []), "janelas_split": [],
            "blocos": [], "letterings": []}


def seg(tipo, s, e, bloco=0, **kw):
    d = {"bloco": bloco, "tipo": tipo, "s": s, "e": e, "sub": 0, "de": 1}
    d.update(kw)
    return d


def tl_com_insert_na_abertura(**kw):
    return tl([seg("insert", 0.0, 2.0, 0, layout="cheio"), seg("apresentador", 2.0, 5.0, 1, base=1.0)], **kw)


def formato_do_laudo(g):
    laudo = json.loads(LAUDO_VALIDO.read_text(encoding="utf-8"))
    laudo["gates"] = [x for x in laudo["gates"] if x["nome"] != g["nome"]] + [g]
    k = len(laudo["gates"]) - 1
    return [e for e in validar.validar("laudo", laudo) if ("gates[%d]" % k) in e.caminho]


@pytest.fixture
def bom(tmp_path):
    """Vídeo normal, texto desde o quadro 0 até o fim, insert na abertura: tudo que o gancho pede."""
    return {"video": video_cinza(tmp_path / "final.mp4"),
            "overlay": overlay_com_texto(tmp_path / "ov.mov", [(0.0, 5.0)]),
            "tl": tl_com_insert_na_abertura(), "tmp": tmp_path}


def rodar(bom, **kw):
    kw.setdefault("cortes_confirmados", [])
    return gate_hook_visual.rodar(kw.pop("video", bom["video"]), kw.pop("tl", bom["tl"]),
                                  overlay=kw.pop("overlay", bom["overlay"]), **kw)


# =================================================================================== passa

def test_gancho_completo_passa_e_esta_no_formato_do_laudo(bom):
    g = rodar(bom)
    assert g["nome"] == "gate_hook_visual" and g["etapa"] == "depois"
    assert g["resultado"] == "PASS" and g["saida"] == 0, g.get("motivo")
    assert formato_do_laudo(g) == []
    m = g["medido"]
    assert m["primeiro_texto_s"] == 0.0
    assert m["sem_texto_s"] == 0.0
    assert m["quadro0"]["razao"] == pytest.approx(1.0, abs=0.05)
    assert [e["tipo"] for e in m["eventos"]] == ["insert"]
    assert g["limiar"] == {"primeiro_texto_max_s": 0.25, "sem_texto_max_s": 1.0, "janela_s": 3.0,
                           "quadro0_razao_min": 0.6}


def test_texto_ate_o_quadro_0_e_na_marca_de_0_25_s_passa(bom):
    ov = overlay_com_texto(bom["tmp"] / "ov25.mov", [(0.25, 5.0)])
    g = rodar(bom, overlay=ov)
    assert g["resultado"] == "PASS", g.get("motivo")
    assert g["medido"]["primeiro_texto_s"] == pytest.approx(0.25, abs=0.051)


def test_punch_conta_como_evento_visual(bom):
    t = tl([seg("apresentador", 0.0, 5.0, 0, base=1.0)], [camera.evento_punch(1.0, 1.5)])
    g = rodar(bom, tl=t)
    assert g["resultado"] == "PASS", g.get("motivo")
    assert [e["tipo"] for e in g["medido"]["eventos"]] == ["punch"]


def test_corte_confirmado_pela_imagem_conta_como_evento(bom):
    t = tl([seg("apresentador", 0.0, 1.5, 0, base=1.0), seg("apresentador", 1.5, 5.0, 1, base=1.0)])
    g = rodar(bom, tl=t, cortes_confirmados=[1.5])
    assert g["resultado"] == "PASS", g.get("motivo")
    assert [(e["tipo"], e["t"]) for e in g["medido"]["eventos"]] == [("corte", 1.5)]


def test_tempos_da_timeline_viram_tempo_entregue(bom):
    """Punch aos 3,5 s de footage é 2,59 s entregues com 1,35x: dentro dos 3 s. Aos 4,5 s já seria 3,33 s."""
    t = tl([seg("apresentador", 0.0, 8.0, 0, base=1.0)], [camera.evento_punch(3.5, 1.5)], aceleracao=1.35)
    assert [e["tipo"] for e in gate_hook_visual.eventos_visuais(t)] == ["punch"]
    t2 = tl([seg("apresentador", 0.0, 8.0, 0, base=1.0)], [camera.evento_punch(4.5, 1.5)], aceleracao=1.35)
    assert gate_hook_visual.eventos_visuais(t2) == []


def test_insert_que_entra_depois_dos_3s_nao_e_gancho(bom):
    t = tl([seg("apresentador", 0.0, 3.5, 0, base=1.0), seg("insert", 3.5, 6.0, 1, layout="cheio")])
    assert gate_hook_visual.eventos_visuais(t) == []


# =================================================================================== mutantes: TÊM que reprovar

def test_mutante_primeiro_texto_depois_de_0_25s_reprova(bom):
    ov = overlay_com_texto(bom["tmp"] / "tarde.mov", [(0.6, 5.0)])
    g = rodar(bom, overlay=ov)
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert "primeiro texto" in g["motivo"] and "0.25" in g["motivo"]
    assert g["medido"]["primeiro_texto_s"] == pytest.approx(0.6, abs=0.06)
    assert formato_do_laudo(g) == []


def test_mutante_sem_texto_nenhum_nos_3s_reprova(bom):
    ov = overlay_com_texto(bom["tmp"] / "mudo.mov", [(3.5, 5.0)])
    g = rodar(bom, overlay=ov)
    assert g["resultado"] == "REPROVA"
    assert g["medido"]["primeiro_texto_s"] is None
    assert "sem texto" in g["motivo"]


def test_mutante_mais_de_1s_sem_texto_em_0_a_3s_reprova(bom):
    ov = overlay_com_texto(bom["tmp"] / "buraco.mov", [(0.0, 0.3), (1.9, 5.0)])
    g = rodar(bom, overlay=ov)
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert "1.0 s" in g["motivo"] and "sem texto" in g["motivo"]
    assert g["medido"]["sem_texto_s"] == pytest.approx(1.6, abs=0.1)


def test_vao_de_exatamente_1s_sem_texto_ainda_passa(bom):
    ov = overlay_com_texto(bom["tmp"] / "um_s.mov", [(0.0, 0.5), (1.5, 5.0)])
    g = rodar(bom, overlay=ov)
    assert g["resultado"] == "PASS", g.get("motivo")


def test_mutante_gancho_sem_evento_visual_reprova(bom):
    t = tl([seg("apresentador", 0.0, 5.0, 0, base=1.0)])
    g = rodar(bom, tl=t)
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert "evento visual" in g["motivo"]
    assert g["medido"]["eventos"] == []


def test_mutante_corte_que_a_imagem_nao_confirma_nao_conta(bom):
    t = tl([seg("apresentador", 0.0, 1.5, 0, base=1.0), seg("apresentador", 1.5, 5.0, 1, base=1.0)])
    g = rodar(bom, tl=t, cortes_confirmados=[])
    assert g["resultado"] == "REPROVA" and "evento visual" in g["motivo"]


def test_mutante_quadro_0_escuro_reprova(bom):
    escuro = video_cinza(bom["tmp"] / "escuro.mp4", fade_in=0.5)
    g = rodar(bom, video=escuro)
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert "quadro 0" in g["motivo"] and "0.6" in g["motivo"]
    assert g["medido"]["quadro0"]["razao"] < 0.6


def test_com_aceleracao_a_janela_de_3s_e_a_do_entregue(bom):
    """Texto no overlay só até 2,0 s de footage: com 1,35x são 1,48 s entregues e sobram 1,52 s sem texto."""
    ov = overlay_com_texto(bom["tmp"] / "curto.mov", [(0.0, 2.0)])
    t = tl_com_insert_na_abertura(aceleracao=1.35)
    g = rodar(bom, tl=t, overlay=ov)
    assert g["resultado"] == "REPROVA"
    assert g["medido"]["sem_texto_s"] == pytest.approx(3.0 - 2.0 / 1.35, abs=0.12)
    # com aceleração 1,0 o mesmo overlay deixaria 1,0 s sem texto: passaria. É a conversão que reprova.
    g1 = rodar(bom, tl=tl_com_insert_na_abertura(), overlay=ov)
    assert g1["resultado"] == "PASS"


# =================================================================================== corte confirmado de verdade

def test_corte_real_na_imagem_confirma_o_corte_do_plano(tmp_path):
    video = sinteticos.video_por_planos(tmp_path / "planos.mp4", [1.5, 2.0, 2.0])
    ov = overlay_com_texto(tmp_path / "ov.mov", [(0.0, 5.5)], dur=5.5, tamanho="180x320")
    t = tl([seg("apresentador", 0.0, 1.5, 0, base=1.0), seg("apresentador", 1.5, 3.5, 1, base=1.0),
            seg("apresentador", 3.5, 5.5, 2, base=1.0)])
    g = gate_hook_visual.rodar(video, t, overlay=ov)
    assert g["resultado"] == "PASS", g.get("motivo")
    assert [(e["tipo"], e["t"]) for e in g["medido"]["eventos"]] == [("corte", 1.5)]


def test_corte_que_so_existe_no_plano_nao_passa_pela_imagem(tmp_path):
    parado = sinteticos.video_por_planos(tmp_path / "parado.mp4", [5.5])
    ov = overlay_com_texto(tmp_path / "ov.mov", [(0.0, 5.5)], dur=5.5, tamanho="180x320")
    t = tl([seg("apresentador", 0.0, 1.5, 0, base=1.0), seg("apresentador", 1.5, 5.5, 1, base=1.0)])
    g = gate_hook_visual.rodar(parado, t, overlay=ov)
    assert g["resultado"] == "REPROVA" and "evento visual" in g["motivo"]


# =================================================================================== insumo inválido

def test_video_ausente_e_erro_com_saida_2(bom):
    g = rodar(bom, video=bom["tmp"] / "nao_existe.mp4")
    assert g["resultado"] == "ERRO" and g["saida"] == 2 and "não existe" in g["motivo"]
    assert formato_do_laudo(g) == []


def test_sem_overlay_e_erro_porque_o_texto_so_se_mede_nele(bom):
    g = gate_hook_visual.rodar(bom["video"], bom["tl"], overlay=None, cortes_confirmados=[])
    assert g["resultado"] == "ERRO" and g["saida"] == 2 and "overlay" in g["motivo"]
    g2 = rodar(bom, overlay=bom["tmp"] / "sumiu.mov")
    assert g2["resultado"] == "ERRO" and "overlay" in g2["motivo"]


def test_video_que_nao_e_video_e_erro_nao_traceback(bom):
    lixo = bom["tmp"] / "lixo.mp4"
    lixo.write_bytes(b"isto nao e um video")
    g = rodar(bom, video=lixo)
    assert g["resultado"] == "ERRO" and g["saida"] == 2


def test_timeline_sem_segmentos_e_erro(bom):
    t = tl_com_insert_na_abertura()
    del t["segmentos"]
    g = rodar(bom, tl=t)
    assert g["resultado"] == "ERRO" and "segmentos" in g["motivo"]


# =================================================================================== linha de comando

def test_cli_devolve_0_passa_1_reprova(bom, capsys):
    (bom["tmp"] / "timeline.json").write_text(json.dumps(bom["tl"]), encoding="utf-8")
    args = [str(bom["video"]), "--timeline", str(bom["tmp"] / "timeline.json"), "--overlay", str(bom["overlay"])]
    assert gate_hook_visual.main(args) == 0
    assert "PASSA" in capsys.readouterr().out
    ruim = overlay_com_texto(bom["tmp"] / "ruim.mov", [(2.5, 5.0)])
    args = [str(bom["video"]), "--timeline", str(bom["tmp"] / "timeline.json"), "--overlay", str(ruim)]
    assert gate_hook_visual.main(args) == 1
    assert "REPROVA" in capsys.readouterr().out
    assert gate_hook_visual.main([str(bom["tmp"] / "nada.mp4"), "--timeline", str(bom["tmp"] / "timeline.json"),
                                  "--overlay", str(bom["overlay"])]) == 2


# =================================================================================== W5.X: texto que não lê não é gancho

def test_mutante_gancho_presente_mas_ilegivel_reprova(bom):
    """O defeito do v1 (0 a 2,1 s): o gancho ESTÁ na tela, mas branco sobre claro. Presença não é leitura: texto que
    não lê conta como tempo sem texto."""
    claro = video_cinza(bom["tmp"] / "claro.mp4", cor="0xE6E6E6")
    g = rodar(bom, video=claro)
    assert g["resultado"] == "REPROVA", g
    assert "legível" in g["motivo"]
    assert g["medido"]["sem_texto_legivel_s"] > 1.0


def test_gancho_legivel_tem_texto_legivel_desde_o_quadro_0(bom):
    g = rodar(bom)
    assert g["medido"]["primeiro_texto_legivel_s"] == 0.0
    assert g["medido"]["sem_texto_legivel_s"] == 0.0


def _v1():
    import os
    base = os.environ.get("VAM_PARIDADE_MIDIA")
    pasta = Path(base) / "regressao" / "w5x_v1" if base else None
    if not pasta or not (pasta / "final_9x16.mp4").is_file():
        pytest.skip("render real da W5.A ausente ($VAM_PARIDADE_MIDIA/regressao/w5x_v1)")
    return pasta


@pytest.mark.midia_real
def test_render_real_v1_gancho_ilegivel_de_0_a_2_08_s_reprova():
    """O render da W5.A: o gancho branco fino sobre o insert de navegador claro não lê em 0,3 s nem em 2,08 s."""
    p = _v1()
    t = json.loads((p / "timeline.json").read_text(encoding="utf-8"))
    g = gate_hook_visual.rodar(str(p / "final_9x16.mp4"), t, overlay=str(p / "overlay.mov"), cortes_confirmados=[])
    assert g["resultado"] == "REPROVA", g
    leg = dict((round(x, 2), v) for x, v in g["medido"]["legivel_por_instante"])
    assert leg[0.3] is False and leg[2.1] is False, leg
    assert g["medido"]["sem_texto_legivel_s"] > 2.0
