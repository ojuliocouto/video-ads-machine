#!/usr/bin/env python3
"""Biblioteca de efeitos sonoros da fábrica (item 1 do brief: som estratégico).

Sintetiza com ffmpeg em vez de baixar: repo limpo, sem licença de terceiro, e o som é
reproduzível (rodar de novo dá o mesmo arquivo). Grava em assets/som/ a 48k, o sample
rate do pipeline.

Regras de USO (do banco de referências, seção "Princípios"): whoosh na entrada de
insert, tick na numeração, riser antes da virada. Sutil, nunca em todo corte; teto de
1 efeito a cada 2,5s; nunca na volta pro avatar. A mixagem entra DEPOIS da aceleração
(senão o efeito acelera junto e desafina), com ducking leve na voz.

Uso:
    python3 som_cortes.py            # gera os três em assets/som/
    python3 som_cortes.py --forcar   # regenera mesmo se existirem
"""
import subprocess
import sys
from pathlib import Path

# (migracao 26/08/2026) era `Path(__file__).parent / "assets" / "som"`, que so
# funcionava porque o codigo morava junto da midia. Agora o som sai do modulo
# central de caminhos: os wav sao dados, ficam com os dados.
from caminhos import ASSETS_V1  # noqa: E402
SOM = ASSETS_V1 / "som"
SR = 48000

# nome -> (duração, cadeia de síntese)
#
# CALIBRAGEM POR NIVEL ABSOLUTO, PORQUE O EFEITO TOCA NO SILENCIO (27/08/2026).
# O Julio: "tem um som ridiculo nas transicoes, parece um tiro".
#
# A primeira hipotese foi "esta competindo com a voz", e a MEDICAO DERRUBOU ela: o
# whoosh isolado esta em -24,6 dBFS, abaixo da voz em -17,9. Comparando a janela do
# efeito com a fala vizinha eu tinha achado +5 a +8 dB, mas essa comparacao e enviesada,
# porque o whoosh cai exatamente nos CORTES, e corte coincide com mudanca de fala.
#
# A medicao que explicou: energia na banda do whoosh (300-2400 Hz) no instante do efeito
# contra 0,7s antes, deu +40, +46 e +51 dB em varios deles. Numeros absurdos porque o
# "antes" e SILENCIO: o efeito nao briga com a voz, ele APARECE SOZINHO numa pausa. Um
# ruido rosa de 0,45s surgindo no silencio a -24 dBFS e um estalo bem marcado.
#
# Entao o contrato nao e relativo a voz, e absoluto: o efeito precisa ser discreto
# TOCANDO SOZINHO.
#
# DUAS ANCORAS HUMANAS, uma de cada lado, as duas medidas no mesmo whoosh:
#     RMS -40,2 dBFS  (volume=-14dB)  ->  INAUDIVEL, defeito de 20/08
#     RMS -27,2 dBFS  (volume= -1dB)  ->  "parece um tiro", defeito de 27/08
# Alvo: -34 dBFS, o meio. Faixa aceita: -38 a -31, travada em test_nivel_som.py.
#
# A faixa ANTERIOR daquele teste era -30 a -20, e ela PERMITIA o defeito: os -27,2 que
# o Julio reprovou cabiam dentro dela com folga. Um teste que passa verde no material
# que o cliente reprova esta calibrado errado, nao "quase certo".
EFEITOS = {
    # varredura de ruído rosa com envelope: leitura de "ar" passando, sem cauda longa
    "whoosh.wav": (0.45,
        "anoisesrc=color=pink:sample_rate=48000:amplitude=0.7,"
        "highpass=f=300,lowpass=f=2400,"
        "afade=t=in:st=0:d=0.12:curve=qsin,afade=t=out:st=0.18:d=0.27:curve=qsin,"
        "volume=-7dB"),          # era -1dB. Ver calibragem por medicao no topo.
    # clique curto: seno agudo com decaimento seco, pra pontuar numeração/lista
    "tick.wav": (0.07,
        "sine=frequency=1750:sample_rate=48000,"
        "afade=t=in:st=0:d=0.004,afade=t=out:st=0.012:d=0.055:curve=exp,"
        "volume=-5dB"),          # era +1dB
    # chirp ascendente 180->760 Hz: tensão subindo antes da virada/CTA
    "riser.wav": (1.20,
        "aevalsrc=exprs='0.55*sin(2*PI*(180*t+241.7*t*t))':sample_rate=48000:duration=1.2,"
        "highpass=f=120,"
        "afade=t=in:st=0:d=0.25:curve=qsin,afade=t=out:st=0.95:d=0.25:curve=qsin,"
        "volume=-25dB"),         # era -12dB: o mais alto dos tres, e cai no CTA.
}


