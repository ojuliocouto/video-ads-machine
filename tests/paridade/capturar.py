#!/usr/bin/env python3
"""Captura da paridade (W0.3): roda o motor num sandbox e devolve o que ele produziu.

Para que serve: a W2 quebra `gen_ad_v2.py` e `produzir_roteiro.py` em módulos. A única
prova de que o comportamento não mudou é rodar o motor ANTES e DEPOIS sobre a mesma
mídia e comparar o que sai. Este módulo faz a captura; `normalizar.py` tira o que muda
de run para run (caminhos, nomes de tempdir); os `test_paridade_*.py` comparam com o
golden guardado fora do repo.

## O que é capturado (chaves de `Captura.arquivos`)

  overlay/{index.html, index_overlay.html, prancha.json, janelas_split.json}
                     gen_ad_v2 sobre o fixture, 1a rodada (sem footage pronta)
  overlay_1x1/...    o mesmo no template quadrado
  overlay_convergido/...
                     2a rodada: o gen_ad_v2 lê o `_ritmo.json` que a footage deixou
                     (o "relógio da footage", defeito 20 do plano). Continua SEM timeline: é a
                     prova de que o caminho antigo segue funcionando até a W5.A
  footage/{ritmo.json, timing.json, video.framemd5, audio.md5}
                     produzir_roteiro sobre o fixture (CAP=0, BAKE=0, como o build), SEM timeline
  timeline/{timeline.json, alinhamento.json}
                     W3.A: timeline/construir.py (uma transcrição, o relógio único). Quando o
                     motor tem `scripts/timeline/`, `overlay/` e `overlay_1x1/` leem esta timeline
  timeline/footage/{ritmo.json, timing.json, video.framemd5, audio.md5}
                     a mesma footage LENDO a timeline (VAM_TIMELINE): tem que sair igual à `footage/`
  argv/<fase>.jsonl  argv normalizado de TODO subprocess, na ordem, por fase

Motor sem `scripts/timeline/` (o commit base do golden antigo): as etapas da timeline não rodam e o
overlay roda como sempre rodou, então o golden antigo continua reproduzível.

## Como o motor roda

  - numa CÓPIA do motor (scripts/, templates/, fonts/) em pasta temporária: é o que
    permite aplicar um mutante sem sujar o repo, e o `caminhos.RAIZ` fica no sandbox;
  - `VAM_ESTADO`/`VAM_DADOS` apontam para o sandbox; HOME falso; TMPDIR no sandbox;
  - `VAM_PARALELO=1`: a footage renderiza segmentos num pool de threads e a ordem dos
    subprocessos seria aleatória; com 1 worker a ordem é determinística;
  - `VAM_SPLIT_BIAS=0.30`: fixa o enquadramento do split. Sem isso o motor chama
    `medir_enquadramento.py` a partir do DADOS (defeito 2 do plano: no clone limpo a
    medição falha calada e cai em 0,30). 0,30 é exatamente o valor desse fallback, então
    o golden vale antes e depois do conserto da W2.B. A medição em si NÃO é coberta;
  - `PYTHONHASHSEED=0` e `PYTHONUTF8=1`: o motor lê arquivo sem `encoding=` e usa
    `hash()` em nome de arquivo; sem isso o resultado dependeria do locale e da semente;
  - ASR gravado: `~/.local/bin/parakeet-mlx` (e um do PATH) e `node_modules/.bin/
    hyperframes transcribe` são stubs que devolvem a saída REAL do parakeet sobre o
    avatar do fixture. Sem rede, sem modelo de 1 GB, sem o binário do HyperFrames. O que
    o `hyperframes render` faria (MOV com alpha) NÃO é coberto: não há Chromium aqui.
    O do parakeet só devolve a fala gravada quando chamado do jeito em que ela foi gravada
    (wav, sem chunk); de outro jeito ela vem deslocada (W3.X A2, ver `stub_parakeet`).

## Uso

    python3 tests/paridade/capturar.py gerar-golden --commit <sha do commit base> --midia "$VAM_PARIDADE_MIDIA"
    python3 tests/paridade/capturar.py comparar --midia "$VAM_PARIDADE_MIDIA"      # working tree deste repo

O golden fica em `$VAM_PARIDADE_GOLDEN` (padrão `$VAM_PARIDADE_MIDIA/golden`), ou em `--golden <pasta>`. Um
rebase deliberado (a W3.A muda o overlay de propósito) nasce em outra pasta e só vira o padrão depois de o
diff ser revisado.
    python3 tests/paridade/capturar.py selar-fixture "$VAM_PARIDADE_MIDIA"         # recalcula o MANIFESTO da fixture

`gerar-golden --commit` extrai o commit com `git archive`: o golden nasce do commit, nunca de
um working tree sujo. Sem `--commit`, usa o `--motor` como está e recusa raiz com alteração em
scripts/, templates/ ou fonts/ (salvo `--forcar`).
"""
import argparse
import atexit
import difflib
import hashlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
try:
    from . import normalizar as N  # importado como tests.paridade.capturar
