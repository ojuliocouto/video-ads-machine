"""W3.B: plano/aprovacao. A aprovação do plano é amarrada por sha256 ao que foi aprovado.

  - grava o sha256 de roteiro.md, projeto.json, plano/plano.json e render/inserts.json, mais o texto do ok
    e o instante; só este módulo escreve plano/aprovacao.json (quem é medido não assina);
  - mudar 1 byte em qualquer um dos quatro vence a aprovação ("aprovação vencida");
  - não aprova plano que não passa nas 6 seções e na checklist, plano medido de outra versão do roteiro
    ou plano_edicao.md que não é o do plano.json.
"""
import ast
import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

from contratos.validar import validar
from entrada import para_motor
from plano import aprovacao, escrever_md, medir
from projeto import pastas, status
from tests.plano.test_medir import AGORA, SLUG, medir_exemplo, nomes_proibidos_em, sha, travessoes_em

RAIZ = Path(__file__).resolve().parents[2]
OK = "aprovado, pode montar. Se o gancho ficar escuro, me avisa."
ARQUIVOS = {"roteiro": "roteiro.md", "projeto": "projeto.json", "plano": "plano/plano.json",
            "inserts": "render/inserts.json"}


def preparar(tmp_path, **kw):
    """Projeto com plano medido, gravado e com o plano_edicao.md escrito (o que `vam plano` entrega)."""
    pj, plano, _ = medir_exemplo(tmp_path, **kw)
    medir.gravar(pj, plano)
    escrever_md.escrever(pj)
    return pj, plano


@pytest.fixture
def pronto(tmp_path):
    return preparar(tmp_path)


@pytest.fixture
def aprovado(pronto):
    pj, plano = pronto
    aprovacao.aprovar(pj, OK, agora=AGORA)
    return pj, plano


def arquivos_do_projeto(pj):
    return sorted(str(p.relative_to(pj.raiz)) for p in pj.raiz.rglob("*") if p.is_file())


# --- o que a aprovação grava -------------------------------------------------------------------------------

def test_grava_os_quatro_sha256_o_ok_e_o_instante(pronto):
    pj, _ = pronto
    ap = aprovacao.aprovar(pj, OK, agora=AGORA)
    lido = json.loads(pj.aprovacao.read_text(encoding="utf-8"))
    assert lido == ap
    assert lido["versao"] == 1 and lido["projeto"] == SLUG
    assert lido["ok"] == OK and lido["aprovado_em"] == AGORA
    assert lido["emissor"] == "plano.aprovacao"
    assert set(lido["arquivos"]) == set(ARQUIVOS)
    for nome, rel in ARQUIVOS.items():
        item = lido["arquivos"][nome]
        assert item["caminho"] == rel
        assert item["sha256"] == hashlib.sha256((pj.raiz / rel).read_bytes()).hexdigest(), nome
    assert validar("aprovacao", lido) == []


def test_o_ok_e_guardado_como_o_aluno_escreveu(pronto):
    pj, _ = pronto
    ap = aprovacao.aprovar(pj, "  ok  \n", agora=AGORA)
    assert ap["ok"] == "ok"                                              # só as pontas em branco saem


def test_instante_padrao_tem_fuso_e_passa_no_contrato(pronto):
    pj, _ = pronto
    ap = aprovacao.aprovar(pj, OK)
    assert validar("aprovacao", ap) == []
    assert re.search(r"(Z|[+-]\d\d:\d\d)$", ap["aprovado_em"])


def test_inserts_json_tem_os_mesmos_bytes_do_para_motor(pronto, tmp_path):
    """O arquivo aprovado é o que o motor consome: mesma função, mesmos bytes, mesmo sha256."""
    pj, _ = pronto
    ap = aprovacao.aprovar(pj, OK, agora=AGORA)
    motor = para_motor.gerar(pj.roteiro.read_text(encoding="utf-8"), pj.projeto_json, avatar=pj.avatar_mp4,
                             out_dir=pj.render_dir, inserts_dir=pj.inserts_dir)
    gravado = para_motor.gravar(motor, tmp_path / "in", tmp_path / "cfg")
    assert ap["arquivos"]["inserts"]["sha256"] == gravado["inserts"]["sha256"]
    assert (pj.render_dir / "inserts.json").read_bytes() == motor.inserts_json().encode("utf-8")


