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
    assert prancha["total"] == TC.duracao_do_overlay(tl)
    assert [(b["s"], b["e"]) for b in prancha["blocos"]] == [(round(b["s"], 2), round(b["e"], 2))
                                                             for b in tl["blocos"]]
    html = (out / "index.html").read_text(encoding="utf-8")
    assert (f'id="root" data-composition-id="main" data-start="0" data-duration="{TC.duracao_do_overlay(tl)}"'
            in html)


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
    # W3.X M1: o overlay cobre a footage com pelo menos 1 quadro de folga (o composite usa shortest=1) e a folga
    # é a da timeline, não a cauda de 0,65 s do caminho antigo
    folga = TC.duracao_do_overlay(tl) - tl["duracao_s"]
    assert QUADRO - 1e-6 <= depois - dur_footage <= folga + 2 * QUADRO + 1e-6


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


# ============================================================================ W3.X A1: nenhuma legenda invertida
# Invariante: toda legenda da timeline tem início < fim e pelo menos 0,20 s (o piso do fechamento), em qualquer
# roteiro que o overlay aceita. O padrão comum que quebrava: o último insert é split com `dur_max` e o CTA vem logo
# depois; o grupo cortado na fronteira do split era truncado no logo DEPOIS do filtro de 0,20 s e nascia invertido
# ("$.legendas[11]: início 13.43 não é menor que o fim 13.25"). A timeline é construída nos 25 cenários fixos do
# diferencial do overlay (tests/overlay/test_gerar.py), com dois modelos de fala sintética.

INSERTS_DO_FIXTURE = {"demo a": {"file": "broll01.mp4", "start": 0, "speed": 1.0},
                      "demo b": {"file": "broll02.mp4", "start": 1.0, "speed": 1.0, "split": True}}


def _tempos(n, pausas, ini=0.4, dur=0.26, vao=0.06):
    """A fala sintética da auditoria: 0,26 s por palavra, 0,06 s de vão e pausas nos índices dados."""
    t, out = ini, []
    for i in range(n):
        t += pausas.get(i, 0.0)
        out.append((round(t, 2), round(t + dur, 2)))
        t = round(t + dur + vao, 2)
    return out


def _cenarios_da_timeline():
    """Os 25 cenários fixos do diferencial do overlay e o que a auditoria mediu quebrando (o 26º): o último insert
    é split com `dur_max` e o CTA vem logo depois dele."""
    from tests.overlay import test_gerar as TG

    cenarios = {c.nome: c for c in TG._cenarios_fixos()}
    auditoria = TG.Cenario(
        "dur_max_fatias_da_auditoria", inserts={"demo a": {"dur_max": 2.0}, "demo b": {"dur_max": 2.5}},
        blocos=[(TG.AVATAR, 0, 6), ("inserção de vídeo: demo a", 6, 24),
                ("apresentador + lettering | LEAD: sabe qual é | KEY: O MELHOR", 24, 30),
                ("inserção de vídeo: demo b", 30, 47),
                ("apresentador + lettering + logo | LEAD: eu consigo | KEY: PRODUZIR", 47, 52)])
    cenarios[auditoria.nome] = auditoria
    return cenarios


def _construir_cenario(cen, pasta, modelo):
    from tests.overlay import test_gerar as TG

    pasta = Path(pasta)
    (pasta / "inputs").mkdir(parents=True, exist_ok=True)
    blocks = _blocos_do_texto(TG.leva(cen.blocos, cen.trocas), pasta)
    narr = BL.palavras_da_narracao(blocks)
    if modelo == "auditoria":
        tempos = _tempos(len(narr), {14: 0.35, 28: 0.4, 33: 0.3, 45: 0.3})
    else:                               # pausa de 0,35 s em cada troca de bloco DESTE cenário
        inicios, k = set(), 0
        for b in blocks[1:]:
            k += len(blocks[len(inicios)]["narr"].split())
            inicios.add(k)
        tempos = _tempos(len(narr), {i: 0.35 for i in inicios})
    inserts = copy.deepcopy(INSERTS_DO_FIXTURE)
    for extra in cen.extras:
        if extra in ("branco", "escuro", "imagem"):
            inserts["demo c"] = {"file": "figura.png" if extra == "imagem" else f"{extra}.mp4", "start": 0,
                                 "speed": 1.0}
    for chave_i, mudancas in cen.inserts.items():
        if mudancas is None:
            inserts.pop(chave_i, None)
        else:
            inserts.setdefault(chave_i, {}).update(mudancas)
    cfg = dict(CFG, format=cen.formato, letterings=copy.deepcopy(TG.LETTERINGS_BASE))
    if cen.letterings is not None:
        cfg["letterings"] = copy.deepcopy(cen.letterings)
    cfg.update(cen.cfg)
    avatar = pasta / "inputs" / "avatar.mp4"
    avatar.write_bytes(b"avatar")
    casadas = [(s, e, w) for (s, e), w in zip(tempos, narr)]
    al = {"versao": 1, "avatar": "inputs/avatar.mp4", "avatar_sha256": hashlib.sha256(b"avatar").hexdigest(),
          "duracao_audio_s": round(tempos[-1][1] + 0.6, 2),
          "transcricao": [{"text": w, "start": s, "end": e} for s, e, w in casadas],
          "palavras": [{"t": w, "s": s, "e": e} for s, e, w in casadas]}
    p_al = pasta / "output" / "alinhamento.json"
    AL.gravar(al, p_al)
    return TC.construir(blocks, al, inserts_map=inserts, cfg=cfg, caminho_alinhamento=p_al, raiz=pasta)


