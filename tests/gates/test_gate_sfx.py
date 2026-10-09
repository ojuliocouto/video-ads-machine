"""W4.B, C11: gate_sfx. O som tem função, cabe no teto e não cai onde o diretor já reprovou.

Reprova quando (e cada regra tem o seu mutante abaixo, provado vermelho):
  - efeito (whoosh, ou qualquer nome fora de riser, tick e boom);
  - nivel: evento ou wav fora de -38 a -31 dBFS RMS (as duas âncoras humanas: -40,2 inaudível, -27,2 "parece um tiro");
  - densidade: mais de 1 evento a cada 4 s no arquivo entregue (a pilha conta como um; ticks dela a 0,5 s ou mais);
  - volta_ao_avatar: evento (que não seja o riser) a menos de 0,25 s da volta de um insert para o apresentador;
  - funcao: riser fora de 1,0 s antes do CTA, tick sem linha de pilha, boom sem KEY gigante-atrás.
"""
import json
import random
import subprocess
from pathlib import Path

import pytest

from cinema import sfx_plano
from gates import gate_sfx
from projeto import pastas, status

RAIZ = Path(__file__).resolve().parents[2]


def exemplo():
    return json.loads((RAIZ / "contratos" / "exemplos" / "timeline.valido.json").read_text(encoding="utf-8"))


def evento(t, efeito="tick", funcao=None, nivel=-34.0):
    return {"t": t, "efeito": efeito, "funcao": funcao or sfx_plano.FUNCAO.get(efeito, "pilha"), "nivel_dbfs": nivel}


def regras(r):
    return {f["regra"] for f in r.detalhes["falhas"]}


def com_sfx(*eventos, **mudancas):
    t = exemplo()
    t["sfx"] = list(eventos)
    t.update(mudancas)
    return t


def com_gigante(t, id_, s):
    """Acrescenta uma KEY gigante-atrás ao exemplo, no bloco 2."""
    t["letterings"].append({"id": id_, "bloco": 2, "lead": None, "key": "TEMPO", "s": s, "d": 1.5,
                            "estilo": "gigante_atras", "split": False, "baixo": False, "pilha": None, "cta": False})
    return t


# --- o que passa ----------------------------------------------------------------------------------

def test_o_exemplo_valido_do_contrato_passa():
    r = gate_sfx.avaliar(exemplo())
    assert r.ok, r.motivo
    assert r.detalhes["estado"] == "PASS" and r.detalhes["falhas"] == []
    assert r.detalhes["medido"]["eventos"] == 4


def test_peca_sem_nenhum_som_passa_porque_vazio_e_melhor_que_inventar():
    r = gate_sfx.avaliar(com_sfx())
    assert r.ok and r.detalhes["medido"]["eventos"] == 0


def test_o_resultado_traz_o_que_o_laudo_precisa():
    r = gate_sfx.avaliar(exemplo())
    assert set(r.detalhes) >= {"estado", "falhas", "medido", "limiar"}
    assert r.detalhes["limiar"]["nivel_dbfs"] == [-38.0, -31.0]
    assert r.detalhes["limiar"]["intervalo_s"] == 4.0
    assert gate_sfx.NOME == "gate_sfx"


# --- os mutantes: cada um tem que reprovar pela regra certa ---------------------------------------

def test_mutante_whoosh_reprova():
    t = com_sfx(evento(5.0, "whoosh", "cta"), evento(22.65, "riser", "cta"))
    r = gate_sfx.avaliar(t)
    assert not r.ok and "efeito" in regras(r)
    assert "whoosh" in r.motivo and "31/08" in r.motivo


def test_mutante_efeito_desconhecido_reprova():
    r = gate_sfx.avaliar(com_sfx(evento(5.0, "zap", "cta")))
    assert not r.ok and "efeito" in regras(r)


@pytest.mark.parametrize("nivel", [-27.2, -40.2, -30.9, -38.1])
def test_mutante_nivel_fora_de_menos_38_a_menos_31_reprova(nivel):
    r = gate_sfx.avaliar(com_sfx(evento(22.65, "riser", "cta", nivel)))
    assert not r.ok and "nivel" in regras(r)
    assert str(nivel) in r.motivo


