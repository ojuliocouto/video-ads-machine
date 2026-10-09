"""W4.B, C11: som com FUNÇÃO. Riser 1,0 s antes do CTA, tick por linha de pilha, boom na KEY
gigante-atrás. O whoosh está DESLIGADO (reprovado duas vezes pelo diretor; ordem de 31/08).

O plano de SFX é uma função pura do timeline.json: entra relógio, segmentos, letterings e CTA e
saem eventos {t, efeito, funcao, nivel_dbfs} no mesmo formato do contrato. Os tempos do contrato
são do relógio da FOOTAGE a 1x; a regra de "1,0 s antes" e o teto de "1 evento a cada 4 s" valem no
arquivo ENTREGUE (o que o espectador ouve), então o plano converte nos dois sentidos.

Duas leituras que o plano pede e que estes testes prendem:
  - "tick por linha de pilha" e "no máximo 1 evento a cada 4 s" não se anulam: a pilha inteira conta
    como UM evento para o teto, e dentro dela os ticks seguem as linhas (mínimo de 0,5 s entre dois);
  - a pilha é atômica na disputa por espaço: ou entra inteira ou sai inteira. Meia pilha tocando é
    um ritmo que o diretor não escolheu.
"""
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

import som_cortes
from cinema import sfx_plano
from contratos.validar import validar

RAIZ = Path(__file__).resolve().parents[2]


def exemplo():
    return json.loads((RAIZ / "contratos" / "exemplos" / "timeline.valido.json").read_text(encoding="utf-8"))


def seg(tipo, s, e):
    return {"bloco": 0, "tipo": tipo, "s": s, "e": e, "sub": 0, "de": 1}


def lett(id, s, estilo="caixa_nativa", pilha=None, cta=False):
    return {"id": id, "bloco": 0, "key": "X", "s": s, "d": 1.0, "estilo": estilo, "split": False,
            "baixo": False, "pilha": pilha, "cta": cta}


def tl(letterings=(), segs=None, cta=40.0, accel=1.35, a0=0.0):
    """Timeline mínima: só o que o plano de SFX lê."""
    return {"relogio": {"base": "footage_1x", "fps": 30, "aceleracao": accel, "cauda_s": 0.45, "a0": a0},
            "segmentos": segs if segs is not None else [seg("insert", 0.0, 3.0), seg("apresentador", 3.0, 80.0)],
            "letterings": list(letterings),
            "cta": {"inicio": cta, "logo": cta + 0.2, "label": "saiba mais", "sem_lead": False}}


def ent(t, accel=1.35, a0=0.0):
    """Instante da footage no arquivo entregue."""
    return (t - a0) / accel


def resumo(plano):
    return [(e["t"], e["efeito"], e["funcao"]) for e in plano]


# --- o plano sobre o exemplo do contrato ----------------------------------------------------------

def test_plano_do_exemplo_do_contrato_tem_os_tres_ticks_da_pilha_e_o_riser():
    t = exemplo()
    t.pop("sfx")
    plano = sfx_plano.plano_de_sfx(t)
    assert resumo(plano) == [(14.6, "tick", "pilha"), (15.9, "tick", "pilha"), (17.1, "tick", "pilha"),
                             (22.65, "riser", "cta")]


def test_o_plano_entra_no_timeline_e_o_contrato_valida():
    t = exemplo()
    t["sfx"] = sfx_plano.plano_de_sfx(t)
    assert validar("timeline", t) == []


def test_todo_evento_tem_nivel_dentro_da_faixa_e_funcao_coerente():
    t = tl([lett("a", 10.0, "gigante_atras"), lett("p1", 30.0, pilha="p"), lett("p2", 31.2, pilha="p")])
    plano = sfx_plano.plano_de_sfx(t)
    assert {e["efeito"] for e in plano} == {"boom", "tick", "riser"}
    for e in plano:
        assert -38.0 <= e["nivel_dbfs"] <= -31.0, e
        assert sfx_plano.FUNCAO[e["efeito"]] == e["funcao"]
        assert set(e) == {"t", "efeito", "funcao", "nivel_dbfs"}
    assert [e["t"] for e in plano] == sorted(e["t"] for e in plano)


# --- whoosh desligado -----------------------------------------------------------------------------