# TETO DE DENSIDADE. O banco de referencias e explicito: "Sutil, NUNCA em todo corte."
# Com o ritmo em ~22 cortes/min (um a cada 2,7s), som em todo corte viraria metralhadora
# e competiria com a voz do Thales, que e o ativo da peca.
# 4,0s: na pratica a ENTRADA de insert ja e rara (no jh13 sao ~9 entradas em 90s, uma a
# cada 10s), entao o intervalo e guarda contra aglomeracao, nao regra de rotina. Com 2,0s
# um trecho de alternancia rapida disparava efeito em quase todo corte, que e exatamente
# o que o banco proibe.
INTERVALO_MIN = 4.0      # segundos entre dois efeitos, no tempo do arquivo entregue
WHOOSH_LIGADO = False    # ver plano_de_som; religar so com ordem explicita do Julio
RISER_ANTES = 1.0        # o riser sobe ANTES da virada, senao chega atrasado


def plano_de_som(segs, accel=1.35, cta=None):
    """Onde cada efeito entra, em tempo do arquivo ENTREGUE (ja acelerado).

    Regras (banco de referencias + plano aprovado pelo Julio):
      whoosh  na ENTRADA de insert, nunca na volta pro avatar (a volta e respiro)
      riser   antes da virada do CTA
      teto    um efeito a cada INTERVALO_MIN

    Devolve [{"t": segundos, "efeito": nome}] ordenado.
    """
    cand = []
    for i, x in enumerate(segs):
        if x["tipo"] != "insert":
            continue
        # so ENTRADA: o segmento anterior tem que ser outra coisa, ou ser o primeiro
        if i > 0 and segs[i - 1]["tipo"] == "insert":
            continue
        # WHOOSH DESLIGADO (31/08/2026). Depois de duas calibragens por medicao o Julio
        # ainda escreveu "tem um som nas transicoes que ta me irritando". Efeito de
        # transicao nao e informacao, e cada tentativa de deixa-lo discreto custou um
        # build. Sai. O riser do CTA fica: nao e transicao, e o unico som com funcao.
        if not WHOOSH_LIGADO:
            continue
        cand.append({"t": round(x["s"] / accel, 3), "efeito": "whoosh.wav", "peso": 1})
    if cta is not None:
        cand.append({"t": round(max(cta / accel - RISER_ANTES, 0.0), 3),
                     "efeito": "riser.wav", "peso": 2})
    # o de maior peso ganha quando dois disputam a mesma janela: a virada importa mais
    cand.sort(key=lambda e: (e["t"], -e["peso"]))
    saida = []
    for e in cand:
        if saida and e["t"] - saida[-1]["t"] < INTERVALO_MIN:
            if e["peso"] > saida[-1]["peso"]:
                saida[-1] = e
            continue
        saida.append(e)
    return [{"t": e["t"], "efeito": e["efeito"]} for e in saida]


def gerar(forcar=False):
    SOM.mkdir(parents=True, exist_ok=True)
    for nome, (dur, cadeia) in EFEITOS.items():
        alvo = SOM / nome
        if alvo.exists() and not forcar:
            print(f"  {nome}: já existe")
            continue
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", cadeia,
             "-t", str(dur), "-ar", str(SR), "-ac", "1", str(alvo)],
            capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  {nome}: FALHOU: {r.stderr.strip()[-160:]}")
            return 1
        print(f"  {nome}: ok ({dur}s)")
    return 0


if __name__ == "__main__":
    sys.exit(gerar("--forcar" in sys.argv))