except ImportError:  # rodando como script: python3 tests/paridade/capturar.py ...
    sys.path.insert(0, str(AQUI))
    import normalizar as N  # noqa: E402

AD = "ad99v2"
LOOK = "espuma_roxa"
LK = "espuma"          # nome do look nos arquivos de config 
VERSAO_GOLDEN = 1
ETAPAS_TODAS = ("timeline", "overlay", "overlay_1x1", "footage", "timeline_footage", "overlay_convergido")
ETAPAS_DA_TIMELINE = ("overlay", "overlay_1x1", "timeline_footage")   # leem a timeline quando o motor tem
SUFIXO_FOOTAGE_TIMELINE = "_pelatimeline"     # nome da saída da footage que roda pela timeline
# A fase dela é `timeline_footage` e nunca `footage_...`: comparar por prefixo `argv/footage` pegaria as duas.

# stubs: devolvem a transcrição REAL gravada em fixture/asr/
# W3.X A2: o stub do parakeet NÃO devolve o mesmo JSON a qualquer chamada. A fala gravada (asr/av.json) é a do
# parakeet sobre o wav 16 kHz, sem chunk: é o que ele devolve quando chamado desse jeito. Chamado de outro (um mp4,
# ou com --chunk-duration), devolve a mesma fala com todo tempo DESLOCADO de DESLOCAMENTO_FORA_DO_JEITO s, o que o
# parakeet real fez no avatar do fixture com chunk de 15/3 s (fronteira 0,16 s adiante). Assim a footage pela
# timeline só sai igual à antiga se a timeline transcrever do mesmo jeito: a paridade não cega de novo.
DESLOCAMENTO_FORA_DO_JEITO = 0.16

_STUB_PARAKEET = """#!/usr/bin/env python3
# Stub do parakeet-mlx (paridade): devolve a saída real gravada em <output-dir>/<nome>.json quando chamado do
# jeito da footage antiga (um .wav, sem --chunk-duration); de outro jeito, a mesma fala com os tempos deslocados.
import json, os, sys
args = sys.argv[1:]
entrada = args[0]
saida = args[args.index("--output-dir") + 1] if "--output-dir" in args else "."
with open(os.path.join("__ASR__", "av.json"), encoding="utf-8") as f:
    dados = json.load(f)
if not entrada.endswith(".wav") or "--chunk-duration" in args:
    def mexe(o):
        if isinstance(o, dict):
            for k in ("start", "end"):
                if isinstance(o.get(k), (int, float)):
                    o[k] = round(o[k] + __DESLOCA__, 3)
            for v in o.values():
                mexe(v)
        elif isinstance(o, list):
            for v in o:
                mexe(v)
    mexe(dados)
nome = os.path.splitext(os.path.basename(entrada))[0]
with open(os.path.join(saida, nome + ".json"), "w", encoding="utf-8") as f:
    json.dump(dados, f)
print("stub parakeet: " + nome)
"""


def stub_parakeet(asr):
    """O texto do stub do parakeet-mlx, lendo a fala gravada da pasta `asr` (fixture/asr)."""
    return _STUB_PARAKEET.replace("__ASR__", str(asr)).replace("__DESLOCA__", repr(DESLOCAMENTO_FORA_DO_JEITO))

_STUB_HYPERFRAMES = """#!/bin/sh
# Stub do hyperframes (paridade): so entende `transcribe`; devolve a transcricao real gravada.
if [ "$1" = "transcribe" ]; then
  dir="."; prev=""
  for a in "$@"; do
    if [ "$prev" = "-d" ] || [ "$prev" = "--dir" ]; then dir="$a"; fi
    prev="$a"
  done
  cp "__ASR__/transcript.json" "$dir/transcript.json"
  echo '{"ok":true,"engine":"parakeet","stub":true}'
  exit 0
fi
echo "stub do hyperframes (paridade): so existe 'transcribe'; o render nao e coberto" >&2
exit 3
"""


class CapturaFalhou(RuntimeError):
    """Uma etapa do motor saiu com erro: a captura não vale."""


class MidiaInvalida(RuntimeError):
    """A pasta de mídia não tem o que a paridade precisa."""


# --------------------------------------------------------------------------------------
# mídia
# --------------------------------------------------------------------------------------

def midia_definida():
    """Path da mídia se VAM_PARIDADE_MIDIA aponta para uma pasta que existe; senão None."""
    v = os.environ.get("VAM_PARIDADE_MIDIA")
    if v and Path(v).is_dir():
        return Path(v)
    return None


def exigir_midia():
    """Para os testes: devolve a pasta de mídia ou PULA com o motivo."""
    import pytest

    m = midia_definida()
    if m is None:
        pytest.skip("VAM_PARIDADE_MIDIA não definida (ou não é uma pasta): a paridade precisa "
                    "da mídia de teste fora do repo. Use: VAM_PARIDADE_MIDIA=<pasta> bash "
                    "scripts/dev/testar_limpo.sh --paridade")
    return m


def raiz_do_repo():
    return AQUI.parent.parent


def ler_manifesto_fixture(midia):
    p = Path(midia) / "fixture" / "MANIFESTO.json"
    if not p.is_file():
        raise MidiaInvalida(f"falta {p}: a pasta de mídia não é a fixture da paridade")
    return json.loads(p.read_text(encoding="utf-8"))


