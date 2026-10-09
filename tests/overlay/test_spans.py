"""overlay.spans: a linha do tempo por bloco (spans contíguos) e o plano de ritmo do overlay.

Valores esperados lidos do `gen_ad_v2.py` original: a fronteira de um bloco é a primeira
palavra do próximo, nenhum bloco tem menos de 0,3 s, e o plano de ritmo que o overlay usa é
o MESMO que a footage usa (chamada ao `ritmo.plano_de_ritmo` com a mesma entrada).
"""
import pytest

from overlay import spans as S


def palavras(*tempos):
    """[(texto, inicio, fim)] -> palavras alinhadas."""
    return [{"text": t, "start": a, "end": b} for t, a, b in tempos]


def blocos(*narracoes, tipos=None):
    tipos = tipos or ["orig"] * len(narracoes)
    return [{"type": t, "instr": f"b{i}", "narr": n} for i, (t, n) in enumerate(zip(tipos, narracoes))]


# --- calcular_spans -------------------------------------------------------------------------

def test_spans_sao_contiguos_e_a_fronteira_e_a_primeira_palavra_do_proximo():
    words = palavras(("a", 0.5, 0.9), ("b", 1.0, 1.4), ("c", 2.0, 2.4), ("d", 3.0, 3.3), ("e", 3.5, 4.0))
    sp = S.calcular_spans(blocos("a b", "c", "d e"), words)
    assert sp == [(0.5, 2.0), (2.0, 3.0), (3.0, 4.0)]


def test_bloco_nunca_tem_menos_de_0_3s():
    words = palavras(("a", 1.0, 1.05), ("b", 1.1, 1.15), ("c", 1.2, 1.25))
    sp = S.calcular_spans(blocos("a", "b", "c"), words)
    plano = [x for par in sp for x in par]
    assert plano == pytest.approx([1.0, 1.3, 1.3, 1.6, 1.6, 1.9])
    # o ultimo bloco termina em max(fim da ultima palavra, inicio + 0,3)
    assert sp[-1][1] == pytest.approx(1.9)


def test_ultimo_bloco_vai_ate_o_fim_da_ultima_palavra_quando_ela_acaba_depois():
    words = palavras(("a", 0.0, 0.2), ("b", 5.0, 9.0))
    assert S.calcular_spans(blocos("a", "b"), words) == [(0.0, 5.0), (5.0, 9.0)]


def test_bloco_sem_fala_nasce_no_fim_da_palavra_anterior():
    words = palavras(("a", 0.5, 0.9), ("b", 1.0, 1.4), ("c", 2.0, 2.4))
    sp = S.calcular_spans(blocos("a b", "", "c"), words)
    # starts = [0.5, 1.4 (fim de "b"), 2.0] -> bounds 0.5, 1.4, 2.0, 2.4
    assert sp == [(0.5, 1.4), (1.4, 2.0), (2.0, 2.4)]


def test_primeiro_bloco_sem_fala_nasce_em_zero():
    words = palavras(("a", 1.0, 1.4))
    sp = S.calcular_spans(blocos("", "a"), words)
    assert sp[0][0] == 0.0
    assert sp[1][0] == 1.0


# --- achar_insert_cfg -----------------------------------------------------------------------

def test_achar_insert_cfg_casa_a_primeira_chave_contida_na_instrucao():
    mapa = {"demo a": {"file": "a.mp4"}, "demo b": {"file": "b.mp4"}}
    assert S.achar_insert_cfg("Inserção de vídeo: DEMO B", mapa) == ("demo b", {"file": "b.mp4"})
    assert S.achar_insert_cfg("insercao demo a e demo b", mapa)[0] == "demo a"


def test_achar_insert_cfg_sem_chave_devolve_none():
    assert S.achar_insert_cfg("apresentador", {"demo a": {}}) == (None, None)


def test_achar_insert_cfg_chave_com_maiuscula_nunca_casa():
    # a instrucao e posta em minusculas e a chave nao: quem escreve a chave em minuscula acerta
    assert S.achar_insert_cfg("demo a", {"Demo A": {"file": "x"}}) == (None, None)


# --- plano_de_ritmo -------------------------------------------------------------------------

