"""Conferência do avatar gerado: dimensão, fração útil do quadro, duração e prancha da boca.

    python3 scripts/avatar/conferir.py <slug> [--estado _local] [--aspecto 9:16]
    exit 0 aprovada · 1 reprovada (o arquivo é gravado do mesmo jeito) · 2 insumo inválido

Mede (ffprobe e ffmpeg):
  - dimensão: 1080x1920 para 9:16 (1080x1080 para 1:1, 1080x1350 para 4:5);
  - fração útil: o quanto do quadro NÃO é barra uniforme no topo e na base. Mede 3 quadros (10%,
    50% e 90% do vídeo) e vale o PIOR. Reprova abaixo de 0,93;
  - duração: |avatar - voz limpa| acima de 1,0 s reprova (passa em 1,0 s exatos);
  - prancha da boca: 3 quadros lado a lado em avatar/boca.png, para o aluno olhar o lip-sync.

Grava `avatar/conferencia.json` (versão 1) de forma atômica. É ESSE arquivo que
`projeto.looks.aprovar(nome, conferencia)` amarra por sha256: reconferir (ou trocar o avatar)
muda o arquivo e a aprovação vence. Formato:

    {"versao": 1, "gerado_em": "<ISO 8601>", "aspecto": "9:16",
     "resultado": "aprovada" | "reprovada",
     "avatar": {"arquivo": "avatar/avatar.mp4", "sha256": "<64 hex>", "largura": 1080,
                "altura": 1920, "duracao_s": 55.0},
     "voz": {"arquivo": "voz/limpo.mp3", "duracao_s": 55.2},
     "diferenca_duracao_s": 0.2,
     "fracao_util": 0.96, "fracao_util_por_quadro": [..3 números..],
     "barra_topo_px": 20, "barra_base_px": 20,            (do pior quadro, em 1080 linhas)
     "prancha": {"arquivo": "avatar/boca.png", "sha256": "<64 hex>", "quadros_s": [t1, t2, t3]},
     "limites": {"fracao_util_min": 0.93, "diferenca_duracao_max_s": 1.0,
                 "largura": 1080, "altura": 1920},
     "reprovacoes": ["frase por motivo", ...]}               (vazio quando aprovada)

Caminhos são relativos à raiz do projeto. Quem só pode aprovar um look com conferência que passou
chama `conferencia_passou(caminho)`.
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

if __name__ == "__main__":      # rodado direto: scripts/avatar/conferir.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from avatar.heygen_cliente import executar_real
from projeto import pastas, status

VERSAO = 1
LIMITE_FRACAO_UTIL = 0.93
LIMITE_DIFERENCA_S = 1.0
TOLERANCIA_BARRA = 6            # diferença de cinza (0 a 255) ainda considerada "linha uniforme"
INSTANTES = (0.10, 0.50, 0.90)
LARGURA_QUADRO_PRANCHA = 540
DIMENSOES = {"9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)}


class InsumoInvalido(ValueError):
    """Falta arquivo ou a mídia não pôde ser lida: não dá nem para reprovar (exit 2)."""


def fracao_util(valores):
    """(fração, barra_topo_px, barra_base_px) de uma coluna de níveis de cinza (1 pixel de largura,
    uma linha por amostra). Barra = sequência de linhas uniformes (dentro da tolerância) a partir
    da borda. Quadro todo uniforme: fração 0."""
    n = len(valores)
    if n == 0:
        return 0.0, 0, 0

    def uniformes(seq):
        k = 0
        for i in range(1, len(seq)):
            if abs(seq[i] - seq[0]) < TOLERANCIA_BARRA:
                k += 1
            else:
                break
        return k + 1 if k else 0      # uma linha sozinha na borda não é barra

    topo, base = uniformes(valores), uniformes(valores[::-1])
    if topo >= n:
        return 0.0, topo, base
    return max(0.0, 1.0 - (topo + base) / float(n)), topo, base


def _sha256(caminho):
    h = hashlib.sha256()
    with open(str(caminho), "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _sonda(executar, caminho, rotulo):
    rc, saida = executar(["ffprobe", "-v", "error", "-show_entries",
                          "stream=width,height:format=duration", "-select_streams", "v:0",
                          "-of", "json", str(caminho)])
    try:
        d = json.loads(saida)
        duracao = float(d["format"]["duration"])
    except (ValueError, KeyError, TypeError):
        d, duracao = None, 0.0
    if rc != 0 or d is None or duracao <= 0:
        raise InsumoInvalido("não consegui ler %s com o ffprobe: %s" % (rotulo, (saida or "").strip()[-160:]))
    streams = d.get("streams") or []
    if streams:
        return int(streams[0]["width"]), int(streams[0]["height"]), duracao
    return None, None, duracao


def _quadro(executar, mp4, t, saida, filtro):
    rc, msg = executar(["ffmpeg", "-v", "error", "-y", "-ss", "%.3f" % t, "-i", str(mp4),
                        "-frames:v", "1", "-vf", filtro, str(saida)])
    if rc != 0 or not Path(str(saida)).is_file():
        raise InsumoInvalido("o ffmpeg não extraiu o quadro em %.1f s: %s" % (t, (msg or "").strip()[-160:]))


def _coluna(png):
    from PIL import Image
    with Image.open(str(png)) as im:
        return list(im.convert("L").getdata())


def _prancha(quadros, destino):
    from PIL import Image
    imgs = [Image.open(str(q)).convert("RGB") for q in quadros]
    altura = max(i.height for i in imgs)
    folha = Image.new("RGB", (sum(i.width for i in imgs), altura), (0, 0, 0))
    x = 0
    for i in imgs:
        folha.paste(i, (x, 0))
        x += i.width
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    folha.save(str(destino))


def conferir(pastas_projeto, aspecto="9:16", voz=None, executar=None, agora=None):
    """Confere avatar/avatar.mp4 contra a voz limpa do projeto. Escreve avatar/conferencia.json e
    avatar/boca.png. Devolve o dict gravado. InsumoInvalido se falta insumo ou a mídia não abre."""
    executar = executar or executar_real
    p = pastas_projeto
    if aspecto not in DIMENSOES:
        raise InsumoInvalido("aspecto %r sem dimensão esperada (aceitos: %s)" % (aspecto, ", ".join(DIMENSOES)))
    voz = Path(voz) if voz else p.voz_limpo
    if not p.avatar_mp4.is_file():
        raise InsumoInvalido("falta o avatar: %s (gere com heygen_av5.py gerar)" % p.avatar_mp4)
    if not voz.is_file():
        raise InsumoInvalido("falta a voz limpa: %s (rode o áudio antes)" % voz)

    w, h, dur_av = _sonda(executar, p.avatar_mp4, "o avatar")
    if w is None:
        raise InsumoInvalido("o avatar não tem trilha de vídeo: %s" % p.avatar_mp4)
    _, _, dur_voz = _sonda(executar, voz, "a voz limpa")

    quadros_s = [round(dur_av * f, 3) for f in INSTANTES]
    util, topos, bases = [], [], []
    with tempfile.TemporaryDirectory(prefix="vam-conferir-") as tmp:
        tmp = Path(tmp)
        quadros = []
        for i, t in enumerate(quadros_s):
            _quadro(executar, p.avatar_mp4, t, tmp / ("c%d.png" % i), "scale=1:1080:flags=area,format=gray")
            f, topo, base = fracao_util(_coluna(tmp / ("c%d.png" % i)))
            util.append(f)
            topos.append(topo)
            bases.append(base)
            _quadro(executar, p.avatar_mp4, t, tmp / ("q%d.png" % i),
                    "scale=%d:-2" % LARGURA_QUADRO_PRANCHA)
            quadros.append(tmp / ("q%d.png" % i))
        _prancha(quadros, p.avatar_boca)

    pior = min(range(len(util)), key=lambda i: util[i])
    esperado = DIMENSOES[aspecto]
    diferenca = abs(dur_av - dur_voz)
    reprovacoes = []
    if (w, h) != esperado:
        reprovacoes.append("dimensão %dx%d: o esperado para %s é %dx%d" % (w, h, aspecto, esperado[0], esperado[1]))
    if util[pior] < LIMITE_FRACAO_UTIL:
        reprovacoes.append("fração útil do quadro %.3f abaixo de %.2f (barra de %d px no topo e %d px na base, "
                           "em 1080 linhas)" % (util[pior], LIMITE_FRACAO_UTIL, topos[pior], bases[pior]))
    if diferenca > LIMITE_DIFERENCA_S:
        reprovacoes.append("duração: avatar %.2f s contra voz %.2f s, diferença de %.2f s acima de %.1f s"
                           % (dur_av, dur_voz, diferenca, LIMITE_DIFERENCA_S))

    resultado = {
        "versao": VERSAO,
        "gerado_em": agora if agora is not None else status.instante(),
        "aspecto": aspecto,
        "resultado": "reprovada" if reprovacoes else "aprovada",
        "avatar": {"arquivo": p.relativo(p.avatar_mp4), "sha256": _sha256(p.avatar_mp4),
                   "largura": w, "altura": h, "duracao_s": round(dur_av, 3)},
        "voz": {"arquivo": p.relativo(voz), "duracao_s": round(dur_voz, 3)},
        "diferenca_duracao_s": round(diferenca, 3),
        "fracao_util": round(util[pior], 4),
        "fracao_util_por_quadro": [round(u, 4) for u in util],
        "barra_topo_px": topos[pior],
        "barra_base_px": bases[pior],
        "prancha": {"arquivo": p.relativo(p.avatar_boca), "sha256": _sha256(p.avatar_boca),
                    "quadros_s": quadros_s},
        "limites": {"fracao_util_min": LIMITE_FRACAO_UTIL, "diferenca_duracao_max_s": LIMITE_DIFERENCA_S,
                    "largura": esperado[0], "altura": esperado[1]},
        "reprovacoes": reprovacoes,
    }
    status.escrever_json_atomico(p.avatar_conferencia, resultado)
    return resultado


def conferencia_passou(caminho):
    """True só se o arquivo existe, é JSON válido e diz `aprovada`."""
    try:
        return status.ler_json(caminho).get("resultado") == "aprovada"
    except (OSError, ValueError, AttributeError):
        return False


def main(argv=None, executar=None):
    ap = argparse.ArgumentParser(description="Confere o avatar gerado de um projeto.")
    ap.add_argument("slug")
    ap.add_argument("--estado", help="pasta _local (padrão: a do repo)")
    ap.add_argument("--aspecto", default="9:16", choices=sorted(DIMENSOES))
    args = ap.parse_args(argv)
    try:
        r = conferir(pastas.projeto(args.slug, args.estado), args.aspecto, executar=executar)
    except (InsumoInvalido, ValueError) as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        return 2
    print("avatar %dx%d, %.1f s, fração útil %.2f, diferença de duração %.2f s"
          % (r["avatar"]["largura"], r["avatar"]["altura"], r["avatar"]["duracao_s"],
             r["fracao_util"], r["diferenca_duracao_s"]))
    print("prancha da boca: %s" % r["prancha"]["arquivo"])
    if r["reprovacoes"]:
        print("REPROVADO:")
        for x in r["reprovacoes"]:
            print("  - " + x)
        return 1
    print("OK: avatar aprovado na conferência (olhe a prancha e aprove o look).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
