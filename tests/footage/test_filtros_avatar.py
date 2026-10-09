"""Filtros do avatar (W2.B): zoom alternado do plano de apresentador e painel de baixo do split.

Cada string golden foi gerada pelo `produzir_roteiro.py` ORIGINAL (commit 2ebd1cc), com o
mesmo bloco, a mesma janela e o mesmo `base`: o módulo novo tem que devolver o mesmo comando,
caractere por caractere. Não precisa de ffmpeg.
"""
import pytest

from footage import filtros_avatar as FA

# (s, e, idx, base ou None) -> comando completo do ffmpeg
GOLDEN_ORIG = [{'nome': 'r_orig_idx0_base1.0',
  's': 5.6,
  'e': 10.0,
  'idx': 0,
  'base': 1.0,
  'out': '/o/s.mp4',
  'comando': ['ffmpeg',
              '-y',
              '-ss',
              '5.6',
              '-t',
              '4.800000000000001',
              '-i',
              '/AV/avatar.mp4',
              '-vf',
              "fps=30,scale=2376:4224:force_original_aspect_ratio=increase,crop=2160:3840:108:652,zoompan=z='1.0+0.16*on/131':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920,setsar=1,trim=end_frame=132,setpts=N/30/TB",
              '-r',
              '30',
              '-an',
              '-c:v',
              'libx264',
              '-pix_fmt',
              'yuv420p',
              '/o/s.mp4']},
 {'nome': 'r_orig_idx1_base1.14',
  's': 9.6,
  'e': 11.28,
  'idx': 1,
  'base': 1.14,
  'out': '/o/s.mp4',
  'comando': ['ffmpeg',
              '-y',
              '-ss',
              '9.6',
              '-t',
              '2.0799999999999996',
              '-i',
              '/AV/avatar.mp4',
              '-vf',
              "fps=30,scale=2376:4224:force_original_aspect_ratio=increase,crop=2160:3840:108:652,zoompan=z='1.2999999999999998-0.16*on/49':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920,setsar=1,trim=end_frame=50,setpts=N/30/TB",
              '-r',
              '30',
              '-an',
              '-c:v',
              'libx264',
              '-pix_fmt',
              'yuv420p',
              '/o/s.mp4']},
 {'nome': 'r_orig_idx2_base1.0',
  's': 0.0,
  'e': 3.04,
  'idx': 2,
  'base': 1.0,
  'out': '/o/s.mp4',
  'comando': ['ffmpeg',
              '-y',
              '-ss',
              '0.0',
              '-t',
              '3.44',
              '-i',
              '/AV/avatar.mp4',
              '-vf',
              "fps=30,scale=2376:4224:force_original_aspect_ratio=increase,crop=2160:3840:108:652,zoompan=z='1.0+0.16*on/90':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920,setsar=1,trim=end_frame=91,setpts=N/30/TB",
              '-r',
              '30',
              '-an',
              '-c:v',
              'libx264',
              '-pix_fmt',
              'yuv420p',
              '/o/s.mp4']},
 {'nome': 'r_orig_idx3_base1.14',
  's': 15.52,
  'e': 18.08,
  'idx': 3,
  'base': 1.14,
  'out': '/o/s.mp4',
  'comando': ['ffmpeg',
              '-y',
              '-ss',
              '15.52',
              '-t',
              '2.9599999999999986',
              '-i',
              '/AV/avatar.mp4',
              '-vf',
              "fps=30,scale=2376:4224:force_original_aspect_ratio=increase,crop=2160:3840:108:652,zoompan=z='1.2999999999999998-0.16*on/76':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920,setsar=1,trim=end_frame=77,setpts=N/30/TB",
              '-r',
              '30',
              '-an',
              '-c:v',
              'libx264',
              '-pix_fmt',
              'yuv420p',
              '/o/s.mp4']},
 {'nome': 'r_orig_idx4_base1.0',
  's': 2.5,
  'e': 2.88,
  'idx': 4,
  'base': 1.0,
  'out': '/o/s.mp4',
  'comando': ['ffmpeg',
              '-y',
              '-ss',
              '2.5',
              '-t',
              '0.7799999999999999',
              '-i',
              '/AV/avatar.mp4',
              '-vf',
              "fps=30,scale=2376:4224:force_original_aspect_ratio=increase,crop=2160:3840:108:652,zoompan=z='1.0+0.16*on/10':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920,setsar=1,trim=end_frame=11,setpts=N/30/TB",
              '-r',
              '30',
              '-an',
              '-c:v',
              'libx264',
              '-pix_fmt',
              'yuv420p',
              '/o/s.mp4']},
 {'nome': 'r_orig_sem_base',
  's': 15.52,
  'e': 18.08,
  'idx': 5,
  'base': None,
  'out': '/o/s.mp4',
  'comando': ['ffmpeg',
              '-y',
              '-ss',
              '15.52',
              '-t',
              '2.9599999999999986',
              '-i',
              '/AV/avatar.mp4',
              '-vf',
              "fps=30,scale=2376:4224:force_original_aspect_ratio=increase,crop=2160:3840:108:652,zoompan=z='1.16-0.16*on/76':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920,setsar=1,trim=end_frame=77,setpts=N/30/TB",
              '-r',
              '30',
              '-an',
              '-c:v',
              'libx264',
              '-pix_fmt',
              'yuv420p',
              '/o/s.mp4']}]

