"""W3.B: plano/medir. O plano.json nasce MEDIDO (roteiro + alinhamento da fala + arquivos de insert),
nunca declarado: tempo dos blocos, densidade, congelamento, letterings, hook, ritmo e efeitos saem de
conta, e quem tenta declarar um desses números é recusado.

Sem mídia e sem ffprobe: o alinhamento são palavras sintéticas com tempo conhecido e `sondar` é
simulado. O ffprobe de verdade só entra no teste do interpretador, com a saída dele em texto.

As funções `montar_projeto`, `palavras_sinteticas` e `sondar_falso` são usadas também pelos testes
de escrever_md, aprovacao e gate_aprovacao.
"""
import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

import analise_inserts
import caminhos
import ritmo
from contratos.validar import normalizar_palavra, validar
from entrada import roteiro_md
from gates import gate_fidelidade_roteiro
from plano import checklist, medir
from projeto import modelo, pastas

RAIZ = Path(__file__).resolve().parents[2]
EXEMPLOS = RAIZ / "contratos" / "exemplos"
SLUG = "tres-horas"
AGORA = "2026-10-09T10:00:00-03:00"
ACEL = 1.35

# O repo não carrega os nomes que ele proíbe: a lista é de sha256 de palavras em minúsculas, como a varredura da
# W6.D. Travessão também não aparece escrito aqui: os códigos são montados na hora.
NOMES_PROIBIDOS = frozenset({
    "901be86d450c504e8555ffeeeab1e06b926c8785fd99ef382c1310b7c66bc167",
    "0f93ac79e8080a952e10e309d126ac2c6309d2a97811e3bc923221bdc63b4778",
    "3dba2d2e96e3a37e36af293826144bf2fcf6e54b279558e8f571acf707881cef",
    "e3a5e4f62a3add3d82bd6b1b2d354c01395b59d4dadebafe5df522736e0a380d"})
TRAVESSOES = (chr(0x2014), chr(0x2013))


def nomes_proibidos_em(texto):
    palavras = set(re.findall(r"\w+", texto.lower()))
    return sorted(p for p in palavras if hashlib.sha256(p.encode("utf-8")).hexdigest() in NOMES_PROIBIDOS)


def travessoes_em(texto):
    return [t for t in TRAVESSOES if t in texto]

ROTEIRO = (EXEMPLOS / "roteiro.valido.completo.md").read_text(encoding="utf-8")

ROTEIRO_GRAVADO = """\
[apresentador | hook: QUANTO CUSTA | por mês | PRA TER ISSO?] Quanto custa por mês ter isso rodando?
[apresentador] Com cem reais você já começa e ainda sobra para o resto do mês.
[cta | KEY: SAIBA MAIS] Toque em saiba mais.
"""

MEDIDAS = {"painel": (1280, 644, 8.36), "planilha": (1280, 692, 10.04), "automacao": (958, 720, 7.16)}


# --- material de teste (também usado pelos outros testes do plano) -----------------------------------

def projeto_base(modo="avatar", **extra):
    p = {"versao": 1, "slug": SLUG, "modo": modo,
         "trilha": {"desligada": True, "motivo": "teste sem trilha licenciada"}}
    if modo == "avatar":
        p["look"] = "meu-look"
    p.update(extra)
    return p


def montar_projeto(tmp_path, roteiro=ROTEIRO, modo="avatar", chaves=("painel", "planilha", "automacao"),
                   **extra):
    """Projeto de teste em tmp: roteiro.md, projeto.json e um arquivo qualquer por chave de insert."""
    pj = pastas.projeto(SLUG, tmp_path / "_local").criar()
    pj.roteiro.write_text(roteiro, encoding="utf-8")
    modelo.escrever(pj.projeto_json, projeto_base(modo, **extra))
    for c in chaves:
        (pj.inserts_dir / (c + ".mp4")).write_bytes(b"insert " + c.encode())
    return pj


def palavras_sinteticas(texto=ROTEIRO, passo=0.4, pausa=0.25):
    """O alinhamento da fala: uma palavra a cada `passo` s, `pausa` s entre blocos."""
    lei = roteiro_md.exigir(roteiro_md.ler(texto))
    saida, t = [], 0.0
    for b in lei.blocos:
        for tok in b["fala"].split():
            if normalizar_palavra(tok):
                saida.append({"text": tok, "start": round(t, 3), "end": round(t + passo * 0.9, 3)})
                t += passo
        t += pausa
    return saida


def tempos_por_bloco(palavras, texto=ROTEIRO):
    """[[início de cada palavra do bloco k]] na ordem em que o plano as conta."""
    lei = roteiro_md.exigir(roteiro_md.ler(texto))
    saida, i = [], 0
    for b in lei.blocos:
        n = len([t for t in b["fala"].split() if normalizar_palavra(t)])
        saida.append([p["start"] for p in palavras[i:i + n]])
        i += n
    return saida


