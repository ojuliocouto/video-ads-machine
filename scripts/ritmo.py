#!/usr/bin/env python3
"""Plano de ritmo: subdivide bloco longo em planos curtos, sem trocar nenhum asset.

Medido em 18/08/2026 com o mesmo metodo nos dois lados (deteccao de cena, limiar 0,30):

    referencias do Julio (@vaibhavsisinty)   19 a 28 cortes/min   plano medio 2,2 a 3,2s
    nossa leva                                4,7 a 7,6           plano medio 7,9 a 12,8s

E a Jheni ja tinha dito em texto: "o video poderia ser mais acelerado".

A regra do Julio e que o ASSET DO DOC NAO SE TROCA. Entao os cortes novos nao vem de
material novo, vem de tres operacoes sobre o que ja existe:

  reenquadrar  o mesmo insert com recortes diferentes em sequencia (jump cut de
               enquadramento). Os recortes derivam do recorte que o diretor JA aprovou,
               nunca de um enquadramento inventado.
  alternar     insert -> avatar -> insert dentro do mesmo bloco. Generaliza o `dur_max`,
               que hoje corta uma vez so.
  punch        bloco de avatar longo vira dois ou tres, e o zoom do motor (que ja
               alterna de direcao por indice) inverte a cada um: jump cut sem asset.

DETERMINISTICO DE PROPOSITO: os dois motores (footage e overlay) chamam esta funcao com
a mesma entrada e TEM que obter o mesmo plano. Nada de random, nada de estado. Se um
motor subdividir e o outro nao, o lettering de um trecho de avatar recebe tratamento de
split e o texto vai parar no rosto (ja aconteceu, custou um render).
"""

ALVO_PLANO = 2.8     # plano medio das referencias fica entre 2,2s e 3,2s
MIN_PLANO = 1.5      # abaixo disso o corte vira nervosismo, nao ritmo
# TEMPO DE LEITURA de tela (19/08/2026, feedback do Julio assistindo o AD13: "os
# inserts nem aparecem direito, saem da tela MUITO rapido"). Fatia de INSERT nunca
# fica abaixo disto em footage (~2,7s entregues a 1,35x): gravacao de tela e pagina
# precisam ser LIDAS, e a leva tinha 9 fatias abaixo de 2,6s entregues.
TELA_MIN = 3.6
FATOR_CORTE = 1.7

# Teto de visitas ao MESMO asset dentro de um bloco. Ver o comentario longo no caminho
# de insert: com `derivar_recortes` neutralizada, a terceira visita mostra exatamente o
# mesmo quadro e o corte nem registra na deteccao de cena.
MAX_VISITAS = 2

# Layout de cada visita ao mesmo asset. Com o `crop` desligado no split (26/08/2026) e
# `derivar_recortes` neutralizada desde 19/08, duas visitas seguidas mostram o quadro
# IDENTICO: zero pixel de diferenca, e a deteccao de cena nao ve corte nenhum. Medido no
# jh13 v6: 17 cortes no arquivo contra 12 visitas planejadas, 75% do anuncio em plano
# acima de 6s. Alternar o LAYOUT (tela dividida x tela cheia) troca ~60% dos pixels e
# REGISTRA, ao contrario do punch de escala (0,16 a 0,23 contra limiar 0,30).
LAYOUTS_INSERT = ("split", "cheio")
# escalas base dos sub-planos de avatar. HISTORIA: 1.14/1.28 foram escolhidos achando
# que o salto registraria como corte; a medicao de 18/08 provou que NAO registra (0,16
# a 0,23 contra limiar 0,30) e o corte real vem da alternancia de conteudo. O punch
# ficou sendo so respiracao visual, e amplitude grande custou caro: no look fechado
# (oficial_13) a base 1.28 empurrou o queixo do Thales pra cima da legenda (gate de
# colisao, jh14 t=18s). Amplitude pequena respira sem invadir texto.
BASES_PUNCH = (1.0, 1.06, 1.12)

