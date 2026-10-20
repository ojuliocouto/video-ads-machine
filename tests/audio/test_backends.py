"""Backends de transcrição: faster-whisper (local, o padrão) e Groq (nuvem, opcional).

Tudo hermético: o faster-whisper é uma classe falsa e o HTTP da Groq é um transporte injetado.
Nenhuma chamada paga, nenhuma rede, nenhum download de modelo.
"""
import json
from pathlib import Path

import pytest

from audio import transcrever as T
from audio.backends import faster_whisper as FW
from audio.backends import groq as G
from audio.backends import mistral as M
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


def amb(sistema="Darwin", arquitetura="arm64", executaveis=(), modulos=(), env=None):
    return T.Ambiente(
        sistema=sistema, arquitetura=arquitetura, env=dict(env or {}),
        which=lambda nome: (f"/falso/bin/{nome}" if nome in executaveis else None),
        importavel=lambda nome: nome in modulos)


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


def test_groq_junta_numero_e_percentual_tambem(audio_groq, tmp_path):
    t = Transporte(_ok([{"word": "cai", "start": 0.0, "end": 0.3}, {"word": "1", "start": 0.4, "end": 0.6},
                        {"word": "%", "start": 0.6, "end": 0.9}]))
    palavras, _ = _rodar(audio_groq, tmp_path, t)
    assert [p["text"] for p in palavras] == ["cai", "1%"]


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


# --- faster-whisper: o modelo é UMA constante, com override por variável -------------------------

def test_o_modelo_do_faster_whisper_e_uma_constante_so_o_large_v3_turbo():
    assert FW.MODELO_PADRAO == "large-v3-turbo"
    assert (FW.COMPUTE, FW.IDIOMA_PADRAO) == ("int8", "pt")
    fonte = Path(FW.__file__).read_text(encoding="utf-8")
    assert fonte.count('"large-v3-turbo"') == 1, "o nome do modelo mora num lugar só"


def test_variavel_vam_whisper_modelo_troca_o_modelo_e_vazia_nao_conta():
    assert FW.VARIAVEL_DO_MODELO == "VAM_WHISPER_MODELO"
    assert FW.modelo_configurado(amb()) == "large-v3-turbo"
    assert FW.modelo_configurado(amb(env={"VAM_WHISPER_MODELO": "small"})) == "small"
    assert FW.modelo_configurado(amb(env={"VAM_WHISPER_MODELO": "   "})) == "large-v3-turbo"


def test_a_fabrica_real_carrega_o_modelo_configurado_em_cpu_int8(monkeypatch):
    import sys
    import types
    carregados = []

    class WhisperModel:
        def __init__(self, nome, **kw):
            carregados.append((nome, kw))

    falso = types.ModuleType("faster_whisper")
    falso.WhisperModel = WhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", falso)
    FW._fabrica_real(amb())()
    FW._fabrica_real(amb(env={"VAM_WHISPER_MODELO": "medium"}))()
    assert carregados == [("large-v3-turbo", {"device": "cpu", "compute_type": "int8"}),
                          ("medium", {"device": "cpu", "compute_type": "int8"})]


def test_modelo_que_nao_carrega_vira_erro_claro_com_o_tamanho_do_download(tmp_path):
    def fabrica():
        raise OSError("sem rede")
    audio = fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=())
    with pytest.raises(FW.ErroFasterWhisper) as e:
        FW.transcrever(audio, amb=amb(), workdir=tmp_path, fabrica_modelo=fabrica)
    msg = str(e.value)
    assert "large-v3-turbo" in msg and "1,5 GB" in msg and "sem rede" in msg
    assert "\n" not in msg.strip()


def test_faster_whisper_liga_o_vad_e_pede_tempo_por_palavra(tmp_path):
    modelo = ModeloFalso([Segmento(" Olá", 0.3, 0.8, [Palavra(" Olá", 0.3, 0.8)])])
    audio = fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=())
    FW.transcrever(audio, amb=amb(), workdir=tmp_path, fabrica_modelo=lambda: modelo)
    kw = modelo.chamado[1]
    assert kw["vad_filter"] is True
    assert kw["word_timestamps"] is True and kw["language"] == "pt"


def test_idioma_auto_ou_vazio_continua_em_portugues(tmp_path):
    audio = fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=())
    for pedido in (None, "", "auto", "AUTO"):
        modelo = ModeloFalso([Segmento(" a", 0.0, 0.5, [Palavra(" a", 0.0, 0.5)])])
        FW.transcrever(audio, amb=amb(), workdir=tmp_path, idioma=pedido, fabrica_modelo=lambda: modelo)
        assert modelo.chamado[1]["language"] == "pt"


# --- faster-whisper: "1 %" vira "1%" (medido: os três modelos escrevem com espaço) ---------------

