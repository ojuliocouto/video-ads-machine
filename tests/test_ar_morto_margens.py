"""Margens de palavra do corte (a Groq marca o início da palavra tarde): antes 0,30 s, depois 0,15 s.

Medido em 20/10/2026: na Groq, 17% dos inícios de palavra chegam mais de 200 ms tarde (p90 do erro 388 ms); no
modelo local, 6%. Cortar pelo tempo cru comeria a sílaba inicial. O corte alarga cada palavra para trás e para a frente
antes de procurar pausa, sem nunca invadir a palavra vizinha.
"""
import ar_morto as AM
import pytest


def _palavras(*tempos):
    return [(a, b, t) for (a, b), t in zip(tempos, "abcdefgh")]


def test_constantes_documentadas():
    assert AM.PRE_ROLL_PALAVRA == 0.30
    assert AM.PRE_ROLL_POR_BACKEND == {"groq": 0.30, "mistral": 0.40}
    assert AM.POS_ROLL_PALAVRA == 0.15
    assert AM.VARIAVEL_PRE_ROLL == "VAM_CORTE_PRE_ROLL" and AM.VARIAVEL_POS_ROLL == "VAM_CORTE_POS_ROLL"


def test_palavra_isolada_ganha_pre_e_pos_roll_cheios():
    saida = AM.margens_de_palavra([(2.0, 2.5, "oi")])
    assert saida == [(pytest.approx(1.70), pytest.approx(2.65), "oi")]


def test_primeira_palavra_nao_vai_abaixo_de_zero():
    (ini, _fim, _t), = AM.margens_de_palavra([(0.10, 0.4, "oi")])
    assert ini == 0.0


def test_palavras_longe_ganham_a_margem_inteira_dos_dois_lados():
    saida = AM.margens_de_palavra(_palavras((1.0, 1.5), (4.0, 4.5)))
    assert saida[0][:2] == (pytest.approx(0.70), pytest.approx(1.65))
    assert saida[1][:2] == (pytest.approx(3.70), pytest.approx(4.65))


def test_vao_menor_que_a_soma_nunca_sobrepoe_a_palavra_anterior():
    """Vão de 0,30 s: o pós-roll da primeira (0,15) fica inteiro e o pré-roll da segunda pega o resto (0,15)."""
    a, b = AM.margens_de_palavra(_palavras((1.0, 1.5), (1.8, 2.3)))
    assert a[1] == pytest.approx(1.65) and b[0] == pytest.approx(1.65)
    assert a[1] <= b[0]


def test_vao_menor_que_o_pos_roll_divide_so_ate_o_inicio_da_proxima():
    a, b = AM.margens_de_palavra(_palavras((1.0, 1.5), (1.58, 2.0)))
    assert a[1] == pytest.approx(1.58) and b[0] == pytest.approx(1.58)


def test_palavras_coladas_ou_sobrepostas_ficam_como_estao():
    a, b = AM.margens_de_palavra(_palavras((1.0, 1.5), (1.4, 2.0)))
    assert a[1] <= b[0] or a[1] == pytest.approx(1.5)
    assert b[0] >= 1.4 - 1e-9 or b[0] == pytest.approx(a[1])


def test_nunca_encolhe_a_palavra_e_a_ordem_se_mantem():
    entrada = _palavras((0.5, 0.9), (1.0, 1.4), (1.45, 2.0), (3.0, 3.2))
    saida = AM.margens_de_palavra(entrada)
    for (a, b, _), (x, y, _) in zip(entrada, saida):
        assert x <= a + 1e-9 and y >= b - 1e-9
    for (_, y1, _), (x2, _, _) in zip(saida, saida[1:]):
        assert y1 <= x2 + 1e-9


def test_pontuacao_passa_igual_e_nao_ganha_margem():
    saida = AM.margens_de_palavra([(1.0, 1.4, "oi"), (1.4, 1.4, ","), (3.0, 3.4, "tchau")])
    assert saida[1] == (1.4, 1.4, ",")


def test_margem_zero_devolve_o_mesmo_tempo():
    entrada = _palavras((1.0, 1.5), (3.0, 3.4))
    assert AM.margens_de_palavra(entrada, pre=0.0, pos=0.0) == entrada


def test_o_pre_roll_depende_do_backend_que_fez_o_tempo_e_o_pos_roll_e_igual():
    assert AM.margens_do_ambiente({}, "groq") == (0.30, 0.15)
    assert AM.margens_do_ambiente({}, "mistral") == (0.40, 0.15)
    assert AM.margens_do_ambiente({}, "faster_whisper") == (0.30, 0.15)
    assert AM.margens_do_ambiente({}, None) == (0.30, 0.15)
    assert AM.margens_do_ambiente({"VAM_CORTE_PRE_ROLL": "0.5"}, "mistral") == (0.5, 0.15), "a variável manda"


