#!/usr/bin/env python3
"""Logica pura de corte de ar morto em take bruto de talking-head.

Sem I/O, sem ffmpeg, sem ASR: recebe tokens e curva de energia, devolve cortes.
E aqui que mora a regra; quem fala com disco e `cortar_ar_morto.py`.

## O problema

Cortar pausa de um take bruto parece trivial e nao e. Existem dois oraculos e os
dois mentem, cada um de um jeito:

- ENERGIA mente pra baixo: a cauda de uma palavra (fricativa, vogal final fraca)
  cai abaixo de qualquer limiar e parece silencio. Cortar por energia sozinha come
  palavra.
- TOKEN do ASR mente pros dois lados: ora estica a vogal por cima do silencio
  (marca "ao" ate 10.08s quando a onda morreu em 9.44s), ora colapsa uma palavra
  inteira em tokens de duracao ZERO (marcou "s"+"ele"+"cao" todos em 74.88s,
  enquanto a onda tem fala a -18dB ate 75.56s).

A saida e usar um pra corrigir o outro: o vao entre tokens diz ONDE e plausivel
existir pausa (ancora semantica, garante que o ASR nao ouviu palavra ali), e a
maior CORRIDA CONTIGUA de baixa energia dentro de uma janela em volta desse vao
diz o tamanho REAL do silencio. Se tem fala no meio do "vao", a corrida nao cobre
ela e o corte respeita a palavra sozinho. Se a fala morreu antes do token acabar,
a corrida passa por cima do token e o corte pega o ar morto de verdade.

## Os cinco bugs que geraram cada regra (todos reais, cada um custou um render)

1. Energia pura            -> comeu "voce nao comprou" inteiro do anuncio.
2. RESPIRO invertido       -> vao de 1.04s perdia so 0.22s. A constante era usada
                              como "janela que removo" em vez de "pausa que sobra".
3. Pontuacao como fala     -> `text.strip()` deixava "." e "," passarem. Pontuacao
                              nao tem som, entao a folga era ancorada num token
                              mudo e 4 vaos ficavam mascarados.
4. Varredura so pra dentro -> a busca de borda so sabia ENCOLHER o corte, nunca
                              expandir. Com o ASR esticando a vogal, sobravam
                              2.24s de ar morto (viravam 0.95s no video final).
5. Vao presumido vazio     -> assumir que o vao de token nao tem audio cortou em
                              cima da palavra "condicao".

Cada um desses e um teste em `test_ar_morto.py`. Nao apague os testes: eles sao a
unica coisa que impede o bug de voltar.
"""

# ---------------------------------------------------------------- parametros

PADRAO = {
    "piso_db": -32.0,       # abaixo disso nao e fala (respiracao, sala)
    "folga": 0.06,          # margem da borda REAL de fala achada na onda
    "respiro": 0.16,        # pausa que SOBRA depois do corte (nunca "que se remove")
    "limiar_corte": 0.40,   # vao de token menor que isso e ritmo natural de fala
    "janela_busca": 0.90,   # quanto olhar pra cada lado do vao procurando a corrida
    "tol_estalo": 0.12,     # blip curto nao quebra a corrida de silencio
    "db_estalo": -22.0,     # ...desde que o blip nao seja alto o bastante pra ser fala
    "cola_token": 0.06,     # tokens mais perto que isso viram o mesmo bloco de fala
    "pre_roll_intro": 0.12, # respiro deixado antes da primeira palavra
    "pos_roll_fim": 0.20,   # respiro deixado depois da ultima palavra
}

PONTUACAO = set(".,?!;:…\"'()-—–")


def e_fala(texto):
    """Token de pontuacao nao tem som e NAO pode ancorar borda de fala (bug 3)."""
    s = (texto or "").strip()
    return bool(s) and not all(c in PONTUACAO for c in s)


def blocos_de_fala(tokens, cola=None):
    """Funde tokens quase colados num bloco continuo.

    `tokens` = iteravel de (inicio, fim, texto). Pontuacao e descartada.
    """
    cola = PADRAO["cola_token"] if cola is None else cola
    reais = sorted((a, b) for a, b, t in tokens if e_fala(t))
    blocos = []
    for a, b in reais:
        if blocos and a - blocos[-1][1] < cola:
            blocos[-1] = (blocos[-1][0], max(blocos[-1][1], b))
        else:
            blocos.append((a, b))
    return blocos


