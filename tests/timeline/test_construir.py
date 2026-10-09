"""timeline.construir (W3.A): o relógio único. Footage e overlay leem a MESMA timeline.json.

Defeito 20 do plano: os dois motores alinhavam a fala cada um por si e derivavam spans por caminhos
diferentes. A deriva chegou a 1,07 s no fim de um anúncio (footage 120,90 s, overlay 121,97 s) e virou a
origem dos remendos de "banda de guarda". O relógio que vale é o da footage, como o próprio código declarava.

O que este arquivo prova:
  - a timeline valida no contrato (`contratos/timeline.schema.json`), cita o sha do alinhamento, tem blocos
    contíguos e traz `camera` (onde moram os punches da W4.A) vazia por padrão;
  - os spans e o plano de ritmo da timeline são EXATAMENTE os que a footage calcularia sozinha;
  - footage e overlay, com a timeline, não transcrevem nem alinham: leem o plano, os spans e as janelas de
    split dela, e os dois saem com o mesmo plano e as mesmas janelas;
  - uma transcrição por avatar no caminho inteiro (espião no audio.transcrever e no subprocess);
  - sem timeline, os dois motores seguem o caminho antigo e avisam;
  - no fixture real (`midia_real`, `lento`), a duração do overlay e a da footage diferem em até 1 quadro.
"""
import copy
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

import ritmo
from audio import transcrever as T
from contratos.validar import validar
from footage import blocos as BL
from footage import cadeia as CA
from footage import grade_final as GF
from footage import montar as MO
from footage import render_segmentos as RS
from overlay import brolls as OB
from overlay import fundo_claro as OF
from overlay import gerar as OG
from overlay import layout_texto as OL
from overlay import transcricao as OT
from timeline import alinhar as AL
from timeline import construir as TC

RAIZ = Path(__file__).resolve().parents[2]

AD = "ad77v2"
LOOK = "neutro"
LEVA = """[inserção de vídeo: demo a] Minha skill de criação de páginas transformou meu Claude em um web designer profissional.
[apresentador de frente para a câmera] Agora eu construo minhas páginas em minutos, sem precisar pagar nada mais por isso.
[apresentador + lettering | LEAD: sabe qual é | KEY: O MELHOR] Sabe qual é o melhor?
[inserção de vídeo: demo b] Se eu usar um conector que é disponibilizado gratuitamente dentro do Claude,
[apresentador + lettering + logo | LEAD: eu consigo não só | KEY: PRODUZIR AS PÁGINAS] eu consigo não só produzir as páginas
"""
CFG = {
    "ad": AD, "look": LOOK, "format": "9x16", "speed": 1.0,
    "hook": {"eyebrow": "MEU CLAUDE", "l1": "virou um web designer", "accent": "PROFISSIONAL"},
    "cta_label": "saiba mais",
    "kw_phrases": ["web designer profissional", "em minutos", "gratuitamente"],
    "letterings": [
        {"lead": "", "key": "em minutos", "anchor": "minutos", "nth": 1, "dur": 2.0, "pilha": "ganhos"},
        {"lead": "", "key": "sem pagar nada", "anchor": "pagar", "nth": 1, "dur": 2.0, "pilha": "ganhos"},
        {"lead": "sabe qual é", "key": "O MELHOR", "anchor": "melhor", "nth": 1, "dur": 1.6},
        {"lead": "eu consigo não só", "key": "PRODUZIR AS PÁGINAS", "anchor": "produzir", "nth": 1, "dur": 2.2},
    ],
}
QUADRO = 1.0 / 30
TOTAL_LEGADO = 21.53     # ceil((20,88 s de áudio + 0,65 de TAIL_PAD) * 100) / 100, a conta do caminho antigo


def _blocos_do_texto(texto, pasta):
    """Os blocos do parser do motor, a partir do texto de um roteiro anotado."""
    p = Path(pasta) / "roteiro_tmp.txt"
    p.write_text(texto, encoding="utf-8")
    return BL.ler_blocos(str(p))


def _palavras_sinteticas(blocos):
    """Fala contínua com pausa entre blocos: 0,36 s por palavra, 0,3 s de pausa na troca de bloco."""
    t, saida = 0.62, []
    for b in blocos:
        for w in b["narr"].split():
            saida.append({"t": w, "s": round(t, 3), "e": round(t + 0.3, 3)})
            t += 0.36
        t += 0.3
    return saida


