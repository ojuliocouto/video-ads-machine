#!/usr/bin/env python3
"""Mensagem unica e clara quando falta o material do SEU anuncio (a pasta _local/).

O repo traz o motor e os gates. O que NAO vem nele, porque e do usuario e nunca e
versionado: configs, roteiros, mapas de insercao, logo, meta.json e a midia (avatar,
voz, inserts). Quando isso falta, o motor nao deve soltar traceback nem uma lista de
"faltam N arquivos": diz uma vez qual e a causa mais a montante e qual comando resolve.

Uso nos scripts:
    from material_local import exigir, checar_config
    exigir(caminho, "o roteiro do anuncio")      # sai com codigo 2 e a mensagem
    if not checar_config(ad, look, fmt): ...     # devolve False e imprime a mensagem
"""
import sys
from pathlib import Path

from caminhos import ESTADO, RAIZ

COMANDO_INIT = "python3 scripts/init_local.py"


def _rel(p):
    """Caminho curto pra mensagem: _local/configs/x.json em vez do absoluto."""
    p = Path(p)
    for base, nome in ((ESTADO, "_local"), (RAIZ, "")):
        try:
            r = p.relative_to(base)
            return f"{nome}/{r}".strip("/") if nome else str(r)
        except ValueError:
            continue
    return str(p)


def mensagem(caminho, o_que):
    """Texto da mensagem. Se o _local inteiro nao existe, a causa e essa, so ela."""
    if not Path(ESTADO).exists():
        causa = ("A pasta _local/ não existe: ela guarda o material do SEU "
                 "anúncio (configs, roteiros, mapas de inserção, logo, meta.json) e "
                 "não vem no repo.")
    else:
        causa = (f"{_rel(caminho)} não existe ({o_que}): esse é o material do SEU "
                 "anúncio e não vem no repo.")
    return (f"{causa}\n"
            f"  Crie a estrutura com exemplos:  {COMANDO_INIT}\n"
            "  Exemplo mínimo de roteiro e brief: veja demo/ "
            "(roteiro_demo.txt, brief.example.json) e a seção "
            "sobre o _local/ no README.md.")


def exigir(caminho, o_que="material do seu anúncio"):
    """Garante que `caminho` existe; senao imprime a mensagem e sai com codigo 2."""
    if Path(caminho).exists():
        return Path(caminho)
    print(mensagem(caminho, o_que), file=sys.stderr, flush=True)
    raise SystemExit(2)


def _ad_v2(ad):
    """Nome do anuncio como o motor usa nos arquivos: 25 -> ad25v2, jh13 -> jh13v2."""
    ad = str(ad)
    if ad.endswith("v2"):
        return ad
    return f"{'' if ad.startswith('jh') else 'ad'}{ad}v2"


def checar_material(ad, look, fmt="9x16"):
    """Confere, na ordem do pipeline, o material do anuncio em _local. Uma mensagem so.

    Ordem: config -> roteiro anotado (<ad>_leva.txt) -> mapa de insercoes. Para no
    primeiro que falta, porque o proximo so faz sentido depois dele.
    """
    if not checar_config(ad, look, fmt):
        return False
    from caminhos import INPUTS
    nome = _ad_v2(ad)
    for arq, o_que in ((f"{nome}_leva.txt", "o roteiro anotado deste anúncio"),
                       (f"{nome}_inserts.json", "o mapa de inserções deste anúncio")):
        if not (Path(INPUTS) / arq).exists():
            print(mensagem(Path(INPUTS) / arq, o_que), file=sys.stderr, flush=True)
            return False
    return True


def checar_config(ad, look, fmt="9x16"):
    """True se o config do (ad, look, fmt) existe em _local/configs; senao imprime e False."""
    from ads_v2_configs import LOOKS          # so dado: a geracao e protegida por __main__
    sufixo = {"9x16": "", "1x1": "_1x1"}.get(fmt, "")
    ad = _ad_v2(ad)
    cfg = Path(ESTADO) / "configs" / f"{ad}_{LOOKS.get(look, look)}{sufixo}.json"
    if cfg.exists():
        return True
    print(mensagem(cfg, "config deste anúncio e look"), file=sys.stderr, flush=True)
    return False
