"""Montagem da footage (W2.B): a orquestração, o wrapper e as garantias de não ter efeito no import.

O `produzir_roteiro.py` antigo (1.730 linhas) executava TUDO no import: parser, alinhamento,
render e mux. Nada dele se testava isolado e importá-lo gastava minutos de ffmpeg. Aqui o
import não chama ffmpeg, não cria pasta e não lê o ambiente do usuário; o wrapper mantém a CLI e
as variáveis de ambiente.
"""
import hashlib
import json
import os
import re
import site
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

from footage import blocos as BL
from footage import cadeia as CA
from footage import grade_final as GF
from footage import montar as MO
from footage import render_segmentos as RS

RAIZ = Path(__file__).resolve().parent.parent.parent
SCRIPTS = RAIZ / "scripts"
MODULOS = ("blocos", "filtros_avatar", "filtros_insert", "exposicao", "enquadramento", "cadeia",
           "render_segmentos", "grade_final", "timing_export", "montar")

# sha256 de palavras que não podem aparecer no código dos módulos (nomes de cliente e de anúncio).
# Guardadas só como hash: o próprio teste não pode carregar o vocabulário que proíbe.
PROIBIDAS = ['1fd117e2890f3aebf0e6cda77d11b7bd19226a55618db6f0d566d275991ef51a',
 '382a9d8d7acc2b157cf88e7552e6efcfe14b906e79e0fce9f4352cb8615c1868',
 '3dba2d2e96e3a37e36af293826144bf2fcf6e54b279558e8f571acf707881cef',
 '50ffafa4cfb0ff0704222a205f31763cb1ca156c7748269a9057f157bd61f49f',
 '57613a4d79246bdb6c31ccdc69671dfa96709c699270ee6321dd9952594a01fc',
 '5db2b9c0d7a494a6097148d29a1bd1ba68783fa8e00a95134214520ff9e9b397',
 '75865419ecbe22ece16bc646cc28e9f181072d37a0f23792a75acd83d3e75f9e',
 '901be86d450c504e8555ffeeeab1e06b926c8785fd99ef382c1310b7c66bc167',
 'a44d51a2fadc9f5eef35b559b0fe178b817bb763b914b4db0b020b7f07c22fd2',
 'ad7d137d48c2463a13359aa27866e6899cc21987a7528506b861c02854cfa805',
 'ae3ad2d023b5251134a97c9692d1f2844a2094d7b00665d0d7fceb01335243b8',
 'b22e803db636f5dec79aeb0983c4535cb7bf674b43d5801247810d41ea6c68d9',
 'e3a5e4f62a3add3d82bd6b1b2d354c01395b59d4dadebafe5df522736e0a380d',
 'e444bd3bca2736f39ca65d53853891a6b0f553b8def766531fbbd6d1b8800521',
 'fe18eb51954dc856b3dca95a169adb7631e82d720829ec9f680e703c1ef07a4a']


def _palavras(texto):
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")
    return set(re.findall(r"[a-z0-9]+", sem_acento))


def _arquivos_do_unit():
    arqs = [SCRIPTS / "footage" / f"{m}.py" for m in MODULOS]
    arqs.append(SCRIPTS / "produzir_roteiro.py")
    arqs += sorted((RAIZ / "tests" / "footage").glob("test_*.py"))
    return arqs


# ------------------------------------------------------------------ import sem efeito (defeito 10)

_SONDA = """
import os, subprocess, sys
def boom(*a, **k):
    raise AssertionError("subprocess no import: " + repr(a))
subprocess.Popen.__init__ = boom
<<IMPORTACOES>>
assert not os.path.exists(os.environ["VAM_DADOS"]), "o import criou a pasta de DADOS"
assert not os.path.exists(os.environ["VAM_ESTADO"]), "o import criou a pasta de ESTADO"
print("IMPORT-OK")
"""


