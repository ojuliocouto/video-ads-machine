"""O chip flutuante com a palavra-chave nos vãos longos de avatar.

DESLIGADO NA ORIGEM em 29/08/2026 (segunda ordem sobre o mesmo assunto: ao ver o chip "DEMORA" o
diretor perguntou se não tinha pedido para tirar esse tipo de coisa). O CSS já esconde nos dois
templates; aqui ele para de ser GERADO, para não ficar marcação morta esperando alguém religar sem
saber por que saiu. Motivo: pílula com pontinho fingindo status, e o texto só repetia em caixa alta
uma palavra que o apresentador tinha acabado de falar.

A lógica de achar os vãos continua intacta, caso um dia entre outra coisa nesses vãos que não seja
enfeite. Vão longo de avatar sem insert e sem lettering é trecho parado; o chip põe um elemento
chamativo com a PALAVRA-CHAVE da fala daquele instante. Data-driven do plano de ritmo.
"""

CHIP_LIGADO = False

# palavras compridas que não carregam conteúdo (o chip saía com "PRATICAMENTE")
MULETAS = {"porque", "enquanto", "tambem", "também", "depois",
           "agora", "ainda", "entao", "então", "quando", "nenhum",
           "nenhuma", "qualquer", "alguma", "mesmo", "mesma",
           "muita", "muito", "aquele", "aquela", "aquilo"}


def runs_de_avatar(plano_ritmo):
    """[(início, fim)] das sequências de planos que NÃO são insert (vãos de avatar)."""
    _runs = []
    _ra = None
    for _x in plano_ritmo:
        if _x["tipo"] != "insert":
            _ra = _x["s"] if _ra is None else _ra
            _rb = _x["e"]
        else:
            if _ra is not None:
                _runs.append((_ra, _rb))
            _ra = None
    if _ra is not None:
        _runs.append((_ra, _rb))
    return _runs


def calcular(plano_ritmo, groups, lett_windows, logo_s, ligado=None):
    """Os chips [{t, kw}] dos vãos de avatar. `ligado=None` lê CHIP_LIGADO na hora da chamada.

    VÃOS MAIORES PRIMEIRO (18/08/2026): com a ordem cronológica, o espaçamento bloqueava o chip
    justamente do maior vão (14 s de fala sem chip porque um vão menor 7,7 s antes já tinha levado o
    dele). Espaçamento mínimo 6 s, no máximo 4 chips, vão de 7 s ou mais, nunca antes de 5,5 s (dentro
    do hook), o lettering é evento e o chip espera a vez.
    """
    ligado = CHIP_LIGADO if ligado is None else ligado
    chips = []
    _runs = sorted(runs_de_avatar(plano_ritmo), key=lambda r: r[1] - r[0], reverse=True)
    for _ra, _rb in _runs:
        if not ligado or _rb - _ra < 7.0 or len(chips) >= 4:
            continue                       # vão curto já é dinâmico por natureza
        _tc = _ra + 1.2
        if _tc < 5.5:
            _tc = 5.5                      # nunca dentro do hook
        for _ls, _le in lett_windows:      # lettering já é evento: chip espera a vez
            if _ls - 0.4 < _tc < _le + 0.4:
                _tc = _le + 0.5
        if _tc > min(_rb - 2.8, logo_s - 3.2) or any(abs(_tc - c['t']) < 6.0 for c in chips):
            continue
        # palavra do chip: kw da fala no instante; senão a palavra mais longa
        _cands = [w for g in groups for w in g["words"]
                  if _tc - 0.5 <= float(w["start"]) <= _tc + 3.5]
        _kw = next((w["text"] for w in _cands if w.get("kw")), None)
        if not _kw:
            # palavra mais longa que NÃO seja muleta: advérbios em -mente e conectivos compridos
            # ganhavam sempre e o chip saía com "PRATICAMENTE", que não carrega conteúdo
            _limpa = [w["text"].strip(".,?!;:") for w in _cands]
            _limpa = [t for t in _limpa if len(t) >= 5
                      and not t.lower().endswith("mente")
                      and t.lower() not in MULETAS]
            _kw = max(_limpa, key=len) if _limpa else None
        if not _kw:
            continue
        chips.append({"t": round(_tc, 2), "kw": _kw.strip(".,?!;:").upper()})
    if chips:
        print(f"   [chips] {len(chips)}: " +
              ", ".join(f"{c['kw']}@{c['t']}s" for c in chips), flush=True)
    return chips


def html(chips):
    """O HTML dos chips, trilhas 58 em diante."""
    return "\n".join(
        f'<div class="chip clip" id="chip{k}" data-start="{c["t"]}" '
        f'data-duration="2.6" data-track-index="{58 + k}">'
        f'<span class="dot"></span>{c["kw"]}</div>'
        for k, c in enumerate(chips))
