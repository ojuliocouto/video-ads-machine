"""A prévia leve do anúncio: `entrega/final_whatsapp.mp4`, para olhar no celular antes dos gates de saída.

O `vam montar` gera esta prévia ASSIM QUE o render termina, antes do primeiro gate de saída (seção 4 do plano): quem
dirige vê o filme enquanto os gates medem, e o laudo amarra o sha256 dela.

Por que reencodar (pendência 12.4, medido na W5.D): a cópia direta saía com o grão da grade final a 11 Mbps, 32 MB
em 23 s, pesada demais para o WhatsApp. Reencodada em 720 de largura com crf 26 e teto de 3 Mbps, a mesma peça deu
8,7 MB, e o grão continua visível (é a textura da grade, não ruído a esconder).

    from entrega import whatsapp_versao
    whatsapp_versao.gerar("entrega/final_9x16.mp4", "entrega/final_whatsapp.mp4")
"""
import subprocess
from pathlib import Path

CRF = 26
MAXRATE = "3M"
BUFSIZE = "6M"
AUDIO_KBPS = "128k"
TAXA_AUDIO = 48000
ESCALA = {"9x16": "720:1280", "1x1": "720:720"}


class ErroDaPrevia(RuntimeError):
    """O ffmpeg não gerou a prévia. A mensagem traz o fim do stderr."""


def comando(final, destino, formato="9x16"):
    """O argv do ffmpeg que gera a prévia (puro: os testes leem os números daqui)."""
    return ["ffmpeg", "-y", "-v", "error", "-i", str(final),
            "-vf", "scale=%s:flags=lanczos" % ESCALA.get(formato, ESCALA["9x16"]),
            "-c:v", "libx264", "-preset", "medium", "-crf", str(CRF), "-maxrate", MAXRATE, "-bufsize", BUFSIZE,
            "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-c:a", "aac", "-b:a", AUDIO_KBPS, "-ar", str(TAXA_AUDIO),
            "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", str(destino)]


def gerar(final, destino, formato="9x16"):
    """Gera a prévia de `final` em `destino` e devolve o Path. ErroDaPrevia se o ffmpeg falhar."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.stem + ".parcial" + destino.suffix)
    r = subprocess.run(comando(final, parcial, formato), capture_output=True, text=True)
    if r.returncode != 0 or not parcial.is_file():
        if parcial.exists():
            parcial.unlink()
        raise ErroDaPrevia("a prévia de WhatsApp não saiu: %s" % (r.stderr or "").strip()[-400:])
    parcial.replace(destino)
    return destino