@pytest.mark.parametrize("modelo", ["auditoria", "pausa_por_bloco"])
@pytest.mark.parametrize("nome", sorted(_cenarios_da_timeline()))
def test_a1_nenhuma_legenda_invertida_nos_25_cenarios_do_diferencial(nome, modelo, tmp_path, capsys):
    cen = _cenarios_da_timeline()[nome]
    try:
        tl = _construir_cenario(cen, tmp_path, modelo)
    except TC.ErroTimeline as e:
        assert "não é menor que o fim" not in str(e), f"{nome}: legenda invertida ({e})"
        assert nome.startswith("erro_"), f"{nome}: a timeline não construiu ({e})"
        return
    for k, lg in enumerate(tl["legendas"]):
        assert lg["s"] < lg["e"], f"{nome}: legenda {k} invertida ({lg['s']}, {lg['e']})"
        assert lg["e"] - lg["s"] >= 0.20 - 1e-9, f"{nome}: legenda {k} com {lg['e'] - lg['s']:.3f}s"


@pytest.mark.parametrize("modelo", ["auditoria", "pausa_por_bloco"])
@pytest.mark.parametrize("nome", sorted(_cenarios_da_timeline()))
def test_w7w_o_cta_nunca_entra_antes_do_inicio_do_bloco_cta(nome, modelo, tmp_path, capsys):
    """W7.W (A2): o CTA entra na âncora do bloco cta, nunca antes do início dele, com `dur_max` no último insert ou sem
    (o cenário da auditoria tem os dois). Antes, a volta da imagem ao avatar adiantava o CTA ~3 s sobre a voz."""
    cen = _cenarios_da_timeline()[nome]
    try:
        tl = _construir_cenario(cen, tmp_path, modelo)
    except TC.ErroTimeline:
        return
    ultimo = tl["blocos"][-1]
    assert tl["cta"]["inicio"] >= ultimo["s"] - 1e-9, \
        f"{nome}: CTA em {tl['cta']['inicio']} antes do bloco {ultimo['tipo']} de {ultimo['s']}"


def test_w7w_o_cta_entra_na_palavra_do_rotulo_no_caminho_real_da_timeline(mundo):
    """W7.W (A2): no caminho real o último bloco NÃO tem `type == "cta"` (o parser o chama de lettering_logo, orig...): a
    timeline é que o rotula `cta` pela posição. A âncora precisa funcionar para qualquer tipo do último bloco (o teste
    de unidade usava `type: cta` e o build real da prova ficou no início do bloco, 0,4 s antes da palavra)."""
    cfg = dict(mundo.cfg, cta_label="PRODUZIR AS PÁGINAS")
    tl = TC.construir(mundo.blocks, mundo.alinhamento, inserts_map=mundo.inserts_map, cfg=cfg,
                      caminho_alinhamento=mundo.caminho_alinhamento, raiz=mundo.dados)
    assert mundo.blocks[-1]["type"] != "cta"
    ultimo = tl["blocos"][-1]
    produzir = next(w["s"] for w in mundo.alinhamento["palavras"] if w["t"] == "produzir" and w["s"] >= ultimo["s"] - 1e-6)
    assert tl["cta"]["inicio"] > ultimo["s"] + 0.1
    assert tl["cta"]["inicio"] == pytest.approx(produzir, abs=1e-6)


def test_a1_os_cenarios_fixos_sao_os_25_do_diferencial_mais_o_da_auditoria():
    from tests.overlay import test_gerar as TG

    assert len(TG._cenarios_fixos()) == 25
    assert len(_cenarios_da_timeline()) == 26



# ============================================================================ W3.X M1: folga de cauda
# Invariante: o overlay (deslocado de -a0 no composite) dura pelo menos 1 quadro a mais que a footage, em qualquer
# configuração de transição. A footage nunca passa da própria janela de áudio (o mux final usa -shortest e corta a
# cadeia mais longa: test_cadeia mede isso com ffmpeg de verdade), então a timeline dá ao overlay a duração da fala
# mais 2 quadros: 1 de folga e 1 para o render do overlay que arredonda a duração para quadro inteiro.

