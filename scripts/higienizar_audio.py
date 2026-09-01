#!/usr/bin/env python3
"""Higieniza a VOZ REAL antes do avatar: encurta SO os SILENCIOS GRANDES (pausas de respiracao),
mantendo os gaps/pausas naturais. Passo OBRIGATORIO do pipeline (voz -> aqui -> avatar).

Por que: o Thales grava a voz e PARA pra respirar entre frases (pausas de 0.5-2s com o som do
respiro). Isso precisa sair pro anuncio ficar dinamico e sem respiro. Mas as pausas naturais
curtas (< ~0.5s) NAO podem sair (senao "picota" e fica robotico).

Como (evolucao 11/07/2026): a deteccao por TRANSCRICAO (parakeet OU whisper) nao serve, os
timestamps de fim de palavra sao curtos demais e alguns silencios grandes escapam. A deteccao
DEFINITIVA e por ENERGIA (ffmpeg silencedetect) = ground truth das pausas reais. O whisper entra
so como conferencia (transcricao no report). Passos:
  1. silencedetect (noise=SIL_DB) acha as regioes de silencio (pausas), com o respiro incluido.
  2. SO nas pausas > BIG_SIL (silencio grande) corta o MEIO deixando KEEP_PAUSE. Corte dentro do
     silencio = nunca corta palavra. Poucos cortes = zero picotado.
  3. apara silencio morto nas pontas (entrada/saida).
  4. micro-fade nas emendas.

Uso: python3 higienizar_audio.py <voz.mp3> [saida.mp3]
Env (s): BIG_SIL=0.55  KEEP_PAUSE=0.26  SIL_DB=-30  MINDET=0.28
         LEAD_KEEP=0.12  TRAIL_KEEP=0.30  FADE=0.012
"""
import os, sys, re, subprocess

BIG_SIL    = float(os.environ.get("BIG_SIL", 0.55))   # silencio > isso = pausa de respiracao -> encurta
KEEP_PAUSE = float(os.environ.get("KEEP_PAUSE", 0.26)) # piso: pausa natural que sobra (pausas curtas)
# TETO DA PAUSA EXPRESSO NO TEMPO DA TELA, nao no do arquivo (17/08/2026).
# Erro que isso corrige: eu calibrava o teto no audio original e esquecia que o video
# e ACELERADO depois. Com teto de 1,20s e aceleracao 1.35x, uma pausa aparecia com
# 0,89s na tela, e o Julio ouviu como "ele para pra respirar" aos 0:12. O que o
# espectador percebe e a pausa DEPOIS da aceleracao, entao o parametro passa a ser
# essa, e o teto no arquivo sai da conta.
PAUSA_MAX_TELA = float(os.environ.get("PAUSA_MAX_TELA", 0.60))
ACCEL_FINAL    = float(os.environ.get("ACCEL_FINAL", 1.35))
KEEP_PAUSE_MAX = float(os.environ.get("KEEP_PAUSE_MAX", PAUSA_MAX_TELA * ACCEL_FINAL))
KEEP_PAUSE_RATIO = float(os.environ.get("KEEP_PAUSE_RATIO", 0.20)) # fatia da pausa ORIGINAL que fica
SIL_DB     = float(os.environ.get("SIL_DB", -36))      # limiar de silencio (respiro fica abaixo disso)
# Distancia minima entre o corte e a borda do silencio detectado. Ver comentario no
# ponto do corte: sem isso o corte comia o comeco/fim das palavras vizinhas.
MARGEM_FALA = float(os.environ.get("MARGEM_FALA", 0.14))
MINDET     = float(os.environ.get("MINDET", 0.28))     # duracao minima de silencio pro detector
LEAD_KEEP  = float(os.environ.get("LEAD_KEEP", 0.12))
TRAIL_KEEP = float(os.environ.get("TRAIL_KEEP", 0.30))
FADE       = float(os.environ.get("FADE", 0.012))

def run(cmd, err=""):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ERRO {err}\n{r.stderr[-800:]}")
    return r

def dur(f):
    o = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
        "-of","default=nw=1:nk=1", f], capture_output=True, text=True).stdout.strip()
    return float(o)

MERGE_GAP = float(os.environ.get("MERGE_GAP", 0.08))   # gaps <= isso entre 2 silencios = 1 pausa so

def silences(mp3):
    """Regioes de silencio (start,end) via ffmpeg silencedetect (ground truth por energia).
    Duas regioes quase coladas (gap <= MERGE_GAP, ex: um blip de amostra cruzando o limiar
    de dB por uma fracao de frame) sao MESCLADAS antes de qualquer corte: senao cada uma vira
    um cut independente que so deixa KEEP_PAUSE na sua propria borda, e a pausa combinada no
    audio final fica maior que qualquer BIG_SIL/KEEP_PAUSE isolado (silencio residual escapa
    do gate sem_respiro_grande do vam_build.py)."""
    r = subprocess.run(["ffmpeg","-i",mp3,"-af",f"silencedetect=noise={SIL_DB}dB:d={MINDET}","-f","null","-"],
                       capture_output=True, text=True)
    raw = []; start = None
    for line in r.stderr.splitlines():
        m = re.search(r"silence_start:\s*(-?\d+\.?\d*)", line)
        if m: start = float(m.group(1)); continue
        m = re.search(r"silence_end:\s*(-?\d+\.?\d*)", line)
        if m and start is not None:
            raw.append((max(0.0, start), float(m.group(1)))); start = None
    out = []
    for s, e in raw:
        if out and s - out[-1][1] <= MERGE_GAP:
            out[-1] = (out[-1][0], e)
        else:
            out.append((s, e))
    return out