def test_so_cria_aprovacao_json_e_render_inserts_json(pronto):
    pj, _ = pronto
    antes = set(arquivos_do_projeto(pj))
    aprovacao.aprovar(pj, OK, agora=AGORA)
    assert set(arquivos_do_projeto(pj)) - antes == {"plano/aprovacao.json", "render/inserts.json"}


def test_aprovar_de_novo_substitui_a_aprovacao_anterior(pronto):
    pj, _ = pronto
    a = aprovacao.aprovar(pj, "primeiro ok", agora="2026-10-09T10:00:00-03:00")
    b = aprovacao.aprovar(pj, "segundo ok", agora="2026-10-09T11:00:00-03:00")
    assert json.loads(pj.aprovacao.read_text(encoding="utf-8")) == b != a


def test_aprovacao_para_gravado(tmp_path):
    from tests.plano.test_medir import ROTEIRO_GRAVADO, TRECHOS
    pj, plano = preparar(tmp_path, roteiro=ROTEIRO_GRAVADO, modo="gravado", chaves=(),
                         sugestoes={"trechos": TRECHOS})
    ap = aprovacao.aprovar(pj, OK, agora=AGORA)
    assert validar("aprovacao", ap) == []
    assert aprovacao.verificar(pj).vigente


# --- o que a aprovação recusa -------------------------------------------------------------------------------

@pytest.mark.parametrize("ok", ["", "   ", "x", None])
def test_ok_vazio_ou_curto_demais_e_recusado(pronto, ok):
    pj, _ = pronto
    with pytest.raises(aprovacao.AprovacaoRecusada) as e:
        aprovacao.aprovar(pj, ok)
    assert "ok" in str(e.value)
    assert not pj.aprovacao.exists()


def test_sem_plano_json_manda_gerar_o_plano(tmp_path):
    pj, _, _ = medir_exemplo(tmp_path)
    with pytest.raises(aprovacao.AprovacaoRecusada) as e:
        aprovacao.aprovar(pj, OK)
    assert "plano.json" in str(e.value) and "vam plano" in str(e.value)


@pytest.mark.parametrize("secao", ["mapa_inserts", "hook", "letterings", "densidade", "referencias", "efeitos"])
def test_plano_sem_uma_secao_nao_e_aprovado_e_a_mensagem_cita_a_secao(pronto, secao):
    pj, plano = pronto
    ruim = copy.deepcopy(plano)
    del ruim[secao]
    pj.plano_json.write_text(json.dumps(ruim), encoding="utf-8")
    with pytest.raises(aprovacao.AprovacaoRecusada) as e:
        aprovacao.aprovar(pj, OK)
    assert "'%s'" % secao in str(e.value)
    assert not pj.aprovacao.exists()


def test_checklist_com_pendente_sem_motivo_nao_e_aprovada(pronto):
    pj, plano = pronto
    ruim = copy.deepcopy(plano)
    ruim["checklist"]["atencao"] = {"status": "pendente"}
    pj.plano_json.write_text(json.dumps(ruim), encoding="utf-8")
    with pytest.raises(aprovacao.AprovacaoRecusada) as e:
        aprovacao.aprovar(pj, OK)
    assert "atencao" in str(e.value) and "motivo" in str(e.value)


def test_plano_medido_de_outra_versao_do_roteiro_nao_e_aprovado(pronto):
    pj, _ = pronto
    pj.roteiro.write_text(pj.roteiro.read_text(encoding="utf-8").replace("três horas", "duas horas"),
                          encoding="utf-8")
    with pytest.raises(aprovacao.AprovacaoRecusada) as e:
        aprovacao.aprovar(pj, OK)
    assert "roteiro.md" in str(e.value) and "vam plano" in str(e.value)


def test_plano_medido_de_outra_versao_do_projeto_nao_e_aprovado(pronto):
    pj, _ = pronto
    dados = json.loads(pj.projeto_json.read_text(encoding="utf-8"))
    dados["aceleracao"] = 1.5
    pj.projeto_json.write_text(json.dumps(dados), encoding="utf-8")
    with pytest.raises(aprovacao.AprovacaoRecusada) as e:
        aprovacao.aprovar(pj, OK)
    assert "projeto.json" in str(e.value)


