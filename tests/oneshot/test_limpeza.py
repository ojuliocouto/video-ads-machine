"""One-shot em take real de celular (ensaio de 20/10/2026, IMG_3751, 54,7 s, sala barulhenta).

Três defeitos, cada um com o seu teste:

  1. PAUSA: o piso de ruído da sala ficava acima do piso fixo de silêncio e o one-shot saía sem cortar nada
     (`1 segmentos, 54.69s de fala`). O piso agora é o ruído MEDIDO do take mais 6 dB, e o preâmbulo antes
     da primeira palavra sai pela transcrição.
  2. RETOMADA: a transcrição do take inteiro deduplica a falsa partida. Cada sub-bloco é lido sozinho e a
     primeira tentativa sai, com o texto no plano.
  3. FALA DE QUEM DIRIGE e OUTRA VOZ: pergunta de direção e voz bem abaixo da do apresentador saem, com
     aviso no plano. O gate de fala preservada compara o final com o bruto menos o que saiu de propósito.
"""
import subprocess
from pathlib import Path

import numpy as np
import pytest

import ar_morto
from oneshot import limpeza, montar
from projeto import novo, pastas
from tests.gravado import sintese as sx

ROSTO = (100, 40, 60, 60)


def _p(texto, a, b):
    return {"text": texto, "start": a, "end": b}


def _bloco(ini, fim, texto, pico=-1.0, palavras=None):
    """Sub-bloco já lido: as palavras se espalham por igual no bloco quando não vêm dadas."""
    if palavras is None:
        ws = texto.split()
        passo = (fim - ini) / max(1, len(ws))
        palavras = [_p(w, round(ini + i * passo, 3), round(ini + (i + 1) * passo, 3)) for i, w in enumerate(ws)]
    return {"ini": ini, "fim": fim, "pico": pico, "palavras": palavras, "texto": texto}


# --- 1. piso de ruído medido -------------------------------------------------------------------------

def test_take_limpo_fica_com_o_piso_fixo():
    db = [-60.0] * 400 + [0.0] * 400
    assert ar_morto.piso_adaptativo(db) == ar_morto.PADRAO["piso_db"]


def test_sala_barulhenta_sobe_o_piso_para_6_db_acima_do_ruido_medido():
    rng = np.random.default_rng(3)
    db = list(-25.6 + rng.normal(0, 0.5, 600)) + [0.0] * 600     # metade do take é sala a -25,6 dB do pico
    piso = ar_morto.piso_adaptativo(db)
    assert -20.5 <= piso <= -19.0
    params = ar_morto.params_do_piso(db)
    assert params["piso_db"] == piso and params["db_estalo"] > piso


def test_pausa_em_sala_barulhenta_e_cortada_pelo_piso_medido():
    """Ruído a -25 dB do pico: com o piso fixo de -32 dB nada era silêncio e a pausa de 2 s ficava inteira."""
    jan = 0.02
    rng = np.random.default_rng(5)
    db = np.concatenate([np.zeros(50), -25.0 + rng.normal(0, 0.8, 100), np.zeros(75)])   # 1 s, 2 s, 1,5 s
    palavras = [_p("um", 0.05, 0.5), _p("dois", 0.5, 0.95), _p("três", 3.05, 3.5), _p("quatro", 3.5, 4.4)]
    toks = ar_morto.margens_de_palavra([(p["start"], p["end"], p["text"]) for p in palavras], 0.3, 0.15)
    blocos = ar_morto.blocos_de_fala(toks)
    fixo = ar_morto.planejar_cortes(blocos, db.tolist(), jan, 4.5)
    assert fixo == []                                             # o defeito: o piso fixo não acha a pausa
    segs = montar.cortes_do_take(palavras, db.tolist(), 4.5, margens=(0.3, 0.15))
    assert len(segs) == 2
    mantido = sum(b - a for a, b in segs)
    assert 2.6 <= mantido <= 3.2
    assert segs[0][1] >= 0.95 and segs[1][0] <= 3.0 - 0.06        # a energia da fala começa em 3,0 s: nada dela sai


