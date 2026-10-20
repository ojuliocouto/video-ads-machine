#!/usr/bin/env python3
"""Transcrição multiplataforma com cache por conteúdo.

Devolve SEMPRE `[{"text": str, "start": float, "end": float}]`, uma entrada por palavra,
monotônica (início não regride, fim >= início, uma palavra não invade a seguinte).

## Qual backend roda

  Nuvem (os padrões, para TUDO: voz, fala x roteiro, legenda, alinhamento, corte de take). `ORDEM_NUVEM` é a ordem
  única; `VAM_TRANSCRITOR=mistral|groq` (no `.env` ou no ambiente) põe um deles na frente. Vale o primeiro cuja
  chave existe:
  1. mistral         Voxtral Mini Transcribe, com a MISTRAL_API_KEY que o aluno criou na aula Curso → Skill.
  2. groq            `whisper-large-v3-turbo`, plano gratuito, com a GROQ_API_KEY.
  Local, OPCIONAL (NÃO é instalado pelo setup):
  3. faster_whisper  Offline: modelo `large-v3-turbo`, CPU, int8, português, VAD ligado (ver
                     `backends/faster_whisper.py`), cerca de 1,5 GB baixados no primeiro uso. Só roda se o aluno
                     instalou o pacote (`pip install faster-whisper`).

Nada pesado fica na máquina do aluno. A nuvem marca o início de algumas palavras tarde (Groq: 17% mais de 200 ms;
Mistral: 39%; o local: 6%). Quem CORTA por tempo de palavra pede `corte=True`: a Groq vai na frente da Mistral (tempo mais
preciso), a palavra ganha margem antes (0,30 s Groq, 0,40 s Mistral) e depois (0,15 s) com `ar_morto.margens_de_palavra`,
e o resultado é conferido re-transcrevendo.

Na escolha automática, se o backend da vez falha (sem internet, limite, chave recusada, resposta sem tempo por
palavra), o seguinte da ordem entra no lugar e UMA linha sai no stderr dizendo qual caiu em qual. Backend pedido pelo
nome ou por objeto nunca cai em outro. Sem nenhum, sai UMA mensagem com o que resolve (SemTranscritor).

## Cache

Chave = sha256 do CONTEÚDO do arquivo (não do caminho, do tamanho nem do mtime). O cache
fica na pasta que o chamador passa em `cache_dir` (a do projeto): este módulo não tem
padrão, de propósito, para nada cair em pasta temporária do sistema. O cache guarda o
resultado BRUTO do ASR; o glossário é aplicado depois, na saída, então trocar o glossário
não retranscreve nada. (O prompt do glossário só influencia a primeira transcrição.)
A chave NÃO inclui o backend nem o modelo: depois de trocar de motor ou de `VAM_WHISPER_MODELO`, apague a pasta
de cache (ou passe `forcar=True`) para transcrever de novo.

## Glossário

`glossario` é o dict de `_local/glossario.json` (contratos/glossario.schema.json):
  - `prompt_do_glossario` monta o prompt de vocabulário (grafias, sem as variantes);
  - `aplicar_glossario` troca as variantes declaradas pela grafia e, além disso, só os padrões fechados do
    glossário PADRÃO da skill (`projeto/glossario_padrao.py`: "Cloud Code" vira "Claude Code", "time de A" vira
    "time de IA"). O artigo "a" e qualquer outra palavra não são reescritos.

Uso:
  from audio.transcrever import transcrever
  palavras = transcrever("voz/limpo.mp3", cache_dir="projetos/x/render/cache_asr",
                         glossario=glossario)
"""
import importlib
import json
import os
import platform
import re
import shutil
import sys
from pathlib import Path

ORDEM_NUVEM = ("mistral", "groq")             # a ordem única dos backends de nuvem (a primeira chave que existe vence)
LOCAIS = ("faster_whisper",)
ORDEM = ORDEM_NUVEM + LOCAIS                  # os nomes que existem (a ordem real sai de `ordem_dos_backends`)

