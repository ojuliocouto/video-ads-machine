"""`vam gravado <slug> <ação>` (W5.D): o pipeline de take gravado pela CLI do produto.

Cada ação é uma etapa do pipeline (criar, extrair, isolar, limpo, plano, montar, caixinha, legendar,
aprovar-legenda, queimar, gates, entregar). Saídas, as mesmas dos gates: 0 fez · 1 defeito medido na
peça (gate reprovou) · 2 pedido ou insumo inválido (slug, projeto que não existe, arquivo ausente,
chave da API, aprovação que falta). O estado do aluno (`_local`) vem de `--estado` (os testes passam o
deles; o padrão é o `caminhos.ESTADO`). Nenhum teste aqui usa rede, ASR de verdade nem API paga.
"""
import argparse
import json
from pathlib import Path

import pytest
from PIL import Image

from cli import gravado as cli_gravado
from gravado import compor_caixinha, entregar, legendar
from gravado import projeto as gp
from gravado.veredito import InsumoInvalido
from projeto import pastas
from tests.fixtures import sinteticos as fx
from tests.gravado import sintese as sx

ADS = sx.ADS_DE_TESTE


def w(texto, ini, fim):
    return {"text": texto, "start": ini, "end": fim}


def _args(*argv):
    ap = argparse.ArgumentParser(prog="vam")
    cli_gravado.registrar(ap.add_subparsers(dest="comando"))
    return ap.parse_args(["gravado", *argv])


def _cli(estado, slug, *argv):
    return cli_gravado.executar(_args(slug, *argv, "--estado", str(estado)))


def _criar(estado, tmp_path, slug="leva", ads=ADS, com_limpo=True):
    """Projeto de gravado criado pela própria CLI e preenchido com o plano de teste."""
    brutos = tmp_path / "brutos"
    brutos.mkdir(parents=True, exist_ok=True)
    assert _cli(estado, slug, "criar", "--brutos", str(brutos)) == 0
    raiz = pastas.projeto(slug, estado).raiz
    sx.projeto_minimo(raiz, ads, brutos=brutos)
    if com_limpo:
        audio = sx.audio_por_blocos(tmp_path / "t.wav", sx.BLOCOS_DO_TAKE)
        (raiz / "limpo").mkdir(exist_ok=True)
        for take in ("T1", "T2"):
            (raiz / "limpo" / (take + ".wav")).write_bytes(audio.read_bytes())
    return gp.carregar(raiz, estado=estado)


# --- registro e pedido inválido ------------------------------------------------------------------

def test_registrar_cria_o_subcomando_gravado_e_aponta_para_executar():
    a = _args("leva", "montar", "A1", "--desconto", "--so-plano")
    assert a.comando == "gravado" and a.func is cli_gravado.executar
    assert (a.slug, a.acao, a.alvos, a.desconto, a.so_plano) == ("leva", "montar", ["A1"], True, True)


def test_as_acoes_sao_as_do_pipeline_e_acao_desconhecida_e_erro_de_uso():
    assert cli_gravado.ACOES == ("criar", "extrair", "isolar", "limpo", "plano", "montar", "caixinha", "legendar",
                                 "aprovar-legenda", "queimar", "gates", "entregar")
    with pytest.raises(SystemExit) as e:
        _args("leva", "publicar")
    assert e.value.code == 2


def test_slug_invalido_sai_2_e_diz_o_formato(estado_vazio, capsys):
    assert _cli(estado_vazio, "Leva Ruim", "plano") == 2
    assert "slug inválido" in capsys.readouterr().err


def test_projeto_que_nao_existe_sai_2_e_diz_como_criar(estado_vazio, capsys):
    assert _cli(estado_vazio, "leva", "plano") == 2
    err = capsys.readouterr().err
    assert "leva" in err and "criar" in err and "--brutos" in err


