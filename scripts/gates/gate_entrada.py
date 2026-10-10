#!/usr/bin/env python3
"""GATE DE ENTRADA (W3.C): confere a voz e o avatar ANTES de gastar um build.

    python3 scripts/gates/gate_entrada.py <slug> [--estado _local]
    exit 0 passa · 1 reprova · 2 insumo inválido (sem voz/limpo.mp3, sem avatar no modo avatar,
    áudio ilegível, sem transcritor, transcrição vazia)

Generaliza o `gate_entrada` do produzir_ad.py do motor antigo (looks, pastas de leva e prefixos de
anúncio cravados no código): aqui tudo vem da pasta do projeto do aluno. O look é do `gate_look`.
O áudio fica GRAVADO dentro do avatar, então descobrir um defeito depois do avatar custa um job
novo do HeyGen e um build inteiro. São quatro conferências, e todas rodam (o motivo junta as que
reprovaram):

  respiro         energia acima de -34 dB DENTRO de uma pausa de 0,62 s ou mais. O Avatar V lipsynca a
                  respiração e a boca mexe no vazio (sorrisos estranhos medidos em agosto/2026). Mede energia, não
                  duração: pausa longa e limpa é ritmo, e é boa.
  ritmo achatado  voz de mais de 30 s com menos pausas acima de 0,60 s do que 1 a cada 15 s de fala
                  (mínimo 2). Higienização que corta
                  toda pausa deixa a fala picotada (reclamação real: "o áudio foi todo picotado").
  fala preservada voz/bruto.* e voz/limpo.mp3 são transcritos de novo; trecho do bruto que sobra com
                  menos de 0,60 das letras no limpo é fala que o corte comeu. Elisão natural (vamos
                  embora, vambora) fica no relatório como suspeita e não reprova. Sem bruto, não há
                  o que comparar: vira aviso, nunca aprovação silenciosa de algo que não foi medido.
  duração         avatar/avatar.mp4 e a voz limpa diferindo mais de 1,0 s (só no modo avatar): o
                  avatar foi gerado do áudio errado (avatar de 92,8 s contra voz limpa de 78,0 s).

Como a pausa é medida: pelo ENVELOPE do áudio (RMS em janelas de 50 ms, `audio.pausas_reais`, a mesma
fonte da pausa que o mix usa), não pelo `silencedetect` do motor antigo. Medido: o silencedetect a
-30 dB olha o pico, e ruído rosa de RMS -36 dB ou mais já não vira "silêncio", então um respiro de
verdade nunca chegava a ser medido. Aqui a pausa começa quando o nível cai 12 dB abaixo da mediana da
voz e só acaba quando sobe a menos de 6 dB dela (histerese): o respiro fica DENTRO da pausa.

Resultado: `Resultado(ok, motivo, detalhes)`; `detalhes["falhas"]` traz {regra, motivo} de cada
reprovação (respiro, ritmo_achatado, fala_preservada, duracao_avatar). A CLI grava em status.json
(etapa `gate_entrada`).
"""
import argparse
import difflib
import math
import os
import subprocess
import sys
from collections import namedtuple

if __name__ == "__main__":      # rodado direto: scripts/gates/gate_entrada.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from audio import pausas_reais  # noqa: E402
from contratos.validar import normalizar_palavra  # noqa: E402
from projeto import glossario, modelo, pastas, status  # noqa: E402

ETAPA = "gate_entrada"
Resultado = namedtuple("Resultado", "ok motivo detalhes")

