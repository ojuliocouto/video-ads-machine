"""doctor (W1.D): cada check devolve OK, WARN ou FAIL com UMA linha de conserto.

Nada aqui toca a máquina de quem roda o teste: o PATH, as variáveis, o subprocesso e a rede
são injetados no `AmbienteDoctor`. O repo é um repo falso em tmp_path. Nenhuma chamada paga.
"""
import ast
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from onboarding import doctor as D
from onboarding.checks import (ffmpeg_libass, fontes, heygen, node_hyperframes, python_deps,
                               rede, transcritor)

RAIZ_REAL = Path(__file__).resolve().parent.parent.parent
CHAVE = "hg_chave_secreta_de_teste_123456"


# --- repo falso e ambiente falso ---------------------------------------------------------------

def _escrever(caminho, conteudo="x", modo=None):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo, encoding="utf-8")
    if modo is not None:
        caminho.chmod(modo)
    return caminho


@pytest.fixture
def repo(tmp_path):
    """Repo falso saudável: package.json pinado, HyperFrames instalado, fontes e GSAP local."""
    raiz = tmp_path / "repo"
    _escrever(raiz / "package.json", json.dumps({"dependencies": {"hyperframes": "0.7.56"}}))
    _escrever(raiz / "node_modules/.bin/hyperframes", "#!/bin/sh\necho 0.7.56\n", 0o755)
    _escrever(raiz / "node_modules/hyperframes/package.json", json.dumps({"version": "0.7.56"}))
    for nome in ("inter-400.woff2", "inter-700.woff2", "playfair-italic-500.woff2"):
        _escrever(raiz / "fonts" / nome)
    _escrever(raiz / "templates/reel-editorial/index.html", """
        <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
        @font-face { src:url("fonts/inter-400.woff2") format("woff2"); }
        @font-face { src:url("fonts/inter-700.woff2") format("woff2"); }
        @font-face { src:url("fonts/playfair-italic-500.woff2") format("woff2"); }
    """)
    _escrever(raiz / "templates/_vendor/gsap.min.js", "/* gsap */" + "x" * 3000)
    return raiz


def executar_falso(regras, chamadas=None):
    """`regras`: lista de (predicado(cmd), (rc, saida)). A primeira que casa responde."""
    def executar(cmd, timeout=60):
        if chamadas is not None:
            chamadas.append(list(cmd))
        for teste, resposta in regras:
            if teste(cmd):
                return resposta
        return (127, "comando não injetado")
    return executar


def exe(nome, *args):
    """Casa o comando pelo NOME do executável (basename), nunca por pedaço do caminho: o
    tmp_path do pytest carrega o nome do teste e acabaria casando 'ffmpeg' ou 'node'."""
    return lambda cmd: (os.path.basename(str(cmd[0])) == nome
                        and all(a in [str(x) for x in cmd] for a in args))


def python_c():
    return lambda cmd: (os.path.basename(str(cmd[0])).startswith("python") and "-c" in cmd)


REGRAS_SAUDAVEIS = [
    (exe("ffmpeg", "-vf"), (0, "")),
    (exe("node", "--version"), (0, "v22.11.0")),
    (exe("hyperframes", "--version"), (0, "0.7.56")),
    (python_c(), (0, "3 11\n\n")),
    (exe("parakeet-mlx", "--help"), (0, "usage")),
]


def amb_falso(raiz, *, sistema="Darwin", arquitetura="arm64", env=None, executaveis=None,
              modulos=("faster_whisper",), regras=None, http=None, chamadas=None):
    executaveis = ("ffmpeg", "ffprobe", "node", "npm") if executaveis is None else executaveis
    return D.AmbienteDoctor(
        raiz=raiz, sistema=sistema, arquitetura=arquitetura, env=dict(env or {}),
        which=lambda nome: (f"/falso/bin/{nome}" if nome in executaveis else None),
        importavel=lambda nome: nome in modulos,
        executar=executar_falso(REGRAS_SAUDAVEIS if regras is None else regras, chamadas),
        http_get=http, python="/falso/bin/python3")


def http_falso(resposta, chamadas=None):
    def http_get(url, headers=None, timeout=10, metodo="GET"):
        if chamadas is not None:
            chamadas.append({"url": url, "headers": dict(headers or {}), "metodo": metodo})
        if isinstance(resposta, Exception):
            raise resposta
        return resposta
    return http_get


