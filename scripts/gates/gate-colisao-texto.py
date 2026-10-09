#!/usr/bin/env python3
"""
Gate de auditoria automatica: colisao entre texto (legenda queimada, bloco de CTA)
e o rosto do apresentador, em video de anuncio 1080x1920.

POR QUE ESSE SCRIPT EXISTE (defeito real, 17/08/2026):
Um anuncio (jh13v2_espuma_roxa) saiu com a legenda queimada e o bloco de CTA caindo
em cima da boca do apresentador, e tambem em cima do diagrama do insert. Ninguem
mediu isso antes de entregar. Foi descoberto so quando alguem assistiu o video
pronto. Esse script MEDE a sobreposicao entre texto e rosto, quadro a quadro, e
reprova a entrega antes de chegar no usuario, em vez de depender do olho humano
pegar isso no replay final.

USO:
    python3 gate-colisao-texto.py <video.mp4> [--overlay <overlay.mov>] [--json]

Com --overlay, o script usa o canal alpha do .mov (onde SO o nosso texto/CTA e
opaco) pra achar a area de texto com precisao. Sem --overlay, ele tenta adivinhar
faixas de texto no proprio video por densidade de pixel muito claro, o que e bem
mais fraco (uma tela de insert clara pode confundir o detector). Sempre que tiver
o .mov do overlay disponivel, use.
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

try:
    import cv2
    import numpy as np
except ImportError as _e:       # dependencia que o aluno ainda nao instalou: mensagem, nao traceback
    sys.exit(f"Falta uma dependência Python deste gate ({_e.name}). Instale com:\n"
             "  pip install -r scripts/gates/requirements.txt")

# Intervalo entre quadros amostrados. 1.5s foi o valor pedido no briefing: denso o
# suficiente pra pegar legenda que troca a cada 1 a 2s, sem gerar milhares de PNGs
# num video de 1 a 2 minutos.
INTERVALO_AMOSTRA_PADRAO = 1.5

# Acima de quantos % da area do rosto cobertos por texto o gate reprova. 12% foi o
# numero pedido no briefing: pequenas bordas de legenda encostando no queixo nao
# reprovam, mas legenda em cima da boca ou bloco de CTA em cima do rosto, sim.
LIMIAR_COLISAO_PADRAO = 1.5

# No overlay, alpha > 40 conta como "pixel do nosso texto". O overlay tem um fundo
# semi-transparente atras da legenda (pra legibilidade) que tambem fica acima desse
# limiar: isso e intencional, porque esse fundo tambem cobre visualmente o rosto por
# baixo, entao deve contar como colisao mesmo sem letra ali.
LIMIAR_ALPHA_OVERLAY = 120

# Sem overlay (fallback), pixel de cinza acima disso e candidato a "texto claro
# sobre fundo escuro", que e o padrao mais comum de legenda queimada nesses anuncios.
LIMIAR_BRILHO_SEM_OVERLAY = 225

# Luminancia minima pra um pixel opaco contar como TINTA de letra e nao como scrim.
# Ver comentario no loop principal: sem isso o degrade de fundo do lettering virava
# uma mancha gigante e reprovava quadro em que o texto esta claramente no peito.
LIMIAR_LUM_TINTA = 150

# Quanto encolher a caixa do Haar de cada lado pra chegar no nucleo do rosto.
INSET_NUCLEO = 0.12

# Por quantos segundos a ultima caixa de rosto conhecida continua valendo quando o
# detector nao acha nada. Existe porque o texto do CTA POR CIMA do rosto e justamente
# o que impede a deteccao (medido: com o CTA na boca, detectMultiScale devolve vazio;
# 1,5s antes, com a mesma cabeca no mesmo lugar, devolve a caixa). Sem essa heranca o
# gate tem ponto cego no pior caso. O apresentador nao sai do quadro nesse intervalo.
JANELA_HERANCA_ROSTO_S = 4.5

# Pele minima dentro da caixa herdada pra aceitar que o apresentador continua ali.
# Sem isso a heranca acusa legenda em cima de "rosto" num insert em tela cheia.
PELE_MIN_HERANCA = 0.12

# Altura do painel de cima na tela dividida (espelha VAM_SPLIT_TOP_H do motor).
# Durante um split o apresentador mora SO na metade de baixo.
SPLIT_TOP_H = int(os.environ.get("VAM_SPLIT_TOP_H", "1150"))


def carregar_janelas_split(caminho, accel, a0=0.0):
    """Janelas (inicio, fim) em que o anuncio esta em TELA DIVIDIDA.

    Vem do plano de ritmo que o proprio build gerou, convertido pro tempo do arquivo
    entregue (o plano fala em tempo de footage 1x; a entrega roda acelerada).

    Existe por causa de um falso positivo medido em 27/08/2026 no jh13: a ultima
    deteccao real de rosto foi em t=40,5s, com o apresentador em TELA CHEIA e a caixa
    em y577-1277. Em 43,5s o plano ja era split, o rosto tinha descido pro painel de
    baixo, e a caixa HERDADA ficou pousada em cima de uma ampulheta de areia ambar no
    painel de cima. Areia quente tem 0,516 de pele pelo criterio YCrCb: passou no filtro
    de pele com folga, e o gate reprovou o lettering por colidir com um relogio.

    Tentei separar por diferenca de imagem antes de chegar aqui e NAO SEPARA: dentro de
    um mesmo plano de avatar, com o punch mexendo o enquadramento, o MAE na caixa fica
    entre 39 e 66; no corte de layout fica entre 53 e 65. As faixas se sobrepoem.
    O que separa e o LAYOUT, e ele nao se adivinha da imagem: se pergunta ao plano.
    """
    if not caminho or not os.path.exists(caminho):
        return []
    with open(caminho, encoding="utf-8") as fh:
        dados = json.load(fh)
    segs = dados.get("segs", dados if isinstance(dados, list) else [])
    # O `a0` ENTRA AQUI TAMBEM (27/08/2026). Corrigi o alinhamento dos QUADROS e deixei
    # a conversao das JANELAS sem ele: setima vez no mesmo dia que emendo um lado e
    # esqueco o irmao. O composite faz `setpts=PTS-a0/TB`, entao plano = entregue*accel
    # + a0, e a volta e (plano - a0)/accel. Sem subtrair, cada janela fica 0,18s
    # adiantada, e o gate acusava colisao em t=10,5s e t=15,5s por achar que ainda
    # havia split quando ele ja tinha acabado 0,03s antes.
    return [((s["s"] - a0) / accel, (s["e"] - a0) / accel)
            for s in segs if s.get("layout") == "split"]


def em_split(t, janelas):
    return any(a <= t < b for a, b in janelas)


def fracao_pele(quadro_bgr, caixa):
    """Fracao de pixels com cor de pele dentro da caixa (YCrCb, faixa larga).

    Serve pra responder UMA pergunta: o apresentador ainda esta nesse pedaco da tela?
    Nao precisa achar o rosto, so dizer se ali tem gente ou se virou b-roll."""
    x, y, w, h = [int(v) for v in caixa]
    alt, lar = quadro_bgr.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(lar, x + w), min(alt, y + h)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    roi = quadro_bgr[y0:y1, x0:x1]
    ycc = cv2.cvtColor(roi, cv2.COLOR_BGR2YCrCb)
    Y, Cr, Cb = ycc[:, :, 0], ycc[:, :, 1], ycc[:, :, 2]
    pele = (Y > 50) & (Cr >= 133) & (Cr <= 180) & (Cb >= 77) & (Cb <= 127)
    return float(pele.mean())

# Tinta de letra e FINA: mesmo uma legenda inteira em cima da boca cobre poucos por
# cento da area do rosto. O limiar de 12% era inalcancavel e deixava passar o defeito
# (contraprova de 17/08: legenda queimada sobre a boca passou). Calibrado em 1.5%.

# Quantos pixels "de texto" uma linha horizontal do quadro precisa ter pra contar
# como "linha com texto". Baixo de proposito: queremos pegar ate a haste fina de
# uma letra isolada no topo ou embaixo de uma palavra, nao so o meio grosso dela.
DENSIDADE_MIN_LINHA = 3

# Tolerancia de linhas em branco entre duas faixas de texto pra ainda considerar
# a mesma regiao (evita fatiar uma palavra em 2 caixas por causa de 1 linha rala
# entre corpo e acento, por exemplo).
TOLERANCIA_GAP_LINHAS = 2

_CASCADE_ROSTO = None


def obter_cascade_rosto():
    """
    Carrega o Haar cascade uma unica vez (evita reparsear o XML a cada quadro).

    scaleFactor=1.1 e minNeighbors=5 foram escolhidos testando no proprio video
    de validacao (jh13v2_espuma_roxa_v2composite_9x16.mp4, closeup com luz roxa
    de estudio): equalizeHist do cinza PIOROU a deteccao aqui (a luz de set ja
    da contraste forte, e o equalize as vezes zerava o rosto detectado), e um
    scaleFactor mais agressivo (1.05) as vezes detectava um segundo "rosto" falso
    dentro de screenshot mostrado no insert (uma foto de pessoa na tela, por
    exemplo). minSize proporcional a largura do quadro filtra esses falsos
    positivos pequenos.
    """
    global _CASCADE_ROSTO
    if _CASCADE_ROSTO is None:
        caminho_xml = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        _CASCADE_ROSTO = cv2.CascadeClassifier(caminho_xml)
        if _CASCADE_ROSTO.empty():
            raise RuntimeError(f"Nao consegui carregar o Haar cascade em: {caminho_xml}")
    return _CASCADE_ROSTO


def rodar(cmd):
    """Roda comando externo (ffmpeg/ffprobe) e estoura erro com o stderr real se falhar."""
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(
            "Comando falhou: " + " ".join(cmd) + "\n" + resultado.stderr.strip()
        )
    return resultado.stdout


def obter_duracao_segundos(caminho_arquivo):
    """Duracao via ffprobe. Usamos format=duration (nao stream=duration) porque e
    o valor mais estavel entre containers diferentes (mp4 vs mov)."""
    saida = rodar([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        caminho_arquivo,
    ])
    return float(saida.strip())


def _fps_de(caminho_video):
    """Taxa de quadros real do arquivo, pra converter intervalo em passo de quadro."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=avg_frame_rate", "-of", "csv=p=0", caminho_video],
        capture_output=True, text=True)
    txt = (r.stdout or "").strip()
    if "/" in txt:
        num, den = txt.split("/")
        if float(den):
            return float(num) / float(den)
    try:
        return float(txt)
    except ValueError:
        return 30.0