def test_projeto_de_outro_modo_sai_2(estado_vazio, tmp_path, capsys):
    from projeto import novo
    novo.criar("leva", "oneshot", sem_trilha="take unico sem trilha", estado=estado_vazio)
    assert _cli(estado_vazio, "leva", "plano") == 2
    err = capsys.readouterr().err
    assert "oneshot" in err and "gravado" in err


# --- criar ---------------------------------------------------------------------------------------

def test_criar_faz_o_projeto_gravado_com_aceleracao_1_2_e_o_plano_de_partida(estado_vazio, tmp_path, capsys):
    brutos = tmp_path / "brutos"
    brutos.mkdir()
    assert _cli(estado_vazio, "leva", "criar", "--brutos", str(brutos)) == 0
    raiz = pastas.projeto("leva", estado_vazio).raiz
    projeto = json.loads((raiz / "projeto.json").read_text(encoding="utf-8"))
    assert projeto["modo"] == "gravado" and projeto["aceleracao"] == 1.2
    assert projeto["trilha"]["desligada"] is True and projeto["trilha"]["motivo"]
    plano = json.loads((raiz / "plano_gravado.json").read_text(encoding="utf-8"))
    assert plano["brutos"] == str(brutos.resolve()) and plano["ads"] == {}
    assert "1.2" in capsys.readouterr().out


def test_criar_de_novo_e_idempotente_e_nunca_sobrescreve_o_plano(estado_vazio, tmp_path):
    brutos = tmp_path / "brutos"
    brutos.mkdir()
    assert _cli(estado_vazio, "leva", "criar", "--brutos", str(brutos)) == 0
    raiz = pastas.projeto("leva", estado_vazio).raiz
    arq = raiz / "plano_gravado.json"
    plano = json.loads(arq.read_text(encoding="utf-8"))
    plano["ads"] = {"A1": {"corpo": [["T1", 0.0, 1.0]], "cta_normal": [["T1", 2.0, 3.0]]}}
    arq.write_text(json.dumps(plano), encoding="utf-8")
    assert _cli(estado_vazio, "leva", "criar", "--brutos", str(brutos)) == 0
    assert json.loads(arq.read_text(encoding="utf-8"))["ads"].keys() == {"A1"}


def test_criar_sem_brutos_sai_2(estado_vazio):
    assert _cli(estado_vazio, "leva", "criar") == 2


def test_criar_aceita_trilha_ou_motivo_mas_nunca_os_dois(estado_vazio, tmp_path):
    brutos = tmp_path / "b"
    brutos.mkdir()
    assert _cli(estado_vazio, "x1", "criar", "--brutos", str(brutos), "--sem-trilha", "evento: o som do ambiente conta") == 0
    assert _cli(estado_vazio, "x2", "criar", "--brutos", str(brutos), "--trilha", "a.mp3",
                "--sem-trilha", "tanto faz") == 2


def test_criar_nao_deixa_pasta_pela_metade_quando_o_pedido_e_ruim(estado_vazio, tmp_path):
    assert _cli(estado_vazio, "leva", "criar", "--brutos", str(tmp_path / "nao-existe")) == 2
    assert not pastas.projeto("leva", estado_vazio).raiz.exists()


# --- plano ---------------------------------------------------------------------------------------

def test_plano_mostra_aceleracao_e_anuncios_e_escreve_o_md(estado_vazio, tmp_path, capsys):
    p = _criar(estado_vazio, tmp_path)
    capsys.readouterr()
    assert _cli(estado_vazio, "leva", "plano", "--md") == 0
    saida = capsys.readouterr().out
    assert "1.2" in saida and "A1" in saida and "B2" in saida
    assert (p.base / "PLANO-CORTES.md").read_text(encoding="utf-8").startswith("# Plano de cortes")


