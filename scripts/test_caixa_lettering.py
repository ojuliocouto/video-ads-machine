#!/usr/bin/env python3
"""Testes de caixa_lettering.py. Rodar: python3 test_caixa_lettering.py"""
import sys
from PIL import ImageFont
from caixa_lettering import (COLORWAYS, LARGURA_CAIXA, TAM_MAX, achar_fonte,
                             quebrar_linhas, cabe, ajustar, render_caixa, montar_overlay)

falhas = []
def checa(cond, nome, det=""):
    print(f"  {'ok  ' if cond else 'FALHA'} {nome}" + (f"  {det}" if not cond else ""))
    if not cond:
        falhas.append(nome)

FP = achar_fonte()
TXT = "Esse desconto só vai aparecer pra você uma vez."


print("\ncolorways: exatamente os tres, com contraste invertido entre eles")
checa(set(COLORWAYS) == {"ambar", "branco", "preto"}, "so os tres colorways aprovados")
checa(COLORWAYS["ambar"]["fundo"][:3] == (254, 198, 77), "ambar e o tom do one-shot")
for nome, c in COLORWAYS.items():
    lum_f = sum(c["fundo"][:3]) / 3
    lum_t = sum(c["texto"][:3]) / 3
    checa(abs(lum_f - lum_t) > 100, f"{nome}: contraste forte fundo x texto",
          f"fundo={lum_f:.0f} texto={lum_t:.0f}")


print("\ncanto RETO (o widget nativo do Instagram e reto)")
img = render_caixa("Oi", 400, 200, "ambar")
cantos = [img.getpixel(p) for p in [(0, 0), (399, 0), (0, 199), (399, 199)]]
checa(all(c[3] == 255 for c in cantos),
      "os quatro cantos sao opacos (arredondado deixaria alpha 0)", f"{cantos}")
checa(all(c[:3] == COLORWAYS["ambar"]["fundo"][:3] for c in cantos),
      "e da cor do fundo, nao transparentes")


print("\nfundo solido: sem sombra, sem contorno, sem gradiente")
img = render_caixa("Oi", 400, 200, "branco")
borda = [img.getpixel((x, 2)) for x in range(0, 400, 40)]
checa(len({p[:3] for p in borda}) == 1, "a faixa de topo tem UMA cor so", f"{set(borda)}")


print("\nquebra de linha por palavra")
f = ImageFont.truetype(FP, 60)
linhas = quebrar_linhas(TXT, f, 700)
checa(len(linhas) >= 2, "texto longo quebra em varias linhas", f"{linhas}")
checa(all(f.getbbox(l)[2] - f.getbbox(l)[0] <= 700 for l in linhas),
      "nenhuma linha estoura a largura util")
checa(" ".join(linhas).split() == TXT.split(), "nenhuma palavra perdida na quebra")


print("\nfonte MEDIDA, nunca chutada")
tam_g, *_ = ajustar(TXT, 728, 198, FP)
tam_p, *_ = ajustar(TXT, 300, 400, FP)
checa(tam_g > tam_p, "caixa mais larga aceita fonte maior", f"{tam_g} vs {tam_p}")
tam, ft, linhas, alt, gap, bloco = ajustar(TXT, 728, 198, FP)
checa(max(ft.getbbox(l)[2] - ft.getbbox(l)[0] for l in linhas) <= 728,
      "o tamanho escolhido de fato CABE na largura")
checa(bloco <= 198, "e cabe na altura", f"bloco={bloco}")
# usa o MESMO predicado do codigo: teste que reimplementa o criterio por fora
# valida a propria copia, nao o codigo.
checa(cabe(TXT, tam, 728, 198, FP) is not None, "o tamanho escolhido cabe pelo predicado")
checa(all(cabe(TXT, t, 728, 198, FP) is None for t in range(tam + 1, TAM_MAX)),
      "e nenhum tamanho MAIOR cabe (e o maximo de verdade)")


print("\noverlay: caixa centrada e do tamanho do frame")
ov = montar_overlay(TXT, (1080, 1920), centro_y=0.786, colorway="ambar")
checa(ov.size == (1080, 1920), "overlay tem o tamanho do frame", f"{ov.size}")
checa(ov.getpixel((5, 5))[3] == 0, "fora da caixa e transparente")
checa(ov.getpixel((540, int(0.786 * 1920)))[3] == 255, "no centro-y tem caixa opaca")
esq = next(x for x in range(1080) if ov.getpixel((x, int(0.786 * 1920)))[3] == 255)
dir_ = next(x for x in range(1079, -1, -1) if ov.getpixel((x, int(0.786 * 1920)))[3] == 255)
checa(abs(esq - (1080 - 1 - dir_)) <= 2, "margem esquerda == direita (centrada)",
      f"esq={esq} dir={1080-1-dir_}")
checa(abs((dir_ - esq + 1) - round(LARGURA_CAIXA * 1080)) <= 2,
      "largura bate com LARGURA_CAIXA", f"{dir_-esq+1}")


print("\n1:1 tambem funciona")
ov = montar_overlay("Título curto", (1080, 1080), colorway="preto")
checa(ov.size == (1080, 1080), "canvas quadrado aceito")


print()
if falhas:
    print(f"{len(falhas)} FALHA(S): {falhas}")
    sys.exit(1)
print("todos os testes passaram")
