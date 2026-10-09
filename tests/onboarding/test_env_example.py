"""`.env.example` (W1.D): toda variável que os scripts leem do ambiente está documentada.

A varredura é por AST, não por grep: pega `os.environ.get("X")`, `os.environ["X"]`,
`"X" in os.environ`, `os.getenv("X")`, `amb.env.get("X")` (os backends de áudio leem o
ambiente injetado), o helper `_env("X", ...)` do `caminhos.py` e o laço
`for v in ("A", "B"): os.environ.get(v)`. Se um script novo ler uma variável nova, este teste
fica vermelho até ela entrar no `.env.example`.
"""
import ast
import re
import warnings
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent.parent
SCRIPTS = RAIZ / "scripts"
ENV_EXAMPLE = RAIZ / ".env.example"

# O que o sistema operacional define e nenhum aluno configura: não vai no .env.example.
DO_SISTEMA = {"HOME", "PATH", "USERPROFILE", "TMPDIR", "PYTHONPATH", "VIRTUAL_ENV"}


def _eh_ambiente(no):
    """`os.environ`, `_os.environ`, `environ`, `env` ou `<x>.env` (ambiente injetado)."""
    if isinstance(no, ast.Attribute) and no.attr in ("environ", "env"):
        return True
    return isinstance(no, ast.Name) and no.id in ("environ", "env")


def _constantes_do_laco(no, pais):
    """Se `no` é um nome que o laço/compreensão mais próximo percorre em literais, devolve-os."""
    atual = no
    while atual in pais:
        atual = pais[atual]
        alvos = []
        if isinstance(atual, ast.comprehension):
            alvos = [(atual.target, atual.iter)]
        elif isinstance(atual, ast.For):
            alvos = [(atual.target, atual.iter)]
        for alvo, iteravel in alvos:
            if isinstance(alvo, ast.Name) and alvo.id == no.id and isinstance(
                    iteravel, (ast.Tuple, ast.List)):
                return [e.value for e in iteravel.elts if isinstance(e, ast.Constant)]
    return []


def variaveis_lidas(arquivo):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")        # escape inválido de script alheio não é problema daqui
        arvore = ast.parse(Path(arquivo).read_text(encoding="utf-8"))
    pais = {filho: pai for pai in ast.walk(arvore) for filho in ast.iter_child_nodes(pai)}
    achadas = set()

    def tratar(chave):
        if isinstance(chave, ast.Constant) and isinstance(chave.value, str):
            achadas.add(chave.value)
        elif isinstance(chave, ast.Name):
            achadas.update(_constantes_do_laco(chave, pais))

    for no in ast.walk(arvore):
        if isinstance(no, ast.Call):
            f = no.func
            if isinstance(f, ast.Attribute) and f.attr in ("get", "pop", "setdefault") \
                    and _eh_ambiente(f.value) and no.args:
                tratar(no.args[0])
            elif isinstance(f, ast.Attribute) and f.attr == "getenv" and no.args:
                tratar(no.args[0])
            elif isinstance(f, ast.Name) and f.id in ("getenv", "_env") and no.args:
                tratar(no.args[0])
        elif isinstance(no, ast.Subscript) and _eh_ambiente(no.value) \
                and isinstance(no.ctx, ast.Load):
            tratar(no.slice if not hasattr(ast, "Index") or not isinstance(no.slice, ast.Index)
                   else no.slice.value)
        elif isinstance(no, ast.Compare) and any(isinstance(o, (ast.In, ast.NotIn))
                                                 for o in no.ops):
            if any(_eh_ambiente(c) for c in no.comparators):
                tratar(no.left)
    return {v for v in achadas if re.match(r"^[A-Z][A-Z0-9_]*$", v)}


def arquivos_do_motor():
    saida = []
    for p in sorted(SCRIPTS.rglob("*.py")):
        if p.name.startswith("test_") or "__pycache__" in p.parts:
            continue
        saida.append(p)
    return saida


def variaveis_do_example():
    texto = ENV_EXAMPLE.read_text(encoding="utf-8")
    return set(re.findall(r"^\s*#?\s*([A-Z][A-Z0-9_]*)=", texto, flags=re.M))


def todas_as_lidas():
    lidas = {}
    for p in arquivos_do_motor():
        for v in variaveis_do_script(p):
            lidas.setdefault(v, []).append(str(p.relative_to(RAIZ)))
    return lidas


def variaveis_do_script(p):
    return variaveis_lidas(p) - DO_SISTEMA


# --- a varredura em si funciona -------------------------------------------------------------------