def test_plano_quebrado_sai_2_e_lista_os_campos(estado_vazio, tmp_path, capsys):
    p = _criar(estado_vazio, tmp_path)
    arq = p.base / "plano_gravado.json"
    plano = json.loads(arq.read_text(encoding="utf-8"))
    plano["ads"]["A1"]["corpo"] = [["T1", 5.0, 1.0]]
    arq.write_text(json.dumps(plano), encoding="utf-8")
    assert _cli(estado_vazio, "leva", "plano") == 2
    assert "corpo[0]" in capsys.readouterr().err


# --- limpo (áudio já higienizado) ----------------------------------------------------------------

def _pasta_de_limpos(tmp_path, takes=("T1", "T2")):
    pasta = tmp_path / "ja_pagos"
    pasta.mkdir()
    audio = sx.audio_por_blocos(tmp_path / "base.wav", sx.BLOCOS_DO_TAKE)
    for t in takes:
        sx.para_mp3(audio, pasta / (t + ".mp3"))
    return pasta


def test_limpo_importa_o_audio_ja_isolado_confere_o_sha_e_nao_toca_na_origem(estado_vazio, tmp_path, capsys):
    p = _criar(estado_vazio, tmp_path, com_limpo=False)
    origem = _pasta_de_limpos(tmp_path)
    antes = {f.name: f.read_bytes() for f in origem.iterdir()}
    assert _cli(estado_vazio, "leva", "limpo", "--de", str(origem)) == 0
    for t in ("T1", "T2"):
        assert (p.base / "limpo" / (t + ".mp3")).read_bytes() == antes[t + ".mp3"]
    assert {f.name: f.read_bytes() for f in origem.iterdir()} == antes
    assert "2 take(s)" in capsys.readouterr().out


def test_limpo_de_so_um_take(estado_vazio, tmp_path):
    p = _criar(estado_vazio, tmp_path, com_limpo=False)
    origem = _pasta_de_limpos(tmp_path)
    assert _cli(estado_vazio, "leva", "limpo", "T1", "--de", str(origem)) == 0
    assert (p.base / "limpo" / "T1.mp3").is_file() and not (p.base / "limpo" / "T2.mp3").exists()


def test_limpo_com_take_ausente_na_origem_sai_2_e_nao_copia_nenhum(estado_vazio, tmp_path, capsys):
    p = _criar(estado_vazio, tmp_path, com_limpo=False)
    origem = _pasta_de_limpos(tmp_path, takes=("T1",))
    assert _cli(estado_vazio, "leva", "limpo", "--de", str(origem)) == 2
    assert "T2" in capsys.readouterr().err
    pasta = p.base / "limpo"
    assert not pasta.exists() or not list(pasta.glob("*"))


def test_limpo_nao_sobrescreve_um_limpo_diferente_que_ja_existe(estado_vazio, tmp_path):
    p = _criar(estado_vazio, tmp_path, com_limpo=False)
    origem = _pasta_de_limpos(tmp_path)
    (p.base / "limpo").mkdir(exist_ok=True)
    (p.base / "limpo" / "T1.mp3").write_bytes(b"outro audio")
    assert _cli(estado_vazio, "leva", "limpo", "--de", str(origem)) == 2
    assert (p.base / "limpo" / "T1.mp3").read_bytes() == b"outro audio"


def test_limpo_sem_a_pasta_de_origem_sai_2(estado_vazio, tmp_path):
    _criar(estado_vazio, tmp_path, com_limpo=False)
    assert _cli(estado_vazio, "leva", "limpo") == 2
    assert _cli(estado_vazio, "leva", "limpo", "--de", str(tmp_path / "nao-existe")) == 2


# --- montar --------------------------------------------------------------------------------------

def test_montar_so_plano_lista_os_segmentos_e_a_aceleracao_do_projeto(estado_vazio, tmp_path, capsys):
    p = _criar(estado_vazio, tmp_path)
    capsys.readouterr()
    assert _cli(estado_vazio, "leva", "montar", "A1", "--so-plano") == 0
    saida = capsys.readouterr().out
    assert "3 segmentos" in saida and "(1.2x)" in saida
    assert not (p.base / "montados").exists() or not list((p.base / "montados").glob("*.mp4"))


