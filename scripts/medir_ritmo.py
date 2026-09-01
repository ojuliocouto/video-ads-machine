#!/usr/bin/env python3
"""Ritmo de corte: um so ponto de verdade pros dois lados da comparacao.

Existe porque "dinamico" virou opiniao. O Julio mandou tres referencias e a Jheni disse
que o anuncio "poderia ser mais acelerado"; sem numero, cada rodada era palpite. Medido
com o MESMO metodo nos dois lados (deteccao de cena, limiar 0,30), em 18/08/2026:

    ref1 Da0WA9pAtDv  27,8 cortes/min   plano medio 2,16s
    ref2 DbBFmwMgJwn  18,9              3,17s
    ref3 DXRwBdlgNLj  19,5              3,08s
    AD13 nosso         4,7             12,80s
    AD14 nosso         7,6              7,91s

O alvo sai dessas referencias, nao de mim. As fixtures vivem em refs/vaibhav/ e o teste
`test_medir_ritmo.py` confere que o medidor concorda com elas: se ele nao pontuar as tres
entre 18 e 28 cortes/min, o errado e o medidor.

ARMADILHA CONHECIDA: `refs/sobral/ref_hook.mp4` tambem e referencia da leva, mandada pela
Jheni, mas de HOOK. Ela tem 2,1 cortes/min. Medir dinamica por ela leva a conclusao
oposta. O teste cobre isso.

Uso:
    python3 medir_ritmo.py <arquivo.mp4> [...]     mede e imprime
    python3 medir_ritmo.py --prancha <prancha.json>  estima ANTES do render
"""
import json
import re
import subprocess
import sys
from pathlib import Path

LIMIAR_CENA = 0.30      # o mesmo dos dois lados; mudar aqui invalida a comparacao
# PISO. LIMITACAO CONHECIDA (27/08/2026): ele NAO da pra calibrar contra a referencia,
# porque os dois lados nao usam o mesmo caminho e nao ha como usar. Os nossos ads sao
# medidos por interseccao plano x imagem (unico jeito de excluir o churn da legenda
# karaoke, que sozinho faz o jh16 pontuar 47/min); a referencia nao tem plano nosso.
# Entao a calibragem sai do unico dado humano que existe: os ads que o Julio e a Jheni
# chamaram de lentos dao 15,1 e 15,3 por este caminho. O piso fica logo acima deles.
# A margem e FINA de proposito e o estrategista apontou isso: um ad que passe raspando
# (o jh13 passou com 16,6, ou seja um corte de folga em 90s) nao esta dinamico, esta no
# limite. Com mais ads julgados por gente, este numero deve subir.
MIN_CORTES_MIN = 16.0
PLANO_LONGO_S = 6.0     # a partir daqui o plano conta como "parado"
# TETO DE TEMPO PARADO, nao de plano isolado. A primeira versao reprovava por "maior
# plano acima de 6s" e reprovava a PROPRIA referencia: a ref1 segura um plano de 13,2s
# e mesmo assim faz 27,8 cortes/min. Gate mais duro que a referencia reprovaria uma peca
# indistinguivel dela. Medido: refs 16,0% / 22,4% / 31,2% do tempo em plano longo; nossos
# ads 86,8% a 93,5%. O teto de 40% separa sem encostar em nenhum dos dois lados.
MAX_CORTES_MIN = 32.0   # teto: a referencia mais rapida faz 27,8. Gate que aprova 40
                        # aprovaria uma peca mais picotada que a propria referencia, e o
                        # Julio ja reclamou de insert "saindo da tela MUITO rapido".
MAX_FRAC_LENTA = 0.40
MAX_PLANO_S = 14.0      # teto absoluto generoso: a pior referencia segura 13,2s


def _dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def cortes_de(p):
    """Instantes de corte detectados no arquivo, em segundos.

    CEGO EM MATERIAL ESCURO. `scene` compara diferenca de pixel, entao um corte entre
    dois quadros escuros nao registra. Serve pra material de terceiro (referencia), onde
    nao existe plano; para os NOSSOS ads use medir_do_plano(), que e exato.
    """
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(p), "-filter_complex",
         f"select='gt(scene,{LIMIAR_CENA})',metadata=print:file=-", "-an", "-f", "null", "-"],
        capture_output=True, text=True)
    return [float(m) for m in re.findall(r"pts_time:([0-9.]+)", r.stdout + r.stderr)]


