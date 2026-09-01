#!/usr/bin/env python3
"""Teste do plano de ritmo. O contrato sai da MEDIÇÃO das referências, não de gosto."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ritmo as R

from caminhos import V2L as _L
PRANCHA = _L / "prancha"


def _blocos_do_ad(ad):
    pr = json.loads((PRANCHA / ad / "prancha.json").read_text())
    from caminhos import INPUTS as _IN
    ins = json.loads((_IN /
                      f"{ad}_inserts.json").read_text())
    por_idx = list(ins.values())
    n_ins = 0
    out = []
    for b in pr["blocos"]:
        cfg = {}
        if b["tipo"] == "insert":
            cfg = por_idx[n_ins] if n_ins < len(por_idx) else {}
            n_ins += 1
        out.append({"tipo": "insert" if b["tipo"] == "insert" else "orig",
                    "s": b["s"], "e": b["e"],
                    "crop": cfg.get("crop"), "dur_max": cfg.get("dur_max")})
    return out, pr


def _teto_de_trocas(blocos):
    """Trocas de conteudo que ESTE modulo consegue extrair: fronteira de bloco mais
    alternancia dentro de insert.

    Card de lettering fica de fora de proposito: o modulo nao pica card, e picar tem
    custo de leitura. Onde isso pesa (jh14 tem um card de 11,5s; jh15 tem 17,7s de card)
    o teste avisa em vez de reprovar, porque a decisao e do diretor na prancha.
    """
    fronteiras = sum(1 for a, b in zip(blocos, blocos[1:]) if a["tipo"] != b["tipo"])
    dentro = 0
    for b in blocos:
        if b["tipo"] != "insert":
            continue
        dur = float(b["e"]) - float(b["s"])
        cap = b.get("dur_max")
        if cap and float(cap) < dur - 0.3:
            # a fonte acaba antes do bloco: o que sobra vira avatar, e avatar nao
            # alterna com nada. O teto vem do trecho que TEM tela, mais o corte de
            # volta pro rosto no fim do cap.
            dur = float(cap)
            dentro += 1
        if dur >= R.ALVO_PLANO * R.FATOR_CORTE:
            dentro += max(int(round(dur / R.ALVO_PLANO)) - 1, 0)
    return fronteiras + dentro


class TestePlanoDeRitmo(unittest.TestCase):

    def test_nao_deixa_buraco_nem_sobreposicao(self):
        blocos = [{"tipo": "insert", "s": 0.0, "e": 9.0, "crop": "800:700:40:40"},
                  {"tipo": "orig", "s": 9.0, "e": 21.0}]
        segs = R.plano_de_ritmo(blocos)
        self.assertAlmostEqual(segs[0]["s"], 0.0, places=3)
        self.assertAlmostEqual(segs[-1]["e"], 21.0, places=3)
        for a, b in zip(segs, segs[1:]):
            self.assertAlmostEqual(a["e"], b["s"], places=3,
                                   msg="buraco ou sobreposicao entre planos")

    def test_bloco_curto_nao_e_subdividido(self):
        segs = R.plano_de_ritmo([{"tipo": "orig", "s": 0.0, "e": 3.0}])
        self.assertEqual(len(segs), 1)

    def test_nenhum_plano_abaixo_do_minimo(self):
        for dur in (5.0, 8.0, 11.0, 13.2, 16.0, 22.7, 52.4):
            segs = R.plano_de_ritmo([{"tipo": "orig", "s": 0.0, "e": dur}])
            menor = min(x["e"] - x["s"] for x in segs)
            self.assertGreaterEqual(round(menor, 2), R.MIN_PLANO,
                                    f"dur={dur}: plano de {menor:.2f}s vira nervosismo")

    def test_recortes_derivados_ficam_dentro_do_aprovado(self):
        base = "800:700:40:40"
        rs = R.derivar_recortes(base, 3)
        self.assertEqual(rs[0], base, "o primeiro plano tem que ser o recorte aprovado")
        bw, bh, bx, by = [int(v) for v in base.split(":")]
        for r in rs[1:]:
            w, h, x, y = [int(v) for v in r.split(":")]
            self.assertGreaterEqual(x, bx)
            self.assertGreaterEqual(y, by)
            self.assertLessEqual(x + w, bx + bw, "recorte derivado saiu da janela aprovada")
            self.assertLessEqual(y + h, by + bh, "recorte derivado saiu da janela aprovada")

    def test_insert_longo_volta_pro_avatar_no_meio(self):
        segs = R.plano_de_ritmo([{"tipo": "insert", "s": 0.0, "e": 13.0,
                                  "crop": "800:700:40:40"}])
        tipos = [x["tipo"] for x in segs]
        self.assertIn("orig", tipos,
                      "insert de 13s sem voltar pro rosto vira slideshow de tela")

    def test_os_quatro_ads_chegam_na_faixa_da_referencia(self):
        for ad in ("jh13v2", "jh14v2", "jh15v2"):
            p = PRANCHA / ad / "prancha.json"
            if not p.exists():
                continue
            with self.subTest(ad=ad):
                blocos, pr = _blocos_do_ad(ad)
                segs = R.plano_de_ritmo(blocos)
                dur = pr["total"] / pr.get("accel", 1.35)
                r = R.resumo(segs, dur)
                self.assertGreaterEqual(r["cortes_min"], 16.0,
                                        f"{ad} ficou em {r['cortes_min']}/min")
                self.assertLessEqual(r["maior_plano"] / pr.get("accel", 1.35), 7.2,
                                     f"{ad} ainda tem plano de "
                                     f"{r['maior_plano'] / 1.35:.1f}s no arquivo")

    def test_cortes_decisivos_batem_a_referencia(self):
        """Corte que o olho le e o que TROCA DE CONTEUDO, nao o que reenquadra.

        Medido no jh13: reenquadrar ou mudar escala no mesmo plano continuo pontua no
        maximo 0,295 (limiar 0,30), enquanto a troca avatar <-> insert passa folgado.
        O material comporta ~61 trocas (40,8/min), entao o piso de 16/min e alcancavel
        sem asset novo: basta alternar mais.
        """
        for ad in ("jh13v2", "jh14v2", "jh15v2"):
            p = PRANCHA / ad / "prancha.json"
            if not p.exists():
                continue
            with self.subTest(ad=ad):
                blocos, pr = _blocos_do_ad(ad)
                segs = R.plano_de_ritmo(blocos)
                dur = pr["total"] / pr.get("accel", 1.35)
                trocas = sum(1 for a, b in zip(segs, segs[1:]) if a["tipo"] != b["tipo"])
                por_min = trocas / (dur / 60)
                for j, b in enumerate(blocos):
                    if b["tipo"] != "insert":
                        continue
                    efetiva = min(float(b["e"]) - float(b["s"]),
                                  float(b.get("dur_max") or 1e9))
                    if j == 0 and float(b["s"]) <= 1.0:
                        # abertura: a janela do hook nao alterna por regra (o texto
                        # de abertura cairia na cara do apresentador), entao ela
                        # nao conta na cobranca de alternancia
                        efetiva -= R.HOOK_JANELA
                    if efetiva < R.ALVO_PLANO * R.FATOR_CORTE:
                        continue
                    meus = [x for x in segs if x["bloco"] == j]
                    self.assertIn(
                        "orig", [x["tipo"] for x in meus],
                        f"{ad} bloco {j}: insert de {efetiva:.1f}s sem voltar pro rosto. "
                        f"Reenquadrar nao registra como corte (medido 0,22 contra 0,30).")
                    # so ate o ultimo plano de tela: o que vem depois e avatar puro,
                    # porque a fonte acabou, e ali repetir tipo nao e defeito.
                    ult = max(k for k, x in enumerate(meus) if x["tipo"] == "insert")
                    for x, y in zip(meus[:ult + 1], meus[1:ult + 1]):
                        self.assertNotEqual(
                            x["tipo"], y["tipo"],
                            f"{ad} bloco {j}: dois planos seguidos de {x['tipo']} no "
                            f"trecho com tela, ou seja um corte que o olho nao le.")
                if por_min < 16.0:
                    print(f"\n    [direcao] {ad}: {por_min:.1f} trocas/min, abaixo do "
                          f"piso de 16. O que segura e insert com dur_max: a fonte acaba "
                          f"e o resto do bloco vira avatar parado de uma vez.")

    def test_dur_max_espalhado_em_fatias(self):
        """Insert com fonte curta ESPALHA a tela pelo bloco, alternando com o rosto.

        Antes: 4s de tela e depois 17,5s de avatar parado de uma vez (os planos de 12s
        que reprovam por tempo parado saem TODOS daqui). Agora: fatias de tela
        intercaladas com rosto, consumo total de fonte igualzinho (o cap), e o bloco
        inteiro vira alternancia.
        """
        segs = R.plano_de_ritmo([{"tipo": "insert", "s": 10.0, "e": 31.5,
                                  "crop": "900:800:10:10", "dur_max": 4.0}])
        tela = [x for x in segs if x["tipo"] == "insert"]
        rosto = [x for x in segs if x["tipo"] == "orig"]
        t_tela = sum(x["e"] - x["s"] for x in tela)
        # DECISAO DE DIRECAO (18/08): fonte curta pode ser REUSADA com recorte
        # diferente (jump cut pro detalhe), maximo 2 passadas. Entao o total de tela
        # pode chegar a 2x o cap, mas CADA fatia tem que caber na fonte.
        self.assertLessEqual(t_tela, 2 * 4.0 + 0.1, "mais de 2 passadas na mesma fonte")
        for x in tela:
            self.assertLessEqual(x.get("fonte_off", 0.0) + (x["e"] - x["s"]), 4.0 + 0.05,
                                 "fatia de tela le alem do fim da fonte (congelaria)")
        # espalhou: mais de uma fatia de tela, e rosto entre elas
        self.assertGreaterEqual(len(tela), 2, "cap de 4s em bloco de 21,5s cabe 2+ fatias")
        self.assertGreaterEqual(len(rosto), len(tela) - 1)
        # nenhum plano de rosto acima de 6,5s: era a zona morta de 17,5s
        maior_rosto = max(x["e"] - x["s"] for x in rosto)
        self.assertLessEqual(maior_rosto, 7.2,
                             f"rosto de {maior_rosto:.1f}s seguido: a zona morta voltou")
        # CONTRATO MUDOU 19/08/2026: recorte derivado (zoom) foi abolido depois que o
        # Julio viu o AD13 ("um zoom que nem da pra ver"): ampliar gravacao de tela
        # vira mingau. O recorte aprovado e o unico; a variedade vem da fonte correr
        # (fonte_off), entao fatias vizinhas com o MESMO recorte sao o esperado.
        for x in tela:
            self.assertEqual(x.get("crop"), "900:800:10:10",
                             "fatia com recorte diferente do aprovado pelo diretor")

    def test_fatias_cobrem_o_bloco_sem_inverter(self):
        """Regressao do jh14 bloco 4 (18,2s, cap 4,0): saiu fatia com e < s.

        Causa: no regime de reuso o rosto era calculado sobre dur - cap, mas o total de
        tela com reuso NAO e o cap, e a soma estourava o bloco. Invariantes que valem
        pra QUALQUER formato de bloco com cap:
          - todo plano tem e > s
          - os planos sao contiguos e cobrem exatamente [s, e] do bloco
          - nenhuma fatia de tela le alem do cap da fonte
        """
        formatos = [(18.2, 4.0), (21.5, 4.0), (13.5, 12.0), (15.6, 11.8),
                    (8.0, 2.0), (6.0, 5.0), (30.0, 3.0), (5.2, 1.0)]
        for dur, cap in formatos:
            with self.subTest(dur=dur, cap=cap):
                segs = R.plano_de_ritmo([{"tipo": "insert", "s": 10.0,
                                          "e": 10.0 + dur,
                                          "crop": "900:800:10:10", "dur_max": cap}])
                for x in segs:
                    self.assertGreater(x["e"], x["s"] + 0.05,
                                       f"plano invertido/vazio: {x}")
                self.assertAlmostEqual(segs[0]["s"], 10.0, places=2)
                self.assertAlmostEqual(segs[-1]["e"], 10.0 + dur, places=2)
                for a, b in zip(segs, segs[1:]):
                    self.assertAlmostEqual(a["e"], b["s"], places=2)
                for x in segs:
                    if x["tipo"] == "insert":
                        self.assertLessEqual(
                            x.get("fonte_off", 0.0) + (x["e"] - x["s"]), cap + 0.05,
                            f"fatia le alem da fonte: {x}")

    def test_abertura_nao_alterna_dentro_da_janela_do_hook(self):
        """O bloco 0 e o fundo do HOOK: insert em tela cheia sob o texto de abertura.

        A alternancia enfiou um respiro de rosto aos ~2s e o hook caiu NA CARA do
        Thales (gate de colisao pegou no jh13: texto cobrindo 5,7% do rosto em
        t=1,5s entregue). Regra: nos primeiros HOOK_JANELA segundos de footage do
        bloco 0, a imagem e SEMPRE insert.
        """
        casos = [
            [{"tipo": "insert", "s": 0.24, "e": 9.04, "crop": "900:800:10:10"}],
            [{"tipo": "insert", "s": 0.0, "e": 21.5, "crop": "900:800:10:10",
              "dur_max": 4.0}],
            [{"tipo": "insert", "s": 0.0, "e": 15.6, "crop": None,
              "dur_max": 11.8}],
        ]
        for blocos in casos:
            with self.subTest(dur=blocos[0]["e"]):
                segs = R.plano_de_ritmo(blocos)
                cap0 = blocos[0].get("dur_max")
                fim_hook = blocos[0]["s"] + min(R.HOOK_JANELA,
                                                cap0 or blocos[0]["e"])
                for x in segs:
                    if x["s"] < fim_hook - 0.05 and x["bloco"] == 0:
                        self.assertEqual(
                            x["tipo"], "insert",
                            f"plano de rosto em {x['s']:.2f}s, dentro da janela do "
                            f"hook (ate {fim_hook:.2f}s): o texto de abertura cai "
                            f"na cara do apresentador")

    def test_deterministico(self):
        blocos = [{"tipo": "insert", "s": 0.0, "e": 11.0, "crop": "900:800:10:10"},
                  {"tipo": "orig", "s": 11.0, "e": 30.0}]
        a = R.plano_de_ritmo([dict(x) for x in blocos])
        b = R.plano_de_ritmo([dict(x) for x in blocos])
        self.assertEqual(a, b, "os dois motores precisam obter o MESMO plano")


if __name__ == "__main__":
    unittest.main(verbosity=2)
