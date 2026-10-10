"""W4.B, C10 + C12: gate_mix. A cama respira nas pausas e some sob a fala; a entrega fica em -14 LUFS.

Régua (porte do verificador de mix da esteira de VSL, sem nome de cliente):
  - pausa real = a do envelope (audio.pausas_reais, a MESMA função que o mix usa para subir a cama);
  - das 8 maiores pausas, a cama (final menos voz sozinha, janela de 0,5 s no meio da pausa) tem que subir
    de +1,5 a +8,0 dB em pelo menos 75% delas;
  - sob a fala contínua, a cama sobe menos de +1,5 dB;
  - peça sem pausa real não cobra respiro, cobra só que a cama não suba sob a fala;
  - a trilha não "canta": a transcrição dela não passa de 60 caracteres;
  - o arquivo final fica em -14 LUFS (mais ou menos 1,2) e true peak até -1,5 dBTP.

Os testes numéricos montam a voz e o mix em numpy (sem ffmpeg, sem relógio, sem aleatório fora da
semente) e provam cada regra com o seu mutante. O mix de verdade (ffmpeg) fica nos `lento`.

No fim há a seção do `auditar_ad`, que passou a ler a aceleração do projeto e a medir o silêncio
na faixa de voz: a música sobe nas pausas e mascara o silêncio no arquivo final.
"""
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from audio import loudness, pausas_reais
from cinema import musica, sfx_plano
from gates import auditar_ad, gate_mix
from projeto import modelo, pastas
from tests.fixtures import sinteticos as SIN

SR = 16000
PAUSAS = [(2.0, 2.8), (6.0, 7.2), (9.5, 10.2), (13.0, 14.0)]
DUR = 16.0
BOA = loudness.Medicao(-14.1, -2.0, 6.0)
TRILHA = Path("trilha.mp3")                         # só o nome: o transcritor é injetado


def ruido(n, rms_db, rng):
    return rng.standard_normal(n) * 10 ** (rms_db / 20)


def voz_numerica(dur=DUR, pausas=PAUSAS, seed=1):
    """Fala de -18 dBFS RMS (seno de 220 Hz) com silêncio nas pausas, sobre um piso de -33 dBFS."""
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    fala = np.sqrt(2) * 10 ** (-18 / 20) * np.sin(2 * np.pi * 220 * t)
    for a, b in pausas:
        fala[int(a * SR):int(b * SR)] = 0.0
    return fala + ruido(n, -33, rng)


def mixar_numerico(voz, pausas_do_mix=PAUSAS, seed=2, **ducking):
    """voz + trilha (ruído a -20 dBFS, já nivelada) vezes o ganho que a expressão de volume descreve."""
    rng = np.random.default_rng(seed)
    n = len(voz)
    t = np.arange(n) / SR
    grade = np.arange(0.0, n / SR + 0.01, 0.005)
    ganho = np.interp(t, grade, [musica.ganho_no_instante(x, pausas_do_mix, **ducking) for x in grade])
    return voz + ruido(n, -20, rng) * ganho


def avaliar(final, voz, **kw):
    kw.setdefault("loudness_medido", BOA)
    kw.setdefault("trilha", TRILHA)
    kw.setdefault("transcritor", lambda p: [])
    return gate_mix.avaliar(gate_mix.Faixa(final, SR), gate_mix.Faixa(voz, SR), **kw)


def regras(r):
    return {f["regra"] for f in r.detalhes["falhas"]}


@pytest.fixture(scope="module")
def voz():
    return voz_numerica()


# --- o que passa ----------------------------------------------------------------------------------

def test_mix_bom_passa_e_mede_cada_pausa(voz):
    r = avaliar(mixar_numerico(voz), voz)
    assert r.ok, r.motivo
    m = r.detalhes["medido"]
    assert len(m["pausas"]) == 4 and m["pausas_ok"] == 4 and m["pausas_exigidas"] == 3
    assert all(1.5 <= p["delta_db"] <= 8.0 for p in m["pausas"]), m["pausas"]
    assert m["pior_sob_a_fala_db"] < 1.5 and m["pontos_de_fala"] >= 5
    assert m["lufs"] == -14.1 and m["true_peak_dbtp"] == -2.0
    assert r.detalhes["estado"] == "PASS" and r.detalhes["falhas"] == []