class Mundo(object):
    """Projeto falso em disco: avatar, roteiro, inserts, alinhamento e timeline gravados."""

    def __init__(self, base):
        self.base = Path(base)
        self.dados = self.base / "dados"
        self.inputs = self.dados / "inputs"
        self.output = self.dados / "output"
        for p in (self.inputs, self.output):
            p.mkdir(parents=True, exist_ok=True)
        self.avatar = self.inputs / f"{AD}_{LOOK}_avatar.mp4"
        self.avatar.write_bytes(b"avatar sintetico")
        self.leva = self.inputs / f"{AD}_leva.txt"
        self.leva.write_text(LEVA, encoding="utf-8")
        for nome in ("a.mp4", "b.mp4"):
            (self.inputs / nome).write_bytes(b"insert")
        self.inserts_map = {"demo a": {"file": str(self.inputs / "a.mp4"), "start": 0, "speed": 1.0},
                            "demo b": {"file": str(self.inputs / "b.mp4"), "start": 1.0, "speed": 1.0,
                                       "split": True}}
        self.inserts = self.inputs / f"{AD}_inserts.json"
        self.inserts.write_text(json.dumps(self.inserts_map), encoding="utf-8")
        self.cfg = dict(CFG, avatar=str(self.avatar))
        self.blocks = BL.ler_blocos(str(self.leva))
        palavras = _palavras_sinteticas(self.blocks)
        self.alinhamento = {"versao": 1, "avatar": "inputs/" + self.avatar.name,
                            "avatar_sha256": hashlib.sha256(self.avatar.read_bytes()).hexdigest(),
                            "duracao_audio_s": round(palavras[-1]["e"] + 0.4, 3),
                            "transcricao": [{"text": p["t"], "start": p["s"], "end": p["e"]} for p in palavras],
                            "palavras": palavras}
        self.caminho_alinhamento = self.output / f"{AD}_{LOOK}_alinhamento.json"
        self.sha_alinhamento = AL.gravar(self.alinhamento, self.caminho_alinhamento)
        self.caminho_timeline = self.output / f"{AD}_{LOOK}_timeline.json"
        self.timeline = TC.construir(self.blocks, self.alinhamento, inserts_map=self.inserts_map, cfg=self.cfg,
                                     caminho_alinhamento=self.caminho_alinhamento, raiz=self.dados)
        TC.gravar(self.timeline, self.caminho_timeline)

    def palavras_motor(self):
        return AL.palavras(self.alinhamento)


@pytest.fixture
def mundo(tmp_path):
    return Mundo(tmp_path)


def _plano_da_footage_sozinha(m):
    """O que a footage calcularia SEM timeline, a partir das mesmas palavras."""
    blocks = BL.ler_blocos(str(m.leva))
    spans, bwords = BL.atribuir_spans(blocks, m.palavras_motor())
    spans = BL.tornar_contiguos(spans)
    _, _, _, plano = BL.aplicar_ritmo(blocks, spans, bwords, m.inserts_map)
    return spans, plano


# ============================================================================ contrato

def test_timeline_valida_no_contrato_e_cita_o_sha_do_alinhamento(mundo):
    tl = mundo.timeline
    assert validar("timeline", tl) == []
    f = tl["fontes"]
    assert f["alinhamento_sha256"] == hashlib.sha256(mundo.caminho_alinhamento.read_bytes()).hexdigest()
    assert f["alinhamento"] == "output/" + mundo.caminho_alinhamento.name
    assert f["avatar"] == "inputs/" + mundo.avatar.name
    assert f["avatar_sha256"] == mundo.alinhamento["avatar_sha256"]
    assert tl["relogio"]["base"] == "footage_1x" and tl["relogio"]["fps"] == 30
    assert tl["formato"] == "9x16" and tl["projeto"] == AD


def test_o_arquivo_gravado_tambem_valida_e_le_igual(mundo):
    assert TC.ler(mundo.caminho_timeline) == mundo.timeline


def test_blocos_contiguos_comecam_no_a0_e_acabam_na_duracao(mundo):
    tl = mundo.timeline
    bl, sg = tl["blocos"], tl["segmentos"]
    assert tl["relogio"]["a0"] == bl[0]["s"]
    assert tl["duracao_s"] == bl[-1]["e"] == sg[-1]["e"]
    for a, b in zip(bl, bl[1:]):
        assert b["s"] == a["e"]
    for a, b in zip(sg, sg[1:]):
        assert b["s"] == a["e"]
    assert [b["i"] for b in bl] == list(range(len(bl)))


def test_camera_dos_punches_vem_vazia_por_padrao_e_sfx_vazio_e_ducking_desligado_com_motivo(mundo):
    """`camera` é o campo do contrato onde a W4.A pousa os punches ({t, tipo: punch, de, para, dur, segura})."""
    tl = mundo.timeline
    assert tl["camera"] == []
    assert tl["sfx"] == []
    assert tl["ducking"]["desligado"] is True and len(tl["ducking"]["motivo"]) >= 5


