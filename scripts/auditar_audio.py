#!/usr/bin/env python3
"""FASE DE AUDIO (dedicada, ordem do Julio 17/08/2026): higieniza e AUDITA a voz
ANTES de gastar job de HeyGen.

Por que virou fase propria: o audio fica GRAVADO dentro do avatar. Descobrir que
ficou ruim depois do avatar pronto custa job novo de HeyGen + rebuild inteiro. Foi
o que aconteceu no jh13: o audio saiu picotado e so apareceu no video final.

O que "picotado" era, medido: a higienizacao cortava TODA pausa acima de 0,55s, entao
as 25 pausas naturais de fim de frase (ate 2,95s no bruto) viravam 0,55s. O resultado
nao tem palavra cortada, tem RITMO ACHATADO: tudo na mesma cadencia curta.
Pior: o gate de entrada ajudava a causar isso, porque reprovava pausa LONGA em vez de
reprovar respiro AUDIVEL dentro da pausa.

Uso:
  python3 auditar_audio.py <bruto.mp3> [--saida <limpo.mp3>] [--json]
  python3 auditar_audio.py --auditar <limpo.mp3>     # so audita um arquivo pronto
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from caminhos import V1, CODIGO  # noqa: E402

# Ritmo: uma fala de anuncio TEM pausa de fim de frase. Zero pausa longa = achatado.
MIN_PAUSAS_LONGAS = 4          # pelo menos isso acima de PAUSA_LONGA num take normal
PAUSA_LONGA = 0.60
# Respiro audivel: energia DENTRO da pausa acima do piso de silencio.
RESPIRO_DB = -34.0             # acima disso, dentro de uma pausa, e respiro audivel
# Parametros de higienizacao que PRESERVAM o ritmo (o default do motor achatava).
# KEEP_PAUSE_MAX saiu daqui de proposito: o higienizador calcula esse teto a partir de
# PAUSA_MAX_TELA x ACCEL_FINAL, ou seja, do que o espectador ve depois da aceleracao.
# Repetir o numero aqui fazia o valor antigo (1,20s) sobrescrever o novo em silencio, e
# a pausa de 0:12 que o Julio reclamou continuou igual mesmo depois de eu "corrigir".
# Manopla duplicada e a mesma armadilha do config gerado: mexer num lugar so nao vale.
PARAMS = {"KEEP_PAUSE_RATIO": "0.45", "KEEP_PAUSE": "0.26"}


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def dur(p):
    o = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", str(p)]).stdout.strip()
    return float(o) if o else 0.0


def pausas(p, db=-30, d=0.15):
    """(inicio, duracao) de cada pausa. -v info: com -v error o ffmpeg engole o log."""
    r = sh(["ffmpeg", "-v", "info", "-i", str(p), "-af",
            f"silencedetect=noise={db}dB:d={d}", "-f", "null", "-"]).stderr
    ini = [float(x) for x in re.findall(r"silence_start: ([\d.-]+)", r)]
    dus = [float(x) for x in re.findall(r"silence_duration: ([\d.]+)", r)]
    return list(zip(ini, dus))


def energia(p, ini, d):
    """RMS dentro de uma janela: separa pausa limpa de pausa com respiro audivel."""
    r = sh(["ffmpeg", "-v", "info", "-ss", str(ini), "-t", str(d), "-i", str(p),
            "-af", "astats=metadata=1:reset=0", "-f", "null", "-"]).stderr
    m = re.findall(r"RMS level dB:\s*(-?[\d.]+|-inf)", r)
    vals = [float(x) for x in m if x != "-inf"]
    return max(vals) if vals else -99.0


def auditar(limpo, bruto=None):
    d = dur(limpo)
    ps = [(i, x) for i, x in pausas(limpo) if x < 5.0]   # ignora cauda
    longas = [x for _, x in ps if x > PAUSA_LONGA]
    problemas, info = [], {}

    info["duracao"] = round(d, 1)
    info["pausas_total"] = len(ps)
    info["pausas_longas"] = len(longas)
    info["maior_pausa"] = round(max([x for _, x in ps], default=0), 2)

    # 1) RITMO ACHATADO (o defeito do jh13)
    if d > 30 and len(longas) < MIN_PAUSAS_LONGAS:
        problemas.append(
            f"ritmo achatado: so {len(longas)} pausa(s) acima de {PAUSA_LONGA}s em "
            f"{d:.0f}s de fala (minimo {MIN_PAUSAS_LONGAS}). A fala perde a respiracao "
            "de fim de frase e soa picotada. Higienize com KEEP_PAUSE_RATIO/MAX maiores.")

    # 2) RESPIRO AUDIVEL dentro de pausa longa (o defeito ORIGINAL, que a higienizacao
    #    existe pra resolver). Mede ENERGIA, nao duracao: pausa longa e limpa e boa.
    ruidosas = []
    for ini, x in ps:
        if x >= 0.45:
            e = energia(limpo, ini + 0.05, min(x - 0.1, 1.0))
            if e > RESPIRO_DB:
                ruidosas.append((round(ini, 1), round(x, 2), round(e, 1)))
    info["pausas_com_respiro"] = ruidosas
    if ruidosas:
        problemas.append(
            f"{len(ruidosas)} pausa(s) com respiro audivel (ex: {ruidosas[:3]}). "
            "O Avatar V lipsynca a respiracao e a boca mexe no vazio.")

    # 3) FALA PRESERVADA: re-transcreve e compara palavra a palavra com o bruto.
    #    OBRIGATORIO (ordem do Julio, 17/08/2026): "esses cortes voce precisa editar com
    #    o higienizador e transcrever NOVAMENTE antes de jogar no avatar".
    #    Ele ouviu no video pronto: "em algo concreto" saiu "em algo creto". A comparacao
    #    mostrou que o corte comeu 4 palavras ("uma campanha"->"panha", "vender"->"ver",
    #    "algo" apagado). Sem esta checagem o estrago so aparece depois do avatar gerado,
    #    e ai custa job de HeyGen mais rebuild.
    if bruto:
        info["duracao_bruto"] = round(dur(bruto), 1)
        info["removido"] = round(dur(bruto) - d, 1)
        perdidas, suspeitas = comparar_transcricoes(bruto, limpo)
        info["palavras_danificadas"] = perdidas
        # Suspeitas NAO reprovam, mas ficam no relatorio: esconder divergencia seria
        # trocar um gate barulhento por um gate cego.
        info["divergencias_de_transcricao"] = suspeitas
        if perdidas:
            problemas.append(
                f"{len(perdidas)} trecho(s) de fala danificado(s) pelo corte: "
                + "; ".join(f"{o!r} virou {n!r}" for o, n in perdidas[:4])
                + ". Aumente MARGEM_FALA ou baixe SIL_DB.")
    return problemas, info


def _transcrever(caminho):
    """Parakeet e o padrao da casa; Whisper esta proibido (trava a maquina do Julio)."""
    import re as _re
    saida = Path("/tmp") / (Path(caminho).stem + ".txt")
    subprocess.run(["parakeet-mlx", str(caminho), "--output-format", "txt",
                    "--output-dir", "/tmp"], capture_output=True, text=True)
    if not saida.exists():
        return None
    txt = saida.read_text().lower()
    return _re.sub(r"[^a-zà-ú0-9 ]+", " ", txt).split()


# Um trecho so conta como DANO quando sobra menos que isso das letras do original.
# Calibrado com casos reais: dano de corte do AD13 ficou em 45% ('uma campanha'->'panha')
# e 50% ('vender'->'ver'); elisao natural da fala ficou em 64% ('vamos embora'->'vambora')
# e 86% ('toque em'->'toquem'). O corte come pedaco de palavra; a elisao junta palavras
# e preserva o miolo.
FRACAO_LETRAS_DANO = 0.60
# Trecho com menos letras que isso e ruido do transcritor, nao fala perdida. Palavra
# curta de funcao ('e', 'um', 'a') troca sozinha entre duas passadas do parakeet: no
# AD16 foi o BRUTO que inventou um 'um' que o roteiro nao tem.
MIN_LETRAS_TRECHO = 3


def comparar_transcricoes(bruto, limpo):
    """Trechos em que a fala do limpo DIVERGE do bruto (palavra comida no corte).

    Devolve (danos, suspeitas): danos reprovam, suspeitas so aparecem no relatorio.
    Comparar duas transcricoes acusa MUITA coisa que nao e corte: o parakeet re-segmenta
    quando o audio muda, e elisao natural ("vamos embora" -> "vambora") encurta sem
    perder fala. Sem separar os dois, o gate reprova audio bom e a leva inteira trava.
    """
    import difflib
    a, b = _transcrever(bruto), _transcrever(limpo)
    if not a or not b:
        return [], []
    danos, suspeitas = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if op == "equal":
            continue
        antes, depois = " ".join(a[i1:i2]), " ".join(b[j1:j2])
        letras_antes = len(antes.replace(" ", ""))
        letras_depois = len(depois.replace(" ", ""))
        if letras_depois >= letras_antes:
            continue
        if letras_antes < MIN_LETRAS_TRECHO:
            continue
        if letras_depois / letras_antes < FRACAO_LETRAS_DANO:
            danos.append((antes, depois))
        else:
            suspeitas.append((antes, depois))
    return danos, suspeitas


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    como_json = "--json" in sys.argv

    if sys.argv[1] == "--auditar":
        limpo = Path(sys.argv[2]).expanduser()
        problemas, info = auditar(limpo)
        bruto = None
    else:
        bruto = Path(sys.argv[1]).expanduser()
        if not bruto.exists():
            sys.exit(f"AUDIO: bruto nao existe: {bruto}")
        saida = (Path(sys.argv[sys.argv.index("--saida") + 1]).expanduser()
                 if "--saida" in sys.argv else bruto.with_name(bruto.stem + "_limpo.mp3"))
        env = dict(os.environ)
        env.update(PARAMS)
        print(f"higienizando com ritmo preservado ({PARAMS})...")
        r = subprocess.run([sys.executable, str(CODIGO / "higienizar_audio.py"),
                            str(bruto), str(saida)], capture_output=True, text=True, env=env)
        print(r.stdout[-400:] if r.stdout else r.stderr[-400:])
        if not saida.exists():
            sys.exit("AUDIO: higienizacao nao produziu arquivo")
        limpo = saida
        problemas, info = auditar(limpo, bruto)

    if como_json:
        print(json.dumps({"arquivo": str(limpo), "info": info,
                          "problemas": problemas}, ensure_ascii=False, indent=2))
    else:
        print(f"\n=== AUDITORIA DE AUDIO: {limpo.name} ===")
        for k, v in info.items():
            print(f"  {k}: {v}")
        if problemas:
            print("\n  >> REPROVA:")
            for p in problemas:
                print("     - " + p)
        else:
            print("\n  >> PASSA: sem respiro audivel e com ritmo preservado")
    sys.exit(1 if problemas else 0)


if __name__ == "__main__":
    main()
