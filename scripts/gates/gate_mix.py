#!/usr/bin/env python3
"""GATE DE MIX (C10 e C12): a cama respira nas pausas e some sob a fala; a entrega fica em -14 LUFS.

    python3 scripts/gates/gate_mix.py <slug> [--estado _local] [--final arquivo] [--voz arquivo]
    exit 0 passa · 1 reprova · 2 insumo inválido (sem arquivo final, sem a voz pré-mix, sem projeto.json,
    trilha ausente, nenhum transcritor para ouvir a trilha)

Porte do verificador de mix da esteira de VSL, sem nome de cliente. Compara o arquivo FINAL com a voz
pré-mix (`render/voz_pre_mix.wav`, gravada pelo `audio.mix_final`), janela a janela. A pausa vem de
`audio.pausas_reais`, a mesma função que o mixer usou para subir a cama: as duas leituras não podem
discordar. Reprova quando:

  loudness           o arquivo final fora de -14 LUFS (mais ou menos 1,2);
  true_peak          o true peak do arquivo final acima de -1,5 dBTP;
  cama_nas_pausas    das 8 maiores pausas reais, a cama (final menos voz sozinha, janela de 0,5 s no meio da
                     pausa) não sobe de +1,5 a +8,0 dB em pelo menos 75% delas;
  sob_a_fala         sob a fala contínua a cama sobe +1,5 dB ou mais;
  trilha_canta       a transcrição da trilha passa de 60 caracteres (música cantada briga com a voz);
  automacao_divergente  a automação gravada no timeline.json não é a das pausas reais da voz;
  ducking_incoerente    o timeline diz "sem trilha" e o projeto tem trilha (ou o contrário).

Peça SEM pausa real (monólogo denso) não cobra respiro: cobra só que a cama não suba sob a fala. Forçar
respiro ali vira bombeamento, e foi o que o diretor reprovou ("a música fica aumentando e diminuindo do
nada"). Projeto SEM trilha: só a entrega (loudness e true peak) é conferida.

Fala contínua = janela de 0,5 s com no máximo 2 de 10 janelas do envelope abaixo da mediana menos 12 dB, e
fora de qualquer pausa real (com 0,1 s de folga). A armadilha medida em 07/09 na esteira de VSL: o ponto
de aceite tem que ser validado NA MESMA JANELA que o medidor lê, senão um ponto que cai em pausa passa por
fala e a peça boa reprova.

Limites desta régua (a do VSL, mantida por decisão do plano): o delta é "final menos voz sozinha", então ele
depende do piso da voz. Em pausa limpa demais (piso muito abaixo de -35 dBFS) a cama sobe mais de 8 dB só
porque a voz sozinha é quase silêncio, e o gate reprova uma mix correta; sob a fala, ele só vê a cama
quando ela fica a menos de uns 4 dB da voz (a trilha a -20 dBFS com cama 0,42 fixa, por exemplo, passa as
duas réguas: ela não respira, mas fica abaixo da voz). Calibrar contra voz real é o trabalho da prova (W7).

Resultado: `Resultado(ok, motivo, detalhes)`. `detalhes["estado"]` é PASS ou REPROVA; `falhas` traz
{regra, motivo} de cada reprovação (o motivo junta todas); `medido` e `limiar` vão para o laudo. A CLI
grava em status.json (etapa `gate_mix`).
"""
import argparse
import math
import os
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

if __name__ == "__main__":      # rodado direto: scripts/gates/gate_mix.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from audio import loudness, mix_final, pausas_reais, transcrever  # noqa: E402
from cinema import musica  # noqa: E402
from projeto import modelo, pastas, status  # noqa: E402

NOME = "gate_mix"
ETAPA = "gate_mix"
Resultado = namedtuple("Resultado", "ok motivo detalhes")

