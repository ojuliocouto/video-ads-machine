"""W3.C: gate_fidelidade_roteiro. O que o roteiro.md marca tem que chegar inteiro ao plano e aos arquivos.

Três conferências, todas contra o roteiro.md (a fonte da verdade):
  - cada chave `insert: <chave>` tem o seu arquivo em inserts/, e nada sobra lá;
  - cada lettering marcado (KEY, itens de lista, CTA) existe no plano, com o mesmo texto e a mesma âncora;
  - âncora ambígua (a palavra aparece mais de uma vez no bloco) sem `#n` reprova.
Sem mídia: os arquivos de insert são bytes quaisquer.
"""
import copy
import subprocess
import sys
from pathlib import Path

import pytest

from entrada import roteiro_md
from gates import gate_fidelidade_roteiro as G
from projeto import modelo, pastas, status

RAIZ = Path(__file__).resolve().parents[2]
SLUG = "anuncio"

ROTEIRO = """\
[insert: painel | hook: VOCÊ PERDE | 3 horas por dia | NISSO AQUI] Você perde três horas por dia nisso aqui.
[apresentador | LEAD: o problema não é | KEY: FALTA DE TEMPO] O problema não é falta de *tempo*.
[insert: planilha | split] É que cada tarefa repetida come um pedaço da sua agenda.
[lista | LEAD: enquanto isso] Enquanto isso: a proposta atrasa, o cliente esfria e você perde a venda.
[insert: painel] Com uma automação simples isso roda sozinho.
[cta | LEAD: toque em | KEY: SAIBA MAIS] Toque em saiba mais.
"""


def plano_para(texto):
    """Um plano.json coerente com o roteiro (só os campos que o gate lê)."""
    lei = roteiro_md.exigir(roteiro_md.ler(texto))
    blocos, letterings, t = [], [], 0.0
    for i, b in enumerate(lei.blocos):
        blocos.append({"i": i, "tipo": b["tipo"], "insert": b["insert"], "layout": b["layout"],
                       "fala": b["fala"], "s": t, "e": t + 3.0})
        if b["tipo"] == "lista":
            for k, item in enumerate(b["itens"]):
                letterings.append({"bloco": i, "lead": b["lead"] if k == 0 else None,
                                   "key": item["texto"], "ancora": {"palavra": item["texto"].split()[0], "n": 1},
                                   "s": t + k, "d": 1.4, "estilo": "caixa_nativa", "pilha": "lista1", "cta": False})
        elif b["key"]:
            letterings.append({"bloco": i, "lead": b["lead"], "key": b["key"],
                               "ancora": {"palavra": b["ancora"]["palavra"], "n": b["ancora"]["n"]},
                               "s": t, "d": 2.2, "estilo": "seta_cta" if b["tipo"] == "cta" else "caixa_nativa",
                               "pilha": None, "cta": b["tipo"] == "cta"})
        t += 3.0
    hook = lei.blocos[0]["hook"]
    return {"versao": 1, "projeto": SLUG, "blocos": blocos, "letterings": letterings,
            "hook": {"eyebrow": hook["eyebrow"], "linha": hook["linha"], "destaque": hook["destaque"],
                     "estilo": "editorial", "fim_s": 3.0} if hook else None}


def montar(tmp_path, texto=ROTEIRO, chaves=("painel", "planilha"), plano=True):
    estado = tmp_path / "_local"
    pj = pastas.projeto(SLUG, estado).criar()
    modelo.escrever(pj.projeto_json, modelo.minimo(SLUG, "gravado", sem_trilha="sem trilha no teste"))
    pj.roteiro.write_text(texto, encoding="utf-8")
    for c in chaves:
        (pj.inserts_dir / (c + ".mp4")).write_bytes(b"video-" + c.encode())
    if plano:
        status.escrever_json_atomico(pj.plano_json, plano_para(texto))
    return estado, pj


def editar_plano(pj, fn):
    p = status.ler_json(pj.plano_json)
    fn(p)
    status.escrever_json_atomico(pj.plano_json, p)


def test_tudo_fiel_passa(tmp_path):
    estado, pj = montar(tmp_path)
    r = G.rodar(pj)
    assert r.ok, r.motivo
    assert r.detalhes["estado"] == "PASS"
    assert r.detalhes["chaves_de_insert"] == ["painel", "planilha"]
    assert r.detalhes["letterings_no_roteiro"] == 5      # KEY + 3 itens da lista + KEY do CTA
    assert r.detalhes["letterings_no_plano"] == 5