def test_numero_e_percentual_separados_viram_uma_palavra(tmp_path):
    modelo = ModeloFalso([Segmento(" cai 1 % ao dia", 0.0, 2.0, [
        Palavra(" cai", 0.0, 0.4), Palavra(" 1", 0.5, 0.8), Palavra(" %", 0.8, 1.2),
        Palavra(" ao", 1.3, 1.5), Palavra(" dia", 1.5, 2.0)])])
    audio = fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=())
    palavras = FW.transcrever(audio, amb=amb(), workdir=tmp_path, fabrica_modelo=lambda: modelo)
    assert [p["text"] for p in palavras] == ["cai", "1%", "ao", "dia"]
    junto = palavras[1]
    assert (junto["start"], junto["end"]) == (0.5, 1.2), "o tempo cobre o número e o símbolo"
    _monotonico(palavras)


def test_percentual_com_pontuacao_e_decimal_tambem_juntam(tmp_path):
    modelo = ModeloFalso([Segmento(" é 1,5 %.", 0.0, 2.0, [
        Palavra(" é", 0.0, 0.2), Palavra(" 1,5", 0.3, 0.7), Palavra(" %.", 0.7, 1.1)])])
    audio = fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=())
    palavras = FW.transcrever(audio, amb=amb(), workdir=tmp_path, fabrica_modelo=lambda: modelo)
    assert [p["text"] for p in palavras] == ["é", "1,5%."]


def test_percentual_sem_tempo_por_palavra_tambem_juntam(tmp_path):
    modelo = ModeloFalso([Segmento(" de 10 % hoje", 0.0, 4.0, None)])
    audio = fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=())
    palavras = FW.transcrever(audio, amb=amb(), workdir=tmp_path, fabrica_modelo=lambda: modelo)
    assert [p["text"] for p in palavras] == ["de", "10%", "hoje"]


def test_normalizacao_nao_mexe_no_que_nao_e_numero_com_percentual():
    brutas = [{"text": "por", "start": 0.0, "end": 0.2}, {"text": "cento", "start": 0.2, "end": 0.5},
              {"text": "%", "start": 0.6, "end": 0.7},                      # sozinho: nada antes para juntar
              {"text": "1", "start": 1.0, "end": 1.2}, {"text": "real", "start": 1.2, "end": 1.6}]
    assert [p["text"] for p in FW.normalizar_numeros(brutas)] == ["por", "cento", "%", "1", "real"]
    assert FW.normalizar_numeros([]) == []


# --- contrato comum ----------------------------------------------------------------------------

@pytest.mark.parametrize("modulo,nome", [(FW, "faster_whisper"), (G, "groq"), (M, "mistral")])
def test_todo_backend_expoe_nome_disponivel_e_transcrever(modulo, nome):
    assert modulo.NOME == nome
    assert callable(modulo.disponivel) and callable(modulo.transcrever)


def test_so_existem_tres_backends_faster_whisper_groq_e_mistral():
    pasta = Path(FW.__file__).parent
    assert sorted(p.stem for p in pasta.glob("*.py") if p.stem != "__init__") == ["faster_whisper", "groq", "mistral"]


# =========================== Mistral (Voxtral Mini Transcribe) =================================

CHAVE_M = "mstrl_chave_de_teste_nao_real"
# O formato REAL medido em 20/10/2026 com timestamp_granularities[]=word: cada segmento é uma palavra.
RESPOSTA_REAL = {
    "model": "voxtral-mini-latest", "text": "Uma skill de criação cai 1 % hoje.", "language": None,
    "segments": [
        {"type": "transcription_segment", "text": "Uma", "start": 0.7, "end": 0.8, "speaker_id": None},
        {"type": "transcription_segment", "text": " skill", "start": 0.8, "end": 1.1, "speaker_id": None},
        {"type": "transcription_segment", "text": " cai", "start": 1.3, "end": 1.5, "speaker_id": None},
        {"type": "transcription_segment", "text": " 1", "start": 1.5, "end": 1.7, "speaker_id": None},
        {"type": "transcription_segment", "text": " %", "start": 1.7, "end": 1.9, "speaker_id": None},
        {"type": "transcription_segment", "text": " hoje.", "start": 2.0, "end": 2.4, "speaker_id": None},
    ],
    "usage": {"prompt_audio_seconds": 3},
}


def _rodar_m(audio, tmp_path, transporte, dormidas=None):
    return M.transcrever(audio, amb=amb(env={"MISTRAL_API_KEY": CHAVE_M}), workdir=tmp_path / "t",
                         transporte=transporte, dormir=(dormidas if dormidas is not None else []).append)


def test_mistral_disponivel_so_com_chave():
    assert M.disponivel(amb(env={"MISTRAL_API_KEY": CHAVE_M}))
    assert not M.disponivel(amb()) and not M.disponivel(amb(env={"MISTRAL_API_KEY": "  "}))


def test_mistral_manda_modelo_palavra_e_nunca_language(audio_groq, tmp_path):
    t = Transporte((200, json.dumps(RESPOSTA_REAL)))
    _rodar_m(audio_groq, tmp_path, t)
    req = t.requisicoes[0]
    assert req["url"] == "https://api.mistral.ai/v1/audio/transcriptions"
    assert req["headers"]["Authorization"] == f"Bearer {CHAVE_M}"
    campos = dict((k, v) for k, v in req["campos"])
    assert campos["model"] == M.MODELO == "voxtral-mini-latest"
    assert [v for k, v in req["campos"] if k == "timestamp_granularities[]"] == ["word"]
    assert "language" not in campos, "a documentação: timestamp por palavra não combina com language"
    assert CHAVE_M not in json.dumps(req["campos"]) and CHAVE_M not in req["url"]


