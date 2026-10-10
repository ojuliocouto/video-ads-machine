"""overlay.layout_texto: onde o texto de tela pousa em cada layout (avatar cheio, split, insert).

É a fonte única das faixas de legenda e das regras de fronteira. Cada teste reproduz um
defeito medido que o `gen_ad_v2.py` original documenta em comentário:

  - "publicação" de 108,40 a 109,20 s, com o split terminando em 108,86, ficava 57,5%
    dentro do split e levava a legenda do avatar cheio para o rosto do painel de baixo;
  - "todo o processo" virava "todo o" por 0,178 s: dois flashes e um apagão no meio;
  - a antecipação do fade-in também atravessa a troca de layout (sem_lead);
  - 60% do grupo dentro do split decide a costura, e a folga de saída foi a zero;
  - um grupo que nasce a menos de 0,18 s do fim do split é empurrado para depois da guarda;
  - queixo abaixo de 60% da altura manda a legenda para o rodapé (nome de look não é critério);
  - o relógio da footage manda no tempo; o layout (split x cheio/pip) é do overlay.
"""
import json

from pathlib import Path

import pytest

from overlay import layout_texto as LT
from overlay.brolls import Visita


def pal(texto, a, b):
    return {"text": texto, "start": a, "end": b}


def grupo(*palavras, **extra):
    g = {"start": palavras[0]["start"], "end": palavras[-1]["end"], "words": list(palavras)}
    g.update(extra)
    return g


# --- constantes e classe -------------------------------------------------------------------

def test_faixas_de_cada_classe_de_legenda():
    assert LT.FAIXA_LEGENDA == {"costura": (963, 1106), "baixa": (1370, 1520), "padrao": (1290, 1500)}


def test_constantes_de_fronteira():
    assert (LT.GUARDA_MOTOR, LT.GUARDA_POS_SPLIT, LT.PISO_FATIA) == (0.12, 0.18, 0.30)


def test_costura_tem_prioridade_sobre_baixa_e_baixa_sobre_padrao():
    assert LT.classe_do_grupo({"costura": True, "baixa": True}) == "costura"
    assert LT.classe_do_grupo({"baixa": True}) == "baixa"
    assert LT.classe_do_grupo({}) == "padrao"


# --- janelas por visita -----------------------------------------------------------------------

def visita(i=0, icfg=None, s=0.0, e=10.0, s2=None, meus=None, cheias=None):
    s2 = s if s2 is None else s2
    return Visita(i=i, key="k", icfg=icfg or {"file": "a.mp4"}, s=s, e=e, s2=s2, dur=e - s2,
                  meus=meus if meus is not None else [(s2, e)], cheias=cheias or set())


def test_insert_de_tela_cheia_vai_para_janelas_de_texto_e_a_legenda_desce_pro_rodape():
    split, texto, mapa = LT.janelas_por_visita([visita(meus=[(2.0, 4.0), (6.0, 12.0)], e=10.0)])
    assert split == []
    # o fim e cortado no fim do bloco (min(b2, e))
    assert texto == [(2.0, 4.0), (6.0, 10.0)]


def test_insert_com_split_vai_para_janelas_de_split():
    split, texto, _ = LT.janelas_por_visita(
        [visita(icfg={"file": "a.mp4", "split": True}, meus=[(2.0, 4.0)], e=10.0)])
    assert split == [(2.0, 4.0)] and texto == []


def test_fatia_cheia_de_um_insert_split_conta_como_tela_cheia():
    # LAYOUT POR FATIA, NAO POR BLOCO (27/08/2026): a fatia `cheio` nao tem apresentador embaixo
    split, texto, _ = LT.janelas_por_visita(
        [visita(icfg={"file": "a.mp4", "split": True}, meus=[(2.0, 4.0), (6.0, 8.0)], e=10.0,
                cheias={(6.0, 8.0)})])
    assert split == [(2.0, 4.0)]
    assert texto == [(6.0, 8.0)]


