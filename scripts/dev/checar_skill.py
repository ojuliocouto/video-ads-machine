#!/usr/bin/env python3
"""Confere a skill como o aluno a lê: link quebrado, comando que não existe e caminho da máquina do dono.

    python3 scripts/dev/checar_skill.py                 confere os arquivos versionados da raiz do repo
    python3 scripts/dev/checar_skill.py --raiz PASTA    confere uma pasta qualquer (usa o vam.py e o cli/ dela)

Três reprovações:
  1. link `[[alvo]]` (ou `[[alvo|rótulo]]`, `[[alvo#âncora]]`) nos .md que não aponta para nenhum arquivo do repo. O alvo
     vale se for um caminho a partir da raiz, com ou sem `.md`, ou o nome de um .md de references/ ou docs/. Código em
     bloco e em crase não conta (é o `[[ -f x ]]` do bash, por exemplo);
  2. comando `vam X` citado em código dos .md (bloco ou crase) que o `vam` não registra. Os comandos vêm de scripts/cli/;
  3. qualquer `~/.claude` nos arquivos de texto do repo. A skill do aluno não conhece a pasta de configuração do dono.
     Isenção declarada: ISENTOS_CLAUDE (o resolvedor de gates que mantém o caminho antigo por compatibilidade e o teste
     que o prova).

Saídas: 0 limpo · 1 achou problema (imprime arquivo:linha e o motivo). Python 3.9, só biblioteca padrão.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

SUFIXOS_TEXTO = {".py", ".sh", ".md", ".json", ".txt", ".html", ".css", ".js", ".mjs", ".yml", ".yaml", ".toml",
                 ".ini", ".cfg", ".example"}
NOMES_TEXTO = {"LICENSE", "NOTICE", ".gitignore"}
ISENTOS_CLAUDE = {"scripts/caminhos.py", "scripts/test_gate_resolver.py", "scripts/dev/checar_skill.py",
                  "tests/dev/test_checar_skill.py", "tests/gravado/test_sem_cliente.py"}
PAGO = "~/" + ".claude"          # montado em pedaços para este arquivo não ser o primeiro a violar a regra
LINK = re.compile(r"\[\[([^\[\]\n]+?)\]\]")
COMANDO = re.compile(r"\bvam ([a-z][a-z0-9_-]*)")
CERCA = re.compile(r"^\s*(```|~~~)")


def versionados(raiz):
    """Caminhos relativos dos arquivos do git; sem git, a pasta toda menos .git, _local, .venv e node_modules."""
    raiz = Path(raiz)
    try:
        r = subprocess.run(["git", "-C", str(raiz), "ls-files", "-z"], capture_output=True, timeout=60)
        if r.returncode == 0 and r.stdout:
            return sorted(n.decode("utf-8") for n in r.stdout.split(b"\0") if n)
    except (OSError, subprocess.SubprocessError):
        pass
    saida = []
    for p in raiz.rglob("*"):
        partes = set(p.relative_to(raiz).parts)
        if p.is_file() and not partes & {".git", "_local", ".venv", "node_modules", "__pycache__"}:
            saida.append(str(p.relative_to(raiz)))
    return sorted(saida)


def comandos_do_vam(raiz):
    """Os subcomandos do `vam`: cada scripts/cli/<nome>.py que não começa com _ e define `registrar`."""
    saida = set()
    cli = Path(raiz) / "scripts" / "cli"
    if cli.is_dir():
        for arq in cli.glob("*.py"):
            if not arq.stem.startswith("_") and re.search(r"^def registrar\(", arq.read_text(encoding="utf-8"), re.M):
                saida.add(arq.stem)
    return saida


def _sem_codigo_inline(linha):
    """A linha sem o conteúdo das crases (o texto fica, o código sai)."""
    return re.sub(r"`[^`\n]*`", " ", linha)


def _codigo_da_linha(linha):
    return re.findall(r"`([^`\n]*)`", linha)


def blocos_do_md(texto):
    """(número da linha, texto, em_codigo_de_bloco) de cada linha de um .md."""
    dentro = False
    for n, linha in enumerate(texto.splitlines(), 1):
        if CERCA.match(linha):
            dentro = not dentro
            yield n, linha, True
            continue
        yield n, linha, dentro


def alvo_existe(alvo, arquivos, nomes_md):
    """Um alvo de [[link]] vale se for um caminho do repo (com ou sem .md) ou o nome de um .md de references/ ou docs/."""
    alvo = alvo.split("|", 1)[0].split("#", 1)[0].strip().strip("/")
    if not alvo:
        return False
    if alvo in arquivos or (alvo + ".md") in arquivos:
        return True
    return alvo in nomes_md


def conferir(raiz):
    """Lista de (arquivo, linha, motivo) dos problemas da skill em `raiz`."""
    raiz = Path(raiz)
    arquivos = versionados(raiz)
    conjunto = set(arquivos)
    nomes_md = {Path(a).stem for a in arquivos if a.endswith(".md") and a.split("/")[0] in ("references", "docs")}
    comandos = comandos_do_vam(raiz)
    problemas = []
    for rel in arquivos:
        p = raiz / rel
        if not p.is_file() or not (p.suffix.lower() in SUFIXOS_TEXTO or p.name in NOMES_TEXTO):
            continue
        try:
            texto = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if rel not in ISENTOS_CLAUDE:
            for n, linha in enumerate(texto.splitlines(), 1):
                if PAGO in linha:
                    problemas.append((rel, n, "caminho da configuração do dono no repo da skill"))
        if p.suffix.lower() != ".md":
            continue
        for n, linha, em_bloco in blocos_do_md(texto):
            if not em_bloco:
                for m in LINK.finditer(_sem_codigo_inline(linha)):
                    if not alvo_existe(m.group(1), conjunto, nomes_md):
                        problemas.append((rel, n, "link quebrado [[%s]]" % m.group(1)))
            codigos = [linha] if em_bloco else _codigo_da_linha(linha)
            if comandos:
                for trecho in codigos:
                    for m in COMANDO.finditer(trecho):
                        if m.group(1) not in comandos:
                            problemas.append((rel, n, "comando `vam %s` não existe (os de scripts/cli/: %s)"
                                              % (m.group(1), ", ".join(sorted(comandos)))))
    return problemas


def main(argv=None):
    ap = argparse.ArgumentParser(prog="checar_skill", description=__doc__.split("\n\n")[0])
    ap.add_argument("--raiz", default=str(RAIZ), help="a pasta a conferir (padrão: a raiz do repo)")
    args = ap.parse_args(argv)
    problemas = conferir(args.raiz)
    for rel, linha, motivo in problemas:
        print("%s:%d: %s" % (rel, linha, motivo))
    if problemas:
        print("checar_skill: %d problema(s)." % len(problemas), file=sys.stderr)
        return 1
    print("checar_skill: limpo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
