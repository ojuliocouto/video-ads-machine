"""overlay.legendas: os grupos de legenda que sobram depois do hook, do CTA e dos letterings.

Defeitos do `gen_ad_v2.py` original reproduzidos aqui:

  - legenda não aparece enquanto o hook está na tela (cap_gate) nem a partir da janela do logo;
  - o grupo que atravessa a fronteira do logo é truncado, não descartado;
  - o eco (a mesma frase na legenda e no lettering) é descartado por inteiro, inclusive o grupo
    que só ENCOSTA no lettering ("o pulo do" fechava 0,05 s antes de "o pulo do gato");
  - legenda e lettering não dividem a tela: folga de 0,35 s de cada lado, e sobra de legenda
    com menos de 0,60 s não entra (um piscar de duas palavras é ruído);
  - o eco parcial foi REVERTIDO (31/08/2026): cortar só as palavras repetidas deixava a frase muda.
"""
from pathlib import Path

import pytest

import build_timeline
from overlay import legendas as G


def pal(texto, a, b, **extra):
    d = {"text": texto, "start": a, "end": b}
    d.update(extra)
    return d


def grupo(*palavras):
    return {"start": palavras[0]["start"], "end": palavras[-1]["end"], "words": list(palavras)}


def lett(lead, key, start, dur, linhas=None):
    d = {"lead": lead, "key": key, "start": start, "dur": dur}
    if linhas:
        d["linhas"] = linhas
    return d


def test_constantes():
    assert (G.FOLGA_LETT, G.PECA_MIN, G.LETT_LOOKBACK, G.MAX_PALAVRAS) == (0.35, 0.60, 2.6, 3)


# --- agrupar ---------------------------------------------------------------------------------

def test_agrupar_fecha_em_3_palavras_ou_na_pontuacao_e_segura_a_frase_na_pausa():
    words = [pal("Oi", 0.0, 0.3), pal("pessoal.", 0.3, 0.8), pal("Tudo", 2.0, 2.3), pal("bem", 2.3, 2.6),
             pal("com", 2.6, 2.9), pal("voce", 5.0, 5.4)]
    gs = G.agrupar(words)
    assert [[w["text"] for w in g["words"]] for g in gs] == [["Oi", "pessoal."], ["Tudo", "bem", "com"], ["voce"]]
    # a legenda acompanha o pensamento: segura ate 1,6 s ou ate 0,06 s antes do proximo
    assert [g["end"] for g in gs] == [1.94, 4.5, 5.4]


def test_agrupar_e_o_mesmo_que_o_build_timeline():
    words = [pal("a", 0.0, 0.2), pal("b", 0.2, 0.4)]
    assert G.agrupar(words) == build_timeline.group_captions(words, max_words=3)


# --- filtrar_corpo -------------------------------------------------------------------------------

def test_so_ficam_os_grupos_depois_do_hook_e_antes_da_janela_do_logo():
    gs = [grupo(pal("a", 1.0, 1.5)), grupo(pal("b", 3.0, 3.5)), grupo(pal("c", 5.0, 5.5)),
          grupo(pal("d", 9.9, 10.4)), grupo(pal("e", 9.96, 10.4)), grupo(pal("f", 12.0, 12.5))]
    saida = G.filtrar_corpo(gs, 3.0, 10.0)
    assert [g["words"][0]["text"] for g in saida] == ["c", "d"]       # 3,0 exato nao passa (estrito)


# --- fechar_grupos ---------------------------------------------------------------------------------

def test_grupo_sem_palavra_ou_com_menos_de_0_20s_sai():
    vazio = {"start": 1.0, "end": 3.0, "words": []}
    curto = grupo(pal("a", 4.0, 4.19))
    ok = grupo(pal("b", 5.0, 5.2))
    assert G.fechar_grupos([vazio, curto, ok], 99.0) == [ok]