def test_punches_entram_em_camera_e_a_timeline_continua_valida(mundo):
    av = next(s for s in mundo.timeline["segmentos"] if s["tipo"] == "apresentador")
    punch = {"t": round(av["s"] + 0.2, 3), "tipo": "punch", "de": 1.0, "para": 1.22, "dur": 0.28, "segura": 1.0}
    tl = TC.construir(mundo.blocks, mundo.alinhamento, inserts_map=mundo.inserts_map, cfg=mundo.cfg,
                      caminho_alinhamento=mundo.caminho_alinhamento, raiz=mundo.dados, punches=[punch])
    assert tl["camera"] == [punch]
    assert validar("timeline", tl) == []


def test_tipos_dos_blocos_e_chave_do_insert_no_formato_do_contrato(mundo):
    bl = mundo.timeline["blocos"]
    assert [b["tipo"] for b in bl] == ["insert", "apresentador", "apresentador", "insert", "cta"]
    assert [b["insert"] for b in bl] == ["demo-a", None, None, "demo-b", None]
    assert TC.chave("Demo  Á_b!") == "demo-a_b"


def test_hook_cta_letterings_e_legendas_saem_no_relogio_unico(mundo):
    tl = mundo.timeline
    h = tl["hook"]
    assert (h["eyebrow"], h["linha"], h["destaque"], h["estilo"]) == (
        "MEU CLAUDE", "virou um web designer", "PROFISSIONAL", "editorial")
    assert h["s"] == tl["relogio"]["a0"] < h["e"]
    assert tl["cta"]["label"] == "saiba mais" and tl["cta"]["sem_lead"] is False
    assert tl["cta"]["inicio"] <= tl["cta"]["logo"] < tl["duracao_s"]
    ids = [l["id"] for l in tl["letterings"]]
    assert ids == sorted(ids) and all(i == i.lower() for i in ids)
    for l in tl["letterings"]:
        assert l["s"] + l["d"] <= tl["duracao_s"] + 1e-9
        assert l["estilo"] == "serif_editorial"
    pilha = [l for l in tl["letterings"] if l["pilha"]]
    assert pilha and pilha[0]["pilha"] == "ganhos"
    assert any(l["cta"] for l in tl["letterings"]), "o lettering do bloco com logo é o do CTA"
    texto_roteiro = " ".join(b["narr"] for b in mundo.blocks)
    for lg in tl["legendas"]:
        assert lg["texto"] == " ".join(p["t"] for p in lg["palavras"])
        assert lg["texto"] in texto_roteiro, "legenda verbatim do roteiro"
        assert lg["suprimida"] is False and lg["posicao"] in ("padrao", "rodape", "costura")


# ============================================================================ o relógio é o da footage

def test_spans_e_plano_da_timeline_sao_os_que_a_footage_calcularia_sozinha(mundo):
    spans, plano = _plano_da_footage_sozinha(mundo)
    assert TC.spans(mundo.timeline) == spans
    plano_tl = TC.plano_do_motor(mundo.timeline, mundo.blocks, mundo.inserts_map, BL.achar_insert)
    assert json.dumps(plano_tl) == json.dumps(plano), "mesmo plano, chave a chave, na mesma ordem"


def test_ida_e_volta_dos_segmentos_do_contrato(mundo):
    plano = TC.plano_do_motor(mundo.timeline, mundo.blocks, mundo.inserts_map, BL.achar_insert)
    assert TC.segmentos_do_plano(plano) == mundo.timeline["segmentos"]


def test_o_crop_do_insert_volta_pelo_config_do_insert(mundo):
    ins = copy.deepcopy(mundo.inserts_map)
    ins["demo a"]["crop"] = "900:1600:90:0"
    plano = TC.plano_do_motor(mundo.timeline, mundo.blocks, ins, BL.achar_insert)
    assert {s["crop"] for s in plano if s["bloco"] == 0 and s["tipo"] == "insert"} == {"900:1600:90:0"}
    assert {s["crop"] for s in plano if s["tipo"] == "orig"} == {None}


def test_janelas_de_split_da_timeline_sao_as_do_overlay_sobre_o_mesmo_plano(mundo):
    spans = TC.spans(mundo.timeline)
    plano = TC.plano_do_motor(mundo.timeline, mundo.blocks, mundo.inserts_map, BL.achar_insert)
    visitas, _ = OB.planejar_visitas(mundo.blocks, spans, mundo.inserts_map, plano)
    janelas, _, _ = OL.janelas_por_visita(visitas)
    assert TC.janelas_split(mundo.timeline) == janelas
    assert janelas, "o fixture sintético tem tela dividida"


