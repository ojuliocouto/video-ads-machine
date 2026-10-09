"""A entrega do gravado no produto (W5.D): gate com saída 1 trava a cópia, e a legenda entregue é a aprovada.

O pipeline de origem copiava `legendado/` para `ENTREGA/` sem consultar gate nenhum. Aqui a entrega:

  - roda os 11 gates do gravado, mais a conferência "legenda aprovada" (o sha256 do .ass que foi
    queimado é o do .ass que o diretor aprovou, e o arquivo da pasta `legendado/` é o que saiu da
    queima), e não copia NADA se qualquer um sai com defeito (1) ou sem conseguir medir (2);
  - confere a cópia byte a byte (sha256) e deixa o `ENTREGA/entrega.json`: o que foi entregue, com o
    hash de cada peça e o veredito de cada gate;
  - pela CLI (`vam gravado <slug> entregar`) sai 0 (entregou), 1 (algum gate reprovou) ou 2 (algum
    gate não mediu, ou não há o que entregar).
"""
import argparse
import json
from pathlib import Path

import pytest

from cli import gravado as cli_gravado
from gravado import entregar, legendar, queimar_legenda
from gravado import projeto as gp
from gravado.veredito import InsumoInvalido
from tests.gravado import sintese as sx

ADS = {"A1": {"corpo": [["T1", 0.0, 3.5]], "cta_normal": [["T1", 4.0, 5.0]]}}


def w(texto, ini, fim):
    return {"text": texto, "start": ini, "end": fim}


def _nada_entregue(proj):
    """Nenhuma peça nem manifesto em ENTREGA/. (No macOS `ENTREGA` e o `entrega/` do layout do projeto são a
    mesma pasta, e o `novo` já cria `entrega/folhas`: por isso a conferência é por peça e manifesto, não por
    pasta vazia.)"""
    pasta = proj.pasta("ENTREGA")
    return not list(pasta.glob("*.mp4")) and not (pasta / "entrega.json").exists()


def _gate(estado, motivo="m"):
    def rodar():
        if estado == "insumo":
            raise InsumoInvalido(motivo)
        return estado, motivo
    return rodar


def _projeto(tmp_path, estado):
    p = sx.projeto_de_teste(tmp_path, ads=ADS, com_limpo=False, estado=estado)
    (p.base / "montados").mkdir()
    (p.base / "montados" / "A1_normal.mp4").write_bytes(b"montada")
    p.garantir("legendado")
    p.legendado("A1_normal").write_bytes(b"peca legendada" * 50)
    return p


def _legenda_aprovada_e_queimada(p, nome="A1_normal"):
    """O que o pipeline faz de verdade: legenda, relatório, aprovação do diretor, queima registrada."""
    legendar.legendar_pecas(p, [nome], sx.LeitorFalso(palavras_da_peca=[w("ola", 0.0, 0.3), w("mundo", 0.4, 0.8)]))
    legendar.aprovar(p, nome, "ok, li a legenda")
    queimar_legenda.registrar_queima(p, nome)


def _args(*argv):
    ap = argparse.ArgumentParser(prog="vam")
    cli_gravado.registrar(ap.add_subparsers(dest="comando"))
    return ap.parse_args(["gravado", *argv])


def _cli(estado, slug, *argv):
    return cli_gravado.executar(_args(slug, *argv, "--estado", str(estado)))


# --- entregar: os gates mandam -------------------------------------------------------------------

def test_entregar_com_um_gate_com_saida_1_nao_copia_nada_e_o_resumo_diz_o_motivo(tmp_path, estado_vazio):
    p = _projeto(tmp_path, estado_vazio)
    r = entregar.entregar(p, gates=[("gate_ar_morto", _gate(False, "pausa de 0.9s em 12.0s")),
                                    ("gate_legenda", _gate(True))])
    assert (r.entregue, r.codigo) == (False, 1)
    assert _nada_entregue(p)
    assert "pausa de 0.9s" in r.resumo() and "NADA FOI COPIADO" in r.resumo()


