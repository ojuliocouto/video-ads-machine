#!/usr/bin/env python3
"""Versao HORIZONTAL (16:9) do montador a partir do roteiro anotado. Avatar = inputs/avatar_h.mp4"""
import os, re, sys, json, glob, subprocess, unicodedata, difflib
from PIL import Image, ImageDraw
from parser_roteiro import parse

# (migracao 26/08/2026) caminho de projeto agora sai de caminhos.py
from caminhos import DADOS as _D
BASE=str(_D); TMP=os.path.join(BASE,"_tmp_h"); OUTD=os.path.join(BASE,"output")
os.makedirs(TMP,exist_ok=True)
W,H,FPS=1920,1080,30
PK=os.path.expanduser("~/.local/bin/parakeet-mlx")
FONTS=os.path.join(BASE,"fonts")
AVATAR=os.path.join(BASE,"inputs","avatar_h.mp4")
LOGO=os.path.join(BASE,"assets","logo_occ_branca.png")
MASK=os.path.join(BASE,"assets","circle_mask_h.png")
RING=os.path.join(BASE,"assets","circle_ring_h.png")
DARK="0x141210"
PIP=230; PIPX=48; PIPY=48   # PiP circular do Thales (canto sup esq)
INSERTS={
  "banco de skills": {"file":os.path.join(BASE,"inserts","banco_skills_h.mp4"),"start":0,"speed":1.0},
  "imers":           {"file":os.path.join(BASE,"inserts","imersao.mp4"),"start":3,"speed":1.5},
}
def run(c):
    r=subprocess.run(c,capture_output=True,text=True)
    if r.returncode!=0: print("ERRO:"," ".join(c[:5]),"\n",r.stderr[-700:]); sys.exit(1)
    return r
def norm(w):
    w=unicodedata.normalize("NFD",w.lower()); return re.sub(r"[^\w]","","".join(c for c in w if unicodedata.category(c)!="Mn"))
def clean_display(t):
    for a,b_ in [("Cláude","Claude"),("Côde","Code"),("IÁ","IA"),("IÃ","IA"),("I.A","IA")]: t=t.replace(a,b_)
    return t
STOP={"e","ou","de","do","da","dos","das","que","o","a","os","as","no","na","nos","nas",
      "um","uma","com","por","pra","para","em","ao","mas","se","ate","sua","seu","seus","suas"}
def smart_lines(tokens, maxc):
    lines=[[]]; ln=0
    for clean,styled in tokens:
        add=len(clean)+(1 if lines[-1] else 0)
        if lines[-1] and ln+add>maxc:
            lines.append([]); ln=0; add=len(clean)
        lines[-1].append((clean,styled)); ln+=add
    for _ in range(3):
        for i in range(len(lines)-1):
            if lines[i] and lines[i][-1][0].lower().strip(".,!?…") in STOP and len(lines[i])>1:
                lines[i+1].insert(0,lines[i].pop())
    return "\\N".join(" ".join(s for _,s in L) for L in lines if L)
def find_insert(instr):
    s=instr.lower()
    for k,v in INSERTS.items():
        if k in s: return v
    return list(INSERTS.values())[0]

def align(avatar, narr_words):
    wav=os.path.join(TMP,"av.wav"); run(["ffmpeg","-y","-i",avatar,"-vn","-ac","1","-ar","16000",wav])
    run([PK,wav,"--output-format","json","--output-dir",TMP])
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
        if nw: pk.append([s,e]);
        else: pk[-1][1]=e
    words=[]
    for i in range(len(narr_words)):
        j=min(int(i*len(pk)/len(narr_words)),len(pk)-1) if pk else 0
        words.append((pk[j][0], pk[j][1], narr_words[i]) if pk else (i*0.4,i*0.4+0.4,narr_words[i]))
    return words

def r_orig(s,e,out):
    vf=(f"scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,"
        f"zoompan=z='min(zoom+0.0009,1.25)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},setsar=1")
    run(["ffmpeg","-y","-ss",str(s),"-t",str(e-s),"-i",AVATAR,"-vf",vf,"-r",str(FPS),"-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",out])
def r_insert(cfg,s,e,out):
    d=e-s; src=cfg["file"]; sp=cfg.get("speed",1.0); st=cfg.get("start",0); take=d*sp
    fc=(f"[0:v]setpts=PTS/{sp},split=2[i1][i2];"
        f"[i1]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=24:1,setsar=1[bg];"
        f"[i2]scale={W}:{H}:force_original_aspect_ratio=decrease,setsar=1[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
        f"[1:v]scale={PIP}:{PIP}:force_original_aspect_ratio=increase,crop={PIP}:{PIP},setsar=1[sq];"
        f"[sq][2:v]alphamerge[pip];"
        f"[base][pip]overlay={PIPX}:{PIPY}[wp];"
        f"[wp][3:v]overlay={PIPX-8}:{PIPY-8}[v]")
    run(["ffmpeg","-y","-ss",str(st),"-t",str(take),"-i",src,"-ss",str(s),"-t",str(d),"-i",AVATAR,
         "-i",MASK,"-i",RING,"-filter_complex",fc,"-r",str(FPS),"-map","[v]","-map","1:a:0",
         "-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac","-t",str(d),out])
