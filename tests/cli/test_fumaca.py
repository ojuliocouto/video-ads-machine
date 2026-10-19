"""`vam fumaca` (W0, port nativo para Windows): o teste de fumaça do render, para o CI provar a máquina.

O render de verdade (Node + HyperFrames + Chromium + fontes) é o teste `lento` do fim. O resto roda sem Chromium: o
`renderizar` é trocado por um que grava o MP4 que o teste quer, e o ffprobe é o de verdade (quando existe) ou um falso
(`exe_falso`, que roda em qualquer sistema).
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import plataforma
import vam
from cli import fumaca
from tests.fixtures.plataforma import exe_falso

RAIZ = Path(__file__).resolve().parent.parent.parent
TEM_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _mp4(destino, segundos):
    """Um MP4 de verdade (preto, sem áudio) com a duração pedida."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=10:d=%s" % segundos,
                    "-pix_fmt", "yuv420p", str(destino)], check=True, capture_output=True, timeout=120)
    return destino


def _so_com_este_ffprobe(monkeypatch, pasta, saida, codigo=0):
    """PATH só com um ffprobe falso (que imprime `saida`); o ffmpeg e o resto do sistema somem."""
    exe_falso(pasta, "ffprobe", saida, codigo)
    monkeypatch.setenv("PATH", str(pasta))


# --- o comando existe e recusa pedido ruim --------------------------------------------------------------

def test_o_vam_descobre_o_comando_fumaca():
    assert "fumaca" in vam.comandos()


def test_a_ajuda_do_comando_diz_o_que_ele_prova(capsys):
    assert vam.main(["fumaca", "--help"]) == 0
    saida = capsys.readouterr().out
    assert "--saida" in saida and "HyperFrames" in saida and "1,5" in saida


def test_sem_saida_o_pedido_e_invalido():
    assert vam.main(["fumaca"]) == 2


def test_saida_que_nao_e_mp4_e_pedido_invalido(tmp_path, capsys):
    assert vam.main(["fumaca", "--saida", str(tmp_path / "fumaca.mov")]) == 2
    assert ".mp4" in capsys.readouterr().err


def test_saida_que_e_uma_pasta_e_pedido_invalido(tmp_path, capsys):
    assert vam.main(["fumaca", "--saida", str(tmp_path)]) == 2
    erro = capsys.readouterr().err
    assert "pasta" in erro or ".mp4" in erro


def test_o_modulo_nao_chama_o_shim_do_npm():
    texto = (RAIZ / "scripts" / "cli" / "fumaca.py").read_text(encoding="utf-8")
    assert ".bin" not in texto and "hf_cmd" in texto


# --- conferir_mp4: existe e dura 1,5 s ou mais ------------------------------------------------------------

def test_mp4_ausente_reprova(tmp_path, monkeypatch):
    _so_com_este_ffprobe(monkeypatch, tmp_path / "bin", "2.000000")
    ok, motivo = fumaca.conferir_mp4(tmp_path / "nao-existe.mp4")
    assert not ok and "não existe" in motivo


def test_mp4_vazio_reprova(tmp_path, monkeypatch):
    _so_com_este_ffprobe(monkeypatch, tmp_path / "bin", "2.000000")
    vazio = tmp_path / "vazio.mp4"
    vazio.write_bytes(b"")
    ok, motivo = fumaca.conferir_mp4(vazio)
    assert not ok and "vazio" in motivo


@pytest.mark.parametrize("duracao, passa", [("2.000000", True), ("1.500000", True), ("1.499000", False),
                                            ("0.033333", False), ("N/A", False), ("", False), ("lixo", False)])
def test_so_passa_com_1_5_s_ou_mais(tmp_path, monkeypatch, duracao, passa):
    _so_com_este_ffprobe(monkeypatch, tmp_path / "bin", duracao)
    arquivo = tmp_path / "f.mp4"
    arquivo.write_bytes(b"x" * 100)
    ok, motivo = fumaca.conferir_mp4(arquivo)
    assert ok is passa, motivo
    if not passa:
        assert "1,5" in motivo or "duração" in motivo


def test_ffprobe_que_falha_reprova(tmp_path, monkeypatch):
    _so_com_este_ffprobe(monkeypatch, tmp_path / "bin", "moov atom not found", codigo=1)
    arquivo = tmp_path / "f.mp4"
    arquivo.write_bytes(b"x" * 100)
    ok, motivo = fumaca.conferir_mp4(arquivo)
    assert not ok and "ffprobe" in motivo


