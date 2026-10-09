"""W2.C: listagem de looks pela API v3 (GET /v3/avatars/looks), paginada. HTTP injetado."""
import json

from avatar import heygen_cliente as H
from avatar import listar as L

CHAVE = "hg_chave_secreta_de_teste_987654"


def resp(obj, status=200):
    return (status, {}, json.dumps(obj).encode("utf-8"))


def look(i, orient="portrait", engines=("avatar_v", "avatar_iv"), nome=None, tipo="digital_twin"):
    return {"id": "look_ficticio_%03d" % i, "name": nome or "Look %d" % i, "avatar_type": tipo,
            "preferred_orientation": orient, "preview_image_url": "https://p/%d.jpg" % i,
            "supported_api_engines": list(engines), "group_id": "grp_1", "status": "completed"}


class HttpFalso:
    def __init__(self, respostas):
        self.respostas, self.chamadas = list(respostas), []

    def __call__(self, metodo, url, headers, corpo, timeout):
        self.chamadas.append({"metodo": metodo, "url": url, "headers": dict(headers or {})})
        return self.respostas.pop(0)


def cli(respostas):
    http = HttpFalso(respostas)
    return H.ClienteHeyGen(CHAVE, http=http, dormir=lambda s: None), http


def test_pagina_ate_acabar_seguindo_o_next_token():
    c, http = cli([resp({"data": [look(1), look(2)], "has_more": True, "next_token": "tok_2"}),
                   resp({"data": [look(3)], "has_more": False, "next_token": None})])
    achados = L.listar_looks(c)
    assert [a["id"] for a in achados] == ["look_ficticio_001", "look_ficticio_002", "look_ficticio_003"]
    u1, u2 = http.chamadas[0]["url"], http.chamadas[1]["url"]
    assert u1.startswith("https://api.heygen.com/v3/avatars/looks?")
    assert "limit=50" in u1 and "ownership=private" in u1 and "token=" not in u1
    assert "token=tok_2" in u2
    assert all(ch["metodo"] == "GET" for ch in http.chamadas)


def test_so_verticais_por_padrao_e_orientacao_traduzida():
    c, _ = cli([resp({"data": [look(1, "portrait"), look(2, "landscape"), look(3, "square")],
                      "has_more": False})])
    achados = L.listar_looks(c)
    assert [a["orientacao"] for a in achados] == ["vertical"]
    c, _ = cli([resp({"data": [look(1, "portrait"), look(2, "landscape"), look(3, "square")],
                      "has_more": False})])
    todos = L.listar_looks(c, apenas_verticais=False)
    assert sorted(a["orientacao"] for a in todos) == ["horizontal", "quadrado", "vertical"]


def test_campos_normalizados_e_suporte_a_avatar_v():
    c, _ = cli([resp({"data": [look(1, engines=("avatar_iv",)), look(2)], "has_more": False})])
    a, b = L.listar_looks(c)
    assert a["suporta_avatar_v"] is False and b["suporta_avatar_v"] is True
    assert b["nome"] == "Look 2" and b["tipo"] == "digital_twin"
    assert b["previa"] == "https://p/2.jpg"


def test_ownership_publico_e_filtro_de_grupo():
    c, http = cli([resp({"data": [], "has_more": False})])
    L.listar_looks(c, ownership="public", group_id="grp_x")
    u = http.chamadas[0]["url"]
    assert "ownership=public" in u and "group_id=grp_x" in u


def test_resposta_sem_data_e_erro():
    c, _ = cli([resp({"oops": 1})])
    import pytest
    with pytest.raises(H.HeyGenErro):
        L.listar_looks(c)


def test_trava_de_paginas_nao_deixa_laco_infinito():
    laco = resp({"data": [look(1)], "has_more": True, "next_token": "mesmo"})
    c, _ = cli([laco] * (L.MAX_PAGINAS + 5))
    import pytest
    with pytest.raises(H.HeyGenErro):
        L.listar_looks(c)


def test_formatacao_nao_mostra_chave_e_marca_o_que_nao_tem_avatar_v():
    c, _ = cli([resp({"data": [look(1, engines=("avatar_iv",)), look(2)], "has_more": False})])
    texto = L.formatar(L.listar_looks(c))
    assert "look_ficticio_001" in texto and "sem Avatar V" in texto
    assert CHAVE not in texto
