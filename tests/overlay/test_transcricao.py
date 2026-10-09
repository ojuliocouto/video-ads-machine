"""overlay.transcricao: avatar acelerado, transcrição com cache por conteúdo e palavras do roteiro.

Sem ffmpeg e sem parakeet: `vdur` e `run` são trocados por falsos. O valor esperado de cada
teste foi lido do `gen_ad_v2.py` original (argv do ffmpeg, arredondamento do total, ordem
em que o cache e o transcritor são consultados).
"""
import json
import subprocess

import pytest

from overlay import transcricao as T


# --- norm, vdur, run ---------------------------------------------------------------------

def test_norm_tira_acento_pontuacao_e_caixa():
    assert T.norm("Páginas,") == "paginas"
    assert T.norm("AÇÃO!") == "acao"
    assert T.norm("R$ 10") == "r10"


def test_vdur_le_a_duracao_do_ffprobe(monkeypatch):
    chamadas = []

    def falso(cmd, **kw):
        chamadas.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="12.5\n", stderr="")

    monkeypatch.setattr(T.subprocess, "run", falso)
    assert T.vdur("a.mp4") == 12.5
    assert chamadas[0] == ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                           "-of", "default=nw=1:nk=1", "a.mp4"]


def test_vdur_sem_saida_e_zero(monkeypatch):
    monkeypatch.setattr(T.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="x"))
    assert T.vdur("nao_existe.mp4") == 0.0


def test_run_que_falha_sai_com_o_comando_e_o_fim_do_stderr(monkeypatch):
    monkeypatch.setattr(T.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="",
                                                                        stderr="x" * 900 + "FIM"))
    with pytest.raises(SystemExit) as e:
        T.run(["ffmpeg", "-y", 7])
    msg = str(e.value)
    assert msg.startswith("ERRO: ffmpeg -y 7\n")
    assert msg.endswith("FIM") and len(msg.split("\n", 1)[1]) == 800


def test_constantes_do_avatar():
    assert T.SPEED == 1.15
    assert T.TAIL_PAD == 0.65


# --- preparar_avatar -----------------------------------------------------------------------

@pytest.fixture
def falsos(monkeypatch):
    """vdur com duração por nome de arquivo e run que só anota o comando."""
    duracoes = {}
    rodados = []
    monkeypatch.setattr(T, "vdur", lambda f: duracoes.get(str(f), 0.0))
    monkeypatch.setattr(T, "run", lambda cmd, **kw: rodados.append(list(cmd)))
    return duracoes, rodados


def test_avatar_sem_aceleracao_so_copia(tmp_path, falsos):
    duracoes, rodados = falsos
    src = tmp_path / "av.mp4"
    src.write_bytes(b"video")
    out = tmp_path / "out"
    out.mkdir()
    duracoes[str(src)] = 18.0
    duracoes[str(out / "avatar.mp4")] = 18.0
    dst, total = T.preparar_avatar(src, out, 1.0)
    assert dst == out / "avatar.mp4" and dst.read_bytes() == b"video"
    assert rodados == []
    # D5: a cauda nunca e cortada. ceil((18.0 + 0.65) * 100) / 100
    assert total == 18.65


