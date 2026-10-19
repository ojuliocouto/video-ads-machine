"""Check: ffmpeg e ffprobe presentes, e o ffmpeg RENDERIZA pelo filtro `subtitles` (libass).

`ffmpeg -version` funcionar não prova nada: um ffmpeg compilado sem libass, ou com uma
biblioteca que o Homebrew removeu num upgrade (`dyld: Library not loaded`), passa por ele e
estoura no meio do build. Por isso o check roda um render de verdade, de um quadro, pelo
filtro, num arquivo .ass mínimo. As legendas e os letterings do motor dependem disso.

O caminho do .ass entra no filtro por `plataforma.escapar_filtro`, que escapa as DUAS camadas do ffmpeg (a opção e o
grafo): o escape de uma camada só quebrava no `C:` do Windows.
"""
import tempfile
from pathlib import Path

import plataforma

from ..doctor import FAIL, OK, Resultado

NOME = "ffmpeg_libass"

INSTALAR_MAC_LINUX = "macOS: brew install ffmpeg | Debian/Ubuntu: sudo apt install ffmpeg"
INSTALAR_WINDOWS = "Windows: winget install -e --id Gyan.FFmpeg"


def instalar():
    """O comando que instala o ffmpeg completo no sistema de quem roda."""
    return INSTALAR_WINDOWS if plataforma.eh_windows() else INSTALAR_MAC_LINUX


_ASS_MINIMO = """[Script Info]
ScriptType: v4.00+
PlayResX: 64
PlayResY: 64

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, Alignment
Style: Default,Arial,20,&H00FFFFFF,2

[Events]
Format: Layer, Start, End, Style, Text
Dialogue: 0,0:00:00.00,0:00:00.20,Default,doctor
"""


def _reinstalar():
    return INSTALAR_WINDOWS if plataforma.eh_windows() else "macOS: brew reinstall ffmpeg"


def checar(amb):
    ffmpeg, ffprobe = amb.which("ffmpeg"), amb.which("ffprobe")
    if not ffmpeg:
        return Resultado(NOME, FAIL, "ffmpeg não encontrado no PATH",
                         "instale o ffmpeg completo, com libass (%s)" % instalar())
    if not ffprobe:
        return Resultado(NOME, FAIL, "ffprobe não encontrado no PATH (vem junto do ffmpeg)",
                         "instale o ffmpeg completo, que traz o ffprobe (%s)" % instalar())
    with tempfile.TemporaryDirectory() as pasta:
        ass = Path(pasta) / "sonda.ass"
        ass.write_text(_ASS_MINIMO, encoding="utf-8")
        rc, saida = amb.executar(
            [ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.2:r=10",
             "-vf", "subtitles=" + plataforma.escapar_filtro(ass), "-frames:v", "1", "-f", "null", "-"],
            timeout=120)
    if rc == 0:
        return Resultado(NOME, OK, "ffmpeg e ffprobe presentes; render pelo filtro subtitles "
                                   "(libass) passou")
    baixo = (saida or "").lower()
    if "dyld" in baixo or "library not loaded" in baixo or "error while loading shared" in baixo:
        return Resultado(NOME, FAIL,
                         "o ffmpeg está instalado mas uma biblioteca dele sumiu (upgrade do "
                         "gerenciador de pacotes)",
                         "reinstale para religar as bibliotecas (%s)" % _reinstalar())
    if "no such filter" in baixo or "libass" in baixo or "subtitles" in baixo:
        return Resultado(NOME, FAIL,
                         "este ffmpeg foi compilado sem libass: não queima legenda nem lettering",
                         "instale um ffmpeg completo, não uma build mínima (%s)" % instalar())
    return Resultado(NOME, FAIL, "o render de teste falhou: " + (saida or "").strip()[-300:],
                     "reinstale o ffmpeg completo (%s)" % instalar())
