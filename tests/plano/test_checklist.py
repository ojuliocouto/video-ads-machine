"""W3.B: plano/checklist. As 6 seções do plano e a checklist do padrão de edição (8 itens + ritmo).

Regras (fase 2 do plano de edição e padrão de edição):
  - plano sem qualquer das 6 seções reprova CITANDO a seção;
  - cada item da checklist é atendido, não se aplica ou pendente COM motivo; pendente sem motivo reprova;
  - os status saem da medição do plano (inserts, split, letterings, ritmo), nunca de declaração.
"""
import copy
import json
from pathlib import Path

import pytest

import medir_ritmo
from contratos.validar import validar
from plano import checklist
from tests.plano.test_medir import nomes_proibidos_em, travessoes_em

RAIZ = Path(__file__).resolve().parents[2]
EXEMPLOS = RAIZ / "contratos" / "exemplos"


def carregar(nome):
    return json.loads((EXEMPLOS / nome).read_text(encoding="utf-8"))


@pytest.fixture
def avatar():
    return carregar("plano.valido.avatar.json")


@pytest.fixture
def gravado():
    return carregar("plano.valido.gravado.json")


def projeto(**extra):
    p = {"versao": 1, "slug": "tres-horas", "modo": "avatar", "look": "meu-look",
         "trilha": {"desligada": True, "motivo": "teste sem trilha licenciada"}}
    p.update(extra)
    return p


# --- os itens ----------------------------------------------------------------------------------------

def test_itens_sao_os_do_contrato_na_mesma_ordem():
    schema = json.loads((RAIZ / "contratos" / "plano.schema.json").read_text(encoding="utf-8"))
    assert list(checklist.ITENS) == schema["properties"]["checklist"]["required"]
    assert len(checklist.ITENS) == 9 and checklist.ITENS[-1] == "ritmo"


def test_cada_item_tem_o_rotulo_do_padrao_de_edicao():
    assert set(checklist.ROTULOS) == set(checklist.ITENS)
    assert all(isinstance(t, str) and len(t) > 15 for t in checklist.ROTULOS.values())
    assert "ritmo" in checklist.ROTULOS["ritmo"].lower()
    assert "degradê" in checklist.ROTULOS["degrade_emenda"].lower()


def test_secoes_sao_as_seis_do_plano():
    assert [s[0] for s in checklist.SECOES] == ["mapa_inserts", "hook", "letterings", "densidade",
                                                 "referencias", "efeitos"]


# --- verificação: seções ------------------------------------------------------------------------------

def test_exemplos_do_contrato_passam(avatar, gravado):
    assert checklist.problemas(avatar) == []
    assert checklist.problemas(gravado) == []


@pytest.mark.parametrize("secao", [s[0] for s in checklist.SECOES])
def test_plano_sem_uma_das_seis_secoes_reprova_citando_a_secao(avatar, secao):
    del avatar[secao]
    probs = checklist.problemas(avatar)
    assert probs, "plano sem a seção %s foi aceito" % secao
    assert any("'%s'" % secao in p for p in probs), probs
    assert all("campo obrigatório" not in p for p in probs)      # a mensagem é a da seção, não a do schema


def test_secao_nula_conta_como_ausente(avatar):
    avatar["hook"] = None
    assert any("'hook'" in p for p in checklist.problemas(avatar))


def test_plano_sem_lettering_de_cta_reprova_na_secao_de_letterings(avatar):
    avatar["letterings"] = [l for l in avatar["letterings"] if not l["cta"]]
    probs = checklist.problemas(avatar)
    assert any("'letterings'" in p and "CTA" in p for p in probs), probs


def test_plano_fora_do_contrato_lista_os_campos(avatar):
    avatar["densidade"]["fracao_insert"] = 1.7
    probs = checklist.problemas(avatar)
    assert any("fracao_insert" in p for p in probs), probs


def test_secoes_ausentes_do_plano_devolve_as_chaves(avatar):
    del avatar["hook"]
    del avatar["efeitos"]
    assert checklist.secoes_ausentes_do_plano(avatar) == ["hook", "efeitos"]


# --- verificação: itens -------------------------------------------------------------------------------

def test_checklist_valida_do_exemplo(avatar):
    assert checklist.problemas_do_checklist(avatar["checklist"]) == []


@pytest.mark.parametrize("item", checklist.ITENS)
def test_item_ausente_cita_o_item(avatar, item):
    del avatar["checklist"][item]
    probs = checklist.problemas_do_checklist(avatar["checklist"])
    assert any(item in p for p in probs), probs


@pytest.mark.parametrize("item", checklist.ITENS)
def test_pendente_sem_motivo_reprova(avatar, item):
    avatar["checklist"][item] = {"status": "pendente"}
    probs = checklist.problemas_do_checklist(avatar["checklist"])
    assert any(item in p and "motivo" in p for p in probs), probs
    assert any(item in p for p in checklist.problemas(avatar))


