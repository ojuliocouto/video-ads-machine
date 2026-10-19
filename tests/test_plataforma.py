"""scripts/plataforma.py: o que muda de um sistema para outro, numa função só (W0, port nativo para Windows).

As funções são puras. O sistema é lido por `plataforma._sistema()`, que os testes trocam para exercitar o ramo do Windows
no macOS e no Linux (e o contrário). O que depende do sistema de verdade (rodar o ffmpeg com um caminho esquisito, rodar o
executável falso) roda no sistema de quem testa.
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path, PureWindowsPath

import pytest

import plataforma as P
from tests.fixtures.plataforma import exe_falso


def _como(monkeypatch, sistema):
    monkeypatch.setattr(P, "_sistema", lambda: sistema)


# --- eh_windows / eh_mac ------------------------------------------------------------------------------

@pytest.mark.parametrize("sistema, windows, mac", [("win32", True, False), ("cygwin", False, False),
                                                   ("darwin", False, True), ("linux", False, False)])
def test_eh_windows_e_eh_mac_leem_o_sistema(monkeypatch, sistema, windows, mac):
    _como(monkeypatch, sistema)
    assert P.eh_windows() is windows
    assert P.eh_mac() is mac


def test_sem_trocar_nada_o_sistema_e_o_de_quem_roda():
    assert P.eh_windows() == sys.platform.startswith("win")
    assert P.eh_mac() == (sys.platform == "darwin")


def test_importar_nao_tem_efeito_colateral():
    r = subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, %r); import plataforma"
                        % str(Path(P.__file__).resolve().parent)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


# --- venv_python --------------------------------------------------------------------------------------

def test_venv_python_no_windows_e_scripts_python_exe(monkeypatch, tmp_path):
    _como(monkeypatch, "win32")
    assert P.venv_python(tmp_path) == tmp_path / ".venv" / "Scripts" / "python.exe"


@pytest.mark.parametrize("sistema", ["darwin", "linux"])
def test_venv_python_fora_do_windows_e_bin_python(monkeypatch, tmp_path, sistema):
    _como(monkeypatch, sistema)
    assert P.venv_python(tmp_path) == tmp_path / ".venv" / "bin" / "python"


def test_venv_python_aceita_texto_e_nao_exige_que_exista(monkeypatch, tmp_path):
    _como(monkeypatch, "linux")
    saida = P.venv_python(str(tmp_path / "ainda-nao-existe"))
    assert isinstance(saida, Path) and not saida.exists()


# --- hf_cmd -------------------------------------------------------------------------------------------

def _pacote(raiz, bin_, arquivos):
    """node_modules/hyperframes/ com o package.json dado e os arquivos (vazios) que o `bin` aponta."""
    pasta = raiz / "node_modules" / "hyperframes"
    pasta.mkdir(parents=True)
    (pasta / "package.json").write_text(json.dumps({"name": "hyperframes", "version": "0.7.56", "bin": bin_}),
                                        encoding="utf-8")
    for rel in arquivos:
        alvo = pasta / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text("// cli\n", encoding="utf-8")
    return pasta


def test_hf_cmd_usa_o_bin_do_pacote_pinado(tmp_path):
    pacote = _pacote(tmp_path, {"hyperframes": "./dist/cli.js"}, ["dist/cli.js"])
    cmd = P.hf_cmd(tmp_path)
    assert cmd == ["node", str(pacote / "dist" / "cli.js")]
    assert all(isinstance(c, str) for c in cmd)


def test_hf_cmd_segue_o_bin_quando_o_pacote_muda_de_layout(tmp_path):
    pacote = _pacote(tmp_path, {"hyperframes": "./bin/hyperframes.mjs", "hyperframes-localize-fonts": "./bin/x.mjs"},
                     ["bin/hyperframes.mjs", "bin/x.mjs"])
    assert P.hf_cmd(tmp_path) == ["node", str(pacote / "bin" / "hyperframes.mjs")]


def test_hf_cmd_bin_como_texto(tmp_path):
    pacote = _pacote(tmp_path, "dist/cli.js", ["dist/cli.js"])
    assert P.hf_cmd(tmp_path) == ["node", str(pacote / "dist" / "cli.js")]


def test_hf_cmd_nao_usa_o_shim_sem_extensao(tmp_path):
    """O shim `node_modules/.bin/hyperframes` é script de shell no Windows (erro 193 ao executar): nunca entra."""
    _pacote(tmp_path, {"hyperframes": "./dist/cli.js"}, ["dist/cli.js"])
    assert ".bin" not in "".join(P.hf_cmd(tmp_path))


def test_hf_cmd_sem_node_modules_diz_o_que_fazer(tmp_path):
    with pytest.raises(P.ErroHyperFrames) as e:
        P.hf_cmd(tmp_path)
    msg = str(e.value)
    assert "node_modules" in msg and "scripts/setup.sh" in msg


def test_hf_cmd_sem_bin_no_package_json(tmp_path):
    _pacote(tmp_path, None, [])
    with pytest.raises(P.ErroHyperFrames) as e:
        P.hf_cmd(tmp_path)
    assert "bin" in str(e.value)


def test_hf_cmd_bin_de_outro_nome_nao_serve(tmp_path):
    _pacote(tmp_path, {"outra-coisa": "./x.js"}, ["x.js"])
    with pytest.raises(P.ErroHyperFrames):
        P.hf_cmd(tmp_path)


def test_hf_cmd_arquivo_do_bin_ausente(tmp_path):
    _pacote(tmp_path, {"hyperframes": "./dist/cli.js"}, [])
    with pytest.raises(P.ErroHyperFrames) as e:
        P.hf_cmd(tmp_path)
    assert "cli.js" in str(e.value)


def test_hf_cmd_package_json_corrompido(tmp_path):
    pasta = _pacote(tmp_path, {"hyperframes": "./dist/cli.js"}, ["dist/cli.js"])
    (pasta / "package.json").write_text("{ isso não é json", encoding="utf-8")
    with pytest.raises(P.ErroHyperFrames):
        P.hf_cmd(tmp_path)


def test_hf_cmd_do_repo_instalado_aponta_para_um_arquivo_que_existe():
    """No repo com o setup feito, o comando é de verdade; sem node_modules (clone sem setup) o teste não se aplica."""
    raiz = Path(P.__file__).resolve().parent.parent
    if not (raiz / "node_modules" / "hyperframes" / "package.json").is_file():
        pytest.skip("node_modules não instalado (rode bash scripts/setup.sh)")
    cmd = P.hf_cmd(raiz)
    assert cmd[0] == "node" and Path(cmd[1]).is_file()


# --- escapar_filtro -----------------------------------------------------------------------------------

def test_caminho_comum_passa_sem_mudar():
    assert P.escapar_filtro("/tmp/video/legenda.ass") == "/tmp/video/legenda.ass"


def test_caminho_do_windows_vira_barra_normal_e_o_dois_pontos_do_disco_e_escapado():
    """`C:\\Dados\\João Silva\\a.ass` -> `C\\\\:/Dados/João Silva/a.ass`: duas barras antes do `:` (duas camadas)."""
    esc = P.escapar_filtro(PureWindowsPath(r"C:\Dados\João Silva\a.ass"))
    assert esc == "C\\\\:/Dados/João Silva/a.ass"
    assert "\\" not in esc.replace("\\\\:", "")                # nenhuma barra invertida sobra além do escape do disco


def test_texto_com_barra_invertida_no_windows_tambem_vira_barra_normal(monkeypatch):
    _como(monkeypatch, "win32")
    assert P.escapar_filtro(r"C:\temp\fonts") == "C\\\\:/temp/fonts"


def test_no_posix_a_barra_invertida_e_letra_do_nome_e_nao_vira_separador(monkeypatch):
    _como(monkeypatch, "linux")
    assert P.escapar_filtro("/tmp/a\\b.png") == "/tmp/a\\\\\\\\b.png"


@pytest.mark.parametrize("bruto, esperado", [
    ("a:b", "a\\\\:b"),            # ':' separa opções do filtro: escapado nas duas camadas
    ("a=b", "a\\\\=b"),            # '=' é chave=valor
    ("a,b", "a\\,b"),              # ',' separa filtros do grafo
    ("a;b", "a\\;b"),
    ("a[b]", "a\\[b\\]"),          # colchetes são rótulos de pad
    ("a'b", "a\\\\\\'b"),          # aspa: cada camada escapa a sua
    ("a b", "a b"),                # espaço passa
    ("a%b", "a%b"),
])
def test_cada_especial_e_escapado_na_camada_certa(bruto, esperado):
    assert P.escapar_filtro(bruto) == esperado


def test_o_escape_nao_depende_de_o_arquivo_existir():
    assert P.escapar_filtro("/nao/existe/x:y.ass") == "/nao/existe/x\\\\:y.ass"


def _png_1x1(destino):
    """Um PNG válido de 1x1 pixel, feito na mão (o teste não depende de ferramenta para criar a imagem)."""
    def bloco(tipo, dados):
        corpo = tipo + dados
        return struct.pack(">I", len(dados)) + corpo + struct.pack(">I", zlib.crc32(corpo) & 0xFFFFFFFF)
    cru = b"\x00\xff\x00\x00"                                   # filtro 0 + 1 pixel RGB vermelho
    png = (b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
           + bloco(b"IDAT", zlib.compress(cru)) + bloco(b"IEND", b""))
    Path(destino).write_bytes(png)
    return Path(destino)


def _ffmpeg_tem_filtro(nome):
    if not shutil.which("ffmpeg"):
        return False
    r = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True, timeout=60)
    return any((" %s " % nome) in linha for linha in r.stdout.splitlines())


# nomes que o disco do Windows também aceita; os demais só existem em POSIX
NOMES_PORTAVEIS = ["simples", "com espaco", "a,b", "a;b", "a[b]", "a=b", "a'b", "a@b", "a%b", "ação ê"]
NOMES_SO_POSIX = ["a:b", "a\\b"]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg ausente")
@pytest.mark.parametrize("nome", NOMES_PORTAVEIS + NOMES_SO_POSIX)
def test_ffmpeg_abre_o_arquivo_pelo_caminho_escapado(tmp_path, nome):
    if nome in NOMES_SO_POSIX and P.eh_windows():
        pytest.skip("o nome não existe no disco do Windows")
    pasta = tmp_path / "sub pasta"
    pasta.mkdir()
    arquivo = _png_1x1(pasta / (nome + ".png"))
    r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "movie=" + P.escapar_filtro(arquivo),
                        "-frames:v", "1", "-f", "null", "-"], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr


SONDA_ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 64
PlayResY: 64

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, Alignment
Style: Default,Arial,20,&H00FFFFFF,2

[Events]
Format: Layer, Start, End, Style, Text
Dialogue: 0,0:00:00.00,0:00:00.20,Default,teste
"""