def test_override_pelas_variaveis_de_ambiente():
    assert AM.margens_do_ambiente({}) == (0.30, 0.15)
    assert AM.margens_do_ambiente({"VAM_CORTE_PRE_ROLL": "0,2", "VAM_CORTE_POS_ROLL": "0.1"}) == (0.2, 0.1)
    assert AM.margens_do_ambiente({"VAM_CORTE_PRE_ROLL": "  "}) == (0.30, 0.15)
    with pytest.raises(ValueError, match="VAM_CORTE_PRE_ROLL"):
        AM.margens_do_ambiente({"VAM_CORTE_PRE_ROLL": "muito"})
    with pytest.raises(ValueError, match="VAM_CORTE_POS_ROLL"):
        AM.margens_do_ambiente({"VAM_CORTE_POS_ROLL": "-1"})


def test_a_margem_recua_o_bloco_de_fala_para_antes_do_inicio_marcado_tarde():
    """O ASR diz que a 2ª palavra começa em 3,00 s, mas a fala real começa em 2,70 s (atraso de 0,30 s, dentro do que
    a Groq faz). Com a margem de 0,30 s o bloco de fala já começa em 2,70 s: o vão que o cortador vê acaba antes da
    sílaba, e nenhum corte entra na fala real."""
    JAN = 0.02
    n = int(4.0 / JAN)
    db = [-45.0] * n
    for i in range(int(0.5 / JAN), int(1.5 / JAN)):
        db[i] = -12.0
    for i in range(int(2.7 / JAN), int(3.8 / JAN)):             # a fala real começa em 2,70 s
        db[i] = -12.0
    tokens = [(0.5, 1.5, "um"), (3.0, 3.8, "dois")]              # o ASR marcou tarde
    blocos = AM.blocos_de_fala(AM.margens_de_palavra(tokens))
    assert blocos[1][0] == pytest.approx(2.70)
    for a, b in AM.planejar_cortes(blocos, db, JAN, 4.0):
        assert b <= 2.70 + 1e-6 or a >= 3.8, "só o rabo do arquivo (depois da fala) pode passar de 2,70 s"


# --- a fiação: o one-shot e o cortador aplicam a margem -------------------------------------------------

def _curva_com_vao(dur, falas, jan=0.02):
    n = int(dur / jan)
    db = [-45.0] * n
    for a, b in falas:
        for i in range(int(a / jan), int(b / jan)):
            db[i] = -12.0
    return db


def test_oneshot_aplica_a_margem_antes_de_procurar_pausa():
    from oneshot import montar as OM
    palavras = [{"text": "um", "start": 0.5, "end": 1.0}, {"text": "dois", "start": 1.8, "end": 2.3}]
    db = _curva_com_vao(3.0, [(0.5, 1.0), (1.8, 2.3)])
    sem_margem = OM.cortes_do_take(palavras, db, 3.0, margens=(0.0, 0.0))
    com_margem = OM.cortes_do_take(palavras, db, 3.0, margens=(0.30, 0.15))
    assert len(com_margem) < len(sem_margem), "vão de 0,8 s: sem margem corta a pausa, com margem (0,35 s) ritmo natural"


def test_oneshot_le_as_variaveis_do_ambiente(monkeypatch):
    from oneshot import montar as OM
    palavras = [{"text": "um", "start": 0.5, "end": 1.0}, {"text": "dois", "start": 1.8, "end": 2.3}]
    db = _curva_com_vao(3.0, [(0.5, 1.0), (1.8, 2.3)])
    monkeypatch.setenv("VAM_CORTE_PRE_ROLL", "0")
    monkeypatch.setenv("VAM_CORTE_POS_ROLL", "0")
    zerado = OM.cortes_do_take(palavras, db, 3.0)
    monkeypatch.delenv("VAM_CORTE_PRE_ROLL")
    monkeypatch.delenv("VAM_CORTE_POS_ROLL")
    padrao = OM.cortes_do_take(palavras, db, 3.0)
    assert len(zerado) > len(padrao)


def test_oneshot_usa_o_pre_roll_do_backend_que_fez_o_tempo(monkeypatch):
    from oneshot import montar as OM
    vistos = []
    original = AM.margens_de_palavra

    def espia(tokens, pre=None, pos=None):
        vistos.append((pre, pos))
        return original(tokens, pre, pos)

    monkeypatch.setattr(AM, "margens_de_palavra", espia)
    for var in ("VAM_CORTE_PRE_ROLL", "VAM_CORTE_POS_ROLL"):
        monkeypatch.delenv(var, raising=False)
    palavras = [{"text": "um", "start": 0.5, "end": 1.0}, {"text": "dois", "start": 2.0, "end": 2.5}]
    db = _curva_com_vao(3.0, [(0.5, 1.0), (2.0, 2.5)])
    for backend in ("mistral", "groq", None):
        OM.cortes_do_take(palavras, db, 3.0, backend=backend)
    assert vistos == [(0.40, 0.15), (0.30, 0.15), (0.30, 0.15)]
