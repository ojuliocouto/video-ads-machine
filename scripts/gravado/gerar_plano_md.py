"""Gera o PLANO-CORTES.md a partir do plano, para o documento nunca divergir do código.

Cada anúncio vira uma tabela por versão (CTA normal e CTA com desconto): take, entrada, saída e
duração de cada segmento DEPOIS do cortador de ar morto. Não editar o markdown à mão: o plano é
a fonte.

    python3 scripts/gravado/gerar_plano_md.py [--projeto DIR]
"""
import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado import montar, veredito  # noqa: E402
from gravado import projeto as gp  # noqa: E402


def gerar(proj):
    """O markdown do plano de cortes, como texto."""
    acel = proj.accel
    linhas = ["# Plano de cortes (gerado do plano)", "",
              "Gerado por `gerar_plano_md.py` a partir de `plano_gravado.json`. Não editar à mão:",
              "o plano é a fonte. Tempos medidos no áudio higienizado, palavra a palavra.", "",
              "Aceleração final %sx. Corpo e CTA são listas separadas, e só a cauda troca" % acel,
              "entre a versão normal e a com desconto.", ""]
    for cod, ad in proj.ads.items():
        linhas.append("## %s: %s" % (cod, ad.get("nome", cod)))
        linhas.append("")
        versoes = [("CTA normal", False)] + ([("CTA com desconto", True)] if "cta_desconto" in ad else [])
        for rotulo, desconto in versoes:
            segs = montar.segmentos_do_ad(proj, cod, desconto)
            total = sum(e - s for _, s, e in segs)
            linhas.append("**%s** (%d segmentos, %.2fs de fala, %.1fs finais)" % (rotulo, len(segs), total, total / acel))
            linhas.append("")
            linhas.append("| take | entra | sai | dur |")
            linhas.append("|---|---|---|---|")
            for take, s, e in segs:
                linhas.append("| %s | %.2f | %.2f | %.2fs |" % (take, s, e, e - s))
            linhas.append("")
    return "\n".join(linhas) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Regera o PLANO-CORTES.md a partir do plano.")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    a = ap.parse_args(argv)

    def fazer():
        proj = gp.carregar(a.projeto)
        texto = gerar(proj)
        proj.plano_md.write_text(texto, encoding="utf-8")
        print("%s regerado: %d linhas" % (proj.plano_md.name, texto.count("\n")))
    return veredito.ferramenta(fazer)


if __name__ == "__main__":
    sys.exit(main())
