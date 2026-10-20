"""Backend faster-whisper: o transcritor OFFLINE e OPCIONAL, igual no Mac, no Windows e no Linux.

O padrão da skill é a Groq (nuvem). Este backend só roda se o aluno instalou o pacote por conta própria
(`pip install faster-whisper`; o setup NÃO instala) e só entra quando falta a GROQ_API_KEY ou a Groq falha.

Modelo `large-v3-turbo`, CPU, int8, português, tempo por palavra e VAD ligado. A disputa medida em 20/10/2026
(WER 5,2% no roteiro exato, o melhor tempo de palavra entre os motores locais, roda offline) escolheu esta
combinação. O modelo pesa cerca de 1,5 GB e é baixado UMA vez, no primeiro uso, para o cache do Hugging Face.

O nome do modelo mora numa constante só (`MODELO_PADRAO`). Quem quer outro modelo define a variável de ambiente
`VAM_WHISPER_MODELO` (por exemplo `small`, mais leve e pior) no `.env` ou no terminal.

Armadilhas medidas que este backend respeita:
  - `condition_on_previous_text=False` sempre. Com `initial_prompt` ligado ele REPETE um
    parágrafo anterior no lugar do trecho atual, o que é pior que perder palavra: sai
    plausível.
  - `vad_filter=True`: sem ele a primeira palavra sai em 0,00 s quando a fala começa em 0,67 s. Com o filtro
    sai em 0,30 s (ainda cedo, mas bem mais perto).
  - o modelo escreve "1 %" com espaço. `normalizar_numeros` (em `transcrever.py`, vale para todo backend) junta número
    e "%" em "1%".
  - nome de marca em inglês sai errado ("Claude" vira "Cloud" em todos os motores). O glossário do aluno
    (`_local/glossario.json`, termos e variantes) corrige a grafia depois; o prompt dele ajuda o modelo antes.
"""
from pathlib import Path

from ..transcrever import monotonizar, normalizar_numeros   # normalizar_numeros: reexportado, o teste lê daqui

NOME = "faster_whisper"
MODELO_PADRAO = "large-v3-turbo"
VARIAVEL_DO_MODELO = "VAM_WHISPER_MODELO"            # o nome também aparece literal em `modelo_configurado` (a varredura do .env.example lê literal)
COMPUTE = "int8"
IDIOMA_PADRAO = "pt"
DOWNLOAD_APROXIMADO = "1,5 GB"          # o large-v3-turbo; um modelo menor baixa menos


class ErroFasterWhisper(RuntimeError):
    """O modelo não carregou (quase sempre: primeira vez sem internet). UMA mensagem, com o motivo."""


def disponivel(amb):
    return bool(amb.importavel("faster_whisper"))


def modelo_configurado(amb):
    """O modelo que vai rodar: `VAM_WHISPER_MODELO` se definida e não vazia, senão `MODELO_PADRAO`."""
    return (amb.env.get("VAM_WHISPER_MODELO") or "").strip() or MODELO_PADRAO


def _fabrica_real(amb):
    def fabrica():
        from faster_whisper import WhisperModel
        return WhisperModel(modelo_configurado(amb), device="cpu", compute_type=COMPUTE)
    return fabrica


def _palavras(segmentos):
    brutas = []
    for seg in segmentos:
        com_tempo = [w for w in (getattr(seg, "words", None) or [])
                     if str(w.word).strip() and w.start is not None and w.end is not None]
        if com_tempo:
            brutas.extend({"text": w.word, "start": w.start, "end": w.end} for w in com_tempo)
            continue
        texto = str(seg.text).split()
        if not texto:
            continue
        passo = (seg.end - seg.start) / len(texto)
        brutas.extend({"text": w, "start": seg.start + k * passo, "end": seg.start + (k + 1) * passo}
                      for k, w in enumerate(texto))
    return monotonizar(normalizar_numeros(brutas))


def transcrever(audio, *, amb, workdir, prompt="", idioma="pt", fabrica_modelo=None):
    modelo_nome = modelo_configurado(amb)
    try:
        modelo = (fabrica_modelo or _fabrica_real(amb))()
    except Exception as e:                       # sem rede na 1ª vez, disco cheio, modelo com nome errado
        raise ErroFasterWhisper(
            f"não consegui carregar o modelo {modelo_nome} do faster-whisper ({type(e).__name__}: {e}). "
            f"Na primeira vez ele baixa cerca de {DOWNLOAD_APROXIMADO} da internet: confira a conexão e o espaço "
            "em disco, e rode de novo.")
    # Idioma SEMPRE fixo: sem ele o modelo detecta sozinho e pode escorregar para o inglês. Vazio, None ou "auto"
    # viram pt; só um código explícito muda o idioma.
    idioma = idioma if idioma and str(idioma).lower() != "auto" else IDIOMA_PADRAO
    segmentos, _info = modelo.transcribe(
        str(Path(audio)), language=idioma, initial_prompt=prompt or None,
        condition_on_previous_text=False, word_timestamps=True, vad_filter=True)
    return _palavras(segmentos)
