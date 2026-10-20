"""Cauda do avatar: o HeyGen devolve o avatar um pouco mais curto que a voz e a footage pede o fim da última palavra.

Defeito do ensaio de 20/10/2026: o avatar tinha 27,56 s para uma voz de 27,58 s, o transcritor deu 27,84 s para o fim
de "comigo." e `vam plano --prancha` quebrou com `ERRO seg 08: duracao 2.77s != esperada 3.07s (fonte curta ou render
quebrado)`. O aluno não tem como consertar. `avatar.cauda.completar_cauda` completa o avatar ao recebê-lo:
congela o último quadro, completa o áudio com a cauda da voz original (e depois silêncio) e deixa a voz coberta com
folga de 0,5 s. Falta de mais de 1 s não se mexe: a conferência reprova com mensagem clara.

Mídia sintética de ffmpeg (160x284), segundos de duração: nenhuma chamada paga. Quem decide o quê é testado com um
executor falso; o efeito de verdade (quadro congelado, tom da voz, silêncio) é testado com o ffmpeg real.
"""
import json
import subprocess
from pathlib import Path

import pytest

from avatar import cauda as K
from projeto import pastas
from tests.fixtures.midia_avatar import (TEM_FFMPEG, criar_avatar, criar_voz, distancia, quadro, sha, sonda,
                                         volume_medio)

com_ffmpeg = pytest.mark.skipif(not TEM_FFMPEG, reason="ffmpeg e ffprobe ausentes")


@pytest.fixture
def proj(tmp_path):
    p = pastas.projeto("tres-horas", tmp_path / "_local").criar()
    return p


# --- a decisão (função pura) --------------------------------------------------------------------------------------

def test_as_constantes_da_regra_sao_as_do_pedido():
    assert K.FOLGA_S == 0.5 and K.FALTA_MAX_S == 1.0


def test_avatar_0_02_s_mais_curto_que_a_voz_completa_ate_a_voz_mais_a_folga():
    plano = K.planejar(avatar_s=27.564, voz_s=27.584)
    assert plano.alvo_s == pytest.approx(28.084, abs=0.001)
    assert plano.falta_s == pytest.approx(0.02, abs=0.001)


def test_avatar_que_ja_cobre_a_voz_com_a_folga_nao_se_mexe():
    assert K.planejar(avatar_s=28.1, voz_s=27.584) is None
    assert K.planejar(avatar_s=28.05, voz_s=27.584) is None        # a 1 quadro da folga: dentro da tolerância


def test_avatar_um_pouco_mais_longo_que_a_voz_mas_sem_a_folga_tambem_completa():
    """O defeito não é o 0,02 s: é o transcritor dar o fim da última palavra DEPOIS do fim do áudio (+0,28 s)."""
    plano = K.planejar(avatar_s=27.60, voz_s=27.584)
    assert plano is not None and plano.alvo_s == pytest.approx(28.084, abs=0.001)


def test_falta_exatamente_1_s_ainda_completa():
    assert K.planejar(avatar_s=26.584, voz_s=27.584) is not None


def test_falta_de_mais_de_1_s_nao_completa_e_a_conferencia_reprova_depois():
    assert K.planejar(avatar_s=26.5, voz_s=27.584) is None


# --- o que o executor recebe --------------------------------------------------------------------------------------

class Executor:
    """ffprobe e ffmpeg falsos. `medidas`: caminho -> (video, audio, formato); None = o ffprobe falha."""

    def __init__(self, medidas):
        self.medidas, self.chamadas = medidas, []

    def __call__(self, argv, **kw):
        argv = [str(a) for a in argv]
        self.chamadas.append(argv)
        if argv[0] == "ffprobe":
            m = self.medidas.get(argv[-1])
            if m is None:
                return 1, "Invalid data found"
            v, a, f = m
            streams = ([{"codec_type": "video", "duration": "%.6f" % v}] if v else []) + \
                      ([{"codec_type": "audio", "duration": "%.6f" % a}] if a else [])
            return 0, json.dumps({"streams": streams, "format": {"duration": "%.6f" % f}})
        if argv[0] == "ffmpeg":
            Path(argv[-1]).write_bytes(b"avatar-completado")
            t = float(argv[argv.index("-t") + 1])
            self.medidas[argv[-1]] = (t, t, t)            # o arquivo novo mede o que o -t pediu
            return 0, ""
        raise AssertionError("comando inesperado: %r" % argv)

    def ffmpeg(self):
        return [c for c in self.chamadas if c[0] == "ffmpeg"]


