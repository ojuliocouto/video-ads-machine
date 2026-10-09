#!/usr/bin/env python3
"""timeline/construir: o relógio único do anúncio (`render/timeline.json`, contrato timeline.schema.json).

    python3 scripts/timeline/construir.py --avatar A --roteiro R --inserts I --config C --timeline T
        [--alinhamento AL] [--cache-dir D] [--raiz P] [--aceleracao 1.35] [--fps 30] [--glossario G]
    saída 0 gravou · 1 insumo com problema (uma mensagem, sem traceback) · 2 uso errado

Defeito 20 do plano: overlay e footage alinhavam a fala cada um por si e derivavam os spans por caminhos
diferentes. A deriva chegou a 1,07 s no fim de um anúncio de 2 min (footage 120,90 s contra overlay
121,97 s) e foi a origem dos remendos de "banda de guarda". Agora há UMA transcrição e UM alinhamento
(`timeline.alinhar`) e este módulo deriva deles, uma vez, tudo o que é tempo. Footage e overlay leem a
timeline e não decidem tempo por conta própria.

## O relógio é o da footage

Todo tempo está no relógio da footage a 1x, que é o do áudio do avatar: a footage começa em `relogio.a0`
(o início do 1º bloco) e acaba em `duracao_s` (o fim do último). O arquivo entregue converte com
`(t - a0) / aceleracao` e soma `cauda_s` só na duração total. Os spans e o plano de ritmo saem das MESMAS
funções que a footage usava sozinha (`footage.blocos`: atribuir_spans, tornar_contiguos, plano_de_ritmo), sobre
uma transcrição feita do mesmo jeito que a footage antiga fazia (`timeline.alinhar`, perfil "alinhamento"). O que foi
medido (W3.X A2): com a mesma transcrição o golden da footage não muda; com o chunk de 15/3 s do parakeet, que a W3.A
usava, a fronteira de bloco andava até 0,16 s no avatar do fixture. O que muda é o overlay, que passa a usar este
relógio no lugar do dele, com a duração da footage mais a folga de cauda (`duracao_do_overlay`).

## A folga de cauda (W3.X, M1)

O composite usa `shortest=1`: se o overlay (deslocado de -a0) acaba antes da footage, a imagem perde a cauda e o
áudio segue. A W3.A zerou a folga (overlay = fim da fala) e a auditoria somou -0,037 s com VAM_XF=0.12. A footage
entregue nunca passa da própria janela de áudio (`duracao_s - a0`): o mux final corta a cadeia mais longa com
-shortest (medido com ffmpeg em tests/footage/test_cadeia.py, cadeia de 1 a 9 quadros mais longa). Então o overlay
dura `duracao_s` mais QUADROS_DE_FOLGA quadros, arredondado para cima no centésimo: 1 quadro de folga garantida e 1
para o render do overlay que arredonda a duração para quadro inteiro. O `gate_relogio` mede a cauda nos arquivos.

## O que vem de onde

  blocos, segmentos     footage.blocos (spans contíguos e plano de ritmo); a chave do insert vira slug
  janelas_split         overlay (visitas de insert sobre o MESMO plano): só fatia que é tela dividida de
                        verdade, o que exige `split: true` no config do insert
  hook, cta, letterings, legendas
                        as funções do overlay, na ordem do `overlay.gerar`, sobre as mesmas palavras e spans
  camera                os punches da W4.A ({t, tipo: punch, de, para, dur, segura}); vazia por padrão
  sfx, ducking          da W4.B; vazios por padrão (ducking desligado com motivo)

Decisões onde o motor e o contrato não falam a mesma língua (registradas, não escondidas):
  - hook.s é o a0: o overlay começa o hook no zero do áudio, mas a tela só existe a partir do a0;
  - cta.logo é o instante REAL do logo: o overlay o antecipa em 0,9 s quando o bloco anterior ao CTA é
    apresentador (`overlay.cta.LOGO_LEAD`), e o contrato aceita até essa antecipação (W5.A; antes a timeline
    grudava o logo no CTA). A subida do CTA (`cta.inicio`), que é o que o som e os gates usam, é exata;
  - legenda: a posição sai do layout (costura no split, rodapé sobre insert com texto). O rodapé por look
    fechado depende de medir o rosto: o chamador passa `medir_rosto`, e a CLI passa a medição do avatar que ela
    alinhou (W3.X M5: sem isso a timeline registrava legenda padrão num look fechado medido);
  - lettering: o estilo EFETIVO do config (`cinema.lettering_estilos.efetivo`: sem estilo, ou em split, close e pilha,
    o `serif_editorial`); o lettering que passaria do fim é aparado no fim.

## Leitura (o que footage e overlay chamam)

`ler_para_motor(timeline, blocos, avatar)` valida o contrato, confere o sha do alinhamento citado, o sha do
avatar e que o roteiro é o mesmo, e devolve as palavras. `spans`, `janelas_split` e `plano_do_motor` dão o
resto no formato de cada motor. O caminho em `fontes` é relativo à pasta do projeto, que é a mãe da pasta da
timeline (`<projeto>/render/timeline.json`; no motor antigo, `<dados>/output/<ad>_timeline.json`).
"""
import argparse
import contextlib
import json
import math
import os
import re
import sys
import unicodedata
from pathlib import Path

