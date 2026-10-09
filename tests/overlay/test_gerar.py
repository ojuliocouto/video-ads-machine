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

import pytest

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
VERSAO_DO_HARNESS = 1       # sobe quando o jeito de montar/normalizar o cenario muda
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
                res[nome] = _normalizar_saida((workdir / nome).read_text(encoding="utf-8"), sb)
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
    c.append(Cenario("look_fechado_pelo_nome", avatar_nome=f"{C.AD}_of13_avatar.mp4"))
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
    return Cenario(f"aleatorio_{semente}", blocos=blocos, inserts=inserts, cfg=cfg, letterings=letts,
                   formato="1x1" if r.random() < 0.2 else "9x16", extras=extras,
                   avatar_nome=(f"{C.AD}_of13_avatar.mp4" if r.random() < 0.15 else None))


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
    for chave in sorted(set(base) | set(novo)):
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