def _n_quadros(caminho, fps):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-count_frames", "-show_entries", "stream=nb_read_frames",
                        "-of", "csv=p=0", caminho], capture_output=True, text=True)
    try:
        return int(r.stdout.strip().split(",")[0])
    except Exception:
        d = obter_duracao_segundos(caminho)
        return int(d * fps) if d else 0


def extrair_quadros(caminho_video, intervalo, pasta_saida, com_alpha=False,
                    desloc=0.0):
    """
    Extrai o quadro mais proximo de cada alvo `desloc + k*intervalo`, um ffmpeg por
    alvo, com seek em duas etapas (grosso antes do -i, fino depois) pra nao decodificar
    do zero a cada chamada. Mais lento que um filtro de passada unica, mas o rotulo de
    cada PNG e o quadro de verdade, nao uma promessa de filtro (ver comentario abaixo:
    tres tentativas de fazer isso numa passada so saíram erradas, cada uma de um jeito
    diferente, e so a medicao pegou).
    """
    # `desloc` existe porque o composite aplica `setpts=PTS-a0/TB` e o overlay comeca
    # a0 segundos depois da footage. Sem somar isso, os dois arrays ficam pareados por
    # indice e desencontrados no tempo.
    #
    # TRES TENTATIVAS ANTERIORES, TODAS ERRADAS, E A MEDICAO PEGOU TODAS (27/08/2026):
    #   `select='not(mod(n,passo))'` com passo inteiro acumula deriva quando
    #      intervalo*fps nao e inteiro (0,6667s por amostra em vez de 0,675s, 1,5s de
    #      erro no fim de 90s);
    #   `select` enumerando os alvos estoura o parser acima de ~160 termos, e por
    #      expressao ele PULA alvo quando nenhum quadro cai dentro de meio quadro do
    #      alvo, o que desloca o indice e reportou colisao aos 45s num clipe de 40s;
    #   `fps` com `start_time` (a versao anterior desta funcao) parecia certa "por
    #      construcao", mas o diretor de arte MEDIU um desvio sistematico de +0,067 a
    #      +0,10s comparando o PNG extraido contra os quadros reais vizinhos por
    #      diferenca de pixel (MAE=0 no quadro errado, nao no rotulado). O filtro `fps`
    #      nao entrega o quadro mais proximo do ROTULO que a documentacao dele sugere;
    #      documentar "por construcao" sem essa prova foi o erro.
    # Comentario velho: "o rotulo passa a valer por construcao". Nao passava, e so
    # descobri porque alguem MEDIU em vez de confiar no nome do parametro do ffmpeg.
    #
    # Aqui: um seek POR ALVO, em duas etapas (seek grosso ANTES do -i, ate a
    # keyframe mais proxima, decodificacao fina DEPOIS do -i ate o quadro exato). E
    # mais lento que uma passada so, mas o rotulo passa a ser o quadro de verdade,
    # nao por promessa de filtro: e o mesmo metodo que a prova de alinhamento (tarja
    # desenhada num instante conhecido) usa pra conferir, entao os dois lados batem
    # pela mesma medida.
    fps = _fps_de(caminho_video)
    dur = obter_duracao_segundos(caminho_video) or 0.0
    meio = (0.5 / fps) if fps else 0.02
    alvos = []
    k = 0
    while True:
        t = desloc + k * intervalo
        if dur and t >= dur - meio:
            break
        if t >= 0:
            alvos.append(t)
        k += 1
        if k > 200000:
            break

    def _extrair_um(par):
        idx, t = par
        destino = os.path.join(pasta_saida, f"q_{idx:06d}.png")
        grosso = max(0.0, t - 6.0)
        fino = t - grosso
        cmd = ["ffmpeg", "-y", "-loglevel", "error",
               "-ss", f"{grosso:.6f}", "-i", caminho_video,
               "-ss", f"{fino:.6f}", "-frames:v", "1"]
        if com_alpha:
            # Forca 4 canais na saida. O PNG final sempre tem RGBA (padrao do
            # formato); isso garante que o ffmpeg nao descarte o alpha antes do encoder.
            cmd += ["-pix_fmt", "rgba"]
        cmd += [destino]
        rodar(cmd)

    # UM SEEK POR ALVO GASTA ~0,5 a 0,6s DE OVERHEAD DE PROCESSO, quase todo ele spawn
    # do ffmpeg e nao decodificacao (medido: seek de 0s a 6s deu o mesmo tempo que
    # seek de 0s). Pra um video de 90s a 0,25s isso e 360 processos so no video, outros
    # tantos no overlay: minutos de build so no gate.
    # PARALELIZAR EM VEZ DE AGRUPAR NUM SO ffmpeg: uma tentativa de agrupar varios
    # alvos num select() so ficou rapida mas reintroduziu risco (quantos quadros o
    # `between()` casa por alvo nao e garantido 1-pra-1, e um alvo perdido no meio do
    # lote desalinha todos os indices depois dele). Cada extracao aqui e independente
    # e correta por construcao (o mesmo metodo que a prova de alinhamento usa); rodar
    # varias ao mesmo tempo custa so I/O de processo, que o SO paraleliza de graca.
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(_extrair_um, enumerate(alvos)))
    return sorted(glob.glob(os.path.join(pasta_saida, "q_*.png")))


