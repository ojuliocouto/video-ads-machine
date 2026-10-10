"""W7.Z: a legenda que atravessa a troca de layout e não tem PISO_FATIA em nenhum dos lados sai da tela.

Com o split por padrão o primeiro insert (o do gancho) passou a ser um split de verdade, e a legenda #0 (3,15 a 3,68 s, a
borda em 3,40 s) ficou com 0,25 s de um lado e 0,28 s do outro. O corte em dois e a aparagem para o lado dominante exigem
0,30 s; abaixo disso o código "deixava como está", e o grupo atravessava a troca com a posição de tela cheia sobre o rosto do
painel de baixo (o gate_geometria reprovou: 210 px no núcleo do rosto). Uma fatia que cabe (0,30 s menos a guarda) e uma
que não cabe nunca davam um grupo legível; sem lado que chegue ao piso, o grupo sai: um flash de 0,16 s não se lê."""
from overlay import layout_texto as L


def grupo(a, b, palavras):
    n = len(palavras)
    passo = (b - a) / n
    return {"start": a, "end": b, "words": [{"text": t, "start": round(a + k * passo, 3), "end": round(a + (k + 1) * passo, 3)}
                                            for k, t in enumerate(palavras)]}


def test_grupo_sem_lado_que_chegue_ao_piso_sai_da_tela():
    g = grupo(3.15, 3.68, ["transformou", "meu", "Claude"])          # 0,25 s antes da borda e 0,28 s depois
    saida = L.cortar_na_fronteira([g], [(0.4, 3.4)])
    assert saida == []


def test_nenhum_grupo_que_sobra_atravessa_a_borda():
    grupos = [grupo(3.15, 3.68, ["a", "b", "c"]), grupo(1.0, 2.0, ["d", "e"]), grupo(3.3, 4.2, ["f", "g", "h"])]
    for g in L.cortar_na_fronteira(grupos, [(0.4, 3.4)]):
        assert not (g["start"] < 3.4 < g["end"]), g


def test_grupo_que_chega_ao_piso_de_um_lado_continua_aparado_para_esse_lado():
    g = grupo(3.0, 3.9, ["a", "b", "c"])       # 0,40 s antes e 0,50 s depois, mas as palavras não dão fatia dos dois lados
    saida = L.cortar_na_fronteira([g], [(0.4, 3.4)])
    assert saida and all(not (x["start"] < 3.4 < x["end"]) for x in saida)


def test_grupo_dentro_de_um_layout_so_fica_como_esta():
    g = grupo(1.0, 2.0, ["a", "b"])
    assert L.cortar_na_fronteira([g], [(0.4, 3.4)])[0]["start"] == 1.0