_RAIZ_DO_REPO = Path(__file__).resolve().parent.parent.parent

PROMPT_BASE = "Transcrição em português do Brasil."
PROMPT_MAX = 600       # o Whisper aceita ~224 tokens de prompt; folga para o português

_PONTUACAO = re.compile(r"^([^\w]*)(.*?)([^\w]*)$", re.S)


class SemTranscritor(RuntimeError):
    """Nenhum backend disponível, ou o pedido não existe nesta máquina. UMA mensagem."""


class Ambiente(object):
    """O que a escolha de backend olha: sistema, módulos importáveis e variáveis (GROQ_API_KEY, VAM_WHISPER_MODELO).

    Existe para a escolha ser testável sem tocar na máquina de quem roda o teste.
    """

    def __init__(self, sistema, arquitetura, env, which, importavel):
        self.sistema = sistema
        self.arquitetura = arquitetura
        self.env = env
        self.which = which                # nome -> caminho do executável ou None (busca no PATH)
        self.importavel = importavel      # nome do módulo -> bool

    @classmethod
    def real(cls, raiz=None):
        """A máquina de verdade. As variáveis do ambiente mandam; o `.env` da raiz do repo completa o que falta
        (é onde o aluno põe a GROQ_API_KEY)."""
        import importlib.util
        from onboarding.doctor import carregar_dotenv
        env = dict(carregar_dotenv(Path(raiz if raiz is not None else _RAIZ_DO_REPO) / ".env"))
        env.update(os.environ)
        return cls(
            sistema=platform.system(), arquitetura=platform.machine(), env=env,
            which=lambda nome: shutil.which(nome),
            importavel=lambda nome: importlib.util.find_spec(nome) is not None)


# --- palavras: forma e monotonia ------------------------------------------------------------

def monotonizar(palavras):
    """Normaliza a saída de qualquer backend para o contrato.

    Descarta texto vazio; força início não decrescente, fim >= início e fim <= início da
    próxima palavra (sem sobreposição); devolve dicts novos só com text/start/end.
    """
    saida = []
    for p in palavras:
        texto = str(p["text"]).strip()
        if not texto:
            continue
        ini = max(float(p["start"]), 0.0)
        fim = float(p["end"])
        if saida:
            ini = max(ini, saida[-1]["start"])
            saida[-1]["end"] = max(saida[-1]["start"], min(saida[-1]["end"], ini))
        saida.append({"text": texto, "start": round(ini, 3), "end": round(max(fim, ini), 3)})
    return saida


_NUMERO = re.compile(r"\d[\d.,]*$")


def normalizar_numeros(palavras):
    """Junta número e "%" que o modelo separou: "1" + "%" vira "1%" (o tempo cobre as duas). Devolve lista nova.

    Só junta quando a palavra anterior termina em dígito e a atual COMEÇA com "%" (a pontuação que vem depois,
    "%.", fica). "%" sem número antes não muda."""
    saida = []
    for p in palavras:
        texto = str(p["text"]).strip()
        if saida and texto.startswith("%") and _NUMERO.search(str(saida[-1]["text"]).strip()):
            anterior = saida[-1]
            saida[-1] = {"text": str(anterior["text"]).strip() + texto, "start": anterior["start"], "end": p["end"]}
        else:
            saida.append(dict(p))
    return saida


# --- cache ----------------------------------------------------------------------------------

def sha_do_conteudo(caminho):
    import hashlib
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def _ler_cache(arquivo, sha):
    """`(palavras, nome do backend que as fez)` guardados, ou `(None, None)`."""
    try:
        dados = json.loads(Path(arquivo).read_text(encoding="utf-8"))
        if dados.get("sha256") == sha and isinstance(dados.get("palavras"), list):
            return monotonizar(dados["palavras"]), str(dados.get("backend") or "")
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None, None


