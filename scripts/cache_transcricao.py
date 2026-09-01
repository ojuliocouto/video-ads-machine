#!/usr/bin/env python3
"""Cache da transcricao do avatar (parakeet-mlx), entre builds diferentes.

## Por que existe

O `gen_ad_v2.py` ja evitava retranscrever DENTRO do mesmo out_dir (checa se
`transcript.json` ja existe ali). O problema e que cada build normalmente cai
num out_dir novo (render-*), entao a checagem local nunca acerta entre builds
do MESMO anuncio. Resultado medido em 31/08/2026: 8 builds seguidos do mesmo
ad, com o MESMO avatar.mp4, geraram 8 transcricoes identicas via parakeet, a
~2,5 min cada, dentro de um build de 20 min. Essa e a parte mais facil de
cortar: a transcricao so depende do AUDIO do avatar, nao do out_dir.

Este modulo guarda o resultado da transcricao numa pasta de cache global,
indexado por uma chave derivada do conteudo do proprio arquivo de audio/video
de origem (nao do caminho). Assim, dois out_dirs diferentes com o mesmo
avatar.mp4 reaproveitam o mesmo transcript.json sem rodar o parakeet de novo.

## Contrato

  chave(audio_path)                      -> string hex de 16 caracteres
  obter(audio_path, pasta_cache)         -> Path do json em cache, ou None
  guardar(audio_path, json_origem, ...)  -> Path do json salvo no cache
"""
import hashlib
import shutil
from pathlib import Path

# Le so os primeiros 8 MB do arquivo pra chave: o avatar.mp4 costuma ter
# dezenas de MB e o motivo do cache e justamente evitar trabalho pesado, entao
# a propria checagem da chave nao pode virar o novo gargalo. 8 MB + tamanho +
# mtime e suficiente pra distinguir avatares diferentes na pratica: um
# reencode ou reacelaracao muda os bytes iniciais (headers/moov) quase sempre,
# e tamanho/mtime pegam o resto dos casos.
_LIMITE_LEITURA = 8 * 1024 * 1024


def chave(audio_path):
    """Chave curta (16 hex) derivada do conteudo + tamanho + mtime do arquivo.

    Nao usa o caminho: dois out_dirs diferentes com o mesmo avatar.mp4 (mesmo
    conteudo) tem que bater na mesma chave pra o cache funcionar entre builds.
    """
    p = Path(audio_path)
    st = p.stat()
    h = hashlib.sha256()
    with open(p, "rb") as f:
        h.update(f.read(_LIMITE_LEITURA))
    h.update(str(st.st_size).encode())
    h.update(str(st.st_mtime_ns).encode())
    return h.hexdigest()[:16]


def obter(audio_path, pasta_cache):
    """Caminho do json em cache pra este audio, ou None se nunca foi guardado."""
    destino = Path(pasta_cache) / f"{chave(audio_path)}.json"
    return destino if destino.exists() else None


def guardar(audio_path, json_origem, pasta_cache):
    """Copia o json de transcricao ja gerado pro cache, indexado pela chave do audio.

    Devolve o caminho salvo no cache. Chamar so DEPOIS de transcrever de fato:
    este modulo nunca chama o parakeet, so guarda/recupera o resultado.
    """
    pasta_cache = Path(pasta_cache)
    pasta_cache.mkdir(parents=True, exist_ok=True)
    destino = pasta_cache / f"{chave(audio_path)}.json"
    shutil.copy(Path(json_origem), destino)
    return destino