def test_whoosh_nao_existe_no_plano_nem_na_biblioteca():
    assert "whoosh" not in sfx_plano.EFEITOS_LIGADOS
    assert "whoosh.wav" not in sfx_plano.ARQUIVO.values()
    assert som_cortes.WHOOSH_LIGADO is False        # a chave antiga também segue desligada


def test_cada_entrada_de_insert_fica_muda():
    # 6 entradas de insert, bem espaçadas: o motor antigo punha um whoosh em cada uma
    segs = []
    for k in range(6):
        segs.append(seg("apresentador", k * 10.0, k * 10.0 + 5.0))
        segs.append(seg("insert", k * 10.0 + 5.0, k * 10.0 + 10.0))
    plano = sfx_plano.plano_de_sfx(tl(segs=segs, cta=70.0))
    assert [e["efeito"] for e in plano] == ["riser"]


# --- riser 1,0 s antes do CTA ---------------------------------------------------------------------

@pytest.mark.parametrize("accel,a0", [(1.35, 0.0), (1.2, 0.0), (1.2, 0.5), (1.0, 0.0)])
def test_riser_fica_1_0_s_antes_do_cta_no_arquivo_entregue(accel, a0):
    cta = 30.5
    plano = sfx_plano.plano_de_sfx(tl(cta=cta, accel=accel, a0=a0))
    (riser,) = [e for e in plano if e["efeito"] == "riser"]
    assert ent(cta, accel, a0) - ent(riser["t"], accel, a0) == pytest.approx(1.0, abs=0.002)
    assert riser["funcao"] == "cta"


def test_cta_logo_no_comeco_nao_gera_riser_com_tempo_negativo():
    assert sfx_plano.plano_de_sfx(tl(cta=0.9, accel=1.0)) == []


def test_o_lettering_do_cta_nao_ganha_som_proprio_alem_do_riser():
    plano = sfx_plano.plano_de_sfx(tl([lett("cta", 40.2, "seta_cta", cta=True)], cta=40.0))
    assert [e["efeito"] for e in plano] == ["riser"]


# --- boom só na KEY gigante-atrás -----------------------------------------------------------------

def test_boom_so_na_key_gigante_atras_e_na_hora_da_entrada_dela():
    estilos = ["caixa_nativa", "serif_editorial", "punch", "marcador", "statement", "lateral", "gigante_atras"]
    letterings = [lett("l%d" % k, 10.0 + 6.0 * k, estilo) for k, estilo in enumerate(estilos)]
    plano = sfx_plano.plano_de_sfx(tl(letterings, cta=70.0))
    booms = [e for e in plano if e["efeito"] == "boom"]
    assert [(e["t"], e["funcao"]) for e in booms] == [(10.0 + 6.0 * 6, "key_gigante")]


# --- tick por linha de pilha ----------------------------------------------------------------------

def test_um_tick_por_linha_na_hora_de_cada_linha():
    pilha = [lett("a", 14.6, pilha="b4"), lett("b", 15.9, pilha="b4"), lett("c", 17.1, pilha="b4")]
    plano = sfx_plano.plano_de_sfx(tl(pilha, cta=60.0))
    assert [(e["t"], e["efeito"]) for e in plano if e["efeito"] == "tick"] == \
        [(14.6, "tick"), (15.9, "tick"), (17.1, "tick")]


def test_dois_ticks_da_mesma_pilha_ficam_a_pelo_menos_0_5_s_no_arquivo_entregue():
    # linhas em 10,0 (7,41 s entregues), 10,4 (7,70: 0,30 s depois, some) e 11,5 (8,52)
    pilha = [lett("a", 10.0, pilha="p"), lett("b", 10.4, pilha="p"), lett("c", 11.5, pilha="p")]
    ticks = [e["t"] for e in sfx_plano.plano_de_sfx(tl(pilha, cta=60.0)) if e["efeito"] == "tick"]
    assert ticks == [10.0, 11.5]
    entregues = [ent(t) for t in ticks]
    assert all(b - a >= sfx_plano.INTERVALO_TICK_S - 1e-9 for a, b in zip(entregues, entregues[1:]))


# --- teto: 1 evento a cada 4 s --------------------------------------------------------------------

