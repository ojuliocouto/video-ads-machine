"""Música de fundo com ducking por AUTOMAÇÃO de volume (C10).

A cama respira com a voz: parada e baixa sob a fala, sobe nas pausas REAIS e volta. Nunca por
compressor, nunca por buraco da transcrição.

    trilha do aluno nivelada a -20 dBFS de média (a saída de cada música varia por geração)
    cama em 0,055 sob a fala  ->  0,42 nas pausas reais do envelope  (salto de +17,7 dB)
    rampa de 150 ms para subir e para descer
    fade de entrada de 1,2 s e de saída de 2,2 s
    sem pausa real: a cama fica PARADA em 0,055

Origem dos números: a esteira de VSL (compor_final.py, ducking por automação, medido em 15/09/2026).
A pausa NÃO é redefinida aqui: vem de `audio.pausas_reais` (mediana da voz menos 12 dB por 0,5 s ou
mais), a mesma função que o `gate_mix` usa para cobrar a subida. As duas leituras não podem discordar.

Por que a pausa sai do ÁUDIO e não da transcrição: o alinhamento por palavra PERDE palavra, e cada
palavra perdida virava um buraco que o motor lia como silêncio. A cama subia 17,7 dB no MEIO da frase,
61 vezes em 311 s, e o diretor reprovou ("a música fica aumentando e diminuindo do nada"). Monólogo
denso, sem nenhum vale de 0,5 s, recebe lista vazia e a cama fica parada: forçar respiro vira bombeamento.

Como a automação chega ao ffmpeg:
    volume=volume='if(between(t\\,a\\,b)\\,min(subida\\,descida)\\,...)':eval=frame
A vírgula dentro da expressão vai escapada (\\,): o aspas simples protege do separador de filtros e a
barra invertida do separador de opções (duas camadas de leitura). `asetnsamples=480` antes do volume
dá passos de 10 ms a 48 kHz, e a rampa de 150 ms sai lisa em vez de em degraus do tamanho do frame do
decodificador.

Uso:
    from cinema import musica
    expr = musica.expressao_volume(pausas_reais.pausas("voz.wav"))
"""
import math
import re
import subprocess
from pathlib import Path

from audio import pausas_reais

NIVEL_TRILHA_DBFS = -20.0
CAMA_FALA = 0.055
CAMA_PAUSA = 0.42
RAMPA_S = 0.15
FADE_IN_S = 1.2
FADE_OUT_S = 2.2

# W7.Z: a cama de CADA pausa sai do nível medido da voz e da trilha ali (ver `cama_da_pausa`); 0,42 é o TETO.
PAUSA_SOBE_DB = (1.5, 8.0)           # quanto a cama sobe sobre a voz sozinha numa pausa (a régua do gate_mix)
CAMA_ALVO_DB = (PAUSA_SOBE_DB[0] + PAUSA_SOBE_DB[1]) / 2.0     # 4,75: o centro da faixa
PISO_AUDIVEL_DB = -40.0              # a subida é medida contra o maior entre a voz na pausa e este nível (ambiente de quem ouve)
JANELA_MEDIDA_S = 0.5                # a janela de 0,5 s no meio da pausa em que o gate lê a subida

PAUSA_MIN_S = pausas_reais.DUR_MIN_S
QUEDA_DB = pausas_reais.QUEDA_DB

PASSO_AUTOMACAO_AMOSTRAS = 480       # 10 ms a 48 kHz
MEDIA_MINIMA_DB = -70.0              # abaixo disso a trilha é silêncio: ganho de 50 dB só amplifica ruído

_RE_PAUSA = re.compile(r"between\(t\\,([0-9]+\.[0-9]+)\\,([0-9]+\.[0-9]+)\)")
_RE_MEDIA = re.compile(r"mean_volume:\s*(-?[0-9.]+|-inf) dB")


class TrilhaInvalida(ValueError):
    """A trilha não existe, não tem sinal ou o projeto não diz o que fazer com ela."""


def salto_db(cama_fala=CAMA_FALA, cama_pausa=CAMA_PAUSA):
    """Quanto a cama sobe de um estado para o outro, em dB (17,66 com os padrões)."""
    return 20.0 * math.log10(cama_pausa / cama_fala)


def _g(x):
    return "%g" % x


def _desmontar(pausa, cama_pausa):
    """(início, fim, platô) de uma pausa que vem como (a, b) ou (a, b, cama)."""
    a, b = float(pausa[0]), float(pausa[1])
    return a, b, (float(pausa[2]) if len(pausa) > 2 and pausa[2] is not None else cama_pausa)


