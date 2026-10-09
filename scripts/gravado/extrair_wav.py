"""FASE 0: tira o áudio de cada bruto (.MOV) para duas pastas do projeto.

    wav/<take>.wav    48 kHz mono PCM, o que vai para o Voice Isolator (isolar.py)
    audio/<take>.mp3  16 kHz mono 32 kbps, leve, para ler o take

    python3 scripts/gravado/extrair_wav.py [TAKE ...] [--projeto DIR]

Os brutos vêm do campo `brutos` do plano; um bruto que não deve entrar na leva se lista em
`ignorar` (nome sem extensão). O bruto é só leitura: nada é gravado lá. Take já extraído não é
refeito. Ler o take INTEIRO antes do plano: uma ação que o áudio condena pode estar no vídeo.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado import projeto as gp  # noqa: E402
from gravado import veredito  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402


def _converter(origem, destino, formato, args):
    """ffmpeg para um .part e rename: nunca deixa arquivo pela metade com o nome final."""
    parcial = destino.with_name(destino.name + ".part")
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(origem), "-vn", "-ac", "1", *args,
           "-f", formato, str(parcial)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise InsumoInvalido("ffmpeg não encontrado: instale com `brew install ffmpeg`")
    if r.returncode != 0:
        if parcial.exists():
            parcial.unlink()
        raise InsumoInvalido("não consegui extrair o áudio de %s: %s" % (origem, r.stderr.strip()[-250:]))
    os.replace(str(parcial), str(destino))


def extrair(proj, takes=None):
    """Extrai wav e mp3 dos brutos. Devolve (extraídos ou já prontos, total considerado)."""
    brutos = proj.takes_brutos()
    if takes:
        brutos = [b for b in brutos if b.stem in set(takes)]
    proj.garantir("wav")
    proj.garantir("audio")
    feitos = 0
    for b in brutos:
        wav, mp3 = proj.wav(b.stem), proj.audio_mp3(b.stem)
        if wav.exists() and mp3.exists():
            print("  %s: já extraído" % b.stem)
            feitos += 1
            continue
        _converter(b, wav, "wav", ["-ar", "48000", "-c:a", "pcm_s16le"])
        _converter(wav, mp3, "mp3", ["-ar", "16000", "-b:a", "32k"])
        print("  %s: wav + mp3" % b.stem)
        feitos += 1
    return feitos, len(brutos)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Extrai o áudio de cada bruto.")
    ap.add_argument("takes", nargs="*", help="só estes takes (sem extensão)")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    a = ap.parse_args(argv)

    def fazer():
        proj = gp.carregar(a.projeto)
        feitos, total = extrair(proj, a.takes or None)
        print("%d/%d brutos com áudio extraído em %s e %s" % (feitos, total, proj.pasta("wav"), proj.pasta("audio")))
    return veredito.ferramenta(fazer)


if __name__ == "__main__":
    sys.exit(main())
