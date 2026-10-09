"""Os 11 gates do gravado (W2.D): função devolve (ok, motivo); CLI sai 0, 1 ou 2.

  0  o gate passou
  1  defeito medido na peça
  2  insumo inválido (arquivo ausente, JSON vazio, ASR que falhou): não é veredito, é "não deu
     para medir". Nunca confundir com 1: um gate que não mediu não pode reprovar nem aprovar.

Cada cenário abaixo é um defeito real da leva que deu origem ao pipeline, reproduzido com
áudio e vídeo sintéticos de propriedades conhecidas.
"""
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from gravado import ar_morto_energia, legendar
from gravado.nucleo import energia
from gravado.veredito import InsumoInvalido
from tests.fixtures import sinteticos as fx
from tests.gravado import sintese as sx

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
GATES = ["gate_ar_morto", "gate_emendas", "gate_envelope", "gate_fala", "gate_legenda",
         "gate_offscript", "gate_redundancia", "gate_repeticao", "gate_retomada",
         "gate_sincronia", "gate_voz_distante"]


def _modulo(nome):
    return importlib.import_module("gravado." + nome)


def _script(nome, *args, cwd):
    return subprocess.run([sys.executable, str(SCRIPTS / "gravado" / (nome + ".py")), *args],
                          cwd=str(cwd), capture_output=True, text=True, env=dict(os.environ))


def w(texto, ini, fim):
    return {"text": texto, "start": ini, "end": fim}


# --- o protocolo comum ---------------------------------------------------------------------

@pytest.mark.parametrize("nome", GATES)
def test_cada_gate_tem_nome_funcao_de_projeto_e_main(nome):
    m = _modulo(nome)
    assert m.NOME == nome
    assert callable(m.main) and callable(m.verificar_projeto)
    assert m.__doc__ and len(m.__doc__) > 60


@pytest.mark.parametrize("nome", GATES)
def test_cli_rodada_como_script_sem_insumo_sai_com_2_e_diz_o_que_falta(tmp_path, nome):
    r = _script(nome, cwd=tmp_path)
    assert r.returncode == 2, r.stdout + r.stderr
    assert r.stderr.strip(), "o insumo inválido tem que dizer o que falta"
    assert "Traceback" not in r.stderr


def test_exit_1_so_significa_defeito_medido_erro_inesperado_sai_com_2(tmp_path, monkeypatch, capsys):
    from gravado import veredito
    import argparse
    p = argparse.ArgumentParser()

    def estoura(args):
        raise KeyError("bug nosso")

    assert veredito.cli("gate_x", p, estoura, []) == 2
    assert "gate_x" in capsys.readouterr().err


def test_veredito_cli_traduz_a_tupla_em_codigo_de_saida(capsys):
    from gravado import veredito
    import argparse
    p = argparse.ArgumentParser()
    assert veredito.cli("g", p, lambda a: (True, "tudo certo"), []) == 0
    assert "tudo certo" in capsys.readouterr().out
    assert veredito.cli("g", p, lambda a: (False, "defeito aqui"), []) == 1
    assert "defeito aqui" in capsys.readouterr().out

    def sem_insumo(a):
        raise InsumoInvalido("faltou o arquivo")
    assert veredito.cli("g", p, sem_insumo, []) == 2
    assert "faltou o arquivo" in capsys.readouterr().err


# --- gate_ar_morto -------------------------------------------------------------------------

def _cortado_pelo_cortador(tmp_path, pausa=1.5):
    """Áudio com duas pausas longas, passado pelo cortador e gravado: o que sobra é o que o
    próprio cortador produz."""
    fonte = sx.audio_por_blocos(tmp_path / "fonte.wav", [(1.0, -12.0), (pausa, None), (1.0, -12.0),
                                                         (pausa, None), (1.0, -12.0)])
    amostras = energia.amostras(fonte).astype(np.float64) / 32768.0
    pedacos = [amostras[int(round(a * sx.SR)):int(round(b * sx.SR))]
               for a, b in ar_morto_energia.manter(fonte)]
    return sx.escrever_wav(tmp_path / "cortado.wav", np.concatenate(pedacos))