if __name__ == "__main__":      # rodado direto: scripts/timeline/construir.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contratos.validar import validar  # noqa: E402
from footage import blocos as BL  # noqa: E402
from timeline import alinhar as AL  # noqa: E402

FPS = 30                    # a footage renderiza a 30 quadros por segundo (o mesmo do overlay)
ACELERACAO_PADRAO = 1.35    # build_composite.ACCEL: aceleração do arquivo entregue com avatar
CAUDA_S = 0.45              # build_composite.TAIL_FINAL: último quadro congelado depois da aceleração
QUADROS_DE_FOLGA = 2        # overlay além da footage: 1 quadro de folga + 1 do arredondamento do render (M1)
ESTILO_LETTERING = "serif_editorial"
DUCKING_SEM_TRILHA = {"desligado": True,
                      "motivo": "a timeline ainda não planeja a cama musical: o mix de hoje é do build_composite"}
# Ordem das chaves de um plano do ritmo.py (todos os ramos seguem esta ordem): o `_ritmo.json` da footage é
# comparado byte a byte pela paridade.
OPCIONAIS_DO_PLANO = ("layout", "fonte_off", "deitico", "base", "punch")
POSICAO = {"costura": "costura", "baixa": "rodape", "padrao": "padrao"}


class ErroTimeline(RuntimeError):
    """A timeline não pode ser construída ou lida como está. Uma mensagem, com o que fazer."""


# ======================================================================================== formatos

def chave(texto):
    """Slug do contrato (`^[a-z0-9][a-z0-9_-]*$`): sem acento, minúsculo, o resto vira hífen."""
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9_-]+", "-", t).strip("-_")
    return t or "item"


def _chave_do_insert(instr, inserts_map):
    s = instr.lower()
    for k in inserts_map:
        if k in s:
            return chave(k)
    raise ErroTimeline(f"nenhum insert do mapa casa com a instrução {instr!r} "
                       f"(chaves: {', '.join(sorted(inserts_map)) or 'nenhuma'})")


def _tipo_do_bloco(b, i, n):
    if b["type"] == "insert":
        return "insert"
    return "cta" if i == n - 1 else "apresentador"


def segmentos_do_plano(plano):
    """Plano do ritmo.py -> `segmentos` do contrato (apresentador/insert; o recorte volta pelo config)."""
    saida = []
    for sg in plano:
        d = {"bloco": sg["bloco"], "tipo": "insert" if sg["tipo"] == "insert" else "apresentador",
             "s": sg["s"], "e": sg["e"], "sub": sg["sub"], "de": sg["de"]}
        for k in OPCIONAIS_DO_PLANO:
            if k in sg:
                d[k] = sg[k]
        saida.append(d)
    return saida