def _roda_sonda(tmp_path, importacoes):
    env = {"PATH": "", "HOME": str(tmp_path / "home"), "PYTHONPATH": str(SCRIPTS), "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONUSERBASE": site.getuserbase(),
           "VAM_DADOS": str(tmp_path / "dados_inexistente"), "VAM_ESTADO": str(tmp_path / "estado_inexistente")}
    (tmp_path / "cwd").mkdir()
    r = subprocess.run([sys.executable, "-c", _SONDA.replace("<<IMPORTACOES>>", importacoes)], env=env, cwd=str(tmp_path / "cwd"),
                       capture_output=True, text=True)
    return r, tmp_path / "cwd"


def test_importar_footage_montar_nao_chama_ffmpeg_nem_cria_pasta(tmp_path):
    r, cwd = _roda_sonda(tmp_path, "import footage.montar")
    assert r.returncode == 0, r.stderr
    assert "IMPORT-OK" in r.stdout
    assert list(cwd.iterdir()) == []


@pytest.mark.parametrize("modulo", MODULOS)
def test_cada_modulo_importa_sem_efeito_colateral(tmp_path, modulo):
    r, _ = _roda_sonda(tmp_path, f"import footage.{modulo}")
    assert r.returncode == 0, r.stderr


def test_wrapper_importado_nao_executa_nada(tmp_path):
    r, _ = _roda_sonda(tmp_path, "import produzir_roteiro")
    assert r.returncode == 0, r.stderr


def test_wrapper_tem_ate_40_linhas():
    linhas = (SCRIPTS / "produzir_roteiro.py").read_text(encoding="utf-8").splitlines()
    assert len(linhas) <= 40, f"o wrapper tem {len(linhas)} linhas"


