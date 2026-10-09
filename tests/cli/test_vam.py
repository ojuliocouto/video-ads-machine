"""`vam` (W5.A): a CLI única do aluno, ponta a ponta.

    python3 scripts/vam.py <comando> [...]

Os subcomandos moram em `scripts/cli/<nome>.py`, cada um com `registrar(subparsers)` e `executar(args) -> int`,
e o `vam.py` os descobre sozinho. Saídas, as mesmas dos gates: 0 fez · 1 defeito medido (um gate reprovou,
roteiro fora da convenção) · 2 pedido ou insumo inválido. O estado do aluno (`_local`) vem de `--estado` (os
testes passam o deles; o padrão é o `caminhos.ESTADO`).

Aqui também moram as varreduras estáticas da unidade: o código não pode mais carregar o look, a leva nem o prefixo
de anúncio do dono, e quem é medido não assina (o montador nunca escreve `nota.json` nem `aprovacao.json`).
"""
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import vam
from projeto import pastas, status

RAIZ = Path(__file__).resolve().parent.parent.parent
SCRIPTS = RAIZ / "scripts"

ROTEIRO = (
    "[insert: demo-a | hook: MEU CLAUDE | virou um web designer | PROFISSIONAL] "
    "Minha skill de criação de páginas transformou meu Claude em um web designer profissional.\n"
    "[apresentador] Agora eu construo minhas páginas em minutos, sem precisar pagar nada mais por isso.\n"
    "[apresentador | LEAD: sabe qual é | KEY: O MELHOR] Sabe qual é o melhor?\n"
    "[insert: demo-b | split] Se eu usar um conector que é disponibilizado gratuitamente dentro do Claude,\n"
    "[cta | LEAD: eu consigo não só | KEY: PRODUZIR AS PÁGINAS | logo] eu consigo não só produzir as páginas\n"
)


def _vam(estado, *argv):
    """Roda o vam em processo, com o _local dos testes."""
    argv = list(argv)
    return vam.main(argv[:2] + ["--estado", str(estado)] + argv[2:] if len(argv) >= 2 else argv)


# --- descoberta e esqueleto ---------------------------------------------------------------------------

COMANDOS_DO_ALUNO = ("novo", "roteiro", "audio", "avatar", "plano", "aprovar", "montar", "auditar", "entregar",
                     "status", "doctor")


def test_vam_descobre_todos_os_subcomandos_de_cli():
    nomes = vam.comandos()
    for c in COMANDOS_DO_ALUNO + ("gravado", "oneshot", "insert"):
        assert c in nomes, c


def test_cada_modulo_de_cli_tem_registrar_e_executar_e_nao_faz_nada_no_import():
    for nome in COMANDOS_DO_ALUNO:
        mod = __import__("cli." + nome, fromlist=["registrar"])
        assert callable(mod.registrar) and callable(mod.executar), nome


def test_importar_o_vam_nao_executa_nada():
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, %r); import vam" % str(SCRIPTS)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


def test_ajuda_sai_com_zero_e_comando_desconhecido_sai_com_dois(capsys):
    assert vam.main(["--help"]) == 0
    assert "montar" in capsys.readouterr().out
    assert vam.main(["nao-existe"]) == 2


def test_sem_argumento_mostra_a_ajuda_e_sai_com_dois(capsys):
    assert vam.main([]) == 2
    assert "novo" in capsys.readouterr().out


def test_python_do_venv_so_reexecuta_quando_ha_venv_e_nao_e_ele_que_roda(tmp_path):
    raiz = tmp_path / "repo"
    assert vam.python_do_venv(raiz, "/usr/bin/python3") is None             # sem .venv: segue com quem roda
    py = raiz / ".venv" / "bin" / "python3"
    py.parent.mkdir(parents=True)
    py.write_text("")
    assert vam.python_do_venv(raiz, "/usr/bin/python3") == py
    assert vam.python_do_venv(raiz, str(py)) is None                        # já é ele: não reexecuta em laço