@pytest.mark.parametrize("nivel", [-38.0, -31.0, -34.5])
def test_nivel_nas_bordas_da_faixa_passa(nivel):
    assert gate_sfx.avaliar(com_sfx(evento(22.65, "riser", "cta", nivel))).ok


def test_mutante_densidade_dois_eventos_a_menos_de_4_s_reprova():
    t = com_gigante(com_gigante(exemplo(), "l5", 7.5), "l6", 8.6)
    t["sfx"] = [evento(7.5, "boom"), evento(8.6, "boom"), evento(22.65, "riser")]
    r = gate_sfx.avaliar(t)
    assert not r.ok and "densidade" in regras(r)
    assert "4" in r.motivo


def test_a_densidade_conta_no_arquivo_entregue_nao_na_footage():
    # 5,0 s de footage = 3,7 s entregues: reprova. 5,6 s de footage = 4,15 s entregues: passa.
    perto = com_gigante(com_gigante(exemplo(), "l5", 7.0), "l6", 12.0)
    perto["sfx"] = [evento(7.0, "boom"), evento(12.0, "boom")]
    assert "densidade" in regras(gate_sfx.avaliar(perto))
    longe = com_gigante(com_gigante(exemplo(), "l5", 7.0), "l6", 12.6)
    longe["sfx"] = [evento(7.0, "boom"), evento(12.6, "boom")]
    assert gate_sfx.avaliar(longe).ok


def test_mutante_ticks_da_pilha_colados_reprovam():
    t = exemplo()
    t["letterings"][2]["s"] = 14.9              # linha b4 a 0,22 s entregue da anterior (14,6)
    t["sfx"] = [evento(14.6), evento(14.9), evento(17.1), evento(22.65, "riser")]
    r = gate_sfx.avaliar(t)
    assert not r.ok and "densidade" in regras(r) and "0,5" in r.motivo


def test_pilha_e_riser_a_4_1_s_um_do_outro_passam_como_no_exemplo_do_contrato():
    assert gate_sfx.avaliar(exemplo()).ok


def test_duas_pilhas_diferentes_coladas_reprovam():
    t = exemplo()
    t["letterings"] += [
        {"id": "m1", "bloco": 4, "lead": None, "key": "x", "s": 18.0, "d": 1.0, "estilo": "caixa_nativa",
         "split": False, "baixo": False, "pilha": "outra", "cta": False}]
    t["sfx"] = [evento(14.6), evento(15.9), evento(17.1), evento(18.0), evento(22.65, "riser")]
    r = gate_sfx.avaliar(t)
    assert not r.ok and "densidade" in regras(r)


def test_mutante_evento_na_volta_pro_avatar_reprova():
    t = com_gigante(exemplo(), "l5", 13.6)         # o insert acaba em 13,6 e o apresentador volta
    t["sfx"] = [evento(13.6, "boom"), evento(22.65, "riser")]
    r = gate_sfx.avaliar(t)
    assert not r.ok and "volta_ao_avatar" in regras(r)
    assert "13.6" in r.motivo or "13,6" in r.motivo


def test_evento_logo_depois_da_volta_tambem_reprova_mas_longe_dela_passa():
    colado = com_gigante(exemplo(), "l5", 13.8)
    colado["sfx"] = [evento(13.8, "boom")]
    assert "volta_ao_avatar" in regras(gate_sfx.avaliar(colado))
    longe = com_gigante(exemplo(), "l5", 14.2)
    longe["sfx"] = [evento(14.2, "boom")]
    assert gate_sfx.avaliar(longe).ok


def test_o_riser_nunca_e_acusado_de_estar_na_volta():
    t = exemplo()                                  # o insert acaba em 22,5 e o riser cai em 22,65
    assert t["segmentos"][6]["e"] == 22.5 and t["segmentos"][7]["s"] == 22.5
    assert gate_sfx.avaliar(t).ok


def test_mutante_riser_longe_do_cta_reprova():
    r = gate_sfx.avaliar(com_sfx(evento(20.0, "riser", "cta")))        # 2,96 s entregues antes do CTA
    assert not r.ok and "funcao" in regras(r)
    assert "1,0" in r.motivo or "1.0" in r.motivo