def test_o_resultado_traz_os_limiares_para_o_laudo(voz):
    r = avaliar(mixar_numerico(voz), voz)
    assert r.detalhes["limiar"] == {"lufs": [-15.2, -12.8], "true_peak_max_dbtp": -1.5,
                                    "pausa_delta_db": [1.5, 8.0], "pausas_minimo": 0.75, "sob_a_fala_max_db": 1.5,
                                    "trilha_caracteres_max": 60, "janela_s": 0.5, "piso_audivel_db": -40.0}
    assert gate_mix.NOME == "gate_mix"


# --- os mutantes de ducking -----------------------------------------------------------------------

def test_mutante_sem_ducking_reprova(voz):
    r = avaliar(mixar_numerico(voz, pausas_do_mix=[]), voz)               # cama parada em 0,055
    assert not r.ok and "cama_nas_pausas" in regras(r)
    assert "sob_a_fala" not in regras(r)
    assert r.detalhes["medido"]["pausas_ok"] == 0


def test_mutante_cama_alta_sob_a_fala_reprova(voz):
    r = avaliar(mixar_numerico(voz, cama_fala=0.9), voz)                  # pausas normais, fala com a cama a 0,9
    assert not r.ok and regras(r) == {"sob_a_fala"}
    assert r.detalhes["medido"]["pior_sob_a_fala_db"] >= 1.5
    assert "sob a fala" in r.motivo


def test_mutante_cama_alta_em_tudo_reprova_pelas_duas_regras(voz):
    r = avaliar(mixar_numerico(voz, cama_fala=0.9, cama_pausa=0.9), voz)
    assert regras(r) == {"cama_nas_pausas", "sob_a_fala"}


def test_pausa_em_que_a_cama_sobe_demais_nao_conta_como_ok(voz):
    r = avaliar(mixar_numerico(voz, cama_pausa=2.0), voz)                 # sobe +20 dB, bombeia
    assert not r.ok and "cama_nas_pausas" in regras(r)
    assert all(p["delta_db"] > 8.0 for p in r.detalhes["medido"]["pausas"])


def test_pelo_menos_75_por_cento_das_maiores_pausas_tem_que_respirar(voz):
    tres_de_quatro = avaliar(mixar_numerico(voz, pausas_do_mix=PAUSAS[:3]), voz)      # a 4ª fica sem subir
    assert tres_de_quatro.ok, tres_de_quatro.motivo
    assert tres_de_quatro.detalhes["medido"]["pausas_ok"] == 3
    duas_de_quatro = avaliar(mixar_numerico(voz, pausas_do_mix=PAUSAS[:2]), voz)
    assert not duas_de_quatro.ok and "cama_nas_pausas" in regras(duas_de_quatro)


def test_so_as_8_maiores_pausas_entram_na_conta():
    pausas = [(2.0 + 3.0 * k, 2.0 + 3.0 * k + 0.6 + 0.05 * k) for k in range(10)]
    voz = voz_numerica(dur=34.0, pausas=pausas)
    r = avaliar(mixar_numerico(voz, pausas_do_mix=pausas), voz)
    assert r.ok, r.motivo
    assert len(r.detalhes["medido"]["pausas"]) == 8
    duracoes = [p["e"] - p["s"] for p in r.detalhes["medido"]["pausas"]]
    assert duracoes == sorted(duracoes, reverse=True)


# --- peça sem pausa real --------------------------------------------------------------------------

def test_peca_sem_pausa_real_nao_cobra_respiro():
    voz = voz_numerica(pausas=())
    r = avaliar(mixar_numerico(voz, pausas_do_mix=[]), voz)
    assert r.ok, r.motivo
    assert r.detalhes["medido"]["sem_pausas"] is True and r.detalhes["medido"]["pausas"] == []


