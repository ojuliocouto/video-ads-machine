"""W5.X, pendência (c) da W5.A: o gate_cor rodava no montar SEM a caixa do rosto, então a regra C5 "razão R/G acima de
1,6 na caixa do rosto" nunca era medida no anúncio de verdade (o laudo da W5.A não tinha rg em nenhum plano).

Invariante: no `vam montar`, todo plano de apresentador chega ao gate_cor com a caixa do rosto MEDIDA no arquivo
entregue (detecção no meio do plano, a mediana das caixas achadas); sem rosto achado, o plano segue sem caixa e o
laudo diz isso (`rosto_medido: false`)."""
import produzir_ad
from gates import gate_cor


def _tl():
    return {"relogio": {"a0": 0.4, "aceleracao": 1.35},
            "segmentos": [{"tipo": "insert", "s": 0.4, "e": 3.68}, {"tipo": "apresentador", "s": 3.68, "e": 5.6},
                          {"tipo": "apresentador", "s": 5.6, "e": 7.52}]}


def test_caixa_do_rosto_e_a_mediana_das_achadas_no_meio_dos_planos_de_apresentador(monkeypatch):
    vistos = []
    caixas = iter([(400, 500, 300, 300), (420, 520, 310, 310)])

    def detectar(video, t):
        vistos.append(round(t, 2))
        return next(caixas)

    monkeypatch.setattr(gate_cor, "_detectar_rosto", detectar)
    caixa = gate_cor.caixa_rosto_entregue("final.mp4", _tl())
    assert vistos == [round(((3.68 + 5.6) / 2 - 0.4) / 1.35, 2), round(((5.6 + 7.52) / 2 - 0.4) / 1.35, 2)]
    assert caixa == [410, 510, 305, 305]


def test_sem_rosto_achado_devolve_none(monkeypatch):
    monkeypatch.setattr(gate_cor, "_detectar_rosto", lambda v, t: None)
    assert gate_cor.caixa_rosto_entregue("final.mp4", _tl()) is None


def test_o_montar_passa_a_caixa_medida_ao_gate_cor(monkeypatch, tmp_path):
    capturado = {}
    monkeypatch.setattr(gate_cor, "caixa_rosto_entregue", lambda video, tl: [10, 20, 30, 40])

    def rodar(video, projeto=None, planos=None, caixa_rosto=None):
        capturado["planos"] = planos
        return {"nome": "gate_cor", "etapa": "depois", "resultado": "PASS", "saida": 0}

    monkeypatch.setattr(gate_cor, "rodar", rodar)

    class Motor(object):
        final = tmp_path / "final.mp4"

    class Ctx(object):
        motor, projeto = Motor(), {}

        def timeline(self):
            return _tl()

    produzir_ad._g_cor(Ctx())
    ap = [p for p in capturado["planos"] if "rosto" in p]
    assert len(ap) == 2 and all(p["rosto"] == [10, 20, 30, 40] for p in ap)
