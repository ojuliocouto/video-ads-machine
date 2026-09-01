#!/usr/bin/env python3
"""Lê uma aba do roteiro (Video Ads Machine) no Google Sheets e devolve o PLANO estruturado:
roteiro principal (Hook/Body/CTA) + hooks alternativos. Cada hook alternativo = um vídeo novo
reaproveitando o mesmo Body + CTA.

Uso: python3 parse_sheet.py "✅ Exemplo (AD34)"   (ou o nome da aba do criativo, ex: AD35)
"""
import json, sys, urllib.request, urllib.parse, os

SID = "1hSyIROfE_7aTyzEwogfNlc4THYnlIksI4-yEOvBnG-A"
TOKENS = os.path.expanduser("~/.claude/google-tokens.json")

# tipos compostos -> componentes (o que a montagem precisa pôr na cena)
JUNCOES = {
    "Avatar (Thales falando)":            ["avatar"],
    "Inserção de vídeo (b-roll)":         ["broll"],
    "Lettering":                          ["lettering"],
    "Logo do evento":                     ["logo"],
    "Avatar + Lettering":                 ["avatar", "lettering"],
    "Avatar + Inserção de vídeo (b-roll)":["avatar", "broll"],
    "Lettering + Logo":                   ["lettering", "logo"],
    "Avatar + Lettering + Logo":          ["avatar", "lettering", "logo"],
    "Lettering + Logo (CTA)":             ["lettering", "logo", "cta"],
}

def tok():
    return json.load(open(TOKENS))["access_token"]

def read_tab(tab):
    rng = urllib.parse.quote(f"'{tab}'!A1:I90", safe="")
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SID}/values/{rng}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok()}"})
    return json.load(urllib.request.urlopen(req)).get("values", [])

def cell(r, i):
    return (r[i].strip() if len(r) > i and r[i] else "")

def parse(tab):
    rows = read_tab(tab)
    if not rows:
        return None
    body = rows[1:]  # pula header
    main = []          # cenas do roteiro principal
    alt_hooks = []     # [{"label","fala","tipo",...}]
    section = "main"   # "main" -> antes da faixa HOOKS ALTERNATIVOS; depois "alt"
    for r in body:
        ordem, fala, fase, tipo = cell(r,0), cell(r,1), cell(r,2), cell(r,3)
        key, broll, zoom, pip, obs = cell(r,4), cell(r,5), cell(r,6), cell(r,7), cell(r,8)
        # faixa separadora
        if fala.startswith("▼") or fala.startswith("▶"):
            if "HOOK" in fala.upper() and "ALTERNATIV" in fala.upper():
                section = "alt"
            continue
        if not (fala or fase or tipo or ordem):
            continue  # linha vazia
        scene = {"ordem": ordem, "fala": fala, "fase": fase, "tipo": tipo,
                 "lettering_key": key, "broll": broll, "zoom": zoom, "pip": pip, "obs": obs,
                 "componentes": JUNCOES.get(tipo, ["?"] if tipo else [])}
        if section == "main":
            main.append(scene)
        else:
            alt_hooks.append(scene)
    return {"main": main, "alt_hooks": alt_hooks}

def fase_groups(main):
    g = {"Hook principal": [], "Body": [], "CTA": [], "?": []}
    for s in main:
        f = s["fase"]
        if f in ("Hook", "Hook principal"):   # aceita os dois (compat)
            g["Hook principal"].append(s)
        elif f in g:
            g[f].append(s)
        else:
            g["?"].append(s)
    return g

def warnings(plan):
    w = []
    for s in plan["main"] + plan["alt_hooks"]:
        comp = s["componentes"]
        if "lettering" in comp and not s["lettering_key"]:
            w.append(f'cena {s["ordem"] or s["fala"][:20]!r}: tipo tem lettering mas sem palavra-destaque')
        if "broll" in comp and not s["broll"]:
            w.append(f'cena {s["ordem"] or s["fala"][:20]!r}: tipo tem b-roll mas coluna B-roll vazia')
        if s["tipo"] and "?" in comp:
            w.append(f'cena {s["ordem"]!r}: tipo de cena nao reconhecido ({s["tipo"]!r})')
    return w

def report(tab):
    plan = parse(tab)
    if not plan:
        print("aba vazia/inexistente"); return
    g = fase_groups(plan["main"])
    alt = [h for h in plan["alt_hooks"] if h["fala"]]   # hooks que a Jheni já preencheu
    alt_vazios = [h for h in plan["alt_hooks"] if not h["fala"]]
    n_videos = 1 + len(alt)

    print(f"========== PLANO: {tab} ==========")
    print(f"Vídeos a gerar: {n_videos}  (1 principal + {len(alt)} hook(s) alternativo(s) preenchido(s))")
    print(f"Cada vídeo sai em 9:16 e 1:1.\n")

    print(f"--- ROTEIRO PRINCIPAL ({len(plan['main'])} cenas) ---")
    for fase in ("Hook principal", "Body", "CTA"):
        if g[fase]:
            print(f"  [{fase}] {len(g[fase])} cena(s):")
            for s in g[fase]:
                extra = []
                if s["lettering_key"]: extra.append(f'destaque={s["lettering_key"]}')
                if s["broll"]: extra.append(f'broll={s["broll"]}')
                if s["zoom"] not in ("", "—"): extra.append(f'zoom={s["zoom"]}')
                if s["pip"] == "Sim": extra.append("PiP")
                tag = f' [{", ".join(extra)}]' if extra else ""
                print(f'    {s["ordem"]:>2}. ({"+".join(s["componentes"])}) "{s["fala"][:60]}"{tag}')
    if g["?"]:
        print(f"  [SEM FASE] {len(g['?'])} cena(s) — Jheni esqueceu de marcar a fase")

    print(f"\n--- HOOKS ALTERNATIVOS ---")
    if not plan["alt_hooks"]:
        print("  (seção não encontrada)")
    for h in plan["alt_hooks"]:
        status = f'"{h["fala"][:60]}"' if h["fala"] else "(vazio — aguardando Jheni)"
        print(f'  {h["ordem"] or "Hook ?"}: {status}')
    if alt:
        print(f"\n  → cada hook acima vira 1 vídeo = (hook) + Body + CTA do principal")

    brolls = sorted({s["broll"] for s in plan["main"]+plan["alt_hooks"] if s["broll"]})
    if brolls:
        print(f"\n--- B-ROLLS NECESSÁRIOS ({len(brolls)}) ---")
        for b in brolls: print(f"  • {b}")

    w = warnings(plan)
    print(f"\n--- VALIDAÇÃO ---")
    print("  OK, sem pendências." if not w else "\n".join("  ⚠ "+x for x in w))
    print(f"\n  Lembrete: preciso do ÁUDIO REAL do Thales lendo as falas (gera o avatar).")

if __name__ == "__main__":
    report(sys.argv[1] if len(sys.argv) > 1 else "✅ Exemplo (AD34)")
