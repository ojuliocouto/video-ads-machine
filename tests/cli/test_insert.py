"""W5.B: `vam insert <slug> <chave> --template whatsapp --dados dados.json --dur 4`.

Escreve inserts/<chave>.mp4 no projeto do aluno. Saídas: 0 escreveu · 1 o render falhou (sem motor,
motor caiu) · 2 pedido inválido (slug, chave, template, dados, duração, proporção, conflito de
arquivo). O motor de render é sempre falso aqui; o render de verdade é do teste `lento`.
"""
import argparse
import json
from pathlib import Path

import pytest

from cinema import insert_ui
from cli import insert
from projeto import pastas


class MotorFalso:
    def __init__(self, falha=None):
        self.pedidos = []
        self.falha = falha

    def __call__(self, pedido):
        self.pedidos.append(pedido)
        if self.falha:
            raise self.falha
        pedido.saida.write_bytes(b"mp4-falso")


@pytest.fixture
def motor(monkeypatch):
    m = MotorFalso()
    monkeypatch.setattr(insert_ui, "motor_padrao", lambda raiz=None: m)
    return m


@pytest.fixture
def projeto(estado_vazio):
    pj = pastas.projeto("meu-ad", estado_vazio).criar()
    return pj


def _args(*argv):
    p = argparse.ArgumentParser(prog="vam")
    sub = p.add_subparsers(dest="comando")
    insert.registrar(sub)
    return p.parse_args(["insert", *argv])


def _dados(tmp_path, template="whatsapp", dados=None, nome="dados.json"):
    arq = tmp_path / nome
    arq.write_text(json.dumps(insert_ui.exemplo(template) if dados is None else dados, ensure_ascii=False),
                   encoding="utf-8")
    return arq


def _rodar(estado, *argv):
    return insert.executar(_args("--estado", str(estado), *argv))


# --- registrar -----------------------------------------------------------------------------------

def test_registrar_cria_o_subcomando_insert_e_aponta_para_executar():
    args = _args("meu-ad", "pergunta", "--template", "whatsapp", "--dados", "d.json", "--dur", "4")
    assert args.comando == "insert" and args.func is insert.executar
    assert (args.slug, args.chave, args.template, args.dados, args.dur) == ("meu-ad", "pergunta", "whatsapp",
                                                                          "d.json", 4.0)


def test_padroes_do_subcomando():
    args = _args("meu-ad", "pergunta", "--template", "terminal", "--dados", "d.json")
    assert args.dur == 4.0 and args.proporcao == insert_ui.PROPORCAO_PADRAO and args.fps == insert_ui.FPS_PADRAO


def test_duracao_que_nao_e_numero_e_erro_de_uso_do_argparse():
    with pytest.raises(SystemExit) as e:
        _args("meu-ad", "pergunta", "--template", "terminal", "--dados", "d.json", "--dur", "muito")
    assert e.value.code == 2


# --- escreve no caminho certo ----------------------------------------------------------------------

def test_escreve_em_inserts_chave_mp4_do_projeto_e_sai_0(projeto, estado_vazio, tmp_path, motor, capsys):
    rc = _rodar(estado_vazio, "meu-ad", "pergunta", "--template", "whatsapp", "--dados", str(_dados(tmp_path)),
                "--dur", "4")
    assert rc == 0
    destino = estado_vazio / "projetos" / "meu-ad" / "inserts" / "pergunta.mp4"
    assert destino.read_bytes() == b"mp4-falso"
    assert projeto.insert("pergunta") == destino            # a convenção `insert: <chave>` o acha
    assert projeto.inserts() == {"pergunta": destino}
    assert "pergunta.mp4" in capsys.readouterr().out


def test_o_motor_recebe_o_template_os_dados_a_duracao_e_a_proporcao(projeto, estado_vazio, tmp_path, motor):
    dados = insert_ui.exemplo("kanban")
    dados["titulo"] = "Funil da semana"
    rc = _rodar(estado_vazio, "meu-ad", "funil", "--template", "kanban",
                "--dados", str(_dados(tmp_path, "kanban", dados)), "--dur", "3", "--proporcao", "painel",
                "--fps", "25")
    assert rc == 0
    (p,) = motor.pedidos
    assert p.template == "kanban" and (p.largura, p.altura) == (1080, 1150)
    assert p.fps == 25 and p.quadros == 75
    assert "Funil da semana" in p.html


