#!/usr/bin/env python3
"""
Skill 2b - Gera um projeto (draft) do CapCut 8.6.0 a partir dos blocos do reel.
Cada bloco vira um clipe separado e trocavel na track de video (com audio embutido),
pronto pra Jheni abrir no CapCut e adicionar legenda/lettering.
"""
import json, os, subprocess, sys, uuid, shutil

# (migracao 26/08/2026) caminho de projeto agora sai de caminhos.py
from caminhos import DADOS as _D
BASE = str(_D)
TMP  = os.path.join(BASE, "_tmp_cc")
CC_ROOT = os.path.expanduser("~/Movies/CapCut/User Data/Projects/com.lveditor.draft")
os.makedirs(TMP, exist_ok=True)
W, H, FPS = 1080, 1920, 30
US = 1_000_000

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("ERRO:", " ".join(cmd[:5]), "\n", r.stderr[-700:]); sys.exit(1)

def uid(): return str(uuid.uuid4())

def probe_dur(p):
    return float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
        "-of","csv=p=0",p],capture_output=True,text=True).stdout.strip())

from PIL import Image, ImageDraw
def rounded_mask(w,h,rad,path):
    m=Image.new("L",(w,h),0); ImageDraw.Draw(m).rounded_rectangle([0,0,w-1,h-1],radius=rad,fill=255)
    Image.merge("RGBA",(Image.new("L",(w,h),255),)*3+(m,)).save(path)

# ---------- spec ----------
spec = json.load(open(sys.argv[1])) if len(sys.argv)>1 else {
    "name": "reel-machine-demo",
    "original": os.path.expanduser("~/Downloads/videos-thales-ads/ad1_v1_vertical.mp4"),
    "insert_A": os.path.expanduser("~/Downloads/thales_higgs/VIDEO_v2_nuzzle.mp4"),
    "insert_B": os.path.expanduser("~/Downloads/thales_higgs/VIDEO_v2_nuzzle.mp4"),
    "blocks": [
        {"type":"orig","start":0.0,"dur":4.0},
        {"type":"rounded","start":4.0,"dur":6.0,"src":"insert_A","src_start":0.5},
        {"type":"orig","start":10.0,"dur":4.0},
        {"type":"split","start":14.0,"dur":6.0,"src":"insert_B","src_start":1.5},
        {"type":"orig","start":20.0,"dur":4.0},
    ],
}
orig = spec["original"]; name = spec.get("name","reel-machine-demo")

# ---------- 1. renderizar cada bloco COM audio do trecho ----------
seg_files=[]
for i,b in enumerate(spec["blocks"]):
    seg=os.path.join(TMP,f"bloco_{i:02d}.mp4"); d=b["dur"]
    if b["type"]=="orig":
        vf=("scale=2160:3840:force_original_aspect_ratio=increase,crop=2160:3840,"
            f"zoompan=z='min(zoom+0.0009,1.30)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},setsar=1")
        run(["ffmpeg","-y","-ss",str(b["start"]),"-t",str(d),"-i",orig,
             "-vf",vf,"-r",str(FPS),"-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",seg])
    elif b["type"]=="rounded":
        src=spec[b["src"]]
        pr=subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-show_entries",
            "stream=width,height","-of","csv=p=0",src],capture_output=True,text=True).stdout.strip().split(",")
        ih=int(1000*int(pr[1])/int(pr[0]))//2*2
        mask=os.path.join(TMP,f"mask_{i}.png"); rounded_mask(1000,ih,60,mask)
        fc=(f"[0:v]scale=1000:{ih},setsar=1[ins];[ins][3:v]alphamerge[insa];"
            f"[1:v]scale={W}:{H},boxblur=40:2,eq=brightness=-0.25[bg];"
            f"[bg][insa]overlay=(W-w)/2:(H-h)/2:format=auto,setsar=1[v]")
        run(["ffmpeg","-y","-ss",str(b.get("src_start",0)),"-t",str(d),"-i",src,
             "-ss",str(b["start"]),"-t",str(d),"-i",orig,"-ss",str(b["start"]),"-t",str(d),"-i",orig,
             "-i",mask,"-filter_complex",fc,"-map","[v]","-map","2:a:0",
             "-r",str(FPS),"-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",seg])
    elif b["type"]=="split":
        src=spec[b["src"]]
        fc=(f"[0:v]scale={W}:960:force_original_aspect_ratio=increase,crop={W}:960,setsar=1[top];"
            f"[1:v]scale={W}:960:force_original_aspect_ratio=increase,crop={W}:960,setsar=1[bot];"
            f"[top][bot]vstack=2,setsar=1[v]")
        run(["ffmpeg","-y","-ss",str(b.get("src_start",0)),"-t",str(d),"-i",src,
             "-ss",str(b["start"]),"-t",str(d),"-i",orig,
             "-filter_complex",fc,"-map","[v]","-map","1:a:0",
             "-r",str(FPS),"-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",seg])
    seg_files.append(seg); print(f"  bloco {i} ({b['type']}) ok")

