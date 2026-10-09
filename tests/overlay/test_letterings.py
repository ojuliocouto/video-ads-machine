"""overlay.letterings: onde cada lettering entra, a pilha da lista e a trava de layout.

Os números vêm dos comentários de defeito do `gen_ad_v2.py` original:

  - âncora = n-ésima ocorrência da palavra (normalizada); sem âncora o motor para;
  - o lettering dentro do split desce para o peito (flag split);
  - bloco do roteiro com "+ logo" põe o logo DENTRO do lettering, na mesma janela;
  - a pilha junta as linhas num bloco só, cada uma entra na hora da própria palavra;
  - a trava de layout roda DEPOIS da fusão da pilha: se rodasse antes, a fusão recalcularia
    a duração pela última linha e apagaria o corte;
  - o adiamento mantém a duração PEDIDA: "SABE / por que?" pedia 1,8 s e sobreviveu com 0,47 s;
  - o `l["start"]` era reatribuído antes do cálculo dos delays, e o ajuste da pilha era no-op.
"""
import pytest

from overlay import letterings as L


def palavras(texto, passo=0.5, inicio=0.0):
    out = []
    for i, t in enumerate(texto.split()):
        a = inicio + i * passo
        out.append({"text": t, "start": a, "end": a + passo * 0.8})
    return out


def lett(key="K", start=10.0, dur=2.0, split=False, linhas=None, **extra):
    d = {"id": "lettA", "lead": "lead", "key": key, "start": start, "dur": dur,
         "split": split, "logo": False, "baixo": False, "pilha": None}
    if linhas is not None:
        d["linhas"] = linhas
    d.update(extra)
    return d


# --- calcular -----------------------------------------------------------------------------------

def test_ancora_e_a_enesima_ocorrencia_da_palavra_normalizada():
    words = palavras("Você perde três horas e perde mais")
    cfg = [{"lead": "a", "key": "B", "anchor": "PERDE", "nth": 2, "dur": 1.6}]
    saida = L.calcular(cfg, words, [(0.0, 99.0)], [{"instr": "x"}], [])
    assert saida == [{"id": "lettA", "lead": "a", "key": "B", "start": 2.5, "dur": 1.6, "split": False,
                      "logo": False, "baixo": False, "pilha": None}]


def test_anchor_com_acento_e_pontuacao_casa_pela_forma_normalizada():
    words = [{"text": "páginas,", "start": 1.0, "end": 1.4}]
    cfg = [{"lead": "", "key": "K", "anchor": "paginas"}]
    assert L.calcular(cfg, words, [(0.0, 9.0)], [{"instr": "x"}], [])[0]["start"] == 1.0


def test_duracao_padrao_e_2_2_e_nth_padrao_e_1():
    words = palavras("a b a")
    saida = L.calcular([{"lead": "", "key": "K", "anchor": "a"}], words, [(0, 9)], [{"instr": "x"}], [])
    assert saida[0]["dur"] == 2.2 and saida[0]["start"] == 0.0


def test_sem_ancora_o_motor_para_citando_o_lettering():
    cfg = {"lead": "l", "key": "K", "anchor": "inexistente"}
    with pytest.raises(SystemExit) as e:
        L.calcular([cfg], palavras("a b"), [(0, 9)], [{"instr": "x"}], [])
    assert str(e.value) == f"lettering sem ancora: {cfg}"


def test_nth_alem_das_ocorrencias_tambem_para():
    with pytest.raises(SystemExit):
        L.calcular([{"lead": "", "key": "K", "anchor": "a", "nth": 3}], palavras("a b a"),
                   [(0, 9)], [{"instr": "x"}], [])


def test_lettering_dentro_do_split_desce_pro_peito():
    # no split o apresentador mora na metade de baixo e o lettering centrado pousa no rosto
    words = palavras("um dois tres quatro")                        # "tres" em 1,0
    cfg = [{"lead": "", "key": "K", "anchor": "tres"}, {"lead": "", "key": "K2", "anchor": "um"}]
    saida = L.calcular(cfg, words, [(0, 9)], [{"instr": "x"}], [(0.5, 1.5)])
    assert [x["split"] for x in saida] == [True, False]
    assert [x["id"] for x in saida] == ["lettA", "lettB"]


