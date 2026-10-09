"""W3.C: gate_fidelidade_doc. Só liga quando o projeto nasceu de um Google Doc do PRÓPRIO aluno.

O que o doc manda nos comentários tem que chegar ao projeto: comentário com N links são N assets
naquele bloco (nunca 1), a âncora tem que cair em um bloco só (ou dizer qual com o número da
ocorrência), e o bloco tem que ser insert. O Doc vem do `entrada.doc_google` com HTTP simulado;
nenhum teste abre socket.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from entrada import doc_google
from gates import gate_fidelidade_doc as G
from projeto import modelo, pastas, status

RAIZ = Path(__file__).resolve().parents[2]
SLUG = "anuncio"
DOC_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
TOKEN = "ya29.TOKEN-DE-TESTE"


def drive(id_):
    return "https://drive.google.com/file/d/%s/view?usp=sharing" % id_


PAINEL = "1PAINELAAAAAAAAAAAAAA"
PIPOCA = ["1PIPOCAAAAAAAAAAAAAA1", "1PIPOCAAAAAAAAAAAAAA2", "1PIPOCAAAAAAAAAAAAAA3"]

PARAGRAFOS = [
    "[insert: painel | split] Você perde três horas por dia nisso aqui.",
    "[apresentador] E eu sei porque eu fazia igual todo santo dia.",
    "[insert: planilha] Com uma automação simples isso roda sozinho.",
    "[cta | KEY: SAIBA MAIS] Toque em saiba mais.",
]


class FakeHttp:
    def __init__(self, *rotas):
        self.rotas = list(rotas)

    def __call__(self, url, headers):
        for i, (trecho, status_http, corpo) in enumerate(self.rotas):
            if trecho in url:
                self.rotas.pop(i)
                return status_http, json.dumps(corpo).encode("utf-8")
        raise AssertionError("chamada HTTP inesperada: %s" % url)


def raw(i, ancora, content, replies=()):
    return {"id": "c%d" % i, "content": content, "createdTime": "2026-10-08T10:0%d:00.000Z" % i,
            "resolved": False, "deleted": False, "quotedFileContent": {"value": ancora},
            "author": {"displayName": "Ana"},
            "replies": [{"id": "c%dr%d" % (i, j), "content": r, "deleted": False,
                         "createdTime": "2026-10-08T11:0%d:00.000Z" % j, "author": {"displayName": "Beto"}}
                        for j, r in enumerate(replies)]}


def importar(paragrafos, comentarios):
    doc = {"title": "Roteiro", "tabs": [{"tabProperties": {"title": "Aba 1"}, "documentTab": {"body": {"content": [
        {"paragraph": {"elements": [{"textRun": {"content": t + "\n"}}]}} for t in paragrafos]}}}]}
    http = FakeHttp(("/documents/", 200, doc), ("/comments", 200, {"comments": comentarios}))
    cli = doc_google.Cliente(token=TOKEN, http=http, dormir=lambda s: None)
    return doc_google.importar(DOC_ID, cliente=cli)


COM_PAINEL = raw(1, "insert: painel", "Usa " + drive(PAINEL))
COM_PIPOCA = raw(2, "insert: planilha", "pipoca: " + " ".join(drive(x) for x in PIPOCA))


def montar(tmp_path, comentarios, paragrafos=PARAGRAFOS, arquivos=("painel.mp4", "planilha.mp4"),
           roteiro=None, excecoes=None, origem=True):
    estado = tmp_path / "_local"
    pj = pastas.projeto(SLUG, estado).criar()
    p = modelo.minimo(SLUG, "gravado", sem_trilha="sem trilha no teste",
                      origem={"tipo": "doc_google", "doc_id": DOC_ID} if origem else {"tipo": "chat"})
    if excecoes:
        p["excecoes"] = excecoes
    modelo.escrever(pj.projeto_json, p)
    pj.roteiro.write_text(roteiro if roteiro is not None else "\n".join(paragrafos) + "\n", encoding="utf-8")
    for a in arquivos:
        (pj.inserts_dir / a).write_bytes(b"x")
    return estado, pj, importar(paragrafos, comentarios)


def partes(pj, chave, itens):
    (pj.inserts_dir / (chave + ".partes.json")).write_text(json.dumps(itens), encoding="utf-8")


# --- o caso certo -------------------------------------------------------------------------------

def test_fiel_ao_doc_passa_com_pipoca_inteira(tmp_path):
    estado, pj, imp = montar(tmp_path, [COM_PAINEL, COM_PIPOCA])
    partes(pj, "planilha", PIPOCA)
    r = G.rodar(pj, imp)
    assert r.ok, r.motivo
    assert r.detalhes["estado"] == "PASS"
    assert r.detalhes["comentarios_com_asset"] == 2
    assert r.detalhes["assets_esperados"] == 4


# --- pipoca incompleta: comentário com N links virando menos de N assets --------------------------

def test_pipoca_com_3_links_e_1_asset_reprova(tmp_path):
    estado, pj, imp = montar(tmp_path, [COM_PAINEL, COM_PIPOCA])
    r = G.rodar(pj, imp)
    assert not r.ok
    assert "pipoca incompleta" in r.motivo
    assert "3 links" in r.motivo and "1 asset" in r.motivo


def test_pipoca_com_parte_faltando_nomeia_o_que_falta(tmp_path):
    estado, pj, imp = montar(tmp_path, [COM_PAINEL, COM_PIPOCA])
    partes(pj, "planilha", PIPOCA[:2])
    r = G.rodar(pj, imp)
    assert not r.ok
    assert PIPOCA[2] in r.motivo


def test_pipoca_cuja_parte_vem_no_nome_do_arquivo_composto_passa(tmp_path):
    estado, pj, imp = montar(tmp_path, [COM_PAINEL, COM_PIPOCA])
    partes(pj, "planilha", ["pipoca_" + "_".join(x.lower() for x in PIPOCA) + ".mp4"])
    assert G.rodar(pj, imp).ok


def test_comentario_com_17_links_virando_uma_imagem_parada_reprova(tmp_path):
    """O erro que custou 6 de 10 anúncios: 17 links no comentário, 1 imagem no vídeo."""
    links = " ".join(drive("1ASSET%014d" % i) for i in range(17))
    estado, pj, imp = montar(tmp_path, [COM_PAINEL, raw(2, "insert: planilha", "pipoca " + links)])
    r = G.rodar(pj, imp)
    assert not r.ok
    assert "17 links" in r.motivo and "1 asset" in r.motivo


def test_pipoca_com_um_link_so_reprova(tmp_path):
    estado, pj, imp = montar(tmp_path, [raw(1, "insert: painel", "pipoca " + drive(PAINEL))])
    r = G.rodar(pj, imp)
    assert not r.ok
    assert "pipoca" in r.motivo and "pelo menos 2" in r.motivo


def test_links_na_resposta_do_comentario_tambem_contam(tmp_path):
    com = raw(2, "insert: planilha", "pipoca " + drive(PIPOCA[0]), replies=[drive(PIPOCA[1])])
    estado, pj, imp = montar(tmp_path, [com])
    assert not G.rodar(pj, imp).ok          # 2 links, 1 arquivo
    partes(pj, "planilha", PIPOCA[:2])
    assert G.rodar(pj, imp).ok


# --- link único e outros comentários ---------------------------------------------------------------

def test_comentario_sem_link_e_so_nota_e_nao_reprova(tmp_path):
    estado, pj, imp = montar(tmp_path, [raw(1, "insert: painel", "Cuidado com o fundo desse trecho.")])
    r = G.rodar(pj, imp)
    assert r.ok, r.motivo
    assert r.detalhes["comentarios_com_asset"] == 0


def test_link_da_web_conta_como_asset_e_passa_com_um_arquivo(tmp_path):
    estado, pj, imp = montar(tmp_path, [raw(1, "insert: painel", "Referência https://exemplo.com/video")])
    assert G.rodar(pj, imp).ok


def test_insert_do_comentario_sem_arquivo_reprova(tmp_path):
    estado, pj, imp = montar(tmp_path, [COM_PAINEL], arquivos=("planilha.mp4",))
    r = G.rodar(pj, imp)
    assert not r.ok
    assert "painel" in r.motivo and "sem arquivo" in r.motivo


def test_comentario_com_link_em_bloco_que_nao_e_insert_reprova(tmp_path):
    estado, pj, imp = montar(tmp_path, [raw(1, "E eu sei porque eu fazia igual", "Mostra " + drive(PAINEL))])
    r = G.rodar(pj, imp)
    assert not r.ok
    assert "apresentador" in r.motivo and "não é insert" in r.motivo


def test_ancora_que_nao_esta_no_roteiro_reprova(tmp_path):
    estado, pj, imp = montar(tmp_path, [raw(1, "trecho que ninguém escreveu", "Usa " + drive(PAINEL))])
    r = G.rodar(pj, imp)
    assert not r.ok
    assert "c1" in r.motivo and "sem âncora" in r.motivo


# --- âncora ambígua sem nth ------------------------------------------------------------------------

AMB = [
    "[insert: painel] Primeiro a automação do dia.",
    "[insert: planilha] Depois a automação da noite.",
    "[cta | KEY: SAIBA MAIS] Toque em saiba mais.",
]


def test_ancora_que_cai_em_dois_blocos_sem_nth_reprova(tmp_path):
    estado, pj, imp = montar(tmp_path, [raw(1, "automação", "Usa " + drive(PAINEL))], paragrafos=AMB)
    r = G.rodar(pj, imp)
    assert not r.ok
    assert "ambígua" in r.motivo and "c1" in r.motivo
    assert r.detalhes["ancoras_ambiguas"] == ["c1"]


def test_nth_dado_por_parametro_escolhe_o_bloco(tmp_path):
    estado, pj, imp = montar(tmp_path, [raw(1, "automação", "Usa " + drive(PAINEL))], paragrafos=AMB)
    r = G.rodar(pj, imp, nths={"c1": 2})
    assert r.ok, r.motivo
    assert r.detalhes["blocos_com_asset"] == [1]


def test_nth_dentro_do_comentario_tambem_vale(tmp_path):
    estado, pj, imp = montar(tmp_path, [raw(1, "automação", "Usa " + drive(PAINEL))], paragrafos=AMB)
    imp["comentarios"][0]["nth"] = 1
    r = G.rodar(pj, imp)
    assert r.ok, r.motivo
    assert r.detalhes["blocos_com_asset"] == [0]


def test_nth_maior_que_as_ocorrencias_reprova(tmp_path):
    estado, pj, imp = montar(tmp_path, [raw(1, "automação", "Usa " + drive(PAINEL))], paragrafos=AMB)
    r = G.rodar(pj, imp, nths={"c1": 3})
    assert not r.ok
    assert "ocorrência 3" in r.motivo and "2 vez" in r.motivo


# --- exceção declarada com motivo -------------------------------------------------------------------

def test_excecao_declarada_no_projeto_libera_so_aquele_comentario(tmp_path):
    exc = [{"regra": "fidelidade_doc.c2", "motivo": "o aluno trocou a pipoca por um take gravado"}]
    estado, pj, imp = montar(tmp_path, [COM_PAINEL, COM_PIPOCA], excecoes=exc)
    r = G.rodar(pj, imp)
    assert r.ok, r.motivo
    assert r.detalhes["excecoes_usadas"] == {"c2": "o aluno trocou a pipoca por um take gravado"}
    estado2, pj2, imp2 = montar(tmp_path / "b", [COM_PAINEL, COM_PIPOCA])
    assert not G.rodar(pj2, imp2).ok


# --- estrutura: o roteiro.md do projeto segue o doc -------------------------------------------------

def test_roteiro_do_projeto_com_bloco_a_menos_reprova(tmp_path):
    roteiro = "\n".join(PARAGRAFOS[:1] + PARAGRAFOS[2:]) + "\n"
    estado, pj, imp = montar(tmp_path, [COM_PAINEL], roteiro=roteiro)
    r = G.rodar(pj, imp)
    assert not r.ok
    assert "3 blocos" in r.motivo and "4" in r.motivo


def test_bloco_insert_no_doc_que_virou_apresentador_no_projeto_reprova(tmp_path):
    roteiro = "\n".join([PARAGRAFOS[0], PARAGRAFOS[1], "[apresentador] Com uma automação simples isso roda sozinho.",
                         PARAGRAFOS[3]]) + "\n"
    estado, pj, imp = montar(tmp_path, [COM_PAINEL], roteiro=roteiro)
    r = G.rodar(pj, imp)
    assert not r.ok
    assert "bloco 2" in r.motivo and "insert: planilha" in r.motivo


def test_excecao_de_estrutura_aceita_o_desvio_com_motivo(tmp_path):
    roteiro = "\n".join([PARAGRAFOS[0], PARAGRAFOS[1], "[apresentador] Com uma automação simples isso roda sozinho.",
                         PARAGRAFOS[3]]) + "\n"
    exc = [{"regra": "fidelidade_doc.estrutura", "motivo": "gravei a tela em vez de usar o insert do doc"}]
    estado, pj, imp = montar(tmp_path, [COM_PAINEL], roteiro=roteiro, excecoes=exc)
    assert G.rodar(pj, imp).ok


# --- insumos -----------------------------------------------------------------------------------------

def test_doc_fora_da_convencao_e_insumo_invalido(tmp_path):
    estado, pj, imp = montar(tmp_path, [], paragrafos=["[desenhar bonito] Isso não é um tipo de bloco."])
    with pytest.raises(G.InsumoInvalido):
        G.rodar(pj, imp)


def test_sem_roteiro_do_projeto_e_insumo_invalido(tmp_path):
    estado, pj, imp = montar(tmp_path, [COM_PAINEL])
    pj.roteiro.unlink()
    with pytest.raises(G.InsumoInvalido):
        G.rodar(pj, imp)


def test_sidecar_de_partes_quebrado_e_insumo_invalido(tmp_path):
    estado, pj, imp = montar(tmp_path, [COM_PAINEL, COM_PIPOCA])
    (pj.inserts_dir / "planilha.partes.json").write_text("{isso não é uma lista", encoding="utf-8")
    with pytest.raises(G.InsumoInvalido):
        G.rodar(pj, imp)


# --- CLI ---------------------------------------------------------------------------------------------

def gravar_importado(tmp_path, imp):
    arq = tmp_path / "importado.json"
    arq.write_text(json.dumps(imp), encoding="utf-8")
    return arq


def test_cli_passa_exit_0_e_registra(tmp_path, capsys):
    estado, pj, imp = montar(tmp_path, [COM_PAINEL, COM_PIPOCA])
    partes(pj, "planilha", PIPOCA)
    arq = gravar_importado(tmp_path, imp)
    assert G.main([SLUG, "--estado", str(estado), "--importado", str(arq)]) == 0
    atual = status.ler(pj)["atual"]
    assert (atual["etapa"], atual["estado"]) == ("gate_fidelidade_doc", "ok")


def test_cli_reprova_exit_1_e_registra(tmp_path, capsys):
    estado, pj, imp = montar(tmp_path, [COM_PAINEL, COM_PIPOCA])
    arq = gravar_importado(tmp_path, imp)
    assert G.main([SLUG, "--estado", str(estado), "--importado", str(arq)]) == 1
    atual = status.ler(pj)["atual"]
    assert (atual["etapa"], atual["estado"]) == ("gate_fidelidade_doc", "falhou")
    assert "pipoca incompleta" in atual["motivo"]


def test_cli_busca_o_doc_pelo_id_do_projeto(tmp_path, capsys):
    estado, pj, imp = montar(tmp_path, [COM_PAINEL])
    pedidos = []

    def importar_falso(doc_id, aba=None):
        pedidos.append((doc_id, aba))
        return imp
    assert G.main([SLUG, "--estado", str(estado), "--aba", "Aba 1"], importar=importar_falso) == 0
    assert pedidos == [(DOC_ID, "Aba 1")]


def test_cli_sem_token_do_google_e_insumo_invalido_exit_2(tmp_path, capsys):
    estado, pj, imp = montar(tmp_path, [COM_PAINEL])

    def sem_token(doc_id, aba=None):
        raise doc_google.ErroGoogle("token vazio: exporte GOOGLE_OAUTH_ACCESS_TOKEN")
    assert G.main([SLUG, "--estado", str(estado)], importar=sem_token) == 2
    atual = status.ler(pj)["atual"]
    assert (atual["etapa"], atual["estado"]) == ("gate_fidelidade_doc", "bloqueado")
    assert "GOOGLE_OAUTH_ACCESS_TOKEN" in atual["motivo"]


def test_projeto_que_nao_veio_de_doc_e_pulado_e_nem_chama_o_google(tmp_path, capsys):
    estado, pj, imp = montar(tmp_path, [], origem=False)

    def nao_deve_chamar(doc_id, aba=None):
        raise AssertionError("o gate pulado não pode ir ao Google")
    assert G.main([SLUG, "--estado", str(estado)], importar=nao_deve_chamar) == 0
    atual = status.ler(pj)["atual"]
    assert atual["estado"] == "ok" and atual["detalhes"]["estado"] == "PULADO"
    assert "doc_google" in atual["motivo"]


def test_roda_como_script_e_sai_2_sem_projeto(tmp_path):
    estado = tmp_path / "_local"
    estado.mkdir()
    p = subprocess.run([sys.executable, str(RAIZ / "scripts" / "gates" / "gate_fidelidade_doc.py"),
                        "nao-existe", "--estado", str(estado)], capture_output=True, text=True)
    assert p.returncode == 2, p.stdout + p.stderr


def test_o_gate_nao_le_planilha_nem_arquivo_de_token_da_maquina():
    fonte = (RAIZ / "scripts" / "gates" / "gate_fidelidade_doc.py").read_text(encoding="utf-8").lower()
    for proibido in ("sheets", "spreadsheet", "google-tokens", ".claude"):
        assert proibido not in fonte