def conserto_de_uma_linha(r):
    assert "\n" not in r.conserto and "\n" not in r.detalhe
    assert "Traceback" not in r.detalhe + r.conserto


# --- Resultado -----------------------------------------------------------------------------------

def test_resultado_so_aceita_ok_warn_fail():
    with pytest.raises(ValueError):
        D.Resultado("x", "TALVEZ")
    for s in ("OK", "WARN", "FAIL"):
        assert D.Resultado("x", s).status == s


def test_resultado_normaliza_conserto_para_uma_linha():
    r = D.Resultado("x", "FAIL", "linha um\nlinha dois", "passo um\n  passo dois")
    conserto_de_uma_linha(r)
    assert "passo um" in r.conserto and "passo dois" in r.conserto


# --- ffmpeg_libass -------------------------------------------------------------------------------

def test_ffmpeg_ausente_e_fail_com_comando_de_instalar(repo):
    r = ffmpeg_libass.checar(amb_falso(repo, executaveis=("ffprobe",)))
    assert r.status == "FAIL" and r.nome == "ffmpeg_libass"
    assert "brew install ffmpeg" in r.conserto
    conserto_de_uma_linha(r)


def test_ffprobe_ausente_e_fail(repo):
    r = ffmpeg_libass.checar(amb_falso(repo, executaveis=("ffmpeg",)))
    assert r.status == "FAIL" and "ffprobe" in r.detalhe
    conserto_de_uma_linha(r)


def test_ffmpeg_que_renderiza_pelo_filtro_subtitles_e_ok(repo):
    chamadas = []
    r = ffmpeg_libass.checar(amb_falso(repo, chamadas=chamadas))
    assert r.status == "OK"
    sonda = [c for c in chamadas if "ffmpeg" in c[0]]
    assert sonda, "o check tem que RENDERIZAR, não só perguntar a versão"
    vf = sonda[0][sonda[0].index("-vf") + 1]
    assert vf.startswith("subtitles=")


def test_ffmpeg_sem_libass_e_fail(repo):
    regras = [(exe("ffmpeg", "-vf"), (1, "No such filter: 'subtitles'"))] + REGRAS_SAUDAVEIS
    r = ffmpeg_libass.checar(amb_falso(repo, regras=regras))
    assert r.status == "FAIL" and "libass" in r.detalhe
    assert "ffmpeg" in r.conserto
    conserto_de_uma_linha(r)


def test_ffmpeg_com_biblioteca_quebrada_manda_reinstalar(repo):
    regras = [(exe("ffmpeg", "-vf"),
               (1, "dyld[123]: Library not loaded: /opt/homebrew/opt/x.dylib"))] + REGRAS_SAUDAVEIS
    r = ffmpeg_libass.checar(amb_falso(repo, regras=regras))
    assert r.status == "FAIL" and "brew reinstall ffmpeg" in r.conserto
    conserto_de_uma_linha(r)


def test_ffmpeg_com_erro_qualquer_e_fail_sem_traceback_e_com_saida_curta(repo):
    regras = [(exe("ffmpeg", "-vf"), (1, "boom\n" * 500))] + REGRAS_SAUDAVEIS
    r = ffmpeg_libass.checar(amb_falso(repo, regras=regras))
    assert r.status == "FAIL" and len(r.detalhe) < 600
    conserto_de_uma_linha(r)


# --- node_hyperframes ----------------------------------------------------------------------------

def node_com(versao):
    return [(exe("node", "--version"), (0, versao))] + REGRAS_SAUDAVEIS


def test_node_ausente_e_fail(repo):
    r = node_hyperframes.checar(amb_falso(repo, executaveis=("ffmpeg", "ffprobe")))
    assert r.status == "FAIL" and "Node" in r.detalhe
    conserto_de_uma_linha(r)


@pytest.mark.parametrize("versao", ["v20.11.0", "v21.9.0", "v18.19.1", "v0.12.0"])
def test_node_abaixo_de_22_e_fail(repo, versao):
    r = node_hyperframes.checar(amb_falso(repo, regras=node_com(versao)))
    assert r.status == "FAIL" and "22" in r.detalhe + r.conserto
    conserto_de_uma_linha(r)