def test_ar_morto_teto_e_respiro_mais_duas_margens_mais_um_quadro():
    m = _modulo("gate_ar_morto")
    base = ar_morto_energia.RESPIRO + 2 * ar_morto_energia.MARGEM
    assert m.teto_s() == pytest.approx(base + 1.0 / 30)
    assert m.teto_s(fps=25) == pytest.approx(base + 0.04)


def test_ar_morto_sem_falso_positivo_nas_pausas_que_o_proprio_cortador_produz(tmp_path):
    m = _modulo("gate_ar_morto")
    ok, motivo = m.verificar(_cortado_pelo_cortador(tmp_path))
    assert ok, motivo


def test_ar_morto_acusa_pausa_de_0_9_s(tmp_path):
    m = _modulo("gate_ar_morto")
    arq = sx.audio_por_blocos(tmp_path / "a.wav", [(1.0, -12.0), (0.9, None), (1.0, -12.0)])
    ok, motivo = m.verificar(arq)
    assert not ok
    assert "0.9" in motivo and "1.0" in motivo       # o tamanho da pausa e onde ela começa
    assert "divida" in motivo.lower()                # e o que fazer: uma frase por trecho


def test_ar_morto_converte_a_pausa_do_arquivo_para_tempo_de_fonte(tmp_path):
    m = _modulo("gate_ar_morto")
    # pausa de 0,35 s no arquivo acelerado 1,2x = 0,42 s na fonte: é a que o cortador deixa
    ok35 = sx.audio_por_blocos(tmp_path / "p35.wav", [(1.0, -12.0), (0.35, None), (1.0, -12.0)])
    assert m.verificar(ok35, accel=1.2)[0]
    # 0,50 s no arquivo = 0,60 s na fonte: passa do teto de 0,4533 s
    p50 = sx.audio_por_blocos(tmp_path / "p50.wav", [(1.0, -12.0), (0.5, None), (1.0, -12.0)])
    assert not m.verificar(p50, accel=1.2)[0]
    assert m.verificar(p50, accel=1.0)[0] is False   # 0,50 s > 0,4533 s também sem aceleração
    p44 = sx.audio_por_blocos(tmp_path / "p44.wav", [(1.0, -12.0), (0.44, None), (1.0, -12.0)])
    assert m.verificar(p44, accel=1.0)[0]


def test_ar_morto_cli_sai_0_1_e_2(tmp_path, capsys):
    m = _modulo("gate_ar_morto")
    bom = _cortado_pelo_cortador(tmp_path)
    ruim = sx.audio_por_blocos(tmp_path / "ruim.wav", [(1.0, -12.0), (0.9, None), (1.0, -12.0)])
    assert m.main([str(bom)]) == 0
    assert m.main([str(ruim)]) == 1
    assert m.main([str(tmp_path / "nao_existe.wav")]) == 2
    # as pausas do cortador (0,42 s) num arquivo que JÁ estaria acelerado 1,2x seriam 0,50 s na fonte
    assert m.main([str(bom), "--accel", "1.0"]) == 0
    assert m.main([str(bom), "--accel", "1.2"]) == 1


# --- gate_emendas --------------------------------------------------------------------------

def test_emenda_no_meio_de_uma_palavra_reprova():
    m = _modulo("gate_emendas")
    palavras = [w("então", 0.0, 0.4), w("vamos", 0.5, 1.3), w("começar", 1.4, 2.0)]
    ok, motivo = m.verificar([0.9], palavras)
    assert not ok
    assert "vamos" in motivo and "0.90" in motivo


def test_emenda_na_borda_de_palavra_passa():
    m = _modulo("gate_emendas")
    palavras = [w("então", 0.0, 0.4), w("vamos", 0.5, 1.3), w("começar", 1.4, 2.0)]
    assert m.verificar([1.35], palavras)[0]
    assert m.verificar([0.45], palavras)[0]


def test_palavra_repetida_colada_na_emenda_reprova():
    m = _modulo("gate_emendas")
    palavras = [w("então", 0.0, 0.4), w("vamos", 0.5, 0.9), w("vamos", 0.95, 1.4), w("lá", 1.5, 1.8)]
    ok, motivo = m.verificar([0.92], palavras)
    assert not ok and "vamos" in motivo and "repet" in motivo