def sondar_falso(medidas=None):
    tabela = dict(MEDIDAS)
    tabela.update(medidas or {})

    def sondar(caminho):
        largura, altura, dur = tabela[Path(caminho).stem]
        return {"largura": largura, "altura": altura, "duracao_s": dur}
    return sondar


def medir_exemplo(tmp_path, roteiro=ROTEIRO, modo="avatar", medidas=None, sugestoes=None, **extra):
    pj = montar_projeto(tmp_path, roteiro=roteiro, modo=modo, **extra)
    chaves = list(MEDIDAS)
    plano = medir.medir(pj, palavras=palavras_sinteticas(roteiro), sondar=sondar_falso(medidas),
                        sugestoes=sugestoes, agora=AGORA)
    return pj, plano, chaves


def sha(caminho):
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


@pytest.fixture
def exemplo(tmp_path):
    pj, plano, _ = medir_exemplo(tmp_path)
    return pj, plano


# --- tempo dos blocos -----------------------------------------------------------------------------------

def test_blocos_contiguos_e_com_o_tempo_do_alinhamento(exemplo):
    pj, plano = exemplo
    pal = palavras_sinteticas()
    inicios = [t[0] for t in tempos_por_bloco(pal)]
    blocos = plano["blocos"]
    assert len(blocos) == 7
    assert blocos[0]["s"] == 0.0
    for k in range(1, 7):
        assert blocos[k]["s"] == pytest.approx(inicios[k], abs=1e-3)
        assert blocos[k]["s"] == blocos[k - 1]["e"]
    assert blocos[-1]["e"] == pytest.approx(pal[-1]["end"], abs=1e-3)
    assert plano["duracao_s"] == blocos[-1]["e"]


def test_bloco_curto_demais_ganha_o_minimo_de_0_3_s(tmp_path):
    """Duas falas coladas: o bloco não pode ter duração zero (o mesmo piso do motor antigo)."""
    texto = ("[apresentador | hook: UM | DOIS | TRÊS] Oi.\n"
             "[apresentador] Tudo bem com você hoje.\n"
             "[cta | KEY: SAIBA MAIS] Toque em saiba mais.\n")
    pal = palavras_sinteticas(texto, passo=0.4, pausa=0.0)
    pal[1]["start"] = pal[0]["start"] + 0.05            # a 2ª fala começa 0,05 s depois da 1ª
    pj = montar_projeto(tmp_path, roteiro=texto, chaves=())
    plano = medir.medir(pj, palavras=pal, sondar=sondar_falso(), agora=AGORA)
    b = plano["blocos"]
    assert all(x["e"] - x["s"] >= 0.3 - 1e-9 for x in b)
    assert all(b[k]["s"] == b[k - 1]["e"] for k in range(1, len(b)))


def test_o_layout_do_roteiro_e_o_padrao_cheio_dos_inserts(exemplo):
    _, plano = exemplo
    layouts = [b.get("layout") for b in plano["blocos"]]
    assert layouts == ["cheio", None, None, "split", None, "cheio", None]


# --- densidade, ritmo e congelamento: medidos -----------------------------------------------------------

def _segmentos(plano, ajustes):
    blocos = []
    for b in plano["blocos"]:
        aj = ajustes.get(b.get("insert") or "", {})
        blocos.append({"tipo": "insert" if b["tipo"] == "insert" else "orig", "s": b["s"], "e": b["e"],
                       "crop": aj.get("recorte"), "dur_max": aj.get("dur_max"), "texto": b["fala"]})
    return ritmo.plano_de_ritmo(blocos)


def test_densidade_e_a_fracao_do_tempo_em_insert_do_plano_de_ritmo(exemplo):
    _, plano = exemplo
    segs = _segmentos(plano, {})
    esperado = sum(x["e"] - x["s"] for x in segs if x["tipo"] == "insert") / plano["duracao_s"]
    d = plano["densidade"]
    assert d["fracao_insert"] == pytest.approx(esperado, abs=1e-3)
    assert (d["alvo_min"], d["alvo_max"], d["piso"], d["teto"]) == (0.45, 0.55, 0.40, 0.65)


def test_dur_max_do_projeto_entra_na_densidade(tmp_path):
    _, sem, _ = medir_exemplo(tmp_path / "a")
    ajustes = {"painel": {"dur_max": 1.0}, "planilha": {"dur_max": 1.5}}
    _, com, _ = medir_exemplo(tmp_path / "b", inserts=ajustes)
    esperado = sum(x["e"] - x["s"] for x in _segmentos(com, ajustes) if x["tipo"] == "insert")
    assert com["densidade"]["fracao_insert"] == pytest.approx(esperado / com["duracao_s"], abs=1e-3)
    assert com["densidade"]["fracao_insert"] < sem["densidade"]["fracao_insert"]