def test_mistral_le_o_formato_real_um_segmento_por_palavra_e_junta_o_percentual(audio_groq, tmp_path):
    palavras = _rodar_m(audio_groq, tmp_path, Transporte((200, json.dumps(RESPOSTA_REAL))))
    assert [p["text"] for p in palavras] == ["Uma", "skill", "cai", "1%", "hoje."]
    assert palavras[0] == {"text": "Uma", "start": 0.7, "end": 0.8}
    _monotonico(palavras)


def test_mistral_parser_defensivo_aceita_words_no_topo_e_dentro_do_segmento():
    topo = {"words": [{"word": "oi", "start": 0.0, "end": 0.2}, {"text": "mundo", "start": 0.3, "end": 0.6}]}
    assert [p["text"] for p in M.palavras_da_resposta(topo)] == ["oi", "mundo"]
    aninhado = {"segments": [{"text": "oi mundo", "start": 0.0, "end": 1.0,
                              "words": [{"word": "oi", "start": 0.0, "end": 0.4}, {"word": "mundo", "start": 0.5, "end": 1.0}]}]}
    assert [p["text"] for p in M.palavras_da_resposta(aninhado)] == ["oi", "mundo"]
    assert M.palavras_da_resposta({"text": "só texto"}) == [] and M.palavras_da_resposta("lixo") == []


def test_mistral_segmento_de_frase_inteira_divide_o_tempo_entre_as_palavras():
    palavras = M.palavras_da_resposta({"segments": [{"text": "um dois", "start": 1.0, "end": 2.0}]})
    assert [(p["text"], p["start"], p["end"]) for p in palavras] == [("um", 1.0, 1.5), ("dois", 1.5, 2.0)]


def test_mistral_texto_sem_tempo_por_palavra_e_erro_claro(audio_groq, tmp_path):
    with pytest.raises(M.ErroMistral, match="palavras com tempo"):
        _rodar_m(audio_groq, tmp_path, Transporte((200, json.dumps({"text": "Olá mundo", "segments": []}))))


def test_mistral_audio_sem_fala_devolve_lista_vazia(audio_groq, tmp_path):
    assert _rodar_m(audio_groq, tmp_path, Transporte((200, json.dumps({"text": "", "segments": []})))) == []


CAPACIDADE = json.dumps({"object": "error", "message": "Not enough capacity available", "code": "3505",
                         "type": "backend_out_of_capacity", "raw_status_code": 429})


def test_mistral_401_vira_erro_sem_retry_e_sem_vazar_a_chave(audio_groq, tmp_path):
    dormidas = []
    t = Transporte((401, '{"detail":"Invalid API Key"}'))
    with pytest.raises(M.ErroMistral) as e:
        _rodar_m(audio_groq, tmp_path, t, dormidas)
    assert "401" in str(e.value) and CHAVE_M not in str(e.value)
    assert dormidas == [] and len(t.requisicoes) == 1


def test_mistral_429_faz_um_retry_depois_de_20_s_e_funciona(audio_groq, tmp_path):
    dormidas = []
    t = Transporte((429, CAPACIDADE), (200, json.dumps(RESPOSTA_REAL)))
    palavras = _rodar_m(audio_groq, tmp_path, t, dormidas)
    assert dormidas == [20.0] and len(t.requisicoes) == 2 and palavras[0]["text"] == "Uma"


def test_mistral_429_duas_vezes_vira_erro_para_o_seletor_cair_na_groq(audio_groq, tmp_path):
    dormidas = []
    t = Transporte((429, CAPACIDADE), (429, CAPACIDADE))
    with pytest.raises(M.ErroMistral, match="429"):
        _rodar_m(audio_groq, tmp_path, t, dormidas)
    assert dormidas == [20.0] and len(t.requisicoes) == 2, "no máximo UM retry"


def test_mistral_palavra_de_duracao_zero_ganha_a_largura_da_grade(audio_groq, tmp_path):
    resposta = {"text": "e agora", "segments": [
        {"type": "transcription_segment", "text": " e", "start": 5.6, "end": 5.6},
        {"type": "transcription_segment", "text": " agora", "start": 5.9, "end": 6.3}]}
    palavras = _rodar_m(audio_groq, tmp_path, Transporte((200, json.dumps(resposta))))
    assert palavras[0] == {"text": "e", "start": 5.6, "end": pytest.approx(5.7)}


def test_mistral_resposta_que_nao_e_json_vira_erro_claro(audio_groq, tmp_path):
    with pytest.raises(M.ErroMistral, match="não é JSON"):
        _rodar_m(audio_groq, tmp_path, Transporte((200, "<html>")))


def test_mistral_sem_chave_da_erro_antes_de_converter(audio_groq, tmp_path):
    with pytest.raises(M.ErroMistral, match="MISTRAL_API_KEY"):
        M.transcrever(audio_groq, amb=amb(), workdir=tmp_path / "t", transporte=Transporte())
