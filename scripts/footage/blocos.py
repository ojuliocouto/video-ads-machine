"""Blocos da footage: do roteiro anotado ao alinhamento com a fala, aos spans, ao plano de ritmo e à
escala base de cada plano. Não monta filtro nem renderiza nada.

## O pipeline, na ordem

  1. `ler_blocos` / `palavras_da_narracao`: o parser do roteiro anotado e a narração contínua.
  2. `alinhar`: a narração casada palavra a palavra com o áudio do avatar (parakeet + difflib). O casamento
     em si mora em `timeline.alinhar.casar` (uma implementação só: a timeline usa o mesmo).
  3. `atribuir_spans`: o span de cada bloco, por CONTAGEM de palavras.
  4. `tornar_contiguos`: a fronteira entre blocos é sempre o início da 1ª palavra do próximo.
  5. `aplicar_ritmo`: o plano de ritmo (`ritmo.py`) fatia blocos longos em N planos.
  6. `decidir_bases`: o salto de escala de cada plano de apresentador (o jump cut).

## Alinhamento PRECISO, por difflib e não por proporção

Cada fronteira de bloco é o fim da última palavra do bloco, que cai num FIM DE PALAVRA real, e os
cortes e dissolves não pegam o meio da fala. O parakeet quebra uma palavra em vários tokens
("Ag" + "ora"); estender só o tempo final SEM concatenar o texto deixava a palavra truncada, e o
difflib casava só 39% das palavras (o resto virava interpolação de 0,18 s fixo, comprimindo os spans
e adiantando os inserts em até 9 s: o insert do clímax durava 1,6 s).

CAUDA FINAL sem casamento (o parakeet às vezes não reconhece as últimas palavras: voz baixa,
respiração, fade-out): sem o ajuste, a interpolação ancorava na última palavra REALMENTE casada e
cortava a fala real cerca de 1 s antes do fim do áudio (o CTA perdia "ainda está disponível"). Se a
cauda do roteiro ficou sem casamento, o fim dela é ancorado no fim REAL do áudio.

## Contiguidade obrigatória

A cadeia posiciona cada bloco pela SOMA DAS DURAÇÕES, então o mapa tempo-do-avatar para tempo-do-reel
só é exato se os spans forem contíguos. O alinhamento gera vãos (pausa entre blocos) e sobreposições
(fuzz do parakeet) de até ~0,7 s, e cada um vira deriva ACUMULADA: o conteúdo desliza em relação às
janelas do PiP e da legenda. Gap: o bloco atual segura a pausa. Overlap: corta o rabo do atual. A
duração mínima de 0,3 s por bloco garante monotonicidade.

## O ritmo roda aqui E no overlay

Capar só o overlay adiantava o CTA mas deixava a imagem no split, e o CTA foi parar em cima do rosto
(medido aos 85,5 s). Overlay e footage são dois motores; plano de ritmo em um só gera desencontro.
Por isso a função é a MESMA (`ritmo.plano_de_ritmo`) e a narração se fatia por CONTAGEM de palavras.

## Com a timeline.json (W3.A, relógio único)

A timeline é construída com ESTAS funções (`atribuir_spans`, `tornar_contiguos`, `plano_de_ritmo`): o
relógio dela é o da footage. Com ela, a montagem não alinha nem calcula o plano: lê os spans e o plano e
só fatia a narração (`fatiar_pelo_plano`). `aplicar_ritmo` é as duas coisas juntas, o caminho antigo.

## A escala base

Depois de insert, escala 1,0 SEMPRE: as fatias que o plano cria já chegam com `_base`, a regra "se
vier de insert, volta em 1,0" não valia pra elas, e a fatia de apresentador logo depois do split
entrou ampliada, o queixo desceu até a faixa da legenda e o gate de colisão pegou 7,5% do rosto
coberto. A troca de imagem já é o corte; ampliar ali não compra nada e custa a legenda. Entre dois
apresentadores a escala alterna (1,0 e 1,14): com 1,28 o rosto desceu até a faixa da legenda (7,6%)
e o ritmo medido não subiu. Escala maior não comprou corte, só comprou colisão. O lettering é
apresentador por baixo e alterna igual: sem isso, 16 de 33 fronteiras planejadas ficavam sem corte
visível.
"""
import json
import os
import subprocess