def test_o_teto_de_1_evento_a_cada_4_s_vale_no_arquivo_entregue():
    # quatro KEYs gigante-atrás a 4,74, 5,93, 8,89 e 10,37 s entregues
    letterings = [lett("a", 6.4, "gigante_atras"), lett("b", 8.0, "gigante_atras"),
                  lett("c", 12.0, "gigante_atras"), lett("d", 14.0, "gigante_atras")]
    plano = sfx_plano.plano_de_sfx(tl(letterings, cta=80.0))
    booms = [e["t"] for e in plano if e["efeito"] == "boom"]
    assert booms == [6.4, 12.0]
    assert sfx_plano.INTERVALO_MIN_S == 4.0
    todos = sorted(ent(e["t"]) for e in plano)
    assert all(b - a >= 4.0 - 1e-9 for a, b in zip(todos, todos[1:]))


def test_a_pilha_conta_como_um_evento_so_para_o_teto():
    # pilha de 3 linhas coladas (0,9 s entre elas) e um boom 4,5 s depois: tudo entra
    pilha = [lett("a", 10.0, pilha="p"), lett("b", 11.2, pilha="p"), lett("c", 12.4, pilha="p")]
    boom = lett("g", 12.4 + 4.5 * 1.35, "gigante_atras")
    plano = sfx_plano.plano_de_sfx(tl(pilha + [boom], cta=80.0))
    assert [e["efeito"] for e in plano] == ["tick", "tick", "tick", "boom", "riser"]


def test_riser_vence_boom_e_tick_na_disputa_por_espaco():
    # boom 2 s entregues antes do riser (cta 40 -> riser em 28,63 entregues): o boom cede
    boom = lett("g", (40.0 / 1.35 - 1.0 - 2.0) * 1.35, "gigante_atras")
    plano = sfx_plano.plano_de_sfx(tl([boom], cta=40.0))
    assert [e["efeito"] for e in plano] == ["riser"]


def test_boom_vence_tick():
    boom = lett("g", 20.0, "gigante_atras")
    ticks = [lett("a", 22.0, pilha="p"), lett("b", 23.3, pilha="p")]
    plano = sfx_plano.plano_de_sfx(tl([boom] + ticks, cta=80.0))
    assert [e["efeito"] for e in plano] == ["boom", "riser"]


def test_pilha_e_atomica_se_uma_linha_nao_cabe_a_pilha_inteira_sai():
    # riser em 32,33 s entregues (cta 45,0). Linhas em 37,0 (27,41 s, a 4,93 do riser: cabe) e 38,4
    # (28,44 s, a 3,89: não cabe). A pilha não toca pela metade.
    pilha = [lett("a", 37.0, pilha="p"), lett("b", 38.4, pilha="p")]
    plano = sfx_plano.plano_de_sfx(tl(pilha, cta=45.0))
    assert [e["efeito"] for e in plano] == ["riser"]
    pilha_longe = [lett("a", 20.0, pilha="p"), lett("b", 21.3, pilha="p")]
    plano = sfx_plano.plano_de_sfx(tl(pilha_longe, cta=45.0))
    assert [e["efeito"] for e in plano] == ["tick", "tick", "riser"]


# --- nunca na volta pro avatar --------------------------------------------------------------------

def _tl_com_volta(s_boom):
    segs = [seg("apresentador", 0.0, 8.0), seg("insert", 8.0, 13.6), seg("apresentador", 13.6, 30.0),
            seg("insert", 30.0, 34.0), seg("insert", 34.0, 38.0), seg("apresentador", 38.0, 80.0)]
    return tl([lett("g", s_boom, "gigante_atras")], segs=segs, cta=70.0)


@pytest.mark.parametrize("s_boom,toca", [
    (13.6, False),      # exatamente na volta
    (13.8, False),      # 0,15 s entregues depois: ainda é a volta
    (13.4, False),      # 0,15 s entregues antes: o fim do insert, colado na volta
    (14.2, True),       # 0,44 s entregues depois: já é fala do avatar
    (9.0, True),        # ENTRADA de insert não é volta
    (34.0, True),       # insert que passa para outro insert não é volta
])
def test_evento_na_volta_pro_avatar_sai(s_boom, toca):
    plano = sfx_plano.plano_de_sfx(_tl_com_volta(s_boom))
    booms = [e["t"] for e in plano if e["efeito"] == "boom"]
    assert (s_boom in booms) is toca


