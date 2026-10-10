"""W7.X item 8: `vam roteiro <slug> --de-audio voz.m4a` e os textos do aluno.

O aluno que grava a voz antes de escrever o roteiro não tinha como tirar a transcrição verbatim da gravação: o comando
transcreve (com o glossário dele), junta em parágrafos nas pausas e grava um RASCUNHO de roteiro.md (roteiro livre) para
ele revisar. O transcritor é falso: zero rede, zero modelo.
"""
import re
from pathlib import Path

import pytest

import vam
from audio import transcrever as T
from entrada import roteiro_md
from projeto import glossario, pastas

RAIZ = Path(__file__).resolve().parents[2]


def palavra(texto, ini, dur=0.3):
    return {"text": texto, "start": ini, "end": ini + dur}


# duas frases separadas por uma pausa de 1,2 s: dois parágrafos
FALA = [palavra("Oi", 0.0), palavra("gente", 0.4), palavra("tudo", 0.8), palavra("bem", 1.2),
        palavra("Hoje", 2.7), palavra("eu", 3.1), palavra("mostro", 3.4), palavra("o", 3.8), palavra("n8n", 4.0)]


@pytest.fixture
def pronto(estado_vazio, tmp_path, monkeypatch):
    vistos = {}

    def falso(audio, **kw):
        vistos.update(kw, audio=audio)
        return list(vistos.get("palavras_do_teste") or FALA)

    monkeypatch.setattr(T, "transcrever", falso)
    assert vam.main(["novo", "meu-ad", "--look", "estudio", "--sem-trilha", "teste", "--estado", str(estado_vazio)]) == 0
    voz = tmp_path / "voz.m4a"
    voz.write_bytes(b"x")

    def roteiro(*extra):
        return vam.main(["roteiro", "meu-ad", "--estado", str(estado_vazio)] + list(extra))

    return type("P", (), {"roteiro": staticmethod(roteiro), "voz": voz, "vistos": vistos,
                          "pj": pastas.projeto("meu-ad", estado_vazio), "estado": estado_vazio})


def test_de_audio_grava_a_transcricao_em_paragrafos_nas_pausas(pronto, capsys):
    assert pronto.roteiro("--de-audio", str(pronto.voz)) == 0
    texto = pronto.pj.roteiro.read_text(encoding="utf-8")
    assert texto.strip().split("\n\n") == ["Oi gente tudo bem", "Hoje eu mostro o n8n"]
    lei = roteiro_md.ler_arquivo(pronto.pj.roteiro, normalizar=False)
    assert lei.ok and lei.precisa_plano and len(lei.blocos) == 2          # roteiro livre válido na convenção
    out = capsys.readouterr().out
    assert "rascunho" in out and "revise" in out.lower()


def test_de_audio_passa_o_glossario_do_aluno_ao_transcritor(pronto):
    glossario.adicionar_termo("n8n", variantes=["n oito n"], estado=pronto.estado)
    assert pronto.roteiro("--de-audio", str(pronto.voz)) == 0
    termos = [t["grafia"] for t in pronto.vistos["glossario"]["termos"]]
    assert termos == ["n8n"]
    assert Path(pronto.vistos["audio"]) == pronto.voz and pronto.vistos["cache_dir"]


def test_de_audio_nao_troca_roteiro_existente_sem_sobrescrever(pronto, capsys):
    pronto.pj.roteiro.write_text("Meu roteiro.\n", encoding="utf-8")
    assert pronto.roteiro("--de-audio", str(pronto.voz)) == 2
    assert pronto.pj.roteiro.read_text(encoding="utf-8") == "Meu roteiro.\n"
    assert "--sobrescrever" in capsys.readouterr().err
    assert pronto.roteiro("--de-audio", str(pronto.voz), "--sobrescrever") == 0
    assert "Oi gente" in pronto.pj.roteiro.read_text(encoding="utf-8")


def test_de_audio_nao_anda_junto_com_de_nem_texto(pronto):
    assert pronto.roteiro("--de-audio", str(pronto.voz), "--texto", "Oi.") == 2
    assert pronto.roteiro("--de-audio", str(pronto.voz), "--de", str(pronto.voz)) == 2
    assert not pronto.pj.roteiro.exists()


def test_de_audio_arquivo_que_nao_existe_ou_formato_errado_sai_com_dois(pronto, tmp_path, capsys):
    assert pronto.roteiro("--de-audio", str(tmp_path / "nao-existe.m4a")) == 2
    ruim = tmp_path / "voz.pdf"
    ruim.write_bytes(b"x")
    assert pronto.roteiro("--de-audio", str(ruim)) == 2
    assert "Traceback" not in capsys.readouterr().err


def test_de_audio_sem_transcritor_sai_com_dois_e_a_mensagem_que_resolve(pronto, monkeypatch, capsys):
    def sem(*a, **k):
        raise T.SemTranscritor("nenhum transcritor disponível: rode bash scripts/setup.sh")
    monkeypatch.setattr(T, "transcrever", sem)
    assert pronto.roteiro("--de-audio", str(pronto.voz)) == 2
    assert "setup.sh" in capsys.readouterr().err and not pronto.pj.roteiro.exists()


def test_de_audio_transcricao_vazia_sai_com_dois_sem_gravar(pronto, capsys):
    pronto.vistos["palavras_do_teste"] = []
    pronto.vistos["palavras_do_teste"] = [palavra("", 0.0)]
    assert pronto.roteiro("--de-audio", str(pronto.voz)) == 2
    assert not pronto.pj.roteiro.exists() and "nenhuma palavra" in capsys.readouterr().err


def test_o_help_do_roteiro_documenta_o_de_audio(capsys):
    vam.main(["roteiro", "--help"])
    assert "--de-audio" in capsys.readouterr().out


# --- textos do aluno -----------------------------------------------------------------------------------------------

def test_aviso_do_vam_novo_manda_o_comando_nao_a_funcao_interna(estado_vazio, capsys):
    assert vam.main(["novo", "meu-ad", "--look", "estudio", "--sem-trilha", "teste", "--estado", str(estado_vazio)]) == 0
    out = capsys.readouterr().out
    assert "projeto.looks.adicionar" not in out
    assert "vam avatar meu-ad --avatar-id <id do look no HeyGen> --plano medio" in out


def test_nenhuma_mensagem_ao_aluno_cita_funcao_interna_do_projeto():
    achados = []
    for arq in (RAIZ / "scripts").rglob("*.py"):
        if "test_" in arq.name or "dev" in arq.parts:
            continue
        for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"[\"'].*(cadastre|use|rode|chame) com projeto\.\w+\.\w+", linha):
                achados.append("%s:%d" % (arq.relative_to(RAIZ), n))
    assert achados == []


def test_guia_e_skill_documentam_o_de_audio_e_a_skill_cabe_em_180_linhas():
    guia = (RAIZ / "docs" / "GUIA-ALUNO.md").read_text(encoding="utf-8")
    skill = (RAIZ / "SKILL.md").read_text(encoding="utf-8")
    assert "--de-audio" in guia and "--de-audio" in skill
    assert len(skill.splitlines()) <= 180
