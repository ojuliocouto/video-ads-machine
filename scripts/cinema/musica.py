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


def ganho_no_instante(t, pausas, cama_fala=CAMA_FALA, cama_pausa=CAMA_PAUSA, rampa_s=RAMPA_S):
    """O que a expressão de volume vale no instante `t` (s). É a mesma conta que o ffmpeg faz:
    sobe em `rampa_s` desde o começo da pausa, desce em `rampa_s` até o fim, e vale `cama_fala` fora.

    Existe para os testes e a documentação serem verificáveis sem ffmpeg; o ffmpeg avalia a expressão
    (`expressao_volume`) e um teste confere que as duas contas dão o mesmo resultado.
    """
    if rampa_s <= 0:
        raise ValueError("a rampa tem que ser positiva (era %r)" % (rampa_s,))
    for a, b in pausas:
        if a <= t <= b:
            salto = cama_pausa - cama_fala
            subida = cama_fala + salto * min(1.0, (t - a) / rampa_s)
            descida = cama_fala + salto * min(1.0, (b - t) / rampa_s)
            return min(subida, descida)
    return cama_fala


def expressao_volume(pausas, cama_fala=CAMA_FALA, cama_pausa=CAMA_PAUSA, rampa_s=RAMPA_S):
    """Expressão do filtro `volume` (eval=frame): `cama_fala` fora das pausas, rampa até `cama_pausa`
    dentro delas. Sem pausa, é só o número: cama constante."""
    if rampa_s <= 0:
        raise ValueError("a rampa tem que ser positiva (era %r)" % (rampa_s,))
    f, p, r = _g(cama_fala), _g(cama_pausa), _g(rampa_s)
    expr = f
    # da última para a primeira, para a primeira pausa ficar na camada de fora
    for a, b in reversed(sorted((float(a), float(b)) for a, b in pausas)):
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
    `-stream_loop -1` do ffmpeg, na entrada."""
    inicio_do_fade_final = max(duracao_s - fade_out_s, 0.0)
    return ("%satrim=0:%.3f,asetpts=N/SR/TB,volume=%.3fdB,"
            "afade=t=in:st=0:d=%s,afade=t=out:st=%.3f:d=%s,%s%s"
            % (entrada, duracao_s, ganho_db, _g(fade_in_s), inicio_do_fade_final, _g(fade_out_s),
               filtro_automacao(expressao), saida))


def ducking_para_timeline(pausas, cama_fala=CAMA_FALA, cama_pausa=CAMA_PAUSA, rampa_s=RAMPA_S,
                          fade_in_s=FADE_IN_S, fade_out_s=FADE_OUT_S):
    """A seção `ducking` do timeline.json (contratos/timeline.schema.json) para uma trilha ligada."""
    return {"cama_fala": cama_fala, "cama_pausa": cama_pausa, "rampa_ms": round(rampa_s * 1000.0, 3),
            "fade_in_s": fade_in_s, "fade_out_s": fade_out_s,
            "pausas": [{"s": round(float(a), 3), "e": round(float(b), 3)} for a, b in pausas]}


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
