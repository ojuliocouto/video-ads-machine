"""Câmera viva (capacidade C3): punch de ênfase, respiro, push-in e o zoom contínuo do avatar.

Um anúncio de avatar com a câmera parada lê como vídeo de webcam. O C3 troca "dinâmico" por números:

  zoom contínuo   16% alternando de sentido a cada plano. Já existe: `footage/filtros_avatar` (AMPL).
  punch           1,00 -> 1,22 em 0,28 s na KEY em avatar cheio, segura até 2,4 s e volta SECO, em 2
                  quadros. Origem: o playbook de câmera da VSL (zoom por quadro: 1 + 0,22 x (T - t) / 0,28, hold, volta).
  respiro         1,10 -> 1,00 em 1 s na entrada de etapa (bloco `lista`). Mesma origem.
  push-in         em gravação de tela, alvo 0,75 e teto 1,70: `push_in.py`, que é o dono dos dois números.
  NUNCA punch em insert, em split nem em lettering de split. Motivo: no insert o que se lê é a tela, e
  sacudir o quadro de um terminal em cima de quem está lendo é o oposto de ênfase.

## Quem usa este módulo

  `footage/filtros_avatar`  pede `expr_fator(eventos)` e multiplica o zoom contínuo pelo fator. O punch é
                            capacidade NOVA: sem eventos o filtro é byte a byte o de antes.
  `timeline/construir`      (W3.A) chama `planejar(timeline_parcial)` e grava o resultado em `camera`.
  `gates/gate_camera`       lê as medidas puras daqui (`variacao_da_escala`, `ganho_do_punch`,
                            `janelas_de_movimento`, `maior_trecho_parado`).

## Os eventos (campo `camera` da timeline.json, contrato `timeline.schema.json`)

    {"t": 21.0, "tipo": "punch",   "de": 1.0,  "para": 1.22, "dur": 0.28, "segura": 1.92}
    {"t": 14.0, "tipo": "respiro", "de": 1.1,  "para": 1.0,  "dur": 1.0}
    {"t": 3.0,  "tipo": "zoom",    "de": 1.16, "para": 1.0,  "dur": 6.0}      (declarado; o filtro faz)
    {"t": 9.0,  "tipo": "push_in", "de": 1.0,  "para": 1.27, "dur": 5.0}      (declarado; o filtro_insert faz)

Todos os tempos (`t`, `dur`, `segura`) estão no relógio da footage a 1x, como o resto da timeline. O
arquivo entregue converte com (t - a0) / aceleração: a subida de 0,28 s dura 0,207 s no entregue a 1,35x.

## O punch é um FATOR sobre o zoom do plano

O zoom contínuo vai de 1,00 a 1,16 (ou de 1,14 a 1,30) ao longo do plano. O punch não troca esse
valor por 1,22: ele MULTIPLICA (z = zoom_do_plano x fator). Absoluto, o punch de um plano com base 1,14
(até 1,30) faria o quadro recuar. Relativo, o rosto cresce 22% sobre o que já está na tela, qualquer que
seja o plano.

## O avaliador do zoompan

`avaliar` lê a mesma string que o ffmpeg lê (o subconjunto: números, `on`, + - * /, parênteses,
if/lt/lte/gt/gte/between/min/max/abs) e devolve o número. É assim que o teste prova "1,00, depois 1,22 em
+0,28 s, e volta a 1,00 dois quadros após o hold" sem renderizar: a string testada é a que vai pro filtro.
Não usa `eval`: um parser próprio que recusa tudo fora do subconjunto.

## Armadilha herdada da VSL

`crop` avalia largura e altura UMA vez (t vira 0) e o zoom sai silenciosamente inexistente. O `zoompan`
avalia `z` por quadro, e é por isso que o filtro do avatar usa `zoompan` com `d=1`.
"""
import math
import re

import push_in

FPS = 30                                    # espelho de footage/filtros_avatar.FPS (o teste confere)

# --- punch (C3) ---------------------------------------------------------------------------------
PUNCH_DE = 1.00
PUNCH_PARA = 1.22                           # +22% sobre o plano
PUNCH_SOBE_S = 0.28                         # subida
PUNCH_SEGURA_MAX_S = 2.4                    # hold máximo
PUNCH_VOLTA_QUADROS = 2                     # a volta é seca: rampa de 2 quadros
# Margens do PLANEJADOR (não do C3): dão ao gate quadros sem punch antes (+15% sobre quê?) e depois.
PUNCH_SEGURA_MIN_S = 0.6                    # hold abaixo disso não se lê como ênfase
PUNCH_ANTES_MIN_S = 0.8                     # o punch espera isto depois do início do plano
PUNCH_CAUDA_MIN_S = 0.5                     # e acaba isto antes do fim dele
PUNCH_ESPACO_MIN_S = 1.0                    # entre o fim de um punch e o começo do próximo

