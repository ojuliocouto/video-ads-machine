"""A ordem dos gates no `vam montar` (W5.A, seção 4 do plano), com o render SIMULADO.

O montador (`produzir_ad.montar`) roda, nesta ordem:

  antes    gate_aprovacao, gate_fidelidade_roteiro, [gate_fidelidade_doc], gate_fala_roteiro, gate_entrada, gate_look
  motor    preparar (os arquivos do motor e a timeline.json, o relógio único)
  plano    gate_geometria, gate_safezone, gate_lettering, gate_congelamento     (sobre a timeline, sem render)
  motor    footage (a 1x, pela timeline: o overlay mede o fundo claro NELA, no mesmo relógio)
  motor    overlay (HTML)
  durante  gate_tela_vazia, gate_congelamento_build
  motor    render do overlay
  durante  gate_relogio
  motor    composição, aceleração, loudness e mix -> entrega/final_9x16.mp4
  durante  gate_template (o template não mudou do começo ao fim do build)
  prévia   entrega/final_whatsapp.mp4, ANTES do primeiro gate de saída
  depois   gate-ad, medir_ritmo, gate-colisao-texto, gate-contraste-legenda, auditar_ad, gate_hook_visual,
           gate_camera, gate_cor, gate_mix, gate_sfx, gate_insert, gate_lettering_depois, gate_safezone_depois,
           gate_geometria_depois, gate_texto_atras (em paralelo, no máximo 4)
  laudo    entrega/laudo.json, no contrato

Antes e durante, o primeiro gate que reprova (saída 1) ou morre (saída 2) INTERROMPE: nada depois dele roda, e o
motivo vai para o status.json. Depois do render todos rodam (o laudo precisa de todos) e qualquer reprovação vira
veredito REPROVA. O montador nunca escreve nota.json nem aprovacao.json.
"""
import json
import threading
from pathlib import Path

import pytest

import produzir_ad as PA
from contratos.validar import validar
from projeto import novo, pastas, status

ANTES = ["gate_aprovacao", "gate_fidelidade_roteiro", "gate_fala_roteiro", "gate_entrada", "gate_look"]
PLANO = ["gate_geometria", "gate_safezone", "gate_lettering", "gate_congelamento"]
DEPOIS = ["gate-ad", "medir_ritmo", "gate-colisao-texto", "gate-contraste-legenda", "auditar_ad", "gate_hook_visual",
          "gate_camera", "gate_cor", "gate_mix", "gate_sfx", "gate_insert", "gate_lettering_depois",
          "gate_safezone_depois", "gate_geometria_depois", "gate_texto_atras"]
ESPERADO = (ANTES + ["motor:preparar"] + PLANO + ["motor:footage", "motor:overlay", "gate_tela_vazia",
            "gate_congelamento_build", "motor:render_overlay", "gate_relogio", "motor:compor", "gate_template",
            "previa"])


class Registro(object):
    def __init__(self):
        self.ordem = []
        self.trava = threading.Lock()

    def anotar(self, nome):
        with self.trava:
            self.ordem.append(nome)


class MotorSimulado(object):
    """O render simulado: cada passo anota e escreve um arquivo de mentira onde o de verdade escreveria."""

    def __init__(self, pj, reg, falhar_em=None):
        self.pj, self.reg, self.falhar_em = pj, reg, falhar_em
        self.final = pj.final_9x16

    def _passo(self, nome):
        self.reg.anotar("motor:" + nome)
        if self.falhar_em == nome:
            raise PA.ErroDoMotor("o ffmpeg morreu no passo %s" % nome)

    def preparar(self):
        self._passo("preparar")

    def gerar_overlay(self):
        self._passo("overlay")

    def renderizar_overlay(self):
        self._passo("render_overlay")

    def montar_footage(self):
        self._passo("footage")

    def compor(self):
        self._passo("compor")
        self.final.parent.mkdir(parents=True, exist_ok=True)
        self.final.write_bytes(b"final simulado")
        return self.final


def _gate(reg, nome, resultado="PASS", saida=0, ver=None):
    def rodar(ctx):
        reg.anotar(nome)
        if ver:
            ver(ctx)
        g = {"nome": nome, "etapa": PA.ETAPA_DO_GATE[nome], "resultado": resultado, "saida": saida,
             "medido": {"simulado": True}}
        if resultado != "PASS":
            g["motivo"] = "%s simulado: %s" % (nome, resultado.lower())
        return g
    return rodar


def _gates(reg, **troca):
    gs = {n: _gate(reg, n) for n in PA.NOMES_DOS_GATES}
    gs.update(troca)
    return gs


def _previa(reg):
    def gerar(final, destino):
        reg.anotar("previa")
        Path(destino).parent.mkdir(parents=True, exist_ok=True)
        Path(destino).write_bytes(b"previa de " + Path(final).read_bytes())
        return Path(destino)
    return gerar


def _medir(final):
    return {"duracao_s": 20.0, "largura": 1080, "altura": 1920, "fps": 30.0, "lufs": -14.1,
            "true_peak_dbtp": -1.7, "taxa_amostragem": 48000,
            "cor": {"primarias": "bt709", "transferencia": "bt709", "matriz": "bt709"}}


