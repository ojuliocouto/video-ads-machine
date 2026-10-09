"""O laudo da entrega: `entrega/laudo.json` (contrato `contratos/laudo.schema.json`).

O `vam montar` escreve o laudo depois dos gates de saída. Ele é a prova de que o arquivo entregue passou por TODOS os
gates, na ordem da seção 4 do plano, e está amarrado ao sha256 desse arquivo: mudar 1 byte do final vence o laudo.

  gates         cada gate, na ordem em que rodou, com resultado (PASS, REPROVA, ERRO, PULADO), saída e o que mediu
  capacidades   as 14 capacidades cinematográficas (C1 a C14), cada uma com os gates que a provam (`CAPACIDADES`):
                  PASS           todos os gates dela que rodaram passaram (os PULADOS não contam)
                  REPROVA        algum gate dela reprovou ou morreu
                  DESLIGADA      só a C13 (texto atrás da pessoa), quando o projeto não a liga
                  NAO_SE_APLICA  todos os gates dela foram pulados com motivo (1x1, por exemplo)
                Gate que a capacidade cita e NÃO rodou entra no laudo como ERRO ("não rodou"): ausência nunca aprova.
  medidas       medidas do ARQUIVO entregue (ffprobe e ebur128), nunca copiadas do plano
  veredito      PASS só sem nenhum gate REPROVA ou ERRO e sem capacidade REPROVA

    from entrega import laudo
    d = laudo.montar(pj, gates, final=pj.final_9x16, previa=pj.final_whatsapp)
    laudo.gravar(pj, d)          # valida no contrato; LaudoInvalido se não passar
"""
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from contratos.validar import validar
from projeto import status

# Os gates que provam cada capacidade (C1 a C14 da seção 3 do plano). A ordem dos nomes é a ordem do laudo.
CAPACIDADES = {
    "C1": ("gate_hook_visual", "gate-ad"),
    "C2": ("medir_ritmo",),
    "C3": ("gate_camera",),
    "C4": ("auditar_ad", "gate-ad"),
    "C5": ("gate_cor",),
    "C6": ("gate-ad", "gate-contraste-legenda", "gate-colisao-texto", "gate_safezone", "gate_geometria",
           "gate_safezone_depois", "gate_geometria_depois"),
    "C7": ("gate_lettering", "gate_lettering_depois"),
    "C8": ("gate_insert", "gate_congelamento", "gate_congelamento_build"),
    "C9": ("gate_lettering_depois",),
    "C10": ("gate_mix",),
    "C11": ("gate_sfx",),
    "C12": ("gate-ad", "gate_mix"),
    "C13": ("gate_texto_atras",),
    "C14": ("gate_relogio",),
}
OPCIONAIS = {"C13"}          # capacidade que o projeto liga ou não (DESLIGADA quando o gate dela foi pulado)
FALHA = ("REPROVA", "ERRO")


class LaudoInvalido(ValueError):
    """O laudo montado não passa no contrato: nada foi gravado."""


def sha256_arquivo(caminho):
    h = hashlib.sha256()
    with open(str(caminho), "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


# --- medidas do arquivo entregue ----------------------------------------------------------------------------

def medir(final):
    """Medidas do arquivo entregue: duração, tamanho, fps, cor, taxa de áudio (ffprobe) e loudness (ebur128)."""
    from audio import loudness
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_type,width,height,avg_frame_rate,sample_rate,color_primaries,color_transfer,"
                        "color_space:format=duration", "-of", "json", str(final)], capture_output=True, text=True)
    d = json.loads(o.stdout or "{}")
    video = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), {})
    num, den = (str(video.get("avg_frame_rate", "0/1")).split("/") + ["1"])[:2]
    m = loudness.medir(final)
    medidas = {"duracao_s": round(float(d.get("format", {}).get("duration", 0.0)), 3),
               "largura": int(video.get("width", 0)), "altura": int(video.get("height", 0)),
               "lufs": round(m.integrado_lufs, 2), "true_peak_dbtp": round(m.true_peak_dbtp, 2)}
    if float(den or 1) and float(num or 0):
        medidas["fps"] = round(float(num) / float(den), 3)
    if audio.get("sample_rate"):
        medidas["taxa_amostragem"] = int(audio["sample_rate"])
    cor = {k: video[c] for k, c in (("primarias", "color_primaries"), ("transferencia", "color_transfer"),
                                     ("matriz", "color_space")) if video.get(c)}
    if cor:
        medidas["cor"] = cor
    return medidas


def ambiente():
    """Versões da máquina que montou (o laudo diz ONDE foi medido). Falha de consulta vira campo ausente."""
    amb = {"plataforma": "%s %s" % (platform.system(), platform.machine()), "python": platform.python_version()}
    for nome, cmd in (("ffmpeg", ["ffmpeg", "-version"]), ("node", ["node", "--version"])):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if r.returncode == 0 and r.stdout.strip():
                amb[nome] = r.stdout.strip().splitlines()[0][:80]
        except (OSError, subprocess.SubprocessError):
            pass
    if os.environ.get("HF_HOME"):
        amb["hf_home"] = os.environ["HF_HOME"]
    return amb