# --- N chaves de insert = N arquivos em inserts/ -------------------------------------------------

def test_chave_do_roteiro_sem_arquivo_reprova(tmp_path):
    estado, pj = montar(tmp_path, chaves=("painel",))
    r = G.rodar(pj)
    assert not r.ok
    assert "planilha" in r.motivo and "sem arquivo" in r.motivo


def test_arquivo_que_o_roteiro_nao_usa_reprova(tmp_path):
    estado, pj = montar(tmp_path, chaves=("painel", "planilha", "sobrou"))
    r = G.rodar(pj)
    assert not r.ok
    assert "sobrou" in r.motivo and "não está no roteiro" in r.motivo


def test_duas_chaves_iguais_em_dois_blocos_pedem_um_arquivo_so(tmp_path):
    """painel aparece em 2 blocos (duas visitas): 1 arquivo basta, N chaves DISTINTAS = N arquivos."""
    estado, pj = montar(tmp_path)
    assert G.rodar(pj).ok
    assert len(pj.inserts()) == 2


def test_dois_arquivos_para_a_mesma_chave_reprova(tmp_path):
    estado, pj = montar(tmp_path)
    (pj.inserts_dir / "painel.png").write_bytes(b"outro")
    r = G.rodar(pj)
    assert not r.ok
    assert "painel" in r.motivo and "mais de um arquivo" in r.motivo


# --- letterings marcados no roteiro = letterings no plano ---------------------------------------

def test_lettering_marcado_que_falta_no_plano_reprova(tmp_path):
    estado, pj = montar(tmp_path)
    editar_plano(pj, lambda p: p["letterings"].pop(0))
    r = G.rodar(pj)
    assert not r.ok
    assert "FALTA DE TEMPO" in r.motivo and "falta no plano" in r.motivo
    assert r.detalhes["letterings_no_plano"] == 4


def test_lettering_do_plano_que_o_roteiro_nao_marcou_reprova(tmp_path):
    estado, pj = montar(tmp_path)

    def extra(p):
        novo = copy.deepcopy(p["letterings"][0])
        novo.update(bloco=0, key="SURPRESA")
        p["letterings"].append(novo)
    editar_plano(pj, extra)
    r = G.rodar(pj)
    assert not r.ok
    assert "SURPRESA" in r.motivo and "o roteiro não marcou" in r.motivo


def test_key_do_plano_com_texto_diferente_reprova(tmp_path):
    estado, pj = montar(tmp_path)
    editar_plano(pj, lambda p: p["letterings"][-1].update(key="COMPRE AGORA"))
    r = G.rodar(pj)
    assert not r.ok
    assert "SAIBA MAIS" in r.motivo and "COMPRE AGORA" in r.motivo


def test_ancora_do_plano_diferente_da_do_roteiro_reprova(tmp_path):
    estado, pj = montar(tmp_path)
    editar_plano(pj, lambda p: p["letterings"][0]["ancora"].update(n=2))
    r = G.rodar(pj)
    assert not r.ok
    assert "âncora" in r.motivo


def test_lista_com_item_a_menos_no_plano_reprova(tmp_path):
    estado, pj = montar(tmp_path)
    editar_plano(pj, lambda p: p["letterings"].remove(next(x for x in p["letterings"] if x.get("pilha"))))
    r = G.rodar(pj)
    assert not r.ok
    assert "lista" in r.motivo


# --- fala e hook do plano não podem divergir do roteiro -------------------------------------------

def test_fala_alterada_no_plano_reprova(tmp_path):
    estado, pj = montar(tmp_path)
    editar_plano(pj, lambda p: p["blocos"][1].update(fala="O problema é outro."))
    r = G.rodar(pj)
    assert not r.ok
    assert "bloco 1" in r.motivo and "fala" in r.motivo


def test_hook_diferente_no_plano_reprova(tmp_path):
    estado, pj = montar(tmp_path)
    editar_plano(pj, lambda p: p["hook"].update(destaque="OUTRA COISA"))
    r = G.rodar(pj)
    assert not r.ok
    assert "hook" in r.motivo


def test_plano_com_numero_de_blocos_diferente_reprova(tmp_path):
    estado, pj = montar(tmp_path)
    editar_plano(pj, lambda p: p["blocos"].pop())
    r = G.rodar(pj)
    assert not r.ok
    assert "blocos" in r.motivo


# --- âncora ambígua sem nth -----------------------------------------------------------------------

