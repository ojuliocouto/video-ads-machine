"""O instrumento da paridade mede de verdade? (W0.3)

Paridade que nunca reprova não prova nada. Este arquivo valida o próprio instrumento:

  1. o COMMIT BASE (o do golden) reproduz o golden, qualquer que seja o working tree;
  2. cada MUTANTE (uma mudança de uma constante, aplicada numa cópia do motor) reprova;
  3. o mutante pedido no plano (XF_SECO 0,04 para 0,05) é EQUIVALENTE: a constante só
     liga o concat quando fica abaixo de 0,01 junto com XF, então 0,05 não muda argv nem
     quadro. O teste registra isso em vez de fingir que reprova. O gêmeo vivo é o XF;
  4. as peças do instrumento (normalização, sitecustomize, comparador, mutação) fazem o que
     dizem, sem precisar de mídia.

Tudo `midia_real`: o que depende da mídia pula com o motivo quando VAM_PARIDADE_MIDIA
falta; os testes de peça (4) não dependem dela.

Cada mutante é (regex, substituição) e vale em QUALQUER arquivo de scripts/: depois da W2
a constante pode ter mudado de módulo e o mutante continua achando-a. Se o padrão deixar
de casar exatamente uma vez, o teste falha dizendo para atualizar o mutante.
"""
import json
import os
import subprocess
import sys

import pytest

from tests.paridade import capturar as C
from tests.paridade import normalizar as N
from tests.paridade import sitecustomize as SC

pytestmark = pytest.mark.midia_real

# nome -> (regex, substituição, etapas, o que tem que reprovar)
MUTANTES = {
    # transição "volta macia" de 0,08 s para 0,10 s: muda o xfade, a duração e os quadros
    "xf_volta_macia": (r'("VAM_XF",\s*")0\.08(")', r"\g<1>0.10\g<2>",
                       ("footage",), ("footage/video.framemd5", "argv/footage.jsonl")),
    # raio da moldura do navegador: o argv é IDÊNTICO (o PNG tem o mesmo nome), só o quadro muda.
    # Prova que o framemd5 enxerga o que o argv não vê.
    "moldura_raio": (r"(?m)^RAIO = 24$", "RAIO = 26",
                     ("footage",), ("footage/video.framemd5",)),
    # teto do hook: muda o HTML do overlay e a prancha
    "hook_teto": (r"(HOOK_MAX\s*=\s*)3\.2\b", r"\g<1>3.0",
                  ("overlay",), ("overlay/index.html", "overlay/prancha.json")),
}

# o mutante literal do plano
XF_SECO = (r'("VAM_XF_SECO",\s*")0\.04(")', r"\g<1>0.05\g<2>")


@pytest.fixture(scope="module")
def midia():
    return C.exigir_midia()


@pytest.fixture(scope="module")
def golden(midia):
    arquivos, _hashes, manifesto = C.ler_golden(midia)
    return arquivos, manifesto


def _pref(etapas):
    pref = []
    if "overlay" in etapas:
        pref += ["overlay/", "argv/overlay.jsonl"]
    if "footage" in etapas:
        pref += ["footage/", "argv/footage.jsonl"]
    return tuple(pref)


# --- 1. o commit base reproduz o golden ---------------------------------------------------

def test_golden_nasceu_de_um_commit_limpo(golden):
    _arquivos, manifesto = golden
    assert manifesto["commit_motor"], "o golden não registra de qual commit nasceu"
    assert manifesto["motor_sujo"] is False, (
        "o golden foi gerado de um working tree sujo: ele tem que nascer de um commit "
        "(`capturar.py gerar-golden` numa raiz limpa)")


def test_commit_base_do_golden_reproduz_o_golden(midia, golden, tmp_path):
    """Extrai do git o commit que gerou o golden e o compara com o golden.

    É independente do working tree: se a W2 mexer em tudo, esta continua dizendo se o
    instrumento (ffmpeg, fixture, stubs) ainda reproduz o golden com o motor ORIGINAL.
    Quando o working tree é idêntico ao commit base, reaproveita a captura (memória).
    """
    arquivos, manifesto = golden
    commit = manifesto["commit_motor"]
    try:
        raiz = C.exportar_commit(C.raiz_do_repo(), commit, tmp_path / "base")
    except C.CommitAusente as e:
        pytest.skip(f"commit base {commit[:9]} ausente deste clone ({e}); sem ele não dá para "
                    "provar que o instrumento reproduz o golden com o motor original")
    atual = C.capturar_memo(raiz, midia).arquivos
    diffs = C.comparar(atual, arquivos, prefixos=("overlay", "footage", "argv"))
    assert not diffs, f"o commit base {commit[:9]} NÃO reproduz o golden:\n" + "\n\n".join(diffs)