def test_mutante_funcao_trocada_reprova():
    r = gate_sfx.avaliar(com_sfx(evento(22.65, "riser", "pilha")))
    assert not r.ok and "funcao" in regras(r)


def test_mutante_tick_sem_linha_de_pilha_reprova():
    r = gate_sfx.avaliar(com_sfx(evento(5.0, "tick", "pilha"), evento(22.65, "riser")))
    assert not r.ok and "funcao" in regras(r)


def test_mutante_boom_sem_key_gigante_atras_reprova():
    r = gate_sfx.avaliar(com_sfx(evento(6.4, "boom", "key_gigante")))   # l0 é caixa_nativa
    assert not r.ok and "funcao" in regras(r)


def test_boom_na_key_gigante_atras_passa():
    t = exemplo()
    t["letterings"][0]["estilo"] = "gigante_atras"
    t["sfx"] = [evento(6.4, "boom"), evento(22.65, "riser")]
    assert gate_sfx.avaliar(t).ok


def test_todas_as_falhas_vao_juntas_no_motivo():
    t = com_sfx(evento(5.0, "whoosh", "cta"), evento(22.65, "riser", "cta", -27.2))
    r = gate_sfx.avaliar(t)
    assert {"efeito", "nivel"} <= regras(r)
    assert "whoosh" in r.motivo and "-27.2" in r.motivo


# --- a biblioteca de wavs -------------------------------------------------------------------------

def test_wav_alto_demais_na_biblioteca_reprova_mesmo_com_o_plano_certo():
    niveis = {"riser": -34.3, "tick": -27.2, "boom": -34.0}
    r = gate_sfx.avaliar(exemplo(), biblioteca=Path("/nao/importa"), medir_wav=lambda p: niveis[p.stem])
    assert not r.ok and "biblioteca" in regras(r)
    assert "tick" in r.motivo and "-27.2" in r.motivo


def test_biblioteca_de_verdade_passa_e_com_um_wav_a_7_dB_acima_reprova(tmp_path):
    pasta = tmp_path / "som"
    sfx_plano.gerar_biblioteca(pasta)
    r = gate_sfx.avaliar(exemplo(), biblioteca=pasta)
    assert r.ok, r.motivo
    assert set(r.detalhes["medido"]["biblioteca"]) == {"riser", "tick", "boom"}
    forte = tmp_path / "forte.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(pasta / "tick.wav"), "-af", "volume=7dB",
                    str(forte)], check=True)
    forte.replace(pasta / "tick.wav")
    r = gate_sfx.avaliar(exemplo(), biblioteca=pasta)
    assert not r.ok and "biblioteca" in regras(r)


def test_biblioteca_sem_um_wav_e_insumo_invalido(tmp_path):
    pasta = tmp_path / "som"
    sfx_plano.gerar_biblioteca(pasta)
    (pasta / "riser.wav").unlink()
    with pytest.raises(gate_sfx.InsumoInvalido) as e:
        gate_sfx.avaliar(exemplo(), biblioteca=pasta)
    assert "riser.wav" in str(e.value)


# --- o plano e o gate concordam, por construção ---------------------------------------------------

def _timeline_aleatoria(rng):
    accel = rng.choice([1.0, 1.2, 1.35, 1.5])
    a0 = rng.choice([0.0, 0.0, 0.3])
    t, segs = a0, []
    for k in range(rng.randint(5, 11)):
        dur = rng.uniform(1.2, 7.0)
        segs.append({"bloco": k, "tipo": rng.choice(["apresentador", "insert", "insert"]), "s": round(t, 3),
                     "e": round(t + dur, 3), "sub": 0, "de": 1})
        t += dur
    fim = round(t, 3)
    letts = []
    for k in range(rng.randint(2, 7)):
        s = round(rng.uniform(a0 + 1.0, fim - 2.0), 3)
        estilo = rng.choice(["caixa_nativa", "gigante_atras", "punch", "gigante_atras"])
        letts.append({"id": "k%d" % k, "bloco": 0, "key": "X", "s": s, "d": 1.0, "estilo": estilo, "split": False,
                      "baixo": False, "pilha": None, "cta": False})
    for p in range(rng.randint(0, 2)):
        base = rng.uniform(a0 + 1.0, fim - 6.0)
        for j in range(rng.randint(2, 4)):
            letts.append({"id": "p%d_%d" % (p, j), "bloco": 0, "key": "X", "s": round(base + j * rng.uniform(0.6, 1.8), 3),
                          "d": 1.0, "estilo": "caixa_nativa", "split": False, "baixo": False, "pilha": "p%d" % p,
                          "cta": False})
    letts.sort(key=lambda l: l["s"])
    return {"relogio": {"base": "footage_1x", "fps": 30, "aceleracao": accel, "cauda_s": 0.45, "a0": a0},
            "segmentos": segs, "letterings": letts,
            "cta": {"inicio": round(fim - 1.0, 3), "logo": round(fim - 0.8, 3), "label": "saiba mais", "sem_lead": False},
            "sfx": []}


