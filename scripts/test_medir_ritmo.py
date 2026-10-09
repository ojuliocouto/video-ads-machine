#!/usr/bin/env python3
"""Teste do medidor de ritmo. ESCRITO ANTES do medidor, e tem que falhar antes de passar.

O contrato é simples e vem de medição, não de gosto:

  - uma peça DINÂMICA (o que o dono mandou como referência: 19 a 28 cortes/min, planos de
    2 a 3 s) pontua dentro da faixa e o gate a aprova. Se o medidor não concordar com
    ela, o medidor está errado.
  - uma peça de HOOK (quase sem corte, como a referência de hook que um criador mandou,
    com 2,1 cortes/min) pontua BAIXO. Ela é a armadilha: é referência de hook, não de
    ritmo. Um medidor que a aprovasse como "dinâmica" estaria medindo outra coisa.
  - um anúncio LENTO reprova, mesmo quando o plano PEDE corte rápido: o corte só conta
    se o plano pediu E a imagem entregou.

COMO OS FIXTURES SAEM (W0.1). Antes, estes testes liam reels de terceiros em
`_local/dados/refs/` (que não vêm no repo, então 4 testes pulavam no clone limpo) e os
anúncios renderizados do dono (caminho absoluto de outra máquina). Agora cada teste gera,
em tmp, um vídeo sintético com os cortes conhecidos (`tests/fixtures/sinteticos.py`:
`video_por_planos`): padrões estáticos diferentes de um plano para o outro, então a
duração de cada plano e o instante de cada corte são os que o teste declarou. A
calibragem contra reels reais fica como prova de campo do dono, não como teste de CI.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
for _p in (str(RAIZ / "scripts"), str(RAIZ)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import medir_ritmo as MR  # noqa: E402
from tests.fixtures import sinteticos as SIN  # noqa: E402

# Referência dinâmica sintética: um plano longo de 13,2 s (a pior referência real segura
# 13,2 s e mesmo assim faz 27,8 cortes/min) seguido de 19 planos curtos.
DUR_REF_DINAMICA = (13.2,) + (1.7,) * 19   # múltiplos de 0,1 s: o fixture roda a 10 fps
# Peça de hook: dois planos de 10 s (1 corte em 20 s = 3 cortes/min).
DUR_HOOK = (10.0, 10.0)
# Peça em ritmo de referência: 9 cortes em 20 s = 27 cortes/min.
DUR_RITMO_BOM = (2.0,) * 10
# Anúncio lento: 3 planos de 10 s.
DUR_LENTO = (10.0, 10.0, 10.0)
ACCEL = 1.35


class TesteMedidor(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="vam_ritmo_"))
        cls.addClassCleanup(shutil.rmtree, cls.tmp, True)
        cls.ref_dinamica = SIN.video_por_planos(cls.tmp / "ref_dinamica.mp4", DUR_REF_DINAMICA)
        cls.ref_hook = SIN.video_por_planos(cls.tmp / "ref_hook.mp4", DUR_HOOK)
        cls.ritmo_bom = SIN.video_por_planos(cls.tmp / "ritmo_bom.mp4", DUR_RITMO_BOM)
        cls.lento = SIN.video_por_planos(cls.tmp / "lento.mp4", DUR_LENTO)

    def test_medidor_enxerga_exatamente_os_cortes_do_fixture(self):
        for nome, video, dur in (("ref dinâmica", self.ref_dinamica, DUR_REF_DINAMICA),
                                 ("ritmo bom", self.ritmo_bom, DUR_RITMO_BOM),
                                 ("hook", self.ref_hook, DUR_HOOK),
                                 ("lento", self.lento, DUR_LENTO)):
            with self.subTest(fixture=nome):
                m = MR.medir(video)
                self.assertEqual(m["cortes"], len(dur) - 1, f"{nome}: {m['instantes']}")
                for esperado, visto in zip(SIN.instantes_de_corte(dur), m["instantes"]):
                    self.assertAlmostEqual(esperado, visto, delta=0.26)  # amostragem a 8 fps: até 2 amostras

    # FAIXA RECALIBRADA (27/08/2026). Era 18 a 28, numeros do detector `scene` do ffmpeg.
    # O medidor passou a normalizar cada quadro (pra nao confundir brilho com conteudo) e
    # as MESMAS tres referencias passaram a dar 20,7 / 27,4 / 30,1 em vez de 18,9 / 27,8 /
    # 19,5. Trocar a regua obriga a reescrever o que "concordar com a referencia" quer
    # dizer, senao o teste passa a reprovar a propria referencia. O que NAO muda e o outro
    # lado da pinça: a ref de HOOK continua tendo que pontuar abaixo de 6.
    def test_referencias_pontuam_na_faixa_dinamica(self):
        for nome, video in (("ref dinâmica", self.ref_dinamica), ("ritmo bom", self.ritmo_bom)):
            with self.subTest(ref=nome):
                m = MR.medir(video)
                self.assertGreaterEqual(m["cortes_min"], 19.0,
                                        f"{nome} deu {m['cortes_min']:.1f}/min")
                self.assertLessEqual(m["cortes_min"], 32.0,
                                     f"{nome} deu {m['cortes_min']:.1f}/min")

    def test_gate_APROVA_as_referencias(self):
        """O teste que faltava, e que custou uma rodada.

        Eu tinha conferido que as refs pontuam alto em cortes/min, mas nunca que o
        VEREDITO as aprova. Nao aprovava: o teto de "maior plano acima de 6s" reprovava
        a ref1, que segura um plano de 13,2s e mesmo assim faz 27,8 cortes/min. Um gate
        mais duro que a referencia reprovaria uma peca indistinguivel dela.

        Regra que fica: todo gate se valida contra a REFERENCIA que ele imita, nao so
        contra o defeito que ele caça. A `ref dinâmica` sintética carrega o plano de 13,2 s.
        """
        for nome, video in (("ref dinâmica", self.ref_dinamica), ("ritmo bom", self.ritmo_bom)):
            with self.subTest(ref=nome):
                m = MR.medir(video)
                ok, motivos = MR.aprova(m)
                self.assertTrue(ok, f"o gate REPROVOU a referência {nome}: {motivos}. "
                                    f"Critério mais duro que a referência está errado.")

    def test_ref_de_hook_nao_e_ref_de_ritmo(self):
        m = MR.medir(self.ref_hook)
        self.assertLess(m["cortes_min"], 6.0,
                        "a ref de hook é quase sem corte; se ela pontuar alto, "
                        "o medidor está contando movimento e não corte")
        self.assertFalse(MR.aprova(m)[0], "uma peça de hook não pode passar como ritmo")

    # REMOVIDO em 27/08/2026: `test_ads_de_hoje_reprovam` media sem passar o plano,
    # entao caia na deteccao pura, que o gate nao usa mais e que infla o nosso material
    # (um ad que o dono achou lento pontuava 31,0/min por esse caminho por causa do churn
    # da legenda karaoke). `test_criterio_do_gate_tambem_reprova_ad_lento` cobre a mesma
    # calibragem pelo caminho que de fato roda.

    def test_criterio_do_gate_tambem_reprova_ad_lento(self):
        """O teste acima mede pelo caminho CEGO, que o gate nao usa mais.

        Desde 27/08/2026 o gate cruza plano e imagem (`cortes_confirmados`), porque a
        deteccao pura errava nos dois sentidos: contou fundo desfocado piscando como 10
        cortes e depois deixou de ver `orig -> cheio` num anuncio escuro. Trocar o
        criterio do gate sem trocar o do teste deixaria a calibragem cobrindo um caminho
        morto: o teste passaria verde enquanto o gate real virava carimbo.

        O anúncio lento sintético tem 3 planos de 10 s na imagem, mas o PLANO pede um
        corte a cada 2 s (footage 1x, acelerado em 1,35x). O cruzamento só conta o que a
        imagem entrega: 2 cortes. Tem que reprovar pelo critério NOVO.
        """
        passo_footage = 2.0 * ACCEL
        segs = [{"bloco": i, "tipo": "orig", "s": round(i * passo_footage, 3),
                 "e": round((i + 1) * passo_footage, 3)} for i in range(15)]
        plano = self.tmp / "lento_ritmo.json"
        plano.write_text(json.dumps({"total": 30.0 * ACCEL, "segs": segs}))
        m = MR.medir(self.lento, str(plano), ACCEL)
        self.assertEqual(m["cortes"], 2, f"o plano pediu 14 cortes, a imagem entrega 2: {m}")
        ok, motivos = MR.aprova(m)
        self.assertFalse(
            ok, f"o anúncio lento passou pelo critério do gate com {m['cortes_min']:.1f}/min: "
                f"o cruzamento plano x imagem afrouxou a calibragem")
        self.assertTrue(motivos)

    def test_plano_que_a_imagem_entrega_conta_inteiro(self):
        """Contraprova: quando plano e imagem concordam, todos os cortes contam."""
        passo = 2.0
        segs = [{"bloco": i, "tipo": "orig", "s": round(i * passo * ACCEL, 3),
                 "e": round((i + 1) * passo * ACCEL, 3)} for i in range(10)]
        plano = self.tmp / "bom_ritmo.json"
        plano.write_text(json.dumps({"total": 20.0 * ACCEL, "segs": segs}))
        m = MR.medir(self.ritmo_bom, str(plano), ACCEL)
        self.assertEqual(m["cortes"], 9, m)
        self.assertTrue(MR.aprova(m)[0], MR.aprova(m)[1])

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
        # segura, senao o gate reprova uma peca indistinguivel dela. A referencia
        # sintética segura 13,2 s, o mesmo da pior referência medida.
        maior_da_ref = MR.medir(self.ref_dinamica)["maior_plano"]
        self.assertGreater(maior_da_ref, 13.0, "o fixture perdeu o plano longo da referência")
        self.assertGreaterEqual(
            MR.MAX_PLANO_S, maior_da_ref,
            f"o teto de plano ({MR.MAX_PLANO_S}s) esta abaixo do maior plano que a "
            f"referencia segura ({maior_da_ref}s): o gate reprovaria a propria referencia")


if __name__ == "__main__":
    unittest.main(verbosity=2)