def test_plano_de_outro_projeto_nao_e_aprovado(pronto):
    pj, plano = pronto
    ruim = dict(plano, projeto="outro-anuncio")
    pj.plano_json.write_text(json.dumps(ruim), encoding="utf-8")
    with pytest.raises(aprovacao.AprovacaoRecusada) as e:
        aprovacao.aprovar(pj, OK)
    assert "outro-anuncio" in str(e.value)


def test_o_aluno_precisa_ter_lido_o_md_deste_plano(pronto):
    pj, plano = pronto
    pj.plano_md.unlink()
    with pytest.raises(aprovacao.AprovacaoRecusada) as e:
        aprovacao.aprovar(pj, OK)
    assert "plano_edicao.md" in str(e.value)
    escrever_md.escrever(pj)
    novo = copy.deepcopy(plano)
    novo["hook"]["linha"] = "4 horas por dia"
    medir.gravar(pj, novo)                                   # o plano mudou e o md que ele leu ficou velho
    with pytest.raises(aprovacao.AprovacaoRecusada) as e:
        aprovacao.aprovar(pj, OK)
    assert "plano_edicao.md" in str(e.value) and "vam plano" in str(e.value)


def test_insert_sem_arquivo_nao_e_aprovado(pronto):
    pj, _ = pronto
    (pj.inserts_dir / "planilha.mp4").unlink()
    with pytest.raises(aprovacao.AprovacaoRecusada) as e:
        aprovacao.aprovar(pj, OK)
    assert "planilha" in str(e.value)
    assert not pj.aprovacao.exists() and not (pj.render_dir / "inserts.json").exists()


def test_roteiro_trocado_por_livre_depois_do_plano_nao_e_aprovado(tmp_path):
    pj, _ = preparar(tmp_path)
    pj.roteiro.write_text("Você perde três horas por dia nisso aqui.\n\nToque em saiba mais.\n",
                          encoding="utf-8")
    with pytest.raises(aprovacao.AprovacaoRecusada):
        aprovacao.aprovar(pj, OK)


def test_recusa_nao_deixa_rastro(pronto):
    pj, plano = pronto
    antes = arquivos_do_projeto(pj)
    ruim = copy.deepcopy(plano)
    del ruim["hook"]
    pj.plano_json.write_text(json.dumps(ruim), encoding="utf-8")
    with pytest.raises(aprovacao.AprovacaoRecusada):
        aprovacao.aprovar(pj, OK)
    assert arquivos_do_projeto(pj) == antes


# --- aprovação vencida --------------------------------------------------------------------------------------

def test_aprovacao_vigente_logo_depois_de_aprovar(aprovado):
    pj, _ = aprovado
    s = aprovacao.verificar(pj)
    assert s.vigente and s.motivo == "" and s.mudados == []


@pytest.mark.parametrize("nome", list(ARQUIVOS))
def test_mudar_um_byte_vence_a_aprovacao(aprovado, nome):
    pj, _ = aprovado
    alvo = pj.raiz / ARQUIVOS[nome]
    dados = bytearray(alvo.read_bytes())
    dados[0] = dados[0] ^ 1                                           # 1 bit de 1 byte
    alvo.write_bytes(bytes(dados))
    s = aprovacao.verificar(pj)
    assert not s.vigente
    assert "aprovação vencida" in s.motivo and ARQUIVOS[nome] in s.motivo
    assert s.mudados == [ARQUIVOS[nome]]


@pytest.mark.parametrize("nome", list(ARQUIVOS))
def test_acrescentar_uma_quebra_de_linha_tambem_vence(aprovado, nome):
    pj, _ = aprovado
    alvo = pj.raiz / ARQUIVOS[nome]
    alvo.write_bytes(alvo.read_bytes() + b"\n")
    assert "aprovação vencida" in aprovacao.verificar(pj).motivo


@pytest.mark.parametrize("nome", list(ARQUIVOS))
def test_arquivo_que_sumiu_vence_a_aprovacao(aprovado, nome):
    pj, _ = aprovado
    (pj.raiz / ARQUIVOS[nome]).unlink()
    s = aprovacao.verificar(pj)
    assert not s.vigente and "aprovação vencida" in s.motivo and "sumiu" in s.motivo