def test_entregar_com_gate_que_nao_mediu_sai_2_e_nao_copia(tmp_path, estado_vazio):
    p = _projeto(tmp_path, estado_vazio)
    r = entregar.entregar(p, gates=[("gate_fala", _gate("insumo", "ASR falhou"))])
    assert (r.entregue, r.codigo) == (False, 2)
    assert _nada_entregue(p)


def test_entregue_deixa_o_manifesto_com_o_hash_de_cada_peca_e_o_veredito_de_cada_gate(tmp_path, estado_vazio):
    p = _projeto(tmp_path, estado_vazio)
    r = entregar.entregar(p, gates=[("gate_a", _gate(True, "ok a")), ("gate_b", _gate(True, "ok b"))])
    assert r.entregue
    m = json.loads((p.pasta("ENTREGA") / "entrega.json").read_text(encoding="utf-8"))
    assert m["versao"] == 1 and m["aceleracao"] == 1.2
    assert [x["nome"] for x in m["pecas"]] == ["A1_normal.mp4"]
    assert m["pecas"][0]["sha256"] == legendar.sha256_arquivo(p.legendado("A1_normal"))
    assert m["pecas"][0]["sha256"] == legendar.sha256_arquivo(p.pasta("ENTREGA") / "A1_normal.mp4")
    assert [(g["nome"], g["estado"]) for g in m["gates"]] == [("gate_a", "ok"), ("gate_b", "ok")]


def test_entrega_que_falhou_nao_deixa_manifesto(tmp_path, estado_vazio):
    p = _projeto(tmp_path, estado_vazio)
    entregar.entregar(p, gates=[("gate_a", _gate(False))])
    assert not (p.pasta("ENTREGA") / "entrega.json").exists()


# --- a legenda entregue é a aprovada -------------------------------------------------------------

def test_gates_da_entrega_sao_os_onze_mais_a_legenda_aprovada_no_fim(tmp_path, estado_vazio):
    p = _projeto(tmp_path, estado_vazio)
    nomes = [n for n, _ in entregar.gates_da_entrega(p, sx.LeitorFalso(textos="x"))]
    assert len(nomes) == 12 and nomes[:11] == [n for n, _ in entregar.gates_padrao(p, sx.LeitorFalso(textos="x"))]
    assert nomes[-1] == "legenda_aprovada"


def test_peca_sem_legenda_aprovada_e_defeito_e_diz_como_aprovar(tmp_path, estado_vazio):
    p = _projeto(tmp_path, estado_vazio)
    ok, motivo = entregar.legenda_aprovada(p)
    assert not ok and "A1_normal" in motivo and "aprovar-legenda" in motivo


def test_peca_sem_registro_de_queima_e_defeito(tmp_path, estado_vazio):
    p = _projeto(tmp_path, estado_vazio)
    legendar.legendar_pecas(p, ["A1_normal"], sx.LeitorFalso(palavras_da_peca=[w("ola", 0.0, 0.3)]))
    legendar.aprovar(p, "A1_normal", "ok")
    ok, motivo = entregar.legenda_aprovada(p)
    assert not ok and "queima" in motivo


def test_legenda_aprovada_e_queimada_passa(tmp_path, estado_vazio):
    p = _projeto(tmp_path, estado_vazio)
    _legenda_aprovada_e_queimada(p)
    ok, motivo = entregar.legenda_aprovada(p)
    assert ok, motivo


def test_ass_editado_depois_da_queima_trava_a_entrega(tmp_path, estado_vazio):
    p = _projeto(tmp_path, estado_vazio)
    _legenda_aprovada_e_queimada(p)
    p.legenda_ass("A1_normal").write_bytes(p.legenda_ass("A1_normal").read_bytes() + b"; editado\n")
    ok, motivo = entregar.legenda_aprovada(p)
    assert not ok and "depois da aprovação" in motivo


def test_arquivo_legendado_trocado_depois_da_queima_trava_a_entrega(tmp_path, estado_vazio):
    p = _projeto(tmp_path, estado_vazio)
    _legenda_aprovada_e_queimada(p)
    p.legendado("A1_normal").write_bytes(b"outra peca que nao saiu da queima")
    ok, motivo = entregar.legenda_aprovada(p)
    assert not ok and "não é o que saiu da queima" in motivo