# ---------- 2. montar a pasta do draft ----------
fold=os.path.join(CC_ROOT,name)
if os.path.exists(fold): shutil.rmtree(fold)
assets=os.path.join(fold,"assets","video"); os.makedirs(assets,exist_ok=True)
copied=[]
for i,s in enumerate(seg_files):
    dst=os.path.join(assets,f"bloco_{i:02d}.mp4"); shutil.copy(s,dst); copied.append(dst)

# materiais auxiliares default (1 conjunto por segmento)
def aux_set():
    return {
        "speed":{"id":uid(),"type":"speed","speed":1,"mode":0,"curve_speed":None},
        "placeholder":{"id":uid(),"type":"placeholder_info","error_path":"","error_text":"","meta_type":"none","res_path":"","res_text":""},
        "scm":{"id":uid(),"type":"none","audio_channel_mapping":0,"is_config_open":False},
        "voc":{"id":uid(),"type":"vocal_separation","choice":0,"enter_from":"","final_algorithm":"","production_path":"","removed_sounds":[],"time_range":None},
        "canvas":{"id":uid(),"type":"canvas_color","album_image":"","blur":0,"color":"","image":"","image_id":"","image_name":"","source_platform":0,"team_id":""},
        "mcolor":{"id":uid(),"type":"material_color","gradient_angle":90,"gradient_colors":[],"gradient_percents":[],"height":0,"is_color_clip":False,"is_gradient":False,"solid_color":"","width":0},
    }

def vmat(path,dur_us):
    return {"id":uid(),"path":path,"material_name":os.path.basename(path),"type":"video",
        "duration":dur_us,"width":W,"height":H,"category_id":"","category_name":"local","check_flag":7,
        "crop":{"lower_left_x":0,"lower_left_y":1,"lower_right_x":1,"lower_right_y":1,"upper_left_x":0,"upper_left_y":0,"upper_right_x":1,"upper_right_y":0},
        "has_audio":True,"extra_type_option":0,"formula_id":"","freeze":None,"intensifies_audio_path":"","intensifies_path":"",
        "is_ai_generate_content":False,"is_copyright":False,"is_text_edit_overdub":False,"is_unified_beauty_mode":False,
        "local_id":"","local_material_id":"","material_url":"","media_path":"","object_locked":None,"origin_material_id":"",
        "request_id":"","reverse_path":"","source_platform":0,
        "stable":{"matrix_path":"","stable_level":0,"time_range":{"duration":0,"start":0}},
        "team_id":"","video_algorithm":{"algorithms":[],"deflicker":None,"motion_blur_config":None,"noise_reduction":None,"path":"","quality_enhance":None,"time_range":None}}

mats={"videos":[],"texts":[],"audios":[],"stickers":[],"video_effects":[],"transitions":[],"masks":[],
      "chromas":[],"audio_fades":[],"audio_effects":[],"speeds":[],"placeholder_infos":[],
      "sound_channel_mappings":[],"vocal_separations":[],"canvases":[],"material_colors":[],"common_mask":[]}
segments=[]; cursor=0; total_us=0
for i,(p,b) in enumerate(zip(copied,spec["blocks"])):
    dur_us=round(b["dur"]*US)
    aud=probe_dur(p); dur_us=round(aud*US)  # usar duracao real do arquivo
    m=vmat(p,dur_us); mats["videos"].append(m)
    a=aux_set()
    mats["speeds"].append(a["speed"]); mats["placeholder_infos"].append(a["placeholder"])
    mats["sound_channel_mappings"].append(a["scm"]); mats["vocal_separations"].append(a["voc"])
    mats["canvases"].append(a["canvas"]); mats["material_colors"].append(a["mcolor"])
    segments.append({"id":uid(),"material_id":m["id"],
        "target_timerange":{"start":cursor,"duration":dur_us},
        "source_timerange":{"start":0,"duration":dur_us},
        "speed":1,"volume":1,"visible":True,"reverse":False,
        "clip":{"alpha":1,"rotation":0,"scale":{"x":1,"y":1},"transform":{"x":0,"y":0},"flip":{"horizontal":False,"vertical":False}},
        "render_index":14000+i,"track_render_index":0,"track_attribute":0,
        "extra_material_refs":[a["speed"]["id"],a["placeholder"]["id"],a["scm"]["id"],a["voc"]["id"],a["canvas"]["id"],a["mcolor"]["id"]],
        "common_keyframes":[],"keyframe_refs":[]})
    cursor+=dur_us; total_us=cursor