def test_peca_sem_pausa_real_reprova_se_a_cama_sobe_sob_a_fala():
    voz = voz_numerica(pausas=())
    r = avaliar(mixar_numerico(voz, pausas_do_mix=[], cama_fala=0.9), voz)
    assert not r.ok and regras(r) == {"sob_a_fala"}


# --- a automação gravada no timeline é a das pausas reais -----------------------------------------

def _ducking(pausas):
    return musica.ducking_para_timeline(pausas)


def test_ducking_do_timeline_igual_as_pausas_reais_passa(voz):
    r = avaliar(mixar_numerico(voz), voz, ducking=_ducking(PAUSAS))
    assert r.ok, r.motivo


def test_mutante_ducking_do_timeline_com_pausas_de_outra_peca_reprova(voz):
    r = avaliar(mixar_numerico(voz), voz, ducking=_ducking([(1.0, 1.8), (5.0, 5.8)]))
    assert not r.ok and "automacao_divergente" in regras(r)


def test_ducking_desligado_com_trilha_e_incoerente(voz):
    r = avaliar(mixar_numerico(voz), voz, ducking=musica.ducking_desligado("o aluno não usa trilha"))
    assert not r.ok and "ducking_incoerente" in regras(r)


def test_sem_trilha_nao_cobra_cama_e_so_confere_a_entrega(voz):
    r = gate_mix.avaliar(gate_mix.Faixa(voz, SR), gate_mix.Faixa(voz, SR), loudness_medido=BOA, trilha=None,
                         ducking=musica.ducking_desligado("o aluno não usa trilha"))
    assert r.ok, r.motivo
    assert r.detalhes["medido"]["pausas"] == [] and r.detalhes["medido"]["sem_trilha"] is True


def test_sem_trilha_mas_com_pausas_no_ducking_e_incoerente(voz):
    r = gate_mix.avaliar(gate_mix.Faixa(voz, SR), gate_mix.Faixa(voz, SR), loudness_medido=BOA, trilha=None,
                         ducking=_ducking(PAUSAS))
    assert not r.ok and "ducking_incoerente" in regras(r)


# --- a trilha não canta ---------------------------------------------------------------------------

def _palavras(*textos):
    return [{"text": t, "start": float(i), "end": float(i) + 0.5} for i, t in enumerate(textos)]


def test_mutante_trilha_que_canta_reprova(voz):
    cantada = _palavras(*["palavra"] * 10)                     # 10 x 7 letras + 9 espaços = 79 caracteres
    r = avaliar(mixar_numerico(voz), voz, transcritor=lambda p: cantada)
    assert not r.ok and regras(r) == {"trilha_canta"}
    assert r.detalhes["medido"]["caracteres_na_trilha"] == 79
    assert "60" in r.motivo and "79" in r.motivo


@pytest.mark.parametrize("n_palavras,esperado", [(8, 63), (7, 55)])
def test_o_limite_e_de_60_caracteres_transcritos(voz, n_palavras, esperado):
    palavras = _palavras(*["palavra"] * n_palavras)             # 8 -> 63 caracteres, 7 -> 55
    r = avaliar(mixar_numerico(voz), voz, transcritor=lambda p: palavras)
    assert r.detalhes["medido"]["caracteres_na_trilha"] == esperado
    assert r.ok is (esperado <= 60)


def test_exatamente_60_caracteres_passa_e_61_reprova(voz):
    sessenta = _palavras("a" * 60)
    sessenta_e_um = _palavras("a" * 61)
    assert avaliar(mixar_numerico(voz), voz, transcritor=lambda p: sessenta).ok
    assert not avaliar(mixar_numerico(voz), voz, transcritor=lambda p: sessenta_e_um).ok


def test_trilha_instrumental_sem_nada_transcrito_passa(voz):
    assert avaliar(mixar_numerico(voz), voz, transcritor=lambda p: []).ok