# --- capacidades --------------------------------------------------------------------------------------------

def _nao_rodou(nome):
    return {"nome": nome, "etapa": "depois", "resultado": "ERRO", "saida": 2,
            "motivo": "o gate não rodou neste build: sem a medida, a capacidade não é provada"}


def _completar(gates):
    """Os gates do laudo mais um ERRO "não rodou" para cada gate que alguma capacidade cita e não está lá."""
    gates = [dict(g) for g in gates]
    vistos = {g["nome"] for g in gates}
    for nomes in CAPACIDADES.values():
        for n in nomes:
            if n not in vistos:
                gates.append(_nao_rodou(n))
                vistos.add(n)
    return gates


def capacidades(gates):
    """{C1..C14: {status, gates, [motivo]}} a partir dos gates (já completados com os que não rodaram)."""
    por_nome = {g["nome"]: g for g in gates}
    saida = {}
    for cap, nomes in CAPACIDADES.items():
        gs = [por_nome[n] for n in nomes if n in por_nome]
        ruins = [g for g in gs if g["resultado"] in FALHA]
        passaram = [g["nome"] for g in gs if g["resultado"] == "PASS"]
        pulados = [g for g in gs if g["resultado"] == "PULADO"]
        if ruins:
            saida[cap] = {"status": "REPROVA", "gates": [g["nome"] for g in gs],
                          "motivo": "; ".join("%s: %s" % (g["nome"], g.get("motivo", g["resultado"]))
                                              for g in ruins)[:900]}
        elif passaram:
            saida[cap] = {"status": "PASS", "gates": passaram}
        else:
            motivo = "; ".join("%s: %s" % (g["nome"], g.get("motivo", "pulado")) for g in pulados)[:900] or "pulado"
            saida[cap] = {"status": "DESLIGADA" if cap in OPCIONAIS else "NAO_SE_APLICA",
                          "gates": [g["nome"] for g in gs], "motivo": motivo}
    return saida


def veredito(gates, caps):
    falhou = any(g["resultado"] in FALHA for g in gates) or any(c["status"] == "REPROVA" for c in caps.values())
    return "REPROVA" if falhou else "PASS"


# --- montar e gravar ------------------------------------------------------------------------------------------

def montar(pj, gates, *, final, previa=None, agora=None, medidas=None, tempos=None, amb=None, modo=None,
           projeto=None):
    """O dict do laudo (ainda não gravado). `medidas`: as do arquivo (padrão: `medir(final)`)."""
    final = Path(final)
    gs = _completar(gates)
    caps = capacidades(gs)
    d = {"versao": 1, "projeto": pj.slug, "modo": modo or (projeto or {}).get("modo", "avatar"),
         "arquivo": pj.relativo(final), "sha256": sha256_arquivo(final),
         "gerado_em": agora or status.instante(),
         "medidas": medidas if medidas is not None else medir(final)}
    if previa is not None and Path(previa).is_file():
        d["previa"] = {"arquivo": pj.relativo(previa), "sha256": sha256_arquivo(previa)}
    d["gates"] = gs
    d["capacidades"] = caps
    exc = [{"regra": e["regra"], "motivo": e["motivo"]} for e in (projeto or {}).get("excecoes", [])]
    if exc:
        d["excecoes"] = exc
    if tempos:
        d["tempos"] = {k: round(float(v), 1) for k, v in tempos.items()}
    if amb:
        d["ambiente"] = amb
    d["veredito"] = veredito(gs, caps)
    return d


def gravar(pj, laudo):
    """Valida no contrato e grava entrega/laudo.json (temporário + rename). LaudoInvalido: nada é gravado."""
    erros = validar("laudo", laudo)
    if erros:
        raise LaudoInvalido("o laudo não passa no contrato: " + "; ".join(str(e) for e in erros[:6]))
    status.escrever_json_atomico(pj.laudo, laudo)
    return pj.laudo


def ler(pj):
    """O laudo gravado (dict) ou None. ValueError se ilegível."""
    if not pj.laudo.is_file():
        return None
    return status.ler_json(pj.laudo)


def resumo(laudo):
    """Uma linha por gate (o que o aluno lê no terminal), e o veredito."""
    linhas = []
    for g in laudo["gates"]:
        extra = (": " + g["motivo"]) if g.get("motivo") else ""
        linhas.append("  %-24s %-8s %-7s%s" % (g["nome"], g["etapa"], g["resultado"], extra[:160]))
    linhas.append("  capacidades: " + ", ".join("%s %s" % (c, v["status"]) for c, v in laudo["capacidades"].items()))
    linhas.append("VEREDITO: %s" % laudo["veredito"])
    return "\n".join(linhas)


if __name__ == "__main__":
    sys.exit("uso: o laudo é escrito pelo `vam montar`; leia entrega/laudo.json ou rode `vam status <slug>`")