def test_wrapper_sem_variaveis_sai_com_erro_dizendo_o_que_falta(tmp_path):
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path), "VAM_DADOS": str(tmp_path / "d"),
           "VAM_ESTADO": str(tmp_path / "e"), "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONUSERBASE": site.getuserbase()}
    r = subprocess.run([sys.executable, str(SCRIPTS / "produzir_roteiro.py")], env=env, cwd=str(tmp_path),
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert "VAM_AVATAR" in r.stderr and "VAM_ROTEIRO" in r.stderr
    assert "Traceback" not in r.stderr


# ------------------------------------------------------------------ configuração (mesmas variáveis)

def _env(tmp_path, **extra):
    base = {"VAM_AVATAR": str(tmp_path / "avatar.mp4"), "VAM_ROTEIRO": str(tmp_path / "roteiro.txt"),
            "VAM_OUT": "x.mp4", "CAP": "0", "VAM_BAKE_LETTERING": "0"}
    base.update(extra)
    return base


def test_config_le_as_variaveis_de_sempre(tmp_path):
    cfg = MO.ler_config(_env(tmp_path, VAM_INSERTS_JSON="ins.json", VAM_CACHE_SEG="0", VAM_PARALELO="2"),
                        dados=str(tmp_path / "D"))
    assert cfg.avatar == str(tmp_path / "avatar.mp4")
    assert cfg.roteiro == str(tmp_path / "roteiro.txt")
    assert cfg.inserts_json == "ins.json"
    assert cfg.cache is False and cfg.paralelo == 2
    assert cfg.nome_saida == "x"
    assert cfg.tmp == os.path.join(str(tmp_path / "D"), "_tmp_rot", "x")
    assert cfg.saida == os.path.join(str(tmp_path / "D"), "output", "x.mp4")
    assert cfg.ritmo == os.path.join(str(tmp_path / "D"), "output", "x_ritmo.json")
    assert cfg.timing == os.path.join(str(tmp_path / "D"), "output", "timing.json")


def test_config_defaults_de_cache_e_paralelismo(tmp_path):
    cfg = MO.ler_config(_env(tmp_path), dados=str(tmp_path))
    assert cfg.cache is True and cfg.paralelo == 4
    assert (cfg.tr.xf, cfg.tr.xf_seco, cfg.tr.tipo) == (0.08, 0.04, "auto")


def test_avatar_com_til_e_expandido(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = MO.ler_config(_env(tmp_path, VAM_AVATAR="~/av.mp4"), dados=str(tmp_path))
    assert cfg.avatar == str(tmp_path / "av.mp4")


def test_saida_absoluta_vence_a_pasta_de_output_como_no_original(tmp_path):
    """A prévia passa VAM_OUT absoluto: os_path.join descarta a base, e é isso que o original fazia."""
    cfg = MO.ler_config(_env(tmp_path, VAM_OUT=str(tmp_path / "prev" / "previa.mp4")), dados=str(tmp_path / "D"))
    assert cfg.saida == str(tmp_path / "prev" / "previa.mp4")
    assert cfg.ritmo == str(tmp_path / "prev" / "previa_ritmo.json")
    assert cfg.tmp == str(tmp_path / "prev" / "previa")


@pytest.mark.parametrize("faltando", ["VAM_AVATAR", "VAM_ROTEIRO"])
def test_avatar_e_roteiro_sao_obrigatorios_e_a_mensagem_diz_qual(tmp_path, faltando):
    env = _env(tmp_path)
    del env[faltando]
    with pytest.raises(CA.ErroFootage) as e:
        MO.ler_config(env, dados=str(tmp_path))
    assert faltando in str(e.value)


def test_cap_1_foi_removido_porque_a_legenda_e_do_overlay(tmp_path):
    with pytest.raises(CA.ErroFootage) as e:
        MO.ler_config(_env(tmp_path, CAP="1"), dados=str(tmp_path))
    assert "CAP" in str(e.value) and "overlay" in str(e.value)


def test_bake_lettering_1_foi_removido_porque_o_lettering_e_do_overlay(tmp_path):
    with pytest.raises(CA.ErroFootage) as e:
        MO.ler_config(_env(tmp_path, VAM_BAKE_LETTERING="1"), dados=str(tmp_path))
    assert "VAM_BAKE_LETTERING" in str(e.value) and "overlay" in str(e.value)


def test_letter_style_e_ignorado_quando_o_bake_esta_desligado(tmp_path):
    MO.ler_config(_env(tmp_path, VAM_LETTER_STYLE="foil"), dados=str(tmp_path))


def test_transicao_que_apaga_a_tela_continua_proibida(tmp_path):
    with pytest.raises(CA.ErroFootage):
        MO.ler_config(_env(tmp_path, VAM_XF_TIPO="fadeblack"), dados=str(tmp_path))


def test_main_devolve_1_e_a_mensagem_no_stderr_sem_traceback(tmp_path, capsys):
    assert MO.main(env={"VAM_DADOS": str(tmp_path)}) == 1
    err = capsys.readouterr().err
    assert "VAM_AVATAR" in err and "Traceback" not in err


# ------------------------------------------------------------------ orquestração completa, com ffmpeg falso

ROTEIRO = """[inserção de vídeo: demo a] Minha skill transformou meu Claude em web designer.
[apresentador de frente para a câmera] Agora eu construo minhas páginas em minutos.
[apresentador + lettering | LEAD: sabe qual é | KEY: O MELHOR] Sabe qual é o melhor?
"""


@pytest.fixture
def mundo(tmp_path, monkeypatch):
    dados = tmp_path / "dados"
    (dados / "output").mkdir(parents=True)
    avatar = tmp_path / "avatar.mp4"
    avatar.write_bytes(b"v")
    roteiro = tmp_path / "roteiro.txt"
    roteiro.write_text(ROTEIRO, encoding="utf-8")
    ins = tmp_path / "ins.json"
    ins.write_text(json.dumps({"demo a": {"file": str(tmp_path / "a.mp4"), "start": 0, "speed": 1.0}}))
    eventos = []
    narr = []
    for linha in ROTEIRO.splitlines():
        narr += linha.split("] ", 1)[1].split()
    palavras = [(round(0.5 + 0.3 * i, 3), round(0.5 + 0.3 * i + 0.25, 3), w) for i, w in enumerate(narr)]

    def alinhar(avatar_, narr_words, tmp, **kw):
        eventos.append("alinhar")
        assert narr_words == narr
        return palavras

    def renderiza(blocks, spans, ctx):
        eventos.append("renderizar")
        out = []
        for i in range(len(blocks)):
            p = os.path.join(ctx.tmp, f"s{i:02d}.mp4")
            Path(p).write_bytes(b"x")
            out.append(p)
        return out

    def run_cadeia(c):
        eventos.append("cadeia")

    def run_grade(c):
        eventos.append("grade")
        eventos.append(list(c))

    monkeypatch.setattr(BL, "alinhar", alinhar)
    monkeypatch.setattr(RS, "renderizar_todos", renderiza)
    monkeypatch.setattr(CA, "run", run_cadeia)
    monkeypatch.setattr(GF, "run", run_grade)
    monkeypatch.setattr(CA, "vdur", lambda p: 99.0)          # o gate de duração da cadeia é testado em test_cadeia
    monkeypatch.setattr(CA, "lum_primeiro_quadro", lambda p: 255.0)
    monkeypatch.setattr(CA, "verificar_segmentos", lambda *a, **k: None)
    monkeypatch.setattr(CA, "verificar_cadeia", lambda *a, **k: None)
    env = {"VAM_AVATAR": str(avatar), "VAM_ROTEIRO": str(roteiro), "VAM_INSERTS_JSON": str(ins),
           "VAM_OUT": "teste.mp4", "CAP": "0", "VAM_BAKE_LETTERING": "0", "VAM_DADOS": str(dados)}
    return env, dados, eventos, palavras


def test_orquestracao_roda_as_etapas_na_ordem_e_escreve_ritmo_e_timing(mundo, capsys):
    env, dados, eventos, palavras = mundo
    assert MO.main(env=env) == 0
    assert [e for e in eventos if isinstance(e, str)] == ["alinhar", "renderizar", "cadeia", "grade"]
    out = capsys.readouterr().out
    assert f"PRONTO: {dados / 'output' / 'teste.mp4'}" in out
    ritmo = json.loads((dados / "output" / "teste_ritmo.json").read_text(encoding="utf-8"))
    assert ritmo["total"] == pytest.approx(ritmo["segs"][-1]["e"])
    timing = json.loads((dados / "output" / "timing.json").read_text(encoding="utf-8"))
    assert list(timing) == ["a0", "total", "xf", "avatar", "inserts", "letterings"]
    assert timing["a0"] == pytest.approx(palavras[0][0]) and timing["letterings"] == []
    assert timing["avatar"] == env["VAM_AVATAR"]


def test_o_comando_final_usa_a_janela_de_audio_do_avatar(mundo):
    env, dados, eventos, palavras = mundo
    MO.main(env=env)
    cmd = eventos[eventos.index("grade") + 1]
    timing = json.loads((dados / "output" / "timing.json").read_text(encoding="utf-8"))
    assert cmd[cmd.index("-ss") + 1] == str(timing["a0"])
    assert cmd[cmd.index("-t") + 1] == str(timing["total"] - timing["a0"])
    assert cmd[-1] == str(dados / "output" / "teste.mp4")


def test_erro_do_render_vira_codigo_1_sem_traceback(mundo, monkeypatch, capsys):
    env, _, _, _ = mundo

    def quebra(blocks, spans, ctx):
        raise CA.ErroFootage("ERRO seg 01: duracao 9.00s != esperada 2.00s")

    monkeypatch.setattr(RS, "renderizar_todos", quebra)
    assert MO.main(env=env) == 1
    err = capsys.readouterr().err
    assert "seg 01" in err and "Traceback" not in err


# ------------------------------------------------------------------ varreduras do que saiu e do que não pode ficar

def test_nenhum_modulo_nem_teste_carrega_nome_de_cliente():
    proibidas = set(PROIBIDAS)
    achados = []
    for arq in _arquivos_do_unit():
        for palavra in _palavras(arq.read_text(encoding="utf-8")):
            if hashlib.sha256(palavra.encode("utf-8")).hexdigest() in proibidas:
                achados.append((arq.name, hashlib.sha256(palavra.encode("utf-8")).hexdigest()[:10]))
    assert not achados, f"vocabulário de cliente em {achados}"


def test_zero_travessao_nos_arquivos_da_unidade():
    for arq in _arquivos_do_unit():
        texto = arq.read_text(encoding="utf-8")
        assert "\u2014" not in texto and "\u2013" not in texto, f"travessão em {arq.name}"


def test_nada_cravado_no_home_nem_assets_externos_nos_modulos():
    ruins = (".local/bin", "sunburst.png", "logo_glow.png", "circle_shadow.png", "circle_mask",
             "circle_ring", "lightleak", "top_scrim", "inputs/ad", "BASE, \"medir_enquadramento")
    for m in MODULOS:
        texto = (SCRIPTS / "footage" / f"{m}.py").read_text(encoding="utf-8")
        for r in ruins:
            assert r not in texto, f"{m}.py ainda traz {r!r}"


def test_modulos_nao_executam_nada_em_nivel_de_modulo():
    """Só def, class, import, constante e docstring no topo: sem chamada solta, sem sys.exit."""
    import ast

    for m in MODULOS:
        arvore = ast.parse((SCRIPTS / "footage" / f"{m}.py").read_text(encoding="utf-8"))
        for no in arvore.body:
            if isinstance(no, ast.Expr):
                assert isinstance(no.value, ast.Constant), f"{m}.py: chamada solta na linha {no.lineno}"
            elif isinstance(no, (ast.For, ast.While, ast.With, ast.Try, ast.If)):
                if isinstance(no, ast.If) and "__name__" in ast.dump(no.test):
                    continue
                pytest.fail(f"{m}.py: bloco de execução no topo, linha {no.lineno}")


def test_renderizadores_mortos_nao_existem_mais_nos_modulos():
    mortos = ("def caption_ass", "def hero_lettering_ass", "def serif_lettering_ass", "def r_split(",
              "def r_lettering", "LETTER_STYLE", "TRANS=[", "_xf_tipo_legado", "def smart_lines")
    for m in MODULOS:
        texto = (SCRIPTS / "footage" / f"{m}.py").read_text(encoding="utf-8")
        for morto in mortos:
            assert morto not in texto, f"{m}.py ainda traz {morto!r}"


def test_o_mutante_do_xf_continua_achando_a_constante_exatamente_uma_vez():
    """A paridade aplica regex nos .py de scripts/: o literal tem que existir uma vez, em um arquivo."""
    achados = 0
    for p in SCRIPTS.rglob("*.py"):
        if p.name.startswith("test_"):
            continue
        achados += len(re.findall(r'("VAM_XF",\s*")0\.08(")', p.read_text(encoding="utf-8")))
    assert achados == 1
    achados = 0
    for p in SCRIPTS.rglob("*.py"):
        if p.name.startswith("test_"):
            continue
        achados += len(re.findall(r'("VAM_XF_SECO",\s*")0\.04(")', p.read_text(encoding="utf-8")))
    assert achados == 1


# ------------------------------------------------------------------ W3.X L6: o ambiente passado chega ao render

def test_l6_config_le_a_geometria_do_split_do_ambiente_passado(tmp_path, monkeypatch):
    monkeypatch.setenv("VAM_SPLIT_TOP_H", "1300")
    env = {"VAM_AVATAR": "/a.mp4", "VAM_ROTEIRO": "/r.txt", "VAM_DADOS": str(tmp_path),
           "VAM_SPLIT_TOP_H": "1000", "VAM_SPLIT_GRAD": "60", "VAM_SPLIT_BIAS": "0.25"}
    geo = MO.ler_config(env).split
    assert (geo.top_h, geo.grad, geo.bias) == (1000, 60, "0.25")


def test_l6_o_contexto_do_render_leva_a_geometria_da_config(mundo, monkeypatch):
    env, _dados, _eventos, _palavras = mundo
    vistos = []

    def renderiza(blocks, spans, ctx):
        vistos.append(ctx.split)
        out = []
        for i in range(len(blocks)):
            p = os.path.join(ctx.tmp, f"s{i:02d}.mp4")
            Path(p).write_bytes(b"x")
            out.append(p)
        return out

    monkeypatch.setattr(RS, "renderizar_todos", renderiza)
    assert MO.main(env=dict(env, VAM_SPLIT_TOP_H="1000")) == 0
    assert vistos and vistos[0].top_h == 1000
