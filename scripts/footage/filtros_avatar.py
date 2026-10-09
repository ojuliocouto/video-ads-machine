"""Filtros do avatar: o plano de apresentador (zoom alternado) e o painel de baixo do split.

É também o dono do canvas e da base de tempo da footage (`W`, `H`, `FPS`, `nframes`, `cap`),
porque todo outro módulo de filtro parte deles. Nada aqui executa ffmpeg: as funções devolvem
strings e listas de argumentos, e quem roda é `render_segmentos`.

## O zoom alterna de sentido a cada bloco

Antes todo bloco empurrava a imagem pra dentro na mesma velocidade, e a cada corte ela "voltava"
ao mesmo tamanho e recomeçava igual: o olho lia como parado. Alternando, cada corte muda de
direção e o plano respira. A amplitude (16%) é percorrida ao longo do bloco INTEIRO, amarrada ao
número de quadros: com 8% e passo fixo por quadro, um bloco de 11 s dava menos de 1% por segundo
e ninguém via o movimento.

## Escala base por sub-plano

Subdividir o bloco não criava corte visível: a imagem seguia contínua e só a direção do zoom
mudava. Com base diferente (1,00 / 1,14 / 1,28) o tamanho da cabeça muda DE UMA VEZ entre um plano
e o outro, que é o jump cut de reel, e não precisa de asset nenhum.

## Punch e respiro (W4.A, capacidade C3)

O zoom contínuo acima é o piso da câmera. Em cima dele a timeline pode pedir o PUNCH de ênfase (1,00 a
1,22 em 0,28 s na KEY, segura até 2,4 s, volta seca em 2 quadros) e o RESPIRO da entrada de etapa
(1,10 a 1,00 em 1 s). Eles entram como `punches=` (eventos de `cinema/camera`, com `t` RELATIVO ao início do
plano) e MULTIPLICAM o zoom do plano: z = zoom_do_plano x fator. Relativo, o rosto cresce 22% sobre o que
já está na tela, qualquer que seja a base do plano; absoluto, um plano com base 1,14 (até 1,30) recuaria.

Capacidade NOVA e opt-in: sem `punches` (ou com nenhum que comece dentro do plano) a expressão é a de
sempre, byte a byte, e o cache dos segmentos já renderizados continua valendo. Quem passa `punches` precisa
colocá-los na chave de cache do segmento (`cache_segmento.chave_segmento`), senão um plano em cache sem punch
seria reaproveitado onde agora há um.

## Painel de baixo do split

O rosto do apresentador ocupa y 330 a y 980 na fonte 1080x1920. O painel recorta a fonte em
largura cheia (antes reduzia a pessoa e deixava duas tarjas escuras nas laterais, com ela
parecendo uma coluna no meio da tela). O corte vertical é MEDIDO por `enquadramento` (perfil de
luminância do próprio avatar): cada look tem um enquadramento e uma constante fixa erra sempre em
algum. `VAM_SPLIT_BIAS` existe só como exceção digitada.
"""
import os

from cinema import camera as _camera

W, H, FPS = 1080, 1920, 30
REFRAME = "scale=2376:4224:force_original_aspect_ratio=increase,crop=2160:3840:108:652"
AMPL = 0.16

# Geometria do split 60/40. O painel de cima é DOMINANTE (cerca de 60% do quadro, a faixa medida
# nas referências); estava em 980 (51%) e o split parecia meio a meio. Env por leva, sem editar
# código. SPLIT_BOT_H deriva do topo: estava digitado duas vezes e dessincronizava.
SPLIT_TOP_H = int(os.environ.get("VAM_SPLIT_TOP_H", "1150"))
SPLIT_BOT_H = H - SPLIT_TOP_H
# Altura do degradê escuro na emenda dos painéis: sempre degradê, nunca linha dura.
SPLIT_GRAD = int(os.environ.get("VAM_SPLIT_GRAD", "90"))
SPLIT_AV_SRC = (0, 100, 1080, 1600)      # janela do avatar (x, y, w, h): cabeça, peito e microfone


def nframes(d):
    """Quadros de uma duração, nunca zero."""
    return max(1, round(d * FPS))


def cap(N):
    """Trecho de filtro que corta o segmento em exatamente N quadros."""
    return f"trim=end_frame={N},setpts=N/{FPS}/TB"


# ------------------------------------------------------------------ plano de apresentador

def expr_zoom(N, idx, base=1.0, punches=None):
    """Expressão do zoom: par empurra pra dentro, ímpar puxa pra fora. `base + AMPL` é feito em
    float de propósito (1,14 + 0,16 dá 1.2999999999999998) para o texto sair igual ao do motor
    antigo e o cache e a paridade não verem diferença.

    `punches` (opcional): eventos de punch/respiro de `cinema/camera` com `t` relativo ao início do
    plano. Os que começam antes do fim do plano multiplicam o zoom; sem nenhum, a string é a de sempre."""
    fim = max(N - 1, 1)
    if idx % 2 == 0:
        z = f"{base}+{AMPL}*on/{fim}"
    else:
        z = f"{base + AMPL}-{AMPL}*on/{fim}"
    eventos = _camera.eventos_no_plano(punches, N / FPS)
    if not eventos:
        return z
    return f"({z})*({_camera.expr_fator(eventos, FPS)})"


def filtro_orig(N, idx=0, base=1.0, punches=None):
    z = expr_zoom(N, idx, base, punches)
    return (f"fps={FPS},{REFRAME},"
            f"zoompan=z='{z}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H},setsar=1,{cap(N)}")


def cmd_orig(avatar, s, e, out, idx=0, base=1.0, punches=None):
    """Comando completo do ffmpeg para um bloco de apresentador (`e` já inclui o handle)."""
    d = e - s
    N = nframes(e - s)
    return ["ffmpeg", "-y", "-ss", str(s), "-t", str(d + 0.4), "-i", avatar,
            "-vf", filtro_orig(N, idx, base, punches), "-r", str(FPS),
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", out]


# ------------------------------------------------------------------ painel de baixo do split

def altura_util_split(src=None):
    """Altura da janela do avatar depois de levada à largura cheia, em número par."""
    _x, _y, w, h = src or SPLIT_AV_SRC
    escala = W / w
    return int(h * escala) // 2 * 2


def corte_y_split(bias, alt_util, bot_h=None):
    """Início do recorte vertical: `bias` da altura útil, limitado ao que sobra pra caber o painel."""
    bot_h = SPLIT_BOT_H if bot_h is None else bot_h
    return max(0, min(int(alt_util * bias), alt_util - bot_h)) // 2 * 2


def filtro_avatar_split(bias, *, bot_h=None):
    """Filtro `[1:v]...[bot];` do painel de baixo do split, com o corte já decidido por `bias`."""
    bot_h = SPLIT_BOT_H if bot_h is None else bot_h
    x, y, w, h = SPLIT_AV_SRC
    alt_util = altura_util_split()
    corte_y = corte_y_split(bias, alt_util, bot_h)
    return (f"[1:v]crop={w}:{h}:{x}:{y},scale={W}:{alt_util},"
            f"crop={W}:{bot_h}:0:{corte_y},setsar=1[bot];")