def test_texto_proprio_acrescenta_a_janela_inteira_do_insert():
    _, texto, _ = LT.janelas_por_visita(
        [visita(icfg={"file": "a.mp4", "split": True, "texto_proprio": True}, s=1.0, e=9.0, s2=1.0,
                meus=[(1.0, 5.0)])])
    assert texto == [(1.0, 9.0)]


def test_mapa_do_insert_guarda_janela_fonte_start_e_velocidade():
    _, _, mapa = LT.janelas_por_visita(
        [visita(icfg={"file": "a.mp4", "start": 1.5, "speed": 2.0}, s=3.0, e=9.0, s2=3.0,
                meus=[(3.0, 5.0), (7.0, 12.0)])])
    assert mapa == [
        {"a": 3.0, "b": 5.0, "file": "a.mp4", "start": 1.5, "speed": 2.0, "s2": 3.0},
        {"a": 7.0, "b": 9.0, "file": "a.mp4", "start": 1.5, "speed": 2.0, "s2": 3.0}]


def test_mapa_do_insert_tem_start_0_e_velocidade_1_por_padrao():
    _, _, mapa = LT.janelas_por_visita([visita(icfg={"file": "a.mp4", "start": None}, meus=[(0.0, 4.0)])])
    assert (mapa[0]["start"], mapa[0]["speed"]) == (0.0, 1.0)


# --- o relogio da footage (28/08/2026) -----------------------------------------------------------

@pytest.fixture
def footage_json(tmp_path, monkeypatch):
    monkeypatch.setattr(LT, "V1", tmp_path)
    (tmp_path / "output").mkdir()

    def gravar(segs, ad="ad1", look="lk"):
        (tmp_path / "output" / f"{ad}_{look}_footage_1x_ritmo.json").write_text(
            json.dumps({"segs": segs}), encoding="utf-8")
    return gravar


def test_janelas_de_split_vem_da_footage_mas_so_as_que_o_overlay_chama_de_split(footage_json, capsys):
    # o insert `pip`/`cheio` e `split` no plano de ritmo cru e tela cheia na tela
    footage_json([{"s": 2.1, "e": 6.14, "layout": "split"},
                  {"s": 20.0, "e": 24.0, "layout": "split"},         # sem janela do overlay por perto
                  {"s": 30.0, "e": 32.0, "layout": "cheio"}])
    novo = LT.aplicar_relogio_footage("ad1", "lk", [(2.0, 6.0)])
    assert novo == [(2.1, 6.14)]
    saida = capsys.readouterr().out
    assert "[relogio] janelas de split da FOOTAGE (ad1_lk_footage_1x_ritmo.json): 1 no lugar das 1 do overlay" in saida
    assert "1 descartada(s): tela cheia (cheio/pip), nao split" in saida


def test_interseccao_exige_mais_de_0_05s_de_sobreposicao(footage_json):
    footage_json([{"s": 6.04, "e": 8.0, "layout": "split"}])
    # sobrepoe 6.04 a 6.0? nao: a janela do overlay termina em 6.0; sobreposicao negativa
    assert LT.aplicar_relogio_footage("ad1", "lk", [(2.0, 6.0)]) == [(2.0, 6.0)]
    footage_json([{"s": 5.96, "e": 8.0, "layout": "split"}])
    assert LT.aplicar_relogio_footage("ad1", "lk", [(2.0, 6.0)]) == [(2.0, 6.0)]      # 0,04 s: pouco
    footage_json([{"s": 5.9, "e": 8.0, "layout": "split"}])
    assert LT.aplicar_relogio_footage("ad1", "lk", [(2.0, 6.0)]) == [(5.9, 8.0)]      # 0,10 s: passa


