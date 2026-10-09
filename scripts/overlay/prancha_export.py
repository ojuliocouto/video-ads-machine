"""A linha do tempo em dados para o diretor de arte (`prancha.json`) e as janelas de split de VERDADE
(`janelas_split.json`).

Tudo em tempo de ÁUDIO (1x): o arquivo entregue roda ACCEL mais rápido, então a prancha converte na
hora de rotular (ver `prancha_direcao.py`). A fala vai junto de cada bloco: quem reconstrói o plano de
ritmo a partir da prancha (som, medidor) precisa do mesmo critério de deixis que os motores usaram,
senão o plano deles diverge do renderizado.

UMA VERDADE SÓ SOBRE ONDE HÁ SPLIT (27/08/2026). O `ritmo.py` marca `layout` em TODA fatia de insert,
mas a footage só honra isso quando o config do insert tem `split: true`; sem a flag ela renderiza tela
cheia. Quem sabe disso é o overlay, que lê as duas coisas, e não o plano de ritmo cru. O gate de colisão
lia o plano cru e por isso acusava 14 colisões em trechos que a tela mostra como insert em tela cheia,
sem apresentador nenhum: falso positivo com a mesma cara de defeito real. Aqui saem as janelas de verdade.
"""
import json

ACCEL = 1.35    # aceleração do arquivo entregue em relação ao áudio do overlay (build_composite)


def montar_prancha(ad, look, total, hook_dur, cfg, cta_s, logo_s, blocks, spans, brolls, letts, groups,
                   vao):
    """O dicionário da prancha. `vao` é (maior vão sem texto, onde começa)."""
    _pior, _quando = vao
    return {
        "ad": ad, "look": look, "total": round(float(total), 2),
        "accel": ACCEL,
        "hook": {"fim": round(float(hook_dur), 2),
                 "texto": {k: v for k, v in (cfg.get("hook") or {}).items()}},
        "cta": {"inicio": cta_s, "logo": logo_s, "label": cfg.get("cta_label", "")},
        "blocos": [{"i": i, "tipo": blocks[i]["type"], "instr": blocks[i]["instr"],
                    "texto": blocks[i].get("narr", ""),
                    "s": round(float(a), 2), "e": round(float(b), 2),
                    "dur": round(float(b - a), 2)}
                   for i, (a, b) in enumerate(spans)],
        "inserts": [{"src": b["src"], "s": round(float(b["s"]), 2),
                     "d": round(float(b["d"]), 2), "label": b.get("label", "")}
                    for b in brolls],
        "letterings": [{"id": l["id"], "lead": l["lead"], "key": l["key"],
                        "s": float(l["start"]), "d": float(l["dur"]),
                        "split": bool(l.get("split")), "baixo": bool(l.get("baixo")),
                        "pilha": bool(l.get("linhas")),
                        "linhas": l.get("linhas") or []}
                       for l in letts],
        "legendas": [{"s": round(float(g["start"]), 2), "e": round(float(g["end"]), 2)}
                     for g in groups],
        "vao_sem_texto": {"maior": round(float(_pior), 2), "em": round(float(_quando), 2)},
    }


def gravar(out, prancha, janelas_split):
    """Escreve `prancha.json` e `janelas_split.json` em `out`."""
    (out / "prancha.json").write_text(json.dumps(prancha, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "janelas_split.json").write_text(json.dumps(
        {"segs": [{"s": a_, "e": b_, "layout": "split"} for a_, b_ in janelas_split]},
        ensure_ascii=False, indent=2), encoding="utf-8")