def test_rodar_o_vam_py_direto_mostra_a_ajuda(tmp_path):
    r = subprocess.run([sys.executable, str(SCRIPTS / "vam.py"), "--help"], capture_output=True, text=True,
                       timeout=120, env={"PATH": "/usr/bin:/bin", "VAM_SEM_VENV": "1", "HOME": str(tmp_path)})
    assert r.returncode == 0, r.stderr
    assert "vam" in r.stdout and "Traceback" not in r.stderr


# --- novo, roteiro, status ----------------------------------------------------------------------------

def test_novo_cria_o_projeto_e_e_idempotente(estado_vazio, capsys):
    assert _vam(estado_vazio, "novo", "meu-ad", "--look", "estudio", "--sem-trilha", "teste sem música") == 0
    pj = pastas.projeto("meu-ad", estado_vazio)
    dados = json.loads(pj.projeto_json.read_text(encoding="utf-8"))
    assert dados["modo"] == "avatar" and dados["look"] == "estudio" and dados["aceleracao"] == 1.35
    assert "vam roteiro meu-ad" in capsys.readouterr().out          # o próximo passo vem escrito
    assert _vam(estado_vazio, "novo", "meu-ad", "--look", "estudio", "--sem-trilha", "teste sem música") == 0


def test_novo_com_pedido_divergente_sai_com_dois_e_nao_toca_no_projeto(estado_vazio):
    assert _vam(estado_vazio, "novo", "meu-ad", "--look", "estudio", "--sem-trilha", "teste sem música") == 0
    pj = pastas.projeto("meu-ad", estado_vazio)
    antes = pj.projeto_json.read_bytes()
    assert _vam(estado_vazio, "novo", "meu-ad", "--look", "outro", "--sem-trilha", "teste sem música") == 2
    assert pj.projeto_json.read_bytes() == antes


def test_novo_modo_avatar_sem_look_sai_com_dois(estado_vazio, capsys):
    assert _vam(estado_vazio, "novo", "meu-ad", "--sem-trilha", "teste sem música") == 2
    assert "look" in capsys.readouterr().err


def test_novo_sem_trilha_nem_motivo_sai_com_dois(estado_vazio):
    assert _vam(estado_vazio, "novo", "meu-ad", "--look", "estudio") == 2


def test_roteiro_grava_normalizado_e_valida(estado_vazio, tmp_path, capsys):
    _vam(estado_vazio, "novo", "meu-ad", "--look", "estudio", "--sem-trilha", "teste sem música")
    arq = tmp_path / "colado.txt"
    arq.write_text(ROTEIRO.replace("Sabe qual", "Sabe  qual"), encoding="utf-8")
    assert _vam(estado_vazio, "roteiro", "meu-ad", "--de", str(arq)) == 0
    pj = pastas.projeto("meu-ad", estado_vazio)
    assert "Sabe qual" in pj.roteiro.read_text(encoding="utf-8")       # espaço duplo normalizado
    out = capsys.readouterr().out
    assert "5 blocos" in out and "2 insert" in out


def test_roteiro_fora_da_convencao_sai_com_um_e_nao_grava(estado_vazio, tmp_path, capsys):
    _vam(estado_vazio, "novo", "meu-ad", "--look", "estudio", "--sem-trilha", "teste sem música")
    arq = tmp_path / "ruim.md"
    arq.write_text("[insert: ] fala\n[cta | logo] fim\n", encoding="utf-8")
    assert _vam(estado_vazio, "roteiro", "meu-ad", "--de", str(arq)) == 1
    assert not pastas.projeto("meu-ad", estado_vazio).roteiro.exists()
    assert "linha" in capsys.readouterr().err