def test_ritmo_e_o_do_arquivo_entregue_dividido_pela_aceleracao(exemplo):
    _, plano = exemplo
    segs = _segmentos(plano, {})
    dur = plano["duracao_s"] / ACEL
    planos = [(x["e"] - x["s"]) / ACEL for x in segs]
    r = plano["ritmo"]
    cortes = len(medir.cortes_previstos(segs, plano["blocos"]))          # W5.X: só fronteira que muda a imagem
    assert r["cortes_min"] == pytest.approx(cortes / (dur / 60), abs=0.06)
    assert r["maior_plano_s"] == pytest.approx(max(planos), abs=0.01)
    assert r["plano_medio_s"] == pytest.approx(dur / len(segs), abs=0.01)
    assert r["frac_acima_6s"] == pytest.approx(sum(p for p in planos if p > 6) / dur, abs=1e-3)


def test_ritmo_usa_a_aceleracao_do_projeto(tmp_path):
    _, a, _ = medir_exemplo(tmp_path / "a")
    _, b, _ = medir_exemplo(tmp_path / "b", aceleracao=1.2)
    assert b["ritmo"]["cortes_min"] < a["ritmo"]["cortes_min"]          # menos aceleração, menos cortes por minuto


def test_mapa_de_inserts_mede_o_arquivo(exemplo):
    pj, plano = exemplo
    mapa = {m["chave"]: m for m in plano["mapa_inserts"]}
    assert list(mapa) == ["painel", "planilha", "automacao"]
    p = mapa["painel"]
    assert (p["arquivo"], p["blocos"], p["largura"], p["altura"], p["duracao_s"]) == \
        ("inserts/painel.mp4", [0], 1280, 644, 8.36)
    assert p["orientacao"] == "horizontal" and p["tratamento"] == "moldura" and p["visitas"] >= 1
    assert mapa["planilha"]["tratamento"] == "split" and mapa["planilha"]["blocos"] == [3]
    assert mapa["automacao"]["tratamento"] == "moldura" and mapa["automacao"]["blocos"] == [5]


def test_insert_vertical_entra_cheio_e_imagem_estatica_e_imagem(tmp_path):
    _, plano, _ = medir_exemplo(tmp_path, medidas={"painel": (1080, 1920, 6.0), "automacao": (1200, 800, 0.0)})
    mapa = {m["chave"]: m for m in plano["mapa_inserts"]}
    assert mapa["painel"]["orientacao"] == "vertical" and mapa["painel"]["tratamento"] == "cheio"
    assert mapa["automacao"]["tratamento"] == "imagem" and mapa["automacao"]["congela_s"] == 0.0


def test_congelamento_e_a_conta_do_analise_inserts(tmp_path):
    """consome = duração do bloco x velocidade; congela = consome - (fonte - início). Insert de 1 s num bloco
    de ~3,4 s congela mais de 2 s; velocidade 2x dobra o consumo; o início da fonte tira da sobra."""
    _, base, _ = medir_exemplo(tmp_path / "a", medidas={"painel": (1280, 644, 1.0)})
    bloco = base["blocos"][0]
    dur_bloco = bloco["e"] - bloco["s"]
    mapa = {m["chave"]: m for m in base["mapa_inserts"]}
    assert mapa["painel"]["congela_s"] == pytest.approx(dur_bloco - 1.0, abs=0.01)
    assert mapa["planilha"]["congela_s"] == 0.0

    _, rapido, _ = medir_exemplo(tmp_path / "b", medidas={"painel": (1280, 644, 1.0)},
                                 inserts={"painel": {"velocidade": 2.0}})
    assert {m["chave"]: m for m in rapido["mapa_inserts"]}["painel"]["congela_s"] == \
        pytest.approx(2 * dur_bloco - 1.0, abs=0.01)

    _, deslocado, _ = medir_exemplo(tmp_path / "c", medidas={"painel": (1280, 644, 5.0)},
                                    inserts={"painel": {"inicio": 3.0}})
    assert {m["chave"]: m for m in deslocado["mapa_inserts"]}["painel"]["congela_s"] == \
        pytest.approx(max(0.0, dur_bloco - 2.0), abs=0.01)


def test_dur_max_limita_o_consumo_no_congelamento(tmp_path):
    _, plano, _ = medir_exemplo(tmp_path, medidas={"painel": (1280, 644, 1.0)},
                                inserts={"painel": {"dur_max": 1.0}})
    assert {m["chave"]: m for m in plano["mapa_inserts"]}["painel"]["congela_s"] == 0.0


