"""Backend Groq (whisper-large-v3-turbo): nuvem, rápido, pago por uso.

Regras medidas que este cliente cumpre:
  - `User-Agent` de navegador é obrigatório: sem ele a Cloudflare da Groq devolve 403
    (`error code: 1010`).
  - `language=pt` e `prompt` com o vocabulário do glossário.
  - timestamp_granularities[]=word SOZINHO: pedir word junto com segment degrada o
    word-level (84 palavras caem para 60 num texto de 88).
  - O corpo multipart NUNCA é montado à mão: montado em Python ele devolveu 200 ecoando o
    prompt, e isso parece "áudio vazio". Quem monta é o `curl` (`form-string` para texto,
    `form` para o arquivo). A chave vai por stdin (`-K -`), então não aparece em `ps`.
    Uma resposta que devolve o texto do prompt é tratada como requisição malformada.
  - Arquivo vai comprimido: mp3 mono 16 kHz 32 kbps (32 min viram ~7,5 MB; limite 25 MB).
  - No máximo UM retry, e só em 429. A conta gratuita limita áudio por HORA: quando a
    mensagem pede mais de 2 minutos de espera, não adianta martelar, o erro avisa quanto
    esperar.

A chave vem de GROQ_API_KEY (ambiente), nunca de arquivo do repo.
"""
import json
import re
import subprocess
import time
from pathlib import Path

from ..transcrever import monotonizar

NOME = "groq"
URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODELO = "whisper-large-v3-turbo"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
LIMITE_BYTES = 25 * 1024 * 1024
ESPERA_PADRAO_S = 20.0
ESPERA_MAX_S = 120.0
TIMEOUT_S = 300


class ErroGroq(RuntimeError):
    pass


def _chave(amb):
    return (amb.env.get("GROQ_API_KEY") or "").strip()


def disponivel(amb):
    return bool(_chave(amb))


def _espera_do_429(corpo):
    """Segundos pedidos na mensagem ('try again in 3s', '10m12s'); padrão se não houver."""
    m = re.search(r"try again in\s+(?:(\d+)m)?\s*([\d.]+)?s?", corpo or "")
    if m and (m.group(1) or m.group(2)):
        return int(m.group(1) or 0) * 60 + float(m.group(2) or 0)
    return ESPERA_PADRAO_S


def _escapar(valor):
    """Aspas duplas de arquivo de configuração do curl: escapa \\, \" e quebra de linha."""
    return (str(valor).replace("\\", "\\\\").replace('"', '\\"')
            .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t"))


def config_curl(req):
    """Config do curl (lida de stdin com `-K -`): chave e texto longo fora do argv."""
    linhas = [f'url = "{_escapar(req["url"])}"', 'request = "POST"', "silent", "show-error",
              f"max-time = {TIMEOUT_S}", 'write-out = "\\n%{http_code}"']
    linhas += [f'header = "{_escapar(k)}: {_escapar(v)}"' for k, v in req["headers"].items()]
    linhas += [f'form-string = "{_escapar(k)}={_escapar(v)}"' for k, v in req["campos"]]
    linhas.append(f'form = "file=@{_escapar(req["arquivo"])}"')
    return "\n".join(linhas) + "\n"


def _transporte_curl(req):
    r = subprocess.run(["curl", "-K", "-"], input=config_curl(req), capture_output=True,
                       text=True)
    if r.returncode != 0:
        raise ErroGroq(f"curl falhou ({r.returncode}): {r.stderr.strip()[-200:]}")
    corpo, _, codigo = r.stdout.rpartition("\n")
    try:
        return int(codigo.strip()), corpo
    except ValueError:
        raise ErroGroq("resposta do curl sem código HTTP")


def _comprimir(audio, destino):
    destino.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", str(audio), "-vn",
                        "-ac", "1", "-ar", "16000", "-b:a", "32k", str(destino)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not destino.is_file():
        raise ErroGroq(f"não consegui converter {audio} para mp3: {r.stderr.strip()[-200:]}")
    return destino


def _normal(texto):
    return re.sub(r"\W+", " ", texto or "").strip().casefold()


def transcrever(audio, *, amb, workdir, prompt="", idioma="pt", transporte=None, dormir=None):
    chave = _chave(amb)
    if not chave:
        raise ErroGroq("GROQ_API_KEY não definida: exporte a chave da Groq para usar este backend")
    mp3 = _comprimir(Path(audio), Path(workdir) / "groq.mp3")
    if mp3.stat().st_size > LIMITE_BYTES:
        raise ErroGroq(f"arquivo de {mp3.stat().st_size / 1e6:.1f} MB passa do limite de 25 MB "
                       "da Groq: corte o áudio em pedaços de 20 minutos")
    req = {
        "url": URL,
        "headers": {"Authorization": f"Bearer {chave}", "User-Agent": USER_AGENT},
        "campos": [("model", MODELO), ("language", idioma), ("response_format", "verbose_json"),
                   ("temperature", "0"), ("prompt", prompt),
                   ("timestamp_granularities[]", "word")],
        "arquivo": str(mp3),
    }
    enviar = transporte or _transporte_curl
    dormir = dormir or time.sleep

    status, corpo = enviar(req)
    if status == 429:
        espera = _espera_do_429(corpo)
        if espera > ESPERA_MAX_S:
            raise ErroGroq(f"429 da Groq: limite de áudio por hora; tente de novo em "
                           f"{int(espera // 60)}m{int(espera % 60)}s")
        dormir(espera)
        status, corpo = enviar(req)
    if status != 200:
        dica = " (User-Agent de navegador é obrigatório)" if status == 403 else ""
        raise ErroGroq(f"Groq respondeu {status}{dica}: {(corpo or '').strip()[:200]}")

    try:
        dados = json.loads(corpo)
    except ValueError:
        raise ErroGroq(f"a resposta da Groq não é JSON: {(corpo or '')[:120]!r}")
    palavras = dados.get("words")
    texto = dados.get("text") or ""
    if not palavras:
        if prompt and _normal(texto) and _normal(texto) == _normal(prompt):
            raise ErroGroq("a Groq devolveu o próprio prompt como texto: requisição malformada, "
                           "não áudio vazio")
        if texto.strip():
            raise ErroGroq("a resposta da Groq tem texto mas não tem words (tempo por palavra)")
        return []
    return monotonizar({"text": w["word"], "start": w["start"], "end": w["end"]}
                       for w in palavras)