def test_construir_e_puro_nao_chama_subprocesso(mundo, monkeypatch):
    def proibido(*a, **k):
        raise AssertionError("construir não chama subprocesso")

    monkeypatch.setattr(subprocess, "run", proibido)
    monkeypatch.setattr(subprocess, "Popen", proibido)
    TC.construir(mundo.blocks, mundo.alinhamento, inserts_map=mundo.inserts_map, cfg=mundo.cfg,
                 caminho_alinhamento=mundo.caminho_alinhamento, raiz=mundo.dados)


def test_avatar_fora_da_pasta_do_projeto_e_erro_claro(mundo):
    al = dict(mundo.alinhamento, avatar="/fora/do/projeto.mp4")
    with pytest.raises(TC.ErroTimeline, match="dentro"):
        TC.construir(mundo.blocks, al, inserts_map=mundo.inserts_map, cfg=mundo.cfg,
                     caminho_alinhamento=mundo.caminho_alinhamento, raiz=mundo.dados)


# ============================================================================ leitura pelos motores

def test_ler_recusa_timeline_fora_do_contrato_nomeando_o_campo(mundo, tmp_path):
    tl = copy.deepcopy(mundo.timeline)
    tl["relogio"]["base"] = "overlay"
    p = tmp_path / "ruim.json"
    p.write_text(json.dumps(tl), encoding="utf-8")
    with pytest.raises(TC.ErroTimeline, match="relogio.base"):
        TC.ler(p)


def test_ler_para_motor_devolve_as_palavras_do_alinhamento(mundo):
    tl, palavras = TC.ler_para_motor(mundo.caminho_timeline, mundo.blocks, avatar=mundo.avatar)
    assert tl == mundo.timeline
    assert palavras == mundo.palavras_motor()


def test_ler_para_motor_recusa_alinhamento_trocado_depois(mundo):
    al = json.loads(mundo.caminho_alinhamento.read_text(encoding="utf-8"))
    al["palavras"][3]["s"] += 0.5
    mundo.caminho_alinhamento.write_text(json.dumps(al), encoding="utf-8")
    with pytest.raises(TC.ErroTimeline, match="alinhamento"):
        TC.ler_para_motor(mundo.caminho_timeline, mundo.blocks, avatar=mundo.avatar)


def test_ler_para_motor_recusa_avatar_trocado(mundo):
    mundo.avatar.write_bytes(b"outro avatar")
    with pytest.raises(TC.ErroTimeline, match="avatar"):
        TC.ler_para_motor(mundo.caminho_timeline, mundo.blocks, avatar=mundo.avatar)


def test_ler_para_motor_recusa_roteiro_de_outro_anuncio(mundo, tmp_path):
    outro = _blocos_do_texto(LEVA.replace("Sabe qual é o melhor?", "Sabe qual é o pior?"), tmp_path)
    with pytest.raises(TC.ErroTimeline, match="roteiro"):
        TC.ler_para_motor(mundo.caminho_timeline, outro, avatar=mundo.avatar)


# ============================================================================ footage com a timeline

@pytest.fixture
def footage_falsa(monkeypatch):
    """A footage inteira sem ffmpeg: render, cadeia e grade viram registro de evento."""
    eventos = []

    def renderiza(blocks, spans, ctx):
        eventos.append("renderizar")
        out = []
        for i in range(len(blocks)):
            p = os.path.join(ctx.tmp, f"s{i:02d}.mp4")
            Path(p).write_bytes(b"x")
            out.append(p)
        return out

    def nao_alinha(*a, **k):
        eventos.append("alinhar")
        return ALINHAR_ORIGINAL(*a, **k)

    monkeypatch.setattr(BL, "alinhar", nao_alinha)
    monkeypatch.setattr(RS, "renderizar_todos", renderiza)
    monkeypatch.setattr(CA, "run", lambda c: eventos.append("cadeia"))
    monkeypatch.setattr(GF, "run", lambda c: eventos.append("grade"))
    monkeypatch.setattr(CA, "vdur", lambda p: 99.0)
    monkeypatch.setattr(CA, "lum_primeiro_quadro", lambda p: 255.0)
    monkeypatch.setattr(CA, "verificar_segmentos", lambda *a, **k: None)
    monkeypatch.setattr(CA, "verificar_cadeia", lambda *a, **k: None)
    return eventos


ALINHAR_ORIGINAL = BL.alinhar


def _env_footage(m, timeline=True, saida="teste_footage_1x.mp4"):
    env = {"VAM_AVATAR": str(m.avatar), "VAM_ROTEIRO": str(m.leva), "VAM_INSERTS_JSON": str(m.inserts),
           "VAM_OUT": saida, "CAP": "0", "VAM_BAKE_LETTERING": "0", "VAM_DADOS": str(m.dados)}
    if timeline:
        env["VAM_TIMELINE"] = str(m.caminho_timeline)
    return env


