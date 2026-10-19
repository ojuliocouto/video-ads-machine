"""Os passos que transcrevem passam pelo seletor de backend (porte Windows e Linux, Wave 1 unidade E).

Antes, quatro passos exigiam o parakeet-mlx (Apple Silicon): o alinhamento da footage (`footage.blocos.alinhar`), o corte
de ar morto (`cortar_ar_morto`), a auditoria de áudio (`auditar_audio`) e a transcrição do overlay. No Windows e no Linux
eles quebravam. Agora cada um pergunta ao `audio.transcrever` qual backend existe na máquina (parakeet, depois
faster-whisper, depois Groq).

Duas regras que estes testes seguram:
  - No Mac com parakeet o resultado é o MESMO de antes (mesmo comando, mesmo arquivo, mesma estrutura).
  - O corte de take recusa a Groq (o tempo por palavra dela não é confiável para cortar).

Nenhum áudio real, nenhum modelo: o parakeet é um script falso que copia uma saída de fixture, o resto é espião.
"""
import json
import os
from pathlib import Path

import pytest

import plataforma
import auditar_audio as AA
import cortar_ar_morto as CAM
from audio import transcrever as T
from audio.backends import faster_whisper as FW
from footage import blocos as BL
from footage import cadeia as CA

# Saída real do parakeet-mlx: sentenças com tokens (token com espaço na frente abre palavra).
SAIDA_PARAKEET = {"text": "Olá mundo agora.", "sentences": [
    {"text": "Olá mundo agora.", "start": 0.0, "end": 1.5, "tokens": [
        {"text": " Ol", "start": 0.0, "end": 0.2}, {"text": "á", "start": 0.2, "end": 0.4},
        {"text": " mun", "start": 0.5, "end": 0.7}, {"text": "do", "start": 0.7, "end": 0.9},
        {"text": " agora.", "start": 1.0, "end": 1.5}]}]}
TEXTO_PARAKEET = "Olá, mundo agora."

PALAVRAS = [{"text": "Olá", "start": 0.0, "end": 0.4},
            {"text": "mundo", "start": 0.5, "end": 0.9},
            {"text": "agora.", "start": 1.0, "end": 1.5}]

so_unix = pytest.mark.skipif(plataforma.eh_windows(),
                             reason="o parakeet falso é um script sh (o parakeet só roda no Mac)")


def ambiente(sistema="Linux", arquitetura="x86_64", exes=None, modulos=(), env=None):
    exes = exes or {}
    return T.Ambiente(sistema=sistema, arquitetura=arquitetura, env=dict(env or {}),
                      which=lambda nome: exes.get(nome), importavel=lambda m: m in modulos)


class BackendFalso:
    """Um backend do seletor que devolve palavras prontas e anota o que recebeu."""

    def __init__(self, nome="faster_whisper", palavras=None):
        self.NOME = nome
        self.palavras = PALAVRAS if palavras is None else palavras
        self.chamadas = []

    def disponivel(self, amb):
        return True

    def transcrever(self, audio, *, amb, workdir, prompt="", idioma="pt", **extra):
        self.chamadas.append({"audio": str(audio), "idioma": idioma, **extra})
        return [dict(p) for p in self.palavras]


