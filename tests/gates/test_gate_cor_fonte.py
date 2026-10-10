"""W7.Z, item 4 da prova como aluno: o gate_cor reprovava R/G de 1,67 a 1,77 em todo plano de rosto, mas o avatar CRU da
HeyGen (look de luz laranja) já media de 1,72 a 1,77: o vermelho vinha da fonte, a grade não tinha culpa.

A régua nova COMPARA o entregue com a fonte, plano a plano:
  - a grade PIOROU o R/G em mais de 0,05 sobre a fonte: reprova (a causa é a grade);
  - o entregue passou de 1,6 e a fonte estava em 1,6 ou abaixo: reprova (a grade empurrou o rosto para o vermelho);
  - o entregue passou de 1,6 e a fonte já estava acima: AVISO no laudo, não reprovação (o look é a fonte);
  - sem fonte medida, vale a régua de antes (1,6)."""
import pytest

from gates import gate_cor
from tests.gates.test_gate_cor import CAIXA, CINZA, PELE_VERMELHA, codificar


def medido(*planos):
    """`medido` de um gate_cor com os planos dados ({rg, rg_fonte}); o resto está em ordem."""
    return {"cor": {"primarias": "bt709", "transferencia": "bt709", "matriz": "bt709"},
            "quadro0": {"luminancia": 80.0, "mediana_dos_quadros": 80.0, "razao": 1.0},
            "planos": [{"indice": i, "inicio": float(i), "fim": float(i + 1), "mediana": 80.0, "rg": p.get("rg"),
                        **({"rg_fonte": p["rg_fonte"]} if "rg_fonte" in p else {})} for i, p in enumerate(planos)],
            "quadros_medidos": 12}


def rodar_motivos(*planos):
    m = medido(*planos)
    return gate_cor._motivos(m, None), m


def test_fonte_ja_vermelha_e_grade_que_nao_piora_e_aviso_nao_reprovacao():
    motivos, m = rodar_motivos({"rg": 1.74, "rg_fonte": 1.72}, {"rg": 1.67, "rg_fonte": 1.72})
    assert motivos == []
    avisos = gate_cor._avisos(m)
    assert len(avisos) == 2 and "fonte" in avisos[0] and "1.74" in avisos[0] and "1.72" in avisos[0]


def test_grade_que_piora_mais_de_0_05_reprova_mesmo_com_fonte_vermelha():
    motivos, _ = rodar_motivos({"rg": 1.80, "rg_fonte": 1.72})
    assert len(motivos) == 1 and "piorou" in motivos[0] and "plano 0" in motivos[0]


def test_grade_que_piora_com_fonte_boa_reprova_antes_de_passar_de_1_6():
    motivos, _ = rodar_motivos({"rg": 1.58, "rg_fonte": 1.50})
    assert len(motivos) == 1 and "piorou" in motivos[0]


def test_passou_de_1_6_com_a_fonte_abaixo_reprova_mesmo_sem_piorar_0_05():
    motivos, _ = rodar_motivos({"rg": 1.62, "rg_fonte": 1.58})
    assert len(motivos) == 1 and "1.6" in motivos[0] and "fonte" in motivos[0]


def test_fonte_exatamente_em_1_6_conta_como_abaixo():
    motivos, _ = rodar_motivos({"rg": 1.64, "rg_fonte": 1.60})
    assert len(motivos) == 1


def test_sem_fonte_medida_vale_a_regua_de_antes():
    motivos, _ = rodar_motivos({"rg": 1.70})
    assert len(motivos) == 1 and "vermelho demais" in motivos[0]
    assert rodar_motivos({"rg": 1.55})[0] == []


def test_entregue_melhor_que_a_fonte_nunca_reprova():
    motivos, m = rodar_motivos({"rg": 1.50, "rg_fonte": 1.75})
    assert motivos == [] and gate_cor._avisos(m) == []