def _proibir_transcricao(monkeypatch, registro):
    def nao_transcreve(*a, **k):
        registro.append(("transcrever", a))
        raise AssertionError("com timeline ninguém transcreve")

    monkeypatch.setattr(T, "transcrever", nao_transcreve)
    monkeypatch.setattr(OT, "transcrever", nao_transcreve)


def test_footage_com_timeline_nao_alinha_e_escreve_o_plano_da_timeline(mundo, footage_falsa, monkeypatch, capsys):
    registro = []
    _proibir_transcricao(monkeypatch, registro)
    assert MO.main(env=_env_footage(mundo)) == 0, capsys.readouterr().err
    assert "alinhar" not in footage_falsa and registro == []
    assert footage_falsa == ["renderizar", "cadeia", "grade"]
    ritmo_json = json.loads((mundo.output / "teste_footage_1x_ritmo.json").read_text(encoding="utf-8"))
    plano = TC.plano_do_motor(mundo.timeline, mundo.blocks, mundo.inserts_map, BL.achar_insert)
    assert ritmo_json == {"segs": json.loads(json.dumps(plano)), "total": mundo.timeline["duracao_s"]}
    timing = json.loads((mundo.output / "timing.json").read_text(encoding="utf-8"))
    assert timing["a0"] == mundo.timeline["relogio"]["a0"]
    assert timing["total"] == mundo.timeline["duracao_s"]


def test_footage_com_e_sem_timeline_escrevem_o_mesmo_ritmo_e_o_mesmo_timing(mundo, footage_falsa, monkeypatch):
    """O relógio é o da footage: com a timeline nada muda no que a footage produz."""
    palavras = mundo.palavras_motor()
    monkeypatch.setattr(BL, "alinhar", lambda *a, **k: palavras)
    assert MO.main(env=_env_footage(mundo, timeline=False, saida="sem_footage_1x.mp4")) == 0
    sem_ritmo = (mundo.output / "sem_footage_1x_ritmo.json").read_text(encoding="utf-8")
    sem_timing = (mundo.output / "timing.json").read_text(encoding="utf-8")
    assert MO.main(env=_env_footage(mundo, timeline=True, saida="sem_footage_1x.mp4")) == 0
    assert (mundo.output / "sem_footage_1x_ritmo.json").read_text(encoding="utf-8") == sem_ritmo
    assert (mundo.output / "timing.json").read_text(encoding="utf-8") == sem_timing


def test_footage_sem_timeline_avisa_e_segue_o_caminho_antigo(mundo, footage_falsa, monkeypatch, capsys):
    palavras = mundo.palavras_motor()
    monkeypatch.setattr(BL, "alinhar", lambda *a, **k: footage_falsa.append("alinhar") or palavras)
    assert MO.main(env=_env_footage(mundo, timeline=False)) == 0
    assert footage_falsa[0] == "alinhar"
    err = capsys.readouterr().err
    assert "[relogio]" in err and "timeline" in err


def test_footage_com_timeline_quebrada_sai_com_1_sem_traceback(mundo, footage_falsa, capsys):
    mundo.caminho_timeline.write_text("{", encoding="utf-8")
    assert MO.main(env=_env_footage(mundo)) == 1
    err = capsys.readouterr().err
    assert "timeline" in err and "Traceback" not in err


def test_config_da_footage_le_vam_timeline(mundo):
    assert MO.ler_config(_env_footage(mundo)).timeline == str(mundo.caminho_timeline)
    assert MO.ler_config(_env_footage(mundo, timeline=False)).timeline is None


# ============================================================================ overlay com a timeline

@pytest.fixture
def overlay_falso(monkeypatch):
    """O overlay inteiro sem ffmpeg, sem Chromium e sem medir rosto: só a decisão de tempo e o HTML."""
    capturado = {}

    def preparar_avatar(src, out, speed):
        """O total do caminho antigo: duração do áudio (fim da fala + 0,4 s) mais a folga de cauda."""
        capturado["speed"] = speed
        return Path(out) / "avatar.mp4", TOTAL_LEGADO

    def preparar_arquivos(brolls, out):
        for k, b in enumerate(brolls):
            b["src"] = f"broll{k + 1:02d}.mp4"

    original_visitas = OB.planejar_visitas

    def visitas(blocks, spans, inserts_map, plano):
        capturado["plano"] = copy.deepcopy(plano)
        capturado["spans"] = list(spans)
        return original_visitas(blocks, spans, inserts_map, plano)

    monkeypatch.setattr(OT, "preparar_avatar", preparar_avatar)
    monkeypatch.setattr(OG, "_preparar_pasta", lambda out, tmpl: None)
    monkeypatch.setattr(OB, "preparar_arquivos", preparar_arquivos)
    monkeypatch.setattr(OB, "planejar_visitas", visitas)
    monkeypatch.setattr(OF, "marcar_grupos_claros", lambda *a, **k: None)
    monkeypatch.setattr(OL, "look_fechado", lambda avatar, medir=None: False)
    return capturado


