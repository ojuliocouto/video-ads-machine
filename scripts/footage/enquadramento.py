"""Enquadramento: o que o motor mede no avatar e nos assets antes de montar um filtro.

## Medir, nunca chutar (defeito 2 do plano)

O motor antigo procurava `medir_enquadramento.py` na pasta de DADOS. No clone limpo ele não está
lá: a medição falhava calada e o split caía em bias 0,30, o centro do recorte em 0,5 e o recorte
da bolinha em y=640. Chute com cara de medição, e ninguém via. Agora:

  - o script é achado pelo CÓDIGO (`caminhos.CODIGO`), onde o repo o versiona;
  - falha de medição (script ausente, saída inválida, tempo esgotado) levanta
    `ErroEnquadramento` com a causa e o que fazer. Nunca devolve número fixo.

A única forma de pular a medição do split é digitar `VAM_SPLIT_BIAS`, como exceção declarada.

## Sondas do arquivo

`aspecto`, `largura_fonte` e `pular_preto` leem o arquivo com ffprobe/ffmpeg. São cacheadas por
arquivo: o mesmo asset em seis fatias custa uma leitura. `executar` é injetável (padrão
`subprocess.run`) para o teste não precisar de ffmpeg.
"""
import json
import os
import re
import subprocess
import sys

import caminhos

AVISO_SEM_MEDICAO = ("Fixe o valor na mão com VAM_SPLIT_BIAS=<número de 0 a 1> só se souber o que está "
                     "fazendo: medido é o padrão e é o que acerta cada look.")

_CACHE_CONTEUDO = {}     # src -> (fx, fy, modo)
_CACHE_ASPECTO = {}
_CACHE_LARG = {}
_PRETO_CACHE = {}
_PIP_CROP_CACHE = {}


class ErroEnquadramento(RuntimeError):
    """A medição de enquadramento não aconteceu. A mensagem diz o que falhou e como seguir."""


def _executar(executar):
    return executar if executar is not None else subprocess.run


def script_de_medicao():
    """Caminho do `medir_enquadramento.py`, no código. Erro alto se não existir."""
    p = caminhos.CODIGO / "medir_enquadramento.py"
    if not p.is_file():
        raise ErroEnquadramento(
            f"O script de medição de enquadramento não existe em {p}. Ele faz parte do código "
            "(scripts/medir_enquadramento.py): reinstale ou restaure o repositório. Medir é obrigatório, "
            "o motor não cai em número fixo.")
    return p


def _medir_json(args, executar, o_que, dica=""):
    """Roda o script de medição e devolve o dict do JSON. Qualquer falha vira ErroEnquadramento."""
    script = script_de_medicao()
    try:
        r = _executar(executar)([sys.executable, str(script), *args],
                                capture_output=True, text=True, timeout=180)
    except Exception as e:  # tempo esgotado, interpretador sumido, etc.
        raise ErroEnquadramento(f"A medição de enquadramento de {o_que} não rodou ({type(e).__name__}: {e}). "
                                f"{dica}".strip())
    if r.returncode != 0:
        cauda = (r.stderr or r.stdout or "").strip()[-300:]
        raise ErroEnquadramento(f"A medição de enquadramento de {o_que} saiu com código {r.returncode}: "
                                f"{cauda or 'sem mensagem'}. {dica}".strip())
    try:
        dados = json.loads(r.stdout)
        if not isinstance(dados, dict):
            raise ValueError("a saída não é um objeto JSON")
    except ValueError as e:
        raise ErroEnquadramento(f"A medição de enquadramento de {o_que} devolveu uma saída que não é JSON "
                                f"({e}): {(r.stdout or '')[:120]!r}. {dica}".strip())
    return dados


# ------------------------------------------------------------------ avatar

def medir_bias_split(avatar, env=None, executar=None):
    """Bias do recorte do painel de baixo do split.

    `VAM_SPLIT_BIAS` (se definida e não vazia) vale e dispensa a medição. Senão o script mede a
    pessoa no avatar. Falha de medição é erro alto, nunca um número padrão."""
    env = os.environ if env is None else env
    digitado = env.get("VAM_SPLIT_BIAS")
    if digitado:
        try:
            return float(digitado)
        except ValueError:
            raise ErroEnquadramento(f"VAM_SPLIT_BIAS={digitado!r} não é um número entre 0 e 1.")
    dados = _medir_json(["avatar", avatar, "--json"], executar, f"o avatar {avatar}", AVISO_SEM_MEDICAO)
    try:
        bias = float(dados["VAM_SPLIT_BIAS"])
    except (KeyError, TypeError, ValueError):
        raise ErroEnquadramento(f"A medição de enquadramento do avatar {avatar} não trouxe o campo "
                                f"VAM_SPLIT_BIAS (veio {sorted(dados)}). {AVISO_SEM_MEDICAO}")
    print(f"  [medido] enquadramento do split: bias={bias}", flush=True)
    return bias


