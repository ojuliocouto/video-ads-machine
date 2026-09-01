#!/usr/bin/env python3
"""
Produz o reel a partir do ROTEIRO ANOTADO da Jheni (parser) + avatar HeyGen + inserts.
Timing de cada bloco vem do alinhamento da narracao ao audio do avatar.
Blocos: orig (avatar+zoom), insert (b-roll), logo (card OCC), lettering (texto animado).
"""
import os, re, sys, json, glob, subprocess, unicodedata, difflib
from PIL import Image, ImageDraw, ImageFont
from parser_roteiro import parse

from caminhos import DADOS as _D, ESTADO as _EST  # noqa: E402
BASE=str(_D)
# TMP e POR RUN (18/08/2026): dois builds em paralelo compartilhavam _tmp_rot com os
# mesmos sNN.mp4 e se atropelavam; o gate de duracao abortava os dois com numeros
# malucos (seg de 3,0s medindo 1,07s: era o arquivo do OUTRO ad pela metade).
TMP=os.path.join(BASE,"_tmp_rot",
                 os.path.splitext(os.environ.get("VAM_OUT","default"))[0])
OUTD=os.path.join(BASE,"output")
os.makedirs(TMP, exist_ok=True)
os.makedirs(TMP,exist_ok=True)
W,H,FPS=1080,1920,30
PK=os.path.expanduser("~/.local/bin/parakeet-mlx")
FONTS=os.path.join(BASE,"fonts")
AVATAR=os.path.expanduser(os.environ.get("VAM_AVATAR", os.path.join(BASE,"inputs","avatar_thales.mp4")))
LOGO=os.path.join(BASE,"assets","logo_occ_branca.png")
MASK=os.path.join(BASE,"assets","circle_mask.png")
RING=os.path.join(BASE,"assets","circle_ring.png")
SHADOW=os.path.join(BASE,"assets","circle_shadow.png")
SUNBURST=os.path.join(BASE,"assets","sunburst.png")
LOGOGLOW=os.path.join(BASE,"assets","logo_glow.png")
LIGHTLEAK=os.path.join(BASE,"assets","lightleak.png")
LIGHTLEAK_FLASH=os.path.join(BASE,"assets","lightleak_flash.mov")
TOPSCRIM=os.path.join(BASE,"assets","top_scrim.png")
DARK="0x141210"
# CAP=0 -> nao queima legendas (o Submagic faz). REFRAME -> puxa rosto pra cima (legenda do Submagic
# cai no terco inferior, livre do rosto). Zoom achatado pq o magicZooms do Submagic faz os punch-ins.
CAP = os.environ.get("CAP","1")=="1"
BAKE_LETTERING = os.environ.get("VAM_BAKE_LETTERING","0")=="1"  # 1 = serif baked nas cenas de lettering (ad01+)
LETTER_STYLE = os.environ.get("VAM_LETTER_STYLE","atual")  # "atual"=laranja chapado (ad34) | "foil"=gradiente metalico EA Premium (AD01+)
# VERSAO do render por segmento (31/08/2026, cache por segmento). Entra na chave sha256
# de cache_segmento.chave_segmento(): mude este valor sempre que qualquer r_orig/r_insert/
# r_split_tela/r_lettering_serif mudar o filtro de video, senao o build proximo reaproveita
# cache velho (pixel errado) achando que e o mesmo segmento.
VERSAO_RENDER = "v1"
REFRAME = "scale=2376:4224:force_original_aspect_ratio=increase,crop=2160:3840:108:652"
# PIPY 150 -> 290 (20/08/2026, medido pelo diretor de arte): com 150 o circulo ia de
# y150 a y450 e a safe zone do Reels comeca em y269, ou seja 119px (40% do circulo)
# ficavam ATRAS da UI do app. Pior, a sombra de 420px comecava em y=90. Com 290 sobra
# 21px de folga abaixo da safe zone.
PIP=300; PIPX=(W-300)//2; PIPY=290   # PiP circular do Thales (fora da safe zone do topo)
PIPF=(420-300)//2                    # offset da moldura (sombra/anel 420) p/ centralizar no avatar 300
XF=float(os.environ.get("VAM_XF","0.08"))          # DECISAO DE DIRECAO 18/08: tudo
# seco. O whip de 0,20s comia o corte na deteccao E no olho (21 cortes com whip,
# 32 seco, mesmo plano de edicao). A referencia corta seco; o receio de "cru" era
# da era fadeblack. Volta com VAM_XF=0.20 por env se o Julio pedir.
# TETO DE 0,08s (19/08/2026, segunda correcao do mesmo dia). Eu subi pra 0,20 de manha
# respondendo ao "os cortes estao secos" do Julio, e reintroduzi um defeito que a
# auditoria de 17/07 ja tinha diagnosticado: `smoothleft` e mistura de OPACIDADE, entao
# 0,20s deixa os dois planos legiveis ao mesmo tempo. Conferido em quadro aos 40,83s do
# entregue: a pagina do Cloudflare mais DOIS rostos do Thales em escalas diferentes, tudo
# sobreposto. O proprio arquivo ja registrava 0,08 como o teto seguro medido. Whip de
# verdade (borrao direcional com concat duro escondido dentro) fica pra Wave 4.
# ASSIMETRIA DE VOLTA (19/08/2026): o Julio assistiu o corte 100% seco e reprovou
# ("os cortes estao secos..."), confirmando o gosto de 12/08. Entrada de insert fica
# quase seca (0,04s, ~1 quadro) e a VOLTA pro avatar leva whip de 0,20s. O concat puro
# so entra se os dois forem ~0 por env.
# CORTE SECO na entrada de insert (18/08/2026). 0,04s a 30fps e ~1 quadro: le como
# corte, nao como transicao. Nao passa pelo preto (e cross, nao fade-to-black), entao
# a regra "corte nunca passa pelo preto" continua valendo.
XF_SECO=float(os.environ.get("VAM_XF_SECO","0.04"))
# TRANSICAO, estilo CapCut. "fadeblack" e PROIBIDO: ele apaga a tela entre os dois
# quadros, e em 0.08s isso vira um flash preto de ~2 frames no meio do corte. Foi o que
# o Julio viu em 12/08: "parecia que tinha um corte, uma tela preta de 0,1s, e ai seguia".
# Fui eu que liguei o fadeblack tentando resolver o corte seco: troquei um defeito por
# outro pior.
#
# O corte do CapCut nao e um fade: e um EMPURRAO. Entrada de insert leva punch de zoom
# (zoomin), volta pro avatar leva um whip lateral curto, e o resto dissolve. Nenhum dos
# tres passa pelo preto, entao da pra usar 0.20s sem flash e sem fantasma.
XFT=os.environ.get("VAM_XF_TIPO","auto")   # "auto" = por corte; ou um nome fixo do xfade
if XFT=="fadeblack" or XFT=="fadewhite":
    sys.exit(f"ERRO: VAM_XF_TIPO={XFT} pisca a tela no meio do corte. Use auto.")


def _lum_primeiro_quadro(path):
    """Luminancia media do primeiro quadro de um arquivo, em 0-255. -1 se nao medir."""
    # SO O PAINEL DE CIMA (31/08/2026, build 40). Media do quadro inteiro nao pegou o
    # defeito: o painel de cima estava preto mas o apresentador embaixo puxava a media
    # para 46. O buraco e sempre no painel do insert, entao mede-se os 60% de cima.
    # RELATIVO AO TERCEIRO QUADRO (31/08/2026, build 41). O limiar absoluto de 12 nao
    # pegou: o quadro preto do s02 media 15,6 (o fundo do painel nao e preto puro) e os
    # seguintes 61 a 65. Preto de verdade e o que esta MUITO abaixo do que vem logo
    # depois. Devolve a razao primeiro/terceiro em 0-255 escalada: <0,5 = descarta.
    r=subprocess.run(["ffmpeg","-v","error","-i",path,"-frames:v","3","-vf",
                      f"crop={W}:{int(H*0.6)}:0:0,format=gray,scale=32:32",
                      "-f","rawvideo","-pix_fmt","gray","-"],
                     capture_output=True)
    d=r.stdout
    if len(d)<3*1024: return 255
    f0=sum(d[:1024])/1024.0; f2=sum(d[2048:3072])/1024.0
    if f2<=0: return 255
    return 255.0*f0/f2      # <128 significa menos da metade da luz do terceiro quadro

def xf_dur(bloco_que_entra, bloco_que_sai=None):
    """Duracao da transicao que ENTRA neste bloco. Assimetrica de proposito.

    Entrada de insert = corte seco (XF_SECO). Volta pro avatar = whip (XF). Ver o
    conflito declarado no topo: o Julio pediu transicao em 12/08 e corte seco em 18/08;
    a assimetria atende os dois, que e o que as referencias fazem.
    """
    if XFT != "auto":
        return XF
    # DURACAO SECA TAMBEM ENTRE DOIS PLANOS DO APRESENTADOR (29/08/2026). Trocar so o
    # TIPO esconderia a faixa do deslize sem tirar; encurtar so a DURACAO deixaria o
    # deslize acontecendo rapido demais, que e outro jeito de piscar. Os dois juntos e
    # que fazem virar corte.
    import produzir_transicao as _pt
    # XF_CORTE (1 quadro) FOI REVERTIDO (29/08/2026). A ideia era virar corte de verdade
    # pra recuperar o ritmo, e o efeito medido foi outro: a footage caiu de 120,40s para
    # 102,20s, ou seja 18 segundos a menos que o audio de 121,3s, e o composite (que corta
    # pelo mais curto) entregou 76,2s em vez de 90,0s. O anuncio saiu MUTILADO.
    # O ritmo tambem piorou em vez de melhorar: 12,6 cortes/min contra 14,1.
    # Licao: duracao de transicao nao e so estetica, ela entra na conta de offset do
    # xfade e mexe no comprimento da peca. Encurtar transicao encurta o filme.
    # Corte de verdade (sem blend nenhum) exige nao usar xfade nessa fronteira, que e
    # mudanca de estrutura do grafo de filtros, nao de constante.
    # JUNCAO SECA E CONCAT, ENTAO A CAUDA E ZERO (31/08/2026). O segmento anterior era
    # renderizado com (e-s)+xf de sobra pra o xfade consumir; com concat nao ha
    # sobreposicao, entao cauda maior que zero viraria um quadro a mais por corte
    # (12 cortes = 0,4s de deriva). Zero aqui e o que faz a soma fechar.
    if (_pt.corte_seco_entre(bloco_que_sai, bloco_que_entra)
            or bloco_que_entra["type"] in ("insert", "logo", "lettering_logo")):
        return 0.0
    return XF


def xf_tipo(bloco_que_entra, i, bloco_que_sai=None):
    """Delegado pro `produzir_transicao`, que e modulo e tem teste.

    A regra nova (29/08/2026): apresentador -> apresentador e corte SECO. Ver o defeito
    de t=56,03s documentado la. O corpo antigo continua abaixo como referencia morta? Nao:
    foi movido inteiro, pra nao existirem duas verdades sobre a mesma escolha.
    """
    import produzir_transicao as _pt
    return _pt.tipo_de_transicao(bloco_que_sai, bloco_que_entra, i, forcado=XFT)


def _xf_tipo_legado(bloco_que_entra, i):
    """Transicao do corte que ENTRA neste bloco. Nenhuma escurece nem amplia o quadro.

    Medido em material real do AD14 (testar_transicoes.py), no corte mais duro do ad:
    slide 30.2 de movimento e ZERO escurecimento; smooth 16.5 e zero. As descartadas e
    o porque: fadeblack apaga a tela (queda 68.8), e zoomin AMPLIA tanto no meio do
    corte que vira borrao escuro. O zoomin passou no teste sintetico e falhou no
    material real, entao a regra e medir no material do proprio ad, nunca no nome.
    """
    if XFT!="auto":
        return XFT
    t=bloco_que_entra["type"]
    if t in ("insert","logo","lettering_logo","lettering"):
        return "slideleft" if i%2 else "slideright"  # empurrao seco pra tela nova
    return "smoothleft" if i%2 else "smoothright"    # whip macio na volta pro avatar
# XF=0.18 (valor antigo) causava dupla exposicao fantasma (>=100ms de blend) em cortes de
# alto contraste avatar-escuro/insert-branco, confirmado em auditoria 17/07/2026 (8 videos,
# ad07-10, TODOS os looks, nao so os de fundo claro). 0.08 e o teto seguro medido (max 2
# frames/66ms residual em todos os cortes testados).
# transicoes que o Julio curtiu (blog Clipchamp): 20=Empurrar(push) e 15=Zoom. Alterna pra dar ritmo.
TRANS=["slideleft","zoomin","slideright","slideup","zoomin","slideleft",
       "slideright","zoomin","slidedown","slideleft","zoomin","slideright","slideup","zoomin"]
def nframes(d): return max(1, round(d*FPS))
def cap(N): return f"trim=end_frame={N},setpts=N/{FPS}/TB"
def vdur(f):  # duracao REAL de video por contagem de frames (ignora padding de audio)
    o=subprocess.run(["ffprobe","-v","error","-select_streams","v","-count_frames",
        "-show_entries","stream=nb_read_frames","-of","default=nw=1:nk=1",f],
        capture_output=True,text=True).stdout.strip()
    return int(o)/FPS

def run(c):
    r=subprocess.run(c,capture_output=True,text=True)
    if r.returncode!=0: print("ERRO:"," ".join(c[:5]),"\n",r.stderr[-700:]); sys.exit(1)
    return r
def norm(w):
    w=unicodedata.normalize("NFD",w.lower()); return re.sub(r"[^\w]","","".join(c for c in w if unicodedata.category(c)!="Mn"))

# fontes de insert por palavra-chave (vem dos comentarios do doc)
# VAM_INSERTS_JSON aponta um mapa {keyword: {file,start,speed,zoom}} para um anuncio novo; sem ele, usa o do ad34.
_ins_json=os.environ.get("VAM_INSERTS_JSON")
if _ins_json:
    INSERTS=json.load(open(_ins_json))
else:
    INSERTS={
      "banco de skills": {"file":os.path.join(BASE,"inserts","banco_skills_prep.mp4"),"start":0,"speed":1.0,"zoom":1.0},
      "imers":           {"file":os.path.join(BASE,"inserts","imersao.mp4"),"start":3,"speed":1.5,"zoom":1.0},
    }
def find_insert(instr):
    """Insert que a instrucao do roteiro pede, casado por keyword.

    FALHA ALTO QUANDO NAO ACHA (28/08/2026). O `return list(INSERTS.values())[0]` que
    estava aqui trocava o asset EM SILENCIO: bloco cuja keyword nao batesse passava a
    mostrar o PRIMEIRO insert do config, e nada no log dizia isso. O outro motor
    (`gen_ad_v2.py`) ja fazia `sys.exit` no mesmo caso, entao os dois discordavam sobre o
    que e erro: um parava o build e o outro entregava a peca com o asset trocado.
    Quem pagaria a conta e quem tentasse a correcao mais obvia do mundo, tirar um insert
    do config: o bloco nao some, ele silenciosamente vira outro asset.
    Substituicao muda o que aparece na tela, entao nao pode ser decisao de fallback.
    """
    s = instr.lower()
    for k, v in INSERTS.items():
        if k in s:
            return v
    raise SystemExit(
        f"ERRO: nenhum insert do config casa com a instrucao {instr!r}.\n"
        f"       keywords disponiveis: {', '.join(sorted(INSERTS))}\n"
        "       Corrija a keyword no roteiro ou a entrada no *_inserts.json. "
        "Trocar de asset em silencio nao e opcao.")