def test_sem_ffprobe_no_path_o_erro_e_claro(tmp_path, monkeypatch):
    pasta = tmp_path / "vazia"
    pasta.mkdir()
    monkeypatch.setenv("PATH", str(pasta))
    arquivo = tmp_path / "f.mp4"
    arquivo.write_bytes(b"x" * 100)
    with pytest.raises(fumaca.SemFfprobe) as e:
        fumaca.conferir_mp4(arquivo)
    assert "ffprobe" in str(e.value)


@pytest.mark.skipif(not TEM_FFMPEG, reason="ffmpeg e ffprobe ausentes")
def test_ffprobe_de_verdade_mede_a_duracao(tmp_path):
    ok2, _ = fumaca.conferir_mp4(_mp4(tmp_path / "dois.mp4", 2))
    ok1, motivo1 = fumaca.conferir_mp4(_mp4(tmp_path / "um.mp4", 1))
    assert ok2 and not ok1 and "1,5" in motivo1


# --- o projeto do overlay -----------------------------------------------------------------------------------

def test_o_projeto_tem_html_de_2_s_sem_insumo_do_anuncio(tmp_path):
    projeto = fumaca.montar_projeto(tmp_path / "p")
    html = (projeto / "index.html").read_text(encoding="utf-8")
    assert 'data-duration="2.0"' in html and 'data-duration="55.36"' not in html
    assert "avatar.mp4" not in html and "logo.png" not in html           # a fumaça não traz mídia de anúncio
    assert 'id="a-roll' not in html and 'id="cta"' not in html and 'id="ev-logo"' not in html
    assert "INJECT:" not in html and "PARCIAL:" not in html               # parciais e marcadores resolvidos
    assert (projeto / "meta.json").is_file()


def test_as_fontes_do_template_chegam_inteiras_ao_projeto(tmp_path):
    projeto = fumaca.montar_projeto(tmp_path / "p")
    html = (projeto / "index.html").read_text(encoding="utf-8")
    pedidas = set(re.findall(r'url\("(fonts/[^"]+\.woff2)"\)', html))
    assert pedidas, "o template deixou de declarar fonte: a fumaça não prova mais as fontes"
    for rel in pedidas:
        assert (projeto / rel).read_bytes()[:4] == b"wOF2", rel
    assert fumaca.conferir_fontes(projeto) == []


def test_fonte_que_virou_texto_de_symlink_e_reprovada(tmp_path):
    """O defeito do Windows: o symlink do git vira um arquivo de texto com o alvo dentro, e o render sai sem a fonte."""
    projeto = fumaca.montar_projeto(tmp_path / "p")
    (projeto / "fonts" / "anton-400.woff2").write_text("../../../fonts/anton-400.woff2", encoding="utf-8")
    problemas = fumaca.conferir_fontes(projeto)
    assert len(problemas) == 1 and "anton-400.woff2" in problemas[0]


def test_fonte_ausente_e_reprovada(tmp_path):
    projeto = fumaca.montar_projeto(tmp_path / "p")
    (projeto / "fonts" / "inter-800.woff2").rename(tmp_path / "fora.woff2")
    problemas = fumaca.conferir_fontes(projeto)
    assert len(problemas) == 1 and "inter-800.woff2" in problemas[0] and "ausente" in problemas[0]


# --- o render pelo comando portátil ---------------------------------------------------------------------------

def test_o_render_usa_node_com_o_cli_do_pacote_e_nunca_o_shim(tmp_path, monkeypatch):
    pacote = tmp_path / "raiz" / "node_modules" / "hyperframes"
    (pacote / "dist").mkdir(parents=True)
    (pacote / "package.json").write_text('{"bin": {"hyperframes": "./dist/cli.js"}}', encoding="utf-8")
    (pacote / "dist" / "cli.js").write_text("//", encoding="utf-8")
    chamados = []

    def run(cmd, **kw):
        chamados.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(fumaca.subprocess, "run", run)
    rc, _texto = fumaca.renderizar(tmp_path / "raiz", tmp_path / "proj", tmp_path / "saida.mp4")
    cmd = chamados[0]
    assert rc == 0
    assert cmd[:2] == ["node", str(pacote / "dist" / "cli.js")]
    assert cmd[2] == "render" and str(tmp_path / "proj") in cmd and str(tmp_path / "saida.mp4") in cmd
    assert ".bin" not in " ".join(cmd)


def test_render_sem_hyperframes_instalado_levanta_o_erro_do_pacote(tmp_path):
    with pytest.raises(plataforma.ErroHyperFrames):
        fumaca.renderizar(tmp_path / "raiz-vazia", tmp_path / "proj", tmp_path / "saida.mp4")


# --- executar: os quatro desfechos -----------------------------------------------------------------------------