def test_a_tolerancia_da_volta_e_de_0_25_s_no_arquivo_entregue():
    assert sfx_plano.TOLERANCIA_VOLTA_S == 0.25
    # 0,30 s entregues (0,405 s de footage) depois da volta: fora da tolerância, o boom toca
    plano = sfx_plano.plano_de_sfx(_tl_com_volta(13.6 + 0.405))
    assert [e["t"] for e in plano if e["efeito"] == "boom"] == [14.005]


def test_o_riser_nao_sai_na_volta_porque_quem_manda_nele_e_o_cta():
    # o insert termina em 22,5 e o riser cai 1,0 s entregue antes do CTA (24,0): 0,15 s depois da
    # volta. É o desenho do exemplo do contrato, e o riser fica.
    segs = [seg("apresentador", 0.0, 5.0), seg("insert", 5.0, 22.5), seg("apresentador", 22.5, 40.0)]
    plano = sfx_plano.plano_de_sfx(tl(segs=segs, cta=24.0))
    assert [(e["t"], e["efeito"]) for e in plano] == [(22.65, "riser")]


def test_so_o_evento_da_volta_sai_e_o_resto_da_pilha_fica():
    segs = [seg("insert", 0.0, 13.6), seg("apresentador", 13.6, 80.0)]
    pilha = [lett("a", 13.6, pilha="p"), lett("b", 14.9, pilha="p"), lett("c", 16.2, pilha="p")]
    ticks = [e["t"] for e in sfx_plano.plano_de_sfx(tl(pilha, segs=segs, cta=70.0)) if e["efeito"] == "tick"]
    assert ticks == [14.9, 16.2]


def test_instantes_de_volta_sao_so_insert_seguido_de_apresentador():
    segs = [seg("apresentador", 0.0, 4.0), seg("insert", 4.0, 8.0), seg("insert", 8.0, 12.0),
            seg("apresentador", 12.0, 20.0), seg("apresentador", 20.0, 30.0)]
    assert sfx_plano.instantes_de_volta(tl(segs=segs)) == [12.0]


# --- a biblioteca de efeitos: cada wav entre -38 e -31 dBFS RMS -----------------------------------

def _amostras(p):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-map", "0:a", "-f", "s16le", "-ac", "1",
                        "-ar", "48000", "-"], capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.int16).astype(np.float64) / 32768.0


def _rms_db(p):
    a = _amostras(p)
    return 20 * np.log10(max(float(np.sqrt((a ** 2).mean())), 1e-9))


@pytest.fixture(scope="module")
def biblioteca_gerada(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("som")
    niveis = sfx_plano.gerar_biblioteca(pasta)
    return pasta, niveis


def test_a_biblioteca_tem_riser_tick_e_boom_e_nenhum_whoosh(biblioteca_gerada):
    pasta, niveis = biblioteca_gerada
    assert sorted(p.name for p in pasta.iterdir()) == ["boom.wav", "riser.wav", "tick.wav"]
    assert sorted(niveis) == ["boom", "riser", "tick"]


@pytest.mark.parametrize("efeito", ["riser", "tick", "boom"])
def test_cada_wav_fica_entre_menos_38_e_menos_31_dbfs_rms(efeito, biblioteca_gerada):
    pasta, niveis = biblioteca_gerada
    medido = _rms_db(pasta / sfx_plano.ARQUIVO[efeito])
    assert -38.0 <= medido <= -31.0, f"{efeito} em {medido:.1f} dBFS (27/08: -27,2 'parece um tiro'; 20/08: -40,2 inaudível)"
    assert niveis[efeito] == pytest.approx(medido, abs=0.1)
    assert abs(sfx_plano.NIVEIS_DBFS[efeito] - medido) <= 0.3, "a tabela do plano descreve outro arquivo"


@pytest.mark.parametrize("efeito,duracao", [("riser", (0.8, 1.6)), ("tick", (0.03, 0.15)), ("boom", (0.4, 1.0))])
def test_wav_a_48k_sem_estourar_e_com_duracao_de_efeito(efeito, duracao, biblioteca_gerada):
    pasta, _ = biblioteca_gerada
    arq = pasta / sfx_plano.ARQUIVO[efeito]
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate:format=duration",
                        "-of", "csv=p=0", str(arq)], capture_output=True, text=True)
    linhas = [x for x in r.stdout.strip().splitlines() if x]
    sr, dur = linhas[0], linhas[-1]
    assert int(sr) == 48000
    assert duracao[0] <= float(dur) <= duracao[1]
    assert float(np.abs(_amostras(arq)).max()) < 0.99