def montar(proj, medida_avatar, medida_voz):
    proj.avatar_mp4.parent.mkdir(parents=True, exist_ok=True)
    proj.avatar_mp4.write_bytes(b"avatar-curto")
    proj.voz_limpo.parent.mkdir(parents=True, exist_ok=True)
    proj.voz_limpo.write_bytes(b"voz")
    return Executor({str(proj.avatar_mp4): medida_avatar, str(proj.voz_limpo): medida_voz})


def test_avatar_curto_chama_o_ffmpeg_uma_vez_e_troca_o_arquivo_de_forma_atomica(proj):
    ex = montar(proj, (27.56, 27.564, 27.564), (None, 27.584, 27.584))
    r = K.completar_cauda(proj, executar=ex)
    assert len(ex.ffmpeg()) == 1
    argv = ex.ffmpeg()[0]
    assert argv[-1] != str(proj.avatar_mp4) and argv[-1].endswith(".mp4"), "escreve em outro arquivo e troca depois"
    assert proj.avatar_mp4.read_bytes() == b"avatar-completado"
    assert not list(proj.avatar_dir.glob("*.completando*")), "nenhum temporário para trás"
    assert r["voz_s"] == pytest.approx(27.584) and r["antes_s"] == pytest.approx(27.56)
    assert r["depois_s"] == pytest.approx(28.084, abs=0.001) and r["cauda_s"] == pytest.approx(0.524, abs=0.001)


def test_avatar_que_cobre_a_voz_nao_chama_o_ffmpeg(proj):
    ex = montar(proj, (28.1, 28.1, 28.1), (None, 27.584, 27.584))
    assert K.completar_cauda(proj, executar=ex) is None
    assert ex.ffmpeg() == [] and proj.avatar_mp4.read_bytes() == b"avatar-curto"


def test_falta_de_mais_de_1_s_nao_mexe_no_arquivo(proj):
    ex = montar(proj, (25.0, 25.0, 25.0), (None, 27.584, 27.584))
    assert K.completar_cauda(proj, executar=ex) is None
    assert ex.ffmpeg() == [] and proj.avatar_mp4.read_bytes() == b"avatar-curto"


@pytest.mark.parametrize("quem", ["avatar", "voz"])
def test_midia_que_o_ffprobe_nao_le_fica_para_a_conferencia(proj, quem):
    ex = montar(proj, None if quem == "avatar" else (27.56, 27.564, 27.564),
                None if quem == "voz" else (None, 27.584, 27.584))
    assert K.completar_cauda(proj, executar=ex) is None
    assert ex.ffmpeg() == [] and proj.avatar_mp4.read_bytes() == b"avatar-curto"


def test_ffmpeg_que_falha_levanta_erro_claro_e_deixa_o_avatar_como_estava(proj):
    ex = montar(proj, (27.56, 27.564, 27.564), (None, 27.584, 27.584))
    chamar = ex.__call__

    def quebrado(argv, **kw):
        if str(argv[0]) == "ffmpeg":
            ex.chamadas.append([str(a) for a in argv])
            return 1, "Error while encoding"
        return chamar(argv, **kw)

    with pytest.raises(K.CaudaFalhou) as e:
        K.completar_cauda(proj, executar=quebrado)
    assert "avatar" in str(e.value) and "Error while encoding" in str(e.value)
    assert proj.avatar_mp4.read_bytes() == b"avatar-curto"
    assert not list(proj.avatar_dir.glob("*.completando*"))


def test_ffmpeg_que_sai_com_zero_mas_entrega_arquivo_curto_e_recusado(proj):
    ex = montar(proj, (27.56, 27.564, 27.564), (None, 27.584, 27.584))
    chamar = ex.__call__

    def enganoso(argv, **kw):
        if str(argv[0]) == "ffmpeg":
            Path(str(argv[-1])).write_bytes(b"arquivo-curto")
            ex.medidas[str(argv[-1])] = (27.0, 27.0, 27.0)
            return 0, ""
        return chamar(argv, **kw)

    with pytest.raises(K.CaudaFalhou) as e:
        K.completar_cauda(proj, executar=enganoso)
    assert "27,00" in str(e.value) and proj.avatar_mp4.read_bytes() == b"avatar-curto"
    assert not list(proj.avatar_dir.glob("*.completando*"))


def test_a_linha_de_registro_diz_o_que_foi_feito_em_uma_linha():
    linha = K.linha({"antes_s": 27.56, "voz_s": 27.584, "depois_s": 28.084, "cauda_s": 0.524})
    assert "\n" not in linha
    assert linha.startswith("avatar completado")
    for pedaco in ("27,56", "27,58", "28,08", "0,52"):
        assert pedaco in linha, pedaco
    assert "\u2014" not in linha and "\u2013" not in linha          # nem travessão nem meia-risca