@pytest.fixture
def pj(estado_vazio):
    novo.criar("ordem", "avatar", look="estudio", sem_trilha="teste da ordem dos gates", estado=estado_vazio)
    return pastas.projeto("ordem", estado_vazio)


def _montar(pj, reg, gates=None, motor=None, **kw):
    return PA.montar(pj, motor=motor or MotorSimulado(pj, reg), gates=gates or _gates(reg), previa=_previa(reg),
                     medir=_medir, saida=lambda *a, **k: None, **kw)


# --- a ordem -------------------------------------------------------------------------------------------

def test_ordem_exata_dos_gates_com_render_simulado(pj):
    reg = Registro()
    assert _montar(pj, reg) == 0
    n = len(ESPERADO)
    assert reg.ordem[:n] == ESPERADO
    assert sorted(reg.ordem[n:]) == sorted(DEPOIS)                    # em paralelo: todos, uma vez cada
    laudo = json.loads(pj.laudo.read_text(encoding="utf-8"))
    assert [g["nome"] for g in laudo["gates"]] == ANTES + PLANO + ["gate_tela_vazia", "gate_congelamento_build",
                                                                   "gate_relogio", "gate_template"] + DEPOIS


def test_a_ordem_declarada_e_a_do_plano():
    assert list(PA.ordem({"modo": "avatar"})) == (ANTES + PLANO + ["gate_tela_vazia", "gate_congelamento_build",
                                                                  "gate_relogio", "gate_template"] + DEPOIS)
    com_doc = list(PA.ordem({"modo": "avatar", "origem": {"tipo": "doc_google", "doc_id": "x" * 30}}))
    assert com_doc[:3] == ["gate_aprovacao", "gate_fidelidade_roteiro", "gate_fidelidade_doc"]


def test_os_gates_de_saida_rodam_no_maximo_4_ao_mesmo_tempo(pj):
    reg, vivos, pico, trava = Registro(), [0], [0], threading.Lock()
    import time

    def lento(nome):
        base = _gate(reg, nome)

        def rodar(ctx):
            with trava:
                vivos[0] += 1
                pico[0] = max(pico[0], vivos[0])
            time.sleep(0.05)
            with trava:
                vivos[0] -= 1
            return base(ctx)
        return rodar
    assert _montar(pj, reg, gates=_gates(reg, **{n: lento(n) for n in DEPOIS})) == 0
    assert 1 < pico[0] <= 4


# --- interrompe e grava o motivo ------------------------------------------------------------------------

@pytest.mark.parametrize("quem", ANTES + PLANO)
def test_gate_com_saida_1_antes_do_render_interrompe_e_grava_o_motivo(pj, quem):
    reg = Registro()
    gs = _gates(reg, **{quem: _gate(reg, quem, "REPROVA", 1)})
    assert _montar(pj, reg, gates=gs) == 1
    assert reg.ordem[-1] == quem                                       # nada depois dele rodou
    assert "motor:compor" not in reg.ordem and "previa" not in reg.ordem
    atual = status.ler(pj)["atual"]
    assert atual["etapa"] == "montar" and atual["estado"] == "falhou"
    assert quem in atual["motivo"] and "simulado" in atual["motivo"]
    assert not pj.final_9x16.exists()


def test_gate_que_morre_tambem_interrompe_com_saida_2(pj):
    reg = Registro()
    gs = _gates(reg, gate_entrada=_gate(reg, "gate_entrada", "ERRO", 2))
    assert _montar(pj, reg, gates=gs) == 2
    assert reg.ordem[-1] == "gate_entrada"
    atual = status.ler(pj)["atual"]
    assert atual["estado"] == "bloqueado" and "gate_entrada" in atual["motivo"]


@pytest.mark.parametrize("quem", ["gate_tela_vazia", "gate_congelamento_build", "gate_relogio", "gate_template"])
def test_gate_durante_o_build_interrompe_antes_da_previa(pj, quem):
    reg = Registro()
    gs = _gates(reg, **{quem: _gate(reg, quem, "REPROVA", 1)})
    assert _montar(pj, reg, gates=gs) == 1
    assert reg.ordem[-1] == quem and "previa" not in reg.ordem
    assert not any(n in reg.ordem for n in DEPOIS)
    assert quem in status.ler(pj)["atual"]["motivo"]


def test_motor_que_morre_para_o_build_com_saida_2_e_motivo(pj):
    reg = Registro()
    assert _montar(pj, reg, motor=MotorSimulado(pj, reg, falhar_em="footage")) == 2
    assert reg.ordem[-1] == "motor:footage"
    atual = status.ler(pj)["atual"]
    assert atual["estado"] == "bloqueado" and "footage" in atual["motivo"] and "ffmpeg" in atual["motivo"]


