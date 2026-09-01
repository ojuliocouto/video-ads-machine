#!/usr/bin/env python3
"""Testes de ate_do_cta (produzir_ad.py). Cada bug real vira teste; nenhum e hipotetico.

Nasceu de ligar o gate de contraste da legenda no build (29/08/2026): o --ate precisa
do instante do CTA no relogio do ENTREGUE, calculado a partir do data-start (no relogio
do overlay, ja acelerado e deslocado por a0) do elemento id="cta" do index_overlay.html.

Rodar: python3 test_gate_contraste_no_build.py
"""
import sys

from produzir_ad import ate_do_cta

falhas = []


def checa(cond, nome, detalhe=""):
    if cond:
        print(f"  ok   {nome}")
    else:
        print(f"  FALHA {nome}  {detalhe}")
        falhas.append(nome)


HTML_COM_CTA = (
    '<div data-hf-id="hf-bi9a" id="cta" class="clip" data-start="116.62" '
    'data-duration="4.96" data-track-index="46"></div>'
)
HTML_SEM_CTA = (
    '<div data-hf-id="hf-bi9a" id="legenda" class="clip" data-start="12.00" '
    'data-duration="1.10" data-track-index="3"></div>'
)

print("\nate_do_cta: html com id=cta devolve o instante no relogio do entregue")
ate = ate_do_cta(HTML_COM_CTA, a0=0.24, accel=1.35)
checa(ate is not None, "achou o cta", f"ate={ate}")
checa(abs(ate - 86.21) < 0.01, "instante bate com (116.62 - 0.24) / 1.35", f"ate={ate}")

print("\nate_do_cta: html sem id=cta devolve None (gate mede o anuncio inteiro)")
checa(ate_do_cta(HTML_SEM_CTA, a0=0.24, accel=1.35) is None, "sem cta -> None")

print("\nate_do_cta: ordem dos atributos nao importa (data-start antes de id)")
html_invertido = (
    '<div data-start="50.00" class="clip" id="cta" data-duration="4.96"></div>'
)
ate2 = ate_do_cta(html_invertido, a0=0.0, accel=1.0)
checa(ate2 == 50.0, "acha o cta com data-start antes do id", f"ate2={ate2}")

print()
if falhas:
    print(f"{len(falhas)} FALHA(S): {falhas}")
    sys.exit(1)
print("todos os testes passaram")