@pytest.mark.parametrize("versao", ["v22.0.0", "v22.11.0", "v24.1.0"])
def test_node_22_ou_mais_passa(repo, versao):
    r = node_hyperframes.checar(amb_falso(repo, regras=node_com(versao)))
    assert r.status == "OK"


def test_node_com_saida_ilegivel_e_fail_sem_traceback(repo):
    r = node_hyperframes.checar(amb_falso(repo, regras=node_com("lixo")))
    assert r.status == "FAIL"
    conserto_de_uma_linha(r)


def test_binario_do_hyperframes_ausente_e_fail_com_setup(repo):
    (repo / "node_modules/.bin/hyperframes").unlink()
    r = node_hyperframes.checar(amb_falso(repo))
    assert r.status == "FAIL"
    assert "bash scripts/setup.sh" in r.conserto
    conserto_de_uma_linha(r)


def test_binario_sem_permissao_de_execucao_e_fail(repo):
    (repo / "node_modules/.bin/hyperframes").chmod(0o644)
    r = node_hyperframes.checar(amb_falso(repo))
    assert r.status == "FAIL" and "bash scripts/setup.sh" in r.conserto


def test_binario_que_nao_executa_e_fail(repo):
    regras = [(exe("hyperframes", "--version"), (1, "SyntaxError: bad"))] + REGRAS_SAUDAVEIS
    r = node_hyperframes.checar(amb_falso(repo, regras=regras))
    assert r.status == "FAIL" and "bash scripts/setup.sh" in r.conserto


def test_binario_instalado_e_na_versao_pinada_e_ok(repo):
    r = node_hyperframes.checar(amb_falso(repo))
    assert r.status == "OK" and "0.7.56" in r.detalhe


def test_versao_instalada_diferente_da_pinada_e_warn(repo):
    _escrever(repo / "node_modules/hyperframes/package.json", json.dumps({"version": "0.8.143"}))
    r = node_hyperframes.checar(amb_falso(repo))
    assert r.status == "WARN" and "0.8.143" in r.detalhe and "0.7.56" in r.detalhe
    assert "bash scripts/setup.sh" in r.conserto


# --- python_deps ---------------------------------------------------------------------------------

def py_com(saida):
    return [(python_c(), (0, saida))]


def test_python_com_tudo_e_ok(repo):
    r = python_deps.checar(amb_falso(repo, regras=py_com("3 9\n\n")))
    assert r.status == "OK"


def test_python_abaixo_de_3_9_e_fail(repo):
    r = python_deps.checar(amb_falso(repo, regras=py_com("3 8\n\n")))
    assert r.status == "FAIL" and "3.9" in r.detalhe + r.conserto
    conserto_de_uma_linha(r)


def test_modulo_faltando_e_fail_com_o_nome_do_pacote_e_o_setup(repo):
    r = python_deps.checar(amb_falso(repo, regras=py_com("3 11\ncv2,scipy\n")))
    assert r.status == "FAIL"
    assert "opencv-python-headless" in r.detalhe and "scipy" in r.detalhe
    assert "bash scripts/setup.sh" in r.conserto
    conserto_de_uma_linha(r)


def test_opencv_sem_cascadeclassifier_e_fail_com_o_conserto_do_pin(repo):
    """opencv 5.0.0 não tem CascadeClassifier: a medição do rosto falha (W7.X item 3)."""
    r = python_deps.checar(amb_falso(repo, regras=py_com("3 11\n\n5.0.0\n")))
    assert r.status == "FAIL"
    assert "CascadeClassifier" in r.detalhe and "5.0.0" in r.detalhe
    assert "opencv-python-headless" in r.conserto and "<5" in r.conserto
    conserto_de_uma_linha(r)


def test_opencv_com_cascade_continua_ok(repo):
    assert python_deps.checar(amb_falso(repo, regras=py_com("3 11\n\n\n"))).status == "OK"


def test_a_sonda_do_doctor_confere_o_cascade_de_verdade():
    cv2 = pytest.importorskip("cv2")
    r = subprocess.run([sys.executable, "-c", python_deps.SONDA], capture_output=True, text=True, timeout=60)
    linhas = r.stdout.splitlines()
    assert r.returncode == 0 and "CascadeClassifier" in python_deps.SONDA
    if hasattr(cv2, "CascadeClassifier"):
        assert len(linhas) < 3 or linhas[2].strip() == ""