def test_overlay_sem_janela_de_split_aceita_as_da_footage(footage_json, capsys):
    footage_json([{"s": 4.0, "e": 7.0, "layout": "split"}])
    assert LT.aplicar_relogio_footage("ad1", "lk", []) == [(4.0, 7.0)]
    assert "1 janelas (overlay nao marcou nenhuma)" in capsys.readouterr().out


def test_nenhuma_janela_da_footage_encosta_nas_do_overlay_mantem_as_do_overlay(footage_json):
    footage_json([{"s": 40.0, "e": 45.0, "layout": "split"}])
    assert LT.aplicar_relogio_footage("ad1", "lk", [(2.0, 6.0)]) == [(2.0, 6.0)]


def test_sem_json_da_footage_ou_com_json_ilegivel_segue_com_o_do_overlay(tmp_path, footage_json, capsys):
    assert LT.aplicar_relogio_footage("ad1", "lk", [(2.0, 6.0)]) == [(2.0, 6.0)]     # primeira rodada
    (tmp_path / "output" / "ad1_lk_footage_1x_ritmo.json").write_text("{nao e json", encoding="utf-8")
    assert LT.aplicar_relogio_footage("ad1", "lk", [(2.0, 6.0)]) == [(2.0, 6.0)]
    assert "footage json ilegivel" in capsys.readouterr().out


def test_footage_sem_nenhum_split_nao_mexe(footage_json):
    footage_json([{"s": 0.0, "e": 5.0, "layout": "cheio"}])
    assert LT.aplicar_relogio_footage("ad1", "lk", [(2.0, 6.0)]) == [(2.0, 6.0)]


# --- legenda em cima de card com texto proprio ------------------------------------------------------

def test_legenda_sobre_card_com_texto_desce_pro_rodape(capsys):
    gs = [grupo(pal("a", 1.0, 1.5)), grupo(pal("vendendo", 36.8, 37.5)), grupo(pal("b", 50.0, 50.5))]
    LT.descer_para_rodape_em_texto(gs, [(30.0, 40.0)])
    assert [bool(g.get("baixa")) for g in gs] == [False, True, False]
    assert "[texto_proprio] 1 grupo(s) de legenda descido(s) pro rodape sobre card com texto" in capsys.readouterr().out


def test_janela_de_texto_e_aberta_no_fim():
    g = grupo(pal("x", 40.0, 40.5))
    LT.descer_para_rodape_em_texto([g], [(30.0, 40.0)])
    assert "baixa" not in g


# --- look fechado: medido, nao pelo nome ---------------------------------------------------------------

def test_queixo_abaixo_de_60_por_cento_da_altura_manda_a_legenda_pro_rodape(capsys):
    gs = [grupo(pal("a", 1, 2)), grupo(pal("b", 3, 4), costura=True), grupo(pal("c", 5, 6), baixa=True)]
    LT.baixar_no_look_fechado(gs, "/x/avatar.mp4", medir=lambda v: (800, 400))      # 1200/1920 = 62,5%
    assert gs[0].get("baixa") is True
    assert "baixa" not in gs[1]                      # a costura nao vira rodape
    saida = capsys.readouterr().out
    assert "queixo do avatar em 62% da altura -> FECHADO, legenda no rodape" in saida
    assert "1 grupo(s) de legenda no rodape" in saida


def test_queixo_em_60_por_cento_exatos_e_aberto():
    gs = [grupo(pal("a", 1, 2))]
    LT.baixar_no_look_fechado(gs, "/x/avatar.mp4", medir=lambda v: (752, 400))      # 1152/1920 = 0,60
    assert "baixa" not in gs[0]


def test_queixo_alto_mantem_a_legenda_padrao(capsys):
    gs = [grupo(pal("a", 1, 2))]
    LT.baixar_no_look_fechado(gs, "/x/avatar.mp4", medir=lambda v: (700, 400))
    assert "baixa" not in gs[0]
    assert "aberto, legenda padrao" in capsys.readouterr().out