# FALA QUE APONTA PRA TELA TRAVA O INSERT NA TELA (28/08/2026, print do Julio).
# O Thales diz "A skill e essa que voce ta vendo NA TELA" e a alternancia ja tinha
# devolvido o quadro pro avatar: o espectador ouve "olha isso" olhando pra cara do
# apresentador. No print seguinte, "Ela e um manual de instrucoes que da ao Claude
# regras..." com o insert (que E o manual) sumindo no meio da explicacao.
# A alternancia existe pra dar ritmo a bloco onde a fala nao depende da imagem.
# Quando a copy REFERENCIA a imagem (deixis: "na tela", "isso aqui", "da uma olhada")
# ou o bloco comeca apontando pra ela ("Ela e...", "Esse..."), a imagem manda:
# o insert cobre o bloco inteiro, sem respiro de rosto e sem fatiar.
# Regra da casa que ja existia por escrito e o motor ignorava: a copy manda a
# direcao do bloco.
import re as _re
_DEITICOS = _re.compile(
    r"na tela|nisso aqui|isso aqui|esse aqui|essa aqui|aqui na|"
    r"d[aá] uma olhada|olha (isso|s[oó]|aqui)|ta vendo|t[aá] vendo",
    _re.IGNORECASE)
_ANAFORA = _re.compile(r"^\s*(ela|ele|isso|esse|essa)\b", _re.IGNORECASE)


def bloco_deitico(texto):
    """A fala deste bloco aponta pra imagem? Entao a imagem nao pode sair da tela."""
    t = (texto or "").strip()
    return bool(t) and bool(_DEITICOS.search(t) or _ANAFORA.match(t))
# janela do hook em tempo de FOOTAGE (~3s entregues a 1,35x). No bloco 0 a imagem e
# SEMPRE insert ate aqui: o hook e desenhado sobre o fundo de abertura, e um respiro
# de rosto nessa janela poe o texto na cara do apresentador (gate pegou no jh13).
HOOK_JANELA = 4.2


def derivar_recortes(crop, n):
    """A partir do recorte aprovado, deriva n enquadramentos para o jump cut.

    Todos SAEM do recorte que o diretor validou: o primeiro e ele mesmo, os seguintes
    sao aproximacoes centradas no mesmo conteudo. Assim o reenquadramento nunca mostra
    uma regiao que ninguem conferiu.
    """
    # SEM DERIVACAO (19/08/2026): os recortes derivados ampliavam a gravacao de tela
    # em ate 2,3x e viravam mingau ilegivel com a webcam decepada ("um zoom que nem da
    # pra ver", Julio assistindo o AD13). O recorte aprovado pelo diretor e o UNICO;
    # variedade entre fatias vem da fonte continuar correndo (fonte_off), nao de zoom.
    return [crop] * max(n, 1)


def _n_planos(dur):
    if dur < ALVO_PLANO * FATOR_CORTE:
        return 1
    n = int(round(dur / ALVO_PLANO))
    while n > 1 and dur / n < MIN_PLANO:
        n -= 1
    return max(n, 1)


