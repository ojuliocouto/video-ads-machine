"""Backends de transcrição (W1.C): parakeet, faster-whisper e Groq.

Tudo hermético: o executável do parakeet é um script falso, o faster-whisper é uma classe
falsa e o HTTP da Groq é um transporte injetado. Nenhuma chamada paga, nenhuma rede.
"""
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from audio import transcrever as T
from audio.backends import faster_whisper as FW
from audio.backends import groq as G
from audio.backends import parakeet as PK
from tests.fixtures import sinteticos as fx

# Dados propositalmente ruins: início regride, fim antes do início, sobreposição.
def _monotonico(palavras):
    assert isinstance(palavras, list) and palavras
    for i, p in enumerate(palavras):
        assert set(p) == {"text", "start", "end"}
        assert isinstance(p["text"], str) and p["text"].strip()
        assert isinstance(p["start"], float) and isinstance(p["end"], float)
        assert p["end"] >= p["start"] >= 0.0
        if i:
            assert p["start"] >= palavras[i - 1]["start"]
            assert p["end"] >= palavras[i - 1]["end"]


def amb(sistema="Darwin", arquitetura="arm64", executaveis=(), modulos=(), env=None, bins=()):
    return T.Ambiente(
        sistema=sistema, arquitetura=arquitetura, env=dict(env or {}),
        which=lambda nome: (f"/falso/bin/{nome}" if nome in executaveis else None),
        importavel=lambda nome: nome in modulos, bins_venv=tuple(bins))


# =========================== parakeet ===========================================================

def _executavel(pasta, nome="parakeet-mlx", corpo="#!/bin/sh\nexit 0\n"):
    pasta.mkdir(parents=True, exist_ok=True)
    p = pasta / nome
    p.write_text(corpo)
    p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return p


def test_parakeet_acha_o_executavel_no_path():
    a = amb(executaveis=("parakeet-mlx",))
    assert PK.achar_executavel(a) == "/falso/bin/parakeet-mlx"
    assert PK.disponivel(a)


def test_parakeet_acha_o_executavel_nos_scripts_do_venv(tmp_path):
    exe = _executavel(tmp_path / "venv" / "bin")
    a = amb(bins=(tmp_path / "venv" / "bin",))
    assert Path(PK.achar_executavel(a)) == exe
    assert PK.disponivel(a)


def test_parakeet_nunca_procura_em_local_bin_cravado(home_falso):
    _executavel(home_falso / ".local" / "bin")
    a = amb(bins=())                       # nem no PATH nem no venv
    assert PK.achar_executavel(a) is None
    assert not PK.disponivel(a)
    assert ".local/bin" not in Path(PK.__file__).read_text(encoding="utf-8")


def test_parakeet_so_no_apple_silicon_mesmo_com_o_executavel():
    assert not PK.disponivel(amb(sistema="Linux", arquitetura="x86_64",
                                 executaveis=("parakeet-mlx",)))


def test_ambiente_real_inclui_o_bin_do_python_em_uso_e_o_venv_do_repo():
    real = T.Ambiente.real()
    bins = [str(b) for b in real.bins_venv]
    assert str(Path(sys.executable).parent) in bins
    assert any(b.endswith(os.path.join(".venv", "bin")) for b in bins)


SAIDA_PARAKEET = {
    "text": " Você perde três horas.",
    "sentences": [{
        "text": " Você perde três horas.", "start": 0.0, "end": 2.0,
        "tokens": [
            {"text": " Você", "start": 0.0, "end": 0.32},
            {"text": " per", "start": 0.48, "end": 0.72},
            {"text": "de", "start": 0.72, "end": 0.88},
            {"text": " tr", "start": 0.88, "end": 1.04},
            {"text": "ês", "start": 1.04, "end": 1.28},
            {"text": " hor", "start": 1.28, "end": 1.44},
            {"text": "as.", "start": 1.4, "end": 2.0},           # início regride 40 ms
        ]}],
}