def test_roteiro_sem_entrada_confere_o_que_ja_esta_la(estado_vazio, tmp_path):
    _vam(estado_vazio, "novo", "meu-ad", "--look", "estudio", "--sem-trilha", "teste sem música")
    assert _vam(estado_vazio, "roteiro", "meu-ad") == 2                     # ainda não há roteiro
    arq = tmp_path / "r.md"
    arq.write_text(ROTEIRO, encoding="utf-8")
    assert _vam(estado_vazio, "roteiro", "meu-ad", "--de", str(arq)) == 0
    assert _vam(estado_vazio, "roteiro", "meu-ad") == 0


def test_roteiro_existente_diferente_so_troca_com_sobrescrever(estado_vazio, tmp_path):
    _vam(estado_vazio, "novo", "meu-ad", "--look", "estudio", "--sem-trilha", "teste sem música")
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    a.write_text(ROTEIRO, encoding="utf-8")
    b.write_text(ROTEIRO.replace("O MELHOR", "O MAIS LEGAL"), encoding="utf-8")
    assert _vam(estado_vazio, "roteiro", "meu-ad", "--de", str(a)) == 0
    assert _vam(estado_vazio, "roteiro", "meu-ad", "--de", str(b)) == 2
    assert _vam(estado_vazio, "roteiro", "meu-ad", "--de", str(b), "--sobrescrever") == 0
    assert "O MAIS LEGAL" in pastas.projeto("meu-ad", estado_vazio).roteiro.read_text(encoding="utf-8")


def test_status_mostra_a_etapa_atual_e_o_proximo_passo(estado_vazio, capsys):
    _vam(estado_vazio, "novo", "meu-ad", "--look", "estudio", "--sem-trilha", "teste sem música")
    pj = pastas.projeto("meu-ad", estado_vazio)
    status.registrar(pj, "gate_look", "falhou", motivo="o look 'estudio' não está aprovado")
    capsys.readouterr()
    assert _vam(estado_vazio, "status", "meu-ad") == 0
    out = capsys.readouterr().out
    assert "gate_look" in out and "falhou" in out and "não está aprovado" in out


def test_status_sem_slug_lista_os_projetos(estado_vazio, capsys):
    _vam(estado_vazio, "novo", "um", "--look", "estudio", "--sem-trilha", "teste sem música")
    _vam(estado_vazio, "novo", "dois", "--look", "estudio", "--sem-trilha", "teste sem música")
    capsys.readouterr()
    assert vam.main(["status", "--estado", str(estado_vazio)]) == 0
    out = capsys.readouterr().out
    assert "um" in out and "dois" in out


def test_slug_invalido_sai_com_dois_sem_traceback(estado_vazio, capsys):
    for cmd in ("roteiro", "plano", "aprovar", "montar", "entregar", "status"):
        extra = ["--ok", "pode"] if cmd == "aprovar" else []
        assert _vam(estado_vazio, cmd, "Ruim/../x", *extra) == 2, cmd
    assert "Traceback" not in capsys.readouterr().err


def test_projeto_que_nao_existe_sai_com_dois(estado_vazio, capsys):
    for cmd in ("roteiro", "audio", "avatar", "plano", "montar", "auditar", "entregar"):
        assert _vam(estado_vazio, cmd, "nao-existe") == 2, cmd
    assert "vam novo" in capsys.readouterr().err


def test_aprovar_sem_plano_sai_com_um_e_grava_o_motivo_no_status(estado_vazio, tmp_path):
    _vam(estado_vazio, "novo", "meu-ad", "--look", "estudio", "--sem-trilha", "teste sem música")
    arq = tmp_path / "r.md"
    arq.write_text(ROTEIRO, encoding="utf-8")
    _vam(estado_vazio, "roteiro", "meu-ad", "--de", str(arq))
    assert _vam(estado_vazio, "aprovar", "meu-ad", "--ok", "aprovado, pode montar") == 1
    pj = pastas.projeto("meu-ad", estado_vazio)
    atual = status.ler(pj)["atual"]
    assert atual["etapa"] == "aprovacao" and atual["estado"] == "falhou" and "plano" in atual["motivo"]
    assert not pj.aprovacao.exists()


