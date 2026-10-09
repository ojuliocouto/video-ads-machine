"""nucleo/asr (W2.D): o ASR do gravado passa por `audio.transcrever` e pelo glossário do projeto.

Antes havia um cliente Groq escrito à mão em nove arquivos, cada um com o vocabulário do
cliente dentro do prompt. Agora o prompt vem do glossário, o cache é por conteúdo e a escolha
do backend é a da máquina. Nenhum teste aqui usa rede: o backend é um objeto falso.
"""
import json
import wave
from pathlib import Path

import pytest

from audio.transcrever import Ambiente
from gravado.nucleo import asr
from gravado.veredito import InsumoInvalido
from tests.gravado import sintese as sx

GLOSSARIO = {"versao": 1, "termos": [{"grafia": "Fluxa", "variantes": ["Flucha"], "tipo": "marca"}]}


class BackendFalso(object):
    """Registra o que recebeu e devolve palavras prontas."""
    NOME = "falso"

    def __init__(self, palavras=None, erro=None):
        self.palavras = palavras if palavras is not None else [
            {"text": "olá", "start": 0.1, "end": 0.5}, {"text": "mundo", "start": 0.6, "end": 1.0}]
        self.erro = erro
        self.chamadas = []
        self.duracoes = []
        self.prompts = []

    def transcrever(self, audio, *, amb, workdir, prompt="", idioma="pt"):
        self.chamadas.append(str(audio))
        self.prompts.append(prompt)
        with wave.open(str(audio), "rb") as w:
            self.duracoes.append((w.getnframes() / float(w.getframerate()), w.getnchannels(),
                                  w.getframerate()))
        if self.erro:
            raise self.erro
        return [dict(p) for p in self.palavras]


def _leitor(tmp_path, backend, glossario=None):
    return asr.Leitor(tmp_path / "cache", glossario=glossario, backend=backend)


def _audio(tmp_path, dur=6.0):
    return sx.audio_por_blocos(tmp_path / "a.wav", [(dur, -12.0)])


def test_trecho_e_recortado_com_margem_em_wav_16k_mono(tmp_path):
    bk = BackendFalso()
    leitor = _leitor(tmp_path, bk)
    leitor.texto(_audio(tmp_path), 2.0, 4.0)
    dur, canais, sr = bk.duracoes[0]
    assert dur == pytest.approx(2.0 + 2 * 0.1, abs=0.02)
    assert (canais, sr) == (1, 16000)


def test_tempos_das_palavras_voltam_para_o_eixo_do_arquivo(tmp_path):
    bk = BackendFalso()
    leitor = _leitor(tmp_path, bk)
    palavras = leitor.palavras_do_trecho(_audio(tmp_path), 3.0, 5.0)
    # o recorte começa em 2,9 s: a palavra em 0,1 s do recorte está em 3,0 s do arquivo
    assert palavras[0]["start"] == pytest.approx(3.0)
    assert palavras[1]["end"] == pytest.approx(3.9)


def test_trecho_no_comeco_do_arquivo_nao_recua_para_antes_de_zero(tmp_path):
    bk = BackendFalso()
    leitor = _leitor(tmp_path, bk)
    palavras = leitor.palavras_do_trecho(_audio(tmp_path), 0.05, 1.5)
    assert palavras[0]["start"] == pytest.approx(0.1)          # o recorte começa em 0
    dur = bk.duracoes[0][0]
    assert dur == pytest.approx(1.5 + 0.1, abs=0.02)


def test_mesma_janela_nao_vai_duas_vezes_ao_backend(tmp_path):
    bk = BackendFalso()
    leitor = _leitor(tmp_path, bk)
    audio = _audio(tmp_path)
    a = leitor.texto(audio, 1.0, 3.0)
    b = leitor.texto(audio, 1.0, 3.0)
    assert a == b == "olá mundo"
    assert len(bk.chamadas) == 1
    leitor.texto(audio, 1.0, 3.5)
    assert len(bk.chamadas) == 2


def test_glossario_corrige_a_saida_e_alimenta_o_prompt(tmp_path):
    bk = BackendFalso(palavras=[{"text": "Flucha", "start": 0.1, "end": 0.6}])
    leitor = _leitor(tmp_path, bk, GLOSSARIO)
    assert leitor.texto(_audio(tmp_path), 0.0, 2.0) == "Fluxa"
    assert "Fluxa" in bk.prompts[0] and "Flucha" not in bk.prompts[0]


def test_peca_inteira_devolve_o_texto_das_palavras(tmp_path):
    bk = BackendFalso()
    leitor = _leitor(tmp_path, bk)
    assert leitor.texto_da_peca(_audio(tmp_path)) == "olá mundo"
    assert [p["text"] for p in leitor.palavras(_audio(tmp_path))] == ["olá", "mundo"]


def test_falha_do_backend_vira_erro_de_asr_com_o_motivo(tmp_path):
    leitor = _leitor(tmp_path, BackendFalso(erro=RuntimeError("HTTP 429 da Groq")))
    with pytest.raises(asr.ErroDeASR) as e:
        leitor.texto(_audio(tmp_path), 0.0, 2.0)
    assert "429" in str(e.value)