# ---------- alinhar narracao ao audio do avatar ----------
def align(avatar, narr_words):
    wav=os.path.join(TMP,"av.wav"); run(["ffmpeg","-y","-i",avatar,"-vn","-ac","1","-ar","16000",wav])
    run([PK,wav,"--output-format","json","--output-dir",TMP])
    audio_dur=float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
        "-of","default=nw=1:nk=1",avatar],capture_output=True,text=True).stdout.strip())
    d=json.load(open(glob.glob(os.path.join(TMP,"av.json"))[0])); raw=[]
    def grab(o):
        if isinstance(o,dict):
            if 'tokens' in o and isinstance(o['tokens'],list):
                for t in o['tokens']: raw.append((float(t['start']),float(t['end']),t.get('text','')))
            for v in o.values(): grab(v)
        elif isinstance(o,list): [grab(v) for v in o]
    grab(d); raw.sort()
    pk=[]
    for s,e,txt in raw:
        nw=txt.startswith(' ') or not pk; c=txt.strip()
        if not c: continue
        if nw: pk.append([s,e,c])
        # o parakeet quebra uma palavra em varios tokens ("Ag"+"ora"). Estender so o
        # tempo final SEM concatenar o texto deixava a palavra TRUNCADA ("Ag"), e o
        # difflib abaixo entao casava so ~39% das palavras (o resto virava interpolacao
        # de 0.18s fixo, comprimindo os spans e adiantando os inserts em ate 9s).
        # Bug real achado no ad01v2 em 04/08/2026: o insert do climax durava 1.6s.
        else: pk[-1][1]=e; pk[-1][2]+=c
    # ALINHAMENTO PRECISO: casa palavra do roteiro <-> palavra do parakeet por difflib (nao por proporcao).
    # Assim cada fronteira de bloco (= fim da ultima palavra do bloco) cai num FIM DE PALAVRA real,
    # e os cortes/dissolves nao pegam o meio da fala do Thales.
    pk=[(s,e,c) for s,e,c in pk]
    pk_norm=[norm(c) for *_,c in pk]
    sn=[norm(w) for w in narr_words]
    sm=difflib.SequenceMatcher(None, pk_norm, sn, autojunk=False)
    times=[None]*len(narr_words)
    for a,b,size in sm.get_matching_blocks():
        for k in range(size):
            times[b+k]=(pk[a+k][0], pk[a+k][1])
    # CAUDA FINAL sem casamento (parakeet as vezes nao reconhece as ultimas palavras: voz baixa,
    # respiracao, fade-out): sem este fix, a interpolacao abaixo usava +0.18s fixo por palavra,
    # ancorada na ultima palavra REALMENTE casada, cortando a fala real ~1s antes do fim do audio
    # (bug real: ad08/ad09 perdiam "ainda ta disponivel"/"tem vaga" do CTA final). Fix: se a cauda
    # do roteiro ficou sem casamento, ancora o fim dela no fim REAL do audio.
    if times and times[-1] is None:
        times[-1]=(max(0.0,audio_dur-0.05), audio_dur)
    # interpola as palavras nao-casadas (variacoes script vs voz) entre as vizinhas casadas
    last=None
    for i in range(len(times)):
        if times[i] is None:
            nxt=next((times[j] for j in range(i+1,len(times)) if times[j]),None)
            if last and nxt and nxt[0]>last[1]: times[i]=(last[1], nxt[0])
            elif last: times[i]=(last[1], last[1]+0.18)
            elif nxt: times[i]=(max(0.0,nxt[0]-0.18), nxt[0])
            else: times[i]=(i*0.3, i*0.3+0.3)
        last=times[i]
    return [(times[i][0], times[i][1], narr_words[i]) for i in range(len(narr_words))]

# ---------- renderers ----------
def r_orig(text,s,e,out,wt=None,idx=0,base=1.0):
    """Bloco de avatar. O ZOOM ALTERNA de sentido a cada bloco: um empurra pra dentro,
    o seguinte puxa pra fora.

    Antes todo bloco empurrava pra dentro na mesma velocidade, entao a cada corte a
    imagem "voltava" pro mesmo tamanho e recomecava igual: o olho lia como parado. O
    Julio pegou isso ("cade os fade-in fade-out e zoom in zoom out quando o thales ta
    na tela?"). Alternando, cada corte muda de direcao e o plano respira.
    """
    d=e-s; N=nframes(e-s); ass=caption_ass(text,s,d,wt)   # legenda karaoke embaixo
    # AMPLITUDE: 16%, percorrida ao longo do BLOCO INTEIRO. Antes era 8% com passo fixo
    # por frame, entao num bloco de 11s dava menos de 1% por segundo e ninguem via ("cade
    # os efeitos de zoom quando o Thales ta na tela?"). Amarrar ao numero de frames faz o
    # movimento durar exatamente o bloco, seja ele de 2s ou de 12s.
    AMPL = 0.16
    # ESCALA BASE por sub-plano (18/08/2026): subdividir o bloco nao criava corte visivel,
    # porque a imagem seguia continua e so a direcao do zoom mudava. Com base diferente
    # (1.00 / 1.14 / 1.28) o tamanho da cabeca muda DE UMA VEZ entre um plano e o outro:
    # e o jump cut de reel, e nao precisa de asset nenhum.
    if idx % 2 == 0:
        z = f"{base}+{AMPL}*on/{max(N-1,1)}"               # empurra pra dentro
    else:
        z = f"{base + AMPL}-{AMPL}*on/{max(N-1,1)}"        # puxa pra fora
    vf=(f"fps={FPS},{REFRAME},"
        f"zoompan=z='{z}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H},setsar=1,{cap(N)}{_sub(ass)}")
    run(["ffmpeg","-y","-ss",str(s),"-t",str(d+0.4),"-i",AVATAR,"-vf",vf,"-r",str(FPS),
         "-an","-c:v","libx264","-pix_fmt","yuv420p",out])
# ---------------------------------------------------------------- SPLIT SCREEN
# Tela dividida: gravacao de tela EM CIMA, Thales EMBAIXO. Pedido do Julio (14/08):
# "pode deixar a tela pequena dentro de um mockup OU tela dividida, com thales embaixo e o
# video em cima. nao vai ter regravacao."
#
# Por que resolve: a gravacao de tela e LARGA. Encaixada num canvas 9:16 pela largura, ela
# vira uma tira de ~600px dentro de 1920 e sobra borrao; foi o "fora de enquadro" do AD21.
# Num painel largo e baixo ela cabe inteira, no tamanho natural, sem enchimento. De quebra
# o Thales fica na tela durante o insert, o que mata o vao de avatar sozinho.
#
# As alturas saem de duas medidas, nao de gosto:
#   - a legenda vive centrada em cy=1250 (ver caption_ass), entao ela cai DENTRO do painel
#     de baixo e precisa de peito/microfone atras dela, nao de rosto.
#   - o rosto do Thales ocupa y330 a y980 na fonte 1080x1920 (medido no frame do avatar).
# INSERT DOMINANTE (18/08/2026, item 4 do brief no padrao-edicao.md): o painel da tela
# ocupa ~60% e o Thales ~40%, a faixa medida nas referencias REF-01/REF-02. Era 980
# (~51%) e o split parecia meio a meio. Env pra ajuste por leva, sem editar codigo.
SPLIT_TOP_H = int(os.environ.get("VAM_SPLIT_TOP_H", "1150"))
SPLIT_BOT_H = H - SPLIT_TOP_H   # deriva: estava 980 digitado 2x, e dessincronizava
# altura do degrade escuro na emenda dos paineis (item 5 do brief): "sempre degrade,
# nunca linha dura" (banco-referencias-edicao, REF-01 e REF-02).
SPLIT_GRAD = int(os.environ.get("VAM_SPLIT_GRAD", "90"))
SPLIT_AV_SRC = (0, 100, 1080, 1600)   # janela do avatar (x,y,w,h): cabeca + peito + micro
V2L_MOLDURAS = str(_EST / "molduras")   # PNGs de moldura, cacheados


def _split_avatar(s, d):
    """Filtro do painel de baixo: Thales reduzido, centrado, sobre fundo desfocado dele mesmo.

    Reduzo em vez de recortar 1080x940 direto porque o rosto dele ocupa 34% da fonte: num
    recorte de largura cheia o painel vira so rosto e a legenda (cy=1250, ou seja 270px
    dentro do painel) cairia em cima da boca. Reduzindo, sobra peito e microfone atras dela.
    """
    x, y, w, h = SPLIT_AV_SRC
    # LARGURA CHEIA (17/08/2026): antes o painel reduzia o Thales e o centrava sobre um
    # fundo desfocado, o que deixava duas tarjas escuras nas laterais e ele parecendo uma
    # coluna no meio da tela (a Jheni viu no primeiro split do jh13). O motivo escrito no
    # comentario antigo era a legenda em cy=1250 cair na boca dele; so que o caminho de
    # split usa cy=1700 (assenta na camiseta), entao a razao nao valia mais.
    # Agora recorta pra largura cheia mantendo a proporcao: enquadramento de peito.
    escala = W / w
    alt_util = int(h * escala) // 2 * 2
    # ENQUADRAMENTO, MEDIDO e nao chutado (17/08/2026): perfil de luminancia da fonte
    # mostra cabeca e rosto entre y=700 e y=1440 do avatar 1080x1920. Com 8% a janela
    # pegava a PAREDE acima dele; centralizado cortava o topo do cabelo. 0.31 assenta a
    # cabeca inteira com peito embaixo. Ajustavel por look via VAM_SPLIT_BIAS.
    # MEDIDO POR PADRAO, digitado so como excecao (ordem do Julio 17/08/2026: "a
    # medicao precisa ser parte OBRIGATORIA do processo"). Sem VAM_SPLIT_BIAS, o motor
    # acha a pessoa no proprio avatar por perfil de luminancia. Cada look tem
    # enquadramento diferente, entao constante fixa erra sempre em algum.
    bias_env = os.environ.get("VAM_SPLIT_BIAS")
    if bias_env:
        bias = float(bias_env)
    else:
        try:
            _m = subprocess.run(
                [sys.executable, os.path.join(BASE, "medir_enquadramento.py"),
                 "avatar", AVATAR, "--json"], capture_output=True, text=True, timeout=180)
            bias = float(json.loads(_m.stdout)["VAM_SPLIT_BIAS"])
            print(f"  [medido] enquadramento do split: bias={bias}", flush=True)
        except Exception as _e:
            bias = 0.30
            print(f"  [AVISO] medicao do enquadramento falhou ({_e}), usando {bias}", flush=True)
    corte_y = max(0, min(int(alt_util * bias), alt_util - SPLIT_BOT_H)) // 2 * 2
    return (f"[1:v]crop={w}:{h}:{x}:{y},scale={W}:{alt_util},"
            f"crop={W}:{SPLIT_BOT_H}:0:{corte_y},setsar=1[bot];")


_CACHE_CONTEUDO = {}


ALVO_LUM = 105.0
# TETO (27/08/2026). O piso acima so LEVANTA, e essa foi a metade que faltou: os assets
# do jh13 se dividem em dois grupos, cinco entre 33 e 64 de luminancia e cinco entre 193
# e 244 (paginas brancas). O anuncio alterna entre eles, entao o corte dava soco de
# +140 a +151 niveis em 0,2s, com o estado branco segurando 3,0s e 4,6s. Nao e corte
# pelo preto, mas e a mesma classe de defeito, e no celular a noite doi mais.
# 185 nao lava a pagina branca (ela continua branca), so tira o estouro.
TETO_LUM = 185.0
EXPO_MIN = -0.22     # luminancia media alvo do painel; os inserts bons caem entre 83 e 100
EXPO_MAX = 0.45     # teto: acima disso a fonte escura vira cinza lavado
_CACHE_LUM = {}
_CACHE_LUM_MED = {}


def _luminancia_mediana_fonte(src, start=0.0):
    """Mediana de luminancia da fonte, medida no mesmo quadro que `_luminancia_fonte`.

    So pro `_bg_offset` (27/08/2026, achado do diretor de arte). A MEDIA mente em asset
    BIMODAL: um insert do jh13 deu media 64,0 mas mediana 33,0 (p10=16, p90=245), ou
    seja a maior parte do quadro e fundo escuro e uma area pequena e pagina bem clara. O
    offset calculado sobre a media ficava fraco demais pro fundo de verdade, e sobrou um
    trecho de 4,4s com 49% do quadro em preto absoluto, bem antes do CTA.
    Boxblur preserva a media (e convolucao linear), mas NAO preserva a mediana: apos o
    desfoque a imagem se parece com o que a MAIORIA da area já era, nao com a media
    puxada pela minoria clara. Por isso o alvo de fundo tem que mirar a mediana.
    Nao troco `_luminancia_fonte`: ela alimenta `_eq_exposicao` (piso/teto do CARD),
    que ja esta calibrado e testado com a media; mudar o significado dela ali sem
    remedir teria efeito colateral fora do escopo deste defeito.
    """
    if src in _CACHE_LUM_MED:
        return _CACHE_LUM_MED[src]
    val = None
    try:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            q = os.path.join(td, "l.png")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(start + 1.5),
                            "-i", src, "-frames:v", "1", q], capture_output=True, timeout=60)
            if os.path.exists(q):
                im = Image.open(q).convert("L")
                px = sorted(im.getdata())
                val = px[len(px) // 2]
    except Exception:
        val = None
    _CACHE_LUM_MED[src] = val
    return val


def _luminancia_fonte(src, start=0.0):
    """Luminancia media da fonte, medida num quadro. Cacheada. None se falhar."""
    if src in _CACHE_LUM:
        return _CACHE_LUM[src]
    val = None
    try:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            q = os.path.join(td, "l.png")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(start + 1.5),
                            "-i", src, "-frames:v", "1", q], capture_output=True, timeout=60)
            if os.path.exists(q):
                im = Image.open(q).convert("L")
                val = sum(im.getdata()) / (im.width * im.height)
    except Exception:
        val = None
    _CACHE_LUM[src] = val
    return val


