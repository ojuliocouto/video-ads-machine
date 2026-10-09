"""Os inserts (b-rolls) do overlay: as visitas por bloco, o encode de cada clipe e o HTML deles.

Uma VISITA é um bloco de insert com tudo que o resto do overlay precisa saber dele: de onde a
tela abre (`s2`), quanto dura, quais fatias o plano de ritmo deixou em insert (`meus`) e quais
dessas fatias são de tela cheia (`cheias`, sem apresentador embaixo).

Cap de duração (`dur_max`). Um b-roll longo no fim empurrava o CTA para 1,98 s de vida
(reprovação do diretor de arte: bloco com 11,5 s de insert e o CTA nascendo só depois dele). Com
`dur_max` o insert entrega o que o doc pede e a imagem volta ao apresentador antes do fim, que é
onde o CTA sobe. O cap NÃO corta o bloco num ponto só (18/08/2026): o `ritmo.py` espalha o
orçamento de tela em fatias pelo bloco inteiro, então a volta que interessa é o início do ÚLTIMO
plano de rosto do bloco, não `s2 + cap`.
"""
import json
import re
import sys
from collections import namedtuple

from overlay.hook import HOOK_END
from overlay.spans import achar_insert_cfg
from overlay.transcricao import run, vdur

XFADE_GAP = 0.6      # brolls a menos de isso um do outro = mesmo grupo (sem wipe entre eles)
IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp")

Visita = namedtuple("Visita", "i key icfg s e s2 dur meus cheias")


def planejar_visitas(blocks, spans, inserts_map, plano_ritmo):
    """([Visita], retorno_avatar) dos blocos de insert.

    `retorno_avatar` é [(bloco, instante)] em que a imagem VOLTA ao avatar por causa de um cap;
    é onde o CTA sobe no fim do anúncio. Bloco de insert com menos de 0,6 s não vira visita (mas
    o cap dele já foi registrado). Insert sem chave no mapa para o motor.
    """
    visitas, retorno_avatar = [], []
    for i, (b, (s, e)) in enumerate(zip(blocks, spans)):
        if b["type"] != "insert":
            continue
        key, icfg = achar_insert_cfg(b["instr"], inserts_map)
        if not icfg:
            sys.exit(f"bloco insert {i} sem key no inserts.json: {b['instr']}")
        s2 = 0.0 if i == 0 else s   # abertura: o insert é o fundo do opening desde t=0, sob o hook
        dur = e - s2
        if icfg.get('dur_max'):
            cap_d = float(icfg['dur_max'])
            if cap_d < dur:
                _rostos = [x for x in plano_ritmo if x["bloco"] == i and x["tipo"] != "insert"]
                _volta = _rostos[-1]["s"] if _rostos else s2 + cap_d
                print(f"   [cap] insert '{key}': {cap_d:.2f}s de tela espalhados em "
                      f"{dur:.2f}s de bloco; ultima volta pro avatar em {_volta:.2f}s",
                      flush=True)
                retorno_avatar.append((i, round(_volta, 2)))
        if dur < 0.6:
            continue
        # so os PLANOS que continuam sendo insert entram na janela; o trecho que o ritmo devolveu
        # pro avatar tem que ser tratado como avatar, senão o lettering daquele trecho desce pro
        # peito achando que tem insert em cima dele.
        meus = [(x["s"], x["e"]) for x in plano_ritmo if x["bloco"] == i and x["tipo"] == "insert"]
        # layout POR FATIA, não por bloco (27/08/2026, regra dos dois motores)
        cheias = {(round(x["s"], 2), round(x["e"], 2)) for x in plano_ritmo
                  if x["bloco"] == i and x["tipo"] == "insert" and x.get("layout") == "cheio"}
        if not meus:
            meus = [(s2, s2 + dur)]
        visitas.append(Visita(i, key, icfg, s, e, s2, dur, meus, cheias))
    return visitas, retorno_avatar


def montar_brolls(visitas, labels):
    """[{src_file, start, s, d, label}]: um clipe por visita. O rótulo vem de `labels` ou é a chave."""
    brolls = []
    for v in visitas:
        label = labels.get(v.key, v.key)
        brolls.append({"src_file": v.icfg["file"], "start": round(v.icfg.get("start", 0), 2),
                       "s": round(v.s2, 2), "d": round(v.dur, 2), "label": label})
    return brolls


