#!/usr/bin/env python3
"""Preflight / onboarding do Video Ads Machine.

Roda no inicio (`vam setup` / `vam doctor`, ou na 1a invocacao da skill). Detecta o que
falta e GUIA o usuario a instalar os MCPs, plugins e dependencias necessarios. Bloqueia a
geracao ate o minimo obrigatorio passar (ffmpeg + 1 backend de alinhamento + HEYGEN key).
"""
import os
import platform
import shutil
import sys

OK, WARN, FAIL = "  [ok]", "  [opcional]", "  [FALTA]"


def _has_module(name):
    try:
        __import__(name)
        return True
    except Exception:
        return False


def check():
    """Retorna (required_ok: bool, linhas: list[str])."""
    out = []
    required_ok = True
    is_mac_arm = platform.system() == "Darwin" and platform.machine() == "arm64"

    # 1) ffmpeg (obrigatorio)
    if shutil.which("ffmpeg"):
        out.append(f"{OK} ffmpeg")
    else:
        required_ok = False
        out.append(f"{FAIL} ffmpeg  ->  mac: brew install ffmpeg | linux: apt install ffmpeg | win: choco install ffmpeg")

    # 2) backend de alinhamento da legenda (obrigatorio: pelo menos 1)
    if is_mac_arm and (_has_module("parakeet_mlx") or shutil.which("parakeet-mlx")):
        out.append(f"{OK} alinhamento: parakeet-mlx (Apple Silicon)")
    elif _has_module("faster_whisper"):
        out.append(f"{OK} alinhamento: faster-whisper")
    else:
        required_ok = False
        if is_mac_arm:
            out.append(f"{FAIL} alinhamento  ->  pip install parakeet-mlx   (ou: pip install '.[whisper]')")
        else:
            out.append(f"{FAIL} alinhamento  ->  pip install '.[whisper]'   (faster-whisper)")

    # 3) chave do HeyGen (obrigatorio)
    if os.environ.get("HEYGEN_API_KEY"):
        out.append(f"{OK} HEYGEN_API_KEY")
    else:
        required_ok = False
        out.append(f"{FAIL} HEYGEN_API_KEY  ->  pegue em app.heygen.com (Settings>API) e ponha no .env")

    # 4) fontes
    fonts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "fonts")
    if os.path.isdir(fonts_dir) and any(f.endswith(".ttf") for f in os.listdir(fonts_dir)):
        out.append(f"{OK} fontes (bundladas)")
    else:
        out.append(f"{WARN} fontes nao encontradas em fonts/")

    # 5) Chrome (lettering avancado, opcional)
    if any(shutil.which(b) for b in ("google-chrome", "chromium", "chromium-browser")) or \
       os.path.exists("/Applications/Google Chrome.app"):
        out.append(f"{OK} Chrome (lettering)")
    else:
        out.append(f"{WARN} Chrome ausente (lettering avancado) -> instale Google Chrome se for usar")

    # --- OPCIONAIS: MCPs e fontes de roteiro ---
    out.append("")
    out.append("  Opcionais (a skill so pede se voce for usar):")
    # Google Sheets (roteiro via planilha)
    if os.environ.get("GOOGLE_CLIENT_ID"):
        out.append(f"{OK} Google Sheets (roteiro via planilha)")
    else:
        out.append(f"{WARN} Google Sheets -> so se o roteiro vier de planilha (senao use YAML local)")
    # uazapi (notificacao WhatsApp)
    if os.environ.get("UAZAPI_INSTANCE_TOKEN"):
        out.append(f"{OK} uazapi (notificacao WhatsApp)")
    else:
        out.append(f"{WARN} uazapi -> so se quiser notificacao de progresso no WhatsApp")

    # MCPs / plugins (Claude Code) -- orientacao (nao da pra checar do script)
    out.append("")
    out.append("  MCPs / plugins do Claude Code (instale se for orquestrar pela skill):")
    out.append("    - skill 'video-ads-machine' (este repo) via marketplace/git")
    out.append("    - MCP uazapi (opcional, notificacao)  |  MCP Google (opcional, Sheets)")
    return required_ok, out


def run():
    print("== Video Ads Machine :: preflight ==\n")
    required_ok, lines = check()
    print("\n".join(lines))
    print()
    if required_ok:
        print("Tudo pronto pro minimo obrigatorio. Pode gerar video (`vam build <roteiro>`).")
        return 0
    print("Faltam itens OBRIGATORIOS (marcados [FALTA]). Resolva e rode `vam doctor` de novo.")
    return 1


if __name__ == "__main__":
    sys.exit(run())
