"""W3.C: gate_entrada. Confere a voz e o avatar ANTES de gastar um build.

Quatro conferências, cada uma com o número de onde veio:
  - respiro: energia acima de -34 dB dentro de uma pausa de 0,62 s ou mais reprova;
  - ritmo achatado: voz de mais de 30 s com menos pausas acima de 0,60 s do que 1 a cada 15 s (mínimo 2) reprova;
  - fala preservada: trecho do bruto que sobra com menos de 0,60 das letras no limpo reprova;
  - duração: avatar e voz limpa diferindo mais de 1,0 s reprova.

O áudio é sintético (tons com pausas exatas, tests/fixtures/sinteticos.py) e o ASR é simulado.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from gates import gate_entrada as G
from projeto import modelo, pastas, status
from tests.fixtures import sinteticos as fx

RAIZ = Path(__file__).resolve().parents[2]
SLUG = "anuncio"
TEXTO = "vamos fazer uma campanha agora e depois revisar tudo com calma"


# --- mídia sintética ---------------------------------------------------------------------------------

def _ffmpeg(args):
    fx.exigir_ffmpeg()
    p = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin"] + [str(a) for a in args],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-300:]


def tom(destino_wav, dur, pausas, respiro_rms_db=None):
    """Seno de RMS -21 dB com silêncio exato nas `pausas`; se `respiro_rms_db`, ruído rosa com
    esse RMS aproximado no FIM de cada pausa (o respiro que o Avatar V lipsynca)."""
    cond = "+".join("between(t,%s,%s)" % p for p in pausas) or "0"
    voz = "sine=frequency=220:sample_rate=48000:duration=%s,volume=enable='%s':volume=0" % (dur, cond)
    if respiro_rms_db is None:
        _ffmpeg(["-f", "lavfi", "-i", voz, "-ac", "1", "-c:a", "pcm_s16le", destino_wav])
        return destino_wav
    # o respiro é a inspiração antes da próxima frase: a pausa começa limpa (0,25 s) e o ruído
    # entra depois. O anoisesrc com amplitude 0.5 mede RMS ~ -20 dB; o volume leva ao alvo.
    cond_ruido = "+".join("between(t,%s,%s)" % (a + 0.25, b) for a, b in pausas)
    ruido = ("anoisesrc=color=pink:amplitude=0.5:seed=7:sample_rate=48000:duration=%s,volume=%sdB,"
             "volume=enable='not(%s)':volume=0" % (dur, respiro_rms_db + 20, cond_ruido))
    _ffmpeg(["-f", "lavfi", "-i", voz, "-f", "lavfi", "-i", ruido, "-filter_complex",
             "[0][1]amix=inputs=2:duration=first:normalize=0", "-ac", "1", "-c:a", "pcm_s16le", destino_wav])
    return destino_wav


def para_mp3(wav, mp3):
    _ffmpeg(["-i", wav, "-c:a", "libmp3lame", "-b:a", "128k", mp3])
    return mp3


def montar(tmp_path, dur=6.0, pausas=((1.5, 2.2), (4.0, 4.9)), respiro_rms_db=None, modo="gravado",
           avatar_dur=None, com_bruto=True):
    estado = tmp_path / "_local"
    pj = pastas.projeto(SLUG, estado).criar()
    extra = {"look": "meu-look"} if modo == "avatar" else {}
    modelo.escrever(pj.projeto_json, modelo.minimo(SLUG, modo, sem_trilha="sem trilha no teste", **extra))
    wav = tom(tmp_path / "limpo.wav", dur, pausas, respiro_rms_db)
    para_mp3(wav, pj.voz_limpo)
    if com_bruto:
        shutil.copy(str(wav), str(pj.voz_dir / "bruto.wav"))
    if modo == "avatar" and avatar_dur is not None:
        fx.testsrc_com_audio(pj.avatar_mp4, dur=avatar_dur)
    return estado, pj


def asr_com(bruto=TEXTO, limpo=TEXTO):
    """ASR simulado: uma transcrição para o bruto e outra para o limpo (pelo nome do arquivo)."""
    def asr(caminho):
        texto = bruto if Path(caminho).stem == "bruto" else limpo
        return [{"text": w, "start": i * 0.4, "end": i * 0.4 + 0.3} for i, w in enumerate(texto.split())]
    return asr


def regras(r):
    return sorted(f["regra"] for f in r.detalhes["falhas"])


# --- o caso certo --------------------------------------------------------------------------------------

def test_entrada_limpa_passa(tmp_path):
    estado, pj = montar(tmp_path)
    r = G.rodar(pj, asr=asr_com())
    assert r.ok, r.motivo
    assert r.detalhes["estado"] == "PASS"
    assert r.detalhes["falhas"] == []
    assert r.detalhes["pausas_acima_de_0_60"] == 2
    assert 5.9 < r.detalhes["duracao_limpo_s"] < 6.3


def test_avatar_com_a_mesma_duracao_do_limpo_passa(tmp_path):
    estado, pj = montar(tmp_path, modo="avatar", avatar_dur=6.0)
    r = G.rodar(pj, asr=asr_com())
    assert r.ok, r.motivo
    assert abs(r.detalhes["diferenca_duracao_s"]) < 0.5


# --- respiro -------------------------------------------------------------------------------------------

def test_respiro_acima_de_menos_34_db_em_pausa_longa_reprova(tmp_path):
    estado, pj = montar(tmp_path, respiro_rms_db=-30)
    r = G.rodar(pj, asr=asr_com())
    assert not r.ok
    assert "respiro" in regras(r)
    assert "respiro audível" in r.motivo
    assert len(r.detalhes["respiros"]) == 2


def test_respiro_abaixo_de_menos_34_db_nao_reprova(tmp_path):
    estado, pj = montar(tmp_path, respiro_rms_db=-42)
    r = G.rodar(pj, asr=asr_com())
    assert r.ok, r.motivo


def test_respiro_em_pausa_curta_nao_entra(tmp_path):
    """Pausa de 0,45 s é menor que 0,62 s: nem é medida."""
    estado, pj = montar(tmp_path, pausas=((1.5, 1.95), (4.0, 4.45)), respiro_rms_db=-30)
    assert G.rodar(pj, asr=asr_com()).ok


def test_respiros_puro_pausa_de_062_vale_e_061_nao_vale():
    jan = 0.05
    db = np.full(100, -21.0)
    db[20:33] = -30.0                        # 20*0.05=1,0 s a 1,65 s com respiro
    assert [round(x[0], 2) for x in G.respiros([(1.0, 1.62)], db, jan)] == [1.0]
    assert G.respiros([(1.0, 1.61)], db, jan) == []


def test_respiros_puro_ignora_a_borda_da_pausa():
    """A cauda da última sílaba cai nos 0,05 s da borda: não é respiro."""
    jan = 0.05
    db = np.full(100, -90.0)
    db[20] = -25.0                           # primeira janela da pausa ainda tem a cauda da fala
    db[33] = -25.0                           # e a última já tem o ataque da próxima palavra
    assert G.respiros([(1.0, 1.7)], db, jan) == []


def test_pausas_do_envelope_o_respiro_fica_dentro_da_pausa():
    """Histerese: respiro de -31 dB não parte a pausa em duas; a palavra seguinte (-21) fecha."""
    jan = 0.05
    db = np.full(100, -21.0)
    db[20:26] = -60.0
    db[26:33] = -31.0                        # respiro, 7 janelas
    db[33:40] = -60.0
    pausas = G.pausas_do_envelope(db, jan)
    assert pausas == [(1.0, 2.0)]


# --- ritmo achatado ------------------------------------------------------------------------------------

def test_pausas_exigidas_cresce_com_a_duracao_1_a_cada_15_s_minimo_2():
    """W7.X item 4: a régua fixa de 4 pausas reprovava voz real normal (57 s, 3 pausas)."""
    assert G.pausas_exigidas(30.0) == 2 and G.pausas_exigidas(31.0) == 2 and G.pausas_exigidas(44.9) == 2
    assert G.pausas_exigidas(45.0) == 3 and G.pausas_exigidas(56.6) == 3
    assert G.pausas_exigidas(60.0) == 4 and G.pausas_exigidas(90.0) == 6


def test_ritmo_achatado_puro():
    assert G.ritmo_achatado(31.0, []) == (True, 0)
    assert G.ritmo_achatado(31.0, [0.8]) == (True, 1)                    # 1 < 2
    assert G.ritmo_achatado(31.0, [0.8, 0.9]) == (False, 2)
    assert G.ritmo_achatado(30.0, []) == (False, 0)                      # só vale acima de 30 s
    assert G.ritmo_achatado(40.0, [0.60, 0.6, 0.6, 0.6]) == (True, 0)    # 0,60 exatos não é MAIS que 0,60
    # a voz real da prova de aluno: 56,6 s e 3 pausas passa; 2 pausas nessa mesma voz reprova
    assert G.ritmo_achatado(56.6, [0.8, 0.9, 1.0]) == (False, 3)
    assert G.ritmo_achatado(56.6, [0.8, 0.9]) == (True, 2)
    assert G.ritmo_achatado(120.0, [0.8] * 7) == (True, 7)               # 120 s pedem 8


def test_motivo_do_ritmo_achatado_nao_manda_o_aluno_mexer_em_variavel_escondida():
    fontes = [(RAIZ / "scripts" / "gates" / "gate_entrada.py"), (RAIZ / "scripts" / "cli" / "audio.py"),
              (RAIZ / "scripts" / "auditar_audio.py")]
    for f in fontes:
        texto = f.read_text(encoding="utf-8")
        assert "Higienize com KEEP_PAUSE" not in texto, "%s manda o aluno mexer em KEEP_PAUSE_RATIO" % f.name


def test_voz_de_32_segundos_sem_pausa_reprova_por_ritmo_achatado(tmp_path):
    estado, pj = montar(tmp_path, dur=32.0, pausas=())
    r = G.rodar(pj, asr=asr_com())
    assert not r.ok
    assert regras(r) == ["ritmo_achatado"]
    assert "ritmo achatado" in r.motivo


def test_voz_de_32_segundos_com_4_pausas_de_fim_de_frase_passa(tmp_path):
    estado, pj = montar(tmp_path, dur=32.0,
                        pausas=((5.0, 5.9), (10.0, 10.9), (15.0, 15.9), (20.0, 20.9)))
    r = G.rodar(pj, asr=asr_com())
    assert r.ok, r.motivo
    assert r.detalhes["pausas_acima_de_0_60"] == 4


def test_pausa_no_comeco_e_no_fim_do_arquivo_nao_conta_como_respiracao(tmp_path):
    """Silêncio de ponta não é pausa de fim de frase."""
    estado, pj = montar(tmp_path, dur=32.0, pausas=((0.0, 1.0), (31.0, 32.0)))
    r = G.rodar(pj, asr=asr_com())
    assert regras(r) == ["ritmo_achatado"]


# --- fala preservada (fração de letras) -----------------------------------------------------------------

def test_trechos_com_dano_corte_comeu_a_palavra():
    danos, suspeitas = G.trechos_com_dano("vamos fazer uma campanha agora".split(),
                                          "vamos fazer panha agora".split())
    assert danos == [("uma campanha", "panha")]       # 5 de 11 letras = 0,45
    assert suspeitas == []


def test_trechos_com_dano_elisao_natural_e_suspeita_nao_dano():
    danos, suspeitas = G.trechos_com_dano("vamos embora agora".split(), "vambora agora".split())
    assert danos == []
    assert suspeitas == [("vamos embora", "vambora")]   # 7 de 11 = 0,64


def test_fracao_de_letras_o_limite_e_menor_que_060_estrito():
    # 3 de 5 letras = 0,60 exato: NÃO é dano. 2 de 5 = 0,40: é.
    assert G.trechos_com_dano(["aaaaa"], ["aaa"])[0] == []
    assert G.trechos_com_dano(["aaaaa"], ["aa"])[0] == [("aaaaa", "aa")]


def test_trecho_de_menos_de_3_letras_e_ruido_do_transcritor():
    assert G.trechos_com_dano("a um b".split(), "a b".split())[0] == []


def test_palavra_a_mais_no_limpo_nunca_e_dano():
    assert G.trechos_com_dano("vamos agora".split(), "vamos todos agora".split()) == ([], [])


def test_corte_que_comeu_fala_reprova_no_gate(tmp_path):
    estado, pj = montar(tmp_path)
    r = G.rodar(pj, asr=asr_com(bruto=TEXTO, limpo=TEXTO.replace("uma campanha", "panha")))
    assert not r.ok
    assert regras(r) == ["fala_preservada"]
    assert "corte comeu fala" in r.motivo and "uma campanha" in r.motivo


def test_elisao_natural_aparece_no_relatorio_e_nao_reprova(tmp_path):
    estado, pj = montar(tmp_path)
    r = G.rodar(pj, asr=asr_com(bruto="vamos embora agora de manhã", limpo="vambora agora de manhã"))
    assert r.ok, r.motivo
    assert r.detalhes["suspeitas"] == 1


def test_sem_bruto_nao_ha_o_que_comparar_e_isso_fica_registrado(tmp_path):
    estado, pj = montar(tmp_path, com_bruto=False)
    r = G.rodar(pj, asr=asr_com())
    assert r.ok, r.motivo
    assert any("sem voz/bruto" in a for a in r.detalhes["avisos"])


# --- duração avatar x limpo -------------------------------------------------------------------------------

def test_duracao_confere_puro_o_limite_e_acima_de_1_0():
    assert G.duracao_confere(7.0, 6.0) is True          # 1,0 s exatos passa
    assert G.duracao_confere(7.01, 6.0) is False
    assert G.duracao_confere(5.0, 6.0) is True
    assert G.duracao_confere(4.99, 6.0) is False


def test_avatar_gerado_do_audio_errado_reprova(tmp_path):
    """Avatar de 8 s para uma voz limpa de 6 s: foi gerado do bruto, com as pausas todas."""
    estado, pj = montar(tmp_path, modo="avatar", avatar_dur=8.0)
    r = G.rodar(pj, asr=asr_com())
    assert not r.ok
    assert regras(r) == ["duracao_avatar"]
    assert "não foi gerado do áudio limpo" in r.motivo


def test_varias_falhas_aparecem_juntas_no_motivo(tmp_path):
    estado, pj = montar(tmp_path, respiro_rms_db=-30, modo="avatar", avatar_dur=8.0)
    r = G.rodar(pj, asr=asr_com(limpo=TEXTO.replace("uma campanha", "panha")))
    assert regras(r) == ["duracao_avatar", "fala_preservada", "respiro"]


# --- insumos ------------------------------------------------------------------------------------------------

def test_sem_voz_limpa_e_insumo_invalido(tmp_path):
    estado, pj = montar(tmp_path)
    pj.voz_limpo.unlink()
    with pytest.raises(G.InsumoInvalido) as e:
        G.rodar(pj, asr=asr_com())
    assert "voz/limpo.mp3" in str(e.value)


def test_modo_avatar_sem_avatar_e_insumo_invalido(tmp_path):
    estado, pj = montar(tmp_path, modo="avatar", avatar_dur=None)
    with pytest.raises(G.InsumoInvalido) as e:
        G.rodar(pj, asr=asr_com())
    assert "avatar/avatar.mp4" in str(e.value)


def test_audio_que_o_ffmpeg_nao_le_e_insumo_invalido(tmp_path):
    estado, pj = montar(tmp_path)
    pj.voz_limpo.write_bytes(b"isto nao e audio")
    with pytest.raises(G.InsumoInvalido):
        G.rodar(pj, asr=asr_com())


def test_sem_projeto_json_e_insumo_invalido(tmp_path):
    estado, pj = montar(tmp_path)
    pj.projeto_json.unlink()
    with pytest.raises(G.InsumoInvalido):
        G.rodar(pj, asr=asr_com())


# --- constantes: o número e a origem -------------------------------------------------------------------------

def test_limiares_do_plano():
    assert G.BIG_SIL_GATE == 0.62            # pausa a partir da qual se mede respiro
    assert G.RESPIRO_DB_GATE == -34.0
    assert G.AVATAR_DUR_TOL == 1.0
    assert G.FRACAO_LETRAS_DANO == 0.60
    assert G.MIN_PAUSAS_LONGAS == 2 and G.PAUSA_A_CADA_S == 15.0
    assert G.PAUSA_LONGA == 0.60 and G.DUR_MIN_RITMO_S == 30.0


def test_constantes_iguais_as_do_passo_que_o_gate_fiscaliza():
    """Princípio 2: o limiar sai do passo fiscalizado. Se auditar_audio mudar, o gate acusa."""
    import auditar_audio as A
    assert G.RESPIRO_DB_GATE == A.RESPIRO_DB
    assert G.PAUSA_LONGA == A.PAUSA_LONGA
    assert G.MIN_PAUSAS_LONGAS == A.MIN_PAUSAS_LONGAS
    assert G.PAUSA_A_CADA_S == A.PAUSA_A_CADA_S
    for d in (30.5, 44.0, 45.0, 56.6, 60.0, 100.0):
        assert G.pausas_exigidas(d) == A.pausas_exigidas(d), d
    assert G.FRACAO_LETRAS_DANO == A.FRACAO_LETRAS_DANO
    assert G.MIN_LETRAS_TRECHO == A.MIN_LETRAS_TRECHO


def test_gate_nao_tem_look_nem_pasta_de_leva_cravados():
    fonte = (RAIZ / "scripts" / "gates" / "gate_entrada.py").read_text(encoding="utf-8")
    for proibido in ("audios_leva", "LOOKS_OK", "/tmp", "parakeet-mlx"):
        assert proibido not in fonte


# --- CLI ------------------------------------------------------------------------------------------------------

def test_cli_passa_exit_0_e_registra(tmp_path, capsys):
    estado, pj = montar(tmp_path)
    assert G.main([SLUG, "--estado", str(estado)], asr=asr_com()) == 0
    atual = status.ler(pj)["atual"]
    assert (atual["etapa"], atual["estado"]) == ("gate_entrada", "ok")
    assert atual["detalhes"]["falhas"] == []


def test_cli_reprova_exit_1_e_registra_com_motivo(tmp_path, capsys):
    estado, pj = montar(tmp_path, respiro_rms_db=-30)
    assert G.main([SLUG, "--estado", str(estado)], asr=asr_com()) == 1
    atual = status.ler(pj)["atual"]
    assert (atual["etapa"], atual["estado"]) == ("gate_entrada", "falhou")
    assert "respiro audível" in atual["motivo"]
    assert "REPROVA" in capsys.readouterr().out


def test_cli_insumo_invalido_exit_2_e_registra(tmp_path, capsys):
    estado, pj = montar(tmp_path)
    pj.voz_limpo.unlink()
    assert G.main([SLUG, "--estado", str(estado)], asr=asr_com()) == 2
    atual = status.ler(pj)["atual"]
    assert (atual["etapa"], atual["estado"]) == ("gate_entrada", "bloqueado")


def test_roda_como_script_e_sai_2_sem_projeto(tmp_path):
    estado = tmp_path / "_local"
    estado.mkdir()
    p = subprocess.run([sys.executable, str(RAIZ / "scripts" / "gates" / "gate_entrada.py"), "nao-existe",
                        "--estado", str(estado)], capture_output=True, text=True)
    assert p.returncode == 2, p.stdout + p.stderr


# --- a voz real da prova de aluno (W7.X item 4) --------------------------------------------------------

NOME_VOZ_REAL = "Nova Gravação 62.m4a"


def _voz_real():
    """A gravação real da prova de aluno: na pasta de paridade (VAM_PARIDADE_MIDIA) ou em Downloads do usuário real
    (o HOME de verdade, não o falso do testar_limpo). None se não está nesta máquina."""
    import os
    import pwd
    pastas_ = []
    if os.environ.get("VAM_PARIDADE_MIDIA"):
        pastas_.append(Path(os.environ["VAM_PARIDADE_MIDIA"]))
    pastas_.append(Path(pwd.getpwuid(os.getuid()).pw_dir) / "Downloads")
    return next((p / NOME_VOZ_REAL for p in pastas_ if (p / NOME_VOZ_REAL).is_file()), None)


@pytest.mark.lento
@pytest.mark.midia_real
def test_voz_real_de_57_s_higienizada_pelo_vam_passa_na_regra_de_ritmo(tmp_path):
    """A gravação real normal (61 s bruta, 56,6 s limpa, 3 pausas acima de 0,60 s) reprovava com a régua fixa de 4.
    Mede só o ritmo (sem transcritor): higieniza como o `vam audio` e aplica a MESMA regra do gate."""
    VOZ_REAL = _voz_real()
    if VOZ_REAL is None:
        pytest.skip("a gravação real da prova (%s) não está nesta máquina" % NOME_VOZ_REAL)
    from audio import pausas_reais
    from cli import audio as cli_audio
    limpo = cli_audio.higienizar(VOZ_REAL, tmp_path / "limpo.mp3", 1.35)
    db, jan = pausas_reais.envelope_db(limpo)
    d = len(db) * jan
    pausas = G.pausas_do_envelope(db, jan)
    internas = [(i, f) for i, f in pausas if i > 1e-9 and f < d - 1e-9]
    achatado, n = G.ritmo_achatado(d, [f - i for i, f in internas])
    assert d > G.DUR_MIN_RITMO_S
    assert not achatado, "voz real de %.1f s com %d pausa(s) longa(s) (exigidas %d) reprovou" % (
        d, n, G.pausas_exigidas(d))
    assert n >= 2