def _eq_exposicao(cfg):
    """Filtro de exposicao por insert, vindo do campo `exposicao` do inserts.json.

    Por que existe (17/08/2026, reprovacao do diretor de arte): os assets da abertura do
    jh13 sao paginas escuras e cinematograficas, com luminancia media 50 e 36 numa escala
    de 255. Os primeiros 11,5s do anuncio ficavam quase pretos, que e exatamente a janela
    que decide retencao no Reels. Clarear e tratamento de exposicao, nao troca de asset:
    o asset marcado pela Brigida continua o mesmo.

    PISO AUTOMATICO (26/08/2026). Depender de alguem acertar `exposicao` na mao nao
    funcionou: o estrategista reprovou o jh13 com dois inserts ilegiveis, e medindo o
    painel de cima no arquivo entregue eles davam luminancia media 17,5 e 2,1 numa
    escala de 255 (p90 ZERO no segundo: 90% do painel era preto puro). As fontes tinham
    43 a 51 de luminancia e `exposicao` declarada de 0,06 a 0,10, insuficiente.

    Agora o motor MEDE a fonte e calcula o piso pra o painel cair na faixa em que os
    inserts bons ja caem (83 a 100 de media, medido nos cinco que passaram). O valor
    declarado no JSON continua valendo como MINIMO: quem quiser clarear mais, clareia.
    """
    ex = float(cfg.get("exposicao", 0) or 0)
    src = cfg.get("file")
    if src:
        lum = _luminancia_fonte(src, float(cfg.get("start", 0) or 0))
        if lum is not None and lum < ALVO_LUM:
            piso = min((ALVO_LUM - lum) / 255.0, EXPO_MAX)
            if piso > ex:
                print(f"  [exposicao] {os.path.basename(src)}: fonte em {lum:.0f}/255, "
                      f"subindo de {ex:.2f} para {piso:.2f} (alvo {ALVO_LUM})", flush=True)
                ex = piso
        elif lum is not None and lum > TETO_LUM:
            # TETO REMOVIDO (28/08/2026, print do Julio). O teto escurecia pagina branca
            # PERMANENTEMENTE (244 -> 188 = cinza), e mesmo depois de consertar o
            # contraste o resultado seguia "um filtro cinza em cima dos inserts, tudo
            # meio palido". Eu declarei o cinza removido e ele nao estava: consertei o
            # sintoma acoplado (contraste) e mantive a causa (brightness negativo).
            # Pagina branca fica BRANCA. O teto so ZERA exposicao declarada pra cima
            # (clarear o que ja e branco continua errado); nunca escurece.
            # O flash de brilho no corte (o motivo do teto existir) fica como custo
            # aceito: era apontamento de auditor com alvo de 90 niveis, nao reclamacao
            # do Julio, e o conserto errado custou o defeito que ele VIU. Se um dia
            # incomodar de verdade, o caminho e rampa por `sendcmd` no eq (o eq NAO
            # avalia expressao por quadro: medido, `if(lt(t,...))` congela no t=0),
            # nunca filtro permanente.
            if ex > 0:
                print(f"  [exposicao] {os.path.basename(src)}: fonte em {lum:.0f}/255 "
                      f"ja e clara, zerando exposicao declarada de {ex:.2f}", flush=True)
                ex = 0.0
    if abs(ex) < 0.005:
        return ""
    # CONTRASTE NUNCA CAI (27/08/2026). A formula era `1 + ex*0.6`, escrita quando `ex`
    # SO PODIA SER POSITIVO (o piso, que clareia asset escuro): clarear lava a imagem,
    # entao subir o contraste junto compensa. Quando adicionei o TETO hoje de manha, `ex`
    # passou a poder ser negativo e a mesma formula virou REDUCAO de contraste: os assets
    # claros (193 a 244 de luminancia) saiam com contrast 0,87 a 0,98, ou seja escurecidos
    # E lavados ao mesmo tempo. O Julio viu na hora: "uma merda de filtro cinza em cima
    # dos inserts, fica tudo meio palido".
    # Mexer num lado do calculo e nao revisar a formula acoplada a ele: o mesmo padrao
    # do dia. `abs(ex)` faz clarear e escurecer preservarem contraste por igual.
    return f"eq=brightness={ex:.3f}:contrast={1 + abs(ex) * 0.6:.3f},"


def _crop_fonte(cfg):
    """Recorte da FONTE declarado no inserts.json: "W:H:X:Y". Devolve (filtro, dims).

    Existe porque `zoom` amplia e corta pelas BORDAS: numa gravacao de tela o assunto
    quase nunca esta centralizado, entao ampliar pra deixar legivel comia a primeira
    letra de cada linha (medido pelo diretor de arte em 18/08/2026: "mentas, leu 3
    arquivos", "riada. Agora construindo"). Com `crop` eu escolho a JANELA da tela que
    vale a pena mostrar e o zoom deixa de ser necessario pra ganhar tamanho.

    `split_crop` continua aceito como nome antigo do mesmo campo.
    """
    sc = cfg.get("crop") or cfg.get("split_crop")
    if not sc:
        return "", None
    cw, ch, cx, cy = [int(v) for v in str(sc).split(":")]
    return f"crop={cw}:{ch}:{cx}:{cy},", (cw, ch)


def _crop_conteudo(src, alvo_w, alvo_h, crop_dims=None):
    """Expressao x:y do crop do painel de cima, ancorada no CONTEUDO medido do asset.

    Devolve string pro filtro `crop=W:H:x:y`. O ffmpeg calcula in_w/in_h em tempo de
    filtro, entao a expressao usa esses simbolos e so injeta a FRAÇÃO medida. Assim
    funciona pra qualquer resolucao de fonte sem eu precisar saber o tamanho aqui.
    """
    if crop_dims:
        # com recorte declarado, o conteudo E o recorte: ancorar no meio dele e correto
        # e dispensa medir (medir aqui mediria o arquivo INTEIRO, nao a janela escolhida,
        # e devolveria um centro que nao existe mais depois do crop).
        return "'(in_w-out_w)/2':'(in_h-out_h)/2'"
    if src not in _CACHE_CONTEUDO:
        fx, fy, modo = 0.5, 0.5, "preencher"
        try:
            r = subprocess.run(
                [sys.executable, os.path.join(BASE, "medir_enquadramento.py"),
                 "asset", src, "--painel", f"{alvo_w}x{alvo_h}", "--json"],
                capture_output=True, text=True, timeout=180)
            d = json.loads(r.stdout)
            fx, fy = float(d["centro_conteudo_x"]), float(d["centro_conteudo_y"])
            modo = d.get("modo", "preencher")
            print(f"  [medido] {os.path.basename(src)}: centro x={fx:.2f} y={fy:.2f} | "
                  f"perda ao preencher {d.get('perda_ao_preencher', 0):.0%} -> {modo}",
                  flush=True)
        except Exception as ex:
            print(f"  [AVISO] conteudo nao medido ({ex}), usando o meio", flush=True)
        _CACHE_CONTEUDO[src] = (fx, fy, modo)
    fx, fy, _modo = _CACHE_CONTEUDO[src]
    # clamp pelo proprio ffmpeg: o centro medido pode pedir recorte fora da borda
    return (f"'clip((in_w*{fx:.4f})-(out_w/2),0,in_w-out_w)'"
            f":'clip((in_h*{fy:.4f})-(out_h/2),0,in_h-out_h)'")


_CACHE_ASPECTO = {}


def _aspecto(src):
    """Aspecto do asset, medido por ffprobe. Cacheado."""
    if src not in _CACHE_ASPECTO:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height",
                            "-of", "csv=p=0:s=x", src],
                           capture_output=True, text=True)
        try:
            w, h = [int(v) for v in r.stdout.strip().split("x")[:2]]
            _CACHE_ASPECTO[src] = w / h
        except Exception:
            _CACHE_ASPECTO[src] = 16 / 9
    return _CACHE_ASPECTO[src]



_CACHE_LARG = {}


def _largura_fonte(src):
    """Largura em pixels do arquivo-fonte, por ffprobe. Cacheada.

    O push-in precisa saber o quanto o asset ENCOLHEU para caber na janela, e isso e a
    razao entre a largura da janela e a largura nativa. Medida, nunca declarada: o campo
    do config pode estar velho, o arquivo nao.
    """
    if src in _CACHE_LARG:
        return _CACHE_LARG[src]
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width", "-of", "csv=p=0", str(src)],
                       capture_output=True, text=True)
    try:
        _CACHE_LARG[src] = int(r.stdout.strip().split(",")[0])
    except Exception:
        _CACHE_LARG[src] = None
    return _CACHE_LARG[src]


def _fg_painel_mockup(src, expo="", dur=None, start=0.0):
    """Painel de cima com o asset INTEIRO dentro de uma moldura de navegador.

    Ordem do Julio (26/08/2026), depois de reprovar o jh13 e de me ver teorizando
    sobre onde recortar:

        "e so colocar ele dentro de algum mockup que caiba na tela, e muito simples.
         E melhor do que voce ficar raciocinando 'aonde que eu posiciono o video pra
         aparecer o que precisa', sendo que O VIDEO TODO QUE APARECE NO VIDEO E O QUE
         PRECISA."

    Isso encerra a decisao de enquadramento: nao existe janela a escolher. O quadro
    inteiro entra, e a moldura faz o formato horizontal parecer intencional em vez de
    sobra. A moldura nasce no ASPECTO DO ASSET (`moldura.py`), entao o video preenche
    a janela exatamente e nao existe vao morto la dentro.

    O `crop` declarado no inserts.json e IGNORADO aqui, de proposito: era ele que
    derrubava a medicao do arquivo e jogava o motor em `preencher`, ampliando 1,5x a
    2,4x e decapitando as linhas (medido no jh13: crops de aspecto 1.10 e ate 0.72
    sobre fontes 16:9, descartando de 31% a 60% da area).
    """
    import moldura
    asp = _aspecto(src)
    # MOCKUP SO EM ASSET HORIZONTAL (27/08/2026). A moldura existe pra dar forma a um
    # quadro DEITADO dentro de um painel quase quadrado. Num asset em pe ela faz o
    # oposto: com LARGURA_JANELA fixa em 1008, um 9:16 gera card de 1854px de altura
    # dentro de um painel de 1150 (medido em tres assets do jh13: drv_1ebXWtW8Is,
    # drv_1cipV29jls e hf_ampulheta). O card sairia decapitado em cima e embaixo, que e
    # exatamente o defeito que a moldura foi criada pra acabar.
    # Asset em pe ja preenche o painel sozinho, sem moldura nenhuma.
    if asp < 1.05:
        print(f"  [mockup] {os.path.basename(src)}: aspecto {asp:.2f} e vertical, "
              f"entra sem moldura (o card nao caberia no painel)", flush=True)
        return _fg_painel(src, W, SPLIT_TOP_H, expo)   # ja devolve [t2]...[tfg];
    nome = f"moldura_{asp:.4f}.png".replace(".", "_", 1)
    destino = os.path.join(V2L_MOLDURAS, nome)
    if not os.path.exists(destino):
        moldura.png_navegador(asp, destino)
    m = moldura.medidas(asp)
    jw, jh = m["janela_w"], m["janela_h"]
    cw, ch = m["canvas_w"], m["canvas_h"]
    vx, vy = m["video_x"], m["video_y"]
    print(f"  [mockup] {os.path.basename(src)}: aspecto {asp:.2f} -> janela {jw}x{jh}, "
          f"card {m['card_w']}x{m['card_h']} (asset INTEIRO, sem recorte)", flush=True)
    png = destino.replace("\\", "/").replace(":", "\\:")
    # PUSH-IN (28/08/2026, excecao autorizada pelo Julio). O asset entra INTEIRO em
    # t=0 e a camera avanca depois, so o quanto ele encolheu para caber. Toda a regra,
    # com os numeros e o porque, mora em `push_in.py`, que e modulo e tem teste; aqui
    # so entra o trecho de filtro. Sem avanco a string vem vazia e o filtro fica
    # identico ao de antes, entao asset que ja entra grande nao muda em nada.
    import push_in as _pi
    _esc = jw / float(m.get("janela_w_fonte") or jw) if m.get("janela_w_fonte") else None
    _mov = ""
    if dur:
        _lf = _largura_fonte(src)
        if _lf:
            _mov = _pi.filtro(jw / _lf, dur, FPS, jw, jh, _pi.foco_do_conteudo(src, start))
            if _mov:
                _z = _pi.fator_push_in(jw / _lf)
                print(f"  [push-in] {os.path.basename(src)}: fonte {_lf}px entra a "
                      f"{jw / _lf:.3f} da largura, avanca ate {_z:.2f}x", flush=True)
    return (f"[t2]{expo}scale={jw}:{jh},setsar=1{_mov}[tvid];"
            f"color=black@0:s={cw}x{ch}:r={FPS},format=rgba,setsar=1[tcv];"
            f"[tcv][tvid]overlay={vx}:{vy}:shortest=1[tcard];"
            f"movie={png},format=rgba,setsar=1[tmold];"
            f"[tcard][tmold]overlay=0:0[tfg];")


def _fg_painel(src, alvo_w, alvo_h, expo="", crop_dims=None):
    """Filtro do painel de cima: PREENCHE ou ENCAIXA, conforme a perda MEDIDA.

    Preencher tapa a tarja mas descarta parte do asset. Numa gravacao de tela isso corta
    o que a fala esta descrevendo (o Julio: "nem da pra ver qual e a skill"). Encaixar
    preserva o asset inteiro e o fundo desfocado do proprio asset preenche a sobra, que
    e o tratamento que a referencia da Jheni usa. A decisao sai da medida, nao de mim:
    perda acima de PERDA_MAX no medir_enquadramento devolve modo "encaixar".

    NOTA (26/08/2026): no SPLIT este caminho nao e mais usado. Ver `_fg_painel_mockup`.
    """
    if crop_dims:
        # perda ao PREENCHER o painel com a janela recortada, calculada direto do aspecto
        cw, ch = crop_dims
        asp_a, asp_p = cw / ch, alvo_w / alvo_h
        perda = 1 - (min(asp_a, asp_p) / max(asp_a, asp_p))
        modo = "encaixar" if perda > 0.22 else "preencher"
        print(f"  [recorte declarado] {cw}x{ch}: perda ao preencher {perda:.0%} -> {modo}",
              flush=True)
    else:
        _crop_conteudo(src, alvo_w, alvo_h)      # popula o cache e loga a medida
        _, _, modo = _CACHE_CONTEUDO[src]
    if modo == "encaixar":
        # SEM TARJA CHAPADA (17/08/2026, reprovacao do diretor de arte: "654px de preto
        # puro em cima, o conteudo ocupa 32% da altura"). Encaixar preserva o asset
        # inteiro, mas deixava as sobras PRETAS. Agora a sobra recebe o proprio asset
        # desfocado e escurecido, igual ao tratamento que o painel ja usa embaixo: le
        # como profundidade, nao como bug. E o card sobe pra 96% da largura.
        card_w = int(alvo_w * 0.96) // 2 * 2
        return (f"[t2]{expo}scale={card_w}:{alvo_h}:force_original_aspect_ratio=decrease,"
                f"setsar=1[tfg];")
    return (f"[t2]{expo}scale={alvo_w}:{alvo_h}:force_original_aspect_ratio=increase,"
            f"crop={alvo_w}:{alvo_h}:{_crop_conteudo(src, alvo_w, alvo_h, crop_dims)},"
            f"setsar=1[tfg];")