def test_usa_o_python_do_venv_do_repo_quando_existe(repo):
    venv_py = _escrever(repo / ".venv/bin/python", "#!/bin/sh\n", 0o755)
    chamadas = []
    python_deps.checar(amb_falso(repo, regras=py_com("3 11\n\n"), chamadas=chamadas))
    assert chamadas and chamadas[0][0] == str(venv_py)


def test_sem_venv_usa_o_python_do_ambiente(repo):
    chamadas = []
    python_deps.checar(amb_falso(repo, regras=py_com("3 11\n\n"), chamadas=chamadas))
    assert chamadas[0][0] == "/falso/bin/python3"


def test_saida_ilegivel_do_python_e_fail_sem_traceback(repo):
    r = python_deps.checar(amb_falso(repo, regras=[(python_c(), (1, "ModuleNotFoundError: x"))]))
    assert r.status == "FAIL"
    conserto_de_uma_linha(r)


# --- transcritor (usa o audio.transcrever, não duplica) ---------------------------------------------

def test_transcritor_parakeet_no_apple_silicon_e_ok(repo):
    amb = amb_falso(repo, executaveis=("ffmpeg", "parakeet-mlx"), modulos=())
    r = transcritor.checar(amb)
    assert r.status == "OK" and "parakeet" in r.detalhe


def test_transcritor_parakeet_quebrado_sem_alternativa_e_fail(repo):
    regras = [(exe("parakeet-mlx", "--help"), (1, "bad interpreter"))]
    amb = amb_falso(repo, executaveis=("parakeet-mlx",), modulos=(), regras=regras)
    r = transcritor.checar(amb)
    assert r.status == "FAIL" and "parakeet" in r.detalhe
    conserto_de_uma_linha(r)


def test_transcritor_parakeet_quebrado_com_groq_de_reserva_e_warn(repo):
    regras = [(exe("parakeet-mlx", "--help"), (1, "bad interpreter"))]
    amb = amb_falso(repo, executaveis=("parakeet-mlx",), modulos=(), regras=regras,
                    env={"GROQ_API_KEY": "gsk_x"})
    r = transcritor.checar(amb)
    assert r.status == "WARN" and "groq" in r.detalhe


def test_nenhum_transcritor_e_fail_com_uma_mensagem_que_resolve(repo):
    r = transcritor.checar(amb_falso(repo, executaveis=(), modulos=()))
    assert r.status == "FAIL"
    assert "pip install parakeet-mlx" in r.conserto and "GROQ_API_KEY" in r.conserto
    conserto_de_uma_linha(r)


def test_nenhum_transcritor_fora_do_mac_sugere_faster_whisper(repo):
    r = transcritor.checar(amb_falso(repo, sistema="Linux", arquitetura="x86_64",
                                     executaveis=(), modulos=()))
    assert r.status == "FAIL" and "faster-whisper" in r.conserto


def test_so_groq_e_ok_e_diz_que_e_nuvem(repo):
    r = transcritor.checar(amb_falso(repo, executaveis=(), modulos=(),
                                     env={"GROQ_API_KEY": "gsk_x"}))
    assert r.status == "OK" and "groq" in r.detalhe


def test_faster_whisper_no_linux_e_ok(repo):
    r = transcritor.checar(amb_falso(repo, sistema="Linux", arquitetura="x86_64",
                                     executaveis=(), modulos=("faster_whisper",)))
    assert r.status == "OK" and "faster_whisper" in r.detalhe


def test_transcritor_delega_a_escolha_ao_audio_transcrever(repo, monkeypatch):
    from audio import transcrever as T
    monkeypatch.setattr(T, "backends_disponiveis", lambda amb=None: ["groq"])
    r = transcritor.checar(amb_falso(repo, executaveis=(), modulos=()))
    assert r.status == "OK" and "groq" in r.detalhe


# --- heygen --------------------------------------------------------------------------------------

def corpo(wallet=20.18, auto=True, plano=False):
    if plano:
        return json.dumps({"billing_type": "subscription"})
    d = {"billing_type": "wallet",
         "wallet": {"currency": "usd", "remaining_balance": wallet,
                    "auto_reload": {"enabled": auto, "amount_usd": 12.0, "threshold_usd": 10.0}}}
    return json.dumps(d)


