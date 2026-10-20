"""Os passos que transcrevem passam pelo seletor de backend (a Groq por padrão, em todos os sistemas).

Quatro passos transcrevem: o alinhamento da footage (`footage.blocos.alinhar`), o corte de ar morto
(`cortar_ar_morto`), a auditoria de áudio (`auditar_audio`) e a transcrição do overlay. Cada um pergunta ao
`audio.transcrever` qual backend existe: a Groq (nuvem, plano gratuito, com GROQ_API_KEY) e, só se o aluno
instalou, o faster-whisper offline.

Regra que estes testes seguram: o corte de take USA a Groq (decisão do dono, 20/10/2026) e compensa o início de
palavra tardio com margem (`ar_morto.margens_de_palavra`) e com o gate que re-transcreve o corte.

Nenhum áudio real, nenhum modelo, nenhuma rede: o backend é um espião.
"""
import json
from pathlib import Path

import pytest

import auditar_audio as AA
import cortar_ar_morto as CAM
from audio import transcrever as T
from audio.backends import faster_whisper as FW
from footage import blocos as BL
from footage import cadeia as CA

SAIDA_EM_TOKENS = {"text": "Olá mundo agora.", "sentences": [
    {"text": "Olá mundo agora.", "start": 0.0, "end": 1.5, "tokens": [
        {"text": " Olá", "start": 0.0, "end": 0.4}, {"text": " mundo", "start": 0.5, "end": 0.9},
        {"text": " agora.", "start": 1.0, "end": 1.5}]}]}

PALAVRAS = [{"text": "Olá", "start": 0.0, "end": 0.4},
            {"text": "mundo", "start": 0.5, "end": 0.9},
            {"text": "agora.", "start": 1.0, "end": 1.5}]


def ambiente(sistema="Linux", arquitetura="x86_64", modulos=(), env=None):
    return T.Ambiente(sistema=sistema, arquitetura=arquitetura, env=dict(env or {}),
                      which=lambda nome: None, importavel=lambda m: m in modulos)


class BackendFalso:
    """Um backend do seletor que devolve palavras prontas e anota o que recebeu."""

    def __init__(self, nome="groq", palavras=None):
        self.NOME = nome
        self.palavras = PALAVRAS if palavras is None else palavras
        self.chamadas = []

    def disponivel(self, amb):
        return True

    def transcrever(self, audio, *, amb, workdir, prompt="", idioma="pt", **extra):
        self.chamadas.append({"audio": str(audio), "idioma": idioma, **extra})
        return [dict(p) for p in self.palavras]


# =========================== faster-whisper (opcional): idioma sempre pt ========================

class _Seg:
    def __init__(self):
        self.text, self.start, self.end, self.words = " oi", 0.0, 0.5, None


class _Modelo:
    def __init__(self):
        self.kw = None

    def transcribe(self, caminho, **kw):
        self.kw = kw
        return iter([_Seg()]), object()


@pytest.mark.parametrize("pedido", [None, "", "auto", "AUTO"])
def test_faster_whisper_sem_idioma_explicito_forca_pt(tmp_path, pedido):
    modelo = _Modelo()
    FW.transcrever(tmp_path / "a.wav", amb=ambiente(), workdir=tmp_path, idioma=pedido,
                   fabrica_modelo=lambda: modelo)
    assert modelo.kw["language"] == "pt"


def test_faster_whisper_respeita_um_idioma_explicito(tmp_path):
    modelo = _Modelo()
    FW.transcrever(tmp_path / "a.wav", amb=ambiente(), workdir=tmp_path, idioma="en",
                   fabrica_modelo=lambda: modelo)
    assert modelo.kw["language"] == "en"


# =========================== footage.blocos.alinhar ============================================

def test_alinhar_usa_o_seletor_sem_subprocesso_e_casa_o_roteiro(tmp_path):
    falso = BackendFalso()
    avatar = tmp_path / "avatar.mp4"
    avatar.write_bytes(b"av")
    out = BL.alinhar(str(avatar), ["Olá", "mundo", "agora"], str(tmp_path), duracao=lambda a: 1.5,
                     amb=ambiente(), backend=falso)
    assert [(s, e, t) for s, e, t in out] == [(0.0, 0.4, "Olá"), (0.5, 0.9, "mundo"), (1.0, 1.5, "agora")]
    assert falso.chamadas[0]["idioma"] == "pt"
    assert falso.chamadas[0]["audio"] == str(avatar)


def test_alinhar_sem_nenhum_transcritor_da_o_conserto_na_mensagem(tmp_path):
    avatar = tmp_path / "avatar.mp4"
    avatar.write_bytes(b"av")
    with pytest.raises(CA.ErroFootage) as e:
        BL.alinhar(str(avatar), ["oi"], str(tmp_path), duracao=lambda a: 1.0, amb=ambiente())
    assert "console.groq.com" in str(e.value) and "GROQ_API_KEY" in str(e.value)


# =========================== cortar_ar_morto ===================================================