def test_trilha_de_video_e_so_audio_nao_quebra_a_decisao(proj):
    ex = montar(proj, (None, 27.564, 27.564), (None, 27.584, 27.584))
    assert K.completar_cauda(proj, executar=ex) is None, "sem vídeo não há o que completar: a conferência reprova"


# --- o efeito de verdade, com o ffmpeg real -----------------------------------------------------------------------

@com_ffmpeg
def test_real_avatar_mais_curto_que_a_voz_ganha_cauda_de_quadro_congelado_e_audio_mudo(proj):
    criar_avatar(proj.avatar_mp4, 3.0)
    criar_voz(proj.voz_limpo, 3.02)
    antes = sonda(proj.avatar_mp4)
    r = K.completar_cauda(proj)
    assert r is not None
    depois = sonda(proj.avatar_mp4)
    alvo = 3.02 + K.FOLGA_S
    assert depois["video"] == pytest.approx(alvo, abs=0.08) and depois["audio"] == pytest.approx(alvo, abs=0.08)
    assert depois["video"] > antes["video"] + 0.4
    # o último quadro fica congelado: o fim do original e o meio da cauda são o mesmo quadro
    assert distancia(quadro(proj.avatar_mp4, 3.30), quadro(proj.avatar_mp4, 3.45)) < 2
    assert distancia(quadro(proj.avatar_mp4, 2.95), quadro(proj.avatar_mp4, 3.30)) < 3, "a cauda não repete o último quadro"
    assert distancia(quadro(proj.avatar_mp4, 2.00), quadro(proj.avatar_mp4, 2.50)) > 8, "o corpo do avatar parou"
    # o tom de 440 Hz segue até o fim da voz; depois da voz, silêncio
    assert volume_medio(proj.avatar_mp4, 1.0, 2.5) > -30
    assert volume_medio(proj.avatar_mp4, 3.15, 3.50) < -60


@com_ffmpeg
def test_real_faltou_voz_de_verdade_a_cauda_do_audio_vem_da_voz_original(proj):
    """Avatar 0,6 s mais curto: o trecho que faltava da fala volta da voz original, não vira silêncio."""
    criar_avatar(proj.avatar_mp4, 3.0)
    criar_voz(proj.voz_limpo, 3.6)
    assert K.completar_cauda(proj) is not None
    assert volume_medio(proj.avatar_mp4, 3.1, 3.5) > -30, "a fala que faltava tem que vir da voz limpa"
    assert volume_medio(proj.avatar_mp4, 3.75, 4.05) < -60, "depois da voz, silêncio"
    d = sonda(proj.avatar_mp4)
    assert d["video"] == pytest.approx(4.1, abs=0.08) and d["audio"] == pytest.approx(4.1, abs=0.08)


@com_ffmpeg
def test_real_mantem_resolucao_taxa_de_quadros_e_o_corpo_do_avatar(proj):
    criar_avatar(proj.avatar_mp4, 3.0, fps=25)
    criar_voz(proj.voz_limpo, 3.02)
    original = quadro(proj.avatar_mp4, 1.0)
    K.completar_cauda(proj)
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate,pix_fmt", "-of", "json", str(proj.avatar_mp4)],
                       capture_output=True, text=True)
    s = json.loads(r.stdout)["streams"][0]
    assert (s["width"], s["height"], s["r_frame_rate"], s["pix_fmt"]) == (160, 284, "25/1", "yuv420p")
    diferenca = distancia(original, quadro(proj.avatar_mp4, 1.0))
    assert diferenca < 3, "o corpo do avatar saiu diferente do original (%.1f níveis de cinza em média)" % diferenca


@com_ffmpeg
def test_real_rodar_de_novo_nao_muda_o_arquivo(proj):
    criar_avatar(proj.avatar_mp4, 3.0)
    criar_voz(proj.voz_limpo, 3.02)
    assert K.completar_cauda(proj) is not None
    depois = sha(proj.avatar_mp4)
    assert K.completar_cauda(proj) is None
    assert sha(proj.avatar_mp4) == depois


@com_ffmpeg
def test_real_falta_de_mais_de_1_s_nao_mexe_no_arquivo(proj):
    criar_avatar(proj.avatar_mp4, 2.0)
    criar_voz(proj.voz_limpo, 3.5)
    antes = sha(proj.avatar_mp4)
    assert K.completar_cauda(proj) is None
    assert sha(proj.avatar_mp4) == antes


@com_ffmpeg
def test_real_avatar_sem_trilha_de_audio_ganha_so_a_cauda_de_video(proj):
    criar_avatar(proj.avatar_mp4, 3.0, audio=False)
    criar_voz(proj.voz_limpo, 3.02)
    assert K.completar_cauda(proj) is not None
    d = sonda(proj.avatar_mp4)
    assert d["audio"] is None and d["video"] == pytest.approx(3.52, abs=0.08)