def test_biblioteca_gera_so_o_que_falta_e_nao_mexe_no_que_existe(tmp_path):
    pasta = tmp_path / "som"
    pasta.mkdir()
    (pasta / "tick.wav").write_bytes(b"RIFF-do-aluno")
    caminhos = sfx_plano.biblioteca(pasta)
    assert sorted(caminhos) == ["boom", "riser", "tick"]
    assert (pasta / "tick.wav").read_bytes() == b"RIFF-do-aluno"      # não regenerou
    assert (pasta / "boom.wav").stat().st_size > 1000 and (pasta / "riser.wav").stat().st_size > 1000


def test_biblioteca_sem_gerar_se_faltar_reclama_com_o_comando(tmp_path):
    with pytest.raises(sfx_plano.BibliotecaIncompleta) as e:
        sfx_plano.biblioteca(tmp_path / "vazia", gerar_se_faltar=False)
    assert "riser.wav" in str(e.value) and "sfx_plano.py --gerar" in str(e.value)


# --- do plano para a mixagem ----------------------------------------------------------------------

def test_eventos_para_mix_convertem_para_o_relogio_entregue(tmp_path):
    pasta = tmp_path / "som"
    caminhos = sfx_plano.biblioteca(pasta)
    sfx = [{"t": 14.6, "efeito": "tick", "funcao": "pilha", "nivel_dbfs": -34.0},
           {"t": 22.65, "efeito": "riser", "funcao": "cta", "nivel_dbfs": -34.0}]
    mix = sfx_plano.eventos_para_mix(sfx, {"aceleracao": 1.35, "a0": 0.0}, caminhos)
    assert [round(m[0], 3) for m in mix] == [round(14.6 / 1.35, 3), round(22.65 / 1.35, 3)]
    assert mix[0][1] == pasta / "tick.wav" and mix[1][1] == pasta / "riser.wav"
    mix2 = sfx_plano.eventos_para_mix(sfx, {"aceleracao": 1.2, "a0": 0.5}, caminhos)
    assert round(mix2[0][0], 3) == round((14.6 - 0.5) / 1.2, 3)


def test_evento_com_efeito_desconhecido_ou_whoosh_e_recusado(tmp_path):
    caminhos = sfx_plano.biblioteca(tmp_path / "som")
    with pytest.raises(ValueError) as e:
        sfx_plano.eventos_para_mix([{"t": 1.0, "efeito": "whoosh", "funcao": "cta", "nivel_dbfs": -34.0}],
                                   {"aceleracao": 1.35, "a0": 0.0}, caminhos)
    assert "whoosh" in str(e.value)


# --- o motor antigo ainda não tem timeline.json: a prancha serve de ponte -------------------------

def test_timeline_de_prancha_leva_as_linhas_da_pilha_e_o_cta():
    prancha = {"accel": 1.35, "cta": {"inicio": 24.0, "logo": 24.2, "label": "saiba mais"},
               "letterings": [
                   {"id": "p1", "s": 14.6, "d": 4.3, "key": "a proposta atrasa", "pilha": True,
                    "linhas": [{"key": "a proposta atrasa", "delay": 0.0}, {"key": "o cliente esfria", "delay": 1.3},
                               {"key": "você perde a venda", "delay": 2.5}]},
                   {"id": "k1", "s": 6.4, "d": 2.2, "key": "FALTA DE TEMPO", "pilha": False, "linhas": []}]}
    segs = [{"bloco": 0, "tipo": "insert", "s": 0.0, "e": 3.1}, {"bloco": 1, "tipo": "orig", "s": 3.1, "e": 24.0}]
    t = sfx_plano.timeline_de_prancha(prancha, segs, 1.35)
    assert t["relogio"]["aceleracao"] == 1.35 and t["relogio"]["a0"] == 0.0
    assert [s["tipo"] for s in t["segmentos"]] == ["insert", "apresentador"]
    assert [(l["s"], l["pilha"]) for l in t["letterings"] if l["pilha"]] == [(14.6, "p1"), (15.9, "p1"), (17.1, "p1")]
    assert t["cta"]["inicio"] == 24.0
    plano = sfx_plano.plano_de_sfx(t)
    assert resumo(plano) == [(14.6, "tick", "pilha"), (15.9, "tick", "pilha"), (17.1, "tick", "pilha"),
                             (22.65, "riser", "cta")]
