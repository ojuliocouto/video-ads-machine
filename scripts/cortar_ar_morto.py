#!/usr/bin/env python3
"""Corta ar morto de take BRUTO de talking-head (pessoa real, sem avatar).

Nao confundir com o resto do pipeline: `auditar_audio.py` prepara audio pra gerar
avatar no HeyGen; `aparar_pausa.py` apara UMA pausa de um ad ja pronto. Este aqui
pega o take cru, de camera, e monta o corte inteiro.

    # so planejar (imprime e salva os segmentos, nao renderiza)
    python3 cortar_ar_morto.py take.mov

    # planejar e renderizar, com o gate de conferencia
    python3 cortar_ar_morto.py take.mov --saida cortado.mp4

    # reaproveitar transcricao ja feita (nao roda o parakeet de novo)
    python3 cortar_ar_morto.py take.mov --json bruto.json --saida cortado.mp4

    # afrouxar/apertar
    python3 cortar_ar_morto.py take.mov --respiro 0.20 --piso-db -30

O GATE e obrigatorio quando renderiza: transcreve o resultado, compara palavra a
palavra com o bruto e SAI COM ERRO se sumiu conteudo. Sem isso o corte parece
bom, o video roda, e a palavra comida so aparece quando alguem assiste. Ja
aconteceu (v1 comeu "voce nao comprou" de um anuncio inteiro).
"""
import argparse, array, json, math, os, re, shutil, subprocess, sys, tempfile, wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ar_morto import PADRAO, blocos_de_fala, planejar_cortes, segmentos_manter

JAN = 0.02


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=isinstance(cmd, str), check=True,
                          capture_output=True, text=True, **kw)


def duracao(path):
    out = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "default=nw=1:nk=1", path]).stdout.strip()
    return float(out)


def extrair_wav(src, dst):
    sh(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-ac", "1",
        "-ar", "16000", "-acodec", "pcm_s16le", dst])


def curva_db(wav_path, jan=JAN):
    """dB por janela, relativo ao pico. Sem audioop (sumiu no Python 3.13)."""
    w = wave.open(wav_path, "rb")
    if w.getsampwidth() != 2 or w.getnchannels() != 1:
        raise SystemExit("esperava wav mono 16-bit (use extrair_wav)")
    sr = w.getframerate()
    amostras = array.array("h")
    amostras.frombytes(w.readframes(w.getnframes()))
    n = int(sr * jan)
    rms = []
    for i in range(0, len(amostras) - n, n):
        soma = 0
        for v in amostras[i:i + n]:
            soma += v * v
        rms.append(math.sqrt(soma / n))
    pico = max(rms) if rms else 1.0
    if pico <= 0:
        pico = 1.0
    return [20 * math.log10(v / pico) if v > 0 else -99.0 for v in rms]


def transcrever(wav_path, saida_dir):
    """parakeet-mlx em json (token a token). Whisper esta proibido nesta casa."""
    if not shutil.which("parakeet-mlx"):
        raise SystemExit("parakeet-mlx nao encontrado no PATH")
    sh(["parakeet-mlx", wav_path, "--output-format", "json",
        "--output-dir", saida_dir])
    base = os.path.splitext(os.path.basename(wav_path))[0]
    return os.path.join(saida_dir, base + ".json")


def tokens_de(json_path):
    d = json.load(open(json_path))
    return [(t["start"], t["end"], t["text"])
            for s in d.get("sentences", []) for t in s.get("tokens", [])]


def texto_de(json_path):
    return json.load(open(json_path)).get("text", "")


def palavras(txt):
    txt = re.sub(r"[^\wáâãàéêíóôõúüçÁÂÃÀÉÊÍÓÔÕÚÜÇ ]", " ", (txt or "").lower())
    return txt.split()