def test_janela_de_split_e_aberta_no_fim():
    words = palavras("um dois")                                   # "dois" em 0,5
    saida = L.calcular([{"lead": "", "key": "K", "anchor": "dois"}], words, [(0, 9)], [{"instr": "x"}],
                       [(0.0, 0.5)])
    assert saida[0]["split"] is False


def test_bloco_com_logo_na_instrucao_leva_o_logo_junto_do_lettering(capsys):
    words = palavras("a b c d")                                   # "c" em 1,0 -> bloco 1
    blocos = [{"instr": "insert"}, {"instr": "apresentador + lettering + Logo do evento"}]
    saida = L.calcular([{"lead": "", "key": "K", "anchor": "c"}], words, [(0, 1.0), (1.0, 9.0)], blocos, [])
    assert saida[0]["logo"] is True
    assert "[logo] roteiro pede logo no bloco 1: entra junto do lettering em 1.00s" in capsys.readouterr().out


def test_lettering_fora_de_qualquer_bloco_nao_leva_logo():
    words = palavras("a b c")
    saida = L.calcular([{"lead": "", "key": "K", "anchor": "c"}], words, [(0, 0.5)], [{"instr": "logo"}], [])
    assert saida[0]["logo"] is False


def test_baixo_e_pilha_viram_campos_do_lettering():
    saida = L.calcular([{"lead": "", "key": "K", "anchor": "a", "baixo": 1, "pilha": "ganhos"}],
                       palavras("a"), [(0, 9)], [{"instr": "x"}], [])
    assert saida[0]["baixo"] is True and saida[0]["pilha"] == "ganhos"


# --- fundir_pilhas -----------------------------------------------------------------------------------

def test_pilha_junta_as_linhas_com_delay_relativo_e_nenhuma_sai_antes_do_fim():
    ls = [lett("a", 5.0, 2.0, pilha="g"), lett("b", 6.0, 2.0, pilha="g"), lett("c", 7.5, 2.0, pilha="g")]
    saida = L.fundir_pilhas(ls)
    assert len(saida) == 1
    base = saida[0]
    assert base["key"] == "a" and base["start"] == 5.0
    assert base["linhas"] == [{"key": "a", "delay": 0.0}, {"key": "b", "delay": 1.0}, {"key": "c", "delay": 2.5}]
    assert base["dur"] == 4.5                       # de 5,0 ate o fim da ultima linha (9,5)


def test_pilha_preserva_a_ordem_e_deixa_lettering_solto_como_esta():
    ls = [lett("a", 5.0, 2.0, pilha="g"), lett("solto", 8.0, 1.5), lett("b", 9.0, 2.0, pilha="g")]
    saida = L.fundir_pilhas(ls)
    assert [x["key"] for x in saida] == ["a", "solto"]
    assert "linhas" not in saida[1]
    assert saida[0]["dur"] == 6.0                   # 5,0 ate 11,0


def test_pilhas_diferentes_ficam_separadas():
    ls = [lett("a", 1.0, 1.0, pilha="g1"), lett("b", 2.0, 1.0, pilha="g2")]
    saida = L.fundir_pilhas(ls)
    assert [len(x["linhas"]) for x in saida] == [1, 1]


# --- travar_no_layout --------------------------------------------------------------------------------------

def test_lettering_que_atravessa_a_troca_de_layout_e_encurtado(capsys):
    ls = [lett("PRODUZIR AS PAGINAS PRONTAS HOJE", 10.0, 3.0)]
    L.travar_no_layout(ls, [(5.0, 11.5)])
    assert ls[0]["dur"] == 1.4                      # 11,5 - 10,0 - 0,10
    assert ls[0]["start"] == 10.0
    assert ls[0]["split"] is True                   # 5,0 <= 10,0 < 11,5
    assert ("[layout] lettering 'PRODUZIR AS PAGINAS PRONTA' encurtado de 3.00s pra 1.40s: "
            "o quadro troca de layout em 11.50s") in capsys.readouterr().out