def conferir_fixture(midia):
    """Confere o sha256 de cada arquivo da fixture contra o MANIFESTO. Erro claro, não diff."""
    man = ler_manifesto_fixture(midia)
    ruins = []
    for rel, esperado in sorted(man["arquivos"].items()):
        p = Path(midia) / "fixture" / rel
        if not p.is_file():
            ruins.append(f"{rel}: ausente")
        elif _sha256_arquivo(p) != esperado:
            ruins.append(f"{rel}: sha256 diferente do MANIFESTO (fixture alterada)")
    if ruins:
        raise MidiaInvalida("fixture da paridade inconsistente:\n  " + "\n  ".join(ruins))
    return man


def _sha256_arquivo(p):
    import hashlib

    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


# --------------------------------------------------------------------------------------
# sandbox
# --------------------------------------------------------------------------------------

class Sandbox:
    def __init__(self, base):
        self.base = Path(base)
        self.raiz = self.base / "raiz"
        self.estado = self.base / "estado"
        self.dados = self.base / "dados"
        self.home = self.base / "home"
        self.bin = self.base / "bin"
        self.tmp = self.base / "tmp"
        self.pysite = self.base / "pysite"
        self.log = self.base / "argv.jsonl"
        self.scripts = self.raiz / "scripts"
        self.midia = None

    def tokens(self):
        return N.construir_tokens(tmp=self.tmp, midia=self.midia, estado=self.estado,
                                  dados=self.dados, raiz=self.raiz, home=self.home)


PASTAS_DO_MOTOR = ("scripts", "templates", "fonts")
# Também roda, quando o motor tem: a timeline (W3.A) valida no contrato ao ser construída e lida. O commit
# base do golden antigo não tem a pasta, e por isso ela não entra em PASTAS_DO_MOTOR.
PASTAS_DE_APOIO = ("contratos",)


def _nome_ignorado(nome):
    """Não vai para a cópia do motor: bytecode e os testes (não fazem parte do que roda)."""
    return (nome == "__pycache__" or nome.endswith(".pyc")
            or (nome.startswith("test_") and nome.endswith(".py")))


def _ignorar_copia(_dir, nomes):
    return [n for n in nomes if _nome_ignorado(n)]


def impressao_motor(raiz):
    """sha256 do que realmente roda (scripts/, templates/, fonts/), sem bytecode nem testes.

    Dois motores com a mesma impressão produzem a mesma captura; é a chave da memória.
    """
    h = hashlib.sha256()
    raiz = Path(raiz)
    for nome in PASTAS_DO_MOTOR + PASTAS_DE_APOIO:
        base = raiz / nome
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            rel = p.relative_to(raiz)
            if p.is_file() and not any(_nome_ignorado(parte) for parte in rel.parts):
                h.update(rel.as_posix().encode("utf-8") + b"\0")
                h.update(p.read_bytes())
                h.update(b"\0")
    return h.hexdigest()


class CommitAusente(RuntimeError):
    """O commit pedido não existe neste clone (clone raso, export sem .git)."""


def exportar_commit(raiz_repo, commit, destino):
    """Extrai scripts/, templates/ e fonts/ de `commit` para `destino` (git archive), mais contratos/
    quando o commit tem."""
    no_commit = set((_git(raiz_repo, "ls-tree", "--name-only", commit) or "").splitlines())
    pastas = list(PASTAS_DO_MOTOR) + [p for p in PASTAS_DE_APOIO if p in no_commit]
    r = subprocess.run(["git", "-C", str(raiz_repo), "archive", "--format=tar", commit, *pastas],
                       capture_output=True)
    if r.returncode != 0:
        raise CommitAusente(f"git archive {commit} falhou: {r.stderr.decode('utf-8', 'replace')[-300:]}")
    Path(destino).mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tf:
        try:
            tf.extractall(destino, filter="data")
        except TypeError:       # Python anterior ao parametro `filter`
            tf.extractall(destino)
    return Path(destino)


def _aplicar_mutacao(raiz, mutacao):
    """mutacao = (regex, substituição). Vale para todos os .py de scripts/ da CÓPIA do motor.

    Tem que casar EXATAMENTE uma vez em todo o conjunto: casar zero é "o código mudou de
    lugar" (atualize o mutante) e casar mais de uma é mutante ambíguo. Procurar na árvore
    inteira, e não num arquivo fixo, é o que deixa o mutante valer depois que a W2 mover a
    constante para outro módulo.
    """
    padrao, subst = mutacao
    rx = re.compile(padrao)
    achados = []
    for p in sorted((Path(raiz) / "scripts").rglob("*.py")):
        n = len(rx.findall(p.read_text(encoding="utf-8")))
        if n:
            achados.append((p, n))
    total = sum(n for _, n in achados)
    if total != 1:
        onde = ", ".join(f"{p.relative_to(raiz)} ({n}x)" for p, n in achados) or "nenhum arquivo"
        raise CapturaFalhou(f"mutante inaplicável: o padrão {padrao!r} casa {total} vez(es) em {onde}; "
                            "precisa casar exatamente 1 (o código mudou de lugar? atualize o mutante)")
    alvo = achados[0][0]
    alvo.write_text(rx.sub(subst, alvo.read_text(encoding="utf-8"), count=1), encoding="utf-8")