def test_varredura_pega_cada_forma_de_ler_o_ambiente(tmp_path):
    arq = tmp_path / "exemplo.py"
    arq.write_text("\n".join([
        "import os",
        "import os as _os",
        "a = os.environ.get('FORMA_GET')",
        "b = os.environ['FORMA_INDICE']",
        "c = 'FORMA_IN' in os.environ",
        "d = os.getenv('FORMA_GETENV')",
        "e = amb.env.get('FORMA_INJETADO')",
        "f = _os.environ.get('FORMA_ALIAS', '1')",
        "g = _env('FORMA_HELPER', None)",
        "h = [v for v in ('FORMA_LACO_A', 'FORMA_LACO_B') if os.environ.get(v) == '0']",
        "i = os.environ.get('minuscula')",
        "os.environ.setdefault('FORMA_SETDEFAULT', 'x')",
    ]), encoding="utf-8")
    assert variaveis_lidas(arq) == {
        "FORMA_GET", "FORMA_INDICE", "FORMA_IN", "FORMA_GETENV", "FORMA_INJETADO", "FORMA_ALIAS",
        "FORMA_HELPER", "FORMA_LACO_A", "FORMA_LACO_B", "FORMA_SETDEFAULT"}


def test_a_varredura_enxerga_as_variaveis_conhecidas_do_motor():
    lidas = todas_as_lidas()
    for conhecida in ("HEYGEN_API_KEY", "GROQ_API_KEY", "VAM_DADOS", "FASE_GATE", "FIDELIDADE",
                      "FASE_GATE_LEGADO", "GATE_FMT", "VAM_MUSICA", "HEYGEN_ENGINE_OVERRIDE",
                      "WHISPER_SIZE", "ACCEL_FINAL"):
        assert conhecida in lidas, f"a varredura deveria ter achado {conhecida}"


# --- o contrato -----------------------------------------------------------------------------------

def test_env_example_existe():
    assert ENV_EXAMPLE.is_file()


def test_toda_variavel_lida_pelos_scripts_esta_no_env_example():
    documentadas = variaveis_do_example()
    faltam = {v: onde for v, onde in todas_as_lidas().items() if v not in documentadas}
    assert not faltam, ("variáveis lidas e ausentes do .env.example: "
                        + "; ".join(f"{v} ({', '.join(sorted(set(o)))})"
                                    for v, o in sorted(faltam.items())))


def test_env_example_nao_documenta_variavel_que_ninguem_le():
    """Fantasma no .env.example engana o aluno: sobra = variável que nenhum script lê."""
    sobram = variaveis_do_example() - set(todas_as_lidas())
    assert not sobram, f"documentadas e nunca lidas: {sorted(sobram)}"


def test_chaves_de_api_vem_vazias_nunca_com_valor():
    texto = ENV_EXAMPLE.read_text(encoding="utf-8")
    for linha in texto.splitlines():
        m = re.match(r"^\s*#?\s*([A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*)=(.*)$",
                     linha)
        if m:
            assert m.group(2).strip() == "", f"{m.group(1)} não pode trazer valor no exemplo"


def test_as_duas_chaves_do_aluno_estao_ativas_e_vazias():
    texto = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert re.search(r"^HEYGEN_API_KEY=$", texto, flags=re.M)
    assert re.search(r"^GROQ_API_KEY=$", texto, flags=re.M)


def test_so_as_chaves_ficam_ativas_o_resto_e_comentado_para_nao_mudar_o_comportamento():
    """Copiar .env.example para .env não pode ligar bypass nem trocar caminho sem querer."""
    ativas = re.findall(r"^([A-Z][A-Z0-9_]*)=", ENV_EXAMPLE.read_text(encoding="utf-8"), re.M)
    assert set(ativas) <= {"HEYGEN_API_KEY", "GROQ_API_KEY"}, ativas


def test_cada_variavel_tem_uma_linha_de_comentario_logo_acima_ou_na_secao():
    """Sem ruído: toda variável vem depois de pelo menos um comentário."""
    linhas = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    for i, linha in enumerate(linhas):
        if re.match(r"^\s*#?\s*[A-Z][A-Z0-9_]*=", linha):
            anteriores = [l for l in linhas[:i] if l.startswith("#")]
            assert anteriores, f"{linha!r} está sem comentário nenhum antes"


def test_env_real_nunca_entra_no_git():
    ignorados = (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in [l.strip() for l in ignorados]


def test_env_example_sem_travessao():
    texto = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "\u2014" not in texto and "\u2013" not in texto


@pytest.mark.parametrize("nome", ["HEYGEN_API_KEY", "GROQ_API_KEY"])
def test_a_chave_diz_onde_conseguir(nome):
    texto = ENV_EXAMPLE.read_text(encoding="utf-8")
    bloco = texto.split(f"{nome}=")[0].splitlines()[-6:]
    assert any("http" in l or "app." in l or "console." in l for l in bloco), nome
