"""A linha do tempo por bloco: spans contíguos e o plano de ritmo que o overlay usa.

Os spans são CONTÍGUOS: a fronteira entre dois blocos é a primeira palavra do bloco seguinte, e
nenhum bloco dura menos de 0,3 s. O plano de ritmo é o MESMO que a footage usa (`ritmo.py` é
determinístico de propósito): se um motor subdividir o bloco e o outro não, o lettering de um
trecho de avatar recebe tratamento de split e o texto vai parar no rosto.

Este é o módulo que a W3.A (relógio único) altera: hoje o overlay deriva os spans a partir da
própria transcrição, e a footage deriva os dela, e as duas não batem (deriva medida de 1,07 s no
fim de um anúncio de 2 min).
"""
import ritmo


def achar_insert_cfg(instr, inserts_map):
    """(chave, config) do insert cuja chave aparece na instrução do bloco; (None, None) se nenhum.

    A instrução é posta em minúsculas e a chave não: quem escreve a chave em minúscula acerta.
    """
    s = instr.lower()
    for k, v in inserts_map.items():
        if k in s:
            return k, v
    return None, None


def calcular_spans(blocks, words):
    """[(início, fim)] por bloco, contíguos.

    Bloco sem fala nasce no fim da palavra anterior (ou em 0.0 se for o primeiro). O último bloco
    vai até o fim da última palavra, e nunca dura menos de 0,3 s.
    """
    idx = 0
    starts = []
    for b in blocks:
        n = len(b["narr"].split())
        starts.append(words[idx]["start"] if n else (words[idx - 1]["end"] if idx else 0.0))
        idx += n
    bounds = [starts[0]]
    for s in starts[1:]:
        bounds.append(max(s, bounds[-1] + 0.3))
    bounds.append(max(words[-1]["end"], bounds[-1] + 0.3))
    return [(bounds[i], bounds[i + 1]) for i in range(len(blocks))]


def plano_de_ritmo(blocks, spans, inserts_map):
    """(plano, resumo) do ritmo.py para os blocos. Serve para saber em que instante a imagem está
    em insert e em que instante volta ao avatar: sem isso o texto é posicionado como se o bloco
    inteiro fosse insert.

    Cada entrada leva o tipo (insert ou orig), o recorte e o `dur_max` do insert, e a FALA do
    bloco: é por ela que o ritmo decide a deixis ("na tela", "isso aqui" trava o insert).
    """
    entradas = []
    for b, (s, e) in zip(blocks, spans):
        _k, c = achar_insert_cfg(b["instr"], inserts_map) if b["type"] == "insert" else (None, None)
        entradas.append({"tipo": "insert" if b["type"] == "insert" else "orig",
                         "s": s, "e": e,
                         "crop": (c or {}).get("crop"),
                         "dur_max": (c or {}).get("dur_max"),
                         "texto": b.get("narr", "")})
    plano = ritmo.plano_de_ritmo(entradas)
    res = ritmo.resumo(plano, spans[-1][1])
    print(f"   [ritmo] {len(plano)} planos | {res['cortes_min']:.1f} "
          f"cortes/min | plano medio {res['plano_medio']:.2f}s", flush=True)
    return plano, res
