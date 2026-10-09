"""Auditoria das peças: o técnico MEDIDO e a fala do arquivo ENTREGUE.

Não confia no plano: mede o mp4. Se a peça perdeu palavra na montagem, só o arquivo entregue
mostra. Duas saídas:

  - o técnico de cada peça (resolução 1080x1920, áudio a 48 kHz, loudness dentro da faixa de
    entrega: -14 LUFS com 1,2 de tolerância e true peak até -1,5 dBTP, via `audio.loudness`);
  - `falas_entregues.json` ({peça: texto lido do arquivo}), o insumo dos gates de repetição e de
    fala fora do roteiro. O vocabulário e a grafia vêm do glossário do aluno. Peça que o ASR não
    leu fica como `FALHA: motivo`, e os gates de texto recusam esse JSON (saída 2).

    python3 scripts/gravado/auditar.py [--de montados|legendado] [--projeto DIR]
Saída: 0 técnico ok, 1 técnico fora da faixa, 2 insumo inválido.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from audio import loudness  # noqa: E402
from gravado import projeto as gp  # noqa: E402
from gravado import veredito  # noqa: E402
from gravado.nucleo import asr  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402
from projeto import status as _status  # noqa: E402

RESOLUCAO = "1080x1920"
TAXA = "48000"


def tecnico(arquivo):
    """{resolucao, sample_rate, duracao, lufs, true_peak, ok, motivo} do arquivo."""
    veredito.exigir_arquivo(arquivo, "a peça")
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,sample_rate",
                        "-show_entries", "format=duration", "-of", "json", str(arquivo)],
                       capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        v = next(s for s in d["streams"] if s.get("codec_type") == "video")
        a = next(s for s in d["streams"] if s.get("codec_type") == "audio")
        duracao = float(d["format"]["duration"])
    except (ValueError, KeyError, StopIteration):
        raise InsumoInvalido("%s não tem vídeo e áudio legíveis: %s" % (arquivo, r.stderr.strip()[-200:]))
    try:
        m = loudness.medir(arquivo)
    except loudness.ErroDeLoudness as e:
        raise InsumoInvalido(str(e))
    res = "%dx%d" % (v["width"], v["height"])
    problemas = []
    if res != RESOLUCAO:
        problemas.append("resolução %s (esperado %s)" % (res, RESOLUCAO))
    if a["sample_rate"] != TAXA:
        problemas.append("áudio a %s Hz (esperado %s)" % (a["sample_rate"], TAXA))
    if not loudness.dentro_da_faixa(m):
        problemas.append("loudness %.1f LUFS e pico %.1f dBTP (faixa: %.0f +- %.1f LUFS, pico até %.1f)"
                         % (m.integrado_lufs, m.true_peak_dbtp, loudness.LUFS_ALVO, loudness.TOLERANCIA_LUFS,
                            loudness.TP_ALVO))
    return {"resolucao": res, "sample_rate": a["sample_rate"], "duracao": duracao, "lufs": m.integrado_lufs,
            "true_peak": m.true_peak_dbtp, "ok": not problemas, "motivo": "; ".join(problemas)}


def gerar_falas(proj, leitor, pasta="montados"):
    """Lê a fala de cada .mp4 de `pasta` e grava `falas_entregues.json`. Devolve o dict."""
    origem = proj.pasta(pasta)
    arquivos = sorted(origem.glob("*.mp4")) if origem.is_dir() else []
    if not arquivos:
        raise InsumoInvalido("nenhum .mp4 em %s: monte as peças antes" % origem)
    falas = asr.falas_dos_arquivos(arquivos, leitor)
    _status.escrever_json_atomico(proj.falas_json, falas)
    return falas


def main(argv=None):
    ap = argparse.ArgumentParser(description="Técnico medido e fala das peças.")
    ap.add_argument("--de", choices=("montados", "legendado"), default="montados", help="de qual pasta ler as peças")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    a = ap.parse_args(argv)
    ruins = []

    def fazer():
        proj = gp.carregar(a.projeto)
        pasta = proj.pasta(a.de)
        arquivos = sorted(pasta.glob("*.mp4")) if pasta.is_dir() else []
        if not arquivos:
            raise InsumoInvalido("nenhum .mp4 em %s" % pasta)
        print("%-16s %11s %7s %7s %7s %7s  VEREDITO" % ("PEÇA", "RESOLUÇÃO", "ÁUDIO", "DUR", "LUFS", "dBTP"))
        for f in arquivos:
            t = tecnico(f)
            print("%-16s %11s %7s %6.1fs %7.2f %7.2f  %s" % (f.stem, t["resolucao"], t["sample_rate"], t["duracao"],
                                                         t["lufs"], t["true_peak"], "OK" if t["ok"] else "CONFERIR: " + t["motivo"]))
            if not t["ok"]:
                ruins.append(f.stem)
        falas = gerar_falas(proj, proj.leitor(), pasta=a.de)
        print("\nfalas dos %d arquivos salvas em %s" % (len(falas), proj.falas_json.name))
    codigo = veredito.ferramenta(fazer)
    if codigo == 0 and ruins:
        return veredito.SAIDA_DEFEITO
    return codigo


if __name__ == "__main__":
    sys.exit(main())