def pip_crop(avatar, executar=None):
    """Recorte quadrado da cabeça para a bolinha, MEDIDO no avatar: 720 px a partir de 60 px acima
    do topo da pessoa, centrado. O chute antigo (640 em y=750) decapitava o apresentador quando o
    topo estava em y~693. Cacheado por avatar."""
    if avatar in _PIP_CROP_CACHE:
        return _PIP_CROP_CACHE[avatar]
    dados = _medir_json(["avatar", avatar, "--json"], executar, f"o recorte da bolinha do avatar {avatar}")
    try:
        topo = int(dados["topo_px"])
    except (KeyError, TypeError, ValueError):
        raise ErroEnquadramento(f"A medição de enquadramento do avatar {avatar} não trouxe topo_px "
                                f"(veio {sorted(dados)}); sem ele o recorte da bolinha não é seguro.")
    lado = 720
    y = min(max(0, topo - 60), 1920 - lado)
    crop = f"{lado}:{lado}:{(1080 - lado) // 2}:{y}"
    _PIP_CROP_CACHE[avatar] = crop
    print(f"  [medido] recorte da bolinha: {crop}", flush=True)
    return crop


# ------------------------------------------------------------------ assets

def medir_conteudo(src, alvo_w, alvo_h, executar=None):
    """(fx, fy, modo) do conteúdo do asset diante do painel `alvo_w x alvo_h`. Cacheado por arquivo.

    `fx, fy` é o centro do conteúdo (gravação de tela tem o assunto fora do meio) e `modo` é
    "preencher" ou "encaixar", decidido pela perda MEDIDA. Falha é erro alto: cair no meio
    (0,5, 0,5) cortava justamente o que a fala descrevia."""
    if src not in _CACHE_CONTEUDO:
        dados = _medir_json(["asset", src, "--painel", f"{alvo_w}x{alvo_h}", "--json"], executar,
                            f"o asset {src}")
        try:
            fx, fy = float(dados["centro_conteudo_x"]), float(dados["centro_conteudo_y"])
        except (KeyError, TypeError, ValueError):
            raise ErroEnquadramento(f"A medição de enquadramento do asset {src} não trouxe o centro do "
                                    f"conteúdo (veio {sorted(dados)}).")
        modo = dados.get("modo", "preencher")
        print(f"  [medido] {os.path.basename(src)}: centro x={fx:.2f} y={fy:.2f} | "
              f"perda ao preencher {dados.get('perda_ao_preencher', 0):.0%} -> {modo}", flush=True)
        _CACHE_CONTEUDO[src] = (fx, fy, modo)
    return _CACHE_CONTEUDO[src]


def crop_conteudo(src, alvo_w, alvo_h, crop_dims=None, executar=None):
    """Expressão `x:y` do crop do painel de cima, ancorada no CONTEÚDO medido do asset.

    O ffmpeg calcula in_w/in_h em tempo de filtro, então a expressão só injeta a FRAÇÃO medida e
    serve a qualquer resolução. Com recorte declarado, o conteúdo É o recorte: ancorar no meio dele
    é correto e dispensa medir (medir aqui mediria o arquivo inteiro, não a janela escolhida)."""
    if crop_dims:
        return "'(in_w-out_w)/2':'(in_h-out_h)/2'"
    fx, fy, _modo = medir_conteudo(src, alvo_w, alvo_h, executar)
    return (f"'clip((in_w*{fx:.4f})-(out_w/2),0,in_w-out_w)'"
            f":'clip((in_h*{fy:.4f})-(out_h/2),0,in_h-out_h)'")