def test_sem_transcritor_na_maquina_e_insumo_invalido_nao_aprovacao(voz):
    from audio import transcrever

    def sem(_):
        raise transcrever.SemTranscritor("nenhum transcritor disponível")
    with pytest.raises(gate_mix.InsumoInvalido) as e:
        avaliar(mixar_numerico(voz), voz, transcritor=sem)
    assert "transcritor" in str(e.value)


# --- loudness: C12 --------------------------------------------------------------------------------

@pytest.mark.parametrize("lufs,tp,ok", [
    (-14.0, -1.5, True), (-15.2, -2.0, True), (-12.8, -2.0, True),       # bordas da faixa
    (-15.3, -2.0, False), (-12.7, -2.0, False), (-11.0, -3.0, False),     # fora por pouco e por muito
    (-14.0, -1.4, False), (-14.0, -0.5, False),                           # true peak acima do teto
])
def test_loudness_fica_em_menos_14_lufs_mais_ou_menos_1_2_e_true_peak_ate_menos_1_5(voz, lufs, tp, ok):
    r = avaliar(mixar_numerico(voz), voz, loudness_medido=loudness.Medicao(lufs, tp, 6.0))
    assert r.ok is ok, r.motivo
    if not ok:
        assert regras(r) <= {"loudness", "true_peak"}
        assert str(lufs).replace(".", ",") in r.motivo or str(lufs) in r.motivo or str(tp) in r.motivo


def test_loudness_vem_de_audio_loudness_medir_no_arquivo_final(tmp_path, voz):
    chamadas = []

    def espia(arq):
        chamadas.append(str(arq))
        return loudness.Medicao(-14.0, -2.0, 5.0)
    final = tmp_path / "final.wav"
    final.write_bytes(b"x")
    gate_mix.avaliar(gate_mix.Faixa(mixar_numerico(voz), SR), gate_mix.Faixa(voz, SR), trilha=TRILHA,
                     transcritor=lambda p: [], medir_loudness=espia, arquivo_final=final)
    assert chamadas == [str(final)]
    assert gate_mix.medir_loudness_padrao is loudness.medir


def test_sem_como_medir_o_loudness_e_insumo_invalido(voz):
    with pytest.raises(gate_mix.InsumoInvalido):
        gate_mix.avaliar(gate_mix.Faixa(mixar_numerico(voz), SR), gate_mix.Faixa(voz, SR), trilha=TRILHA,
                         transcritor=lambda p: [])


def test_o_motivo_junta_todas_as_falhas(voz):
    r = avaliar(mixar_numerico(voz, pausas_do_mix=[]), voz, loudness_medido=loudness.Medicao(-11.0, -0.5, 6.0),
                transcritor=lambda p: _palavras(*["palavra"] * 12))
    assert regras(r) == {"loudness", "true_peak", "cama_nas_pausas", "trilha_canta"}


# --- a medida em si -------------------------------------------------------------------------------

def test_faixa_mede_o_nivel_como_o_volumedetect():
    t = np.arange(SR * 2) / SR
    seno = np.sqrt(2) * 10 ** (-20 / 20) * np.sin(2 * np.pi * 440 * t)
    f = gate_mix.Faixa(seno, SR)
    assert f.nivel_db(0.5, 0.5) == pytest.approx(-20.0, abs=0.05)
    assert f.duracao_s == pytest.approx(2.0)
    assert f.nivel_db(1.9, 0.5) == pytest.approx(-20.0, abs=0.3)         # janela que passa do fim: mede o que há


def test_faixa_carrega_do_arquivo_e_o_envelope_bate_com_pausas_reais(tmp_path):
    arq = SIN.tom_com_pausas(tmp_path / "tom.wav", dur=14.0, pausas=((1.5, 2.1), (4.0, 4.8), (6.5, 7.7), (9.0, 11.0)))
    f = gate_mix.Faixa.carregar(arq)
    assert f.sr == gate_mix.SR_MEDIDA and f.duracao_s == pytest.approx(14.0, abs=0.05)
    achadas = pausas_reais.pausas_do_envelope(f.envelope_db(), 0.05)
    esperadas = pausas_reais.pausas(str(arq))
    assert len(achadas) == len(esperadas) == 4
    for (a1, b1), (a2, b2) in zip(achadas, esperadas):
        assert abs(a1 - a2) <= 0.051 and abs(b1 - b2) <= 0.051


