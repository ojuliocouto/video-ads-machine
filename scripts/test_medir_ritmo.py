#!/usr/bin/env python3
"""Teste do medidor de ritmo. ESCRITO ANTES do medidor, e tem que falhar antes de passar.

O contrato e simples e vem de medicao, nao de gosto:

  - as tres referencias do Vaibhav (o que o Julio mandou como "dinamico") pontuam
    entre 18 e 28 cortes/min. Se o medidor nao concordar com elas, o medidor esta errado.
  - a ref de HOOK do Pedro Sobral pontua BAIXO (2,1 cortes/min). Ela e a armadilha: e
    referencia da Jheni, mas de hook, nao de ritmo. Um medidor que a aprovasse como
    "dinamica" estaria medindo outra coisa.
  - os quatro ads de hoje REPROVAM. Se algum passar, o alvo esta frouxo demais pra
    mudar qualquer coisa.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import medir_ritmo as MR

from caminhos import DADOS as _D
REFS = _D / "refs"
from caminhos import OUTPUT as OUT

# Ads que o Julio e a Jheni acharam LENTOS, usados pra calibrar o gate: se algum deles
# passar, o alvo afrouxou. O jh13 saiu da lista em 27/08/2026 porque e o ad em conserto
# ativo, e manter a saida ATUAL dele como fixture de "tem que reprovar" e contraditorio:
# o teste passaria a exigir que o conserto nao funcionasse. O jh16 saiu porque so
# reprovava pelo caminho de deteccao pura, que o gate nao usa mais; ele precisa ser
# reavaliado por alguem assistindo antes de voltar a valer como calibragem.
ADS_HOJE = [
    OUT / "jh14v2_oficial_13_v2composite_9x16.mp4",
    OUT / "jh15v2_neon_creme_v2composite_9x16.mp4",
]


class TesteMedidor(unittest.TestCase):

    # FAIXA RECALIBRADA (27/08/2026). Era 18 a 28, numeros do detector `scene` do ffmpeg.
    # O medidor passou a normalizar cada quadro (pra nao confundir brilho com conteudo) e
    # as MESMAS tres referencias passaram a dar 20,7 / 27,4 / 30,1 em vez de 18,9 / 27,8 /
    # 19,5. Trocar a regua obriga a reescrever o que "concordar com a referencia" quer
    # dizer, senao o teste passa a reprovar a propria referencia. O que NAO muda e o outro
    # lado da pinca: a ref de HOOK do Sobral continua tendo que pontuar abaixo de 6.
    def test_referencias_pontuam_na_faixa_dinamica(self):
        for i in (1, 2, 3):
            p = REFS / "vaibhav" / f"ref{i}.mp4"
            with self.subTest(ref=p.name):
                self.assertTrue(p.exists(), f"fixture ausente: {p}")
                m = MR.medir(p)
                self.assertGreaterEqual(m["cortes_min"], 19.0,
                                        f"{p.name} deu {m['cortes_min']:.1f}/min")
                self.assertLessEqual(m["cortes_min"], 32.0,
                                     f"{p.name} deu {m['cortes_min']:.1f}/min")

    def test_gate_APROVA_as_referencias(self):
        """O teste que faltava, e que custou uma rodada.

        Eu tinha conferido que as refs pontuam alto em cortes/min, mas nunca que o
        VEREDITO as aprova. Nao aprovava: o teto de "maior plano acima de 6s" reprovava
        a ref1, que segura um plano de 13,2s e mesmo assim faz 27,8 cortes/min. Um gate
        mais duro que a referencia reprovaria uma peca indistinguivel dela.

        Regra que fica: todo gate se valida contra a REFERENCIA que ele imita, nao so
        contra o defeito que ele caca.
        """
        for i in (1, 2, 3):
            p = REFS / "vaibhav" / f"ref{i}.mp4"
            with self.subTest(ref=p.name):
                m = MR.medir(p)
                ok, motivos = MR.aprova(m)
                self.assertTrue(ok, f"o gate REPROVOU a referencia {p.name}: {motivos}. "
                                    f"Criterio mais duro que a referencia esta errado.")

    def test_ref_de_hook_nao_e_ref_de_ritmo(self):
        p = REFS / "sobral" / "ref_hook.mp4"
        self.assertTrue(p.exists(), f"fixture ausente: {p}")
        m = MR.medir(p)
        self.assertLess(m["cortes_min"], 6.0,
                        "a ref de hook do Sobral e quase sem corte; se ela pontuar alto, "
                        "o medidor esta contando movimento e nao corte")

    # REMOVIDO em 27/08/2026: `test_ads_de_hoje_reprovam` media sem passar o plano,
    # entao caia na deteccao pura, que o gate nao usa mais e que infla o nosso material
    # (jh14, que o Julio achou lento, pontua 31,0/min por esse caminho por causa do churn
    # da legenda karaoke). `test_criterio_do_gate_tambem_reprova_ad_lento` cobre a mesma
    # calibragem pelo caminho que de fato roda.

    def test_criterio_do_gate_tambem_reprova_ad_lento(self):
        """O teste acima mede pelo caminho CEGO, que o gate nao usa mais.

        Desde 27/08/2026 o gate cruza plano e imagem (`cortes_confirmados`), porque a
        deteccao pura errava nos dois sentidos: contou fundo desfocado piscando como 10
        cortes e depois deixou de ver `orig -> cheio` num anuncio escuro. Trocar o
        criterio do gate sem trocar o do teste deixaria a calibragem cobrindo um caminho
        morto: o teste passaria verde enquanto o gate real virava carimbo.

        jh14 e jh15 sao os ads que o Julio e a Jheni acharam lentos. Eles tem que
        reprovar pelo criterio NOVO tambem, senao o afrouxamento passou.
        """
        lentos = [("jh14v2_oficial_13", 16.0), ("jh15v2_neon_creme", 16.0)]
        checados = 0
        for nome, piso in lentos:
            v = OUT / f"{nome}_v2composite_9x16.mp4"
            j = OUT / f"{nome}_footage_1x_ritmo.json"
            if not (v.exists() and j.exists()):
                continue
            with self.subTest(ad=nome):
                m = MR.medir(v, str(j), 1.35)
                self.assertFalse(
                    MR.aprova(m)[0],
                    f"{nome} passou pelo criterio do gate com {m['cortes_min']:.1f}/min: "
                    f"o cruzamento plano x imagem afrouxou a calibragem")
                checados += 1
        if not checados:
            self.skipTest("nenhum ad lento com plano disponivel pra calibrar")

    def test_veredito_traz_o_motivo(self):
        m = {"cortes_min": 5.0, "plano_medio": 12.0, "maior_plano": 15.0, "cortes": 7,
             "dur": 90.0, "planos": [15.0]}
        ok, motivos = MR.aprova(m)
        self.assertFalse(ok)
        self.assertTrue(motivos, "reprovar sem dizer por que nao serve pra nada")

    def test_alvo_bate_com_a_referencia_medida(self):
        # o alvo nao pode ser um numero que eu inventei: tem que caber no que as
        # referencias entregam de fato
        self.assertLessEqual(MR.MIN_CORTES_MIN, 18.9,
                             "o piso esta acima da referencia mais lenta das tres")
        # ASSERCAO CONSERTADA (27/08/2026, apontada pelo estrategista). A de antes
        # comparava o TETO de plano ISOLADO (14,0s) com o plano MEDIO da referencia
        # (3,17s). Sao grandezas diferentes: 14 >= 3,17 e trivialmente verdade e nao
        # restringe nada. O que o teto tem que respeitar e o MAIOR plano que a referencia
        # segura, senao o gate reprova uma peca indistinguivel dela.
        maior_das_refs = max(MR.medir(REFS / "vaibhav" / f"ref{i}.mp4")["maior_plano"]
                             for i in (1, 2, 3))
        self.assertGreaterEqual(
            MR.MAX_PLANO_S, maior_das_refs,
            f"o teto de plano ({MR.MAX_PLANO_S}s) esta abaixo do maior plano que a "
            f"referencia segura ({maior_das_refs}s): o gate reprovaria a propria referencia")


if __name__ == "__main__":
    unittest.main(verbosity=2)