def test_medidor_que_falha_cai_no_plano_declarado_do_look(capsys):
    def quebra(video):
        raise RuntimeError("sem opencv")

    gs = [grupo(pal("a", 1, 2))]
    LT.baixar_no_look_fechado(gs, "/x/avatar_comum.mp4", medir=quebra)
    assert "baixa" not in gs[0]
    assert "nao consegui medir o avatar (sem opencv); caindo no plano declarado do look" in capsys.readouterr().out


# W3.X L10: o look fechado DECLARADO vem do looks.json do aluno (campo `plano`), nunca de nome de look do dono
# escrito no código. Nome de arquivo não é critério; o enquadramento medido é, e o plano declarado completa.

def test_plano_fechado_declarado_manda_a_legenda_pro_rodape_mesmo_sem_rosto():
    gs = [grupo(pal("a", 1, 2)), grupo(pal("b", 3, 4), costura=True)]
    LT.baixar_no_look_fechado(gs, "/x/ad_comum_avatar.mp4", medir=lambda v: None, plano_do_look="fechado")
    assert gs[0].get("baixa") is True and "baixa" not in gs[1]


@pytest.mark.parametrize("plano", [None, "medio", "aberto"])
def test_plano_que_nao_e_fechado_nao_baixa_a_legenda(plano):
    gs = [grupo(pal("a", 1, 2))]
    LT.baixar_no_look_fechado(gs, "/x/ad_comum_avatar.mp4", medir=lambda v: None, plano_do_look=plano)
    assert "baixa" not in gs[0]


def test_nome_de_look_no_arquivo_nao_decide_mais_nada():
    gs = [grupo(pal("a", 1, 2))]
    LT.baixar_no_look_fechado(gs, "/x/ad99_" + "of" + "13_avatar.mp4", medir=lambda v: None)
    assert "baixa" not in gs[0]


def test_o_modulo_nao_carrega_nome_de_look_do_dono():
    fonte = Path(LT.__file__).read_text(encoding="utf-8")
    for nome in ("oficial" + "_13", "_of" + "13"):
        assert nome not in fonte, nome
    assert not hasattr(LT, "NOMES_DE_LOOK_FECHADO")


def test_avatar_de_nome_comum_sem_rosto_nao_e_look_fechado():
    gs = [grupo(pal("a", 1, 2))]
    LT.baixar_no_look_fechado(gs, "/x/ad_comum_avatar.mp4", medir=lambda v: None)
    assert "baixa" not in gs[0]


def test_rosto_nao_detectado_nao_e_look_fechado():
    assert LT.look_fechado("/x/a.mp4", medir=lambda v: None) is False


# --- a fronteira de layout: o grupo nao atravessa ---------------------------------------------------------

def test_publicacao_fica_inteira_do_lado_do_split(capsys):
    # medido no anuncio longo: 108,40 a 109,20 com o split acabando em 108,86 (57,5% dentro)
    g = grupo(pal("publicação", 108.40, 109.20))
    saida = LT.cortar_na_fronteira([g], [(100.0, 108.86)])
    assert len(saida) == 1
    assert (saida[0]["start"], saida[0]["end"]) == (108.40, 108.74)      # para na fronteira - 0,12
    assert "[split] 1 grupo(s) de legenda cortado(s) na fronteira de layout" in capsys.readouterr().out


def test_grupo_com_a_fatia_depois_da_fronteira_maior_vai_pro_lado_de_fora():
    g = grupo(pal("palavra", 10.0, 10.9))           # mid 10,45 > borda 10,30
    saida = LT.cortar_na_fronteira([g], [(5.0, 10.30)])
    assert len(saida) == 1
    assert (saida[0]["start"], saida[0]["end"]) == (10.42, 10.9)         # borda + 0,12