# --- o mix de verdade (ffmpeg) --------------------------------------------------------------------

def _voz_wav(destino, **kw):
    from tests.audio.test_mix_final import voz_sintetica
    return voz_sintetica(destino, **kw)


@pytest.mark.lento
def test_mix_real_do_mixer_passa_no_gate_e_os_mutantes_reprovam(tmp_path):
    from audio import mix_final
    voz = _voz_wav(tmp_path / "voz.wav")
    trilha = SIN.ruido_rosa(tmp_path / "trilha.wav", dur=6.0, amplitude=0.5)
    voz_norm = loudness.normalizar(voz, tmp_path / "voz_norm.wav")
    biblioteca = sfx_plano.biblioteca(tmp_path / "som")

    def gerar(nome, **kw):
        saida = tmp_path / (nome + ".wav")
        mix_final.mixar(voz_norm, saida, trilha=trilha, efeitos=[(14.6, biblioteca["riser"])],
                        voz_ref=tmp_path / (nome + "_ref.wav"), **kw)
        return saida, tmp_path / (nome + "_ref.wav")

    bom, ref = gerar("bom")
    r = gate_mix.avaliar(bom, ref, trilha=trilha, transcritor=lambda p: [])
    assert r.ok, r.motivo
    assert r.detalhes["medido"]["pausas_ok"] == 4

    sem, ref_sem = gerar("sem_ducking", pausas=[])
    r = gate_mix.avaliar(sem, ref_sem, trilha=trilha, transcritor=lambda p: [])
    assert not r.ok and "cama_nas_pausas" in regras(r)

    # A régua de "sob a fala" (+1,5 dB sobre a voz sozinha) só vê a música a menos de uns 4 dB da voz. Com a voz
    # a -14 LUFS e a trilha a -20 dBFS, o mutante realista é a trilha no talo, sem ducking nenhum.
    alta, ref_alta = gerar("cama_alta", cama_fala=1.0, cama_pausa=1.0, nivel_trilha_dbfs=-14.0)
    r = gate_mix.avaliar(alta, ref_alta, trilha=trilha, transcritor=lambda p: [])
    assert not r.ok and "sob_a_fala" in regras(r)


@pytest.mark.lento
def test_cli_sai_0_com_o_mix_do_projeto_e_1_com_o_mutante(tmp_path, capsys):
    from audio import mix_final
    estado = tmp_path / "_local"
    (estado / "trilhas").mkdir(parents=True)
    SIN.ruido_rosa(estado / "trilhas" / "fundo.wav", dur=6.0, amplitude=0.5)
    pj = pastas.projeto("anuncio", estado).criar()
    modelo.escrever(pj.projeto_json, modelo.minimo("anuncio", "avatar", look="meu-look", trilha="fundo.wav"))
    voz = loudness.normalizar(_voz_wav(tmp_path / "voz.wav"), tmp_path / "voz_norm.wav")
    mix_final.mixar(voz, pj.final_9x16.with_suffix(".wav"), trilha=estado / "trilhas" / "fundo.wav",
                    voz_ref=mix_final.caminho_voz_ref(pj))
    args = ["anuncio", "--estado", str(estado), "--final", str(pj.final_9x16.with_suffix(".wav"))]
    assert gate_mix.main(args, transcritor=lambda p: []) == 0
    assert "PASSA" in capsys.readouterr().out
    mix_final.mixar(voz, pj.final_9x16.with_suffix(".wav"), trilha=estado / "trilhas" / "fundo.wav",
                    voz_ref=mix_final.caminho_voz_ref(pj), pausas=[])
    assert gate_mix.main(args, transcritor=lambda p: []) == 1
    assert "REPROVA" in capsys.readouterr().out