def cortes_confirmados(video, plano_json, accel=1.35, limiar=0.62, fps=8, tol=0.45, a0=0.0):
    """Cortes que o plano PEDIU e que a imagem de fato entrega.

    Nasceu de duas medicoes que se contradiziam no mesmo arquivo (27/08/2026):

      `cortes_de` disse 31 cortes, 20,6/min      -> o diretor de arte mostrou na mao que
                                                    10 deles eram o fundo desfocado de UM
                                                    insert piscando em 4,4s
      `cortes_de` disse 15 cortes, 10,0/min      -> depois de congelar o fundo, o mesmo
                                                    detector parou de ver corte que existe:
                                                    `orig -> cheio` troca 100% do conteudo
                                                    e pontuou 0,18 contra limiar 0,30

    As duas falhas tem a MESMA causa: `scene` compara diferenca ABSOLUTA de pixel, entao
    confunde mudanca de brilho com mudanca de conteudo. Num anuncio escuro de ponta a
    ponta ele sub-conta; num fundo que pisca ele super-conta. O proprio modulo ja avisava
    ("CEGO EM MATERIAL ESCURO"), mas o gate chamava esse caminho mesmo assim.

    Aqui a conta cruza as duas fontes que temos e que sao independentes:
      1. o PLANO diz onde nos mandamos cortar (nao adivinha, nos escrevemos)
      2. a IMAGEM diz se aquele corte mudou alguma coisa, medida com cada quadro
         normalizado (media zero, desvio um), o que tira o brilho da conta

    Um corte so conta se as duas concordarem. Isso derruba de uma vez os tres erros:
    piscada de fundo nao esta no plano; mudanca de pagina dentro de uma gravacao continua
    nao esta no plano; e punch de avatar esta no plano mas nao muda a imagem.

    Validado contra as referencias do Julio, com a metrica normalizada: ref1 25,5/min,
    ref2 19,8, ref3 23,6 (todas na faixa 18 a 28 que o ffmpeg tambem dava) e a ref de
    HOOK do Sobral em 1,4/min, que e o caso que nao pode pontuar alto.
    """
    import numpy as np
    LARG, ALT = 64, 114
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video),
         "-vf", f"fps={fps},scale={LARG}:{ALT},format=gray", "-f", "rawvideo", "-"],
        capture_output=True).stdout
    n = len(out) // (LARG * ALT)
    if n < 2:
        return []
    f = np.frombuffer(out[:n * LARG * ALT], dtype=np.uint8).reshape(n, ALT * LARG)
    f = f.astype(np.float32)
    f = (f - f.mean(axis=1, keepdims=True)) / (f.std(axis=1, keepdims=True) + 1e-6)
    d = np.abs(f[1:] - f[:-1]).mean(axis=1)
    vistos = [(i + 1) / fps for i in np.where(d > limiar)[0]]
    if plano_json is None:
        # SEM PLANO (referencia de terceiro): so a imagem. Este e o caminho que TEM que
        # ser usado nos dois lados quando o numero vai ser COMPARADO com a referencia.
        return vistos
    # O `a0` FALTAVA AQUI TAMBEM (27/08/2026). O composite aplica `setpts=PTS-a0/TB`
    # na footage: plano = entregue*accel + a0, e a volta e (plano-a0)/accel. Sem
    # subtrair, cada alvo do plano fica adiantado (com a0=0,24 e accel=1,35, 0,178s,
    # que come 40% da tolerancia de 0,45s). E o MESMO esquecimento que ja tinha
    # corrigido no gate de colisao, e ficou de fora daqui: neste jh13 nao mudou o
    # resultado (27 casados nos dois jeitos, o estrategista testou e confirmou), mas o
    # erro fica LATENTE pra qualquer ad com a0 maior ou tolerancia mais apertada.
    segs = json.loads(Path(plano_json).read_text()).get("segs", [])
    pedidos = sorted({round((x["s"] - a0) / accel, 2) for x in segs if x["s"] > 0.5})
    return [t for t in pedidos if any(abs(t - v) <= tol for v in vistos)]


def _planos(cortes, dur):
    """Duracao de cada plano, a partir dos instantes de corte."""
    marcos = [0.0] + sorted(cortes) + [dur]
    return [b - a for a, b in zip(marcos, marcos[1:]) if b > a]


