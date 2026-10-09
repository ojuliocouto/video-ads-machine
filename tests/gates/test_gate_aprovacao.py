"""W3.B: gate_aprovacao. É o primeiro gate do `vam montar`: sem aprovação vigente do plano, não monta.

Vigente = o aluno deu o ok e os quatro arquivos aprovados (roteiro.md, projeto.json, plano/plano.json e
render/inserts.json) continuam byte a byte como estavam. Mudar 1 byte de qualquer um vence a aprovação
("aprovação vencida"). O gate só LÊ: quem escreve a aprovação é plano/aprovacao.py.
"""
import json
from pathlib import Path

import pytest

from gates import gate_aprovacao as G
from plano import aprovacao, escrever_md, medir
from projeto import status
from tests.plano.test_medir import AGORA, SLUG, medir_exemplo

RAIZ = Path(__file__).resolve().parents[2]
OK = "aprovado, pode montar"
ARQUIVOS = {"roteiro": "roteiro.md", "projeto": "projeto.json", "plano": "plano/plano.json",
            "inserts": "render/inserts.json"}


@pytest.fixture
def pronto(tmp_path):
    pj, plano, _ = medir_exemplo(tmp_path)
    medir.gravar(pj, plano)
    escrever_md.escrever(pj)
    return pj


@pytest.fixture
def aprovado(pronto):
    aprovacao.aprovar(pronto, OK, agora=AGORA)
    return pronto


def test_aprovacao_vigente_passa(aprovado):
    r = G.rodar(aprovado)
    assert r.ok, r.motivo
    assert r.detalhes["estado"] == "PASS"
    assert r.detalhes["aprovado_em"] == AGORA
    assert [a["arquivo"] for a in r.detalhes["arquivos"]] == list(ARQUIVOS.values())
    assert all(a["vigente"] for a in r.detalhes["arquivos"])


def test_sem_aprovacao_reprova_e_diz_como_aprovar(pronto):
    r = G.rodar(pronto)
    assert not r.ok and r.detalhes["estado"] == "REPROVA"
    assert "sem aprovação" in r.motivo and "vam aprovar" in r.motivo


@pytest.mark.parametrize("nome", list(ARQUIVOS))
def test_mudar_um_byte_de_qualquer_dos_quatro_reprova_com_aprovacao_vencida(aprovado, nome):
    alvo = aprovado.raiz / ARQUIVOS[nome]
    dados = bytearray(alvo.read_bytes())
    dados[-1] = dados[-1] ^ 1
    alvo.write_bytes(bytes(dados))
    r = G.rodar(aprovado)
    assert not r.ok
    assert "aprovação vencida" in r.motivo
    assert ARQUIVOS[nome] in r.motivo
    assert [a["arquivo"] for a in r.detalhes["arquivos"] if not a["vigente"]] == [ARQUIVOS[nome]]


def test_roteiro_editado_depois_do_ok_e_o_caso_tipico(aprovado):
    aprovado.roteiro.write_text(aprovado.roteiro.read_text(encoding="utf-8").replace("três", "duas"),
                                encoding="utf-8")
    r = G.rodar(aprovado)
    assert not r.ok and "aprovação vencida" in r.motivo and "roteiro.md" in r.motivo
    assert "vam plano" in r.motivo and "vam aprovar" in r.motivo


def test_plano_refeito_depois_do_ok_vence(aprovado):
    """O plano é medido de novo (outro número) e gravado por cima: a aprovação era do plano anterior."""
    plano = json.loads(aprovado.plano_json.read_text(encoding="utf-8"))
    plano["hook"]["linha"] = "4 horas por dia"
    medir.gravar(aprovado, plano)
    r = G.rodar(aprovado)
    assert not r.ok and "plano/plano.json" in r.motivo


def test_aprovacao_forjada_com_emissor_errado_reprova(aprovado):
    dados = json.loads(aprovado.aprovacao.read_text(encoding="utf-8"))
    dados["emissor"] = "montador"
    aprovado.aprovacao.write_text(json.dumps(dados), encoding="utf-8")
    r = G.rodar(aprovado)
    assert not r.ok and "emissor" in r.motivo


def test_plano_invalido_com_aprovacao_refeita_a_mao_reprova(aprovado):
    import hashlib
    plano = json.loads(aprovado.plano_json.read_text(encoding="utf-8"))
    del plano["hook"]
    aprovado.plano_json.write_text(json.dumps(plano), encoding="utf-8")
    dados = json.loads(aprovado.aprovacao.read_text(encoding="utf-8"))
    dados["arquivos"]["plano"]["sha256"] = hashlib.sha256(aprovado.plano_json.read_bytes()).hexdigest()
    aprovado.aprovacao.write_text(json.dumps(dados), encoding="utf-8")
    r = G.rodar(aprovado)
    assert not r.ok and "'hook'" in r.motivo


def test_o_gate_so_le(aprovado):
    antes = {p: p.read_bytes() for p in aprovado.raiz.rglob("*") if p.is_file()}
    G.rodar(aprovado)
    assert {p: p.read_bytes() for p in aprovado.raiz.rglob("*") if p.is_file()} == antes


# --- CLI e códigos de saída ----------------------------------------------------------------------------

def test_cli_passa_com_0_e_registra_ok(aprovado, capsys):
    assert G.main([SLUG, "--estado", str(aprovado.estado)]) == 0
    atual = status.ler(aprovado)["atual"]
    assert (atual["etapa"], atual["estado"]) == ("gate_aprovacao", "ok")
    assert "PASSA" in capsys.readouterr().out


def test_cli_reprova_com_1_registra_falhou_e_nao_toca_na_aprovacao(aprovado, capsys):
    aprovado.roteiro.write_bytes(aprovado.roteiro.read_bytes() + b"\n")
    antes = aprovado.aprovacao.read_bytes()
    assert G.main([SLUG, "--estado", str(aprovado.estado)]) == 1
    atual = status.ler(aprovado)["atual"]
    assert (atual["etapa"], atual["estado"]) == ("gate_aprovacao", "falhou")
    assert "aprovação vencida" in atual["motivo"]
    assert "REPROVA" in capsys.readouterr().out
    assert aprovado.aprovacao.read_bytes() == antes


def test_cli_sem_aprovacao_sai_com_1(pronto):
    assert G.main([SLUG, "--estado", str(pronto.estado)]) == 1


def test_cli_slug_invalido_sai_com_2(tmp_path, capsys):
    assert G.main(["Slug Ruim", "--estado", str(tmp_path)]) == 2
    assert "slug" in capsys.readouterr().err


def test_cli_projeto_inexistente_sai_com_2(tmp_path, capsys):
    assert G.main(["nao-existe", "--estado", str(tmp_path)]) == 2
    assert "nao-existe" in capsys.readouterr().err


def test_rodado_como_script(aprovado):
    import subprocess
    import sys
    r = subprocess.run([sys.executable, str(RAIZ / "scripts" / "gates" / "gate_aprovacao.py"), SLUG,
                        "--estado", str(aprovado.estado)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr + r.stdout


def test_modulo_nao_tem_nome_do_dono_nem_escreve_a_aprovacao():
    fonte = (RAIZ / "scripts" / "gates" / "gate_aprovacao.py").read_text(encoding="utf-8")
    for nome in ("julio", "júlio", "thales", "jheni"):
        assert nome not in fonte.lower()
    assert "—" not in fonte and "–" not in fonte
    assert "aprovacao.json" not in fonte or "write" not in fonte
