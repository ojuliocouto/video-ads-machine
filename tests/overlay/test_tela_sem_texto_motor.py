"""W5.X, pendência (d) da W5.A: o gate-ad acusou tela sem texto (15% do tempo) por dois descartes do MOTOR, que a
W5.A contornou mexendo no roteiro do e2e. O conserto é no motor:

  1. o grupo de legenda que COMEÇA enquanto o gancho está na tela era descartado inteiro, mesmo quando a fala dele
     continua depois que o gancho sai: a tela ficava vazia até o grupo seguinte. Invariante: grupo que termina
     depois do gancho (com o piso de 0,20 s de sobra) entra, aparado no fim do gancho;
  2. a KEY que não cabe antes da troca de layout é ADIADA, e a legenda da mesma frase (o eco) era descartada pela
     janela retroativa de 2,6 s: a frase saía da tela e o lettering só entrava depois da troca. Invariante: com o
     lettering adiado, só é eco o grupo que encosta nele (até FOLGA_ECO_ADIADO); o resto da legenda fica.
"""
from overlay import legendas as G
from overlay import letterings as L


def pal(texto, a, b):
    return {"text": texto, "start": a, "end": b}


def grupo(*palavras):
    return {"start": palavras[0]["start"], "end": palavras[-1]["end"], "words": list(palavras)}


def test_grupo_que_comeca_no_gancho_e_termina_depois_entra_aparado():
    g = grupo(pal("transformou", 2.9, 3.3), pal("meu", 3.3, 3.45), pal("Claude", 3.45, 3.8))
    saida = G.filtrar_corpo([g], 3.15, 99.0)
    assert len(saida) == 1 and saida[0]["start"] == 3.15 and saida[0]["end"] == 3.8
    assert [w["text"] for w in saida[0]["words"]] == ["transformou", "meu", "Claude"]


def test_grupo_que_mal_passa_do_gancho_nao_vira_piscar():
    g = grupo(pal("a", 2.9, 3.3))
    assert G.filtrar_corpo([g], 3.15, 99.0) == []


def test_eco_de_lettering_adiado_so_sai_se_encostar():
    letts = [{"lead": "sabe qual é", "key": "O MELHOR", "start": 12.34, "dur": 2.2}]
    letts[0]["adiado"] = True                    # o travar_no_layout marca (teste abaixo)
    eco_longe = grupo(pal("sabe", 10.0, 10.3), pal("qual", 10.3, 10.5), pal("é", 10.5, 10.7))
    saida = G.aparar_nos_letterings([eco_longe], letts, [(12.34, 14.54)])
    assert saida and [w["text"] for w in saida[0]["words"]] == ["sabe", "qual", "é"]
    eco_colado = grupo(pal("sabe", 11.6, 11.8), pal("qual", 11.8, 11.95), pal("é", 11.95, 12.1))
    assert G.aparar_nos_letterings([eco_colado], letts, [(12.34, 14.54)]) == []


def test_eco_de_lettering_no_lugar_continua_saindo():
    letts = [{"lead": "sabe qual é", "key": "O MELHOR", "start": 12.34, "dur": 2.2}]
    eco_longe = grupo(pal("sabe", 10.0, 10.3), pal("qual", 10.3, 10.5), pal("é", 10.5, 10.7))
    assert G.aparar_nos_letterings([eco_longe], letts, [(12.34, 14.54)]) == []


def test_lettering_adiado_fica_marcado():
    ls = [{"id": "lettA", "lead": "x", "key": "Y", "start": 10.5, "dur": 2.2, "split": False}]
    L.travar_no_layout(ls, [(10.0, 11.0)])      # nasce dentro do split e não cabe antes do fim: adia
    assert ls[0].get("adiado") is True and ls[0]["start"] == 11.1