def test_congelamento_confere_com_o_analise_inserts_existente(tmp_path, monkeypatch):
    """A mesma medição que o gate de entrada do motor antigo faz: se os dois divergirem, um dos dois mente."""
    medidas = {"painel": (1280, 644, 1.7), "planilha": (1280, 692, 2.5), "automacao": (958, 720, 7.16)}
    pj, plano, _ = medir_exemplo(tmp_path, medidas=medidas,
                                 inserts={"planilha": {"velocidade": 1.5, "inicio": 0.4}})
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    entradas, prancha = {}, {"inserts": []}
    for n, m in enumerate(plano["mapa_inserts"], 1):
        b = plano["blocos"][m["blocos"][0]]
        aj = {"planilha": {"speed": 1.5, "start": 0.4}}.get(m["chave"], {})
        entradas["#%d#" % n] = {"file": "/x/%s.mp4" % m["chave"], "start": aj.get("start", 0),
                                "speed": aj.get("speed", 1.0)}
        prancha["inserts"].append({"src": "broll%02d.mp4" % n, "s": b["s"], "d": b["e"] - b["s"]})
    (inputs / "x_inserts.json").write_text(json.dumps(entradas), encoding="utf-8")
    monkeypatch.setattr(caminhos, "INPUTS", inputs)
    monkeypatch.setattr(analise_inserts, "dur_fonte", lambda p: medidas[Path(p).stem][2])
    antigo = analise_inserts.analisar("x", prancha)
    novo = {m["chave"]: m["congela_s"] for m in plano["mapa_inserts"]}
    for linha, m in zip(antigo, plano["mapa_inserts"]):
        assert novo[m["chave"]] == pytest.approx(linha["congela"], abs=0.01), m["chave"]


def test_visitas_contam_trechos_seguidos_de_insert(exemplo):
    _, plano = exemplo
    assert all(1 <= m["visitas"] <= 2 for m in plano["mapa_inserts"])


# --- hook -------------------------------------------------------------------------------------------------

def test_hook_vem_do_roteiro_e_termina_quando_o_rosto_volta(exemplo):
    _, plano = exemplo
    h = plano["hook"]
    assert (h["eyebrow"], h["linha"], h["destaque"]) == ("VOCÊ PERDE", "3 horas por dia", "NISSO AQUI")
    assert h["estilo"] == "editorial" and h["evento_visual"] == "insert"
    retorno = plano["blocos"][1]["s"]
    assert h["fim_s"] == pytest.approx(min(retorno + 0.1 * ACEL, 3.2 * ACEL), abs=0.011)


def test_hook_tem_teto_de_3_2_s_entregues(tmp_path):
    """Com 3 inserts de abertura seguidos o hook não segura até o rosto voltar: teto de 3,2 s entregues."""
    texto = ("[insert: painel | hook: A | B | C] Primeira frase bem longa para este bloco durar bastante tempo.\n"
             "[insert: planilha] Segunda frase também comprida para empurrar o rosto para longe da abertura.\n"
             "[apresentador] Agora sim o rosto.\n"
             "[cta | KEY: SAIBA MAIS] Toque em saiba mais.\n")
    _, plano, _ = medir_exemplo(tmp_path, roteiro=texto)
    assert plano["blocos"][2]["s"] > 3.2 * ACEL
    assert plano["hook"]["fim_s"] == pytest.approx(3.2 * ACEL, abs=0.011)


def test_estilo_do_hook_vem_do_projeto(tmp_path):
    _, plano, _ = medir_exemplo(tmp_path, estilo={"hook": "punch"})
    assert plano["hook"]["estilo"] == "punch"


def test_hook_sem_insert_de_abertura_dura_3_s_entregues(tmp_path):
    _, plano, _ = medir_exemplo(tmp_path, roteiro=ROTEIRO_GRAVADO, modo="gravado", chaves=(),
                                sugestoes={"trechos": TRECHOS})
    assert plano["hook"]["fim_s"] == pytest.approx(3.0 * 1.2, abs=0.011)          # take real: aceleração 1,2
    assert plano["hook"].get("evento_visual") in ("corte", "punch", None)


# --- letterings ------------------------------------------------------------------------------------------

def _por_bloco(plano, bloco):
    return [l for l in plano["letterings"] if l["bloco"] == bloco]


def test_cinco_letterings_com_o_tempo_da_palavra_ancora(exemplo):
    _, plano = exemplo
    t = tempos_por_bloco(palavras_sinteticas())
    ls = plano["letterings"]
    assert [(l["bloco"], l["key"]) for l in ls] == [
        (2, "FALTA DE TEMPO"), (4, "a proposta atrasa"), (4, "o cliente esfria"),
        (4, "você perde a venda"), (6, "SAIBA MAIS")]
    assert ls[0]["s"] == pytest.approx(t[2][0], abs=1e-3)
    assert [l["s"] for l in ls[1:4]] == pytest.approx([t[4][2], t[4][5], t[4][9]], abs=1e-3)
    assert ls[4]["s"] == pytest.approx(t[6][0], abs=1e-3)


def test_ancoras_lead_e_pilha(exemplo):
    _, plano = exemplo
    ls = plano["letterings"]
    assert ls[0]["lead"] == "o problema não é" and ls[0]["ancora"] == {"palavra": "O", "n": 1}
    assert [l["pilha"] for l in ls] == [None, "b4", "b4", "b4", None]
    assert [l["lead"] for l in ls[1:4]] == ["enquanto isso", None, None]
    assert [l["ancora"] for l in ls[1:4]] == [{"palavra": "a", "n": 1}, {"palavra": "o", "n": 1},
                                              {"palavra": "você", "n": 1}]
    assert ls[4]["lead"] == "toque em" and ls[4]["ancora"] == {"palavra": "Toque", "n": 1}