def test_excecao_dentro_de_um_gate_vira_erro_nunca_aprovacao(pj):
    reg = Registro()

    def explode(ctx):
        reg.anotar("gate_look")
        raise RuntimeError("detector caiu")
    assert _montar(pj, reg, gates=_gates(reg, gate_look=explode)) == 2
    assert "detector caiu" in status.ler(pj)["atual"]["motivo"]


# --- prévia e gates de saída ----------------------------------------------------------------------------

def test_a_previa_existe_antes_do_primeiro_gate_de_saida(pj):
    reg = Registro()
    vistos = []

    def ver(ctx):
        vistos.append(pj.final_whatsapp.is_file())
    gs = _gates(reg, **{n: _gate(reg, n, ver=ver) for n in DEPOIS})
    assert _montar(pj, reg, gates=gs) == 0
    assert vistos and all(vistos)


def test_gate_de_saida_que_reprova_nao_para_os_outros_e_o_laudo_sai_reprovado(pj):
    reg = Registro()
    gs = _gates(reg, gate_cor=_gate(reg, "gate_cor", "REPROVA", 1))
    assert _montar(pj, reg, gates=gs) == 1
    assert sorted(n for n in reg.ordem if n in DEPOIS) == sorted(DEPOIS)
    laudo = json.loads(pj.laudo.read_text(encoding="utf-8"))
    assert validar("laudo", laudo) == []
    assert laudo["veredito"] == "REPROVA" and laudo["capacidades"]["C5"]["status"] == "REPROVA"
    atual = status.ler(pj)["atual"]
    assert atual["estado"] == "falhou" and "gate_cor" in atual["motivo"]


def test_laudo_todo_pass_valida_no_contrato_e_amarra_o_sha_do_final(pj):
    reg = Registro()
    assert _montar(pj, reg) == 0
    laudo = json.loads(pj.laudo.read_text(encoding="utf-8"))
    assert validar("laudo", laudo) == []
    assert laudo["veredito"] == "PASS"
    import hashlib
    assert laudo["sha256"] == hashlib.sha256(pj.final_9x16.read_bytes()).hexdigest()
    assert laudo["arquivo"] == "entrega/final_9x16.mp4"
    assert laudo["previa"]["arquivo"] == "entrega/final_whatsapp.mp4"
    assert set(laudo["capacidades"]) == {"C%d" % i for i in range(1, 15)}
    assert laudo["tempos"]["build_s"] >= 0
    assert status.ler(pj)["atual"]["etapa"] == "montar" and status.ler(pj)["atual"]["estado"] == "ok"


def test_gate_pulado_com_motivo_nao_reprova_o_laudo(pj):
    reg = Registro()
    gs = _gates(reg, gate_texto_atras=_gate(reg, "gate_texto_atras", "PULADO", 0))
    assert _montar(pj, reg, gates=gs) == 0
    laudo = json.loads(pj.laudo.read_text(encoding="utf-8"))
    assert laudo["veredito"] == "PASS" and laudo["capacidades"]["C13"]["status"] == "DESLIGADA"


def test_o_montador_nao_escreve_nota_nem_aprovacao(pj):
    pj.aprovacao.parent.mkdir(parents=True, exist_ok=True)
    pj.aprovacao.write_text('{"marca": "do aluno"}\n', encoding="utf-8")
    reg = Registro()
    assert _montar(pj, reg) == 0
    assert pj.aprovacao.read_text(encoding="utf-8") == '{"marca": "do aluno"}\n'
    assert not pj.nota.exists()


def test_uma_entrega_anterior_e_sua_nota_saem_de_cena_quando_o_montar_recomeca(pj):
    """Nota e laudo velhos não podem amarrar um final novo: o montar tira o final velho antes de começar."""
    pj.final_9x16.parent.mkdir(parents=True, exist_ok=True)
    pj.final_9x16.write_bytes(b"final velho")
    reg = Registro()
    gs = _gates(reg, gate_aprovacao=_gate(reg, "gate_aprovacao", "REPROVA", 1))
    assert _montar(pj, reg, gates=gs) == 1
    assert not pj.final_9x16.exists() and not pj.laudo.exists()


# --- a geometria que pede supressão de legenda ----------------------------------------------------------

def test_geometria_que_pede_supressao_aplica_e_confere_de_novo(pj, monkeypatch):
    reg = Registro()
    rodadas = []

    def geometria(ctx):
        reg.anotar("gate_geometria")
        rodadas.append(1)
        if len(rodadas) == 1:
            return {"nome": "gate_geometria", "etapa": "antes", "resultado": "REPROVA", "saida": 1,
                    "motivo": "faixa livre menor que a legenda", "medido": {"acao": "suprimir_legenda",
                                                                            "suprimir": [{"indice": 0}]}}
        return {"nome": "gate_geometria", "etapa": "antes", "resultado": "PASS", "saida": 0, "medido": {}}
    aplicadas = []
    monkeypatch.setattr(PA, "_aplicar_supressao", lambda ctx, g: aplicadas.append(g) or True)
    assert _montar(pj, reg, gates=_gates(reg, gate_geometria=geometria)) == 0
    assert len(rodadas) == 2 and len(aplicadas) == 1