# --- 2. os mutantes reprovam --------------------------------------------------------------

@pytest.mark.parametrize("nome", sorted(MUTANTES))
def test_mutante_reprova(nome, midia, golden):
    padrao, subst, etapas, deve_reprovar = MUTANTES[nome]
    arquivos, _ = golden
    cap = C.capturar(C.raiz_do_repo(), midia, etapas=etapas, mutacao=(padrao, subst))
    diffs = C.comparar(cap.arquivos, arquivos, prefixos=_pref(etapas))
    reprovados = {d.split(":")[0] for d in diffs}
    faltou = [k for k in deve_reprovar if k not in reprovados]
    assert not faltou, (f"o mutante {nome!r} NÃO foi pego em {faltou}: a paridade deixaria passar "
                        f"essa regressão. Reprovou apenas {sorted(reprovados) or 'nada'}.")


def test_moldura_so_muda_o_quadro_o_argv_e_identico(midia, golden):
    """O argv sozinho não bastaria: o mutante da moldura passa no argv e só o framemd5 pega."""
    padrao, subst, etapas, _ = MUTANTES["moldura_raio"]
    arquivos, _ = golden
    cap = C.capturar(C.raiz_do_repo(), midia, etapas=etapas, mutacao=(padrao, subst))
    assert C.comparar(cap.arquivos, arquivos, prefixos=("argv/footage",)) == []
    assert C.comparar(cap.arquivos, arquivos, prefixos=("footage/video.framemd5",)) != []


# --- 3. o mutante literal do plano é equivalente ------------------------------------------

def test_xf_seco_literal_do_plano_e_mutante_equivalente(midia, golden):
    """XF_SECO 0,04 para 0,05 NÃO reprova a paridade, e não é defeito do instrumento.

    No motor, XF_SECO só entra em `if XF < 0.01 and XF_SECO < 0.01` (liga o concat puro).
    Com XF em 0,08 e XF_SECO acima de 0,01 em qualquer dos dois valores, o ramo é o mesmo:
    argv e quadros idênticos. Se este teste ficar vermelho, alguém tornou XF_SECO
    observável: troque este teste por um mutante de verdade.
    """
    arquivos, _ = golden
    cap = C.capturar(C.raiz_do_repo(), midia, etapas=("footage",), mutacao=XF_SECO)
    assert C.comparar(cap.arquivos, arquivos, prefixos=_pref(("footage",))) == [], (
        "XF_SECO deixou de ser equivalente: agora ele muda a footage. Vire este em mutante "
        "que reprova (e registre no relatório da W2)")


# --- 4. as peças do instrumento, sem mídia ------------------------------------------------

def _tokens(tmp_path):
    for nome in ("raiz", "dados", "estado", "midia", "tmp", "home"):
        (tmp_path / nome).mkdir(exist_ok=True)
    return N.construir_tokens(**{n: tmp_path / n for n in ("raiz", "dados", "estado", "midia", "tmp", "home")})


def test_normalizar_troca_caminhos_do_sandbox_por_tokens(tmp_path):
    t = _tokens(tmp_path)
    dados = os.path.realpath(tmp_path / "dados")
    assert N.normalizar_texto(f"-i {dados}/inputs/a.mp4", t) == "-i <DADOS>/inputs/a.mp4"
    assert N.normalizar_texto(f"{tmp_path}/midia/fixture/x.png", t).startswith("<MIDIA>/fixture/")


def test_normalizar_nao_confunde_caminhos_com_prefixo_em_comum(tmp_path):
    """<TMP> vem antes de <DADOS> na ordem de troca? Nenhum caminho pode virar outro token."""
    (tmp_path / "dados").mkdir()
    (tmp_path / "dados" / "tmp").mkdir()
    t = N.construir_tokens(dados=tmp_path / "dados", tmp=tmp_path / "dados" / "tmp")
    assert N.normalizar_texto(f"{os.path.realpath(tmp_path)}/dados/tmp/x", t) == "<TMP>/x"
    assert N.normalizar_texto(f"{os.path.realpath(tmp_path)}/dados/inputs/x", t) == "<DADOS>/inputs/x"


def test_normalizar_tira_o_nome_aleatorio_do_tempdir(tmp_path):
    t = _tokens(tmp_path)
    a = N.normalizar_texto(f"{tmp_path}/tmp/tmpab12cd34/l.pgm", t)
    b = N.normalizar_texto(f"{tmp_path}/tmp/tmpzz99yy88/l.pgm", t)
    assert a == b == "<TMP>/tmp*/l.pgm"


