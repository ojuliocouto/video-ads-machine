"""Backend parakeet-mlx: Apple Silicon, local, sem custo.

O executável é achado no PATH e, depois, nos scripts do `.venv` do repo e do Python em uso.
Nunca numa pasta cravada dentro do HOME (a do aluno não tem a do dono). Sem ele, o
backend simplesmente não está disponível e a escolha segue para o próximo.

`--chunk-duration 15 --overlap-duration 3` são obrigatórios na prática: sem eles o modelo
escorrega para o inglês e come frases em áudio longo (medido em 31/08/2026).

## Perfil "alinhamento" (W3.X, A2)

O relógio do anúncio (timeline/alinhar) é transcrito do jeito que a footage SEMPRE transcreveu: o áudio extraído
para wav 16 kHz mono e o parakeet SEM chunk, lido pela regra da footage (`footage.blocos.tokens_do_parakeet`:
tokens em qualquer profundidade, em ordem de tempo, espaço na frente abre palavra, sentença não abre). Medido no
avatar do fixture com o parakeet real: o chunk de 15/3 s desloca fronteira de bloco em até 0,16 s (16 de 52 palavras
com outro tempo, a0 de 0,62 para 0,54, fim de 17,68 para 17,84); trocar mp4 por wav e o leitor antigo pelo novo
não muda nada. O perfil "padrao" (gates, plano) segue com chunk.
"""
import json
import os
import subprocess
from pathlib import Path

from ..transcrever import monotonizar

NOME = "parakeet"
EXECUTAVEL = "parakeet-mlx"
CHUNK_S, OVERLAP_S = 15, 3
PERFIS = ("padrao", "alinhamento")
WAV_ALINHAMENTO = "av.wav"      # o nome que a footage sempre usou: o parakeet grava av.json ao lado


class ErroParakeet(RuntimeError):
    pass


# Teto de uma transcrição: sem ele, o download do modelo sem rede deixa o processo parado para sempre
# (medido em 09/10/2026: a suíte travou 30 min com o parakeet a 0% de CPU sob HOME vazio).
TETO_S = 900


def achar_executavel(amb):
    """Caminho do `parakeet-mlx` no PATH ou nos scripts do venv; None se não existe."""
    achado = amb.which(EXECUTAVEL)
    if achado:
        return str(achado)
    for pasta in amb.bins_venv:
        cand = Path(pasta) / EXECUTAVEL
        if cand.is_file() and os.access(str(cand), os.X_OK):
            return str(cand)
    return None


def disponivel(amb):
    return amb.apple_silicon and achar_executavel(amb) is not None


def palavras_da_saida(dados):
    """Junta os tokens do JSON do parakeet em palavras. Token com espaço na frente abre
    palavra nova; sem espaço continua a anterior ("per" + "de" = "perde")."""
    brutas = []
    for sentenca in dados.get("sentences") or []:
        tokens = sentenca.get("tokens") or []
        if not tokens:
            texto = str(sentenca.get("text", "")).split()
            ini, fim = float(sentenca.get("start", 0.0)), float(sentenca.get("end", 0.0))
            passo = (fim - ini) / len(texto) if texto else 0.0
            for k, w in enumerate(texto):
                brutas.append({"text": w, "start": ini + k * passo, "end": ini + (k + 1) * passo})
            continue
        abrir = True                      # a primeira palavra de cada sentença é palavra nova
        for t in tokens:
            texto = str(t.get("text", ""))
            if not texto.strip():
                abrir = True              # o espaço solto (o parakeet o emite antes de número) abre a próxima palavra
                continue
            if abrir or texto[0].isspace() or not brutas:
                brutas.append({"text": texto.strip(), "start": float(t["start"]),
                               "end": float(t["end"])})
                abrir = False
            else:
                brutas[-1]["text"] += texto.strip()
                brutas[-1]["end"] = max(brutas[-1]["end"], float(t["end"]))
    return monotonizar(brutas)


def palavras_como_a_footage(dados):
    """As palavras do JSON do parakeet pela regra da FOOTAGE antiga, que é a do relógio do anúncio. A regra mora num
    lugar só (`footage.blocos.tokens_do_parakeet`, que a footage sem timeline também usa): importada aqui, na hora,
    para o alinhamento e a footage antiga nunca lerem a mesma fala de dois jeitos."""
    from footage.blocos import tokens_do_parakeet
    return [{"text": c, "start": s, "end": e} for s, e, c in tokens_do_parakeet(dados)]


def transcrever(audio, *, amb, workdir, prompt="", idioma="pt", executar=None, perfil="padrao"):
    """O parakeet não usa prompt nem idioma (o modelo v3 é multilíngue); ficam na
    assinatura só para o contrato comum dos backends.

    `perfil`: "padrao" (o arquivo como veio, com chunk) ou "alinhamento" (wav 16 kHz mono, sem chunk, leitor da
    footage: ver o docstring do módulo)."""
    if perfil not in PERFIS:
        raise ValueError(f"perfil desconhecido: {perfil!r} (use um de {', '.join(PERFIS)})")
    exe = achar_executavel(amb)
    if exe is None:
        raise ErroParakeet("parakeet-mlx não encontrado: instale com "
                           "`python3 -m pip install parakeet-mlx`")
    audio, workdir = Path(audio), Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    rodar = executar or (lambda c: subprocess.run(c, capture_output=True, text=True, timeout=TETO_S))
    if perfil == "alinhamento":
        entrada, extra = workdir / WAV_ALINHAMENTO, []
        r = rodar(["ffmpeg", "-y", "-i", str(audio), "-vn", "-ac", "1", "-ar", "16000", str(entrada)])
        if r.returncode != 0:
            raise ErroParakeet(f"o ffmpeg não extraiu o áudio de {audio} para o alinhamento: "
                               f"{(r.stderr or r.stdout or '').strip()[-300:]}")
    else:
        entrada, extra = audio, ["--chunk-duration", str(CHUNK_S), "--overlap-duration", str(OVERLAP_S)]
    cmd = [exe, str(entrada), "--output-format", "json", "--output-dir", str(workdir), *extra]
    try:
        r = rodar(cmd)
    except subprocess.TimeoutExpired:
        raise ErroParakeet(f"parakeet-mlx passou de {TETO_S} s e foi parado. Na primeira vez ele baixa o "
                           "modelo (cerca de 1 GB): rode com rede, ou aponte HF_HOME para um cache que já tenha o modelo.")
    if r.returncode != 0:
        raise ErroParakeet(f"parakeet-mlx saiu com {r.returncode}: "
                           f"{(r.stderr or r.stdout or '').strip()[-300:]}")
    saida = workdir / f"{entrada.stem}.json"
    if not saida.is_file():
        raise ErroParakeet(f"parakeet-mlx não gerou o json esperado em {saida}")
    dados = json.loads(saida.read_text(encoding="utf-8"))
    return palavras_como_a_footage(dados) if perfil == "alinhamento" else palavras_da_saida(dados)