@pytest.mark.skipif(not _ffmpeg_tem_filtro("ass"), reason="ffmpeg sem libass")
def test_ffmpeg_queima_ass_com_fontsdir_em_pasta_de_nome_esquisito(tmp_path):
    """O caso real da legenda: duas opções (`arquivo` e `fontsdir`) no mesmo filtro, cada uma com o próprio escape."""
    nome = "pasta,com [x] e espaço" if P.eh_windows() else "pasta:com,tudo [x] e espaço"
    pasta = tmp_path / nome
    pasta.mkdir()
    ass = pasta / "legenda.ass"
    ass.write_text(SONDA_ASS, encoding="utf-8")
    vf = "ass=%s:fontsdir=%s" % (P.escapar_filtro(ass), P.escapar_filtro(pasta))
    r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.2:r=10", "-vf", vf,
                        "-frames:v", "1", "-f", "null", "-"], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr


# --- abrir_pasta --------------------------------------------------------------------------------------

class _Chamadas(object):
    def __init__(self):
        self.cmds, self.startfile = [], []


@pytest.fixture
def chamadas(monkeypatch):
    c = _Chamadas()

    def run(cmd, **kw):
        c.cmds.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(P.subprocess, "run", run)
    monkeypatch.setattr(P.os, "startfile", lambda caminho: c.startfile.append(caminho), raising=False)
    return c


