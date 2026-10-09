"""Legenda do gravado no produto (W5.D): texto corrigido pelo glossário, relatório fala x roteiro e
aprovação amarrada ao sha do .ass.

Três regras, cada uma nasceu de um defeito do pipeline de origem:

  1. A legenda NASCE da transcrição já corrigida pelo glossário do projeto. O dicionário de
     correções do cliente que morava no gerador virou `_local/glossario.json`, e a legenda errada
     ("Cloud" por "Claude", um "não" inventado) é pior que legenda nenhuma.
  2. Toda legenda gerada traz um RELATÓRIO fala x roteiro: o que a peça diz contra o que o roteiro
     pediu. Sem roteiro o relatório diz isso, nunca finge que conferiu.
  3. Queimar a legenda exige legenda APROVADA, e a aprovação guarda o sha256 do .ass. Quem é medido
     não assina: a aprovação é escrita por UM comando (`legendar.aprovar`), nunca pelo montador, pelo
     gerador nem pelo queimador. Mexer 1 byte no .ass depois do ok vence a aprovação.
"""
import json
import re
import subprocess
from pathlib import Path

import pytest

from audio.transcrever import Ambiente
from gravado import legendar, queimar_legenda
from gravado import projeto as gp
from gravado.veredito import InsumoInvalido
from projeto import glossario
from tests.fixtures import sinteticos as fx
from tests.gravado import sintese as sx

RAIZ = Path(__file__).resolve().parents[2]
SCRIPTS = RAIZ / "scripts"
ADS_UM = {"A1": {"corpo": [["T1", 0.0, 3.5]], "cta_normal": [["T1", 4.0, 5.0]]}}


def w(texto, ini, fim):
    return {"text": texto, "start": ini, "end": fim}


class BackendFalso(object):
    """Faz de conta que é o parakeet: devolve palavras prontas (com o erro do ASR dentro)."""
    NOME = "parakeet"

    def __init__(self, palavras):
        self.palavras = palavras

    def transcrever(self, audio, *, amb, workdir, prompt="", idioma="pt"):
        return [dict(p) for p in self.palavras]


def _ambiente():
    return Ambiente("Darwin", "arm64", {}, which=lambda n: "/bin/true" if n == "parakeet-mlx" else None,
                    importavel=lambda n: False)


def _projeto(tmp_path, estado, ads=None):
    p = sx.projeto_de_teste(tmp_path, ads=ads or ADS_UM, com_limpo=False, estado=estado)
    fx.testsrc_com_audio(p.garantir("montados") / "A1_normal.mp4", dur=3.0)
    return p


def _roteiro(p, texto, cod="A1"):
    pasta = p.base / "roteiros"
    pasta.mkdir(exist_ok=True)
    (pasta / (cod + ".md")).write_text(texto, encoding="utf-8")


PALAVRAS = [w("abra", 0.0, 0.3), w("a", 0.3, 0.4), w("Flucha", 0.4, 0.8), w("para", 0.9, 1.2),
            w("começar", 1.2, 1.7), w("hoje", 1.8, 2.2)]
TEXTO_CERTO = "Abra a Fluxa para começar hoje."


def _legendar(p, palavras=None):
    return legendar.legendar_pecas(p, ["A1_normal"], sx.LeitorFalso(palavras_da_peca=palavras or PALAVRAS))


# --- 1. o texto vem da transcrição corrigida pelo glossário --------------------------------------

def test_a_legenda_vem_da_transcricao_corrigida_pelo_glossario_do_projeto(tmp_path, estado_vazio):
    glossario.adicionar_termo("Fluxa", variantes=["Flucha"], tipo="marca", estado=estado_vazio)
    p = _projeto(tmp_path, estado_vazio)
    leitor = p.leitor(backend=BackendFalso(PALAVRAS), amb=_ambiente())
    legendar.legendar_pecas(p, ["A1_normal"], leitor)
    ass = p.legenda_ass("A1_normal").read_text(encoding="utf-8")
    texto = " ".join(legendar.sem_tags(l.split(",", 9)[9]) for l in ass.splitlines() if l.startswith("Dialogue"))
    assert "Fluxa" in texto and "Flucha" not in texto
    assert texto == "abra a Fluxa para começar hoje"