def plano_do_motor(tl, blocks, inserts_map, achar):
    """`segmentos` da timeline -> o plano no formato do ritmo.py (o que footage e overlay usam).

    `achar(inserts_map, instr)` devolve o config do insert do bloco (o recorte do plano é o do config).
    """
    plano = []
    for sg in tl["segmentos"]:
        crop = None
        if sg["tipo"] == "insert":
            crop = (achar(inserts_map, blocks[sg["bloco"]]["instr"]) or {}).get("crop")
        d = {"bloco": sg["bloco"], "tipo": "insert" if sg["tipo"] == "insert" else "orig",
             "s": sg["s"], "e": sg["e"], "crop": crop, "sub": sg["sub"], "de": sg["de"]}
        for k in OPCIONAIS_DO_PLANO:
            if k in sg:
                d[k] = sg[k]
        plano.append(d)
    return plano


def spans(tl):
    """[(início, fim)] de cada bloco: os spans contíguos dos dois motores."""
    return [(b["s"], b["e"]) for b in tl["blocos"]]


def janelas_split(tl):
    """[(início, fim)] onde a tela está dividida de verdade."""
    return [(j["s"], j["e"]) for j in tl["janelas_split"]]


def duracao_do_overlay(tl):
    """Até onde o overlay vai, no relógio da timeline: o fim da footage mais QUADROS_DE_FOLGA quadros do fps dela,
    arredondado para cima no centésimo (ver "A folga de cauda" no topo)."""
    fim = float(tl["duracao_s"]) + QUADROS_DE_FOLGA / float(tl["relogio"]["fps"])
    return math.ceil(fim * 100 - 1e-6) / 100


# ======================================================================================== o texto da tela

def _texto_da_tela(blocks, words, spans_, plano, inserts_map, cfg, medir_rosto):
    """Hook, janelas, letterings, CTA e legendas, pelas funções do overlay na ordem do `overlay.gerar`."""
    from overlay import (brolls as OB, cta as OC, gerar as OG, hook as OH, layout_texto as OL,
                         letterings as OLE, transcricao as OT)
    ov = OT.palavras_da_timeline(words)
    OT.marcar_kw(ov, cfg.get("kw_phrases", []))
    h = OH.calcular_hook(blocks, spans_)
    visitas, retorno_avatar = OB.planejar_visitas(blocks, spans_, inserts_map, plano)
    js, jt, mapa = OL.janelas_por_visita(visitas)
    letts, lett_windows = OLE.montar(cfg.get("letterings", []), ov, spans_, blocks, js)
    cta_start = OC.calcular_cta_start(blocks, spans_, retorno_avatar)
    logo_start = OC.logo_start(cta_start, OC.logo_lead(blocks))
    groups = OG._montar_legendas(ov, cfg, cfg.get("ad", ""), cfg.get("look", ""), h, logo_start, js, jt, mapa,
                                 letts, lett_windows, medir_rosto=medir_rosto or (lambda avatar: None),
                                 medir_fundo=False)
    return h, js, letts, groups, cta_start, logo_start, OL.classe_do_grupo


def _bloco_de(t, spans_):
    return next((i for i, (a, b) in enumerate(spans_) if a <= t < b), len(spans_) - 1)


from cinema import lettering_estilos as LE  # noqa: E402  (o estilo efetivo de cada lettering)


def _letterings(letts, spans_, dur):
    saida = []
    for l in letts:
        s = float(l["start"])
        d = round(min(float(l["dur"]), dur - s), 3)
        if d <= 0:
            continue
        estilo = LE.efetivo(l.get("estilo"), split=bool(l.get("split")), baixo=bool(l.get("baixo")),
                            pilha=bool(l.get("pilha")))
        saida.append({"id": str(l["id"]).lower(), "bloco": _bloco_de(s, spans_), "lead": l.get("lead") or None,
                      "key": l["key"], "s": s, "d": d, "estilo": estilo, "split": bool(l.get("split")),
                      "baixo": bool(l.get("baixo")), "pilha": chave(l["pilha"]) if l.get("pilha") else None,
                      "cta": bool(l.get("logo"))})
    return saida


def _legendas(groups, classe):
    saida = []
    for g in groups:
        s, e = float(g["start"]), float(g["end"])
        palavras = []
        for w in g["words"]:
            ws = min(max(float(w["start"]), s), e)
            palavras.append({"t": w["text"], "s": ws, "e": min(max(float(w["end"]), ws), e)})
        saida.append({"s": s, "e": e, "texto": " ".join(w["text"] for w in g["words"]), "palavras": palavras,
                      "posicao": POSICAO[classe(g)], "suprimida": False})
    return saida