def plano_de_ritmo(blocos):
    """blocos: [{"tipo","s","e","crop"(opcional),"dur_max"(opcional)}] -> lista de segmentos.

    Cada segmento: {"bloco", "tipo", "s", "e", "crop", "sub", "de"} onde `sub` e o indice
    do plano dentro do bloco e `de` o total de planos daquele bloco.
    """
    segs = []
    fila = list(blocos)
    idx_orig = list(range(len(fila)))
    k_f = 0
    while k_f < len(fila):
        b = fila[k_f]
        i = idx_orig[k_f]
        k_f += 1
        s, e = float(b["s"]), float(b["e"])
        dur = e - s
        tipo = b["tipo"]
        # layout forcado pelo chamador (resto do hook). Lido no TOPO do laco: quando
        # ficava mais abaixo, os ramos que emitem antes dele davam
        # UnboundLocalError, e os testes pegaram.
        _forcado = b.get("_layout_forcado")

        # ABERTURA NAO ALTERNA (18/08/2026): o bloco 0 e o fundo do hook, e um
        # respiro de rosto nos primeiros segundos poe o texto de abertura na cara
        # do apresentador (gate de colisao pegou: 5,7% do rosto coberto). A
        # primeira fatia de tela cobre a janela do hook; o RESTO do bloco volta
        # pra fila como bloco sintetico e alterna normalmente. Fonte respeitada:
        # a fatia forcada nunca passa do cap; se consumir o cap inteiro, o resto
        # reusa a fonte (segunda passada, recorte diferente).
        if (i == 0 and tipo == "insert" and s <= 1.0 and not b.get("_pos_hook")
                and dur > HOOK_JANELA + 0.3):
            cap0 = float(b["dur_max"]) if b.get("dur_max") else None
            f0 = min(HOOK_JANELA, cap0) if cap0 else HOOK_JANELA
            segs.append({"bloco": i, "tipo": "insert", "s": round(s, 3),
                         "e": round(s + f0, 3), "crop": b.get("crop"),
                         "sub": 0, "de": 1, "layout": "split", "fonte_off": 0.0})
            # O RESTO DO HOOK ALTERNA (26/08/2026). A fatia forcada da abertura e
            # sempre split; o resto reusa a MESMA fonte, entao sem alternar os dois
            # trechos sao o mesmo quadro e o corte nao registra. Medido no jh13: a
            # abertura inteira, 11,93s, virava UM plano so na deteccao de cena.
            resto = {**b, "s": s + f0, "_pos_hook": True, "_off_extra": f0,
                     "_layout_forcado": "cheio"}
            if cap0:
                sobra_cap = cap0 - f0
                if sobra_cap >= MIN_PLANO:
                    resto["dur_max"] = sobra_cap
                else:
                    resto["dur_max"] = cap0        # reuso: segunda passada
                    resto["_off_extra"] = 0.0
            fila.insert(k_f, resto)
            idx_orig.insert(k_f, i)
            continue

        # BLOCO DEITICO NAO ALTERNA (28/08/2026). Se a fala aponta pra imagem, o
        # insert cobre o bloco inteiro: sem fatia, sem respiro de rosto, sem dur_max
        # (os blocos com dur_max desta leva nao sao deiticos; se um dia coincidirem,
        # a deixis vence, porque mostrar o que a fala aponta importa mais que o cap).
        # O custo em cortes/min e pago pelos blocos nao-deiticos.
        if tipo == "insert" and bloco_deitico(b.get("texto")) and not b.get("_pos_hook"):
            segs.append({"bloco": i, "tipo": "insert", "s": round(s, 3),
                         "e": round(e, 3), "crop": b.get("crop"),
                         "sub": 0, "de": 1,
                         "layout": _forcado or "split", "fonte_off": 0.0,
                         "deitico": True})
            continue

        # cap declarado: a fonte do insert acaba antes do bloco. A versao antiga
        # mostrava a tela ate o cap e despejava TODO o resto no avatar de uma vez:
        # era dali que saiam os planos de 12s a 17s parados que reprovavam os quatro
        # ads (medido 18/08: jh15 bloco 8 = 4s de tela + 17,5s de rosto morto).
        # Agora o orcamento de tela se ESPALHA pelo bloco em fatias, alternando com o
        # rosto: mesmo consumo de fonte, e o bloco inteiro vira alternancia.
        if tipo == "insert" and b.get("dur_max") and float(b["dur_max"]) < dur - 0.3:
            # A fonte acaba antes do bloco. A versao antiga mostrava a tela ate o cap e
            # despejava o resto no rosto DE UMA VEZ: eram os planos de 12 a 17s parados
            # que reprovavam os quatro ads. Agora: fatias de tela intercaladas com
            # respiros de rosto. Regras (medidas, nao chutadas):
            #   - o orcamento de tela (cap) e usado INTEIRO: jogar fora conteudo que o
            #     doc pede foi bug real (18/08: so 4s dos 11,8s da aula entravam)
            #   - fatia de tela <= ~5s (footage; ~3,7s entregues, dentro da faixa)
            #   - respiro de rosto >= MIN_PLANO, e os respiros ficam ENTRE as fatias
            #   - fonte escassa (cap << bloco): REUSO com recorte diferente, jump cut
            #     pro detalhe, maximo 2 passadas; cada fatia sempre cabe na fonte
            cap = float(b["dur_max"])
            # SOLVER (18/08/2026, 3a versao): escolhe n_t fatias de tela e m respiros
            # de rosto tais que n_t*f_tela + m*f_rosto == dur, com:
            #   f_tela <= cap (fatia nunca le alem da fonte; congelar e o defeito n.1)
            #   n_t*f_tela <= 2*cap (reuso com recorte diferente, max 2 passadas)
            #   f_rosto >= MIN_PLANO, respiros ENTRE fatias (m=n_t-1) ou com um
            #     respiro final (m=n_t), nunca duas telas coladas
            # Preferencia: mais fatias (mais cortes). Fallback: 2 fatias emendadas com
            # recorte diferente (jump cut de reenquadre, nao conta pro ritmo mas nao
            # congela nem estoura fonte).
            alvo = max(-(-int(dur - cap) // 4) + 1, -(-int(cap) // 5), 1)
            # O TETO VALE AQUI TAMBEM (26/08/2026). Eu tinha capado so o caminho sem
            # `dur_max`, e os blocos 6 e 14 do jh13, que TEM cap, seguiram com 3 visitas
            # de ~3s: exatamente a queixa que o teto existia pra resolver. O diretor de
            # arte pegou na auditoria seguinte. Cap aplicado num ramo so nao e cap.
            alvo = min(alvo, MAX_VISITAS)
            escolha = None
            for n_t in range(alvo, 0, -1):
                f_tela = cap / n_t
                if f_tela < TELA_MIN:
                    # fatia abaixo do tempo de LEITURA nao existe (19/08/2026): ou a
                    # fatia cresce reusando a fonte (recorte igual, fonte corre), ou
                    # o n_t cai. Fonte menor que TELA_MIN: mostra o cap inteiro 1x.
                    f_tela = min(cap, max(TELA_MIN, 3.9))
                if n_t * f_tela > 2 * cap + 1e-6:
                    continue
                sobra = dur - n_t * f_tela
                # o MAIOR m possivel (19/08/2026): preferir poucos respiros abria um
                # vao de rosto de 13,7s num bloco de 21,5s. Quanto mais respiros
                # couberem acima do piso, menor cada vao e mais viva a alternancia.
                if abs(sobra) <= 0.05:
                    escolha = (n_t, f_tela, 0, 0.0)
                else:
                    for m in range(n_t, max(n_t - 2, 0), -1):
                        # m >= n_t-1: intercalado de VERDADE. Menos respiro que isso
                        # cola tela com tela, e com recorte unico (19/08) duas fatias
                        # coladas ou sao continuacao invisivel ou repeticao nua.
                        if sobra / m >= MIN_PLANO - 1e-6:
                            escolha = (n_t, f_tela, m, sobra / m)
                            break
                if escolha:
                    break
            if not escolha:
                # nada fecha com respiro: fatias emendadas cobrindo o bloco, cada uma
                # dentro da fonte (reuso por recorte); e melhor que congelar a cauda
                n_t = min(max(2, -(-int(dur) // 5)), MAX_VISITAS)
                f_tela = dur / n_t
                while f_tela > cap and n_t < 12:
                    n_t += 1
                    f_tela = dur / n_t
                escolha = (n_t, f_tela, 0, 0.0)
            n_t, f_tela, m, f_rosto = escolha
            recortes = derivar_recortes(b.get("crop"), 3)
            t = s
            for k in range(n_t):
                fatia = min(f_tela, cap)
                pos = k * fatia
                off = pos % cap if cap > 0 else 0.0
                if off + fatia > cap:
                    off = max(0.0, cap - fatia)
                segs.append({"bloco": i, "tipo": "insert",
                             "s": round(t, 3), "e": round(t + f_tela, 3),
                             "crop": recortes[k % len(recortes)],
                             "sub": 2 * k, "de": 2 * n_t,
                             "layout": _forcado or LAYOUTS_INSERT[k % len(LAYOUTS_INSERT)],
                             # _off_extra: pedaco pos-hook le a fonte DEPOIS da
                             # fatia forcada da abertura
                             "fonte_off": round(off + float(b.get("_off_extra", 0)), 3)})
                t += f_tela
                if k < m:
                    segs.append({"bloco": i, "tipo": "orig",
                                 "s": round(t, 3), "e": round(t + f_rosto, 3),
                                 "crop": None, "sub": 2 * k + 1, "de": 2 * n_t,
                                 "base": BASES_PUNCH[k % len(BASES_PUNCH)]})
                    t += f_rosto
            segs[-1]["e"] = e   # absorve arredondamento no ultimo plano
            assert all(x["e"] > x["s"] for x in segs if x["bloco"] == i), \
                f"bloco {i}: plano invertido (dur={dur:.1f} cap={cap:.1f})"
            continue
        n = _n_planos(dur)
        if n == 1:
            segs.append({"bloco": i, "tipo": tipo, "s": s, "e": e,
                         "crop": b.get("crop"), "sub": 0, "de": 1,
                         # visita UNICA tambem precisa de layout: era por aqui que o
                         # resto do hook saia com layout=None e a abertura do jh13
                         # virava um plano so de 11,93s na deteccao de cena.
                         **({"layout": _forcado} if _forcado and tipo == "insert" else {})})
            continue

        if tipo == "insert":
            # ALTERNA COM TEMPO DE LEITURA (19/08/2026). A versao anterior fatiava a
            # tela no mesmo passo do avatar (~2,8s footage) e o Julio pegou 9 fatias
            # ilegiveis. Agora: fatias de tela >= TELA_MIN, respiros de rosto entre
            # elas (>= MIN_PLANO), e a fonte segue correndo por tras (fonte_off).
            # TETO DE VISITAS (26/08/2026, o Julio reprovando o jh13: "estao durando
            # muito pouco, nao da nem pra ver direito"). A duracao nao era o problema:
            # nenhuma fatia do jh13 ficou abaixo de 2,91s de tela, mediana 3,19s. O
            # problema era VISITA REPETIDA. Nos blocos b06 e b14 o mesmo asset foi
            # picado em TRES fatias, todas com o mesmo recorte (`derivar_recortes` esta
            # neutralizada desde 19/08), com respiros de rosto de 1,2s no meio. O
            # espectador perde a tela e volta no meio da acao, tres vezes.
            #
            # E o pior: metade desses cortes NAO EXISTE. Comparando o plano com a
            # deteccao de cena no arquivo entregue, 19 dos 38 cortes planejados nao
            # registram. Fatia com mesmo asset e mesmo recorte muda zero pixel: paga-se
            # o custo de leitura e nao vem ritmo nenhum.
            #
            # Com o recorte derivado desligado, mais de duas visitas nao tem como
            # entregar informacao nova. Duas ainda dao respiro pro rosto; tres viram
            # soluco.
            n_t = max(1, int(dur // (TELA_MIN + MIN_PLANO)))
            n_t = min(n_t, MAX_VISITAS)
            m = n_t - 1 if n_t > 1 else (1 if dur - TELA_MIN >= MIN_PLANO else 0)
            f_rosto = MIN_PLANO * 1.3 if m else 0.0
            f_tela = (dur - m * f_rosto) / max(n_t, 1)
            recortes = derivar_recortes(b.get("crop"), 3)
            t2 = s
            off = float(b.get("_off_extra", 0))
            for k in range(n_t):
                segs.append({"bloco": i, "tipo": "insert",
                             "s": round(t2, 3), "e": round(t2 + f_tela, 3),
                             "crop": recortes[k % len(recortes)],
                             "sub": 2 * k, "de": 2 * n_t,
                             "layout": _forcado or LAYOUTS_INSERT[k % len(LAYOUTS_INSERT)],
                             "fonte_off": round(off, 3)})
                off += f_tela
                t2 += f_tela
                if k < m:
                    segs.append({"bloco": i, "tipo": "orig",
                                 "s": round(t2, 3), "e": round(t2 + f_rosto, 3),
                                 "crop": None, "sub": 2 * k + 1, "de": 2 * n_t,
                                 "base": BASES_PUNCH[k % len(BASES_PUNCH)]})
                    t2 += f_rosto
            segs[-1]["e"] = e
        else:
            passo = dur / n
            for k in range(n):
                segs.append({"bloco": i, "tipo": tipo,
                             "s": round(s + passo * k, 3),
                             "e": round(s + passo * (k + 1), 3),
                             "crop": None, "sub": k, "de": n,
                             # escala base do sub-plano: o salto entre elas E o corte
                             "base": BASES_PUNCH[k % len(BASES_PUNCH)],
                             # corte INTERNO ao bloco: tem que ser seco, senao o whip
                             # de 0,2s dissolve a troca de escala e o corte some
                             "punch": k > 0})
    # costura: o fim de um segmento e o inicio do proximo, sem buraco nem sobra
    for a, b in zip(segs, segs[1:]):
        b["s"] = a["e"]
    return segs


def resumo(segs, dur_total):
    n = max(len(segs) - 1, 0)
    planos = [x["e"] - x["s"] for x in segs]
    return {
        "planos": len(segs),
        "cortes": n,
        "cortes_min": round(n / (dur_total / 60), 2) if dur_total else 0.0,
        "plano_medio": round(dur_total / max(len(segs), 1), 2),
        "maior_plano": round(max(planos), 2) if planos else 0.0,
    }
