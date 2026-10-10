"""A varredura de nomes proibidos (W6.D): o repo não carrega os nomes que proíbe, só os hashes.

Cada termo plantado aqui é montado em pedaços, para este arquivo não ser o primeiro a violar a regra.
"""
import hashlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "scripts" / "dev" / "varrer_nomes.py"
LISTA = RAIZ / "scripts" / "dev" / "denylist.sha256"
sys.path.insert(0, str(RAIZ / "scripts" / "dev"))
import varrer_nomes as V  # noqa: E402

# termo proibido -> pedaços (juntos dão o termo; separados não casam com nada)
PLANTADOS = [("th", "ales"), ("jh", "eni"), ("jú", "lio"), ("ju", "lio"), ("oc", "c"), ("lar", "ay"),
             ("brí", "gida"), ("bri", "gida"), ("opera", "ção claude co", "de"), ("vaib", "hav"), ("sob", "ral"),
             ("mar", "co aurélio"), ("espu", "ma roxa"), ("jh", "13v2")]


def _rodar(*args):
    return subprocess.run([sys.executable, str(SCRIPT)] + [str(a) for a in args], capture_output=True, text=True)


def _pasta(tmp_path, arquivos):
    for nome, texto in arquivos.items():
        p = tmp_path / nome
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")
    return tmp_path


def test_a_lista_de_hashes_existe_e_so_tem_sha256():
    hs = V.carregar_hashes(LISTA)
    assert len(hs) >= 10
    for h in hs:
        assert re.fullmatch(r"[0-9a-f]{64}", h), h


def test_a_lista_nao_carrega_nenhum_termo_em_texto():
    texto = LISTA.read_text(encoding="utf-8").casefold()
    for partes in PLANTADOS:
        assert "".join(partes) not in texto


@pytest.mark.parametrize("partes", PLANTADOS)
def test_termo_plantado_faz_a_varredura_sair_com_um(tmp_path, partes):
    termo = "".join(partes)
    pasta = _pasta(tmp_path, {"a.py": "# um comentário qualquer\nx = 1  # " + termo + " aqui\n"})
    r = _rodar("--raiz", pasta)
    assert r.returncode == 1, (termo, r.stdout, r.stderr)
    assert "a.py:2" in r.stdout


@pytest.mark.parametrize("variacao", [str.upper, str.title, lambda t: t + "7", lambda t: "_" + t + "_x"])
def test_maiuscula_numero_e_underscore_colados_nao_escondem_o_termo(tmp_path, variacao):
    termo = variacao("".join(("th", "ales")))
    pasta = _pasta(tmp_path, {"a.md": "texto " + termo + " texto\n"})
    assert _rodar("--raiz", pasta).returncode == 1


def test_termo_com_acento_e_sem_acento_sao_pegos(tmp_path):
    for termo in ("".join(("jú", "lio")), "".join(("ju", "lio"))):
        pasta = _pasta(tmp_path / termo[:2], {"a.md": "ordem do " + termo + " de ontem\n"})
        assert _rodar("--raiz", pasta).returncode == 1


def test_o_codigo_de_anuncio_com_numero_e_pego_pelo_prefixo(tmp_path):
    pasta = _pasta(tmp_path, {"a.py": 'AD = "' + "".join(("jh", "13v2")) + '_look"\n'})
    assert _rodar("--raiz", pasta).returncode == 1


def test_variavel_curta_e_codigo_de_anuncio_generico_nao_sao_acusados(tmp_path):
    pasta = _pasta(tmp_path, {"a.py": "jw, jh = 10, 20\nAD = 'ad99v2_look_a'\n# o apresentador, o diretor e a estrategista\n"})
    r = _rodar("--raiz", pasta)
    assert r.returncode == 0, r.stdout


def test_o_nome_do_arquivo_tambem_e_varrido(tmp_path):
    pasta = _pasta(tmp_path, {"notas_" + "".join(("th", "ales")) + ".md": "texto limpo\n"})
    r = _rodar("--raiz", pasta)
    assert r.returncode == 1 and "nome do arquivo" in r.stdout


def test_so_a_linha_de_copyright_de_license_e_notice_e_isenta(tmp_path):
    termo = "".join(("ju", "lio"))
    pasta = _pasta(tmp_path, {"LICENSE": "MIT\nCopyright (c) 2026 " + termo + " Fulano\n",
                              "NOTICE": "Copyright (c) 2026 " + termo + " Fulano\n"})
    assert _rodar("--raiz", pasta).returncode == 0
    (pasta / "NOTICE").write_text("Copyright (c) 2026 Fulano\nobra de " + termo + "\n", encoding="utf-8")
    assert _rodar("--raiz", pasta).returncode == 1
    (pasta / "NOTICE").unlink()
    (pasta / "README.md").write_text("Copyright (c) 2026 " + termo + "\n", encoding="utf-8")
    assert _rodar("--raiz", pasta).returncode == 1       # a isenção é só de LICENSE e NOTICE


def test_arquivo_sha256_e_arquivo_binario_nao_sao_varridos(tmp_path):
    termo = "".join(("th", "ales"))
    pasta = _pasta(tmp_path, {"lista.sha256": termo + "\n", "foto.png": termo})
    assert _rodar("--raiz", pasta).returncode == 0


def test_lista_ausente_ou_invalida_sai_com_dois(tmp_path):
    pasta = _pasta(tmp_path, {"a.md": "limpo\n"})
    assert _rodar("--raiz", pasta, "--denylist", tmp_path / "nao-existe.sha256").returncode == 2
    ruim = tmp_path / "ruim.sha256"
    ruim.write_text("# só comentário\nisto-nao-e-um-hash\n", encoding="utf-8")
    assert _rodar("--raiz", pasta, "--denylist", ruim).returncode == 2
    vazia = tmp_path / "vazia.sha256"
    vazia.write_text("# nada\n", encoding="utf-8")
    assert _rodar("--raiz", pasta, "--denylist", vazia).returncode == 2


def test_lista_propria_pega_o_termo_dela(tmp_path):
    lista = tmp_path / "minha.sha256"
    lista.write_text(hashlib.sha256(b"abracadabra").hexdigest() + "\n", encoding="utf-8")
    pasta = _pasta(tmp_path / "p", {"a.md": "diga ABRACADABRA agora\n"})
    assert _rodar("--raiz", pasta, "--denylist", lista).returncode == 1


def test_o_repo_inteiro_esta_limpo():
    r = _rodar()
    assert r.returncode == 0, r.stdout[-2000:]