# --- limiares: o número, de onde veio, e o passo que ele fiscaliza ---------------------------------
# produzir_ad.py:143 (BIG_SIL_GATE). A pausa a partir da qual vale medir respiro.
BIG_SIL_GATE = 0.62
# produzir_ad.py:144 e auditar_audio.py (RESPIRO_DB). Energia dentro da pausa acima disso é respiro audível.
RESPIRO_DB_GATE = -34.0
# produzir_ad.py:145 (AVATAR_DUR_TOL). Avatar e voz limpa têm que casar em duração.
AVATAR_DUR_TOL = 1.0
# auditar_audio.py (PAUSA_LONGA) e produzir_ad.py:225. "Pausa longa" é acima de 0,60 s.
PAUSA_LONGA = 0.60
# Quantas pausas longas a voz TEM que ter é proporcional à duração (W7.X): a régua fixa de 4 reprovava voz real
# normal (a gravação da prova de aluno: 56,6 s de fala limpa e 3 pausas de fim de parágrafo). Derivação: um anúncio
# fala ~2,5 palavras por segundo e uma ideia (2 frases) leva ~15 s, então há uma pausa de fim de ideia a cada
# ~15 s; abaixo disso a fala está sem respiração de fim de frase. Mínimo 2 para a voz de 30 a 45 s: uma pausa
# sozinha não faz ritmo. Resultado: 30 a 44 s pedem 2, 45 a 59 s pedem 3, 60 s pedem 4. O aluno nunca regula isso
# (o gate lê a duração da própria voz).
PAUSA_A_CADA_S = 15.0
MIN_PAUSAS_LONGAS = 2
# produzir_ad.py:285 (`d_limpo > 30`). Só voz de mais de 30 s tem que ter pausa de fim de frase.
DUR_MIN_RITMO_S = 30.0
# auditar_audio.py (`x < 5.0`, "ignora cauda"). Pausa de 5 s ou mais é cauda, não respiração.
PAUSA_CAUDA_S = 5.0
# auditar_audio.py (FRACAO_LETRAS_DANO). Calibrado em anúncios reais (agosto/2026): dano de corte ficou em 45% e 50%, elisão
# natural em 64% e 86%.
FRACAO_LETRAS_DANO = 0.60
# auditar_audio.py (MIN_LETRAS_TRECHO). Trecho com menos letras que isso é ruído do transcritor.
MIN_LETRAS_TRECHO = 3
# produzir_ad.py:_respiros_grandes media a partir de ini+0,05 até dur-0,1: a borda da pausa é a cauda
# da última sílaba e o ataque da próxima, não respiro.
MARGEM_BORDA_S = 0.05
# Medição desta unidade (ver docstring): a pausa começa 12 dB abaixo da mediana da voz (a mesma
# queda de audio/pausas_reais.QUEDA_DB, que o mix usa) e só fecha quando o nível volta a menos de
# 6 dB dela. Com 6 dB de folga o respiro mais forte que ainda é respiro (acima de -34 dB e abaixo da
# voz) fica dentro da pausa, e a primeira palavra da frase seguinte (a voz volta ao nível da mediana)
# fecha.
QUEDA_ENTRADA_DB = pausas_reais.QUEDA_DB
QUEDA_SAIDA_DB = 6.0
# A mediana da voz é calculada só nas janelas até 30 dB abaixo do pico (percentil 95): sem isso, um
# arquivo com mais da metade de silêncio teria mediana de silêncio e nenhuma pausa seria achada.
VOZ_ACIMA_DO_PICO_DB = 30.0
PERCENTIL_PICO = 95

_UMA_JANELA_EPS = 1e-9


class InsumoInvalido(Exception):
    """Falta arquivo ou o arquivo não pôde ser lido: não dá nem para reprovar (exit 2)."""


# --- medições puras (testáveis sem áudio) ------------------------------------------------------------

def pausas_do_envelope(db, jan, queda_entrada_db=QUEDA_ENTRADA_DB, queda_saida_db=QUEDA_SAIDA_DB,
                       dur_min_s=PAUSA_LONGA):
    """[(início, fim)] em segundos das pausas de um envelope em dB (uma janela de `jan` s por valor)."""
    db = np.asarray(db, dtype=np.float64)
    if not len(db):
        return []
    pico = float(np.percentile(db, PERCENTIL_PICO))
    voz = db[db >= pico - VOZ_ACIMA_DO_PICO_DB]
    ref = float(np.median(voz if len(voz) else db))
    entrada, saida = ref - queda_entrada_db, ref - queda_saida_db
    pausas, ini = [], None

    def fechar(fim_idx):
        if (fim_idx - ini) * jan >= dur_min_s - _UMA_JANELA_EPS:
            pausas.append((round(ini * jan, 3), round(fim_idx * jan, 3)))

    for i, v in enumerate(db):
        if ini is None:
            if v < entrada:
                ini = i
        elif v > saida:
            fechar(i)
            ini = None
    if ini is not None:
        fechar(len(db))
    return pausas