def test_grupo_que_atravessa_o_logo_e_truncado_nao_descartado():
    # "o motor e mais." ficava atras do wordmark: corta ate o ultimo instante livre
    g = grupo(pal("o", 8.0, 8.5), pal("motor", 8.5, 11.0))
    saida = G.fechar_grupos([g], 10.0)
    assert saida == [g] and saida[0]["end"] == 10.0 and saida[0]["start"] == 8.0


def test_o_piso_de_0_20s_vale_depois_do_truncamento():
    """W3.X A1: o piso rodava ANTES de truncar no logo (herdado do gen_ad_v2.py:957-967), e o que o truncamento
    encurtava passava com 0,1 s ou até invertido. O piso é a última palavra: vale sobre o grupo como ele fica."""
    g = grupo(pal("a", 9.9, 11.0))                     # 1,1 s; vira 0,1 s depois de truncar: sai
    assert G.fechar_grupos([g], 10.0) == []


def test_grupo_empurrado_para_depois_do_logo_nunca_nasce_invertido():
    """O caso medido pela auditoria (dur_max com o CTA logo depois do último split): o grupo cortado na fronteira
    nasce em 13,37 e o logo entra em 13,25. Truncar daria início 13,37 e fim 13,25; o contrato da timeline recusa."""
    from overlay import layout_texto as LT

    g = {"start": 13.37, "end": 14.2, "words": [pal("um", 13.0, 13.2), pal("que", 13.4, 13.6), pal("dois", 13.7, 14.0)]}
    groups = [g]
    LT.empurrar_pos_split(groups, [(12.0, 13.25)])
    saida = G.fechar_grupos(groups, 13.25)
    assert all(x["start"] < x["end"] and x["end"] - x["start"] >= 0.20 for x in saida)
    assert saida == []


@pytest.mark.parametrize("logo", [5.0, 5.15, 5.3, 6.0, 9.0])
def test_nenhum_grupo_sai_do_fechamento_com_menos_de_0_20s_nem_invertido(logo):
    gs = [grupo(pal("a", 4.0, 4.5)), grupo(pal("b", 5.1, 5.6)), grupo(pal("c", 5.2, 5.25)),
          {"start": 7.0, "end": 6.0, "words": [pal("d", 6.0, 6.5)]}]
    for x in G.fechar_grupos(gs, logo):
        assert x["words"] and x["end"] - x["start"] >= 0.20, x


# --- eco do lettering -------------------------------------------------------------------------------

def test_frases_dos_letterings_juntam_lead_e_key_normalizados():
    fr = G.frases_dos_letterings([lett("O pulo<br>do", "GATO!", 10.0, 2.0)])
    assert fr == [(10.0, 12.0, {"o", "pulo", "do", "gato"})]


def test_pilha_usa_as_chaves_das_linhas_no_lugar_da_key():
    fr = G.frases_dos_letterings([lett("", "ignorada", 5.0, 3.0,
                                       linhas=[{"key": "em minutos", "delay": 0}, {"key": "sem pagar", "delay": 1}])])
    assert fr == [(5.0, 8.0, {"em", "minutos", "sem", "pagar"})]


FRASES = [(10.0, 12.0, {"o", "pulo", "do", "gato"})]


def test_legenda_que_fecha_logo_antes_do_lettering_e_eco():
    # ad08: "o pulo do" fechava 0,05 s ANTES de "o pulo do gato" comecar
    g = grupo(pal("o", 9.0, 9.3), pal("pulo", 9.3, 9.6), pal("do", 9.6, 9.95))
    assert G.eco_do_lettering(g, FRASES) is True


def test_legenda_com_palavra_fora_da_frase_nao_e_eco():
    g = grupo(pal("o", 9.0, 9.3), pal("salto", 9.3, 9.6))
    assert G.eco_do_lettering(g, FRASES) is False


def test_legenda_muito_antes_do_lettering_nao_e_eco_mesmo_com_as_mesmas_palavras():
    g = grupo(pal("o", 1.0, 1.3), pal("gato", 1.3, 1.9))          # fim 1,9 <= 10,0 - 2,6
    assert G.eco_do_lettering(g, FRASES) is False


