import sys,time,json,urllib.request,os
import requests
# (migracao 26/08/2026) caminho de projeto agora sai de caminhos.py
from caminhos import DADOS as _D
KEY=open(_D / ".submagic_key").read().strip()
H={"x-api-key":KEY}
API="https://api.submagic.co/v1"
def upload(path,template,lang="pt",magic_zooms=False,clean_audio=False,theme_id=None):
    with open(path,"rb") as f:
        files={"file":(os.path.basename(path),f,"video/mp4")}
        data={"title":f"AD34 {template or 'theme'}","language":lang,
              "dictionary":json.dumps(["Claude","Claude Code","Operação Claude Code","skills","IA"])}
        # userThemeId NAO combina com templateName (mutuamente exclusivos)
        if theme_id: data["userThemeId"]=theme_id
        else:        data["templateName"]=template
        if magic_zooms: data["magicZooms"]="true"
        if clean_audio: data["cleanAudio"]="true"
        r=requests.post(f"{API}/projects/upload",headers=H,files=files,data=data,timeout=300)
    if r.status_code>=400: print("UPLOAD ERR",r.status_code,r.text[:300])
    r.raise_for_status(); return r.json()["id"]
def get(pid): return requests.get(f"{API}/projects/{pid}",headers=H,timeout=60).json()
def export(pid): return requests.post(f"{API}/projects/{pid}/export",headers=H,timeout=60).json()
def run(path,template,out,magic_zooms=False,clean_audio=False,theme_id=None):
    pid=upload(path,template,magic_zooms=magic_zooms,clean_audio=clean_audio,theme_id=theme_id)
    tag=template or theme_id
    print(f"[{tag}] project {pid} uploaded (zooms={magic_zooms} clean={clean_audio} theme={theme_id})",flush=True)
    for i in range(120):
        d=get(pid); ts=d.get("transcriptionStatus"); st=d.get("status")
        print(f"[{template}] status={st} transcription={ts} ({i})",flush=True)
        if ts=="COMPLETED" and st!="uploading": break
        if st=="failed": print("FAILED",d.get("failureReason")); return
        time.sleep(5)
    export(pid); print(f"[{template}] export triggered",flush=True)
    for i in range(120):
        d=get(pid); st=d.get("status"); url=d.get("downloadUrl") or d.get("directUrl")
        print(f"[{template}] export status={st} ({i})",flush=True)
        if st=="completed" and (d.get("directUrl") or d.get("downloadUrl")):
            du=d.get("directUrl"); 
            r2=requests.get(du,timeout=300) if du else None
            if not du or r2.status_code!=200:
                r2=requests.get(d.get("downloadUrl"),headers=H,timeout=300)
            open(out,"wb").write(r2.content); print(f"[{template}] DOWNLOADED -> {out} ({len(r2.content)} bytes)",flush=True); return out
        if st=="failed": print("EXPORT FAILED"); return
        time.sleep(5)
if __name__=="__main__":
    mz="--zooms" in sys.argv; ca="--clean" in sys.argv
    theme=None
    for a in sys.argv:
        if a.startswith("--theme="): theme=a.split("=",1)[1]
    pos=[a for a in sys.argv[1:] if not a.startswith("--")]
    # uso: submagic_run.py <in> <template|-> <out> [--zooms] [--clean] [--theme=UUID]
    tmpl=None if (theme and (len(pos)<2 or pos[1]=="-")) else pos[1]
    run(pos[0],tmpl,pos[2],magic_zooms=mz,clean_audio=ca,theme_id=theme)