def test_sem_glossario_a_legenda_nao_troca_nada(tmp_path, estado_vazio):
    p = _projeto(tmp_path, estado_vazio)
    leitor = p.leitor(backend=BackendFalso(PALAVRAS), amb=_ambiente())
    legendar.legendar_pecas(p, ["A1_normal"], leitor)
    assert "Flucha" in p.legenda_ass("A1_normal").read_text(encoding="utf-8")


# --- 2. relatório fala x roteiro -----------------------------------------------------------------

def test_relatorio_passa_quando_a_legenda_diz_o_que_o_roteiro_pede():
    r = legendar.relatorio_fala_roteiro("A1_normal", ["abra", "a", "Fluxa", "para", "começar", "hoje"],
                                        TEXTO_CERTO, {"versao": 1, "termos": []})
    assert r["estado"] == "PASS" and r["faltando"] == 0 and r["extras"] == 0
    assert r["palavras_roteiro"] == 6 and r["palavras_fala"] == 6


def test_relatorio_reprova_com_mais_de_2_por_cento_faltando_e_lista_o_trecho():
    r = legendar.relatorio_fala_roteiro("A1_normal", ["abra", "a", "Fluxa", "hoje"], TEXTO_CERTO,
                                        {"versao": 1, "termos": []})
    assert r["estado"] == "REPROVA"
    assert r["faltando"] == 2 and r["maior_sequencia"] == 2
    assert r["trechos_faltando"] == ["para começar"]
    assert r["fracao_faltando"] == pytest.approx(2 / 6, abs=1e-3)


def test_relatorio_conta_sequencia_de_3_palavras_sumidas_mesmo_em_texto_longo():
    roteiro = " ".join("palavra%d" % i for i in range(200))
    fala = [("palavra%d" % i) for i in range(200) if i not in (50, 51, 52)]
    r = legendar.relatorio_fala_roteiro("A1_normal", fala, roteiro, {"versao": 1, "termos": []})
    assert r["fracao_faltando"] < 0.02 and r["maior_sequencia"] == 3 and r["estado"] == "REPROVA"


def test_relatorio_so_aceita_equivalencia_declarada_no_glossario():
    g = {"versao": 1, "termos": [], "equivalencias": [{"roteiro": "para", "fala": "pra"}]}
    declarada = legendar.relatorio_fala_roteiro("A1_normal", ["abra", "a", "Fluxa", "pra", "começar", "hoje"],
                                                TEXTO_CERTO, g)
    assert declarada["estado"] == "PASS" and declarada["faltando"] == 0
    sem = legendar.relatorio_fala_roteiro("A1_normal", ["abra", "a", "Fluxa", "pra", "começar", "hoje"],
                                          TEXTO_CERTO, {"versao": 1, "termos": []})
    assert sem["faltando"] == 1 and sem["extras"] == 1


def test_relatorio_sem_roteiro_diz_que_nao_conferiu():
    r = legendar.relatorio_fala_roteiro("A1_normal", ["abra", "a"], None, {"versao": 1, "termos": []})
    assert r["estado"] == "SEM_ROTEIRO" and r["palavras_fala"] == 2
    assert "faltando" not in r


def test_legendar_grava_o_relatorio_amarrado_ao_sha_do_ass(tmp_path, estado_vazio):
    p = _projeto(tmp_path, estado_vazio)
    _roteiro(p, TEXTO_CERTO.replace("Fluxa", "Flucha"))
    _legendar(p)
    rel = json.loads(legendar.caminho_relatorio(p, "A1_normal").read_text(encoding="utf-8"))
    assert rel["peca"] == "A1_normal" and rel["estado"] == "PASS"
    assert rel["ass_sha256"] == legendar.sha256_arquivo(p.legenda_ass("A1_normal"))
    assert rel["roteiro"] == "roteiros/A1.md"