def whisper_words(mp3):
    """So pra conferencia (nao dirige o corte). Se faltar faster-whisper, retorna []."""
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(os.environ.get("WHISPER_SIZE","small"), device="cpu", compute_type="int8")
        segs, _ = model.transcribe(mp3, language="pt", word_timestamps=True, vad_filter=False)
        return [(w.start, w.end, w.word.strip()) for s in segs if s.words for w in s.words]
    except Exception:
        return []

def word_at(words, t):
    for s, e, w in words:
        if s <= t <= e: return w
    # palavra mais proxima antes
    prev = [w for s,e,w in words if e <= t]
    return prev[-1] if prev else "?"

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = os.path.abspath(sys.argv[1])
    out = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else \
          os.path.splitext(src)[0] + "_clean.mp3"
    total = dur(src)
    sils = silences(src)
    words = whisper_words(src)   # conferencia

    cuts = []; report = []
    for s, e in sils:
        d = e - s
        if s <= 0.06:                       # silencio de ENTRADA
            if e - LEAD_KEEP > 0.05:
                cuts.append((0.0, round(e - LEAD_KEEP, 3)))
                report.append(f"  trim entrada {e-LEAD_KEEP:.2f}s")
            continue
        if e >= total - 0.06:               # silencio de SAIDA
            if total - (s + TRAIL_KEEP) > 0.05:
                cuts.append((round(s + TRAIL_KEEP, 3), total))
                report.append(f"  trim saida {total-(s+TRAIL_KEEP):.2f}s")
            continue
        if d > BIG_SIL:                      # SILENCIO GRANDE (respiracao) -> encurta o meio
            # pausa que sobra escala com o tamanho ORIGINAL (piso KEEP_PAUSE, teto KEEP_PAUSE_MAX):
            # pausa curta (0.6s) fica quase igual a antes, mas uma pausa de 3s nao pode virar um
            # corte seco de 0.26s (92% de compressao soa violento mesmo sem estourar amostra).
            keep = min(KEEP_PAUSE_MAX, max(KEEP_PAUSE, d * KEEP_PAUSE_RATIO))
            cut_len = d - keep
            mid = (s + e) / 2
            a = round(mid - cut_len/2, 3); b = round(mid + cut_len/2, 3)
            # MARGEM DE SEGURANCA (17/08/2026, defeito ouvido pelo Julio): o
            # silencedetect marca como silencio tambem a cauda fraca de uma palavra
            # (fricativa, vogal final baixa). Com o corte centrado, a BORDA caia dentro
            # da fala e comia pedaco: "uma campanha" virou "panha", "vender" virou
            # "ver", e "algo" sumiu inteiro. Nunca cortar perto da borda do silencio.
            a = max(a, round(s + MARGEM_FALA, 3))
            b = min(b, round(e - MARGEM_FALA, 3))
            if b - a < 0.06:                 # sobrou margem de menos: nao corta
                continue
            cuts.append((a, b))
            ctx = f"[{word_at(words,s)!r}->{word_at(words,e+0.01)!r}]" if words else ""
            report.append(f"  silencio grande {d:.2f}s em {s:.2f}-{e:.2f}s {ctx} -> corta {b-a:.2f}s (pausa fica {d-(b-a):.2f}s)")

    if not cuts:
        run(["ffmpeg","-y","-i",src,"-c","copy",out], "copy")
        print(f"nenhum silencio grande (> {BIG_SIL}s). copiado -> {out}"); return

    keeps = []; cur = 0.0
    for a, b in sorted(cuts):
        if a > cur: keeps.append((cur, a))
        cur = max(cur, b)
    if cur < total: keeps.append((cur, total))
    parts, labels = [], []
    for idx, (a, b) in enumerate(keeps):
        dd = b - a; lbl = f"k{idx}"
        parts.append(f"[0:a]atrim={a}:{b},asetpts=N/SR/TB,"
                     f"afade=t=in:st=0:d={FADE},afade=t=out:st={max(0,dd-FADE):.3f}:d={FADE}[{lbl}]")
        labels.append(f"[{lbl}]")
    fc = ";".join(parts) + ";" + "".join(labels) + f"concat=n={len(keeps)}:v=0:a=1[o]"
    run(["ffmpeg","-y","-i",src,"-filter_complex",fc,"-map","[o]",
         "-c:a","libmp3lame","-b:a","192k",out], "concat")

    removed = sum(b - a for a, b in cuts)
    print(f"=== HIGIENIZACAO (silencedetect {SIL_DB}dB, so silencios > {BIG_SIL}s): {os.path.basename(src)} ===")
    for r in report: print(r)
    print(f"cortes: {len(cuts)} | removido {removed:.2f}s | {total:.2f}s -> {dur(out):.2f}s")
    print(f"OUT: {out}")

if __name__ == "__main__":
    main()