def test_legenda_depois_do_lettering_e_eco_so_ate_0_2s_do_fim():
    assert G.eco_do_lettering(grupo(pal("gato", 12.1, 12.6)), FRASES) is True
    assert G.eco_do_lettering(grupo(pal("gato", 12.3, 12.8)), FRASES) is False


def test_grupo_sem_palavra_normalizavel_nao_e_eco():
    assert G.eco_do_lettering(grupo(pal("...", 10.0, 11.0)), FRASES) is False


# --- aparar_nos_letterings ------------------------------------------------------------------------------

def texto_longo(ini, fim, passo=0.5):
    n = int(round((fim - ini) / passo))
    return grupo(*[pal(f"p{i}", ini + i * passo, ini + (i + 1) * passo) for i in range(n)])


def test_eco_e_descartado_por_inteiro():
    ls = [lett("o pulo do", "gato", 10.0, 2.0)]
    eco = grupo(pal("o", 9.0, 9.3), pal("pulo", 9.3, 9.6), pal("do", 9.6, 9.95))
    assert G.aparar_nos_letterings([eco], ls, [(10.0, 12.0)]) == []


def test_legenda_longa_perde_so_o_miolo_do_lettering_com_folga_de_0_35s():
    ls = [lett("x", "Y", 10.0, 1.0)]
    saida = G.aparar_nos_letterings([texto_longo(7.0, 14.0)], ls, [(10.0, 11.0)])
    assert len(saida) == 2
    antes, depois = saida
    assert (antes["start"], antes["end"]) == (7.0, 9.65)
    assert (depois["start"], depois["end"]) == (11.35, 14.0)
    # as palavras acompanham a janela pelo MEIO de cada uma
    assert antes["words"][0]["text"] == "p0" and antes["words"][-1]["text"] == "p4"
    assert depois["words"][0]["text"] == "p9" and depois["words"][-1]["text"] == "p13"


def test_grupo_curto_dentro_da_folga_do_lettering_some():
    ls = [lett("x", "Y", 10.0, 1.0)]
    assert G.aparar_nos_letterings([grupo(pal("a", 10.1, 10.8))], ls, [(10.0, 11.0)]) == []


def test_pedaco_de_legenda_com_menos_de_0_60s_nao_entra():
    # um piscar de duas palavras entre dois letterings e ruido, nao informacao
    ls = [lett("x", "Y", 10.0, 1.0)]
    assert G.aparar_nos_letterings([texto_longo(9.2, 10.4, 0.3)], ls, [(10.0, 11.0)]) == []


def test_grupo_que_so_toca_a_folga_de_um_lado_fica_com_o_outro():
    ls = [lett("x", "Y", 10.0, 1.0)]
    saida = G.aparar_nos_letterings([texto_longo(8.0, 10.3)], ls, [(10.0, 11.0)])
    assert len(saida) == 1 and (saida[0]["start"], saida[0]["end"]) == (8.0, 9.65)


def test_grupo_longe_de_qualquer_lettering_passa_como_copia():
    ls = [lett("x", "Y", 10.0, 1.0)]
    g = texto_longo(20.0, 22.0)
    saida = G.aparar_nos_letterings([g], ls, [(10.0, 11.0)])
    assert saida == [g] and saida[0] is not g


def test_varios_letterings_aparam_em_sequencia():
    ls = [lett("x", "Y", 5.0, 1.0), lett("x", "Z", 10.0, 1.0)]
    saida = G.aparar_nos_letterings([texto_longo(3.0, 14.0)], ls, [(10.0, 11.0), (5.0, 6.0)])
    spans = [(round(g["start"], 2), round(g["end"], 2)) for g in saida]
    assert spans == [(3.0, 4.65), (6.35, 9.65), (11.35, 14.0)]