def medir(p, plano=None, accel=1.35, a0=0.0):
    """Mede ritmo. O numero que VALE no gate sai da mesma metrica dos dois lados.

    A ASSIMETRIA E REAL E FICA (27/08/2026). O estrategista apontou, com razao, que o
    nosso ad era medido por interseccao (plano x imagem) e a referencia so por deteccao,
    e que interseccao so encurta: pela mesma regua normalizada davam 24,0 contra 27,4 da
    referencia, ou seja paridade, e nao os 16,6 contra 25,5 que eu tinha reportado.
    O docstring de abertura promete "o MESMO metodo nos dois lados", e a objecao dele
    bate nessa promessa.

    Testei a simetria e ela produz numero absurdo no nosso material:

        ref mais rapida do Julio ......... 30,1/min
        jh16, que o Julio achou LENTO .... 47,1/min
        jh15, LENTO ...................... 34,1/min
        jh14, LENTO ...................... 31,0/min

    A causa: a nossa legenda troca 2 a 3 palavras GRANDES por segundo, e quadro
    normalizado le cada troca dessas como mudanca de estrutura. A referencia nao tem esse
    churn de texto na mesma escala, entao o mesmo detector infla so o nosso lado. Trocar
    uma assimetria por outra maior nao e simetria.

    Entao `cortes_min` continua vindo da interseccao pros NOSSOS ads: o corte tem que ser
    pedido pelo plano e visto na imagem, o que exclui churn de legenda por construcao.
    O numero da regua simetrica vai junto em `cortes_so_imagem`, pra assimetria ficar
    VISIVEL no relatorio em vez de escondida, e o piso segue calibrado contra a
    referencia medida do jeito dela.
    """
    p = Path(p)
    dur = _dur(p)
    cortes = cortes_confirmados(p, plano, accel, a0=a0) if plano else cortes_confirmados(p, None)
    # o numero da regua simetrica fica visivel do lado, pra assimetria nao ficar escondida
    so_imagem = cortes_confirmados(p, None) if plano else cortes
    planos = _planos(cortes, dur)
    lentos = [x for x in planos if x > PLANO_LONGO_S]
    return {
        "arquivo": p.name,
        "frac_lenta": round(sum(lentos) / dur, 4) if dur else 0.0,
        "planos_longos": len(lentos),
        "dur": round(dur, 2),
        "cortes": len(cortes),
        "cortes_min": round(len(cortes) / (dur / 60), 2) if dur else 0.0,
        "plano_medio": round(dur / max(len(cortes), 1), 2),
        "maior_plano": round(max(planos), 2) if planos else round(dur, 2),
        "planos": [round(x, 2) for x in planos],
        "instantes": [round(x, 2) for x in sorted(cortes)],
        # diagnostico: dos cortes que o plano pediu, quantos a imagem entregou
        "cortes_so_imagem": len(so_imagem),
        "so_imagem_min": round(len(so_imagem) / (dur / 60), 2) if dur else 0.0,
    }


def medir_prancha(caminho):
    """Estimativa ANTES do render, a partir dos blocos do prancha.json.

    E um PISO, nao a medida final: conta so corte editorial (troca de bloco) e ignora
    tanto o corte interno de asset pre-concatenado quanto o fato de que crossfade longo
    nao le como corte. Serve pra reprovar cedo, de graca, antes de 20 minutos de render.
    """
    pr = json.loads(Path(caminho).read_text())
    accel = pr.get("accel", 1.35)
    dur = pr["total"] / accel
    planos = [b["dur"] / accel for b in pr["blocos"]]
    n = max(len(planos) - 1, 0)
    lentos = [x for x in planos if x > PLANO_LONGO_S]
    return {
        "arquivo": f"{pr['ad']} (prancha)",
        "frac_lenta": round(sum(lentos) / dur, 4) if dur else 0.0,
        "planos_longos": len(lentos),
        "dur": round(dur, 2),
        "cortes": n,
        "cortes_min": round(n / (dur / 60), 2) if dur else 0.0,
        "plano_medio": round(dur / max(n, 1), 2),
        "maior_plano": round(max(planos), 2) if planos else 0.0,
        "planos": [round(x, 2) for x in planos],
        "instantes": [],
    }