def test_duracoes_key_pilha_e_cta(exemplo):
    _, plano = exemplo
    ls, blocos = plano["letterings"], plano["blocos"]
    assert ls[0]["d"] == pytest.approx(2.2 * ACEL, abs=0.011)               # DUR_KEY entregue, no relógio da footage
    fim_pilha = blocos[4]["e"]
    for l in ls[1:4]:
        assert l["s"] + l["d"] == pytest.approx(fim_pilha, abs=0.011)       # a pilha fecha junto
    assert ls[4]["s"] + ls[4]["d"] == pytest.approx(plano["duracao_s"], abs=0.011)
    assert all(l["s"] + l["d"] <= plano["duracao_s"] + 1e-6 for l in ls)


def test_key_nao_atravessa_o_fim_do_bloco(tmp_path):
    texto = ("[insert: painel | hook: A | B | C] Abertura com tempo suficiente.\n"
             "[apresentador | KEY: FRASE CURTA] Pouco.\n"
             "[cta | KEY: SAIBA MAIS] Toque em saiba mais.\n")
    _, plano, _ = medir_exemplo(tmp_path, roteiro=texto)
    b = plano["blocos"][1]
    key = _por_bloco(plano, 1)[0]
    assert key["s"] + key["d"] <= b["e"] + 1e-6


def test_estilos_de_lettering(tmp_path):
    _, plano, _ = medir_exemplo(tmp_path, estilo={"lettering": "punch"})
    assert [l["estilo"] for l in plano["letterings"]] == ["punch"] * 4 + ["seta_cta"]
    assert [l["cta"] for l in plano["letterings"]] == [False] * 4 + [True]


def test_ancora_explicita_e_ocorrencia_dentro_do_bloco(tmp_path):
    texto = ("[insert: painel | hook: A | B | C] Abertura com tempo suficiente.\n"
             "[apresentador | KEY: DIA A DIA | âncora: dia#2] Todo dia eu faço isso, dia após dia, sem parar.\n"
             "[cta | KEY: SAIBA MAIS] Toque em saiba mais.\n")
    pal = palavras_sinteticas(texto)
    pj = montar_projeto(tmp_path, roteiro=texto)
    plano = medir.medir(pj, palavras=pal, sondar=sondar_falso(), agora=AGORA)
    key = _por_bloco(plano, 1)[0]
    assert key["ancora"] == {"palavra": "dia", "n": 2}
    assert key["s"] == pytest.approx(tempos_por_bloco(pal, texto)[1][5], abs=1e-3)       # 2º "dia" é a 6ª palavra


def test_o_plano_medido_passa_na_fidelidade_ao_roteiro(exemplo):
    """Cross-check com o gate de entrada da W3.C: o que o roteiro marca está no plano, igual."""
    pj, plano = exemplo
    medir.gravar(pj, plano)
    r = gate_fidelidade_roteiro.rodar(pj)
    assert r.ok, r.motivo


# --- efeitos, referências e checklist ---------------------------------------------------------------------

def test_sfx_com_funcao_e_sem_whoosh(exemplo):
    _, plano = exemplo
    sfx = plano["efeitos"]["sfx"]
    assert {s["efeito"] for s in sfx} <= {"riser", "tick", "boom"}
    ticks = [s for s in sfx if s["efeito"] == "tick"]
    assert [t["t"] for t in ticks] == pytest.approx([l["s"] for l in plano["letterings"][1:4]], abs=1e-3)
    riser = [s for s in sfx if s["efeito"] == "riser"]
    assert len(riser) == 1 and riser[0]["funcao"] == "cta"
    assert riser[0]["t"] == pytest.approx(plano["blocos"][6]["s"] - 1.0 * ACEL, abs=0.011)
    assert [s["t"] for s in sfx] == sorted(s["t"] for s in sfx)


def test_camera_nunca_pune_em_insert_nem_em_split(exemplo):
    _, plano = exemplo
    por_bloco = {c["bloco"]: c for c in plano["efeitos"]["camera"]}
    assert por_bloco[2]["tipo"] == "punch" and por_bloco[2]["t"] == plano["letterings"][0]["s"]
    assert por_bloco[4]["tipo"] == "respiro"
    for c in plano["efeitos"]["camera"]:
        if plano["blocos"][c["bloco"]]["tipo"] == "insert":
            assert c["tipo"] in ("push_in", "zoom")
            assert c["tipo"] != "punch"