def test_sem_dur_valem_4_segundos(projeto, estado_vazio, tmp_path, motor):
    assert _rodar(estado_vazio, "meu-ad", "k", "--template", "contador",
                  "--dados", str(_dados(tmp_path, "contador"))) == 0
    assert motor.pedidos[0].quadros == 4 * insert_ui.FPS_PADRAO


def test_os_sete_templates_saem_0(projeto, estado_vazio, tmp_path, motor):
    for nome in insert_ui.templates():
        assert _rodar(estado_vazio, "meu-ad", "i-" + nome, "--template", nome,
                      "--dados", str(_dados(tmp_path, nome))) == 0, nome
    assert sorted(projeto.inserts()) == sorted("i-" + n for n in insert_ui.templates())


def test_refazer_o_mesmo_insert_troca_o_arquivo(projeto, estado_vazio, tmp_path, motor):
    dados = str(_dados(tmp_path, "contador"))
    destino = projeto.inserts_dir / "k.mp4"
    destino.write_bytes(b"velho")
    assert _rodar(estado_vazio, "meu-ad", "k", "--template", "contador", "--dados", dados) == 0
    assert destino.read_bytes() == b"mp4-falso"
    assert sorted(p.name for p in projeto.inserts_dir.iterdir()) == ["k.mp4"]


def test_nao_cria_projeto_nem_mexe_em_outros_arquivos_do_projeto(projeto, estado_vazio, tmp_path, motor):
    antes = sorted(p.relative_to(projeto.raiz).as_posix() for p in projeto.raiz.rglob("*"))
    _rodar(estado_vazio, "meu-ad", "k", "--template", "contador", "--dados", str(_dados(tmp_path, "contador")))
    depois = sorted(p.relative_to(projeto.raiz).as_posix() for p in projeto.raiz.rglob("*"))
    assert depois == sorted(antes + ["inserts/k.mp4"])


def test_a_pasta_inserts_e_criada_se_o_projeto_nao_a_tem(estado_vazio, tmp_path, motor):
    pj = pastas.projeto("sem-pasta", estado_vazio)
    pj.raiz.mkdir(parents=True)
    assert _rodar(estado_vazio, "sem-pasta", "k", "--template", "contador",
                  "--dados", str(_dados(tmp_path, "contador"))) == 0
    assert (pj.inserts_dir / "k.mp4").is_file()


# --- exemplo e lista de templates --------------------------------------------------------------------

def test_exemplo_imprime_o_json_valido_do_template_e_sai_0_sem_projeto(estado_vazio, capsys, motor):
    for nome in insert_ui.templates():
        assert insert.executar(_args("--estado", str(estado_vazio), "--exemplo", nome)) == 0
        saida = capsys.readouterr().out
        assert json.loads(saida) == insert_ui.exemplo(nome)
    assert motor.pedidos == []


def test_exemplo_de_template_que_nao_existe_sai_2(estado_vazio, capsys):
    assert insert.executar(_args("--estado", str(estado_vazio), "--exemplo", "planilha")) == 2
    assert "whatsapp" in capsys.readouterr().err


def test_templates_lista_os_sete(estado_vazio, capsys):
    assert insert.executar(_args("--estado", str(estado_vazio), "--templates")) == 0
    saida = capsys.readouterr().out
    for nome in insert_ui.templates():
        assert nome in saida


# --- exit 2: pedido inválido ---------------------------------------------------------------------------

@pytest.mark.parametrize("argv", [
    ["meu-ad"],                                                           # falta a chave
    ["meu-ad", "k"],                                                      # falta o template
    ["meu-ad", "k", "--template", "contador"],                            # faltam os dados
    ["--template", "contador", "--dados", "d.json"],                      # faltam slug e chave
])
def test_pedido_incompleto_sai_2_e_diz_o_que_falta(argv, estado_vazio, projeto, motor, capsys):
    assert _rodar(estado_vazio, *argv) == 2
    assert capsys.readouterr().err.strip()
    assert motor.pedidos == []


