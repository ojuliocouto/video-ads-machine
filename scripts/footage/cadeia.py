"""Cadeia: dos segmentos renderizados ao vídeo único, com a transição de cada corte.

Também é o único lugar que EXECUTA ffmpeg por conta própria (`run`) e mede duração de vídeo
(`vdur`); os módulos de render e de grade importam `run` daqui. Quem monta strings de filtro
(`filtros_*`) nunca executa nada, e importar este módulo não chama ffmpeg.

## Por que o grafo é misto

Cada decisão abaixo nasceu de um defeito medido, e cada uma tem teste:

  - JUNÇÃO SECA É CONCAT, não xfade curto. Um xfade de 0,04 s gera UM quadro de blend no meio do
    corte e o salto se divide em dois degraus que não cruzam o limiar de cena (medido 0,23 + 0,06
    num anúncio de inserts escuros); o olho vê a mesma coisa, um corte amortecido. E um xfade de
    duração menor que um quadro COLAPSA a cadeia no primeiro corte: o arquivo saiu com 4,8 s de 85.
  - VOLTA MACIA É XFADE (whip de 0,08 s), com tipo que não rasga o quadro: deslize em dois quadros
    não lê como movimento, lê como quadro partido ao meio.
  - UM TIMEBASE SÓ. O concat devolve tb 1/1000000 e os arquivos vêm em 1/15360; o xfade exige os
    dois lados iguais. Toda entrada e toda saída intermediária passam por `settb=AVTB`.
  - CONTAGEM EXATA DE QUADROS por segmento (K = quadros do bloco + quadros da cauda). Com concat a
    cadeia saiu 0,86 s mais curta que o plano e os cortes derivaram até 0,5 s no fim: cada segmento
    perdia ~1 quadro na emenda (24 junções x 1/30 s). Aqui a soma da cadeia é aritmética, não medição.
  - QUADRO PRETO NA FRENTE: o painel de cima entrava preto por um quadro enquanto o apresentador já
    estava embaixo. O blend do xfade escondia; o concat mostra. O segmento cujo primeiro quadro é
    escuro perde esse quadro e ganha um clone no fim, então a contagem não muda.
  - Duração de transição não é só estética: ela entra na conta do offset do xfade e mexe no
    comprimento da peça. Encurtar a transição encurtou o filme (a footage caiu 18 s abaixo do áudio
    e o composite entregou 76 s em vez de 90). Cauda do segmento de junção seca é ZERO: com concat
    não há sobreposição, e cauda maior que zero viraria um quadro a mais por corte.

## Gates

`verificar_segmentos` confere cada segmento contra o esperado (diferença acima de 0,1 s desloca
todos os blocos seguintes) e `verificar_cadeia` confere a cadeia contra a ARITMÉTICA do grafo, não
contra a soma dos spans (o arredondamento para quadro inteiro acumula sub-segundo e isso não é
colapso). Colapso é perder segundos. O build que perdeu 18,7 s de fala devolveu código 0 e o
`-shortest` do mux final aparou o resto em silêncio.
"""
import os
import subprocess
from dataclasses import dataclass

from .filtros_avatar import FPS, H, W, nframes

# Tipos cujo primeiro quadro não é o apresentador. Mesma lista do `produzir_transicao`.
_TIPOS_TELA = ("insert", "logo", "lettering_logo")


class ErroFootage(RuntimeError):
    """Erro alto da footage: a mensagem diz o que falhou. O `montar.main` imprime e sai com 1."""


def run(c):
    """Roda um comando; falhou, levanta ErroFootage com o começo do comando e o fim do stderr."""
    r = subprocess.run(c, capture_output=True, text=True)
    if r.returncode != 0:
        raise ErroFootage("ERRO: " + " ".join(str(x) for x in c[:5]) + "\n " + r.stderr[-700:])
    return r


def vdur(f):
    """Duração REAL de vídeo por contagem de quadros (ignora padding de áudio)."""
    o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-count_frames",
                        "-show_entries", "stream=nb_read_frames", "-of", "default=nw=1:nk=1", f],
                       capture_output=True, text=True).stdout.strip()
    return int(o) / FPS


# ------------------------------------------------------------------ transição de cada corte