def test_m1_duracao_do_overlay_e_a_da_footage_mais_2_quadros_arredondada_para_cima(mundo):
    import math

    tl = mundo.timeline
    dur = TC.duracao_do_overlay(tl)
    fps = tl["relogio"]["fps"]
    assert dur - tl["duracao_s"] >= 2.0 / fps - 1e-9
    assert dur - tl["duracao_s"] < 2.0 / fps + 0.01
    assert dur == math.ceil(dur * 100 - 1e-6) / 100


@pytest.mark.parametrize("xf", ["0.08", "0.12", "0.2"])
def test_m1_folga_do_overlay_nunca_negativa_qualquer_que_seja_o_whip(mundo, footage_falsa, overlay_falso, monkeypatch,
                                                                    xf):
    """A footage nominal (timing.json) e o overlay que saem da MESMA timeline, com o whip pedido."""
    monkeypatch.setattr(OG, "V1", mundo.dados)
    env = dict(_env_footage(mundo), VAM_XF=xf)
    assert MO.main(env=env) == 0
    timing = json.loads((mundo.output / "timing.json").read_text(encoding="utf-8"))
    cfg, out = _cfg_overlay(mundo)
    OG.main(str(cfg))
    prancha = json.loads((out / "prancha.json").read_text(encoding="utf-8"))
    folga = (prancha["total"] - timing["a0"]) - (timing["total"] - timing["a0"])
    assert folga >= QUADRO - 1e-9, f"VAM_XF={xf}: folga de cauda {folga:+.3f}s"


# ============================================================================ W3.X M2: janela do CTA no relógio antigo

def test_m2_overlay_com_timeline_mede_a_janela_do_cta_no_relogio_em_que_o_teto_foi_calibrado(
        mundo, overlay_falso, monkeypatch, capsys):
    """O teto de 12 s foi calibrado no relógio do overlay antigo (fim do áudio + TAIL_PAD); com a timeline a conta
    é a mesma, sobre o total do caminho antigo, e não sobre o fim da fala (que mediria 0,97 s a menos no fixture)."""
    import re

    monkeypatch.setattr(OG, "V1", mundo.dados)
    cfg, _out = _cfg_overlay(mundo)
    OG.main(str(cfg))
    linha = next(l for l in capsys.readouterr().out.splitlines() if "janela do CTA" in l)
    janela = float(re.search(r"janela do CTA: ([0-9.]+)s", linha).group(1))
    cta_s = round(mundo.timeline["cta"]["inicio"], 2)
    assert janela == pytest.approx(TOTAL_LEGADO - cta_s, abs=0.006)


# ============================================================================ W3.X M4: fundo claro no relógio da footage

def test_m4_overlay_com_timeline_passa_o_a0_para_medir_o_fundo_na_footage(mundo, overlay_falso, monkeypatch):
    recebidos = []
    monkeypatch.setattr(OF, "marcar_grupos_claros", lambda *a, **k: recebidos.append(k.get("a0")))
    monkeypatch.setattr(OG, "V1", mundo.dados)
    cfg, _out = _cfg_overlay(mundo)
    OG.main(str(cfg))
    assert recebidos == [mundo.timeline["relogio"]["a0"]]


# ============================================================================ W3.X M5: o que a timeline registra é desenhado

def _cli(mundo, cfg, destino):
    p = mundo.base / "cfg_cli.json"
    p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return TC.main(["--avatar", str(mundo.avatar), "--roteiro", str(mundo.leva), "--inserts", str(mundo.inserts),
                    "--config", str(p), "--timeline", str(destino)])


def _cli_sem_midia(mundo, monkeypatch):
    transcricao = mundo.alinhamento["transcricao"]
    monkeypatch.setattr(T, "transcrever", lambda audio, **kw: [dict(p) for p in transcricao])
    monkeypatch.setattr(AL, "duracao_do_audio", lambda p: mundo.alinhamento["duracao_audio_s"])


def test_m5_cli_mede_o_rosto_e_a_posicao_das_legendas_segue_o_look_fechado(mundo, monkeypatch, capsys):
    """A CLI nunca passava `medir_rosto` e a timeline registrava legenda padrão num look fechado medido."""
    import sys
    import types

    _cli_sem_midia(mundo, monkeypatch)
    rosto = types.ModuleType("medir_rosto")
    medidos = []
    rosto.caixa_rosto = lambda video, *a, **k: medidos.append(str(video)) or (900, 600)   # queixo em 78%
    monkeypatch.setitem(sys.modules, "medir_rosto", rosto)
    destino = mundo.output / "fechado_timeline.json"
    assert _cli(mundo, mundo.cfg, destino) == 0, capsys.readouterr().err
    tl = TC.ler(destino)
    assert medidos and medidos[0] == str(mundo.avatar)
    posicoes = {lg["posicao"] for lg in tl["legendas"]}
    assert "padrao" not in posicoes and "rodape" in posicoes