def test_parakeet_junta_tokens_em_palavras_e_devolve_monotonico():
    palavras = PK.palavras_da_saida(SAIDA_PARAKEET)
    assert [p["text"] for p in palavras] == ["Você", "perde", "três", "horas."]
    assert palavras[1]["start"] == 0.48 and palavras[1]["end"] == 0.88
    _monotonico(palavras)


def test_parakeet_sem_tokens_cai_na_sentenca():
    saida = {"sentences": [{"text": " Olá mundo.", "start": 1.0, "end": 2.0}]}
    palavras = PK.palavras_da_saida(saida)
    assert [p["text"] for p in palavras] == ["Olá", "mundo."]
    _monotonico(palavras)
    assert palavras[0]["start"] == 1.0 and palavras[-1]["end"] == 2.0


def test_parakeet_chama_o_executavel_com_json_e_chunk_e_le_o_arquivo(tmp_path):
    corpo = ("#!/bin/sh\n"
             'while [ "$#" -gt 0 ]; do case "$1" in --output-dir) D="$2"; shift;; '
             '--output-format) F="$2"; shift;; --chunk-duration) C="$2"; shift;; '
             '--overlap-duration) O="$2"; shift;; *) A="$1";; esac; shift; done\n'
             '[ "$F" = json ] && [ "$C" = 15 ] && [ "$O" = 3 ] || exit 3\n'
             'B=$(basename "$A"); cat > "$D/${B%.*}.json" <<\'EOF\'\n'
             + json.dumps(SAIDA_PARAKEET) + "\nEOF\n")
    _executavel(tmp_path / "bin", corpo=corpo)
    audio = fx.tom_com_pausas(tmp_path / "fala.wav", dur=1.0, pausas=())
    a = amb(bins=(tmp_path / "bin",))
    trabalho = tmp_path / "trabalho"
    palavras = PK.transcrever(audio, amb=a, workdir=trabalho)
    assert [p["text"] for p in palavras] == ["Você", "perde", "três", "horas."]
    _monotonico(palavras)
    assert (trabalho / "fala.json").exists()


def test_parakeet_com_falha_do_executavel_cita_a_saida_de_erro(tmp_path):
    _executavel(tmp_path / "bin", corpo="#!/bin/sh\necho 'modelo nao encontrado' >&2\nexit 4\n")
    audio = fx.tom_com_pausas(tmp_path / "fala.wav", dur=1.0, pausas=())
    with pytest.raises(PK.ErroParakeet, match="modelo nao encontrado"):
        PK.transcrever(audio, amb=amb(bins=(tmp_path / "bin",)), workdir=tmp_path / "t")


def test_parakeet_sem_arquivo_de_saida_e_erro_nao_lista_vazia(tmp_path):
    _executavel(tmp_path / "bin", corpo="#!/bin/sh\nexit 0\n")
    audio = fx.tom_com_pausas(tmp_path / "fala.wav", dur=1.0, pausas=())
    with pytest.raises(PK.ErroParakeet, match="json"):
        PK.transcrever(audio, amb=amb(bins=(tmp_path / "bin",)), workdir=tmp_path / "t")


# =========================== faster-whisper =====================================================

class Palavra:
    def __init__(self, word, start, end):
        self.word, self.start, self.end = word, start, end


class Segmento:
    def __init__(self, text, start, end, words=None):
        self.text, self.start, self.end, self.words = text, start, end, words


class ModeloFalso:
    def __init__(self, segmentos):
        self.segmentos, self.chamado = segmentos, None

    def transcribe(self, caminho, **kw):
        self.chamado = (caminho, kw)
        return iter(self.segmentos), object()


def test_faster_whisper_disponivel_so_se_o_modulo_importa():
    assert FW.disponivel(amb(modulos=("faster_whisper",)))
    assert not FW.disponivel(amb())
    assert FW.disponivel(amb(sistema="Linux", arquitetura="x86_64", modulos=("faster_whisper",)))


