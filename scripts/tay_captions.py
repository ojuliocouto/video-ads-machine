#!/usr/bin/env python3
"""Gera a legenda estilo tay.ldantas (1 palavra por vez, minuscula, branca Nunito, halo escuro sutil)
e queima na base limpa. ROBUSTO: layout sequencial que GARANTE zero sobreposicao e duracao minima
por palavra, mesmo com glitch de alinhamento do Parakeet (ex: "20 mil" sai fora de ordem).

Bug que isso previne: se a alinhadora devolve tempos nao-monotonicos, o "preenche ate a proxima"
ingênuo faz a janela de uma palavra cruzar com a da outra e as duas aparecem juntas (ex: "p20r").
Aqui cada palavra e disposta em sequencia: start nunca antes do fim da anterior, fim >= start+MIN.

Uso: python3 tay_captions.py <base_sem_legenda.mp4> <saida.mp4>
"""
import os,re,json,glob,unicodedata,difflib,subprocess,sys
from parser_roteiro import parse
from caption_styles import STYLES, DEFAULT, build_ass, build_ass_editorial

# (migracao 26/08/2026) caminho de projeto agora sai de caminhos.py
from caminhos import DADOS as _D
BASE=str(_D); TMP=os.path.join(BASE,"_tmp_rot"); FONTS=os.path.join(BASE,"fonts")
Y=1410            # posicao vertical (sobre o peito, estilo tay)
FSZ=122           # Nunito
MIN_DUR=0.22      # duracao minima por palavra (reel-time, pre-1.2x) -> ~0.18s no final
MAX_LAG=0.6       # se a legenda atrasar mais que isso da fala, encolhe MIN pra recuperar
HOLD_MAX=0.45     # duracao maxima de uma palavra apos a fala (evita legenda "travar" na pausa)

def _norm(w):
    w=unicodedata.normalize("NFD",w.lower()); return re.sub(r"[^\w]","","".join(c for c in w if unicodedata.category(c)!="Mn"))

def _clean(w):
    w=w.strip(); w=re.sub(r"[,\.;:]+$","",w)   # tira virgula/ponto/; finais; mantem ? e !
    return w.lower()

