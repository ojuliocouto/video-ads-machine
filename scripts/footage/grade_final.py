"""Grade final da footage: ruído, contraste, saturação, vinheta e as tags de cor bt709.

Um ffmpeg só, sobre a cadeia pronta: reanexa o áudio CONTÍNUO do avatar (mantém o lip-sync, zero
deriva) e grava `<saida>.mp4`.

## Por que as tags bt709 e por que dentro do filtro

Sem `colorspace=all=bt709:iall=bt709:fast=1` no FIM da cadeia, o libx264 marca a saída como
bt2020nc/arib-std-b67 (HDR/HLG) mesmo com o conteúdo SDR normal. As flags `-color_primaries` e
`-color_trc` de saída sozinhas NÃO bastam (testado): só o filtro escreve a VUI certa no bitstream. O
`fast=1` só re-marca a tag (a fonte JÁ é bt709, só estava sem tag), sem conversão de pixel. Player
que respeita a tag (WhatsApp, iPhone) decodifica com a curva errada e o vídeo sai avermelhado e quente.

## A grade vem do `cinema.grade` (W4.C)

O filtro não mora mais aqui: é pedido ao `cinema.grade` pelo nome do preset (`estilo.grade` do
projeto.json). Sem preset vale o PADRÃO, `quente-suave`, que é a grade que o motor sempre aplicou
(grão 7, contraste 1,03, saturação 0,97, vinheta PI/5,5) e gera a MESMA string de antes: a paridade
com a fixture do dono continua caractere a caractere. As tags bt709 fecham a cadeia de todo preset.
`FILTRO_GRADE` fica como o filtro do preset padrão, por compatibilidade.
"""
from cinema import grade

from .cadeia import run

FILTRO_GRADE = grade.filtro(grade.PADRAO)


def cmd_grade_final(vchain, a0, total, avatar, out, preset=None):
    """Comando do mux final. `a0` é o início do 1º span no avatar e `total - a0` a janela de áudio
    (a soma das durações dos spans). `preset` é o nome do preset de grade (`None` = padrão);
    nome desconhecido levanta `cinema.grade.GradeDesconhecida` antes de qualquer ffmpeg."""
    audlen = total - a0
    return ["ffmpeg", "-y", "-i", vchain, "-ss", str(a0), "-t", str(audlen), "-i", avatar,
            "-filter_complex", grade.filtro(preset),
            "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
            "-c:a", "aac", "-shortest", out]


def aplicar(vchain, a0, total, avatar, out, preset=None):
    """Roda a grade final e devolve o caminho de saída. `preset`: ver `cmd_grade_final`."""
    run(cmd_grade_final(vchain, a0, total, avatar, out, preset))
    return out
