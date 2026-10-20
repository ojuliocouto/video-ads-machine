"""Check: a transcrição tem como rodar. O padrão é a nuvem (Mistral ou Groq), com a chave no `.env`.

A skill transcreve TUDO na nuvem: nada pesado fica na máquina do aluno. A ordem vem do `audio.transcrever`
(`ORDEM_NUVEM`, com `VAM_TRANSCRITOR` na frente se definida) e vale a primeira chave que existe:

  - MISTRAL_API_KEY (Voxtral Mini Transcribe): a mesma chave que o aluno criou na aula Curso → Skill;
  - GROQ_API_KEY (`whisper-large-v3-turbo`): plano GRATUITO, console.groq.com.

Resultado:
  - alguma chave presente e aceita: OK, e a linha diz QUAL será usada (e qual é a reserva);
  - sem chave, mas o faster-whisper está instalado (opcional, por conta do aluno): WARN, o local assume, mais lento, e
    baixa cerca de 1,5 GB no primeiro uso;
  - sem chave e sem faster-whisper: FAIL com os dois consertos, porque todo caminho precisa de transcrição;
  - todas as chaves recusadas (HTTP 401/403): WARN se o local existe, senão FAIL.

Cada chave presente passa por uma chamada leve (`GET /models`) para ver se a nuvem aceita (o `User-Agent` de navegador é
obrigatório na Groq: sem ele a Cloudflare devolve 403). Sem rede, a chave presente conta OK e o detalhe diz que não deu
para conferir. A chave nunca aparece na saída. O nome do modelo local vem do backend (`audio.backends.faster_whisper`).
"""
from ..doctor import FAIL, OK, USER_AGENT, WARN, ErroRede, Resultado

NOME = "transcritor"
URLS = {"groq": "https://api.groq.com/openai/v1/models", "mistral": "https://api.mistral.ai/v1/models"}
ROTULO = {"mistral": "Mistral (Voxtral)", "groq": "Groq (whisper-large-v3-turbo, plano gratuito)"}
COMO_CRIAR = ("ponha no arquivo .env da raiz do repo a MISTRAL_API_KEY (a mesma chave que você criou na aula Curso → "
              "Skill) ou a GROQ_API_KEY (chave GRÁTIS em console.groq.com, API Keys)")


def _local(tamb):
    """(instalado, descrição curta do local)."""
    from audio.backends import faster_whisper as FW
    modelo = FW.modelo_configurado(tamb)
    tamanho = "cerca de %s, " % FW.DOWNLOAD_APROXIMADO if modelo == FW.MODELO_PADRAO else ""
    return FW.disponivel(tamb), "faster-whisper local (modelo %s, baixa %sno primeiro uso)" % (modelo, tamanho)


def _conferir(amb, nome):
    """(status http ou None se sem rede, erro)."""
    chave = (amb.env.get(nome.upper() + "_API_KEY") or "").strip()
    try:
        status, _corpo = amb.http_get(URLS[nome], headers={"Authorization": "Bearer " + chave,
                                                           "Accept": "application/json",
                                                           "User-Agent": USER_AGENT}, timeout=15)
    except ErroRede as erro:
        return None, erro
    return status, None


def checar(amb):
    from audio import transcrever as T
    tamb = amb.para_transcritor()
    try:
        nuvem = [n for n in T.backends_disponiveis(tamb) if n in T.ORDEM_NUVEM]
    except T.SemTranscritor as erro:
        return Resultado(NOME, FAIL, str(erro), "use VAM_TRANSCRITOR=mistral ou VAM_TRANSCRITOR=groq (ou apague a variável)")
    instalado, local = _local(tamb)
    if not nuvem:
        if instalado:
            return Resultado(NOME, WARN, "sem MISTRAL_API_KEY nem GROQ_API_KEY: transcrevendo no " + local,
                             COMO_CRIAR + " (a nuvem é o padrão e não pesa no PC)")
        return Resultado(NOME, FAIL, "sem MISTRAL_API_KEY nem GROQ_API_KEY: nada transcreve (a Groq é gratuita)",
                         COMO_CRIAR)
    recusadas = []
    for nome in nuvem:
        status, erro = _conferir(amb, nome)
        if status in (401, 403):
            recusadas.append("%s recusou a chave (HTTP %d)" % (nome, status))
            continue
        resto = [n for n in nuvem if n != nome and n not in recusadas]
        reserva = ("; reserva: " + ", ".join(resto)) if resto else ""
        if instalado:
            reserva += "; reserva offline: " + local
        if erro is not None:
            return Resultado(NOME, OK, "vai usar %s: chave presente, não consegui conferir agora (%s)%s"
                             % (ROTULO[nome], erro, reserva))
        return Resultado(NOME, OK, "vai usar %s: chave aceita%s" % (ROTULO[nome], reserva))
    detalhe = "; ".join(recusadas)
    conserto = "gere uma chave nova: " + COMO_CRIAR
    if instalado:
        return Resultado(NOME, WARN, detalhe + "; transcrevendo no " + local, conserto)
    return Resultado(NOME, FAIL, detalhe, conserto)