def test_avatar_acelerado_roda_o_ffmpeg_com_o_argv_do_original(tmp_path, falsos):
    duracoes, rodados = falsos
    src = tmp_path / "av.mp4"
    src.write_bytes(b"video")
    out = tmp_path / "out"
    out.mkdir()
    duracoes[str(src)] = 23.0
    duracoes[str(out / "avatar.mp4")] = 20.0
    dst, total = T.preparar_avatar(src, out, 1.15)
    assert rodados == [[
        "ffmpeg", "-y", "-i", str(src),
        "-filter_complex", "[0:v]setpts=PTS/1.15[v];[0:a]atempo=1.15[a]",
        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-c:a", "aac", "-b:a", "192k", str(out / "avatar.mp4")]]
    assert total == 20.65


def test_reacelerar_apaga_os_derivados_do_avatar_antigo(tmp_path, falsos):
    duracoes, rodados = falsos
    src = tmp_path / "av.mp4"
    src.write_bytes(b"video")
    out = tmp_path / "out"
    out.mkdir()
    (out / "avatar.mp4").write_bytes(b"velho")
    for nome in ("transcript.json", "broll01.mp4", "broll02.mp4", "mantem.txt"):
        (out / nome).write_text("x")
    duracoes[str(src)] = 23.0
    duracoes[str(out / "avatar.mp4")] = 99.0     # nao bate com 23 / 1.15 = 20.0
    T.preparar_avatar(src, out, 1.15)
    assert not (out / "transcript.json").exists()
    assert not list(out.glob("broll*.mp4"))
    assert (out / "mantem.txt").exists()


def test_avatar_ja_na_duracao_certa_nao_refaz_nada(tmp_path, falsos):
    duracoes, rodados = falsos
    src = tmp_path / "av.mp4"
    src.write_bytes(b"video")
    out = tmp_path / "out"
    out.mkdir()
    (out / "avatar.mp4").write_bytes(b"pronto")
    (out / "transcript.json").write_text("[]")
    duracoes[str(src)] = 23.0
    duracoes[str(out / "avatar.mp4")] = 20.03     # dentro de 0,05 de 20.0
    dst, total = T.preparar_avatar(src, out, 1.15)
    assert rodados == [] and (out / "transcript.json").exists()
    assert dst.read_bytes() == b"pronto"
    assert total == 20.68      # ceil((20.03 + 0.65) * 100) / 100


def test_total_arredonda_pra_cima_no_centesimo(tmp_path, falsos):
    duracoes, _ = falsos
    src = tmp_path / "av.mp4"
    src.write_bytes(b"v")
    out = tmp_path / "out"
    out.mkdir()
    duracoes[str(src)] = 10.0
    duracoes[str(out / "avatar.mp4")] = 10.001
    _, total = T.preparar_avatar(src, out, 1.0)
    assert total == 10.66      # ceil(1065.1) = 1066


# --- transcrever: o cache e do CONTEUDO do avatar, nao do out_dir ----------------------------

@pytest.fixture
def cache_em_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "V1", tmp_path / "dados")
    return tmp_path / "dados" / "output" / "_cache" / "transcricao"


def test_transcript_ja_no_out_dir_nao_consulta_cache_nem_transcritor(tmp_path, cache_em_tmp, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    (out / "transcript.json").write_text(json.dumps([{"text": "oi", "start": 0, "end": 1}]))
    dst = out / "avatar.mp4"
    dst.write_bytes(b"a")
    monkeypatch.setattr(T, "run", lambda *a, **k: pytest.fail("nao deveria transcrever"))
    assert T.transcrever(dst, out) == [{"text": "oi", "start": 0, "end": 1}]


def test_cache_miss_roda_o_hyperframes_e_guarda(tmp_path, cache_em_tmp, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    dst = out / "avatar.mp4"
    dst.write_bytes(b"conteudo do avatar")
    chamadas = []

    def falso_run(cmd, **kw):
        chamadas.append((list(cmd), kw))
        (kw["cwd"] / "transcript.json").write_text(json.dumps([{"text": "ola", "start": 0.1, "end": 0.4}]))

    monkeypatch.setattr(T, "run", falso_run)
    palavras = T.transcrever(dst, out)
    assert palavras == [{"text": "ola", "start": 0.1, "end": 0.4}]
    # o argv do original: transcribe do avatar.mp4 no diretorio de saida
    assert chamadas[0][0] == [T.HF, "transcribe", "avatar.mp4", "--engine", "parakeet",
                              "--json", "-d", "."]
    assert chamadas[0][1] == {"cwd": out}
    assert len(list(cache_em_tmp.glob("*.json"))) == 1


def test_cache_hit_em_outro_out_dir_nao_chama_o_parakeet(tmp_path, cache_em_tmp, monkeypatch):
    # 31/08/2026: 8 builds do mesmo avatar rodaram o parakeet 8 vezes
    conteudo = b"mesmo avatar nos dois builds"
    for nome in ("a", "b"):
        (tmp_path / nome).mkdir()
        (tmp_path / nome / "avatar.mp4").write_bytes(conteudo)
    rodou = []

    def falso_run(cmd, **kw):
        rodou.append(cmd)
        (kw["cwd"] / "transcript.json").write_text(json.dumps([{"text": "um", "start": 0, "end": 1}]))

    monkeypatch.setattr(T, "run", falso_run)
    T.transcrever(tmp_path / "a" / "avatar.mp4", tmp_path / "a")
    import os
    os.utime(tmp_path / "b" / "avatar.mp4",
             ns=(os.stat(tmp_path / "a" / "avatar.mp4").st_atime_ns,
                 os.stat(tmp_path / "a" / "avatar.mp4").st_mtime_ns))
    palavras = T.transcrever(tmp_path / "b" / "avatar.mp4", tmp_path / "b")
    assert len(rodou) == 1
    assert palavras == [{"text": "um", "start": 0, "end": 1}]
    assert (tmp_path / "b" / "transcript.json").exists()


# --- palavras do roteiro --------------------------------------------------------------------

def test_alinhar_palavras_usa_a_grafia_do_roteiro_e_o_tempo_do_transcript():
    blocks = [{"narr": "Minha skill de páginas"}, {"narr": "agora *roda* sozinha"}]
    transcript = [{"text": t, "start": i * 0.5, "end": i * 0.5 + 0.4}
                  for i, t in enumerate("minha skill de paginas agora roda sozinha".split())]
    words = T.alinhar_palavras(blocks, transcript)
    assert [w["text"] for w in words] == ["Minha", "skill", "de", "páginas", "agora", "roda", "sozinha"]
    assert words[3]["start"] == 1.5 and words[3]["end"] == 1.9
    assert [w["kw"] for w in words] == [False, False, False, False, False, True, False]


def test_marcar_kw_marca_a_frase_pela_forma_normalizada():
    words = [{"text": t, "start": i, "end": i + 1, "kw": False}
             for i, t in enumerate(["O", "Web", "Designer,", "profissional.", "e", "Web", "designer"])]
    T.marcar_kw(words, ["web designer profissional"])
    assert [w["kw"] for w in words] == [False, True, True, True, False, False, False]


def test_marcar_kw_marca_todas_as_ocorrencias():
    words = [{"text": t, "start": i, "end": i + 1} for i, t in enumerate(["em", "minutos", "ou", "em", "minutos"])]
    T.marcar_kw(words, ["em minutos"])
    assert [bool(w.get("kw")) for w in words] == [True, True, False, True, True]


def test_marcar_kw_sem_frases_nao_mexe():
    words = [{"text": "a", "start": 0, "end": 1}]
    T.marcar_kw(words, [])
    assert "kw" not in words[0]
