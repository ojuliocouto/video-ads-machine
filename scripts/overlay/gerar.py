"""Gerador do overlay do anúncio no motor v2 (HyperFrames), padrão validado num piloto.

Fonte de verdade por anúncio: o roteiro anotado (`<ad>_leva.txt`, verbatim ao falado) mais o mapa de
inserts (`<ad>_inserts.json`). Este módulo deriva TUDO deles: spans por bloco (contíguos), b-roll
cards, legendas palavra a palavra (kw por frase), letterings, CTA e logo no bloco final.

Uso: `python3 gen_ad_v2.py <config.json>` (o wrapper chama `main`).
Config: {"ad", "look", "avatar", "out_dir", "hook": {eyebrow, l1, accent[, style]}, "cta_label",
         "kw_phrases": [...], "letterings": [{"lead", "key", "anchor", "nth": 1, "dur": 2.2}],
         "format": "9x16" | "1x1", "speed", "labels", "cta_sem_lead"}

Importar este módulo não executa nada. O pipeline, na ordem em que o original o fazia (a ordem
importa: cada passo lê o que o anterior decidiu):

   avatar acelerado -> transcrição -> palavras -> spans -> hook -> ritmo -> visitas de insert
   -> janelas de layout -> b-rolls -> letterings -> relógio da footage -> legendas -> CTA
   -> gate de tela vazia -> chips -> HTML -> prancha e arquivos
"""
import json
import shutil
from pathlib import Path

from caminhos import V1, V2, RENDER_MODELO as ESTADO_RENDER, achar_logo, achar_meta
from material_local import exigir
from overlay import (brolls as brolls_m, chips as chips_m, cta as cta_m, fundo_claro, hook as hook_m,
                     html_injecao, layout_texto, legendas, letterings as letterings_m, prancha_export,
                     spans as spans_m, tela_vazia, transcricao)
from parser_roteiro import parse as parse_v1


def _preparar_pasta(out, tmpl):
    """Fontes do template, logo e meta.json do SEU anúncio (`_local/render-reel-editorial/`). Falta vira
    uma mensagem só, com o comando que cria a estrutura."""
    if not (out / "fonts").exists():
        shutil.copytree(tmpl.parent / "fonts", out / "fonts")
    _logo = achar_logo() or exigir(ESTADO_RENDER / "logo.png", "o logo do seu anúncio (PNG)")
    _meta = achar_meta() or exigir(ESTADO_RENDER / "meta.json", "metadados do render")
    shutil.copy(_logo, out / "logo.png")
    shutil.copy(_meta, out / "meta.json")


def _montar_legendas(words, cfg, ad, look, h, logo_start, janelas_split, janelas_texto, mapa_insert, letts,
                     lett_windows):
    """Os grupos de legenda finais, na ordem do original: corpo, texto próprio, look fechado,
    fronteira de split, costura, tinta invertida, guarda pós-split, fechamento e letterings."""
    groups = legendas.agrupar(words)
    groups = legendas.filtrar_corpo(groups, h.cap_gate, logo_start)
    layout_texto.descer_para_rodape_em_texto(groups, janelas_texto)
    layout_texto.baixar_no_look_fechado(groups, cfg.get("avatar", ""))
    if janelas_split:
        groups = layout_texto.cortar_na_fronteira(groups, janelas_split)
        layout_texto.marcar_costura(groups, janelas_split)
    fundo_claro.marcar_grupos_claros(groups, ad, look, mapa_insert)
    layout_texto.empurrar_pos_split(groups, janelas_split)
    groups = legendas.fechar_grupos(groups, logo_start)
    return legendas.aparar_nos_letterings(groups, letts, lett_windows)