def test_emendas_sem_palavra_nenhuma_e_insumo_invalido():
    m = _modulo("gate_emendas")
    with pytest.raises(InsumoInvalido):
        m.verificar([1.0], [])


def test_emendas_sem_emenda_passa_sem_consultar_nada():
    m = _modulo("gate_emendas")
    assert m.verificar([], [w("oi", 0.0, 0.3)])[0]


# --- gate_envelope -------------------------------------------------------------------------

BRUTO = [(1.5, -12.0), (0.8, None), (1.7, -12.0), (0.5, None), (1.5, -12.0)]       # 6,0 s


def test_envelope_limpo_igual_ao_bruto_passa(tmp_path):
    m = _modulo("gate_envelope")
    bruto = sx.audio_por_blocos(tmp_path / "b.wav", BRUTO)
    limpo = sx.audio_por_blocos(tmp_path / "l.wav", BRUTO)
    ok, motivo = m.verificar(bruto, limpo)
    assert ok, motivo


def test_envelope_reprova_limpo_3_s_mais_curto_na_cauda(tmp_path):
    m = _modulo("gate_envelope")
    bruto = sx.audio_por_blocos(tmp_path / "b.wav", BRUTO)
    # as 3,0 s iniciais do bruto: o isolador devolveu o arquivo cortado na cauda
    limpo = sx.audio_por_blocos(tmp_path / "l.wav", [(1.5, -12.0), (0.8, None), (0.7, -12.0)])
    ok, motivo = m.verificar(bruto, limpo)
    assert not ok
    assert "mais curto" in motivo


def test_envelope_reprova_fala_comida_no_meio(tmp_path):
    m = _modulo("gate_envelope")
    bruto = sx.audio_por_blocos(tmp_path / "b.wav", BRUTO)
    limpo = sx.audio_por_blocos(tmp_path / "l.wav", [(1.5, -12.0), (0.8, None), (1.7, None),
                                                     (0.5, None), (1.5, -12.0)])
    ok, motivo = m.verificar(bruto, limpo)
    assert not ok and "buraco" in motivo


def test_envelope_ruido_do_bruto_que_o_isolador_limpou_nao_e_perda(tmp_path):
    m = _modulo("gate_envelope")
    sinal = sx.sinal_por_blocos(BRUTO)
    ruido = np.random.RandomState(7).randn(len(sinal))
    ruido *= (10 ** (-45.0 / 20.0)) / np.sqrt(np.mean(ruido ** 2))
    bruto = sx.escrever_wav(tmp_path / "b.wav", sinal + ruido)
    limpo = sx.para_mp3(sx.audio_por_blocos(tmp_path / "l.wav", BRUTO), tmp_path / "l.mp3")
    ok, motivo = m.verificar(bruto, limpo)
    assert ok, motivo


def test_envelope_cli_sai_0_1_e_2(tmp_path):
    m = _modulo("gate_envelope")
    bruto = sx.audio_por_blocos(tmp_path / "b.wav", BRUTO)
    curto = sx.audio_por_blocos(tmp_path / "c.wav", [(1.5, -12.0), (0.8, None), (0.7, -12.0)])
    assert m.main([str(bruto), str(bruto)]) == 0
    assert m.main([str(bruto), str(curto)]) == 1
    assert m.main([str(bruto), str(tmp_path / "nao_existe.mp3")]) == 2


# --- gate_fala (bruto x limpo) -------------------------------------------------------------

def _texto(n):
    return " ".join("palavra%d" % i for i in range(n))


def test_fala_igual_passa():
    m = _modulo("gate_fala")
    ok, motivo = m.verificar(_texto(100), _texto(100))
    assert ok, motivo


def test_fala_comida_pelo_isolador_reprova():
    m = _modulo("gate_fala")
    limpo = " ".join("palavra%d" % i for i in range(100) if i % 10 != 3)          # 10 sumidas
    ok, motivo = m.verificar(_texto(100), limpo)
    assert not ok and "palavra3" in motivo and "10" in motivo


