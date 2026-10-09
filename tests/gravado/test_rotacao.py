"""O render do gravado (W5.D): rotação do celular, grade de cor e as tags.

O vídeo de celular gravado em pé chega DEITADO (1920x1080) com uma matriz de rotação -90 no
contêiner. O `ffprobe` de largura e altura mente sobre o que o aluno vê. A montagem tem que sair
1080x1920, na orientação certa, sem esticar e sem barra preta. Os testes medem o pixel do arquivo
de saída contra o que o próprio ffmpeg mostra para aquele arquivo (o autorotate é a verdade do
que o aluno vê no celular), e provam que a medida enxerga o defeito: com a rotação ignorada ela
reprova.

A grade (C5) entra no mesmo render: preset do `projeto.json` (padrão `quente-suave`), tags bt709
no fim da cadeia e, se a fonte for HDR (iPhone grava em HLG), a conversão para SDR ANTES da grade.
"""
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from cinema import grade
from gravado import montar
from gravado import projeto as gp
from projeto import modelo
from tests.gravado import sintese as sx

ADS = {"A1": {"corpo": [["T1", 0.0, 3.5]], "cta_normal": [["T1", 4.0, 5.0]]}}


def _projeto(tmp_path, estilo=None):
    p = sx.projeto_de_teste(tmp_path, ads=ADS)
    projeto = {"versao": 1, "slug": "teste", "modo": "gravado",
               "trilha": {"desligada": True, "motivo": "gravado: a voz real segue sem trilha"}}
    if estilo:
        projeto["estilo"] = estilo
    modelo.escrever(p.base / "projeto.json", projeto)
    return p


# --- o grafo do render (sem ffmpeg) --------------------------------------------------------------

def test_o_grafo_tem_a_grade_quente_suave_por_padrao_e_fecha_com_as_tags_bt709(tmp_path):
    p = _projeto(tmp_path)
    segs = [("T1", 0.0, 1.2), ("T1", 2.0, 3.2)]
    fc = montar.filtro_complexo(p, segs)
    assert "setpts=PTS/1.2" in fc and "atempo=1.2" in fc
    for trecho in ("noise=alls=7:allf=t+u", "eq=contrast=1.03:saturation=0.97", "vignette=PI/5.5"):
        assert trecho in fc, trecho
    assert "colorspace=all=bt709:iall=bt709:fast=1[vo]" in fc
    assert fc.index("setpts=PTS/1.2") < fc.index("vignette=PI/5.5")      # a grade vem depois de acelerar


def test_o_preset_de_grade_vem_do_projeto_json(tmp_path):
    p = _projeto(tmp_path, estilo={"grade": "pb"})
    fc = montar.filtro_complexo(p, [("T1", 0.0, 1.0)])
    assert "hue=s=0" in fc and "vignette=PI/5.5" not in fc
    assert montar.preset_de_grade(p) == "pb"
    assert montar.preset_de_grade(_projeto(tmp_path / "outro")) == grade.PADRAO


def test_preset_de_grade_desconhecido_e_insumo_invalido_antes_de_qualquer_ffmpeg(tmp_path):
    from gravado.veredito import InsumoInvalido
    p = _projeto(tmp_path, estilo={"grade": "sepia-violeta"})
    with pytest.raises(InsumoInvalido) as e:
        montar.filtro_complexo(p, [("T1", 0.0, 1.0)])
    assert "sepia-violeta" in str(e.value) and "quente-suave" in str(e.value)


def test_sem_projeto_json_vale_o_padrao_do_gravado(tmp_path):
    p = sx.projeto_de_teste(tmp_path, ads=ADS)
    assert montar.preset_de_grade(p) == grade.PADRAO and p.accel == 1.2
    assert "vignette=PI/5.5" in montar.filtro_complexo(p, [("T1", 0.0, 1.0)])


def test_cada_segmento_do_grafo_entra_inteiro_na_tela_sem_esticar(tmp_path):
    p = _projeto(tmp_path)
    fc = montar.filtro_complexo(p, [("T1", 0.0, 1.0)])
    assert "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2" in fc
    assert "setsar=1" in fc and "fps=30" in fc


def test_fonte_hdr_converte_para_sdr_antes_da_grade_e_fonte_sdr_nao_mexe(tmp_path):
    p = _projeto(tmp_path)
    sdr = montar.filtro_complexo(p, [("T1", 0.0, 1.0)], hdr={"T1": False})
    hdr = montar.filtro_complexo(p, [("T1", 0.0, 1.0)], hdr={"T1": "/tmp/lut.cube"})
    assert "lut3d" not in sdr and "lut3d" in hdr and "interp=tetrahedral" in hdr
    assert hdr.index("lut3d") < hdr.index("vignette")
    assert "in_color_matrix=bt2020" in hdr and "out_color_matrix=bt709" in hdr


