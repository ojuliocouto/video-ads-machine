"""Testa a funcao pura de chave de cache por segmento (cache_segmento.py).

So cobre a chave: nao roda ffmpeg nem toca o produzir_roteiro.py (que executa
parser+alinhamento na importacao, por ser script). Verificacao de que a
paralelizacao do build inteiro nao quebrou nada e feita a parte, rodando um
build real (ver relatorio da tarefa).
"""
from cache_segmento import chave_segmento


def _args(**over):
    base = dict(
        tipo="orig", narr="ola mundo", s=1.0, e=3.0, ee=3.08,
        base=1.0, layout=None, insert_cfg=None,
        fonte_stat=(1000.0, 2048), versao="v1",
    )
    base.update(over)
    return base


def test_mesma_entrada_mesma_chave():
    a = chave_segmento(**_args())
    b = chave_segmento(**_args())
    assert a == b


def test_mudar_base_muda_chave():
    a = chave_segmento(**_args())
    b = chave_segmento(**_args(base=1.28))
    assert a != b


def test_mudar_mtime_muda_chave():
    a = chave_segmento(**_args())
    b = chave_segmento(**_args(fonte_stat=(1001.0, 2048)))
    assert a != b


def test_mudar_tamanho_muda_chave():
    a = chave_segmento(**_args())
    b = chave_segmento(**_args(fonte_stat=(1000.0, 4096)))
    assert a != b


def test_mudar_narr_muda_chave():
    a = chave_segmento(**_args())
    b = chave_segmento(**_args(narr="outra fala"))
    assert a != b


def test_mudar_layout_muda_chave():
    a = chave_segmento(**_args())
    b = chave_segmento(**_args(layout="cheio"))
    assert a != b


def test_mudar_insert_cfg_muda_chave():
    a = chave_segmento(**_args())
    b = chave_segmento(**_args(insert_cfg={"file": "x.mp4", "speed": 1.0}))
    c = chave_segmento(**_args(insert_cfg={"file": "x.mp4", "speed": 1.5}))
    assert a != b
    assert b != c


def test_mudar_versao_muda_chave():
    a = chave_segmento(**_args())
    b = chave_segmento(**_args(versao="v2"))
    assert a != b


def test_ordem_das_chaves_do_json_nao_importa():
    """insert_cfg com chaves em ordem diferente tem que dar a MESMA chave
    (json.dumps sort_keys=True), senao cache falso-negativo por reordenacao
    de dict em versoes diferentes do codigo."""
    a = chave_segmento(**_args(insert_cfg={"file": "x.mp4", "speed": 1.0, "zoom": 1.2}))
    b = chave_segmento(**_args(insert_cfg={"zoom": 1.2, "file": "x.mp4", "speed": 1.0}))
    assert a == b


def test_chave_tem_16_hex():
    a = chave_segmento(**_args())
    assert len(a) == 16
    int(a, 16)  # nao levanta ValueError