# --- respiro e push-in (C3) -----------------------------------------------------------------------
RESPIRO_DE = 1.10
RESPIRO_PARA = 1.00
RESPIRO_DUR_S = 1.0
PUSH_IN_ALVO = push_in.ZOOM_ALVO            # 0,75: mora em push_in.py
PUSH_IN_TETO = push_in.ZOOM_MAX             # 1,70
KEN_BURNS_FIM = 1.06                        # imagem estática (filtros_insert.fc_imagem: min(zoom+0.0007, 1.06))

# --- o que o gate_camera cobra --------------------------------------------------------------------
PUNCH_GANHO_MIN = 0.15                      # "punch sem +15% de escala medida" (o pedido é 22%)
ESCALA_VARIACAO_MIN = 0.08                  # "caixa do rosto varia menos de 8%": câmera parada (medida na escala da imagem)
CAIXA_VARIACAO_MIN = ESCALA_VARIACAO_MIN    # o nome do plano
PLANO_AVATAR_MIN_S = 2.0                    # ... num plano de avatar de 2 s ou mais (entregues)
PARADO_MAX_S = 20.0                         # mais de 20 s sem movimento reprova

TIPOS_FATOR = ("punch", "respiro")          # os que viram expressão do zoompan
_ORDEM = {"zoom": 0, "push_in": 1, "respiro": 2, "punch": 3}
_EPS = 1e-9


# =================================================================================== eventos

def _r(x):
    return round(float(x), 4)


def evento_punch(t, segura=PUNCH_SEGURA_MAX_S, de=PUNCH_DE, para=PUNCH_PARA, dur=PUNCH_SOBE_S):
    """Evento de punch. `segura` passa de 2,4 s? O C3 proíbe: erro, não corte em silêncio."""
    if t < 0:
        raise ValueError("punch com t negativo (%s)" % t)
    if segura < 0 or segura > PUNCH_SEGURA_MAX_S + _EPS:
        raise ValueError("segura %.2f s fora de 0 a %.1f s (o C3 segura o punch até %.1f s)"
                         % (segura, PUNCH_SEGURA_MAX_S, PUNCH_SEGURA_MAX_S))
    if dur <= 0:
        raise ValueError("a subida do punch precisa de duração positiva")
    return {"t": _r(t), "tipo": "punch", "de": _r(de), "para": _r(para), "dur": _r(dur), "segura": _r(segura)}


def evento_respiro(t, de=RESPIRO_DE, para=RESPIRO_PARA, dur=RESPIRO_DUR_S):
    if t < 0:
        raise ValueError("respiro com t negativo (%s)" % t)
    return {"t": _r(t), "tipo": "respiro", "de": _r(de), "para": _r(para), "dur": _r(dur)}


def janela(ev, fps=FPS):
    """(início, fim) do evento, no relógio dele. O punch inclui o hold e a volta de 2 quadros."""
    t0 = float(ev["t"])
    if ev["tipo"] == "punch":
        return t0, t0 + float(ev["dur"]) + float(ev.get("segura", 0.0)) + PUNCH_VOLTA_QUADROS / float(fps)
    return t0, t0 + float(ev["dur"])


def janelas_de_movimento(eventos, fps=FPS):
    """As janelas (início, fim) de todos os eventos de câmera, em ordem de início."""
    return sorted(janela(e, fps) for e in (eventos or []))


def eventos_do_segmento(eventos, s, e):
    """Os eventos de fator (punch e respiro) que começam dentro do plano [s, e), com `t` relativo ao início
    do plano: é o `punches=` do `filtros_avatar.cmd_orig`, que renderiza cada plano num ffmpeg à parte."""
    saida = []
    for ev in eventos or []:
        if ev.get("tipo") in TIPOS_FATOR and s - _EPS <= ev["t"] < e - _EPS:
            copia = dict(ev)
            copia["t"] = round(float(ev["t"]) - float(s), 6)
            saida.append(copia)
    return sorted(saida, key=lambda x: x["t"])


