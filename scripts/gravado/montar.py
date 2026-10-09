"""Monta um anúncio de take gravado a partir do plano do projeto.

Seleciona os trechos do plano, tira o ar morto DENTRO deles (cortador por energia), costura o
vídeo bruto com o áudio higienizado, acelera pela aceleração do projeto (1,2x em take real), passa a
grade de cor e normaliza o loudness (-14 LUFS, true peak -1,5 dBTP, vídeo copiado, via `audio.loudness`).

    python3 scripts/gravado/montar.py A1 [--desconto] [--so-plano] [--projeto DIR]

`--so-plano` lista o que entra, sem renderizar nem criar pasta. Importar este módulo não faz
nada: o ffmpeg só roda dentro de `render`.

A saída é `montados/<cod>_normal.mp4` ou `<cod>_desconto.mp4`, 1080x1920 a 30 quadros, com a
rotação do contêiner aplicada (o vídeo de celular gravado em pé chega guardado deitado, com uma matriz
de rotação -90; o ffmpeg gira o quadro na entrada do grafo e o filtro de escala só ENCAIXA, nunca estica:
`force_original_aspect_ratio=decrease` mais `pad`). Um teste mede o pixel do arquivo contra o que o
próprio ffmpeg mostra da fonte, e prova que a medida reprova a rotação ignorada.

## Cor (W5.D)

A grade é o preset `estilo.grade` do `projeto.json` (padrão `quente-suave`, o de `cinema.grade`) e fecha a
cadeia com as tags bt709. Se o take é HDR (o iPhone grava em HLG, bt2020), a conversão para SDR vem ANTES da
grade, por segmento, com a LUT de `oneshot.luz`: reetiquetar HLG como bt709 mantém o pixel e erra a matriz.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from audio import loudness  # noqa: E402
from cinema import grade as _grade  # noqa: E402
from gravado import ar_morto_energia  # noqa: E402
from gravado import projeto as gp  # noqa: E402
from gravado.nucleo import energia  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402
from oneshot import luz as _luz  # noqa: E402
from projeto import modelo as _modelo  # noqa: E402

FPS = 30
LARGURA, ALTURA = 1080, 1920


class ErroDeRender(RuntimeError):
    """O ffmpeg falhou ao montar a peça."""


def _rodar(cmd):
    try:
        p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    except FileNotFoundError:
        raise ErroDeRender("ffmpeg não encontrado: instale com `brew install ffmpeg`")
    if p.returncode != 0:
        raise ErroDeRender("ffmpeg falhou: %s ...\n%s" % (" ".join(str(c) for c in cmd[:9]), p.stderr[-1200:]))
    return p


def duracao(caminho):
    return float(_rodar(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=nw=1:nk=1", caminho]).stdout.strip())


def intersecao(janela, segs):
    a, b = janela
    return [(max(a, s), min(b, e)) for s, e in segs if min(b, e) - max(a, s) > 0.08]


def manter_do_take(proj, take):
    """Segmentos do take que NÃO são ar morto, por energia no áudio higienizado (cache no projeto)."""
    chave = ("manter", take)
    if chave not in proj.memo:
        audio = proj.limpo(take)
        if not Path(audio).is_file():
            raise InsumoInvalido("falta o áudio higienizado do take %s: %s (rode o isolar antes)" % (take, audio))
        try:
            proj.memo[chave] = ar_morto_energia.manter(audio)
        except energia.ErroDeAudio as e:
            raise InsumoInvalido(str(e))
    return proj.memo[chave]


def segmentos_do_ad(proj, cod, desconto=False):
    """[(take, início, fim)] que entram no anúncio, já sem o ar morto de dentro de cada trecho."""
    try:
        trechos = proj.trechos_do_ad(cod, desconto)
    except KeyError as e:
        raise InsumoInvalido("anúncio %s da versão %s: %s" % (cod, "desconto" if desconto else "normal", e.args[0]))
    saida = []
    for take, ini, fim in trechos:
        for s, e in intersecao((ini, fim), manter_do_take(proj, take)):
            saida.append((take, round(s, 3), round(e, 3)))
    return saida


def emendas(segs, accel):
    """Instantes (s) das costuras na peça final: tempo acumulado dos segmentos já acelerado."""
    t, pontos = 0.0, []
    for _, s, e in segs[:-1]:
        t += (e - s) / accel
        pontos.append(round(t, 2))
    return pontos


def duracao_final(segs, accel):
    return sum(e - s for _, s, e in segs) / accel


def nome_da_peca(cod, desconto):
    return "%s_%s" % (cod, "desconto" if desconto else "normal")


def preset_de_grade(proj):
    """O preset de grade do projeto (`estilo.grade` do projeto.json), ou o padrão. Nome que não existe é
    insumo inválido, com a lista dos que existem, antes de qualquer ffmpeg."""
    arq = proj.base / "projeto.json"
    projeto = {}
    if arq.is_file():
        try:
            projeto = _modelo.carregar(arq)
        except _modelo.ContratoInvalido as e:
            raise InsumoInvalido(str(e))
    try:
        return _grade.do_projeto(projeto)
    except _grade.GradeDesconhecida as e:
        raise InsumoInvalido(str(e))


def _entradas(proj, segs):
    """Os `-i` do render: para cada take, o vídeo do bruto e o áudio higienizado, nesta ordem."""
    entradas = []
    for t in sorted({t for t, _, _ in segs}):
        try:
            entradas += ["-i", proj.bruto(t), "-i", proj.limpo(t)]
        except FileNotFoundError as e:
            raise InsumoInvalido(str(e))
    return entradas


def filtro_complexo(proj, segs, hdr=None):
    """O `-filter_complex` do render (texto, sem ffmpeg).

    `hdr`: {take: caminho da LUT} para os takes HDR (a conversão para SDR entra no segmento, antes de
    concatenar, porque os takes podem misturar HDR e SDR); take ausente ou False é SDR."""
    accel = proj.accel
    grade_ = _grade.cadeia(preset_de_grade(proj))
    hdr = hdr or {}
    takes = sorted({t for t, _, _ in segs})
    indice = {t: i for i, t in enumerate(takes)}
    fc, vlab, alab = [], [], []
    for i, (t, s, e) in enumerate(segs):
        vi, ai = indice[t] * 2, indice[t] * 2 + 1
        conversao = (_luz.cadeia_hdr_para_sdr(hdr[t]) + ",") if hdr.get(t) else ""
        fc.append("[%d:v]trim=%s:%s,setpts=PTS-STARTPTS,fps=%d,scale=%d:%d:force_original_aspect_ratio=decrease,"
                  "pad=%d:%d:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,%sformat=yuv420p[v%d]"
                  % (vi, s, e, FPS, LARGURA, ALTURA, LARGURA, ALTURA, conversao, i))
        fc.append("[%d:a]atrim=%s:%s,asetpts=PTS-STARTPTS,aformat=sample_fmts=fltp:sample_rates=48000:"
                  "channel_layouts=mono[a%d]" % (ai, s, e, i))
        vlab.append("[v%d]" % i)
        alab.append("[a%d]" % i)
    pares = "".join(v + a for v, a in zip(vlab, alab))
    fc.append("%sconcat=n=%d:v=1:a=1[vc][ac]" % (pares, len(segs)))
    fc.append("[vc]setpts=PTS/%s,%s[vo]" % (accel, grade_))
    fc.append("[ac]atempo=%s[ao]" % accel)
    return ";".join(fc)


def comando_render(proj, segs, saida, entradas=None, hdr=None):
    """O comando do ffmpeg (lista). `entradas` troca os `-i` (os testes passam os deles)."""
    entradas = list(entradas) if entradas is not None else _entradas(proj, segs)
    return ["ffmpeg", "-v", "error", "-y", *entradas, "-filter_complex", filtro_complexo(proj, segs, hdr),
            "-map", "[vo]", "-map", "[ao]", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-color_range", "tv", "-c:a", "aac", "-b:a", "192k", str(saida)]


def render(proj, cod, segs, desconto=False):
    """Renderiza `segs` em `montados/<peça>.mp4`. Devolve o Path."""
    entradas = _entradas(proj, segs)
    nome = nome_da_peca(cod, desconto)
    pasta = proj.garantir("montados")
    sem_loud = pasta / ("%s_semloud.mp4" % nome)
    with tempfile.TemporaryDirectory(prefix="vam-hdr-") as tmp:
        hdr = {}
        for t in sorted({t for t, _, _ in segs}):
            transferencia = _luz.transferencia_do_video(proj.bruto(t))
            if _luz.eh_hdr(transferencia):
                hdr[t] = str(_luz.gerar_lut(Path(tmp) / ("%s.cube" % transferencia), transferencia=transferencia))
        try:
            _rodar(comando_render(proj, segs, sem_loud, entradas, hdr))
            try:
                loudness.normalizar(sem_loud, proj.montado(nome))
            except loudness.ErroDeLoudness as e:
                raise ErroDeRender(str(e))
        finally:
            if sem_loud.exists():
                sem_loud.unlink()
    return proj.montado(nome)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Monta um anúncio do plano do projeto.")
    ap.add_argument("ad", help="código do anúncio no plano, como A1")
    ap.add_argument("--desconto", action="store_true", help="troca a cauda pelo CTA com desconto")
    ap.add_argument("--so-plano", action="store_true", help="lista o que entra, não renderiza")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    a = ap.parse_args(argv)
    try:
        proj = gp.carregar(a.projeto)
        if a.ad not in proj.ads:
            raise InsumoInvalido("o anúncio %s não está no plano (tem: %s)" % (a.ad, ", ".join(proj.ads) or "nenhum"))
        segs = segmentos_do_ad(proj, a.ad, a.desconto)
        total = sum(e - s for _, s, e in segs)
        print("%s %s: %d segmentos, %.2fs -> %.2fs acelerado (%sx)"
              % (a.ad, "(desconto)" if a.desconto else "(normal)", len(segs), total, total / proj.accel, proj.accel))
        for t, s, e in segs:
            print("   %s  %7.2f > %7.2f   (%5.2fs)" % (t, s, e, e - s))
        if a.so_plano:
            return 0
        destino = render(proj, a.ad, segs, a.desconto)
        print("\n-> %s  (%.2fs)" % (destino.name, duracao(destino)))
    except (InsumoInvalido, ErroDeRender) as e:
        print(str(e), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