def test_fala_tolera_3_por_cento_ou_2_palavras_o_que_for_maior():
    m = _modulo("gate_fala")
    tres = " ".join("palavra%d" % i for i in range(100) if i not in (5, 50, 90))
    assert m.verificar(_texto(100), tres)[0]
    quatro = " ".join("palavra%d" % i for i in range(100) if i not in (5, 50, 90, 95))
    assert not m.verificar(_texto(100), quatro)[0]
    dez = _texto(10)
    assert m.verificar(dez, " ".join(dez.split()[2:]))[0]                        # 2 de 10 passa


def test_fala_grafias_que_o_asr_alterna_nao_contam_como_perda():
    m = _modulo("gate_fala")
    bruto = "eu vou para casa porque voce esta cansado " + _texto(40)
    limpo = "eu vou pra casa porque ce ta cansado " + _texto(40)
    ok, motivo = m.verificar(bruto, limpo)
    assert ok, motivo


def test_fala_variante_do_glossario_equivale_a_grafia():
    m = _modulo("gate_fala")
    glossario = {"versao": 1, "termos": [{"grafia": "Fluxa", "variantes": ["Flucha"]}]}
    bruto = "abra a Flucha agora mesmo e depois a Flucha de novo " + _texto(10)
    limpo = "abra a Fluxa agora mesmo e depois a Fluxa de novo " + _texto(10)
    assert m.verificar(bruto, limpo, glossario)[0]


def test_fala_bruto_sem_fala_transcrita_e_insumo_invalido():
    m = _modulo("gate_fala")
    with pytest.raises(InsumoInvalido):
        m.verificar("", "alguma coisa")


# --- gate_legenda --------------------------------------------------------------------------

def _ass(eventos, tmp_path, nome="l.ass"):
    """eventos: [(ini, fim, texto)] -> arquivo ASS que o gate lê."""
    linhas = [legendar.cabecalho()]
    for ini, fim, texto in eventos:
        linhas.append("Dialogue: 0,%s,%s,Base,,0,0,0,,%s" % (legendar.tempo(ini), legendar.tempo(fim), texto))
    arq = tmp_path / nome
    arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return arq


def test_legenda_continua_passa(tmp_path):
    m = _modulo("gate_legenda")
    eventos = [(i * 1.0, i * 1.0 + 1.0, "linha %d da legenda" % i) for i in range(10)]
    ok, motivo = m.verificar(_ass(eventos, tmp_path), 10.0)
    assert ok, motivo


def test_legenda_com_vao_de_mais_de_2_5_s_reprova(tmp_path):
    m = _modulo("gate_legenda")
    eventos = [(0.0, 2.0, "começa bem"), (8.0, 10.0, "e volta tarde")]
    ok, motivo = m.verificar(_ass(eventos, tmp_path), 10.0)
    assert not ok and "vão" in motivo


def test_legenda_pica_mais_de_12_por_cento_sem_texto_reprova(tmp_path):
    m = _modulo("gate_legenda")
    # vãos de 0,4 s (nenhum passa de 2,5 s) que somam 20% da peça
    eventos = [(i * 2.0, i * 2.0 + 1.6, "linha %d" % i) for i in range(10)]
    ok, motivo = m.verificar(_ass(eventos, tmp_path), 20.0)
    assert not ok and "%" in motivo


def test_legenda_com_linha_acima_do_maximo_reprova(tmp_path):
    m = _modulo("gate_legenda")
    longa = "x" * (legendar.MAX_CHARS + 6)
    eventos = [(0.0, 5.0, longa)]
    ok, motivo = m.verificar(_ass(eventos, tmp_path), 5.0)
    assert not ok and str(legendar.MAX_CHARS) in motivo


def test_legenda_tags_de_cor_nao_contam_como_texto(tmp_path):
    m = _modulo("gate_legenda")
    com_tag = r"{\c&H4E7DE8&}" + "x" * legendar.MAX_CHARS + r"{\c&HFFFFFF&}"
    ok, motivo = m.verificar(_ass([(0.0, 5.0, com_tag)], tmp_path), 5.0)
    assert ok, motivo