draft_id=str(uuid.uuid4()).upper()
content={"id":draft_id,"name":name,"duration":total_us,"fps":FPS,
    "canvas_config":{"width":W,"height":H,"ratio":"9:16"},
    "platform":{"app_source":"cc","app_version":"6.5.0","os":"mac"},
    "tracks":[{"id":uid(),"type":"video","attribute":0,"flag":0,"segments":segments}],
    "materials":mats,"extra_info":{"created_via":"reel-machine"}}
json.dump(content,open(os.path.join(fold,"draft_content.json"),"w"),ensure_ascii=False)

# draft_info.json (minimo)
json.dump({"id":draft_id.lower(),"name":name,"duration":0,"fps":FPS,
    "canvas_config":{"width":W,"height":H,"ratio":"9:16"},
    "platform":{"app_source":"cc","app_version":"6.5.0","os":"mac"},
    "tracks":[],"materials":{k:[] for k in mats},"extra_info":{"created_via":"reel-machine"}},
    open(os.path.join(fold,"draft_info.json"),"w"),ensure_ascii=False)

# cover (primeiro frame)
run(["ffmpeg","-y","-i",copied[0],"-frames:v","1",os.path.join(fold,"draft_cover.jpg")])

# draft_meta_info.json
import time
now=int(time.time())
dmats=[{"type":0,"value":[{"ai_group_type":"","create_time":now,"duration":round(probe_dur(p)*US),
        "extra_info":os.path.basename(p),"file_Path":p,"height":H,"width":W,
        "id":uid(),"import_time":now,"import_time_ms":now*1000,"item_source":1,
        "md5":"","metetype":"video","roughcut_time_range":{"duration":-1,"start":-1},
        "sub_time_range":{"duration":-1,"start":-1},"type":0} for p in copied]}]
meta={"cloud_draft_cover":False,"cloud_draft_sync":False,"draft_cover":"draft_cover.jpg",
    "draft_deeplink_url":"","draft_enterprise_info":{"draft_enterprise_extra":"","draft_enterprise_id":"","draft_enterprise_name":"","enterprise_material":[]},
    "draft_fold_path":fold,"draft_id":draft_id,"draft_is_ae_produce":False,"draft_is_ai_packaging_used":False,
    "draft_is_ai_shorts":False,"draft_is_ai_translate":False,"draft_is_article_video_draft":False,
    "draft_is_from_deeplink":"false","draft_is_invisible":False,"draft_materials":dmats,
    "draft_name":name,"draft_new_version":"137.0.0","draft_root_path":CC_ROOT,
    "draft_timeline_materials_size_":0,"tm_draft_create":now*1000,"tm_draft_modified":now*1000}
json.dump(meta,open(os.path.join(fold,"draft_meta_info.json"),"w"),ensure_ascii=False)

# registrar no root_meta_info.json
rp=os.path.join(CC_ROOT,"root_meta_info.json")
root=json.load(open(rp))
shutil.copy(rp, rp+".reelmachine.bak")
entry={"cloud_draft_cover":False,"cloud_draft_sync":False,"draft_cover":os.path.join(fold,"draft_cover.jpg"),
    "draft_fold_path":fold,"draft_id":draft_id,"draft_is_ai_shorts":False,"draft_is_cloud_temp_draft":False,
    "draft_is_invisible":False,"draft_json_file":os.path.join(fold,"draft_content.json"),
    "draft_name":name,"draft_new_version":"137.0.0","draft_root_path":CC_ROOT,
    "tm_draft_create":now*1000,"tm_draft_modified":now*1000}
root.setdefault("all_draft_store",[]).insert(0,entry)
# draft_ids eh um contador inteiro nesta versao; nao mexer como lista
json.dump(root,open(rp,"w"),ensure_ascii=False)

print(f"\nDRAFT CRIADO: {fold}")
print(f"duracao total: {total_us/US:.1f}s | {len(segments)} clipes | id {draft_id}")
print("Abra o CapCut e procure o projeto:", name)