def test_borda_perto_da_ponta_apara_em_vez_de_cortar():
    # borda a 0,05 do comeco: nao cabe cortar em dois (um lado ficaria com menos de 0,12)
    g = grupo(pal("a", 10.0, 10.4), pal("b", 10.4, 10.9))
    saida = LT.cortar_na_fronteira([g], [(1.0, 10.05)])
    assert len(saida) == 1
    assert (saida[0]["start"], saida[0]["end"]) == (10.17, 10.9)
    assert len(saida[0]["words"]) == 2               # nao filtra palavras no ramo de aparar


def test_corte_em_duas_quando_as_duas_fatias_tem_pelo_menos_0_30s():
    g = grupo(pal("todo", 20.0, 20.25), pal("o", 20.25, 20.4), pal("processo", 20.4, 21.0))
    saida = LT.cortar_na_fronteira([g], [(10.0, 20.55)])
    assert len(saida) == 2
    antes, depois = saida
    assert [w["text"] for w in antes["words"]] == ["todo", "o"]
    assert (antes["start"], antes["end"]) == (20.0, 20.4)
    assert [w["text"] for w in depois["words"]] == ["processo"]
    assert (depois["start"], depois["end"]) == (20.67, 21.0)


def test_corte_em_duas_com_fatia_abaixo_de_0_30s_apara_tudo_pro_lado_dominante():
    # "todo o processo" virava "todo o" por 0,178 s e "processo" por 0,185 s: dois flashes
    g = grupo(pal("todo", 33.42, 33.52), pal("o", 33.52, 33.598), pal("processo", 33.6, 34.3))
    saida = LT.cortar_na_fronteira([g], [(30.0, 33.62)])
    assert len(saida) == 1
    assert (saida[0]["start"], saida[0]["end"]) == (33.74, 34.3)         # lado de fora, borda + 0,12
    assert len(saida[0]["words"]) == 3


def test_as_duas_fatias_curtas_e_sem_lado_dominante_tiram_o_grupo_da_tela():
    """W7.Z: antes o grupo ficava como estava e atravessava a troca com a posição do outro layout."""
    g = grupo(pal("a", 1.0, 1.15), pal("b", 1.15, 1.3), pal("c", 1.3, 1.5))
    assert LT.cortar_na_fronteira([g], [(0.0, 1.25)]) == []


def test_grupo_que_nao_atravessa_nenhuma_borda_passa_inteiro():
    g = grupo(pal("a", 50.0, 50.5))
    saida = LT.cortar_na_fronteira([g], [(1.0, 10.0)])
    assert saida == [g] and saida[0] is g


def test_fatia_nasce_sem_lead_quando_comeca_perto_de_uma_borda():
    # A ANTECIPACAO DO FADE-IN TAMBEM ATRAVESSA: a janela cobre GUARDA_MOTOR + o lead de 0,12 s
    perto = grupo(pal("a", 10.2, 10.7))
    longe = grupo(pal("b", 12.0, 12.5))
    saida = LT.cortar_na_fronteira([perto, longe], [(1.0, 10.0)])
    assert saida[0].get("sem_lead") is True
    assert "sem_lead" not in saida[1]


def test_a_janela_do_sem_lead_e_0_35s_de_cada_lado_da_borda():
    for inicio, esperado in ((10.34, True), (10.36, False), (9.66, True), (9.64, False)):
        g = grupo(pal("a", inicio, inicio + 0.5))
        saida = LT.cortar_na_fronteira([g], [(1.0, 10.0)])
        assert bool(saida[0].get("sem_lead")) is esperado, inicio


def test_sem_janela_de_split_nada_muda_e_nada_imprime(capsys):
    g = grupo(pal("a", 1.0, 2.0))
    assert LT.cortar_na_fronteira([g], []) == [g]
    assert capsys.readouterr().out == ""


# --- costura: 60% do grupo dentro do split ----------------------------------------------------------------

