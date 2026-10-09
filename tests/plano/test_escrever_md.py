"""W3.B: plano/escrever_md. O plano_edicao.md é o que o aluno LÊ antes de dar o ok: ele nasce do plano.json
(nunca o contrário), traz as 6 seções, os números medidos, a checklist com as pendências e o sha256 do
plano.json que ele mostra. Se o md não é o do plano.json atual, a aprovação recusa.
"""
import copy
import re

import pytest

from plano import checklist, escrever_md, medir
from tests.plano.test_medir import SLUG, medir_exemplo, sha


@pytest.fixture
def pronto(tmp_path):
    pj, plano, _ = medir_exemplo(tmp_path, sugestoes={"propostos": [5]})
    medir.gravar(pj, plano)
    return pj, plano


def texto(pj):
    return escrever_md.escrever(pj).read_text(encoding="utf-8")


def test_escrever_grava_em_plano_edicao_md(pronto):
    pj, _ = pronto
    destino = escrever_md.escrever(pj)
    assert destino == pj.plano_md and destino.is_file()
    assert not [p for p in pj.plano_dir.iterdir() if p.name.endswith(".tmp")]


def test_as_seis_secoes_aparecem_na_ordem_com_o_rotulo_do_contrato(pronto):
    pj, _ = pronto
    md = texto(pj)
    posicoes = [md.index("## %d. %s" % (n, rotulo)) for n, (_, rotulo, _) in enumerate(checklist.SECOES, 1)]
    assert posicoes == sorted(posicoes)


def test_um_plano_gerado_passa_na_conferencia_por_palavra_chave(pronto):
    pj, _ = pronto
    md = texto(pj)
    assert escrever_md.secoes_ausentes(md) == []
    assert len(md) >= escrever_md.TAMANHO_MIN


REPRESENTANTE = {"mapa_inserts": "insert", "hook": "hook", "letterings": "lettering", "densidade": "densidade",
                 "referencias": "referencias", "efeitos": "efeitos"}


@pytest.mark.parametrize("chave", [s[0] for s in checklist.SECOES])
def test_secoes_ausentes_nomeia_a_secao_que_falta(chave):
    resto = " ".join(v for k, v in REPRESENTANTE.items() if k != chave)
    assert escrever_md.secoes_ausentes(resto) == [chave]


def test_palavra_chave_so_vale_como_palavra_inteira_ou_prefixo_marcado():
    """"som" dentro de "resumo" ou "somente" não é a seção de efeitos."""
    md = "insert hook lettering densidade referencias resumo somente assombro"
    assert escrever_md.secoes_ausentes(md) == ["efeitos"]
    assert escrever_md.secoes_ausentes(md + " som") == []
    assert escrever_md.secoes_ausentes(md + " efeitos sonoros") == []


def test_secoes_ausentes_ignora_acento_e_caixa():
    md = "REFERÊNCIAS\nMAPA DE INSERTS\nHOOK\nLETTERING\nDENSIDADE\nEFEITOS e SOM"
    assert escrever_md.secoes_ausentes(md) == []
    assert escrever_md.secoes_ausentes("só texto solto") == [s[0] for s in checklist.SECOES]


def test_mostra_os_numeros_medidos_em_portugues(pronto):
    pj, plano = pronto
    md = texto(pj)
    d = plano["densidade"]
    assert ("%.1f%%" % (d["fracao_insert"] * 100)).replace(".", ",") in md
    assert ("%.1f" % plano["ritmo"]["cortes_min"]).replace(".", ",") in md
    assert ("%.1f" % plano["duracao_s"]).replace(".", ",") in md
    for chave in ("painel", "planilha", "automacao"):
        assert chave in md
    assert "1280x644" in md
    assert "VOCÊ PERDE" in md and "NISSO AQUI" in md


def test_traz_o_bloco_a_bloco_com_a_fala(pronto):
    pj, plano = pronto
    md = texto(pj)
    for b in plano["blocos"]:
        assert b["fala"] in md


def test_bloco_proposto_pelo_plano_vem_marcado(pronto):
    pj, _ = pronto
    md = texto(pj)
    assert "proposto" in md.lower()
    linha = [l for l in md.splitlines() if "Com uma automação simples" in l][0]
    assert "proposto" in linha.lower()


def test_checklist_lista_cada_item_com_status(pronto):
    pj, plano = pronto
    md = texto(pj)
    for item in checklist.ITENS:
        assert checklist.ROTULOS[item] in md
    assert md.count("atendido") >= 4