_SANDBOXES = set()     # sandboxes vivos; o que sobrar ao sair do processo é removido
_MANTIDOS = set()      # sandboxes de captura que FALHOU: ficam para inspeção


def _limpar_sandboxes():
    for base in _SANDBOXES - _MANTIDOS:
        shutil.rmtree(base, ignore_errors=True)


atexit.register(_limpar_sandboxes)


def montar_sandbox(motor_raiz, midia, mutacao=None):
    motor_raiz, midia = Path(motor_raiz), Path(midia)
    base = tempfile.mkdtemp(prefix="vam-paridade-")
    _SANDBOXES.add(os.path.realpath(base))
    sb = Sandbox(os.path.realpath(base))
    sb.midia = midia
    for pasta in (sb.raiz, sb.estado, sb.dados / "inputs", sb.dados / "output", sb.home / ".local" / "bin",
                  sb.bin, sb.tmp, sb.pysite):
        pasta.mkdir(parents=True, exist_ok=True)
    for nome in PASTAS_DO_MOTOR + PASTAS_DE_APOIO:
        origem = motor_raiz / nome
        if origem.is_dir():
            shutil.copytree(origem, sb.raiz / nome, ignore=_ignorar_copia)
    if mutacao:
        _aplicar_mutacao(sb.raiz, mutacao)
    shutil.copy(AQUI / "sitecustomize.py", sb.pysite / "sitecustomize.py")

    asr = (midia / "fixture" / "asr").resolve()
    _gravar_exec(sb.bin / "parakeet-mlx", stub_parakeet(asr))
    _gravar_exec(sb.home / ".local" / "bin" / "parakeet-mlx", stub_parakeet(asr))
    (sb.raiz / "node_modules" / ".bin").mkdir(parents=True, exist_ok=True)
    _gravar_exec(sb.raiz / "node_modules" / ".bin" / "hyperframes",
                 _STUB_HYPERFRAMES.replace("__ASR__", str(asr)))
    _materializar_antigo(sb, midia)
    return sb


def _gravar_exec(caminho, texto):
    caminho.write_text(texto, encoding="utf-8")
    caminho.chmod(0o755)


def _substituir(texto, sb):
    return (texto.replace("@MIDIA@", str(Path(sb.midia) / "fixture" / "midia"))
            .replace("@DADOS@", str(sb.dados)).replace("@ESTADO@", str(sb.estado)))


def _materializar_antigo(sb, midia):
    """Escreve o formato ANTIGO (leva, inserts, config) no sandbox, com os caminhos reais."""
    fx = Path(midia) / "fixture"
    inputs = sb.dados / "inputs"
    shutil.copy(fx / "midia" / "avatar_18s.mp4", inputs / f"{AD}_{LOOK}_avatar.mp4")
    for nome in (f"{AD}_leva.txt", f"{AD}_inserts.json"):
        (inputs / nome).write_text(_substituir((fx / "antigo" / nome).read_text(encoding="utf-8"), sb),
                                   encoding="utf-8")
    cfgs = sb.estado / "configs"
    cfgs.mkdir(parents=True, exist_ok=True)
    nome_cfg = f"{AD}_{LK}.json"
    (cfgs / nome_cfg).write_text(_substituir((fx / "antigo" / nome_cfg).read_text(encoding="utf-8"), sb),
                                 encoding="utf-8")
    ren = sb.estado / "render-reel-editorial"
    ren.mkdir(parents=True, exist_ok=True)
    shutil.copy(fx / "midia" / "logo.png", ren / "logo.png")


def _env(sb, extra=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("VAM_")}
    try:
        import site

        userbase = os.environ.get("PYTHONUSERBASE") or site.getuserbase()
    except Exception:
        userbase = os.environ.get("PYTHONUSERBASE", "")
    env.update({
        "HOME": str(sb.home),
        "TMPDIR": str(sb.tmp),
        "PATH": os.pathsep.join([str(sb.bin), env.get("PATH", "/usr/bin:/bin")]),
        "PYTHONPATH": str(sb.pysite),
        "PYTHONHASHSEED": "0",
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "VAM_ESTADO": str(sb.estado),
        "VAM_DADOS": str(sb.dados),
        "VAM_PARALELO": "1",
        "VAM_SPLIT_BIAS": "0.30",
        "VAM_PARIDADE_LOG": str(sb.log),
    })
    if userbase:
        env["PYTHONUSERBASE"] = userbase
    env.update(extra or {})
    return env


def _marcar_fase(sb, fase):
    with open(sb.log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"fase": fase}) + "\n")


