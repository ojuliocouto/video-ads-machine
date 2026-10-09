"""Normalização do que a paridade compara (W0.3).

Dois runs do mesmo motor em pastas temporárias diferentes têm que dar o MESMO golden.
Tudo que muda de um run para outro sem mudar o comportamento é trocado aqui por um
token estável:

  caminhos do sandbox      <RAIZ> <ESTADO> <DADOS> <MIDIA> <HOME> <TMP>
  nome aleatório de tempdir <TMP>/tmp*   (tempfile.TemporaryDirectory do motor)
  executável do Python     <PY>
  executável do parakeet   <PARAKEET>    (a W2.B muda onde ele é achado: só o caminho)
  executável do hyperframes <HF>
  ffmpeg / ffprobe         só o nome, sem o caminho

Nada aqui é por "parecer igual": só caminho e nome aleatório. Número, filtro, ordem dos
argumentos e texto de HTML passam intactos, e é isso que a paridade tem que enxergar.

Módulo puro (sem ffmpeg, sem rede, sem pytest), para o comparador poder ser testado sem
mídia.
"""
import hashlib
import json
import os
import re

ORDEM_TOKENS = ("TMP", "MIDIA", "ESTADO", "DADOS", "RAIZ", "HOME")
_TEMPDIR_ALEATORIO = re.compile(r"(<TMP>/tmp)[A-Za-z0-9_]{6,}")


def construir_tokens(**caminhos):
    """Lista [(texto_do_caminho, token)] do mais longo para o mais curto.

    Cada caminho entra também na forma `realpath` (no macOS `/var` e `/private/var` são o
    mesmo lugar e o motor pode devolver qualquer um dos dois).
    """
    pares = []
    for nome in ORDEM_TOKENS:
        valor = caminhos.get(nome.lower())
        if not valor:
            continue
        formas = {os.fspath(valor).rstrip("/"), os.path.realpath(os.fspath(valor)).rstrip("/")}
        for forma in formas:
            if forma:
                pares.append((forma, f"<{nome}>"))
    pares.sort(key=lambda p: len(p[0]), reverse=True)
    return pares


def normalizar_texto(texto, tokens):
    """Troca caminhos do sandbox por tokens e tira o nome aleatório de tempdir."""
    for caminho, token in tokens:
        texto = texto.replace(caminho, token)
    return _TEMPDIR_ALEATORIO.sub(r"\1*", texto)


def _executavel(primeiro, tokens):
    base = os.path.basename(primeiro)
    if base in ("ffmpeg", "ffprobe"):
        return base
    if base.startswith("python"):
        return "<PY>"
    if base == "parakeet-mlx":
        return "<PARAKEET>"
    if base == "hyperframes":
        return "<HF>"
    return normalizar_texto(primeiro, tokens)


def normalizar_argv(argv, tokens):
    """argv normalizado (lista nova). O primeiro item é o executável."""
    if not argv:
        return []
    saida = [_executavel(argv[0], tokens)]
    saida.extend(normalizar_texto(a, tokens) for a in argv[1:])
    return saida


def normalizar_registro(registro, tokens):
    """Linha do JSONL do sitecustomize -> linha do golden. `fase` passa como está."""
    if "fase" in registro:
        return {"fase": registro["fase"]}
    cwd = registro.get("cwd")
    return {
        "argv": normalizar_argv(registro.get("argv", []), tokens),
        "cwd": normalizar_texto(cwd, tokens) if cwd else None,
        "shell": bool(registro.get("shell")),
    }


def normalizar_jsonl(texto_bruto, tokens):
    """JSONL bruto do sitecustomize -> lista de registros normalizados, na mesma ordem."""
    saida = []
    for linha in texto_bruto.splitlines():
        linha = linha.strip()
        if linha:
            saida.append(normalizar_registro(json.loads(linha), tokens))
    return saida


def serializar_jsonl(registros):
    """Forma canônica gravada no golden: uma linha por registro, chaves ordenadas."""
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in registros)


def sha256_texto(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()
