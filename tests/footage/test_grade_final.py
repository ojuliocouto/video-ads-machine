"""Grade final (W2.B): ruído, contraste, vinheta e as tags bt709, sobre a cadeia pronta.

O comando golden é o do `produzir_roteiro.py` ORIGINAL (fixture de paridade, commit 2ebd1cc).
As tags bt709 importam porque o libx264 marca a saída como HDR/HLG mesmo com conteúdo SDR e o
player que respeita a tag (WhatsApp, iPhone) decodifica com a curva errada e avermelha o vídeo.
"""
import pytest

from footage import grade_final as GF

GOLDEN_CMD = ["ffmpeg", "-y", "-i", "/D/_tmp_rot/x/vchain0.mp4", "-ss", "0.62", "-t", "17.06", "-i",
              "/D/inputs/avatar.mp4", "-filter_complex",
              "[0:v]noise=alls=7:allf=t+u,eq=contrast=1.03:saturation=0.97,vignette=PI/5.5,"
              "colorspace=all=bt709:iall=bt709:fast=1[v]",
              "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
              "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
              "-color_range", "tv", "-c:a", "aac", "-shortest", "/D/output/saida.mp4"]


def test_comando_bate_com_o_original():
    cmd = GF.cmd_grade_final("/D/_tmp_rot/x/vchain0.mp4", 0.62, 17.68, "/D/inputs/avatar.mp4", "/D/output/saida.mp4")
    assert cmd == GOLDEN_CMD


def test_janela_de_audio_e_o_total_menos_o_inicio_do_primeiro_span():
    cmd = GF.cmd_grade_final("v.mp4", 0.62, 17.68, "a.mp4", "o.mp4")
    assert cmd[cmd.index("-ss") + 1] == "0.62"
    assert cmd[cmd.index("-t") + 1] == str(17.68 - 0.62)


def test_a_saida_leva_as_tres_tags_bt709_e_a_do_filtro():
    cmd = GF.cmd_grade_final("v", 0.0, 1.0, "a", "o")
    for flag in ("-colorspace", "-color_primaries", "-color_trc"):
        assert cmd[cmd.index(flag) + 1] == "bt709"
    assert cmd[cmd.index("-color_range") + 1] == "tv"
    assert "colorspace=all=bt709:iall=bt709:fast=1" in GF.FILTRO_GRADE


def test_valores_da_grade_sao_os_do_motor_original():
    assert "noise=alls=7:allf=t+u" in GF.FILTRO_GRADE
    assert "eq=contrast=1.03:saturation=0.97" in GF.FILTRO_GRADE
    assert "vignette=PI/5.5" in GF.FILTRO_GRADE
    assert GF.FILTRO_GRADE.startswith("[0:v]") and GF.FILTRO_GRADE.endswith("[v]")


def test_audio_continuo_do_avatar_e_reanexado_pra_manter_o_lip_sync():
    cmd = GF.cmd_grade_final("v", 0.5, 9.0, "avatar.mp4", "o")
    assert cmd.count("-i") == 2 and cmd[cmd.index("-map", cmd.index("[v]")) + 1] == "1:a"
    assert "-shortest" in cmd and cmd[-1] == "o"


def test_aplicar_roda_o_ffmpeg_uma_vez_e_devolve_o_destino(monkeypatch):
    cmds = []
    monkeypatch.setattr(GF, "run", lambda c: cmds.append([str(x) for x in c]))
    assert GF.aplicar("v.mp4", 0.62, 17.68, "a.mp4", "/D/output/s.mp4") == "/D/output/s.mp4"
    assert len(cmds) == 1 and cmds[0][-1] == "/D/output/s.mp4"
