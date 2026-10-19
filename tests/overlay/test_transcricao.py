"""overlay.transcricao: avatar acelerado, transcrição com cache por conteúdo e palavras do roteiro.

Sem ffmpeg e sem parakeet: `vdur` e `run` são trocados por falsos. O valor esperado de cada
teste foi lido do `gen_ad_v2.py` original (argv do ffmpeg, arredondamento do total, ordem
em que o cache e o transcritor são consultados).
"""
import json
import subprocess
from pathlib import Path

import pytest

import plataforma

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


class _BackendFalso:
    """Um backend do seletor de transcrição (`audio.transcrever`): devolve palavras prontas, sem rodar nada."""

    def __init__(self, nome, palavras):
        self.NOME, self.palavras, self.chamadas = nome, palavras, []

    def transcrever(self, audio, *, amb, workdir, prompt="", idioma="pt", **extra):
        self.chamadas.append({"audio": str(audio), "idioma": idioma, **extra})
        return [dict(p) for p in self.palavras]


def test_cache_miss_passa_pelo_seletor_e_guarda(tmp_path, cache_em_tmp, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    dst = out / "avatar.mp4"
    dst.write_bytes(b"conteudo do avatar")
    falso = _BackendFalso("faster_whisper", [{"text": "ola", "start": 0.1, "end": 0.4}])
    monkeypatch.setattr(T, "run", lambda *a, **k: pytest.fail("nao deveria chamar o HyperFrames"))
    palavras = T.transcrever(dst, out, backend=falso)
    assert palavras == [{"id": "", "text": "ola", "start": 0.1, "end": 0.4}]
    # o seletor recebeu o avatar e o idioma fixo em portugues (o dono viu o modelo escorregar para o ingles)
    assert falso.chamadas == [{"audio": str(dst), "idioma": "pt"}]
    # o transcript.json tem a forma de sempre: lista de {text, start, end}
    assert json.loads((out / "transcript.json").read_text(encoding="utf-8")) == palavras
    assert len(list(cache_em_tmp.glob("*.json"))) == 1


def test_sem_transcritor_para_com_a_mensagem_do_conserto(tmp_path, cache_em_tmp):
    from audio import transcrever as asr
    out = tmp_path / "out"
    out.mkdir()
    (out / "avatar.mp4").write_bytes(b"x")
    vazio = asr.Ambiente(sistema="Linux", arquitetura="x86_64", env={}, which=lambda n: None,
                         importavel=lambda m: False)
    with pytest.raises(SystemExit) as e:
        T.transcrever(out / "avatar.mp4", out, amb=vazio)
    assert str(e.value).startswith("ERRO: ") and "faster-whisper" in str(e.value)


# Saída do parakeet-mlx (formato real: sentenças com tokens; token com espaço na frente abre palavra).
_SAIDA_PARAKEET = {"text": "Olá mundo agora.", "sentences": [
    {"text": "Olá mundo agora.", "start": 0.0, "end": 1.5, "tokens": [
        {"text": " Ol", "start": 0.0, "end": 0.2}, {"text": "á", "start": 0.2, "end": 0.4},
        {"text": " mun", "start": 0.5, "end": 0.7}, {"text": "do", "start": 0.7, "end": 0.9},
        {"text": " agora.", "start": 1.0, "end": 1.5}]}]}
# A forma que o `hyperframes transcribe` gravava (medida com o parakeet real): `id` vazio, text, start, end.
_PALAVRAS_ESPERADAS = [{"id": "", "text": "Olá", "start": 0.0, "end": 0.4},
                       {"id": "", "text": "mundo", "start": 0.5, "end": 0.9},
                       {"id": "", "text": "agora.", "start": 1.0, "end": 1.5}]


@pytest.mark.skipif(plataforma.eh_windows(), reason="o parakeet falso é um script sh (o parakeet só roda no Mac)")
def test_backend_forcado_em_parakeet_da_a_mesma_estrutura_do_caminho_antigo(tmp_path, cache_em_tmp):
    """No Mac com parakeet o transcript.json segue sendo a lista `[{id, text, start, end}]` que o transcribe do
    HyperFrames gravava: o resto do overlay (alinhar_palavras) não percebe a troca."""
    from audio import transcrever as asr
    exe = tmp_path / "bin" / "parakeet-mlx"
    exe.parent.mkdir()
    exe.write_text('#!/bin/sh\nb=$(basename "$1"); b="${b%%.*}"\ncp "%s" "$5/$b.json"\n'
                   % (tmp_path / "saida.json"), encoding="utf-8")
    exe.chmod(0o755)
    (tmp_path / "saida.json").write_text(json.dumps(_SAIDA_PARAKEET), encoding="utf-8")
    mac = asr.Ambiente(sistema="Darwin", arquitetura="arm64", env={},
                       which=lambda n: str(exe) if n == "parakeet-mlx" else None, importavel=lambda m: False)
    out = tmp_path / "out"
    out.mkdir()
    dst = out / "avatar.mp4"
    dst.write_bytes(b"avatar")
    palavras = T.transcrever(dst, out, backend="parakeet", amb=mac)
    assert palavras == _PALAVRAS_ESPERADAS
    assert json.loads((out / "transcript.json").read_text(encoding="utf-8")) == _PALAVRAS_ESPERADAS
    assert all(list(p) == ["id", "text", "start", "end"] for p in palavras)
    # e o casamento com o roteiro (o consumidor do transcript) funciona sobre essa estrutura
    words = T.alinhar_palavras([{"narr": "Olá mundo agora"}], palavras)
    assert [(w["text"], w["start"], w["end"]) for w in words] == [("Olá", 0.0, 0.4), ("mundo", 0.5, 0.9),
                                                                   ("agora", 1.0, 1.5)]


def test_overlay_nao_chama_mais_o_hyperframes_para_transcrever():
    fonte = Path(T.__file__).read_text(encoding="utf-8")
    assert '"transcribe"' not in fonte and "--engine" not in fonte


def test_cache_hit_em_outro_out_dir_nao_chama_o_parakeet(tmp_path, cache_em_tmp, monkeypatch):
    # 31/08/2026: 8 builds do mesmo avatar rodaram o parakeet 8 vezes
    conteudo = b"mesmo avatar nos dois builds"
    for nome in ("a", "b"):
        (tmp_path / nome).mkdir()
        (tmp_path / nome / "avatar.mp4").write_bytes(conteudo)
    falso = _BackendFalso("faster_whisper", [{"text": "um", "start": 0, "end": 1}])
    rodou = falso.chamadas
    monkeypatch.setattr(T, "run", lambda *a, **k: pytest.fail("nao deveria chamar o HyperFrames"))
    T.transcrever(tmp_path / "a" / "avatar.mp4", tmp_path / "a", backend=falso)
    import os
    os.utime(tmp_path / "b" / "avatar.mp4",
             ns=(os.stat(tmp_path / "a" / "avatar.mp4").st_atime_ns,
                 os.stat(tmp_path / "a" / "avatar.mp4").st_mtime_ns))
    palavras = T.transcrever(tmp_path / "b" / "avatar.mp4", tmp_path / "b", backend=falso)
    assert len(rodou) == 1
    assert palavras == [{"id": "", "text": "um", "start": 0, "end": 1}]
    assert (tmp_path / "b" / "transcript.json").exists()


def test_l5_copia_do_avatar_com_outro_mtime_acerta_o_cache(tmp_path, cache_em_tmp, monkeypatch):
    """W3.X L5: a chave era 8 MB + tamanho + mtime, e a cópia do mesmo avatar em outra pasta (mtime novo) nunca
    acertava. A chave agora é o sha256 do conteúdo inteiro, como a docstring sempre afirmou."""
    import os
    import time

    conteudo = b"o mesmo avatar copiado para outra pasta"
    for nome in ("a", "b"):
        (tmp_path / nome).mkdir()
        (tmp_path / nome / "avatar.mp4").write_bytes(conteudo)
    os.utime(tmp_path / "b" / "avatar.mp4", (time.time() + 500, time.time() + 500))
    falso = _BackendFalso("faster_whisper", [{"text": "um", "start": 0, "end": 1}])
    rodou = falso.chamadas
    monkeypatch.setattr(T, "run", lambda *a, **k: pytest.fail("nao deveria chamar o HyperFrames"))
    T.transcrever(tmp_path / "a" / "avatar.mp4", tmp_path / "a", backend=falso)
    T.transcrever(tmp_path / "b" / "avatar.mp4", tmp_path / "b", backend=falso)
    assert len(rodou) == 1
    import hashlib
    assert (cache_em_tmp / (hashlib.sha256(conteudo).hexdigest() + ".json")).is_file()


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