def test_faster_whisper_pede_pt_prompt_e_desliga_o_condition_on_previous_text(tmp_path):
    modelo = ModeloFalso([Segmento(" Olá mundo", 0.0, 1.0,
                                   [Palavra(" Olá", 0.0, 0.4), Palavra(" mundo", 0.5, 1.0)])])
    audio = fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=())
    FW.transcrever(audio, amb=amb(modulos=("faster_whisper",)), workdir=tmp_path,
                   prompt="Vocabulário: Claude.", fabrica_modelo=lambda: modelo)
    caminho, kw = modelo.chamado
    assert kw["language"] == "pt"
    assert kw["initial_prompt"] == "Vocabulário: Claude."
    assert kw["condition_on_previous_text"] is False      # senão repete parágrafo anterior
    assert kw["word_timestamps"] is True


def test_faster_whisper_devolve_monotonico_mesmo_com_segmentos_sobrepostos(tmp_path):
    modelo = ModeloFalso([
        Segmento(" um dois", 0.0, 1.0, [Palavra(" um", 0.0, 0.6), Palavra(" dois", 0.5, 1.0)]),
        Segmento(" três", 0.9, 1.5, [Palavra(" três", 0.8, 1.5)]),
    ])
    audio = fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=())
    palavras = FW.transcrever(audio, amb=amb(), workdir=tmp_path, fabrica_modelo=lambda: modelo)
    assert [p["text"] for p in palavras] == ["um", "dois", "três"]
    _monotonico(palavras)


def test_faster_whisper_sem_tempo_por_palavra_distribui_pelo_segmento(tmp_path):
    modelo = ModeloFalso([Segmento(" a b c d", 2.0, 4.0, None)])
    audio = fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=())
    palavras = FW.transcrever(audio, amb=amb(), workdir=tmp_path, fabrica_modelo=lambda: modelo)
    assert [p["text"] for p in palavras] == ["a", "b", "c", "d"]
    assert palavras[0]["start"] == 2.0 and palavras[-1]["end"] == 4.0
    _monotonico(palavras)


# =========================== Groq ===========================================================

class Transporte:
    """Transporte HTTP falso: devolve as respostas na ordem e guarda as requisições."""

    def __init__(self, *respostas):
        self.respostas, self.requisicoes = list(respostas), []

    def __call__(self, req):
        self.requisicoes.append(req)
        return self.respostas.pop(0)


def _ok(palavras=None, texto="Olá mundo"):
    palavras = palavras if palavras is not None else [
        {"word": "Olá", "start": 0.0, "end": 0.4}, {"word": "mundo", "start": 0.5, "end": 0.9}]
    return 200, json.dumps({"text": texto, "words": palavras})


CHAVE = "gsk_chave_de_teste_nao_real"


@pytest.fixture
def audio_groq(tmp_path):
    return fx.tom_com_pausas(tmp_path / "fala.wav", dur=1.5, pausas=())


def _rodar(audio, tmp_path, transporte, prompt="Transcrição em português do Brasil.", **kw):
    dormidas = []
    palavras = G.transcrever(audio, amb=amb(env={"GROQ_API_KEY": CHAVE}),
                             workdir=tmp_path / "t", prompt=prompt, transporte=transporte,
                             dormir=dormidas.append, **kw)
    return palavras, dormidas


def test_groq_disponivel_so_com_chave():
    assert G.disponivel(amb(env={"GROQ_API_KEY": CHAVE}))
    assert not G.disponivel(amb())
    assert not G.disponivel(amb(env={"GROQ_API_KEY": ""}))