@pytest.mark.parametrize("semente", range(40))
def test_todo_plano_de_sfx_passa_no_gate_sfx(semente):
    t = _timeline_aleatoria(random.Random(semente))
    t["sfx"] = sfx_plano.plano_de_sfx(t)
    r = gate_sfx.avaliar(t)
    assert r.ok, "semente %d: %s" % (semente, r.motivo)


# --- a CLI ----------------------------------------------------------------------------------------

def _projeto_com_timeline(tmp_path, timeline):
    estado = tmp_path / "_local"
    pj = pastas.projeto("anuncio", estado).criar()
    if timeline is not None:
        status.escrever_json_atomico(pj.timeline, timeline)
    return estado, pj


def test_cli_sai_0_com_o_timeline_do_contrato(tmp_path, capsys):
    estado, pj = _projeto_com_timeline(tmp_path, exemplo())
    assert gate_sfx.main(["anuncio", "--estado", str(estado)]) == 0
    assert "PASSA" in capsys.readouterr().out
    assert status.ler_json(pj.status_json)["atual"]["etapa"] == "gate_sfx"
    assert status.ler_json(pj.status_json)["atual"]["estado"] == "ok"


def test_cli_sai_1_e_diz_o_motivo_quando_o_mutante_reprova(tmp_path, capsys):
    t = com_sfx(evento(5.0, "whoosh", "cta"))
    estado, pj = _projeto_com_timeline(tmp_path, t)
    assert gate_sfx.main(["anuncio", "--estado", str(estado)]) == 1
    assert "REPROVA" in capsys.readouterr().out
    atual = status.ler_json(pj.status_json)["atual"]
    assert atual["estado"] == "falhou" and "whoosh" in atual["motivo"]


def test_cli_sai_2_sem_timeline(tmp_path, capsys):
    estado, pj = _projeto_com_timeline(tmp_path, None)
    assert gate_sfx.main(["anuncio", "--estado", str(estado)]) == 2
    assert "timeline.json" in capsys.readouterr().err


def test_cli_sai_2_com_timeline_que_nao_cumpre_o_contrato(tmp_path, capsys):
    t = exemplo()
    t["relogio"]["aceleracao"] = 9.0                # fora do contrato: o relógio não é confiável para medir nada
    estado, pj = _projeto_com_timeline(tmp_path, t)
    assert gate_sfx.main(["anuncio", "--estado", str(estado)]) == 2
    assert "aceleracao" in capsys.readouterr().err


def test_cli_reprova_whoosh_e_nivel_fora_mesmo_que_o_contrato_tambem_os_recuse(tmp_path, capsys):
    t = exemplo()
    t["sfx"][0]["efeito"] = "whoosh"
    t["sfx"][1]["nivel_dbfs"] = -27.2
    estado, pj = _projeto_com_timeline(tmp_path, t)
    assert gate_sfx.main(["anuncio", "--estado", str(estado)]) == 1
    saida = capsys.readouterr().out
    assert "REPROVA (efeito)" in saida and "REPROVA (nivel)" in saida


def test_cli_sai_2_com_slug_invalido(tmp_path, capsys):
    assert gate_sfx.main(["../fora", "--estado", str(tmp_path)]) == 2