def test_abrir_pasta_no_windows_usa_startfile(monkeypatch, chamadas, tmp_path):
    _como(monkeypatch, "win32")
    assert P.abrir_pasta(tmp_path) is True
    assert chamadas.startfile == [str(tmp_path)] and chamadas.cmds == []


def test_abrir_pasta_no_mac_usa_open(monkeypatch, chamadas, tmp_path):
    _como(monkeypatch, "darwin")
    assert P.abrir_pasta(tmp_path) is True
    assert chamadas.cmds == [["open", str(tmp_path)]] and chamadas.startfile == []


def test_abrir_pasta_no_linux_usa_xdg_open(monkeypatch, chamadas, tmp_path):
    _como(monkeypatch, "linux")
    assert P.abrir_pasta(tmp_path) is True
    assert chamadas.cmds == [["xdg-open", str(tmp_path)]]


@pytest.mark.parametrize("sistema", ["win32", "darwin", "linux"])
def test_abrir_pasta_que_falha_devolve_false_e_nao_estoura(monkeypatch, tmp_path, sistema):
    """Abrir a pasta é conveniência: sem gerenciador de arquivos (servidor, CI) o comando não pode derrubar o fluxo."""
    _como(monkeypatch, sistema)

    def estoura(*a, **k):
        raise OSError("sem gerenciador de arquivos")

    monkeypatch.setattr(P.subprocess, "run", estoura)
    monkeypatch.setattr(P.os, "startfile", estoura, raising=False)
    assert P.abrir_pasta(tmp_path) is False