def r_split_tela(cfg, text, s, e, out, wt=None):
    """Bloco de tela dividida: insert em cima, Thales embaixo, legenda por cima do conjunto.

    NAO chamar de `r_split`: ja existe um `r_split()` mais abaixo neste arquivo (bloco
    "time de IA", Thales em CIMA e aula embaixo, hoje sem dispatch). Como Python resolve
    nome por ultima definicao, o de baixo sobrescrevia este e o build morria com
    "r_split() takes from 4 to 5 positional arguments but 6 were given".
    """
    d = e - s
    src = cfg["file"]; sp = cfg.get("speed", 1.0); st = cfg.get("start", 0)
    st = _pular_preto(src, float(st), d * sp)   # idem r_insert: entrada nunca preta
    take = d * sp
    N = nframes(d)
    # LEGENDA MAIS BAIXA no split. O padrao (cy=1250) cai 270px dentro do painel de baixo,
    # que e exatamente a altura dos olhos dele nesse enquadramento: a legenda ficaria em
    # cima do rosto. Em 1700 ela assenta na camiseta, acima do microfone. Medido no frame
    # de teste, nao chutado.
    ass = caption_ass(text, s, d, wt, cy=1700)
    # recorte da tela pro painel de cima. Sem isso, um 1080x1920 entraria pela largura e
    # so 50% dele apareceria; com ele eu escolho QUAL pedaco da tela vale a pena mostrar.
    # CROP FORA DE VERDADE NO SPLIT (26/08/2026, segunda passada). Na primeira eu tirei
    # o `crop` so do CALCULO DO MODO e ele continuou sendo APLICADO na fonte: a moldura
    # passou a garantir a janela inteira, mas o conteudo seguia decapitado antes de
    # entrar nela. O diretor de arte mediu e cinco inserts ainda descartavam de 31% a
    # 60% da largura, com linha do Cloudflare cortada e headline pela metade.
    # Meia correcao nao corrige: aqui o `crop` nao entra no filtro.
    _cropf, _cropd = _crop_fonte(cfg)
    if _cropf:
        print(f"  [split] ignorando crop declarado {_cropd}: no mockup o quadro entra "
              f"INTEIRO", flush=True)
    topsrc = "[0:v]"
    fc = (f"{topsrc}setpts=PTS/{sp},tpad=stop_mode=clone:stop_duration=4,split=2[t1][t2];"
          f"[t1]scale={W}:{SPLIT_TOP_H}:force_original_aspect_ratio=increase,"
          # o ganho de exposicao vale pro FUNDO tambem: clarear so o card deixava o
          # painel de cima em 23,6 de luminancia (medido no build G1 aos 2,0s), porque
          # a maior parte do painel e este fundo desfocado, nao o card.
          f"crop={W}:{SPLIT_TOP_H},{_eq_exposicao(cfg)}boxblur=26:1,"
          f"eq=brightness=-0.12,setsar=1[tbg];"
          # PREENCHER o painel de cima (increase+crop) em vez de encaixar inteiro
          # (decrease): a pagina 2.4:1 dentro de um painel quase quadrado deixava uma
          # faixa escura de ~265px em cima e embaixo, e o split parecia mal montado.
          # O recorte segue o CENTRO DE CONTEUDO medido, nao o centro geometrico:
          # gravacao de tela tem o assunto fora do meio (lista de skills a esquerda,
          # conversa do Claude a esquerda) e recortar pelo meio cortava justamente o
          # que a fala descrevia. Ver _crop_conteudo() e medir_enquadramento.py.
          # MOCKUP (26/08/2026): o asset entra INTEIRO dentro de uma moldura de
          # navegador, em vez de o motor escolher que pedaco mostrar. Ordem do Julio:
          # "o video todo que aparece no video e o que precisa". O `crop` declarado
          # deixa de valer no split, e era ele que causava a ampliacao de 1,5x a 2,4x.
          + _fg_painel_mockup(src, _eq_exposicao(cfg), dur=(e - s),
                             start=float(cfg.get("start", 0) or 0)) +
          f"[tbg][tfg]overlay=(W-w)/2:(H-h)/2,setsar=1[top];"
          + _split_avatar(s, d) +
          f"color={DARK}:s={W}x{H}:r={FPS}[cv];"
          f"[cv][top]overlay=0:0:shortest=1[c1];"
          f"[c1][bot]overlay=0:{SPLIT_TOP_H}[c2];"
          # degrade escuro na emenda (item 5 do brief): banda rgba transparente no topo
          # e escura na borda, por cima do fim do painel de tela. Substitui a linha dura
          # de 3px; as duas referencias com split usam degrade, nunca linha.
          f"color=black:s={W}x{SPLIT_GRAD}:r={FPS},format=rgba,"
          # PISO DO DEGRADE (27/08/2026). Com 0.85 a ultima parada chegava em preto quase
          # puro; quando o pe do insert JA e escuro, degrade e asset somam e a emenda
          # vira regua preta. Medido pelo diretor: faixa de 25px com luminancia 0,3 em
          # t=61,5s, contra 39 no painel do avatar logo abaixo. Em painel claro nao
          # acontecia, entao o defeito so aparecia em metade dos splits.
          # 0.62 deixa a linha mais escura em ~14, que e o proprio preto do avatar.
          f"geq=r=0:g=0:b=0:a='255*0.62*pow(Y/{SPLIT_GRAD-1},1.6)'[grad];"
          f"[c2][grad]overlay=0:{SPLIT_TOP_H-SPLIT_GRAD}:shortest=1,"
          f"fps={FPS},{cap(N)}{_sub(ass)}[v]")
    run(["ffmpeg", "-y", "-ss", str(st), "-t", str(take + 0.4), "-i", src,
         "-ss", str(s), "-t", str(d + 0.4), "-i", AVATAR,
         "-filter_complex", fc, "-r", str(FPS), "-map", "[v]", "-an",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", out])



_PIP_CROP_CACHE = {}
def _pip_crop():
    """Recorte quadrado da cabeca pro PiP, MEDIDO no avatar (nao chutado).

    O chute anterior (640@y750) decapitava o Thales no espuma_roxa: topo da pessoa
    em y~693 (medido). Quadrado de 720px comecando 60px ACIMA do topo, centrado."""
    if AVATAR in _PIP_CROP_CACHE:
        return _PIP_CROP_CACHE[AVATAR]
    y = 640
    try:
        r = subprocess.run([sys.executable, os.path.join(BASE, "medir_enquadramento.py"),
                            "avatar", AVATAR, "--json"],
                           capture_output=True, text=True, timeout=180)
        topo = int(json.loads(r.stdout)["topo_px"])
        y = max(0, topo - 60)
    except Exception as _e:
        print(f"  [AVISO] medicao do pip falhou ({_e}), usando y={y}", flush=True)
    lado = 720
    y = min(y, 1920 - lado)
    crop = f"{lado}:{lado}:{(1080 - lado) // 2}:{y}"
    _PIP_CROP_CACHE[AVATAR] = crop
    print(f"  [medido] recorte da bolinha: {crop}", flush=True)
    return crop


_PRETO_CACHE = {}
def _pular_preto(src, st, dur_take):
    """Se a fonte esta PRETA em `st` (fade-in do proprio asset), devolve st deslocado
    pro primeiro quadro claro. O whip de 0,20s mascarava isso; o corte seco (18/08)
    expos 0,3-0,6s de preto na entrada de CADA fatia de insert (8 ocorrencias em
    jh14+jh16, medidas com blackdetect). Deslocar no maximo 1,2s e so quando o
    comeco e preto de verdade: fonte escura legitima (lum>12) nao é tocada."""
    chave = (src, round(st, 2))
    if chave in _PRETO_CACHE:
        return _PRETO_CACHE[chave]
    novo_st = st
    try:
        r = subprocess.run(
            ["ffmpeg", "-v", "info", "-ss", str(st), "-t", "1.5", "-i", src,
             "-vf", "blackdetect=d=0.1:pix_th=0.06", "-an", "-f", "null", "-"],
            capture_output=True, text=True, timeout=60)
        m = re.search(r"black_start:(0(?:\.0+)?|0\.[0-9]+) black_end:([0-9.]+)", r.stderr)
        if m and float(m.group(1)) <= 0.05:
            salto = min(float(m.group(2)) + 0.05, 1.2)
            novo_st = st + salto
            print(f"  [preto] fonte {os.path.basename(src)} preta em {st:.2f}s: "
                  f"entrada desloca +{salto:.2f}s", flush=True)
    except Exception:
        pass
    _PRETO_CACHE[chave] = novo_st
    return novo_st

ALVO_BG_CHEIO = 30.0     # luminancia alvo do fundo desfocado, de 0 a 255


def _bg_offset(src, cfg):
    """Quanto clarear ou escurecer o fundo desfocado do insert em tela cheia.

    OFFSET FIXO ZERAVA O QUADRO (27/08/2026). Estava em `brightness=-0.40`, que e -102
    niveis: num asset de luminancia 33 (cinco dos dez do jh13 estao entre 33 e 64) isso
    nao escurece, ZERA. O diretor de arte mediu 11,07s do anuncio, 12,3%, com 60% a 67%
    do quadro em preto absoluto, e um dos trechos e t=3,17 a 6,60s, dentro da janela que
    decide o scroll. O conserto declarado ("congelado, desfoque 60, brilho -0,40") nao
    mudava um pixel do que se via: era o preto chapado de novo, por outro caminho.

    Fixo nao serve porque o material varia de 33 a 244 de luminancia. Aqui o alvo e
    medido: o fundo pousa em ~30/255, escuro o bastante pra nao competir com o card e
    claro o bastante pra ler como cenario em vez de buraco.

    MEDIANA, NAO MEDIA (27/08/2026, segunda passada). A media mente em asset bimodal
    (fundo escuro + area pequena bem clara): dava offset fraco demais e sobrava
    trecho em preto quase absoluto. Ver `_luminancia_mediana_fonte`.
    """
    lum = _luminancia_mediana_fonte(src, float(cfg.get("start", 0) or 0))
    if lum is None:
        return -0.20
    off = max(-0.40, min(0.16, (ALVO_BG_CHEIO - lum) / 255.0))
    print(f"  [fundo cheio] {os.path.basename(src)}: fonte em {lum:.0f}/255, "
          f"offset {off:+.3f} (alvo {ALVO_BG_CHEIO:.0f})", flush=True)
    return off


def r_insert_moldura(cfg, text, s, e, out, wt=None):
    """Insert em TELA CHEIA com a mesma moldura de navegador do split.

    Mesma regra do split: o quadro entra INTEIRO, `crop` declarado nao vale. A unica
    diferenca e que o card ocupa o quadro todo em vez de 1150px, e nao ha apresentador
    embaixo. Isso troca ~60% dos pixels contra o plano vizinho, que e o que faz a
    deteccao de cena registrar o corte (o split sozinho muda 0,144 contra limiar 0,30).
    """
    import moldura
    d = e - s
    src = cfg["file"]; sp = cfg.get("speed", 1.0); st = cfg.get("start", 0)
    st = _pular_preto(src, float(st), d * sp)
    N = nframes(d)
    ass = caption_ass(text, s, d, wt, cy=1700)
    asp = _aspecto(src)
    nome = f"moldura_cheio_{asp:.4f}.png".replace(".", "_", 1)
    destino = os.path.join(V2L_MOLDURAS, nome)
    # no quadro cheio o card pode ser mais largo: 92% de 1080
    # 92% da largura dava card de 27,7% do quadro, MENOS que os 37,5% que o proprio
    # split entrega (medido pelo diretor de arte nas tres fatias `cheio`). A fatia que
    # existe pra dar a tela ao insert estava dando menos tela que a que divide o quadro
    # com o apresentador. 96% e a mesma margem do painel encaixado do split.
    larg = int(W * 0.96) // 2 * 2
    _antes = moldura.LARGURA_JANELA
    moldura.LARGURA_JANELA = larg
    try:
        if not os.path.exists(destino):
            moldura.png_navegador(asp, destino)
        m = moldura.medidas(asp)
    finally:
        moldura.LARGURA_JANELA = _antes
    jw, jh, cw, ch = m["janela_w"], m["janela_h"], m["canvas_w"], m["canvas_h"]
    vx, vy = m["video_x"], m["video_y"]
    print(f"  [mockup cheio] {os.path.basename(src)}: janela {jw}x{jh} no quadro inteiro",
          flush=True)
    png = destino.replace("\\", "/").replace(":", "\\:")
    import push_in as _pi
    _mov_cheio = ""
    _lf = _largura_fonte(src)
    if _lf:
        _mov_cheio = _pi.filtro(jw / _lf, d, FPS, jw, jh, _pi.foco_do_conteudo(src, st))
        if _mov_cheio:
            print(f"  [push-in cheio] {os.path.basename(src)}: fonte {_lf}px entra a "
                  f"{jw / _lf:.3f}, avanca ate {_pi.fator_push_in(jw / _lf):.2f}x",
                  flush=True)
    # FUNDO CONGELADO (27/08/2026). O fundo desfocado rodava AO VIVO junto com o card,
    # entao a gravacao de tela por baixo piscava: medido nas laterais do quadro, 35,2 de
    # luminancia em t=82,8s, 149,7 em t=83,0s e 48,3 em t=84,3s. O medidor de ritmo
    # contou isso como 10 cortes em 4,4s e o numero de 20,6 cortes/min veio dai; o olho
    # via estroboscopia, nao corte. E o mesmo fundo duplicava a manchete do asset,
    # gigante e fora de foco, atras da copia nitida dentro do card.
    # Um quadro so, esticado pela duracao: fica textura, nao segundo video.
    # FUNDO CHAPADO, NAO O ASSET DESFOCADO (27/08/2026, segunda passada). Congelar o
    # quadro matou o estrobo, mas o diretor de arte apontou o defeito que restava: em
    # t=5,0s a manchete do asset aparecia GIGANTE e fora de foco no topo, com a copia
    # nitida dela pequena dentro do card. A mesma manchete duas vezes, uma borrada.
    # E media 0,18 de mudanca de pixel contra o plano vizinho (limiar 0,30), porque
    # fundo desfocado do asset escuro contra sala escura da quase nada: a troca de
    # layout nao registrava como corte nem pro medidor nem pro olho.
    # Chapado resolve os dois: nao repete conteudo e muda o quadro inteiro.
    # NEM AO VIVO NEM CHAPADO (27/08/2026, terceira passada). Ao vivo o fundo piscava;
    # chapado, o diretor mediu o card ocupando 95,9% da largura mas so 44% da altura, com
    # 65% a 69% do quadro em preto liso: virou "tela vazia com um cardzinho no meio", ao
    # lado do split, onde o fundo e o asset desfocado.
    # O terceiro caminho tem as duas coisas: o asset CONGELADO num quadro (mata o
    # estrobo) e desfocado a 60 com brilho -0,40 (mata a leitura da manchete duplicada,
    # que era o outro motivo de eu ter chapado). Fica textura de profundidade, nao
    # segundo video nem buraco preto.
    fc = (f"[0:v]setpts=PTS/{sp},tpad=stop_mode=clone:stop_duration=4,split=2[t1][t2];"
          f"[t1]trim=end_frame=1,loop=loop=-1:size=1:start=0,setpts=N/{FPS}/TB,"
          f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"boxblur=60:2,eq=brightness={_bg_offset(src, cfg):.3f}:saturation=0.7,"
          f"setsar=1[bg];"
          # PUSH-IN TAMBEM AQUI (29/08/2026). Estava so no split, e tela cheia sao
          # 18,01s do anuncio com o mesmo problema: o asset encolhe para caber e o
          # texto dele nao le. Mesma regra, mesmo modulo, mesmo teto.
          f"[t2]{_eq_exposicao(cfg)}scale={jw}:{jh},setsar=1{_mov_cheio}[vid];"
          f"color=black@0:s={cw}x{ch}:r={FPS},format=rgba,setsar=1[cv];"
          f"[cv][vid]overlay={vx}:{vy}:shortest=1[card];"
          f"movie={png},format=rgba,setsar=1[mold];"
          f"[card][mold]overlay=0:0[fg];"
          # shortest=1 e OBRIGATORIO aqui: o [bg] congelado e um `loop` infinito, e sem
          # isso quem termina o fluxo e so o trim la na frente, com o ffmpeg moendo
          # quadro a toa ate la (travou no teste antes de eu por).
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,setsar=1,fps={FPS},{cap(N)}{_sub(ass)}[v]")
    run(["ffmpeg", "-y", "-ss", str(st), "-t", str(d * sp + 0.4), "-i", src,
         "-filter_complex", fc, "-r", str(FPS), "-map", "[v]", "-an",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", out])


def r_insert(cfg,text,s,e,out,wt=None):
    if cfg.get("split"):
        # o layout marcado pelo ritmo VENCE o `split` do config: e ele que faz a
        # visita seguinte ao mesmo asset parecer outra coisa (ver _layout no ritmo.py)
        if cfg.get("_layout") == "cheio":
            # TELA CHEIA COM MOLDURA (26/08/2026). A alternancia de layout mandava o
            # asset horizontal pro caminho antigo de tela cheia, que RECORTA: o Julio
            # viu como "falhas de renderizacao nos cortes", e de fato o quadro saia sem
            # moldura e com toda linha decapitada nos dois lados (medido em t=83,5s e
            # t=85,0s: "...nos", "Integra...", "Agendar aval...").
            # Consertar a metade e deixar a outra quebrada foi o erro que se repetiu o
            # dia inteiro. Aqui o card entra inteiro tambem, so que MAIOR e sem o
            # apresentador embaixo: e essa a diferenca visual que faz o corte registrar.
            # Asset EM PE nao ganha moldura: ele ja preenche um quadro 9:16 sozinho,
            # e a moldura so faria o card estourar (mesma guarda de _fg_painel_mockup).
            if _aspecto(cfg["file"]) >= 1.05:
                return r_insert_moldura(cfg, text, s, e, out, wt)
        else:
            return r_split_tela(cfg,text,s,e,out,wt)
    # INSERT HORIZONTAL EM TELA CHEIA TAMBEM ENTRA INTEIRO (27/08/2026).
    # O veto ao `crop` de 26/08 pegou so as entradas com `split: true`. As que nao tem a
    # flag continuaram pelo caminho antigo, e o diretor de arte achou tres delas ainda
    # recortando: `gal_8f78677c` guarda 775x1080 de uma fonte 1916x1080, ou seja joga
    # fora 59,5% da area, e o quadro entregue em t=69,5s mostra so a coluna do preview,
    # sem a sidebar nem o chat que a fala esta descrevendo.
    # A ordem do Julio nao tinha ressalva de layout: "o video todo que aparece no video
    # e o que precisa". Entao vale aqui igual: asset deitado entra na moldura, inteiro.
    # Imagem estatica e asset em pe seguem pelo caminho de sempre.
    if (not cfg.get("split")
            and os.path.splitext(cfg["file"])[1].lower() not in (".jpg",".jpeg",".png",".webp")
            and _aspecto(cfg["file"]) >= 1.05):
        return r_insert_moldura(cfg, text, s, e, out, wt)
    d=e-s; src=cfg["file"]; sp=cfg.get("speed",1.0); st=cfg.get("start",0); take=d*sp
    st=_pular_preto(src, float(st), take)   # fade-from-black da fonte nao entra no corte seco
    N=nframes(e-s); ass=caption_ass(text,s,d,wt)   # legenda karaoke embaixo
    is_image = os.path.splitext(src)[1].lower() in (".jpg",".jpeg",".png",".webp")
    if is_image:
        # insert de IMAGEM ESTATICA (ex: dashboard/screenshot sem gravacao de tela
        # disponivel): zoom Ken Burns bem sutil (1.0->1.06) pra nao ficar morto na tela.
        # -loop 1 trata a imagem como fonte "infinita" pro ffmpeg, igual r_logo() ja faz
        # com os assets de PNG do card. Sem tpad/setpts de video (nao se aplicam a imagem).
        dur = take+0.4
        fc=(f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=24:1,setsar=1[bg];"
            f"[0:v]scale={int(W*1.08)}:-1,"
            f"zoompan=z='min(zoom+0.0007,1.06)':d={nframes(dur)}:s={W}x{H}:fps={FPS},setsar=1[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={FPS},{cap(N)}{_sub(ass)}[v]")
        run(["ffmpeg","-y","-loop","1","-t",str(dur),"-i",src,
             "-filter_complex",fc,"-r",str(FPS),"-map","[v]","-an",
             "-c:v","libx264","-pix_fmt","yuv420p",out])
        return
    # b-roll em TELA CHEIA (fit sobre fundo desfocado). SEM bolinha do Thales:
    # o magicZooms do Submagic dava zoom no frame e arrastava a bolinha do topo pro centro.
    # tpad clone: se a fonte for mais curta que take+0.4, congela o ultimo frame em vez de
    # encurtar o segmento (segmento curto desloca TODOS os blocos seguintes na cadeia xfade
    # e dessincroniza pip/legenda/audio; ver nota de contiguidade no main).
    # ZOOM por insert (o campo "zoom" do inserts.json existia mas NUNCA era lido:
    # todo b-roll entrava com o frame inteiro encolhido pra caber na largura, entao
    # gravacao de tela 1920x1080 virava 1080x607 e a fonte do terminal ficava com
    # ~10px de altura, ilegivel no celular. Achado na auditoria de 04/08/2026).
    # zoom>1 amplia e recorta o CENTRO: bom pra terminal/tela de codigo, ruim pra
    # organograma (cortaria os cargos das pontas), por isso e opt-in por insert.
    _cropf, _cropd = _crop_fonte(cfg)
    zm = float(cfg.get("zoom", 1.0) or 1.0)
    if zm > 1.001:
        # RECORTE NO CONTEUDO, nao no centro. O zoom cortava o meio do quadro, e em
        # gravacao de tela o que interessa nao esta no meio: o diretor de arte mediu a
        # PRIMEIRA LETRA de cada linha sendo comida na borda esquerda ("xecutado um
        # comando", "erfeita como referencia"). O centroide de conteudo ja era medido
        # pro split; agora vale aqui tambem.
        fg = (f"[i2]scale={int(W*zm)}:{int(H*zm)}:force_original_aspect_ratio=decrease,"
              f"crop='min(iw,{W})':'min(ih,{H})':{_crop_conteudo(src, W, H, _cropd)},"
              f"setsar=1[fg];")
    else:
        fg = f"[i2]scale={W}:{H}:force_original_aspect_ratio=decrease,setsar=1[fg];"
    # BOLINHA DO THALES (19/08/2026, feedback da Jheni: "alguns poderiam ter o rosto
    # do Thales numa bolinha, outros o insert total; as referencias fazem muito isso").
    # Opt-in por insert ("pip": true no inserts.json): o apresentador segue presente
    # durante a demo, num circulo com a sombra que ja existia em assets. A era
    # Submagic tirou a bolinha porque o magicZooms a arrastava; sem Submagic o motivo
    # morreu. Enquadramento do circulo: cabeca medida no avatar (y~700-1440 na fonte
    # 1080x1920), recorte quadrado centrado nela.
    _pip = bool(cfg.get("pip"))
    _base = (f"[i1]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=24:1,setsar=1[bg];"
             + fg +
             f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={FPS},{cap(N)}[base];")
    if _pip:
        fc=(f"[0:v]{_cropf}{_eq_exposicao(cfg)}setpts=PTS/{sp},"
            f"tpad=stop_mode=clone:stop_duration=4,split=2[i1][i2];"
            + _base +
            f"[1:v]crop={_pip_crop()},scale={PIP}:{PIP},format=yuva420p,"
            f"geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':"
            f"a='if(lte(pow(X-{PIP//2},2)+pow(Y-{PIP//2},2),{(PIP//2)*(PIP//2)}),255,0)'[pipv];"
            f"[2:v]scale=420:420[sh];"
            # shortest=1 nos dois: a sombra em -loop e o avatar (d+0.4) sao mais
            # longos que o [base] capado em N frames, e sem isso o overlay estende o
            # segmento em +0,4s (gate de duracao pegou: 3,13s contra 2,72s esperados)
            f"[base][sh]overlay={PIPX-PIPF}:{PIPY-PIPF}:shortest=1[b1];"
            f"[b1][pipv]overlay={PIPX}:{PIPY}:shortest=1{_sub(ass)}[v]")
        run(["ffmpeg","-y","-ss",str(st),"-t",str(take+0.4),"-i",src,
             "-ss",str(s),"-t",str(d+0.4),"-i",AVATAR,
             "-loop","1","-t",str(d+0.4),"-i",SHADOW,
             "-filter_complex",fc,"-r",str(FPS),"-map","[v]","-an",
             "-c:v","libx264","-pix_fmt","yuv420p",out])
    else:
        fc=(f"[0:v]{_cropf}{_eq_exposicao(cfg)}setpts=PTS/{sp},"
            f"tpad=stop_mode=clone:stop_duration=4,split=2[i1][i2];"
            + _base.replace("[base];", f"{_sub(ass)}[v]") )
        run(["ffmpeg","-y","-ss",str(st),"-t",str(take+0.4),"-i",src,
             "-filter_complex",fc,"-r",str(FPS),"-map","[v]","-an",
             "-c:v","libx264","-pix_fmt","yuv420p",out])
def r_logo(s,e,out):
    # REVEAL DA LOGO mais RICO: sunburst girando (raios) + glow radial + scale-in + light sweep.
    # Logo no terco superior (legenda do Submagic cai livre embaixo). cy = centro vertical da logo.
    d=e-s; N=nframes(e-s)
    fade_d=min(0.5,max(0.25,d*0.4)); sc_d=min(0.7,max(0.35,d*0.55))
    cy=H//2-300
    fc=(
        f"color={DARK}:s={W}x{H}:r={FPS}[bg0];"
        # raios: sunburst girando devagar atras, laranja suave
        f"[2:v]format=rgba,scale=1180:1180,rotate='0.3*t':c=none:ow=1180:oh=1180,"
        f"colorchannelmixer=aa=0.28[rays];"
        f"[bg0][rays]overlay=x=(W-1180)/2:y={cy}-590:format=auto[bg1];"
        # glow radial (respira via fade-in)
        f"[1:v]format=rgba,fade=t=in:st=0:d={fade_d}:alpha=1[gl];"
        f"[bg1][gl]overlay=0:0:format=auto[bg2];"
        # lockup OCC maior, scale-in + fade
        f"[0:v]fps={FPS},setpts=PTS-STARTPTS,format=yuva420p,scale=940:-1,"
        f"scale=w='trunc(iw*(0.84+0.16*min(t/{sc_d},1))/2)*2':"
        f"h='trunc(ih*(0.84+0.16*min(t/{sc_d},1))/2)*2':eval=frame,"
        f"fade=t=in:st=0:d={fade_d}:alpha=1[lg];"
        f"[bg2][lg]overlay=x='(W-w)/2':y='(H-h)/2-300':eval=frame,{cap(N)}[v]"
        # nota: a 4a camada (light sweep) usava assets/lightleak_flash.mov, que nunca foi criado
        # (r_logo nunca tinha sido exercitado num build real ate o ad02). Removida ate existir o asset.
    )
    run(["ffmpeg","-y","-loop","1","-t",str(d+0.4),"-i",LOGO,"-loop","1","-t",str(d+0.4),"-i",LOGOGLOW,
         "-loop","1","-t",str(d+0.4),"-i",SUNBURST,
         "-filter_complex",fc,"-map","[v]","-r",str(FPS),"-an","-c:v","libx264","-pix_fmt","yuv420p",out])
def r_split(text,s,e,out,wt=None):
    # SPLIT-SCREEN (bloco "time de IA"): Thales em cima + aula acelerada embaixo + legenda karaoke.
    d=e-s; N=nframes(e-s); ass=caption_ass(text,s,d,wt)
    cfg=INSERTS["imers"]; src=cfg["file"]; sp=cfg.get("speed",1.5); st=cfg.get("start",0); take=d*sp
    HALF=H//2
    fc=(
        f"[0:v]fps={FPS},scale={W}:{HALF}:force_original_aspect_ratio=increase,crop={W}:{HALF},setsar=1,{cap(N)}[top];"
        f"[1:v]setpts=PTS/{sp},fps={FPS},scale={W}:{HALF}:force_original_aspect_ratio=increase,crop={W}:{HALF},setsar=1,{cap(N)}[bot];"
        f"[top][bot]vstack=inputs=2[stk];"
        f"[stk]drawbox=x=0:y={HALF-3}:w={W}:h=6:color=0xDE7A5C@0.9:t=fill{_sub(ass)}[v]"  # divisoria laranja + legenda
    )
    run(["ffmpeg","-y","-ss",str(s),"-t",str(d+0.4),"-i",AVATAR,"-ss",str(st),"-t",str(take+0.4),"-i",src,
         "-filter_complex",fc,"-map","[v]","-an","-r",str(FPS),"-c:v","libx264","-pix_fmt","yuv420p",out])
def clean_display(t):
    # guias de pronuncia da Jheni viram texto limpo na tela
    import re as _r
    for a,b_ in [("Cláude","Claude"),("Côde","Code"),("IÁ","IA"),("IÃ","IA"),("I.A","IA"),("I.Á","IA")]:
        t=t.replace(a,b_)
    t=t.replace("…","").replace("..","")   # tira reticencias/pontinhos do roteiro da tela
    t=_r.sub(r"\s{2,}"," ",t).strip()
    return t

# conectores que NUNCA podem terminar uma linha de lettering (empurra pra proxima)
STOP={"e","ou","de","do","da","dos","das","que","o","a","os","as","no","na","nos","nas",
      "um","uma","com","por","pra","para","em","ao","mas","se","ate","sua","seu","seus","suas"}
def smart_lines(tokens, maxc):
    """tokens=[(clean,styled)]; quebra por largura ~maxc sem terminar linha em conector."""
    lines=[[]]; ln=0
    for clean,styled in tokens:
        add=len(clean)+(1 if lines[-1] else 0)
        if lines[-1] and ln+add>maxc:
            lines.append([]); ln=0; add=len(clean)
        lines[-1].append((clean,styled)); ln+=add
    # empurra conector orfao no fim da linha pra linha seguinte (2 passes)
    for _ in range(3):
        for i in range(len(lines)-1):
            if lines[i] and lines[i][-1][0].lower().strip(".,!?…") in STOP and len(lines[i])>1:
                lines[i+1].insert(0,lines[i].pop())
    return [L for L in lines if L]
def _wclean(w): return re.sub(r"[^\wÀ-ÿ'\-!?…,.]","",w)
_ANTON_FP=os.path.join(FONTS,"Anton-Regular.ttf")
_FCACHE={}
def _anton(size):
    if size not in _FCACHE:
        try: _FCACHE[size]=ImageFont.truetype(_ANTON_FP,size)
        except Exception: _FCACHE[size]=None
    return _FCACHE[size]
def caption_ass(text,s,d,wt,fontsize=92,cy=None,maxchars=14,maxw=2,big=False):
    # MOTOR estilo da REF (IG): Poppins bold BRANCO, limpo, 1-2 palavras grandes por vez (kinetic),
    # centralizado, pop de entrada. Palavra de ENFASE (CAPS do doc) em Pacifico (cursiva) com NEON rosa/azul + glow.
    if not CAP: return None   # legendas vem do Submagic (Iman); base sai limpa
    text=clean_display(text)
    def ts(x): return f"{int(x//3600)}:{int((x%3600)//60):02d}:{x%60:05.2f}"
    words=[w for w in text.split() if w.strip()]; nw=len(words)
    if nw==0: return None
    if big and words[0][:1].islower(): words[0]=words[0][:1].upper()+words[0][1:]
    disp=[_wclean(w) for w in words]
    rel=([(max(0.0,wt[j][0]-s), max(wt[j][1]-s, wt[j][0]-s+0.12)) for j in range(nw)]
         if (wt and len(wt)>=nw) else [(j*d/nw,(j+1)*d/nw) for j in range(nw)])
    def isstop(j): return disp[j].lower().strip(".,!?…") in STOP
    def emph(j):
        cw=re.sub(r"[^\wÀ-ÿ]","",disp[j]); return cw.isupper() and len(cw)>1
    # chunks de 1-2 palavras (kinetic, nunca termina em conector)
    chunks=[]; cur=[]; cl=0
    for j in range(nw):
        wl=len(disp[j])
        if cur and (cl+wl+1>maxchars or len(cur)>=maxw):
            chunks.append(cur); cur=[]; cl=0
        cur.append(j); cl+=wl+1
    if cur: chunks.append(cur)
    for i in range(len(chunks)-1):
        while len(chunks[i])>1 and isstop(chunks[i][-1]):
            chunks[i+1].insert(0,chunks[i].pop())
    if len(chunks)>=2 and len(chunks[-1])<=1:
        _last=chunks.pop(); chunks[-1]+=_last
    cx=W//2; cy=1250 if cy is None else cy
    so=max(5,fontsize//16)   # sombra suave (sem contorno preto duro, igual a ref)
    head=("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV\n"
        f"Style: L, Poppins, {fontsize}, &H00FFFFFF, &H00000000, &H64000000, -1, 0, 1, 0, {so}, 5, 60, 60, 0\n\n"  # Outline 0 = branco LIMPO + sombra
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, Effect, Text\n")
    # ENFASE = laranja do Claude (#DE7A5C, acento da marca/OCC), MESMA fonte. SEM rosa/cursiva.
    ORANGE="{\\c&H5C7ADE&}"; WHT="{\\c&HFFFFFF&}"
    # SPRING bounce estilo CapCut: entra pequena -> passa de 100% -> recua -> assenta
    SPRING="\\fscx26\\fscy26\\t(0,135,\\fscx115\\fscy115)\\t(135,210,\\fscx92\\fscy92)\\t(210,290,\\fscx100\\fscy100)"
    nc=len(chunks); raw=[rel[ch[0]][0] for ch in chunks]
    minw=d/(nc+0.5)                      # duracao minima por chunk (evita clump do align grosseiro)
    starts=[0.0]*nc
    for ci in range(nc):
        lo=starts[ci-1]+minw if ci>0 else 0.0
        starts[ci]=min(max(raw[ci],lo), d-(nc-ci)*minw*0.6)
    ev=[]
    for ci,ch in enumerate(chunks):
        cs=starts[ci]; ce=starts[ci+1] if ci+1<nc else d   # contiguo: 1 chunk por vez, sem sobrepor
        parts=[(ORANGE+disp[j]+WHT) if emph(j) else disp[j] for j in ch]
        txt=" ".join(parts)
        ev.append(f"Dialogue: 0,{ts(cs)},{ts(ce)},L,,0,0,0,"
                  f"{{\\an5\\pos({cx},{cy})\\fad(45,0){SPRING}}}{txt}")
    ass=os.path.join(TMP,f"cap_{abs(hash(text+str(s)+str(big)))%99999}.ass")
    open(ass,"w").write(head+"\n".join(ev)+"\n")
    return ass

def _sub(ass): return f",subtitles={ass}:fontsdir={FONTS}" if ass else ""

def hero_lettering_ass(text,s,d,wt,withlogo=False):
    # LETTERING GRANDE (cenas de ENFASE): metade da frase ACIMA do rosto, metade ABAIXO
    # (rosto 100% livre). Revelacao LINHA POR LINHA com pop/overshoot (limpo + impactante).
    text=clean_display(text)
    def ts(x): return f"{int(x//3600)}:{int((x%3600)//60):02d}:{x%60:05.2f}"
    words=[w for w in text.split() if w.strip()]; nw=len(words)
    if nw==0: return None
    if words[0][:1].islower(): words[0]=words[0][:1].upper()+words[0][1:]   # 1a palavra maiuscula
    rel=[max(0.0,wt[j][0]-s) for j in range(nw)] if (wt and len(wt)>=nw) else [j*d/nw for j in range(nw)]
    def isstop(j): return _wclean(words[j]).lower().strip(".,!?…") in STOP
    def emph(j):
        cw=re.sub(r"[^\wÀ-ÿ]","",_wclean(words[j])); return cw.isupper() and len(cw)>1
    mid=nw//2; sp=mid
    for cand in range(1,nw):
        if isstop(cand-1): continue
        if abs(cand-mid)<abs(sp-mid): sp=cand
    groups=[list(range(0,sp)), list(range(sp,nw))]
    def wrap(idxs):
        lines=[[]]; ln=0
        for j in idxs:
            wl=len(_wclean(words[j]))
            if lines[-1] and (ln+wl+1>16) and not isstop(lines[-1][-1]):
                lines.append([]); ln=0
            lines[-1].append(j); ln+=wl+1
        return [L for L in lines if L]
    head=("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV\n"
        "Style: H, Anton, 112, &H00FFFFFF, &H00000000, &HA0000000, 0, 0, 1, 7, 4, 5, 40, 40, 0\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, Effect, Text\n")
    ev=[]; lh=128; TOP_END=400; BOT_START=(1230 if withlogo else 1300)
    for gi,idxs in enumerate(groups):
        if not idxs: continue
        lines=wrap(idxs); nl=len(lines)
        if gi==0:  ys=[TOP_END-(nl-1-li)*lh for li in range(nl)]      # CIMA: acima do rosto
        else:      ys=[BOT_START+li*lh for li in range(nl)]           # BAIXO: abaixo do queixo
        for li,L in enumerate(lines):
            y=ys[li]; first=rel[L[0]]
            txt=" ".join((("{\\c&H00FFFF&}" if emph(j) else "{\\c&HFFFFFF&}")+_wclean(words[j])) for j in L)
            # LINHA inteira entra com pop (overshoot 70->108->100) + fade -> impactante e limpo
            ev.append(f"Dialogue: 0,{ts(first)},{ts(d)},H,,0,0,0,"
                      f"{{\\an5\\pos({W//2},{y})\\fad(90,0)\\fscx70\\fscy70\\t(0,150,\\fscx108\\fscy108)\\t(150,250,\\fscx100\\fscy100)}}"+txt)
    ass=os.path.join(TMP,f"hero_{abs(hash(text+str(s)))%99999}.ass")
    open(ass,"w").write(head+"\n".join(ev)+"\n")
    return ass

_DMFP_LET=os.path.join(FONTS,"DMSerifDisplay.ttf")
def _fit_key(key, base=176, maxw=960):
    # reduz a KEY pra caber em ~maxw px de largura (DM Serif)
    try:
        for sz in range(base, 84, -6):
            f=ImageFont.truetype(_DMFP_LET, sz)
            if f.getbbox(key)[2] <= maxw: return sz
        return 96
    except Exception:
        return base if len(key) <= 7 else 120

def serif_lettering_ass(lead, key, d, withlogo=False):
    # LETTERING estilo ad34 (tay Dantas): LEAD pequeno Playfair italico BRANCO em cima +
    # KEY GIGANTE DM Serif LARANJA embaixo, no TERCO INFERIOR (fora do rosto), com POP na entrada.
    lead=clean_display(lead or "").strip(); key=clean_display(key or "").strip().upper()
    def ts(x): return f"{int(x//3600)}:{int((x%3600)//60):02d}:{x%60:05.2f}"
    if not key: return None
    ksz=_fit_key(key)
    # POSICAO NA PARTE DE BAIXO (fora do rosto). Sem logo: bem embaixo. Com logo: acima do logo.
    y_key = 1500 if withlogo else 1690
    y_lead = y_key - int(ksz*0.58) - 40
    # VIVIDO: laranja OCC solido, contorno FINO ESCURO (nao branco) + sombra sutil -> texto crisp, nao "opaco".
    head=("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV\n"
        "Style: P, Playfair Display, 90, &H00FFFFFF, &H00202020, &H90000000, 0, 1, 1, 2.4, 3, 5, 60, 60, 0\n"
        f"Style: D, DM Serif Display, {ksz}, &H004AA6FF, &H00101010, &H90000000, 0, 0, 1, 3.2, 4, 5, 40, 40, 0\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, Effect, Text\n")
    # DINAMICO: lead sobe suave; key sobe + POP com overshoot forte (staggered, entra depois do lead)
    POP_L=r"\fscx74\fscy74\t(0,150,\fscx104\fscy104)\t(150,260,\fscx100\fscy100)"
    POP_K=r"\fscx44\fscy44\t(0,160,\fscx114\fscy114)\t(160,300,\fscx100\fscy100)"
    ev=[]
    if lead:
        ev.append(f"Dialogue: 0,{ts(0.0)},{ts(d)},P,,0,0,0,{{\\an5\\move(540,{y_lead+24},540,{y_lead},0,220)\\fad(110,0){POP_L}}}{lead}")
    if LETTER_STYLE == "foil":
        # FOIL EA PREMIUM (11/07/2026, escolha do Julio): gradiente metalico em 5 faixas (clip fixo + 1c
        # interpolada, so tons quentes) + rim-light na crista + bloom sutil por tras; base laranja crisp intocada.
        gs = 0.42                                    # foil entra APOS o pop assentar (base start 0.12 + 0.30)
        gtop = round(y_key - 0.44*ksz); gbot = round(y_key + 0.32*ksz); span = gbot - gtop
        yb = [gtop + round(i*span/5) for i in range(6)]
        rimTop = gtop; rimBot = gtop + round(0.16*span)
        cols = ["A8E0FF", "7AC6FF", "4AA6FF", "3084E2", "1C64BC"]   # crista->bronze (BGR)
        ev.append(f"Dialogue: 3,{ts(gs)},{ts(d)},D,,0,0,0,{{\\an5\\pos(540,{y_key})\\bord5\\blur9\\shad0\\1c&H4AA6FF&\\3c&H145AB4&\\1a&H86&\\3a&H4A&\\4a&HFF&\\fad(200,0)}}{key}")
        ev.append(f"Dialogue: 4,{ts(0.12)},{ts(d)},D,,0,0,0,{{\\an5\\move(540,{y_key+38},540,{y_key},0,250)\\fad(130,0){POP_K}}}{key}")
        for i, c in enumerate(cols):
            ev.append(f"Dialogue: 5,{ts(gs)},{ts(d)},D,,0,0,0,{{\\an5\\pos(540,{y_key})\\bord0\\shad0\\1c&H{c}&\\fad(150,0)\\clip(30,{yb[i]},1050,{yb[i+1]})}}{key}")
        ev.append(f"Dialogue: 6,{ts(gs)},{ts(d)},D,,0,0,0,{{\\an5\\pos(540,{y_key})\\bord0\\shad0\\blur0.6\\1c&HDCF5FF&\\fad(150,0)\\clip(30,{rimTop},1050,{rimBot})}}{key}")
    else:
        ev.append(f"Dialogue: 0,{ts(0.12)},{ts(d)},D,,0,0,0,{{\\an5\\move(540,{y_key+38},540,{y_key},0,250)\\fad(130,0){POP_K}}}{key}")
    ass=os.path.join(TMP,f"serif_{abs(hash(lead+key))%99999}.ass")
    open(ass,"w").write(head+"\n".join(ev)+"\n")
    return ass

def r_lettering_serif(lead,key,s,e,out,withlogo=False):
    # LETTERING sobre avatar CLARO/NORMAL (NAO escurece a tela, NAO desfoca) -> pedido do Julio.
    # Texto legivel pelo contorno+sombra da fonte. Texto BAKED; cena registrada no timing pra blank do tay.
    d=e-s; N=nframes(e-s); ass=serif_lettering_ass(lead,key,d,withlogo)
    zp=(f"fps={FPS},{REFRAME},"
        f"zoompan=z='min(zoom+0.0003,1.06)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H},setsar=1,{cap(N)}")
    inputs=["-ss",str(s),"-t",str(d+0.4),"-i",AVATAR]
    fc=f"[0:v]{zp}{_sub(ass)}[v]"
    if withlogo:
        inputs=["-ss",str(s),"-t",str(d+0.4),"-i",AVATAR,"-i",LOGO]
        fc=(f"[0:v]{zp}[bg];[1:v]scale=430:-1[lg];[bg][lg]overlay=(W-w)/2:H-h-46{_sub(ass)}[v]")  # logo bem embaixo
    run(["ffmpeg","-y",*inputs,"-filter_complex",fc,"-map","[v]","-an",
         "-r",str(FPS),"-c:v","libx264","-pix_fmt","yuv420p",out])

def r_lettering(text,s,e,out,withlogo=False,wt=None):
    # CENA DE ENFASE: Thales P&B + KINETIC TYPOGRAPHY grande (poucas palavras por vez, 1 linha,
    # caixa de destaque). Nunca quebra em varias linhas. Posicao fora do rosto (baixo, ou cima qd tem logo).
    d=e-s; N=nframes(e-s)
    ass=caption_ass(text,s,d,wt,fontsize=120,cy=(520 if withlogo else 1180),maxchars=13,maxw=2,big=True)
    # base limpa (sem P&B): talking-head reenquadrado igual r_orig; texto vem do Submagic.
    zp=(f"fps={FPS},{REFRAME},"
        f"zoompan=z='min(zoom+0.0003,1.07)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H},setsar=1,{cap(N)}")
    inputs=["-ss",str(s),"-t",str(d+0.4),"-i",AVATAR]
    fc=f"[0:v]{zp}{_sub(ass)}[v]"
    if withlogo:
        # CTA: faixa escura no topo (logo descola do cabelo) + logo MAIOR com destaque.
        inputs=["-ss",str(s),"-t",str(d+0.4),"-i",AVATAR,"-i",LOGO,"-i",TOPSCRIM,"-i",LOGOGLOW]
        fc=(f"[0:v]{zp}{_sub(ass)}[bgt];"
            f"[2:v]format=rgba[scrim];[bgt][scrim]overlay=0:0:format=auto[bsc];"        # gradiente escuro no topo
            f"[3:v]format=rgba,crop={W}:520:0:0,colorchannelmixer=aa=0.55[glow];"        # glow atras da logo (so o topo)
            f"[bsc][glow]overlay=0:-120:format=auto[bgl];"
            f"[1:v]scale=560:-1[lg];"                                                     # logo maior
            f"[bgl][lg]overlay=(W-w)/2:70[v]")                                            # mais alta, sobre a faixa
    run(["ffmpeg","-y",*inputs,"-filter_complex",fc,"-map","[v]","-an",
         "-r",str(FPS),"-c:v","libx264","-pix_fmt","yuv420p",out])

# ================= MAIN =================
blocks=parse(os.environ.get("VAM_ROTEIRO", os.path.join(BASE,"inputs","ad34_leva3.txt")))
narr_words=[]
for b in blocks: narr_words += b["narr"].split()
words=align(AVATAR, narr_words)
# atribuir spans por contagem de palavras de cada bloco
spans=[]; bwords=[]; idx=0
for b in blocks:
    n=len(b["narr"].split())
    seg=words[idx:idx+n] if n else words[idx:idx+1]
    idx+=n
    s=seg[0][0] if seg else (spans[-1][1] if spans else 0)
    e=seg[-1][1] if seg else s+0.8
    if e<=s: e=s+0.6
    spans.append((s,e)); bwords.append([(w[0],w[1]) for w in seg])
# CONTIGUIDADE OBRIGATORIA (bug do pip sobre avatar, 16/07): a cadeia xfade posiciona
# cada bloco por SOMA DAS DURACOES, entao o mapeamento avatar-time -> reel-time so e exato
# se os spans forem contiguos (fim do bloco i == inicio do bloco i+1). O alinhamento de
# palavras gera gaps (pausa entre blocos) e overlaps (fuzz do parakeet) de ate ~0.7s, e cada
# um vira drift ACUMULADO: o conteudo desliza em relacao as janelas do pip/legenda (avatar-time)
# e a bolinha aparece em cima do avatar em tela cheia. Fix: a fronteira entre blocos e SEMPRE
# o inicio da 1a palavra do proximo bloco (gap = bloco atual segura a pausa; overlap = corta
# o rabo do atual). Monotonicidade garantida com duracao minima de 0.3s por bloco.
_bounds=[spans[0][0]]
for i in range(1,len(spans)):
    _bounds.append(max(spans[i][0], _bounds[-1]+0.3))
_bounds.append(max(spans[-1][1], _bounds[-1]+0.3))
spans=[(_bounds[i],_bounds[i+1]) for i in range(len(spans))]

# CAP DE INSERT (campo `dur_max` do inserts.json). B-roll longo no fim do anuncio nao
# deixa o CTA respirar: no jh13 o bloco 15 tinha 11,6s de tela e o CTA nascia so depois,
# vivendo 1,99s (reprovacao do diretor de arte). Com dur_max o bloco vira DOIS: o insert
# ate o cap e o avatar no resto, e o CTA sobe no retorno do avatar.
# TEM que ser aqui tambem, nao so no gen_ad_v2: capar apenas o overlay adiantou o CTA
# mas deixou a imagem no split, e o CTA foi parar em cima do rosto dele (medido aos
# 85,5s no build de 23h30). Overlay e footage sao dois motores; cap num so = desencontro.
# RITMO (18/08/2026): o `dur_max` cortava o bloco em DOIS. Agora o mesmo mecanismo corta
# em N planos, com reenquadramento e volta pro avatar no meio, porque a medicao mostrou a
# leva em 4,7 a 7,6 cortes/min contra 19 a 28 das referencias que o Julio mandou. Ver
# ritmo.py: o plano e deterministico e o gen_ad_v2 chama a MESMA funcao.
sys.path.insert(0, BASE)
import ritmo as _R

_entrada = []
for _b, (_s, _e) in zip(blocks, spans):
    _cfg = find_insert(_b["instr"]) if _b["type"] == "insert" else None
    _entrada.append({"tipo": "insert" if _b["type"] == "insert" else "orig",
                     "s": _s, "e": _e,
                     "crop": (_cfg or {}).get("crop"),
                     "dur_max": (_cfg or {}).get("dur_max"),
                     # a fala do bloco: o ritmo trava o insert quando ela aponta pra
                     # tela ("...que voce ta vendo NA TELA" com o quadro no avatar,
                     # print do Julio 28/08). Nos QUATRO chamadores, ou desencontra.
                     "texto": _b.get("narr", "")})
_plano = _R.plano_de_ritmo(_entrada)

_nb, _ns, _nw = [], [], []
# a tupla de palavra e (inicio, fim), NAO (texto, tempo): a narracao se fatia por
# CONTAGEM, igual o cap antigo fazia (_pal[:len(_wa)]). Descobri isso quebrando.
_usadas = {}
for _seg in _plano:
    _bi = _seg["bloco"]
    _b = blocks[_bi]
    _wt = bwords[_bi]
    _s2, _e2 = _seg["s"], _seg["e"]
    _wa = [w for w in _wt if _s2 <= w[1] < _e2]
    _ini = _usadas.get(_bi, 0)
    _pal = _b["narr"].split()
    _novo = {**_b, "narr": " ".join(_pal[_ini:_ini + len(_wa)])}
    _usadas[_bi] = _ini + len(_wa)
    if _seg["tipo"] == "orig" and _b["type"] == "insert":
        _novo["type"] = "orig"          # plano que volta pro rosto no meio do insert
    if _seg.get("layout"):
        # ALTERNANCIA DE LAYOUT (26/08/2026). Com o `crop` desligado no split, duas
        # visitas ao mesmo asset mostravam o quadro IDENTICO e o corte nao registrava
        # na deteccao de cena: medi 17 cortes no arquivo contra 12 visitas planejadas,
        # e 75% do anuncio em plano acima de 6s. Trocar o layout entre visitas muda
        # ~60% dos pixels e registra de verdade, sem precisar de asset novo nem de
        # zoom (que foi o que o Julio reprovou).
        _novo["_layout"] = _seg["layout"]
    if _seg.get("crop"):
        _novo["_crop"] = _seg["crop"]   # reenquadramento deste plano
    if _seg.get("base"):
        _novo["_base"] = _seg["base"]   # escala base: o salto entre planos E o corte
    if _seg.get("fonte_off"):
        _novo["_fonte_off"] = _seg["fonte_off"]   # a fonte do insert nao reinicia
    _nb.append(_novo); _ns.append((_s2, _e2)); _nw.append(_wa)
blocks, spans, bwords = _nb, _ns, _nw
_res = _R.resumo(_plano, spans[-1][1])
# o plano vai pro disco: o mixador de SFX (mixar_sfx.py) coloca whoosh/riser em cima
# dos cortes REAIS, e recalcular isso fora daqui dessincroniza (dois motores, regra 1).
_nome_out = os.path.splitext(os.environ.get("VAM_OUT", "ad34_validacao.mp4"))[0]
with open(os.path.join(OUTD, _nome_out + "_ritmo.json"), "w") as _fh:
    json.dump({"segs": _plano, "total": spans[-1][1]}, _fh)
print(f"  [ritmo] {len(_plano)} planos | {_res['cortes_min']:.1f} cortes/min | "
      f"plano medio {_res['plano_medio']:.2f}s | maior {_res['maior_plano']:.2f}s "
      f"(referencia: 19 a 28 cortes/min)")

total=spans[-1][1]
print(f"{len(blocks)} blocos | total {total:.1f}s")

N=len(blocks)
# RENDER EM PARALELO POR SEGMENTO (31/08/2026, build 42->43). Este loop renderizava os
# 43 segmentos um ffmpeg atras do outro: ~7 min de um build de ~20 (o passo [4/6] sozinho
# e a maior fatia). Cada segmento e independente (recebe bloco+span+out e escreve um mp4),
# entao vira pool de threads (o ffmpeg roda em subprocess, o GIL nao pesa).
# DEPENDENCIA REAL ENTRE VIZINHOS (a unica achada): o jump cut de escala em "orig" e
# "lettering" alterna contra `blocks[i-1]["_base"]`, e o proprio loop escrevia `_base`
# no bloco atual pra o proximo ler. Isso e sequencial por natureza (cada base depende da
# anterior) mas NAO depende de render nenhum: e so decisao de numero. Por isso ela sai
# do pool e vira um PASSE 1 sequencial e barato (sem ffmpeg), exatamente com a mesma
# logica que o loop original tinha; o PASSE 2 (o ffmpeg de verdade) roda em paralelo,
# cada thread so lendo `b["_base"]` ja decidido, nunca escrevendo no bloco do vizinho.
# `segs`/`letter_ranges` viram listas append-only preenchidas POR INDICE (nao por ordem
# de termino), pra o resto do arquivo (cadeia xfade, timing.json) continuar recebendo os
# segmentos na mesma ordem de sempre.
import concurrent.futures
import hashlib
import shutil
import cache_segmento

VAM_CACHE_SEG = os.environ.get("VAM_CACHE_SEG", "1") != "0"
CACHE_DIR = os.path.join(TMP, "cache")
if VAM_CACHE_SEG:
    os.makedirs(CACHE_DIR, exist_ok=True)

# ---- PASSE 1 (sequencial, sem ffmpeg): decide b["_base"] de cada bloco em ordem ----
for i, b in enumerate(blocks):
    # DEPOIS DE INSERT, ESCALA 1,0 SEMPRE (31/08/2026, build 44). As fatias que o plano de
    # ritmo cria ja chegam com `_base` (linha do `_novo["_base"] = _seg["base"]`), entao a
    # regra "se vier de insert, volta em 1,0" nao valia pra elas: a fatia de apresentador
    # logo depois do split entrou ampliada, o queixo desceu ate a faixa da legenda e o
    # gate de colisao pegou 7,5% do rosto coberto em t=10,5s. A troca de imagem ja e o
    # corte; ampliar ali nao compra nada e custa a legenda.
    if i > 0 and b["type"] in ("orig", "lettering") and \
            blocks[i-1]["type"] in ("insert", "logo", "lettering_logo"):
        b["_base"] = 1.0
        continue
    if b["type"] == "orig":
        # `_base` NUNCA ERA PREENCHIDO (31/08/2026, build 41): o r_orig documenta o jump
        # cut por escala (1,00 / 1,14 / 1,28) mas nenhum modulo grava `_base`, entao todo
        # bloco de apresentador entrava em 1,0 e fronteira orig->orig tinha scene 0,008.
        # Mesma regra do lettering: alterna contra o bloco anterior se ele tambem for
        # apresentador; se vier de insert, volta em 1,0 (a troca de imagem ja e o corte).
        if "_base" not in b:
            _prev = blocks[i-1] if i>0 else None
            _prev_apres = _prev is not None and _prev["type"] not in ("insert","logo","lettering_logo")
            b["_base"] = (1.14 if _prev.get("_base",1.0) < 1.07 else 1.0) if _prev_apres else 1.0
    elif b["type"] == "lettering":
        # JUMP CUT TAMBEM NO LETTERING (31/08/2026, build 40). O bloco de lettering e
        # apresentador por baixo, e era renderizado sem `base`: a imagem seguia igual a
        # do bloco vizinho e a fronteira nao existia visualmente (scene 0,01). Com a
        # juncao seca isso ficou nu: 16 de 33 fronteiras planejadas sem corte visivel e
        # o ritmo medido caiu a 14,7/min. A escala alterna contra o bloco ANTERIOR, o
        # mesmo jump cut de reel que os sub-planos do apresentador ja usam.
        _bprev = blocks[i-1].get("_base",1.0) if i>0 else 1.0
        # 1,28 e nao 1,14 (build 41): o salto de 14% deu scene 0,12 a 0,21 nas fronteiras,
        # abaixo dos 0,30 que as referencias cruzam, e o olho concorda: 14% em rosto
        # sobre fundo escuro le como tremida, nao como corte. 1,28 e o terceiro degrau
        # que os sub-planos do apresentador ja usam.
        # 1,14 e nao 1,28 (31/08, build 43): com 1,28 o rosto desceu ate a faixa da legenda
        # (colisao: 7,6% do rosto em t=10,5s) e o ritmo medido NAO subiu (15,3/min nos
        # dois). Escala maior nao comprou corte, so comprou colisao.
        b["_base"] = 1.14 if _bprev < 1.07 else 1.0

def _preparar_insert_cfg(b):
    """Monta o cfg final do insert (mesma logica do loop antigo) uma unica vez, pra
    servir tanto a chave de cache quanto o render de verdade: duplicar essa logica em
    dois lugares e como a marcacao de layout do ritmo ja vazou silenciosamente antes."""
    _c = find_insert(b["instr"])
    if b.get("_layout"):
        # O layout vem do PLANO DE RITMO e mora no bloco; o r_insert recebe o cfg do
        # INSERT. Sem repassar aqui, a marcacao nunca chegava e as duas fatias
        # marcadas "cheio" no jh13 renderizaram em split assim mesmo (conferido em
        # quadro, t=37s e t=84s). Quarto ramo do mesmo erro do dia: emenda que
        # compila, nao aplica.
        _c = {**_c, "_layout": b["_layout"]}
    if b.get("_crop"):
        _c = {**_c, "crop": b["_crop"]}   # reenquadramento deste plano (jump cut)
    if b.get("_fonte_off"):
        # a fonte do insert continua de onde parou quando o plano volta pro rosto e
        # depois retorna. `start` e em tempo de FONTE, entao o deslocamento entra
        # multiplicado pela velocidade do insert.
        _off = float(b["_fonte_off"]) * float(_c.get("speed", 1.0) or 1.0)
        _c = {**_c, "start": float(_c.get("start", 0) or 0) + _off}
    return _c

def _render_segmento(i):
    """Corpo do loop antigo pra UM segmento. So le `b["_base"]` (ja decidido no passe
    1); nao escreve em nenhum bloco vizinho. Devolve (i, out, letter_range_ou_None)."""
    b, (s, e) = blocks[i], spans[i]
    # o handle deste bloco alimenta a transicao que entra no bloco SEGUINTE, entao ele
    # tem que ser o XF DAQUELA transicao. Se divergir, o total muda e a footage deixa de
    # casar com o overlay (e o composite corta a cauda junto com o audio).
    h = xf_dur(blocks[i+1], blocks[i]) if i<N-1 else 0.0
    ee = e+h
    out = os.path.join(TMP,f"s{i:02d}.mp4")
    tipo = b["type"]
    letter_range = None
    _c = _preparar_insert_cfg(b) if tipo == "insert" else None
    _sera_serif = tipo in ("lettering","lettering_logo") and BAKE_LETTERING
    if _sera_serif:
        letter_range = (s, e)

    def _renderizar():
        if   tipo=="orig":
            r_orig(b["narr"],s,ee,out,wt=bwords[i],idx=i,base=b["_base"])
        elif tipo=="insert":
            r_insert(_c,b["narr"],s,ee,out,wt=bwords[i])
        elif tipo=="logo":
            r_logo(s,ee,out)
        # lettering: BAKE_LETTERING (ad01) -> serif do TEXTO DE DESTAQUE (b["key"], coluna E da
        # planilha, != legenda), avatar escurecido; blankar a legenda tay nessa cena. Default
        # (ad34) -> talking-head limpo.
        elif tipo=="lettering":
            if BAKE_LETTERING:
                r_lettering_serif(b.get("lead",""), b.get("key") or b["narr"], s, ee, out)
            else:
                r_orig(b["narr"],s,ee,out,wt=bwords[i],idx=i,base=b["_base"])
        elif tipo=="lettering_logo":
            if BAKE_LETTERING:
                r_lettering_serif(b.get("lead",""), b.get("key") or b["narr"], s, ee, out, withlogo=True)
            else:
                r_orig(b["narr"],s,ee,out,wt=bwords[i],idx=i)

    if not VAM_CACHE_SEG:
        _renderizar()
        print(f"  {i:2d} {tipo:14} {s:5.1f}-{e:5.1f}s ok")
        return i, out, letter_range

    # CACHE POR SEGMENTO: chave sha256 de tudo que decide o pixel final. Fonte (AVATAR
    # ou o arquivo do insert) entra por mtime+tamanho, nao pelo caminho: o mesmo nome
    # com conteudo trocado nao pode devolver cache velho.
    fonte_path = _c["file"] if _c else AVATAR
    try:
        _st = os.stat(fonte_path)
        fonte_stat = (_st.st_mtime, _st.st_size)
    except OSError:
        fonte_stat = (0.0, 0)
    chave = cache_segmento.chave_segmento(
        tipo=tipo, narr=b["narr"], s=s, e=e, ee=ee,
        base=b.get("_base",1.0), layout=b.get("_layout"), insert_cfg=_c,
        fonte_stat=fonte_stat, versao=VERSAO_RENDER)
    cache_path = os.path.join(CACHE_DIR, chave+".mp4")
    if os.path.exists(cache_path):
        shutil.copyfile(cache_path, out)
        print(f"  {i:2d} {tipo:14} cache")
        return i, out, letter_range
    _renderizar()
    try:
        shutil.copyfile(out, cache_path)
    except OSError as _e:
        print(f"  [AVISO] nao gravou cache do segmento {i:02d}: {_e}", flush=True)
    print(f"  {i:2d} {tipo:14} {s:5.1f}-{e:5.1f}s ok")
    return i, out, letter_range

# ---- PASSE 2 (paralelo, com ffmpeg de verdade) ----
_segs_por_i = [None]*N
_letter_por_i = [None]*N
_max_workers = int(os.environ.get("VAM_PARALELO","4"))
with concurrent.futures.ThreadPoolExecutor(max_workers=_max_workers) as _ex:
    for _i, _out, _lr in _ex.map(_render_segmento, range(N)):
        _segs_por_i[_i] = _out
        _letter_por_i[_i] = _lr
segs = _segs_por_i
letter_ranges = [lr for lr in _letter_por_i if lr is not None]

# cadeia de xfade: DISSOLVE puro (transition=fade) -> nada desliza, entao a bolinha do PiP
# nao "viaja" no corte. O ritmo/luz vem dos light-leaks (overlay abaixo), nao de slides.
durs=[vdur(p) for p in segs]
# GATE de duracao: cada segmento tem que medir (e-s)+XF (ultimo: e-s). Segmento fora disso
# desloca todos os blocos seguintes na cadeia e o pip/legenda dessincroniza do conteudo.
for i,((s,e),d_real) in enumerate(zip(spans,durs)):
    d_exp=(e-s)+(xf_dur(blocks[i+1], blocks[i]) if i<N-1 else 0.0)
    if abs(d_real-d_exp)>0.1:
        sys.exit(f"ERRO seg {i:02d}: duracao {d_real:.2f}s != esperada {d_exp:.2f}s "
                 f"(fonte curta ou render quebrado); abortando pra nao montar video dessincronizado")
inputs=[]
for p in segs: inputs+=["-i",p]
fc=[]; prev="0:v"; acc=durs[0]; cut_centers=[]
_secos=0
# CORTE SECO DE VERDADE E CONCAT, NAO XFADE CURTO (18/08/2026). Dois modos:
#   xfade com duration=0.04 gera UM quadro de blend no meio do corte e o salto se
#     divide em dois degraus que nao cruzam o limiar de cena (medido: 0,23+0,06 no
#     jh14, cujos inserts sao escuros). O olho ve a mesma coisa: corte amortecido.
#   xfade com duration<1 frame (0.001) COLAPSA a cadeia no primeiro corte: o ffmpeg
#     encerra o stream no offset e o arquivo sai com 4,8s dos 85s.
# Entao quando o ad inteiro e seco (XF e XF_SECO ambos ~0), a emenda e concat puro.
if XF < 0.01 and XF_SECO < 0.01:
    for i in range(1,N):
        if blocks[i]["type"] in ("insert","logo","lettering_logo") or \
           (blocks[i]["type"]=="lettering" and "time de" in blocks[i]["narr"].lower()):
            cut_centers.append(acc)
        acc=acc+durs[i]
    fc=["".join(f"[{i}:v]" for i in range(N))+f"concat=n={N}:v=1:a=0[vcat]"]
    prev="vcat"; _secos=N-1; _xf_total=0.0
    print(f"  transicoes: concat puro, {N-1} corte(s) seco(s) sem blend")
else:
    # GRAFO MISTO (31/08/2026): juncao seca e CONCAT (zero blend, corte de verdade),
    # volta macia e XFADE. Historico que obriga isso: xfade de 0,04s amortece o corte
    # (o detector de cena e o olho veem degrau duplo), xfade de 1/30s COLAPSA a cadeia
    # (build 36 saiu com 76s de 90, com codigo 0), e deslize em 2 quadros rasga o quadro
    # (4 costuras achadas em 29/08). Concat nao tem nenhum dos tres.
    # TIMEBASE UNICO: concat devolve tb 1/1000000 e os arquivos vem em 1/15360; o xfade
    # exige os dois lados iguais. Toda entrada e toda saida intermediaria passam por
    # settb=AVTB. Provado em repro sintetico (5 clipes, 18,000s exatos) antes de entrar.
    # CONTAGEM EXATA DE QUADROS POR SEGMENTO (31/08/2026, build 39). Com concat, a cadeia
    # saiu 0,86s mais curta que o plano e os cortes derivaram ate 0,5s no fim do video:
    # cada segmento perdia ~1 quadro na emenda (24 juncoes secas x 1/30s = 0,8s). O xfade
    # de antes escondia isso porque o offset era calculado do arquivo medido. Aqui cada
    # segmento e forcado a K = nframes(bloco) + nframes(cauda) quadros: se sobrar, corta;
    # se faltar, clona o ultimo. A soma da cadeia passa a ser aritmetica, nao medicao.
    # QUADRO PRETO NA FRENTE (mesmo build, corte de 7,27s): o painel de cima entrava preto
    # por um quadro enquanto o apresentador ja estava embaixo. O overlay do split com
    # shortest=1 nao tem o primeiro quadro do insert pronto em t=0. O blend do xfade
    # escondia; o concat mostra. Segmento cujo primeiro quadro e escuro perde esse quadro
    # e ganha um clone no fim, entao a contagem nao muda.
    _kf=[]
    for i,(s,e) in enumerate(spans):
        _xf_next = xf_dur(blocks[i+1], blocks[i]) if i<N-1 else 0.0
        _kf.append(nframes(e-s)+nframes(_xf_next) if _xf_next>1e-6 else nframes(e-s))
    fc=[]
    for i in range(N):
        _ini = 1 if _lum_primeiro_quadro(segs[i]) < 128 else 0
        if _ini:
            print(f"  seg {i:02d}: primeiro quadro preto, descartado", flush=True)
        fc.append(f"[{i}:v]trim=start_frame={_ini},setpts=PTS-STARTPTS,fps={FPS},"
                  f"tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame={_kf[i]},"
                  f"setpts=PTS-STARTPTS,settb=AVTB[n{i}]")
    durs=[k/FPS for k in _kf]      # a partir daqui a duracao e a contada, nao a medida
    acc=durs[0]
    prev="n0"; _xf_total=0.0
    for i in range(1,N):
        _xf=xf_dur(blocks[i], blocks[i-1])
        if _xf<=1e-6:
            _secos+=1
            fc.append(f"[{prev}][n{i}]concat=n=2:v=1:a=0,settb=AVTB[v{i}]")
            centro=acc
        else:
            off=acc-_xf; _xf_total+=_xf
            fc.append(f"[{prev}][n{i}]xfade=transition={xf_tipo(blocks[i],i,blocks[i-1])}:duration={_xf}:offset={off:.4f},settb=AVTB[v{i}]")
            centro=off+_xf/2
        # corte "grande" = entra insert/logo/split/cta -> ganha light-leak quente
        if blocks[i]["type"] in ("insert","logo","lettering_logo") or \
           (blocks[i]["type"]=="lettering" and "time de" in blocks[i]["narr"].lower()):
            cut_centers.append(centro)
        prev=f"v{i}"; acc=acc+durs[i]-_xf
    print(f"  transicoes: {_secos} corte(s) seco(s) por concat + "
          f"{N-1-_secos} whip(s) de {XF}s por xfade")
vchain0=os.path.join(TMP,"vchain0.mp4")
run(["ffmpeg","-y",*inputs,"-filter_complex","; ".join(fc),"-map",f"[{prev}]",
     "-r",str(FPS),"-c:v","libx264","-pix_fmt","yuv420p","-an",vchain0])
# GATE DE DURACAO DA CADEIA (31/08/2026). O build 36 perdeu 18,7s de fala e o ffmpeg
# devolveu codigo 0: o -shortest do mux final aparou o resto em silencio. A cadeia tem
# que medir a soma dos blocos; qualquer coisa diferente e colapso e aborta AQUI, antes
# de gastar mais 10 minutos de composite num video mutilado.
# ESPERADO = ARITMETICA DO GRAFO, NAO SOMA DOS SPANS (31/08/2026). A primeira versao
# comparava com sum(e-s) e abortou o build 38 por 0,86s: cada segmento arredonda para
# quadro inteiro (nframes) e ~30 segmentos acumulam sub-segundo. Isso nao e colapso.
# Colapso e perder segundos: a cadeia medir menos que (soma dos segmentos renderizados
# menos a sobreposicao dos whips). E contra ISSO que o gate compara. A diferenca para
# a soma dos spans fica so no log, como aviso.
_esp_cadeia=sum(durs)-_xf_total
_real_cadeia=vdur(vchain0)
_esp_spans=sum(e-s for s,e in spans)
if abs(_esp_cadeia-_esp_spans)>0.5:
    print(f"  AVISO cadeia: grafo soma {_esp_cadeia:.2f}s, spans somam {_esp_spans:.2f}s "
          f"({_esp_cadeia-_esp_spans:+.2f}s de arredondamento/gaps)", flush=True)
if abs(_real_cadeia-_esp_cadeia)>0.15:
    sys.exit(f"ERRO cadeia: {_real_cadeia:.2f}s != {_esp_cadeia:.2f}s esperados "
             f"(diferenca {_real_cadeia-_esp_cadeia:+.2f}s). A cadeia de transicoes colapsou; "
             "abortando pra nao entregar video aparado.")
print(f"  cadeia: {_real_cadeia:.2f}s (esperado {_esp_cadeia:.2f}s) ok")

# LIGHT-LEAKS: bloom quente sutil (screen) nos cortes grandes -> "efeito de luz" sem mover conteudo
vchain=os.path.join(TMP,"vchain.mp4")
if cut_centers and os.path.exists(LIGHTLEAK_FLASH):
    li=["-i",vchain0]
    for _ in cut_centers: li+=["-i",LIGHTLEAK_FLASH]
    fl=[]; prev="0:v"
    for k,tc in enumerate(cut_centers):
        idx=k+1; st=max(0.0,tc-0.25)
        fl.append(f"[{idx}:v]format=rgba,colorchannelmixer=aa=0.55,setpts=PTS+{st:.3f}/TB[lk{k}]")
        fl.append(f"[{prev}][lk{k}]overlay=0:0:eof_action=pass:format=auto[ov{k}]")
        prev=f"ov{k}"
    run(["ffmpeg","-y",*li,"-filter_complex","; ".join(fl),"-map",f"[{prev}]",
         "-r",str(FPS),"-c:v","libx264","-pix_fmt","yuv420p","-an",vchain])
else:
    vchain=vchain0

# reanexar o audio CONTINUO do avatar por cima (mantem lip-sync, zero drift)
a0=spans[0][0]            # inicio do 1o span no avatar
audlen=total-a0          # janela de audio = soma das duracoes dos spans
# DUMP de timing: a0 + spans dos b-rolls (avatar-time). reel-time t <-> avatar-time (a0+t).
# Usado pra compor o circulo do Thales DEPOIS do Submagic (assim o magicZooms nao arrasta).
_ins=[{"s":spans[i][0],"e":spans[i][1]} for i,b in enumerate(blocks) if b["type"]=="insert"]
_let=[{"s":a,"e":b} for (a,b) in letter_ranges]   # cenas serif: blankar legenda do Submagic
json.dump({"a0":a0,"total":total,"xf":XF,"avatar":AVATAR,"inserts":_ins,"letterings":_let}, open(os.path.join(OUTD,"timing.json"),"w"))
out=os.path.join(OUTD, os.environ.get("VAM_OUT","ad34_validacao.mp4"))
run(["ffmpeg","-y","-i",vchain,"-ss",str(a0),"-t",str(audlen),"-i",AVATAR,
     # colorspace=all=bt709:iall=bt709:fast=1 no FIM da cadeia: so re-marca a tag (fast=1 = sem
     # conversao de pixel de verdade, ja que a fonte JA e bt709, so estava sem tag). Sem isso o
     # libx264 marca a saida como bt2020nc/arib-std-b67 (HDR/HLG) mesmo o conteudo sendo SDR normal
     # (as flags -color_primaries/-color_trc de output sozinhas NAO bastam, testado: so o filtro
     # escreve a VUI certa no bitstream). Player que respeita a tag (WhatsApp, iPhone) decodifica
     # com a curva errada e o video sai avermelhado/quente.
     "-filter_complex","[0:v]noise=alls=7:allf=t+u,eq=contrast=1.03:saturation=0.97,vignette=PI/5.5,"
     "colorspace=all=bt709:iall=bt709:fast=1[v]",
     "-map","[v]","-map","1:a","-c:v","libx264","-crf","18","-pix_fmt","yuv420p",
     "-colorspace","bt709","-color_primaries","bt709","-color_trc","bt709","-color_range","tv",
     "-c:a","aac","-shortest",out])
print("PRONTO:",out)
