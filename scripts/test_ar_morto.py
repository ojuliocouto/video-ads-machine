#!/usr/bin/env python3
"""Testes de ar_morto.py. Cada bug real virou um teste; nenhum e hipotetico.

Rodar: python3 test_ar_morto.py
"""
import sys
from ar_morto import (PADRAO, e_fala, blocos_de_fala, corridas_silencio,
                      planejar_cortes, segmentos_manter)

JAN = 0.02
FALA_DB, SILENCIO_DB = -12.0, -45.0


def onda(dur, trechos_de_fala):
    """Curva de dB sintetica: silencio por padrao, fala nos trechos dados."""
    n = int(round(dur / JAN))
    db = [SILENCIO_DB] * n
    for a, b in trechos_de_fala:
        for i in range(int(round(a / JAN)), min(n, int(round(b / JAN)))):
            db[i] = FALA_DB
    return db


def duracao_cortada(cortes):
    return sum(b - a for a, b in cortes)


falhas = []
def checa(cond, nome, detalhe=""):
    if cond:
        print(f"  ok   {nome}")
    else:
        print(f"  FALHA {nome}  {detalhe}")
        falhas.append(nome)


# ---------------------------------------------------------------- bug 3
print("\nbug 3: token de pontuacao nao pode ancorar borda de fala")
checa(e_fala("casa"), "palavra e fala")
checa(not e_fala("."), "ponto nao e fala")
checa(not e_fala(" , "), "virgula com espaco nao e fala")
checa(not e_fala("?!"), "pontuacao composta nao e fala")
checa(e_fala("nao."), "palavra com ponto colado ainda e fala")

toks = [(1.00, 1.20, "fim"), (1.20, 1.44, "."), (2.40, 2.60, "Eu")]
b = blocos_de_fala(toks)
checa(b == [(1.00, 1.20), (2.40, 2.60)],
      "pontuacao fora dos blocos (senao o vao 1.20-2.40 vira 1.44-2.40)", f"deu {b}")


# ---------------------------------------------------------------- bug 2
print("\nbug 2: RESPIRO e a pausa que SOBRA, nao a janela que se remove")
# fala 0-1s, silencio 1-2.04s (1.04s), fala 2.04-3s
db = onda(3.0, [(0.0, 1.0), (2.04, 3.0)])
blocos = [(0.0, 1.0), (2.04, 3.0)]
cortes = planejar_cortes(blocos, db, JAN, 3.0)
removido = duracao_cortada(cortes)
sobra = 1.04 - removido
checa(removido > 0.60,
      f"vao de 1.04s perde bem mais que RESPIRO (removeu {removido:.2f}s)",
      "o bug antigo removia so 0.22s")
checa(abs(sobra - (PADRAO["respiro"] + 2 * PADRAO["folga"])) < 0.05,
      f"sobra ~= respiro + 2x folga (sobrou {sobra:.2f}s)")


# ---------------------------------------------------------------- bug 4
print("\nbug 4: silencio ALEM da borda do token (ASR estica a vogal)")
# a onda diz que a fala morre em 1.0s, mas o token afirma ir ate 1.60s
db = onda(4.0, [(0.0, 1.0), (3.0, 4.0)])
blocos = [(0.0, 1.60), (2.60, 4.0)]     # ASR esticou dos DOIS lados
cortes = planejar_cortes(blocos, db, JAN, 4.0)
removido = duracao_cortada(cortes)
checa(removido > 1.40,
      f"corte expande alem do token e pega o silencio real (removeu {removido:.2f}s)",
      "a versao antiga so encolhia, entao removia ~0.7s")


# ---------------------------------------------------------------- bug 5
print("\nbug 5: fala DENTRO do vao de token (ASR colapsa palavra em duracao zero)")
# vao de token 1.0-2.6s, mas tem uma palavra falada em 1.6-2.2s no meio dele
db = onda(4.0, [(0.0, 1.0), (1.6, 2.2), (2.6, 4.0)])
blocos = [(0.0, 1.0), (2.60, 4.0)]
cortes = planejar_cortes(blocos, db, JAN, 4.0)
invadiu = any(a < 2.2 and b > 1.6 for a, b in cortes)
checa(not invadiu, "nao corta em cima da palavra escondida no vao", f"cortes={cortes}")
checa(duracao_cortada(cortes) > 0.20, "ainda assim corta o silencio de verdade em volta")