@pytest.mark.parametrize("slug", ["Meu Ad", "../fora", "", "MAIUSCULA"])
def test_slug_invalido_sai_2(slug, estado_vazio, tmp_path, motor, capsys):
    assert _rodar(estado_vazio, slug, "k", "--template", "contador",
                  "--dados", str(_dados(tmp_path, "contador"))) == 2
    assert "slug" in capsys.readouterr().err
    assert motor.pedidos == []


def test_projeto_que_nao_existe_sai_2_e_nao_o_cria(estado_vazio, tmp_path, motor, capsys):
    assert _rodar(estado_vazio, "nao-existe", "k", "--template", "contador",
                  "--dados", str(_dados(tmp_path, "contador"))) == 2
    assert "nao-existe" in capsys.readouterr().err
    assert not (estado_vazio / "projetos" / "nao-existe").exists()


@pytest.mark.parametrize("chave", ["Pergunta", "com espaço", "a/b", "../x", "-comeca"])
def test_chave_invalida_sai_2(chave, projeto, estado_vazio, tmp_path, motor, capsys):
    assert _rodar(estado_vazio, "meu-ad", chave, "--template", "contador",
                  "--dados", str(_dados(tmp_path, "contador"))) == 2
    assert "chave" in capsys.readouterr().err
    assert motor.pedidos == []


def test_template_desconhecido_sai_2_e_lista_os_que_existem(projeto, estado_vazio, tmp_path, motor, capsys):
    assert _rodar(estado_vazio, "meu-ad", "k", "--template", "planilha",
                  "--dados", str(_dados(tmp_path, "contador"))) == 2
    err = capsys.readouterr().err
    for nome in insert_ui.templates():
        assert nome in err


def test_arquivo_de_dados_que_nao_existe_sai_2(projeto, estado_vazio, tmp_path, motor, capsys):
    assert _rodar(estado_vazio, "meu-ad", "k", "--template", "contador",
                  "--dados", str(tmp_path / "nao-tem.json")) == 2
    assert "nao-tem.json" in capsys.readouterr().err


def test_json_quebrado_sai_2(projeto, estado_vazio, tmp_path, motor, capsys):
    arq = tmp_path / "ruim.json"
    arq.write_text('{"valor": 6000,', encoding="utf-8")
    assert _rodar(estado_vazio, "meu-ad", "k", "--template", "contador", "--dados", str(arq)) == 2
    assert "ruim.json" in capsys.readouterr().err
    assert motor.pedidos == []


def test_json_com_chave_repetida_sai_2(projeto, estado_vazio, tmp_path, motor, capsys):
    arq = tmp_path / "dup.json"
    arq.write_text('{"valor": 1, "valor": 2, "legenda": "x"}', encoding="utf-8")
    assert _rodar(estado_vazio, "meu-ad", "k", "--template", "contador", "--dados", str(arq)) == 2
    assert "valor" in capsys.readouterr().err


def test_dado_invalido_sai_2_e_a_mensagem_nomeia_o_campo(projeto, estado_vazio, tmp_path, motor, capsys):
    dados = insert_ui.exemplo("dashboard")
    dados["kpis"][1]["valor"] = "muitos"
    assert _rodar(estado_vazio, "meu-ad", "k", "--template", "dashboard",
                  "--dados", str(_dados(tmp_path, "dashboard", dados))) == 2
    err = capsys.readouterr().err
    assert "kpis" in err and "valor" in err
    assert motor.pedidos == []
    assert not (projeto.inserts_dir / "k.mp4").exists()


@pytest.mark.parametrize("dur", ["0", "0.2", "-3", "99", "nan", "inf"])
def test_duracao_fora_da_faixa_sai_2(dur, projeto, estado_vazio, tmp_path, motor, capsys):
    assert _rodar(estado_vazio, "meu-ad", "k", "--template", "contador",
                  "--dados", str(_dados(tmp_path, "contador")), "--dur", dur) == 2
    assert capsys.readouterr().err.strip()
    assert motor.pedidos == []