def test_varios_arquivos_mudados_aparecem_todos(aprovado):
    pj, _ = aprovado
    for nome in ("roteiro", "inserts"):
        alvo = pj.raiz / ARQUIVOS[nome]
        alvo.write_bytes(alvo.read_bytes() + b" ")
    s = aprovacao.verificar(pj)
    assert s.mudados == ["roteiro.md", "render/inserts.json"]


def test_sem_aprovacao_json(pronto):
    pj, _ = pronto
    s = aprovacao.verificar(pj)
    assert not s.vigente and "sem aprovação" in s.motivo and "vam aprovar" in s.motivo


def test_aprovacao_json_ilegivel(aprovado):
    pj, _ = aprovado
    pj.aprovacao.write_text("{ quebrado", encoding="utf-8")
    s = aprovacao.verificar(pj)
    assert not s.vigente and "aprovacao.json" in s.motivo


def test_emissor_forjado_nao_vale(aprovado):
    pj, _ = aprovado
    dados = json.loads(pj.aprovacao.read_text(encoding="utf-8"))
    dados["emissor"] = "montador"
    pj.aprovacao.write_text(json.dumps(dados), encoding="utf-8")
    s = aprovacao.verificar(pj)
    assert not s.vigente and "emissor" in s.motivo


def test_caminho_apontando_para_outro_arquivo_nao_vale(aprovado):
    """Os sha256 batem com os arquivos de hoje, mas a aprovação diz que aprovou OUTRO arquivo: incoerente, não vale."""
    pj, _ = aprovado
    dados = json.loads(pj.aprovacao.read_text(encoding="utf-8"))
    dados["arquivos"]["roteiro"]["caminho"] = "roteiro_antigo.md"
    pj.aprovacao.write_text(json.dumps(dados), encoding="utf-8")
    s = aprovacao.verificar(pj)
    assert not s.vigente and "roteiro.md" in s.motivo and "roteiro_antigo.md" in s.motivo


def test_aprovacao_de_outro_projeto_nao_vale(aprovado):
    pj, _ = aprovado
    dados = json.loads(pj.aprovacao.read_text(encoding="utf-8"))
    dados["projeto"] = "outro-anuncio"
    pj.aprovacao.write_text(json.dumps(dados), encoding="utf-8")
    s = aprovacao.verificar(pj)
    assert not s.vigente and "outro-anuncio" in s.motivo


def _reassinar(pj):
    """Simula quem edita o plano.json e refaz a aprovação à mão com os sha novos (o emissor não impede)."""
    dados = json.loads(pj.aprovacao.read_text(encoding="utf-8"))
    for nome, rel in ARQUIVOS.items():
        dados["arquivos"][nome]["sha256"] = hashlib.sha256((pj.raiz / rel).read_bytes()).hexdigest()
    pj.aprovacao.write_text(json.dumps(dados), encoding="utf-8")


def test_plano_editado_e_reassinado_a_mao_ainda_e_pego_pela_fonte(aprovado):
    pj, plano = aprovado
    forjado = copy.deepcopy(plano)
    forjado["fonte"]["roteiro_sha256"] = "0" * 64
    pj.plano_json.write_text(json.dumps(forjado), encoding="utf-8")
    _reassinar(pj)
    s = aprovacao.verificar(pj)
    assert not s.vigente and "outra versão" in s.motivo and "roteiro.md" in s.motivo


def test_plano_invalido_e_reassinado_a_mao_ainda_e_pego_pelas_secoes(aprovado):
    pj, plano = aprovado
    forjado = copy.deepcopy(plano)
    del forjado["efeitos"]
    pj.plano_json.write_text(json.dumps(forjado), encoding="utf-8")
    _reassinar(pj)
    s = aprovacao.verificar(pj)
    assert not s.vigente and "'efeitos'" in s.motivo


def test_plano_ilegivel_com_aprovacao_refeita_a_mao_nao_derruba_a_verificacao(aprovado):
    pj, _ = aprovado
    pj.plano_json.write_text("{ nao e json", encoding="utf-8")
    _reassinar(pj)
    s = aprovacao.verificar(pj)
    assert not s.vigente and "plano.json" in s.motivo and "ilegível" in s.motivo


