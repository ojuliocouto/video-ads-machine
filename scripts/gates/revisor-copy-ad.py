#!/usr/bin/env python3
"""Revisor de COPY do roteiro anotado: pega erro de transcricao antes de virar legenda.

Por que existe (regra do dono do motor, 05/08/2026): a legenda vem do roteiro anotado, que eu
escrevo a partir da transcricao do parakeet. O parakeet ouve "Claude" e escreve
"Cloud": foram 39 ocorrencias em 10 dos 12 anuncios de uma leva de 08/2026, ou seja, o
nome do PRODUTO errado queimado na tela de um anuncio pago. Ninguem revisou porque
nao havia etapa de revisao de copy: a transcricao virava legenda direto.

Checa:
  1. termos da marca escritos errado (Cloud/Claud/Cloude -> Claude)
  2. "I.A" grafado de forma inconsistente dentro do mesmo anuncio
  3. nome do evento/produto incompleto (regras proprias em _local/revisor-trocas.json)
  4. cacos de transcricao (palavra repetida colada, frase iniciada em minuscula)

Uso:
  python3 revisor-copy-ad.py 03 04 ...      revisa
  python3 revisor-copy-ad.py --corrigir 03  aplica as correcoes automaticas
Exit code 1 se sobrar erro.
"""
import json
import os
import re
import sys
from pathlib import Path

# Raiz de scripts/ no sys.path: caminhos.py e a fonte unica dos caminhos do repo.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from caminhos import ESTADO, INPUTS  # noqa: E402

V1 = str(INPUTS)

# (regex, substituicao, descricao): só termos com correção inequívoca
TROCAS = [
    (r"\bCloud\b", "Claude", "nome do produto: Cloud -> Claude"),
    (r"\bCloude\b", "Claude", "Cloude -> Claude"),
    (r"\bClaud\b", "Claude", "Claud -> Claude"),
    (r"\bcloud\b", "Claude", "cloud -> Claude"),
    (r"\bClaude Cod\b", "Claude Code", "Claude Cod -> Claude Code"),
]

# Trocas do SEU anuncio (nome do evento, da marca, do produto): _local/revisor-trocas.json,
# lista de [regex, substituicao, descricao]. Sem o arquivo, so valem as genericas acima.
_EXTRAS = Path(ESTADO) / "revisor-trocas.json"
if _EXTRAS.exists():
    try:
        TROCAS += [tuple(x) for x in json.loads(_EXTRAS.read_text(encoding="utf-8"))]
    except (ValueError, TypeError):
        print(f"AVISO: {_EXTRAS} invalido, ignorado (esperado: lista de [regex, troca, descricao])")

# avisos que exigem olho humano, nao corrigidos sozinhos
SUSPEITOS = [
    (r"\btime de A\b", 'ambíguo: "time de A" provavelmente é "time de I.A"'),
    (r"\bde A que\b", 'ambíguo: "de A que" provavelmente é "de I.A que"'),
    (r"\bagentes de A\b", '"agentes de A" provavelmente é "agentes de I.A"'),
    (r"\bfuncionários de A\b", '"funcionários de A" provavelmente é "de I.A"'),
    (r"\b(\w+) \1\b", "palavra repetida (caco de transcrição)"),
]


def fala(linha):
    """So o texto falado: a direcao entre colchetes nao vira legenda."""
    return re.sub(r"^\[[^\]]*\]\s*", "", linha).strip()


def _leva(n):
    """A leva do anúncio `n`: `<n>_leva.txt` (nome do projeto, como o motor do produto grava) ou o nome antigo."""
    for nome in (f"{n}_leva.txt", f"ad{n}v2_leva.txt"):
        p = os.path.join(V1, nome)
        if os.path.exists(p):
            return p
    return None


def revisar(n, corrigir=False):
    p = _leva(n)
    if p is None:
        return None
    linhas = open(p, encoding="utf-8").read().split("\n")
    achados, novas = [], []
    for i, l in enumerate(linhas, 1):
        t = fala(l)
        nova = l
        if t:
            for rx, sub, desc in TROCAS:
                if re.search(rx, t):
                    achados.append((i, "ERRO", desc, t[:70]))
                    if corrigir:
                        # troca so na parte falada, preserva a direcao entre colchetes
                        m = re.match(r"^(\[[^\]]*\]\s*)(.*)$", nova, re.S)
                        if m:
                            nova = m.group(1) + re.sub(rx, sub, m.group(2))
                        else:
                            nova = re.sub(rx, sub, nova)
            for rx, desc in SUSPEITOS:
                if re.search(rx, t, re.I):
                    achados.append((i, "AVISO", desc, t[:70]))
        novas.append(nova)

    if corrigir and any(a[1] == "ERRO" for a in achados):
        open(p, "w", encoding="utf-8").write("\n".join(novas))
    return achados


def main():
    if any(a in ("-h", "--help") for a in sys.argv[1:]):
        print(__doc__)
        return
    corrigir = "--corrigir" in sys.argv
    # id alfanumérico (pendência 12, item 3): só número deixava de fora qualquer anúncio com nome, e o revisor
    # "passava" sem ter lido nada
    alvos = [a for a in sys.argv[1:] if not a.startswith("-")] or [f"{i:02d}" for i in range(1, 13)]
    erros_totais = 0
    sem_roteiro = 0
    for n in alvos:
        a = revisar(n, corrigir)
        if a is None:
            sem_roteiro += 1
            continue
        erros = [x for x in a if x[1] == "ERRO"]
        avisos = [x for x in a if x[1] == "AVISO"]
        erros_totais += len(erros)
        if not a:
            print(f"AD{n}: copy limpa")
            continue
        print(f"\nAD{n}: {len(erros)} erro(s), {len(avisos)} aviso(s)")
        for i, tipo, desc, tr in a[:8]:
            print(f"  L{i:3d} [{tipo}] {desc}")
            print(f"        {tr}")
    if sem_roteiro == len(alvos):
        # nenhum roteiro do SEU anuncio encontrado: uma mensagem so, nao silencio
        from material_local import exigir
        exigir(Path(V1) / f"{alvos[0]}_leva.txt", "o roteiro anotado do seu anúncio")
    if corrigir:
        print(f"\n{erros_totais} erro(s) corrigido(s). Rode de novo pra conferir.")
    sys.exit(1 if erros_totais and not corrigir else 0)


if __name__ == "__main__":
    main()