def medir_do_plano(ad, prancha=None):
    """Ritmo EXATO dos nossos ads, a partir do plano que o ritmo.py produziu.

    Nos controlamos onde cortamos, entao nao ha por que adivinhar por deteccao. Esta e a
    medida que vale no gate; `medir()` fica como referencia cruzada.
    """
    import sys as _sys
    # (migracao 26/08/2026) codigo agora vizinho; import direto resolve
    import ritmo as _R
    from caminhos import V2L as L
    if prancha is None:
        cand = sorted(L.glob(f"render-{ad}-*-ovl/prancha.json"),
                      key=lambda x: x.stat().st_mtime)
        if not cand:
            cand = sorted((L / "prancha" / ad).glob("prancha.json"))
        if not cand:
            raise FileNotFoundError(f"sem prancha.json para {ad}")
        prancha = cand[-1]
    pr = json.loads(Path(prancha).read_text())
    ac = pr.get("accel", 1.35)
    from caminhos import INPUTS as _IN
    ins = json.loads((_IN /
                      f"{ad}_inserts.json").read_text())
    vals = list(ins.values())
    n, blocos = 0, []
    for b in pr["blocos"]:
        cfg = {}
        if b["tipo"] == "insert":
            cfg = vals[n] if n < len(vals) else {}
            n += 1
        blocos.append({"tipo": "insert" if b["tipo"] == "insert" else "orig",
                       "s": b["s"], "e": b["e"],
                       "crop": cfg.get("crop"), "dur_max": cfg.get("dur_max"),
                       "texto": b.get("texto", "")})
    segs = _R.plano_de_ritmo(blocos)
    dur = pr["total"] / ac
    planos = [(x["e"] - x["s"]) / ac for x in segs]
    lentos = [x for x in planos if x > PLANO_LONGO_S]
    return {
        "arquivo": f"{ad} (plano)",
        "dur": round(dur, 2),
        "cortes": len(segs) - 1,
        "cortes_min": round((len(segs) - 1) / (dur / 60), 2) if dur else 0.0,
        "plano_medio": round(dur / max(len(segs), 1), 2),
        "maior_plano": round(max(planos), 2) if planos else 0.0,
        "frac_lenta": round(sum(lentos) / dur, 4) if dur else 0.0,
        "planos_longos": len(lentos),
        "planos": [round(x, 2) for x in planos],
        "instantes": [],
    }


def aprova(m):
    """Devolve (ok, motivos). Reprovar sem dizer o motivo nao serve pra nada."""
    motivos = []
    if m["cortes_min"] < MIN_CORTES_MIN:
        motivos.append(f"ritmo lento: {m['cortes_min']:.1f} cortes/min "
                       f"(minimo {MIN_CORTES_MIN:.0f}; a referencia faz 19 a 28)")
    if m["cortes_min"] > MAX_CORTES_MIN:
        motivos.append(f"picotado demais: {m['cortes_min']:.1f} cortes/min "
                       f"(teto {MAX_CORTES_MIN:.0f}; a referencia mais rapida faz 27,8)")
    if m.get("frac_lenta", 0) > MAX_FRAC_LENTA:
        piores = sorted(m["planos"], reverse=True)[:3]
        motivos.append(f"tempo parado: {m['frac_lenta']:.0%} do anuncio em plano acima de "
                       f"{PLANO_LONGO_S:.0f}s (teto {MAX_FRAC_LENTA:.0%}; a referencia "
                       f"fica entre 16% e 31%). Os tres maiores planos: "
                       f"{', '.join(f'{x:.1f}s' for x in piores)}")
    if m["maior_plano"] > MAX_PLANO_S:
        motivos.append(f"plano unico de {m['maior_plano']:.1f}s "
                       f"(teto {MAX_PLANO_S:.0f}s; a pior referencia segura 13,2s)")
    return (not motivos), motivos


def imprimir(m, alvo=True):
    ok, motivos = aprova(m)
    print(f"  {m['arquivo'][:44]:46s} {m['dur']:6.1f}s  {m['cortes']:3d} cortes  "
          f"{m['cortes_min']:5.1f}/min  plano medio {m['plano_medio']:5.2f}s  "
          f"maior {m['maior_plano']:5.2f}s  parado {m.get('frac_lenta', 0):5.1%}"
          + (f"  |  so imagem {m['so_imagem_min']:.1f}/min"
             if m.get("so_imagem_min") and m["so_imagem_min"] != m["cortes_min"] else ""))
    if alvo:
        for x in motivos:
            print(f"      REPROVA: {x}")
        if ok:
            print("      PASSA")
    return ok


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    if args[0] == "--plano":
        todos = [medir_do_plano(a) for a in args[1:]]
        ok = all([imprimir(m) for m in todos])
        return 0 if ok else 1
    if args[0] == "--prancha":
        todos = [medir_prancha(a) for a in args[1:]]
    else:
        _plano = _accel = None
        if "--ritmo-json" in args:
            i = args.index("--ritmo-json"); _plano = args[i + 1]; del args[i:i + 2]
        if "--accel" in args:
            i = args.index("--accel"); _accel = float(args[i + 1]); del args[i:i + 2]
        _a0 = 0.0
        if "--a0" in args:
            i = args.index("--a0"); _a0 = float(args[i + 1]); del args[i:i + 2]
        todos = [medir(a, _plano, _accel or 1.35, _a0) for a in args]
    # NAO usar all(...) com gerador: ele faz short-circuit e para de imprimir no
    # primeiro que reprova, escondendo os demais. Medir varios e mostrar um so e pior
    # que nao medir, porque parece cobertura.
    ok = all([imprimir(m) for m in todos])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