# ======================================================================================== construir

def _relativo(caminho, raiz, o_que):
    try:
        return Path(os.path.realpath(caminho)).relative_to(Path(os.path.realpath(raiz))).as_posix()
    except ValueError:
        raise ErroTimeline(f"{o_que} ({caminho}) tem que morar dentro da pasta do projeto ({raiz}): o contrato "
                           "guarda caminho relativo, para a timeline valer em qualquer máquina")


def com_camera(tl):
    """A timeline com o plano de câmera (`cinema.camera.planejar`): zoom por plano de apresentador, respiro e o
    punch da KEY em avatar cheio (W5.X, pendência b: a timeline do montar saía com `camera` vazia)."""
    from cinema import camera
    novo = dict(tl)
    novo["camera"] = camera.planejar(tl)
    return novo


def construir(blocks, alinhamento, *, inserts_map, cfg, caminho_alinhamento, raiz, fps=FPS,
              aceleracao=ACELERACAO_PADRAO, cauda_s=CAUDA_S, formato=None, projeto=None, punches=(), sfx=(),
              ducking=None, medir_rosto=None):
    """A timeline (dict validado no contrato). Não grava nada e não chama subprocesso.

    `alinhamento` é o que `timeline.alinhar` gravou em `caminho_alinhamento` (o sha do arquivo vai para
    `fontes`); `raiz` é a pasta do projeto; `cfg` é o config do overlay (hook, cta_label, letterings,
    kw_phrases, format). `punches` são os eventos de câmera da W4.A.
    """
    if str(alinhamento.get("avatar", "")).startswith("/"):
        raise ErroTimeline(f"o avatar ({alinhamento['avatar']}) tem que morar dentro da pasta do projeto ({raiz}): "
                           "alinhe passando a raiz do projeto")
    if AL.ler(caminho_alinhamento) != alinhamento:
        raise ErroTimeline(f"o alinhamento em memória não é o gravado em {caminho_alinhamento}: grave antes "
                           "(timeline.alinhar.gravar) e construa a partir do arquivo")
    words = AL.palavras(alinhamento)
    if [w[2] for w in words] != BL.palavras_da_narracao(blocks):
        raise ErroTimeline("o alinhamento é de outro roteiro: as palavras não batem com a fala dos blocos. "
                           "Alinhe de novo com este roteiro")
    try:
        sp, _bwords = BL.atribuir_spans(blocks, words)
        sp = BL.tornar_contiguos(sp)
        # os diagnósticos do overlay ("[split]", "[look]", "[ritmo]") vão para o stderr: o stdout da timeline é só o
        # resumo (W3.X L8), e quem lê a saída da CLI não tem que separar uma coisa da outra
        with contextlib.redirect_stdout(sys.stderr):
            plano = BL.plano_de_ritmo(blocks, sp, inserts_map)
            h, js, letts, groups, cta_start, logo_start, classe = _texto_da_tela(
                blocks, words, sp, plano, inserts_map, cfg, medir_rosto)
    except SystemExit as e:                 # o overlay para o motor com sys.exit(mensagem)
        raise ErroTimeline(str(e.code))
    except BL.CA.ErroFootage as e:
        raise ErroTimeline(str(e))
    a0, dur = sp[0][0], sp[-1][1]
    hook_cfg = cfg.get("hook") or {}
    tl = {
        "versao": 1,
        "projeto": chave(projeto or cfg.get("ad") or "projeto")[:63],
        "relogio": {"base": "footage_1x", "fps": int(fps), "aceleracao": float(aceleracao),
                    "cauda_s": float(cauda_s), "a0": a0},
        "duracao_s": dur,
        "formato": formato or cfg.get("format") or "9x16",
        "fontes": {"avatar": alinhamento["avatar"], "avatar_sha256": alinhamento["avatar_sha256"],
                   "alinhamento": _relativo(caminho_alinhamento, raiz, "o alinhamento"),
                   "alinhamento_sha256": AL.sha256_arquivo(caminho_alinhamento)},
        "blocos": [{"i": i, "tipo": _tipo_do_bloco(b, i, len(blocks)),
                    "insert": _chave_do_insert(b["instr"], inserts_map) if b["type"] == "insert" else None,
                    "s": s, "e": e} for i, (b, (s, e)) in enumerate(zip(blocks, sp))],
        "segmentos": segmentos_do_plano(plano),
        "janelas_split": [{"s": s, "e": e} for s, e in js],
        "legendas": _legendas(groups, classe),
        "letterings": _letterings(letts, sp, dur),
        "hook": {"s": a0, "e": max(float(h.hook_gone), round(a0 + 1.0 / fps, 3)),
                 "eyebrow": hook_cfg.get("eyebrow", ""), "linha": hook_cfg.get("l1", ""),
                 "destaque": hook_cfg.get("accent", ""),
                 "estilo": "punch" if hook_cfg.get("style") == "punch" else "editorial"},
        "cta": {"inicio": cta_start, "logo": logo_start,
                "label": cfg.get("cta_label") or "saiba mais", "sem_lead": bool(cfg.get("cta_sem_lead"))},
        "camera": [dict(p) for p in punches],
        "sfx": [dict(x) for x in sfx],
        "ducking": dict(ducking or DUCKING_SEM_TRILHA),
    }
    erros = validar("timeline", tl)
    if erros:
        raise ErroTimeline("a timeline construída não passa no contrato: "
                           + "; ".join(str(e) for e in erros[:6]))
    volta = plano_do_motor(tl, blocks, inserts_map, BL.achar_insert)
    if json.dumps(volta) != json.dumps(plano):
        raise ErroTimeline("o plano de ritmo tem campo que o contrato não carrega: footage e overlay leriam outro "
                           "plano. Atualize contratos/timeline.schema.json e OPCIONAIS_DO_PLANO juntos")
    return tl