def test_preambulo_sem_palavra_sai_pela_transcricao_mesmo_com_barulho():
    """O preâmbulo (quem pega o celular, ruído de mão) não é silêncio: a energia não acha, a transcrição acha."""
    db = [-5.0] * 20 + [-25.0] * 130 + [0.0] * 100               # mão no celular, sala, e só então a fala
    palavras = [_p("quanto", 3.0, 3.6), _p("custa", 3.6, 4.9)]
    segs = montar.cortes_do_take(palavras, db, 5.0, margens=(0.3, 0.15))
    assert segs[0][0] == pytest.approx(3.0 - 0.3 - ar_morto.PADRAO["pre_roll_intro"], abs=0.02)
    assert segs[-1][1] == pytest.approx(5.0, abs=0.02)


# --- 2 e 3. sub-blocos, retomada, direção e outra voz -----------------------------------------------

def test_subblocos_saem_da_energia_acima_do_limiar_e_juntam_pausa_curta():
    db = [0.0] * 20 + [-30.0] * 5 + [0.0] * 20 + [-30.0] * 30 + [0.0] * 20
    assert limpeza.subblocos(db, 0.02, -20.0) == [(0.0, 0.9), (1.5, 1.9)]


def test_falsa_partida_sai_e_o_recomeco_fica():
    """O caso do take real: "Tá. Cara..." / "Com cem reais você já começa..." / "Cara, com 100 reais você já
    consegue criar". A tentativa começa no "Cara" de dentro do primeiro sub-bloco, e o "Tá." fica."""
    blocos = [_bloco(11.06, 13.48, "Para ter um time de A na sua operação"),
              _bloco(13.76, 15.08, "Tá. Cara...", palavras=[_p("Tá.", 13.80, 14.30), _p("Cara...", 14.80, 15.05)]),
              _bloco(15.62, 17.24, "Com cem reais você já começa..."),
              _bloco(17.64, 21.76, "Cara, com 100 reais você já consegue criar ali o seu primeiro funcionário IA.")]
    brutas = limpeza.classificar(blocos)
    assert [(r["motivo"], r["ini"], r["fim"]) for r in brutas] == [("retomada", 14.80, 17.64)]
    ret, avisos = limpeza.retiradas(blocos, [])
    assert len(ret) == 1
    assert 14.30 <= ret[0]["ini"] <= 14.80 and 17.40 <= ret[0]["fim"] < 17.64
    assert "Com cem reais" in ret[0]["texto"] and "14." in avisos[0] and "confira" in avisos[0]


def test_frase_que_repete_palavras_mas_nao_e_tentativa_fica():
    blocos = [_bloco(17.6, 21.7, "Cara, com 100 reais você já consegue criar ali o seu primeiro funcionário IA."),
              _bloco(22.0, 24.7, "Por exemplo, um editor de vídeo, um social media,"),
              _bloco(25.0, 27.9, "É o mínimo que você precisa e com 100 reais você consegue."),
              _bloco(28.4, 28.8, "E olha só,")]
    assert limpeza.classificar(blocos) == []


def test_pergunta_de_quem_dirige_e_voz_baixa_ao_fundo_saem_com_a_retomada_numa_retirada_so():
    blocos = [_bloco(25.06, 27.96, "É o mínimo que você precisa e com 100 reais você consegue."),
              _bloco(28.40, 28.84, "E olha só,"),
              _bloco(29.26, 29.46, "Transcrição em português do Brasil.", pico=-15.0),
              _bloco(31.36, 32.18, "Depois o que é que ele faz?"),
              _bloco(32.88, 34.06, "Você precisa saber a maneira certa", pico=-14.0),
              _bloco(36.70, 38.24, "O que você precisa saber na..."),
              _bloco(38.92, 43.00, "O que você precisa saber, na verdade, é a maneira certa de como criar isso daí.")]
    motivos = [r["motivo"] for r in limpeza.classificar(blocos)]
    assert motivos == ["voz baixa", "direção", "voz baixa", "retomada"]
    ret, avisos = limpeza.retiradas(blocos, [])
    assert len(ret) == 1 and len(avisos) == 1
    assert ret[0]["ini"] == pytest.approx(28.84 + limpeza.FOLGA_S, abs=0.01)
    assert ret[0]["fim"] == pytest.approx(38.92 - limpeza.FOLGA_S, abs=0.01)
    assert set(ret[0]["motivo"].split(" + ")) == {"voz baixa", "direção", "retomada"}


