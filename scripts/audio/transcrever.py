#!/usr/bin/env python3
"""Transcrição multiplataforma com cache por conteúdo.

Devolve SEMPRE `[{"text": str, "start": float, "end": float}]`, uma entrada por palavra,
monotônica (início não regride, fim >= início, uma palavra não invade a seguinte).

## Qual backend roda (a primeira que existir na máquina)

  1. parakeet      Apple Silicon (Darwin + arm64) e o executável `parakeet-mlx` no PATH ou
                   nos scripts do `.venv`. Nunca num caminho cravado.
  2. faster_whisper  qualquer máquina onde o módulo `faster_whisper` importa.
  3. groq          a variável GROQ_API_KEY está definida (API de nuvem, pagamento por uso).

Sem nenhum dos três, sai UMA mensagem com o comando que resolve (SemTranscritor).

## Cache

Chave = sha256 do CONTEÚDO do arquivo (não do caminho, do tamanho nem do mtime). O cache
fica na pasta que o chamador passa em `cache_dir` (a do projeto): este módulo não tem
padrão, de propósito, para nada cair em pasta temporária do sistema. O cache guarda o
resultado BRUTO do ASR; o glossário é aplicado depois, na saída, então trocar o glossário
não retranscreve nada. (O prompt do glossário só influencia a primeira transcrição.)

## Glossário

`glossario` é o dict de `_local/glossario.json` (contratos/glossario.schema.json):
  - `prompt_do_glossario` monta o prompt de vocabulário (grafias, sem as variantes);
  - `aplicar_glossario` troca SÓ as variantes declaradas pela grafia. Nada fora do
    glossário é reescrito.

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
import sysconfig
from pathlib import Path

ORDEM = ("parakeet", "faster_whisper", "groq")

PROMPT_BASE = "Transcrição em português do Brasil."
PROMPT_MAX = 600       # o Whisper aceita ~224 tokens de prompt; folga para o português

_RAIZ_DO_REPO = Path(__file__).resolve().parent.parent.parent
_PONTUACAO = re.compile(r"^([^\w]*)(.*?)([^\w]*)$", re.S)


class SemTranscritor(RuntimeError):
    """Nenhum backend disponível, ou o pedido não existe nesta máquina. UMA mensagem."""


class Ambiente(object):
    """O que a escolha de backend olha: sistema, arquitetura, PATH, módulos e variáveis.

    Existe para a escolha ser testável sem tocar na máquina de quem roda o teste.
    """

    def __init__(self, sistema, arquitetura, env, which, importavel, bins_venv=()):
        self.sistema = sistema
        self.arquitetura = arquitetura
        self.env = env
        self.which = which                # nome -> caminho do executável ou None (busca no PATH)
        self.importavel = importavel      # nome do módulo -> bool
        self.bins_venv = tuple(Path(b) for b in bins_venv)

    @property
    def apple_silicon(self):
        return self.sistema == "Darwin" and self.arquitetura == "arm64"

    @classmethod
    def real(cls):
        import importlib.util
        bins = []
        for b in (Path(sys.executable).parent, Path(sysconfig.get_path("scripts") or "."),
                  _RAIZ_DO_REPO / ".venv" / "bin"):
            if b not in bins:
                bins.append(b)
        return cls(
            sistema=platform.system(), arquitetura=platform.machine(), env=dict(os.environ),
            which=lambda nome: shutil.which(nome),
            importavel=lambda nome: importlib.util.find_spec(nome) is not None,
            bins_venv=bins)


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


# --- cache ----------------------------------------------------------------------------------

def sha_do_conteudo(caminho):
    import hashlib
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def _ler_cache(arquivo, sha):
    try:
        dados = json.loads(Path(arquivo).read_text(encoding="utf-8"))
        if dados.get("sha256") == sha and isinstance(dados.get("palavras"), list):
            return monotonizar(dados["palavras"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def _gravar_cache(arquivo, sha, backend, palavras):
    arquivo = Path(arquivo)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    tmp = arquivo.with_name(arquivo.name + ".tmp")
    tmp.write_text(json.dumps({"versao": 1, "sha256": sha, "backend": backend,
                               "palavras": palavras}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(str(tmp), str(arquivo))


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
    """Troca só as variantes DECLARADAS pela grafia. A pontuação da ponta fica.

    Variante de várias palavras vence a de uma (mais longa primeiro). Quando a grafia tem
    outro número de palavras que a variante, o intervalo coberto é preservado e dividido
    em partes iguais. Devolve lista nova; não altera a de entrada.
    """
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


def backends_disponiveis(amb=None):
    amb = amb or Ambiente.real()
    return [n for n in ORDEM if _modulo(n).disponivel(amb)]


def mensagem_sem_transcritor(amb):
    if amb.apple_silicon:
        instalar = f"{sys.executable} -m pip install parakeet-mlx"
    else:
        instalar = f"{sys.executable} -m pip install faster-whisper"
    return (f"Nenhum transcritor disponível. Instale um com `{instalar}` "
            "(ou defina GROQ_API_KEY para usar a Groq).")


def escolher_backend(amb=None, preferido=None):
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
    for nome in ORDEM:
        modulo = _modulo(nome)
        if modulo.disponivel(amb):
            return modulo
    raise SemTranscritor(mensagem_sem_transcritor(amb))


# --- API ------------------------------------------------------------------------------------

def transcrever(audio, *, cache_dir, glossario=None, backend=None, amb=None, forcar=False,
                idioma="pt"):
    """Palavras com tempo de `audio`. `cache_dir` é obrigatório (a pasta do projeto).

    `backend`: nome (um de ORDEM), um módulo/objeto com `NOME` e `transcrever`, ou None
    para a escolha automática. `forcar=True` ignora o cache.
    """
    audio = Path(audio)
    if not audio.is_file():
        raise FileNotFoundError(f"áudio não encontrado: {audio}")
    amb = amb or Ambiente.real()
    cache_dir = Path(cache_dir)
    sha = sha_do_conteudo(audio)
    arquivo = cache_dir / f"{sha}.json"

    palavras = None if forcar else _ler_cache(arquivo, sha)
    if palavras is None:
        if backend is None or isinstance(backend, str):
            modulo = escolher_backend(amb, preferido=backend)
        else:
            modulo = backend
        trabalho = cache_dir / "_trabalho" / sha[:16]
        trabalho.mkdir(parents=True, exist_ok=True)
        try:
            bruto = modulo.transcrever(audio, amb=amb, workdir=trabalho,
                                       prompt=prompt_do_glossario(glossario), idioma=idioma)
        finally:
            shutil.rmtree(str(trabalho), ignore_errors=True)
            try:
                trabalho.parent.rmdir()          # some a pasta _trabalho se ficou vazia
            except OSError:
                pass
        palavras = monotonizar(bruto)
        _gravar_cache(arquivo, sha, getattr(modulo, "NOME", "desconhecido"), palavras)
    return aplicar_glossario(palavras, glossario)


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
