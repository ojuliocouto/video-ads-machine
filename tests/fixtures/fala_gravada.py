"""Lê as falas GRAVADAS dos goldens (JSON de sentenças e tokens) como palavras com tempo.

Os goldens do alinhamento (`tests/footage/test_blocos.py::GOLDEN_ALINHAR`) guardam a fala de um avatar real no formato
de sentenças com tokens: token com espaço na frente abre palavra nova, sem espaço continua a anterior ("Ag" + "ora").
O motor de hoje recebe palavras prontas do transcritor; aqui o teste junta os tokens do golden do mesmo jeito que a
footage antiga juntava, para provar que o `casar` não mudou.
"""


def palavras_dos_tokens(dados):
    """`[(início, fim, texto)]` dos tokens do JSON gravado, em qualquer profundidade e em ordem de tempo."""
    cru = []

    def pegar(o):
        if isinstance(o, dict):
            if "tokens" in o and isinstance(o["tokens"], list):
                for t in o["tokens"]:
                    cru.append((float(t["start"]), float(t["end"]), t.get("text", "")))
            for v in o.values():
                pegar(v)
        elif isinstance(o, list):
            for v in o:
                pegar(v)

    pegar(dados)
    cru.sort()
    palavras = []
    for s, e, txt in cru:
        nova = txt.startswith(" ") or not palavras
        c = txt.strip()
        if not c:
            continue
        if nova:
            palavras.append([s, e, c])
        else:
            palavras[-1][1] = e
            palavras[-1][2] += c
    return [(s, e, c) for s, e, c in palavras]
