#!/usr/bin/env python3
"""Quanto de fonte cada insert CONSOME, e quanto ele CONGELA quando a fonte acaba.

Nasceu de um achado do diretor de arte (18/08/2026) que a prancha nao pegava e o gate
tambem nao: `tpad=stop_mode=clone` no motor de footage clona o ultimo quadro quando o
arquivo acaba antes do bloco. Quatro inserts do jh13 congelavam, 3,68s de audio somados,
e nenhum quadro parado denunciava porque congelado e um quadro normal repetido.

Isso nao e defeito de olho, e de ARITMETICA:

    consome = dur_do_bloco * speed      (o motor le a fonte nessa velocidade)
    sobra   = duracao_da_fonte - start
    congela = max(0, consome - sobra)

Serve a dois donos: a prancha amostra um quadro no instante em que a fonte acaba, e o
gate de entrada recusa buildar com congelamento acima do limite.
"""
import json
import subprocess
import sys
from pathlib import Path

LIMITE_S = 0.20      # abaixo disso e arredondamento de quadro, nao defeito


def dur_fonte(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def analisar(ad, prancha=None):
    """Devolve uma linha por insert do ad. `prancha` e o prancha.json (pra pegar a
    duracao REAL de cada bloco); sem ele, usa o dur do proprio insert quando existir."""
    from caminhos import INPUTS as _IN
    ins_p = _IN / f"{ad}_inserts.json"
    cfgs = json.loads(ins_p.read_text())
    dur_por_src = {}
    if prancha:
        pr = json.loads(Path(prancha).read_text()) if not isinstance(prancha, dict) else prancha
        for b in pr.get("inserts", []):
            # o src vem como "broll01.mp4"; a chave que eu monto e "broll01"
            dur_por_src.setdefault(b["src"].rsplit(".", 1)[0], []).append((b["s"], b["d"]))
    linhas = []
    for i, (nome, cfg) in enumerate(cfgs.items()):
        src = Path(cfg["file"])
        sp = float(cfg.get("speed", 1.0) or 1.0)
        st = float(cfg.get("start", 0) or 0)
        fonte = dur_fonte(src)
        sobra = max(fonte - st, 0.0)
        # duracao do bloco: do prancha.json quando der, senao o dur_max declarado
        chave = f"broll{i + 1:02d}"
        blocos = dur_por_src.get(chave) or []
        dur_bloco = blocos[0][1] if blocos else float(cfg.get("dur_max") or 0.0)
        # `dur_max` CAPA o insert e devolve o resto do bloco pro avatar, entao o que
        # consome fonte e o menor dos dois. Sem isso o checador acusa congelamento onde
        # o cap ja resolveu: falso positivo que faria eu "consertar" o que estava certo.
        _cap = float(cfg.get("dur_max") or 0.0)
        if _cap and dur_bloco:
            dur_bloco = min(dur_bloco, _cap)
        elif _cap:
            dur_bloco = _cap
        inicio = blocos[0][0] if blocos else None
        consome = dur_bloco * sp
        congela = max(0.0, consome - sobra)
        linhas.append({
            "i": i, "chave": chave, "nome": nome, "arquivo": src.name,
            "fonte": round(fonte, 2), "start": st, "speed": sp,
            "sobra": round(sobra, 2), "dur_bloco": round(dur_bloco, 2),
            "consome": round(consome, 2), "congela": round(congela, 2),
            # instante do ANUNCIO em que a fonte acaba (pra prancha amostrar ali)
            "congela_em": (round(inicio + sobra / sp, 2)
                           if inicio is not None and congela > LIMITE_S else None),
        })
    return linhas


def imprimir(linhas):
    ruim = [l for l in linhas if l["congela"] > LIMITE_S]
    print("  insert                         fonte  start  speed   sobra  consome  CONGELA")
    for l in linhas:
        marca = "  <<<" if l["congela"] > LIMITE_S else ""
        print(f"  {l['chave']} {l['arquivo'][:22]:24s} {l['fonte']:6.2f} {l['start']:6.2f} "
              f"{l['speed']:6.2f} {l['sobra']:7.2f} {l['consome']:8.2f} "
              f"{l['congela']:7.2f}{marca}")
    if ruim:
        tot = sum(l["congela"] for l in ruim)
        print(f"  >> {len(ruim)} insert(s) congelam, {tot:.2f}s de audio somados")
    else:
        print("  >> nenhum insert pede mais fonte do que o arquivo tem")
    return ruim


if __name__ == "__main__":
    ad = sys.argv[1]
    if not ad.endswith("v2"):
        ad = ad + "v2"
    pr = sys.argv[2] if len(sys.argv) > 2 else None
    ruim = imprimir(analisar(ad, pr))
    sys.exit(1 if ruim else 0)
