"""A linha do tempo por bloco: spans contíguos e o plano de ritmo que o overlay usa.

Os spans são CONTÍGUOS: a fronteira entre dois blocos é a primeira palavra do bloco seguinte, e
nenhum bloco dura menos de 0,3 s. O plano de ritmo é o MESMO que a footage usa (`ritmo.py` é
determinístico de propósito): se um motor subdividir o bloco e o outro não, o lettering de um
trecho de avatar recebe tratamento de split e o texto vai parar no rosto.

W3.A (relógio único): com a timeline.json o overlay não deriva os spans nem o plano, LÊ os dois dela
(`da_timeline`, `plano_da_timeline`), e a footage lê os mesmos. Sem a timeline (caminho antigo) o
overlay deriva os spans da própria transcrição e a footage deriva os dela, e as duas não batiam
(deriva medida de 1,07 s no fim de um anúncio de 2 min).
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


def da_timeline(tl):
    """[(início, fim)] por bloco, lidos da timeline (os spans da footage)."""
    from timeline import construir as TC
    return TC.spans(tl)


def plano_da_timeline(tl, blocks, inserts_map):
    """(plano, resumo) LIDOS da timeline, no formato do ritmo.py: o mesmo plano que a footage usa."""
    from timeline import construir as TC
    plano = TC.plano_do_motor(tl, blocks, inserts_map, lambda m, instr: achar_insert_cfg(instr, m)[1])
    res = ritmo.resumo(plano, tl["duracao_s"])
    print(f"   [ritmo] {len(plano)} planos da timeline | {res['cortes_min']:.1f} "
          f"cortes/min | plano medio {res['plano_medio']:.2f}s", flush=True)
    return plano, res


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
                         "layout_padrao": (c or {}).get("layout_padrao"),
                         "texto": b.get("narr", "")})
    plano = ritmo.plano_de_ritmo(entradas)
    res = ritmo.resumo(plano, spans[-1][1])
    print(f"   [ritmo] {len(plano)} planos | {res['cortes_min']:.1f} "
          f"cortes/min | plano medio {res['plano_medio']:.2f}s", flush=True)
    return plano, res