def ganho_no_instante(t, pausas, cama_fala=CAMA_FALA, cama_pausa=CAMA_PAUSA, rampa_s=RAMPA_S):
    """O que a expressão de volume vale no instante `t` (s). É a mesma conta que o ffmpeg faz:
    sobe em `rampa_s` desde o começo da pausa, desce em `rampa_s` até o fim, e vale `cama_fala` fora.
    Cada pausa pode trazer o platô dela, `(início, fim, cama)`; sem ele vale `cama_pausa`.

    Existe para os testes e a documentação serem verificáveis sem ffmpeg; o ffmpeg avalia a expressão
    (`expressao_volume`) e um teste confere que as duas contas dão o mesmo resultado.
    """
    if rampa_s <= 0:
        raise ValueError("a rampa tem que ser positiva (era %r)" % (rampa_s,))
    for pausa in pausas:
        a, b, platoe = _desmontar(pausa, cama_pausa)
        if a <= t <= b:
            salto = platoe - cama_fala
            subida = cama_fala + salto * min(1.0, (t - a) / rampa_s)
            descida = cama_fala + salto * min(1.0, (b - t) / rampa_s)
            return min(subida, descida)
    return cama_fala


def expressao_volume(pausas, cama_fala=CAMA_FALA, cama_pausa=CAMA_PAUSA, rampa_s=RAMPA_S):
    """Expressão do filtro `volume` (eval=frame): `cama_fala` fora das pausas, rampa até o platô dentro delas. O platô é
    `cama_pausa` ou, se a pausa vier como `(início, fim, cama)`, o dela. Sem pausa, é só o número: cama constante."""
    if rampa_s <= 0:
        raise ValueError("a rampa tem que ser positiva (era %r)" % (rampa_s,))
    f, r = _g(cama_fala), _g(rampa_s)
    expr = f
    normalizadas = sorted(_desmontar(p, cama_pausa) for p in pausas)
    # da última para a primeira, para a primeira pausa ficar na camada de fora
    for a, b, platoe in reversed(normalizadas):
        p = _g(platoe)
        subida = "(%s+(%s-%s)*min(1\\,(t-%.3f)/%s))" % (f, p, f, a, r)
        descida = "(%s+(%s-%s)*min(1\\,(%.3f-t)/%s))" % (f, p, f, b, r)
        expr = "if(between(t\\,%.3f\\,%.3f)\\,min(%s\\,%s)\\,%s)" % (a, b, subida, descida, expr)
    return expr


def pausas_da_expressao(expr):
    """As pausas que uma `expressao_volume` contém, na ordem em que aparecem."""
    return [(float(a), float(b)) for a, b in _RE_PAUSA.findall(expr)]


def filtro_automacao(expr):
    """A automação como filtro: passos de 10 ms e `volume` avaliado por frame."""
    return "asetnsamples=n=%d:p=0,volume=volume='%s':eval=frame" % (PASSO_AUTOMACAO_AMOSTRAS, expr)


def ganho_para_nivel_db(media_db, alvo_db=NIVEL_TRILHA_DBFS):
    """Ganho (dB) que leva a média da trilha ao alvo."""
    return alvo_db - media_db