def test_groq_manda_user_agent_de_navegador_language_pt_e_o_prompt_do_glossario(
        audio_groq, tmp_path):
    t = Transporte(_ok())
    prompt = T.prompt_do_glossario({"versao": 1, "termos": [{"grafia": "Claude Code"}]})
    palavras, _ = _rodar(audio_groq, tmp_path, t, prompt=prompt)
    req = t.requisicoes[0]
    assert req["url"] == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert req["headers"]["User-Agent"].startswith("Mozilla/5.0")          # sem isso: 403 / 1010
    assert req["headers"]["Authorization"] == f"Bearer {CHAVE}"
    campos = dict((k, v) for k, v in req["campos"])
    assert campos["language"] == "pt"
    assert campos["prompt"] == prompt and "Claude Code" in campos["prompt"]
    assert campos["model"] == "whisper-large-v3-turbo"
    assert campos["response_format"] == "verbose_json"
    assert campos["temperature"] == "0"
    # word SOZINHO: pedir word junto com segment degrada o word-level (perde ~30%)
    granularidades = [v for k, v in req["campos"] if k == "timestamp_granularities[]"]
    assert granularidades == ["word"]
    assert palavras == [{"text": "Olá", "start": 0.0, "end": 0.4},
                        {"text": "mundo", "start": 0.5, "end": 0.9}]


def test_groq_a_chave_so_vai_no_header_nunca_nos_campos_ou_na_url(audio_groq, tmp_path):
    t = Transporte(_ok())
    _rodar(audio_groq, tmp_path, t)
    req = t.requisicoes[0]
    assert CHAVE not in req["url"]
    assert all(CHAVE not in str(v) for _, v in req["campos"])


def test_groq_comprime_para_mp3_mono_16k_antes_de_enviar(audio_groq, tmp_path):
    import subprocess
    t = Transporte(_ok())
    _rodar(audio_groq, tmp_path, t)
    enviado = Path(t.requisicoes[0]["arquivo"])
    assert enviado.suffix == ".mp3" and enviado.exists()
    assert (tmp_path / "t") in enviado.parents                  # dentro do workdir, nunca /tmp
    info = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                          "stream=sample_rate,channels", "-of", "csv=p=0", str(enviado)],
                          capture_output=True, text=True).stdout.strip()
    assert info == "16000,1"


def test_groq_devolve_monotonico_com_palavras_fora_de_ordem(audio_groq, tmp_path):
    ruim = [{"word": "um", "start": 0.0, "end": 0.7}, {"word": "dois", "start": 0.5, "end": 0.4},
            {"word": "três", "start": 0.45, "end": 1.0}]
    palavras, _ = _rodar(audio_groq, tmp_path, Transporte(_ok(ruim, "um dois três")))
    assert [p["text"] for p in palavras] == ["um", "dois", "três"]
    _monotonico(palavras)


def test_groq_um_retry_em_429_e_depois_funciona(audio_groq, tmp_path):
    t = Transporte((429, '{"error":{"message":"Rate limit reached. Please try again in 3s."}}'),
                   _ok())
    palavras, dormidas = _rodar(audio_groq, tmp_path, t)
    assert len(t.requisicoes) == 2 and len(palavras) == 2
    assert len(dormidas) == 1 and dormidas[0] >= 3


def test_groq_no_maximo_um_retry_dois_429_viram_erro(audio_groq, tmp_path):
    t = Transporte((429, "{}"), (429, "{}"), _ok())
    with pytest.raises(G.ErroGroq, match="429"):
        _rodar(audio_groq, tmp_path, t)
    assert len(t.requisicoes) == 2


def test_groq_limite_por_hora_com_espera_longa_nao_martela(audio_groq, tmp_path):
    corpo = '{"error":{"message":"Rate limit reached for ASPH. Please try again in 10m12s."}}'
    t = Transporte((429, corpo), _ok())
    with pytest.raises(G.ErroGroq, match="10m"):
        _rodar(audio_groq, tmp_path, t)
    assert len(t.requisicoes) == 1


def test_groq_outros_erros_nao_tem_retry_e_nao_vazam_a_chave(audio_groq, tmp_path):
    t = Transporte((500, "erro interno"), _ok())
    with pytest.raises(G.ErroGroq) as e:
        _rodar(audio_groq, tmp_path, t)
    assert "500" in str(e.value) and CHAVE not in str(e.value)
    assert len(t.requisicoes) == 1