def filtro_ffmpeg(segs, extra_v="", extra_a=""):
    pv = [f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{i}]"
          for i, (a, b) in enumerate(segs)]
    pa = [f"[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS[a{i}]"
          for i, (a, b) in enumerate(segs)]
    ent = "".join(f"[v{i}][a{i}]" for i in range(len(segs)))
    fc = ";".join(pv + pa + [f"{ent}concat=n={len(segs)}:v=1:a=1[vc][ac]"])
    fc += f";[vc]{extra_v or 'null'}[v];[ac]{extra_a or 'anull'}[a]"
    return fc


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada")
    ap.add_argument("--saida", help="renderiza o corte aqui (e roda o gate)")
    ap.add_argument("--json", dest="json_path", help="transcricao json ja pronta")
    ap.add_argument("--segmentos", help="onde salvar a lista de segmentos")
    ap.add_argument("--filtro-v", default="", help="filtro de video extra (crop, eq...)")
    ap.add_argument("--filtro-a", default="", help="filtro de audio extra (atempo...)")
    for k in ("piso_db", "folga", "respiro", "limiar_corte", "janela_busca"):
        ap.add_argument("--" + k.replace("_", "-"), type=float, default=None)
    ap.add_argument("--sem-gate", action="store_true",
                    help="NAO conferir por re-transcricao (so com motivo escrito)")
    a = ap.parse_args()

    params = {k: getattr(a, k) for k in
              ("piso_db", "folga", "respiro", "limiar_corte", "janela_busca")
              if getattr(a, k) is not None}

    tmp = tempfile.mkdtemp(prefix="ar_morto_")
    wav = os.path.join(tmp, "bruto.wav")
    print(f"extraindo audio de {a.entrada}")
    extrair_wav(a.entrada, wav)
    dur = duracao(a.entrada)

    jpath = a.json_path
    if not jpath:
        print("transcrevendo com parakeet (token a token)")
        jpath = transcrever(wav, tmp)

    toks = tokens_de(jpath)
    blocos = blocos_de_fala(toks)
    print(f"{len(toks)} tokens -> {len(blocos)} blocos de fala | duracao {dur:.2f}s\n")

    db = curva_db(wav)
    cortes = planejar_cortes(blocos, db, JAN, dur, params, log=lambda m: print("  " + m))
    segs = segmentos_manter(cortes, dur)

    cortado = sum(b - a_ for a_, b in cortes)
    print(f"\n{len(segs)} segmentos | {dur:.2f}s -> {dur-cortado:.2f}s "
          f"(cortei {cortado:.2f}s de ar morto, {100*cortado/dur:.1f}%)")
    for s, e in segs:
        print(f"  {s:7.3f} -> {e:7.3f}  ({e-s:.3f}s)")

    if a.segmentos:
        with open(a.segmentos, "w") as f:
            for s, e in segs:
                f.write(f"{s} {e}\n")
        print(f"\nsegmentos salvos em {a.segmentos}")

    if not a.saida:
        return

    print(f"\nrenderizando {a.saida}")
    fc = filtro_ffmpeg(segs, a.filtro_v, a.filtro_a)
    sh(["ffmpeg", "-v", "error", "-y", "-i", a.entrada, "-filter_complex", fc,
        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium",
        "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", a.saida])

    if a.sem_gate:
        print("\nGATE PULADO por --sem-gate. Conteudo NAO conferido.")
        return

    print("\ngate: re-transcrevendo o corte pra conferir que nada sumiu")
    wav2 = os.path.join(tmp, "cortado.wav")
    extrair_wav(a.saida, wav2)
    j2 = transcrever(wav2, tmp)

    pa, pb = palavras(texto_de(jpath)), palavras(texto_de(j2))
    print(f"  bruto: {len(pa)} palavras | cortado: {len(pb)} palavras")
    if len(pb) < len(pa) - 2:
        import difflib
        print("\n  GATE REPROVADO: sumiu conteudo.")
        for tag, i1, i2, j1, j2_ in difflib.SequenceMatcher(None, pa, pb).get_opcodes():
            if tag == "delete":
                print(f"    perdido: {' '.join(pa[i1:i2])!r}")
                print(f"    contexto: ...{' '.join(pa[max(0,i1-5):i2+5])}...")
        print("\n  Afrouxe (--respiro maior, --piso-db mais estrito) e rode de novo.")
        sys.exit(1)
    print("  GATE OK: contagem de palavras preservada.")


if __name__ == "__main__":
    main()