from timeline import alinhar as AL

from . import cadeia as CA

TIPOS_TELA = ("insert", "logo", "lettering_logo")


norm = AL.norm      # palavra sem caixa, acento nem pontuação (a mesma do casamento)


# ------------------------------------------------------------------ roteiro e inserts

def ler_blocos(roteiro):
    from parser_roteiro import parse
    return parse(roteiro)


def palavras_da_narracao(blocks):
    narr = []
    for b in blocks:
        narr += b["narr"].split()
    return narr


def carregar_inserts(caminho):
    """Mapa {palavra-chave: {file, start, speed, zoom, crop, split, pip, ...}} do `VAM_INSERTS_JSON`.
    Sem arquivo, vazio: não existe mapa padrão (o antigo apontava para os assets de um anúncio)."""
    if not caminho:
        return {}
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def achar_insert(inserts, instr):
    """Insert que a instrução do roteiro pede, casado por palavra-chave (sem ligar pra caixa).

    FALHA ALTO QUANDO NÃO ACHA. O `return list(INSERTS.values())[0]` de antes trocava o asset EM
    SILÊNCIO: o bloco cuja palavra-chave não batesse passava a mostrar o PRIMEIRO insert do config, e
    nada no log dizia isso. Quem pagaria a conta era quem tentasse a correção mais óbvia, tirar um
    insert do config: o bloco não some, ele vira outro asset. Substituição muda o que aparece na
    tela, então não pode ser decisão de fallback."""
    s = instr.lower()
    for k, v in inserts.items():
        if k in s:
            return v
    raise CA.ErroFootage(
        f"ERRO: nenhum insert do config casa com a instrucao {instr!r}.\n"
        f"       keywords disponiveis: {', '.join(sorted(inserts)) or '(nenhuma)'}\n"
        "       Corrija a keyword no roteiro ou a entrada no *_inserts.json (VAM_INSERTS_JSON). "
        "Trocar de asset em silencio nao e opcao.")


def preparar_insert_cfg(b, inserts):
    """cfg final do insert, montado UMA vez para servir à chave de cache e ao render: duplicar essa
    lógica em dois lugares é como a marcação de layout do ritmo já vazou em silêncio antes."""
    c = achar_insert(inserts, b["instr"])
    if b.get("_layout"):
        # o layout vem do PLANO DE RITMO e mora no bloco; o render recebe o cfg do INSERT
        c = {**c, "_layout": b["_layout"]}
    if b.get("_crop"):
        c = {**c, "crop": b["_crop"]}      # reenquadramento deste plano (jump cut)
    if b.get("_fonte_off"):
        # a fonte do insert continua de onde parou quando o plano volta pro rosto e depois retorna.
        # `start` é em tempo de FONTE, então o deslocamento entra multiplicado pela velocidade.
        off = float(b["_fonte_off"]) * float(c.get("speed", 1.0) or 1.0)
        c = {**c, "start": float(c.get("start", 0) or 0) + off}
    return c


# ------------------------------------------------------------------ alinhamento (parakeet)

def executavel_parakeet(amb=None):
    """Caminho do `parakeet-mlx`, achado pelo backend de áudio (PATH e scripts do `.venv`). Nunca num
    caminho cravado no HOME: o do aluno não tem o do dono. Sem ele, UMA mensagem com o conserto."""
    from audio.backends import parakeet as pk
    from audio.transcrever import Ambiente
    exe = pk.achar_executavel(amb if amb is not None else Ambiente.real())
    if exe is None:
        raise CA.ErroFootage(
            "ERRO: parakeet-mlx não encontrado (ele alinha a narração ao áudio do avatar). "
            "Instale com: python3 -m pip install parakeet-mlx (Apple Silicon). "
            "O `bash setup.sh` instala no .venv do repo.")
    return exe