def _cfg_overlay(m, timeline=True):
    cfg = dict(m.cfg, out_dir=str(m.base / "render-ovl"))
    if timeline:
        cfg["timeline"] = str(m.caminho_timeline)
    p = m.base / "cfg_overlay.json"
    p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return p, Path(cfg["out_dir"])


def _proibir_subprocesso(monkeypatch, registro):
    def proibido(*a, **k):
        registro.append(("subprocess", a[0] if a else k.get("args")))
        raise AssertionError("com timeline e mídia falsa o overlay não chama subprocesso")

    monkeypatch.setattr(subprocess, "run", proibido)
    monkeypatch.setattr(subprocess, "Popen", proibido)


def test_overlay_com_timeline_nao_transcreve_e_usa_spans_plano_janelas_e_duracao_dela(
        mundo, overlay_falso, monkeypatch):
    monkeypatch.setattr(OG, "V1", mundo.dados)
    registro = []
    _proibir_transcricao(monkeypatch, registro)
    _proibir_subprocesso(monkeypatch, registro)
    cfg, out = _cfg_overlay(mundo)
    OG.main(str(cfg))
    assert registro == [], "nenhuma transcrição, nenhum subprocesso (zero hyperframes transcribe)"
    tl = mundo.timeline
    assert overlay_falso["spans"] == TC.spans(tl)
    plano = TC.plano_do_motor(tl, mundo.blocks, mundo.inserts_map, BL.achar_insert)
    assert json.dumps(overlay_falso["plano"]) == json.dumps(plano)
    janelas = json.loads((out / "janelas_split.json").read_text(encoding="utf-8"))["segs"]
    assert [(j["s"], j["e"]) for j in janelas] == TC.janelas_split(tl)
    prancha = json.loads((out / "prancha.json").read_text(encoding="utf-8"))
    assert prancha["total"] == round(tl["duracao_s"], 2)
    assert [(b["s"], b["e"]) for b in prancha["blocos"]] == [(round(b["s"], 2), round(b["e"], 2))
                                                             for b in tl["blocos"]]
    html = (out / "index.html").read_text(encoding="utf-8")
    assert f'id="root" data-composition-id="main" data-start="0" data-duration="{tl["duracao_s"]}"' in html


def test_overlay_e_footage_leem_o_mesmo_plano_e_as_mesmas_janelas(mundo, overlay_falso, footage_falsa,
                                                                 monkeypatch):
    monkeypatch.setattr(OG, "V1", mundo.dados)
    cfg, out = _cfg_overlay(mundo)
    OG.main(str(cfg))
    assert MO.main(env=_env_footage(mundo)) == 0
    segs_footage = json.loads((mundo.output / "teste_footage_1x_ritmo.json").read_text(encoding="utf-8"))["segs"]
    assert segs_footage == json.loads(json.dumps(overlay_falso["plano"]))
    janelas_overlay = json.loads((out / "janelas_split.json").read_text(encoding="utf-8"))["segs"]
    visitas, _ = OB.planejar_visitas(mundo.blocks, TC.spans(mundo.timeline), mundo.inserts_map, segs_footage)
    janelas_footage, _, _ = OL.janelas_por_visita(visitas)
    assert [(j["s"], j["e"]) for j in janelas_overlay] == janelas_footage


def test_overlay_com_timeline_recusa_aceleracao_no_overlay(mundo, overlay_falso, monkeypatch):
    monkeypatch.setattr(OG, "V1", mundo.dados)
    cfg, _ = _cfg_overlay(mundo)
    dados = json.loads(cfg.read_text(encoding="utf-8"))
    dados["speed"] = 1.15
    cfg.write_text(json.dumps(dados), encoding="utf-8")
    with pytest.raises(SystemExit, match="1x"):
        OG.main(str(cfg))


def test_overlay_com_timeline_de_outro_avatar_para(mundo, overlay_falso, monkeypatch):
    monkeypatch.setattr(OG, "V1", mundo.dados)
    mundo.avatar.write_bytes(b"outro avatar")
    cfg, _ = _cfg_overlay(mundo)
    with pytest.raises(SystemExit, match="avatar"):
        OG.main(str(cfg))


