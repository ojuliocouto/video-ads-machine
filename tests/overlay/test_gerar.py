"""overlay.gerar: o orquestrador, o wrapper de 40 linhas e a paridade nos ramos que a fixture não cobre.

Duas partes.

1. Sem mídia (rápido): importar `overlay.gerar` (e todo módulo do pacote) não executa nada, o
   `gen_ad_v2.py` virou um wrapper de até 40 linhas com a mesma CLI, e o que os testes antigos
   importavam dele continua lá.

2. Com mídia (`midia_real` + `lento`): o diferencial. A paridade da W0.3 roda UM cenário (o da
   fixture). O `gen_ad_v2.py` tem ramos que ele não exercita: dur_max, imagem estática, fundo
   claro (footage e arquivo-fonte), relógio da footage, look fechado, texto próprio, hook
   punch, CTA em tela dividida, aceleração, erros. Aqui cada ramo vira um CENÁRIO (a fala da
   fixture reagrupada em blocos diferentes, com outros inserts e outras flags) e o mesmo
   cenário roda no motor do COMMIT BASE do golden (`git archive`) e no motor deste working
   tree. Têm que sair: o mesmo `index.html`, o mesmo `index_overlay.html`, a mesma
   `prancha.json`, as mesmas `janelas_split.json`, o mesmo argv de TODO subprocess, o mesmo
   stdout e a mesma mensagem de erro. Mais sementes aleatórias: reagrupamentos e flags
   sorteados, para pegar o ramo em que ninguém pensou.

   O resultado do motor base é guardado em `$VAM_PARIDADE_MIDIA/golden_variantes/<commit>/`
   (fora do repo), então só a primeira rodada paga os dois motores.

3. Sem mídia, com o git: a equivalência FUNÇÃO POR FUNÇÃO. O trecho do `main` original que cada
   módulo herdou é extraído do blob do `gen_ad_v2.py` antes da quebra (`ORIGINAL_BLOB`), embrulhado
   numa função e comparado com o módulo novo em centenas de entradas aleatórias (inclusive as de
   borda, que nenhum cenário de mídia alcança): resultado, mensagem de erro e stdout iguais. É o
   que prova os ramos que a paridade não exercita (chips ligado, vão de tela vazia, adiamento da
   pilha, corte em duas na fronteira).

   Rodar só esta parte:
       VAM_PARIDADE_MIDIA=<pasta> bash scripts/dev/testar_limpo.sh --paridade -k diferencial
"""
import ast
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import collections
import contextlib
import copy
import io
import math

import pytest

import build_timeline
import ritmo
from overlay import (brolls as B, chips as CH, cta as CTA, hook as K, layout_texto as LT, legendas as LG,
                     letterings as LE, spans as S, tela_vazia as TV, transcricao as T)
from tests.paridade import capturar as C
from tests.paridade import normalizar as N

RAIZ = Path(__file__).resolve().parents[2]
MODULOS = ("transcricao", "spans", "hook", "brolls", "letterings", "layout_texto", "fundo_claro",
           "legendas", "cta", "tela_vazia", "chips", "html_injecao", "prancha_export", "gerar")


# ==============================================================================================
# 1. sem mídia
# ==============================================================================================

def test_o_pacote_tem_os_14_modulos_do_plano():
    for nome in MODULOS:
        assert (RAIZ / "scripts" / "overlay" / f"{nome}.py").is_file(), nome