def test_direcao_casa_expressao_inteira_e_nao_pedaco_do_roteiro():
    assert limpeza.eh_direcao("Depois, o que é que você quer falar?")
    assert limpeza.eh_direcao("o que é que eu falo agora")
    assert not limpeza.eh_direcao("O que você precisa saber, na verdade, é a maneira certa")
    assert not limpeza.eh_direcao("eu te mostro exatamente como fazer isso na Operação")


def test_a_retirada_nunca_passa_por_cima_de_palavra_que_fica():
    blocos = [_bloco(43.36, 44.78, "Para que ele funcione da melhor forma.",
                     palavras=[_p("Para", 43.4, 43.6), _p("forma.", 44.3, 45.22)]),
              _bloco(45.36, 47.08, "E olha que interessante, eu te mostro..."),
              _bloco(48.10, 54.56, "E olha que interessante, eu te mostro exatamente como fazer isso.")]
    ret, _ = limpeza.retiradas(blocos, [])
    assert len(ret) == 1 and ret[0]["ini"] >= 45.22 and ret[0]["fim"] <= 48.10 - limpeza.FOLGA_S + 1e-6


def test_palavras_fora_das_retiradas_sao_o_que_o_final_tem_que_ter():
    palavras = [_p("tá", 12.8, 14.2), _p("cara", 14.8, 15.5), _p("consegue", 16.7, 19.4), _p("criar", 19.4, 19.9)]
    fora = limpeza.palavras_fora(palavras, [{"ini": 14.68, "fim": 17.52}])
    assert [p["text"] for p in fora] == ["tá", "consegue", "criar"]


# --- integração com o plano e o gate de fala ----------------------------------------------------------

def _take(destino, trechos):
    destino = Path(destino)
    wav = sx.audio_por_blocos(destino.with_name(destino.stem + "-fonte.wav"), trechos)
    dur = sum(d for d, _ in trechos)
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
                        "color=c=0x808080:s=320x180:r=25:d=%s" % dur, "-i", str(wav), "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-shortest",
                        str(destino)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return destino


class _Leitor(object):
    def __init__(self, palavras, texto_final=None):
        self.palavras_ = palavras
        self.texto_final = texto_final

    def palavras(self, audio, exigir_borda=False):
        return [dict(p) for p in self.palavras_]

    def palavras_do_trecho(self, audio, ini, fim):
        return [dict(p) for p in self.palavras_ if ini - 0.1 <= (p["start"] + p["end"]) / 2.0 <= fim + 0.1]

    def texto_da_peca(self, arquivo):
        if self.texto_final is not None and "final" in Path(arquivo).name:
            return self.texto_final
        return " ".join(p["text"] for p in self.palavras_)


def _projeto(estado):
    novo.criar("take", "oneshot", sem_trilha="take único: a voz real segue sem trilha", estado=estado)
    return pastas.projeto("take", estado)


def test_plano_de_take_em_sala_barulhenta_corta_a_pausa(estado_vazio, tmp_path):
    """Sala a -18 dB da fala: com o piso fixo o plano saía com 1 segmento só."""
    pj = _projeto(estado_vazio)
    take = _take(tmp_path / "take.mp4", [(1.0, -12.0), (2.0, -30.0), (1.5, -12.0)])
    palavras = [_p("um", 0.05, 0.5), _p("dois", 0.5, 0.95), _p("três", 3.05, 3.5), _p("quatro", 3.5, 4.4)]
    plano = montar.planejar(pj, take, _Leitor(palavras), detector=lambda img: [ROSTO], medidor_luz=lambda t, j: 111.0)
    assert len(plano["segmentos"]) == 2
    assert 2.6 <= plano["dur_cortada"] <= 3.2
    assert plano["piso_db"] > ar_morto.PADRAO["piso_db"] and plano["retiradas"] == []


