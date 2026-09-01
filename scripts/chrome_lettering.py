#!/usr/bin/env python3
"""Renderiza UMA cena de lettering chrome (lead Playfair + key DM Serif com espelhado sutil)
sobre talking-head escurecido+vinheta. 3 passes: base sharp + mascara da key + sheen.
Uso: importar render_chrome(lead,key,s,dur,out,withlogo) — AVATAR/REFRAME vem do produzir."""
import os,subprocess,sys,re
# (migracao 26/08/2026) caminho de projeto agora sai de caminhos.py
from caminhos import DADOS as _D
BASE=str(_D); TMP=os.path.join(BASE,"_tmp_chrome"); FONTS=os.path.join(BASE,"fonts")
os.makedirs(TMP,exist_ok=True)
AVATAR=os.path.join(BASE,"inputs","avatar_thales.mp4")
LOGO=os.path.join(BASE,"assets","logo_occ_branca.png")
GRAD=os.path.join(BASE,"_tmp_let","sheen_grad.png")  # gradiente sutil ja gerado
REFRAME="scale=2376:4224:force_original_aspect_ratio=increase,crop=2160:3840:108:652,scale=1080:1920"
W,H,FPS=1080,1920,30
YA,YS=1450,1620   # lead em 1450, key em 1620

def _run(c,err=""):
    r=subprocess.run(c,capture_output=True,text=True)
    if r.returncode!=0: print("ERRO",err,"\n",r.stderr[-900:]); sys.exit(1)
def _ts(x): return f"{int(x//3600)}:{int((x%3600)//60):02d}:{x%60:05.2f}"

_DMFP=os.path.join(FONTS,"DMSerifDisplay.ttf")
def _fit_key_size(key,base=286,maxw=1000):
    # reduz o tamanho da key pra caber em ~maxw px de largura (libass ~ PIL * 1.0 p/ DM Serif)
    try:
        from PIL import ImageFont
        for sz in range(base,120,-6):
            f=ImageFont.truetype(_DMFP,sz)
            w=f.getbbox(key)[2]
            if w<=maxw: return sz
        return 140
    except Exception:
        return base if len(key)<=8 else 190

def _ass(lead,key,d,mask=False,withlogo=False):
    kparts=key.split()
    multi=len(kparts)>=2
    # palavra-chave: 1 palavra grande; 2+ palavras = empilhadas (cada uma grande), nao encolhe
    ksz=190 if multi else _fit_key_size(key)
    lh=ksz-58  # entrelinha justa das keys empilhadas (palavras bem proximas)
    if multi:
        ys=YS-100; ya=ys-138   # 1a key + lead logo acima, bem proximos
    else:
        ys=YS; ya=ys-130       # lead colado na key
    POP=r"\fscx40\fscy40\t(0,200,\fscx115\fscy115)\t(200,340,\fscx100\fscy100)"
    def keyev(layer,style):
        out=[]
        if multi:
            for i,kw in enumerate(kparts):
                y=ys+i*lh
                out.append(f"Dialogue: {layer},{_ts(0.18+0.06*i)},{_ts(d)},{style},,0,0,0,{{\\an5\\pos(540,{y})\\fad(120,0){POP}}}{kw}")
        else:
            out.append(f"Dialogue: {layer},{_ts(0.18)},{_ts(d)},{style},,0,0,0,{{\\an5\\pos(540,{ys})\\fad(120,0){POP}}}{key}")
        return out
    if mask:
        head=("[Script Info]\nScriptType: v4.00+\nPlayResX:1080\nPlayResY:1920\nWrapStyle:2\nScaledBorderAndShadow: yes\n\n"
          "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,Bold,Italic,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV\n"
          f"Style: D, DM Serif Display, {ksz}, &H00FFFFFF, &H00000000, &H00000000, 0,0,1,0,0,5,30,30,0\n\n"
          "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,Effect,Text\n")
        ev=keyev(0,"D")
    else:
        head=("[Script Info]\nScriptType: v4.00+\nPlayResX:1080\nPlayResY:1920\nWrapStyle:2\nScaledBorderAndShadow: yes\n\n"
          "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,Bold,Italic,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV\n"
          "Style: P, Playfair Display, 122, &H00FFFFFF, &H00000000, &H64000000, 0,1,1,0,7,4,5,50,50,0\n"
          f"Style: D, DM Serif Display, {ksz}, &H005C7ADE, &H00FFFFFF, &H64000000, 0,0,1,0,10,5,30,30,0\n\n"
          "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,Effect,Text\n")
        ev=[f"Dialogue: 1,{_ts(0)},{_ts(d)},P,,0,0,0,{{\\an5\\pos(540,{ya})\\fad(220,0)\\move(540,{ya+45},540,{ya},0,260)}}{lead}"]+keyev(1,"D")
    p=os.path.join(TMP,f"{'mask' if mask else 'let'}_{abs(hash(lead+key))%99999}.ass")
    open(p,"w").write(head+"\n".join(ev)+"\n"); return p