def test_referencias_saem_das_tecnicas_que_o_plano_tem(exemplo):
    _, plano = exemplo
    ref = plano["referencias"][0]
    assert ref["nome"] == "padrão do produto"
    t = " ".join(ref["tecnicas"]).lower()
    assert "split" in t and "seta" in t and "insert" in t


def test_checklist_tem_os_oito_itens_mais_ritmo(exemplo):
    _, plano = exemplo
    assert tuple(plano["checklist"]) == checklist.ITENS
    assert len(checklist.ITENS) == 9
    assert checklist.problemas_do_checklist(plano["checklist"]) == []


def test_o_plano_medido_cumpre_o_contrato_e_as_seis_secoes(exemplo):
    _, plano = exemplo
    assert validar("plano", plano) == []
    assert checklist.problemas(plano) == []


def test_fonte_amarra_roteiro_e_projeto(exemplo):
    pj, plano = exemplo
    assert plano["fonte"] == {"roteiro_sha256": sha(pj.roteiro), "projeto_sha256": sha(pj.projeto_json)}
    assert plano["projeto"] == SLUG and plano["modo"] == "avatar" and plano["gerado_em"] == AGORA


def test_medir_e_deterministico(tmp_path):
    _, a, _ = medir_exemplo(tmp_path / "a")
    _, b, _ = medir_exemplo(tmp_path / "b")
    assert a == b


# --- o que é declarado e o que não pode ser ---------------------------------------------------------------

@pytest.mark.parametrize("campo", ["densidade", "letterings", "blocos", "mapa_inserts", "ritmo", "checklist",
                                   "hook", "efeitos"])
def test_nao_se_declara_o_que_se_mede(tmp_path, campo):
    pj = montar_projeto(tmp_path)
    with pytest.raises(ValueError) as e:
        medir.medir(pj, palavras=palavras_sinteticas(), sondar=sondar_falso(), sugestoes={campo: {}})
    assert campo in str(e.value) and "medid" in str(e.value)


def test_sugestoes_aceitas(tmp_path):
    sug = {"referencias": [{"nome": "referência de ritmo A", "tecnicas": ["corte seco na entrada do insert"]}],
           "propostas": [{"bloco": 1, "opcoes": ["gravação de tela do painel", "print da fatura"]}],
           "propostos": [5]}
    _, plano, _ = medir_exemplo(tmp_path, sugestoes=sug)
    assert [r["nome"] for r in plano["referencias"]] == ["padrão do produto", "referência de ritmo A"]
    prop = plano["densidade"]["propostas"]
    assert prop == [{"bloco": 1, "fala": plano["blocos"][1]["fala"],
                     "opcoes": ["gravação de tela do painel", "print da fatura"]}]
    assert [b.get("proposto", False) for b in plano["blocos"]] == [False] * 5 + [True, False]
    assert validar("plano", plano) == []


def test_sugestao_com_bloco_inexistente_ou_sem_opcoes_e_recusada(tmp_path):
    pj = montar_projeto(tmp_path)
    for ruim in ({"propostas": [{"bloco": 40, "opcoes": ["x"]}]},
                 {"propostas": [{"bloco": 1, "opcoes": []}]},
                 {"referencias": [{"nome": "A", "tecnicas": []}]},
                 {"propostos": [99]},
                 {"inventada": 1}):
        with pytest.raises(ValueError):
            medir.medir(pj, palavras=palavras_sinteticas(), sondar=sondar_falso(), sugestoes=ruim)


# --- modos e entradas que não se medem ---------------------------------------------------------------------

TRECHOS = {"corpo": [{"take": "IMG_0001", "inicio": 9.3, "fim": 14.0}],
           "cta": [{"take": "IMG_0001", "inicio": 52.16, "fim": 53.9}]}


def test_gravado_exige_os_trechos_do_take(tmp_path):
    pj = montar_projeto(tmp_path, roteiro=ROTEIRO_GRAVADO, modo="gravado", chaves=())
    pal = palavras_sinteticas(ROTEIRO_GRAVADO)
    with pytest.raises(medir.PlanoNaoMedivel) as e:
        medir.medir(pj, palavras=pal, sondar=sondar_falso(), agora=AGORA)
    assert "trechos" in str(e.value)
    plano = medir.medir(pj, palavras=pal, sondar=sondar_falso(), sugestoes={"trechos": TRECHOS}, agora=AGORA)
    assert plano["modo"] == "gravado" and plano["trechos"] == TRECHOS
    assert plano["mapa_inserts"] == [] and plano["densidade"]["fracao_insert"] == 0.0
    assert validar("plano", plano) == []
    assert checklist.problemas(plano) == []
    assert plano["checklist"]["efeito_por_insert"]["status"] == "nao_se_aplica"


def test_roteiro_livre_nao_se_mede(tmp_path):
    livre = "Você perde três horas por dia nisso aqui.\n\nToque em saiba mais.\n"
    pj = montar_projeto(tmp_path, roteiro=livre, chaves=())
    with pytest.raises(medir.PlanoNaoMedivel) as e:
        medir.medir(pj, palavras=palavras_sinteticas(livre), sondar=sondar_falso())
    assert "livre" in str(e.value) and "roteiro_livre" in str(e.value)