def duracao_do_audio(avatar):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=nw=1:nk=1", avatar],
                                capture_output=True, text=True).stdout.strip())


def tokens_do_parakeet(dados):
    """As palavras ouvidas, `[(inicio, fim, texto)]`, do JSON do parakeet (tokens em qualquer
    profundidade, em ordem de tempo). Token com espaço na frente abre palavra nova; sem espaço continua
    a anterior ("Ag" + "ora")."""
    raw = []

    def grab(o):
        if isinstance(o, dict):
            if "tokens" in o and isinstance(o["tokens"], list):
                for t in o["tokens"]:
                    raw.append((float(t["start"]), float(t["end"]), t.get("text", "")))
            for v in o.values():
                grab(v)
        elif isinstance(o, list):
            for v in o:
                grab(v)

    grab(dados)
    raw.sort()
    pk = []
    for s, e, txt in raw:
        nova = txt.startswith(" ") or not pk
        c = txt.strip()
        if not c:
            continue
        if nova:
            pk.append([s, e, c])
        else:
            pk[-1][1] = e
            pk[-1][2] += c
    return [(s, e, c) for s, e, c in pk]


def alinhar_palavras(dados, narr_words, audio_dur):
    """Casa as palavras do roteiro com as do parakeet. Devolve `[(inicio, fim, palavra)]`, uma por
    palavra da narração. `dados` é o JSON do parakeet (tokens em qualquer profundidade). O casamento é o
    `timeline.alinhar.casar`."""
    return AL.casar(tokens_do_parakeet(dados), narr_words, audio_dur)


def alinhar(avatar, narr_words, tmp, executavel=None, run=None, duracao=None):
    """Extrai o áudio do avatar, roda o parakeet e alinha. Ordem dos subprocessos: ffmpeg, parakeet,
    ffprobe (a paridade confere essa ordem)."""
    executavel = executavel or executavel_parakeet()
    run = run or CA.run
    duracao = duracao or duracao_do_audio
    wav = os.path.join(tmp, "av.wav")
    run(["ffmpeg", "-y", "-i", avatar, "-vn", "-ac", "1", "-ar", "16000", wav])
    run([executavel, wav, "--output-format", "json", "--output-dir", tmp])
    audio_dur = duracao(avatar)
    saida = os.path.join(tmp, "av.json")
    if not os.path.isfile(saida):
        raise CA.ErroFootage(f"ERRO: o parakeet não gerou {saida}; rode `{executavel} {wav}` à mão para ver o motivo.")
    with open(saida, encoding="utf-8") as f:
        dados = json.load(f)
    return alinhar_palavras(dados, narr_words, audio_dur)


# ------------------------------------------------------------------ spans

def atribuir_spans(blocks, words):
    """Span de cada bloco por contagem de palavras. Devolve `(spans, bwords)`: `bwords[i]` é a lista de
    `(inicio, fim)` das palavras do bloco i."""
    spans, bwords = [], []
    idx = 0
    for b in blocks:
        n = len(b["narr"].split())
        seg = words[idx:idx + n] if n else words[idx:idx + 1]
        idx += n
        s = seg[0][0] if seg else (spans[-1][1] if spans else 0)
        e = seg[-1][1] if seg else s + 0.8
        if e <= s:
            e = s + 0.6
        spans.append((s, e))
        bwords.append([(w[0], w[1]) for w in seg])
    return spans, bwords


def tornar_contiguos(spans):
    """Fronteira entre blocos = início da 1ª palavra do próximo, com no mínimo 0,3 s por bloco."""
    bounds = [spans[0][0]]
    for i in range(1, len(spans)):
        bounds.append(max(spans[i][0], bounds[-1] + 0.3))
    bounds.append(max(spans[-1][1], bounds[-1] + 0.3))
    return [(bounds[i], bounds[i + 1]) for i in range(len(spans))]


# ------------------------------------------------------------------ plano de ritmo e escala

