"""timeline/alinhar: UMA transcrição e UM alinhamento por avatar.

Antes desta unidade o mesmo avatar era transcrito três vezes num build (o overlay pelo `hyperframes
transcribe`, uma vez por formato, e a footage pelo parakeet) e cada motor casava o roteiro com a fala por um
algoritmo próprio. Os dois relógios derivavam: 1,07 s no fim de um anúncio de 2 min (defeito 20 do plano).

Agora:
  - a transcrição sai do `audio.transcrever` (W1.C), uma chamada por alinhamento, com cache pelo sha256 do
    CONTEÚDO do avatar: o mesmo avatar nunca é transcrito duas vezes, em build nenhum. É o perfil "alinhamento", o
    jeito que a footage sempre transcreveu (wav 16 kHz mono, parakeet SEM chunk, leitor da footage). Medido no
    fixture com o parakeet real (W3.X A2): o chunk de 15/3 s que a W3.A usava deslocava fronteira de bloco em até
    0,16 s, 16 de 52 palavras; mp4 x wav e leitor antigo x novo, zero. Com o perfil, a transcrição é a mesma;
  - o casamento roteiro x fala é o da FOOTAGE, o relógio que vale (`casar`, abaixo). A footage não tem mais
    cópia dele: `footage.blocos.alinhar_palavras` junta os tokens do parakeet e chama o `casar` daqui;
  - o resultado vai para um arquivo (`render/alinhamento.json` no projeto) cujo sha256 a timeline cita em
    `fontes.alinhamento_sha256`. É a prova de que footage e overlay usaram a mesma transcrição.

## O casamento (o algoritmo da footage, sem mudança)

Palavra do roteiro e palavra ouvida são comparadas sem caixa, acento nem pontuação, por `difflib` (sem
autojunk). Casou: herda o tempo da palavra ouvida. A grafia é SEMPRE a do roteiro. O que não casou:
  - a CAUDA (o ASR às vezes não ouve as últimas palavras: voz baixa, respiração) ancora no fim real do áudio,
    (duração - CAUDA_S, duração). Sem isso a interpolação ancorava na última palavra casada e cortava a fala
    real cerca de 1 s antes do fim;
  - no meio, ocupa o vão entre as vizinhas casadas; sem vão, dura SEM_PAR_S depois da anterior;
  - antes da primeira casada, dura SEM_PAR_S e encosta nela (é assim que nasce o a0 de um anúncio cuja
    primeira palavra o ASR errou);
  - nenhuma casada no roteiro inteiro: passo fixo de PASSO_SEM_PAR_S.

## O arquivo

    {"versao": 1, "avatar": <relativo à raiz>, "avatar_sha256", "duracao_audio_s",
     "transcricao": [{text, start, end}]   a fala como o ASR ouviu (bruta, depois do glossário),
     "palavras":    [{t, s, e}]            o roteiro, palavra a palavra, no relógio do áudio a 1x}

Sem caminho absoluto dentro: o sha não pode depender da máquina. Escrita atômica e determinística
(`gravar` devolve o sha256 dos bytes gravados).
"""
import difflib
import hashlib
import json
import os
import re
import subprocess
import unicodedata
from pathlib import Path

from audio import transcrever as _T

VERSAO = 1
SEM_PAR_S = 0.18          # duração de uma palavra sem par encostada na vizinha
CAUDA_S = 0.05            # a cauda sem par termina no fim real do áudio e começa isto antes
PASSO_SEM_PAR_S = 0.3     # nenhum par no roteiro inteiro: uma palavra a cada 0,3 s


class ErroAlinhamento(RuntimeError):
    """Falta insumo (avatar, transcritor) ou o arquivo de alinhamento não é o esperado. Uma mensagem só."""


def norm(w):
    """Palavra sem caixa, acento nem pontuação, para casar roteiro com a fala."""
    w = unicodedata.normalize("NFD", w.lower())
    return re.sub(r"[^\w]", "", "".join(c for c in w if unicodedata.category(c) != "Mn"))


def casar(palavras, narr_words, audio_dur):
    """`[(início, fim, palavra do roteiro)]`, uma por palavra da narração.

    `palavras` é a fala ouvida, `[(início, fim, texto)]` em ordem; `audio_dur` é a duração real do áudio.
    """
    pk_norm = [norm(c) for *_, c in palavras]
    sn = [norm(w) for w in narr_words]
    sm = difflib.SequenceMatcher(None, pk_norm, sn, autojunk=False)
    times = [None] * len(narr_words)
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            times[b + k] = (palavras[a + k][0], palavras[a + k][1])
    if times and times[-1] is None:
        times[-1] = (max(0.0, audio_dur - CAUDA_S), audio_dur)
    # interpola as palavras sem casamento (variações roteiro x voz) entre as vizinhas casadas
    last = None
    for i in range(len(times)):
        if times[i] is None:
            nxt = next((times[j] for j in range(i + 1, len(times)) if times[j]), None)
            if last and nxt and nxt[0] > last[1]:
                times[i] = (last[1], nxt[0])
            elif last:
                times[i] = (last[1], last[1] + SEM_PAR_S)
            elif nxt:
                times[i] = (max(0.0, nxt[0] - SEM_PAR_S), nxt[0])
            else:
                times[i] = (i * PASSO_SEM_PAR_S, i * PASSO_SEM_PAR_S + PASSO_SEM_PAR_S)
        last = times[i]
    return [(times[i][0], times[i][1], narr_words[i]) for i in range(len(narr_words))]