# ---------------------------------------------------------------- bug 1
print("\nbug 1: nao cortar onde o ASR reconheceu fala continua")
# silencio de energia no meio de um bloco de fala continuo (fala baixinha)
db = onda(3.0, [(0.0, 1.0), (2.0, 3.0)])
blocos = [(0.0, 3.0)]                    # um bloco so: o ASR ouviu fala o tempo todo
cortes = planejar_cortes(blocos, db, JAN, 3.0)
no_meio = [c for c in cortes if c[0] > 0.5 and c[1] < 2.5]
checa(not no_meio, "sem vao de token, nao corta por energia sozinha", f"cortes={cortes}")


# ---------------------------------------------------------------- estalo
print("\nestalo curto nao quebra a corrida de silencio")
db = onda(4.0, [(0.0, 1.0), (3.0, 4.0)])
for i in range(int(2.0 / JAN), int(2.04 / JAN)):
    db[i] = -25.0                        # blip baixo de 40ms no meio do silencio
runs = corridas_silencio(db, JAN, 0.0, 4.0)
grandes = [r for r in runs if r[1] - r[0] > 1.5]
checa(len(grandes) == 1, "blip baixo e absorvido, corrida continua inteira", f"runs={runs}")

db2 = onda(4.0, [(0.0, 1.0), (3.0, 4.0)])
for i in range(int(2.0 / JAN), int(2.04 / JAN)):
    db2[i] = -8.0                        # blip ALTO: isso e fala, tem que quebrar
runs2 = corridas_silencio(db2, JAN, 0.0, 4.0)
checa(len(runs2) >= 2, "blip alto QUEBRA a corrida (pode ser palavra)", f"runs={runs2}")


# ---------------------------------------------------------------- intro
print("\nintro: ruido solto no comeco nao pode virar 'inicio da fala'")
db = onda(8.0, [(0.6, 0.64), (6.0, 8.0)])   # tosse em 0.6s, fala so em 6.0s
blocos = [(6.0, 8.0)]
cortes = planejar_cortes(blocos, db, JAN, 8.0)
corte_intro = [c for c in cortes if c[0] == 0.0]
checa(bool(corte_intro) and corte_intro[0][1] > 5.0,
      "corta ate perto de 6.0s, nao para em 0.64s", f"cortes={cortes}")


# ---------------------------------------------------------------- limiar
print("\npausa curta e ritmo natural, nao se mexe")
db = onda(3.0, [(0.0, 1.0), (1.30, 3.0)])   # so 0.30s de pausa
blocos = [(0.0, 1.0), (1.30, 3.0)]
cortes = planejar_cortes(blocos, db, JAN, 3.0)
checa(not [c for c in cortes if c[0] > 0.5], "vao abaixo do limiar fica intacto", f"{cortes}")


# ---------------------------------------------------------------- inversao
print("\nsegmentos_manter inverte a lista de cortes")
seg = segmentos_manter([(1.0, 2.0), (4.0, 5.0)], 6.0)
checa(seg == [(0.0, 1.0), (2.0, 4.0), (5.0, 6.0)], "inversao simples", f"deu {seg}")
seg = segmentos_manter([(1.0, 3.0), (2.0, 4.0)], 5.0)
checa(seg == [(0.0, 1.0), (4.0, 5.0)], "cortes sobrepostos fundem", f"deu {seg}")
seg = segmentos_manter([(0.0, 2.0)], 5.0)
checa(seg == [(2.0, 5.0)], "corte no inicio nao gera segmento vazio", f"deu {seg}")


# ------------------------------------------------- intro que ja abre falando
print("\ntake que ja comeca falando nao leva corte no inicio")
db = onda(4.0, [(0.0, 1.0), (3.0, 4.0)])
blocos = [(0.0, 1.60), (2.60, 4.0)]
cortes = planejar_cortes(blocos, db, JAN, 4.0)
checa(not [c for c in cortes if c[0] == 0.0],
      "sem cabecalho mudo, nao inventa corte de intro", f"cortes={cortes}")
checa(abs(duracao_cortada(cortes) - (2.0 - PADRAO["respiro"] - 2*PADRAO["folga"])) < 0.05,
      f"remove exatamente o silencio real menos o respiro ({duracao_cortada(cortes):.2f}s)")


print()
if falhas:
    print(f"{len(falhas)} FALHA(S): {falhas}")
    sys.exit(1)
print("todos os testes passaram")
