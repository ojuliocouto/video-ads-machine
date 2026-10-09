"""Gate de FALA (bruto x limpo): o Voice Isolator comeu palavra?

Re-transcreve o áudio higienizado e compara palavra a palavra com a transcrição do bruto.
Diferença de grafia que o ASR alterna ("para" e "pra") é ruído, não perda: as equivalências vêm
de uma lista curta de alternâncias genéricas do português e do GLOSSÁRIO do aluno (a grafia
conta como igual às suas variantes). Nada específico de cliente mora aqui.

Reprova com mais de max(2, 3% das palavras do bruto) palavras sumidas.

O gate de envelope é a prova que não depende do ASR; este pega a perda que a energia não vê
(o isolador troca uma palavra fraca por outra). Os dois rodam, nesta ordem, antes de avançar.

    python3 scripts/gravado/gate_fala.py [--projeto DIR]
Saída: 0 passou, 1 palavras perdidas, 2 insumo inválido (sem áudio, ASR falhou).
"""
import argparse
import difflib
import re
import sys
import unicodedata
from pathlib import Path

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado import projeto as gp  # noqa: E402
from gravado import veredito  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402

NOME = "gate_fala"
TOL_FRAC = 0.03
TOL_MIN = 2
MIN_LETRAS = 3
AMOSTRA = 8
EQUIV_BASE = ({"para", "pra", "pro"}, {"esta", "ta"}, {"voce", "ce"}, {"e", "eh"})


def norm(texto):
    """Palavras em minúsculas, sem acento e sem pontuação."""
    t = unicodedata.normalize("NFD", str(texto).lower())
    return re.findall(r"[a-z0-9]+", "".join(c for c in t if unicodedata.category(c) != "Mn"))


def grupos_de_equivalencia(glossario=None):
    """Alternâncias aceitas: a base genérica + as do glossário (palavras soltas)."""
    grupos = [set(g) for g in EQUIV_BASE]
    for termo in (glossario or {}).get("termos", []):
        grafia = norm(termo.get("grafia", ""))
        if len(grafia) == 1:
            g = {grafia[0]}
            for v in termo.get("variantes", []):
                if len(norm(v)) == 1:
                    g.add(norm(v)[0])
            if len(g) > 1:
                grupos.append(g)
    for eq in (glossario or {}).get("equivalencias", []):
        r, f = norm(eq.get("roteiro", "")), norm(eq.get("fala", ""))
        if len(r) == 1 and len(f) == 1:
            grupos.append({r[0], f[0]})
    return grupos


def sumidas(texto_bruto, texto_limpo, grupos):
    """([palavras do bruto que sumiram], nº de palavras do bruto, nº do limpo)."""
    wb, wl = norm(texto_bruto), norm(texto_limpo)
    sm = difflib.SequenceMatcher(None, wb, wl, autojunk=False)
    perdidas = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("delete", "replace"):
            ganhas = wl[j1:j2]
            for k, p in enumerate(wb[i1:i2]):
                alvo = ganhas[k] if k < len(ganhas) else ""
                if len(p) >= MIN_LETRAS and not any(p in g and alvo in g for g in grupos):
                    perdidas.append(p)
    return perdidas, len(wb), len(wl)


def verificar(texto_bruto, texto_limpo, glossario=None, tol_frac=TOL_FRAC, tol_min=TOL_MIN):
    perdidas, nb, nl = sumidas(texto_bruto, texto_limpo, grupos_de_equivalencia(glossario))
    if nb == 0:
        raise InsumoInvalido("o bruto não tem fala transcrita: não há o que comparar")
    limite = max(tol_min, nb * tol_frac)
    amostra = ", ".join(perdidas[:AMOSTRA]) + ("..." if len(perdidas) > AMOSTRA else "")
    if len(perdidas) > limite:
        return False, ("%d palavra(s) sumida(s) de %d no bruto (tolerância %.1f): %s"
                       % (len(perdidas), nb, limite, amostra))
    return True, "%d palavra(s) sumida(s) de %d no bruto (tolerância %.1f)%s" % (
        len(perdidas), nb, limite, (": " + amostra) if perdidas else "")


def verificar_projeto(proj, leitor=None, pecas=None):
    from gravado.gate_envelope import takes_para_conferir
    takes = takes_para_conferir(proj)
    if not takes:
        raise InsumoInvalido("nenhum take para conferir: faltam o plano ou os áudios em %s" % proj.pasta("limpo"))
    leitor = leitor or proj.leitor()
    glossario = proj.glossario()
    resultados = []
    for take in takes:
        bruto = veredito.exigir_arquivo(proj.wav(take), "o wav do bruto (rode o extrair_wav)")
        limpo = veredito.exigir_arquivo(proj.limpo(take), "o áudio limpo (rode o isolar)")
        ok, motivo = verificar(leitor.texto_da_peca(bruto), leitor.texto_da_peca(limpo), glossario)
        resultados.append((ok, "%s: %s" % (take, motivo)))
    return veredito.juntar(resultados)


def _parser():
    ap = argparse.ArgumentParser(prog=NOME, description="Bruto x limpo palavra a palavra.")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    return ap


def _verificar(args):
    return verificar_projeto(gp.carregar(args.projeto))


def main(argv=None):
    return veredito.cli(NOME, _parser(), _verificar, argv)


if __name__ == "__main__":
    sys.exit(main())