def corridas_silencio(db, jan, t0, t1, piso=None, tol_estalo=None, db_estalo=None):
    """Corridas contiguas abaixo do piso dentro de [t0, t1].

    `db` = lista de dB (relativos ao pico) amostrados a cada `jan` segundos.

    Blip curto e baixo (estalo de boca, roupa, clique de mesa) NAO quebra a
    corrida: sem essa tolerancia um clique de 40ms parte um silencio de 2s em
    dois pedacos e o corte sai pela metade.
    """
    piso = PADRAO["piso_db"] if piso is None else piso
    tol_estalo = PADRAO["tol_estalo"] if tol_estalo is None else tol_estalo
    db_estalo = PADRAO["db_estalo"] if db_estalo is None else db_estalo

    i0, i1 = max(0, int(round(t0 / jan))), min(len(db), int(round(t1 / jan)))
    cruas, ini = [], None
    for i in range(i0, i1):
        if db[i] < piso:
            if ini is None:
                ini = i
        elif ini is not None:
            cruas.append((ini * jan, i * jan))
            ini = None
    if ini is not None:
        cruas.append((ini * jan, i1 * jan))

    fundidas = []
    for r in cruas:
        if fundidas:
            ba, bb = fundidas[-1][1], r[0]
            if bb - ba <= tol_estalo:
                ia = int(round(ba / jan))
                ib = max(int(round(bb / jan)), ia + 1)
                if max(db[ia:ib], default=-99.0) < db_estalo:
                    fundidas[-1] = (fundidas[-1][0], r[1])
                    continue
        fundidas.append(r)
    return fundidas


def planejar_cortes(blocos, db, jan, dur_total, params=None, log=None):
    """Devolve a lista de (inicio, fim) a REMOVER do arquivo.

    O vao de token e a ancora (onde e seguro cortar); a corrida de energia e a
    medida (quanto de fato e silencio). Nenhuma das duas sozinha basta.
    """
    p = dict(PADRAO)
    if params:
        p.update(params)
    diga = log if log else (lambda *_: None)

    def corridas(a, b):
        return corridas_silencio(db, jan, a, b, p["piso_db"], p["tol_estalo"], p["db_estalo"])

    if not blocos:
        return []

    cortes = []

    # --- intro: onde a fala REALMENTE comeca -------------------------------
    # Duas condicoes, e as duas nasceram de erro:
    # (a) so ha o que aparar se o arquivo COMECA em silencio. Sem isso, um take
    #     que ja abre falando levava corte no comeco (a corrida achada era a
    #     primeira PAUSA da fala, nao o cabecalho mudo).
    # (b) entre as corridas do cabecalho, vale a ULTIMA que comeca antes da
    #     primeira palavra: um ruido solto (tosse, batida) parte o cabecalho em
    #     dois e a primeira corrida sozinha daria "a fala comeca em 0.6s".
    runs_intro = corridas(0.0, blocos[0][1])
    if runs_intro and runs_intro[0][0] <= 0.10:
        antes = [r for r in runs_intro if r[0] < blocos[0][0]]
        if antes:
            inicio_fala = antes[-1][1]
            fim_corte = max(0.0, inicio_fala - p["pre_roll_intro"])
            if fim_corte > 0.05:
                cortes.append((0.0, fim_corte))
                diga(f"intro: token dizia {blocos[0][0]:.2f}s, onda diz {inicio_fala:.2f}s "
                     f"-> corto 0 a {fim_corte:.2f}s")

    # --- pausas no meio ----------------------------------------------------
    for (_, b0), (a1, _) in zip(blocos, blocos[1:]):
        vao = a1 - b0
        if vao < p["limiar_corte"]:
            continue
        cands = corridas(b0 - p["janela_busca"], a1 + p["janela_busca"])
        cands = [(s, e) for s, e in cands if e > b0 and s < a1]   # tem que encostar no vao
        if not cands:
            diga(f"vao {vao:5.2f}s ({b0:6.2f}-{a1:6.2f}): a onda NAO tem silencio ali "
                 f"(ASR errou a borda) -> NAO corto")
            continue
        s, e = max(cands, key=lambda r: r[1] - r[0])
        ini, fim = s + p["folga"], e - p["folga"]
        if fim - ini <= p["respiro"]:
            diga(f"vao {vao:5.2f}s ({b0:6.2f}-{a1:6.2f}): silencio real so {max(0.0, e-s):.2f}s "
                 f"-> curto demais, NAO corto")
            continue
        remover = (fim - ini) - p["respiro"]     # RESPIRO e o que SOBRA (bug 2)
        meio = (ini + fim) / 2
        cortes.append((meio - remover / 2, meio + remover / 2))
        diga(f"vao {vao:5.2f}s ({b0:6.2f}-{a1:6.2f}) | onda: silencio {s:6.2f}-{e:6.2f} "
             f"= {e-s:5.2f}s -> removo {remover:5.2f}s, sobra {(e-s)-remover:.2f}s")

    # --- rabo do arquivo ---------------------------------------------------
    fim_corridas = corridas(blocos[-1][0], dur_total)
    if fim_corridas and fim_corridas[-1][1] > dur_total - 0.15:
        cortes.append((fim_corridas[-1][0] + p["pos_roll_fim"], dur_total))

    return cortes


def segmentos_manter(cortes, dur_total, minimo=0.05):
    """Inverte a lista de cortes: o que sobra pra concatenar."""
    manter, cursor = [], 0.0
    for a, b in sorted(cortes):
        if a > cursor:
            manter.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < dur_total:
        manter.append((cursor, dur_total))
    return [(round(a, 3), round(b, 3)) for a, b in manter if b - a > minimo]
