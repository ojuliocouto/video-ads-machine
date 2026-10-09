#!/usr/bin/env python3
"""doctor: confere o ambiente do aluno ANTES de gastar um render ou um crédito.

    python3 scripts/vam.py doctor
    python3 scripts/onboarding/doctor.py          (o mesmo, direto)

Cada check devolve um `Resultado`: OK, WARN ou FAIL, com UMA linha de conserto. Nenhum check
mostra traceback: o que estoura por dentro vira FAIL com a mensagem do erro.

  python_deps       Python 3.9+ e numpy, opencv, pillow, scipy (no .venv do repo, se existe)
  ffmpeg_libass     ffmpeg e ffprobe; um render de verdade pelo filtro `subtitles` prova o libass
  node_hyperframes  Node 22+ e o binário do HyperFrames em node_modules/.bin, na versão pinada.
                    Binário ausente BARRA: é ele que o motor chama para renderizar.
  transcritor       parakeet, faster-whisper ou Groq, pela mesma escolha do audio.transcrever
  fontes            as fontes que os templates pedem existem em fonts/
  rede              o GSAP local existe, ou a CDN responde (o render carrega o GSAP)
  heygen            HEYGEN_API_KEY e o saldo em US$ (/v3/users/me). Sem chave é WARN: o modo
                    gravado e o one-shot não usam avatar.

Saída: 0 se nada deu FAIL (WARN passa), 1 caso contrário.

O ambiente é injetado (`AmbienteDoctor`): PATH, variáveis, subprocesso e HTTP. É o que permite
testar tudo sem rede, sem instalar nada e sem tocar na máquina de quem roda.
"""
import importlib
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

OK, WARN, FAIL = "OK", "WARN", "FAIL"
STATUS = (OK, WARN, FAIL)

RAIZ_DO_REPO = Path(__file__).resolve().parent.parent.parent
CHECKS = ("python_deps", "ffmpeg_libass", "node_hyperframes", "transcritor", "fontes", "rede",
          "heygen")

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


class ErroRede(Exception):
    """Sem rede, DNS, certificado ou tempo esgotado. UMA mensagem curta."""


def _uma_linha(texto):
    return " ".join(str(texto).split())


@dataclass
class Resultado(object):
    """Um check: o status, o que viu e UMA linha com o que fazer quando não está OK."""
    nome: str
    status: str
    detalhe: str = ""
    conserto: str = ""

    def __post_init__(self):
        if self.status not in STATUS:
            raise ValueError("status deve ser um de %s, veio %r" % (", ".join(STATUS), self.status))
        self.detalhe = _uma_linha(self.detalhe)
        self.conserto = _uma_linha(self.conserto)


# --- .env -----------------------------------------------------------------------------------------

def carregar_dotenv(caminho):
    """Lê um `.env` simples: CHAVE=valor, `export`, aspas e comentários. Ausente = {}.

    Só lê. Nunca imprime valor. Quem monta o ambiente decide a precedência.
    """
    try:
        linhas = Path(caminho).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return {}
    valores = {}
    for linha in linhas:
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        if linha.startswith("export "):
            linha = linha[len("export "):].strip()
        if "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        chave, valor = chave.strip(), valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
            valor = valor[1:-1]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", chave):
            valores[chave] = valor
    return valores


# --- o ambiente injetável ---------------------------------------------------------------------------

def _executar_real(cmd, timeout=60):
    try:
        p = subprocess.run([str(c) for c in cmd], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, universal_newlines=True, timeout=timeout)
        return p.returncode, p.stdout or ""
    except subprocess.TimeoutExpired:
        return 124, "tempo esgotado (%ss)" % timeout
    except OSError as erro:
        return 127, str(erro)


def _http_get_real(url, headers=None, timeout=10, metodo="GET"):
    pedido = urllib.request.Request(url, method=metodo)
    pedido.add_header("User-Agent", USER_AGENT)
    for chave, valor in (headers or {}).items():
        pedido.add_header(chave, valor)
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as erro:
        try:
            corpo = erro.read().decode("utf-8", "replace")
        except Exception:
            corpo = ""
        return erro.code, corpo
    except (urllib.error.URLError, OSError, ValueError) as erro:
        raise ErroRede(_uma_linha(getattr(erro, "reason", None) or erro))


def _nunca(nome):
    return None


def _nao_importa(nome):
    return False


def _sem_comando(cmd, timeout=60):
    return 127, "subprocesso não injetado"


def _sem_rede(url, headers=None, timeout=10, metodo="GET"):
    raise ErroRede("rede não injetada")