def test_build_composite_chamado_direto_sai_com_dois():
    r = subprocess.run([sys.executable, str(SCRIPTS / "build_composite.py"), "ad99v2", "espuma_roxa", "9x16"],
                       capture_output=True, text=True, timeout=120, cwd=str(SCRIPTS))
    assert r.returncode == 2
    assert "vam montar" in r.stderr and "Traceback" not in r.stderr


def test_produzir_ad_sem_slug_sai_com_dois():
    r = subprocess.run([sys.executable, str(SCRIPTS / "produzir_ad.py")], capture_output=True, text=True,
                       timeout=120, cwd=str(SCRIPTS))
    assert r.returncode == 2 and "Traceback" not in r.stderr


# --- o build por projeto (build_composite.Motor) -------------------------------------------------------

def _projeto_com_roteiro(estado, tmp_path, slug="build"):
    _vam(estado, "novo", slug, "--look", "estudio", "--sem-trilha", "teste do build")
    arq = tmp_path / "r.md"
    arq.write_text(ROTEIRO, encoding="utf-8")
    assert _vam(estado, "roteiro", slug, "--de", str(arq)) == 0
    pj = pastas.projeto(slug, estado)
    for chave in ("demo-a", "demo-b"):
        (pj.inserts_dir / (chave + ".mp4")).write_bytes(b"x")
    return pj


def test_motor_mora_inteiro_dentro_do_projeto(estado_vazio, tmp_path):
    import build_composite as BC
    pj = _projeto_com_roteiro(estado_vazio, tmp_path)
    m = BC.Motor(pj)
    for caminho in (m.dados, m.leva, m.inserts, m.config, m.overlay_dir, m.overlay_render_dir, m.footage, m.timing,
                    m.composite, m.final):
        assert pj.dentro(caminho), caminho
    assert m.final == pj.final_9x16 and m.accel == 1.35


def test_os_dois_motores_recebem_a_mesma_timeline(estado_vazio, tmp_path):
    import build_composite as BC
    pj = _projeto_com_roteiro(estado_vazio, tmp_path)
    m = BC.Motor(pj)
    m.escrever_arquivos_do_motor()
    cfg = json.loads(m.config.read_text(encoding="utf-8"))
    env = m.env_footage()
    assert cfg["timeline"] == str(pj.timeline) == env["VAM_TIMELINE"]
    assert cfg["speed"] == 1.0 and cfg["out_dir"] == str(m.overlay_dir)
    assert env["VAM_AVATAR"] == str(pj.avatar_mp4) and env["VAM_ROTEIRO"] == str(m.leva)
    assert env["VAM_DADOS"] == str(m.dados) and env["CAP"] == "0" and env["VAM_BAKE_LETTERING"] == "0"
    assert m.inserts.read_bytes() == (pj.render_dir / "inserts.json").read_bytes() or not (
        pj.render_dir / "inserts.json").exists()


def test_o_logo_do_anuncio_e_o_da_marca_do_aluno(estado_vazio, tmp_path):
    import build_composite as BC
    pj = _projeto_com_roteiro(estado_vazio, tmp_path)
    assert BC.Motor(pj).env_motor()["VAM_ASSETS"] == str(pastas.logo(estado_vazio).parent)


def test_o_look_fechado_do_looks_json_chega_ao_overlay(estado_vazio, tmp_path):
    import build_composite as BC
    from projeto import looks
    pj = _projeto_com_roteiro(estado_vazio, tmp_path)
    looks.adicionar("estudio", "look_estudio_01", "fechado", estado=estado_vazio)
    m = BC.Motor(pj)
    m.escrever_arquivos_do_motor()
    assert json.loads(m.config.read_text(encoding="utf-8"))["look_plano"] == "fechado"


def test_a_impressao_do_template_ve_os_parciais():
    import build_composite as BC
    from overlay import html_injecao
    tmpl = RAIZ / "templates" / "reel-editorial" / "index.html"
    assert BC.assinatura_template("9x16") == html_injecao.assinatura_template(tmpl)