def test_pendencia_aparece_com_o_motivo(tmp_path):
    pj, plano, _ = medir_exemplo(tmp_path, medidas={"painel": (1280, 644, 1.0)})
    medir.gravar(pj, plano)
    md = texto(pj)
    motivo = plano["checklist"]["edicao_por_insert"]["motivo"]
    assert plano["checklist"]["edicao_por_insert"]["status"] == "pendente"
    assert motivo in md
    assert "pendente" in md.lower()


def test_densidade_fora_do_alvo_diz_o_que_fazer(tmp_path):
    pj, plano, _ = medir_exemplo(tmp_path, roteiro=ROTEIRO_SEM_INSERT, chaves=())
    medir.gravar(pj, plano)
    md = texto(pj)
    assert plano["densidade"]["fracao_insert"] < plano["densidade"]["piso"]
    assert "abaixo do piso" in md.lower()
    assert "exceção" in md.lower()


ROTEIRO_SEM_INSERT = """\
[apresentador | hook: QUANTO CUSTA | por mês | PRA TER ISSO?] Quanto custa por mês ter isso rodando agora.
[apresentador] Com cem reais você já começa e ainda sobra para o resto do mês inteiro.
[cta | KEY: SAIBA MAIS] Toque em saiba mais.
"""


def test_propostas_de_insert_aparecem_na_densidade(tmp_path):
    sug = {"propostas": [{"bloco": 1, "opcoes": ["gravação de tela do painel", "print da fatura"]}]}
    pj, plano, _ = medir_exemplo(tmp_path, roteiro=ROTEIRO_SEM_INSERT, chaves=(), sugestoes=sug)
    medir.gravar(pj, plano)
    md = texto(pj)
    assert "gravação de tela do painel" in md and "print da fatura" in md


def test_rodape_declara_o_sha_do_plano_json_lido(pronto):
    pj, _ = pronto
    md = texto(pj)
    assert escrever_md.sha_declarado(md) == sha(pj.plano_json)
    assert re.search(r"sha256 %s" % sha(pj.plano_json), md)


def test_confere_acusa_md_velho_ou_ausente(pronto):
    pj, plano = pronto
    ok, motivo = escrever_md.confere(pj)
    assert not ok and "plano_edicao.md" in motivo                       # ainda não escrito
    escrever_md.escrever(pj)
    assert escrever_md.confere(pj) == (True, "")
    novo = copy.deepcopy(plano)
    novo["hook"]["linha"] = "4 horas por dia"
    medir.gravar(pj, novo)                                              # plano.json mudou, md ficou
    ok, motivo = escrever_md.confere(pj)
    assert not ok and "plano.json" in motivo and "vam plano" in motivo


def test_confere_acusa_md_editado_a_mao(pronto):
    pj, _ = pronto
    escrever_md.escrever(pj)
    pj.plano_md.write_text(pj.plano_md.read_text(encoding="utf-8").replace("Hook", "Gancho"), encoding="utf-8")
    ok, motivo = escrever_md.confere(pj)
    assert not ok and "editado" in motivo


def test_md_e_deterministico(pronto):
    pj, _ = pronto
    assert texto(pj) == texto(pj)


def test_instrucao_de_aprovacao_fala_do_ok_no_chat(pronto):
    pj, _ = pronto
    md = texto(pj)
    assert "ok" in md.lower() and "vam aprovar %s" % SLUG in md


def test_sem_travessao_sem_nome_do_dono_e_sem_marcador_de_ia(pronto):
    pj, _ = pronto
    md = texto(pj)
    assert "—" not in md and "–" not in md
    for nome in ("julio", "júlio", "thales", "jheni"):
        assert nome not in md.lower()


def test_renderizar_aceita_plano_de_gravado(tmp_path):
    from tests.plano.test_medir import ROTEIRO_GRAVADO, TRECHOS
    pj, plano, _ = medir_exemplo(tmp_path, roteiro=ROTEIRO_GRAVADO, modo="gravado", chaves=(),
                                 sugestoes={"trechos": TRECHOS})
    md = escrever_md.renderizar(plano)
    assert "IMG_0001" in md and "9,3" in md
    assert escrever_md.secoes_ausentes(md) == []


def test_modulo_nao_tem_nome_do_dono():
    from pathlib import Path
    fonte = (Path(__file__).resolve().parents[2] / "scripts" / "plano" / "escrever_md.py").read_text(
        encoding="utf-8").lower()
    for nome in ("julio", "júlio", "thales", "jheni"):
        assert nome not in fonte
    assert "—" not in fonte and "–" not in fonte