def test_normalizar_executaveis(tmp_path):
    t = _tokens(tmp_path)
    assert N.normalizar_argv(["/opt/homebrew/bin/ffmpeg", "-y"], t) == ["ffmpeg", "-y"]
    assert N.normalizar_argv(["/usr/bin/ffprobe", "-v", "error"], t)[0] == "ffprobe"
    assert N.normalizar_argv(["/usr/bin/python3.9", "x.py"], t)[0] == "<PY>"
    assert N.normalizar_argv(["/qualquer/lugar/parakeet-mlx", "a.wav"], t)[0] == "<PARAKEET>"
    assert N.normalizar_argv([f"{tmp_path}/raiz/node_modules/.bin/hyperframes", "transcribe"], t)[0] == "<HF>"


def test_normalizar_deixa_filtro_numero_e_ordem_intactos(tmp_path):
    t = _tokens(tmp_path)
    argv = ["ffmpeg", "-filter_complex", "[0:v]xfade=transition=fade:duration=0.08:offset=3.1234,settb=AVTB[v1]",
            "-r", "30", "-crf", "18"]
    assert N.normalizar_argv(argv, t) == argv


def test_normalizar_jsonl_preserva_ordem_e_marca_de_fase(tmp_path):
    t = _tokens(tmp_path)
    bruto = "\n".join(json.dumps(r) for r in (
        {"fase": "footage"},
        {"argv": ["ffmpeg", "-i", f"{tmp_path}/dados/a.mp4"], "cwd": f"{tmp_path}/dados", "shell": False},
        {"argv": ["ffprobe", "b"], "cwd": None, "shell": False}))
    regs = N.normalizar_jsonl(bruto, t)
    assert regs[0] == {"fase": "footage"}
    assert regs[1]["argv"][2] == "<DADOS>/a.mp4" and regs[1]["cwd"] == "<DADOS>"
    assert regs[2]["argv"] == ["ffprobe", "b"] and regs[2]["cwd"] is None


def test_sitecustomize_registro_de_aceita_lista_string_e_pathlike(tmp_path):
    assert SC.registro_de(["ffmpeg", "-i", tmp_path / "a"], {})["argv"] == ["ffmpeg", "-i", str(tmp_path / "a")]
    assert SC.registro_de("echo oi", {"shell": True}) == {"argv": ["echo oi"], "cwd": None, "shell": True}
    assert SC.registro_de(["x"], {"cwd": tmp_path})["cwd"] == str(tmp_path)


def _python_com_hook(tmp_path, codigo, log):
    pasta = tmp_path / "pysite"
    pasta.mkdir(exist_ok=True)
    (pasta / "sitecustomize.py").write_text(
        (C.AQUI / "sitecustomize.py").read_text(encoding="utf-8"), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("VAM_")}
    env.update({"PYTHONPATH": str(pasta), "VAM_PARIDADE_LOG": str(log)})
    return subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, env=env)


def test_sitecustomize_grava_o_argv_e_nao_muda_a_execucao(tmp_path):
    log = tmp_path / "log.jsonl"
    codigo = ("import subprocess, sys\n"
              "r = subprocess.run(['echo', 'ola'], capture_output=True, text=True, cwd='.')\n"
              "sys.stdout.write(r.stdout)\n"
              "subprocess.check_output(['echo', 'dois'])\n")
    r = _python_com_hook(tmp_path, codigo, log)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "ola\n", "o hook mudou a saída do subprocess"
    linhas = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert [x["argv"] for x in linhas] == [["echo", "ola"], ["echo", "dois"]]
    assert linhas[0]["cwd"] == "." and linhas[1]["cwd"] is None


def test_sitecustomize_com_log_ilegivel_ainda_executa(tmp_path):
    """Falha ao gravar o log nunca pode derrubar o motor."""
    log = tmp_path / "nao_existe" / "pasta" / "log.jsonl"
    r = _python_com_hook(tmp_path, "import subprocess; print(subprocess.run(['echo','vivo'], capture_output=True, text=True).stdout.strip())", log)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "vivo"


def test_sitecustomize_sem_variavel_nao_instala_nada(tmp_path):
    pasta = tmp_path / "pysite"
    pasta.mkdir()
    (pasta / "sitecustomize.py").write_text((C.AQUI / "sitecustomize.py").read_text(encoding="utf-8"), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("VAM_")}
    env["PYTHONPATH"] = str(pasta)
    r = subprocess.run([sys.executable, "-c", "import subprocess; print(hasattr(subprocess.Popen, '_paridade_instalado'))"],
                       capture_output=True, text=True, env=env)
    assert r.stdout.strip() == "False"