def test_roteiro_da_peca_e_o_do_anuncio_ou_o_unico_do_projeto(tmp_path, estado_vazio):
    p = _projeto(tmp_path, estado_vazio)
    assert legendar.roteiro_da_peca(p, "A1_normal") is None
    (p.base / "roteiro.md").write_text("texto", encoding="utf-8")
    assert legendar.roteiro_da_peca(p, "A1_normal") == p.base / "roteiro.md"      # projeto de um anúncio só
    _roteiro(p, "outro texto")
    assert legendar.roteiro_da_peca(p, "A1_normal") == p.base / "roteiros" / "A1.md"   # o do anúncio manda
    dois = _projeto(tmp_path / "x", estado_vazio, ads={**ADS_UM, "B2": {"corpo": [["T2", 0.5, 2.0]],
                                                                       "cta_normal": [["T1", 4.0, 5.0]]}})
    (dois.base / "roteiro.md").write_text("texto", encoding="utf-8")
    assert legendar.roteiro_da_peca(dois, "A1_normal") is None      # com dois anúncios, o roteiro único não vale


# --- 3. aprovação amarrada ao sha do .ass --------------------------------------------------------

def _pronto_para_aprovar(tmp_path, estado, roteiro=TEXTO_CERTO.replace("Fluxa", "Flucha")):
    p = _projeto(tmp_path, estado)
    if roteiro:
        _roteiro(p, roteiro)
    _legendar(p)
    return p


def test_aprovar_grava_o_ok_e_o_sha_do_ass_e_do_relatorio(tmp_path, estado_vazio):
    p = _pronto_para_aprovar(tmp_path, estado_vazio)
    ap = legendar.aprovar(p, "A1_normal", "li as 2 linhas, estão certas", agora="2026-10-09T08:00:00-03:00")
    arq = legendar.caminho_aprovacao(p, "A1_normal")
    assert json.loads(arq.read_text(encoding="utf-8")) == ap
    assert ap["ok"] == "li as 2 linhas, estão certas" and ap["aprovado_em"] == "2026-10-09T08:00:00-03:00"
    assert ap["ass"] == {"arquivo": "legendas/A1_normal.ass",
                         "sha256": legendar.sha256_arquivo(p.legenda_ass("A1_normal"))}
    assert ap["relatorio"]["sha256"] == legendar.sha256_arquivo(legendar.caminho_relatorio(p, "A1_normal"))
    assert ap["relatorio"]["estado"] == "PASS" and ap["divergencia_aceita"] is False
    assert legendar.situacao(p, "A1_normal").vigente


def test_aprovar_sem_o_ok_do_diretor_recusa_e_nao_grava(tmp_path, estado_vazio):
    p = _pronto_para_aprovar(tmp_path, estado_vazio)
    for ok in ("", "  ", None):
        with pytest.raises(InsumoInvalido):
            legendar.aprovar(p, "A1_normal", ok)
    assert not legendar.caminho_aprovacao(p, "A1_normal").exists()


def test_aprovar_sem_legenda_ou_sem_relatorio_recusa(tmp_path, estado_vazio):
    p = _projeto(tmp_path, estado_vazio)
    with pytest.raises(InsumoInvalido) as e:
        legendar.aprovar(p, "A1_normal", "ok")
    assert "legendar" in str(e.value)
    _legendar(p)
    legendar.caminho_relatorio(p, "A1_normal").unlink()
    with pytest.raises(InsumoInvalido) as e2:
        legendar.aprovar(p, "A1_normal", "ok")
    assert "relatório" in str(e2.value)


def test_aprovar_com_relatorio_de_outra_versao_do_ass_recusa(tmp_path, estado_vazio):
    p = _pronto_para_aprovar(tmp_path, estado_vazio)
    ass = p.legenda_ass("A1_normal")
    ass.write_text(ass.read_text(encoding="utf-8") + "Dialogue: 0,0:00:03.00,0:00:03.50,Base,,0,0,0,,extra\n",
                   encoding="utf-8")
    with pytest.raises(InsumoInvalido) as e:
        legendar.aprovar(p, "A1_normal", "ok")
    assert "outra versão" in str(e.value)