def test_queima_de_um_ass_que_nao_e_o_aprovado_trava_a_entrega(tmp_path, estado_vazio):
    p = _projeto(tmp_path, estado_vazio)
    _legenda_aprovada_e_queimada(p)
    reg_arq = queimar_legenda.caminho_queima(p, "A1_normal")
    reg = json.loads(reg_arq.read_text(encoding="utf-8"))
    reg["ass_sha256"] = "0" * 64
    reg_arq.write_text(json.dumps(reg), encoding="utf-8")
    ok, motivo = entregar.legenda_aprovada(p)
    assert not ok and "queimada de outro .ass" in motivo


def test_entregar_padrao_sem_legenda_aprovada_nao_copia_nada(tmp_path, estado_vazio, monkeypatch):
    """A cadeia real: com todos os 11 gates verdes e a legenda sem aprovação, nada sai."""
    p = _projeto(tmp_path, estado_vazio)
    monkeypatch.setattr(entregar, "gates_padrao",
                        lambda proj, leitor: [("gate_a", _gate(True)), ("gate_b", _gate(True))])
    r = entregar.entregar(p, leitor=sx.LeitorFalso(textos="x"))
    assert (r.entregue, r.codigo) == (False, 1)
    assert [(n, e) for n, e, _ in r.gates][-1] == ("legenda_aprovada", "defeito")
    assert _nada_entregue(p)
    _legenda_aprovada_e_queimada(p)
    r2 = entregar.entregar(p, leitor=sx.LeitorFalso(textos="x"))
    assert (r2.entregue, r2.codigo) == (True, 0)


# --- a CLI: vam gravado <slug> entregar ----------------------------------------------------------

def _preparar_cli(tmp_path, estado, monkeypatch, gates):
    from projeto import novo
    novo.criar("leva", "gravado", sem_trilha="gravado: a voz real segue sem trilha", estado=estado)
    raiz = estado / "projetos" / "leva"
    sx.projeto_minimo(raiz, ADS)
    pr = gp.carregar(raiz, estado=estado)
    (raiz / "montados").mkdir()
    (raiz / "montados" / "A1_normal.mp4").write_bytes(b"montada")
    pr.garantir("legendado")
    pr.legendado("A1_normal").write_bytes(b"peca legendada" * 50)
    monkeypatch.setattr(entregar, "gates_da_entrega", lambda proj, leitor: gates)
    return pr


def test_cli_entregar_com_gate_reprovado_sai_1_e_nao_copia(tmp_path, estado_vazio, monkeypatch, capsys):
    pr = _preparar_cli(tmp_path, estado_vazio, monkeypatch,
                       [("gate_ar_morto", _gate(False, "pausa de 0.9s")), ("gate_legenda", _gate(True))])
    assert _cli(estado_vazio, "leva", "entregar") == 1
    saida = capsys.readouterr().out
    assert "NADA FOI COPIADO" in saida and "pausa de 0.9s" in saida
    assert _nada_entregue(pr)


def test_cli_entregar_com_gate_sem_medir_sai_2(tmp_path, estado_vazio, monkeypatch):
    pr = _preparar_cli(tmp_path, estado_vazio, monkeypatch, [("gate_fala", _gate("insumo", "ASR falhou"))])
    assert _cli(estado_vazio, "leva", "entregar") == 2
    assert _nada_entregue(pr)


def test_cli_entregar_tudo_verde_sai_0_copia_e_confere(tmp_path, estado_vazio, monkeypatch, capsys):
    pr = _preparar_cli(tmp_path, estado_vazio, monkeypatch, [("gate_a", _gate(True)), ("gate_b", _gate(True))])
    assert _cli(estado_vazio, "leva", "entregar") == 0
    assert "ENTREGUE: 1 peça(s)" in capsys.readouterr().out
    assert (pr.pasta("ENTREGA") / "A1_normal.mp4").read_bytes() == pr.legendado("A1_normal").read_bytes()


def test_cli_entregar_sem_pecas_legendadas_sai_2(tmp_path, estado_vazio, monkeypatch):
    pr = _preparar_cli(tmp_path, estado_vazio, monkeypatch, [("gate_a", _gate(True))])
    pr.legendado("A1_normal").unlink()
    assert _cli(estado_vazio, "leva", "entregar") == 2