def test_roteiro_fora_da_convencao_cita_a_linha(tmp_path):
    pj = montar_projeto(tmp_path, roteiro="[apresentador] Oi.\n[desconhecido] Tchau.\n", chaves=())
    with pytest.raises(roteiro_md.RoteiroInvalido) as e:
        medir.medir(pj, palavras=[{"text": "x", "start": 0, "end": 1}], sondar=sondar_falso())
    assert "linha 2" in str(e.value)


def test_insert_sem_arquivo_cita_a_chave(tmp_path):
    pj = montar_projeto(tmp_path, chaves=("painel", "planilha"))
    with pytest.raises(medir.PlanoNaoMedivel) as e:
        medir.medir(pj, palavras=palavras_sinteticas(), sondar=sondar_falso())
    assert "automacao" in str(e.value)


def test_sem_alinhamento_diz_onde_esta_a_voz(tmp_path):
    pj = montar_projeto(tmp_path)
    with pytest.raises(medir.PlanoNaoMedivel) as e:
        medir.medir(pj, sondar=sondar_falso())
    assert "voz/limpo.mp3" in str(e.value)


def test_asr_injetado_e_usado_quando_nao_ha_palavras(tmp_path):
    pj = montar_projeto(tmp_path)
    pj.voz_dir.mkdir(parents=True, exist_ok=True)
    pj.voz_limpo.write_bytes(b"mp3")
    chamadas = []

    def asr(caminho):
        chamadas.append(Path(caminho))
        return palavras_sinteticas()
    plano = medir.medir(pj, asr=asr, sondar=sondar_falso(), agora=AGORA)
    assert chamadas == [pj.voz_limpo] and len(plano["blocos"]) == 7


def test_transcricao_vazia_nao_vira_plano_inventado(tmp_path):
    pj = montar_projeto(tmp_path)
    with pytest.raises(medir.PlanoNaoMedivel) as e:
        medir.medir(pj, palavras=[], sondar=sondar_falso())
    assert "vazia" in str(e.value)


def test_fala_que_nao_bate_com_o_roteiro_nao_vira_tempo(tmp_path):
    """Mesma quantidade de palavras, outro texto: o alinhamento por posição daria tempos de mentira."""
    pj = montar_projeto(tmp_path)
    falsas = [dict(p, text="lorem") for p in palavras_sinteticas()]
    with pytest.raises(medir.PlanoNaoMedivel) as e:
        medir.medir(pj, palavras=falsas, sondar=sondar_falso())
    assert "gate_fala_roteiro" in str(e.value)


def test_erro_de_grafia_do_asr_nao_atrapalha(tmp_path):
    pal = palavras_sinteticas()
    pal[2]["text"] = "tres"                      # acento perdido
    pal[5]["text"] = "diaa"                      # palavra com erro
    pj = montar_projeto(tmp_path)
    plano = medir.medir(pj, palavras=pal, sondar=sondar_falso(), agora=AGORA)
    assert len(plano["blocos"]) == 7


def test_alinhamento_fora_do_formato_diz_o_que_falta(tmp_path):
    pj = montar_projeto(tmp_path)
    for ruim in ([{"text": "oi"}], [{"text": "oi", "start": "a", "end": 1}], ["oi"], [{"start": 0, "end": 1}]):
        with pytest.raises(medir.PlanoNaoMedivel) as e:
            medir.medir(pj, palavras=ruim, sondar=sondar_falso())
        assert "text" in str(e.value) and "start" in str(e.value)


def test_trechos_e_sugestoes_nao_sao_compartilhados_com_quem_chamou(tmp_path):
    from tests.plano.test_medir import ROTEIRO_GRAVADO
    pj = montar_projeto(tmp_path, roteiro=ROTEIRO_GRAVADO, modo="gravado", chaves=())
    sug = {"trechos": copy.deepcopy(TRECHOS)}
    plano = medir.medir(pj, palavras=palavras_sinteticas(ROTEIRO_GRAVADO), sondar=sondar_falso(), sugestoes=sug,
                        agora=AGORA)
    plano["trechos"]["corpo"][0]["take"] = "OUTRO"
    assert sug["trechos"] == TRECHOS


# --- ffprobe -----------------------------------------------------------------------------------------------

def test_interpretar_ffprobe_video_horizontal():
    saida = {"streams": [{"width": 1920, "height": 1080}], "format": {"duration": "30.160000"}}
    assert medir.interpretar_ffprobe(saida) == {"largura": 1920, "altura": 1080, "duracao_s": 30.16}