def test_abrir_pasta_com_saida_diferente_de_zero_e_false(monkeypatch, tmp_path):
    _como(monkeypatch, "linux")
    monkeypatch.setattr(P.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 3, b"", b""))
    assert P.abrir_pasta(tmp_path) is False


# --- exe_falso ----------------------------------------------------------------------------------------

def test_exe_falso_roda_no_sistema_de_quem_testa(tmp_path):
    exe = exe_falso(tmp_path, "ferramenta", "ola mundo", 0)
    r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip() == "ola mundo"


def test_exe_falso_devolve_o_codigo_de_saida(tmp_path):
    exe = exe_falso(tmp_path, "ferramenta", "deu ruim", 3)
    r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 3 and "deu ruim" in r.stdout


def test_exe_falso_funciona_em_pasta_com_espaco_e_acento(tmp_path):
    exe = exe_falso(tmp_path / "pasta com espaço", "ferramenta", "ok", 0)
    r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip() == "ok"


def test_exe_falso_e_achado_pelo_path_pelo_nome_simples(monkeypatch, tmp_path):
    exe_falso(tmp_path, "ferramenta-falsa", "ok", 0)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    achado = shutil.which("ferramenta-falsa")
    assert achado and Path(achado).parent == tmp_path


def test_exe_falso_saida_vazia_nao_imprime_nada(tmp_path):
    exe = exe_falso(tmp_path, "mudo", "", 0)
    r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_exe_falso_so_aceita_saida_em_ascii(tmp_path):
    with pytest.raises(ValueError):
        exe_falso(tmp_path, "ferramenta", "ação", 0)


def test_exe_falso_no_ramo_do_windows_e_um_cmd(monkeypatch, tmp_path):
    _como(monkeypatch, "win32")
    exe = exe_falso(tmp_path, "ferramenta", "a & b | c % d", 3)
    assert exe.name == "ferramenta.cmd"
    texto = exe.read_bytes().decode("ascii")
    assert texto.startswith("@echo off\r\n") and texto.endswith("exit /b 3\r\n")
    assert "echo(a ^& b ^| c %% d\r\n" in texto             # especial do cmd escapado


def test_exe_falso_no_ramo_do_posix_e_um_script_sh_executavel(monkeypatch, tmp_path):
    _como(monkeypatch, "linux")
    exe = exe_falso(tmp_path, "ferramenta", "it's ok", 2)
    assert exe.name == "ferramenta"
    texto = exe.read_text(encoding="utf-8")
    assert texto.startswith("#!/bin/sh\n") and texto.endswith("exit 2\n")
    assert os.access(str(exe), os.X_OK)


def test_exe_falso_multilinha_vira_uma_linha_de_eco_por_linha(monkeypatch, tmp_path):
    _como(monkeypatch, "win32")
    texto = exe_falso(tmp_path, "f", "um\ndois", 0).read_bytes().decode("ascii")
    assert "echo(um\r\necho(dois\r\n" in texto
