#!/usr/bin/env python3
"""Parser do roteiro anotado da Jheni -> plano de blocos + narracao continua.
Cada linha: [instrucao visual] texto narrado.
"""
import re, json, sys

def classify(instr):
    s=instr.lower()
    if "lettering" in s:
        return ("lettering_logo" if "logo" in s else "lettering")
    # THALES ANTES DE LOGO. Com "logo" testado primeiro, o bloco
    # "[Thales de frente para a camera + logo da imersao]" virava tipo "logo" e o motor
    # entregava um CARD DE LOGO EM TELA CHEIA, sem o apresentador, justamente no bloco
    # em que ele pede a inscricao. Reprovado pelo diretor de arte no jh14 (8,2s de card)
    # e no jh16 (6,7s). "+ logo" num bloco de Thales quer dizer logo SOBRE ele.
    if "thales" in s:
        return ("lettering_logo" if "logo" in s else "orig")
    if "logo" in s:
        return "logo"
    if any(k in s for k in ["inserção de video","insercao de video","inserção de vídeo","insercao de vídeo","insert","banco de skills","imersão","imersao"]):
        return "insert"
    return "insert"

def parse(path):
    blocks=[]
    for raw in open(path):
        raw=raw.strip()
        if not raw: continue
        m=re.match(r"\[(.+?)\]\s*(.*)", raw)
        if not m: continue
        instr, narr = m.group(1), m.group(2).strip()
        # LETTERING estilo ad34: LEAD (linha pequena italico) + KEY (palavra GIGANTE laranja).
        # Ex: [avatar + lettering | LEAD: uma skill de | KEY: PAGINAS] fala...
        key=""; lead=""
        if "KEY:" in instr:
            instr, key = instr.split("KEY:", 1); key = key.strip()
            if "LEAD:" in instr:
                instr, lead = instr.split("LEAD:", 1); lead = lead.strip().strip("|").strip()
            instr = instr.rstrip(" |")
        # limpar virgula/reticencias soltas no inicio da narracao
        narr=re.sub(r"^[\s,…\.]+","",narr)
        typ=classify(instr)
        blocks.append({"type":typ,"instr":instr,"narr":narr,"key":key,"lead":lead,
                       "zoom": "zoom" in instr.lower()})
    return blocks

if __name__=="__main__":
    path=sys.argv[1] if len(sys.argv)>1 else "inputs/ad34_leva3.txt"
    blocks=parse(path)
    narr_full=" ".join(b["narr"] for b in blocks if b["narr"])
    print("=== PLANO DE BLOCOS ===")
    for i,b in enumerate(blocks):
        z=" +zoom" if b["zoom"] else ""
        print(f"{i:2d}. [{b['type']}{z}] {b['instr'][:42]:42} | \"{b['narr'][:50]}\"")
    print()
    from collections import Counter
    print("contagem:", dict(Counter(b['type'] for b in blocks)))
    print()
    print("=== NARRAÇÃO COMPLETA (pro avatar HeyGen) ===")
    print(narr_full)