def test_relatorio_que_reprova_so_se_aprova_com_a_divergencia_aceita_por_escrito(tmp_path, estado_vazio):
    p = _projeto(tmp_path, estado_vazio)
    _roteiro(p, "uma frase que ninguém disse nesta peça inteira")
    _legendar(p)
    with pytest.raises(InsumoInvalido) as e:
        legendar.aprovar(p, "A1_normal", "ok")
    assert "REPROVA" in str(e.value) or "divergência" in str(e.value)
    assert not legendar.caminho_aprovacao(p, "A1_normal").exists()
    ap = legendar.aprovar(p, "A1_normal", "ok, ele improvisou", divergencia_aceita=True)
    assert ap["divergencia_aceita"] is True and ap["relatorio"]["estado"] == "REPROVA"


def test_sem_roteiro_aprova_mas_o_relatorio_diz_sem_roteiro(tmp_path, estado_vazio):
    p = _pronto_para_aprovar(tmp_path, estado_vazio, roteiro=None)
    ap = legendar.aprovar(p, "A1_normal", "li a legenda inteira")
    assert ap["relatorio"]["estado"] == "SEM_ROTEIRO"


def test_mexer_1_byte_no_ass_depois_do_ok_vence_a_aprovacao(tmp_path, estado_vazio):
    p = _pronto_para_aprovar(tmp_path, estado_vazio)
    legendar.aprovar(p, "A1_normal", "ok")
    ass = p.legenda_ass("A1_normal")
    ass.write_bytes(ass.read_bytes().replace(b"hoje", b"hoJe"))
    s = legendar.situacao(p, "A1_normal")
    assert not s.vigente and "depois da aprovação" in s.motivo
    with pytest.raises(legendar.LegendaNaoAprovada) as e:
        legendar.exigir_aprovada(p, "A1_normal")
    assert "A1_normal" in str(e.value)


def test_legendar_de_novo_vence_a_aprovacao_anterior(tmp_path, estado_vazio):
    p = _pronto_para_aprovar(tmp_path, estado_vazio)
    legendar.aprovar(p, "A1_normal", "ok")
    _legendar(p, [w("outra", 0.0, 0.4), w("fala", 0.5, 0.9)])
    assert not legendar.situacao(p, "A1_normal").vigente


def test_sem_aprovacao_a_situacao_diz_como_aprovar(tmp_path, estado_vazio):
    p = _pronto_para_aprovar(tmp_path, estado_vazio)
    s = legendar.situacao(p, "A1_normal")
    assert not s.vigente and "aprovar-legenda" in s.motivo


# --- queimar exige legenda aprovada --------------------------------------------------------------

@pytest.fixture
def ffmpeg_falso(monkeypatch):
    """O ffmpeg do queimador: registra o comando e cria o arquivo de saída."""
    chamadas = []
    real = subprocess.run

    def run(cmd, **kw):
        if "-vf" in cmd and str(cmd[cmd.index("-vf") + 1]).startswith("ass="):
            chamadas.append(list(cmd))
            Path(cmd[-1]).write_bytes(b"video queimado")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return real(cmd, **kw)             # o resto (fixtures de mídia) roda de verdade
    monkeypatch.setattr(queimar_legenda.subprocess, "run", run)
    return chamadas


def _fontes(tmp_path):
    pasta = tmp_path / "fontes"
    pasta.mkdir(exist_ok=True)
    (pasta / "inter-800.ttf").write_bytes(b"x")
    return pasta


def test_queimar_sem_aprovacao_nao_roda_o_ffmpeg_e_diz_o_que_fazer(tmp_path, estado_vazio, ffmpeg_falso):
    p = _pronto_para_aprovar(tmp_path, estado_vazio)
    with pytest.raises(legendar.LegendaNaoAprovada) as e:
        queimar_legenda.queimar_peca(p, "A1_normal", _fontes(tmp_path))
    assert "aprovar-legenda" in str(e.value)
    assert ffmpeg_falso == [] and not p.legendado("A1_normal").exists()


def test_queimar_com_o_ass_alterado_depois_do_ok_nao_roda_o_ffmpeg(tmp_path, estado_vazio, ffmpeg_falso):
    p = _pronto_para_aprovar(tmp_path, estado_vazio)
    legendar.aprovar(p, "A1_normal", "ok")
    p.legenda_ass("A1_normal").write_bytes(p.legenda_ass("A1_normal").read_bytes() + b"\n; editado\n")
    with pytest.raises(legendar.LegendaNaoAprovada):
        queimar_legenda.queimar_peca(p, "A1_normal", _fontes(tmp_path))
    assert ffmpeg_falso == [] and not p.legendado("A1_normal").exists()