def render_chrome(lead,key,s,d,out,withlogo=False):
    assL=_ass(lead,key,d,mask=False,withlogo=withlogo)
    assM=_ass(lead,key,d,mask=True,withlogo=withlogo)
    base=os.path.join(TMP,"base.mp4"); mask=os.path.join(TMP,"mask.mp4")
    # pass A: talking-head escurecido+vinheta + lettering sharp (+logo)
    if withlogo:
        _run(["ffmpeg","-y","-ss",str(s),"-t",str(d),"-i",AVATAR,"-i",LOGO,"-filter_complex",
          f"[0:v]fps={FPS},{REFRAME},setsar=1,eq=brightness=-0.06,vignette=PI/4.5,subtitles={assL}:fontsdir={FONTS}[bg];"
          f"[1:v]scale=440:-1[lg];[bg][lg]overlay=(W-w)/2:90[v]","-map","[v]","-t",str(d),"-r",str(FPS),
          "-an","-c:v","libx264","-crf","20","-pix_fmt","yuv420p",base],"passA-logo")
    else:
        _run(["ffmpeg","-y","-ss",str(s),"-t",str(d),"-i",AVATAR,"-vf",
          f"fps={FPS},{REFRAME},setsar=1,eq=brightness=-0.06,vignette=PI/4.5,subtitles={assL}:fontsdir={FONTS}",
          "-t",str(d),"-r",str(FPS),"-an","-c:v","libx264","-crf","20","-pix_fmt","yuv420p",base],"passA")
    # pass B: mascara da key (branco em preto, mesma anim)
    _run(["ffmpeg","-y","-f","lavfi","-t",str(d),"-i",f"color=black:s={W}x{H}:r={FPS}","-vf",
      f"subtitles={assM}:fontsdir={FONTS}","-r",str(FPS),"-c:v","libx264","-crf","18","-pix_fmt","yuv420p",mask],"passB")
    # pass C: sheen = gradiente mascarado pela key (opacidade baixa) sobre a base
    _run(["ffmpeg","-y","-i",base,"-loop","1","-i",GRAD,"-i",mask,"-filter_complex",
      "[1:v]format=rgba,scale=1080:1920[grad];"
      "[2:v]format=gray,curves=all='0/0 0.5/1 1/1',colorlevels=romax=0.45:gomax=0.45:bomax=0.45[m];"
      "[grad][m]alphamerge[gl];[0:v][gl]overlay=0:0[v]","-map","[v]","-t",str(d),"-r",str(FPS),
      "-an","-c:v","libx264","-crf","20","-pix_fmt","yuv420p",out],"passC")
    return out

if __name__=="__main__":
    # teste cena 1
    render_chrome("as melhores","SKILLS",30,3.6,"/tmp/chrome_scene1.mp4")
    print("OK /tmp/chrome_scene1.mp4")