# ======================================================================================== arquivo

def gravar(tl, caminho):
    """Grava (temporário + rename) e devolve o sha256 dos bytes."""
    import hashlib
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    dados = (json.dumps(tl, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    tmp = caminho.with_name(caminho.name + ".tmp")
    tmp.write_bytes(dados)
    os.replace(str(tmp), str(caminho))
    return hashlib.sha256(dados).hexdigest()


def ler(caminho):
    """A timeline gravada, validada no contrato (ErroTimeline nomeando o campo)."""
    try:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except OSError as e:
        raise ErroTimeline(f"timeline ilegível em {caminho}: {e}")
    except ValueError as e:
        raise ErroTimeline(f"timeline com JSON inválido em {caminho}: {e}")
    erros = validar("timeline", dados)
    if erros:
        raise ErroTimeline(f"timeline fora do contrato ({caminho}): " + "; ".join(str(e) for e in erros[:6]))
    return dados


def raiz_de(caminho_timeline):
    """A pasta do projeto: a mãe da pasta da timeline (`<projeto>/render/timeline.json`)."""
    return Path(os.path.realpath(caminho_timeline)).parent.parent


def exigir_alinhamento(tl, caminho_timeline):
    """O alinhamento que a timeline cita, conferido pelo sha256."""
    p = raiz_de(caminho_timeline) / tl["fontes"]["alinhamento"]
    try:
        return AL.ler(p, tl["fontes"]["alinhamento_sha256"])
    except AL.ErroAlinhamento as e:
        raise ErroTimeline(str(e))


def ler_para_motor(caminho_timeline, blocks, avatar=None):
    """`(timeline, palavras)` para footage e overlay: contrato, alinhamento citado, avatar e roteiro conferidos.

    `palavras` é `[(início, fim, palavra do roteiro)]`, as mesmas que a timeline usou.
    """
    tl = ler(caminho_timeline)
    al = exigir_alinhamento(tl, caminho_timeline)
    if avatar is not None:
        try:
            sha = AL.sha256_arquivo(avatar)
        except OSError as e:
            raise ErroTimeline(f"avatar ilegível ({avatar}): {e}")
        if sha != tl["fontes"]["avatar_sha256"]:
            raise ErroTimeline(f"o avatar {avatar} não é o da timeline (sha256 diferente): o avatar mudou depois "
                               "do alinhamento. Reconstrua a timeline com o avatar novo")
    palavras = AL.palavras(al)
    if len(tl["blocos"]) != len(blocks) or [p[2] for p in palavras] != BL.palavras_da_narracao(blocks):
        raise ErroTimeline("a timeline é de outro roteiro: os blocos ou as palavras não batem com o roteiro "
                           "deste anúncio. Reconstrua a timeline")
    return tl, palavras


# ======================================================================================== CLI

def medir_rosto_do_avatar(avatar):
    """A medição do rosto que o overlay usa (`medir_rosto.caixa_rosto`), sempre sobre o avatar que a CLI alinhou (e
    não sobre o `avatar` do config do overlay, que pode ser outra cópia). Falha de medição chega ao overlay como
    exceção e ele cai no plano declarado do look."""
    def medir(_avatar_do_config):
        import medir_rosto
        return medir_rosto.caixa_rosto(str(avatar))
    return medir


def _alinhamento_padrao(timeline):
    nome = timeline.name
    if nome == "timeline.json":
        return timeline.with_name("alinhamento.json")
    if nome.endswith("_timeline.json"):
        return timeline.with_name(nome[:-len("_timeline.json")] + "_alinhamento.json")
    return timeline.with_name(timeline.stem + "_alinhamento.json")


def _ler_json(caminho, o_que):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ErroTimeline(f"{o_que} ilegível ({caminho}): {e}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="timeline/construir.py",
                                 description="Alinha a fala uma vez e grava a timeline.json (relógio único).")
    ap.add_argument("--avatar", required=True, help="vídeo do apresentador (avatar, take ou one-shot)")
    ap.add_argument("--roteiro", required=True, help="roteiro anotado do motor (<ad>_leva.txt)")
    ap.add_argument("--inserts", required=True, help="mapa de inserts (<ad>_inserts.json)")
    ap.add_argument("--config", required=True, help="config do overlay (hook, cta_label, letterings, format)")
    ap.add_argument("--timeline", required=True, help="onde gravar a timeline.json")
    ap.add_argument("--alinhamento", help="onde gravar o alinhamento (padrão: ao lado da timeline)")
    ap.add_argument("--cache-dir", help="cache da transcrição (padrão: <pasta da timeline>/cache_asr)")
    ap.add_argument("--raiz", help="pasta do projeto (padrão: a mãe da pasta da timeline)")
    ap.add_argument("--aceleracao", type=float, default=ACELERACAO_PADRAO)
    ap.add_argument("--fps", type=int, default=FPS)
    ap.add_argument("--glossario", help="glossario.json do aluno (grafias e variantes do ASR)")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0)
    timeline = Path(a.timeline)
    alinhamento = Path(a.alinhamento) if a.alinhamento else _alinhamento_padrao(timeline)
    raiz = Path(a.raiz) if a.raiz else raiz_de(timeline)
    try:
        cfg = _ler_json(a.config, "config do overlay")
        inserts_map = _ler_json(a.inserts, "mapa de inserts")
        try:
            blocks = BL.ler_blocos(a.roteiro)
        except OSError as e:
            raise ErroTimeline(f"roteiro ilegível ({a.roteiro}): {e}")
        glossario = _ler_json(a.glossario, "glossário") if a.glossario else None
        al = AL.alinhar(a.avatar, BL.palavras_da_narracao(blocks),
                        cache_dir=Path(a.cache_dir) if a.cache_dir else timeline.parent / "cache_asr",
                        raiz=raiz, glossario=glossario)
        sha = AL.gravar(al, alinhamento)
        tl = construir(blocks, al, inserts_map=inserts_map, cfg=cfg, caminho_alinhamento=alinhamento, raiz=raiz,
                       fps=a.fps, aceleracao=a.aceleracao, medir_rosto=medir_rosto_do_avatar(a.avatar))
        gravar(tl, timeline)
    except (ErroTimeline, AL.ErroAlinhamento) as e:
        sys.stderr.write(f"ERRO: {e}\n")
        return 1
    print(f"[timeline] {len(tl['blocos'])} blocos | {len(tl['segmentos'])} planos | "
          f"{len(tl['janelas_split'])} janela(s) de split | a0 {tl['relogio']['a0']:.2f}s | "
          f"fim {tl['duracao_s']:.2f}s | alinhamento {sha[:12]} -> {timeline}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