def r_logo(s,e,out):
    d=e-s
    run(["ffmpeg","-y","-f","lavfi","-t",str(d),"-i",f"color={DARK}:s={W}x{H}","-i",LOGO,
         "-ss",str(s),"-t",str(d),"-i",AVATAR,"-filter_complex",
         f"[1:v]scale=1100:-1[lg];[0:v][lg]overlay=(W-w)/2:(H-h)/2[v]",
         "-map","[v]","-map","2:a:0","-r",str(FPS),"-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac","-t",str(d),out])
def r_lettering(text,s,e,out,withlogo=False):
    d=e-s; text=clean_display(text)
    def ts(x): return f"{int(x//3600)}:{int((x%3600)//60):02d}:{x%60:05.2f}"
    words=text.split(); tokens=[]
    for w in words:
        clean=re.sub(r"[^\wÀ-ÿ'\-!?…,.]","",w)
        styled="{\\c&H00FFFF&}"+clean+"{\\c&HFFFFFF&}" if (clean.isupper() and len(clean)>1) else clean
        tokens.append((clean,styled))
    body=smart_lines(tokens, 30)
    ass=os.path.join(TMP,f"let_{abs(hash(text))%9999}.ass")
    head=("[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV\n"
        "Style: L, Anton, 88, &H00FFFFFF, &H00000000, &H00000000, 0, 0, 1, 7, 4, 5, 120, 120, 0\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, Effect, Text\n"
        f"Dialogue: 0,{ts(0)},{ts(d)},L,,0,0,0,{{\\fad(200,0)}}{body}\n")
    open(ass,"w").write(head)
    # lettering "na tela" = SOBRE o avatar, com leve escurecimento pra legibilidade.
    zp=(f"scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,"
        f"zoompan=z='min(zoom+0.0006,1.12)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},setsar=1,"
        f"drawbox=x=0:y=0:w={W}:h={H}:color=black@0.45:t=fill")
    inputs=["-ss",str(s),"-t",str(d),"-i",AVATAR]; amap="0:a:0"
    fc=f"[0:v]{zp},subtitles={ass}:fontsdir={FONTS}[v]"
    if withlogo:
        inputs=["-ss",str(s),"-t",str(d),"-i",AVATAR,"-i",LOGO]; amap="0:a:0"
        fc=(f"[0:v]{zp},subtitles={ass}:fontsdir={FONTS}[bgt];[1:v]scale=520:-1[lg];"
            f"[bgt][lg]overlay=(W-w)/2:H-h-90[v]")
    run(["ffmpeg","-y",*inputs,"-filter_complex",fc,"-map","[v]","-map",amap,"-r",str(FPS),"-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac","-t",str(d),out])

blocks=parse(os.path.join(BASE,"inputs","ad34_leva3.txt"))
narr_words=[]
for bk in blocks: narr_words += bk["narr"].split()
words=align(AVATAR, narr_words)
spans=[]; idx=0
for bk in blocks:
    n=len(bk["narr"].split()); seg=words[idx:idx+n] if n else words[idx:idx+1]; idx+=n
    s=seg[0][0] if seg else (spans[-1][1] if spans else 0); e=seg[-1][1] if seg else s+0.8
    if e<=s: e=s+0.6
    spans.append((s,e))
total=words[-1][1]; print(f"{len(blocks)} blocos | total {total:.1f}s")
segs=[]
for i,(bk,(s,e)) in enumerate(zip(blocks,spans)):
    out=os.path.join(TMP,f"s{i:02d}.mp4")
    if bk["type"]=="orig": r_orig(s,e,out)
    elif bk["type"]=="insert": r_insert(find_insert(bk["instr"]),s,e,out)
    elif bk["type"]=="logo": r_logo(s,e,out)
    elif bk["type"]=="lettering": r_lettering(bk["narr"],s,e,out)
    elif bk["type"]=="lettering_logo": r_lettering(bk["narr"],s,e,out,withlogo=True)
    segs.append(out); print(f"  {i:2d} {bk['type']:14} {s:5.1f}-{e:5.1f}s ok")
lst=os.path.join(TMP,"list.txt"); open(lst,"w").write("".join(f"file '{x}'\n" for x in segs))
out=os.path.join(OUTD,"ad34_horizontal.mp4")
run(["ffmpeg","-y","-f","concat","-safe","0","-i",lst,"-c:v","libx264","-pix_fmt","yuv420p","-r",str(FPS),"-c:a","aac",out])
print("PRONTO:",out)