def test_montar_anuncio_fora_do_plano_ou_sem_limpo_ou_sem_alvo_sai_2(estado_vazio, tmp_path, capsys):
    _criar(estado_vazio, tmp_path)
    assert _cli(estado_vazio, "leva", "montar", "Z9", "--so-plano") == 2
    assert _cli(estado_vazio, "leva", "montar") == 2
    sem = _criar(estado_vazio, tmp_path / "x", slug="sem-limpo", com_limpo=False)
    capsys.readouterr()
    assert _cli(estado_vazio, "sem-limpo", "montar", "A1", "--so-plano") == 2
    assert "T1" in capsys.readouterr().err


# --- gates ---------------------------------------------------------------------------------------

def _gate(estado, motivo="m"):
    def rodar():
        if estado == "insumo":
            raise InsumoInvalido(motivo)
        return estado, motivo
    return rodar


def test_gates_imprime_cada_um_com_o_codigo_e_sai_pelo_pior(estado_vazio, tmp_path, monkeypatch, capsys):
    _criar(estado_vazio, tmp_path)
    for gates, esperado in (([("gate_a", _gate(True)), ("gate_b", _gate(True))], 0),
                            ([("gate_a", _gate(True)), ("gate_b", _gate(False, "pausa de 0.9s"))], 1),
                            ([("gate_a", _gate("insumo", "ASR falhou")), ("gate_b", _gate(True))], 2),
                            ([("gate_a", _gate("insumo")), ("gate_b", _gate(False))], 1)):
        monkeypatch.setattr(entregar, "gates_da_entrega", lambda proj, leitor, g=gates: g)
        assert _cli(estado_vazio, "leva", "gates") == esperado
    saida = capsys.readouterr().out
    assert "gate_b" in saida and "saída 1" in saida and "saída 0" in saida and "pausa de 0.9s" in saida


# --- legendar, aprovar-legenda, queimar ----------------------------------------------------------

def _montada(p, nome="A1_normal"):
    fx.testsrc_com_audio(p.garantir("montados") / (nome + ".mp4"), dur=3.0)


@pytest.fixture
def leitor_falso(monkeypatch):
    leitor = sx.LeitorFalso(palavras_da_peca=[w("abra", 0.0, 0.3), w("a", 0.3, 0.4), w("Fluxa", 0.4, 0.8)])
    monkeypatch.setattr(gp.Projeto, "leitor", lambda self, backend=None, amb=None: leitor)
    return leitor


def test_legendar_gera_o_ass_e_o_relatorio_da_peca(estado_vazio, tmp_path, leitor_falso, capsys):
    p = _criar(estado_vazio, tmp_path)
    _montada(p)
    assert _cli(estado_vazio, "leva", "legendar", "A1_normal") == 0
    assert p.legenda_ass("A1_normal").is_file() and legendar.caminho_relatorio(p, "A1_normal").is_file()
    assert "SEM_ROTEIRO" in capsys.readouterr().out


def test_legendar_sem_peca_montada_sai_2(estado_vazio, tmp_path, leitor_falso):
    _criar(estado_vazio, tmp_path)
    assert _cli(estado_vazio, "leva", "legendar") == 2


def test_aprovar_legenda_grava_o_ok_so_com_o_texto_do_diretor(estado_vazio, tmp_path, leitor_falso, capsys):
    p = _criar(estado_vazio, tmp_path)
    _montada(p)
    assert _cli(estado_vazio, "leva", "legendar", "A1_normal") == 0
    assert _cli(estado_vazio, "leva", "aprovar-legenda", "A1_normal") == 2                 # sem --ok
    assert not legendar.caminho_aprovacao(p, "A1_normal").exists()
    assert _cli(estado_vazio, "leva", "aprovar-legenda", "A1_normal", "--ok", "li, está certa") == 0
    ap = json.loads(legendar.caminho_aprovacao(p, "A1_normal").read_text(encoding="utf-8"))
    assert ap["ok"] == "li, está certa" and ap["ass"]["sha256"] == legendar.sha256_arquivo(p.legenda_ass("A1_normal"))
    assert "aprovada" in capsys.readouterr().out