def test_corte_converte_o_seletor_para_o_json_de_sentencas_e_tokens(tmp_path):
    falso = BackendFalso()
    wav = tmp_path / "bruto.wav"
    wav.write_bytes(b"RIFF")
    j = CAM.transcrever(str(wav), str(tmp_path), amb=ambiente(), backend=falso)
    assert j == str(tmp_path / "bruto.json")
    # o downstream (tokens_de, texto_de, blocos_de_fala) lê a mesma forma de sempre
    assert CAM.tokens_de(j) == [(0.0, 0.4, " Olá"), (0.5, 0.9, " mundo"), (1.0, 1.5, " agora.")]
    assert CAM.blocos_de_fala(CAM.tokens_de(j)) == [(0.0, 0.4), (0.5, 0.9), (1.0, 1.5)]
    assert CAM.texto_de(j) == "Olá mundo agora."
    assert falso.chamadas[0]["idioma"] == "pt"


def test_corte_de_take_aceita_a_groq(tmp_path):
    """Decisão do dono (20/10/2026): tudo roda na nuvem. A Groq serve para cortar, com margem de palavra."""
    wav = tmp_path / "bruto.wav"
    wav.write_bytes(b"RIFF")
    groq = BackendFalso(nome="groq")
    j = CAM.transcrever(str(wav), str(tmp_path), amb=ambiente(env={"GROQ_API_KEY": "gsk_falsa"}), backend=groq)
    assert CAM.texto_de(j) == "Olá mundo agora." and groq.chamadas


def test_corte_sem_nenhum_transcritor_sai_com_o_conserto_da_chave_gratis(tmp_path):
    wav = tmp_path / "bruto.wav"
    wav.write_bytes(b"RIFF")
    with pytest.raises(SystemExit) as e:
        CAM.transcrever(str(wav), str(tmp_path), amb=ambiente())
    assert "console.groq.com" in str(e.value) and "GROQ_API_KEY" in str(e.value)


def test_corte_le_json_de_transcricao_em_utf8(tmp_path):
    j = tmp_path / "t.json"
    j.write_text(json.dumps(SAIDA_EM_TOKENS, ensure_ascii=False), encoding="utf-8")
    assert CAM.texto_de(str(j)) == "Olá mundo agora."


# --- o gate que re-transcreve o corte: sumiu ou encurtou palavra reprova ----------------------------

def _p(texto):
    return texto.split()


def test_gate_aprova_quando_nenhuma_palavra_sumiu():
    assert CAM.gate_de_palavras(_p("você perde três horas por dia"), _p("você perde três horas por dia")) == []


def test_gate_reprova_palavra_que_sumiu():
    danos = CAM.gate_de_palavras(_p("você não comprou nada hoje"), _p("você comprou nada hoje"))
    assert danos and "não" not in danos[0][1]


def test_gate_reprova_palavra_encurtada():
    danos = CAM.gate_de_palavras(_p("quero vender mais hoje"), _p("quero ver mais hoje"))
    assert danos == [("vender", "ver")]


def test_gate_nao_reprova_ruido_de_palavra_curta_de_funcao():
    assert CAM.gate_de_palavras(_p("eu vendo um curso"), _p("eu vendo curso")) == []


# =========================== auditar_audio =====================================================

def test_auditoria_usa_o_seletor_e_normaliza(tmp_path):
    falso = BackendFalso()
    mp3 = tmp_path / "voz.mp3"
    mp3.write_bytes(b"ID3")
    palavras = AA._transcrever(mp3, amb=ambiente(), backend=falso)
    assert palavras == ["olá", "mundo", "agora"]
    assert falso.chamadas[0]["idioma"] == "pt"


def test_auditoria_sem_nenhum_transcritor_avisa_alto_e_nao_quebra(tmp_path, capsys):
    mp3 = tmp_path / "voz.mp3"
    mp3.write_bytes(b"ID3")
    assert AA._transcrever(mp3, amb=ambiente()) is None
    err = capsys.readouterr().err
    assert "console.groq.com" in err and "GROQ_API_KEY" in err


def test_auditoria_nao_tem_mais_tmp_cravado():
    fonte = Path(AA.__file__).read_text(encoding="utf-8")
    assert '"/tmp"' not in fonte and "'/tmp'" not in fonte


# --- o JSON do corte guarda quem fez o tempo (a margem de palavra depende dele) ------------------------

def test_corte_grava_o_backend_no_json_e_le_de_volta(tmp_path):
    wav = tmp_path / "bruto.wav"
    wav.write_bytes(b"RIFF")
    j = CAM.transcrever(str(wav), str(tmp_path), amb=ambiente(), backend=BackendFalso(nome="mistral"))
    assert CAM.backend_de(j) == "mistral"
    externo = tmp_path / "externo.json"
    externo.write_text(json.dumps(SAIDA_EM_TOKENS), encoding="utf-8")
    assert CAM.backend_de(str(externo)) is None, "JSON de fora não diz quem fez: vale o pré-roll padrão"


def test_leitor_do_gravado_guarda_o_backend_da_ultima_leitura(tmp_path):
    from gravado.nucleo import asr
    leitor = asr.Leitor(tmp_path / "cache", backend=BackendFalso(nome="groq"), amb=ambiente())
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    assert leitor.ultimo_backend is None
    leitor._transcrever(wav)
    assert leitor.ultimo_backend == "groq"