def test_importar_o_pacote_nao_executa_nada(tmp_path):
    """Nenhum subprocess, nenhum arquivo escrito, nenhuma saída: so definicoes."""
    codigo = textwrap.dedent("""
        import os, subprocess, sys
        sys.path.insert(0, %r)

        def boom(*a, **k):
            raise AssertionError("subprocess no import")

        subprocess.Popen = boom
        subprocess.run = boom
        import overlay.gerar
        for nome in %r:
            __import__("overlay." + nome)
        print("IMPORTOU", sorted(os.listdir(".")))
    """) % (str(RAIZ / "scripts"), MODULOS)
    r = subprocess.run([sys.executable, "-c", codigo], cwd=str(tmp_path), capture_output=True,
                       text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "IMPORTOU []"


def test_gen_ad_v2_e_um_wrapper_de_ate_40_linhas():
    caminho = RAIZ / "scripts" / "gen_ad_v2.py"
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    assert len(linhas) <= 40, f"{len(linhas)} linhas"
    arvore = ast.parse("\n".join(linhas))
    defs = [n for n in ast.walk(arvore) if isinstance(n, ast.FunctionDef)]
    assert defs == [], "o wrapper nao define funcao: so chama overlay.gerar"


def test_wrapper_mantem_a_cli_e_o_que_os_testes_antigos_importavam():
    sys.path.insert(0, str(RAIZ / "scripts"))
    import gen_ad_v2
    from overlay import fundo_claro, gerar
    assert gen_ad_v2.main is gerar.main
    assert gen_ad_v2.fundo_claro is fundo_claro.fundo_claro
    assert gen_ad_v2.LIMIAR_FUNDO_CLARO == 119


def test_wrapper_sem_argumento_mostra_uso_e_sai_com_2(tmp_path):
    r = subprocess.run([sys.executable, str(RAIZ / "scripts" / "gen_ad_v2.py")], cwd=str(tmp_path),
                       capture_output=True, text=True)
    assert r.returncode == 2
    assert "gen_ad_v2.py <config.json>" in r.stderr


def test_main_recebe_so_o_caminho_da_config():
    from overlay import gerar
    import inspect
    assert list(inspect.signature(gerar.main).parameters) == ["cfg_path"]


def test_nenhum_modulo_novo_traz_nome_de_cliente_nem_travessao():
    # o padrao e montado em pedacos para este arquivo nao se acusar
    termos = ["Tha" + "les", "Jhe" + "ni", "J[uú]" + "lio", r"\bOC" + r"C\b", "Lar" + "ay", "Br[ií]" + "gida",
              "Opera[cç][aã]o Cl" + "aude", "Marco Au" + "r", r"\bjh" + r"1[0-9]\b", "vaib" + "hav", "Sob" + "ral",
              chr(0x2014), chr(0x2013)]
    proibidos = re.compile("|".join(termos), re.IGNORECASE)
    achados = []
    for pasta in (RAIZ / "scripts" / "overlay", RAIZ / "tests" / "overlay"):
        for p in sorted(pasta.glob("*.py")):
            for n, linha in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if proibidos.search(linha):
                    achados.append(f"{p.relative_to(RAIZ)}:{n}: {linha.strip()[:80]}")
    assert not achados, "\n".join(achados)


# ==============================================================================================
# 2. o diferencial (com mídia)
# ==============================================================================================

PALAVRAS = ("Minha skill de criação de páginas transformou meu Claude em um web designer profissional. "
            "Agora eu construo minhas páginas em minutos, sem precisar pagar nada mais por isso. "
            "Sabe qual é o melhor? "
            "Se eu usar um conector que é disponibilizado gratuitamente dentro do Claude, "
            "eu consigo não só produzir as páginas").split()
VERSAO_DO_HARNESS = 3       # sobe quando o jeito de montar/normalizar o cenario muda (3: W3.X, a0 da footage sintética)
AVATAR = "apresentador de frente para a câmera"
LETT = "apresentador + lettering"
LOGO = "apresentador + lettering + logo"
BASE_BLOCOS = [("inserção de vídeo: demo a", 0, 14), (AVATAR, 14, 28), (LETT, 28, 33),
               ("inserção de vídeo: demo b", 33, 45), (LOGO, 45, 52)]
LETTERINGS_BASE = [
    {"lead": "", "key": "✓ em minutos", "anchor": "minutos", "nth": 1, "dur": 2.0, "pilha": "ganhos"},
    {"lead": "", "key": "✓ sem pagar nada", "anchor": "pagar", "nth": 1, "dur": 2.0, "pilha": "ganhos"},
    {"lead": "sabe qual é", "key": "O MELHOR", "anchor": "melhor", "nth": 1, "dur": 1.6},
    {"lead": "eu consigo não só", "key": "PRODUZIR AS PÁGINAS", "anchor": "produzir", "nth": 1, "dur": 2.2}]


def _ffmpeg(*args):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *[str(a) for a in args]], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-300:]


def _cor(destino, cor, dur=6.0, tam="1080x1920", taxa=10):
    _ffmpeg("-f", "lavfi", "-i", f"color=c={cor}:s={tam}:d={dur}:r={taxa}", "-pix_fmt", "yuv420p",
            "-c:v", "libx264", "-preset", "ultrafast", destino)


def _footage_branco_depois_preto(destino):
    _ffmpeg("-f", "lavfi", "-i", "color=c=white:s=1080x1920:d=10:r=2",
            "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=12:r=2",
            "-filter_complex", "[0][1]concat=n=2:v=1:a=0", "-pix_fmt", "yuv420p",
            "-c:v", "libx264", "-preset", "ultrafast", destino)


def leva(blocos, trocas=None):
    palavras = list(PALAVRAS)
    for i, nova in (trocas or {}).items():
        palavras[i] = nova
    return "\n".join(f"[{instr}] " + " ".join(palavras[a:b]) for instr, a, b in blocos) + "\n"


