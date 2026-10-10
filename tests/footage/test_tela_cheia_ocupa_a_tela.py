"""W7.Z, item 6 da prova como aluno: insert HORIZONTAL em layout cheio deixava metade da tela vazia e escura (os quadros
de 5,5 s, 15,5 s e 35 s da folha). Regra do dono (feedback-lettering-exclui-legenda-e-insert-ocupa-a-tela): insert ocupa
a tela, nunca peça com metade vazia. Aqui: no cheio, a moldura escala para o CARD (barra + janela) ocupar pelo menos 70%
da altura do quadro, com zoom e recorte no conteúdo MEDIDO, nunca uma janela pequena com faixa morta em volta."""
import pytest

import moldura
from footage import enquadramento as ENQ
from footage import exposicao as EX
from footage import filtros_insert as FI
from footage import render_segmentos as RS

ALTURA = 1920
CARD_MIN = 0.70 * ALTURA


@pytest.mark.parametrize("aspecto", [1.05, 1.33, 1.7778, 2.0, 2.4])
def test_a_janela_cheia_faz_o_card_ocupar_70_por_cento_da_altura(aspecto):
    jw, jh = moldura.janela_cheia(aspecto)
    assert jw == 1036                                     # 96% da largura, como sempre foi
    assert jh + moldura.BARRA_H >= CARD_MIN               # o card inteiro (barra + janela)
    assert jh % 2 == 0 and jw % 2 == 0
    assert jh + moldura.BARRA_H + 2 * moldura.PAD_SOMBRA <= ALTURA     # e cabe no quadro com a sombra


def test_constante_de_ocupacao_e_a_do_dono():
    assert moldura.CHEIO_ALTURA_MIN == 0.70


def test_moldura_cheia_nasce_no_aspecto_da_janela_cheia_e_diz_que_preenche(tmp_path):
    m, png = FI.moldura_cheia(16 / 9.0, str(tmp_path / "molduras"))
    assert m["preenche"] is True
    assert m["janela_w"] == 1036 and m["janela_h"] == moldura.janela_cheia(16 / 9.0)[1]
    assert m["card_h"] >= CARD_MIN
    assert (tmp_path / "molduras").is_dir() and "moldura_cheio_0_" in png


def test_filtro_da_tela_cheia_preenche_a_janela_com_recorte_no_conteudo(tmp_path):
    m, png = FI.moldura_cheia(16 / 9.0, str(tmp_path / "molduras"))
    expr = "'clip((in_w*0.3000)-(out_w/2),0,in_w-out_w)':'clip((in_h*0.5000)-(out_h/2),0,in_h-out_h)'"
    fc = FI.fc_tela_cheia_moldura(1.0, -0.04, "", m, png, "", 90, expr)
    jw, jh = m["janela_w"], m["janela_h"]
    assert f"scale={jw}:{jh}:force_original_aspect_ratio=increase,crop={jw}:{jh}:{expr}" in fc
    assert "zoompan" not in fc                              # o asset já entra grande: não há avanço a fazer


def test_asset_cujo_aspecto_ja_faz_o_card_passar_de_70_por_cento_entra_inteiro():
    """Aspecto alto o bastante (a moldura só vale de 1,05 em diante, mas a função é total): a altura natural manda."""
    jw, jh = moldura.janela_cheia(0.75)
    assert jh == int(round(jw / 0.75)) // 2 * 2 and jh + moldura.BARRA_H >= CARD_MIN


@pytest.fixture
def gravador(monkeypatch):
    cmds = []
    monkeypatch.setattr(RS, "run", lambda c: cmds.append([str(x) for x in c]))
    for nome in ("_CACHE_CONTEUDO", "_CACHE_ASPECTO", "_CACHE_LARG", "_PRETO_CACHE"):
        getattr(ENQ, nome).clear()
    monkeypatch.setattr(ENQ, "aspecto", lambda src, executar=None: 1280 / 644.0)
    monkeypatch.setattr(ENQ, "largura_fonte", lambda src, executar=None: 1280)
    monkeypatch.setattr(ENQ, "pular_preto", lambda src, st, take, *a, **k: st)
    monkeypatch.setattr(ENQ, "medir_conteudo", lambda src, w, h, executar=None: (0.62, 0.40, "preencher"))
    monkeypatch.setattr(EX, "luminancia_fonte", lambda src, start=0.0: 120.0)
    monkeypatch.setattr(EX, "luminancia_mediana_fonte", lambda src, start=0.0: 120)
    return cmds


def test_o_render_da_tela_cheia_escala_ate_70_por_cento_e_recorta_no_conteudo_medido(gravador, tmp_path):
    RS.r_insert_moldura({"file": "/m/paginas.mp4", "start": 0, "speed": 1.0}, 0.0, 3.0, "/o/s.mp4",
                        str(tmp_path / "molduras"))
    fc = gravador[0][gravador[0].index("-filter_complex") + 1]
    jw, jh = moldura.janela_cheia(1280 / 644.0)
    assert f"scale={jw}:{jh}:force_original_aspect_ratio=increase,crop={jw}:{jh}:" in fc
    assert "in_w*0.6200" in fc and "in_h*0.4000" in fc      # o foco é o do conteúdo medido, não o centro do arquivo
    assert "zoompan" not in fc


def test_o_render_da_tela_cheia_nao_gasta_push_in_num_asset_que_ja_entra_ampliado(gravador, tmp_path):
    RS.r_insert_moldura({"file": "/m/paginas.mp4", "start": 0, "speed": 1.0}, 0.0, 3.0, "/o/s.mp4",
                        str(tmp_path / "molduras"))
    assert "zoompan" not in gravador[0][gravador[0].index("-filter_complex") + 1]


def test_fundo_desfocado_nao_escurece_nas_bordas_do_quadro(tmp_path):
    """O fundo da tela cheia era o quadro congelado com `boxblur=60:2`; o filtro trata fora do quadro como preto e as bordas
    morriam em preto liso (os 120 px de baixo mediam 0 a 5 de luminância): faixa morta em volta do card. O desfoque agora
    roda numa folga de 240 px e o recorte final tira a borda escurecida."""
    import subprocess
    import numpy as np
    from PIL import Image
    pasta = tmp_path
    asset = pasta / "claro.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "lavfi", "-i", "color=c=0xC8C8C8:s=1280x720:r=30:d=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(asset)], check=True, capture_output=True)
    m, png = FI.moldura_cheia(1280 / 720.0, str(pasta / "mol"))
    fc = FI.fc_tela_cheia_moldura(1.0, 0.0, "", m, png, "", 15)
    assert "boxblur=60:2,crop=1080:1920" in fc
    quadro = pasta / "q.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", str(asset), "-filter_complex", fc, "-map", "[v]",
                    "-frames:v", "1", str(quadro)], check=True, capture_output=True)
    g = np.asarray(Image.open(quadro).convert("L")).astype(float)
    assert g[:20].mean() > 150 and g[-20:].mean() > 150, (g[:20].mean(), g[-20:].mean())


def test_a_versao_do_render_subiu_para_nao_reaproveitar_o_cache_da_tela_cheia_pequena():
    """O cache de segmento é por (conteúdo, config, VERSAO_RENDER): a tela cheia que mudou de filtro não pode voltar do
    cache de um build anterior, que tinha o card pequeno e a faixa morta."""
    assert RS.VERSAO_RENDER != "v2"