def palavras_do_asr(transcricao):
    """`[{text, start, end}]` do `audio.transcrever` -> `[(início, fim, texto)]` para o `casar`."""
    return [(float(p["start"]), float(p["end"]), str(p["text"])) for p in transcricao]


def duracao_do_audio(caminho):
    """Duração do arquivo (ffprobe), a mesma medida que a footage usava para ancorar a cauda."""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(caminho)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise ErroAlinhamento(f"o ffprobe não mediu a duração de {caminho}: {(r.stderr or '').strip()[-200:]}")


def sha256_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _relativo(caminho, raiz):
    """Caminho relativo à raiz quando ele mora dentro dela; senão, o absoluto (e a timeline recusa)."""
    caminho = Path(os.path.realpath(caminho))
    if raiz is not None:
        try:
            return caminho.relative_to(Path(os.path.realpath(raiz))).as_posix()
        except ValueError:
            pass
    return str(caminho)


def alinhar(avatar, narr_words, *, cache_dir, raiz=None, glossario=None, duracao=None):
    """O alinhamento do roteiro com a fala do `avatar` (dict do arquivo, ainda não gravado).

    Chama o `audio.transcrever` UMA vez (o cache pelo sha do avatar segura as seguintes) e o `casar`.
    `raiz` é a pasta do projeto: o caminho do avatar sai relativo a ela. `duracao` mede o áudio (padrão:
    ffprobe), injetável para teste.
    """
    avatar = Path(avatar)
    if not avatar.is_file():
        raise ErroAlinhamento(f"avatar não encontrado: {avatar}. Gere ou copie o avatar antes de alinhar.")
    duracao = duracao or duracao_do_audio
    try:
        transcricao = _T.transcrever(avatar, cache_dir=Path(cache_dir), glossario=glossario, perfil="alinhamento")
    except _T.SemTranscritor as e:
        raise ErroAlinhamento(str(e))
    dur = float(duracao(avatar))      # sem arredondar: a cauda sem par ancora neste número, como na footage
    casadas = casar(palavras_do_asr(transcricao), list(narr_words), dur)
    return {
        "versao": VERSAO,
        "avatar": _relativo(avatar, raiz),
        "avatar_sha256": sha256_arquivo(avatar),
        "duracao_audio_s": dur,
        "transcricao": [{"text": p["text"], "start": p["start"], "end": p["end"]} for p in transcricao],
        "palavras": [{"t": t, "s": s, "e": e} for s, e, t in casadas],
    }


def palavras(alinhamento):
    """`[(início, fim, palavra do roteiro)]` do alinhamento: o formato que a footage usa."""
    return [(p["s"], p["e"], p["t"]) for p in alinhamento["palavras"]]


def _bytes(alinhamento):
    return (json.dumps(alinhamento, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8")


def gravar(alinhamento, caminho):
    """Grava (temporário + rename) e devolve o sha256 dos bytes gravados."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    dados = _bytes(alinhamento)
    tmp = caminho.with_name(caminho.name + ".tmp")
    tmp.write_bytes(dados)
    os.replace(str(tmp), str(caminho))
    return hashlib.sha256(dados).hexdigest()


def ler(caminho, sha256=None):
    """O alinhamento gravado. Com `sha256`, confere que o arquivo é o citado (senão, outra transcrição)."""
    caminho = Path(caminho)
    try:
        dados = caminho.read_bytes()
    except OSError as e:
        raise ErroAlinhamento(f"alinhamento ilegível em {caminho}: {e}")
    if sha256 is not None and hashlib.sha256(dados).hexdigest() != sha256:
        raise ErroAlinhamento(
            f"o alinhamento em {caminho} não é o que a timeline cita (sha256 diferente): a fala foi transcrita "
            "ou alinhada de novo depois da timeline. Reconstrua a timeline (timeline/construir).")
    try:
        al = json.loads(dados.decode("utf-8"))
    except ValueError as e:
        raise ErroAlinhamento(f"alinhamento com JSON inválido em {caminho}: {e}")
    if not isinstance(al, dict) or al.get("versao") != VERSAO or not isinstance(al.get("palavras"), list):
        raise ErroAlinhamento(f"{caminho} não é um alinhamento da versão {VERSAO}")
    return al
