"""overlay.chips: o chip flutuante com a palavra-chave nos vãos longos de avatar.

DESLIGADO NA ORIGEM em 29/08/2026 (segunda ordem sobre o mesmo assunto: a pílula fingia status e
o texto só repetia em caixa alta uma palavra que o apresentador acabara de falar). A lógica de
achar os vãos continua, para quando entrar outra coisa nesses vãos que não seja enfeite, e
por isso os ramos dela têm teste mesmo com `CHIP_LIGADO = False`:

  - vãos MAIORES primeiro (um vão menor 7,7 s antes tirava o chip do maior);
  - espaçamento mínimo de 6 s, no máximo 4 chips, vão de 7 s ou mais;
  - nunca antes de 5,5 s (dentro do hook) e nunca em cima de um lettering;
  - a palavra é a kw da fala; senão a mais longa que não seja muleta nem advérbio em -mente.
"""
from overlay import chips as C


def plano(*itens):
    return [{"tipo": t, "s": a, "e": b} for t, a, b in itens]


def palavras(*pares):
    return [{"text": t, "start": a, "end": a + 0.4, **({"kw": True} if kw else {})}
            for t, a, kw in pares]


def grupos_de(words):
    return [{"start": w["start"], "end": w["end"], "words": [w]} for w in words]


def fala_corrida(fim, texto="palavra", passo=0.5):
    n = int(fim / passo)
    return grupos_de(palavras(*[(texto, i * passo, False) for i in range(n)]))


def test_chip_nasce_desligado():
    assert C.CHIP_LIGADO is False
    assert C.calcular(plano(("orig", 0.0, 30.0)), fala_corrida(30), [], 100.0) == []


# --- vãos de avatar -------------------------------------------------------------------------------

def test_vao_de_avatar_e_a_sequencia_de_planos_sem_insert():
    pl = plano(("orig", 0.0, 3.0), ("insert", 3.0, 6.0), ("orig", 6.0, 10.0), ("orig", 10.0, 12.0))
    assert C.runs_de_avatar(pl) == [(0.0, 3.0), (6.0, 12.0)]


def test_vao_que_termina_em_insert_fecha_ali():
    assert C.runs_de_avatar(plano(("orig", 0.0, 3.0), ("insert", 3.0, 6.0))) == [(0.0, 3.0)]
    assert C.runs_de_avatar(plano(("insert", 0.0, 3.0), ("orig", 3.0, 6.0))) == [(3.0, 6.0)]
    assert C.runs_de_avatar(plano(("insert", 0.0, 3.0))) == []


# --- calcular (com o chip ligado) -----------------------------------------------------------------

def test_chip_nunca_nasce_dentro_do_hook_e_leva_a_kw_da_fala(capsys):
    words = palavras(("de", 5.0, False), ("gratuitamente", 6.0, True), ("dentro", 7.0, False))
    chips = C.calcular(plano(("orig", 0.0, 20.0)), grupos_de(words), [], 100.0, ligado=True)
    assert chips == [{"t": 5.5, "kw": "GRATUITAMENTE"}]
    assert "   [chips] 1: GRATUITAMENTE@5.5s" in capsys.readouterr().out


def test_sem_kw_vale_a_palavra_mais_longa_que_nao_e_muleta_nem_mente():
    words = palavras(("porque", 5.5, False), ("praticamente", 6.0, False), ("projetos,", 6.5, False),
                     ("pagina.", 7.0, False), ("ola", 7.5, False))
    chips = C.calcular(plano(("orig", 0.0, 20.0)), grupos_de(words), [], 100.0, ligado=True)
    assert chips == [{"t": 5.5, "kw": "PROJETOS"}]


def test_muletas_com_acento_tambem_ficam_de_fora():
    words = palavras(("também", 6.0, False), ("então", 6.5, False), ("Quando", 7.0, False))
    assert C.calcular(plano(("orig", 0.0, 20.0)), grupos_de(words), [], 100.0, ligado=True) == []


def test_chip_so_olha_as_palavras_de_0_5s_antes_a_3_5s_depois():
    words = palavras(("longe", 1.0, True), ("aqui", 5.0, False), ("alem", 9.1, True))
    chips = C.calcular(plano(("orig", 0.0, 20.0)), grupos_de(words), [], 100.0, ligado=True)
    assert chips == []      # "longe" esta antes de 5,0 e "alem" depois de 9,0; "aqui" tem 4 letras


def test_vao_curto_de_menos_de_7s_nao_ganha_chip():
    # vao curto ja e dinamico por natureza
    assert C.calcular(plano(("orig", 0.0, 6.9)), fala_corrida(7), [], 100.0, ligado=True) == []
    # com 12 s o mesmo chip cabe: 5,5 <= 12,0 - 2,8
    assert C.calcular(plano(("orig", 0.0, 12.0)), fala_corrida(12), [], 100.0, ligado=True) == \
        [{"t": 5.5, "kw": "PALAVRA"}]


def test_chip_espera_o_lettering_passar():
    ls = [(5.0, 7.0)]
    chips = C.calcular(plano(("orig", 0.0, 30.0)), fala_corrida(30), ls, 100.0, ligado=True)
    assert chips[0]["t"] == 7.5            # _le + 0,5


def test_chip_que_nao_cabe_antes_do_fim_do_vao_ou_do_logo_e_descartado():
    assert C.calcular(plano(("orig", 0.0, 10.0)), fala_corrida(10), [(5.0, 7.0)], 100.0, ligado=True) == []
    # o logo sobe aos 8,0: 5,5 > 8,0 - 3,2 = 4,8
    assert C.calcular(plano(("orig", 0.0, 30.0)), fala_corrida(30), [], 8.0, ligado=True) == []


def test_vao_maior_primeiro_e_espacamento_de_6s():
    # A (0 a 9) daria chip em 5,5; B (10 a 20) em 11,2. Diferenca de 5,7 s: so um cabe, o do vao MAIOR
    pl = plano(("orig", 0.0, 9.0), ("insert", 9.0, 10.0), ("orig", 10.0, 20.0))
    chips = C.calcular(pl, fala_corrida(20), [], 100.0, ligado=True)
    assert chips == [{"t": 11.2, "kw": "PALAVRA"}]


def test_no_maximo_quatro_chips():
    itens, t = [], 0.0
    for _ in range(6):
        itens += [("orig", t, t + 20.0), ("insert", t + 20.0, t + 22.0)]
        t += 22.0
    chips = C.calcular(plano(*itens), fala_corrida(140), [], 500.0, ligado=True)
    assert len(chips) == 4
    assert [c["t"] for c in chips] == [5.5, 23.2, 45.2, 67.2]


def test_ligado_padrao_le_a_constante_do_modulo(monkeypatch):
    monkeypatch.setattr(C, "CHIP_LIGADO", True)
    assert C.calcular(plano(("orig", 0.0, 30.0)), fala_corrida(30), [], 100.0) != []


# --- html -------------------------------------------------------------------------------------------------

def test_html_dos_chips_usa_as_trilhas_58_e_seguintes():
    chips = [{"t": 5.5, "kw": "PRO"}, {"t": 20.0, "kw": "SIM"}]
    assert C.html(chips) == (
        '<div class="chip clip" id="chip0" data-start="5.5" data-duration="2.6" data-track-index="58">'
        '<span class="dot"></span>PRO</div>\n'
        '<div class="chip clip" id="chip1" data-start="20.0" data-duration="2.6" data-track-index="59">'
        '<span class="dot"></span>SIM</div>')


def test_html_sem_chips_e_vazio():
    assert C.html([]) == ""