def _renderizador(duracao=None, rc=0, texto=""):
    """Um `renderizar` que grava o MP4 de `duracao` segundos (ou nada) e devolve `(rc, texto)`."""
    def renderizar(raiz, projeto, destino, **kw):
        if duracao is not None:
            _mp4(destino, duracao)
        return rc, texto
    return renderizar


@pytest.mark.skipif(not TEM_FFMPEG, reason="ffmpeg e ffprobe ausentes")
def test_render_bom_sai_com_zero_e_deixa_o_mp4_no_destino(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fumaca, "renderizar", _renderizador(duracao=2))
    destino = tmp_path / "saida" / "nova" / "fumaca.mp4"                    # as pastas do caminho nascem
    assert vam.main(["fumaca", "--saida", str(destino)]) == 0
    assert destino.is_file() and destino.stat().st_size > 0
    assert "OK" in capsys.readouterr().out


@pytest.mark.skipif(not TEM_FFMPEG, reason="ffmpeg e ffprobe ausentes")
def test_mp4_curto_demais_sai_com_um_e_nao_deixa_arquivo(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fumaca, "renderizar", _renderizador(duracao=1))
    destino = tmp_path / "fumaca.mp4"
    assert vam.main(["fumaca", "--saida", str(destino)]) == 1
    assert not destino.exists()
    assert "1,5" in capsys.readouterr().err


def test_render_que_falha_sai_com_um_e_mostra_o_fim_do_erro(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fumaca, "renderizar", _renderizador(rc=3, texto="x" * 5000 + "Chromium não abriu"))
    monkeypatch.setattr(fumaca, "_ffprobe", lambda: "ffprobe")               # sem ffprobe de verdade neste teste
    destino = tmp_path / "fumaca.mp4"
    assert vam.main(["fumaca", "--saida", str(destino)]) == 1
    erro = capsys.readouterr().err
    assert "Chromium não abriu" in erro and "x" * 3000 not in erro            # só o rabo do log
    assert not destino.exists()


def test_render_que_nao_gravou_nada_sai_com_um(tmp_path, monkeypatch):
    monkeypatch.setattr(fumaca, "renderizar", _renderizador(duracao=None))
    monkeypatch.setattr(fumaca, "_ffprobe", lambda: "ffprobe")
    assert vam.main(["fumaca", "--saida", str(tmp_path / "fumaca.mp4")]) == 1


@pytest.mark.skipif(not TEM_FFMPEG, reason="ffmpeg e ffprobe ausentes")
def test_arquivo_velho_no_destino_nao_vira_falso_positivo(tmp_path, monkeypatch):
    destino = _mp4(tmp_path / "fumaca.mp4", 2)                                # sobra de uma rodada anterior
    monkeypatch.setattr(fumaca, "renderizar", _renderizador(rc=1, texto="falhou"))
    assert vam.main(["fumaca", "--saida", str(destino)]) == 1
    assert not destino.exists()


def test_hyperframes_nao_instalado_sai_com_dois_e_diz_o_conserto(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fumaca, "RAIZ", tmp_path / "clone-sem-setup")
    monkeypatch.setattr(fumaca, "_ffprobe", lambda: "ffprobe")
    assert vam.main(["fumaca", "--saida", str(tmp_path / "fumaca.mp4")]) == 2
    assert "scripts/setup.sh" in capsys.readouterr().err


def test_sem_ffprobe_sai_com_dois_antes_de_gastar_o_render(tmp_path, monkeypatch, capsys):
    chamou = []
    monkeypatch.setattr(fumaca, "renderizar", lambda *a, **k: chamou.append(1) or (0, ""))
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    monkeypatch.setenv("PATH", str(vazio))
    assert vam.main(["fumaca", "--saida", str(tmp_path / "fumaca.mp4")]) == 2
    assert chamou == [] and "ffprobe" in capsys.readouterr().err


# --- o render de verdade ------------------------------------------------------------------------------------------

@pytest.mark.lento
@pytest.mark.skipif(not TEM_FFMPEG or not shutil.which("node"), reason="precisa de ffmpeg, ffprobe e Node")
def test_render_de_verdade_pelo_hyperframes(tmp_path):
    if not (RAIZ / "node_modules" / "hyperframes" / "package.json").is_file():
        pytest.skip("HyperFrames não instalado (rode bash scripts/setup.sh)")
    destino = tmp_path / "fumaca.mp4"
    assert vam.main(["fumaca", "--saida", str(destino)]) == 0
    ok, motivo = fumaca.conferir_mp4(destino)
    assert ok, motivo
    sonda = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", str(destino)], capture_output=True, text=True)
    assert sonda.stdout.strip() == "1080,1920"
