"""W7.Y: o `dur_max` por insert e o ritmo que o plano mede.

Na prova como aluno, `dur_max: 4.0` nos 5 inserts do anúncio não mexeu nos cortes/min (13,9 antes, 13,9 depois) e
parecia que o plano ignorava o campo. Não ignora: plano, footage e overlay chamam a MESMA função (`ritmo.plano_de_ritmo`)
com o mesmo `dur_max`. O que acontece é de conta:

  - bloco longo (8,2 s, 5,7 s, 6,3 s): o teto só MUDA O INSTANTE da volta pro rosto, e já havia uma volta sem teto;
  - bloco curto (4,6 s e 4,4 s) com teto 4,0: sobram 0,6 s e 0,4 s, abaixo do piso de rosto (MIN_PLANO, 1,5 s). O ritmo
    prefere não piscar o rosto por 0,6 s e cobre o bloco inteiro com duas fatias de insert. O teto não devolve o rosto.

O defeito real era o silêncio: o plano ficava pendente em ritmo sem dizer que o `dur_max` não tinha efeito. Estes testes
travam (1) a paridade plano x motor com `dur_max` e (2) o aviso, com o teto que funcionaria.
"""
import pytest

import ritmo
from footage import blocos as FB
from plano import checklist
from plano import medir as M

BLOCOS = [  # os blocos de insert do anúncio da prova (duração em segundos de footage 1x)
    {"i": 0, "tipo": "insert", "insert": "paginas", "layout": "cheio", "fala": "a", "s": 0.0, "e": 5.44},
    {"i": 1, "tipo": "insert", "insert": "vendas", "layout": "cheio", "fala": "b", "s": 5.44, "e": 9.6},
    {"i": 2, "tipo": "apresentador", "fala": "c", "s": 9.6, "e": 10.88},
    {"i": 3, "tipo": "insert", "insert": "conector", "layout": "cheio", "fala": "d", "s": 10.88, "e": 15.52},
    {"i": 4, "tipo": "insert", "insert": "publicar", "layout": "cheio", "fala": "e", "s": 15.52, "e": 23.68},
    {"i": 5, "tipo": "insert", "insert": "conector", "layout": "cheio", "fala": "f", "s": 23.68, "e": 28.08},
    {"i": 6, "tipo": "cta", "fala": "g", "s": 28.08, "e": 33.0}]
CHAVES = ("paginas", "vendas", "conector", "publicar")


def projeto(cap):
    return {"inserts": {k: ({"dur_max": cap} if cap else {}) for k in CHAVES}}


def cortes(cap):
    segs = M._plano_de_ritmo(BLOCOS, projeto(cap))
    return M._ritmo_entregue(segs, 33.0, 1.35, BLOCOS)["cortes_min"], segs


def test_plano_e_motor_aplicam_o_mesmo_dur_max():
    """Uma função só: o plano de ritmo do motor (footage) com o config do insert é o do plano.json."""
    for cap in (4.0, 3.0, 2.0):
        do_plano = M._plano_de_ritmo(BLOCOS, projeto(cap))
        inserts = {"#%d#" % (n + 1): {"file": "x.mp4", "dur_max": cap} for n in range(len(BLOCOS))}
        blocks = [{"type": "insert" if b["tipo"] == "insert" else "orig", "instr": "#%d#" % (n + 1), "narr": b["fala"]}
                  for n, b in enumerate(BLOCOS)]
        spans = [(b["s"], b["e"]) for b in BLOCOS]
        do_motor = FB.plano_de_ritmo(blocks, spans, inserts)
        chaves = ("bloco", "tipo", "s", "e", "layout", "fonte_off")
        assert [{k: s.get(k) for k in chaves} for s in do_plano] == [{k: s.get(k) for k in chaves} for s in do_motor], cap


def test_teto_que_deixa_rosto_suficiente_muda_o_ritmo():
    sem, _ = cortes(None)
    com, segs = cortes(2.5)
    assert com > sem
    # e o rosto volta de verdade nos blocos 3 e 5 (antes eram só insert)
    for bloco in (3, 5):
        assert any(s["bloco"] == bloco and s["tipo"] != "insert" for s in segs), bloco


def test_teto_perto_do_tamanho_do_bloco_nao_devolve_o_rosto():
    """O caso da prova: 4,0 s num bloco de 4,6 s sobra menos que o piso de rosto, o bloco fica todo em insert."""
    _, segs = cortes(4.0)
    assert not any(s["bloco"] in (3, 5) and s["tipo"] != "insert" for s in segs)


def plano_pendente_em_ritmo(cap):
    r = {"cortes_min": 13.9, "frac_acima_6s": 0.0, "maior_plano_s": 3.1, "plano_medio_s": 2.2}
    return {"blocos": BLOCOS, "ritmo": r, "mapa_inserts": [], "letterings": []}, projeto(cap)


def test_ritmo_pendente_diz_qual_dur_max_nao_teve_efeito_e_o_teto_que_teria():
    plano, pj = plano_pendente_em_ritmo(4.0)
    item = checklist._ritmo(plano, pj)
    assert item["status"] == "pendente"
    m = item["motivo"]
    assert "dur_max" in m and "conector" in m and "3 (4,6 s)" in m and "5 (4,4 s)" in m, m
    # o teto que funciona deixa o piso de rosto: o menor dos dois blocos, 4,4 - 1,5 = 2,9 s
    assert "2,9" in m, m
    assert len(m) <= checklist.MOTIVO_MAX


def test_sem_dur_max_o_motivo_do_ritmo_nao_muda():
    plano, pj = plano_pendente_em_ritmo(None)
    item = checklist._ritmo(plano, pj)
    assert "dur_max" not in item["motivo"]


def test_o_piso_do_aviso_e_o_piso_do_ritmo():
    assert checklist.PISO_ROSTO_S == ritmo.MIN_PLANO


@pytest.mark.parametrize("cap", [2.5, 2.0])
def test_dur_max_que_funciona_nao_gera_aviso(cap):
    plano, pj = plano_pendente_em_ritmo(cap)
    assert "dur_max" not in checklist._ritmo(plano, pj)["motivo"]
