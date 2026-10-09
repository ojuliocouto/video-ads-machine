"""Montagem da footage: lê o ambiente, orquestra os módulos na ordem certa e escreve os arquivos.

Este é o antigo MAIN do `produzir_roteiro.py`, que executava tudo no import. Agora nada acontece até
`main()` ser chamada: importar o módulo não chama ffmpeg, não cria pasta e não lê o ambiente.

## A ordem

  1. `ler_config`: variáveis de ambiente -> `Config` (as mesmas de sempre).
  2. blocos: parser e, com a timeline.json, os spans e o plano de ritmo LIDOS dela (W3.A, relógio único:
     nada de alinhar de novo); sem ela, o caminho antigo (alinhamento com o áudio do avatar, spans,
     contiguidade, plano de ritmo), com aviso no stderr até a W5.A ligar a timeline no build.
  3. `<saida>_ritmo.json` (o plano vai pro disco ANTES do render: o `gen_ad_v2` e o mixador de SFX leem).
  4. `blocos.decidir_bases`: o salto de escala de cada plano de apresentador.
  5. render dos segmentos (pool + cache) e gate de duração de cada um.
  6. cadeia de transições e gate de duração da cadeia.
  7. `timing.json` e a grade final (áudio contínuo do avatar por cima).

## O que o ambiente aceita

VAM_AVATAR e VAM_ROTEIRO são obrigatórias: os padrões antigos apontavam para os arquivos de um
anúncio específico. VAM_INSERTS_JSON, VAM_OUT, VAM_XF, VAM_XF_SECO, VAM_XF_TIPO, VAM_SPLIT_TOP_H,
VAM_SPLIT_GRAD, VAM_SPLIT_BIAS, VAM_CACHE_SEG e VAM_PARALELO seguem como eram. VAM_TIMELINE (W3.A) é o
caminho da timeline.json: o relógio é o dela, que foi construído com as funções desta footage, então o
`_ritmo.json`, o `timing.json` e os quadros saem iguais aos do caminho antigo.

`CAP=1` e `VAM_BAKE_LETTERING=1` foram removidos e viram ERRO ALTO: legenda e lettering da footage
são do overlay (`gen_ad_v2`). Ignorar o valor em silêncio entregaria um vídeo sem o que o chamador
pediu.
"""
import os
import sys
from dataclasses import dataclass
from typing import Optional

import caminhos
from timeline import construir as TC

from . import blocos as BL
from . import cadeia as CA
from . import grade_final as GF
from . import render_segmentos as RS
from . import timing_export as TE
from .enquadramento import ErroEnquadramento

SAIDA_PADRAO = "footage.mp4"


@dataclass(frozen=True)
class Config(object):
    avatar: str
    roteiro: str
    inserts_json: Optional[str]
    saida: str          # caminho do mp4 final
    nome_saida: str     # nome sem extensão (dá nome ao tmp e ao _ritmo.json)
    tmp: str
    outd: str
    ritmo: str
    timing: str
    tr: CA.Transicao
    cache: bool
    paralelo: int
    timeline: Optional[str] = None      # VAM_TIMELINE: o relógio único (W3.A)


def ler_config(env=None, dados=None):
    """Variáveis de ambiente -> `Config`. Erro alto (ErroFootage) para o que falta ou o que foi removido."""
    env = os.environ if env is None else env
    base = dados if dados is not None else os.path.expanduser(env.get("VAM_DADOS") or str(caminhos.DADOS))
    faltam = [n for n in ("VAM_AVATAR", "VAM_ROTEIRO") if not env.get(n)]
    if faltam:
        raise CA.ErroFootage("ERRO: defina " + " e ".join(faltam) + " (o avatar mp4 e o roteiro anotado "
                             "do anúncio). Uso: VAM_AVATAR=... VAM_ROTEIRO=... [VAM_INSERTS_JSON=...] "
                             "[VAM_OUT=...] python3 scripts/produzir_roteiro.py")
    if env.get("CAP") == "1":
        raise CA.ErroFootage("ERRO: CAP=1 foi removido: a legenda da footage é do overlay (gen_ad_v2). "
                             "Use CAP=0 ou não defina CAP.")
    if env.get("VAM_BAKE_LETTERING", "0") == "1":
        raise CA.ErroFootage("ERRO: VAM_BAKE_LETTERING=1 foi removido: o lettering é do overlay (gen_ad_v2). "
                             "Use VAM_BAKE_LETTERING=0 ou não defina.")
    tr = CA.Transicao.do_ambiente(env)
    saida = env.get("VAM_OUT") or SAIDA_PADRAO
    nome = os.path.splitext(saida)[0]
    outd = os.path.join(base, "output")
    return Config(
        avatar=os.path.expanduser(env["VAM_AVATAR"]),
        roteiro=env["VAM_ROTEIRO"],
        inserts_json=env.get("VAM_INSERTS_JSON") or None,
        saida=os.path.join(outd, saida),
        nome_saida=nome,
        tmp=os.path.join(base, "_tmp_rot", nome),
        outd=outd,
        ritmo=os.path.join(outd, nome + "_ritmo.json"),
        timing=os.path.join(outd, "timing.json"),
        tr=tr,
        cache=env.get("VAM_CACHE_SEG", "1") != "0",
        paralelo=int(env.get("VAM_PARALELO", "4")),
        timeline=os.path.expanduser(env["VAM_TIMELINE"]) if env.get("VAM_TIMELINE") else None)