def detectar_rostos(quadro_bgr):
    """Retorna lista de (x, y, w, h) dos rostos encontrados no quadro. Lista vazia
    e normal e esperado em quadros de insert puro (sem apresentador na tela)."""
    cinza = cv2.cvtColor(quadro_bgr, cv2.COLOR_BGR2GRAY)
    altura, largura = cinza.shape[:2]
    # Rosto minimo = 12% da largura do quadro. Nesses anuncios o apresentador
    # fala em closeup ocupando boa parte do frame vertical, entao um rosto
    # "de verdade" nunca e menor que isso; qualquer coisa menor detectada e
    # muito mais provavel de ser ruido ou um rostinho dentro de screenshot.
    # 12% (129px) deixava passar padrao de 133px no canto escuro do cenario, e o gate
    # media o hook contra ele (falso positivo de 60,4% no jh15). O apresentador foi
    # medido entre 528 e 713px de largura em toda a leva, entao 20% separa com folga.
    tam_min = max(1, int(largura * 0.20))
    rostos = obter_cascade_rosto().detectMultiScale(
        cinza, scaleFactor=1.1, minNeighbors=5, minSize=(tam_min, tam_min)
    )
    return list(rostos)


def _agrupar_linhas_em_caixas(mascara_binaria, tolerancia_gap=TOLERANCIA_GAP_LINHAS):
    """
    Recebe uma mascara booleana (altura x largura) de pixels de texto e devolve
    uma lista de caixas (x0, y0, x1, y1), uma por FAIXA HORIZONTAL contigua de
    texto (permitindo pequenos vazios de ate `tolerancia_gap` linhas dentro da
    mesma faixa).

    Agrupar por linha (e nao por blob/contorno) e de proposito: a legenda e o
    CTA desses anuncios sempre aparecem como faixas horizontais (uma ou mais
    linhas de texto, as vezes com fundo atras). Ir por linha e robusto tanto
    pro texto solto quanto pro texto com fundo semi-transparente atras.
    """
    contagem_por_linha = mascara_binaria.sum(axis=1)
    linha_tem_texto = contagem_por_linha >= DENSIDADE_MIN_LINHA

    altura = len(linha_tem_texto)
    faixas = []
    inicio = None
    linhas_vazias_seguidas = 0

    for y in range(altura):
        if linha_tem_texto[y]:
            if inicio is None:
                inicio = y
            linhas_vazias_seguidas = 0
        elif inicio is not None:
            linhas_vazias_seguidas += 1
            if linhas_vazias_seguidas > tolerancia_gap:
                fim = y - linhas_vazias_seguidas
                faixas.append((inicio, fim))
                inicio = None
                linhas_vazias_seguidas = 0

    if inicio is not None:
        faixas.append((inicio, altura - 1 - linhas_vazias_seguidas))

    caixas = []
    for y0, y1 in faixas:
        if y1 < y0:
            continue
        fatia = mascara_binaria[y0:y1 + 1, :]
        colunas_com_texto = np.where(fatia.any(axis=0))[0]
        if len(colunas_com_texto) == 0:
            continue
        x0, x1 = int(colunas_com_texto.min()), int(colunas_com_texto.max())
        caixas.append((x0, y0, x1, y1))
    return caixas