def test_legenda_gerada_pelo_gerador_passa_no_gate(tmp_path):
    m = _modulo("gate_legenda")
    palavras = [w("palavra%d" % i, i * 0.4, i * 0.4 + 0.35) for i in range(25)]
    destino = tmp_path / "g.ass"
    legendar.gerar(palavras, destino)
    ok, motivo = m.verificar(destino, 10.0)
    assert ok, motivo


def test_legenda_cli_sai_0_1_e_2(tmp_path):
    m = _modulo("gate_legenda")
    bom = _ass([(i * 1.0, i * 1.0 + 1.0, "linha %d" % i) for i in range(10)], tmp_path, "bom.ass")
    ruim = _ass([(0.0, 1.0, "só uma")], tmp_path, "ruim.ass")
    assert m.main([str(bom), "--duracao", "10"]) == 0
    assert m.main([str(ruim), "--duracao", "10"]) == 1
    assert m.main([str(tmp_path / "nao_existe.ass"), "--duracao", "10"]) == 2


# --- gate_offscript e gate_repeticao (falas_entregues.json) --------------------------------

def _falas(tmp_path, conteudo):
    arq = tmp_path / "falas_entregues.json"
    arq.write_text(conteudo if isinstance(conteudo, str) else json.dumps(conteudo, ensure_ascii=False),
                   encoding="utf-8")
    return arq


def test_offscript_acha_fala_de_direcao_e_palavrao():
    m = _modulo("gate_offscript")
    ok, motivo = m.verificar({"A1_normal": "então a gente automatiza isso. tá bom? deixa eu ver a planilha"})
    assert not ok and "tá bom" in motivo and "deixa eu" in motivo and "A1_normal" in motivo
    assert not m.verificar({"A2_normal": "putz, esqueci o que ia dizer"})[0]


def test_offscript_casa_palavra_inteira_nao_pedaco():
    m = _modulo("gate_offscript")
    assert m.verificar({"A1": "a operação roda sozinha, cortamos o custo"})[0]
    assert not m.verificar({"A1": "ele disse corta e a cena acabou"})[0]


def test_offscript_peca_limpa_passa():
    m = _modulo("gate_offscript")
    ok, motivo = m.verificar({"A1": "você perde três horas por dia nisso", "A2": "com uma automação isso roda sozinho"})
    assert ok, motivo


def test_repeticao_ngrama_de_5_palavras_perto_reprova():
    m = _modulo("gate_repeticao")
    texto = "eu vou te mostrar como funciona isso aqui e depois eu vou te mostrar como funciona de verdade"
    ok, motivo = m.verificar({"A1_normal": texto})
    assert not ok and "eu vou te mostrar como" in motivo and "A1_normal" in motivo


def test_repeticao_longe_demais_nao_e_costura():
    m = _modulo("gate_repeticao")
    meio = " ".join("meio%d" % i for i in range(60))
    texto = "eu vou te mostrar como " + meio + " eu vou te mostrar como"
    assert m.verificar({"A1": texto})[0]


def test_repeticao_peca_sem_repeticao_passa_e_conta_as_pecas():
    m = _modulo("gate_repeticao")
    ok, motivo = m.verificar({"A1": "uma frase sem repetir nada aqui", "A2": "outra frase bem diferente da primeira"})
    assert ok and "2" in motivo


@pytest.mark.parametrize("nome", ["gate_repeticao", "gate_offscript"])
def test_texto_cli_sai_2_diante_de_json_vazio_ou_falha_do_asr(tmp_path, nome):
    m = _modulo(nome)
    for ruim in ({}, [], "", "{quebrado", {"A1_normal": "FALHA: HTTP 429"},
                 {"A1_normal": "texto bom", "A2_normal": "FALHA"}, {"A1_normal": ""}):
        assert m.main([str(_falas(tmp_path, ruim))]) == 2, ruim
    assert m.main([str(tmp_path / "nao_existe.json")]) == 2