def eventos_no_plano(eventos, duracao_s):
    """Os eventos de fator que ainda começam antes do fim de um plano de `duracao_s` (relativos a ele)."""
    return [ev for ev in (eventos or []) if ev.get("tipo") in TIPOS_FATOR and ev["t"] < duracao_s - _EPS]


# =================================================================================== o fator, em número e em expressão

def fator(ev, t, fps=FPS):
    """Fator de UM evento no instante t (mesmo relógio de `ev["t"]`). 1,0 fora da janela."""
    tipo, t0, d = ev["tipo"], float(ev["t"]), float(ev["dur"])
    de, para = float(ev["de"]), float(ev["para"])
    if tipo == "respiro":
        if t < t0 or t >= t0 + d:
            return 1.0
        return de + (para - de) * (t - t0) / d
    if tipo != "punch":
        return 1.0
    t1 = t0 + d
    t2 = t1 + float(ev.get("segura", 0.0))
    t3 = t2 + PUNCH_VOLTA_QUADROS / float(fps)
    if t < t0 or t >= t3:
        return 1.0
    if t < t1:
        return de + (para - de) * (t - t0) / d
    if t < t2:
        return para
    return para + (1.0 - para) * (t - t2) / (t3 - t2)


def fator_total(eventos, t, fps=FPS):
    """Produto dos fatores de todos os eventos no instante t."""
    total = 1.0
    for ev in eventos or []:
        total *= fator(ev, t, fps)
    return total


def _n(x):
    """Número para a expressão: 10 algarismos significativos, sem notação científica nos casos usados."""
    s = format(float(x), ".10g")
    return s


def _expr_evento(ev, fps):
    T = "on/%d" % int(fps)
    t0, d = float(ev["t"]), float(ev["dur"])
    de, para = float(ev["de"]), float(ev["para"])
    if ev["tipo"] == "respiro":
        return ("if(lt({T},{t0}),1,if(lt({T},{t1}),{de}+({dd})*({T}-{t0})/{d},1))"
                .format(T=T, t0=_n(t0), t1=_n(t0 + d), de=_n(de), dd=_n(para - de), d=_n(d)))
    t1 = t0 + d
    t2 = t1 + float(ev.get("segura", 0.0))
    volta = PUNCH_VOLTA_QUADROS / float(fps)
    t3 = t2 + volta
    return ("if(lt({T},{t0}),1,if(lt({T},{t1}),{de}+({dd})*({T}-{t0})/{d},if(lt({T},{t2}),{pa},"
            "if(lt({T},{t3}),{pa}+({back})*({T}-{t2})/{volta},1))))"
            .format(T=T, t0=_n(t0), t1=_n(t1), t2=_n(t2), t3=_n(t3), de=_n(de), dd=_n(para - de), d=_n(d),
                    pa=_n(para), back=_n(1.0 - para), volta=_n(volta)))


def expr_fator(eventos, fps=FPS):
    """Expressão do zoompan para o fator dos eventos (punch e respiro; os outros tipos são ignorados).
    Sem nenhum, "1". Só usa o subconjunto que `avaliar` entende e nenhum caractere que quebre o `z='...'`
    (aspas, dois-pontos, ponto e vírgula, espaço)."""
    partes = [_expr_evento(ev, fps) for ev in sorted((e for e in (eventos or []) if e.get("tipo") in TIPOS_FATOR),
                                                     key=lambda e: e["t"])]
    if not partes:
        return "1"
    if len(partes) == 1:
        return partes[0]
    return "*".join("(%s)" % p for p in partes)


# =================================================================================== avaliador do subconjunto do ffmpeg

_LEXICO = re.compile(r"\s*(?:(\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+)|([A-Za-z_][A-Za-z_0-9]*)|(.))", re.S)


def _tokens(texto):
    texto = texto.strip()
    if not texto:
        raise ValueError("expressão vazia")
    saida, pos = [], 0
    while pos < len(texto):
        m = _LEXICO.match(texto, pos)
        if not m or m.end() == pos:
            break
        num, nome, simbolo = m.groups()
        if num is not None:
            saida.append(("num", float(num)))
        elif nome is not None:
            saida.append(("nome", nome))
        else:
            saida.append(("simb", simbolo))
        pos = m.end()
    return saida


def _se(c, a, b=0.0):
    return a if c else b