def test_o_laudo_traz_o_rg_da_fonte_e_os_avisos(tmp_path):
    v = codificar(tmp_path / "rosto_vermelho.mp4", [(1, CINZA, PELE_VERMELHA)] * 2)
    base = gate_cor.rodar(v, planos=[{"inicio": 0.0, "fim": 1.0, "rosto": CAIXA}, {"inicio": 1.0, "fim": 2.0, "rosto": CAIXA}])
    rg = base["medido"]["planos"][0]["rg"]
    assert base["resultado"] == "REPROVA" and rg > 1.6           # sem a fonte, a régua de antes
    planos = [{"inicio": 0.0, "fim": 1.0, "rosto": CAIXA, "rg_fonte": rg - 0.01},
              {"inicio": 1.0, "fim": 2.0, "rosto": CAIXA, "rg_fonte": rg - 0.01}]
    g = gate_cor.rodar(v, planos=planos)
    assert g["resultado"] == "PASS", g.get("motivo")
    assert g["medido"]["planos"][0]["rg_fonte"] == pytest.approx(rg - 0.01, abs=1e-3)
    assert len(g["medido"]["avisos"]) == 2


def test_o_laudo_reprova_quando_a_grade_piora_sobre_a_fonte(tmp_path):
    v = codificar(tmp_path / "rosto_vermelho.mp4", [(1, CINZA, PELE_VERMELHA)] * 2)
    planos = [{"inicio": 0.0, "fim": 1.0, "rosto": CAIXA, "rg_fonte": 1.4},
              {"inicio": 1.0, "fim": 2.0, "rosto": CAIXA, "rg_fonte": 1.4}]
    g = gate_cor.rodar(v, planos=planos)
    assert g["resultado"] == "REPROVA" and "piorou" in g["motivo"]


def test_limiar_de_piora_esta_nos_limiares_do_gate():
    g = gate_cor._gate("PASS", 0)
    assert g["limiar"]["piora_rg_max"] == 0.05 and g["limiar"]["razao_rg_max"] == 1.6


def test_planos_da_timeline_levam_o_rg_da_fonte_so_nos_de_apresentador():
    tl = {"relogio": {"a0": 0.4, "aceleracao": 1.35},
          "segmentos": [{"tipo": "insert", "s": 0.4, "e": 3.68}, {"tipo": "apresentador", "s": 3.68, "e": 5.6},
                        {"tipo": "apresentador", "s": 5.6, "e": 7.52}]}
    p = gate_cor.planos_da_timeline(tl, rosto=[1, 2, 3, 4], rg_fonte=[None, 1.71, None])
    assert "rg_fonte" not in p[0] and p[1]["rg_fonte"] == 1.71 and "rg_fonte" not in p[2]


def test_rg_da_fonte_mede_o_cru_com_a_mesma_regua_do_entregue(monkeypatch):
    tl = {"relogio": {"a0": 0.4, "aceleracao": 1.35},
          "segmentos": [{"tipo": "insert", "s": 0.4, "e": 3.68}, {"tipo": "apresentador", "s": 3.68, "e": 5.68},
                        {"tipo": "apresentador", "s": 5.68, "e": 7.68}]}
    vistos = []

    def rg_em(avatar, t, caixa):
        vistos.append((round(t, 2), tuple(caixa)))
        return 1.70 + 0.01 * len(vistos)

    r = gate_cor.rg_da_fonte("avatar.mp4", tl, detectar=lambda v, t: (10, 20, 300, 300), rg_em=rg_em)
    assert r[0] is None and r[1] is not None and r[2] is not None
    # o cru mede o instante do plano no relógio do AVATAR (o da timeline), em 3 pontos do plano
    assert {t for t, _c in vistos[:3]} == {round(3.68 + 2.0 * f, 2) for f in (0.25, 0.5, 0.75)}
    assert all(c == (10, 20, 300, 300) for _t, c in vistos)


def test_rg_da_fonte_sem_rosto_no_cru_devolve_none_e_o_gate_cai_na_regua_antiga(monkeypatch):
    tl = {"relogio": {"a0": 0.4, "aceleracao": 1.35}, "segmentos": [{"tipo": "apresentador", "s": 3.68, "e": 5.6}]}
    assert gate_cor.rg_da_fonte("avatar.mp4", tl, detectar=lambda v, t: None, rg_em=lambda *a: 1.7) is None