def test_plano_tira_a_falsa_partida_e_o_gate_confere_o_bruto_menos_ela(estado_vazio, tmp_path, monkeypatch):
    pj = _projeto(estado_vazio)
    take = _take(tmp_path / "take.mp4", [(1.2, -12.0), (0.8, -30.0), (2.0, -12.0), (0.5, -30.0)])
    palavras = [_p("eu", 0.05, 0.3), _p("te", 0.3, 0.5), _p("mostro...", 0.5, 1.1),
                _p("eu", 2.05, 2.3), _p("te", 2.3, 2.5), _p("mostro", 2.5, 2.8), _p("tudo", 2.8, 3.1),
                _p("agora", 3.1, 3.4), _p("mesmo", 3.4, 3.7), _p("aqui", 3.7, 3.95)]
    plano = montar.planejar(pj, take, _Leitor(palavras), detector=lambda img: [ROSTO], medidor_luz=lambda t, j: 111.0)
    assert [r["motivo"] for r in plano["retiradas"]] == ["retomada"]
    assert plano["segmentos"][0][0] >= 1.1                       # a primeira tentativa não entra no final
    assert any("retirado" in a and "confira" in a for a in plano["avisos"])
    monkeypatch.setattr(montar.auditar, "tecnico", lambda f: {"ok": True, "motivo": "", "resolucao": "1080x1920",
                                                              "duracao": 2.0, "lufs": -14.0, "true_peak": -2.0})
    monkeypatch.setattr(montar.gate_ar_morto, "verificar", lambda f, accel: (True, "sem pausa"))
    pj.entrega_dir.mkdir(parents=True, exist_ok=True)
    pj.final_9x16.write_bytes(b"x")
    bom = dict((n, (ok, m)) for n, ok, m in montar.conferir(pj, plano, _Leitor(palavras, "eu te mostro tudo agora mesmo aqui"),
                                                             pj.final_9x16))
    assert bom["fala_preservada"][0] is True and "retirado" in bom["fala_preservada"][1]
    ruim = dict((n, ok) for n, ok, _ in montar.conferir(pj, plano, _Leitor(palavras, "eu"), pj.final_9x16))
    assert ruim["fala_preservada"] is False                       # fora da retirada, palavra sumida reprova


def test_pergunta_respondida_por_outra_voz_e_direcao_mesmo_lida_com_outras_palavras():
    """A Mistral leu a pergunta do take real como "Depois quer que eu faça?" e a Groq como "Depois o que é que ele
    faz?". O que não muda é a estrutura: pergunta, e logo depois a voz baixa de quem dirige respondendo."""
    blocos = [_bloco(28.40, 28.84, "E olha só,"),
              _bloco(31.36, 32.18, "Depois, sabe o que eu faço?"),
              _bloco(32.88, 33.36, "serviços.", pico=-14.0),
              _bloco(38.92, 43.00, "O que você precisa saber, na verdade, é a maneira certa de como criar isso daí.")]
    assert [r["motivo"] for r in limpeza.classificar(blocos)] == ["direção", "voz baixa"]


def test_pergunta_do_roteiro_seguida_da_fala_dele_ou_de_ruido_fica():
    gancho = _bloco(9.34, 13.48, "Quanto custa por mês para ter um time de IA na sua operação?")
    assert limpeza.classificar([gancho, _bloco(13.76, 14.30, "Tá.")]) == []
    ruido = _bloco(13.9, 14.2, "Transcrição em português do Brasil.", pico=-15.0)
    assert [r["motivo"] for r in limpeza.classificar([gancho, ruido, _bloco(14.8, 17.0, "Cara, com 100 reais")])] \
        == ["voz baixa"]


def test_corte_vazio_do_rabo_nao_vira_segmento_fantasma():
    """No take real o respiro do rabo passava do fim do arquivo: (54,76, 54,69) virava um segmento de 0,07 s."""
    assert ar_morto.segmentos_manter([(10.0, 54.69), (54.76, 54.69)], 54.76) == [(0.0, 10.0), (54.69, 54.76)]
    assert ar_morto.segmentos_manter([(10.0, 54.69), (54.76, 54.69)], 54.69) == [(0.0, 10.0)]
