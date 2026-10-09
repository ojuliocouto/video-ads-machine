"""ASR do gravado: tudo passa por `audio.transcrever` e pelo glossário do projeto.

O pipeline de origem tinha um cliente Groq escrito à mão em nove arquivos, cada um com o
vocabulário do cliente dentro do prompt e um cache próprio. Aqui há UM caminho:

  - o backend é o da máquina (`audio.transcrever` escolhe parakeet, faster-whisper ou Groq);
  - o prompt de vocabulário e a correção de grafia vêm do glossário do aluno (nunca cravados);
  - o cache é por CONTEÚDO do trecho recortado, na pasta do projeto (`cache_dir`).

Duas regras medidas que este módulo cumpre:

  - BORDA de palavra pede um backend que não infle o tempo. A Groq infla token (um "Mas" de
    7,3 s escondeu uma pausa de 5,4 s), então `exigir_borda=True` recusa a Groq e diz o comando
    para instalar o parakeet-mlx ou o faster-whisper.
  - Trecho isolado faz o ASR completar a frase que falta e inventar repetição; a janela precisa
    de contexto dos dois lados. Quem decide a janela é o gate; aqui só se recorta com margem.

Falha do ASR nunca vira texto vazio calado: `ErroDeASR` na API de função, e o marcador
`FALHA: motivo` no `falas_entregues.json`, que os gates de texto recusam com saída 2.

  Leitor(cache_dir, glossario=None, backend=None, amb=None)
    .palavras(arquivo, exigir_borda=False)         palavras com tempo, peça inteira
    .palavras_do_trecho(arquivo, ini, fim)         idem, só o trecho; tempo no eixo do arquivo
    .texto(arquivo, ini, fim)                      texto do trecho
    .texto_da_peca(arquivo)                        texto da peça inteira
    .fala_ou_falha(arquivo)                        texto, ou "FALHA: motivo"
"""
import json
import subprocess
import tempfile
from pathlib import Path

from audio import transcrever as _t
from gravado.veredito import InsumoInvalido

FALHA = "FALHA"
MARGEM_S = 0.1

_DETERMINISTICO = ["-map_metadata", "-1", "-fflags", "+bitexact", "-flags:a", "+bitexact"]


class ErroDeASR(RuntimeError):
    """A transcrição não saiu. A mensagem traz o motivo do backend."""


def falhou(texto):
    """True para texto vazio ou para o marcador de falha (`FALHA: ...` ou o antigo `[falha]`)."""
    t = (texto or "").strip()
    if not t:
        return True
    return t.startswith(FALHA) or t.casefold().startswith("[falha")


def texto_das_palavras(palavras):
    return " ".join(str(p["text"]) for p in palavras).strip()


def janelas(duracao, janela=8.0, passo=6.0):
    """Janelas sobrepostas (início, fim) que cobrem `duracao`: nenhuma emenda cai na borda de
    duas janelas e passa sem ser lida."""
    saida, a = [], 0.0
    while True:
        b = min(a + janela, duracao)
        saida.append((a, b))
        if b >= duracao - 1e-9:
            return saida
        a += passo


def _ffmpeg_para_wav(origem, destino, ini=None, dur=None):
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin"]
    if ini:
        cmd += ["-ss", str(float(ini))]
    cmd += ["-i", str(origem)]
    if dur is not None:
        cmd += ["-t", str(float(dur))]
    cmd += ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", *_DETERMINISTICO, str(destino)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise ErroDeASR("ffmpeg não encontrado: instale com `brew install ffmpeg`")
    if r.returncode != 0:
        raise ErroDeASR("não consegui preparar o áudio de %s: %s" % (origem, r.stderr.strip()[-250:]))


def recortar(audio, ini, fim, destino, margem=MARGEM_S):
    """Recorta [ini - margem, fim + margem] em wav 16 kHz mono. Devolve o início real do recorte
    (o `ini - margem`, nunca abaixo de zero), que é o deslocamento para voltar ao eixo do arquivo."""
    a = max(0.0, float(ini) - margem)
    _ffmpeg_para_wav(audio, destino, ini=a, dur=(float(fim) + margem) - a)
    return a


