"""W7.Z, item 3: a régua do gate_mix com a voz ISOLADA (piso de pausa muito abaixo de -35 dBFS) e com os fades.

  - a subida é medida contra o MAIOR entre a voz sozinha na pausa e o piso audível (-40 dBFS): contra uma voz a -55 dBFS
    toda música parece +15 dB, e o gate reprovava mix correto (o aviso já estava no docstring do gate);
  - pausa dentro do fade de entrada ou do fade de saída da trilha não entra na régua: a cama está sumindo ali de propósito;
  - o que NÃO muda: cama que não respira acima do piso audível (+1,5 dB) continua reprovando, e cama que bombeia (+8 dB)
    também."""
import numpy as np
import pytest

from cinema import musica
from gates import gate_mix
from tests.gates.test_gate_mix import BOA, DUR, PAUSAS, SR, TRILHA, ruido


def voz_com_piso(piso_db, dur=DUR, pausas=PAUSAS, seed=1):
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    fala = np.sqrt(2) * 10 ** (-18 / 20) * np.sin(2 * np.pi * 220 * t)
    for a, b in pausas:
        fala[int(a * SR):int(b * SR)] = 0.0
    return fala + ruido(n, piso_db, rng)


def mix_com_musica_nas_pausas(voz, musica_db, pausas=PAUSAS, seed=2, sob_a_fala_db=-45.0):
    """voz + música: `musica_db` dentro das pausas, `sob_a_fala_db` fora (as rampas não importam para a janela do meio)."""
    rng = np.random.default_rng(seed)
    n = len(voz)
    ganho = np.full(n, 10 ** (sob_a_fala_db / 20))
    for a, b in pausas:
        ganho[int(a * SR):int(b * SR)] = 10 ** (musica_db / 20)
    return voz + ruido(n, 0.0, rng) * ganho


def avaliar(final, voz, **kw):
    kw.setdefault("loudness_medido", BOA)
    kw.setdefault("trilha", TRILHA)
    kw.setdefault("transcritor", lambda p: [])
    return gate_mix.avaliar(gate_mix.Faixa(final, SR), gate_mix.Faixa(voz, SR), **kw)


def regras(r):
    return {f["regra"] for f in r.detalhes["falhas"]}


def test_o_piso_audivel_e_o_da_automacao():
    assert gate_mix.PISO_AUDIVEL_DB == musica.PISO_AUDIVEL_DB == -40.0
    assert gate_mix.PAUSA_DELTA_DB == musica.PAUSA_SOBE_DB == (1.5, 8.0)


def test_voz_isolada_a_menos_55_com_musica_a_menos_35_passa_contra_o_piso_audivel():
    voz = voz_com_piso(-55.0)
    r = avaliar(mix_com_musica_nas_pausas(voz, -35.3), voz)
    assert r.ok, r.motivo
    deltas = [p["delta_db"] for p in r.detalhes["medido"]["pausas"]]
    assert all(1.5 <= d <= 8.0 for d in deltas), deltas
    assert r.detalhes["medido"]["piso_audivel_db"] == -40.0


def test_a_mesma_cama_contra_a_voz_sozinha_parecia_mais_de_15_dB():
    """O mutante da causa: sem o piso, a pausa a -55 dBFS leria +19,7 dB e o mix correto reprovava."""
    voz = voz_com_piso(-55.0)
    final = mix_com_musica_nas_pausas(voz, -35.3)
    contra_a_voz = gate_mix.Faixa(final, SR).nivel_db(2.15) - gate_mix.Faixa(voz, SR).nivel_db(2.15)
    assert contra_a_voz > 15.0


def test_cama_que_nao_respira_acima_do_piso_audivel_continua_reprovando():
    voz = voz_com_piso(-55.0)
    r = avaliar(mix_com_musica_nas_pausas(voz, -48.0), voz)          # sobe 0 dB sobre a voz, e fica a 8 dB abaixo do piso audível
    assert not r.ok and "cama_nas_pausas" in regras(r)


def test_cama_que_bombeia_continua_reprovando_com_o_piso_audivel():
    voz = voz_com_piso(-55.0)
    r = avaliar(mix_com_musica_nas_pausas(voz, -25.0), voz)          # +15 dB sobre o piso audível
    assert not r.ok and "cama_nas_pausas" in regras(r)
    assert all(p["delta_db"] > 8.0 for p in r.detalhes["medido"]["pausas"])


def test_voz_acima_do_piso_audivel_segue_medida_contra_a_propria_voz():
    voz = voz_com_piso(-33.0)                                          # o piso das fixtures do gate
    r = avaliar(mix_com_musica_nas_pausas(voz, -29.0), voz)            # +2,5 dB sobre -33
    assert r.ok, r.motivo


# --- fades -------------------------------------------------------------------------------------------------

PAUSAS_NO_FADE = [(0.3, 0.9), (2.0, 2.8), (6.0, 7.2), (9.5, 10.2), (14.5, 15.3)]    # a 1ª e a última dentro dos fades


def test_pausa_no_fade_de_saida_ou_de_entrada_nao_entra_na_regua():
    voz = voz_com_piso(-45.0, pausas=PAUSAS_NO_FADE)
    final = mix_com_musica_nas_pausas(voz, -36.0, pausas=PAUSAS_NO_FADE[1:4])
    # as pausas de dentro respiram; a música não respira nas duas dos fades (ela está sumindo)
    r = avaliar(final, voz)
    assert r.ok, r.motivo
    m = r.detalhes["medido"]
    assert len(m["pausas"]) == 3
    assert {(p["s"], p["e"]) for p in m["pausas_nos_fades"]} == {(0.3, 0.9), (14.5, 15.3)}


def test_o_fade_vem_do_ducking_do_timeline_quando_ele_existe():
    voz = voz_com_piso(-45.0, pausas=PAUSAS_NO_FADE)
    final = mix_com_musica_nas_pausas(voz, -36.0, pausas=PAUSAS_NO_FADE[1:4])
    ducking = musica.ducking_para_timeline(PAUSAS_NO_FADE, fade_in_s=0.5, fade_out_s=0.5)
    r = avaliar(final, voz, ducking=ducking, pausas=PAUSAS_NO_FADE)
    # com fades de 0,5 s só a pausa de 0,3 a 0,9 s toca o fade de entrada; a de 14,5 s não toca o de saída (começa em 15,5 s)
    assert [(p["s"], p["e"]) for p in r.detalhes["medido"]["pausas_nos_fades"]] == [(0.3, 0.9)]
    m = r.detalhes["medido"]                                    # a de 14,5 s agora conta, e a cama não respira ali
    assert len(m["pausas"]) == 4 and m["pausas_ok"] == 3
    assert [p["ok"] for p in m["pausas"] if p["s"] == 14.5] == [False]


def test_peca_so_com_pausa_nos_fades_nao_cobra_respiro():
    pausas = [(0.3, 0.9), (14.5, 15.3)]
    voz = voz_com_piso(-45.0, pausas=pausas)
    final = mix_com_musica_nas_pausas(voz, -60.0, pausas=pausas)
    r = avaliar(final, voz)
    assert r.ok, r.motivo
    assert r.detalhes["medido"]["sem_pausas"] is True and r.detalhes["medido"]["pausas"] == []


def test_o_limiar_do_laudo_traz_o_piso_audivel(voz=None):
    voz = voz_com_piso(-33.0)
    r = avaliar(mix_com_musica_nas_pausas(voz, -29.0), voz)
    assert r.detalhes["limiar"]["piso_audivel_db"] == -40.0