def test_comparar_acusa_uma_diferenca_de_um_caractere():
    g = {"overlay/index.html": "<html>a</html>\n", "argv/footage.jsonl": "{}\n"}
    a = dict(g)
    assert C.comparar(a, g, prefixos=("overlay", "argv")) == []
    a["overlay/index.html"] = "<html>b</html>\n"
    diffs = C.comparar(a, g, prefixos=("overlay", "argv"))
    assert len(diffs) == 1 and diffs[0].startswith("overlay/index.html: sha256 diferente")
    assert "-<html>a</html>" in diffs[0] and "+<html>b</html>" in diffs[0]


def test_diff_de_argv_aponta_o_numero_que_mudou_e_nao_a_linha_inteira():
    """Um registro de argv tem 2 mil caracteres; o diff tem que mostrar SÓ o filtro que mudou."""
    def reg(dur):
        return json.dumps({"argv": ["ffmpeg", "-filter_complex",
                                    f"[0:v]fps=30;[1:v]xfade=transition=fade:duration={dur}:offset=3.1[v1];"
                                    "[v1]settb=AVTB[v]", "-r", "30"],
                           "cwd": None, "shell": False}) + "\n"
    diffs = C.comparar({"argv/footage.jsonl": reg("0.10")}, {"argv/footage.jsonl": reg("0.08")},
                       prefixos=("argv",))
    assert len(diffs) == 1
    mudou = [l for l in diffs[0].splitlines() if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    assert [l[0] for l in mudou] == ["-", "+"], mudou
    assert "duration=0.08" in mudou[0] and "duration=0.10" in mudou[1]
    assert "settb=AVTB" not in mudou[0], "o diff arrastou o resto do registro junto"


def test_comparar_acusa_chave_que_existe_so_de_um_lado():
    diffs = C.comparar({"overlay/a": "x"}, {"overlay/b": "x"}, prefixos=("overlay",))
    assert sorted(d.split(":")[0] for d in diffs) == ["overlay/a", "overlay/b"]


def test_comparar_ignora_chaves_fora_dos_prefixos():
    assert C.comparar({"footage/x": "1"}, {"footage/x": "2"}, prefixos=("overlay",)) == []


def test_comparar_sem_ordem_aceita_reordenacao_mas_acusa_comando_novo():
    g = {"argv/footage.jsonl": "a\nb\nc\n"}
    assert C.comparar_sem_ordem({"argv/footage.jsonl": "c\na\nb\n"}, g, chaves=["argv/footage.jsonl"]) == []
    assert C.comparar({"argv/footage.jsonl": "c\na\nb\n"}, g, prefixos=("argv",)) != [], "a ordem estrita tem que pegar"
    diffs = C.comparar_sem_ordem({"argv/footage.jsonl": "a\nb\nc\nd\n"}, g, chaves=["argv/footage.jsonl"])
    assert len(diffs) == 1 and "1 linha(s) a mais" in diffs[0]


def _raiz_com_constante(tmp_path, *arquivos):
    for rel, texto in arquivos:
        p = tmp_path / "scripts" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")
    return tmp_path


def test_mutacao_acha_a_constante_em_qualquer_arquivo_de_scripts(tmp_path):
    raiz = _raiz_com_constante(tmp_path, ("outro.py", "x = 1\n"), ("footage/cadeia.py", 'XF = float(os.environ.get("VAM_XF", "0.08"))\n'))
    C._aplicar_mutacao(raiz, MUTANTES["xf_volta_macia"][:2])
    assert '"0.10"' in (raiz / "scripts" / "footage" / "cadeia.py").read_text(encoding="utf-8")


def test_mutacao_que_nao_casa_exatamente_uma_vez_falha_com_mensagem_clara(tmp_path):
    raiz = _raiz_com_constante(tmp_path, ("a.py", "x = 1\n"))
    with pytest.raises(C.CapturaFalhou, match="casa 0 vez"):
        C._aplicar_mutacao(raiz, MUTANTES["xf_volta_macia"][:2])
    raiz2 = _raiz_com_constante(tmp_path / "dois", ("a.py", 'a = os.environ.get("VAM_XF", "0.08")\nb = os.environ.get("VAM_XF", "0.08")\n'))
    with pytest.raises(C.CapturaFalhou, match="casa 2 vez"):
        C._aplicar_mutacao(raiz2, MUTANTES["xf_volta_macia"][:2])


def test_impressao_do_motor_ignora_bytecode_e_testes_mas_pega_mudanca(tmp_path):
    raiz = _raiz_com_constante(tmp_path, ("a.py", "x = 1\n"))
    antes = C.impressao_motor(raiz)
    (raiz / "scripts" / "__pycache__").mkdir()
    (raiz / "scripts" / "__pycache__" / "a.cpython-39.pyc").write_bytes(b"\x00")
    (raiz / "scripts" / "test_a.py").write_text("def test(): pass\n", encoding="utf-8")
    assert C.impressao_motor(raiz) == antes
    (raiz / "scripts" / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert C.impressao_motor(raiz) != antes