def test_sem_chave_e_warn_e_diz_que_gravado_e_oneshot_seguem(repo):
    chamadas = []
    r = heygen.checar(amb_falso(repo, http=http_falso((200, "{}"), chamadas)))
    assert r.status == "WARN"
    assert "HEYGEN_API_KEY" in r.conserto
    assert "gravado" in r.detalhe and "one-shot" in r.detalhe
    assert chamadas == [], "sem chave não há chamada de rede"
    conserto_de_uma_linha(r)


def test_saldo_do_users_me_aparece_em_dolar(repo):
    chamadas = []
    amb = amb_falso(repo, env={"HEYGEN_API_KEY": CHAVE},
                    http=http_falso((200, corpo(20.18)), chamadas))
    r = heygen.checar(amb)
    assert r.status == "OK"
    assert "US$ 20,18" in r.detalhe
    assert chamadas[0]["url"].endswith("/v3/users/me")
    assert chamadas[0]["headers"].get("X-Api-Key") == CHAVE


def test_a_chave_nunca_aparece_no_resultado(repo):
    r = heygen.checar(amb_falso(repo, env={"HEYGEN_API_KEY": CHAVE},
                                http=http_falso((200, corpo(20.18)))))
    assert CHAVE not in r.detalhe + r.conserto + r.nome
    r = heygen.checar(amb_falso(repo, env={"HEYGEN_API_KEY": CHAVE},
                                http=http_falso((401, '{"error":"x"}'))))
    assert CHAVE not in r.detalhe + r.conserto


def test_resposta_embrulhada_em_data_tambem_le(repo):
    embrulho = json.dumps({"data": json.loads(corpo(7.5))})
    r = heygen.checar(amb_falso(repo, env={"HEYGEN_API_KEY": CHAVE},
                                http=http_falso((200, embrulho))))
    assert r.status == "OK" and "US$ 7,50" in r.detalhe


@pytest.mark.parametrize("status", [401, 403])
def test_chave_recusada_e_fail(repo, status):
    r = heygen.checar(amb_falso(repo, env={"HEYGEN_API_KEY": CHAVE},
                                http=http_falso((status, '{"error":"unauthorized"}'))))
    assert r.status == "FAIL" and "recusou" in r.detalhe
    conserto_de_uma_linha(r)


def test_saldo_baixo_sem_recarga_automatica_e_warn(repo):
    r = heygen.checar(amb_falso(repo, env={"HEYGEN_API_KEY": CHAVE},
                                http=http_falso((200, corpo(3.10, auto=False)))))
    assert r.status == "WARN" and "US$ 3,10" in r.detalhe
    conserto_de_uma_linha(r)


def test_saldo_baixo_com_recarga_automatica_e_ok(repo):
    r = heygen.checar(amb_falso(repo, env={"HEYGEN_API_KEY": CHAVE},
                                http=http_falso((200, corpo(3.10, auto=True)))))
    assert r.status == "OK" and "US$ 3,10" in r.detalhe and "recarga" in r.detalhe


def test_conta_por_plano_sem_wallet_e_ok_e_nao_inventa_dolar(repo):
    r = heygen.checar(amb_falso(repo, env={"HEYGEN_API_KEY": CHAVE},
                                http=http_falso((200, corpo(plano=True)))))
    assert r.status == "OK" and "US$" not in r.detalhe


def test_sem_rede_e_warn_nao_fail(repo):
    r = heygen.checar(amb_falso(repo, env={"HEYGEN_API_KEY": CHAVE},
                                http=http_falso(D.ErroRede("sem rede"))))
    assert r.status == "WARN"
    conserto_de_uma_linha(r)


@pytest.mark.parametrize("resposta", [(500, "erro"), (200, "isto não é json"), (200, "[]")])
def test_resposta_estranha_e_warn_sem_traceback(repo, resposta):
    r = heygen.checar(amb_falso(repo, env={"HEYGEN_API_KEY": CHAVE}, http=http_falso(resposta)))
    assert r.status == "WARN"
    conserto_de_uma_linha(r)


# --- fontes --------------------------------------------------------------------------------------

def test_fontes_que_os_templates_pedem_existem_e_ok(repo):
    r = fontes.checar(amb_falso(repo))
    assert r.status == "OK" and "3" in r.detalhe