def respiros(pausas, db, jan):
    """[(início, duração, pior nível em dB)] das pausas de BIG_SIL_GATE s ou mais com energia acima
    de RESPIRO_DB_GATE. A borda de MARGEM_BORDA_S de cada lado não conta."""
    db = np.asarray(db, dtype=np.float64)
    achados = []
    for ini, fim in pausas:
        dur = round(fim - ini, 3)
        if dur < BIG_SIL_GATE:
            continue
        i0 = int(math.ceil(round((ini + MARGEM_BORDA_S) / jan, 6)))
        i1 = int(math.floor(round((fim - MARGEM_BORDA_S) / jan, 6)))
        trecho = db[i0:i1]
        if len(trecho) and float(np.max(trecho)) > RESPIRO_DB_GATE:
            achados.append((round(ini, 2), dur, round(float(np.max(trecho)), 1)))
    return achados


def pausas_exigidas(duracao_s):
    """Quantas pausas longas uma voz de `duracao_s` precisa ter: 1 a cada PAUSA_A_CADA_S s, no mínimo MIN_PAUSAS_LONGAS."""
    return max(MIN_PAUSAS_LONGAS, int(duracao_s // PAUSA_A_CADA_S))


def ritmo_achatado(duracao_s, duracoes_das_pausas):
    """(achatado, quantas pausas longas). Pausa longa é a que passa de PAUSA_LONGA e não é cauda."""
    longas = [d for d in duracoes_das_pausas if PAUSA_LONGA < d < PAUSA_CAUDA_S]
    return (duracao_s > DUR_MIN_RITMO_S and len(longas) < pausas_exigidas(duracao_s)), len(longas)


def trechos_com_dano(bruto, limpo):
    """(danos, suspeitas) comparando as palavras normalizadas do bruto com as do limpo.

    Só conta trecho em que o limpo tem MENOS letras que o bruto; dano é sobrar menos que
    FRACAO_LETRAS_DANO das letras, suspeita é elisão (juntou palavras e preservou o miolo).
    """
    danos, suspeitas = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, bruto, limpo, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        antes, depois = " ".join(bruto[i1:i2]), " ".join(limpo[j1:j2])
        letras_antes, letras_depois = len(antes.replace(" ", "")), len(depois.replace(" ", ""))
        if letras_depois >= letras_antes or letras_antes < MIN_LETRAS_TRECHO:
            continue
        (danos if letras_depois / float(letras_antes) < FRACAO_LETRAS_DANO else suspeitas).append((antes, depois))
    return danos, suspeitas


def duracao_confere(duracao_avatar, duracao_limpo):
    return abs(duracao_avatar - duracao_limpo) <= AVATAR_DUR_TOL + _UMA_JANELA_EPS


# --- insumos -----------------------------------------------------------------------------------------

def _projeto(pj):
    try:
        return modelo.carregar(pj.projeto_json)
    except FileNotFoundError:
        raise InsumoInvalido("projeto.json não existe em %s: crie o projeto antes (vam novo)" % pj.raiz)
    except modelo.ContratoInvalido as e:
        raise InsumoInvalido(str(e))


def _duracao(caminho):
    try:
        p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=nw=1:nk=1", str(caminho)], capture_output=True, text=True)
        d = float(p.stdout.strip())
    except (OSError, ValueError):
        d = 0.0
    if d <= 0:
        raise InsumoInvalido("não consegui ler a duração de %s: o arquivo está corrompido ou o ffprobe "
                             "não está instalado (rode `python3 scripts/vam.py doctor`)" % os.path.basename(str(caminho)))
    return d


def _glossario(pj):
    try:
        return glossario.carregar(pj.estado)
    except ValueError as e:
        raise InsumoInvalido(str(e))


def _asr_padrao(pj, g):
    def asr(caminho):
        from audio import transcrever as T
        try:
            return T.transcrever(caminho, cache_dir=pj.render_dir / "cache_asr", glossario=g)
        except T.SemTranscritor as e:
            raise InsumoInvalido(str(e))
    return asr


def _tokens(asr, caminho, g):
    brutas = list(asr(caminho))
    lista = [p if isinstance(p, dict) else {"text": str(p), "start": 0.0, "end": 0.0} for p in brutas]
    tokens = [t for t in (normalizar_palavra(str(p["text"])) for p in glossario.corrigir_palavras(lista, g)) if t]
    if not tokens:
        raise InsumoInvalido("transcrição vazia de %s: o transcritor não ouviu nenhuma palavra (áudio mudo, "
                             "corrompido ou idioma errado)" % os.path.basename(str(caminho)))
    return tokens


def _formatar_respiros(achados):
    return ", ".join("em %.1f s (pausa de %.2f s, %.1f dB)" % (ini, dur, nivel) for ini, dur, nivel in achados[:3])


# --- o gate --------------------------------------------------------------------------------------------

def rodar(pastas_projeto, asr=None, so_voz=False):
    """Confere voz e avatar do projeto. `asr(caminho) -> [{text, start, end}]` troca o transcritor
    (os testes passam uma função simulada). Levanta InsumoInvalido quando não há o que conferir.

    `so_voz=True` é a conferência do `vam audio`, ANTES de gastar o avatar: respiro, ritmo e fala preservada, sem a
    duração do avatar (que ainda não existe). O `vam montar` roda a conferência inteira."""
    pj = pastas_projeto
    projeto = _projeto(pj)
    modo = projeto["modo"]
    if not pj.voz_limpo.is_file():
        raise InsumoInvalido("voz/limpo.mp3 não existe em %s: higienize a voz antes de conferir a entrada" % pj.raiz)
    d_limpo = _duracao(pj.voz_limpo)
    try:
        db, jan = pausas_reais.envelope_db(pj.voz_limpo)
    except pausas_reais.ErroDeAudio as e:
        raise InsumoInvalido(str(e))
    if not len(db):
        raise InsumoInvalido("voz/limpo.mp3 não tem áudio para medir")

    falhas, avisos = [], []
    pausas = pausas_do_envelope(db, jan)
    fim_do_arquivo = len(db) * jan
    internas = [(i, f) for i, f in pausas if i > _UMA_JANELA_EPS and f < fim_do_arquivo - _UMA_JANELA_EPS]

    achados = respiros(pausas, db, jan)
    if achados:
        falhas.append({"regra": "respiro", "motivo": "respiro audível dentro de pausa (energia acima de %.0f dB em pausa "
                       "de %.2f s ou mais): %s. O Avatar V lipsynca a respiração e a boca mexe no vazio"
                       % (RESPIRO_DB_GATE, BIG_SIL_GATE, _formatar_respiros(achados))})

    achatado, n_longas = ritmo_achatado(d_limpo, [f - i for i, f in internas])
    if achatado:
        falhas.append({"regra": "ritmo_achatado", "motivo": "ritmo achatado: só %d pausa(s) acima de %.2f s em %.0f s "
                       "de fala (mínimo %d: 1 a cada %.0f s). A fala fica sem respiração de fim de frase e soa "
                       "picotada: grave com uma pausa curta entre as ideias e rode vam audio de novo"
                       % (n_longas, PAUSA_LONGA, d_limpo, pausas_exigidas(d_limpo), PAUSA_A_CADA_S)})

    danos, suspeitas = [], []
    bruto = pj.voz_bruto()
    if bruto is None:
        avisos.append("sem voz/bruto.*: a fala preservada não foi conferida (não há o que comparar com o limpo)")
    else:
        g = _glossario(pj)
        asr = asr or _asr_padrao(pj, g)
        danos, suspeitas = trechos_com_dano(_tokens(asr, bruto, g), _tokens(asr, pj.voz_limpo, g))
        if danos:
            falhas.append({"regra": "fala_preservada", "motivo": "corte comeu fala: " + "; ".join(
                "%r virou %r" % (a, d) for a, d in danos[:4])})

    detalhes = {"modo": modo, "duracao_limpo_s": round(d_limpo, 2), "pausas": len(pausas),
                "pausas_acima_de_0_60": n_longas,
                "respiros": [{"inicio_s": i, "duracao_s": d, "nivel_db": n} for i, d, n in achados],
                "danos": [list(x) for x in danos], "suspeitas": len(suspeitas), "avisos": avisos,
                "limiares": {"pausa_respiro_s": BIG_SIL_GATE, "respiro_db": RESPIRO_DB_GATE,
                             "avatar_dur_tol_s": AVATAR_DUR_TOL, "min_pausas_longas": pausas_exigidas(d_limpo),
                             "pausa_longa_s": PAUSA_LONGA, "fracao_letras_dano": FRACAO_LETRAS_DANO}}

    if modo == "avatar" and not so_voz:
        if not pj.avatar_mp4.is_file():
            raise InsumoInvalido("avatar/avatar.mp4 não existe em %s: gere o avatar a partir de voz/limpo.mp3 "
                                 "antes de conferir a entrada" % pj.raiz)
        d_av = _duracao(pj.avatar_mp4)
        detalhes["duracao_avatar_s"] = round(d_av, 2)
        detalhes["diferenca_duracao_s"] = round(d_av - d_limpo, 2)
        if not duracao_confere(d_av, d_limpo):
            falhas.append({"regra": "duracao_avatar", "motivo": "o avatar não foi gerado do áudio limpo (avatar %.1f s, "
                           "voz limpa %.1f s, diferença acima de %.1f s): gere o avatar de novo a partir de "
                           "voz/limpo.mp3" % (d_av, d_limpo, AVATAR_DUR_TOL)})

    detalhes["falhas"] = falhas
    detalhes["estado"] = "REPROVA" if falhas else "PASS"
    return Resultado(not falhas, "; ".join(f["motivo"] for f in falhas), detalhes)


# --- CLI -----------------------------------------------------------------------------------------------

def _registrar(pj, r):
    if r.ok:
        status.registrar(pj, ETAPA, "ok", motivo=r.motivo or None, detalhes=r.detalhes)
    else:
        status.registrar(pj, ETAPA, "falhou", motivo=r.motivo, detalhes=r.detalhes)


def main(argv=None, asr=None):
    ap = argparse.ArgumentParser(description="Confere a voz e o avatar do projeto antes do build.")
    ap.add_argument("slug")
    ap.add_argument("--estado", help="pasta _local (padrão: a do repo)")
    args = ap.parse_args(argv)
    try:
        pj = pastas.projeto(args.slug, args.estado)
    except ValueError as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        return 2
    try:
        r = rodar(pj, asr=asr)
    except (InsumoInvalido, ValueError) as e:      # ValueError: mais de um voz/bruto.*
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        if pj.raiz.is_dir():
            status.registrar(pj, ETAPA, "bloqueado", motivo=str(e)[:400])
        return 2
    _registrar(pj, r)
    for aviso in r.detalhes["avisos"]:
        print("AVISO: %s" % aviso)
    if r.ok:
        print("PASSA: voz limpa de %.1f s, %d pausa(s) acima de 0,60 s, sem respiro audível"
              % (r.detalhes["duracao_limpo_s"], r.detalhes["pausas_acima_de_0_60"]))
        return 0
    for f in r.detalhes["falhas"]:
        print("REPROVA (%s): %s" % (f["regra"], f["motivo"]))
    return 1


if __name__ == "__main__":
    sys.exit(main())