def test_entrada_do_ritmo_leva_tipo_recorte_cap_e_fala(monkeypatch):
    recebido = {}

    def falso(entrada):
        recebido["entrada"] = entrada
        return [{"bloco": 0, "tipo": "insert", "s": 0.0, "e": 4.0},
                {"bloco": 1, "tipo": "orig", "s": 4.0, "e": 9.0}]

    monkeypatch.setattr(S.ritmo, "plano_de_ritmo", falso)
    bl = [{"type": "insert", "instr": "demo a", "narr": "olha isso aqui na tela"},
          {"type": "lettering", "instr": "apresentador + lettering", "narr": "e depois"}]
    mapa = {"demo a": {"file": "a.mp4", "crop": [1, 2, 3, 4], "dur_max": 3.0}}
    plano, res = S.plano_de_ritmo(bl, [(0.0, 4.0), (4.0, 9.0)], mapa)
    assert recebido["entrada"] == [
        {"tipo": "insert", "s": 0.0, "e": 4.0, "crop": [1, 2, 3, 4], "dur_max": 3.0,
         "texto": "olha isso aqui na tela"},
        {"tipo": "orig", "s": 4.0, "e": 9.0, "crop": None, "dur_max": None, "texto": "e depois"}]
    assert plano[0]["bloco"] == 0
    assert res["cortes_min"] == 6.67      # 1 corte em 9 s: round(1 / (9 / 60), 2)


def test_bloco_que_nao_e_insert_vira_orig_mesmo_com_tipo_de_lettering(monkeypatch):
    visto = {}
    monkeypatch.setattr(S.ritmo, "plano_de_ritmo", lambda e: visto.setdefault("e", e) and [])
    monkeypatch.setattr(S.ritmo, "resumo", lambda p, d: {"cortes_min": 0.0, "plano_medio": 0.0})
    for tipo in ("orig", "lettering", "lettering_logo", "logo"):
        S.plano_de_ritmo([{"type": tipo, "instr": "x", "narr": ""}], [(0.0, 1.0)], {})
        assert visto["e"][0]["tipo"] == "orig"
        visto.clear()


def test_plano_de_ritmo_imprime_o_resumo(monkeypatch, capsys):
    monkeypatch.setattr(S.ritmo, "plano_de_ritmo", lambda e: [{"tipo": "orig", "s": 0.0, "e": 6.0}])
    monkeypatch.setattr(S.ritmo, "resumo", lambda p, d: {"cortes_min": 17.04, "plano_medio": 2.951})
    S.plano_de_ritmo([{"type": "orig", "instr": "x", "narr": ""}], [(0.0, 6.0)], {})
    assert capsys.readouterr().out == "   [ritmo] 1 planos | 17.0 cortes/min | plano medio 2.95s\n"


def test_o_plano_do_overlay_e_o_mesmo_que_a_footage_calcula():
    # DETERMINISTICO DE PROPOSITO (ritmo.py): os dois motores chamam a mesma funcao
    import ritmo
    bl = [{"type": "insert", "instr": "demo a", "narr": "uma fala qualquer"},
          {"type": "orig", "instr": "apresentador", "narr": "outra fala bem mais longa que a primeira"}]
    spans = [(0.0, 4.0), (4.0, 20.0)]
    mapa = {"demo a": {"file": "a.mp4", "dur_max": 2.0}}
    plano, _ = S.plano_de_ritmo(bl, spans, mapa)
    direto = ritmo.plano_de_ritmo([
        {"tipo": "insert", "s": 0.0, "e": 4.0, "crop": None, "dur_max": 2.0, "texto": "uma fala qualquer"},
        {"tipo": "orig", "s": 4.0, "e": 20.0, "crop": None, "dur_max": None,
         "texto": "outra fala bem mais longa que a primeira"}])
    assert plano == direto


def _plano_com_fala(fala, dur_max=3.0):
    bl = [{"type": "orig", "instr": "apresentador", "narr": "abertura"},
          {"type": "insert", "instr": "demo a", "narr": fala}]
    plano, _ = S.plano_de_ritmo(bl, [(0.0, 3.0), (3.0, 15.0)], {"demo a": {"file": "a.mp4", "dur_max": dur_max}})
    return [x for x in plano if x["bloco"] == 1]


def test_fala_deitica_trava_o_insert_o_bloco_inteiro_fica_em_tela():
    # FALA QUE APONTA PRA TELA TRAVA O INSERT (28/08/2026): "na tela" nao pode cair no rosto
    mine = _plano_com_fala("olha isso aqui na tela")
    assert len(mine) == 1
    assert (mine[0]["s"], mine[0]["e"], mine[0]["tipo"], mine[0].get("deitico")) == (3.0, 15.0, "insert", True)


def test_fala_comum_com_cap_alterna_insert_e_rosto():
    mine = _plano_com_fala("uma fala qualquer")
    assert len(mine) > 1
    assert {x["tipo"] for x in mine} == {"insert", "orig"}
    assert not any(x.get("deitico") for x in mine)


def test_bloco_que_comeca_apontando_pra_imagem_tambem_trava():
    # "Ela e um manual..." com o insert (que E o manual) sumindo no meio da explicacao
    mine = _plano_com_fala("Ela é um manual de instrucoes")
    assert len(mine) == 1 and mine[0]["deitico"] is True