def test_verificar_so_le(aprovado):
    pj, _ = aprovado
    antes = {p: p.read_bytes() for p in pj.raiz.rglob("*") if p.is_file()}
    aprovacao.verificar(pj)
    assert {p: p.read_bytes() for p in pj.raiz.rglob("*") if p.is_file()} == antes


# --- quem escreve aprovacao.json ----------------------------------------------------------------------------

ESCRITA = re.compile(r"write_text|write_bytes|escrever|\bopen\(|\.replace\(|rename|unlink|shutil|copy|mkstemp|dump\(")


def _escritores(base):
    achados = []
    for caminho in sorted(Path(base).rglob("*.py")):
        if caminho.name.startswith("test_"):
            continue
        fonte = caminho.read_text(encoding="utf-8")
        if "aprovacao" not in fonte:
            continue
        arvore = ast.parse(fonte)
        pais = {}
        for pai in ast.walk(arvore):
            for filho in ast.iter_child_nodes(pai):
                pais[filho] = pai
        for no in ast.walk(arvore):
            cita = (isinstance(no, ast.Constant) and isinstance(no.value, str) and "aprovacao.json" in no.value) \
                or (isinstance(no, ast.Attribute) and no.attr == "aprovacao")
            if not cita:
                continue
            instrucao = no
            while not isinstance(instrucao, ast.stmt):
                instrucao = pais[instrucao]
            if ESCRITA.search(ast.get_source_segment(fonte, instrucao) or ""):
                achados.append(caminho.relative_to(base).as_posix())
                break
    return achados


def test_so_plano_aprovacao_escreve_aprovacao_json():
    assert _escritores(RAIZ / "scripts") == ["plano/aprovacao.py"]


def test_o_varredor_enxerga_um_escritor_escondido(tmp_path):
    """Controle positivo: escrever o arquivo em outro módulo, de qualquer jeito, é acusado."""
    (tmp_path / "gates").mkdir()
    (tmp_path / "gates" / "falso1.py").write_text("def f(pj):\n    pj.aprovacao.write_text('{}')\n", encoding="utf-8")
    (tmp_path / "gates" / "falso2.py").write_text(
        "def f(raiz):\n    with open(raiz / 'plano' / 'aprovacao.json', 'w') as f:\n        f.write('{}')\n",
        encoding="utf-8")
    (tmp_path / "gates" / "leitor.py").write_text(
        "import json\ndef f(pj):\n    return json.loads(pj.aprovacao.read_text())\n", encoding="utf-8")
    assert _escritores(tmp_path) == ["gates/falso1.py", "gates/falso2.py"]


# --- CLI ------------------------------------------------------------------------------------------------------

def test_cli_aprova_e_registra_no_status(pronto, capsys):
    pj, _ = pronto
    rc = aprovacao.main([SLUG, "--estado", str(pj.estado), "--ok", OK])
    assert rc == 0
    assert aprovacao.verificar(pj).vigente
    atual = status.ler(pj)["atual"]
    assert atual["etapa"] == "aprovacao" and atual["estado"] == "ok"
    assert "aprovado" in capsys.readouterr().out.lower()


def test_cli_recusa_com_1_e_diz_o_motivo(pronto, capsys):
    pj, plano = pronto
    ruim = copy.deepcopy(plano)
    del ruim["hook"]
    pj.plano_json.write_text(json.dumps(ruim), encoding="utf-8")
    rc = aprovacao.main([SLUG, "--estado", str(pj.estado), "--ok", OK])
    assert rc == 1
    assert "'hook'" in capsys.readouterr().err
    assert status.ler(pj)["atual"]["estado"] == "falhou"
    assert not pj.aprovacao.exists()


def test_cli_slug_invalido_ou_projeto_inexistente_sai_com_2(tmp_path, capsys):
    assert aprovacao.main(["Slug Ruim", "--estado", str(tmp_path), "--ok", OK]) == 2
    assert aprovacao.main(["nao-existe", "--estado", str(tmp_path), "--ok", OK]) == 2
    assert "projeto" in capsys.readouterr().err


def test_modulo_nao_tem_nome_do_dono():
    fonte = (RAIZ / "scripts" / "plano" / "aprovacao.py").read_text(encoding="utf-8")
    assert nomes_proibidos_em(fonte) == []
    assert travessoes_em(fonte) == []