def test_overlay_sem_timeline_avisa_no_fim_e_segue_o_caminho_antigo(mundo, overlay_falso, monkeypatch, capsys):
    monkeypatch.setattr(OG, "V1", mundo.dados)
    palavras = [{"id": f"w{i}", "text": p["t"].strip(".,?"), "start": p["s"], "end": p["e"]}
                for i, p in enumerate(mundo.alinhamento["palavras"])]
    chamadas = []
    monkeypatch.setattr(OT, "transcrever", lambda dst, out: chamadas.append(1) or palavras)
    monkeypatch.setattr(OL, "aplicar_relogio_footage", lambda ad, look, j: j)
    cfg, out = _cfg_overlay(mundo, timeline=False)
    OG.main(str(cfg))
    assert chamadas == [1]
    cap = capsys.readouterr()
    assert "[relogio]" in cap.err and "timeline" in cap.err


# ============================================================================ uma transcrição no caminho todo

def test_uma_transcricao_por_avatar_no_caminho_inteiro(tmp_path, overlay_falso, footage_falsa, monkeypatch):
    """alinhar (1 audio.transcrever) -> construir -> footage e overlay: nenhuma outra transcrição."""
    m = Mundo(tmp_path)
    monkeypatch.setattr(OG, "V1", m.dados)
    contagem = {"transcrever": 0, "backend": 0}
    original = T.transcrever

    class Backend(object):
        NOME = "falso"

        def transcrever(self, audio, **kw):
            contagem["backend"] += 1
            return [dict(p) for p in m.alinhamento["transcricao"]]

    def espia(audio, **kw):
        contagem["transcrever"] += 1
        kw["backend"] = Backend()
        return original(audio, **kw)

    monkeypatch.setattr(T, "transcrever", espia)
    def hyperframes(*a, **k):
        raise AssertionError("hyperframes transcribe com timeline")

    monkeypatch.setattr(OT, "transcrever", hyperframes)
    registro = []
    al = AL.alinhar(m.avatar, BL.palavras_da_narracao(m.blocks), cache_dir=m.output / "cache_asr", raiz=m.dados,
                    duracao=lambda p: m.alinhamento["duracao_audio_s"])
    AL.gravar(al, m.caminho_alinhamento)
    tl = TC.construir(m.blocks, al, inserts_map=m.inserts_map, cfg=m.cfg,
                      caminho_alinhamento=m.caminho_alinhamento, raiz=m.dados)
    TC.gravar(tl, m.caminho_timeline)
    _proibir_subprocesso(monkeypatch, registro)
    cfg, _ = _cfg_overlay(m)
    OG.main(str(cfg))
    cfg_q = json.loads(cfg.read_text(encoding="utf-8"))
    cfg_q["format"], cfg_q["out_dir"] = "1x1", str(m.base / "render-ovl-1x1")
    cfg.write_text(json.dumps(cfg_q, ensure_ascii=False), encoding="utf-8")
    OG.main(str(cfg))
    assert MO.main(env=_env_footage(m)) == 0
    assert contagem == {"transcrever": 1, "backend": 1}
    assert registro == [] and "alinhar" not in footage_falsa


# ============================================================================ CLI

def test_cli_alinha_e_constroi_os_dois_arquivos(mundo, monkeypatch, capsys):
    transcricao = mundo.alinhamento["transcricao"]
    monkeypatch.setattr(T, "transcrever", lambda audio, **kw: [dict(p) for p in transcricao])
    monkeypatch.setattr(AL, "duracao_do_audio", lambda p: mundo.alinhamento["duracao_audio_s"])
    cfg = mundo.base / "cfg.json"
    cfg.write_text(json.dumps(mundo.cfg, ensure_ascii=False), encoding="utf-8")
    destino = mundo.output / "cli_timeline.json"
    rc = TC.main(["--avatar", str(mundo.avatar), "--roteiro", str(mundo.leva), "--inserts", str(mundo.inserts),
                  "--config", str(cfg), "--timeline", str(destino)])
    assert rc == 0, capsys.readouterr().err
    tl = TC.ler(destino)
    alinhamento = destino.with_name("cli_alinhamento.json")
    assert alinhamento.is_file()
    assert tl["fontes"]["alinhamento"] == "output/cli_alinhamento.json"
    assert TC.spans(tl) == TC.spans(mundo.timeline)
    assert tl["segmentos"] == mundo.timeline["segmentos"]


def test_cli_sem_argumento_sai_com_2_e_mostra_o_uso(capsys):
    assert TC.main([]) == 2
    assert "--avatar" in capsys.readouterr().err


def test_cli_com_erro_de_entrada_sai_com_1_sem_traceback(mundo, capsys):
    rc = TC.main(["--avatar", str(mundo.base / "nao_existe.mp4"), "--roteiro", str(mundo.leva),
                  "--inserts", str(mundo.inserts), "--config", str(mundo.base / "nao.json"),
                  "--timeline", str(mundo.output / "x_timeline.json")])
    assert rc == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err and err.strip()