def _gravar_cache(arquivo, sha, backend, palavras):
    arquivo = Path(arquivo)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    tmp = arquivo.with_name(arquivo.name + ".tmp")
    dados = {"versao": 1, "sha256": sha, "backend": backend, "palavras": palavras}
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(str(tmp), str(arquivo))


def arquivo_de_cache(cache_dir, sha):
    """`<sha>.json` dentro da pasta de cache do projeto."""
    return Path(cache_dir) / f"{sha}.json"


# --- glossário ------------------------------------------------------------------------------

def prompt_do_glossario(glossario):
    """Prompt de vocabulário: as GRAFIAS certas, nunca as variantes erradas. Respeita
    PROMPT_MAX cortando entre termos, jamais no meio de um."""
    termos = [t["grafia"] for t in ((glossario or {}).get("termos") or []) if t.get("grafia")]
    if not termos:
        return PROMPT_BASE
    cabeca = PROMPT_BASE + " Vocabulário: "
    escolhidos = []
    for t in termos:
        candidato = cabeca + ", ".join(escolhidos + [t]) + "."
        if len(candidato) > PROMPT_MAX:
            break
        escolhidos.append(t)
    return (cabeca + ", ".join(escolhidos) + ".") if escolhidos else PROMPT_BASE


def _normal(texto):
    return _PONTUACAO.match(texto).group(2).casefold()


def _dividir_pontuacao(texto):
    m = _PONTUACAO.match(texto)
    return m.group(1), m.group(3)


def aplicar_glossario(palavras, glossario):
    """Troca as variantes DECLARADAS pela grafia e aplica o padrão da skill em padrões fechados
    (`projeto.glossario_padrao.corrigir_contexto`: "Cloud Code" -> "Claude Code", "time de A" -> "time de IA").
    A pontuação da ponta fica.

    Variante de várias palavras vence a de uma (mais longa primeiro). Quando a grafia tem
    outro número de palavras que a variante, o intervalo coberto é preservado e dividido
    em partes iguais. Devolve lista nova; não altera a de entrada.
    """
    from projeto import glossario_padrao
    resultado = _trocar_variantes(palavras, glossario)
    return glossario_padrao.corrigir_contexto(resultado, glossario)


def _trocar_variantes(palavras, glossario):
    """As variantes declaradas viram a grafia (sem o padrão por contexto)."""
    saida = [dict(p) for p in palavras]
    pares = []
    for termo in ((glossario or {}).get("termos") or []):
        for v in (termo.get("variantes") or []):
            alvo = [_normal(w) for w in v.split()]
            if alvo and all(alvo):
                pares.append((alvo, termo["grafia"]))
    if not pares:
        return saida
    pares.sort(key=lambda par: -len(par[0]))

    resultado, i = [], 0
    while i < len(saida):
        for alvo, grafia in pares:
            n = len(alvo)
            trecho = saida[i:i + n]
            if len(trecho) == n and [_normal(w["text"]) for w in trecho] == alvo:
                resultado.extend(_trocar(trecho, grafia))
                i += n
                break
        else:
            resultado.append(saida[i])
            i += 1
    return resultado


def _trocar(trecho, grafia):
    antes = _dividir_pontuacao(trecho[0]["text"])[0]
    depois = _dividir_pontuacao(trecho[-1]["text"])[1]
    novas = grafia.split()
    if len(novas) == len(trecho):
        partes = [dict(w) for w in trecho]
        for w, nova in zip(partes, novas):
            w["text"] = nova
    else:
        ini, fim = trecho[0]["start"], trecho[-1]["end"]
        passo = (fim - ini) / len(novas)
        partes = [{"text": nova, "start": round(ini + k * passo, 3),
                   "end": round(ini + (k + 1) * passo, 3)} for k, nova in enumerate(novas)]
    partes[0]["text"] = antes + partes[0]["text"]
    partes[-1]["text"] = partes[-1]["text"] + depois
    return partes


# --- escolha do backend ---------------------------------------------------------------------