@pytest.mark.parametrize("motivo", ["", "   ", None])
def test_pendente_com_motivo_vazio_reprova(avatar, motivo):
    avatar["checklist"]["atencao"] = {"status": "pendente", "motivo": motivo}
    assert any("atencao" in p for p in checklist.problemas_do_checklist(avatar["checklist"]))


def test_pendente_com_motivo_passa(avatar):
    avatar["checklist"]["atencao"] = {"status": "pendente", "motivo": "falta a seta no CTA, o diretor decide"}
    assert checklist.problemas_do_checklist(avatar["checklist"]) == []
    assert checklist.problemas(avatar) == []


def test_status_desconhecido_reprova(avatar):
    avatar["checklist"]["ritmo"] = {"status": "talvez"}
    probs = checklist.problemas_do_checklist(avatar["checklist"])
    assert any("ritmo" in p and "talvez" in p for p in probs), probs


def test_nao_se_aplica_pode_vir_sem_motivo_como_no_contrato(gravado):
    assert gravado["checklist"]["elemento_atras"] == {"status": "nao_se_aplica"}
    assert checklist.problemas_do_checklist(gravado["checklist"]) == []


def test_checklist_que_nao_e_objeto_reprova():
    assert checklist.problemas_do_checklist(None)
    assert checklist.problemas_do_checklist([])


# --- avaliação: os status saem da medição ------------------------------------------------------------

def status_de(plano, **proj):
    return {k: v["status"] for k, v in checklist.avaliar(plano, projeto(**proj)).items()}


def test_avaliar_devolve_os_nove_itens_validos(avatar):
    r = checklist.avaliar(avatar, projeto())
    assert tuple(r) == checklist.ITENS
    assert checklist.problemas_do_checklist(r) == []
    avatar["checklist"] = r
    assert validar("plano", avatar) == []


def test_avaliar_nao_muda_o_plano(avatar):
    antes = copy.deepcopy(avatar)
    checklist.avaliar(avatar, projeto())
    assert avatar == antes


def test_plano_com_insert_split_seta_e_ritmo_bom_atende_tudo_menos_o_que_nao_se_aplica(avatar):
    st = status_de(avatar)
    assert st == {"efeito_por_insert": "atendido", "elemento_atras": "nao_se_aplica", "atencao": "atendido",
                  "split_dominante": "atendido", "degrade_emenda": "atendido", "lettering_legenda": "atendido",
                  "variacao_contexto": "atendido", "edicao_por_insert": "atendido", "ritmo": "atendido"}


def test_nao_se_aplica_sempre_traz_o_motivo(avatar):
    r = checklist.avaliar(avatar, projeto())
    assert r["elemento_atras"]["motivo"]
    avatar["mapa_inserts"] = []
    for b in avatar["blocos"]:
        if b["tipo"] == "insert":
            b["tipo"], b["insert"], b["layout"] = "apresentador", None, None
    r = checklist.avaliar(avatar, projeto())
    for item in ("efeito_por_insert", "split_dominante", "degrade_emenda", "variacao_contexto",
                 "edicao_por_insert"):
        assert r[item]["status"] == "nao_se_aplica" and r[item]["motivo"], item


def test_texto_atras_ligado_atende_o_elemento_atras(avatar):
    assert status_de(avatar, estilo={"texto_atras": True})["elemento_atras"] == "atendido"
    assert status_de(avatar, estilo={"texto_atras": False})["elemento_atras"] == "nao_se_aplica"


def test_sem_seta_no_cta_a_atencao_fica_pendente_com_motivo(avatar):
    for l in avatar["letterings"]:
        if l["cta"]:
            l["estilo"] = "caixa_nativa"
    r = checklist.avaliar(avatar, projeto())
    assert r["atencao"]["status"] == "pendente" and "seta" in r["atencao"]["motivo"]


def test_marcador_conta_como_elemento_de_atencao(avatar):
    for l in avatar["letterings"]:
        if l["cta"]:
            l["estilo"] = "caixa_nativa"
    avatar["letterings"][0]["estilo"] = "marcador"
    assert status_de(avatar)["atencao"] == "atendido"


def test_sem_split_nao_ha_degrade_nem_split_dominante(avatar):
    for b in avatar["blocos"]:
        if b.get("layout") == "split":
            b["layout"] = "cheio"
    for m in avatar["mapa_inserts"]:
        if m["tratamento"] == "split":
            m["tratamento"] = "moldura"
    r = checklist.avaliar(avatar, projeto())
    assert r["split_dominante"]["status"] == "nao_se_aplica" and "split" in r["split_dominante"]["motivo"]
    assert r["degrade_emenda"]["status"] == "nao_se_aplica"