def regioes_texto_por_alpha(quadro_overlay_bgra):
    """
    Overlay .mov: canal alpha onde SO o nosso texto/CTA e opaco, resto e
    transparente. alpha e sempre o ultimo canal do array, tanto em ordenacao
    BGRA quanto RGBA, entao nao importa qual das duas o OpenCV decidiu usar
    ao ler o PNG: quadro[:, :, 3] e sempre o alpha.
    """
    alpha = quadro_overlay_bgra[:, :, 3]
    mascara = alpha > LIMIAR_ALPHA_OVERLAY
    return _agrupar_linhas_em_caixas(mascara)


def regioes_texto_por_brilho(quadro_bgr):
    """
    Fallback sem overlay: aproxima "texto" por pixel bem claro (legenda branca
    com contorno escuro e o padrao mais comum). Mais fraco que o metodo com
    overlay: uma tela de insert clara (print de site, por exemplo) tambem
    acende esse limiar e pode virar falso positivo. Preferir sempre --overlay
    quando o .mov estiver disponivel.
    """
    cinza = cv2.cvtColor(quadro_bgr, cv2.COLOR_BGR2GRAY)
    mascara = cinza > LIMIAR_BRILHO_SEM_OVERLAY
    return _agrupar_linhas_em_caixas(mascara)