def test_cli_sai_2_sem_a_voz_de_referencia(tmp_path, capsys):
    estado = tmp_path / "_local"
    pj = pastas.projeto("anuncio", estado).criar()
    modelo.escrever(pj.projeto_json, modelo.minimo("anuncio", "gravado", sem_trilha="só voz neste teste"))
    pj.final_9x16.parent.mkdir(parents=True, exist_ok=True)
    pj.final_9x16.write_bytes(b"x")                      # o final existe; falta a voz pré-mix
    assert gate_mix.main(["anuncio", "--estado", str(estado)]) == 2
    assert "voz_pre_mix.wav" in capsys.readouterr().err


# --- auditar_ad: aceleração do projeto e silêncio na faixa de voz ---------------------------------

def _timing(tmp_path, a0=0.0):
    p = tmp_path / "timing.json"
    p.write_text(json.dumps({"a0": a0, "total": 40.0, "xf": 0.2, "avatar": "x.mp4", "letterings": [],
                             "inserts": [{"s": 10.5, "e": 14.0}, {"s": 20.0, "e": 24.0}]}), encoding="utf-8")
    return str(p)


def test_o_cravado_1_30_morreu_os_cortes_seguem_a_aceleracao_dada(tmp_path):
    timing = _timing(tmp_path, a0=0.5)
    assert auditar_ad.cortes_do_timing(timing, 1.35) == sorted({round((10.5 - 0.5) / 1.35, 2),
                                                                round((14.0 - 0.5) / 1.35, 2),
                                                                round((20.0 - 0.5) / 1.35, 2),
                                                                round((24.0 - 0.5) / 1.35, 2)})
    assert auditar_ad.cortes_do_timing(timing, 1.2) == sorted({round((10.5 - 0.5) / 1.2, 2),
                                                               round((14.0 - 0.5) / 1.2, 2),
                                                               round((20.0 - 0.5) / 1.2, 2),
                                                               round((24.0 - 0.5) / 1.2, 2)})
    assert auditar_ad.cortes_do_timing(timing, 1.35) != auditar_ad.cortes_do_timing(timing, 1.2)


def test_cortes_do_timing_nao_tem_mais_aceleracao_padrao(tmp_path):
    with pytest.raises(TypeError):
        auditar_ad.cortes_do_timing(_timing(tmp_path))


def test_sem_arquivo_de_timing_nao_ha_cortes_para_conferir(tmp_path):
    assert auditar_ad.cortes_do_timing(str(tmp_path / "nao-existe.json"), 1.35) is None


def _projeto(tmp_path, modo="avatar", aceleracao=None, slug="anuncio"):
    estado = tmp_path / "_local"
    pj = pastas.projeto(slug, estado).criar()
    dados = modelo.minimo(slug, modo, look="meu-look" if modo == "avatar" else None, sem_trilha="sem trilha no teste")
    if aceleracao is not None:
        dados["aceleracao"] = aceleracao
    modelo.escrever(pj.projeto_json, dados)
    return estado, pj


@pytest.mark.parametrize("modo,aceleracao,esperada", [
    ("avatar", None, 1.35),         # o padrão do avatar
    ("gravado", None, 1.2),         # o padrão do take real
    ("avatar", 1.2, 1.2),           # o aluno mudou
    ("gravado", 1.35, 1.35),
])
def test_aceleracao_vem_do_projeto(tmp_path, modo, aceleracao, esperada):
    estado, pj = _projeto(tmp_path, modo, aceleracao)
    assert auditar_ad.aceleracao_do_projeto("anuncio", estado) == esperada


def test_projeto_inexistente_nao_vira_aceleracao_chutada(tmp_path):
    with pytest.raises(FileNotFoundError):
        auditar_ad.aceleracao_do_projeto("fantasma", tmp_path / "_local")