AMBIGUO = """\
[apresentador | LEAD: todo | KEY: DIA | âncora: dia] Todo dia eu acordo e penso no dia seguinte.
[cta | KEY: SAIBA MAIS] Toque em saiba mais.
"""


def test_ancora_que_aparece_duas_vezes_sem_nth_reprova(tmp_path):
    estado, pj = montar(tmp_path, texto=AMBIGUO, chaves=(), plano=False)
    r = G.rodar(pj, plano={"blocos": [], "letterings": [], "hook": None})
    assert not r.ok
    assert "ambígua" in r.motivo and "dia#n" in r.motivo
    assert r.detalhes["ancoras_ambiguas"] == ["dia"]


def test_ancora_com_nth_explicito_passa(tmp_path):
    texto = AMBIGUO.replace("âncora: dia]", "âncora: dia#2]")
    estado, pj = montar(tmp_path, texto=texto, chaves=())
    r = G.rodar(pj)
    assert r.ok, r.motivo


# --- roteiro livre: não há direção marcada para cobrar do plano -----------------------------------

LIVRE = "Você perde três horas por dia nisso aqui.\n\nO problema não é falta de tempo.\n"


def test_roteiro_livre_cobra_so_os_inserts_que_o_plano_propos(tmp_path):
    estado, pj = montar(tmp_path, texto=LIVRE, chaves=("painel",), plano=False)
    plano = {"blocos": [{"i": 0, "tipo": "insert", "insert": "painel", "layout": None,
                         "fala": "Você perde três horas por dia nisso aqui.", "proposto": True},
                        {"i": 1, "tipo": "apresentador", "insert": None, "layout": None,
                         "fala": "O problema não é falta de tempo."}],
             "letterings": [], "hook": None}
    status.escrever_json_atomico(pj.plano_json, plano)
    r = G.rodar(pj)
    assert r.ok, r.motivo
    assert r.detalhes["livre"] is True
    (pj.inserts_dir / "painel.mp4").unlink()
    assert not G.rodar(pj).ok


# --- insumos --------------------------------------------------------------------------------------

def test_sem_roteiro_e_insumo_invalido(tmp_path):
    estado, pj = montar(tmp_path)
    pj.roteiro.unlink()
    with pytest.raises(G.InsumoInvalido):
        G.rodar(pj)


def test_roteiro_com_erro_de_gramatica_que_nao_e_ancora_e_insumo_invalido(tmp_path):
    estado, pj = montar(tmp_path, plano=False)
    pj.roteiro.write_text("[desenhar bonito] Isso não é um tipo de bloco.\n", encoding="utf-8")
    with pytest.raises(G.InsumoInvalido) as e:
        G.rodar(pj, plano={})
    assert "roteiro" in str(e.value)


def test_sem_plano_e_insumo_invalido(tmp_path):
    estado, pj = montar(tmp_path, plano=False)
    with pytest.raises(G.InsumoInvalido) as e:
        G.rodar(pj)
    assert "plano.json" in str(e.value)


# --- CLI ------------------------------------------------------------------------------------------

def test_cli_passa_exit_0_e_registra(tmp_path, capsys):
    estado, pj = montar(tmp_path)
    assert G.main([SLUG, "--estado", str(estado)]) == 0
    atual = status.ler(pj)["atual"]
    assert (atual["etapa"], atual["estado"]) == ("gate_fidelidade_roteiro", "ok")


def test_cli_reprova_exit_1_e_registra(tmp_path, capsys):
    estado, pj = montar(tmp_path, chaves=("painel",))
    assert G.main([SLUG, "--estado", str(estado)]) == 1
    atual = status.ler(pj)["atual"]
    assert (atual["etapa"], atual["estado"]) == ("gate_fidelidade_roteiro", "falhou")
    assert "planilha" in atual["motivo"]


def test_cli_insumo_invalido_exit_2_e_registra(tmp_path, capsys):
    estado, pj = montar(tmp_path, plano=False)
    assert G.main([SLUG, "--estado", str(estado)]) == 2
    atual = status.ler(pj)["atual"]
    assert (atual["etapa"], atual["estado"]) == ("gate_fidelidade_roteiro", "bloqueado")


def test_roda_como_script_e_sai_2_sem_projeto(tmp_path):
    estado = tmp_path / "_local"
    estado.mkdir()
    p = subprocess.run([sys.executable, str(RAIZ / "scripts" / "gates" / "gate_fidelidade_roteiro.py"),
                        "nao-existe", "--estado", str(estado)], capture_output=True, text=True)
    assert p.returncode == 2, p.stdout + p.stderr