def test_interpretar_ffprobe_com_rotacao_troca_largura_e_altura():
    """ffprobe mente sobre rotação: o vídeo de celular vem 1920x1080 com rotação de -90 graus."""
    saida = {"streams": [{"width": 1920, "height": 1080, "side_data_list": [{"rotation": -90}]}],
             "format": {"duration": "54.7"}}
    assert medir.interpretar_ffprobe(saida) == {"largura": 1080, "altura": 1920, "duracao_s": 54.7}
    antigo = {"streams": [{"width": 1920, "height": 1080, "tags": {"rotate": "90"}}], "format": {"duration": "1"}}
    assert medir.interpretar_ffprobe(antigo)["largura"] == 1080


def test_interpretar_ffprobe_imagem_nao_tem_duracao():
    saida = {"streams": [{"width": 800, "height": 600, "codec_name": "png"}], "format": {"format_name": "png_pipe"}}
    assert medir.interpretar_ffprobe(saida)["duracao_s"] == 0.0


def test_interpretar_ffprobe_sem_stream_de_video():
    with pytest.raises(medir.PlanoNaoMedivel):
        medir.interpretar_ffprobe({"streams": [], "format": {}})


def test_sondar_ffprobe_usa_ffprobe_e_devolve_o_interpretado(monkeypatch, tmp_path):
    arquivo = tmp_path / "x.mp4"
    arquivo.write_bytes(b"x")
    visto = {}

    class R:
        returncode = 0
        stdout = json.dumps({"streams": [{"width": 10, "height": 20}], "format": {"duration": "2.5"}})
        stderr = ""

    def falso(cmd, **kw):
        visto["cmd"] = cmd
        return R()
    monkeypatch.setattr(medir.subprocess, "run", falso)
    assert medir.sondar_ffprobe(arquivo) == {"largura": 10, "altura": 20, "duracao_s": 2.5}
    assert visto["cmd"][0] == "ffprobe" and str(arquivo) in visto["cmd"]


def test_sondar_ffprobe_que_falha_diz_o_arquivo(monkeypatch, tmp_path):
    arquivo = tmp_path / "quebrado.mp4"
    arquivo.write_bytes(b"x")

    class R:
        returncode = 1
        stdout = ""
        stderr = "Invalid data found"
    monkeypatch.setattr(medir.subprocess, "run", lambda *a, **k: R())
    with pytest.raises(medir.PlanoNaoMedivel) as e:
        medir.sondar_ffprobe(arquivo)
    assert "quebrado.mp4" in str(e.value)


# --- gravar e CLI ------------------------------------------------------------------------------------------

def test_gravar_escreve_o_plano_validado_de_forma_atomica(exemplo):
    pj, plano = exemplo
    destino = medir.gravar(pj, plano)
    assert destino == pj.plano_json
    assert json.loads(destino.read_text(encoding="utf-8")) == plano
    assert not [p for p in pj.plano_dir.iterdir() if p.name.endswith(".tmp")]


def test_gravar_recusa_plano_invalido_e_nao_deixa_arquivo(exemplo):
    pj, plano = exemplo
    ruim = copy.deepcopy(plano)
    del ruim["hook"]
    with pytest.raises(ValueError) as e:
        medir.gravar(pj, ruim)
    assert "hook" in str(e.value)
    assert not pj.plano_json.exists()


def test_cli_grava_plano_e_md_e_registra_o_status(tmp_path, capsys):
    pj = montar_projeto(tmp_path)
    arq = tmp_path / "palavras.json"
    arq.write_text(json.dumps(palavras_sinteticas()), encoding="utf-8")
    rc = medir.main(["--projeto", str(pj.raiz), "--palavras", str(arq)], sondar=sondar_falso())
    assert rc == 0
    assert pj.plano_json.is_file() and pj.plano_md.is_file()
    assert validar("plano", json.loads(pj.plano_json.read_text(encoding="utf-8"))) == []
    from projeto import status
    assert status.ler(pj)["atual"]["etapa"] == "plano" and status.ler(pj)["atual"]["estado"] == "ok"
    assert "blocos" in capsys.readouterr().out


def test_cli_insumo_invalido_sai_com_2(tmp_path, capsys):
    pj = montar_projeto(tmp_path, chaves=("painel",))
    arq = tmp_path / "palavras.json"
    arq.write_text(json.dumps(palavras_sinteticas()), encoding="utf-8")
    rc = medir.main(["--projeto", str(pj.raiz), "--palavras", str(arq)], sondar=sondar_falso())
    assert rc == 2
    assert "planilha" in capsys.readouterr().err
    assert not pj.plano_json.exists()


def test_cli_pasta_que_nao_e_projeto_sai_com_2(tmp_path, capsys):
    rc = medir.main(["--projeto", str(tmp_path / "solta")], sondar=sondar_falso())
    assert rc == 2
    assert "projetos" in capsys.readouterr().err


def test_modulo_nao_tem_nome_do_dono():
    texto = (RAIZ / "scripts" / "plano" / "medir.py").read_text(encoding="utf-8")
    assert nomes_proibidos_em(texto) == []
    assert travessoes_em(texto) == []