class Cenario(object):
    """Tudo que muda de um cenário para outro, aplicado ao sandbox ANTES de rodar o motor."""

    def __init__(self, nome, blocos=None, inserts=None, cfg=None, formato="9x16", speed=1.0, letterings=None,
                 trocas=None, extras=(), avatar_nome=None, ritmo=None):
        self.nome, self.blocos, self.formato, self.speed = nome, blocos or BASE_BLOCOS, formato, speed
        self.inserts, self.cfg, self.letterings = inserts or {}, cfg or {}, letterings
        self.trocas, self.extras, self.avatar_nome, self.ritmo = trocas, tuple(extras), avatar_nome, ritmo

    def chave(self):
        """Impressao do que o cenario faz: resultado guardado de um cenario mudado nao vale."""
        corpo = json.dumps([self.nome, self.blocos, self.inserts, self.cfg, self.formato, self.speed,
                            self.letterings, self.trocas, list(self.extras), self.avatar_nome, self.ritmo,
                            VERSAO_DO_HARNESS], sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(corpo.encode("utf-8")).hexdigest()[:16]


def _aplicar(sb, cen):
    """Escreve leva, inserts e config do cenário no sandbox. Devolve o caminho da config."""
    inputs = sb.dados / "inputs"
    (inputs / f"{C.AD}_leva.txt").write_text(leva(cen.blocos, cen.trocas), encoding="utf-8")
    ins_arq = inputs / f"{C.AD}_inserts.json"
    ins = json.loads(ins_arq.read_text(encoding="utf-8"))
    for extra in cen.extras:
        if extra == "branco":
            _cor(inputs / "branco.mp4", "white")
            ins["demo c"] = {"file": str(inputs / "branco.mp4"), "start": 0, "speed": 1.0}
        elif extra == "escuro":
            _cor(inputs / "escuro.mp4", "black")
            ins["demo c"] = {"file": str(inputs / "escuro.mp4"), "start": 0, "speed": 1.0}
        elif extra == "imagem":
            shutil.copy(sb.midia / "fixture" / "midia" / "logo.png", inputs / "figura.png")
            ins["demo c"] = {"file": str(inputs / "figura.png"), "start": 0, "speed": 1.0}
        elif extra == "footage":
            saida = sb.dados / "output"
            _footage_branco_depois_preto(saida / f"{C.AD}_{C.LOOK}_footage_1x.mp4")
            # W3.X M4: a footage é amostrada em t - a0, e o a0 vem do _ritmo.json dela (a footage sintética começa
            # no zero do avatar). Sem plano de split: as janelas do overlay não mudam.
            (saida / f"{C.AD}_{C.LOOK}_footage_1x_ritmo.json").write_text(
                json.dumps({"segs": [{"s": 0.0, "e": 22.0, "tipo": "orig"}], "total": 22.0}), encoding="utf-8")
    for chave, mudancas in cen.inserts.items():
        if mudancas is None:
            ins.pop(chave, None)
        else:
            ins.setdefault(chave, {}).update(mudancas)
    ins_arq.write_text(json.dumps(ins), encoding="utf-8")

    cfg_arq = sb.estado / "configs" / f"{C.AD}_{C.LK}.json"
    cfg = json.loads(cfg_arq.read_text(encoding="utf-8"))
    cfg["format"] = cen.formato
    if cen.speed is not None:
        cfg["speed"] = cen.speed
    if cen.letterings is not None:
        cfg["letterings"] = cen.letterings
    if cen.avatar_nome:
        copia = inputs / cen.avatar_nome
        shutil.copy(inputs / f"{C.AD}_{C.LOOK}_avatar.mp4", copia)
        cfg["avatar"] = str(copia)
    cfg.update(cen.cfg)
    if cen.ritmo is not None:
        texto = cen.ritmo if isinstance(cen.ritmo, str) else json.dumps({"segs": cen.ritmo})
        (sb.dados / "output" / f"{C.AD}_{C.LOOK}_footage_1x_ritmo.json").write_text(texto, encoding="utf-8")
    cfg["out_dir"] = str(sb.estado / f"render-{cen.nome}")
    destino = sb.estado / f"_cfg_{cen.nome}.json"
    destino.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return destino, Path(cfg["out_dir"])


def _normalizar_saida(texto, sb):
    texto = N.normalizar_texto(texto, sb.tokens())
    texto = re.sub(r"\(([0-9a-f]{16})\)", "(<chave>)", texto)
    # a mensagem do look fechado perdeu o nome do look antigo: normaliza as duas versoes
    texto = re.sub(r"\([^)]*nao tem peito pra legenda padrao\)", "(<look fechado>)", texto)
    return texto


def executar(motor_raiz, midia, cen):
    """Roda o cenário num sandbox novo do motor dado. Devolve tudo que o motor produziu."""
    sb = C.montar_sandbox(motor_raiz, midia)
    try:
        cfg, workdir = _aplicar(sb, cen)
        r = subprocess.run([sys.executable, str(sb.scripts / "gen_ad_v2.py"), str(cfg)], cwd=str(sb.raiz),
                           env=C._env(sb), capture_output=True, text=True, encoding="utf-8")
        res = {"rc": r.returncode, "stdout": _normalizar_saida(r.stdout, sb),
               "stderr": _normalizar_saida(r.stderr[-1200:], sb) if r.returncode else ""}
        if r.returncode == 0:
            C._rodar(sb, [sys.executable, Path(C.__file__).resolve(), "--strip", sb.scripts, workdir / "index.html"],
                     cwd=sb.raiz)
            for nome in ("index.html", "index_overlay.html", "prancha.json", "janelas_split.json"):
                texto = _normalizar_saida((workdir / nome).read_text(encoding="utf-8"), sb)
                if nome.endswith(".html"):
                    # comentario CSS/JS nao e comportamento: o do hook punch foi reescrito sem nome de cliente
                    texto = re.sub(r"/\*.*?\*/", "/*c*/", texto, flags=re.S)
                res[nome] = texto
            res["brolls"] = sorted(p.name for p in workdir.glob("broll*.mp4"))
        bruto = sb.log.read_text(encoding="utf-8") if sb.log.exists() else ""
        res["argv"] = N.serializar_jsonl(
            [x for x in N.normalizar_jsonl(bruto, sb.tokens()) if "fase" not in x])
        return res
    finally:
        shutil.rmtree(sb.base, ignore_errors=True)


def _cenarios_fixos():
    ins_b_split = {"demo b": {"split": True}}
    c = []
    c.append(Cenario("dur_max", inserts={"demo a": {"dur_max": 2.0}, "demo b": {"dur_max": 2.5, "split": True}}))
    c.append(Cenario("dur_max_so_na_abertura", inserts={"demo a": {"dur_max": 3.0}}))
    c.append(Cenario("imagem_estatica", extras=("imagem",),
                     blocos=[("inserção de vídeo: demo c", 0, 14), (AVATAR, 14, 28), (LETT, 28, 33),
                             ("inserção de vídeo: demo b", 33, 45), (LOGO, 45, 52)]))
    c.append(Cenario("fundo_claro_pela_fonte", extras=("branco",),
                     blocos=[("inserção de vídeo: demo a", 0, 14), (AVATAR, 14, 28),
                             ("inserção de vídeo: demo c", 28, 45), (LOGO, 45, 52)]))
    c.append(Cenario("fundo_claro_pela_footage", extras=("footage",)))
    c.append(Cenario("relogio_da_footage", inserts={"demo a": {"split": True}, "demo b": {"split": True}},
                     ritmo=[{"s": 0.0, "e": 5.7, "layout": "split"}, {"s": 7.0, "e": 8.0, "layout": "cheio"},
                            {"s": 11.0, "e": 15.6, "layout": "split"}, {"s": 20.0, "e": 22.0, "layout": "split"}]))
    c.append(Cenario("relogio_da_footage_sem_split_no_overlay", inserts={"demo b": {"split": False}},
                     ritmo=[{"s": 11.0, "e": 15.6, "layout": "split"}]))
    c.append(Cenario("relogio_da_footage_sem_encontro", ritmo=[{"s": 3.0, "e": 4.0, "layout": "split"}]))
    c.append(Cenario("relogio_json_ilegivel", ritmo="{isso nao e json"))
    c.append(Cenario("fundo_claro_footage_em_split", extras=("footage",),
                     inserts={"demo a": {"split": True}, "demo b": {"split": True}}))
    c.append(Cenario("hook_punch_e_cta_sem_lead",
                     cfg={"hook": {"eyebrow": "ISSO MUDOU", "l1": "o jeito de", "accent": "VENDER", "style": "punch"},
                          "cta_sem_lead": True, "cta_label": "ver agora"}))
    c.append(Cenario("abertura_no_avatar_e_cta_em_split", inserts=ins_b_split,
                     blocos=[(AVATAR, 0, 14), ("inserção de vídeo: demo a", 14, 28), (LETT, 28, 33),
                             ("inserção de vídeo: demo b", 33, 52)]))
    c.append(Cenario("tres_inserts_na_abertura",
                     blocos=[("inserção de vídeo: demo a", 0, 8), ("inserção de vídeo: demo b", 8, 14),
                             ("inserção de vídeo: demo a", 14, 20), (AVATAR, 20, 33), (LETT, 33, 45),
                             (LOGO, 45, 52)]))
    # W3.X L10: o look fechado vem do plano declarado (looks.json do aluno); o nome do arquivo só existe aqui para o
    # motor do commit base, que ainda decidia pelo nome, dar o mesmo resultado
    c.append(Cenario("look_fechado_pelo_nome", avatar_nome=f"{C.AD}_lookb_avatar.mp4", cfg={"look_plano": "fechado"}))
    c.append(Cenario("texto_proprio_e_baixo", inserts={"demo a": {"texto_proprio": True}},
                     letterings=LETTERINGS_BASE[:2] + [dict(LETTERINGS_BASE[3], baixo=True)]))
    c.append(Cenario("lettering_cruza_a_troca_de_layout", inserts=ins_b_split,
                     letterings=[{"lead": "", "key": "TUDO GRATIS", "anchor": "gratuitamente", "dur": 3.0},
                                 {"lead": "", "key": "DENTRO", "anchor": "dentro", "dur": 3.0},
                                 {"lead": "", "key": "linha um", "anchor": "conector", "dur": 2.0, "pilha": "g"},
                                 {"lead": "", "key": "linha dois", "anchor": "dentro", "dur": 2.0, "pilha": "g"}]))
    c.append(Cenario("quadrado_com_dur_max", formato="1x1",
                     inserts={"demo b": {"dur_max": 2.5, "split": True}}))
    c.append(Cenario("com_aceleracao_padrao", speed=None))
    c.append(Cenario("com_aceleracao_1_3", speed=1.3))
    c.append(Cenario("fala_deitica_trava_o_insert", trocas={14: "Isso"},
                     blocos=[("inserção de vídeo: demo a", 0, 14), ("inserção de vídeo: demo b", 14, 28),
                             (AVATAR, 28, 45), (LOGO, 45, 52)]))
    c.append(Cenario("insert_com_start_e_velocidade", extras=("branco",),
                     inserts={"demo c": {"start": 1.5, "speed": 1.5}},
                     blocos=[(AVATAR, 0, 14), ("inserção de vídeo: demo c", 14, 33), (AVATAR, 33, 45),
                             (LOGO, 45, 52)]))
    c.append(Cenario("rotulos_do_insert", cfg={"labels": {"demo a": "O SEU SITE", "demo b": "NO CLAUDE"}}))
    # erros: o motor para igual, com a mesma mensagem
    c.append(Cenario("erro_lettering_sem_ancora",
                     letterings=[{"lead": "", "key": "K", "anchor": "naoexiste", "dur": 2.0}]))
    c.append(Cenario("erro_insert_sem_chave_no_mapa", inserts={"demo b": None}))
    c.append(Cenario("erro_janela_de_cta_longa",
                     blocos=[("inserção de vídeo: demo a", 0, 14), (AVATAR, 14, 52)]))
    return c


def _cenario_aleatorio(semente):
    r = random.Random(semente)
    while True:
        n = r.randint(3, 7)
        cortes = sorted(r.sample(range(3, 50), n - 1))
        pontos = [0] + cortes + [52]
        if all(b - a >= 3 for a, b in zip(pontos, pontos[1:])):
            break
    extras = []
    usa_c = r.random() < 0.6
    if usa_c:
        extras.append(r.choice(["branco", "escuro", "imagem"]))
    if r.random() < 0.3:
        extras.append("footage")
    chaves = ["demo a", "demo b"] + (["demo c"] if usa_c else [])
    blocos = []
    for i, (a, b) in enumerate(zip(pontos, pontos[1:])):
        if r.random() < (0.55 if i == 0 else 0.4):
            blocos.append((f"inserção de vídeo: {r.choice(chaves)}", a, b))
        else:
            blocos.append((r.choice([AVATAR, LETT, LOGO]), a, b))
    inserts = {}
    for k in chaves:
        m = {"split": r.random() < 0.5}
        if r.random() < 0.25:
            m["dur_max"] = round(r.uniform(2.0, 5.0), 1)
        if r.random() < 0.15:
            m["texto_proprio"] = True
        if r.random() < 0.4:
            m["start"] = r.choice([0, 1.0, 2.0])
        inserts[k] = m
    letts = []
    pilha = r.random() < 0.4
    for _ in range(r.randint(1, 4)):
        d = {"lead": r.choice(["", "sabe qual é", "olha"]), "key": r.choice(["ÓTIMO", "PRODUZIR AS PÁGINAS", "✓ item"]),
             "anchor": r.choice(PALAVRAS), "dur": round(r.uniform(1.4, 3.0), 1)}
        if pilha and r.random() < 0.6:
            d["pilha"] = "g"
        if r.random() < 0.15:
            d["baixo"] = True
        letts.append(d)
    cfg = {}
    if r.random() < 0.3:
        cfg["hook"] = {"eyebrow": "E", "l1": "L", "accent": "A", "style": "punch"}
    if r.random() < 0.2:
        cfg["cta_sem_lead"] = True
    if r.random() < 0.3:
        cfg["cta_label"] = r.choice(["ver agora", "clique aqui"])
    formato = "1x1" if r.random() < 0.2 else "9x16"
    avatar_nome = f"{C.AD}_lookb_avatar.mp4" if r.random() < 0.15 else None
    if avatar_nome:
        cfg["look_plano"] = "fechado"          # W3.X L10: o plano declarado, sem sortear nada a mais
    return Cenario(f"aleatorio_{semente}", blocos=blocos, inserts=inserts, cfg=cfg, letterings=letts,
                   formato=formato, extras=extras, avatar_nome=avatar_nome)


CENARIOS = {c.nome: c for c in _cenarios_fixos()}
SEMENTES = list(range(1, 17))
for _s in SEMENTES:
    _c = _cenario_aleatorio(_s)
    CENARIOS[_c.nome] = _c


@pytest.fixture(scope="module")
def midia():
    return C.exigir_midia()


@pytest.fixture(scope="module")
def motor_base(midia, tmp_path_factory):
    _arquivos, _hashes, manifesto = C.ler_golden(midia)
    commit = manifesto["commit_motor"]
    try:
        raiz = C.exportar_commit(C.raiz_do_repo(), commit, tmp_path_factory.mktemp("base"))
    except C.CommitAusente as e:
        pytest.skip(f"commit base {commit[:9]} ausente deste clone ({e})")
    return commit, raiz


def _resultado_base(midia, motor_base, cen):
    commit, raiz = motor_base
    pasta = Path(midia) / "golden_variantes" / commit[:12]
    arquivo = pasta / f"{cen.nome}.json"
    if arquivo.is_file():
        guardado = json.loads(arquivo.read_text(encoding="utf-8"))
        if guardado.get("_chave") == cen.chave():
            return guardado
    res = executar(raiz, midia, cen)
    res["_chave"] = cen.chave()
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    return res


def _diferencas(base, novo):
    out = []
    for chave in sorted((set(base) | set(novo)) - {"_chave"}):
        if base.get(chave) != novo.get(chave):
            a, b = str(base.get(chave)), str(novo.get(chave))
            i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
            out.append(f"{chave}: difere a partir do caractere {i}\n  base: ...{a[max(i - 60, 0):i + 120]!r}"
                       f"\n  novo: ...{b[max(i - 60, 0):i + 120]!r}")
    return out


@pytest.mark.midia_real
@pytest.mark.lento
@pytest.mark.parametrize("nome", sorted(CENARIOS))
def test_diferencial_cenario(nome, midia, motor_base):
    """O motor deste working tree dá, no cenário, exatamente o que o motor do commit base deu."""
    cen = CENARIOS[nome]
    base = _resultado_base(midia, motor_base, cen)
    novo = executar(C.raiz_do_repo(), midia, cen)
    dif = _diferencas(base, novo)
    assert not dif, f"cenário {nome}: o overlay mudou de comportamento\n" + "\n".join(dif)


@pytest.mark.midia_real
@pytest.mark.lento
def test_os_cenarios_exercitam_os_ramos_que_a_fixture_nao_cobre(midia, motor_base):
    """Se um cenário parar de chegar no ramo, o diferencial deixa de provar aquele ramo."""
    esperado = {
        "dur_max": "[cap] insert",
        "imagem_estatica": "-loop",
        "fundo_claro_pela_footage": "medidos na footage",
        "fundo_claro_pela_fonte": "pelo ARQUIVO-FONTE",
        "look_fechado_pelo_nome": "[look fechado]",
        "texto_proprio_e_baixo": "[texto_proprio]",
        "lettering_cruza_a_troca_de_layout": "[layout]",
    }
    faltando = []
    for nome, trecho in esperado.items():
        res = _resultado_base(midia, motor_base, CENARIOS[nome])
        if trecho not in res.get("stdout", "") + res.get("argv", ""):
            faltando.append(f"{nome}: nao apareceu {trecho!r}")
    assert not faltando, "\n".join(faltando)


@pytest.mark.midia_real
@pytest.mark.lento
def test_os_cenarios_de_erro_param_igual(midia, motor_base):
    for nome in ("erro_lettering_sem_ancora", "erro_insert_sem_chave_no_mapa", "erro_janela_de_cta_longa"):
        res = _resultado_base(midia, motor_base, CENARIOS[nome])
        assert res["rc"] != 0, nome
    assert "lettering sem ancora" in _resultado_base(midia, motor_base, CENARIOS["erro_lettering_sem_ancora"])["stderr"]
    assert "JANELA DE CTA LONGA" in _resultado_base(midia, motor_base, CENARIOS["erro_janela_de_cta_longa"])["stderr"]


# ==============================================================================================
# 3. equivalência com o original, função por função (sem mídia)
# ==============================================================================================

ORIGINAL_BLOB = "b4aaa100f46ee3e5099c8fa2ac7d949caa01425d"    # scripts/gen_ad_v2.py antes da quebra


@pytest.fixture(scope="module")
def original():
    r = subprocess.run(["git", "-C", str(RAIZ), "cat-file", "-p", ORIGINAL_BLOB], capture_output=True)
    if r.returncode != 0:
        pytest.skip("o blob do gen_ad_v2.py original nao esta neste clone (clone raso?)")
    return r.stdout.decode("utf-8").splitlines()


def fatiar(linhas, intervalos, entradas, saidas, subst=(), regex=()):
    """Embrulha linhas do `main` original (1-based, fechadas) numa função de `entradas` a `saidas`. `subst` troca texto
    exato; `regex` troca por expressão regular `(padrão, substituto, mínimo de trocas)`."""
    corpo = []
    for a, b in intervalos:
        corpo.extend(linhas[a - 1:b])
    texto = textwrap.dedent("\n".join(corpo))
    for velho, novo in subst:
        assert velho in texto, velho
        texto = texto.replace(velho, novo)
    for padrao, novo, minimo in regex:
        texto, n = re.subn(padrao, novo, texto)
        assert n >= minimo, padrao
    codigo = ("def _f(%s):\n" % ", ".join(entradas) + textwrap.indent(texto, "    ")
              + "\n    return (%s,)\n" % ", ".join(saidas))
    ns = {"sys": sys, "math": math, "norm": T.norm, "build_timeline": build_timeline}
    exec(codigo, ns)
    return ns["_f"]


def rodar(f, entrada):
    """('ok', resultado, stdout) ou ('exit', mensagem, stdout), sobre uma CÓPIA da entrada."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            return ("ok", f(*copy.deepcopy(entrada)), buf.getvalue())
        except SystemExit as e:
            return ("exit", str(e.code), buf.getvalue())


def _tipo_de_saida(mensagem):
    for trecho, nome in (("JANELA DE CTA", "janela"), ("TELA VAZIA", "vao"), ("lettering sem ancora", "ancora"),
                         ("sem key no inserts.json", "sem_chave")):
        if trecho in mensagem:
            return nome
    return "outro"


def comparar(velho, novo, gerar, n=400, semente=7):
    resumo = collections.Counter()
    for i in range(n):
        entrada = gerar(random.Random(semente * 100003 + i))
        a, b = rodar(velho, entrada), rodar(novo, entrada)
        assert a == b, f"caso {i}: o modulo novo diverge do original\n entrada: {entrada!r}\n original: {a!r}\n novo: {b!r}"
        resumo[a[0]] += 1
        if a[0] == "exit":
            resumo["exit:" + _tipo_de_saida(a[1])] += 1
    return resumo


VOC = ["o", "pulo", "do", "gato", "melhor", "produzir", "páginas", "eu", "consigo", "sabe", "qual", "é",
       "isso", "aqui", "agora", "minutos", "tela", "dentro", "porque", "gratuitamente", "praticamente"]


def g_palavras(rnd, n=None):
    n = n or rnd.randint(4, 40)
    t, out = round(rnd.uniform(0.0, 1.0), 2), []
    for _ in range(n):
        dur = round(rnd.uniform(0.12, 0.5), 2)
        out.append({"text": rnd.choice(VOC) + rnd.choice(["", "", ",", "."]), "start": t, "end": round(t + dur, 2),
                    "kw": rnd.random() < 0.2})
        t = round(t + dur + rnd.choice([0, 0.02, 0.1, 0.4, 1.2]), 2)
    return out


def g_grupos(rnd, n=None):
    return build_timeline.group_captions(g_palavras(rnd, n), max_words=3)


def g_janelas(rnd, groups, k=None):
    k = rnd.randint(0, 3) if k is None else k
    pontos = [g["start"] for g in groups] + [g["end"] for g in groups]
    out = []
    for _ in range(k):
        a = rnd.choice(pontos) + rnd.choice([-0.4, -0.14, -0.1, -0.03, 0, 0.03, 0.1, 0.14, 0.4])
        out.append((round(max(a, 0.0), 2), round(max(a, 0.0) + rnd.choice([0.5, 1.3, 2.8, 5.0, 9.0]), 2)))
    return out


def g_spans(rnd, n, fim):
    cortes = sorted(round(rnd.uniform(0.3, fim), 2) for _ in range(n - 1))
    pontos = [0.0] + cortes + [round(fim + 0.3, 2)]
    return [(pontos[i], pontos[i + 1]) for i in range(n)]


def g_blocos(rnd, n, tipos=("insert", "orig", "lettering", "lettering_logo")):
    return [{"type": rnd.choice(tipos), "instr": rnd.choice(["x", "apresentador + logo", "demo a", "demo b"]),
             "narr": " ".join(rnd.choice(VOC) for _ in range(rnd.randint(0, 5)))} for _ in range(n)]


def test_equivalencia_spans(original):
    velho = fatiar(original, [(264, 274)], ["blocks", "words"], ["spans"])

    def gerar(rnd):
        words = g_palavras(rnd, rnd.randint(3, 25))
        blocos, i = [], 0
        while i < len(words):
            n = rnd.randint(0, 5) if rnd.random() < 0.2 else rnd.randint(1, 6)
            n = min(n, len(words) - i)
            blocos.append({"type": "orig", "instr": "x", "narr": " ".join(["w"] * n)})
            i += n
        return blocos, words

    r = comparar(velho, lambda blocks, words: (S.calcular_spans(blocks, words),), gerar)
    assert r["ok"] == 400


def test_equivalencia_hook(original):
    velho = fatiar(original, [(279, 299)], ["blocks", "spans"],
                   ["opening_insert", "hook_gone", "hook_fade", "hook_dur", "cap_gate"])

    def novo(blocks, spans):
        # W5.Y: o gancho agora SAI antes da primeira legenda entrar, então `hook_fade` (o início da saída) deixou de ser
        # hook_gone - 0,4. É a única divergência deliberada do original: confere a regra nova e devolve o valor antigo.
        op, gone, fade, dur, gate = K.calcular_hook(blocks, spans)
        assert fade == round(gone - K.FOLGA_GANCHO - K.FADE_GANCHO, 2)
        return op, gone, round(gone - 0.4, 2), dur, gate

    def gerar(rnd):
        n = rnd.randint(1, 6)
        return g_blocos(rnd, n, ("insert", "insert", "orig")), g_spans(rnd, n, 30.0)

    assert comparar(velho, novo, gerar)["ok"] == 400


def test_equivalencia_cta_start_e_logo(original):
    velho = fatiar(original, [(654, 678)], ["blocks", "spans", "_retorno_avatar"],
                   ["cta_start", "LOGO_LEAD", "logo_start"])

    def novo(blocks, spans, retorno):
        # W7.W (A2): única divergência deliberada do original. O CTA não sobe mais quando a imagem volta ao avatar
        # (`retorno`), e sim no início do bloco cta; sem retorno as duas regras são a mesma e é isso que se confere.
        cta_start = CTA.calcular_cta_start(blocks, spans, retorno_avatar=retorno)
        assert cta_start == spans[-1][0]
        lead = CTA.logo_lead(blocks)
        return cta_start, lead, CTA.logo_start(cta_start, lead)

    def gerar(rnd):
        n = rnd.randint(1, 6)
        blocos = g_blocos(rnd, n, ("insert", "insert", "orig"))
        return blocos, g_spans(rnd, n, 30.0), []

    assert comparar(velho, novo, gerar)["ok"] == 400


def test_equivalencia_visitas_janelas_e_brolls(original):
    velho = fatiar(original, [(302, 308), (309, 309), (337, 430)],
                   ["blocks", "spans", "inserts_map", "_plano_ritmo", "cfg"],
                   ["janelas_split", "janelas_texto", "mapa_insert", "_retorno_avatar", "brolls"])

    def novo(blocks, spans, inserts_map, plano, cfg):
        visitas, retorno = B.planejar_visitas(blocks, spans, inserts_map, plano)
        split, texto, mapa = LT.janelas_por_visita(visitas)
        return split, texto, mapa, retorno, B.montar_brolls(visitas, cfg.get("labels", {}))

    def gerar(rnd):
        n = rnd.randint(1, 6)
        spans = g_spans(rnd, n, 40.0)
        blocos = []
        for i in range(n):
            if rnd.random() < 0.55:
                blocos.append({"type": "insert", "instr": "inserção de vídeo: " + rnd.choice(["demo a", "demo b", "demo c"]),
                               "narr": rnd.choice(["uma fala qualquer", "olha isso aqui na tela", "Isso é um manual"])})
            else:
                blocos.append({"type": "orig", "instr": "apresentador", "narr": "fala do apresentador"})
        mapa = {}
        for chave in ("demo a", "demo b", "demo c"):
            if rnd.random() < 0.05:
                continue                       # insert sem chave no mapa: o motor para igual
            m = {"file": chave.replace(" ", "_") + ".mp4"}
            if rnd.random() < 0.5:
                m["split"] = True
            if rnd.random() < 0.35:
                m["dur_max"] = round(rnd.uniform(1.0, 6.0), 1)
            if rnd.random() < 0.15:
                m["texto_proprio"] = True
            if rnd.random() < 0.5:
                m["start"] = rnd.choice([0, 1.5, 2.25])
            if rnd.random() < 0.3:
                m["speed"] = rnd.choice([1.0, 1.5])
            if rnd.random() < 0.2:
                m["crop"] = [0, 0, 100, 100]
            mapa[chave] = m
        entradas = []
        for b, (s0, e0) in zip(blocos, spans):
            k, c = S.achar_insert_cfg(b["instr"], mapa) if b["type"] == "insert" else (None, None)
            entradas.append({"tipo": "insert" if b["type"] == "insert" else "orig", "s": s0, "e": e0,
                             "crop": (c or {}).get("crop"), "dur_max": (c or {}).get("dur_max"), "texto": b["narr"]})
        plano = ritmo.plano_de_ritmo(entradas)
        cfg = {"labels": {"demo a": "A"}} if rnd.random() < 0.3 else {}
        return blocos, spans, mapa, plano, cfg

    r = comparar(velho, novo, gerar, n=500)
    assert r["ok"] > 350 and r["exit:sem_chave"] > 0      # inclui o insert sem chave


def test_equivalencia_letterings_pilha_e_trava_de_layout(original):
    velho = fatiar(original, [(482, 531), (540, 583)],
                   ["cfg", "words", "spans", "blocks", "janelas_split"], ["letts", "lett_windows"])
    def novo(cfg, words, spans, blocks, janelas_split):
        letts, janelas = LE.montar(cfg.get("letterings", []), words, spans, blocks, janelas_split)
        # W5.X: a marca `adiado` é nova (o eco do lettering adiado só sai se encostar); o resto é o original
        return [{k: v for k, v in l.items() if k != "adiado"} for l in letts], janelas

    def gerar(rnd):
        words = g_palavras(rnd, rnd.randint(8, 40))
        fim = words[-1]["end"]
        blocos = [{"instr": rnd.choice(["x", "apresentador + lettering + logo"])} for _ in range(3)]
        spans = g_spans(rnd, 3, fim)
        letts = []
        for _ in range(rnd.randint(0, 5)):
            d = {"lead": rnd.choice(["", "sabe qual é"]), "key": rnd.choice(["ÓTIMO", "linha a", "PRODUZIR AS PÁGINAS"]),
                 "anchor": rnd.choice(VOC) if rnd.random() < 0.97 else "inexistente",
                 "dur": round(rnd.uniform(1.0, 3.5), 1)}
            if rnd.random() < 0.3:
                d["nth"] = rnd.randint(1, 2)
            if rnd.random() < 0.4:
                d["pilha"] = rnd.choice(["g", "h"])
            if rnd.random() < 0.15:
                d["baixo"] = True
            letts.append(d)
        return {"letterings": letts}, words, spans, blocos, g_janelas(rnd, g_grupos(rnd, 10), rnd.randint(0, 3)) \
            + [(round(fim * 0.3, 2), round(fim * 0.5, 2))][:rnd.randint(0, 1)]

    r = comparar(velho, novo, gerar, n=600)
    assert r["ok"] > 150 and r["exit:ancora"] > 50      # inclui a ancora que nao existe


# APOSENTADOS em 10/10/2026 ("Sim pros 2"): `test_equivalencia_fronteira_de_split_e_costura` e
# `test_equivalencia_guarda_pos_split_e_fechamento`. A legenda tem UMA posição (a base do quadro; no CTA, acima da pílula),
# então o motor não parte mais o grupo na fronteira de uma troca de layout, não marca a costura, não empurra o grupo que
# nasce colado no fim do split e não corta a legenda no logo: ela é partida por palavra e continua no CTA. O trecho do
# `gen_ad_v2.py` original que esses testes comparavam morreu de propósito; o comportamento novo está em
# test_legendas.py (fechar_grupos), test_layout_texto.py e test_legenda_halo_na_base.py.


# 10/10/2026: a UNICA mudança deliberada no aparo é o piso da sobra de legenda, de 0,60 s para 0,50 s: com grupos de até 4
# palavras uma sobra de 0,57 s (3 palavras faladas depois do lettering) ficava sem texto. O resto é o original.
PECA_MIN_ORIGINAL = ("FOLGA_LETT, PECA_MIN = 0.35, 0.60", "FOLGA_LETT, PECA_MIN = 0.35, 0.50")


def test_equivalencia_eco_e_aparo_nos_letterings(original):
    velho = fatiar(original, [(975, 1032)], ["groups", "letts", "lett_windows"], ["groups"], subst=[PECA_MIN_ORIGINAL])
    novo = lambda groups, letts, lett_windows: (LG.aparar_nos_letterings(groups, letts, lett_windows),)   # noqa: E731

    def gerar(rnd):
        groups = g_grupos(rnd)
        letts = []
        for _ in range(rnd.randint(0, 3)):
            ini = round(rnd.choice([g["start"] for g in groups]) + rnd.choice([-1.0, -0.3, 0, 0.3, 1.0]), 2)
            d = {"lead": rnd.choice(["", "o pulo do", "sabe qual é"]), "key": rnd.choice(["gato", "MELHOR", "isso aqui"]),
                 "start": max(ini, 0.0), "dur": round(rnd.uniform(1.0, 3.0), 1)}
            if rnd.random() < 0.3:
                d["linhas"] = [{"key": rnd.choice(VOC), "delay": 0.0}, {"key": rnd.choice(VOC), "delay": 1.0}]
            letts.append(d)
        return groups, letts, [(l["start"], l["start"] + l["dur"]) for l in letts]

    assert comparar(velho, novo, gerar, n=1000)["ok"] == 1000


def test_equivalencia_gate_de_tela_vazia(original):
    velho = fatiar(original, [(1073, 1107)], ["hook_dur", "groups", "lett_windows", "cta_s", "total"],
                   ["_pior", "_quando"])
    novo = lambda hook_dur, groups, lett_windows, cta_s, total: TV.checar(    # noqa: E731
        hook_dur, groups, lett_windows, cta_s, total)

    def gerar(rnd):
        groups = g_grupos(rnd, rnd.randint(1, 30))
        total = round(groups[-1]["end"] + rnd.choice([0.5, 2.0, 6.0]), 2)
        letts = [(round(rnd.uniform(0, total), 2),) for _ in range(rnd.randint(0, 2))]
        letts = [(a[0], round(a[0] + rnd.uniform(1, 3), 2)) for a in letts]
        return (rnd.choice([2.2, 3.1, 3.3]), groups, letts, round(rnd.uniform(total * 0.3, total), 2), total)

    r = comparar(velho, novo, gerar, n=800)
    # os dois abortos e o caso que passa acontecem
    assert r["ok"] > 100 and r["exit:janela"] > 10 and r["exit:vao"] > 10


def test_equivalencia_chips_com_o_chip_ligado(original):
    velho = fatiar(original, [(1118, 1178)], ["_plano_ritmo", "groups", "lett_windows", "logo_s"], ["chips"],
                   subst=[("CHIP_LIGADO = False", "CHIP_LIGADO = True")])
    novo = lambda plano, groups, lett_windows, logo_s: (CH.calcular(plano, groups, lett_windows, logo_s, ligado=True),)  # noqa: E731

    def gerar(rnd):
        t, plano = 0.0, []
        for _ in range(rnd.randint(1, 8)):
            d = rnd.choice([1.0, 3.0, 6.0, 8.0, 12.0, 20.0])
            plano.append({"tipo": rnd.choice(["orig", "orig", "insert"]), "s": t, "e": round(t + d, 2)})
            t = round(t + d, 2)
        groups = g_grupos(rnd, 160)
        letts = [(round(rnd.uniform(3, t), 2),) for _ in range(rnd.randint(0, 2))]
        letts = [(a[0], round(a[0] + 2.0, 2)) for a in letts]
        return plano, groups, letts, round(rnd.uniform(t * 0.5, t + 5), 2)

    r = comparar(velho, novo, gerar, n=500)
    assert r["ok"] == 500
