"""Backend Mistral (Voxtral Mini Transcribe): nuvem, usa a MISTRAL_API_KEY que o aluno criou na aula Curso → Skill.

Regras que este cliente cumpre (da documentação oficial, docs.mistral.ai, audio transcription):
  - `POST https://api.mistral.ai/v1/audio/transcriptions`, modelo `voxtral-mini-latest` (o id fixo é
    `voxtral-mini-2602`; `MODELO` é a constante única).
  - tempo por palavra vem de `timestamp_granularities[]=word`. A documentação diz que isso NÃO combina com o campo
    `language`: por isso o idioma NÃO é enviado e a Mistral detecta sozinha. Em contrapartida, não há prompt de
    vocabulário; o glossário do aluno corrige a grafia depois.
  - o esquema real (medido em 20/10/2026): com `timestamp_granularities[]=word`, a resposta traz `segments`, e CADA
    segmento é UMA palavra (`{"type": "transcription_segment", "text": " skill", "start": 0.8, "end": 1.1}`, texto com
    espaço na frente e pontuação colada, tempo arredondado a 0,1 s). `language` volta `null`. O parser também aceita
    `words` no topo ou dentro de `segments[].words`, o texto em `word` ou `text`. Sem palavra com tempo, o backend
    falha com mensagem clara (o seletor cai na Groq e avisa em uma linha).
  - erro de capacidade da Mistral vem como HTTP 429 (`backend_out_of_capacity`): UM retry após 20 s; se repetir, vira
    ErroMistral e o seletor cai na Groq. Palavra de duração zero (cerca de 7,5%) ganha 0,1 s.
  - o corpo multipart é montado pelo `curl` (a chave vai por stdin), igual ao backend da Groq.

A chave vem de MISTRAL_API_KEY (ambiente ou `.env`), nunca de arquivo do repo.
"""
import json
import time
from pathlib import Path

from ..transcrever import monotonizar, normalizar_numeros
from . import groq as _groq

NOME = "mistral"
URL = "https://api.mistral.ai/v1/audio/transcriptions"
URL_MODELOS = "https://api.mistral.ai/v1/models"
MODELO = "voxtral-mini-latest"
ESPERA_429_S = 20.0          # a Mistral devolve 429 `backend_out_of_capacity`; UMA nova tentativa depois disto resolveu
DURACAO_MINIMA_S = 0.1       # a grade de tempo é de 0,1 s e cerca de 7,5% das palavras vêm com duração zero


class ErroMistral(RuntimeError):
    pass


def _chave(amb):
    return (amb.env.get("MISTRAL_API_KEY") or "").strip()


def disponivel(amb):
    return bool(_chave(amb))


def palavras_da_resposta(dados):
    """`[{text, start, end}]` da resposta, sem exigir um esquema só. Lista vazia se não há palavra com tempo."""
    if not isinstance(dados, dict):
        return []
    candidatos = []
    topo = dados.get("words")
    if isinstance(topo, list):
        candidatos.extend(topo)
    for seg in (dados.get("segments") or []):
        if not isinstance(seg, dict):
            continue
        if isinstance(seg.get("words"), list):
            candidatos.extend(seg["words"])
        elif not isinstance(topo, list):
            candidatos.append(seg)           # o formato real: o segmento É a palavra
    saida = []
    for w in candidatos:
        if not isinstance(w, dict):
            continue
        texto = w.get("word", w.get("text"))
        ini, fim = w.get("start"), w.get("end")
        if texto is None or ini is None or fim is None:
            continue
        try:
            ini, fim = float(ini), float(fim)
        except (TypeError, ValueError):
            continue
        partes = str(texto).split()
        if len(partes) > 1:                  # segmento com várias palavras (sem granularidade): divide o tempo
            passo = (fim - ini) / len(partes)
            saida.extend({"text": s, "start": ini + k * passo, "end": ini + (k + 1) * passo}
                         for k, s in enumerate(partes))
        elif partes:
            saida.append({"text": partes[0], "start": ini, "end": fim})
    return saida


def transcrever(audio, *, amb, workdir, prompt="", idioma="pt", transporte=None, dormir=None):
    chave = _chave(amb)
    if not chave:
        raise ErroMistral("MISTRAL_API_KEY não definida: ponha a chave da Mistral no .env")
    try:
        mp3 = _groq._comprimir(Path(audio), Path(workdir) / "mistral.mp3")
    except _groq.ErroGroq as e:
        raise ErroMistral(str(e))
    if mp3.stat().st_size > _groq.LIMITE_BYTES:
        raise ErroMistral(f"arquivo de {mp3.stat().st_size / 1e6:.1f} MB passa do limite de 25 MB: corte o áudio em "
                          "pedaços de 20 minutos")
    req = {
        "url": URL,
        "headers": {"Authorization": f"Bearer {chave}", "User-Agent": _groq.USER_AGENT},
        "campos": [("model", MODELO), ("timestamp_granularities[]", "word")],     # sem language: não combina
        "arquivo": str(mp3),
    }
    enviar = transporte or _groq._transporte_curl
    try:
        status, corpo = enviar(req)
        if status == 429:                    # capacidade esgotada: UM retry com espera, depois cai na Groq
            (dormir or time.sleep)(ESPERA_429_S)
            status, corpo = enviar(req)
    except _groq.ErroGroq as e:
        raise ErroMistral(str(e))
    if status != 200:
        raise ErroMistral(f"Mistral respondeu {status}: {(corpo or '').strip()[:200]}")
    try:
        dados = json.loads(corpo)
    except ValueError:
        raise ErroMistral(f"a resposta da Mistral não é JSON: {(corpo or '')[:120]!r}")
    palavras = palavras_da_resposta(dados)
    if not palavras:
        if isinstance(dados, dict) and (dados.get("text") or "").strip():
            raise ErroMistral("a resposta da Mistral tem texto mas não tem palavras com tempo (start e end por palavra)")
        return []
    for p in palavras:
        if p["end"] <= p["start"]:
            p["end"] = p["start"] + DURACAO_MINIMA_S        # palavra de duração zero: dá a ela a largura da grade
    return monotonizar(normalizar_numeros(palavras))