def test_sem_letterings_a_lista_passa_inteira():
    g = texto_longo(1.0, 3.0)
    assert G.aparar_nos_letterings([g], [], []) == [g]


# --- html ---------------------------------------------------------------------------------------------------

def test_html_e_o_do_build_timeline():
    gs = [dict(grupo(pal("oi", 1.0, 1.4, kw=True), pal("mundo", 1.4, 1.9)), costura=True, claro=True)]
    html = G.html(gs)
    assert html == build_timeline._render_captions_html(gs)
    assert "cgrp-costura" in html and "cgrp-claro" in html and 'class="cw kw"' in html


def test_html_sem_grupos_e_um_wrapper_vazio():
    assert G.html([]) == ('<div id="caps" class="clip" data-start="0" data-duration="0" '
                          'data-track-index="30"></div>')


def test_pedaco_de_0_55s_tambem_nao_entra_e_o_de_0_65s_entra():
    ls = [lett("x", "Y", 10.0, 1.0)]
    # a sobra antes do lettering vai de 9,1 a 9,65: 0,55 s, abaixo do piso de 0,60 s
    assert G.aparar_nos_letterings([texto_longo(9.1, 10.3, 0.3)], ls, [(10.0, 11.0)]) == []
    # de 9,0 a 9,65 sobram 0,65 s: entra
    saida = G.aparar_nos_letterings([texto_longo(9.0, 10.3, 0.3)], ls, [(10.0, 11.0)])
    assert len(saida) == 1 and (saida[0]["start"], saida[0]["end"]) == (9.0, 9.65)


def test_janela_retroativa_do_eco_e_de_2_6s():
    # o lettering comeca em 10,0: o grupo que termina depois de 7,4 ainda ecoa; antes disso, nao
    assert G.eco_do_lettering(grupo(pal("gato", 7.0, 7.6)), FRASES) is True
    assert G.eco_do_lettering(grupo(pal("gato", 6.9, 7.3)), FRASES) is False


# --- W5.A (pendência 12.3): a legenda que a timeline marcou como suprimida não chega ao overlay -------------

def _leg_tl(s, e, suprimida):
    return {"s": s, "e": e, "texto": "x", "palavras": [], "posicao": "padrao", "suprimida": suprimida}


def test_legenda_suprimida_na_timeline_sai_dos_grupos_do_overlay():
    gs = [grupo(pal("eu", 1.0, 1.2), pal("faço", 1.2, 1.6)), grupo(pal("toda", 2.0, 2.3), pal("semana", 2.3, 2.9))]
    tl = [_leg_tl(1.0, 1.6, False), _leg_tl(2.0, 2.9, True)]
    saida = G.filtrar_suprimidas(gs, tl)
    assert [g["start"] for g in saida] == [1.0]


def test_legenda_suprimida_nao_aparece_no_html_do_overlay():
    gs = [grupo(pal("eu", 1.0, 1.2), pal("faço", 1.2, 1.6)), grupo(pal("toda", 2.0, 2.3), pal("semana", 2.3, 2.9))]
    html = G.html(G.filtrar_suprimidas(gs, [_leg_tl(1.0, 1.6, False), _leg_tl(2.0, 2.9, True)]))
    assert "faço" in html and "semana" not in html


def test_sem_supressao_nada_muda_e_sem_timeline_tambem_nao():
    gs = [grupo(pal("eu", 1.0, 1.2))]
    assert G.filtrar_suprimidas(gs, [_leg_tl(1.0, 1.2, False)]) == gs
    assert G.filtrar_suprimidas(gs, None) == gs


def test_o_overlay_gerado_pela_timeline_filtra_as_suprimidas():
    """A fiação: o `overlay.gerar` passa as legendas da timeline ao filtro (senão a supressão nasce inerte)."""
    texto = (Path(__file__).resolve().parents[2] / "scripts" / "overlay" / "gerar.py").read_text(encoding="utf-8")
    assert "filtrar_suprimidas(" in texto