def test_encurtar_respeita_o_piso_de_1_20s():
    ls = [lett("K", 10.0, 3.0)]
    L.travar_no_layout(ls, [(5.0, 11.3)])           # novo = 1,20: ainda encurta
    assert ls[0]["dur"] == 1.2 and ls[0]["start"] == 10.0


def test_nao_cabendo_antes_da_troca_o_lettering_e_adiado_e_a_duracao_pedida_se_mantem(capsys):
    # 1,8 s pedido; o adiamento descontava o tempo que NAO chegou a ficar na tela e sobrava 0,47 s
    ls = [lett("SABE POR QUE?", 10.0, 1.8)]
    L.travar_no_layout(ls, [(5.0, 11.23)])          # novo = 1,13 < 1,20 -> adia pra 11,33
    assert ls[0]["start"] == 11.33
    assert ls[0]["dur"] == 1.8
    assert ls[0]["split"] is False                  # 11,33 ja esta fora do split
    assert ("adiado de 10.00s pra 11.33s: nao cabe antes da troca (duracao mantida em 1.80s)"
            in capsys.readouterr().out)


def test_adiar_nunca_deixa_a_duracao_abaixo_do_piso():
    ls = [lett("K", 10.0, 0.5)]
    L.travar_no_layout(ls, [(5.0, 10.2)])
    assert ls[0]["dur"] == 1.2 and ls[0]["start"] == 10.3


def test_adiamento_desloca_os_delays_da_pilha_pelo_deslocamento_real():
    # o `start` era reatribuido antes do calculo, entao o deslocamento dava sempre zero
    ls = [lett("a", 10.0, 3.0, linhas=[{"key": "a", "delay": 0.0}, {"key": "b", "delay": 1.5},
                                       {"key": "c", "delay": 0.4}])]
    L.travar_no_layout(ls, [(5.0, 11.23)])          # desloc = 1,33
    assert ls[0]["start"] == 11.33
    assert [x["delay"] for x in ls[0]["linhas"]] == [0.0, 0.17, 0.0]
    assert ls[0]["dur"] == 3.0


def test_so_a_primeira_borda_que_atravessa_conta():
    ls = [lett("K", 10.0, 3.0)]
    L.travar_no_layout(ls, [(10.5, 11.5), (12.0, 20.0)])
    # primeira janela: borda 10,5 -> novo = 0,40 < 1,20 -> adiado pra 10,6 (so uma vez, `break`)
    assert ls[0]["start"] == 10.6 and ls[0]["dur"] == 3.0


def test_borda_exatamente_no_inicio_ou_no_fim_nao_atravessa():
    ls = [lett("K", 10.0, 3.0)]
    L.travar_no_layout(ls, [(10.0, 13.0)])
    assert (ls[0]["start"], ls[0]["dur"]) == (10.0, 3.0)
    assert ls[0]["split"] is False                                  # sem borda, nao recalcula


def test_lettering_que_nao_toca_janela_nenhuma_nao_muda():
    ls = [lett("K", 10.0, 2.0, split=True)]
    L.travar_no_layout(ls, [(30.0, 40.0)])
    assert (ls[0]["start"], ls[0]["dur"], ls[0]["split"]) == (10.0, 2.0, True)


# --- finalizar / montar -------------------------------------------------------------------------------------

def test_a_trava_roda_depois_da_fusao_da_pilha():
    # duas linhas: a fusao daria dur 3,0 (10,0 a 13,0). A janela de split fecha em 12,0, entao a
    # trava corta em 12,0 - 10,0 - 0,10 = 1,9. Se a trava rodasse ANTES, a fusao apagaria o corte.
    cfg = [{"lead": "", "key": "linha a", "anchor": "um", "dur": 2.0, "pilha": "g"},
           {"lead": "", "key": "linha b", "anchor": "dois", "dur": 2.0, "pilha": "g"}]
    words = [{"text": "um", "start": 10.0, "end": 10.4}, {"text": "dois", "start": 11.0, "end": 11.4}]
    letts, janelas = L.montar(cfg, words, [(0.0, 99.0)], [{"instr": "x"}], [(5.0, 12.0)])
    assert len(letts) == 1
    assert letts[0]["dur"] == 1.9
    assert janelas == [(10.0, 11.9)]
    assert letts[0]["linhas"] == [{"key": "linha a", "delay": 0.0}, {"key": "linha b", "delay": 1.0}]