# --- limiares: o número e de onde veio ---------------------------------------------------------------
# esteira de VSL, verificar_mix.py (JAN): janela do medidor, a mesma em que se valida o ponto de fala.
JAN = 0.5
# verificar_mix.py: `1.5 <= d <= 8.0`. A cama sobe pelo menos 1,5 dB (se não, não respira) e no máximo 8,0 dB.
PAUSA_DELTA_DB = (1.5, 8.0)
# verificar_mix.py: `pior < 1.5`.
SOB_A_FALA_MAX_DB = 1.5
# verificar_mix.py: `round(0.75 * len(pausas))`, aqui sem o piso de 3 (com 1 ou 2 pausas ele era inalcançável).
PAUSAS_MINIMO = 0.75
MAIORES_PAUSAS = 8
# plano W4.B, C10: a trilha "canta" com mais de 60 caracteres transcritos.
TRILHA_CARACTERES_MAX = 60
TRILHA_ASR_S = 90                 # ouve os primeiros 90 s da trilha
# C12 (audio.loudness): -14 LUFS, mais ou menos 1,2, true peak até -1,5 dBTP.
LUFS_ALVO, LUFS_TOLERANCIA, TP_MAX = loudness.LUFS_ALVO, loudness.TOLERANCIA_LUFS, loudness.TP_ALVO
TOL_AUTOMACAO_S = 0.06            # a pausa do timeline contra a do áudio: a borda do envelope erra até 50 ms
SR_MEDIDA = 16000                 # 16 kHz cobre a fala e quase toda a energia da música; decodificar é barato
FOLGA_PAUSA_S = 0.1               # fala contínua fica a pelo menos 0,1 s de qualquer pausa
FALA_JANELAS_ABAIXO_MAX = 2       # de 10 janelas de 50 ms
PASSO_FALA_S = 1.0
EPS = 1e-9

medir_loudness_padrao = loudness.medir


class InsumoInvalido(Exception):
    """Falta arquivo ou ele não pôde ser lido: não dá nem para reprovar (exit 2)."""


class Faixa(object):
    """Áudio decodificado em mono para medir nível por janela. Em numpy: sem ffmpeg por janela."""

    def __init__(self, amostras, sr):
        self.x = np.asarray(amostras, dtype=np.float64)
        self.sr = int(sr)

    @property
    def duracao_s(self):
        return len(self.x) / float(self.sr)

    def nivel_db(self, t, d=JAN):
        """RMS em dB da janela [t, t + d) (o que o volumedetect chama de mean_volume)."""
        i, j = max(int(round(t * self.sr)), 0), min(int(round((t + d) * self.sr)), len(self.x))
        if j <= i:
            return -120.0
        seg = self.x[i:j]
        return float(10.0 * math.log10(float(np.mean(seg ** 2)) + 1e-12))

    def envelope_db(self, jan=pausas_reais.JAN):
        """RMS em dB por janela de `jan` s: o mesmo envelope de `audio.pausas_reais`."""
        n = int(self.sr * jan)
        m = len(self.x) // n * n
        if m == 0:
            return np.array([])
        return 20.0 * np.log10(np.sqrt((self.x[:m].reshape(-1, n) ** 2).mean(axis=1) + 1e-12))

    @classmethod
    def carregar(cls, arquivo, sr=SR_MEDIDA):
        p = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(arquivo), "-vn", "-ac", "1",
                            "-ar", str(sr), "-f", "f32le", "-"], capture_output=True)
        if p.returncode != 0:
            raise InsumoInvalido("não consegui ler o áudio de %s: %s" %
                                 (arquivo, p.stderr.decode("utf-8", "replace").strip()[-200:] or "ffmpeg falhou"))
        x = np.frombuffer(p.stdout, dtype=np.float32)
        if not len(x):
            raise InsumoInvalido("%s não tem áudio para medir" % (arquivo,))
        return cls(x, sr)


def _faixa(x):
    return x if isinstance(x, Faixa) else Faixa.carregar(x)


def _n(x):
    return "%.1f" % x


def _pausas_da_voz(voz_original, voz):
    """As pausas reais: pela função de `audio.pausas_reais` (arquivo) ou pelo envelope da Faixa."""
    if isinstance(voz_original, (str, Path)):
        try:
            return [(float(a), float(b)) for a, b in pausas_reais.pausas(str(voz_original))]
        except pausas_reais.ErroDeAudio as e:
            raise InsumoInvalido(str(e))
    jan = pausas_reais.JAN
    return [(float(a), float(b)) for a, b in pausas_reais.pausas_do_envelope(voz.envelope_db(jan), jan)]