def test_aceleracao_e_cauda_vem_das_constantes_do_motor():
    """O padrão da timeline é o do arquivo entregue hoje (build_composite: ACCEL e TAIL_FINAL)."""
    import re
    texto = (RAIZ / "scripts" / "build_composite.py").read_text(encoding="utf-8")
    accel = float(re.search(r"^ACCEL = ([0-9.]+)", texto, re.M).group(1))
    cauda = float(re.search(r"^TAIL_FINAL = ([0-9.]+)", texto, re.M).group(1))
    assert TC.ACELERACAO_PADRAO == accel and TC.CAUDA_S == cauda


# ============================================================================ fixture real (lento)

@pytest.mark.midia_real
@pytest.mark.lento
def test_fixture_uma_transcricao_e_overlay_e_footage_no_mesmo_relogio():
    """Na mídia real da paridade: uma transcrição no build, mesmo plano e mesmas janelas nos dois motores,
    e a duração do overlay e a da footage diferem em até 1 quadro (antes: a deriva medida, impressa)."""
    from tests.paridade import capturar as C

    midia = C.exigir_midia()
    cap = C.capturar_memo(RAIZ, midia).arquivos
    tl = json.loads(cap["timeline/timeline.json"])
    assert validar("timeline", tl) == []

    # uma transcrição por avatar no caminho novo
    novo = [cap[f"argv/{f}.jsonl"] for f in ("timeline", "overlay", "overlay_1x1", "timeline_footage")]
    assert sum(t.count('"<PARAKEET>"') for t in novo) == 1
    assert all('"<HF>", "transcribe"' not in t for t in novo)

    # mesmo plano e mesmas janelas
    segs_footage = json.loads(cap["timeline/footage/ritmo.json"])["segs"]
    assert segs_footage == json.loads(cap["footage/ritmo.json"])["segs"], "o relógio é o da footage"
    janelas_overlay = json.loads(cap["overlay/janelas_split.json"])["segs"]
    assert [(j["s"], j["e"]) for j in janelas_overlay] == [(j["s"], j["e"]) for j in tl["janelas_split"]]

    # duração: overlay (deslocado de -a0 no composite) x footage medida em quadros
    def quadros(framemd5):
        return sum(1 for l in framemd5.splitlines() if l and not l.startswith("#"))

    a0 = json.loads(cap["timeline/footage/timing.json"])["a0"]
    dur_footage = quadros(cap["timeline/footage/video.framemd5"]) / 30.0
    antes = json.loads(cap["overlay_convergido/prancha.json"])["total"] - a0
    depois = json.loads(cap["overlay/prancha.json"])["total"] - a0
    print(f"\n[relogio] footage {dur_footage:.3f}s | overlay antes {antes:.3f}s (deriva {antes - dur_footage:+.3f}s)"
          f" | overlay depois {depois:.3f}s (deriva {depois - dur_footage:+.3f}s)")
    assert abs(depois - dur_footage) <= QUADRO + 1e-6


@pytest.mark.midia_real
@pytest.mark.lento
def test_fixture_gate_relogio_passa_nos_arquivos_reais_e_pega_a_janela_deslocada(tmp_path):
    """O gate sobre o que a footage e o overlay gravaram de verdade no fixture; e a timeline mutada reprova."""
    from gates import gate_relogio as G
    from tests.paridade import capturar as C

    cap = C.capturar_memo(RAIZ, C.exigir_midia()).arquivos
    out, ovl = tmp_path / "output", tmp_path / "ovl"
    out.mkdir()
    ovl.mkdir()
    tl_txt = cap["timeline/timeline.json"]
    tl = json.loads(tl_txt)
    (tmp_path / tl["fontes"]["alinhamento"]).write_text(cap["timeline/alinhamento.json"], encoding="utf-8")
    (out / "f_timeline.json").write_text(tl_txt, encoding="utf-8")
    (out / "f_ritmo.json").write_text(cap["timeline/footage/ritmo.json"], encoding="utf-8")
    (out / "timing.json").write_text(cap["timeline/footage/timing.json"], encoding="utf-8")
    (ovl / "prancha.json").write_text(cap["overlay/prancha.json"], encoding="utf-8")
    (ovl / "janelas_split.json").write_text(cap["overlay/janelas_split.json"], encoding="utf-8")
    argv = ["--timeline", str(out / "f_timeline.json"), "--footage-ritmo", str(out / "f_ritmo.json"),
            "--footage-timing", str(out / "timing.json"), "--overlay-dir", str(ovl)]
    assert G.main(argv) == 0
    tl["janelas_split"][0]["s"] = round(tl["janelas_split"][0]["s"] + 2 * QUADRO, 4)
    tl["janelas_split"][0]["e"] = round(tl["janelas_split"][0]["e"] + 2 * QUADRO, 4)
    (out / "f_timeline.json").write_text(json.dumps(tl), encoding="utf-8")
    assert G.main(argv) == 1