def test_ids_sao_renumerados_depois_da_fusao_e_as_janelas_acompanham(capsys):
    cfg = [{"lead": "", "key": "a", "anchor": "um", "pilha": "g"},
           {"lead": "", "key": "solto", "anchor": "dois"},
           {"lead": "", "key": "b", "anchor": "tres", "pilha": "g"}]
    words = palavras("um dois tres", passo=3.0)
    letts, janelas = L.montar(cfg, words, [(0.0, 99.0)], [{"instr": "x"}], [])
    assert [x["id"] for x in letts] == ["lettA", "lettB"]
    assert [x["key"] for x in letts] == ["a", "solto"]
    assert janelas == [(0.0, 8.2), (3.0, 5.2)]
    assert "[pilha] lettA: 2 linhas, 0.00s por 8.20s (delays [0.0, 6.0])" in capsys.readouterr().out


def test_sem_letterings_nao_ha_janelas():
    assert L.montar([], palavras("a"), [(0, 9)], [{"instr": "x"}], []) == ([], [])


# --- html ---------------------------------------------------------------------------------------------------

def test_html_de_um_lettering_simples():
    l = lett("O MELHOR", 7.1, 1.6, id="lettA", lead="sabe qual é")
    assert L.html([l]) == (
        '<div class="lett clip" id="lettA" data-start="7.1" data-duration="1.6" data-track-index="32">\n'
        '  <div class="lead">sabe qual é</div>\n'
        '  <div class="key">O MELHOR</div>\n'
        '</div>')


def test_key_com_mais_de_18_caracteres_ganha_key_longa():
    l = lett("PRODUZIR AS PÁGINAS", id="lettA")         # 19 caracteres
    assert '<div class="key key-longa">PRODUZIR AS PÁGINAS</div>' in L.html([l])
    l = lett("PRODUZIR AS PÁGINA", id="lettA")          # 18: nao ganha
    assert '<div class="key">PRODUZIR AS PÁGINA</div>' in L.html([l])


def test_classes_split_baixo_e_pilha_e_a_trilha_sobe_de_um_em_um():
    a = lett("a", id="lettA", split=True, baixo=True)
    b = lett("b", id="lettB", linhas=[{"key": "x", "delay": 0.0}])
    html = L.html([a, b])
    assert ('class="lett clip lett-split lett-baixo" id="lettA" data-start="10.0" '
            'data-duration="2.0" data-track-index="32">') in html
    assert ('class="lett clip lett-pilha" id="lettB" data-start="10.0" '
            'data-duration="2.0" data-track-index="33">') in html


def test_pilha_vira_uma_linha_key_por_item_com_o_delay_de_cada_uma():
    l = lett("a", id="lettA", linhas=[{"key": "✓ em minutos", "delay": 0.0},
                                      {"key": "❌ sem pagar nada", "delay": 1.25}])
    html = L.html([l])
    assert '  <div class="key" data-delay="0.0">em minutos</div>\n' in html
    assert '  <div class="key" data-delay="1.25">sem pagar nada</div>\n' in html


def test_emoji_sai_do_lettering_inclusive_no_ramo_da_pilha():
    # o ramo da PILHA era o unico que mandava o texto cru: o anuncio saiu com emoji 3,87 s
    l = lett("K", id="lettA", lead="\U0001F680 olha", linhas=[{"key": "❌ dor", "delay": 0.0}])
    html = L.html([l])
    assert "❌" not in html and "\U0001F680" not in html
    assert '<div class="lead">olha</div>' in html


def test_logo_entra_dentro_do_lettering():
    l = lett("K", id="lettA", logo=True)
    assert L.html([l]).endswith('  <img class="lett-logo" src="logo.png" alt="">\n</div>')