def test_fonte_pedida_pelo_template_e_ausente_e_fail(repo):
    (repo / "fonts/inter-700.woff2").unlink()
    r = fontes.checar(amb_falso(repo))
    assert r.status == "FAIL" and "inter-700.woff2" in r.detalhe
    conserto_de_uma_linha(r)


def test_pasta_de_fontes_ausente_e_fail(repo):
    for f in (repo / "fonts").iterdir():
        f.unlink()
    (repo / "fonts").rmdir()
    r = fontes.checar(amb_falso(repo))
    assert r.status == "FAIL"
    conserto_de_uma_linha(r)


def test_vam_fonts_aponta_para_outra_pasta(repo, tmp_path):
    outra = tmp_path / "minhas-fontes"
    for nome in ("inter-400.woff2", "inter-700.woff2", "playfair-italic-500.woff2"):
        _escrever(outra / nome)
    for f in (repo / "fonts").iterdir():
        f.unlink()
    r = fontes.checar(amb_falso(repo, env={"VAM_FONTS": str(outra)}))
    assert r.status == "OK"


# --- rede ----------------------------------------------------------------------------------------

def test_com_gsap_local_o_render_nao_depende_de_rede_e_nao_chama_a_rede(repo):
    chamadas = []
    r = rede.checar(amb_falso(repo, http=http_falso(D.ErroRede("x"), chamadas)))
    assert r.status == "OK" and "local" in r.detalhe
    assert chamadas == []


def test_sem_gsap_local_com_cdn_alcancavel_e_warn_e_manda_o_setup(repo):
    (repo / "templates/_vendor/gsap.min.js").unlink()
    chamadas = []
    r = rede.checar(amb_falso(repo, http=http_falso((200, ""), chamadas)))
    assert r.status == "WARN" and "bash scripts/setup.sh" in r.conserto
    assert "gsap@3.14.2" in chamadas[0]["url"], "a versão vem do template, não é chutada"
    conserto_de_uma_linha(r)


def test_sem_gsap_local_e_sem_rede_e_fail(repo):
    (repo / "templates/_vendor/gsap.min.js").unlink()
    r = rede.checar(amb_falso(repo, http=http_falso(D.ErroRede("sem rede"))))
    assert r.status == "FAIL"
    conserto_de_uma_linha(r)


def test_gsap_local_vazio_conta_como_ausente(repo):
    (repo / "templates/_vendor/gsap.min.js").write_text("", encoding="utf-8")
    r = rede.checar(amb_falso(repo, http=http_falso((200, ""))))
    assert r.status == "WARN"


# --- o runner ------------------------------------------------------------------------------------

NOMES = ["python_deps", "ffmpeg_libass", "node_hyperframes", "transcritor", "fontes", "rede",
         "heygen"]


def amb_saudavel(repo):
    return amb_falso(repo, env={"HEYGEN_API_KEY": CHAVE}, executaveis=("ffmpeg", "ffprobe",
                                                                      "node", "parakeet-mlx"),
                     http=http_falso((200, corpo())))


def test_os_sete_checks_do_plano_existem_na_ordem(repo):
    assert [m.NOME for m in D.checks_padrao()] == NOMES


def test_ambiente_saudavel_passa_tudo(repo):
    resultados = D.rodar_checks(amb_saudavel(repo))
    assert [r.nome for r in resultados] == NOMES
    assert [r.status for r in resultados] == ["OK"] * 7, [(r.nome, r.status, r.detalhe)
                                                         for r in resultados]


def test_check_que_estoura_vira_fail_sem_traceback(repo):
    class Quebrado:
        NOME = "quebrado"

        @staticmethod
        def checar(amb):
            raise RuntimeError("explodiu")

    r = D.rodar_checks(amb_saudavel(repo), checks=[Quebrado])[0]
    assert r.status == "FAIL" and r.nome == "quebrado"
    assert "explodiu" in r.detalhe and "Traceback" not in r.detalhe + r.conserto
    conserto_de_uma_linha(r)


def test_codigo_de_saida_so_conta_fail():
    ok, aviso, falha = (D.Resultado("a", "OK"), D.Resultado("b", "WARN", "", "faça x"),
                        D.Resultado("c", "FAIL", "", "faça y"))
    assert D.codigo_de_saida([ok, aviso]) == 0
    assert D.codigo_de_saida([ok, aviso, falha]) == 1