def _modulo(nome):
    return importlib.import_module(f"{__package__ or 'audio'}.backends.{nome}")


PREFERIDO_NO_CORTE = "groq"       # medido: o início de palavra da Groq é mais preciso que o da Mistral (grade de 0,1 s)


def ordem_dos_backends(amb, corte=False):
    """Os nomes na ordem em que são tentados: a nuvem (`ORDEM_NUVEM`, com `VAM_TRANSCRITOR` na frente se definida) e
    depois o local. `corte=True` (passos que cortam por tempo de palavra) põe a Groq na frente da Mistral quando
    `VAM_TRANSCRITOR` não manda outra coisa: o tempo de palavra dela é mais preciso."""
    pedido = str(amb.env.get("VAM_TRANSCRITOR") or "").strip().lower()
    if not pedido:
        if corte:
            return [PREFERIDO_NO_CORTE] + [n for n in ORDEM_NUVEM if n != PREFERIDO_NO_CORTE] + list(LOCAIS)
        return list(ORDEM_NUVEM) + list(LOCAIS)
    if pedido not in ORDEM_NUVEM:
        raise SemTranscritor(f"VAM_TRANSCRITOR={pedido!r} não existe (use {' ou '.join(ORDEM_NUVEM)})")
    return [pedido] + [n for n in ORDEM_NUVEM if n != pedido] + list(LOCAIS)


def backends_disponiveis(amb=None, corte=False):
    amb = amb or Ambiente.real()
    return [n for n in ordem_dos_backends(amb, corte) if _modulo(n).disponivel(amb)]


def mensagem_sem_transcritor(amb=None):
    return ("Nenhum transcritor disponível. Ponha no arquivo .env da raiz do repo a MISTRAL_API_KEY (a mesma chave que "
            "você criou na aula Curso → Skill) ou a GROQ_API_KEY (chave GRÁTIS em console.groq.com). (O faster-whisper "
            f"local serve offline, mas é opcional: `{sys.executable} -m pip install faster-whisper`.)")


def escolher_backend(amb=None, preferido=None, corte=False):
    """Módulo do backend: o `preferido` se existir nesta máquina, senão o primeiro da ORDEM."""
    amb = amb or Ambiente.real()
    if preferido is not None:
        if preferido not in ORDEM:
            raise ValueError(f"backend desconhecido: {preferido!r} (use um de {', '.join(ORDEM)})")
        modulo = _modulo(preferido)
        if not modulo.disponivel(amb):
            raise SemTranscritor(f"O backend {preferido} não está disponível nesta máquina. "
                                 + mensagem_sem_transcritor(amb))
        return modulo
    for nome in ordem_dos_backends(amb, corte):
        modulo = _modulo(nome)
        if modulo.disponivel(amb):
            return modulo
    raise SemTranscritor(mensagem_sem_transcritor(amb))


# --- API ------------------------------------------------------------------------------------

def _candidatos(amb, backend, corte=False):
    """Os módulos a tentar, em ordem. Escolha automática: todos os disponíveis (o seguinte é a reserva do
    anterior). Pedido por nome ou por objeto: só ele."""
    if backend is None:
        achados = [m for m in (_modulo(n) for n in ordem_dos_backends(amb, corte)) if m.disponivel(amb)]
        if not achados:
            raise SemTranscritor(mensagem_sem_transcritor(amb))
        return achados
    if isinstance(backend, str):
        return [escolher_backend(amb, preferido=backend)]
    return [backend]


def _rodar(modulo, audio, amb, trabalho, prompt, idioma):
    trabalho.mkdir(parents=True, exist_ok=True)
    try:
        return monotonizar(modulo.transcrever(audio, amb=amb, workdir=trabalho, prompt=prompt, idioma=idioma))
    finally:
        shutil.rmtree(str(trabalho), ignore_errors=True)
        try:
            trabalho.parent.rmdir()          # some a pasta _trabalho se ficou vazia
        except OSError:
            pass