def test_queimar_aprovada_queima_e_registra_o_sha_do_ass_e_do_arquivo_queimado(tmp_path, estado_vazio, ffmpeg_falso):
    p = _pronto_para_aprovar(tmp_path, estado_vazio)
    ap = legendar.aprovar(p, "A1_normal", "ok")
    destino = queimar_legenda.queimar_peca(p, "A1_normal", _fontes(tmp_path))
    assert destino == p.legendado("A1_normal") and destino.read_bytes() == b"video queimado"
    assert len(ffmpeg_falso) == 1 and ffmpeg_falso[0][-1] == str(destino)
    reg = json.loads(queimar_legenda.caminho_queima(p, "A1_normal").read_text(encoding="utf-8"))
    assert reg["ass_sha256"] == ap["ass"]["sha256"]
    assert reg["legendado_sha256"] == legendar.sha256_arquivo(destino)
    assert reg["peca"] == "A1_normal"


def test_queimar_a_fonte_da_legenda_e_a_do_repo_e_nunca_a_do_sistema():
    texto = (SCRIPTS / "gravado" / "queimar_legenda.py").read_text(encoding="utf-8")
    assert "/System/Library" not in texto and "/Library/Fonts" not in texto
    assert (RAIZ / "fonts" / "inter-800.ttf").is_file()
    assert queimar_legenda.achar_fonte(RAIZ / "fonts") == RAIZ / "fonts"


@pytest.mark.lento
def test_queimar_de_verdade_com_a_inter_do_repo_escreve_texto_na_faixa_da_legenda(tmp_path, estado_vazio):
    from PIL import Image
    import numpy as np
    p = _pronto_para_aprovar(tmp_path, estado_vazio)
    legendar.aprovar(p, "A1_normal", "ok")
    destino = queimar_legenda.queimar_peca(p, "A1_normal", RAIZ / "fonts")
    quadro = tmp_path / "q.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "0.5", "-i", str(destino), "-frames:v", "1", str(quadro)],
                   check=True)
    antes = tmp_path / "a.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "0.5", "-i", str(p.montado("A1_normal")), "-frames:v", "1",
                    str(antes)], check=True)
    a, b = np.asarray(Image.open(antes).convert("L"), float), np.asarray(Image.open(quadro).convert("L"), float)
    assert a.shape == b.shape
    h = b.shape[0]
    faixa = slice(int(h * 0.55), int(h * 0.75))                  # onde a legenda mora (y 1300 de 1920 é 68%)
    assert np.abs(a[faixa] - b[faixa]).mean() > 1.0              # a legenda desenhou alguma coisa
    assert np.abs(a[: int(h * 0.3)] - b[: int(h * 0.3)]).mean() < 3.0     # e só ali


# --- quem assina e quem nunca assina -------------------------------------------------------------

def test_so_o_comando_de_aprovar_escreve_a_aprovacao_da_legenda():
    """Varredura estática: só legendar.py monta o caminho da aprovação, e só a CLI chama `legendar.aprovar`."""
    arquivos = [q for q in SCRIPTS.rglob("*.py") if "__pycache__" not in q.parts]
    mencionam = sorted(q.relative_to(SCRIPTS).as_posix() for q in arquivos
                       if ".aprovacao.json" in q.read_text(encoding="utf-8")
                       and not q.name.startswith("test_") and q.parts[-2] != "plano")
    assert mencionam == ["gravado/legendar.py"], mencionam
    chamam = sorted(q.relative_to(SCRIPTS).as_posix() for q in arquivos
                    if re.search(r"\blegendar\.aprovar\(", q.read_text(encoding="utf-8")))
    assert chamam == ["cli/gravado.py"], chamam
    for nome in ("montar.py", "queimar_legenda.py", "entregar.py", "compor_caixinha.py"):
        assert not re.search(r"\baprovar\(", (SCRIPTS / "gravado" / nome).read_text(encoding="utf-8")), nome