# bias do VAM_SPLIT_BIAS -> filtro do painel de baixo do split
GOLDEN_SPLIT = [{'bias': '0.30',
  'filtro': '[1:v]crop=1080:1600:0:100,scale=1080:1600,crop=1080:770:0:480,setsar=1[bot];'},
 {'bias': '0.0',
  'filtro': '[1:v]crop=1080:1600:0:100,scale=1080:1600,crop=1080:770:0:0,setsar=1[bot];'},
 {'bias': '0.5',
  'filtro': '[1:v]crop=1080:1600:0:100,scale=1080:1600,crop=1080:770:0:800,setsar=1[bot];'},
 {'bias': '0.049',
  'filtro': '[1:v]crop=1080:1600:0:100,scale=1080:1600,crop=1080:770:0:78,setsar=1[bot];'},
 {'bias': '0.9',
  'filtro': '[1:v]crop=1080:1600:0:100,scale=1080:1600,crop=1080:770:0:830,setsar=1[bot];'}]


def test_constantes_mantem_nomes_e_valores():
    assert (FA.W, FA.H, FA.FPS) == (1080, 1920, 30)
    assert FA.REFRAME == "scale=2376:4224:force_original_aspect_ratio=increase,crop=2160:3840:108:652"
    assert FA.AMPL == 0.16
    assert (FA.SPLIT_TOP_H, FA.SPLIT_BOT_H, FA.SPLIT_GRAD) == (1150, 770, 90)
    assert FA.SPLIT_AV_SRC == (0, 100, 1080, 1600)


def test_nframes_nunca_zero_e_cap_conta_quadros():
    assert FA.nframes(0) == 1
    assert FA.nframes(0.5) == 15
    assert FA.cap(126) == "trim=end_frame=126,setpts=N/30/TB"


@pytest.mark.parametrize("caso", GOLDEN_ORIG, ids=lambda c: c["nome"])
def test_comando_do_avatar_bate_com_o_original(caso):
    kw = {} if caso["base"] is None else {"base": caso["base"]}
    cmd = FA.cmd_orig("/AV/avatar.mp4", caso["s"], caso["e"], caso["out"], idx=caso["idx"], **kw)
    assert cmd == caso["comando"]


def test_o_zoom_alterna_de_sentido_a_cada_bloco():
    assert FA.expr_zoom(100, 0, 1.0) == "1.0+0.16*on/99"        # par: empurra pra dentro
    assert FA.expr_zoom(100, 1, 1.0) == "1.16-0.16*on/99"       # ímpar: puxa pra fora
    assert FA.expr_zoom(100, 2, 1.14) == "1.14+0.16*on/99"


def test_base_alternada_preserva_o_ponto_flutuante_do_original():
    """1,14 + 0,16 em float dá 1.2999999999999998: o string tem que sair igual ao do motor antigo."""
    assert FA.expr_zoom(50, 1, 1.14) == "1.2999999999999998-0.16*on/49"


def test_bloco_de_um_quadro_nao_divide_por_zero():
    assert FA.expr_zoom(1, 0, 1.0) == "1.0+0.16*on/1"


@pytest.mark.parametrize("caso", GOLDEN_SPLIT, ids=lambda c: "bias_" + c["bias"])
def test_painel_de_baixo_do_split_bate_com_o_original(caso):
    assert FA.filtro_avatar_split(float(caso["bias"])) == caso["filtro"]


def test_corte_do_split_nunca_passa_do_que_sobra_na_fonte():
    """Com bias alto o corte é limitado: janela de 770 px precisa caber dentro da altura útil."""
    alt_util = FA.altura_util_split()
    assert alt_util == 1600
    assert FA.corte_y_split(0.9, alt_util) == alt_util - FA.SPLIT_BOT_H
    assert FA.corte_y_split(0.0, alt_util) == 0
    assert FA.corte_y_split(0.30, alt_util) % 2 == 0