@dataclass(frozen=True)
class Transicao(object):
    """`xf` é a duração do whip (o xfade da volta para o apresentador) e `tipo` é o tipo do xfade ("auto" decide por
    corte). `xf_seco` NÃO é a duração de junção nenhuma: a junção seca é concat, de duração zero. O valor só serve,
    junto com `xf`, para ligar o concat puro (os dois quase zero, `concat_puro`)."""
    xf: float
    xf_seco: float
    tipo: str

    @classmethod
    def do_ambiente(cls, env=None):
        """Lê VAM_XF, VAM_XF_SECO e VAM_XF_TIPO.

        Decisão de direção 18/08: tudo seco; o whip de 0,20 s comia o corte na detecção E no olho
        (21 cortes com whip contra 32 secos no mesmo plano de edição). O teto de 0,08 s vale porque
        `smoothleft` é mistura de OPACIDADE: 0,20 s deixa os dois planos legíveis ao mesmo tempo
        (a página de um site mais DOIS rostos em escalas diferentes, medido em quadro). Entrada
        de insert fica quase seca (0,04 s, cerca de 1 quadro) e a VOLTA pro apresentador leva o
        whip. O concat puro só entra se os dois forem ~0. VAM_XF=0.20 volta o whip longo se o
        diretor pedir."""
        env = os.environ if env is None else env
        xf = float(env.get("VAM_XF", "0.08"))
        xf_seco = float(env.get("VAM_XF_SECO", "0.04"))
        tipo = env.get("VAM_XF_TIPO", "auto")
        if tipo in ("fadeblack", "fadewhite"):
            # fadeblack apaga a tela entre os dois quadros e, em 0,08 s, vira um flash preto de ~2
            # quadros no meio do corte ("parecia que tinha um corte, uma tela preta de 0,1 s")
            raise ErroFootage(f"ERRO: VAM_XF_TIPO={tipo} pisca a tela no meio do corte. Use auto.")
        return cls(xf=xf, xf_seco=xf_seco, tipo=tipo)


def xf_dur(bloco_que_entra, bloco_que_sai, tr):
    """Duração da transição que ENTRA neste bloco. Assimétrica de propósito: entrada de insert é
    corte seco; volta pro apresentador é o whip; apresentador com apresentador também é seco."""
    if tr.tipo != "auto":
        return tr.xf
    import produzir_transicao as _pt
    if (_pt.corte_seco_entre(bloco_que_sai, bloco_que_entra)
            or bloco_que_entra["type"] in _TIPOS_TELA):
        return 0.0
    return tr.xf


def xf_tipo(bloco_que_entra, i, bloco_que_sai, tr):
    """Tipo do xfade do corte que entra neste bloco. A regra mora em `produzir_transicao`, que é
    módulo e tem teste: duas verdades sobre a mesma escolha foi o que gerou o defeito de t=56 s."""
    import produzir_transicao as _pt
    return _pt.tipo_de_transicao(bloco_que_sai, bloco_que_entra, i, forcado=tr.tipo)


# ------------------------------------------------------------------ medidas de arquivo