def test_texto_cli_sai_1_com_defeito_e_0_sem(tmp_path):
    rep, off = _modulo("gate_repeticao"), _modulo("gate_offscript")
    limpo = _falas(tmp_path, {"A1": "uma frase limpa e curta"})
    assert rep.main([str(limpo)]) == 0 and off.main([str(limpo)]) == 0
    sujo = _falas(tmp_path, {"A1": "eu vou te mostrar como funciona isso e eu vou te mostrar como funciona. tá bom?"})
    assert rep.main([str(sujo)]) == 1 and off.main([str(sujo)]) == 1


# --- gate_redundancia ----------------------------------------------------------------------

def test_termos_portadores_ignoram_funcionais_e_palavras_curtas():
    m = _modulo("gate_redundancia")
    t = m.termos("Porque você vai automatizar a agenda quando o cliente chegar, VOCÊS também")
    assert {"automatizar", "agenda", "cliente", "chegar"} <= t
    assert "porque" not in t and "quando" not in t and "voces" not in t and "voce" not in t
    assert "vai" not in t


def test_dois_termos_em_comum_dos_dois_lados_da_emenda_reprova():
    m = _modulo("gate_redundancia")
    ok, motivo = m.verificar([("A1_normal", 12.4, "agora a planilha de vendas e a agenda", "com a planilha e a agenda eu ganho tempo")])
    assert not ok and "planilha" in motivo and "agenda" in motivo and "12.40" in motivo


def test_um_termo_em_comum_so_nao_e_redundancia():
    m = _modulo("gate_redundancia")
    ok, motivo = m.verificar([("A1_normal", 5.0, "a planilha de vendas", "a planilha ficou pronta ontem")])
    assert ok, motivo


def test_redundancia_le_seis_segundos_de_cada_lado_da_emenda():
    m = _modulo("gate_redundancia")
    leitor = sx.LeitorFalso(textos={(4.0, 10.0): "texto antes da emenda", (10.0, 16.0): "texto depois da emenda"})
    pares = m.ler_lados("peca.mp4", [10.0], leitor)
    assert pares == [(10.0, "texto antes da emenda", "texto depois da emenda")]
    assert leitor.chamadas == [("peca.mp4", 4.0, 10.0), ("peca.mp4", 10.0, 16.0)]


def test_redundancia_no_comeco_da_peca_nao_pede_tempo_negativo():
    m = _modulo("gate_redundancia")
    leitor = sx.LeitorFalso(textos="x")
    m.ler_lados("peca.mp4", [2.0], leitor)
    assert leitor.chamadas[0] == ("peca.mp4", 0.0, 2.0)


# --- gate_retomada -------------------------------------------------------------------------

def test_retomada_por_similaridade_acha_a_frase_dita_duas_vezes():
    m = _modulo("gate_retomada")
    subs = [m.SubBloco(0.0, 1.5, "e sabe o que aconteceu?", True),
            m.SubBloco(1.8, 3.3, "e sabe o que aconteceu", False),
            m.SubBloco(3.6, 5.0, "depois eu fui embora de vez", True)]
    retomadas, fragmentos = m.achar(subs)
    assert [(i, j) for i, j, _ in retomadas] == [(0, 1)]
    assert fragmentos == []


def test_retomada_com_palavra_trocada_tambem_e_achada():
    m = _modulo("gate_retomada")
    subs = [m.SubBloco(0.0, 2.0, "vou te dar um exemplo agora", True),
            m.SubBloco(2.2, 4.2, "vou te dar o exemplo agora", True)]
    assert len(m.achar(subs)[0]) == 1


def test_retomada_olha_tambem_o_vizinho_de_distancia_2():
    m = _modulo("gate_retomada")
    subs = [m.SubBloco(0.0, 2.0, "a primeira vez que eu falei isso", True),
            m.SubBloco(2.1, 2.9, "hum", False),
            m.SubBloco(3.1, 5.1, "a primeira vez que eu falei isso", True)]
    assert [(i, j) for i, j, _ in m.achar(subs)[0]] == [(0, 2)]


def test_frases_diferentes_nao_sao_retomada():
    m = _modulo("gate_retomada")
    subs = [m.SubBloco(0.0, 2.0, "você perde três horas por dia", True),
            m.SubBloco(2.2, 4.2, "com uma automação isso roda sozinho", True)]
    assert m.achar(subs) == ([], [])