def test_dois_inserts_com_o_mesmo_tratamento_deixam_a_variacao_pendente(avatar):
    for m in avatar["mapa_inserts"]:
        m["tratamento"] = "moldura"
    r = checklist.avaliar(avatar, projeto())
    assert r["variacao_contexto"]["status"] == "pendente" and "tratamento" in r["variacao_contexto"]["motivo"]


def test_um_insert_so_nao_pede_variacao(avatar):
    avatar["mapa_inserts"] = avatar["mapa_inserts"][:1]
    for b in avatar["blocos"]:
        if b.get("insert") in ("planilha", "automacao"):
            b["tipo"], b["insert"], b["layout"] = "apresentador", None, None
    avatar["mapa_inserts"][0]["blocos"] = [0]
    assert checklist.avaliar(avatar, projeto())["variacao_contexto"]["status"] == "nao_se_aplica"


def test_insert_que_congela_deixa_a_edicao_por_insert_pendente(avatar):
    avatar["mapa_inserts"][1]["congela_s"] = 1.4
    r = checklist.avaliar(avatar, projeto())
    item = r["edicao_por_insert"]
    assert item["status"] == "pendente"
    assert "planilha" in item["motivo"] and "1,4" in item["motivo"]


def test_congelamento_no_limite_nao_reprova(avatar):
    avatar["mapa_inserts"][1]["congela_s"] = 0.2
    assert status_de(avatar)["edicao_por_insert"] == "atendido"


@pytest.mark.parametrize("campo,valor,trecho", [
    ("cortes_min", 9.0, "cortes/min"),
    ("cortes_min", 40.0, "cortes/min"),
    ("frac_acima_6s", 0.55, "tempo parado"),
    ("maior_plano_s", 16.0, "16"),
])
def test_ritmo_fora_dos_limites_fica_pendente_com_o_motivo_do_medir_ritmo(avatar, campo, valor, trecho):
    avatar["ritmo"][campo] = valor
    r = checklist.avaliar(avatar, projeto())
    assert r["ritmo"]["status"] == "pendente"
    assert trecho in r["ritmo"]["motivo"]
    assert len(r["ritmo"]["motivo"]) <= 500


def test_limites_do_ritmo_sao_os_do_medir_ritmo():
    assert checklist.LIMITES_RITMO == {"cortes_min": (medir_ritmo.MIN_CORTES_MIN, medir_ritmo.MAX_CORTES_MIN),
                                      "frac_lenta": medir_ritmo.MAX_FRAC_LENTA,
                                      "maior_plano": medir_ritmo.MAX_PLANO_S}


def test_sem_lettering_a_variacao_lettering_legenda_fica_pendente(avatar):
    avatar["letterings"] = [l for l in avatar["letterings"] if l["cta"]]
    avatar["letterings"][0]["estilo"] = "seta_cta"
    r = checklist.avaliar(avatar, projeto())
    assert r["lettering_legenda"]["status"] == "pendente"
    assert "KEY" in r["lettering_legenda"]["motivo"]


def test_todo_pendente_traz_motivo_em_qualquer_combinacao(avatar):
    """Invariante: nenhuma combinação de plano produz pendente sem motivo ou item fora do contrato."""
    base = copy.deepcopy(avatar)
    mutacoes = [
        lambda p: p["ritmo"].update(cortes_min=3.0),
        lambda p: p["mapa_inserts"][0].update(congela_s=2.0),
        lambda p: [l.update(estilo="caixa_nativa") for l in p["letterings"]],
        lambda p: p.update(letterings=[l for l in p["letterings"] if l["cta"]]),
        lambda p: [m.update(tratamento="moldura") for m in p["mapa_inserts"]],
        lambda p: p.update(mapa_inserts=[]),
    ]
    for n in range(1 << len(mutacoes)):
        p = copy.deepcopy(base)
        for k, m in enumerate(mutacoes):
            if n >> k & 1:
                m(p)
        r = checklist.avaliar(p, projeto())
        assert checklist.problemas_do_checklist(r) == [], (n, r)
        for item, v in r.items():
            if v["status"] in ("pendente", "nao_se_aplica"):
                assert v.get("motivo"), (n, item)
            else:
                assert v.get("como"), (n, item)


def test_avaliar_aceita_projeto_ausente(avatar):
    assert tuple(checklist.avaliar(avatar)) == checklist.ITENS


def test_modulo_nao_tem_nome_do_dono_nem_travessao():
    texto = (RAIZ / "scripts" / "plano" / "checklist.py").read_text(encoding="utf-8")
    assert nomes_proibidos_em(texto) == []
    assert travessoes_em(texto) == []
