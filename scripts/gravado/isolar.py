"""FASE 1: higieniza o áudio pelo Voice Isolator da ElevenLabs (tira o ruído de fundo).

Sem isso nada mais funciona: o burburinho de um evento a -32 dB não deixa NENHUMA pausa virar
silêncio, e todo detector de borda depende disso. Medido num evento lotado: piso de ruído de
-32,7 dB para -90,3 dB, pico e duração intactos. Ele preserva TODAS as vozes, não só a do expert:
quem fala fora de quadro continua audível (o `gate_voz_distante` separa por nível).

  POST https://api.elevenlabs.io/v1/audio-isolation, campo `audio`, mínimo de 4,6 s por arquivo.
  Abaixo disso o áudio ganha silêncio NO FIM até 4,7 s antes de subir (o fim, para o eixo de
  tempo do take não mudar).

A chave vem da variável de ambiente ELEVENLABS_API_KEY (começa com `sk_`), nunca de arquivo. A
conta é paga por uso. Dois takes por vez; HTTP 429 espera 20 s e tenta UMA vez de novo.

    python3 scripts/gravado/isolar.py [TAKE ...] [--projeto DIR]
Lê `wav/<take>.wav` e grava `limpo/<take>.mp3`; take já isolado não sobe de novo.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado import projeto as gp  # noqa: E402
from gravado import veredito  # noqa: E402
from gravado.nucleo import energia  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402

URL = "https://api.elevenlabs.io/v1/audio-isolation"
VAR_CHAVE = "ELEVENLABS_API_KEY"
MINIMO_S = 4.6
ALVO_S = 4.7
ESPERA_429_S = 20
MIN_BYTES = 1000


def chave_do_ambiente(env=None):
    """A chave da ElevenLabs. Insumo inválido se falta ou não parece uma (`sk_...`)."""
    env = os.environ if env is None else env
    chave = (env.get(VAR_CHAVE) or "").strip()
    if not chave.startswith("sk_"):
        raise InsumoInvalido("falta a chave da ElevenLabs: exporte %s (ela começa com sk_), "
                             "crie em elevenlabs.io, Developers, API Keys" % VAR_CHAVE)
    return chave


def preparar_minimo(src, pasta):
    """`src` se já tem o mínimo da API; senão um wav em `pasta` com silêncio no fim até ALVO_S."""
    src = Path(src)
    if energia.duracao_s(src) >= MINIMO_S:
        return src
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / (src.stem + "_min.wav")
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(src), "-af",
                        "apad=whole_dur=%s" % ALVO_S, "-c:a", "pcm_s16le", str(destino)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise InsumoInvalido("não consegui completar %s até %.1fs: %s" % (src.name, ALVO_S, r.stderr.strip()[-200:]))
    return destino


def _multipart(caminho):
    fronteira = "----vam" + uuid.uuid4().hex
    corpo = ('--%s\r\nContent-Disposition: form-data; name="audio"; filename="%s"\r\n'
             "Content-Type: application/octet-stream\r\n\r\n" % (fronteira, Path(caminho).name)).encode()
    corpo += Path(caminho).read_bytes() + b"\r\n"
    corpo += ('--%s\r\nContent-Disposition: form-data; name="file_format"\r\n\r\nother\r\n--%s--\r\n'
              % (fronteira, fronteira)).encode()
    return corpo, "multipart/form-data; boundary=" + fronteira


def _transporte_http(url, cabecalhos, corpo):
    req = urllib.request.Request(url, data=corpo, headers=cabecalhos)
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:                       # rede fora, DNS, timeout
        return 0, ("%s: %s" % (type(e).__name__, e)).encode()


def isolar(src, dest, chave, transporte=None):
    """Isola `src` em `dest`. Devolve o status em texto: "cache", "ok (N KB)" ou o erro."""
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > MIN_BYTES:
        return "cache"
    with tempfile.TemporaryDirectory(prefix="vam-iso-") as pasta:
        enviar = preparar_minimo(src, pasta)
        corpo, tipo = _multipart(enviar)
    status, dados = (transporte or _transporte_http)(
        URL, {"xi-api-key": chave, "Content-Type": tipo, "Accept": "audio/mpeg"}, corpo)
    if status == 0:
        return "sem resposta: %s" % dados.decode(errors="replace")[:300]
    if status != 200:
        return "HTTP %d: %s" % (status, dados.decode(errors="replace")[:300])
    if len(dados) < MIN_BYTES:
        return "resposta curta (%d bytes): %r" % (len(dados), dados[:200])
    dest.parent.mkdir(parents=True, exist_ok=True)
    parcial = dest.with_name(dest.name + ".part")
    parcial.write_bytes(dados)
    os.replace(str(parcial), str(dest))
    return "ok (%d KB)" % (len(dados) // 1024)


def isolar_lote(proj, chave, takes=None, transporte=None, dormir=None, paralelo=2):
    """Isola `wav/*.wav` do projeto. Devolve {take: status}, em ordem alfabética."""
    dormir = dormir or time.sleep
    wavs = sorted(p for p in proj.pasta("wav").glob("*.wav") if not takes or p.stem in set(takes))
    if not wavs:
        raise InsumoInvalido("nenhum wav em %s: rode o extrair_wav antes" % proj.pasta("wav"))
    destino = proj.garantir("limpo")

    def tarefa(w):
        dest = destino / (w.stem + ".mp3")
        r = isolar(w, dest, chave, transporte)
        if r.startswith("HTTP 429"):
            dormir(ESPERA_429_S)
            r = isolar(w, dest, chave, transporte) + " (após backoff)"
        return w.stem, r

    with ThreadPoolExecutor(max_workers=max(1, paralelo)) as ex:
        return dict(ex.map(tarefa, wavs))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Higieniza o áudio dos takes pelo Voice Isolator.")
    ap.add_argument("takes", nargs="*", help="só estes takes (sem extensão)")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    a = ap.parse_args(argv)
    falhou = []

    def fazer():
        chave = chave_do_ambiente()
        proj = gp.carregar(a.projeto)
        for take, status in isolar_lote(proj, chave, a.takes or None).items():
            print("  %s: %s" % (take, status))
            if not (status.startswith("ok") or status == "cache"):
                falhou.append(take)
        if falhou:
            raise InsumoInvalido("não isolou: %s" % ", ".join(falhou))
    return veredito.ferramenta(fazer)


if __name__ == "__main__":
    sys.exit(main())