def test_o_comando_marca_a_saida_bt709_em_tv(tmp_path):
    p = _projeto(tmp_path)
    cmd = montar.comando_render(p, [("T1", 0.0, 1.0)], Path("/x/saida.mp4"), entradas=["-i", "a.mov", "-i", "a.mp3"])
    for flag, valor in (("-colorspace", "bt709"), ("-color_primaries", "bt709"), ("-color_trc", "bt709"),
                        ("-color_range", "tv"), ("-pix_fmt", "yuv420p")):
        assert cmd[cmd.index(flag) + 1] == valor, flag
    assert cmd[-1] == "/x/saida.mp4"


# --- a rotação -90, medida no pixel --------------------------------------------------------------

def _fonte_deitada(destino, dur=5.0):
    """320x180 guardado, matriz de rotação -90 no contêiner (o que se vê é 180x320).

    Quadro estático e assimétrico: um disco (para medir se esticou) e uma cunha de luz no canto
    superior esquerdo do quadro GUARDADO (para medir a orientação)."""
    base = Path(destino).with_name("deitada_base.mp4")
    geq = "lum='if(lt(hypot(X-250,Y-90),40),230,if(lt(X+Y,70),255,40))':cb=128:cr=128"
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
                        "color=c=black:s=320x180:r=25:d=%s,format=yuv420p,geq=%s" % (dur, geq),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "12", str(base)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-display_rotation:v:0", "-90", "-i", str(base),
                        "-c", "copy", str(destino)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return Path(destino)


def _quadro(video, t, largura, altura, noautorotate=False):
    cmd = ["ffmpeg", "-v", "error", "-nostdin"]
    if noautorotate:
        cmd += ["-noautorotate"]
    cmd += ["-ss", str(t), "-i", str(video), "-frames:v", "1", "-vf",
            "scale=%d:%d:flags=area,format=gray" % (largura, altura), "-f", "rawvideo", "-"]
    r = subprocess.run(cmd, capture_output=True)
    assert r.returncode == 0 and len(r.stdout) == largura * altura, r.stderr[-200:]
    return np.frombuffer(r.stdout, dtype=np.uint8).reshape(altura, largura).astype(float)


def _confere_orientacao_e_forma(saida, fonte):
    """(correlação com o que o ffmpeg mostra da fonte, razão largura/altura do disco)."""
    visto = _quadro(fonte, 0.2, 180, 320)                  # autorotate: a verdade do que o aluno vê
    nosso = _quadro(saida, 0.1, 180, 320)
    corr = float(np.corrcoef(visto.ravel(), nosso.ravel())[0, 1])
    central = nosso[60:260, :]                               # fora da cunha do canto
    disco = np.argwhere(central > 200)
    razao = (disco[:, 1].ptp() + 1) / float(disco[:, 0].ptp() + 1) if len(disco) else 0.0
    return corr, razao


@pytest.mark.lento
def test_rotacao_menos_90_sai_1080x1920_sem_esticar_e_na_orientacao_do_aluno(tmp_path):
    p = _projeto(tmp_path)
    p.brutos.mkdir(parents=True, exist_ok=True)
    fonte = _fonte_deitada(p.brutos / "T1.mp4")
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                      "stream=width,height", "-of", "json", str(fonte)],
                                     capture_output=True, text=True).stdout)["streams"][0]
    assert (info["width"], info["height"]) == (320, 180)            # o ffprobe mente: guardado deitado
    segs = montar.segmentos_do_ad(p, "A1", False)
    saida = montar.render(p, "A1", segs, False)
    v = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height,color_space,color_primaries,color_transfer",
                                   "-of", "json", str(saida)], capture_output=True, text=True).stdout)["streams"][0]
    assert (v["width"], v["height"]) == (1080, 1920)
    assert (v["color_space"], v["color_primaries"], v["color_transfer"]) == ("bt709", "bt709", "bt709")
    corr, razao = _confere_orientacao_e_forma(saida, fonte)
    assert razao == pytest.approx(1.0, abs=0.04), "o disco esticou: %.2f" % razao
    assert corr > 0.9, "orientação ou conteúdo diferente do que o aluno vê: correlação %.2f" % corr


@pytest.mark.lento
def test_a_medida_reprova_quando_a_rotacao_e_ignorada(tmp_path, monkeypatch):
    """Mutante: o mesmo render com `-noautorotate`. Se a medida não o reprovasse, o teste acima não provaria nada."""
    p = _projeto(tmp_path)
    p.brutos.mkdir(parents=True, exist_ok=True)
    fonte = _fonte_deitada(p.brutos / "T1.mp4")
    real = montar._rodar

    def sem_rotacao(cmd):
        cmd = [str(c) for c in cmd]
        if cmd and cmd[0] == "ffmpeg" and "-filter_complex" in cmd:
            cmd = [cmd[0], "-noautorotate"] + cmd[1:]
        return real(cmd)
    monkeypatch.setattr(montar, "_rodar", sem_rotacao)
    saida = montar.render(p, "A1", montar.segmentos_do_ad(p, "A1", False), False)
    corr, razao = _confere_orientacao_e_forma(saida, fonte)
    assert corr <= 0.9 or abs(razao - 1.0) > 0.04