def parakeet_falso(pasta):
    """Cria um `parakeet-mlx` falso que copia `saida.json` ou `saida.txt` (conforme --output-format) para a pasta de
    saída, com o nome do áudio. Anota os argumentos em `chamadas.txt`. Devolve (caminho do exe, ambiente de Mac)."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "saida.json").write_text(json.dumps(SAIDA_PARAKEET), encoding="utf-8")
    (pasta / "saida.txt").write_text(TEXTO_PARAKEET, encoding="utf-8")
    exe = pasta / "parakeet-mlx"
    exe.write_text('#!/bin/sh\necho "$@" >> "%s"\nb=$(basename "$1"); b="${b%%.*}"\ncp "%s/saida.$3" "$5/$b.$3"\n'
                   % (pasta / "chamadas.txt", pasta), encoding="utf-8")
    exe.chmod(0o755)
    amb = ambiente("Darwin", "arm64", exes={"parakeet-mlx": str(exe)})
    return exe, amb


# =========================== seletor: excluir a Groq ============================================

def test_escolher_backend_exclui_a_groq_da_escolha_automatica():
    so_groq = ambiente(env={"GROQ_API_KEY": "gsk_falsa"})
    assert T.escolher_backend(so_groq).NOME == "groq"
    with pytest.raises(T.SemTranscritor) as e:
        T.escolher_backend(so_groq, excluir=("groq",))
    assert "Groq" in str(e.value) and "faster-whisper" in str(e.value)


def test_escolher_backend_com_excluir_ainda_prefere_a_ordem():
    amb = ambiente(modulos=("faster_whisper",), env={"GROQ_API_KEY": "gsk_falsa"})
    assert T.escolher_backend(amb, excluir=("groq",)).NOME == "faster_whisper"


def test_pedir_pelo_nome_um_backend_excluido_e_erro():
    amb = ambiente(env={"GROQ_API_KEY": "gsk_falsa"})
    with pytest.raises(T.SemTranscritor):
        T.escolher_backend(amb, preferido="groq", excluir=("groq",))


# =========================== faster-whisper: idioma sempre pt ===================================

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

def _runner_que_grava_o_json(tmp, dados):
    chamadas = []

    def run(cmd):
        chamadas.append([str(c) for c in cmd])
        if "parakeet" in str(cmd[0]):
            Path(tmp, "av.json").write_text(json.dumps(dados), encoding="utf-8")

    return run, chamadas


@so_unix
def test_alinhar_no_mac_sem_executavel_usa_o_do_seletor_e_mantem_os_comandos(tmp_path):
    """Backend parakeet: mesma ordem e mesmos argumentos de antes (ffmpeg, parakeet, ffprobe)."""
    amb = ambiente("Darwin", "arm64", exes={"parakeet-mlx": "/opt/x/bin/parakeet-mlx"})
    run, chamadas = _runner_que_grava_o_json(tmp_path, SAIDA_PARAKEET)
    out = BL.alinhar("/AV/avatar.mp4", ["Olá", "mundo", "agora"], str(tmp_path), run=run,
                     duracao=lambda a: 1.5, amb=amb)
    assert chamadas[0] == ["ffmpeg", "-y", "-i", "/AV/avatar.mp4", "-vn", "-ac", "1", "-ar", "16000",
                           str(tmp_path / "av.wav")]
    assert chamadas[1] == ["/opt/x/bin/parakeet-mlx", str(tmp_path / "av.wav"), "--output-format", "json",
                           "--output-dir", str(tmp_path)]
    # idêntico ao que o caminho antigo (executável passado à mão) produz
    antigo = BL.alinhar("/AV/avatar.mp4", ["Olá", "mundo", "agora"], str(tmp_path), executavel="/x/parakeet-mlx",
                        run=run, duracao=lambda a: 1.5)
    assert out == antigo
    assert [(round(s, 3), round(e, 3), t) for s, e, t in out] == [(0.0, 0.4, "Olá"), (0.5, 0.9, "mundo"),
                                                                    (1.0, 1.5, "agora")]


def test_alinhar_sem_parakeet_usa_o_seletor_e_nao_chama_o_parakeet(tmp_path):
    falso = BackendFalso()
    amb = ambiente(modulos=("faster_whisper",))
    avatar = tmp_path / "avatar.mp4"
    avatar.write_bytes(b"av")

    def run(cmd):
        pytest.fail("sem parakeet nenhum subprocesso deste modulo deve rodar: %r" % (cmd,))

    out = BL.alinhar(str(avatar), ["Olá", "mundo", "agora"], str(tmp_path), run=run, duracao=lambda a: 1.5,
                     amb=amb, backend=falso)
    assert [(s, e, t) for s, e, t in out] == [(0.0, 0.4, "Olá"), (0.5, 0.9, "mundo"), (1.0, 1.5, "agora")]
    # o seletor recebeu o avatar, o idioma fixo em português e o perfil do relógio do anúncio (o parakeet o usa)
    assert falso.chamadas[0]["idioma"] == "pt"
    assert falso.chamadas[0]["audio"] == str(avatar)


def test_alinhar_sem_nenhum_transcritor_da_o_conserto_na_mensagem(tmp_path):
    amb = ambiente()
    with pytest.raises(CA.ErroFootage) as e:
        BL.alinhar(str(tmp_path / "avatar.mp4"), ["oi"], str(tmp_path), run=lambda c: None,
                   duracao=lambda a: 1.0, amb=amb)
    assert "faster-whisper" in str(e.value)


# =========================== cortar_ar_morto ===================================================

@so_unix
def test_corte_no_mac_roda_o_parakeet_como_sempre_e_devolve_o_json(tmp_path):
    exe, amb = parakeet_falso(tmp_path / "bin")
    wav = tmp_path / "bruto.wav"
    wav.write_bytes(b"RIFF")
    saida = tmp_path / "saida"
    saida.mkdir()
    j = CAM.transcrever(str(wav), str(saida), amb=amb)
    assert j == str(saida / "bruto.json")
    # comando antigo: sem chunk, formato json
    args = (tmp_path / "bin" / "chamadas.txt").read_text(encoding="utf-8").split()
    assert args == [str(wav), "--output-format", "json", "--output-dir", str(saida)]
    assert CAM.tokens_de(j) == [(0.0, 0.2, " Ol"), (0.2, 0.4, "á"), (0.5, 0.7, " mun"), (0.7, 0.9, "do"),
                                (1.0, 1.5, " agora.")]
    assert CAM.texto_de(j) == "Olá mundo agora."


def test_corte_sem_parakeet_converte_o_seletor_para_a_forma_do_parakeet(tmp_path):
    falso = BackendFalso()
    wav = tmp_path / "bruto.wav"
    wav.write_bytes(b"RIFF")
    j = CAM.transcrever(str(wav), str(tmp_path), amb=ambiente(modulos=("faster_whisper",)), backend=falso)
    assert j == str(tmp_path / "bruto.json")
    # o downstream (tokens_de, texto_de, blocos_de_fala) não percebe a troca de backend
    assert CAM.tokens_de(j) == [(0.0, 0.4, " Olá"), (0.5, 0.9, " mundo"), (1.0, 1.5, " agora.")]
    assert CAM.blocos_de_fala(CAM.tokens_de(j)) == [(0.0, 0.4), (0.5, 0.9), (1.0, 1.5)]
    assert CAM.texto_de(j) == "Olá mundo agora."
    assert falso.chamadas[0]["idioma"] == "pt"


def test_corte_de_take_recusa_a_groq(tmp_path):
    wav = tmp_path / "bruto.wav"
    wav.write_bytes(b"RIFF")
    so_groq = ambiente(env={"GROQ_API_KEY": "gsk_falsa"})
    with pytest.raises(SystemExit) as e:
        CAM.transcrever(str(wav), str(tmp_path), amb=so_groq)
    msg = str(e.value)
    assert "Groq" in msg and "faster-whisper" in msg


def test_corte_recusa_a_groq_tambem_quando_injetada(tmp_path):
    wav = tmp_path / "bruto.wav"
    wav.write_bytes(b"RIFF")
    with pytest.raises(SystemExit):
        CAM.transcrever(str(wav), str(tmp_path), amb=ambiente(), backend=BackendFalso(nome="groq"))


def test_corte_sem_nenhum_transcritor_sai_com_o_conserto(tmp_path):
    wav = tmp_path / "bruto.wav"
    wav.write_bytes(b"RIFF")
    with pytest.raises(SystemExit) as e:
        CAM.transcrever(str(wav), str(tmp_path), amb=ambiente())
    assert "faster-whisper" in str(e.value)


def test_corte_le_json_de_transcricao_em_utf8(tmp_path):
    j = tmp_path / "t.json"
    j.write_text(json.dumps(SAIDA_PARAKEET, ensure_ascii=False), encoding="utf-8")
    assert CAM.texto_de(str(j)) == "Olá mundo agora."


# =========================== auditar_audio =====================================================

@so_unix
def test_auditoria_no_mac_roda_o_parakeet_txt_numa_pasta_temporaria(tmp_path):
    exe, amb = parakeet_falso(tmp_path / "bin")
    mp3 = tmp_path / "voz.mp3"
    mp3.write_bytes(b"ID3")
    palavras = AA._transcrever(mp3, amb=amb)
    assert palavras == ["olá", "mundo", "agora"]
    args = (tmp_path / "bin" / "chamadas.txt").read_text(encoding="utf-8").split()
    assert args[:4] == [str(mp3), "--output-format", "txt", "--output-dir"]
    assert not args[4].startswith("/tmp")          # nada cravado em /tmp: tempfile
    assert not os.path.exists(args[4])             # e a pasta temporária some depois


def test_auditoria_sem_parakeet_usa_o_seletor_e_normaliza_igual(tmp_path):
    falso = BackendFalso()
    mp3 = tmp_path / "voz.mp3"
    mp3.write_bytes(b"ID3")
    palavras = AA._transcrever(mp3, amb=ambiente(modulos=("faster_whisper",)), backend=falso)
    assert palavras == ["olá", "mundo", "agora"]
    assert falso.chamadas[0]["idioma"] == "pt"


def test_auditoria_sem_nenhum_transcritor_avisa_alto_e_nao_quebra(tmp_path, capsys):
    mp3 = tmp_path / "voz.mp3"
    mp3.write_bytes(b"ID3")
    assert AA._transcrever(mp3, amb=ambiente()) is None
    assert "faster-whisper" in capsys.readouterr().err


def test_auditoria_nao_tem_mais_tmp_cravado():
    fonte = Path(AA.__file__).read_text(encoding="utf-8")
    assert '"/tmp"' not in fonte and "'/tmp'" not in fonte
