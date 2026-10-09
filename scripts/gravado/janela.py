"""As palavras com tempo numa janela do take, e onde uma frase está dita.

Serve para medir a borda de um trecho: `--achar "frase"` devolve o início e o fim de cada vez que
a frase aparece, nas palavras cronometradas (sem diferenciar acento, caixa nem pontuação). A
borda de PALAVRA se mede pelo tempo de palavra do transcritor local (parakeet ou faster-whisper),
nunca lendo o texto de um recorte: o ASR omite o fragmento da borda numa ponta e inventa o que
falta na outra. O leitor recusa a Groq aqui, que infla o token.

    python3 scripts/gravado/janela.py TAKE INI FIM [--projeto DIR]
    python3 scripts/gravado/janela.py TAKE --achar "uma frase" [--projeto DIR]
    python3 scripts/gravado/janela.py --peca montados/A1_normal.mp4 INI FIM
"""
import argparse
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


def _tokens(texto):
    t = unicodedata.normalize("NFD", str(texto).lower())
    return re.findall(r"[a-z0-9]+", "".join(c for c in t if unicodedata.category(c) != "Mn"))


def palavras_na_janela(palavras, ini, fim):
    return [w for w in palavras if w["end"] >= ini and w["start"] <= fim]


def achar(palavras, frase):
    """[(início, fim)] de cada ocorrência da frase nas palavras cronometradas."""
    alvo = _tokens(frase)
    if not alvo:
        return []
    chaves = [(_tokens(w["text"]) or [""])[0] for w in palavras]
    saida = []
    for i in range(len(chaves) - len(alvo) + 1):
        if chaves[i:i + len(alvo)] == alvo:
            saida.append((palavras[i]["start"], palavras[i + len(alvo) - 1]["end"]))
    return saida


def main(argv=None):
    ap = argparse.ArgumentParser(description="Palavras cronometradas numa janela, ou onde uma frase foi dita.")
    ap.add_argument("alvo", nargs="?", help="o take (sem extensão), ou use --peca")
    ap.add_argument("ini", nargs="?", type=float)
    ap.add_argument("fim", nargs="?", type=float)
    ap.add_argument("--achar", help="a frase a localizar")
    ap.add_argument("--peca", help="arquivo de uma peça montada, em vez de um take")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    a = ap.parse_args(argv)

    def fazer():
        proj = gp.carregar(a.projeto)
        if a.peca:
            audio = veredito.exigir_arquivo(a.peca, "a peça")
        elif a.alvo:
            audio = veredito.exigir_arquivo(proj.limpo(a.alvo), "o áudio limpo do take %s" % a.alvo)
        else:
            raise veredito.InsumoInvalido("passe o take (ou --peca) e a janela, ou --achar FRASE")
        palavras = proj.leitor().palavras(audio, exigir_borda=True)
        if a.achar:
            achados = achar(palavras, a.achar)
            for n, (x, y) in enumerate(achados, 1):
                print("  #%d  [%6.2f > %6.2f]" % (n, x, y))
            if not achados:
                print("  (não achei %r)" % a.achar)
            return
        ini = 0.0 if a.ini is None else a.ini
        fim = palavras[-1]["end"] if a.fim is None and palavras else (a.fim or 0.0)
        print("  " + " ".join("%s[%.2f>%.2f]" % (w["text"], w["start"], w["end"])
                              for w in palavras_na_janela(palavras, ini, fim)))
    return veredito.ferramenta(fazer)


if __name__ == "__main__":
    sys.exit(main())