def test_fragmento_curto_na_borda_do_trecho_e_acusado_no_meio_nao():
    m = _modulo("gate_retomada")
    subs = [m.SubBloco(0.0, 0.4, "e vo", True),                       # sobra da frase descartada
            m.SubBloco(0.6, 3.0, "você vai ver como isso funciona", False),
            m.SubBloco(3.2, 3.6, "né", False),                        # interjeição no meio: normal
            m.SubBloco(3.8, 6.0, "e é simples de verdade", True)]
    _, fragmentos = m.achar(subs)
    assert fragmentos == [0]


def test_trecho_de_um_sub_bloco_so_nunca_e_fragmento(tmp_path):
    m = _modulo("gate_retomada")
    audio = sx.audio_por_blocos(tmp_path / "t.wav", [(0.5, None), (0.5, -12.0), (0.5, None)])
    subs = m.coletar(lambda take: audio, [("T1", 0.0, 1.5)], sx.LeitorFalso(textos="vambora"))
    assert len(subs) == 1 and subs[0].na_borda is False
    assert m.achar(subs) == ([], [])


def test_retomada_de_0_32_s_no_audio_e_achada_pelo_gate_de_ponta_a_ponta(tmp_path):
    m = _modulo("gate_retomada")
    audio = sx.audio_por_blocos(tmp_path / "t.wav", [(0.8, -12.0), (0.32, None), (0.8, -12.0),
                                                     (1.0, None), (0.8, -12.0)])
    leitor = sx.LeitorFalso(textos=["e sabe o que aconteceu?", "e sabe o que aconteceu?",
                                    "uma outra frase bem diferente"])
    subs = m.coletar(lambda take: audio, [("T1", 0.0, 3.72)], leitor)
    assert len(subs) == 3
    ok, motivo = m.verificar_versoes({"A1_normal": subs})
    assert not ok and "A1_normal" in motivo and "RETOMADA" in motivo


def test_retomada_versao_limpa_passa(tmp_path):
    m = _modulo("gate_retomada")
    audio = sx.audio_por_blocos(tmp_path / "t.wav", [(0.8, -12.0), (0.5, None), (0.8, -12.0)])
    leitor = sx.LeitorFalso(textos=["primeira frase inteira aqui", "depois disso eu fui para casa"])
    subs = m.coletar(lambda take: audio, [("T1", 0.0, 2.1)], leitor)
    ok, motivo = m.verificar_versoes({"A1_normal": subs})
    assert ok, motivo


# --- gate_sincronia ------------------------------------------------------------------------

def _re_encode_com_faixa(origem, destino, altura_pct=0.62):
    """Simula a legenda queimada: um retângulo branco dentro da faixa da legenda."""
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", str(origem), "-vf",
                        "drawbox=x=0:y=ih*%s:w=iw:h=ih*0.08:color=white:t=fill" % altura_pct,
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
                        "-crf", "20", "-c:a", "copy", str(destino)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return destino


def test_sincronia_legendada_do_mesmo_corte_passa(tmp_path):
    m = _modulo("gate_sincronia")
    fonte = fx.testsrc_com_audio(tmp_path / "fonte.mp4", dur=3.0)
    legendada = _re_encode_com_faixa(fonte, tmp_path / "legendada.mp4")
    ok, motivo = m.verificar(legendada, fonte)
    assert ok, motivo


def test_sincronia_reprova_peca_trocada_com_a_mesma_duracao(tmp_path):
    m = _modulo("gate_sincronia")
    fonte = fx.testsrc_com_audio(tmp_path / "fonte.mp4", dur=3.0)
    outra = fx.video_cores(tmp_path / "outra.mp4", cores=("red", "green", "blue"), dur_cada=1.0,
                           tamanho="320x568", fps=25)
    ok, motivo = m.verificar(outra, fonte)
    assert not ok and "quadros" in motivo
    # a duração é a mesma: o gate antigo (só duração) aprovaria
    assert abs(m.duracao(outra) - m.duracao(fonte)) < 0.25


