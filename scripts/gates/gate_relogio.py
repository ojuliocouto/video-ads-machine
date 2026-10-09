#!/usr/bin/env python3
"""GATE RELÓGIO (W3.A, capacidade C14): footage e overlay saíram do MESMO relógio, a timeline.json?

    python3 scripts/gates/gate_relogio.py --timeline T --footage-ritmo R --footage-timing J --overlay-dir D
        [--footage-mp4 M] [--overlay-mov V]
    exit 0 passa · 1 reprova · 2 insumo inválido (arquivo ausente, JSON quebrado, timeline fora do contrato)

Defeito 20 do plano: os dois motores alinhavam a fala cada um por si e derivaram até 1,07 s no fim de um
anúncio de 2 min. Com a timeline os dois leem o mesmo arquivo; este gate confere, DEPOIS do build, que o
que cada um gravou é o que a timeline diz. Uma timeline editada à mão depois do build, um motor que ainda
alinha por conta própria ou uma transcrição refeita no meio do caminho aparecem aqui.

O que é comparado (limite: 1 quadro, `1 / relogio.fps` da própria timeline, nunca número redondo):

  alinhamento   o arquivo citado em `fontes.alinhamento` tem o sha256 de `fontes.alinhamento_sha256`
  plano         o `_ritmo.json` da footage: mesmo número de planos, mesmo tipo, mesmo layout e mesmas
                bordas (s, e) que `segmentos`
  footage       `timing.json`: a0 e fim iguais a `relogio.a0` e `duracao_s`
  janelas       `janelas_split.json` do overlay: as mesmas janelas de `janelas_split`
  blocos        `prancha.json` do overlay: os mesmos blocos (s, e) de `blocos`
  duração       a da footage (`timing.total - timing.a0`) é a da timeline; a do overlay (`prancha.total`) é a
                `duracao_do_overlay` da timeline (o fim da footage mais a folga de cauda)
  cauda         W3.X M1: o overlay deslocado de -a0 dura pelo menos 1 quadro a mais que a footage, senão o
                composite (shortest=1) corta a imagem e o áudio segue. Medida nos ARQUIVOS: a footage é o mp4 ao lado
                do `_ritmo.json` (`<nome>_ritmo.json` -> `<nome>.mp4`) sempre que ele existe, ou o `--footage-mp4`; o
                overlay, o `--overlay-mov`. A duração da footage é a do VÍDEO (o composite enxerga o vídeo; o áudio do
                mux pode passar dele)

Saída: uma linha `RELOGIO REPROVA: <o quê>: <detalhe>` por falha, ou `RELOGIO OK` com os números.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":      # rodado direto: scripts/gates/gate_relogio.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from timeline import alinhar as AL  # noqa: E402
from timeline import construir as TC  # noqa: E402

TIPO_DO_PLANO = {"orig": "apresentador", "insert": "insert"}


class InsumoInvalido(RuntimeError):
    """O gate não tem como conferir: falta arquivo ou ele está quebrado (exit 2)."""


def limite_s(tl):
    """1 quadro no fps da timeline."""
    return 1.0 / float(tl["relogio"]["fps"])


def _perto(a, b, lim):
    return abs(float(a) - float(b)) <= lim + 1e-6


def _fmt(x):
    return f"{float(x):.3f}s"


def _intervalos(o_que, nossos, deles, lim, rotulo_deles):
    """Falhas entre duas listas de (s, e): número diferente ou borda além de 1 quadro."""
    if len(nossos) != len(deles):
        return [f"{o_que}: a timeline tem {len(nossos)}, {rotulo_deles} tem {len(deles)}"]
    falhas = []
    for k, ((s1, e1), (s2, e2)) in enumerate(zip(nossos, deles)):
        if not (_perto(s1, s2, lim) and _perto(e1, e2, lim)):
            falhas.append(f"{o_que} {k}: timeline {_fmt(s1)}-{_fmt(e1)}, {rotulo_deles} {_fmt(s2)}-{_fmt(e2)} "
                          f"(diferença de {max(abs(s1 - s2), abs(e1 - e2)):.3f}s, limite 1 quadro = {lim:.3f}s)")
    return falhas


def checar(tl, *, ritmo, timing, prancha, janelas, sha_alinhamento, dur_footage=None, dur_overlay=None):
    """Lista de falhas (vazia = mesmo relógio). Todos os argumentos já lidos dos arquivos."""
    lim = limite_s(tl)
    a0, fim = tl["relogio"]["a0"], tl["duracao_s"]
    falhas = []
    if sha_alinhamento != tl["fontes"]["alinhamento_sha256"]:
        falhas.append("alinhamento: o arquivo em disco não é o que a timeline cita (sha256 diferente): a fala foi "
                      "transcrita ou alinhada de novo depois da timeline")

    segs, plano = tl["segmentos"], ritmo.get("segs", [])
    if len(segs) != len(plano):
        falhas.append(f"plano da footage: a timeline tem {len(segs)} planos, o _ritmo.json tem {len(plano)}")
    else:
        for k, (a, b) in enumerate(zip(segs, plano)):
            tipo_b = TIPO_DO_PLANO.get(b.get("tipo"), b.get("tipo"))
            if a["tipo"] != tipo_b or a.get("layout") != b.get("layout"):
                falhas.append(f"plano da footage {k}: timeline {a['tipo']}/{a.get('layout')}, "
                              f"_ritmo.json {tipo_b}/{b.get('layout')}")
            elif not (_perto(a["s"], b["s"], lim) and _perto(a["e"], b["e"], lim)):
                falhas.append(f"plano da footage {k}: timeline {_fmt(a['s'])}-{_fmt(a['e'])}, _ritmo.json "
                              f"{_fmt(b['s'])}-{_fmt(b['e'])} (limite 1 quadro = {lim:.3f}s)")

    if not _perto(timing["a0"], a0, lim):
        falhas.append(f"footage: começa em {_fmt(timing['a0'])} e a timeline em {_fmt(a0)}")
    if not _perto(timing["total"], fim, lim):
        falhas.append(f"footage: acaba em {_fmt(timing['total'])} e a timeline em {_fmt(fim)}")

    falhas += _intervalos("janela de split", TC.janelas_split(tl),
                          [(j["s"], j["e"]) for j in janelas.get("segs", [])], lim, "o overlay")
    falhas += _intervalos("bloco", TC.spans(tl), [(b["s"], b["e"]) for b in prancha.get("blocos", [])], lim,
                          "a prancha do overlay")

    dur_tl = fim - a0
    ovl_tl = TC.duracao_do_overlay(tl)
    dur_ovl = float(prancha["total"]) - a0
    dur_ft = float(timing["total"]) - float(timing["a0"])
    if not _perto(prancha["total"], ovl_tl, lim):
        falhas.append(f"duração do overlay: {_fmt(prancha['total'])}, a timeline diz {_fmt(ovl_tl)} (o fim da "
                      f"footage, {_fmt(fim)}, mais a folga de cauda)")
    falhas += _cauda("timing.json", dur_ovl, dur_ft, lim)
    if dur_footage is not None:
        if not _perto(dur_footage, dur_tl, lim):
            falhas.append(f"duração medida da footage: {_fmt(dur_footage)}, a timeline diz {_fmt(dur_tl)}")
        falhas += _cauda("footage medida", dur_ovl, dur_footage, lim)
    if dur_overlay is not None:
        mov = float(dur_overlay) - a0
        if not _perto(mov, ovl_tl - a0, lim):
            falhas.append(f"duração medida do overlay: {_fmt(dur_overlay)} ({_fmt(mov)} depois de -a0), a timeline "
                          f"diz {_fmt(ovl_tl - a0)}")
        falhas += _cauda("overlay medido", mov, dur_footage if dur_footage is not None else dur_ft, lim)
    return falhas


def _cauda(o_que, overlay, footage, lim):
    """Pelo menos 1 quadro de overlay (deslocado de -a0) depois do último quadro da footage."""
    if overlay - footage >= lim - 1e-6:
        return []
    return [f"cauda ({o_que}): o overlay deslocado de -a0 acaba em {_fmt(overlay)} e a footage em {_fmt(footage)} "
            f"(folga {overlay - footage:+.3f}s, mínimo 1 quadro = {lim:.3f}s): o composite (shortest=1) cortaria a "
            "imagem e o áudio seguiria"]


def mp4_da_footage(caminho_ritmo):
    """A footage que gravou este `_ritmo.json` (`<nome>_ritmo.json` -> `<nome>.mp4`), se existe; senão None."""
    p = Path(caminho_ritmo)
    if not p.name.endswith("_ritmo.json"):
        return None
    mp4 = p.with_name(p.name[:-len("_ritmo.json")] + ".mp4")
    return mp4 if mp4.is_file() else None


def medir_duracao_video(caminho):
    """Duração do VÍDEO (stream v:0) pelo ffprobe, em segundos: é o que o composite (shortest=1) enxerga."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration",
                        "-of", "default=nw=1:nk=1", str(caminho)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise InsumoInvalido(f"o ffprobe não mediu o vídeo de {caminho}: {(r.stderr or '').strip()[-200:]}")