def plano_de_ritmo(blocks, spans, inserts):
    """O plano de ritmo (`ritmo.plano_de_ritmo`) dos blocos com estes spans. É o que a timeline guarda."""
    import ritmo as _R

    entrada = []
    for b, (s, e) in zip(blocks, spans):
        cfg = achar_insert(inserts, b["instr"]) if b["type"] == "insert" else None
        entrada.append({"tipo": "insert" if b["type"] == "insert" else "orig",
                        "s": s, "e": e,
                        "crop": (cfg or {}).get("crop"),
                        "dur_max": (cfg or {}).get("dur_max"),
                        # a fala do bloco: o ritmo trava o insert quando ela aponta pra tela
                        # ("...que você tá vendo NA TELA" com o quadro no avatar). Nos QUATRO
                        # chamadores, ou desencontra.
                        "texto": b.get("narr", "")})
    return _R.plano_de_ritmo(entrada)


def aplicar_ritmo(blocks, spans, bwords, inserts):
    """Aplica o plano de ritmo: cada plano vira um bloco (a narração do bloco original se fatia por
    contagem de palavras). Devolve `(blocks, spans, bwords, plano)`.

    A tupla de palavra é `(inicio, fim)`, NÃO `(texto, tempo)`: a narração se fatia por CONTAGEM."""
    return fatiar_pelo_plano(blocks, bwords, plano_de_ritmo(blocks, spans, inserts))


def fatiar_pelo_plano(blocks, bwords, plano):
    """Cada plano vira um bloco, com a narração do bloco original fatiada por contagem de palavras.
    Devolve `(blocks, spans, bwords, plano)`. É o que a montagem faz com o plano lido da timeline."""
    nb, ns, nw = [], [], []
    usadas = {}
    for seg in plano:
        bi = seg["bloco"]
        b = blocks[bi]
        wt = bwords[bi]
        s2, e2 = seg["s"], seg["e"]
        wa = [w for w in wt if s2 <= w[1] < e2]
        ini = usadas.get(bi, 0)
        pal = b["narr"].split()
        novo = {**b, "narr": " ".join(pal[ini:ini + len(wa)])}
        usadas[bi] = ini + len(wa)
        if seg["tipo"] == "orig" and b["type"] == "insert":
            novo["type"] = "orig"           # plano que volta pro rosto no meio do insert
        if seg.get("layout"):
            # alternância de layout: com o `crop` desligado no split, duas visitas ao mesmo asset
            # mostravam o quadro IDÊNTICO e o corte não registrava na detecção de cena (17 cortes no
            # arquivo contra 12 visitas planejadas). Trocar o layout muda ~60% dos pixels.
            novo["_layout"] = seg["layout"]
        if seg.get("crop"):
            novo["_crop"] = seg["crop"]       # reenquadramento deste plano
        if seg.get("base"):
            novo["_base"] = seg["base"]       # escala base: o salto entre planos É o corte
        if seg.get("fonte_off"):
            novo["_fonte_off"] = seg["fonte_off"]    # a fonte do insert não reinicia
        nb.append(novo)
        ns.append((s2, e2))
        nw.append(wa)
    return nb, ns, nw, plano


def decidir_bases(blocks):
    """Decide `_base` de cada bloco, em ordem. Sequencial por natureza (cada base depende da anterior)
    mas não depende de render nenhum: é só decisão de número, por isso fica fora do pool de render."""
    for i, b in enumerate(blocks):
        if i > 0 and b["type"] in ("orig", "lettering") and blocks[i - 1]["type"] in TIPOS_TELA:
            b["_base"] = 1.0
            continue
        if b["type"] == "orig":
            # alterna contra o bloco anterior se ele também for apresentador; se vier de tela, 1,0
            if "_base" not in b:
                prev = blocks[i - 1] if i > 0 else None
                prev_apres = prev is not None and prev["type"] not in TIPOS_TELA
                b["_base"] = (1.14 if prev.get("_base", 1.0) < 1.07 else 1.0) if prev_apres else 1.0
        elif b["type"] == "lettering":
            bprev = blocks[i - 1].get("_base", 1.0) if i > 0 else 1.0
            b["_base"] = 1.14 if bprev < 1.07 else 1.0