_FUNCOES = {
    "if": (2, 3, _se),
    "lt": (2, 2, lambda a, b: 1.0 if a < b else 0.0),
    "lte": (2, 2, lambda a, b: 1.0 if a <= b else 0.0),
    "gt": (2, 2, lambda a, b: 1.0 if a > b else 0.0),
    "gte": (2, 2, lambda a, b: 1.0 if a >= b else 0.0),
    "between": (3, 3, lambda x, lo, hi: 1.0 if lo <= x <= hi else 0.0),
    "min": (2, 2, min),
    "max": (2, 2, max),
    "abs": (1, 1, abs),
}


class _Parser(object):
    def __init__(self, tokens, variaveis):
        self.t, self.i, self.v = tokens, 0, variaveis

    def _ver(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def _pegar(self):
        tok = self._ver()
        self.i += 1
        return tok

    def _simbolo(self, s):
        tipo, valor = self._ver()
        if tipo == "simb" and valor == s:
            self.i += 1
            return True
        return False

    def expressao(self):
        v = self.termo()
        while True:
            if self._simbolo("+"):
                v += self.termo()
            elif self._simbolo("-"):
                v -= self.termo()
            else:
                return v

    def termo(self):
        v = self.unario()
        while True:
            if self._simbolo("*"):
                v *= self.unario()
            elif self._simbolo("/"):
                d = self.unario()
                if d == 0:
                    raise ValueError("divisão por zero")
                v /= d
            else:
                return v

    def unario(self):
        if self._simbolo("-"):
            return -self.unario()
        if self._simbolo("+"):
            return self.unario()
        return self.atomo()

    def atomo(self):
        tipo, valor = self._pegar()
        if tipo == "num":
            return valor
        if tipo == "nome":
            if self._simbolo("("):
                return self.chamada(valor)
            if valor not in self.v:
                raise ValueError("variável não declarada: %r" % valor)
            return float(self.v[valor])
        if tipo == "simb" and valor == "(":
            v = self.expressao()
            if not self._simbolo(")"):
                raise ValueError("faltou fechar o parêntese")
            return v
        raise ValueError("expressão inválida perto de %r" % (valor,))

    def chamada(self, nome):
        if nome not in _FUNCOES:
            raise ValueError("função fora do subconjunto do zoompan: %r" % nome)
        minimo, maximo, f = _FUNCOES[nome]
        args = []
        if not self._simbolo(")"):
            while True:
                args.append(self.expressao())
                if self._simbolo(")"):
                    break
                if not self._simbolo(","):
                    raise ValueError("faltou ',' ou ')' em %s(...)" % nome)
        if not minimo <= len(args) <= maximo:
            raise ValueError("%s() leva de %d a %d argumentos, recebeu %d" % (nome, minimo, maximo, len(args)))
        return float(f(*args))


def avaliar(expr, **variaveis):
    """Valor numérico de uma expressão do zoompan (`on` e o que mais vier em `variaveis`).
    ValueError para o que sair do subconjunto: sintaxe, nome, função, divisão por zero."""
    p = _Parser(_tokens(expr), variaveis)
    v = p.expressao()
    if p.i != len(p.t):
        raise ValueError("sobrou texto depois da expressão: %r" % (p.t[p.i][1],))
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        raise ValueError("a expressão não deu um número")
    return v


# =================================================================================== planejar a câmera da timeline

def _segmento_em(segmentos, t):
    for sg in segmentos:
        if sg["s"] - _EPS <= t < sg["e"] - _EPS:
            return sg
    return None


def planejar_com_motivos(tl, push_in_por_insert=None, imagens=None):
    """Planeja o campo `camera` da timeline. Devolve `(eventos, recusados)`.

    `tl` traz o que a timeline já sabe: `segmentos`, `blocos`, `letterings`, `janelas_split` e `relogio`.
      - todo plano de apresentador ganha seu `zoom` (declarado: quem faz é o `filtros_avatar`). O sentido
        alterna pela POSIÇÃO do segmento na lista, que é o `idx` que o render usa, e a base é a do plano;
      - insert de gravação de tela ganha `push_in` quando o fator pedido (`push_in_por_insert[chave]`, vindo
        de `push_in.fator_push_in`) passa de 1; imagem estática (`imagens`) ganha o Ken Burns; o resto fica
        sem evento (nada se mexe e o gate vai dizer se passar de 20 s);
      - plano de apresentador que abre um bloco `lista` ganha o `respiro`;
      - KEY de apresentador em avatar cheio ganha o `punch`.
    `recusados` explica cada KEY sem punch ({"lettering": id, "motivo": ...}) para o plano mostrar.
    """
    from footage import filtros_avatar as FA          # a amplitude é a de lá, não uma cópia (sem import circular)

    segs = tl["segmentos"]
    blocos = tl.get("blocos") or []
    letterings = tl.get("letterings") or []
    janelas = tl.get("janelas_split") or []
    fps = (tl.get("relogio") or {}).get("fps", FPS)
    push_in_por_insert = push_in_por_insert or {}
    imagens = set(imagens or ())
    insert_do_bloco = {b["i"]: b.get("insert") for b in blocos}

    eventos, recusados = [], []
    for k, sg in enumerate(segs):
        dur = sg["e"] - sg["s"]
        if dur <= _EPS:
            continue
        if sg["tipo"] == "apresentador":
            base = float(sg.get("base") or 1.0)
            de, para = (base, base + FA.AMPL) if k % 2 == 0 else (base + FA.AMPL, base)
            eventos.append({"t": _r(sg["s"]), "tipo": "zoom", "de": _r(de), "para": _r(para), "dur": _r(dur)})
        elif sg["tipo"] == "insert":
            chave = insert_do_bloco.get(sg["bloco"])
            f = push_in_por_insert.get(chave)
            if f is not None and f > 1.0001:
                eventos.append({"t": _r(sg["s"]), "tipo": "push_in", "de": 1.0,
                                "para": _r(min(f, PUSH_IN_TETO)), "dur": _r(dur)})
            elif chave in imagens:
                eventos.append({"t": _r(sg["s"]), "tipo": "zoom", "de": 1.0, "para": KEN_BURNS_FIM, "dur": _r(dur)})

    ocupadas = []                       # janelas de respiro e de punch já ocupadas: (início, fim, é_punch)
    for b in blocos:
        if b.get("tipo") != "lista":
            continue
        dele = [sg for sg in segs if sg["bloco"] == b["i"] and sg["tipo"] == "apresentador"]
        if dele and dele[0]["e"] - dele[0]["s"] >= RESPIRO_DUR_S - _EPS:
            ev = evento_respiro(dele[0]["s"])
            eventos.append(ev)
            ocupadas.append(janela(ev, fps) + (False,))

    for L in sorted(letterings, key=lambda x: (x["s"], str(x.get("id")))):
        ev, motivo = _punch_da_key(L, segs, janelas, ocupadas, fps)
        if ev is None:
            recusados.append({"lettering": L.get("id"), "motivo": motivo})
            continue
        eventos.append(ev)
        ocupadas.append(janela(ev, fps) + (True,))

    eventos.sort(key=lambda e: (e["t"], _ORDEM[e["tipo"]]))
    return eventos, recusados


def _punch_da_key(L, segs, janelas, ocupadas, fps):
    """(evento, None) ou (None, motivo). Cada recusa diz por que, na ordem em que o C3 a proíbe."""
    if L.get("cta"):
        return None, "KEY de CTA tem a seta e o riser, não punch"
    if L.get("pilha"):
        return None, "item de pilha tem o tick, não punch"
    if L.get("split"):
        return None, "lettering de split: nunca punch (o quadro dividido já está cheio)"
    sg = _segmento_em(segs, L["s"])
    if sg is None:
        return None, "a KEY cai fora de qualquer plano"
    if sg["tipo"] != "apresentador":
        return None, "a KEY cai em insert: nunca punch em insert"
    if any(j["s"] - _EPS <= L["s"] < j["e"] - _EPS for j in janelas):
        return None, "a KEY cai em janela de split: nunca punch em split"
    t = max(float(L["s"]), float(sg["s"]) + PUNCH_ANTES_MIN_S)
    segura_key = float(L["s"]) + float(L["d"]) - t - PUNCH_SOBE_S
    segura_plano = float(sg["e"]) - t - PUNCH_SOBE_S - PUNCH_CAUDA_MIN_S
    if segura_key < PUNCH_SEGURA_MIN_S - _EPS:
        return None, ("KEY curta demais: %.2f s de KEY não comportam a subida de %.2f s e um hold de %.1f s"
                      % (float(L["d"]), PUNCH_SOBE_S, PUNCH_SEGURA_MIN_S))
    if segura_plano < PUNCH_SEGURA_MIN_S - _EPS:
        return None, ("sem espaço no plano de avatar: o plano acaba em %.2f s e o punch pediria até lá "
                      "mais %.1f s de cauda" % (float(sg["e"]), PUNCH_CAUDA_MIN_S))
    ev = evento_punch(t, min(PUNCH_SEGURA_MAX_S, segura_key, segura_plano))
    ini, fim = janela(ev, fps)
    for j in janelas:
        if j["s"] < fim and ini < j["e"]:
            return None, "o punch invadiria a janela de split: nunca punch em split"
    for a, b, eh_punch in ocupadas:
        folga = PUNCH_ESPACO_MIN_S if eh_punch else 0.0
        if a - folga < fim and ini < b + folga:
            return None, ("a KEY fica a menos de %.1f s de outro punch" % PUNCH_ESPACO_MIN_S if eh_punch
                          else "a KEY cai no respiro de entrada da etapa")
    return ev, None


def planejar(tl, push_in_por_insert=None, imagens=None):
    """Só os eventos de `planejar_com_motivos`: o campo `camera` da timeline."""
    return planejar_com_motivos(tl, push_in_por_insert, imagens)[0]


# =================================================================================== medidas puras (o que os gates usam)

def para_entregue(t, relogio):
    """Instante da footage a 1x -> instante do arquivo entregue: (t - a0) / aceleração."""
    return (float(t) - float(relogio.get("a0", 0.0))) / float(relogio["aceleracao"])


def _mediana(valores):
    v = sorted(valores)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def variacao_da_escala(escalas, tempos=None):
    """Quanto a imagem CRESCEU OU ENCOLHEU ao longo de um plano: `exp(|inclinação| x duração) - 1`, com a
    inclinação do logaritmo da escala cumulativa contra o tempo (mínimos quadrados). É o tamanho do zoom (o de 16%
    mede cerca de 15% depois de tirar 0,25 s de cada ponta), com o sinal ignorado: o zoom alterna de sentido. Usa
    todos os quadros, não só as pontas, que carregam o ruído acumulado do rastreador. `tempos` são os instantes das
    escalas (padrão: 0, 1, 2, ...). Sem pelo menos 3 quadros, None: não dá para dizer.

    A escala vem de pontos de textura rastreados entre quadros (`gates/gate_camera`) e não da caixa do rosto: num
    avatar real e PARADO a altura da caixa balança 12% sozinha (a pessoa se inclina, o detector anda em degraus
    de 10%), contra p90 de 1,6% da escala."""
    pares = [(float(tempos[i]) if tempos is not None else float(i), math.log(float(e)))
             for i, e in enumerate(escalas) if e is not None and e > 0]
    if len(pares) < 3:
        return None
    t = [x for x, _y in pares]
    y = [v for _x, v in pares]
    tm, ym = sum(t) / len(t), sum(y) / len(y)
    var_t = sum((x - tm) ** 2 for x in t)
    if var_t <= 0:
        return None
    inclinacao = sum((x - tm) * (v - ym) for x, v in zip(t, y)) / var_t
    return math.exp(abs(inclinacao) * (t[-1] - t[0])) - 1.0          # simétrico: 1,16 para fora também é 16%


def ganho_do_punch(antes, depois):
    """Ganho de escala medido: mediana da escala depois da subida sobre a de antes (as duas a partir do mesmo
    quadro de referência), menos 1."""
    a = [float(h) for h in antes if h is not None and h > 0]
    d = [float(h) for h in depois if h is not None and h > 0]
    if not a or not d:
        return None
    return _mediana(d) / _mediana(a) - 1.0


def maior_trecho_parado(janelas, duracao):
    """O maior vão sem movimento em [0, duracao]: `(tamanho, início, fim)`. As janelas podem se sobrepor."""
    duracao = float(duracao)
    cobertas = []
    for a, b in sorted((max(0.0, float(a)), min(duracao, float(b))) for a, b in janelas):
        if b <= a:
            continue
        if cobertas and a <= cobertas[-1][1]:
            cobertas[-1][1] = max(cobertas[-1][1], b)
        else:
            cobertas.append([a, b])
    vaos, cursor = [], 0.0
    for a, b in cobertas:
        if a > cursor:
            vaos.append((a - cursor, cursor, a))
        cursor = max(cursor, b)
    if duracao > cursor:
        vaos.append((duracao - cursor, cursor, duracao))
    if not vaos:
        return 0.0, 0.0, 0.0
    maior = max(vaos, key=lambda x: x[0])
    return float(maior[0]), float(maior[1]), float(maior[2])