def test_fala_ou_falha_devolve_o_marcador_em_vez_de_levantar(tmp_path):
    ruim = _leitor(tmp_path, BackendFalso(erro=RuntimeError("sem rede")))
    texto = ruim.fala_ou_falha(_audio(tmp_path))
    assert texto.startswith(asr.FALHA) and "sem rede" in texto
    bom = _leitor(tmp_path / "b", BackendFalso())
    assert bom.fala_ou_falha(_audio(tmp_path)) == "olá mundo"


def test_falhou_reconhece_o_marcador_o_vazio_e_a_falha_antiga():
    for ruim in ("", "   ", "FALHA: HTTP 429", "FALHA", "[falha]", "[falha: x]"):
        assert asr.falhou(ruim), ruim
    for bom in ("olá mundo", "a falha é nossa", "fala"):
        assert not asr.falhou(bom), bom


def test_falas_dos_arquivos_mistura_texto_e_marcador(tmp_path):
    bom, ruim = tmp_path / "bom", tmp_path / "ruim"
    bom.mkdir(), ruim.mkdir()
    a = sx.audio_por_blocos(bom / "A1_normal.wav", [(2.0, -12.0)])
    b = sx.audio_por_blocos(ruim / "A2_normal.wav", [(2.0, -12.0)])

    class Misto(object):
        def fala_ou_falha(self, arquivo):
            return "olá mundo" if "bom" in str(arquivo) else "FALHA: sem rede"

    falas = asr.falas_dos_arquivos([a, b], Misto())
    assert falas == {"A1_normal": "olá mundo", "A2_normal": "FALHA: sem rede"}


def test_janelas_sobrepostas_cobrem_cada_emenda_com_margem(tmp_path):
    jan = asr.janelas(20.0, janela=8.0, passo=6.0)
    assert jan[0][0] == 0.0 and jan[-1][1] == pytest.approx(20.0)
    for i in range(10, 191):
        t = i * 0.1                                  # qualquer instante de 1,0 s a 19,0 s
        assert any(a + 1.0 - 1e-9 <= t <= b - 1.0 + 1e-9 for a, b in jan), t


def test_borda_de_palavra_exige_backend_que_nao_infla_token():
    groq_so = Ambiente("Darwin", "arm64", {"GROQ_API_KEY": "x"}, which=lambda n: None,
                       importavel=lambda m: False)
    with pytest.raises(asr.ErroDeASR) as e:
        asr.checar_borda(groq_so)
    assert "parakeet" in str(e.value) and "faster-whisper" in str(e.value)
    com_parakeet = Ambiente("Darwin", "arm64", {}, which=lambda n: "/x/parakeet-mlx" if n == "parakeet-mlx" else None,
                            importavel=lambda m: False)
    assert asr.checar_borda(com_parakeet) == "parakeet"
    com_whisper = Ambiente("Linux", "x86_64", {}, which=lambda n: None,
                           importavel=lambda m: m == "faster_whisper")
    assert asr.checar_borda(com_whisper) == "faster_whisper"


def test_sem_nenhum_backend_a_mensagem_e_uma_so_com_o_comando():
    vazio = Ambiente("Linux", "x86_64", {}, which=lambda n: None, importavel=lambda m: False)
    with pytest.raises(asr.ErroDeASR) as e:
        asr.checar_borda(vazio)
    assert str(e.value).count("pip install") == 1


# --- falas_entregues.json: o insumo dos gates de repetição e fora do roteiro -----------------

def _json(tmp_path, conteudo, nome="falas.json"):
    arq = tmp_path / nome
    arq.write_text(conteudo if isinstance(conteudo, str) else json.dumps(conteudo), encoding="utf-8")
    return arq


def test_carregar_falas_valido_devolve_o_dict(tmp_path):
    arq = _json(tmp_path, {"A1_normal": "olá mundo"})
    assert asr.carregar_falas(arq) == {"A1_normal": "olá mundo"}


@pytest.mark.parametrize("conteudo,pedaco", [
    ({}, "vazio"),
    ([], "objeto"),
    ({"A1": ""}, "A1"),
    ({"A1": "FALHA: HTTP 429", "A2": "ok"}, "A1"),
    ({"A1": 7}, "A1"),
    ("{quebrado", "JSON"),
])
def test_carregar_falas_insumo_invalido_diz_o_que_esta_errado(tmp_path, conteudo, pedaco):
    arq = _json(tmp_path, conteudo)
    with pytest.raises(InsumoInvalido) as e:
        asr.carregar_falas(arq)
    assert pedaco in str(e.value)


def test_carregar_falas_arquivo_ausente_e_insumo_invalido(tmp_path):
    with pytest.raises(InsumoInvalido) as e:
        asr.carregar_falas(tmp_path / "nao_existe.json")
    assert "nao_existe.json" in str(e.value)


def test_nenhum_cliente_de_asr_proprio_no_gravado():
    """Tudo passa por audio.transcrever: nada de URL de ASR nem de modelo escrito à mão."""
    raiz = Path(__file__).resolve().parents[2] / "scripts" / "gravado"
    for arq in sorted(raiz.rglob("*.py")):
        texto = arq.read_text(encoding="utf-8")
        assert "api.groq.com" not in texto, arq
        assert "whisper-large" not in texto, arq