def test_groq_403_aponta_o_user_agent(audio_groq, tmp_path):
    t = Transporte((403, "error code: 1010"))
    with pytest.raises(G.ErroGroq, match="1010"):
        _rodar(audio_groq, tmp_path, t)


def test_groq_resposta_que_ecoa_o_prompt_e_requisicao_malformada_nao_audio_vazio(
        audio_groq, tmp_path):
    prompt = "Transcrição em português do Brasil. Vocabulário: Claude."
    t = Transporte((200, json.dumps({"text": prompt, "words": []})))
    with pytest.raises(G.ErroGroq, match="prompt"):
        _rodar(audio_groq, tmp_path, t, prompt=prompt)


def test_groq_audio_sem_fala_devolve_lista_vazia(audio_groq, tmp_path):
    palavras, _ = _rodar(audio_groq, tmp_path, Transporte((200, '{"text":"","words":[]}')))
    assert palavras == []


def test_groq_texto_sem_palavras_e_erro_porque_nao_tem_tempo(audio_groq, tmp_path):
    t = Transporte((200, '{"text":"tem texto mas sem tempo"}'))
    with pytest.raises(G.ErroGroq, match="words"):
        _rodar(audio_groq, tmp_path, t)


def test_groq_resposta_que_nao_e_json_vira_erro_claro(audio_groq, tmp_path):
    with pytest.raises(G.ErroGroq, match="JSON"):
        _rodar(audio_groq, tmp_path, Transporte((200, "<html>")))


def test_groq_arquivo_acima_do_limite_pede_para_cortar(audio_groq, tmp_path, monkeypatch):
    monkeypatch.setattr(G, "LIMITE_BYTES", 10)
    with pytest.raises(G.ErroGroq, match="25"):
        _rodar(audio_groq, tmp_path, Transporte(_ok()))


def test_groq_sem_chave_da_erro_antes_de_qualquer_conversao(audio_groq, tmp_path):
    with pytest.raises(G.ErroGroq, match="GROQ_API_KEY"):
        G.transcrever(audio_groq, amb=amb(), workdir=tmp_path / "t", transporte=Transporte())


def test_groq_o_transporte_padrao_usa_curl_com_a_chave_fora_do_argv():
    """O corpo multipart NUNCA é montado à mão (200 ecoando o prompt): curl monta."""
    fonte = Path(G.__file__).read_text(encoding="utf-8")
    assert '"curl"' in fonte and "form-string" in fonte
    assert "multipart/form-data" not in fonte and "boundary" not in fonte
    cfg = G.config_curl({"url": "https://x/y", "headers": {"Authorization": f"Bearer {CHAVE}"},
                         "campos": [("prompt", 'diz "oi"; type=x\nlinha2'), ("language", "pt")],
                         "arquivo": "/pasta/a.mp3"})
    assert 'form-string = "prompt=diz \\"oi\\"; type=x\\nlinha2"' in cfg
    assert 'form = "file=@/pasta/a.mp3"' in cfg
    assert f'header = "Authorization: Bearer {CHAVE}"' in cfg      # vai por stdin (-K -)


# =========================== contrato comum ==================================================

@pytest.mark.parametrize("modulo,nome", [(PK, "parakeet"), (FW, "faster_whisper"), (G, "groq")])
def test_todo_backend_expoe_nome_disponivel_e_transcrever(modulo, nome):
    assert modulo.NOME == nome
    assert callable(modulo.disponivel) and callable(modulo.transcrever)


@pytest.mark.lento
def test_parakeet_real_no_apple_silicon(tmp_path):
    a = T.Ambiente.real()
    if not PK.disponivel(a):
        pytest.skip("parakeet-mlx não está instalado nesta máquina "
                    "(python3 -m pip install parakeet-mlx)")
    audio = fx.tom_com_pausas(tmp_path / "tom.wav", dur=2.0, pausas=())
    palavras = PK.transcrever(audio, amb=a, workdir=tmp_path / "t")
    assert isinstance(palavras, list)                    # um tom não tem fala: pode vir vazio
    for p in palavras:
        assert set(p) == {"text", "start", "end"}