def test_o_build_normaliza_pela_regua_da_entrega_do_gravado():
    texto = (SCRIPTS / "build_composite.py").read_text(encoding="utf-8")
    assert "normalizar_para_entrega(" in texto
    assert "def normalizar_loudness" not in texto


def test_o_build_recusa_rodar_sem_aprovacao_vigente(estado_vazio, tmp_path):
    import build_composite as BC
    pj = _projeto_com_roteiro(estado_vazio, tmp_path)
    with pytest.raises(BC.ErroDoMotor) as e:
        BC.Motor(pj).preparar()
    assert "aprova" in str(e.value)


# --- prancha, init_local e material_local por projeto ---------------------------------------------------

def test_prancha_nao_procura_mais_o_gen_ad_v2_no_local():
    texto = (SCRIPTS / "prancha_direcao.py").read_text(encoding="utf-8")
    assert 'V2L / "gen_ad_v2.py"' not in texto and "V2L" not in texto


def test_prancha_escreve_na_pasta_do_plano_do_projeto(estado_vazio, tmp_path):
    import prancha_direcao as PD
    pj = _projeto_com_roteiro(estado_vazio, tmp_path)
    assert PD.pasta_de_saida(pj) == pj.prancha_dir
    assert PD.main(["nao-existe", "--estado", str(estado_vazio)]) == 2


def test_init_local_cria_o_local_do_produto(tmp_path):
    import init_local
    estado = tmp_path / "_local"
    criados, _ = init_local.criar(estado)
    for sub in ("projetos", "trilhas", "marca"):
        assert (estado / sub).is_dir(), sub
    assert json.loads((estado / "looks.json").read_text(encoding="utf-8")) == {"versao": 1, "looks": {}}
    assert (estado / "README.md").is_file()
    assert not (estado / "configs").exists() and not (estado / "dados" / "inputs").exists()
    criados2, existentes = init_local.criar(estado)
    assert criados2 == [] and existentes


def test_material_local_aponta_o_comando_vam_que_resolve(estado_vazio, capsys):
    import material_local
    _vam(estado_vazio, "novo", "mat", "--look", "estudio", "--sem-trilha", "teste do material")
    pj = pastas.projeto("mat", estado_vazio)
    assert material_local.checar_material(pj) is False
    err = capsys.readouterr().err
    assert "vam roteiro mat" in err and err.count("\n") <= 3


# --- varreduras estáticas -------------------------------------------------------------------------------

# Arquivos que a seção 2.5 do plano tira do repo na W6.D (código de cliente e caminhos mortos). Eles não são
# chamados por nenhum comando do produto; a varredura de nomes da W6 cobre o resto.
SAEM_NA_W6 = {"ads_v2_configs.py", "parse_sheet.py", "drive_push.py", "verificar_fidelidade.py", "travas.py",
              "previa_bloco.py", "vam_build.py", "produzir_roteiro_h.py", "submagic_run.py", "gerar_capcut_draft.py",
              "check_assets.py", "check_overlap.py", "conferir_recortes.py", "acelerar.py", "audit_ad.py",
              "add_pip.py", "sample_lettering.py", "chrome_lettering.py", "tay_captions.py", "caption_styles.py",
              "heygen_avatar.py", "criar_look_avatar.py", "mixar_sfx.py"}
PROIBIDOS = (re.compile(r"LOOK_POR_AD"), re.compile(r"LOOKS_OK_9X16"), re.compile(r"audios_leva"),
             re.compile(r"""startswith\(\s*["']jh["']"""), re.compile(r"""replace\(\s*["']jh["']"""),
             re.compile(r"""["']jh["']\s+if\b"""), re.compile(r"""\bif\b[^\n]*\.startswith\(["']jh"""))


def _codigo_do_produto():
    for p in sorted(SCRIPTS.rglob("*.py")):
        if p.name in SAEM_NA_W6 or p.name.startswith("test_") or "__pycache__" in p.parts:
            continue
        yield p