def test_aprovar_legenda_de_peca_sem_legenda_sai_2(estado_vazio, tmp_path):
    _criar(estado_vazio, tmp_path)
    assert _cli(estado_vazio, "leva", "aprovar-legenda", "A1_normal", "--ok", "ok") == 2
    assert _cli(estado_vazio, "leva", "aprovar-legenda", "--ok", "ok") == 2                # sem a peça


def test_queimar_sem_legenda_aprovada_sai_2_diz_como_aprovar_e_nao_cria_arquivo(estado_vazio, tmp_path, leitor_falso,
                                                                                capsys):
    p = _criar(estado_vazio, tmp_path)
    _montada(p)
    assert _cli(estado_vazio, "leva", "legendar", "A1_normal") == 0
    capsys.readouterr()
    assert _cli(estado_vazio, "leva", "queimar", "A1_normal") == 2
    assert "aprovar-legenda" in capsys.readouterr().err
    assert not p.legendado("A1_normal").exists()


# --- caixinha (caixa de lettering nativa) --------------------------------------------------------

def test_gerar_png_faz_a_caixa_nativa_no_topo_com_o_texto_inteiro_em_ate_2_linhas(tmp_path):
    img = compor_caixinha.gerar_png("Quanto custa por mês para ter um time de IA na sua operação?",
                                    colorway="ambar", topo=210)
    assert img.size == (1080, 1920) and img.mode == "RGBA"
    alfa = img.split()[3]
    caixa = alfa.getbbox()
    assert caixa[1] == pytest.approx(210, abs=2)                 # o topo pedido
    assert caixa[0] >= 100 and caixa[2] <= 980                   # dentro da zona segura
    assert img.getpixel((caixa[0] + 3, caixa[1] + 3))[:3] == (254, 198, 77)       # âmbar do one-shot, canto reto


def test_gerar_png_usa_a_fonte_do_repo_e_nunca_a_do_sistema():
    import caixa_lettering
    assert caixa_lettering.FONTES and all("/System/" not in f for f in caixa_lettering.FONTES)
    assert Path(caixa_lettering.achar_fonte()).parent.name == "fonts"


def test_cli_caixinha_escreve_o_png_e_compoe_a_peca(estado_vazio, tmp_path, capsys):
    p = _criar(estado_vazio, tmp_path)
    _montada(p)
    assert _cli(estado_vazio, "leva", "caixinha", "A1", "--texto", "Pergunta de teste para a caixa?",
                "--colorway", "branco", "--topo", "200") == 0
    png = p.base / "caixinhas" / "A1_normal.png"
    assert png.is_file() and Image.open(png).size == (1080, 1920)
    assert p.com_caixinha("A1_normal").is_file()
    assert p.fonte_da_peca("A1_normal") == p.com_caixinha("A1_normal")


def test_cli_caixinha_sem_texto_ou_com_colorway_inventado_sai_2(estado_vazio, tmp_path):
    p = _criar(estado_vazio, tmp_path)
    _montada(p)
    assert _cli(estado_vazio, "leva", "caixinha", "A1") == 2
    assert _cli(estado_vazio, "leva", "caixinha", "A1", "--texto", "oi", "--colorway", "rosa") == 2
    assert _cli(estado_vazio, "leva", "caixinha", "Z9", "--texto", "oi") == 2


# --- a CLI não assina nada -----------------------------------------------------------------------

def test_a_cli_so_aprova_pela_funcao_do_legendar_e_so_na_acao_aprovar_legenda():
    texto = (Path(cli_gravado.__file__)).read_text(encoding="utf-8")
    assert texto.count("legendar.aprovar(") == 1
    assert ".aprovacao.json" not in texto
    assert "--ok" in texto