def main(cfg_path):
    cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
    ad, look = cfg["ad"], cfg["look"]
    out = Path(cfg["out_dir"])
    out.mkdir(parents=True, exist_ok=True)

    # template por formato: 9x16 (padrão) ou 1x1 (quadrado dedicado)
    fmt = cfg.get("format", "9x16")
    tmpl = V2 / "templates" / ("reel-editorial-1x1" if fmt == "1x1" else "reel-editorial") / "index.html"

    # ---------- assets base e transcrição ----------
    speed = float(cfg.get("speed", transcricao.SPEED))
    dst, total = transcricao.preparar_avatar(Path(cfg["avatar"]), out, speed)
    _preparar_pasta(out, tmpl)
    transcript = transcricao.transcrever(dst, out)

    # ---------- roteiro: blocos, narração e palavras com tempo ----------
    _leva = exigir(V1 / "inputs" / f"{ad}_leva.txt", "o roteiro anotado deste anúncio")
    _ins = exigir(V1 / "inputs" / f"{ad}_inserts.json", "o mapa de inserções deste anúncio")
    blocks = parse_v1(str(_leva))
    inserts_map = json.loads(_ins.read_text(encoding="utf-8"))
    words = transcricao.alinhar_palavras(blocks, transcript)
    transcricao.marcar_kw(words, cfg.get("kw_phrases", []))
    spans = spans_m.calcular_spans(blocks, words)
    h = hook_m.calcular_hook(blocks, spans)

    # ---------- inserts: ritmo, visitas, janelas de layout e arquivos ----------
    plano_ritmo, _ = spans_m.plano_de_ritmo(blocks, spans, inserts_map)
    visitas, retorno_avatar = brolls_m.planejar_visitas(blocks, spans, inserts_map, plano_ritmo)
    janelas_split, janelas_texto, mapa_insert = layout_texto.janelas_por_visita(visitas)
    brolls = brolls_m.montar_brolls(visitas, cfg.get("labels", {}))
    brolls_m.preparar_arquivos(brolls, out)

    # ---------- letterings, antes das legendas, para deconflitar ----------
    letts, lett_windows = letterings_m.montar(cfg.get("letterings", []), words, spans, blocks, janelas_split)
    janelas_split = layout_texto.aplicar_relogio_footage(ad, look, janelas_split)
    # rastro de deconflito: sem isso não dá para saber se a flag chegou (um build inteiro foi perdido
    # achando que o CSS estava errado quando a janela é que estava vazia)
    print(f"   [deconflito] split={janelas_split} texto={janelas_texto} "
          f"letts={[(l['id'], l['start'], l['split']) for l in letts]}", flush=True)

    # ---------- CTA, logo e legendas ----------
    cta_start = cta_m.calcular_cta_start(blocks, spans, retorno_avatar)
    lead = cta_m.logo_lead(blocks)
    logo_start = cta_m.logo_start(cta_start, lead)
    groups = _montar_legendas(words, cfg, ad, look, h, logo_start, janelas_split, janelas_texto, mapa_insert,
                              letts, lett_windows)
    caps_html = legendas.html(groups)
    letts_html = letterings_m.html(letts)
    cta_s, logo_s = cta_m.janela(cta_start, lead)

    # ---------- gate de tela vazia (barato, antes do render) ----------
    vao = tela_vazia.checar(h.hook_dur, groups, lett_windows, cta_s, total)

    # ---------- montar html ----------
    chips = chips_m.calcular(plano_ritmo, groups, lett_windows, logo_s)
    html = html_injecao.injetar_marcadores(tmpl.read_text(encoding="utf-8"), caps_html, letts_html)
    html = html_injecao.injetar_chips(html, chips_m.html(chips))
    html = html_injecao.fixar_duracao(html, total)
    html = hook_m.aplicar_html(html, cfg["hook"], h)
    html = html_injecao.suavizar_grade(html)
    html = brolls_m.injetar_html(html, brolls)
    html = cta_m.aplicar_html(html, cfg, cta_s, logo_s, total, janelas_split)
    html = html_injecao.remover_beat_pb(html)
    wipes = brolls_m.wipes_de_entrada(brolls_m.agrupar(brolls))
    html = html_injecao.remover_wipes(html)

    # ---------- prancha e arquivos ----------
    prancha = prancha_export.montar_prancha(ad, look, total, h.hook_dur, cfg, cta_s, logo_s, blocks, spans,
                                            brolls, letts, groups, vao)
    prancha_export.gravar(out, prancha, janelas_split)
    (out / "index.html").write_text(html, encoding="utf-8")
    print(f"[{ad} {look}] total={total}s | {len(brolls)} brolls | {len(letts)} letterings | "
          f"{len(groups)} grupos de legenda | CTA {cta_s}s | wipes {wipes}")
    for b in brolls:
        print(f"   {b['src']:14} {b['s']:6.2f}s +{b['d']:5.2f}s  {b['label']}")
