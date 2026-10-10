#!/usr/bin/env python3
"""Varredura de nomes proibidos: o repo público não pode carregar nome de pessoa, de cliente, de evento nem de look.

    python3 scripts/dev/varrer_nomes.py                 varre os arquivos versionados (git ls-files) da raiz do repo
    python3 scripts/dev/varrer_nomes.py --raiz PASTA    varre os arquivos de texto de uma pasta qualquer
    python3 scripts/dev/varrer_nomes.py --denylist F    usa outra lista de hashes (padrão: scripts/dev/denylist.sha256)

Como funciona: `denylist.sha256` guarda o sha256 de cada termo proibido (minúsculas, sem acento), um por linha. A
varredura tira de cada linha de texto as sequências de 1 a 3 palavras (só letras, sem caixa, sem acento), calcula o
hash de cada uma e confere se está na lista. Assim o repo não carrega os nomes que proíbe. Número e símbolo colados na
palavra não escondem o termo ("PALAVRA13" vira a palavra "palavra"). Um nome de código com número ("ab12v2") também
é conferido pelos prefixos de 3 a 8 caracteres, para pegar o termo que tem número no meio. O nome do arquivo também é
varrido.

Isenção única e declarada: nos arquivos LICENSE e NOTICE a linha de copyright é o titular legal da licença e não conta.

Saídas: 0 limpo · 1 achou termo proibido (imprime arquivo:linha e o trecho) · 2 lista de hashes ausente ou inválida.
Python 3.9, só biblioteca padrão.
"""
import argparse
import hashlib
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DENYLIST = Path(__file__).resolve().parent / "denylist.sha256"

SUFIXOS = {".py", ".sh", ".md", ".json", ".txt", ".html", ".css", ".js", ".mjs", ".yml", ".yaml", ".toml", ".ini",
           ".cfg", ".example", ".ass", ".csv", ".svg"}
NOMES = {"LICENSE", "NOTICE", ".gitignore", ".env.example", "requirements.txt"}
PULAR = {"package-lock.json"}
TETO_BYTES = 3 * 1024 * 1024            # arquivo maior que isso não é texto do produto (dado gerado)
ISENTOS_COPYRIGHT = {"LICENSE", "NOTICE"}
PADRAO_HASH = re.compile(r"^[0-9a-f]{64}$")
PALAVRAS = re.compile(r"[^\W\d_]+")
CODIGOS = re.compile(r"[^\W_]*\d[^\W_]*")        # nome com número ("ab12v2"): termo de código, como o de anúncio


def sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def sha(texto):
    return hashlib.sha256(unicodedata.normalize("NFC", texto).encode("utf-8")).hexdigest()


def carregar_hashes(caminho):
    """O conjunto de hashes da lista. FileNotFoundError se não existe; ValueError se uma linha não é um sha256."""
    saida = set()
    for n, linha in enumerate(Path(caminho).read_text(encoding="utf-8").splitlines(), 1):
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        if not PADRAO_HASH.match(linha):
            raise ValueError("%s:%d não é um sha256 em minúsculas" % (caminho, n))
        saida.add(linha)
    if not saida:
        raise ValueError("%s não tem nenhum hash" % caminho)
    return saida


def achados_no_texto(texto, hashes):
    """Trechos de 1 a 3 palavras (sem caixa e sem acento) cujo sha256 está na lista."""
    palavras = [sem_acento(t) for t in PALAVRAS.findall(texto.casefold())]
    achados = []
    for n in (1, 2, 3):
        for i in range(len(palavras) - n + 1):
            trecho = " ".join(palavras[i:i + n])
            if sha(trecho) in hashes:
                achados.append(trecho)
    for codigo in CODIGOS.findall(texto.casefold()):
        codigo = sem_acento(codigo)
        for k in range(3, min(len(codigo), 8) + 1):
            if sha(codigo[:k]) in hashes:
                achados.append(codigo[:k])
    return achados


def _eh_texto(p):
    return p.name in NOMES or p.suffix.lower() in SUFIXOS


def arquivos_versionados(raiz):
    """Os arquivos do git (rastreados); sem git, o passeio pela pasta ignorando .git, _local, .venv e node_modules."""
    try:
        r = subprocess.run(["git", "-C", str(raiz), "ls-files", "-z"], capture_output=True, timeout=60)
        if r.returncode == 0 and r.stdout:
            return [Path(raiz) / n.decode("utf-8") for n in r.stdout.split(b"\0") if n]
    except (OSError, subprocess.SubprocessError):
        pass
    saida = []
    for dirpath, dirnames, nomes in os.walk(str(raiz)):
        dirnames[:] = [d for d in dirnames if d not in (".git", "_local", ".venv", "node_modules", "__pycache__")]
        for n in nomes:
            saida.append(Path(dirpath) / n)
    return saida


def varrer(raiz, hashes, arquivos=None):
    """Lista de (caminho relativo, linha ou 0 para o nome do arquivo, trecho) dos termos achados."""
    raiz = Path(raiz)
    achados = []
    for p in sorted(arquivos if arquivos is not None else arquivos_versionados(raiz)):
        if not p.is_file() or p.name in PULAR or p.name.endswith(".sha256") or not _eh_texto(p):
            continue
        rel = str(p.relative_to(raiz)) if raiz in p.parents else str(p)
        for trecho in achados_no_texto(rel, hashes):
            achados.append((rel, 0, trecho))
        try:
            if p.stat().st_size > TETO_BYTES:
                continue
            texto = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, linha in enumerate(texto.splitlines(), 1):
            if p.name in ISENTOS_COPYRIGHT and linha.strip().lower().startswith("copyright"):
                continue
            for trecho in achados_no_texto(linha, hashes):
                achados.append((rel, n, trecho))
    return achados


def main(argv=None):
    ap = argparse.ArgumentParser(prog="varrer_nomes", description=__doc__.split("\n\n")[0])
    ap.add_argument("--raiz", default=str(RAIZ), help="a pasta a varrer (padrão: a raiz do repo)")
    ap.add_argument("--denylist", default=str(DENYLIST), help="a lista de hashes sha256 dos termos proibidos")
    args = ap.parse_args(argv)
    try:
        hashes = carregar_hashes(args.denylist)
    except (OSError, ValueError) as e:
        print("varrer_nomes: lista de hashes inválida: %s" % e, file=sys.stderr)
        return 2
    achados = varrer(args.raiz, hashes)
    for rel, linha, trecho in achados:
        print("%s:%s: termo proibido %r" % (rel, linha if linha else "(nome do arquivo)", trecho))
    if achados:
        print("varrer_nomes: %d achado(s). Troque por termo genérico (o apresentador, o diretor, a estrategista, "
              "o evento, look_a)." % len(achados), file=sys.stderr)
        return 1
    print("varrer_nomes: limpo (%d hashes na lista)" % len(hashes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