def test_main_sai_0_com_ambiente_saudavel_e_imprime_um_painel(repo, capsys):
    rc = D.main([], amb=amb_saudavel(repo))
    saida = capsys.readouterr().out
    assert rc == 0
    assert saida.count("[OK]") == 7 and "[FAIL]" not in saida
    assert "Traceback" not in saida


def test_main_barra_quando_o_binario_do_hyperframes_falta(repo, capsys):
    (repo / "node_modules/.bin/hyperframes").unlink()
    rc = D.main([], amb=amb_saudavel(repo))
    saida = capsys.readouterr().out
    assert rc == 1
    assert "[FAIL] node_hyperframes" in saida
    assert "bash scripts/setup.sh" in saida


def test_main_warn_sozinho_nao_barra_e_mostra_o_conserto(repo, capsys):
    amb = amb_falso(repo, executaveis=("ffmpeg", "ffprobe", "node", "parakeet-mlx"),
                    http=http_falso((200, "{}")))      # sem HEYGEN_API_KEY
    rc = D.main([], amb=amb)
    saida = capsys.readouterr().out
    assert rc == 0
    assert "[WARN] heygen" in saida and "conserto:" in saida


def test_main_cada_linha_de_conserto_e_uma_linha(repo, capsys):
    (repo / "node_modules/.bin/hyperframes").unlink()
    D.main([], amb=amb_falso(repo, executaveis=(), modulos=(), http=http_falso((401, "x"))))
    linhas = capsys.readouterr().out.splitlines()
    for i, linha in enumerate(linhas):
        if linha.strip().startswith("conserto:"):
            assert linhas[i - 1].startswith("[")      # sempre logo depois do seu check


# --- .env ----------------------------------------------------------------------------------------

def test_dotenv_le_chave_valor_comentario_aspas_e_export(tmp_path):
    arq = _escrever(tmp_path / ".env", "\n".join([
        "# comentário", "", "HEYGEN_API_KEY=abc123", "GROQ_API_KEY='gsk_x'",
        'VAM_DADOS="/algum lugar"', "export OUTRA=1", "SEM_VALOR=", "linha solta sem igual"]))
    d = D.carregar_dotenv(arq)
    assert d == {"HEYGEN_API_KEY": "abc123", "GROQ_API_KEY": "gsk_x",
                 "VAM_DADOS": "/algum lugar", "OUTRA": "1", "SEM_VALOR": ""}


def test_dotenv_ausente_devolve_vazio(tmp_path):
    assert D.carregar_dotenv(tmp_path / "nao-existe") == {}


def test_ambiente_real_junta_o_dotenv_sem_sobrescrever_o_que_ja_esta_no_ambiente(tmp_path,
                                                                                monkeypatch):
    _escrever(tmp_path / ".env", "HEYGEN_API_KEY=do_arquivo\nGROQ_API_KEY=do_arquivo\n")
    monkeypatch.setenv("HEYGEN_API_KEY", "do_ambiente")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    amb = D.AmbienteDoctor.real(raiz=tmp_path)
    assert amb.env["HEYGEN_API_KEY"] == "do_ambiente"
    assert amb.env["GROQ_API_KEY"] == "do_arquivo"


def test_ambiente_real_monta_sem_estourar_e_o_executar_real_nao_levanta(tmp_path):
    amb = D.AmbienteDoctor.real(raiz=tmp_path)
    rc, saida = amb.executar(["comando-que-nao-existe-vam"], timeout=5)
    assert rc != 0 and isinstance(saida, str)


# --- compatibilidade com o Python 3.9 do macOS ------------------------------------------------------

ARQUIVOS = ["scripts/onboarding/doctor.py"] + [
    f"scripts/onboarding/checks/{n}.py" for n in
    ("ffmpeg_libass", "node_hyperframes", "python_deps", "transcritor", "heygen", "fontes", "rede")]


@pytest.mark.parametrize("arquivo", ARQUIVOS)
def test_arquivo_parseia_como_python_3_9(arquivo):
    ast.parse((RAIZ_REAL / arquivo).read_text(encoding="utf-8"), feature_version=(3, 9))


@pytest.mark.parametrize("arquivo", ARQUIVOS)
def test_sem_travessao_nos_arquivos(arquivo):
    texto = (RAIZ_REAL / arquivo).read_text(encoding="utf-8")
    assert "\u2014" not in texto and "\u2013" not in texto