AVISO_SEM_TIMELINE = ("  [relogio] AVISO: footage sem VAM_TIMELINE: alinhando a fala por conta propria (caminho "
                      "antigo). O relogio unico e a timeline.json (timeline/construir.py).")


def _blocos_spans_e_plano(cfg, blocks, inserts):
    """(blocks, spans, bwords, plano) fatiados pelo plano: LIDOS da timeline ou, sem ela, calculados aqui."""
    if cfg.timeline:
        try:
            tl, words = TC.ler_para_motor(cfg.timeline, blocks, avatar=cfg.avatar)
        except TC.ErroTimeline as e:
            raise CA.ErroFootage(f"ERRO: timeline: {e}")
        _spans, bwords = BL.atribuir_spans(blocks, words)
        plano = TC.plano_do_motor(tl, blocks, inserts, BL.achar_insert)
        print(f"  [relogio] timeline.json ({os.path.basename(cfg.timeline)}): {len(plano)} planos, "
              f"a0 {tl['relogio']['a0']:.2f}s, fim {tl['duracao_s']:.2f}s")
        return BL.fatiar_pelo_plano(blocks, bwords, plano)
    sys.stderr.write(AVISO_SEM_TIMELINE + "\n")
    words = BL.alinhar(cfg.avatar, BL.palavras_da_narracao(blocks), cfg.tmp)
    spans, bwords = BL.atribuir_spans(blocks, words)
    spans = BL.tornar_contiguos(spans)
    return BL.aplicar_ritmo(blocks, spans, bwords, inserts)


def montar(cfg):
    """Monta a footage e devolve o caminho do mp4."""
    import ritmo as _R

    os.makedirs(cfg.tmp, exist_ok=True)
    os.makedirs(cfg.outd, exist_ok=True)
    os.makedirs(os.path.dirname(cfg.saida) or ".", exist_ok=True)

    blocks = BL.ler_blocos(cfg.roteiro)
    inserts = BL.carregar_inserts(cfg.inserts_json)
    blocks, spans, bwords, plano = _blocos_spans_e_plano(cfg, blocks, inserts)
    total = spans[-1][1]
    res = _R.resumo(plano, total)
    TE.escrever_ritmo(cfg.ritmo, plano, total)
    print(f"  [ritmo] {len(plano)} planos | {res['cortes_min']:.1f} cortes/min | "
          f"plano medio {res['plano_medio']:.2f}s | maior {res['maior_plano']:.2f}s "
          f"(referencia: 19 a 28 cortes/min)")
    print(f"{len(blocks)} blocos | total {total:.1f}s")

    BL.decidir_bases(blocks)
    logo = caminhos.achar_logo() if any(b["type"] == "logo" for b in blocks) else None
    ctx = RS.Contexto(avatar=cfg.avatar, tmp=cfg.tmp, tr=cfg.tr, inserts=inserts,
                      dir_molduras=str(caminhos.ESTADO / "molduras"),
                      dir_gerados=str(caminhos.ESTADO / "gerados"),
                      logo=str(logo) if logo else None, cache=cfg.cache, paralelo=cfg.paralelo)
    segs = RS.renderizar_todos(blocks, spans, ctx)

    durs = CA.medir_duracoes(segs)
    CA.verificar_segmentos(spans, durs, blocks, cfg.tr)
    vchain = os.path.join(cfg.tmp, "vchain0.mp4")
    CA.montar_vchain(segs, blocks, spans, durs, cfg.tr, vchain)

    a0 = spans[0][0]
    TE.escrever_timing(cfg.timing, a0, total, cfg.tr.xf, cfg.avatar, spans, blocks)
    GF.aplicar(vchain, a0, total, cfg.avatar, cfg.saida)
    print("PRONTO:", cfg.saida)
    return cfg.saida


def main(argv=None, env=None):
    """Ponto de entrada. Devolve o código de saída: 0 ok, 1 com a mensagem no stderr (sem traceback)."""
    try:
        montar(ler_config(env))
    except (CA.ErroFootage, ErroEnquadramento) as e:
        sys.stderr.write(str(e) + "\n")
        return 1
    return 0
