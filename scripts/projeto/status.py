"""Estado do projeto do aluno (status.json) e a escrita atômica que todos os JSON do projeto usam.

Escrita atômica: o conteúdo vai para um arquivo temporário na MESMA pasta, é gravado no disco
(fsync) e só então vira o arquivo final por `os.replace` (rename). Quem lê nunca vê arquivo
pela metade, e uma falha no meio deixa o arquivo antigo intacto e nenhum temporário para trás.

status.json (sem contrato próprio; quem lê é o `vam status` e o orquestrador):

    {"versao": 1,
     "atual": {"etapa": "gate_look", "estado": "falhou", "motivo": "...", "em": "<ISO 8601>"},
     "historico": [ {mesmo formato}, ... ]}      os LIMITE_HISTORICO mais novos, do mais antigo ao mais novo

Estados: em_andamento, ok, falhou, bloqueado. `falhou` e `bloqueado` exigem motivo escrito.
"""
import json
import os
import re
import tempfile
from datetime import datetime

ESTADOS = ("em_andamento", "ok", "falhou", "bloqueado")
ESTADOS_COM_MOTIVO = ("falhou", "bloqueado")
LIMITE_HISTORICO = 500
_RE_ETAPA = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,62}$")


def instante():
    """Instante atual com fuso, em ISO 8601 (segundos)."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _sem_repeticao(pares):
    d = {}
    for k, v in pares:
        if k in d:
            raise ValueError("chave repetida no JSON: %r" % k)
        d[k] = v
    return d


def _constante(c):
    raise ValueError("valor %s não é JSON válido" % c)


def ler_json(caminho):
    """Lê um JSON recusando chave repetida, NaN e Infinity. Levanta ValueError (e
    FileNotFoundError se o arquivo não existe)."""
    with open(str(caminho), "r", encoding="utf-8") as f:
        texto = f.read()
    try:
        return json.loads(texto, object_pairs_hook=_sem_repeticao, parse_constant=_constante)
    except json.JSONDecodeError as e:
        raise ValueError("JSON quebrado: %s" % e)


def escrever_json_atomico(caminho, dados):
    """Grava `dados` em `caminho` por temporário + rename. Cria a pasta se faltar."""
    destino = os.fspath(caminho)
    pasta = os.path.dirname(os.path.abspath(destino))
    os.makedirs(pasta, exist_ok=True)
    texto = json.dumps(dados, ensure_ascii=False, indent=2) + "\n"  # falha aqui = nada foi tocado
    fd, tmp = tempfile.mkstemp(dir=pasta, prefix="." + os.path.basename(destino) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, destino)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _caminho(alvo):
    return getattr(alvo, "status_json", alvo)


def _vazio():
    return {"versao": 1, "atual": None, "historico": []}


def _estrutura_ok(s):
    return (isinstance(s, dict) and s.get("versao") == 1 and isinstance(s.get("historico"), list)
            and (s.get("atual") is None or isinstance(s.get("atual"), dict)))


def ler(alvo):
    """status.json do projeto (`alvo` é o PastasProjeto ou o caminho do arquivo).
    Sem arquivo: estrutura vazia. Arquivo ilegível: levanta ValueError."""
    p = _caminho(alvo)
    if not os.path.exists(os.fspath(p)):
        return _vazio()
    s = ler_json(p)
    if not _estrutura_ok(s):
        raise ValueError("status.json com estrutura inesperada: %s" % p)
    return s


def _ler_ou_recomecar(p):
    """Como `ler`, mas um arquivo estragado vai para status.json.corrompido (a prova fica) e o
    histórico recomeça: o status nunca pode travar o pipeline."""
    try:
        return ler(p)
    except (ValueError, OSError):
        lado = os.fspath(p) + ".corrompido"
        os.replace(os.fspath(p), lado)
        return _vazio()


def registrar(alvo, etapa, estado, motivo=None, detalhes=None, agora=None):
    """Registra uma etapa no status.json e devolve a estrutura gravada.

    `agora` existe para teste; o padrão é o instante da chamada. Levanta ValueError para etapa,
    estado ou motivo inválidos (antes de tocar em qualquer arquivo).
    """
    if not isinstance(etapa, str) or not _RE_ETAPA.match(etapa):
        raise ValueError("etapa inválida: %r (minúsculas, dígitos, _ . -)" % (etapa,))
    if estado not in ESTADOS:
        raise ValueError("estado inválido: %r (aceitos: %s)" % (estado, ", ".join(ESTADOS)))
    if motivo is not None and not isinstance(motivo, str):
        raise ValueError("motivo tem que ser texto")
    if estado in ESTADOS_COM_MOTIVO and not (motivo and motivo.strip()):
        raise ValueError("estado %r exige motivo escrito" % estado)
    p = _caminho(alvo)
    s = _ler_ou_recomecar(p) if os.path.exists(os.fspath(p)) else _vazio()
    reg = {"etapa": etapa, "estado": estado}
    if motivo:
        reg["motivo"] = motivo.strip()
    if detalhes is not None:
        reg["detalhes"] = detalhes
    reg["em"] = agora if agora is not None else instante()
    s["atual"] = reg
    s["historico"].append(reg)
    s["historico"] = s["historico"][-LIMITE_HISTORICO:]
    escrever_json_atomico(p, s)
    return s