def _pontos_de_fala(voz, pausas):
    """Instantes (s) de janelas de 0,5 s que são fala contínua da voz: fora das pausas e quase sem vale."""
    jan = pausas_reais.JAN
    env = voz.envelope_db(jan)
    if not len(env):
        return []
    limiar = float(np.median(env)) - musica.QUEDA_DB
    por_janela = int(round(JAN / jan))
    pontos = []
    t = 0.0
    while t + JAN <= voz.duracao_s + EPS:
        i = int(round(t / jan))
        trecho = env[i:i + por_janela]
        em_pausa = any(t < b + FOLGA_PAUSA_S and t + JAN > a - FOLGA_PAUSA_S for a, b in pausas)
        if len(trecho) == por_janela and not em_pausa and int(np.sum(trecho < limiar)) <= FALA_JANELAS_ABAIXO_MAX:
            pontos.append(round(t, 3))
        t += PASSO_FALA_S
    return pontos


def _caracteres(palavras):
    textos = []
    for p in palavras:
        t = str(p.get("text", "") if isinstance(p, dict) else p).strip()
        if t:
            textos.append(t)
    return len(" ".join(textos))


def avaliar(final, voz, *, pausas=None, ducking=None, trilha=None, transcritor=None,
            loudness_medido=None, medir_loudness=None, arquivo_final=None):
    """Confere um mix. `final` e `voz` são Faixa ou caminho de áudio.

    pausas           lista (início, fim) a usar no lugar da medida na voz (só para teste)
    ducking          a seção `ducking` do timeline.json, ou None
    trilha           caminho da trilha (None = projeto sem trilha: só a entrega é conferida)
    transcritor      `f(caminho) -> [{text, start, end}]`, para ouvir a trilha (padrão: nenhum -> insumo inválido)
    loudness_medido  Medicao já feita; senão mede `arquivo_final` (ou `final`, se for caminho) com `medir_loudness`
    """
    final_faixa, voz_faixa = _faixa(final), _faixa(voz)
    falhas = []

    def falha(regra, motivo):
        falhas.append({"regra": regra, "motivo": motivo})

    # --- entrega (C12) ---
    if loudness_medido is None:
        alvo = arquivo_final if arquivo_final is not None else (final if isinstance(final, (str, Path)) else None)
        if alvo is None:
            raise InsumoInvalido("sem como medir o loudness: passe o arquivo final (arquivo_final) ou a Medicao")
        try:
            loudness_medido = (medir_loudness or medir_loudness_padrao)(alvo)
        except loudness.ErroDeLoudness as e:
            raise InsumoInvalido(str(e))
    lufs, tp = loudness_medido.integrado_lufs, loudness_medido.true_peak_dbtp
    if abs(lufs - LUFS_ALVO) > LUFS_TOLERANCIA + EPS:
        falha("loudness", "o arquivo final está em %s LUFS; a entrega pede -14 LUFS (mais ou menos 1,2)" % _n(lufs))
    if tp > TP_MAX + EPS:
        falha("true_peak", "o true peak do arquivo final é %s dBTP; o teto da entrega é -1,5 dBTP" % _n(tp))

    medido = {"lufs": lufs, "true_peak_dbtp": tp, "sem_trilha": trilha is None, "sem_pausas": False,
              "pausas": [], "pausas_ok": 0, "pausas_exigidas": 0, "pior_sob_a_fala_db": None,
              "pontos_de_fala": 0, "caracteres_na_trilha": None}

    # --- coerência do timeline com o projeto ---
    if ducking is not None:
        desligado = bool(ducking.get("desligado"))
        if trilha is not None and desligado:
            falha("ducking_incoerente", "o timeline diz que o ducking está desligado (%s) mas o projeto tem trilha"
                  % ducking.get("motivo", "sem motivo"))
        if trilha is None and not desligado:
            falha("ducking_incoerente", "o timeline traz automação de cama (%d pausa(s)) mas o projeto não tem trilha"
                  % len(ducking.get("pausas", [])))

    if trilha is not None:
        # --- cama nas pausas reais (C10) ---
        todas = pausas if pausas is not None else _pausas_da_voz(voz, voz_faixa)
        todas = sorted((float(a), float(b)) for a, b in todas)
        if ducking is not None and not ducking.get("desligado") and "pausas" in ducking and pausas is None:
            gravadas = [(p["s"], p["e"]) for p in ducking["pausas"]]
            if len(gravadas) != len(todas) or any(abs(a1 - a2) > TOL_AUTOMACAO_S or abs(b1 - b2) > TOL_AUTOMACAO_S
                                                  for (a1, b1), (a2, b2) in zip(gravadas, todas)):
                falha("automacao_divergente", "a automação gravada no timeline (%d pausa(s)) não é a das pausas reais "
                      "da voz (%d pausa(s)): o mix foi feito de outra voz, ou o timeline está velho"
                      % (len(gravadas), len(todas)))
        maiores = sorted(todas, key=lambda p: p[1] - p[0], reverse=True)[:MAIORES_PAUSAS]
        medido["sem_pausas"] = not todas
        ok = 0
        for a, b in maiores:
            m = (a + b) / 2.0 - JAN / 2.0
            d = final_faixa.nivel_db(m) - voz_faixa.nivel_db(m)
            passa = PAUSA_DELTA_DB[0] - EPS <= d <= PAUSA_DELTA_DB[1] + EPS
            ok += passa
            medido["pausas"].append({"s": round(a, 3), "e": round(b, 3), "delta_db": round(d, 2), "ok": bool(passa)})
        exigidas = int(math.ceil(PAUSAS_MINIMO * len(maiores) - EPS)) if maiores else 0
        medido["pausas_ok"], medido["pausas_exigidas"] = ok, exigidas
        if maiores and ok < exigidas:
            piores = sorted(medido["pausas"], key=lambda p: abs(p["delta_db"] - sum(PAUSA_DELTA_DB) / 2.0), reverse=True)[:3]
            falha("cama_nas_pausas", "a cama só respira em %d das %d maiores pausas (mínimo %d): em cada uma ela tem "
                  "que subir de +1,5 a +8,0 dB sobre a voz sozinha. Piores: %s" %
                  (ok, len(maiores), exigidas, "; ".join("pausa de %.1f s a %.1f s: %+.1f dB" % (p["s"], p["e"], p["delta_db"])
                                                         for p in piores)))
        # --- sob a fala ---
        pontos = _pontos_de_fala(voz_faixa, todas)
        medido["pontos_de_fala"] = len(pontos)
        if pontos:
            deltas = sorted(((final_faixa.nivel_db(t) - voz_faixa.nivel_db(t), t) for t in pontos), reverse=True)
            pior, quando = deltas[0]
            medido["pior_sob_a_fala_db"] = round(pior, 2)
            if pior >= SOB_A_FALA_MAX_DB - EPS:
                falha("sob_a_fala", "a música sobe %+.1f dB sob a fala contínua (em %.1f s); o limite é menos de +1,5 dB: "
                      "a cama está alta demais sob a voz" % (pior, quando))
        # --- a trilha não canta ---
        if transcritor is None:
            raise InsumoInvalido("sem transcritor para ouvir a trilha: instale um (bash setup.sh) ou passe o transcritor")
        try:
            palavras = transcritor(trilha)
        except transcrever.SemTranscritor as e:
            raise InsumoInvalido(str(e))
        n = _caracteres(palavras)
        medido["caracteres_na_trilha"] = n
        if n > TRILHA_CARACTERES_MAX:
            falha("trilha_canta", "a trilha tem %d caracteres transcritos (o limite é %d): é música cantada, e a letra "
                  "briga com a voz do anúncio. Troque por uma instrumental" % (n, TRILHA_CARACTERES_MAX))

    detalhes = {
        "estado": "REPROVA" if falhas else "PASS",
        "falhas": falhas,
        "medido": medido,
        "limiar": {"lufs": [round(LUFS_ALVO - LUFS_TOLERANCIA, 3), round(LUFS_ALVO + LUFS_TOLERANCIA, 3)],
                   "true_peak_max_dbtp": TP_MAX, "pausa_delta_db": list(PAUSA_DELTA_DB),
                   "pausas_minimo": PAUSAS_MINIMO, "sob_a_fala_max_db": SOB_A_FALA_MAX_DB,
                   "trilha_caracteres_max": TRILHA_CARACTERES_MAX, "janela_s": JAN},
    }
    return Resultado(not falhas, "; ".join(f["motivo"] for f in falhas), detalhes)


