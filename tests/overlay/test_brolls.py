"""overlay.brolls: as visitas de insert, os arquivos de b-roll e o HTML deles.

Valores esperados lidos do `gen_ad_v2.py` original: o argv do ffmpeg (imagem estática com
Ken Burns até 1,06; vídeo com keyframes densos e laço quando a fonte é curta), a regra de
tamanho zero (cache truncado), o cap de duração (`dur_max`) que devolve a imagem ao
apresentador, e as trilhas do HTML (8 + 2k, 9 + 2k, 50 + k).
"""
import json

import pytest

from overlay import brolls as B
from overlay import hook as K


def plano(*itens):
    """[(bloco, tipo, s, e[, layout])] -> plano de ritmo."""
    saida = []
    for it in itens:
        d = {"bloco": it[0], "tipo": it[1], "s": it[2], "e": it[3]}
        if len(it) > 4:
            d["layout"] = it[4]
        saida.append(d)
    return saida


BLOCOS = [{"type": "insert", "instr": "demo a", "narr": "x"},
          {"type": "orig", "instr": "apresentador", "narr": "y"},
          {"type": "insert", "instr": "demo b", "narr": "z"}]
SPANS = [(0.4, 6.0), (6.0, 10.0), (10.0, 20.0)]


# --- planejar_visitas --------------------------------------------------------------------------

def test_visitas_de_insert_com_janelas_e_fatias_cheias():
    mapa = {"demo a": {"file": "a.mp4", "split": True}, "demo b": {"file": "b.mp4", "split": True}}
    pl = plano((0, "insert", 0.0, 6.0, "split"), (1, "orig", 6.0, 10.0),
               (2, "insert", 10.0, 14.0, "cheio"), (2, "orig", 14.0, 16.0),
               (2, "insert", 16.0, 20.0, "split"))
    visitas, retorno = B.planejar_visitas(BLOCOS, SPANS, mapa, pl)
    assert retorno == []
    a, b = visitas
    # o bloco 0 e o fundo do hook desde t=0: s2 = 0, nao o inicio da fala (0,4)
    assert (a.i, a.key, a.s, a.e, a.s2, a.dur) == (0, "demo a", 0.4, 6.0, 0.0, 6.0)
    assert a.meus == [(0.0, 6.0)] and a.cheias == set()
    assert (b.i, b.key, b.s2, b.dur) == (2, "demo b", 10.0, 10.0)
    assert b.meus == [(10.0, 14.0), (16.0, 20.0)]
    assert b.cheias == {(10.0, 14.0)}


def test_sem_plano_de_insert_a_visita_cobre_o_bloco_todo():
    visitas, _ = B.planejar_visitas(BLOCOS[:1], SPANS[:1], {"demo a": {"file": "a.mp4"}},
                                    plano((0, "orig", 0.0, 6.0)))
    assert visitas[0].meus == [(0.0, 6.0)]


def test_insert_sem_chave_no_mapa_para_o_motor():
    with pytest.raises(SystemExit) as e:
        B.planejar_visitas(BLOCOS, SPANS, {"demo a": {"file": "a.mp4"}}, [])
    assert str(e.value) == "bloco insert 2 sem key no inserts.json: demo b"


def test_insert_curto_demais_nao_vira_visita_mas_o_cap_continua_valendo():
    # `dur < 0.6: continue` vem DEPOIS do calculo do retorno ao avatar
    blocos = [{"type": "orig", "instr": "x", "narr": ""}, {"type": "insert", "instr": "demo a", "narr": ""}]
    visitas, retorno = B.planejar_visitas(blocos, [(0.0, 5.0), (5.0, 5.5)],
                                          {"demo a": {"file": "a.mp4", "dur_max": 0.3}}, [])
    assert visitas == []
    assert retorno == [(1, 5.3)]


def test_cap_de_duracao_espalha_a_tela_e_a_volta_e_o_ultimo_plano_de_rosto(capsys):
    # dur_max 4 s num bloco de 10 s: o CTA sobe onde a imagem volta pro avatar pela ultima vez
    mapa = {"demo a": {"file": "a.mp4"}, "demo b": {"file": "b.mp4", "dur_max": 4.0}}
    pl = plano((2, "insert", 10.0, 13.0), (2, "orig", 13.0, 15.0), (2, "insert", 15.0, 17.0),
               (2, "orig", 17.0, 20.0))
    visitas, retorno = B.planejar_visitas(BLOCOS, SPANS, mapa, pl)
    assert retorno == [(2, 17.0)]
    assert "[cap] insert 'demo b': 4.00s de tela espalhados em 10.00s de bloco; " \
           "ultima volta pro avatar em 17.00s" in capsys.readouterr().out


def test_cap_sem_plano_de_rosto_volta_em_s2_mais_cap():
    mapa = {"demo a": {"file": "a.mp4"}, "demo b": {"file": "b.mp4", "dur_max": 4.0}}
    _, retorno = B.planejar_visitas(BLOCOS, SPANS, mapa, [])
    assert retorno == [(2, 14.0)]