def transcrever_detalhado(audio, *, cache_dir, glossario=None, backend=None, amb=None, forcar=False,
                          idioma="pt", corte=False):
    """`(palavras, nome do backend)`. Palavras com tempo de `audio`; `cache_dir` é obrigatório (a pasta do projeto).

    `backend`: nome (um de ORDEM), um módulo/objeto com `NOME` e `transcrever`, ou None para a escolha
    automática (a nuvem na ordem de `ordem_dos_backends`, e o faster-whisper, se instalado, quando a nuvem falha).
    `corte=True` marca o passo que corta por tempo de palavra: a Groq vai na frente da Mistral. O nome do backend
    serve para escolher a margem de palavra do corte (`ar_morto.margens_do_ambiente`). `forcar=True` ignora o cache.
    """
    audio = Path(audio)
    if not audio.is_file():
        raise FileNotFoundError(f"áudio não encontrado: {audio}")
    amb = amb or Ambiente.real()
    cache_dir = Path(cache_dir)
    sha = sha_do_conteudo(audio)
    arquivo = arquivo_de_cache(cache_dir, sha)

    palavras, nome = (None, None) if forcar else _ler_cache(arquivo, sha)
    if palavras is None:
        candidatos = _candidatos(amb, backend, corte)
        prompt = prompt_do_glossario(glossario)
        trabalho = cache_dir / "_trabalho" / sha[:16]
        for k, modulo in enumerate(candidatos):
            try:
                palavras = _rodar(modulo, audio, amb, trabalho, prompt, idioma)
                break
            except Exception as e:
                if k + 1 < len(candidatos):
                    print(f"AUDIO: {getattr(modulo, 'NOME', 'o transcritor')} falhou ({e}); "
                          f"tentando {getattr(candidatos[k + 1], 'NOME', 'o próximo')}.", file=sys.stderr)
                    continue
                if backend is None and getattr(modulo, "NOME", "") in ORDEM_NUVEM:
                    raise SemTranscritor(
                        f"O transcritor {modulo.NOME} falhou ({e}). Confira a internet e a chave no .env "
                        "(MISTRAL_API_KEY ou GROQ_API_KEY, a da Groq é grátis em console.groq.com). "
                        f"Para trabalhar offline, instale o faster-whisper: `{sys.executable} -m pip install faster-whisper`.")
                raise
        nome = getattr(modulo, "NOME", "desconhecido")
        _gravar_cache(arquivo, sha, nome, palavras)
    return aplicar_glossario(palavras, glossario), nome


def transcrever(audio, *, cache_dir, glossario=None, backend=None, amb=None, forcar=False,
                idioma="pt", corte=False):
    """Só as palavras com tempo de `transcrever_detalhado`."""
    return transcrever_detalhado(audio, cache_dir=cache_dir, glossario=glossario, backend=backend, amb=amb,
                                 forcar=forcar, idioma=idioma, corte=corte)[0]


def main(argv=None, amb=None):
    import argparse
    ap = argparse.ArgumentParser(description="Transcreve um áudio com cache por conteúdo.")
    ap.add_argument("audio")
    ap.add_argument("--cache-dir", required=True, help="pasta de cache DO PROJETO")
    ap.add_argument("--glossario", help="caminho do _local/glossario.json")
    ap.add_argument("--backend", choices=ORDEM)
    ap.add_argument("--forcar", action="store_true")
    a = ap.parse_args(argv)
    glossario = json.loads(Path(a.glossario).read_text(encoding="utf-8")) if a.glossario else None
    try:
        palavras = transcrever(a.audio, cache_dir=a.cache_dir, glossario=glossario,
                               backend=a.backend, amb=amb, forcar=a.forcar)
    except SemTranscritor as e:
        print(str(e), file=sys.stderr)
        return 2
    print(json.dumps(palavras, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from audio.transcrever import main as _main
    sys.exit(_main())
