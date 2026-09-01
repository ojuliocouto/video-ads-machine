#!/usr/bin/env python3
"""Compoe o circulo (PiP) do Thales nos b-rolls DEPOIS do Submagic (magicZooms nao arrasta).
Avatar trimado do a0 => avatar-time alinha com reel-time. enable nas janelas dos inserts.
Uso: add_pip.py <in.mp4> <out.mp4>"""
import json, subprocess, os, sys
from caminhos import DADOS as _D  # noqa: E402
BASE=str(_D)
T=json.load(open(os.path.join(BASE,"output","timing.json")))
a0=T["a0"]; AV=os.path.expanduser(os.environ.get("VAM_AVATAR", os.path.join(BASE,"inputs","avatar_thales.mp4")))
MASK=os.path.join(BASE,"assets","circle_mask.png")
RING=os.path.join(BASE,"assets","circle_ring.png")
SH=os.path.join(BASE,"assets","circle_shadow.png")
inp=sys.argv[1]; out=sys.argv[2]
PIP=300; PIPX=390; PIPY=150; PIPF=60
# janela = OR (soma) das janelas reel-time dos inserts.
# Encolhida: comeca XF depois (o insert entra por dissolve de XF; a bolinha so aparece com o
# insert 100% na tela) e termina no inicio do dissolve de saida. Sem isso a bolinha aparece
# sobre o avatar em tela cheia durante as transicoes (bug reportado 16/07).
XFAD=float(T.get("xf",0.18))
wins=[]
for i in T["inserts"]:
    rs=i["s"]-a0
    if rs<0.05:
        # INSERT DE ABERTURA (video comeca em b-roll): SEM bolinha (pedido do Julio 16/07,
        # "o insert dos primeiros videos tem que ser so o video, sem o Thales na bolinha")
        continue
    wins.append((round(rs+XFAD,3), round(i["e"]-a0,3)))
# anti-piscada: inserts CONSECUTIVOS (transicao insert->insert) mantem a bolinha ligada;
# sem isso ela some por XFAD e volta, parecendo glitch.
_m=[]
for rs,re_ in sorted(wins):
    if _m and rs-_m[-1][1]<=XFAD+0.1: _m[-1]=(_m[-1][0],max(_m[-1][1],re_))
    else: _m.append((rs,re_))
wins=_m
EN="+".join(f"between(t,{rs},{re})" for rs,re in wins)
fc=(
  f"[1:v]scale={PIP}:{PIP}:force_original_aspect_ratio=increase,crop={PIP}:{PIP},setsar=1[sq];"
  f"[sq][2:v]alphamerge[pip];"
  f"[0:v][4:v]overlay={PIPX-PIPF}:{PIPY-PIPF+14}:enable='{EN}'[sh];"   # sombra (flutua)
  f"[sh][pip]overlay={PIPX}:{PIPY}:enable='{EN}'[wp];"                 # avatar circular
  f"[wp][3:v]overlay={PIPX-PIPF}:{PIPY-PIPF}:enable='{EN}',"
  f"colorspace=all=bt709:iall=bt709:fast=1[v]"                         # re-marca a tag SDR
)
cmd=["ffmpeg","-y","-i",inp,"-ss",str(a0),"-i",AV,"-i",MASK,"-i",RING,"-i",SH,
     "-filter_complex",fc,"-map","[v]","-map","0:a","-shortest",
     "-c:v","libx264","-crf","18","-pix_fmt","yuv420p",
     "-colorspace","bt709","-color_primaries","bt709","-color_trc","bt709","-color_range","tv",
     "-c:a","copy","-movflags","+faststart",out]
r=subprocess.run(cmd,capture_output=True,text=True)
if r.returncode!=0: print("ERR\n",r.stderr[-1800:]); sys.exit(1)
print("OK",out)