def aligned_words():
    """Retorna [(palavra_limpa, start_reel, end_reel)] com layout sequencial sem overlap."""
    _timing=json.load(open(os.path.join(BASE,"output","timing.json")))
    a0=_timing["a0"]
    audio_dur=float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
        "-of","default=nw=1:nk=1",_timing["avatar"]],capture_output=True,text=True).stdout.strip())
    d=json.load(open(glob.glob(os.path.join(TMP,"av.json"))[0])); raw=[]
    def grab(o):
        if isinstance(o,dict):
            if 'tokens' in o and isinstance(o['tokens'],list):
                for t in o['tokens']: raw.append((float(t['start']),float(t['end']),t.get('text','')))
            for v in o.values(): grab(v)
        elif isinstance(o,list): [grab(v) for v in o]
    grab(d); raw.sort()
    pk=[]
    for s,e,txt in raw:
        nw=txt.startswith(' ') or not pk; c=txt.strip()
        if not c: continue
        if nw: pk.append([s,e,c])
        else: pk[-1][1]=e; pk[-1][2]+=c
    blocks=parse(os.environ.get("VAM_ROTEIRO", os.path.join(BASE,"inputs","ad34_leva3.txt")))
    narr=[]
    for b in blocks: narr+=b["narr"].split()
    pk_norm=[_norm(c) for *_,c in pk]; sn=[_norm(w) for w in narr]
    sm=difflib.SequenceMatcher(None,pk_norm,sn,autojunk=False)
    times=[None]*len(narr)
    for a,b,size in sm.get_matching_blocks():
        for k in range(size): times[b+k]=(pk[a+k][0],pk[a+k][1])
    # cauda final sem casamento (parakeet as vezes nao reconhece as ultimas palavras): ancora
    # no fim REAL do audio em vez de deixar a interpolacao +0.18s/palavra cortar a legenda antes
    # do fim da fala (mesmo bug do produzir_roteiro.py, corrigido la tambem).
    if times and times[-1] is None:
        times[-1]=(max(0.0,audio_dur-0.05), audio_dur)
    last=None
    for i in range(len(times)):
        if times[i] is None:
            nxt=next((times[j] for j in range(i+1,len(times)) if times[j]),None)
            if last and nxt and nxt[0]>last[1]: times[i]=(last[1],nxt[0])
            elif last: times[i]=(last[1],last[1]+0.18)
            elif nxt: times[i]=(max(0,nxt[0]-0.18),nxt[0])
            else: times[i]=(i*0.3,i*0.3+0.3)
        last=times[i]
    # starts cruas em reel-time
    raws=[(_clean(w), times[i][0]-a0, times[i][1]-a0) for i,w in enumerate(narr)]
    raws=[(w,s,e) for (w,s,e) in raws if w]
    # BLANK: cenas de lettering serif ja tem o texto baked -> tira a legenda tay ali (timing.json letterings, avatar-time).
    # Cena de ABERTURA (range comeca em ~0): as 1as palavras podem ter reel-time NEGATIVO (av.json antes do a0),
    # entao pega tudo <= fim do range. Cenas do meio: margem justa pra nao blankar palavra da cena vizinha.
    _lets=[(l["s"]-a0, l["e"]-a0) for l in json.load(open(os.path.join(BASE,"output","timing.json"))).get("letterings",[])]
    def _in_lett(s):
        for ls, le in _lets:
            if ls <= 0.10:
                if s <= le+0.02: return True
            elif ls-0.05 <= s <= le+0.02:
                return True
        return False
    if _lets:
        raws=[(w,s,e) for (w,s,e) in raws if not _in_lett(s)]
    # bordas de entrada de cada cena de lettering (reel-time): a ULTIMA palavra ANTES de uma cena
    # de lettering nao pode ter seu fim esticado (HOLD_MAX) pra DENTRO da janela de blank seguinte,
    # senao a legenda tay fica sobreposta ao texto baked do lettering (ex: "pelo..." em cima de
    # "CLAUDE"). So importa cena de lettering no MEIO do video: a do FIM nao tem "proxima palavra
    # normal" depois, entao o filtro _in_lett ja remove tudo ate o final e nunca sobra o que esticar.
    _lett_starts=sorted(ls for ls,le in _lets if ls > 0.10)
    # LAYOUT SEQUENCIAL: nunca antes do cursor, fim = max(start+MIN, proxima_start_crua), sem overlap
    out=[]; cursor=0.0
    for idx,(w,s_raw,e_raw) in enumerate(raws):
        s=max(s_raw, cursor)
        nxt_raw = raws[idx+1][1] if idx+1<len(raws) else max(e_raw, s+MIN_DUR)
        mind = MIN_DUR
        if s - s_raw > MAX_LAG: mind=0.14   # atrasou demais: encolhe pra recuperar sync
        # fim = ate a proxima palavra, MAS no maximo HOLD_MAX apos a fala (nao "trava" na pausa,
        # some no silencio -> nao sobrepoe cena de lettering nem congela na tela).
        e=max(s+mind, min(nxt_raw, e_raw + HOLD_MAX))
        # nunca esticar pra dentro da proxima cena de lettering (blank window a frente de s)
        prox_lett = next((ls for ls in _lett_starts if ls > s), None)
        if prox_lett is not None and prox_lett < e:
            e = max(s + mind, prox_lett)
        out.append((w, round(s,3), round(e,3)))
        cursor=e
    # VALIDACAO: zero overlap (assercao dura)
    for i in range(len(out)-1):
        assert out[i][2] <= out[i+1][1] + 1e-6, f"OVERLAP {out[i]} x {out[i+1]}"
        assert out[i][2] > out[i][1], f"DUR<=0 em {out[i]}"
    return out

def _ts(x): return f"{int(x//3600)}:{int((x%3600)//60):02d}:{x%60:05.2f}"

def burn(base_in, out, ass):
    r=subprocess.run(["ffmpeg","-y","-i",base_in,"-vf",
      f"subtitles={ass}:fontsdir={FONTS},colorspace=all=bt709:iall=bt709:fast=1",
      "-c:v","libx264","-crf","18","-pix_fmt","yuv420p",
      "-colorspace","bt709","-color_primaries","bt709","-color_trc","bt709","-color_range","tv",
      "-c:a","copy","-movflags","+faststart",out],
      capture_output=True,text=True)
    if r.returncode!=0: print("ERRO ffmpeg\n",r.stderr[-1200:]); sys.exit(1)
    return out

if __name__=="__main__":
    # Uso: python3 tay_captions.py <base.mp4> <saida.mp4> [--style NOME] [--format 9x16|1x1]
    args=[a for a in sys.argv[1:] if not a.startswith("--")]
    base_in=args[0]; out=args[1]
    style=DEFAULT
    if "--style" in sys.argv:
        style=sys.argv[sys.argv.index("--style")+1]
    fmt="9x16"
    if "--format" in sys.argv:
        fmt=sys.argv[sys.argv.index("--format")+1]
    if style != "editorial" and style not in STYLES:
        print(f"estilo '{style}' nao existe. disponiveis: editorial, {', '.join(STYLES)}"); sys.exit(1)
    words=aligned_words()
    print(f"estilo: {style} | formato: {fmt} | palavras: {len(words)} | overlaps: 0 (validado) | min_dur={MIN_DUR}s")
    if style == "editorial":
        # estilo reelC v7 (HyperFrames) validado pela Jheni. Hook fixado opcional via env.
        hook_text = os.environ.get("VAM_HOOK_TEXT") or None
        hook_end = float(os.environ.get("VAM_HOOK_END", "0"))
        ass=build_ass_editorial(words, fmt=fmt, hook_text=hook_text, hook_end=hook_end)
    else:
        ass=build_ass(words,style,fmt=fmt)
    burn(base_in,out,ass)
    print("OK",out)