def test_cortes_da_timeline_do_projeto_usam_a_aceleracao_da_propria_timeline():
    t = json.loads((Path(__file__).resolve().parents[2] / "contratos" / "exemplos" / "timeline.valido.json").read_text())
    inserts = [s for s in t["segmentos"] if s["tipo"] == "insert"]
    marcas = sorted({round((x - 0.0) / 1.35, 2) for s in inserts for x in (s["s"], s["e"]) if x > 0})
    assert auditar_ad.cortes_da_timeline(t) == [m for m in marcas if m > 0]


def test_limiar_do_silencio_sai_do_passo_que_ele_fiscaliza():
    import higienizar_audio
    assert auditar_ad.LIMIAR_SILENCIO_S == pytest.approx(higienizar_audio.PAUSA_MAX_TELA + 0.10)
    assert auditar_ad.LIMIAR_SILENCIO_S == pytest.approx(0.70)


def test_silencio_mede_a_faixa_de_voz_e_ignora_comeco_e_fim(tmp_path):
    # pausa de 0,9 s no meio (reprova), de 0,6 s (é a que o higienizador deixa: passa), 1,0 s no começo e
    # 1,2 s no fim (não são pausa entre falas)
    voz = SIN.tom_com_pausas(tmp_path / "voz.wav", dur=14.0,
                             pausas=((0.0, 1.0), (3.0, 3.9), (7.0, 7.6), (12.8, 14.0)))
    achados = auditar_ad.silencios_da_voz(str(voz))
    assert len(achados) == 1
    ini, dur = achados[0]
    assert ini == pytest.approx(3.0, abs=0.06) and dur == pytest.approx(0.9, abs=0.1)


def test_silencio_so_acima_do_limiar_derivado(tmp_path):
    voz = SIN.tom_com_pausas(tmp_path / "voz.wav", dur=10.0, pausas=((3.0, 3.69),))        # 0,69 s < 0,70
    assert auditar_ad.silencios_da_voz(str(voz)) == []
    voz2 = SIN.tom_com_pausas(tmp_path / "voz2.wav", dur=10.0, pausas=((3.0, 3.75),))      # 0,75 s > 0,70
    assert len(auditar_ad.silencios_da_voz(str(voz2))) == 1


def _mp4_de_teste(tmp_path, voz):
    destino = tmp_path / "ad.mp4"
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
                        "testsrc2=size=320x568:rate=25:duration=6", "-i", str(voz), "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-preset", "veryfast", "-c:a", "aac", "-shortest", str(destino)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-300:]
    return destino


def test_cli_le_a_aceleracao_do_projeto_e_o_silencio_da_voz(tmp_path, capsys):
    estado, pj = _projeto(tmp_path, "gravado")
    voz = SIN.tom_com_pausas(tmp_path / "voz.wav", dur=6.0, pausas=((2.0, 2.95),))
    ad = _mp4_de_teste(tmp_path, voz)
    rc = auditar_ad.main([str(ad), "--projeto", "anuncio", "--estado", str(estado), "--voz", str(voz),
                          "--timing", _timing(tmp_path)])
    saida = capsys.readouterr().out
    assert "aceleração 1.2" in saida and "projeto" in saida
    assert "[X] SILENCIO" in saida and rc == 1


def test_cli_sem_aceleracao_nem_projeto_sai_2_sem_chutar(tmp_path, capsys):
    voz = SIN.tom_com_pausas(tmp_path / "voz.wav", dur=6.0, pausas=())
    ad = _mp4_de_teste(tmp_path, voz)
    assert auditar_ad.main([str(ad)]) == 2
    assert "--projeto" in capsys.readouterr().err


def test_cli_aceita_a_aceleracao_explicita(tmp_path, capsys):
    voz = SIN.tom_com_pausas(tmp_path / "voz.wav", dur=6.0, pausas=())
    ad = _mp4_de_teste(tmp_path, voz)
    auditar_ad.main([str(ad), "--aceleracao", "1.35", "--voz", str(voz), "--timing", _timing(tmp_path)])
    assert "aceleração 1.35" in capsys.readouterr().out
