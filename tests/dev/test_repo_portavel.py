"""O repo tem que sair do `git clone` igual em macOS, Linux e Windows (W0, port nativo para Windows).

Duas coisas quebram o clone no Windows sem ninguém perceber no Mac:

- symlink versionado: o Git for Windows sem privilégio (core.symlinks=false) grava o ALVO como texto num arquivo comum.
  Uma fonte .woff2 vira um arquivo de 30 bytes com o caminho dentro, e o render sai sem a fonte, sem erro nenhum;
- fim de linha: com core.autocrlf=true o setup.sh chega com CRLF e o bash morre em `$'\\r': command not found`.
  O `.gitattributes` fixa LF nos textos que o bash, o Python e o Node leem.
"""
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent.parent


def _git(*args):
    try:
        r = subprocess.run(["git", "-C", str(RAIZ)] + list(args), capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git indisponível")
    if r.returncode != 0:
        pytest.skip("a pasta não é um clone do git: %s" % r.stderr.decode("utf-8", "replace").strip()[:200])
    return r.stdout


def test_nenhum_arquivo_versionado_e_symlink():
    """Modo 120000 no índice = symlink. Fonte, template e script entram como arquivo de verdade."""
    saida = _git("ls-files", "-s", "-z").decode("utf-8")
    links = []
    for entrada in saida.split("\0"):
        if not entrada:
            continue
        meta, _tab, caminho = entrada.partition("\t")
        if meta.split(" ")[0] == "120000":
            links.append(caminho)
    assert not links, ("symlink versionado quebra o clone no Windows (vira um arquivo de texto com o alvo). "
                       "Troque por uma cópia: %s" % ", ".join(links))


def test_nenhum_arquivo_versionado_aparece_como_symlink_na_pasta_de_trabalho():
    saida = _git("ls-files", "-z").decode("utf-8")
    links = [c for c in saida.split("\0") if c and (RAIZ / c).is_symlink()]
    assert not links, "symlink na pasta de trabalho: %s" % ", ".join(links)


def _atributos(*caminhos):
    """{caminho: {atributo: valor}} do `git check-attr text eol` (a regra que o Git aplicaria ao arquivo)."""
    saida = _git("check-attr", "-z", "text", "eol", "--", *caminhos).decode("utf-8")
    campos = saida.split("\0")
    resultado = {}
    for i in range(0, len(campos) - 2, 3):
        caminho, atributo, valor = campos[i], campos[i + 1], campos[i + 2]
        resultado.setdefault(caminho, {})[atributo] = valor
    return resultado


@pytest.mark.parametrize("caminho", ["scripts/setup.sh", "scripts/dev/testar_limpo.sh", "scripts/vam.py",
                                     "SKILL.md", "package.json", "templates/reel-editorial/index.html",
                                     "templates/_parciais/base.css", "templates/_parciais/timeline.js"])
def test_texto_que_o_bash_python_e_node_leem_fica_com_lf(caminho):
    attrs = _atributos(caminho)[caminho]
    assert attrs["text"] == "set" and attrs["eol"] == "lf", "%s: %s" % (caminho, attrs)


@pytest.mark.parametrize("caminho", ["fonts/inter-800.ttf", "templates/reel-editorial/fonts/inter-400.woff2",
                                     "fonts/x.otf", "x/logo.png", "x/foto.jpg", "x/v.mp4", "x/v.mov", "x/a.m4a",
                                     "x/a.mp3", "x/a.wav"])
def test_binario_nunca_e_convertido(caminho):
    attrs = _atributos(caminho)[caminho]
    assert attrs["text"] == "unset", "%s: %s" % (caminho, attrs)


def test_o_resto_deixa_o_git_decidir():
    assert _atributos("LICENSE")["LICENSE"]["text"] == "auto"
