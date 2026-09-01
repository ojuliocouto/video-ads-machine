#!/usr/bin/env python3
"""Cache do render de overlay (passo [3/6] do build_composite).

O render do overlay em MOV com alpha (hyperframes render, ~3 min) so depende
do HTML final gerado no passo [2/6] (index_overlay.html): ele ja incorpora
roteiro, transcricao, config, template e ritmo. Se esse HTML nao mudou byte a
byte desde o ultimo build do mesmo ad/look/fmt, o MOV tambem nao muda, e
renderizar de novo e trabalho jogado fora.

Conferido em 31/08/2026: o index_overlay.html gerado pelo pipeline nao carrega
timestamp de build, id aleatorio nem caminho absoluto (so tem UM comentario
mencionando "timestamp", que se refere ao instante da FALA no roteiro, nao ao
momento em que o build rodou). Por isso a assinatura pode usar o arquivo como
esta, sem normalizar nada.
"""
import hashlib
from pathlib import Path


def assinatura(caminhos) -> str:
    """sha256 (hex, 16 chars) do conteudo dos arquivos em `caminhos`, concatenado
    na ordem dada. Um arquivo ausente conta como bytes vazios (nao quebra)."""
    h = hashlib.sha256()
    for c in caminhos:
        p = Path(c)
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def reaproveitavel(html_overlay, mov_existente, arquivo_assinatura) -> bool:
    """True se da pra pular o render [3/6] e usar `mov_existente` de novo.

    Exige: (1) `arquivo_assinatura` existir com o mesmo valor que a assinatura
    atual de `html_overlay`, e (2) `mov_existente` existir e ter tamanho > 0.
    """
    ass_path = Path(arquivo_assinatura)
    if not ass_path.exists():
        return False
    mov_path = Path(mov_existente)
    if not mov_path.exists() or mov_path.stat().st_size <= 0:
        return False
    atual = assinatura([html_overlay])
    guardada = ass_path.read_text().strip()
    return atual == guardada