def lum_primeiro_quadro(path):
    """Razão primeiro/terceiro quadro do painel de cima, em 0 a 255. Menos de 128 = descarta.

    SÓ O PAINEL DE CIMA: a média do quadro inteiro não pegou o defeito (o painel estava preto mas o
    apresentador embaixo puxava a média pra 46); o buraco é sempre no painel do insert, então mede-se
    os 60% de cima. RELATIVO AO TERCEIRO QUADRO: o limiar absoluto não pegou (o quadro preto media
    15,6 e os seguintes 61 a 65). Preto de verdade é o que está MUITO abaixo do que vem logo depois."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-frames:v", "3", "-vf",
                        f"crop={W}:{int(H * 0.6)}:0:0,format=gray,scale=32:32",
                        "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                       capture_output=True)
    d = r.stdout
    if len(d) < 3 * 1024:
        return 255
    f0 = sum(d[:1024]) / 1024.0
    f2 = sum(d[2048:3072]) / 1024.0
    if f2 <= 0:
        return 255
    return 255.0 * f0 / f2


def lum_primeiro_quadro_e_preto(valor):
    """Menos da metade da luz do terceiro quadro."""
    return valor < 128


# ------------------------------------------------------------------ grafo

def concat_puro(tr):
    """Quando o anúncio inteiro é seco (xf e xf_seco quase zero) a emenda é concat puro."""
    return tr.xf < 0.01 and tr.xf_seco < 0.01


def contagem_de_quadros(blocks, spans, tr):
    """K de cada segmento: quadros do bloco mais os quadros da cauda (zero na junção seca)."""
    N = len(blocks)
    kf = []
    for i, (s, e) in enumerate(spans):
        xf_next = xf_dur(blocks[i + 1], blocks[i], tr) if i < N - 1 else 0.0
        kf.append(nframes(e - s) + nframes(xf_next) if xf_next > 1e-6 else nframes(e - s))
    return kf


def montar_grafo(blocks, spans, tr, ini=None):
    """Grafo de filtros da cadeia: `{"fc": [...], "saida", "durs", "secos", "xf_total"}`.

    `ini[i]` é 1 quando o primeiro quadro do segmento i é preto e deve ser descartado. No concat
    puro `durs` volta None: valem as durações medidas dos arquivos."""
    N = len(blocks)
    if concat_puro(tr):
        fc = ["".join(f"[{i}:v]" for i in range(N)) + f"concat=n={N}:v=1:a=0[vcat]"]
        return {"fc": fc, "saida": "vcat", "durs": None, "secos": N - 1, "xf_total": 0.0}
    kf = contagem_de_quadros(blocks, spans, tr)
    ini = ini if ini is not None else [0] * N
    fc = []
    for i in range(N):
        fc.append(f"[{i}:v]trim=start_frame={ini[i]},setpts=PTS-STARTPTS,fps={FPS},"
                  f"tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame={kf[i]},"
                  f"setpts=PTS-STARTPTS,settb=AVTB[n{i}]")
    durs = [k / FPS for k in kf]      # a partir daqui a duração é a contada, não a medida
    acc = durs[0]
    prev = "n0"
    xf_total = 0.0
    secos = 0
    for i in range(1, N):
        xf = xf_dur(blocks[i], blocks[i - 1], tr)
        if xf <= 1e-6:
            secos += 1
            fc.append(f"[{prev}][n{i}]concat=n=2:v=1:a=0,settb=AVTB[v{i}]")
        else:
            off = acc - xf
            xf_total += xf
            fc.append(f"[{prev}][n{i}]xfade=transition={xf_tipo(blocks[i], i, blocks[i - 1], tr)}"
                      f":duration={xf}:offset={off:.4f},settb=AVTB[v{i}]")
        prev = f"v{i}"
        acc = acc + durs[i] - xf
    return {"fc": fc, "saida": prev, "durs": durs, "secos": secos, "xf_total": xf_total}


# ------------------------------------------------------------------ gates

def medir_duracoes(segs):
    return [vdur(p) for p in segs]


def verificar_segmentos(spans, durs, blocks, tr):
    """Cada segmento tem que medir (e-s) + a transição que sai dele (o último, e-s). Fora disso o
    segmento desloca todos os blocos seguintes e legenda e sobreposição dessincronizam."""
    N = len(blocks)
    for i, ((s, e), d_real) in enumerate(zip(spans, durs)):
        d_exp = (e - s) + (xf_dur(blocks[i + 1], blocks[i], tr) if i < N - 1 else 0.0)
        if abs(d_real - d_exp) > 0.1:
            raise ErroFootage(f"ERRO seg {i:02d}: duracao {d_real:.2f}s != esperada {d_exp:.2f}s "
                              f"(fonte curta ou render quebrado); abortando pra nao montar video dessincronizado")


def verificar_cadeia(real, esperado, spans_total):
    """A cadeia medida tem que bater com a aritmética do grafo (até 0,15 s). A diferença para a soma
    dos spans só vira aviso: é arredondamento de quadro inteiro, não colapso."""
    if abs(esperado - spans_total) > 0.5:
        print(f"  AVISO cadeia: grafo soma {esperado:.2f}s, spans somam {spans_total:.2f}s "
              f"({esperado - spans_total:+.2f}s de arredondamento/gaps)", flush=True)
    if abs(real - esperado) > 0.15:
        raise ErroFootage(f"ERRO cadeia: {real:.2f}s != {esperado:.2f}s esperados "
                          f"(diferenca {real - esperado:+.2f}s). A cadeia de transicoes colapsou; "
                          "abortando pra nao entregar video aparado.")
    print(f"  cadeia: {real:.2f}s (esperado {esperado:.2f}s) ok")


def montar_vchain(segs, blocks, spans, durs, tr, destino, lum=None):
    """Mede o preto de entrada, monta o grafo, roda o ffmpeg uma vez e confere a duração.

    `durs` são as durações medidas dos segmentos (valem no concat puro). Devolve
    `{"esperado", "real", "secos", "xf_total"}`."""
    lum = lum if lum is not None else lum_primeiro_quadro
    N = len(blocks)
    inputs = []
    for p in segs:
        inputs += ["-i", p]
    if concat_puro(tr):
        g = montar_grafo(blocks, spans, tr)
        durs_g = durs
        print(f"  transicoes: concat puro, {N - 1} corte(s) seco(s) sem blend")
    else:
        ini = []
        for i in range(N):
            descartar = 1 if lum_primeiro_quadro_e_preto(lum(segs[i])) else 0
            if descartar:
                print(f"  seg {i:02d}: primeiro quadro preto, descartado", flush=True)
            ini.append(descartar)
        g = montar_grafo(blocks, spans, tr, ini=ini)
        durs_g = g["durs"]
        print(f"  transicoes: {g['secos']} corte(s) seco(s) por concat + "
              f"{N - 1 - g['secos']} whip(s) de {tr.xf}s por xfade")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", "; ".join(g["fc"]), "-map", f"[{g['saida']}]",
         "-r", str(FPS), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", destino])
    esperado = sum(durs_g) - g["xf_total"]
    real = vdur(destino)
    verificar_cadeia(real, esperado, sum(e - s for s, e in spans))
    return {"esperado": esperado, "real": real, "secos": g["secos"], "xf_total": g["xf_total"]}