def test_sincronia_reprova_cores_chapadas_diferentes_com_hash_igual(tmp_path):
    m = _modulo("gate_sincronia")
    vermelho = fx.video_cores(tmp_path / "v.mp4", cores=("red",), dur_cada=3.0, tamanho="320x568", fps=25)
    verde = fx.video_cores(tmp_path / "g.mp4", cores=("green",), dur_cada=3.0, tamanho="320x568", fps=25)
    assert not m.verificar(verde, vermelho)[0]


def test_sincronia_reprova_corte_de_duracao_diferente(tmp_path):
    m = _modulo("gate_sincronia")
    fonte = fx.testsrc_com_audio(tmp_path / "fonte.mp4", dur=3.0)
    velha = fx.testsrc_com_audio(tmp_path / "velha.mp4", dur=2.0)
    ok, motivo = m.verificar(velha, fonte)
    assert not ok and "duração" in motivo


def test_sincronia_cli_sai_0_1_e_2(tmp_path):
    m = _modulo("gate_sincronia")
    fonte = fx.testsrc_com_audio(tmp_path / "fonte.mp4", dur=3.0)
    legendada = _re_encode_com_faixa(fonte, tmp_path / "legendada.mp4")
    velha = fx.testsrc_com_audio(tmp_path / "velha.mp4", dur=2.0)
    assert m.main([str(legendada), str(fonte)]) == 0
    assert m.main([str(velha), str(fonte)]) == 1
    assert m.main([str(legendada), str(tmp_path / "nao_existe.mp4")]) == 2


# --- gate_voz_distante ---------------------------------------------------------------------

LONGOS = [(0.0, 2.0, -10.0), (3.0, 5.0, -10.0), (6.0, 8.0, -10.0)]


def test_6_db_abaixo_da_mediana_e_voz_distante_5_db_nao_e():
    m = _modulo("gate_voz_distante")
    ref, suspeitos = m.classificar(LONGOS + [(9.0, 9.3, -16.0)])
    assert ref == -10.0
    assert suspeitos == [(9.0, 9.3, -16.0)]
    _, suspeitos = m.classificar(LONGOS + [(9.0, 9.3, -15.0)])
    assert suspeitos == []


def test_mediana_so_conta_blocos_longos():
    m = _modulo("gate_voz_distante")
    # o bloco curto e baixo não puxa a referência para baixo
    ref, _ = m.classificar(LONGOS + [(9.0, 9.2, -30.0), (10.0, 10.2, -30.0), (11.0, 11.2, -30.0)])
    assert ref == -10.0


def test_sem_bloco_longo_a_referencia_cai_no_padrao():
    m = _modulo("gate_voz_distante")
    ref, _ = m.classificar([(0.0, 0.3, -12.0)])
    assert ref == -10.0


def test_voz_distante_dentro_do_trecho_reprova_fora_dele_passa():
    m = _modulo("gate_voz_distante")
    blocos = {"T1": LONGOS + [(9.0, 9.3, -20.0)]}
    ok, motivo = m.verificar([("A1", "T1", 8.5, 10.0)], blocos)
    assert not ok and "A1" in motivo and "T1" in motivo and "9.0" in motivo
    assert m.verificar([("A1", "T1", 0.0, 8.0)], blocos)[0]


def test_voz_distante_no_audio_sintetico(tmp_path):
    m = _modulo("gate_voz_distante")
    arq = sx.audio_por_blocos(tmp_path / "t.wav", [
        (1.0, -10.0), (0.3, None), (1.0, -10.0), (0.3, None), (1.0, -10.0), (0.3, None),
        (0.4, -20.0), (0.3, None), (1.0, -10.0)])
    blocos = {"T1": m.blocos_do_take(arq)}
    assert not m.verificar([("A1", "T1", 3.5, 5.5)], blocos)[0]       # pega a voz de fora
    assert m.verificar([("A1", "T1", 0.0, 3.0)], blocos)[0]


def test_voz_distante_take_sem_bloco_nenhum_e_insumo_invalido(tmp_path):
    m = _modulo("gate_voz_distante")
    mudo = sx.audio_por_blocos(tmp_path / "m.wav", [(2.0, None)])
    with pytest.raises(InsumoInvalido):
        m.verificar([("A1", "T1", 0.0, 1.0)], {"T1": m.blocos_do_take(mudo)})