def comando_encode(b, dst):
    """O argv do ffmpeg que prepara o clipe do b-roll: h264, recorte no `start`, laço se curto."""
    need = b["d"] + 0.6
    is_img = str(b["src_file"]).lower().endswith(IMG_EXTS)
    cmd = ["ffmpeg", "-y"]
    if is_img:
        # imagem estática: -stream_loop -1 no demuxer image2 não respeita -t de forma confiável (fica
        # rodando indefinidamente). -loop 1 repete um quadro único por -t segundos. Ken Burns leve
        # para não ficar uma imagem morta.
        dur = round(need + 0.5, 2)
        zoom = f"zoompan=z='min(zoom+0.0007,1.06)':d={int(dur*30)}:s=1080x1920:fps=30"
        cmd += ["-loop", "1", "-i", b["src_file"], "-t", str(dur),
                "-vf", zoom,
                "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", "-an", str(dst)]
    else:
        src_d = vdur(b["src_file"])
        avail = src_d - b["start"]
        if avail < need:  # laço
            cmd += ["-stream_loop", "-1"]
        # keyframes densos (seek rápido) + faststart. O "black-hole" do wipe (0,3 a 0,5 s de tela
        # preta na entrada de um insert 100% SDR) só some com o modo de captura layered/screenshot do
        # HyperFrames, que é MUITO mais pesado e estourou a memória da máquina de produção. Testado e
        # descartado: keyframes (g=1), workers=1, --experimental-fast-capture=false, --hdr, preload
        # antecipado do <video>. O modo rápido tem uma limitação própria com <video> nesse cenário.
        cmd += ["-ss", str(b["start"]), "-t", str(need + 0.5), "-i", b["src_file"],
                "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                "-vsync", "cfr", "-r", "30",
                "-g", "15", "-keyint_min", "15", "-sc_threshold", "0",
                "-force_key_frames", "expr:eq(n,0)",
                "-movflags", "+faststart", "-an", str(dst)]
    return cmd


def preparar_arquivos(brolls, out):
    """Gera `broll01.mp4`, `broll02.mp4`... em `out` e põe o nome em `b["src"]`.

    O clipe pronto é reaproveitado, MENOS o de 0 bytes: processo morto no meio do encode deixava um
    arquivo truncado que `if not dst.exists()` reusava para sempre.
    """
    for k, b in enumerate(brolls):
        name = f"broll{k+1:02d}.mp4"
        dst = out / name
        if not dst.exists() or dst.stat().st_size == 0:
            run(comando_encode(b, dst))
        b["src"] = name


def agrupar(brolls):
    """[(início, fim)] dos grupos de brolls: os que ficam a menos de XFADE_GAP um do outro são um."""
    grupos = []
    for b in brolls:
        e = b["s"] + b["d"]
        if grupos and b["s"] - grupos[-1][1] <= XFADE_GAP:
            grupos[-1] = (grupos[-1][0], e)
        else:
            grupos.append((b["s"], e))
    return grupos


def wipes_de_entrada(grupos):
    """Instantes dos wipes de ENTRADA (avatar para insert). O wipe de saída causava o flash preto e a
    transição dupla; o retorno é um fade limpo do próprio broll. Pula a abertura (já é o fade do hook)
    e o fim do hook. O wipe de grade está DESLIGADO no template; a lista só alimenta o relatório."""
    wipes = []
    for gs, ge in grupos:
        if gs > 0.34 and abs(gs - HOOK_END) > 0.3:
            wipes.append(round(gs - 0.34, 2))
    return wipes


def injetar_html(html, brolls):
    """Os blocos `<video>`, o scrim e a etiqueta de cada b-roll, mais a constante BROLLS do JS.

    Faixas: o vídeo ocupa 8 + 2k e o scrim 9 + 2k (banda 8..29, ABAIXO de #caps na 30 e dos
    letterings na 32/33 mesmo com 11 brolls); a etiqueta fica em 50 + k.
    """
    bh, bj = [], []
    for k, b in enumerate(brolls):
        tk, sk, tag_tk = 8 + 2 * k, 9 + 2 * k, 50 + k
        bid = f"b{k+1}"
        bh.append(
            f'<div id="{bid}_scrim" class="broll-scrim clip" data-start="{b["s"]}" data-duration="{b["d"]}" data-track-index="{sk}"></div>\n'
            f'<div id="{bid}_tag" class="broll-tag clip" data-start="{b["s"]}" data-duration="{b["d"]}" data-track-index="{tag_tk}">'
            # sem o pontinho aceso (28/08/2026): o circulo ambar com brilho imitava indicador de ao
            # vivo/gravando, nao indicava nada e e um dos tells mais diretos de interface gerada.
            f'<span class="t">{b["label"]}</span></div>\n'
            f'<video id="{bid}_vid" class="broll-vid clip" src="{b["src"]}" muted playsinline data-start="{b["s"]}" data-duration="{b["d"]}" data-track-index="{tk}"></video>')
        bj.append({"id": bid, "src": b["src"], "start": b["s"], "dur": b["d"], "tk": tk, "sk": sk})
    bloco = "<!-- B-ROLLS (injected) -->\n" + "\n".join(bh) + "\n\n      <!-- LOWER THIRD -->"
    constante = "const BROLLS = " + json.dumps(bj, ensure_ascii=False) + ";"
    # funcao no lugar da string: um rotulo com barra invertida nao pode virar escape do re
    html = re.sub(r"<!-- B-ROLLS \(injected\) -->.*?<!-- LOWER THIRD -->", lambda m: bloco, html, flags=re.S)
    html = re.sub(r"const BROLLS = \[.*?\];", lambda m: constante, html, flags=re.S)
    return html