def cobertura_por_mascara(rosto, mascara):
    """% do rosto coberta pela MASCARA real de texto, nao pela caixa envolvente.

    Por que trocar: a caixa envolvente de uma faixa horizontal vai da primeira ate a
    ultima coluna com tinta, entao um lettering de duas linhas no PEITO do apresentador
    virava um retangulo enorme que encostava na caixa do rosto. Foi assim que o gate
    reprovou o quadro de 67,5s do jh13 dizendo "43% do rosto coberto", quando na imagem
    o texto esta claramente abaixo do queixo (conferido a olho). Falso positivo mata
    gate: se ele grita no lugar errado, a gente aprende a ignorar.

    Contando os pixels de tinta DENTRO do retangulo do rosto, texto ao lado ou abaixo
    nao pontua. O scrim do overlay entra na conta de proposito: faixa escura em cima da
    boca atrapalha tanto quanto a letra.
    """
    fx, fy, fw, fh = rosto
    # NUCLEO: a caixa do Haar sobra pra fora do rosto (pega cabelo em cima e pescoco
    # embaixo). Medir no miolo, onde moram olhos, nariz e boca, e o que corresponde ao
    # que o olho chama de "texto na cara dele". Sem isso, lettering no PEITO reprovava.
    dx, dy = int(fw * INSET_NUCLEO), int(fh * INSET_NUCLEO)
    fx, fy, fw, fh = fx + dx, fy + dy, fw - 2 * dx, fh - 2 * dy
    fh = int(fh * 0.78)   # queixo fora da conta; ver nota na outra funcao
    area_rosto = fw * fh
    if area_rosto <= 0:
        return 0.0, None
    h, w = mascara.shape[:2]
    x0, y0 = max(0, fx), max(0, fy)
    x1, y1 = min(w, fx + fw), min(h, fy + fh)
    if x1 <= x0 or y1 <= y0:
        return 0.0, None
    dentro = mascara[y0:y1, x0:x1]
    area_coberta = int(dentro.sum())
    linhas = np.where(dentro.any(axis=1))[0]
    faixa = [int(y0 + linhas.min()), int(y0 + linhas.max())] if len(linhas) else None
    return 100.0 * area_coberta / area_rosto, faixa


def calcular_cobertura(rosto, caixas_texto):
    """
    % da area do rosto coberta por texto, e o intervalo [y_min, y_max] das
    faixas de texto que colidiram com esse rosto.

    As faixas vem de linhas horizontais disjuntas em Y (por construcao do
    agrupamento acima), entao somar a intersecao de cada faixa com o rosto
    e equivalente a unir as areas: nao ha risco de contar a mesma regiao
    duas vezes mesmo com varias faixas de texto no mesmo quadro (por exemplo,
    legenda em cima e CTA embaixo ao mesmo tempo).
    """
    fx, fy, fw, fh = rosto
    # QUEIXO FORA DA CONTA (31/08/2026, builds 44-45). A caixa do Haar desce ate o fim
    # da barba: rosto [y1260..1751] com legenda em y1405-1473 dava 7,6% "de rosto"
    # coberto num quadro em que a legenda esta no PEITO/queixo e le normal (conferido no
    # quadro). O defeito que criou este gate foi texto na BOCA; boca e olhos vivem nos
    # 78% de cima da caixa. O quarto de baixo (queixo/barba) sai da conta.
    fh = int(fh * 0.78)
    area_rosto = fw * fh
    if area_rosto <= 0:
        return 0.0, None

    area_coberta = 0
    y_min_total = None
    y_max_total = None

    for (x0, y0, x1, y1) in caixas_texto:
        ix0 = max(fx, x0)
        iy0 = max(fy, y0)
        ix1 = min(fx + fw, x1 + 1)
        iy1 = min(fy + fh, y1 + 1)
        if ix1 > ix0 and iy1 > iy0:
            area_coberta += (ix1 - ix0) * (iy1 - iy0)
            y_min_total = y0 if y_min_total is None else min(y_min_total, y0)
            y_max_total = y1 if y_max_total is None else max(y_max_total, y1)

    if y_min_total is None:
        return 0.0, None

    pct = 100.0 * area_coberta / area_rosto
    return pct, [int(y_min_total), int(y_max_total)]