def test_zero_look_cravado_leva_cravada_e_prefixo_de_anuncio_no_codigo():
    achados = []
    for p in _codigo_do_produto():
        texto = p.read_text(encoding="utf-8")
        for rx in PROIBIDOS:
            for m in rx.finditer(texto):
                linha = texto[:m.start()].count("\n") + 1
                achados.append("%s:%d %s" % (p.relative_to(RAIZ), linha, m.group(0)))
    assert achados == []


def test_o_build_nao_le_mais_o_dicionario_de_looks_do_dono():
    for nome in ("build_composite.py", "produzir_ad.py", "prancha_direcao.py", "material_local.py"):
        texto = (SCRIPTS / nome).read_text(encoding="utf-8")
        assert "ads_v2_configs" not in texto, nome
        assert "LK[" not in texto, nome


MONTADOR = ("produzir_ad.py", "build_composite.py", "prancha_direcao.py", "entrega/pacote.py", "entrega/laudo.py",
            "entrega/whatsapp_versao.py", "cli/montar.py", "cli/entregar.py", "gates/gate_entrega.py")
# função ou método de escrita -> de onde sai o ALVO da escrita
#   ("self", None): o objeto do método (p.write_text(...));  ("arg", n): o n-ésimo argumento
ALVO_DA_ESCRITA = {"write_text": ("self", None), "write_bytes": ("self", None), "symlink_to": ("self", None),
                   "replace": ("arg", 0), "rename": ("arg", 0), "escrever_json_atomico": ("arg", 0),
                   "escrever_atomico": ("arg", 0), "open": ("arg", 0), "copy": ("arg", 1), "copy2": ("arg", 1),
                   "copyfile": ("arg", 1), "move": ("arg", 1), "dump": ("arg", 1)}


def _alvos_de_escrita(arquivo):
    """(função, texto do alvo) de cada chamada de escrita do arquivo (análise estática)."""
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        f = no.func
        nome = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)
        if nome not in ALVO_DA_ESCRITA:
            continue
        de, i = ALVO_DA_ESCRITA[nome]
        if nome == "open" and not any(isinstance(a, ast.Constant) and isinstance(a.value, str)
                                      and set(a.value) & set("wax") for a in no.args[1:2]):
            continue
        if de == "self":
            alvo = f.value if isinstance(f, ast.Attribute) else None
        else:
            alvo = no.args[i] if len(no.args) > i else None
        if alvo is not None:
            yield nome, ast.unparse(alvo)


NOTA = re.compile(r"\bnota\b|nota\.json|nota_json")
APROVACAO = re.compile(r"\baprovacao\b|aprovacao\.json")


def test_o_montador_nunca_escreve_nota_json_nem_aprovacao_json():
    """Quem é medido não assina: a nota é do `vam auditar` e a aprovação é do `plano.aprovacao`."""
    achados = []
    for rel in MONTADOR:
        for nome, alvo in _alvos_de_escrita(SCRIPTS / rel):
            if NOTA.search(alvo) or APROVACAO.search(alvo):
                achados.append("%s: %s(%s)" % (rel, nome, alvo))
    assert achados == []


def test_so_o_vam_auditar_escreve_a_nota_e_so_o_plano_aprovacao_escreve_a_aprovacao():
    escrevem_nota, escrevem_aprovacao = set(), set()
    for p in SCRIPTS.rglob("*.py"):
        if "__pycache__" in p.parts or p.name.startswith("test_"):
            continue
        for _nome, alvo in _alvos_de_escrita(p):
            if NOTA.search(alvo):
                escrevem_nota.add(p.relative_to(SCRIPTS).as_posix())
            if APROVACAO.search(alvo):
                escrevem_aprovacao.add(p.relative_to(SCRIPTS).as_posix())
    assert escrevem_nota == {"cli/auditar.py"}
    assert escrevem_aprovacao == {"plano/aprovacao.py"}