def test_m5_cli_com_look_aberto_mantem_a_legenda_padrao(mundo, monkeypatch, capsys):
    import sys
    import types

    _cli_sem_midia(mundo, monkeypatch)
    rosto = types.ModuleType("medir_rosto")
    rosto.caixa_rosto = lambda video, *a, **k: (488, 425)                                # queixo em 47%
    monkeypatch.setitem(sys.modules, "medir_rosto", rosto)
    destino = mundo.output / "aberto_timeline.json"
    assert _cli(mundo, mundo.cfg, destino) == 0, capsys.readouterr().err
    assert "padrao" in {lg["posicao"] for lg in TC.ler(destino)["legendas"]}


def test_m5_rotulo_do_cta_da_timeline_e_o_texto_do_botao_no_html(mundo, overlay_falso, monkeypatch):
    import re

    cfg_tl = dict(mundo.cfg, cta_label="ver agora")
    tl = TC.construir(mundo.blocks, mundo.alinhamento, inserts_map=mundo.inserts_map, cfg=cfg_tl,
                      caminho_alinhamento=mundo.caminho_alinhamento, raiz=mundo.dados)
    TC.gravar(tl, mundo.caminho_timeline)
    monkeypatch.setattr(OG, "V1", mundo.dados)
    cfg, out = _cfg_overlay(mundo)
    dados = json.loads(cfg.read_text(encoding="utf-8"))
    dados["cta_label"] = "ver agora"
    cfg.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    OG.main(str(cfg))
    html = (out / "index.html").read_text(encoding="utf-8")
    botao = re.search(r'id="cta-pill">([^<]*)', html).group(1)
    assert botao == tl["cta"]["label"] == "ver agora"


# ============================================================================ W3.X L8: diagnósticos no stderr

def test_l8_a_cli_imprime_so_o_resumo_no_stdout(mundo, monkeypatch, capsys):
    import sys
    import types

    _cli_sem_midia(mundo, monkeypatch)
    rosto = types.ModuleType("medir_rosto")
    rosto.caixa_rosto = lambda video, *a, **k: None
    monkeypatch.setitem(sys.modules, "medir_rosto", rosto)
    assert _cli(mundo, mundo.cfg, mundo.output / "l8_timeline.json") == 0
    cap = capsys.readouterr()
    linhas = [l for l in cap.out.splitlines() if l.strip()]
    assert len(linhas) == 1 and linhas[0].startswith("[timeline]"), cap.out
    assert "[ritmo]" in cap.err or "[split]" in cap.err or "[look]" in cap.err



# ============================================================================ W5.A: o logo real no contrato

def test_logo_antecipado_pelo_overlay_entra_na_timeline_como_e(mundo, monkeypatch):
    """O overlay sobe o logo 0,9 s antes da pílula quando o bloco anterior ao CTA é apresentador. A timeline grava
    esse instante (antes ela grudava o logo no CTA, porque o contrato não aceitava)."""
    from overlay import cta as OC
    monkeypatch.setattr(OC, "logo_lead", lambda blocks: OC.LOGO_LEAD)
    tl = TC.construir(mundo.blocks, mundo.alinhamento, inserts_map=mundo.inserts_map, cfg=mundo.cfg,
                      caminho_alinhamento=mundo.caminho_alinhamento, raiz=mundo.dados)
    assert validar("timeline", tl) == []
    assert tl["cta"]["logo"] == pytest.approx(max(tl["cta"]["inicio"] - OC.LOGO_LEAD, 0.0), abs=1e-6)


def test_o_estilo_do_lettering_no_config_vai_para_a_timeline(mundo):
    """O estilo pedido no config chega à timeline (os gates medem a faixa DELE); em split, close e pilha só o
    editorial cabe (`lettering_estilos.efetivo`)."""
    from cinema import lettering_estilos as LE
    cfg = copy.deepcopy(mundo.cfg)
    for l in cfg["letterings"]:
        l["estilo"] = "punch"
    tl = TC.construir(mundo.blocks, mundo.alinhamento, inserts_map=mundo.inserts_map, cfg=cfg,
                      caminho_alinhamento=mundo.caminho_alinhamento, raiz=mundo.dados)
    assert validar("timeline", tl) == []
    for l in tl["letterings"]:
        assert l["estilo"] == LE.efetivo("punch", split=l["split"], baixo=l["baixo"], pilha=bool(l["pilha"]))
    assert any(l["estilo"] == "punch" for l in tl["letterings"])