# --- projeto -----------------------------------------------------------------------------------------

def _transcritor_padrao(pj):
    def asr(faixa):
        pasta = Path(pj.render_dir) / "cache_asr_trilha"
        pasta.mkdir(parents=True, exist_ok=True)
        trecho = pasta / "trilha_inicio.wav"
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-t", str(TRILHA_ASR_S), "-i", str(faixa),
                            "-vn", "-ac", "1", "-ar", "16000", str(trecho)], capture_output=True, text=True)
        if r.returncode != 0:
            raise InsumoInvalido("não consegui ler a trilha %s: %s" % (faixa, r.stderr.strip()[-200:]))
        return transcrever.transcrever(trecho, cache_dir=pasta)
    return asr


def rodar(pastas_projeto, transcritor=None, final=None, voz=None):
    """Confere o mix do projeto: o arquivo final, a voz pré-mix e a trilha do projeto.json."""
    pj = pastas_projeto
    try:
        projeto = modelo.carregar(pj.projeto_json)
    except FileNotFoundError:
        raise InsumoInvalido("projeto.json não existe em %s: crie o projeto antes (vam novo)" % pj.raiz)
    except modelo.ContratoInvalido as e:
        raise InsumoInvalido(str(e))
    try:
        trilha, _ = musica.resolver_trilha(projeto, pj.estado)
    except musica.TrilhaInvalida as e:
        raise InsumoInvalido(str(e))
    final = Path(final) if final else pj.final_9x16
    voz = Path(voz) if voz else mix_final.caminho_voz_ref(pj)
    if not final.is_file():
        raise InsumoInvalido("o arquivo final não existe: %s (rode o mix antes de conferir)" % final)
    if not voz.is_file():
        raise InsumoInvalido("a voz de referência %s não existe: o mixer a grava (mix_final.mixar, voz_ref=...)" % voz)
    ducking = None
    if pj.timeline.is_file():
        try:
            ducking = status.ler_json(pj.timeline).get("ducking")
        except (OSError, ValueError) as e:
            raise InsumoInvalido("não consegui ler %s: %s" % (pj.timeline, e))
    if trilha is not None and transcritor is None:
        transcritor = _transcritor_padrao(pj)
    return avaliar(final, voz, ducking=ducking, trilha=trilha, transcritor=transcritor)