def test_cap_maior_que_o_bloco_nao_registra_retorno(capsys):
    mapa = {"demo a": {"file": "a.mp4"}, "demo b": {"file": "b.mp4", "dur_max": 30.0}}
    _, retorno = B.planejar_visitas(BLOCOS, SPANS, mapa, [])
    assert retorno == [] and "[cap]" not in capsys.readouterr().out


# --- montar_brolls -------------------------------------------------------------------------------

def test_brolls_levam_arquivo_inicio_janela_e_rotulo():
    mapa = {"demo a": {"file": "a.mp4", "start": 1.234}, "demo b": {"file": "b.png"}}
    visitas, _ = B.planejar_visitas(BLOCOS, SPANS, mapa, [])
    brolls = B.montar_brolls(visitas, {"demo b": "SEU SITE"})
    assert brolls == [
        {"src_file": "a.mp4", "start": 1.23, "s": 0.0, "d": 6.0, "label": "demo a"},
        {"src_file": "b.png", "start": 0, "s": 10.0, "d": 10.0, "label": "SEU SITE"}]


# --- comando_encode / preparar_arquivos -----------------------------------------------------------

def test_imagem_estatica_vira_clipe_com_ken_burns_leve():
    # `-loop 1` repete um quadro; -stream_loop -1 no image2 nao respeita -t
    b = {"src_file": "foto.png", "start": 0, "s": 1.0, "d": 3.9, "label": "x"}
    cmd = B.comando_encode(b, "saida/broll01.mp4")
    assert cmd == ["ffmpeg", "-y", "-loop", "1", "-i", "foto.png", "-t", "5.0",
                   "-vf", "zoompan=z='min(zoom+0.0007,1.06)':d=150:s=1080x1920:fps=30",
                   "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                   "-movflags", "+faststart", "-an", "saida/broll01.mp4"]


@pytest.mark.parametrize("nome", ["a.jpg", "a.JPEG", "a.PNG", "a.webp"])
def test_extensoes_de_imagem_sao_reconhecidas_sem_olhar_a_caixa(nome):
    b = {"src_file": nome, "start": 0, "s": 0, "d": 2.0, "label": "x"}
    assert "-loop" in B.comando_encode(b, "o.mp4")


def test_video_com_fonte_suficiente_nao_faz_laco(monkeypatch):
    monkeypatch.setattr(B, "vdur", lambda f: 20.0)
    b = {"src_file": "v.mp4", "start": 2.0, "s": 1.0, "d": 4.0, "label": "x"}
    cmd = B.comando_encode(b, "o.mp4")
    assert "-stream_loop" not in cmd
    assert cmd == ["ffmpeg", "-y", "-ss", "2.0", "-t", "5.1", "-i", "v.mp4",
                   "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                   "-vsync", "cfr", "-r", "30",
                   "-g", "15", "-keyint_min", "15", "-sc_threshold", "0",
                   "-force_key_frames", "expr:eq(n,0)",
                   "-movflags", "+faststart", "-an", "o.mp4"]


def test_video_curto_faz_laco_antes_do_resto(monkeypatch):
    monkeypatch.setattr(B, "vdur", lambda f: 3.0)      # 3,0 - 2,0 = 1,0 de fonte, precisa de 4,6
    b = {"src_file": "v.mp4", "start": 2.0, "s": 1.0, "d": 4.0, "label": "x"}
    cmd = B.comando_encode(b, "o.mp4")
    assert cmd[:4] == ["ffmpeg", "-y", "-stream_loop", "-1"]
    assert cmd[4:6] == ["-ss", "2.0"]


def test_preparar_arquivos_nomeia_broll01_broll02_e_roda_o_ffmpeg(tmp_path, monkeypatch):
    rodados = []
    monkeypatch.setattr(B, "vdur", lambda f: 99.0)
    monkeypatch.setattr(B, "run", lambda cmd: (rodados.append(cmd), open(cmd[-1], "wb").write(b"x")))
    brolls = [{"src_file": "a.mp4", "start": 0, "s": 0, "d": 2.0, "label": "a"},
              {"src_file": "b.png", "start": 0, "s": 5, "d": 2.0, "label": "b"}]
    B.preparar_arquivos(brolls, tmp_path)
    assert [b["src"] for b in brolls] == ["broll01.mp4", "broll02.mp4"]
    assert [c[-1] for c in rodados] == [str(tmp_path / "broll01.mp4"), str(tmp_path / "broll02.mp4")]


def test_broll_truncado_de_0_bytes_e_refeito_e_o_inteiro_e_reaproveitado(tmp_path, monkeypatch):
    # processo morto no meio do encode deixava um arquivo de 0 bytes que o cache reusava para sempre
    rodados = []
    monkeypatch.setattr(B, "vdur", lambda f: 99.0)
    monkeypatch.setattr(B, "run", lambda cmd: (rodados.append(cmd[-1]), open(cmd[-1], "wb").write(b"novo")))
    (tmp_path / "broll01.mp4").write_bytes(b"")
    (tmp_path / "broll02.mp4").write_bytes(b"bom")
    brolls = [{"src_file": "a.mp4", "start": 0, "s": 0, "d": 2.0, "label": "a"},
              {"src_file": "b.mp4", "start": 0, "s": 5, "d": 2.0, "label": "b"}]
    B.preparar_arquivos(brolls, tmp_path)
    assert rodados == [str(tmp_path / "broll01.mp4")]
    assert (tmp_path / "broll02.mp4").read_bytes() == b"bom"
    assert brolls[1]["src"] == "broll02.mp4"


# --- grupos e wipes ---------------------------------------------------------------------------------

def test_brolls_a_menos_de_0_6s_um_do_outro_sao_o_mesmo_grupo():
    brolls = [{"s": 2.0, "d": 3.0}, {"s": 5.5, "d": 2.0}, {"s": 9.0, "d": 1.0}]
    assert B.agrupar(brolls) == [(2.0, 7.5), (9.0, 10.0)]


def test_wipe_so_de_entrada_e_nunca_na_abertura_nem_no_fim_do_hook():
    assert B.XFADE_GAP == 0.6
    grupos = [(0.0, 3.0), (2.2, 4.0), (6.0, 8.0), (0.34, 1.0)]
    # 0,0 e a abertura; 2,2 cai a 0,026 do fim do hook (2,174); 0,34 nao passa de 0,34
    assert B.wipes_de_entrada(grupos) == [5.66]
    assert K.HOOK_END == 2.174


# --- HTML -------------------------------------------------------------------------------------------

def test_html_dos_brolls_usa_as_faixas_8_9_e_50():
    modelo = ("a\n<!-- B-ROLLS (injected) -->\nVELHO\n      <!-- LOWER THIRD -->\n"
              "const BROLLS = [{\"id\": \"b1\"}];\nz")
    brolls = [{"src": "broll01.mp4", "s": 2.5, "d": 3.0, "label": "ACOMPANHE"},
              {"src": "broll02.mp4", "s": 7.0, "d": 4.5, "label": "DEPOIS"}]
    html = B.injetar_html(modelo, brolls)
    assert "VELHO" not in html
    assert ('<div id="b1_scrim" class="broll-scrim clip" data-start="2.5" data-duration="3.0" '
            'data-track-index="9"></div>') in html
    assert ('<div id="b1_tag" class="broll-tag clip" data-start="2.5" data-duration="3.0" '
            'data-track-index="50"><span class="t">ACOMPANHE</span></div>') in html
    assert ('<video id="b1_vid" class="broll-vid clip" src="broll01.mp4" muted playsinline '
            'data-start="2.5" data-duration="3.0" data-track-index="8"></video>') in html
    # k = 1: faixas 10, 11 e 51
    assert 'id="b2_scrim" class="broll-scrim clip" data-start="7.0" data-duration="4.5" data-track-index="11"' in html
    assert 'data-track-index="51"><span class="t">DEPOIS</span>' in html
    assert 'src="broll02.mp4" muted playsinline data-start="7.0" data-duration="4.5" data-track-index="10"' in html
    esperado = [{"id": "b1", "src": "broll01.mp4", "start": 2.5, "dur": 3.0, "tk": 8, "sk": 9},
                {"id": "b2", "src": "broll02.mp4", "start": 7.0, "dur": 4.5, "tk": 10, "sk": 11}]
    assert "const BROLLS = " + json.dumps(esperado, ensure_ascii=False) + ";" in html
    assert html.startswith("a\n<!-- B-ROLLS (injected) -->\n<div id=\"b1_scrim\"")
    assert "\n\n      <!-- LOWER THIRD -->" in html


def test_onze_brolls_ficam_abaixo_da_trilha_das_legendas():
    # banda 8..29: com 11 brolls o ultimo usa as faixas 28 e 29, abaixo de #caps (30)
    modelo = "<!-- B-ROLLS (injected) -->\nx\n<!-- LOWER THIRD -->\nconst BROLLS = [];"
    brolls = [{"src": f"broll{k:02d}.mp4", "s": float(k), "d": 1.0, "label": "x"} for k in range(1, 12)]
    html = B.injetar_html(modelo, brolls)
    assert 'id="b11_vid" class="broll-vid clip" src="broll11.mp4" muted playsinline data-start="11.0" ' \
           'data-duration="1.0" data-track-index="28"' in html
    assert 'id="b11_scrim" class="broll-scrim clip" data-start="11.0" data-duration="1.0" data-track-index="29"' in html


def test_label_com_barra_invertida_nao_quebra_o_html():
    modelo = "<!-- B-ROLLS (injected) -->\nx\n<!-- LOWER THIRD -->\nconst BROLLS = [];"
    html = B.injetar_html(modelo, [{"src": "broll01.mp4", "s": 0.0, "d": 1.0, "label": r"C:\dir\1"}])
    assert r'<span class="t">C:\dir\1</span>' in html


def test_sem_brolls_o_bloco_fica_vazio():
    modelo = "<!-- B-ROLLS (injected) -->\nvelho\n<!-- LOWER THIRD -->\nconst BROLLS = [1];"
    html = B.injetar_html(modelo, [])
    assert html == "<!-- B-ROLLS (injected) -->\n\n\n      <!-- LOWER THIRD -->\nconst BROLLS = [];"
