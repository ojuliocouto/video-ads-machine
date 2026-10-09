"""O gravado sai do motor privado sem nada do dono, de cliente ou da máquina de quem escreveu (W2.D).

A varredura é por HASH: `denylist_local.sha256` guarda o sha256 de cada termo proibido (em
minúsculas), e o teste calcula o hash de cada sequência de 1 a 3 palavras dos arquivos. Assim o
repo não carrega os nomes que proíbe. O gate vale para `scripts/gravado` e para os testes do
gravado, e o próprio teste prova que a varredura não é vazia: ele planta cada termo (montado em
pedaços, para não aparecer escrito aqui) e confere que é pego.
"""
import ast
import hashlib
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SCRIPTS = RAIZ / "scripts"
GRAVADO = SCRIPTS / "gravado"
TESTES = Path(__file__).resolve().parent
DENYLIST = TESTES / "denylist_local.sha256"

# Cada termo proibido, em pedaços: junto dá o termo, separado não casa com nada.
PLANTADOS = [("th", "ales"), ("jh", "eni"), ("jú", "lio"), ("ju", "lio"), ("oc", "c"),
             ("lar", "ay"), ("brí", "gida"), ("bri", "gida"), ("opera", "ção claude co", "de"),
             ("opera", "cao claude co", "de")]


def _hashes():
    saida = set()
    for linha in DENYLIST.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#"):
            saida.add(linha)
    return saida


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _sha(texto):
    return hashlib.sha256(unicodedata.normalize("NFC", texto).encode("utf-8")).hexdigest()


def achados_no_texto(texto, hashes):
    """Sequências de 1 a 3 palavras (só letras, sem caixa) cujo sha256 está na lista."""
    tokens = re.findall(r"[^\W\d_]+", texto.casefold())
    achados = []
    for n in (1, 2, 3):
        for i in range(len(tokens) - n + 1):
            gram = " ".join(tokens[i:i + n])
            if _sha(gram) in hashes or _sha(_sem_acento(gram)) in hashes:
                achados.append(gram)
    return achados


def _arquivos_de_texto():
    saida = []
    for base in (GRAVADO, TESTES):
        for p in sorted(base.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix in (".py", ".sh", ".md", ".json", ".txt"):
                saida.append(p)
    return saida


def test_a_lista_de_hashes_existe_e_tem_o_formato_certo():
    hs = _hashes()
    assert len(hs) >= 10
    for h in hs:
        assert re.fullmatch(r"[0-9a-f]{64}", h), h


@pytest.mark.parametrize("partes", PLANTADOS)
def test_a_varredura_pega_cada_termo_proibido_plantado(partes):
    planta = "".join(partes)
    assert achados_no_texto("trecho qualquer de texto, " + planta + ", e mais texto", _hashes()), planta
    assert achados_no_texto(planta.upper() + "6", _hashes()), planta         # maiúscula e número colado


def test_a_varredura_nao_acusa_texto_comum():
    assert achados_no_texto("o apresentador grava o take, o diretor aprova e a estrategista confere",
                            _hashes()) == []


def test_ha_arquivos_para_varrer():
    nomes = {p.name for p in _arquivos_de_texto()}
    assert "gate_ar_morto.py" in nomes and "test_sem_cliente.py" in nomes


def test_zero_vocabulario_de_cliente_nos_arquivos_do_gravado_e_dos_testes():
    hs = _hashes()
    sujos = {}
    for p in _arquivos_de_texto():
        achados = achados_no_texto(p.read_text(encoding="utf-8"), hs)
        if achados:
            sujos[str(p.relative_to(RAIZ))] = sorted(set(achados))
    assert not sujos, sujos


def test_nenhum_caminho_da_maquina_do_dono_nem_nome_de_credencial_antiga():
    proibido = ["/Users/", "~/.claude", ".claude/", "google-tokens", "Library/Fonts", ".local/bin",
                "creds.sh", "ELEVEN_KEY", "GROQ_KEY", "VAM_PROJETO", "creative-studio"]
    ruins = []
    for p in sorted(GRAVADO.rglob("*.py")):
        texto = p.read_text(encoding="utf-8")
        for termo in proibido:
            if termo in texto:
                ruins.append((p.name, termo))
    assert not ruins, ruins


def test_zero_travessao_no_gravado_e_nos_testes():
    ruins = []
    for p in _arquivos_de_texto():
        texto = p.read_text(encoding="utf-8")
        if chr(0x2014) in texto or chr(0x2013) in texto:
            ruins.append(p.name)
    assert not ruins, ruins


def test_os_arquivos_de_cliente_e_de_drive_nao_vieram():
    ausentes = ["exemplo_conferencia_occ6.py", "subir_drive.py", "conferir_drive.py", "renomear_drive.py",
                "teste_caixinha_fundo_preto.png", "novo_projeto.sh", "plano.exemplo.py", "parakeet_lote.sh"]
    for nome in ausentes:
        assert not (GRAVADO / nome).exists(), nome
    assert not any(GRAVADO.rglob("*drive*"))


def test_os_dicionarios_de_cliente_nao_existem_como_nome_de_modulo():
    proibidos = {"GANCHO", "PIOR", "PROMPT", "CORRECOES"}
    achados = []
    for p in sorted(GRAVADO.rglob("*.py")):
        arvore = ast.parse(p.read_text(encoding="utf-8"))
        for no in arvore.body:
            alvos = no.targets if isinstance(no, ast.Assign) else ([no.target] if isinstance(no, ast.AnnAssign) else [])
            for a in alvos:
                if isinstance(a, ast.Name) and a.id in proibidos:
                    achados.append((p.name, a.id))
    assert not achados, achados


def test_o_plano_do_projeto_nunca_e_codigo_que_executa():
    texto = (GRAVADO / "projeto.py").read_text(encoding="utf-8")
    for perigo in ("spec_from_file_location", "exec_module", "exec(", "eval("):
        assert perigo not in texto, perigo


def _modulos_do_gravado():
    nomes = []
    for p in sorted(GRAVADO.glob("*.py")):
        if p.name != "__init__.py":
            nomes.append("gravado." + p.stem)
    for p in sorted((GRAVADO / "nucleo").glob("*.py")):
        if p.name != "__init__.py":
            nomes.append("gravado.nucleo." + p.stem)
    return nomes


def test_ha_modulos_para_importar():
    nomes = _modulos_do_gravado()
    assert "gravado.nucleo.energia" in nomes and "gravado.montar" in nomes and len(nomes) >= 30


@pytest.mark.parametrize("modulo", _modulos_do_gravado())
def test_importar_nao_executa_nada_nem_cria_arquivo_nem_chama_ffmpeg(tmp_path, modulo):
    """Sem ffmpeg no PATH e numa pasta vazia: o import tem que passar calado e não criar nada."""
    vazio = tmp_path / "sem_path"
    vazio.mkdir()
    trabalho = tmp_path / "trabalho"
    trabalho.mkdir()
    env = dict(os.environ)
    env.update({"PATH": str(vazio), "PYTHONPATH": str(SCRIPTS), "PYTHONDONTWRITEBYTECODE": "1"})
    r = subprocess.run([sys.executable, "-c", "import importlib,sys; importlib.import_module(sys.argv[1])", modulo],
                       cwd=str(trabalho), env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    assert r.stdout == "" and r.stderr == ""
    assert list(trabalho.iterdir()) == []
