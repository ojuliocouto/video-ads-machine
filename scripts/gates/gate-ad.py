#!/usr/bin/env python3
"""GATE obrigatorio: roda ANTES de declarar qualquer ad pronto.

Por que existe: numa leva de 10 anuncios produzidos em sequencia, so duracao, LUFS e ultimo frame
foram verificados, que sao as metricas baratas de medir. As que importam (legenda na tela, insert
casado com o roteiro, frame solto) exigem olhar o video, e foram puladas. Resultado: media 5,2 e a
leva inteira reprovada. Este script e o instrumento.

Checa, no arquivo entregue:
  1. quanto tempo fica SEM texto na tela (o defeito que derrubou a leva), medido no overlay com alfa
  2. o gancho: texto nos primeiros 3 s
  3. frames soltos de outra cena dentro dos inserts (piscada)
  4. se todo insert do mapa aponta para um arquivo que existe
  5. loudness

Uso (o `vam montar` chama sozinho, na etapa 12 da ordem de gates):
  python3 gate-ad.py --video entrega/final_9x16.mp4 --overlay render/overlay_render/renders/x.mov
                     [--inserts render/motor/inputs/<slug>_inserts.json] [--formato 9x16]
Saida: PASSA ou REPROVA com o motivo. Exit 1 se reprovar, 2 se o pedido ou o arquivo nao existe.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Raiz de scripts/ no sys.path: caminhos.py e a fonte unica dos caminhos do repo.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import PIL  # noqa: F401  (usado nas medicoes de quadro, mais abaixo)
except ImportError:       # dependencia que o aluno ainda nao instalou: mensagem, nao traceback
    sys.exit("Falta uma dependência Python deste gate (pillow). Instale com:\n"
             "  pip install -r scripts/gates/requirements.txt")

MAX_SEM_LEGENDA_PCT = 12.0     # acima disso o anuncio roda mudo em feed silencioso
MAX_BURACO_S = 2.5             # nenhum vao unico maior que isso
# HOOK (17/08/2026, feedback da cliente no ad13: "sem lettering chamativo e sem legenda
# nos primeiros segundos"): a janela 0-3s e onde a conversao vive, e a media global
# de legenda deixava passar buraco justamente ali. Checagem dedicada:
HOOK_JANELA_S = 3.0            # janela do gancho
HOOK_PASSO_S = 0.25            # amostragem mais fina que o resto do video
HOOK_MAX_SEM_TEXTO_S = 1.0     # acumulado sem texto tolerado dentro da janela
LUFS_ALVO, LUFS_TOL = -14.0, 1.2
FAIXA_Y, FAIXA_H = 1540, 160   # a base do quadro, onde a legenda mora desde 10/10/2026 (era 1240, o peito)



def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def dur(p):
    o = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1", p]).stdout.strip()
    try:
        return float(o)
    except ValueError:
        return 0.0


def sem_legenda(video, passo=0.5, overlay=None):
    """Devolve (pct_sem_texto, maior_buraco_s, buracos).

    Mede no OVERLAY quando disponivel: la qualquer pixel opaco e texto (legenda,
    lettering, hook ou CTA), que e o que de fato importa pro espectador no mudo.
    Medir so a faixa da legenda no video final contava o hook (que fica no centro)
    como buraco, e dava falso positivo.
    """
    from PIL import Image
    alvo = overlay or video
    usa_alpha = alvo.endswith(".mov")
    d = dur(video)
    # O overlay roda na velocidade do MOTOR e o final esta acelerado. O fator estava
    # cravado em 1.25 enquanto o build usa ACCEL = 1.30, entao a varredura parava em
    # d*1.25 e os ULTIMOS ~3,6s do overlay (CTA e logo) nunca eram medidos. Numero
    # cravado em dois arquivos diferentes envelhece calado: aqui ele passa a ser MEDIDO
    # a partir das duracoes reais dos dois arquivos, e acompanha qualquer mudanca de ACCEL.
    fator = (dur(alvo) / d) if (usa_alpha and d > 0) else 1.0
    buracos, ini = [], None
    with tempfile.TemporaryDirectory() as tmp:
        # UMA PASSADA (17/08/2026): antes era um processo ffmpeg POR AMOSTRA, com seek.
        # Num ad de 86s a 0,5s isso dava 172 processos e o gate sozinho levava minutos.
        # Extrair tudo de uma vez le o arquivo linearmente e cai pra um processo so.
        # A conta de tempo continua a mesma: quadro i corresponde a t = i * passo.
        vf = ("format=rgba" if usa_alpha else f"crop=1080:{FAIXA_H}:0:{FAIXA_Y}")
        vf = f"fps={1.0/passo}," + vf if not usa_alpha else f"fps={1.0/(passo*fator)},{vf}"
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", alvo, "-vf", vf]
        if usa_alpha:
            cmd += ["-pix_fmt", "rgba"]
        sh(cmd + [os.path.join(tmp, "f_%05d.png")])
        quadros = sorted(f for f in os.listdir(tmp) if f.endswith(".png"))
        for i, nome in enumerate(quadros):
            t = i * passo
            if t >= d:
                break
            im = Image.open(os.path.join(tmp, nome))
            if usa_alpha:
                a = [q[3] for q in im.convert("RGBA").getdata()]
                tem = (sum(1 for v in a if v > 190) / len(a)) > 0.002
            else:
                px = list(im.convert("L").getdata())
                tem = (sum(1 for v in px if v > 225) / len(px)) > 0.004
            if not tem and ini is None:
                ini = t
            elif tem and ini is not None:
                if t - ini >= 1.0:
                    buracos.append((ini, t))
                ini = None
        if ini is not None and d - ini >= 1.0:
            buracos.append((ini, d))
    total = sum(b - a for a, b in buracos)
    maior = max((b - a for a, b in buracos), default=0.0)
    return (100 * total / d if d else 0), maior, buracos


def checar_hook(video, overlay=None):
    """Mede a janela do GANCHO (0 ate HOOK_JANELA_S no video final).

    Devolve (segundos_sem_texto, t_primeiro_texto). Texto = legenda, KEY de
    lettering ou hook queimado; mede no MOV alpha quando existe (pixel opaco =
    texto nosso), igual ao sem_legenda(). Sem overlay, cai pra faixa da legenda,
    que pode dar falso positivo em hook de lettering central: nesse caso o
    chamador so reporta, nao reprova.
    """
    from PIL import Image
    alvo = overlay or video
    usa_alpha = alvo.endswith(".mov")
    d = dur(video)
    if d <= 0:
        return None, None
    fator = (dur(alvo) / d) if (usa_alpha and d > 0) else 1.0
    sem, primeiro = 0.0, None
    janela = min(HOOK_JANELA_S, d)
    with tempfile.TemporaryDirectory() as tmp:
        # mesma otimizacao do sem_legenda: uma passada em vez de um ffmpeg por amostra
        vf = "format=rgba" if usa_alpha else f"crop=1080:{FAIXA_H}:0:{FAIXA_Y}"
        fps = 1.0 / (HOOK_PASSO_S * fator) if usa_alpha else 1.0 / HOOK_PASSO_S
        cmd = ["ffmpeg", "-y", "-v", "error", "-t", str(janela * fator + 0.1),
               "-i", alvo, "-vf", f"fps={fps},{vf}"]
        if usa_alpha:
            cmd += ["-pix_fmt", "rgba"]
        sh(cmd + [os.path.join(tmp, "h_%05d.png")])
        quadros = sorted(f for f in os.listdir(tmp) if f.endswith(".png"))
        n_esperado = int(janela / HOOK_PASSO_S)
        for i in range(n_esperado):
            t = i * HOOK_PASSO_S
            tem = False
            if i < len(quadros):
                im = Image.open(os.path.join(tmp, quadros[i]))
                if usa_alpha:
                    a = [q[3] for q in im.convert("RGBA").getdata()]
                    tem = (sum(1 for v in a if v > 190) / len(a)) > 0.002
                else:
                    px = list(im.convert("L").getdata())
                    tem = (sum(1 for v in px if v > 225) / len(px)) > 0.004
            if tem and primeiro is None:
                primeiro = t
            if not tem:
                sem += HOOK_PASSO_S
    return sem, primeiro


def frames_soltos(video, limiar=0.72):
    """Frame solto de outra cena = a imagem SAI e VOLTA em menos de meio segundo.

    Contar so "dois cortes proximos" dava falso positivo em transicao de design: um
    crossfade entre avatar e insert gera varios cortes seguidos e era lido como piscada
    (o ad01v2 reprovava por um corte normal aos 46,8s). O teste certo e comparar o
    frame ANTES da rajada com o frame DEPOIS: se voltaram a ser parecidos, a cena
    piscou; se ficaram diferentes, foi transicao legitima.
    """
    from PIL import Image
    r = sh(["ffmpeg", "-i", video, "-filter_complex",
            f"select='gt(scene,{limiar})',metadata=print:file=-", "-an", "-f", "null", "-"])
    ts = sorted(float(m.group(1)) for m in
                re.finditer(r"pts_time:([0-9.]+)", r.stdout + r.stderr))
    suspeitos = [(ts[i - 1], ts[i]) for i in range(1, len(ts)) if ts[i] - ts[i - 1] < 0.4]

    def assinatura(t, tmp):
        png = os.path.join(tmp, "s.png")
        if sh(["ffmpeg", "-y", "-ss", str(max(t, 0)), "-i", video, "-frames:v", "1",
               "-vf", "scale=32:56", png]).returncode != 0 or not os.path.exists(png):
            return None
        return list(Image.open(png).convert("L").getdata())

    piscadas = []
    with tempfile.TemporaryDirectory() as tmp:
        for a, b in suspeitos:
            antes, depois = assinatura(a - 0.25, tmp), assinatura(b + 0.25, tmp)
            if not antes or not depois:
                continue
            dif = sum(abs(x - y) for x, y in zip(antes, depois)) / len(antes)
            if dif < 12:  # voltou a ser a mesma cena => piscou de verdade
                piscadas.append(b)
    return piscadas


def inserts_pendentes(caminho):
    """Inserts do mapa do motor que ficaram como pendencia ou apontam para arquivo que sumiu.

    Pular sem checar nada seria aprovar no escuro: o que importa e que nenhum insert tenha
    ficado como pendencia nem aponte para arquivo que sumiu. None se nao ha mapa."""
    if not caminho or not os.path.exists(caminho):
        return None
    d = json.load(open(caminho, encoding="utf-8"))
    ruins = []
    for k, v in d.items():
        if "_PENDENCIA" in v:
            ruins.append(f"{k} (pendencia)")
        elif not os.path.exists(v.get("file", "")):
            ruins.append(f"{k} (arquivo sumiu)")
    return sorted(ruins)


def lufs(video):
    r = sh(["ffmpeg", "-i", video, "-af", "ebur128=framelog=quiet", "-f", "null", "-"])
    m = re.search(r"I:\s*(-?[0-9.]+)\s*LUFS", r.stderr)
    return float(m.group(1)) if m else None


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="gate-ad", description="O gate obrigatorio do arquivo entregue.")
    ap.add_argument("--video", help="o arquivo entregue (mp4)")
    ap.add_argument("--overlay", help="o overlay com alfa (mov): todo pixel opaco e texto nosso")
    ap.add_argument("--inserts", help="o mapa de inserts do motor (json)")
    ap.add_argument("--formato", default="9x16", choices=("9x16", "1x1"))
    ap.add_argument("resto", nargs="*", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.resto or not a.video:
        print("uso: gate-ad.py --video <final.mp4> --overlay <overlay.mov> [--inserts <inserts.json>]\n"
              "  (o modo por numero de anuncio saiu: quem chama e o `vam montar <slug>`)", file=sys.stderr)
        return 2
    v, ov = a.video, a.overlay
    if not os.path.isfile(v):
        print(f"video nao encontrado: {v}", file=sys.stderr)
        return 2
    if ov and not os.path.isfile(ov):
        print(f"overlay nao encontrado: {ov}", file=sys.stderr)
        return 2
    print(f"\n===== {os.path.basename(v)} [{a.formato}] =====")
    problemas = []

    pct, maior, buracos = sem_legenda(v, overlay=ov)
    print(f"  sem texto na tela: {pct:.0f}% | maior vao: {maior:.1f}s")
    if pct > MAX_SEM_LEGENDA_PCT:
        problemas.append(f"{pct:.0f}% sem texto (teto {MAX_SEM_LEGENDA_PCT:.0f}%)")
    if maior > MAX_BURACO_S:
        pior = max(buracos, key=lambda b: b[1] - b[0])
        problemas.append(f"vao de {maior:.1f}s sem texto em {pior[0]:.1f}s")

    hk_sem, hk_1o = checar_hook(v, overlay=ov)
    if hk_sem is not None:
        p1 = "nunca" if hk_1o is None else f"{hk_1o:.2f}s"
        print(f"  hook (0-{HOOK_JANELA_S:.0f}s): {hk_sem:.2f}s sem texto | 1o texto em {p1}")
        estourou = hk_sem > HOOK_MAX_SEM_TEXTO_S or hk_1o is None or hk_1o > HOOK_MAX_SEM_TEXTO_S
        if estourou:
            msg = (f"hook sem texto: {hk_sem:.1f}s vazios nos primeiros "
                   f"{HOOK_JANELA_S:.0f}s (teto {HOOK_MAX_SEM_TEXTO_S:.1f}s)")
            if ov:
                problemas.append(msg)
            else:
                # sem overlay a medicao usa so a faixa da legenda e pode ser falso
                # positivo com hook de lettering central: reportar, nao reprovar.
                print(f"  AVISO (sem overlay, conferir a olho): {msg}")

    p = frames_soltos(v)
    print(f"  frames soltos/piscadas: {len(p)}")
    if p:
        problemas.append(f"{len(p)} piscadas (1a em {p[0]:.1f}s)")

    falt = inserts_pendentes(a.inserts)
    if falt:
        print(f"  inserts pendentes: {', '.join(falt)}")
        problemas.append(f"inserts pendentes: {', '.join(falt)}")
    elif falt is not None:
        print("  inserts pendentes: nenhum")

    L = lufs(v)
    print(f"  loudness: {L} LUFS | duracao: {dur(v):.1f}s")
    if L is not None and abs(L - LUFS_ALVO) > LUFS_TOL:
        problemas.append(f"loudness {L} fora de {LUFS_ALVO}+-{LUFS_TOL}")

    if problemas:
        print("  >> REPROVA:")
        for x in problemas:
            print("     - " + x)
        return 1
    print("  >> PASSA")
    return 0


if __name__ == "__main__":
    sys.exit(main())