def checar_borda(amb=None, backend=None):
    """Nome do backend que vai rodar, desde que dê tempo de palavra confiável. A Groq não dá."""
    amb = amb or _t.Ambiente.real()
    pedido = getattr(backend, "NOME", backend)
    try:
        modulo = _t.escolher_backend(amb, preferido=pedido)
    except (_t.SemTranscritor, ValueError) as e:
        raise ErroDeASR(str(e))
    if modulo.NOME == "groq":
        raise ErroDeASR(
            "a Groq infla o tempo de palavra (um token de 7 s escondeu uma pausa de 5 s) e a borda de "
            "palavra precisa de tempo real. Instale um transcritor local com "
            "`python3 -m pip install parakeet-mlx` (Apple Silicon) ou "
            "`python3 -m pip install faster-whisper`.")
    return modulo.NOME


class Leitor(object):
    """Lê o que se fala em um arquivo ou trecho. Cache por conteúdo em `cache_dir`."""

    def __init__(self, cache_dir, glossario=None, backend=None, amb=None):
        self.cache_dir = Path(cache_dir)
        self.glossario = glossario
        self.backend = backend
        self.amb = amb

    def _transcrever(self, wav):
        try:
            return _t.transcrever(wav, cache_dir=self.cache_dir, glossario=self.glossario,
                                  backend=self.backend, amb=self.amb)
        except ErroDeASR:
            raise
        except Exception as e:                    # SemTranscritor, ErroGroq, ErroParakeet, rede...
            raise ErroDeASR(str(e) if isinstance(e, _t.SemTranscritor) else "%s: %s" % (type(e).__name__, e))

    def palavras(self, audio, exigir_borda=False):
        """Palavras com tempo da peça inteira. `exigir_borda` recusa a Groq."""
        if exigir_borda:
            checar_borda(self.amb, self.backend)
        with tempfile.TemporaryDirectory(prefix="vam-asr-") as pasta:
            wav = Path(pasta) / "peca.wav"
            _ffmpeg_para_wav(audio, wav)
            return self._transcrever(wav)

    def palavras_do_trecho(self, audio, ini, fim, margem=MARGEM_S):
        """Palavras do trecho, com o tempo já no eixo do arquivo original."""
        with tempfile.TemporaryDirectory(prefix="vam-asr-") as pasta:
            wav = Path(pasta) / "trecho.wav"
            deslocamento = recortar(audio, ini, fim, wav, margem)
            palavras = self._transcrever(wav)
        return [{"text": p["text"], "start": round(p["start"] + deslocamento, 3),
                 "end": round(p["end"] + deslocamento, 3)} for p in palavras]

    def texto(self, audio, ini, fim, margem=MARGEM_S):
        return texto_das_palavras(self.palavras_do_trecho(audio, ini, fim, margem))

    def texto_da_peca(self, arquivo):
        return texto_das_palavras(self.palavras(arquivo))

    def fala_ou_falha(self, arquivo):
        """O texto da peça, ou `FALHA: motivo`. Nunca levanta: o marcador é o contrato do JSON."""
        try:
            texto = self.texto_da_peca(arquivo)
        except ErroDeASR as e:
            return "%s: %s" % (FALHA, e)
        return texto if texto else "%s: o ASR não devolveu nenhuma palavra" % FALHA


def falas_dos_arquivos(arquivos, leitor):
    """{nome do arquivo sem extensão: texto ou "FALHA: motivo"}, em ordem alfabética."""
    return {Path(a).stem: leitor.fala_ou_falha(a) for a in sorted(arquivos, key=lambda x: Path(x).name)}


def carregar_falas(caminho):
    """Lê o `falas_entregues.json`. Insumo inválido (saída 2) se não existe, não é JSON, não é
    objeto, está vazio, ou alguma peça veio sem texto ou com o marcador de falha do ASR."""
    caminho = Path(caminho)
    if not caminho.is_file():
        raise InsumoInvalido("não achei %s: gere as falas das peças com `python3 scripts/gravado/auditar.py`"
                             % caminho)
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except ValueError as e:
        raise InsumoInvalido("%s não é JSON válido: %s" % (caminho, e))
    if not isinstance(dados, dict):
        raise InsumoInvalido("%s: o JSON deve ser um objeto {peça: texto}" % caminho)
    if not dados:
        raise InsumoInvalido("%s está vazio: nenhuma peça foi transcrita" % caminho)
    for peca, texto in dados.items():
        if not isinstance(texto, str) or falhou(texto):
            raise InsumoInvalido("a fala de %s não existe ou o ASR falhou (%.60r): rode o auditar de novo"
                                 % (peca, texto))
    return dados