def modo_do_painel(src, alvo_w, alvo_h, crop_dims=None, executar=None):
    """"preencher" ou "encaixar", conforme a perda MEDIDA (ou calculada, com recorte declarado).

    Preencher tapa a tarja mas descarta parte do asset; numa gravação de tela isso corta o que a fala
    descreve. Acima de 22% de perda, encaixar: o asset inteiro, com o fundo desfocado dele mesmo."""
    if crop_dims:
        cw, ch = crop_dims
        asp_a, asp_p = cw / ch, alvo_w / alvo_h
        perda = 1 - (min(asp_a, asp_p) / max(asp_a, asp_p))
        modo = "encaixar" if perda > 0.22 else "preencher"
        print(f"  [recorte declarado] {cw}x{ch}: perda ao preencher {perda:.0%} -> {modo}", flush=True)
        return modo
    return medir_conteudo(src, alvo_w, alvo_h, executar)[2]


def crop_fonte(cfg):
    """Recorte da FONTE declarado no inserts.json ("W:H:X:Y"): devolve (filtro, (w, h)).

    Existe porque `zoom` amplia e corta pelas BORDAS: numa gravação de tela o assunto quase nunca
    está centralizado, e ampliar comia a primeira letra de cada linha. Com `crop` escolhe-se a
    JANELA da tela que vale a pena mostrar. `split_crop` continua aceito como nome antigo."""
    sc = cfg.get("crop") or cfg.get("split_crop")
    if not sc:
        return "", None
    cw, ch, cx, cy = [int(v) for v in str(sc).split(":")]
    return f"crop={cw}:{ch}:{cx}:{cy},", (cw, ch)


# ------------------------------------------------------------------ sondas do arquivo

def aspecto(src, executar=None):
    """Aspecto (largura/altura) do asset, por ffprobe. Cacheado. Arquivo ilegível avisa e cai em
    16:9: o render seguinte falha por conta própria num arquivo quebrado."""
    if src not in _CACHE_ASPECTO:
        r = _executar(executar)(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                 "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", src],
                                capture_output=True, text=True)
        try:
            w, h = [int(v) for v in r.stdout.strip().split("x")[:2]]
            _CACHE_ASPECTO[src] = w / h
        except Exception:
            print(f"  [AVISO] não consegui ler as dimensões de {os.path.basename(src)}; "
                  "assumindo 16:9 até o ffmpeg dizer se o arquivo está quebrado", flush=True)
            _CACHE_ASPECTO[src] = 16 / 9
    return _CACHE_ASPECTO[src]


def largura_fonte(src, executar=None):
    """Largura em pixels do arquivo-fonte, por ffprobe. Cacheada; None se ilegível.

    O push-in precisa saber o quanto o asset ENCOLHEU para caber na janela, e isso é a razão entre a
    largura da janela e a largura nativa. Medida, nunca declarada: o campo do config pode estar
    velho, o arquivo não."""
    if src in _CACHE_LARG:
        return _CACHE_LARG[src]
    r = _executar(executar)(["ffprobe", "-v", "error", "-select_streams", "v:0",
                             "-show_entries", "stream=width", "-of", "csv=p=0", str(src)],
                            capture_output=True, text=True)
    try:
        _CACHE_LARG[src] = int(r.stdout.strip().split(",")[0])
    except Exception:
        _CACHE_LARG[src] = None
    return _CACHE_LARG[src]


def pular_preto(src, st, dur_take, executar=None):
    """Se a fonte está PRETA em `st` (fade-in do próprio asset), devolve `st` deslocado para o primeiro
    quadro claro. O corte seco expôs de 0,3 a 0,6 s de preto na entrada de cada fatia de insert
    (8 ocorrências medidas com blackdetect). Desloca no máximo 1,2 s e só quando o começo é preto de
    verdade: fonte escura legítima (luminância acima de 12) não é tocada."""
    chave = (src, round(st, 2))
    if chave in _PRETO_CACHE:
        return _PRETO_CACHE[chave]
    novo_st = st
    try:
        r = _executar(executar)(
            ["ffmpeg", "-v", "info", "-ss", str(st), "-t", "1.5", "-i", src,
             "-vf", "blackdetect=d=0.1:pix_th=0.06", "-an", "-f", "null", "-"],
            capture_output=True, text=True, timeout=60)
        m = re.search(r"black_start:(0(?:\.0+)?|0\.[0-9]+) black_end:([0-9.]+)", r.stderr)
        if m and float(m.group(1)) <= 0.05:
            salto = min(float(m.group(2)) + 0.05, 1.2)
            novo_st = st + salto
            print(f"  [preto] fonte {os.path.basename(src)} preta em {st:.2f}s: "
                  f"entrada desloca +{salto:.2f}s", flush=True)
    except Exception:
        pass
    _PRETO_CACHE[chave] = novo_st
    return novo_st
