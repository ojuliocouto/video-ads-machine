"""Varredura completa: TODO trecho de TODO anúncio, quebrado em sub-blocos e lido um a um.

Cobre `corpo`, `corpo_desconto`, `cta_normal` e `cta_desconto` de todos os anúncios, sem repetir o
mesmo trecho, e imprime quantos trechos conferiu. Existe porque analisar o corpo frase a frase e
esquecer os takes de CTA deixou passar uma abertura abortada em duas versões: lista que se confere
em partes deixa parte sem conferir.

Com `--janela TAKE INI FIM` lista os sub-blocos de uma janela qualquer do take, com texto.

    python3 scripts/gravado/varredura_total.py [--projeto DIR]
    python3 scripts/gravado/varredura_total.py --janela IMG_0001 56 63 [--projeto DIR]
"""
import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado import projeto as gp  # noqa: E402
from gravado import veredito  # noqa: E402
from gravado.nucleo import segmentos  # noqa: E402


def subblocos_lidos(audio, ini, fim, leitor):
    return [(a, b, leitor.texto(audio, a, b)) for a, b in segmentos.subblocos(audio, ini, fim)]


def varrer(proj, leitor):
    """[{cod, chave, take, ini, fim, subblocos: [(a, b, texto)]}] de cada trecho distinto do plano."""
    achados = []
    for cod, chave, take, ini, fim in proj.todos_os_trechos():
        audio = veredito.exigir_arquivo(proj.limpo(take), "o áudio limpo do take %s (rode o isolar)" % take)
        achados.append({"cod": cod, "chave": chave, "take": take, "ini": ini, "fim": fim,
                        "subblocos": subblocos_lidos(audio, ini, fim, leitor)})
    return achados


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lê todos os sub-blocos de todos os trechos do plano.")
    ap.add_argument("--janela", nargs=3, metavar=("TAKE", "INI", "FIM"))
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    a = ap.parse_args(argv)

    def fazer():
        proj = gp.carregar(a.projeto)
        leitor = proj.leitor()
        if a.janela:
            take, ini, fim = a.janela[0], float(a.janela[1]), float(a.janela[2])
            audio = veredito.exigir_arquivo(proj.limpo(take), "o áudio limpo do take %s" % take)
            for x, y, t in subblocos_lidos(audio, ini, fim, leitor):
                print("   %7.2f > %7.2f (%4.2fs)  %s" % (x, y, y - x, t))
            return
        achados = varrer(proj, leitor)
        for ach in achados:
            print("\n%s %s %s [%s a %s]  (%d sub-blocos)" % (ach["cod"], ach["chave"], ach["take"], ach["ini"],
                                                           ach["fim"], len(ach["subblocos"])))
            for x, y, t in ach["subblocos"]:
                print("    %7.2f > %7.2f (%4.2fs)  %s" % (x, y, y - x, t))
        print("\n%d trechos distintos conferidos" % len(achados))
    return veredito.ferramenta(fazer)


if __name__ == "__main__":
    sys.exit(main())