def medir_media_db(arquivo, ate_s=None):
    """mean_volume (dB) da trilha, só dos primeiros `ate_s` segundos quando se passa. É a média do que
    vai ao ar: trilha mais longa que a peça só entra até o fim dela."""
    cmd = ["ffmpeg", "-v", "info", "-nostdin"]
    if ate_s is not None:
        cmd += ["-t", "%.3f" % ate_s]
    cmd += ["-i", str(arquivo), "-vn", "-af", "volumedetect", "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise TrilhaInvalida("não consegui ler a trilha %s: %s" % (arquivo, r.stderr.strip()[-200:] or "ffmpeg falhou"))
    m = _RE_MEDIA.search(r.stderr)
    if not m or m.group(1) == "-inf" or float(m.group(1)) < MEDIA_MINIMA_DB:
        raise TrilhaInvalida("a trilha %s está sem sinal (média %s dB): troque o arquivo" %
                             (arquivo, m.group(1) if m else "?"))
    return float(m.group(1))


def cadeia_da_trilha(entrada, saida, duracao_s, ganho_db, expressao, fade_in_s=FADE_IN_S, fade_out_s=FADE_OUT_S):
    """Trecho de filtergraph da trilha: corta no tamanho da peça, nivela, faz os dois fades e aplica a
    automação. `entrada` e `saida` são rótulos ("[2:a]", "[m]"). A repetição de trilha curta é do
    `-stream_loop -1` do ffmpeg, na entrada. `expressao=None` devolve a trilha COMO CHEGA à automação (sem ela): é o que
    se mede para calcular o ganho de cada pausa."""
    inicio_do_fade_final = max(duracao_s - fade_out_s, 0.0)
    base = ("%satrim=0:%.3f,asetpts=N/SR/TB,volume=%.3fdB,"
            "afade=t=in:st=0:d=%s,afade=t=out:st=%.3f:d=%s"
            % (entrada, duracao_s, ganho_db, _g(fade_in_s), inicio_do_fade_final, _g(fade_out_s)))
    if expressao is None:
        return base + saida
    return "%s,%s%s" % (base, filtro_automacao(expressao), saida)


def ducking_para_timeline(pausas, cama_fala=CAMA_FALA, cama_pausa=CAMA_PAUSA, rampa_s=RAMPA_S,
                          fade_in_s=FADE_IN_S, fade_out_s=FADE_OUT_S):
    """A seção `ducking` do timeline.json (contratos/timeline.schema.json) para uma trilha ligada. `cama_pausa` é o TETO;
    a pausa que vem como `(início, fim, cama)` grava a cama dela."""
    saida = []
    for pausa in pausas:
        item = {"s": round(float(pausa[0]), 3), "e": round(float(pausa[1]), 3)}
        if len(pausa) > 2 and pausa[2] is not None:
            item["cama"] = round(float(pausa[2]), 4)
        saida.append(item)
    return {"cama_fala": cama_fala, "cama_pausa": cama_pausa, "rampa_ms": round(rampa_s * 1000.0, 3),
            "fade_in_s": fade_in_s, "fade_out_s": fade_out_s, "pausas": saida}


# --- o ganho de cada pausa, fechado sobre o que foi MEDIDO (W7.Z) ---------------------------------------------------

def fator_de_rampa(a, b, rampa_s=RAMPA_S, janela_s=JANELA_MEDIDA_S):
    """Fração da potência do platô que a janela de `janela_s` s no MEIO da pausa [a, b] recebe, por causa das rampas de
    subida e descida (uma pausa de 0,5 s não tem platô: as duas rampas ocupam a janela inteira; de 0,8 s em diante, tem)."""
    meio = (a + b) / 2.0
    ini, n = meio - janela_s / 2.0, 100
    soma = 0.0
    for k in range(n):
        t = ini + (k + 0.5) * janela_s / n
        soma += max(0.0, min(1.0, (t - a) / rampa_s, (b - t) / rampa_s)) ** 2
    return soma / n


def delta_previsto_db(voz_db, trilha_db, ganho, fator_rampa=1.0):
    """A subida que o gate vai medir numa pausa: o nível do mix (voz + trilha com `ganho`, na potência) menos o MAIOR
    entre a voz sozinha e o piso audível. `trilha_db` é o nível da trilha ali, antes da automação."""
    mix = 10.0 ** (voz_db / 10.0) + 10.0 ** (trilha_db / 10.0) * ganho * ganho * fator_rampa
    return 10.0 * math.log10(mix) - max(voz_db, PISO_AUDIVEL_DB)


def cama_da_pausa(voz_db, trilha_db, fator_rampa=1.0, cama_fala=CAMA_FALA, cama_max=CAMA_PAUSA, alvo_db=CAMA_ALVO_DB):
    """O platô (ganho linear sobre a trilha) que leva a subida da pausa ao centro da faixa (`alvo_db`).

    A causa do +11 a +21 dB da prova: a cama tinha um nível absoluto (0,42 = a trilha a -20 dBFS menos 7,5 dB) e a subida,
    medida sobre a voz sozinha, dependia do piso da voz ali (-36 a -55 dBFS numa voz isolada) e da dinâmica da trilha (-25 a
    -33 dBFS no mesmo ganho). Aqui cada pausa recebe o ganho que fecha a conta com o que foi medido nela. Limites: `cama_max`
    (0,42, o teto: trilha sumindo num fade não ganha ganho infinito) e `cama_fala` (nunca abaixo da cama sob a fala)."""
    referencia = max(10.0 ** (voz_db / 10.0), 10.0 ** (PISO_AUDIVEL_DB / 10.0))
    musica_alvo = referencia * 10.0 ** (alvo_db / 10.0) - 10.0 ** (voz_db / 10.0)
    base = 10.0 ** (trilha_db / 10.0) * max(fator_rampa, 1e-6)
    ganho = math.sqrt(max(musica_alvo, 0.0) / base)
    return max(cama_fala, min(cama_max, ganho))


def ducking_desligado(motivo):
    """A seção `ducking` quando o projeto não tem trilha. O motivo escrito é obrigatório."""
    if not isinstance(motivo, str) or len(motivo.strip()) < 5:
        raise ValueError("ducking desligado exige o motivo escrito (5 caracteres ou mais); veio %r" % (motivo,))
    return {"desligado": True, "motivo": motivo.strip()}


def resolver_trilha(projeto, estado=None):
    """(caminho, None) da trilha do projeto, ou (None, motivo) se ele a desligou com motivo escrito.

    TrilhaInvalida se o projeto não declara nada, ou se declara um arquivo que não está em
    `_local/trilhas/`. O repo não embarca música: o aluno traz a dele ou diz por que não usa.
    """
    from projeto import pastas
    tr = projeto.get("trilha") if isinstance(projeto, dict) else None
    if not isinstance(tr, dict):
        raise TrilhaInvalida("o projeto não diz nada sobre a trilha: ponha o arquivo dela em _local/trilhas/ "
                             "(trilha.arquivo) ou desligue com o motivo escrito (trilha.desligada e trilha.motivo)")
    if tr.get("desligada"):
        return None, tr.get("motivo")
    nome = tr.get("arquivo")
    try:
        caminho = pastas.trilha(nome, estado)
    except ValueError as e:
        raise TrilhaInvalida(str(e))
    if not caminho.is_file():
        raise TrilhaInvalida("a trilha %s não está em %s: copie o arquivo para lá ou troque o nome no projeto.json"
                             % (nome, pastas.trilhas_dir(estado)))
    return Path(caminho), None
