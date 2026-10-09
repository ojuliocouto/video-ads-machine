"""Backend parakeet-mlx: Apple Silicon, local, sem custo.

O executável é achado no PATH e, depois, nos scripts do `.venv` do repo e do Python em uso.
Nunca numa pasta cravada dentro do HOME (a do aluno não tem a do dono). Sem ele, o
backend simplesmente não está disponível e a escolha segue para o próximo.

`--chunk-duration 15 --overlap-duration 3` são obrigatórios na prática: sem eles o modelo
escorrega para o inglês e come frases em áudio longo (medido em 31/08/2026).
"""
import json
import os
import subprocess
from pathlib import Path

from ..transcrever import monotonizar

NOME = "parakeet"
EXECUTAVEL = "parakeet-mlx"
CHUNK_S, OVERLAP_S = 15, 3


class ErroParakeet(RuntimeError):
    pass


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
                continue
            if abrir or texto[0].isspace() or not brutas:
                brutas.append({"text": texto.strip(), "start": float(t["start"]),
                               "end": float(t["end"])})
                abrir = False
            else:
                brutas[-1]["text"] += texto.strip()
                brutas[-1]["end"] = max(brutas[-1]["end"], float(t["end"]))
    return monotonizar(brutas)


def transcrever(audio, *, amb, workdir, prompt="", idioma="pt", executar=None):
    """O parakeet não usa prompt nem idioma (o modelo v3 é multilíngue); ficam na
    assinatura só para o contrato comum dos backends."""
    exe = achar_executavel(amb)
    if exe is None:
        raise ErroParakeet("parakeet-mlx não encontrado: instale com "
                           "`python3 -m pip install parakeet-mlx`")
    audio, workdir = Path(audio), Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    cmd = [exe, str(audio), "--output-format", "json", "--output-dir", str(workdir),
           "--chunk-duration", str(CHUNK_S), "--overlap-duration", str(OVERLAP_S)]
    r = (executar or (lambda c: subprocess.run(c, capture_output=True, text=True)))(cmd)
    if r.returncode != 0:
        raise ErroParakeet(f"parakeet-mlx saiu com {r.returncode}: "
                           f"{(r.stderr or r.stdout or '').strip()[-300:]}")
    saida = workdir / f"{audio.stem}.json"
    if not saida.is_file():
        raise ErroParakeet(f"parakeet-mlx não gerou o json esperado em {saida}")
    return palavras_da_saida(json.loads(saida.read_text(encoding="utf-8")))