class AmbienteDoctor(object):
    """O que os checks olham: raiz do repo, sistema, variáveis, PATH, módulos, subprocesso, HTTP.

    Os padrões do construtor são "nada existe, nada responde": um teste que esquece de injetar
    algo falha de forma barata em vez de tocar a máquina. Em produção use `real()`.
    """

    def __init__(self, raiz, sistema="Darwin", arquitetura="arm64", env=None, which=None,
                 importavel=None, executar=None, http_get=None, python="python3", bins_venv=()):
        self.raiz = Path(raiz)
        self.sistema = sistema
        self.arquitetura = arquitetura
        self.env = dict(env or {})
        self.which = which or _nunca
        self.importavel = importavel or _nao_importa
        self.executar = executar or _sem_comando
        self.http_get = http_get or _sem_rede
        self.python = python
        self.bins_venv = tuple(Path(b) for b in bins_venv)

    @property
    def apple_silicon(self):
        return self.sistema == "Darwin" and self.arquitetura == "arm64"

    @property
    def venv_python(self):
        """O Python do `.venv` do repo se existe e executa; senão None."""
        candidato = self.raiz / ".venv" / "bin" / "python"
        if candidato.is_file() and os.access(str(candidato), os.X_OK):
            return candidato
        return None

    def para_transcritor(self):
        """O mesmo ambiente, no formato que o `audio.transcrever` escolhe backend."""
        from audio.transcrever import Ambiente
        return Ambiente(sistema=self.sistema, arquitetura=self.arquitetura, env=self.env,
                        which=self.which, importavel=self.importavel,
                        bins_venv=self.bins_venv)

    @classmethod
    def real(cls, raiz=None):
        raiz = Path(raiz) if raiz is not None else RAIZ_DO_REPO
        # Variável do ambiente manda; o .env do repo só completa o que falta.
        env = dict(carregar_dotenv(raiz / ".env"))
        env.update(os.environ)
        bins = []
        for b in (Path(sys.executable).parent, Path(sysconfig.get_path("scripts") or "."),
                  raiz / ".venv" / "bin"):
            if b not in bins:
                bins.append(b)
        return cls(raiz=raiz, sistema=platform.system(), arquitetura=platform.machine(), env=env,
                   which=shutil.which,
                   importavel=lambda nome: importlib.util.find_spec(nome) is not None,
                   executar=_executar_real, http_get=_http_get_real, python=sys.executable,
                   bins_venv=bins)


# --- o runner ---------------------------------------------------------------------------------------

def checks_padrao():
    """Os módulos de check, na ordem em que aparecem no painel."""
    return [importlib.import_module("%s.checks.%s" % (__package__ or "onboarding", nome))
            for nome in CHECKS]


def rodar_checks(amb, checks=None):
    resultados = []
    for modulo in (checks if checks is not None else checks_padrao()):
        nome = getattr(modulo, "NOME", getattr(modulo, "__name__", "check"))
        try:
            r = modulo.checar(amb)
            if not isinstance(r, Resultado):
                raise TypeError("o check devolveu %s em vez de Resultado" % type(r).__name__)
        except Exception as erro:   # um check quebrado nunca derruba o painel nem mostra traceback
            r = Resultado(nome, FAIL,
                          "o check falhou por dentro: %s: %s" % (type(erro).__name__, erro),
                          "rode de novo; se repetir, reporte esta linha")
        resultados.append(r)
    return resultados


def codigo_de_saida(resultados):
    return 1 if any(r.status == FAIL for r in resultados) else 0


def formatar(resultados):
    linhas = []
    for r in resultados:
        linha = "[%s] %s" % (r.status, r.nome)
        if r.detalhe:
            linha += ": " + r.detalhe
        linhas.append(linha)
        if r.status != OK and r.conserto:
            linhas.append("       conserto: " + r.conserto)
    n = {s: sum(1 for r in resultados if r.status == s) for s in STATUS}
    linhas.append("")
    linhas.append("%d ok, %d aviso(s), %d falha(s)." % (n[OK], n[WARN], n[FAIL]))
    if n[FAIL]:
        linhas.append("Aplique os consertos acima e rode de novo: python3 scripts/vam.py doctor")
    else:
        linhas.append("Ambiente pronto." + (" Os avisos não impedem o build." if n[WARN] else ""))
    return "\n".join(linhas)


def main(argv=None, amb=None):
    import argparse
    ap = argparse.ArgumentParser(description="Confere o ambiente do aluno antes de um build.")
    ap.add_argument("--raiz", help="raiz do repo (padrão: a deste arquivo)")
    args = ap.parse_args(argv)
    amb = amb or AmbienteDoctor.real(raiz=args.raiz)
    print("vam doctor: o ambiente em %s\n" % amb.raiz)
    resultados = rodar_checks(amb)
    print(formatar(resultados))
    return codigo_de_saida(resultados)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from onboarding.doctor import main as _main
    sys.exit(_main())
