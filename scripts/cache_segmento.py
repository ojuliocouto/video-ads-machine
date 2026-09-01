"""Chave de cache por segmento da footage (produzir_roteiro.py).

Modulo separado por dois motivos: (1) ser importavel sem puxar o resto do
produzir_roteiro.py (que executa o parser e o alinhamento assim que e importado,
por ser script e nao biblioteca); (2) a funcao de chave e pura (sem tocar
sistema de arquivos), entao o teste (test_paralelo_footage.py) cobre a logica
de hash sem precisar de video real nem ffmpeg.
"""
import hashlib
import json


def chave_segmento(tipo, narr, s, e, ee, base, layout, insert_cfg, fonte_stat, versao):
    """Chave sha256 (16 hex) que identifica um segmento renderizavel.

    tipo: b["type"] do bloco ("orig", "insert", "logo", "lettering", "lettering_logo").
    narr: texto da narracao daquele bloco (a legenda depende dele).
    s, e, ee: janela de tempo do bloco (ee ja inclui o handle de transicao).
    base: escala do jump cut (b["_base"]), decide o corte de tamanho da cabeca.
    layout: b.get("_layout") do plano de ritmo (split/cheio), muda o filtro inteiro.
    insert_cfg: dict de config do insert (arquivo, speed, start, crop, zoom, pip...)
        ou None para blocos sem insert. Vira JSON ordenado pra entrar na chave.
    fonte_stat: tupla (mtime, tamanho) do arquivo fonte (AVATAR ou insert file).
        Se a fonte mudar de conteudo sem mudar de nome, o cache antigo nao serve.
    versao: constante VERSAO_RENDER do produzir_roteiro.py; sobe sempre que o
        filtro de render mudar, pra invalidar cache de builds anteriores.
    """
    payload = {
        "tipo": tipo,
        "narr": narr,
        "s": round(float(s), 3),
        "e": round(float(e), 3),
        "ee": round(float(ee), 3),
        "base": base,
        "layout": layout,
        "insert_cfg": json.dumps(insert_cfg, sort_keys=True, default=str) if insert_cfg else None,
        "fonte_stat": list(fonte_stat),
        "versao": versao,
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]
