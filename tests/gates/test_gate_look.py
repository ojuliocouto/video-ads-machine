"""W3.C: gate_look. O look do HeyGen tem que existir, estar aprovado (com a conferência vigente)
e ser vertical. Sem mídia: o look é um JSON do aluno e a conferência é o JSON que o avatar gera."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from gates import gate_look
from projeto import looks, modelo, pastas, status

RAIZ = Path(__file__).resolve().parents[2]
SLUG = "anuncio"
AVATAR_ID = "a1b2c3d4e5f6a7b8c9d0"
REL_CONF = "projetos/%s/avatar/conferencia.json" % SLUG


def conferencia(largura=1080, altura=1920, resultado="aprovada"):
    return {"versao": 1, "gerado_em": "2026-10-09T10:00:00-03:00", "aspecto": "9:16",
            "resultado": resultado,
            "avatar": {"arquivo": "avatar/avatar.mp4", "sha256": "0" * 64, "largura": largura,
                       "altura": altura, "duracao_s": 55.0},
            "reprovacoes": [] if resultado == "aprovada" else ["fração útil abaixo do piso"]}


def montar(tmp_path, modo="avatar", look="meu-look", cadastrar=True, aprovar=True, conf=None):
    estado = tmp_path / "_local"
    pj = pastas.projeto(SLUG, estado).criar()
    projeto = modelo.minimo(SLUG, modo, look=look if modo == "avatar" else None,
                            sem_trilha="sem trilha no teste")
    modelo.escrever(pj.projeto_json, projeto)
    pj.avatar_conferencia.write_text(json.dumps(conf or conferencia()), encoding="utf-8")
    if cadastrar:
        looks.adicionar(look, AVATAR_ID, "medio", estado=estado)
        if aprovar:
            looks.aprovar(look, REL_CONF, estado=estado)
    return estado, pj


def test_look_aprovado_e_vertical_passa(tmp_path):
    estado, pj = montar(tmp_path)
    r = gate_look.rodar(pj)
    assert r.ok, r.motivo
    assert r.detalhes["estado"] == "PASS"
    assert r.detalhes["look"] == "meu-look"


def test_look_ausente_reprova(tmp_path):
    estado, pj = montar(tmp_path, cadastrar=False)
    r = gate_look.rodar(pj)
    assert not r.ok
    assert "meu-look" in r.motivo and "não existe" in r.motivo


def test_look_nao_aprovado_reprova(tmp_path):
    estado, pj = montar(tmp_path, aprovar=False)
    r = gate_look.rodar(pj)
    assert not r.ok
    assert "não está aprovado" in r.motivo


def test_aprovacao_vencida_reprova(tmp_path):
    """Conferência regravada depois da aprovação: o sha não bate mais."""
    estado, pj = montar(tmp_path)
    pj.avatar_conferencia.write_text(json.dumps(conferencia(altura=1919)), encoding="utf-8")
    r = gate_look.rodar(pj)
    assert not r.ok
    assert "mudou depois da aprovação" in r.motivo


def test_look_horizontal_no_looks_json_reprova(tmp_path):
    """looks.json escrito à mão com orientação horizontal: o contrato recusa e o gate diz por quê."""
    estado, pj = montar(tmp_path, cadastrar=False)
    (estado / "looks.json").write_text(json.dumps({"versao": 1, "looks": {"meu-look": {
        "avatar_id": AVATAR_ID, "orientacao": "horizontal", "plano": "medio", "aprovado": False}}}),
        encoding="utf-8")
    r = gate_look.rodar(pj)
    assert not r.ok
    assert "horizontal" in r.motivo


def test_look_cadastrado_vertical_mas_avatar_gerado_horizontal_reprova(tmp_path):
    """O que vale é o avatar medido: 1920x1080 na conferência é horizontal, mesmo aprovado no papel."""
    estado, pj = montar(tmp_path, conf=conferencia(largura=1920, altura=1080))
    r = gate_look.rodar(pj)
    assert not r.ok
    assert "horizontal" in r.motivo
    assert "1920x1080" in r.motivo


def test_conferencia_reprovada_reprova(tmp_path):
    estado, pj = montar(tmp_path, conf=conferencia(resultado="reprovada"))
    r = gate_look.rodar(pj)
    assert not r.ok
    assert "conferência" in r.motivo and "reprovada" in r.motivo


def test_modo_sem_avatar_nao_usa_look_e_e_pulado(tmp_path):
    estado, pj = montar(tmp_path, modo="gravado", cadastrar=False)
    r = gate_look.rodar(pj)
    assert r.ok
    assert r.detalhes["estado"] == "PULADO"
    assert "gravado" in r.motivo


def test_sem_projeto_json_e_insumo_invalido(tmp_path):
    pj = pastas.projeto(SLUG, tmp_path / "_local").criar()
    with pytest.raises(gate_look.InsumoInvalido):
        gate_look.rodar(pj)


def test_looks_json_quebrado_e_insumo_invalido(tmp_path):
    estado, pj = montar(tmp_path, cadastrar=False)
    (estado / "looks.json").write_text("{isto não é json", encoding="utf-8")
    with pytest.raises(gate_look.InsumoInvalido):
        gate_look.rodar(pj)


# --- CLI: exit 0 (passa) / 1 (reprova) / 2 (insumo inválido) e registro no status.json ---------

def test_cli_passa_exit_0_e_registra_ok(tmp_path, capsys):
    estado, pj = montar(tmp_path)
    assert gate_look.main([SLUG, "--estado", str(estado)]) == 0
    atual = status.ler(pj)["atual"]
    assert atual["etapa"] == "gate_look" and atual["estado"] == "ok"
    assert atual["detalhes"]["look"] == "meu-look"


def test_cli_reprova_exit_1_e_registra_falhou_com_motivo(tmp_path, capsys):
    estado, pj = montar(tmp_path, aprovar=False)
    assert gate_look.main([SLUG, "--estado", str(estado)]) == 1
    atual = status.ler(pj)["atual"]
    assert atual["etapa"] == "gate_look" and atual["estado"] == "falhou"
    assert "não está aprovado" in atual["motivo"]
    assert "REPROVA" in capsys.readouterr().out


def test_cli_insumo_invalido_exit_2_e_registra_bloqueado(tmp_path, capsys):
    pj = pastas.projeto(SLUG, tmp_path / "_local").criar()
    assert gate_look.main([SLUG, "--estado", str(tmp_path / "_local")]) == 2
    atual = status.ler(pj)["atual"]
    assert atual["etapa"] == "gate_look" and atual["estado"] == "bloqueado"


def test_cli_projeto_que_nao_existe_exit_2_sem_criar_pasta(tmp_path, capsys):
    estado = tmp_path / "_local"
    estado.mkdir()
    assert gate_look.main(["nao-existe", "--estado", str(estado)]) == 2
    assert not (estado / "projetos").exists()


def test_roda_como_script_e_sai_2_sem_projeto(tmp_path):
    estado = tmp_path / "_local"
    estado.mkdir()
    p = subprocess.run([sys.executable, str(RAIZ / "scripts" / "gates" / "gate_look.py"), "nao-existe",
                        "--estado", str(estado)], capture_output=True, text=True)
    assert p.returncode == 2, p.stdout + p.stderr


def test_resultado_tem_os_campos_que_a_w5a_espera():
    assert gate_look.Resultado._fields == ("ok", "motivo", "detalhes")
