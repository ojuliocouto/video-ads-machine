#!/usr/bin/env python3
"""GATE obrigatorio: roda ANTES de declarar qualquer ad pronto.

Por que existe: na leva AD03..AD12 eu produzi 10 anuncios seguidos verificando so
duracao, LUFS e ultimo frame, que sao as metricas baratas de medir. As que importam
(legenda na tela, insert casado com o doc, frame solto) exigem olhar o video, e eu
pulei. Resultado: media 5,2 e a leva inteira reprovada.

Pior: o defeito de legenda ja existia no AD01 (9% do tempo) e no AD02 (27%) e eu
entreguei os dois dizendo 8,5. Nao passou por descuido pontual, passou porque eu nao
tinha INSTRUMENTO. Este script e o instrumento.

Checa, por ad:
  1. quanto tempo fica SEM legenda na tela (o defeito que derrubou a leva)
  2. frames soltos de outra cena dentro dos inserts (piscada)
  3. se todo marcador do doc virou insert
  4. loudness e duracao

Uso: python3 gate_ad.py 03 04 05 ...
Saida: PASSA ou REPROVA por ad, com o motivo. Exit code 1 se algum reprovar.
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
from caminhos import ESTADO, INPUTS, OUTPUT, ROTEIROS, gate_excecoes  # noqa: E402

V1 = str(INPUTS)
OUT = str(OUTPUT)

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
FAIXA_Y, FAIXA_H = 1240, 220

# Formato do ad a medir: 9x16 (padrao) ou 1x1. So muda QUAL arquivo o gate acha; a
# medicao de legenda usa o MOV overlay (alpha do quadro inteiro), que independe do
# formato. Passado por env pra nao alterar a assinatura da CLI do gate.
FMT = os.environ.get("GATE_FMT", "9x16")


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def dur(p):
    o = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1", p]).stdout.strip()
    try:
        return float(o)
    except ValueError:
        return 0.0


def achar_video(n):
    """Pega o render MAIS RECENTE do ad.

    Antes era sorted()[-1] (ordem alfabetica). O AD01 tem duas versoes renderizadas
    (espuma_roxa e selfie_neon) e o alfabetico devolvia a selfie_neon, que nao e a
    entregue: o gate media 62,8s de um arquivo velho enquanto o atual tinha 78,3s.
    Medir o arquivo errado e pior que nao medir."""
    # Ad de outra leva ja vem prefixado ("jh13"): prefixar "ad" de novo procurava
    # "adjh13v2_" e o gate dizia "video nao encontrado" com o arquivo pronto do lado.
    # Quarto lugar onde o prefixo estava cravado (audio, avatar, config e aqui).
    pref = "" if str(n).startswith("jh") else "ad"
    c = [os.path.join(OUT, f) for f in os.listdir(OUT)
         if f.startswith(f"{pref}{n}v2_") and f.endswith(f"_v2composite_{FMT}.mp4")]
    return max(c, key=os.path.getmtime) if c else None


def achar_overlay(n):
    """O MOV alpha do ad: nele TODO pixel opaco e texto nosso, entao medir ali e exato."""
    base = ESTADO
    pref = "" if str(n).startswith("jh") else "ad"
    cands = list(base.glob(f"render-{pref}{n}v2-*-ovlonly/renders/*.mov"))
    # o dir do 1x1 termina em _1x1-ovlonly; o do 9x16 nao. Filtrar pra nao medir o
    # overlay do formato errado quando os dois existem.
    if FMT == "1x1":
        cands = [p for p in cands if "_1x1-ovlonly" in str(p.parent.parent)]
    else:
        cands = [p for p in cands if "_1x1-ovlonly" not in str(p.parent.parent)]
    return str(max(cands, key=lambda p: p.stat().st_mtime)) if cands else None


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


def inserts_pendentes(n):
    """Equivalente do check de marcadores pra essa outra leva.

    O roteiro dela nao usa marcador de letra do doc (`][a]`), usa chave nomeada, entao
    `marcadores_faltando` nao se aplica. Pular sem checar nada seria aprovar no escuro:
    o que importa aqui e que nenhum insert tenha ficado como pendencia nem aponte pra
    arquivo que sumiu."""
    ins = os.path.join(V1, f"{n}v2_inserts.json")
    if not os.path.exists(ins):
        return None
    d = json.load(open(ins, encoding="utf-8"))
    ruins = []
    for k, v in d.items():
        if "_PENDENCIA" in v:
            ruins.append(f"{k} (pendencia)")
        elif not os.path.exists(v.get("file", "")):
            ruins.append(f"{k} (arquivo sumiu)")
    return sorted(ruins)


def marcadores_faltando(n):
    if str(n).startswith("jh"):
        return inserts_pendentes(n)
    doc = os.path.join(str(ROTEIROS), f"ad{int(n):02d}.txt")
    ins = os.path.join(V1, f"ad{n}v2_inserts.json")
    if not (os.path.exists(doc) and os.path.exists(ins)):
        return None
    letras_doc = set(re.findall(r"\]\[([a-z]{1,2})\]", open(doc, encoding="utf-8").read()))
    # excecoes DOCUMENTADAS: marcador que nao e asset baixavel (ex: link de design que o
    # doc manda CRIAR, ou marcador de direcao). Ficam num json a parte pra a dispensa ser
    # explicita e auditavel, nunca uma decisao silenciosa minha no meio do codigo.
    exc_path = gate_excecoes()
    if exc_path and os.path.exists(exc_path):
        exc = json.load(open(exc_path, encoding="utf-8")).get(n, {})
        letras_doc -= set(exc)
    d = json.load(open(ins, encoding="utf-8"))
    usadas = set()
    for v in d.values():
        # aceita sufixo depois do marcador (ad07_ai_video.mp4 = marcador [ai] convertido
        # de PNG pra video). Sem isso o gate acusava marcador faltando por causa do nome.
        m = re.match(rf"ad{int(n):02d}_([a-z]{{1,2}})(?:[._])", os.path.basename(v["file"]))
        if m:
            usadas.add(m.group(1))
    return sorted(letras_doc - usadas)


def lufs(video):
    r = sh(["ffmpeg", "-i", video, "-af", "ebur128=framelog=quiet", "-f", "null", "-"])
    m = re.search(r"I:\s*(-?[0-9.]+)\s*LUFS", r.stderr)
    return float(m.group(1)) if m else None


def main():
    if any(a in ("-h", "--help") for a in sys.argv[1:]):
        print(__doc__)
        return
    if not os.path.isdir(OUT):
        # a pasta de renders e do SEU anuncio (_local): mensagem unica, sem traceback
        from material_local import exigir
        exigir(OUT, "a pasta de saída dos renders do seu anúncio")
    alvos = sys.argv[1:] or [f"{i:02d}" for i in range(1, 13)]
    reprovou = False
    for n in alvos:
        v = achar_video(n)
        print(f"\n===== AD{n} [{FMT}] =====")
        if not v:
            print("  video nao encontrado"); reprovou = True; continue
        problemas = []

        ov = achar_overlay(n)
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

        rot = "inserts pendentes" if str(n).startswith("jh") else "marcadores do doc"
        falt = marcadores_faltando(n)
        if falt:
            print(f"  {rot}: {', '.join(falt)}")
            problemas.append(f"{rot}: {', '.join(falt)}")
        elif falt is not None:
            print(f"  {rot}: nenhum" if str(n).startswith("jh")
                  else "  marcadores do doc: todos usados")

        L = lufs(v)
        print(f"  loudness: {L} LUFS | duracao: {dur(v):.1f}s")
        if L is not None and abs(L - LUFS_ALVO) > LUFS_TOL:
            problemas.append(f"loudness {L} fora de {LUFS_ALVO}±{LUFS_TOL}")

        if problemas:
            reprovou = True
            print("  >> REPROVA:")
            for x in problemas:
                print("     - " + x)
        else:
            print("  >> PASSA")

    sys.exit(1 if reprovou else 0)


if __name__ == "__main__":
    main()