def _rodar(sb, cmd, *, cwd, extra_env=None):
    r = subprocess.run([str(c) for c in cmd], cwd=str(cwd), env=_env(sb, extra_env),
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        cauda = (r.stdout + r.stderr)[-1800:]
        raise CapturaFalhou(f"etapa falhou (saída {r.returncode}): {' '.join(str(c) for c in cmd)}\n{cauda}")
    return r


# --------------------------------------------------------------------------------------
# etapas do motor (espelham o build_composite.build, sem o render do overlay)
# --------------------------------------------------------------------------------------

def _config_overlay(sb, sufixo, formato, rotulo, timeline=None):
    base = json.loads((sb.estado / "configs" / f"{AD}_{LK}.json").read_text(encoding="utf-8"))
    workdir = sb.estado / f"render-{AD}-{LK}{sufixo}-ovl{rotulo}"
    cfg = dict(base)
    cfg["speed"] = 1.0
    cfg["out_dir"] = str(workdir)
    cfg["format"] = formato
    if timeline:
        cfg["timeline"] = str(timeline)
    caminho = sb.estado / f"_cfg_{AD}_{LK}{sufixo}{rotulo}.json"
    caminho.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return caminho, workdir


def motor_tem_timeline(sb):
    """O motor do sandbox já tem o relógio único (W3.A)?"""
    return (sb.scripts / "timeline" / "construir.py").is_file()


def caminho_timeline(sb):
    return sb.dados / "output" / f"{AD}_{LOOK}_timeline.json"


def rodar_timeline(sb):
    """timeline/construir.py: UMA transcrição (o stub do parakeet) e a timeline.json. Devolve o caminho."""
    _marcar_fase(sb, "timeline")
    inputs = sb.dados / "inputs"
    destino = caminho_timeline(sb)
    _rodar(sb, [sys.executable, sb.scripts / "timeline" / "construir.py",
                "--avatar", inputs / f"{AD}_{LOOK}_avatar.mp4", "--roteiro", inputs / f"{AD}_leva.txt",
                "--inserts", inputs / f"{AD}_inserts.json", "--config", sb.estado / "configs" / f"{AD}_{LK}.json",
                "--timeline", destino], cwd=sb.raiz)
    return destino


def rodar_overlay(sb, fase, *, formato="9x16", rotulo="", timeline=None):
    """gen_ad_v2 + strip_overlay. Devolve a pasta de saída (workdir)."""
    _marcar_fase(sb, fase)
    sufixo = "" if formato == "9x16" else "_1x1"
    cfg, workdir = _config_overlay(sb, sufixo, formato, rotulo, timeline)
    _rodar(sb, [sys.executable, sb.scripts / "gen_ad_v2.py", cfg], cwd=sb.raiz)
    _rodar(sb, [sys.executable, Path(__file__).resolve(), "--strip", sb.scripts, workdir / "index.html"],
           cwd=sb.raiz)
    return workdir


def rodar_footage(sb, timeline=None):
    """produzir_roteiro com o mesmo ambiente que o build_composite monta (e, com `timeline`, lendo ela)."""
    _marcar_fase(sb, "timeline_footage" if timeline else "footage")
    inputs = sb.dados / "inputs"
    saida = f"{AD}_{LOOK}_footage_1x{SUFIXO_FOOTAGE_TIMELINE if timeline else ''}.mp4"
    extra = {
        "VAM_AVATAR": str(inputs / f"{AD}_{LOOK}_avatar.mp4"),
        "VAM_ROTEIRO": str(inputs / f"{AD}_leva.txt"),
        "VAM_INSERTS_JSON": str(inputs / f"{AD}_inserts.json"),
        "VAM_BAKE_LETTERING": "0",
        "CAP": "0",
        "VAM_OUT": saida,
    }
    if timeline:
        extra["VAM_TIMELINE"] = str(timeline)
    _rodar(sb, [sys.executable, sb.scripts / "produzir_roteiro.py"], cwd=sb.dados, extra_env=extra)
    return sb.dados / "output" / saida


def _saida_ffmpeg(args):
    r = subprocess.run(["ffmpeg", "-v", "error", *[str(a) for a in args]], capture_output=True, text=True)
    if r.returncode != 0:
        raise CapturaFalhou(f"ffmpeg falhou ao medir a footage: {r.stderr[-600:]}")
    return r.stdout


def framemd5_video(arquivo):
    """framemd5 dos quadros decodificados. A linha `#software` (versão da libavformat) sai:
    ela muda com o ffmpeg sem que nenhum quadro mude."""
    bruto = _saida_ffmpeg(["-i", arquivo, "-map", "0:v:0", "-f", "framemd5", "-"])
    return "".join(l + "\n" for l in bruto.splitlines() if not l.startswith("#software"))


def md5_audio(arquivo):
    return _saida_ffmpeg(["-i", arquivo, "-map", "0:a:0", "-f", "md5", "-"]).strip()


def versao_ffmpeg():
    r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
    return (r.stdout.splitlines() or ["ffmpeg ?"])[0]


# --------------------------------------------------------------------------------------
# captura
# --------------------------------------------------------------------------------------

class Captura:
    """O que o motor produziu: `arquivos` {chave: texto normalizado} e metadados."""

    def __init__(self):
        self.arquivos = {}
        self.meta = {}

    def hashes(self):
        return {k: N.sha256_texto(v) for k, v in sorted(self.arquivos.items())}


def _ler(workdir, nome, tokens):
    return N.normalizar_texto(Path(workdir, nome).read_text(encoding="utf-8"), tokens)


def _coletar_overlay(cap, prefixo, workdir, tokens):
    for nome in ("index.html", "index_overlay.html", "prancha.json", "janelas_split.json"):
        cap.arquivos[f"{prefixo}/{nome}"] = _ler(workdir, nome, tokens)


def _coletar_argv(cap, sb):
    bruto = sb.log.read_text(encoding="utf-8") if sb.log.exists() else ""
    por_fase, fase = {}, "sem_fase"
    for reg in N.normalizar_jsonl(bruto, sb.tokens()):
        if "fase" in reg:
            fase = reg["fase"]
            continue
        por_fase.setdefault(fase, []).append(reg)
    for fase, regs in por_fase.items():
        cap.arquivos[f"argv/{fase}.jsonl"] = N.serializar_jsonl(regs)


def capturar(motor_raiz, midia, *, etapas=ETAPAS_TODAS, mutacao=None):
    """Roda as etapas pedidas num sandbox novo e devolve a `Captura`.

    `etapas` é um subconjunto de ETAPAS_TODAS; `overlay_convergido` exige `footage`.
    """
    etapas = tuple(etapas)
    desconhecidas = set(etapas) - set(ETAPAS_TODAS)
    if desconhecidas:
        raise ValueError(f"etapas desconhecidas: {sorted(desconhecidas)}")
    if "overlay_convergido" in etapas and "footage" not in etapas:
        raise ValueError("overlay_convergido lê a saída da footage: peça 'footage' junto")
    conferir_fixture(midia)
    sb = montar_sandbox(motor_raiz, midia, mutacao)
    try:
        cap = _executar_etapas(sb, etapas)
    except CapturaFalhou as e:
        _MANTIDOS.add(str(sb.base))
        raise CapturaFalhou(f"{e}\n(sandbox mantido para inspeção em {sb.base})") from None
    shutil.rmtree(sb.base, ignore_errors=True)
    return cap


def _coletar_footage(cap, prefixo, sb, foot, tokens):
    nome = Path(foot).stem
    cap.arquivos[f"{prefixo}/ritmo.json"] = N.normalizar_texto(
        (sb.dados / "output" / f"{nome}_ritmo.json").read_text(encoding="utf-8"), tokens)
    cap.arquivos[f"{prefixo}/timing.json"] = N.normalizar_texto(
        (sb.dados / "output" / "timing.json").read_text(encoding="utf-8"), tokens)
    cap.arquivos[f"{prefixo}/video.framemd5"] = framemd5_video(foot)
    cap.arquivos[f"{prefixo}/audio.md5"] = md5_audio(foot) + "\n"


def _executar_etapas(sb, etapas):
    tokens = sb.tokens()
    cap = Captura()
    cap.meta = {"ffmpeg": versao_ffmpeg(), "python": platform.python_version()}
    tl = None
    if motor_tem_timeline(sb) and ("timeline" in etapas or any(e in etapas for e in ETAPAS_DA_TIMELINE)):
        tl = rodar_timeline(sb)
        for nome, arq in (("timeline.json", tl), ("alinhamento.json", tl.with_name(f"{AD}_{LOOK}_alinhamento.json"))):
            cap.arquivos[f"timeline/{nome}"] = N.normalizar_texto(arq.read_text(encoding="utf-8"), tokens)
    if "overlay" in etapas:
        _coletar_overlay(cap, "overlay", rodar_overlay(sb, "overlay", timeline=tl), tokens)
    if "overlay_1x1" in etapas:
        _coletar_overlay(cap, "overlay_1x1", rodar_overlay(sb, "overlay_1x1", formato="1x1", timeline=tl), tokens)
    if "footage" in etapas:
        _coletar_footage(cap, "footage", sb, rodar_footage(sb), tokens)
    if "timeline_footage" in etapas and tl is not None:
        _coletar_footage(cap, "timeline/footage", sb, rodar_footage(sb, timeline=tl), tokens)
    if "overlay_convergido" in etapas:
        _coletar_overlay(cap, "overlay_convergido",
                         rodar_overlay(sb, "overlay_convergido", rotulo="-conv"), tokens)
    _coletar_argv(cap, sb)
    return cap


_MEMO = {}


def capturar_memo(motor_raiz, midia, *, etapas=ETAPAS_TODAS, mutacao=None):
    """`capturar` com memória, chaveada pelo CONTEÚDO do motor (não pelo caminho): os testes de
    overlay e de footage dividem o mesmo run, e o commit base reaproveita a captura do working
    tree quando os dois são idênticos."""
    chave = (impressao_motor(motor_raiz), str(Path(midia).resolve()), tuple(etapas), mutacao)
    if chave not in _MEMO:
        _MEMO[chave] = capturar(motor_raiz, midia, etapas=etapas, mutacao=mutacao)
    return _MEMO[chave]


# --------------------------------------------------------------------------------------
# golden
# --------------------------------------------------------------------------------------

def pasta_golden(midia):
    """`$VAM_PARIDADE_GOLDEN` quando definida; senão `<mídia>/golden`."""
    v = os.environ.get("VAM_PARIDADE_GOLDEN")
    return Path(v) if v else Path(midia) / "golden"


def _git(raiz, *args):
    r = subprocess.run(["git", "-C", str(raiz), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def estado_git(motor_raiz):
    """(commit, sujo) do motor. sujo = há alteração em scripts/, templates/ ou fonts/."""
    commit = _git(motor_raiz, "rev-parse", "HEAD")
    sujo = _git(motor_raiz, "status", "--porcelain", "--", *PASTAS_DO_MOTOR, *PASTAS_DE_APOIO)
    return commit, bool(sujo)


def gravar_golden(cap, midia, motor_raiz, *, forcar=False, commit=None):
    """Grava o golden. Com `commit`, o motor veio desse commit (git archive): nunca é sujo."""
    if commit:
        sujo = False
    else:
        commit, sujo = estado_git(motor_raiz)
    if sujo and not forcar:
        raise CapturaFalhou("o motor tem alteração não commitada em scripts/, templates/ ou fonts/: "
                            "o golden tem que nascer de um commit (use --forcar para ignorar)")
    destino = pasta_golden(midia)
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)
    for chave, texto in cap.arquivos.items():
        p = destino / chave
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")
    (destino / "HASHES.json").write_text(json.dumps(cap.hashes(), indent=2, sort_keys=True) + "\n",
                                         encoding="utf-8")
    manifesto = {
        "formato": VERSAO_GOLDEN,
        "commit_motor": commit,
        "motor_sujo": sujo,
        "ffmpeg": cap.meta.get("ffmpeg"),
        "python": cap.meta.get("python"),
        "plataforma": platform.platform(),
        "fixture": ler_manifesto_fixture(midia)["arquivos"],
    }
    (destino / "MANIFESTO.json").write_text(json.dumps(manifesto, indent=2, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
    return destino


def ler_golden(midia):
    destino = pasta_golden(midia)
    if not (destino / "HASHES.json").is_file():
        raise MidiaInvalida(f"golden ausente em {destino}: gere com `capturar.py gerar-golden` "
                            "a partir do commit base")
    hashes = json.loads((destino / "HASHES.json").read_text(encoding="utf-8"))
    arquivos = {k: (destino / k).read_text(encoding="utf-8") for k in hashes}
    manifesto = json.loads((destino / "MANIFESTO.json").read_text(encoding="utf-8"))
    return arquivos, hashes, manifesto


def _visao_humana(chave, texto):
    """Texto para MOSTRAR no diff (a igualdade é decidida pelo sha256 do original).

    Um registro de argv é uma linha JSON de 2 mil caracteres; no diff unificado isso vira
    "linha diferente" sem dizer onde. Aqui cada argumento ganha a sua linha e cada filtro do
    ffmpeg é quebrado em `;`, então o diff aponta o número que mudou.
    """
    if not chave.endswith(".jsonl"):
        return texto
    saida = []
    for n, linha in enumerate(texto.splitlines(), 1):
        try:
            reg = json.loads(linha)
        except ValueError:
            saida.append(linha)
            continue
        saida.append(f"== comando {n}" + (f" (cwd {reg['cwd']})" if reg.get("cwd") else ""))
        for arg in reg.get("argv", []):
            partes = arg.split(";") if len(arg) > 80 and ";" in arg else [arg]
            for i, parte in enumerate(partes):
                saida.append(("    " if i else "  ") + parte + (";" if i < len(partes) - 1 else ""))
    return "\n".join(saida) + "\n"


def comparar(atual, golden_arquivos, *, prefixos, max_linhas=40):
    """Diferenças (lista de textos) entre a captura e o golden nas chaves com esses prefixos.

    Vazia = paridade. Compara por sha256 do texto normalizado; o diff unificado é só para
    o humano. Chave que existe de um lado e não do outro também é diferença.
    """
    def seleciona(d):
        return {k for k in d if any(k == p or k.startswith(p) for p in prefixos)}

    diffs = []
    chaves = seleciona(atual) | seleciona(golden_arquivos)
    for chave in sorted(chaves):
        if chave not in golden_arquivos:
            diffs.append(f"{chave}: existe na captura e não no golden")
        elif chave not in atual:
            diffs.append(f"{chave}: existe no golden e não na captura")
        elif N.sha256_texto(atual[chave]) != N.sha256_texto(golden_arquivos[chave]):
            dif = list(difflib.unified_diff(_visao_humana(chave, golden_arquivos[chave]).splitlines(),
                                            _visao_humana(chave, atual[chave]).splitlines(),
                                            "golden", "atual", lineterm="", n=1))
            corte = "\n".join(dif[:max_linhas])
            resto = f"\n... (+{len(dif) - max_linhas} linhas)" if len(dif) > max_linhas else ""
            diffs.append(f"{chave}: sha256 diferente\n{corte}{resto}")
    return diffs


def comparar_sem_ordem(atual, golden_arquivos, *, chaves, max_linhas=8):
    """Compara cada chave como MULTICONJUNTO de linhas: mesmos comandos, ordem livre.

    A ordem estrita (`comparar`) depende de `VAM_PARALELO=1` ser honrado pela footage; este
    é o teste que continua valendo se a ordem dos subprocessos mudar de propósito.
    """
    from collections import Counter

    diffs = []
    for chave in chaves:
        a = Counter(atual.get(chave, "").splitlines())
        g = Counter(golden_arquivos.get(chave, "").splitlines())
        if a == g:
            continue
        sobra, falta = list((a - g).elements()), list((g - a).elements())
        trecho = lambda xs: "\n".join("    " + x[:240] for x in xs[:max_linhas])  # noqa: E731
        diffs.append(f"{chave}: {len(sobra)} linha(s) a mais e {len(falta)} a menos que o golden\n"
                     f"  a mais:\n{trecho(sobra)}\n  a menos:\n{trecho(falta)}")
    return diffs


def conferir_toolchain(manifesto_golden):
    """Diferença de ffmpeg entre o golden e a máquina atual (texto) ou None se igual."""
    golden, atual = manifesto_golden.get("ffmpeg"), versao_ffmpeg()
    if golden != atual:
        return f"golden gerado com [{golden}], esta máquina tem [{atual}]"
    return None


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

def _modo_strip(scripts_dir, html):
    """Roda `build_composite.strip_overlay` sobre o index.html, dentro do sandbox."""
    sys.path.insert(0, str(scripts_dir))
    import build_composite

    build_composite.strip_overlay(Path(html))
    return 0


def selar_fixture(midia):
    """Recalcula o sha256 de cada arquivo da fixture e grava no MANIFESTO.json.

    Mantém as demais chaves do MANIFESTO (origem, comandos usados para montar a fixture).
    Roda depois de montar ou alterar a fixture de propósito; o golden precisa ser gerado
    de novo (a fixture dele muda junto).
    """
    raiz = Path(midia) / "fixture"
    arquivos = {}
    for sub in ("midia", "antigo", "novo", "asr"):
        for p in sorted((raiz / sub).rglob("*")):
            if p.is_file() and not p.name.startswith("."):
                arquivos[p.relative_to(raiz).as_posix()] = _sha256_arquivo(p)
    alvo = raiz / "MANIFESTO.json"
    man = json.loads(alvo.read_text(encoding="utf-8")) if alvo.is_file() else {}
    man["arquivos"] = arquivos
    alvo.write_text(json.dumps(man, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return man


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--strip":
        return _modo_strip(argv[1], argv[2])
    if argv and argv[0] == "selar-fixture":
        m = os.environ.get("VAM_PARIDADE_MIDIA") if len(argv) < 2 else argv[1]
        man = selar_fixture(m)
        print(f"{len(man['arquivos'])} arquivos selados em {m}/fixture/MANIFESTO.json")
        return 0
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nome in ("gerar-golden", "comparar"):
        p = sub.add_parser(nome)
        p.add_argument("--motor", default=str(raiz_do_repo()), help="raiz do repo com scripts/ templates/ fonts/")
        p.add_argument("--midia", default=os.environ.get("VAM_PARIDADE_MIDIA"),
                       help="pasta da fixture (padrão: VAM_PARIDADE_MIDIA)")
        p.add_argument("--golden", help="pasta do golden (padrão: VAM_PARIDADE_GOLDEN ou <mídia>/golden)")
        if nome == "gerar-golden":
            p.add_argument("--forcar", action="store_true")
            p.add_argument("--commit", help="gera de ESTE commit do repo do --motor (git archive), "
                                            "sem depender do working tree. Forma recomendada.")
    args = ap.parse_args(argv)
    if not args.midia:
        ap.error("falta --midia (ou VAM_PARIDADE_MIDIA)")
    if args.golden:
        os.environ["VAM_PARIDADE_GOLDEN"] = str(Path(args.golden).resolve())
    commit_completo = None
    motor = args.motor
    if args.cmd == "gerar-golden" and args.commit:
        commit_completo = _git(args.motor, "rev-parse", "--verify", args.commit + "^{commit}")
        if not commit_completo:
            ap.error(f"commit {args.commit} não existe em {args.motor}")
        motor = exportar_commit(args.motor, commit_completo, tempfile.mkdtemp(prefix="vam-base-"))
        atexit.register(shutil.rmtree, str(motor), True)
    cap = capturar(motor, args.midia)
    if args.cmd == "gerar-golden":
        destino = gravar_golden(cap, args.midia, motor, forcar=args.forcar, commit=commit_completo)
        print(f"golden gravado em {destino}" + (f" (commit {commit_completo})" if commit_completo else ""))
        for k, h in cap.hashes().items():
            print(f"  {h[:16]}  {k}")
        return 0
    golden, _hashes, _man = ler_golden(args.midia)
    diffs = comparar(cap.arquivos, golden, prefixos=("overlay", "footage", "argv", "timeline"))
    for d in diffs:
        print(d)
    print("PARIDADE OK" if not diffs else f"PARIDADE QUEBRADA: {len(diffs)} diferença(s)")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
