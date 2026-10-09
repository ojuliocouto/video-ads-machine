"""Exportação do tempo da footage: o plano de ritmo e o `timing.json`.

Os dois arquivos são o contrato com o resto da fábrica:

  - `<saida>_ritmo.json` guarda o plano de ritmo (`segs`) e o total. O `gen_ad_v2` lê o MESMO plano
    (o "relógio da footage") e o mixador de SFX coloca whoosh e riser em cima dos cortes REAIS: recalcular
    o plano fora daqui dessincroniza o overlay, a footage e o som.
  - `timing.json` guarda `a0` (início do 1º span no avatar), o total, o `xf`, o avatar, as janelas dos
    inserts em tempo de avatar e as janelas de lettering queimado. Mapeia tempo de reel `t` para tempo
    de avatar `a0 + t`, que é como o círculo do apresentador e a legenda se alinham.

O formato é byte a byte o do motor antigo (a paridade compara o texto). `letterings` fica sempre vazio:
o lettering agora é do overlay e nenhum bloco é queimado na footage.
"""
import json


def escrever_ritmo(caminho, plano, total):
    with open(caminho, "w", encoding="utf-8") as fh:
        json.dump({"segs": plano, "total": total}, fh)
    return caminho


def dados_do_timing(a0, total, xf, avatar, spans, blocks, letterings=()):
    inserts = [{"s": spans[i][0], "e": spans[i][1]} for i, b in enumerate(blocks) if b["type"] == "insert"]
    lets = [{"s": a, "e": b} for (a, b) in letterings]
    return {"a0": a0, "total": total, "xf": xf, "avatar": avatar, "inserts": inserts, "letterings": lets}


def escrever_timing(caminho, a0, total, xf, avatar, spans, blocks, letterings=()):
    with open(caminho, "w", encoding="utf-8") as fh:
        json.dump(dados_do_timing(a0, total, xf, avatar, spans, blocks, letterings), fh)
    return caminho