def imprimir_legivel(resultado, intervalo, limiar):
    print(f"Video: {resultado['video']}")
    print(f"Amostras analisadas: {resultado['amostras']} (a cada {intervalo}s)")
    print(f"Limiar de reprovacao: texto cobrindo mais de {limiar}% da area do rosto")
    print()
    colisoes = resultado["colisoes"]
    if not colisoes:
        print("PASSA: nenhuma colisao de texto com rosto encontrada.")
        return
    print(f"REPROVA: {len(colisoes)} colisao(oes) encontrada(s):")
    for c in colisoes:
        print(
            f"  t={c['t']:.1f}s   texto cobre {c['pct_rosto_coberto']:.1f}% do rosto"
            f"   rosto={c['rosto']}   texto_y={c['texto_y']}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Gate de colisao entre texto (legenda/CTA) e rosto em video de anuncio 1080x1920."
    )
    parser.add_argument("video", help="Caminho do video final (mp4).")
    parser.add_argument("--overlay", default=None, help="Caminho do overlay .mov com canal alpha (so o nosso texto opaco).")
    parser.add_argument("--json", action="store_true", help="Imprime o resultado em JSON em vez de texto legivel.")
    parser.add_argument("--intervalo", type=float, default=INTERVALO_AMOSTRA_PADRAO, help="Segundos entre quadros amostrados (padrao 1.5).")
    parser.add_argument("--limiar", type=float, default=LIMIAR_COLISAO_PADRAO, help="Percentual de cobertura do rosto que reprova o gate (padrao 12).")
    parser.add_argument("--ritmo", default=None,
                        help="Plano de ritmo do build (JSON). Diz em que trechos o "
                             "anuncio esta em tela dividida, pra caixa de rosto herdada "
                             "nao ser medida no painel do insert.")
    parser.add_argument("--a0", type=float, default=0.0,
                        help="Deslocamento que o composite aplicou na footage "
                             "(setpts=PTS-a0/TB). Sem ele o overlay fica desencontrado.")
    parser.add_argument("--accel", type=float, default=1.0,
                        help="Aceleracao aplicada na entrega (o plano fala em tempo 1x).")
    args = parser.parse_args()

    if not os.path.isfile(args.video):
        print(f"Video nao encontrado: {args.video}", file=sys.stderr)
        sys.exit(2)
    if args.overlay and not os.path.isfile(args.overlay):
        print(f"Overlay nao encontrado: {args.overlay}", file=sys.stderr)
        sys.exit(2)

    duracao_video = obter_duracao_segundos(args.video)

    tempdir = tempfile.mkdtemp(prefix="gate_colisao_texto_")
    try:
        pasta_video = os.path.join(tempdir, "video")
        os.makedirs(pasta_video)
        quadros_video = extrair_quadros(args.video, args.intervalo, pasta_video, com_alpha=False)

        quadros_overlay = None
        if args.overlay:
            duracao_overlay = obter_duracao_segundos(args.overlay)
            # O overlay roda em velocidade diferente do video final (o final e
            # acelerado em relacao ao material usado pra gerar o overlay). Sem
            # corrigir isso, o texto do overlay no tempo t não bate com o que
            # aparece no video final no mesmo t. O fator escala o tempo do video
            # final pro tempo equivalente dentro do overlay.
            # A aceleracao do build e a fonte certa. A razao das duracoes so vale
            # quando o overlay NAO tem cauda a mais que o video; com folga de cauda ela
            # estica o mapeamento e o gate passa a comparar instantes diferentes.
            _accel = float(os.environ.get("VAM_ACCEL", "1.35"))
            fator = min(_accel, duracao_overlay / duracao_video)
            pasta_overlay = os.path.join(tempdir, "overlay")
            os.makedirs(pasta_overlay)
            # Amostrar o overlay num intervalo ja multiplicado pelo fator faz a
            # amostra de indice i do overlay cair exatamente em t_video(i) * fator,
            # entao os dois arrays de quadros ficam pareados pelo MESMO indice,
            # sem precisar calcular nem buscar timestamp por amostra.
            intervalo_overlay = args.intervalo * fator
            # O composite aplica `setpts=PTS-a0/TB` na footage: o instante t do arquivo
            # entregue corresponde a t*fator + a0 no overlay. Sem somar o a0 os dois
            # arrays ficam pareados por indice e desencontrados no tempo, e o gate
            # compara um quadro de video com uma legenda que nao e a daquele quadro.
            quadros_overlay = extrair_quadros(args.overlay, intervalo_overlay,
                                              pasta_overlay, com_alpha=True,
                                              desloc=args.a0)

        colisoes = []
        n_amostras = 0
        ultimo_rosto = None      # (t, caixa) do ultimo rosto REALMENTE detectado
        janelas_split = carregar_janelas_split(args.ritmo, args.accel, args.a0)
        if janelas_split:
            print(f"Trechos em tela dividida: {len(janelas_split)} "
                  f"(caixa herdada nao vale no painel de cima)")

        for i, caminho_quadro in enumerate(quadros_video):
            t = round(i * args.intervalo, 2)
            quadro = cv2.imread(caminho_quadro)
            if quadro is None:
                continue
            n_amostras += 1

            rostos = detectar_rostos(quadro)
            # ROSTO SEM PELE NAO E ROSTO (18/08/2026): o Haar devolveu uma "cara" de
            # 711px numa pagina roxa escura de b-roll (jh13 t=1,5s) e o gate mediu o
            # hook contra ela. O mesmo criterio de pele que valida a heranca vale pra
            # deteccao nova: caixa em que quase nao ha pixel de pele e padrao
            # geometrico do conteudo, nao gente nem foto de gente.
            rostos = [r for r in rostos
                      if fracao_pele(quadro, r) >= PELE_MIN_HERANCA]
            # PAINEL, TAMBEM PRA CAIXA DETECTADA (27/08/2026). O filtro de painel valia
            # so pra caixa HERDADA. Detectada no painel de CIMA durante um split e
            # conteudo do asset, nao o apresentador: o Haar acha "rosto" numa ampulheta
            # de areia (0,516 de pele) e em foto dentro de gravacao de tela, e a legenda
            # da costura mora exatamente naquela faixa por desenho. Sem isto o gate
            # acusava 44 colisoes, boa parte delas legenda legitima contra rosto que nao
            # existe, e gate barulhento e tao inutil quanto gate cego.
            # A legibilidade do conteudo do asset continua sendo defeito, mas ela se
            # audita no olho, nao neste gate (regra da casa: o asset manda no que
            # aparece; o que vale aqui e o rosto do apresentador).
            if em_split(t, janelas_split):
                rostos = [r for r in rostos if r[1] + r[3] / 2 >= SPLIT_TOP_H]
            herdado = False
            if rostos:
                maior = max(rostos, key=lambda r: r[2] * r[3])
                ultimo_rosto = (t, maior)
            elif (ultimo_rosto and t - ultimo_rosto[0] <= JANELA_HERANCA_ROSTO_S
                  and fracao_pele(quadro, ultimo_rosto[1]) >= PELE_MIN_HERANCA
                  # ...e a caixa velha tem que estar onde o apresentador PODE estar.
                  # Num trecho de tela dividida ele so existe abaixo da costura; caixa
                  # herdada de um plano de tela cheia fica no painel do insert e mede o
                  # texto contra o b-roll. So vale a heranca se o miolo da caixa cair no
                  # painel de baixo. Filtra a caixa HERDADA apenas: rosto detectado
                  # NESTE quadro continua valendo em qualquer painel (pode ser gente
                  # dentro do insert, e texto em cima dela tambem e defeito).
                  and not (em_split(t, janelas_split)
                           and ultimo_rosto[1][1] + ultimo_rosto[1][3] / 2
                               < SPLIT_TOP_H)):
                # Nao achou rosto, achou ha pouco, e ali AINDA tem pele: quase sempre e
                # o NOSSO texto tapando a cara e quebrando o detector. Mede contra a
                # ultima caixa. Se a pele sumiu, virou insert e nao ha o que colidir.
                rostos = [ultimo_rosto[1]]
                herdado = True
            if not rostos:
                # GEOMETRIA EM VEZ DE DETECTOR, DURANTE O SPLIT (27/08/2026).
                # O detector some justamente quando a colisao e grave: texto em cima da
                # cara quebra o Haar, entao quanto pior o defeito, mais certo o gate
                # aprovava. Medido no jh13: 1,27s sem NENHUMA deteccao (t=59,93 a
                # 61,20), com os vizinhos detectando em 100% das amostras, e era
                # exatamente a janela em que a lista "ENQUANTO ISSO" cobria 9,2% a 13,1%
                # do rosto. O gate voltou dizendo "nenhuma ocorrencia".
                #
                # A primeira tentativa foi herdar a ultima caixa e medir texto nela.
                # Nao serve por dois motivos que a medicao mostrou: deu 77 falsos
                # positivos (caixa herdada de um plano de avatar pousada em cima de
                # insert, onde nao ha ninguem) e AINDA perdeu a janela real, porque a
                # caixa vinha de um quadro de tela cheia e o rosto ja tinha descido.
                # Gate barulhento e tao inutil quanto gate cego.
                #
                # Num SPLIT nao ha o que detectar: o apresentador ocupa o painel de
                # baixo por construcao. Entao tinta clara ali dentro e colisao, medida
                # por geometria, sem depender de o Haar estar enxergando.
                if (em_split(t, janelas_split) and quadros_overlay is not None
                        and i < len(quadros_overlay)):
                    _qo = cv2.imread(quadros_overlay[i], cv2.IMREAD_UNCHANGED)
                    if _qo is not None and _qo.ndim >= 3 and _qo.shape[2] >= 4:
                        # a faixa da costura e legitima; o resto do painel, nao
                        _y0 = SPLIT_TOP_H + 120
                        _pn = _qo[_y0:, :, :]
                        _tinta = ((_pn[:, :, 3] > LIMIAR_ALPHA_OVERLAY)
                                  & (_pn[:, :, :3].max(axis=2) > LIMIAR_LUM_TINTA))
                        _pct = 100.0 * float(_tinta.mean())
                        if _pct > args.limiar:
                            colisoes.append({
                                "t": t,
                                "pct_rosto_coberto": round(_pct, 1),
                                "rosto": [0, _y0, 1080, 1920 - _y0],
                                "texto_y": [int(np.where(_tinta.any(axis=1))[0].min()) + _y0,
                                            int(np.where(_tinta.any(axis=1))[0].max()) + _y0],
                                "rosto_herdado": False,
                                "painel_do_apresentador": True})
                            continue
                # Quadro de insert puro (sem apresentador na tela) ou passou da janela
                # de heranca: nao ha com o que colidir.
                continue

            if quadros_overlay is not None:
                if i >= len(quadros_overlay):
                    # Cauda do video sem quadro de overlay correspondente (pode
                    # acontecer por arredondamento de duracao entre os dois
                    # arquivos). Sem dado de texto, nao da pra afirmar colisao.
                    continue
                quadro_overlay = cv2.imread(quadros_overlay[i], cv2.IMREAD_UNCHANGED)
                if quadro_overlay is None or quadro_overlay.ndim < 3 or quadro_overlay.shape[2] < 4:
                    continue
                # TINTA, nao scrim (calibrado 17/08/2026 olhando o quadro com a
                # mascara desenhada): so o alpha marcava tambem o degrade radial
                # atras do lettering, um oval enorme que fica ABAIXO do queixo. Isso
                # reprovava quadro bom. A letra e clara e opaca; o scrim e opaco e
                # ESCURO. Exigir os dois deixa a medida igual ao que o olho chama de
                # "texto em cima do rosto".
                _a = quadro_overlay[:, :, 3] > LIMIAR_ALPHA_OVERLAY
                _lum = quadro_overlay[:, :, :3].max(axis=2) > LIMIAR_LUM_TINTA
                mascara_texto = _a & _lum
            else:
                cinza = cv2.cvtColor(quadro, cv2.COLOR_BGR2GRAY)
                mascara_texto = cinza > LIMIAR_BRILHO_SEM_OVERLAY

            if not mascara_texto.any():
                continue

            for rosto in rostos:
                # ROSTO CRIADO PELO PROPRIO TEXTO NAO CONTA (18/08/2026): o Haar
                # detectou o hook "COM CARA DE I.A [emoji de palhaco]" como um rosto
                # de 711px e o gate reprovou o texto por colidir consigo mesmo. O
                # criterio: APAGAR a tinta do overlay (inpaint) dentro da caixa e
                # re-detectar. Rosto de verdade (apresentador ou foto no insert)
                # sobrevive sem o texto; rosto que so existe por causa do desenho do
                # texto e artefato e sai da medida.
                # ...MAS a guarda so vale pra rosto DETECTADO NESTE quadro. Numa caixa
                # HERDADA ela se anula com a heranca e cria um ponto cego (26/08/2026):
                # a heranca existe justamente porque o Haar falhou aqui, quase sempre
                # por causa do nosso texto tapando a cara. A guarda entao apaga o texto,
                # re-detecta, nao acha (a oclusao continua grande demais) e DESCARTA a
                # colisao. Resultado: o defeito apaga o sinal que o gate usa pra ve-lo.
                # Foi assim que o jh13 passou com o lettering "SEM PAGAR HOSPEDAGEM" em
                # cima do nariz e da boca do apresentador em t=40,5s, medido depois na mao:
                # glifos em y1582-1796 dentro do rosto em y1296-1829.
                # A caixa herdada ja passou por dois filtros (veio de um quadro com rosto
                # de verdade + tem pele suficiente agora), entao nao precisa deste.
                if quadros_overlay is not None and not herdado:
                    _x, _y, _w, _h = [int(v) for v in rosto]
                    _mk = (quadro_overlay[_y:_y+_h, _x:_x+_w, 3]
                           > LIMIAR_ALPHA_OVERLAY).astype(np.uint8) * 255
                    if _mk.size and _mk.mean() > 2:
                        _roi = cv2.inpaint(quadro[_y:_y+_h, _x:_x+_w],
                                           _mk, 5, cv2.INPAINT_TELEA)
                        _cz = cv2.cvtColor(_roi, cv2.COLOR_BGR2GRAY)
                        _min = max(24, int(min(_w, _h) * 0.7))
                        _sem_texto = obter_cascade_rosto().detectMultiScale(
                            _cz, scaleFactor=1.1, minNeighbors=4,
                            minSize=(_min, _min))
                        if len(_sem_texto) == 0:
                            continue
                # mascara real, nao caixa envolvente: ver cobertura_por_mascara()
                pct, texto_y = cobertura_por_mascara(rosto, mascara_texto)
                if pct > args.limiar:
                    colisoes.append({
                        "t": t,
                        "pct_rosto_coberto": round(pct, 1),
                        "rosto": [int(v) for v in rosto],
                        "texto_y": texto_y,
                        "rosto_herdado": herdado,
                    })

        veredito = "REPROVA" if colisoes else "PASSA"
        resultado = {
            "video": args.video,
            "amostras": n_amostras,
            "colisoes": colisoes,
            "veredito": veredito,
        }

        if args.json:
            print(json.dumps(resultado, ensure_ascii=False, indent=2))
        else:
            imprimir_legivel(resultado, args.intervalo, args.limiar)

        sys.exit(1 if colisoes else 0)
    finally:
        # Limpa os PNGs extraidos mesmo se algo estourar no meio do caminho.
        shutil.rmtree(tempdir, ignore_errors=True)


if __name__ == "__main__":
    main()