def test_sessenta_por_cento_dentro_do_split_e_costura_e_perde_o_rodape(capsys):
    dentro = grupo(pal("a", 10.0, 11.25), baixa=True)          # 0,75 de 1,25 = 60% exatos
    fora = grupo(pal("b", 9.0, 11.0))                           # 0,5 de 2,0 = 25%
    LT.marcar_costura([dentro, fora], [(10.5, 20.0)])
    assert dentro.get("costura") is True and "baixa" not in dentro
    assert "costura" not in fora
    assert "1 grupo(s) de legenda na COSTURA dos paineis" in capsys.readouterr().out


def test_meio_dentro_nao_basta_a_pergunta_e_quanto_vive_dentro():
    # "pagina completamente diferente" tem o meio dentro do split e vive 0,3 a 0,9 s fora dele
    g = grupo(pal("pagina", 27.47, 28.77))
    LT.marcar_costura([g], [(20.0, 28.17)])                    # 0,70 de 1,30 = 53,8%
    assert "costura" not in g


def test_soma_a_sobreposicao_de_todas_as_janelas():
    g = grupo(pal("a", 10.0, 12.0))
    LT.marcar_costura([g], [(10.0, 10.8), (11.0, 11.6)])      # 0,8 + 0,6 = 1,4 de 2,0 = 70%
    assert g.get("costura") is True


# --- depois do split: a guarda de 0,18 s ---------------------------------------------------------------------

def test_grupo_que_nasce_colado_no_fim_do_split_e_empurrado_pra_depois_da_guarda():
    # o corte visual da footage vem ate 0,1 s depois do relogio do overlay
    g = grupo(pal("profissionais", 14.40, 15.0), pal("e", 15.0, 15.3))
    LT.empurrar_pos_split([g], [(5.0, 14.37)])
    assert g["start"] == 14.55
    assert [w["text"] for w in g["words"]] == ["profissionais", "e"]       # o meio de cada palavra >= 14,55


def test_palavra_que_ficaria_antes_do_novo_inicio_cai_fora():
    g = grupo(pal("uma", 14.40, 14.50), pal("frase", 14.60, 15.2))
    LT.empurrar_pos_split([g], [(5.0, 14.37)])
    assert g["start"] == 14.55
    assert [w["text"] for w in g["words"]] == ["frase"]


def test_grupo_que_nasce_longe_do_fim_do_split_nao_e_tocado():
    g = grupo(pal("a", 14.60, 15.0))
    LT.empurrar_pos_split([g], [(5.0, 14.37)])
    assert g["start"] == 14.60


def test_grupo_que_nasce_antes_do_fim_do_split_nao_e_tocado():
    g = grupo(pal("a", 14.00, 15.0))
    LT.empurrar_pos_split([g], [(5.0, 14.37)])
    assert g["start"] == 14.00


def test_o_piso_de_fatia_e_0_30s_nem_0_29_nem_0_31():
    # um lado com 0,31 s puxa o grupo inteiro para ele; com 0,29 s o grupo sai da tela (W7.Z: antes ficava como estava)
    g1 = grupo(pal("a", 10.0, 10.51))
    s1 = LT.cortar_na_fronteira([g1], [(1.0, 10.31)])
    assert (s1[0]["start"], s1[0]["end"]) == (10.0, 10.19)
    g2 = grupo(pal("a", 10.0, 10.51))
    assert LT.cortar_na_fronteira([g2], [(1.0, 10.29)]) == []


def test_costura_e_uma_so_a_tinta_medida_no_template():
    """W5.A (pendência 12.3): o CSS punha a tinta da costura em y 963 a 1106 (medido pela W4.D no render real, `bottom:
    790px` com padding de 24 px) e a faixa do layout dizia 1000 a 1130. Uma fonte só: a do que se mede na tela."""
    assert LT.FAIXA_LEGENDA["costura"] == (963, 1106)
    css = (Path(__file__).resolve().parents[2] / "templates" / "reel-editorial" / "index.html").read_text(encoding="utf-8")
    assert "#caps .cgrp.cgrp-costura { bottom:790px;" in css