def test_proporcao_invalida_sai_2(projeto, estado_vazio, tmp_path, motor, capsys):
    assert _rodar(estado_vazio, "meu-ad", "k", "--template", "contador",
                  "--dados", str(_dados(tmp_path, "contador")), "--proporcao", "banana") == 2
    assert "banana" in capsys.readouterr().err


def test_fps_fora_da_faixa_sai_2(projeto, estado_vazio, tmp_path, motor):
    assert _rodar(estado_vazio, "meu-ad", "k", "--template", "contador",
                  "--dados", str(_dados(tmp_path, "contador")), "--fps", "7") == 2


def test_outro_arquivo_com_a_mesma_chave_sai_2_e_nao_o_apaga(projeto, estado_vazio, tmp_path, motor, capsys):
    do_aluno = projeto.inserts_dir / "pergunta.mov"
    do_aluno.write_bytes(b"filmagem do aluno")
    assert _rodar(estado_vazio, "meu-ad", "pergunta", "--template", "contador",
                  "--dados", str(_dados(tmp_path, "contador"))) == 2
    assert "pergunta.mov" in capsys.readouterr().err
    assert do_aluno.read_bytes() == b"filmagem do aluno"
    assert motor.pedidos == []


# --- exit 1: o render falhou ------------------------------------------------------------------------

def test_motor_que_cai_sai_1_com_a_mensagem_e_sem_arquivo(projeto, estado_vazio, tmp_path, monkeypatch, capsys):
    falso = MotorFalso(falha=insert_ui.RenderFalhou("o Chromium fechou no quadro 12"))
    monkeypatch.setattr(insert_ui, "motor_padrao", lambda raiz=None: falso)
    assert _rodar(estado_vazio, "meu-ad", "k", "--template", "contador",
                  "--dados", str(_dados(tmp_path, "contador"))) == 1
    assert "quadro 12" in capsys.readouterr().err
    assert list(projeto.inserts_dir.iterdir()) == []


def test_render_que_falha_nao_estraga_o_insert_que_ja_existia(projeto, estado_vazio, tmp_path, monkeypatch):
    destino = projeto.inserts_dir / "k.mp4"
    destino.write_bytes(b"bom")
    falso = MotorFalso(falha=insert_ui.RenderFalhou("caiu"))
    monkeypatch.setattr(insert_ui, "motor_padrao", lambda raiz=None: falso)
    assert _rodar(estado_vazio, "meu-ad", "k", "--template", "contador",
                  "--dados", str(_dados(tmp_path, "contador"))) == 1
    assert destino.read_bytes() == b"bom"
    assert sorted(p.name for p in projeto.inserts_dir.iterdir()) == ["k.mp4"]


def test_sem_motor_sai_1_com_uma_linha_e_o_comando(projeto, estado_vazio, tmp_path, monkeypatch, capsys):
    def sem_motor(raiz=None):
        raise insert_ui.SemMotorDeRender("Sem motor de render para o insert: rode `bash scripts/setup.sh`.")

    monkeypatch.setattr(insert_ui, "motor_padrao", sem_motor)
    assert _rodar(estado_vazio, "meu-ad", "k", "--template", "contador",
                  "--dados", str(_dados(tmp_path, "contador"))) == 1
    err = capsys.readouterr().err.strip()
    assert "\n" not in err and "bash scripts/setup.sh" in err
    assert list(projeto.inserts_dir.iterdir()) == []


# --- o módulo e a descoberta pelo vam.py --------------------------------------------------------------

def test_o_modulo_nao_faz_nada_ao_ser_importado_e_expoe_registrar():
    assert callable(insert.registrar) and callable(insert.executar)


def test_sem_estado_explicito_usa_o_estado_padrao(estado_vazio, tmp_path, monkeypatch, motor):
    pastas.projeto("padrao", estado_vazio).criar()
    monkeypatch.setattr(pastas, "estado_padrao", lambda: Path(estado_vazio))
    p = argparse.ArgumentParser(prog="vam")
    insert.registrar(p.add_subparsers(dest="comando"))
    args = p.parse_args(["insert", "padrao", "k", "--template", "contador",
                         "--dados", str(_dados(tmp_path, "contador"))])
    assert insert.executar(args) == 0
    assert (estado_vazio / "projetos" / "padrao" / "inserts" / "k.mp4").is_file()