def _registrar(pj, r):
    if r.ok:
        status.registrar(pj, ETAPA, "ok", detalhes=r.detalhes)
    else:
        status.registrar(pj, ETAPA, "falhou", motivo=r.motivo[:600], detalhes=r.detalhes)


def main(argv=None, transcritor=None):
    ap = argparse.ArgumentParser(description="Confere a cama de música e a entrega do mix do projeto.")
    ap.add_argument("slug")
    ap.add_argument("--estado", help="pasta _local (padrão: a do repo)")
    ap.add_argument("--final", help="arquivo final (padrão: entrega/final_9x16.mp4 do projeto)")
    ap.add_argument("--voz", help="voz pré-mix (padrão: render/voz_pre_mix.wav do projeto)")
    args = ap.parse_args(argv)
    try:
        pj = pastas.projeto(args.slug, args.estado)
    except ValueError as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        return 2
    try:
        r = rodar(pj, transcritor=transcritor, final=args.final, voz=args.voz)
    except InsumoInvalido as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        if pj.raiz.is_dir():
            status.registrar(pj, ETAPA, "bloqueado", motivo=str(e)[:400])
        return 2
    _registrar(pj, r)
    m = r.detalhes["medido"]
    if r.ok:
        if m["sem_trilha"]:
            print("PASSA: sem trilha, entrega em %.1f LUFS e %.1f dBTP" % (m["lufs"], m["true_peak_dbtp"]))
        else:
            print("PASSA: cama respira em %d de %d pausa(s) reais, sem subir sob a fala (pior %s dB), entrega em %.1f LUFS "
                  "e %.1f dBTP" % (m["pausas_ok"], len(m["pausas"]),
                                   "%+.1f" % m["pior_sob_a_fala_db"] if m["pior_sob_a_fala_db"] is not None else "n/a",
                                   m["lufs"], m["true_peak_dbtp"]))
        return 0
    for f in r.detalhes["falhas"]:
        print("REPROVA (%s): %s" % (f["regra"], f["motivo"]))
    return 1


if __name__ == "__main__":
    sys.exit(main())
