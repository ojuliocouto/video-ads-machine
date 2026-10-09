"""Grade de cor (C5): os 4 presets como filtros de ffmpeg determinísticos.

Quem pede o filtro é o `footage/grade_final`. Aqui só mora a receita de cada preset e a escolha
pelo nome. Nada roda ffmpeg e nada lê relógio, aleatório ou disco: a mesma chamada devolve a mesma
string, e a string é o que a paridade com o dono compara caractere a caractere.

## Os presets

  quente-suave  O PADRÃO e a grade que o motor sempre aplicou: grão 7, contraste 1,03, saturação
                0,97, vinheta PI/5,5. A string é IDÊNTICA à de antes da W4.C (a fixture de
                paridade depende disso). A camada quente do template (CSS) continua no overlay.
  natural       Quase neutra, sem empurrar a cor: grão leve (5), contraste 1,01, saturação 1,0,
                vinheta mais fraca (PI/4).
  frio-teal     Tira vermelho e põe azul nas sombras, nos meios e nas altas (`colorbalance`),
                contraste 1,04, saturação 0,95, vinheta um pouco mais forte (PI/6).
  pb            Preto e branco: `hue=s=0`, contraste leve 1,08, vinheta PI/6.

As intenções vêm dos CSS do caminho antigo (`presets/grade/*.css`): natural, frio-teal e pb só
mudam quando o projeto os escolhe (`estilo.grade` do projeto.json).

## Vinheta

No `vignette` do ffmpeg o ângulo MENOR escurece mais as bordas. Por isso a natural (a mais leve)
usa PI/4 e a quente-suave (a de referência) PI/5,5.

## As tags bt709

Toda cadeia fecha com `colorspace=all=bt709:iall=bt709:fast=1`, que NÃO sai do preset: é anexada
aqui, para que nenhum preset, atual ou futuro, esqueça. Sem ele o libx264 marca a saída como
bt2020nc/arib-std-b67 (HDR/HLG) e o WhatsApp e o iPhone decodificam avermelhado. Detalhe em
`footage/grade_final.py`; quem confere no arquivo entregue é o `gates/gate_cor.py`.
"""

PADRAO = "quente-suave"

TAG_BT709 = "colorspace=all=bt709:iall=bt709:fast=1"

# Ordem = ordem do mostruário. Cada preset é a lista de filtros ANTES da tag bt709.
_PRESETS = (
    ("quente-suave", (
        "noise=alls=7:allf=t+u",
        "eq=contrast=1.03:saturation=0.97",
        "vignette=PI/5.5",
    ), "Quente e suave: a grade do motor (grão 7, contraste 1,03, saturação 0,97). O padrão."),
    ("natural", (
        "noise=alls=5:allf=t+u",
        "eq=contrast=1.01:saturation=1.0",
        "vignette=PI/4",
    ), "Natural: quase neutra, sem empurrar a cor, grão leve e vinheta fraca."),
    ("frio-teal", (
        "noise=alls=7:allf=t+u",
        "eq=contrast=1.04:saturation=0.95",
        "colorbalance=rs=-0.05:bs=0.06:rm=-0.04:bm=0.05:rh=-0.03:bh=0.04",
        "vignette=PI/6",
    ), "Frio teal: menos vermelho e mais azul em sombras, meios e altas; vinheta mais forte."),
    ("pb", (
        "noise=alls=7:allf=t+u",
        "hue=s=0",
        "eq=contrast=1.08",
        "vignette=PI/6",
    ), "Preto e branco: sem cor, contraste leve e vinheta mais forte, clima editorial."),
)

_RECEITA = {nome: partes for nome, partes, _ in _PRESETS}
_DESCRICAO = {nome: desc for nome, _, desc in _PRESETS}


class GradeDesconhecida(ValueError):
    """O nome do preset não existe. A mensagem lista os que existem."""


def nomes():
    """Os presets, na ordem do mostruário."""
    return tuple(nome for nome, _, _ in _PRESETS)


def validar(nome):
    """Devolve o nome do preset (`None` vira o padrão). GradeDesconhecida se não existe."""
    if nome is None:
        return PADRAO
    if nome not in _RECEITA:
        raise GradeDesconhecida("preset de grade desconhecido: %r (os que existem: %s)"
                                % (nome, ", ".join(nomes())))
    return nome


def descricao(nome=None):
    """Uma linha em português sobre o preset, para o mostruário e para o aluno escolher."""
    return _DESCRICAO[validar(nome)]


def cadeia(preset=None):
    """A cadeia do preset SEM rótulos, fechando com a tag bt709. Serve para `-vf`."""
    return ",".join(_RECEITA[validar(preset)] + (TAG_BT709,))


def filtro(preset=None):
    """O filtro do preset para `-filter_complex`: entrada `[0:v]`, saída `[v]`."""
    return "[0:v]" + cadeia(preset) + "[v]"


def do_projeto(projeto):
    """O preset que o projeto escolheu (`estilo.grade` do projeto.json), ou o padrão.
    GradeDesconhecida se o nome escolhido não existe: o contrato só confere o formato do slug."""
    return validar((projeto.get("estilo") or {}).get("grade"))
