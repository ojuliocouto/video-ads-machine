"""Motor de montagem de timeline do Video Ads Machine 2.0.

Substitui o trabalho manual feito no reelC: casa a fala verbatim do roteiro
(grafia/acentuacao corretas) com os timestamps de um transcript word-level
(que pode ter erro de grafia), agrupa em legendas word-by-word e posiciona
os letterings LEAD/KEY no timestamp certo da fala. Ver DESIGN.md secao 6.

Convencao de marcacao no roteiro (arquivo .txt lido por `build`):
    - Trechos entre colchetes sao DIRECOES, nunca fazem parte da fala:
        [LEAD: ROTINA MATINAL]   -> eyebrow/texto pequeno do lettering
        [KEY: o cafe some]       -> frase-chave (texto grande) do lettering
        [DUR: 3.2]               -> (opcional) duracao em segundos do
                                     lettering; se omitido usa DEFAULT_LETT_DUR
      Cada par LEAD+KEY consecutivo vira UMA entrada de lettering, ancorada
      na PROXIMA palavra falada depois do marcador (a marcacao fica logo
      ANTES do trecho de fala que ela ilustra). ids gerados em sequencia:
      lettA, lettB, lettC... (mesma convencao usada no reelC real).
    - Palavras-chave dentro da fala usam *asteriscos*: podem marcar uma
      palavra sozinha ("*muda*") ou abrir numa palavra e fechar em outra
      mais adiante ("*oportunidade de ouro*"), cobrindo todas as palavras
      no meio. Os asteriscos nunca aparecem no texto final (kw=True).
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from pathlib import Path
from typing import Any


DEFAULT_LETT_DUR = 2.5


# ---------------------------------------------------------------------------
# align_words
# ---------------------------------------------------------------------------

def _strip_kw_markers(tokens: list[str]) -> tuple[list[str], list[bool]]:
    """Remove os *asteriscos* de marcacao de palavra-chave e devolve as flags.

    Suporta palavra unica (`*muda*`) e frase que abre numa palavra e fecha
    em outra (`*oportunidade`, `de`, `ouro*`).
    """
    cleaned: list[str] = []
    kw_flags: list[bool] = []
    in_kw = False
    for tok in tokens:
        starts = tok.startswith("*") and len(tok) > 1
        ends = tok.endswith("*") and len(tok) > 1
        text = tok
        if starts and ends:
            text = tok[1:-1]
            is_kw = True
            # in_kw nao muda: e uma marcacao autocontida numa palavra so.
        elif starts:
            text = tok[1:]
            in_kw = True
            is_kw = True
        elif ends and in_kw:
            text = tok[:-1]
            is_kw = True
            in_kw = False
        else:
            is_kw = in_kw
        cleaned.append(text)
        kw_flags.append(is_kw)
    return cleaned, kw_flags


def _word_text(transcript_word: dict) -> str:
    """Le o texto de uma palavra do transcript, aceitando as chaves usuais."""
    return str(transcript_word.get("text", transcript_word.get("word", "")))


def _normalize(word: str) -> str:
    """Normaliza pra comparacao: sem acento, sem pontuacao, minusculo."""
    word = unicodedata.normalize("NFKD", word)
    word = "".join(c for c in word if not unicodedata.combining(c))
    word = re.sub(r"[^a-z0-9]", "", word.lower())
    return word


def _distribute(timestamps: list, j1: int, j2: int, span_start: float, span_end: float) -> None:
    """Distribui um intervalo de tempo igualmente entre varias palavras do roteiro."""
    n = j2 - j1
    if n <= 0:
        return
    step = (span_end - span_start) / n
    for k in range(n):
        start = span_start + step * k
        end = span_start + step * (k + 1)
        timestamps[j1 + k] = (start, end)


def _fill_gaps(timestamps: list) -> None:
    """Interpola palavras do roteiro sem nenhuma correspondencia no transcript."""
    n = len(timestamps)
    i = 0
    while i < n:
        if timestamps[i] is not None:
            i += 1
            continue
        j = i
        while j < n and timestamps[j] is None:
            j += 1
        prev_end = timestamps[i - 1][1] if i > 0 else 0.0
        if j < n:
            next_start = timestamps[j][0]
        else:
            # nao ha proxima palavra alinhada: estende com um passo padrao.
            next_start = prev_end + 0.3 * (j - i)
        gap = j - i
        step = (next_start - prev_end) / gap if gap else 0.0
        for k in range(gap):
            start = prev_end + step * k
            end = prev_end + step * (k + 1)
            timestamps[i + k] = (start, end)
        i = j


def _align_timestamps(clean_roteiro: list[str], transcript_words: list[dict]) -> list[tuple]:
    """Casa cada palavra do roteiro com um (start, end) vindo do transcript."""
    t_texts = [_normalize(_word_text(tw)) for tw in transcript_words]
    r_texts = [_normalize(w) for w in clean_roteiro]

    timestamps: list[Any] = [None] * len(clean_roteiro)
    matcher = difflib.SequenceMatcher(None, t_texts, r_texts, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        t_len = i2 - i1
        r_len = j2 - j1
        if tag == "equal":
            for k in range(r_len):
                tw = transcript_words[i1 + k]
                timestamps[j1 + k] = (tw["start"], tw["end"])
        elif tag == "replace" and t_len > 0 and r_len > 0:
            if t_len == r_len:
                # mesma contagem: so a grafia mudou (correcao de erro).
                for k in range(r_len):
                    tw = transcript_words[i1 + k]
                    timestamps[j1 + k] = (tw["start"], tw["end"])
            else:
                span_start = transcript_words[i1]["start"]
                span_end = transcript_words[i2 - 1]["end"]
                _distribute(timestamps, j1, j2, span_start, span_end)
        # "insert" (roteiro tem palavra que o transcript nao tem) fica None
        # e e preenchido por _fill_gaps. "delete" (transcript tem palavra
        # extra que o roteiro nao tem) e simplesmente ignorado.

    _fill_gaps(timestamps)
    return timestamps


def align_words(roteiro_words: list[str], transcript_words: list[dict]) -> list[dict]:
    """Casa a fala verbatim do roteiro com os timestamps do transcript.

    A grafia (acentuacao correta) SEMPRE vem do roteiro; os tempos vem do
    transcript, alinhados por ordem/similaridade (difflib). `kw` marca
    palavra-chave conforme a marcacao de *asteriscos* no roteiro.
    """
    clean_texts, kw_flags = _strip_kw_markers(roteiro_words)
    timestamps = _align_timestamps(clean_texts, transcript_words)

    result = []
    for text, (start, end), kw in zip(clean_texts, timestamps, kw_flags):
        result.append({"text": text, "start": start, "end": end, "kw": kw})
    return result


# ---------------------------------------------------------------------------
# group_captions
# ---------------------------------------------------------------------------

_CAPTION_BREAK_PUNCT = (".", ",", "?", "!", ";", ":")


def _ends_with_break_punct(text: str) -> bool:
    text = text.rstrip()
    return bool(text) and text[-1] in _CAPTION_BREAK_PUNCT


def _close_caption_group(bucket: list[dict]) -> dict:
    return {
        "start": bucket[0]["start"],
        "end": bucket[-1]["end"],
        "words": list(bucket),
    }


# Quanto um grupo de legenda SEGURA depois da ultima palavra, pra atravessar a pausa
# da fala. Ver `_segurar_nas_pausas`.
# 1,30s deixava 11,8% do anuncio sem texto (teto 12%), com dois vaos de 1,41s e
# 1,56s, este ultimo bem na virada de argumento. 1,60s fecha os dois.
SEGURAR_MAX = 1.60      # nunca segurar mais que isso
SEGURAR_FOLGA = 0.06    # respiro antes do proximo grupo entrar


def _segurar_nas_pausas(groups, segurar_max=SEGURAR_MAX, folga=SEGURAR_FOLGA):
    """Estende o fim de cada grupo ate perto do inicio do proximo.

    POR QUE (26/08/2026): o grupo morria na ultima palavra, entao toda pausa da fala
    virava tela sem texto nenhum. Medido no jh13: 11 vaos de 1,0 a 1,5s, somando 12%
    do anuncio, e o `gate-ad.py` reprova acima de 12% ("o anuncio roda mudo em feed
    silencioso"). Nos tres vaos que conferi era ele falando em tela cheia, sem legenda.

    Segurar a frase durante a pausa e o que o CapCut faz e o que o olho espera: a
    legenda acompanha o pensamento, nao a silaba. O teto de 1,30s existe pra frase
    velha nao ficar pendurada quando a pausa e longa de verdade (troca de bloco,
    respiro dramatico): ai a tela limpa e intencional.

    Nao mexe em `start` nem na ordem: so empurra `end` pra frente, no maximo ate
    `folga` antes do proximo grupo. Grupo nunca passa a se sobrepor ao seguinte.
    """
    for atual, prox in zip(groups, groups[1:]):
        limite = prox["start"] - folga
        alvo = min(atual["end"] + segurar_max, limite)
        if alvo > atual["end"]:
            atual["end"] = round(alvo, 3)
    return groups


def group_captions(words: list[dict], max_words: int = 3) -> list[dict]:
    """Agrupa palavras em janelas de legenda respeitando pontuacao.

    Fecha o grupo ao atingir `max_words` OU quando a ultima palavra
    adicionada termina em pontuacao (.,?!;:), o que vier primeiro.

    Depois de agrupar, cada grupo SEGURA durante a pausa da fala
    (ver `_segurar_nas_pausas`), pra a tela nao ficar sem texto entre frases.
    """
    groups: list[dict] = []
    bucket: list[dict] = []
    for word in words:
        bucket.append(word)
        if len(bucket) >= max_words or _ends_with_break_punct(word["text"]):
            groups.append(_close_caption_group(bucket))
            bucket = []
    if bucket:
        groups.append(_close_caption_group(bucket))
    return _segurar_nas_pausas(groups)


# ---------------------------------------------------------------------------
# parser do roteiro (compartilhado por place_letterings e build)
# ---------------------------------------------------------------------------

# Um token e um marcador `[TAG: conteudo]` OU uma palavra sem espaco.
_ROTEIRO_TOKEN_RE = re.compile(r"\[(?P<tag>[A-Z]+):\s*(?P<content>[^\]]*)\]|(?P<word>\S+)")


def _parse_roteiro(roteiro_text: str) -> tuple[list[str], list[dict]]:
    """Separa o roteiro em palavras faladas e marcadores de direcao.

    Cada marcador guarda `word_index`: quantas palavras faladas ja foram
    vistas ANTES dele (ou seja, o indice da proxima palavra falada).
    """
    words: list[str] = []
    markers: list[dict] = []
    for m in _ROTEIRO_TOKEN_RE.finditer(roteiro_text):
        if m.group("tag"):
            markers.append({
                "tag": m.group("tag"),
                "content": m.group("content").strip(),
                "word_index": len(words),
            })
        elif m.group("word"):
            words.append(m.group("word"))
    return words, markers


def _timestamp_for_index(words: list[dict], word_index: int) -> float:
    """Tempo de ancoragem pra um indice de palavra falada (ver docstring do modulo)."""
    if not words:
        return 0.0
    if word_index >= len(words):
        return words[-1]["end"]
    return words[word_index]["start"]


# ---------------------------------------------------------------------------
# place_letterings
# ---------------------------------------------------------------------------

def place_letterings(roteiro_text: str, words: list[dict]) -> list[dict]:
    """Extrai os pares LEAD/KEY do roteiro e casa cada um com o tempo da fala.

    `words` deve ser a saida (ja alinhada) de `align_words` aplicada as
    mesmas palavras faladas que `_parse_roteiro` extrai de `roteiro_text`
    (e o que `build` garante ao encadear as duas chamadas).

    Um par LEAD+KEY so e fechado (e vira uma entrada) quando aparece o
    proximo LEAD ou quando o roteiro acaba: isso permite que o `[DUR: ...]`
    opcional venha DEPOIS do KEY (a ordem natural de escrever: lead, key,
    e so por ultimo, se precisar, ajustar a duracao).
    """
    _, markers = _parse_roteiro(roteiro_text)

    letterings: list[dict] = []
    pending_lead: dict | None = None
    pending_key: dict | None = None
    pending_dur: float | None = None

    def _flush() -> None:
        if pending_lead is not None and pending_key is not None:
            start = _timestamp_for_index(words, pending_lead["word_index"])
            dur = pending_dur if pending_dur is not None else DEFAULT_LETT_DUR
            letterings.append({
                "id": f"lett{chr(65 + len(letterings))}",
                "lead": pending_lead["content"],
                "key": pending_key["content"],
                "start": start,
                "dur": dur,
            })

    for marker in markers:
        tag = marker["tag"]
        if tag == "LEAD":
            _flush()
            pending_lead = marker
            pending_key = None
            pending_dur = None
        elif tag == "KEY" and pending_lead is not None:
            pending_key = marker
        elif tag == "DUR" and pending_lead is not None:
            try:
                pending_dur = float(marker["content"])
            except ValueError:
                pending_dur = None

    _flush()
    return letterings


# ---------------------------------------------------------------------------
# get_transcript (stub documentado)
# ---------------------------------------------------------------------------

def get_transcript(voz_path: str) -> list[dict]:
    """Gera o transcript word-level a partir do audio da voz.

    STUB: a integracao real com o transcript do HyperFrames (whisper
    word-level, ver DESIGN.md secao 6 passo 1) ainda nao foi feita. Quem
    chamar `build()` fora de teste precisa substituir esta funcao por uma
    implementacao real (que roda o transcriber do HyperFrames sobre
    `voz_path` e devolve uma lista de dicts no formato
    `{"text": str, "start": float, "end": float}`, um por palavra).

    Em teste, mocke com `monkeypatch.setattr(build_timeline, "get_transcript", ...)`.
    """
    raise NotImplementedError(
        "get_transcript ainda nao integra com o HyperFrames (DESIGN.md secao 6). "
        "Substitua esta funcao pela integracao real ou mocke em teste."
    )


# ---------------------------------------------------------------------------
# build: injecao no template
# ---------------------------------------------------------------------------

_PRESET_MARKER_RE = re.compile(r"<!--\s*INJECT:preset:(?P<dim>[a-zA-Z0-9_-]+)\s*-->")


def _render_captions_html(groups: list[dict]) -> str:
    if not groups:
        return '<div id="caps" class="clip" data-start="0" data-duration="0" data-track-index="30"></div>'
    # O wrapper #caps comeca em 0 e cobre ate a ultima palavra, SEMPRE.
    # Antes ele comecava no 1o grupo (data-start=5.04 no ad03v2) e o render engolia
    # os primeiros grupos: o overlay saia VAZIO de 5s a 16s, mesmo com os grupos
    # presentes no HTML, e a 1a legenda so aparecia em 16,5s. Foram 13s (25% do ad)
    # sem legenda, o defeito que mais derrubou nota na leva inteira. Quem controla
    # a visibilidade de cada grupo e o GSAP via data-g-start; o clip so precisa
    # estar vivo desde o inicio.
    caps_dur = groups[-1]["end"]
    lines = [
        f'<div id="caps" class="clip" data-start="0" '
        f'data-duration="{caps_dur:.3f}" data-track-index="30">'
    ]
    # Atencao: as legendas usam attrs CUSTOM (data-g-start/data-w-start), NAO
    # data-start/data-end. O HyperFrames trata data-start/data-duration como
    # clip e reclamaria (as palavras nao sao clips: o runtime do template as
    # anima via GSAP lendo esses attrs custom). So o #caps (wrapper) e clip.
    for group in groups:
        lines.append(
            # "baixa" vem do gen_ad_v2 quando a legenda cai sobre insert que JA TEM texto
            # proprio (card de depoimento, print de prova social). La ela desce pro rodape
            # em vez de pousar no paragrafo do card. Suprimir era a primeira ideia e deu
            # errado: sem legenda o AD15 ficou 6,0s sem texto de tela e o gate reprovou
            # (teto de 12% do video sem texto). Descer resolve os dois lados.
            # "costura" (split) tem prioridade sobre "baixa": no split a posicao baixa
            # cai na boca do apresentador, que e o defeito que ela deveria evitar.
            # "claro" vem do gen_ad_v2 quando o fundo daquele trecho e CLARO (insert de
            # tela cheia com mockup de pagina branca). A legenda e branca, e sobre fundo
            # claro ela some: contraste medido no quadro entregue do build 26, 1,52:1,
            # contra 11,7 e 14,3 nos trechos escuros do mesmo anuncio. Mudar de posicao
            # nao resolve nesse caso: o perfil do quadro inteiro nao tem UMA faixa acima
            # de 3,6:1 fora da zona morta da UI. La a legenda INVERTE a tinta (escura em
            # vez de branca), que resolve sem tarja (vetada pela Jheni em 19/08) e sem
            # engrossar contorno (deixa a letra oca sobre branco, achado do diretor).
            f'  <div class="cgrp'
            f'{" cgrp-costura" if group.get("costura") else (" cgrp-baixa" if group.get("baixa") else "")}{" cgrp-sem-lead" if group.get("sem_lead") else ""}{" cgrp-claro" if group.get("claro") else ""}" '
            f'data-g-start="{group["start"]:.3f}" '
            f'data-g-end="{group["end"]:.3f}">'
        )
        for word in group["words"]:
            css_class = "cw kw" if word.get("kw") else "cw"
            # DUAS CAMADAS POR PALAVRA (29/08/2026, pedido do Julio por audio: "nao
            # gosto desse estilo de legenda onde ela sobe, fica pulando; gosto quando e
            # uma cor, vai preenchendo ela, de forma linear").
            # `base` e a palavra apagada, `fill` e a mesma palavra acesa por cima, e o
            # GSAP revela a de cima da esquerda pra direita enquanto ela e falada.
            # Por que duas camadas e nao `background-clip: text`: aquele caminho exige
            # `color: transparent`, e se o recurso falhar no renderizador a palavra SOME.
            # Aqui o pior caso e a camada de cima aparecer de uma vez, ou seja legenda
            # sem animacao, que e chato mas legivel. Legenda invisivel e defeito grave.
            lines.append(
                f'    <span class="{css_class}" data-w-start="{word["start"]:.3f}" '
                f'data-w-end="{word["end"]:.3f}">'
                f'<span class="base">{word["text"]}</span>'
                f'<span class="fill">{word["text"]}</span></span>'
            )
        lines.append("  </div>")
    lines.append("</div>")
    return "\n".join(lines)


def _render_letterings_html(letterings: list[dict]) -> str:
    blocks = []
    for i, lett in enumerate(letterings):
        track = 32 + i
        blocks.append(
            # "split" vem do gen_ad_v2 quando o lettering cai num bloco de tela dividida.
            # La ele desce pro peito do Thales; centrado no quadro ele pousaria no rosto.
            f'<div class="lett clip{" lett-split" if lett.get("split") else ""}" '
            f'id="{lett["id"]}" data-start="{lett["start"]:.3f}" '
            f'data-duration="{lett["dur"]:.3f}" data-track-index="{track}">\n'
            f'  <div class="lead">{lett["lead"]}</div>\n'
            f'  <div class="key">{lett["key"]}</div>\n'
            f"</div>"
        )
    return "\n".join(blocks)


def _inject_presets(html: str, brief: dict) -> str:
    """Substitui `<!-- INJECT:preset:<dimensao> -->` pelo CSS/JS do preset.

    Le o preset escolhido em `brief["styles"][dimensao]` e busca o arquivo
    em `presets/<dimensao>/<nome>.css` (ou `.js`). Se o preset nao foi
    escolhido no brief, ou o arquivo ainda nao existe (a biblioteca de
    presets e outra task da Wave 1, em paralelo), cai num comentario de
    fallback em vez de quebrar: o template continua lintavel.
    """
    styles = (brief or {}).get("styles", {})
    presets_root = Path(__file__).resolve().parent.parent / "presets"

    def _replace(match: re.Match) -> str:
        dim = match.group("dim")
        name = styles.get(dim)
        if not name:
            return f"<!-- preset:{dim} nao escolhido no brief -->"
        for ext, tag in ((".css", "style"), (".js", "script")):
            candidate = presets_root / dim / f"{name}{ext}"
            if candidate.exists():
                return f"<{tag}>\n{candidate.read_text(encoding='utf-8')}\n</{tag}>"
        return f"<!-- preset:{dim}:{name} (arquivo ainda nao existe) -->"

    return _PRESET_MARKER_RE.sub(_replace, html)


def build(roteiro_path: str, voz_path: str, template_path: str, brief: dict) -> str:
    """Orquestra o pipeline: roteiro + voz -> template preenchido (HTML).

    1. Le o roteiro e separa palavras faladas dos marcadores de direcao.
    2. Gera o transcript word-level (`get_transcript`, stub ate a
       integracao real com o HyperFrames).
    3. `align_words` casa a fala do roteiro com os tempos do transcript.
    4. `group_captions` agrupa em legendas word-by-word.
    5. `place_letterings` posiciona os letterings LEAD/KEY.
    6. Injeta tudo no template (`<!-- INJECT:captions -->`,
       `<!-- INJECT:letterings -->`, `<!-- INJECT:preset:<dim> -->`) e
       devolve o HTML final como string (pronto pra `hyperframes lint`).
    """
    roteiro_text = Path(roteiro_path).read_text(encoding="utf-8")
    template_html = Path(template_path).read_text(encoding="utf-8")

    roteiro_words, _markers = _parse_roteiro(roteiro_text)
    transcript_words = get_transcript(voz_path)
    words = align_words(roteiro_words, transcript_words)

    max_words = (brief or {}).get("max_words_per_caption", 3)
    groups = group_captions(words, max_words=max_words)
    letterings = place_letterings(roteiro_text, words)

    html = template_html
    html = html.replace("<!-- INJECT:captions -->", _render_captions_html(groups))
    html = html.replace("<!-- INJECT:letterings -->", _render_letterings_html(letterings))
    html = _inject_presets(html, brief or {})
    return html