def medir_duracao(caminho):
    """Duração do arquivo pelo ffprobe (segundos)."""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                        "default=nw=1:nk=1", str(caminho)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise InsumoInvalido(f"o ffprobe não mediu {caminho}: {(r.stderr or '').strip()[-200:]}")


def _json(caminho, o_que):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except OSError as e:
        raise InsumoInvalido(f"{o_que} ilegível ({caminho}): {e.strerror or e}")
    except ValueError as e:
        raise InsumoInvalido(f"{o_que} com JSON inválido ({caminho}): {e}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="gate_relogio.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--timeline", required=True)
    ap.add_argument("--footage-ritmo", required=True, help="o <saida>_ritmo.json da footage")
    ap.add_argument("--footage-timing", required=True, help="o timing.json da footage")
    ap.add_argument("--overlay-dir", required=True, help="a pasta do overlay (prancha.json, janelas_split.json)")
    ap.add_argument("--footage-mp4", help="a footage renderizada (padrão: o mp4 ao lado do --footage-ritmo, se "
                                          "existir): mede a duração e a cauda de verdade")
    ap.add_argument("--overlay-mov", help="o overlay renderizado: mede a duração de verdade")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0)
    try:
        try:
            tl = TC.ler(a.timeline)
        except TC.ErroTimeline as e:
            raise InsumoInvalido(str(e))
        ritmo = _json(a.footage_ritmo, "plano da footage")
        timing = _json(a.footage_timing, "timing da footage")
        prancha = _json(Path(a.overlay_dir) / "prancha.json", "prancha.json do overlay")
        janelas = _json(Path(a.overlay_dir) / "janelas_split.json", "janelas_split.json do overlay")
        p_al = TC.raiz_de(a.timeline) / tl["fontes"]["alinhamento"]
        try:
            sha = AL.sha256_arquivo(p_al)
        except OSError as e:
            raise InsumoInvalido(f"alinhamento citado pela timeline ilegível ({p_al}): {e.strerror or e}")
        mp4 = a.footage_mp4 or mp4_da_footage(a.footage_ritmo)
        dur_footage = medir_duracao_video(mp4) if mp4 else None
        dur_overlay = medir_duracao(a.overlay_mov) if a.overlay_mov else None
        falhas = checar(tl, ritmo=ritmo, timing=timing, prancha=prancha, janelas=janelas, sha_alinhamento=sha,
                        dur_footage=dur_footage, dur_overlay=dur_overlay)
    except (InsumoInvalido, KeyError, TypeError) as e:
        print(f"RELOGIO INSUMO INVALIDO: {e}")
        return 2
    if falhas:
        for f in falhas:
            print(f"RELOGIO REPROVA: {f}")
        return 1
    print(f"RELOGIO OK: {len(tl['segmentos'])} planos, {len(tl['janelas_split'])} janela(s) de split e "
          f"{len(tl['blocos'])} blocos no mesmo relógio; duração {tl['duracao_s'] - tl['relogio']['a0']:.3f}s "
          f"(limite 1 quadro = {limite_s(tl):.3f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
