"""W4.A: gate_insert (capacidade C8). Insert com tratamento e densidade.

Reprova quando:
  - a densidade (fração do tempo com insert na tela) está fora de 45 a 55% sem exceção declarada em
    `projeto.excecoes` (regra `densidade`); fora de piso 40 e teto 65 reprova até com exceção;
  - o congelamento previsto de um insert passa de 0,20 s (a conta do `analise_inserts`, já medida em
    `plano.mapa_inserts[].congela_s` pela W3.B);
  - há faixa morta (preto liso) contínua acima de 40 px no composto, em 6 instantes dentro dos inserts;
  - um insert horizontal entra recortado, sem a moldura de navegador.

Densidade e congelamento NÃO são recalculados aqui: a densidade vem dos segmentos da timeline (ou do
`plano.densidade`) e o congelamento do `plano.mapa_inserts`, com os limites de `plano.medir` e
`analise_inserts`.

A faixa morta e a moldura são medidas em quadros do composto de VERDADE: os quadros de teste saem dos
filtros do próprio motor (`filtros_insert`), então a geometria do gate é conferida contra o que o motor
desenha, não contra uma cópia dela.
"""
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import analise_inserts
from contratos import validar
from footage import enquadramento as enq
from footage import filtros_avatar as FA
from footage import filtros_insert as FI
from footage import grade_final as GF
from gates import gate_insert
from plano import medir as plano_medir

RAIZ = Path(__file__).resolve().parents[2]
LAUDO_VALIDO = RAIZ / "contratos" / "exemplos" / "laudo.valido.json"
EXC_DENSIDADE = {"regra": "densidade", "motivo": "anúncio de depoimento, o desenho pede poucos inserts"}


# =================================================================================== insumos sintéticos

def projeto(modo="avatar", excecoes=()):
    return {"versao": 1, "slug": "teste", "modo": modo, "excecoes": list(excecoes)}


def mapa_item(chave="painel", blocos=(1,), largura=1280, altura=720, tratamento="moldura", congela_s=0.0):
    orient = "horizontal" if largura > altura else ("vertical" if altura > largura else "quadrado")
    return {"chave": chave, "arquivo": "inserts/%s.mp4" % chave, "blocos": list(blocos), "largura": largura,
            "altura": altura, "duracao_s": 8.0, "orientacao": orient, "tratamento": tratamento, "visitas": 1,
            "congela_s": congela_s}


def plano(mapa=None, fracao=0.5):
    return {"versao": 1, "projeto": "teste", "modo": "avatar", "mapa_inserts": mapa if mapa is not None else [mapa_item()],
            "densidade": {"fracao_insert": fracao, "alvo_min": 0.45, "alvo_max": 0.55, "piso": 0.40, "teto": 0.65}}


def plano_do_layout(layout, **kw):
    """O plano de um insert horizontal que o motor renderiza em `layout`: em split o tratamento é `split`, em tela cheia
    é `moldura` (W7.Z: o gate mede pelo tratamento que o motor obedeceu, não pelo layout que o ritmo marcou)."""
    return plano([mapa_item(tratamento="split" if layout == "split" else "moldura")], **kw)


def timeline_com_densidade(fracao, total=20.0, layout="cheio"):
    """Avatar, insert, avatar. O insert ocupa `fracao` do tempo."""
    ins = round(total * fracao, 3)
    resto = total - ins
    a, b = round(resto / 2, 3), round(resto / 2, 3)
    segs = [{"bloco": 0, "tipo": "apresentador", "s": 0.0, "e": a, "sub": 0, "de": 1, "base": 1.0},
            {"bloco": 1, "tipo": "insert", "s": a, "e": a + ins, "sub": 0, "de": 1, "layout": layout},
            {"bloco": 2, "tipo": "apresentador", "s": a + ins, "e": total, "sub": 0, "de": 1, "base": 1.0}]
    return timeline_de(segs, total)


def timeline_de(segs, total, aceleracao=1.0):
    blocos = [{"i": sg["bloco"], "tipo": "insert" if sg["tipo"] == "insert" else "apresentador",
               "insert": "painel" if sg["tipo"] == "insert" else None, "s": sg["s"], "e": sg["e"]} for sg in segs]
    return {"relogio": {"base": "footage_1x", "fps": 30, "aceleracao": aceleracao, "cauda_s": 0.0, "a0": 0.0},
            "duracao_s": total, "segmentos": segs, "blocos": blocos, "camera": [],
            "janelas_split": [{"s": sg["s"], "e": sg["e"]} for sg in segs if sg.get("layout") == "split"],
            "letterings": []}


def formato_do_laudo(g):
    laudo = json.loads(LAUDO_VALIDO.read_text(encoding="utf-8"))
    laudo["gates"] = [x for x in laudo["gates"] if x["nome"] != g["nome"]] + [g]
    k = len(laudo["gates"]) - 1
    return [e for e in validar.validar("laudo", laudo) if ("gates[%d]" % k) in e.caminho]


def rodar(**kw):
    kw.setdefault("projeto", projeto())
    return gate_insert.rodar(**kw)


# =================================================================================== constantes: origem única

def test_limites_sao_os_do_plano_medir_e_do_analise_inserts():
    assert (gate_insert.ALVO_MIN, gate_insert.ALVO_MAX, gate_insert.PISO, gate_insert.TETO) == \
        (plano_medir.ALVO_MIN, plano_medir.ALVO_MAX, plano_medir.PISO, plano_medir.TETO) == (0.45, 0.55, 0.40, 0.65)
    assert gate_insert.CONGELA_MAX_S == analise_inserts.LIMITE_S == 0.20
    assert gate_insert.FAIXA_MORTA_MAX_PX == 40
    assert gate_insert.INSTANTES == 6


# =================================================================================== densidade (45 a 55%, piso 40, teto 65)

@pytest.mark.parametrize("fracao", [0.45, 0.50, 0.55])
def test_densidade_na_faixa_passa_e_o_resultado_esta_no_formato_do_laudo(fracao):
    g = rodar(timeline=timeline_com_densidade(fracao), plano=plano())
    assert g["nome"] == "gate_insert" and g["etapa"] == "depois"
    assert g["resultado"] == "PASS" and g["saida"] == 0, g.get("motivo")
    assert g["medido"]["densidade"]["fracao_insert"] == pytest.approx(fracao, abs=0.001)
    assert g["limiar"]["densidade"] == {"alvo_min": 0.45, "alvo_max": 0.55, "piso": 0.40, "teto": 0.65}
    assert formato_do_laudo(g) == []


@pytest.mark.parametrize("fracao", [0.42, 0.60, 0.40, 0.65])
def test_densidade_fora_do_alvo_sem_excecao_reprova(fracao):
    g = rodar(timeline=timeline_com_densidade(fracao), plano=plano())
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert "densidade" in g["motivo"] and "45" in g["motivo"] and "55" in g["motivo"]
    assert "projeto.json" in g["motivo"] and "excecoes" in g["motivo"]
    assert formato_do_laudo(g) == []


@pytest.mark.parametrize("fracao", [0.42, 0.60])
def test_densidade_fora_do_alvo_com_excecao_declarada_passa_e_registra_o_motivo(fracao):
    g = rodar(timeline=timeline_com_densidade(fracao), plano=plano(), projeto=projeto(excecoes=[EXC_DENSIDADE]))
    assert g["resultado"] == "PASS", g.get("motivo")
    assert g["medido"]["densidade"]["excecao"] == EXC_DENSIDADE["motivo"]


@pytest.mark.parametrize("fracao,palavra", [(0.30, "piso"), (0.70, "teto")])
def test_abaixo_do_piso_ou_acima_do_teto_reprova_ate_com_excecao(fracao, palavra):
    g = rodar(timeline=timeline_com_densidade(fracao), plano=plano(), projeto=projeto(excecoes=[EXC_DENSIDADE]))
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert palavra in g["motivo"]


def test_excecao_de_outra_regra_nao_vale_para_a_densidade():
    outra = {"regra": "gate_cor", "motivo": "abertura escura de propósito"}
    g = rodar(timeline=timeline_com_densidade(0.42), plano=plano(), projeto=projeto(excecoes=[outra]))
    assert g["resultado"] == "REPROVA"


def test_sem_timeline_a_densidade_vem_do_plano():
    g = rodar(plano=plano(fracao=0.42))
    assert g["resultado"] == "REPROVA" and g["medido"]["densidade"]["fonte"] == "plano"
    g2 = rodar(plano=plano(fracao=0.50))
    assert g2["resultado"] == "PASS"


def test_modo_sem_inserts_por_desenho_nao_cobra_densidade():
    g = rodar(timeline=timeline_com_densidade(0.0), plano=plano(), projeto=projeto(modo="gravado"))
    assert g["resultado"] == "PASS", g.get("motivo")
    assert g["medido"]["densidade"]["estado"] == "PULADO" and "gravado" in g["medido"]["densidade"]["motivo"]


# =================================================================================== congelamento (até 0,20 s)

@pytest.mark.parametrize("congela,ok", [(0.0, True), (0.20, True), (0.21, False), (0.25, False), (1.4, False)])
def test_congelamento_acima_de_0_20s_reprova(congela, ok):
    p = plano(mapa=[mapa_item("painel", congela_s=congela), mapa_item("planilha", blocos=(3,))])
    g = rodar(timeline=timeline_com_densidade(0.5), plano=p)
    assert (g["resultado"] == "PASS") is ok, g.get("motivo")
    if not ok:
        assert g["saida"] == 1 and "congela" in g["motivo"] and "painel" in g["motivo"] and "0.2" in g["motivo"]
        assert g["medido"]["congelamento"]["maior"]["chave"] == "painel"


# =================================================================================== horizontal recortado (plano)

@pytest.mark.parametrize("tratamento", ["cheio", "imagem", "pip"])
def test_insert_horizontal_sem_moldura_no_plano_reprova(tratamento):
    p = plano(mapa=[mapa_item(tratamento=tratamento)])
    g = rodar(timeline=timeline_com_densidade(0.5), plano=p)
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert "horizontal" in g["motivo"] and "moldura" in g["motivo"] and "painel" in g["motivo"]


@pytest.mark.parametrize("tratamento", ["moldura", "split"])
def test_insert_horizontal_em_moldura_ou_split_passa(tratamento):
    g = rodar(timeline=timeline_com_densidade(0.5), plano=plano(mapa=[mapa_item(tratamento=tratamento)]))
    assert g["resultado"] == "PASS", g.get("motivo")


def test_insert_vertical_em_tela_cheia_nao_precisa_de_moldura():
    p = plano(mapa=[mapa_item(largura=720, altura=1280, tratamento="cheio")])
    g = rodar(timeline=timeline_com_densidade(0.5), plano=p)
    assert g["resultado"] == "PASS", g.get("motivo")


# =================================================================================== quadros do motor de verdade

@pytest.fixture(scope="module")
def oficina(tmp_path_factory):
    """Assets e quadros compostos pelos filtros do motor (uma vez por módulo)."""
    tmp = tmp_path_factory.mktemp("insert")

    def ff(*args):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", *args], check=True, capture_output=True)

    asset = tmp / "asset.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(asset))
    avatar = tmp / "avatar.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(avatar))
    # asset que começa colorido (vira o fundo congelado) e depois fica preto: o INTERIOR do card é liso, o fundo não
    escuro = tmp / "escuro_depois.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=0.2", "-f", "lavfi", "-i",
       "color=c=black:s=1280x720:r=30:d=2.5", "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0,format=yuv420p[v]",
       "-map", "[v]", "-c:v", "libx264", str(escuro))
    molduras = str(tmp / "molduras")

    def quadro_cheio(src, t=0.5, nome="cheio"):
        asp = enq.aspecto(str(src))
        m, png = FI.moldura_cheia(asp, molduras)
        fc = FI.fc_tela_cheia_moldura(1.0, 0.0, "", m, png, "", 90)
        out = tmp / ("%s.png" % nome)
        ff("-i", str(src), "-filter_complex", fc, "-map", "[v]", "-ss", str(t), "-frames:v", "1", str(out))
        return out

    def quadro_split(src, nome="split"):
        painel = FI.painel_mockup(str(src), "", 0, 0.0, molduras)
        fc = FI.fc_split_tela(1.0, "", painel, FA.filtro_avatar_split(0.30), 30)
        out = tmp / ("%s.png" % nome)
        ff("-i", str(src), "-i", str(avatar), "-filter_complex", fc, "-map", "[v]", "-frames:v", "1", str(out))
        return out

    def recortado(src, nome="recortado"):
        out = tmp / ("%s.png" % nome)
        ff("-i", str(src), "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
           "-frames:v", "1", str(out))
        return out

    def graduar(png, nome):
        """A grade final do motor (grão 7, contraste, saturação, vinheta) + h264 crf 18, num quadro só."""
        mp4, saida = tmp / ("%s_g.mp4" % nome), tmp / ("%s_g.png" % nome)
        ff("-loop", "1", "-framerate", "30", "-i", str(png), "-t", "1", "-filter_complex", GF.FILTRO_GRADE,
           "-map", "[v]", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(mp4))
        ff("-i", str(mp4), "-ss", "0.5", "-frames:v", "1", str(saida))
        return saida

    def com_faixa_preta(png, y0, altura, nome):
        im = Image.open(png).convert("RGB")
        im.paste((0, 0, 0), (0, y0, im.width, y0 + altura))
        saida = tmp / ("%s.png" % nome)
        im.save(saida)
        return saida

    return {"tmp": tmp, "asset": asset, "cheio": quadro_cheio(asset), "split": quadro_split(asset),
            "recortado": recortado(asset), "cheio_interior_preto": quadro_cheio(escuro, t=1.5, nome="cheio_escuro"),
            "ff": ff, "graduar": graduar, "com_faixa_preta": com_faixa_preta}


def meio(png):
    """Quadro em meia resolução (540x960 RGB uint8), o que o gate mede."""
    return np.array(Image.open(png).convert("RGB").resize((540, 960), Image.BOX))


def leitor_de(*quadros):
    def leitor(video, instantes):
        return [quadros[i % len(quadros)] for i, _ in enumerate(instantes)]
    return leitor


def tl_de_layout(layout, total=20.0):
    return timeline_com_densidade(0.5, total, layout)


def com_faixa(quadro, y0, altura_px, cor=(4, 4, 4), grao=0):
    """Pinta uma faixa lisa de largura inteira (y0 e altura em px do quadro 1080x1920). Com `grao`, soma o
    ruído uniforme de +-grao níveis que a grade final (noise=alls=7) põe em tudo, seed fixa."""
    q = quadro.copy()
    y_a, y_b = y0 // 2, (y0 + altura_px) // 2
    faixa = np.full((y_b - y_a, q.shape[1], 3), cor, dtype=np.float32)
    if grao:
        faixa += np.random.RandomState(7).uniform(-grao, grao, faixa.shape)
    q[y_a:y_b, :, :] = np.clip(faixa, 0, 255).astype(np.uint8)
    return q


def test_o_quadro_real_do_motor_nao_tem_faixa_morta_e_tem_a_moldura(oficina):
    for layout in ("cheio", "split"):
        q = meio(oficina[layout])
        g = rodar(timeline=tl_de_layout(layout), plano=plano_do_layout(layout), video="x.mp4", leitor=leitor_de(q))
        assert g["resultado"] == "PASS", (layout, g.get("motivo"))
        fm = g["medido"]["faixa_morta"]
        assert len(fm["instantes"]) == 6 and fm["maior_px"] <= 40
        assert all(i["moldura"] is True for i in fm["instantes"])
        assert formato_do_laudo(g) == []


def test_a_geometria_do_gate_acha_os_pontos_da_moldura_onde_o_motor_os_desenha(oficina):
    for layout in ("cheio", "split"):
        geo = gate_insert.geometria_do_card(layout, 1280 / 720.0)
        q = meio(oficina[layout])
        assert gate_insert.moldura_presente(q, geo), layout
        # um quadro sem moldura não tem os pontos
        assert not gate_insert.moldura_presente(meio(oficina["recortado"]), geo)


@pytest.mark.parametrize("layout", ["cheio", "split"])
def test_mutante_faixa_morta_de_60px_no_fundo_reprova(oficina, layout):
    q = com_faixa(meio(oficina[layout]), 40, 60)              # acima do card nos dois layouts
    g = rodar(timeline=tl_de_layout(layout), plano=plano_do_layout(layout), video="x.mp4", leitor=leitor_de(q))
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert "faixa morta" in g["motivo"] and "40 px" in g["motivo"]
    assert g["medido"]["faixa_morta"]["maior_px"] >= 60
    assert formato_do_laudo(g) == []


def test_faixa_de_40px_ainda_passa_e_de_42px_reprova(oficina):
    base = meio(oficina["cheio"])
    g40 = rodar(timeline=tl_de_layout("cheio"), plano=plano(), video="x.mp4",
                leitor=leitor_de(com_faixa(base, 100, 40)))
    assert g40["resultado"] == "PASS", g40.get("motivo")
    g42 = rodar(timeline=tl_de_layout("cheio"), plano=plano(), video="x.mp4",
                leitor=leitor_de(com_faixa(base, 100, 42)))
    assert g42["resultado"] == "REPROVA" and g42["medido"]["faixa_morta"]["maior_px"] == 42


def test_faixa_morta_em_um_so_dos_6_instantes_reprova(oficina):
    ok, ruim = meio(oficina["cheio"]), com_faixa(meio(oficina["cheio"]), 1660, 80)   # abaixo do card (que vai até ~1632)
    g = rodar(timeline=tl_de_layout("cheio"), plano=plano(), video="x.mp4", leitor=leitor_de(ok, ok, ok, ok, ok, ruim))
    assert g["resultado"] == "REPROVA"
    assert [i["faixa_morta_px"] > 40 for i in g["medido"]["faixa_morta"]["instantes"]].count(True) == 1


def test_faixa_morta_com_o_grao_da_grade_final_ainda_e_pega(oficina):
    """A grade final põe ruído de +-7 em tudo: o preto liso entregue não tem desvio zero."""
    q = com_faixa(meio(oficina["cheio"]), 100, 80, cor=(5, 5, 5), grao=7)
    g = rodar(timeline=tl_de_layout("cheio"), plano=plano(), video="x.mp4", leitor=leitor_de(q))
    assert g["resultado"] == "REPROVA" and g["medido"]["faixa_morta"]["maior_px"] >= 80


@pytest.mark.parametrize("cor", [(230, 230, 230), (60, 60, 60), (24, 24, 24)])
def test_faixa_lisa_que_nao_e_preta_nao_e_faixa_morta(oficina, cor):
    """Página branca e fundo desfocado claro são o desenho do motor; só preto liso é faixa morta."""
    q = com_faixa(meio(oficina["cheio"]), 100, 200, cor=cor, grao=3)
    g = rodar(timeline=tl_de_layout("cheio"), plano=plano(), video="x.mp4", leitor=leitor_de(q))
    assert g["resultado"] == "PASS", g.get("motivo")


@pytest.mark.parametrize("layout", ["cheio", "split"])
def test_a_grade_final_nao_esconde_a_moldura_e_o_quadro_real_segue_passando(oficina, layout):
    """Depois da grade (grão, vinheta, h264) o vermelho do ponto já não é (255, 95, 86): a moldura se acha pelo matiz."""
    q = meio(oficina["graduar"](oficina[layout], layout))
    g = rodar(timeline=tl_de_layout(layout), plano=plano_do_layout(layout), video="x.mp4", leitor=leitor_de(q))
    assert g["resultado"] == "PASS", g.get("motivo")
    assert all(i["moldura"] for i in g["medido"]["faixa_morta"]["instantes"])


def test_faixa_preta_de_80px_sobrevive_a_grade_final(oficina):
    png = oficina["com_faixa_preta"](oficina["cheio"], 100, 80, "cheio_faixa")
    q = meio(oficina["graduar"](png, "cheio_faixa"))
    g = rodar(timeline=tl_de_layout("cheio"), plano=plano(), video="x.mp4", leitor=leitor_de(q))
    assert g["resultado"] == "REPROVA" and g["medido"]["faixa_morta"]["maior_px"] == 80


def test_horizontal_recortado_depois_da_grade_continua_sem_moldura(oficina):
    q = meio(oficina["graduar"](oficina["recortado"], "recortado"))
    g = rodar(timeline=tl_de_layout("cheio"), plano=plano(), video="x.mp4", leitor=leitor_de(q))
    assert g["resultado"] == "REPROVA" and "moldura" in g["motivo"]


def test_o_interior_liso_do_card_nao_e_faixa_morta(oficina):
    """Terminal preto dentro da moldura: o card tem 580 px de preto liso e isso é conteúdo, não defeito."""
    q = meio(oficina["cheio_interior_preto"])
    g = rodar(timeline=tl_de_layout("cheio"), plano=plano(), video="x.mp4", leitor=leitor_de(q))
    assert g["resultado"] == "PASS", g.get("motivo")


def test_o_painel_do_avatar_no_split_nao_entra_na_conta(oficina):
    q = meio(oficina["split"])
    q[(FA.SPLIT_TOP_H // 2):, :, :] = 20                       # o avatar embaixo, liso: não é do insert
    g = rodar(timeline=tl_de_layout("split"), plano=plano_do_layout("split"), video="x.mp4", leitor=leitor_de(q))
    assert g["resultado"] == "PASS", g.get("motivo")


def test_mutante_horizontal_recortado_sem_moldura_reprova(oficina):
    q = meio(oficina["recortado"])
    g = rodar(timeline=tl_de_layout("cheio"), plano=plano(), video="x.mp4", leitor=leitor_de(q))
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert "moldura" in g["motivo"] and "recortado" in g["motivo"]
    assert all(i["moldura"] is False for i in g["medido"]["faixa_morta"]["instantes"])


def test_insert_vertical_nao_precisa_da_moldura_no_quadro(oficina):
    q = meio(oficina["recortado"])
    p = plano(mapa=[mapa_item(largura=720, altura=1280, tratamento="cheio")])
    g = rodar(timeline=tl_de_layout("cheio"), plano=p, video="x.mp4", leitor=leitor_de(q))
    assert g["resultado"] == "PASS", g.get("motivo")


def test_instantes_ficam_dentro_dos_inserts_longe_da_transicao():
    tl = timeline_com_densidade(0.5)
    ins = gate_insert.instantes_de_amostra(tl)
    assert len(ins) == 6
    seg = tl["segmentos"][1]
    assert all(seg["s"] + 0.25 <= i["t"] <= seg["e"] - 0.25 for i in ins)
    assert all(i["segmento"] == 1 for i in ins)
    assert ins == sorted(ins, key=lambda i: i["t"])
    assert gate_insert.instantes_de_amostra(timeline_com_densidade(0.0)) == []


def test_instantes_em_tempo_entregue_dividem_pela_aceleracao():
    tl = timeline_com_densidade(0.5)
    tl["relogio"]["aceleracao"] = 1.35
    ins = gate_insert.instantes_de_amostra(tl)
    seg = tl["segmentos"][1]
    assert all(seg["s"] / 1.35 <= i["t"] <= seg["e"] / 1.35 for i in ins)


# =================================================================================== vídeo de verdade (o leitor padrão)

@pytest.fixture(scope="module")
def videos(oficina):
    tmp, ff = oficina["tmp"], oficina["ff"]

    def de_quadro(png, nome):
        out = tmp / nome
        ff("-loop", "1", "-framerate", "10", "-i", str(png), "-t", "21", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-crf", "14", str(out))
        return out
    return {"ok": de_quadro(oficina["cheio"], "ok.mp4"), "recortado": de_quadro(oficina["recortado"], "recortado.mp4")}


def test_leitor_padrao_decodifica_o_video_e_passa(videos):
    g = rodar(timeline=tl_de_layout("cheio"), plano=plano(), video=videos["ok"])
    assert g["resultado"] == "PASS", g.get("motivo")
    assert all(i["moldura"] for i in g["medido"]["faixa_morta"]["instantes"])


def test_leitor_padrao_pega_o_horizontal_recortado(videos):
    g = rodar(timeline=tl_de_layout("cheio"), plano=plano(), video=videos["recortado"])
    assert g["resultado"] == "REPROVA" and "moldura" in g["motivo"]


# =================================================================================== insumo inválido

def test_sem_plano_nem_timeline_e_erro():
    g = gate_insert.rodar(projeto=projeto())
    assert g["resultado"] == "ERRO" and g["saida"] == 2
    assert formato_do_laudo(g) == []


def test_video_sem_plano_e_erro_porque_o_aspecto_do_insert_vem_do_plano(videos):
    g = gate_insert.rodar(timeline=tl_de_layout("cheio"), projeto=projeto(), video=videos["ok"])
    assert g["resultado"] == "ERRO" and g["saida"] == 2 and "plano" in g["motivo"]


def test_video_ausente_e_erro():
    g = rodar(timeline=tl_de_layout("cheio"), plano=plano(), video="/nao/existe.mp4")
    assert g["resultado"] == "ERRO" and g["saida"] == 2 and "não existe" in g["motivo"]


def test_leitor_que_quebra_vira_erro(oficina):
    def quebrado(video, instantes):
        raise OSError("ffmpeg não leu o quadro")
    g = rodar(timeline=tl_de_layout("cheio"), plano=plano(), video="x.mp4", leitor=quebrado)
    assert g["resultado"] == "ERRO" and g["saida"] == 2 and "ffmpeg" in g["motivo"]


def test_plano_sem_mapa_de_inserts_e_erro():
    p = plano()
    del p["mapa_inserts"]
    g = rodar(timeline=timeline_com_densidade(0.5), plano=p)
    assert g["resultado"] == "ERRO" and "mapa_inserts" in g["motivo"]


# =================================================================================== linha de comando

def test_cli_devolve_0_1_2(tmp_path, capsys):
    (tmp_path / "timeline.json").write_text(json.dumps(timeline_com_densidade(0.5)), encoding="utf-8")
    (tmp_path / "plano.json").write_text(json.dumps(plano()), encoding="utf-8")
    (tmp_path / "projeto.json").write_text(json.dumps(projeto()), encoding="utf-8")
    base = ["--timeline", str(tmp_path / "timeline.json"), "--plano", str(tmp_path / "plano.json"),
            "--projeto", str(tmp_path / "projeto.json")]
    assert gate_insert.main(base) == 0
    assert "PASSA" in capsys.readouterr().out
    (tmp_path / "timeline.json").write_text(json.dumps(timeline_com_densidade(0.3)), encoding="utf-8")
    assert gate_insert.main(base) == 1
    assert "REPROVA" in capsys.readouterr().out
    assert gate_insert.main(["--timeline", str(tmp_path / "nao.json")]) == 2


# =================================================================================== W7.Z: a chave do insert e o layout efetivo

def plano_com_blocos(chave="painel", tratamento="moldura", bloco=1):
    p = plano([mapa_item(chave, blocos=(bloco,), tratamento=tratamento)])
    p["blocos"] = [{"i": 0, "tipo": "apresentador", "fala": "x", "s": 0.0, "e": 5.0},
                   {"i": bloco, "tipo": "insert", "insert": chave, "layout": "cheio", "fala": "y", "s": 5.0, "e": 15.0}]
    return p


def tl_com_chave_numerica(layout=None, total=20.0):
    """A timeline REAL guarda no bloco o número do insert no inserts.json ("1", "2"...), não a chave do roteiro."""
    tl = tl_de_layout(layout or "cheio", total)
    for b in tl["blocos"]:
        if b["tipo"] == "insert":
            b["insert"] = "1"
    if layout is None:
        for sg in tl["segmentos"]:
            sg.pop("layout", None)
    return tl


def test_timeline_com_chave_numerica_e_medida_pela_chave_do_plano(oficina):
    """O gate passou cego na prova: a chave do bloco na timeline ("1") nunca casava com a do plano ("painel") e as 6
    amostras saíam com faixa_morta_px = null. O bloco do insert se acha pelo índice, no plano."""
    q = com_faixa(meio(oficina["cheio"]), 40, 60)
    g = rodar(timeline=tl_com_chave_numerica("cheio"), plano=plano_com_blocos(), video="x.mp4", leitor=leitor_de(q))
    inst = g["medido"]["faixa_morta"]["instantes"]
    assert all(i["faixa_morta_px"] is not None for i in inst)
    assert g["resultado"] == "REPROVA" and "faixa morta" in g["motivo"]


def test_layout_ausente_no_segmento_vale_pelo_tratamento_do_plano(oficina):
    """Insert de visita única (sem layout no segmento) em moldura é tela cheia: tem que ser medido, não pulado."""
    q = meio(oficina["cheio"])
    g = rodar(timeline=tl_com_chave_numerica(None), plano=plano_com_blocos(), video="x.mp4", leitor=leitor_de(q))
    inst = g["medido"]["faixa_morta"]["instantes"]
    assert all(i["faixa_morta_px"] is not None and i["moldura"] is True for i in inst), inst
    assert g["resultado"] == "PASS", g.get("motivo")


def test_insert_em_moldura_e_sempre_cheio_mesmo_que_o_ritmo_diga_split(oficina):
    """`inserts.json` sem `split: true` (cheio explícito) renderiza tela cheia em toda visita: o `layout: split` do ritmo
    nesse bloco não vale, e medir como split dava a geometria errada."""
    q = meio(oficina["cheio"])
    g = rodar(timeline=tl_com_chave_numerica("split"), plano=plano_com_blocos(tratamento="moldura"), video="x.mp4",
              leitor=leitor_de(q))
    assert {i["layout"] for i in g["medido"]["faixa_morta"]["instantes"]} == {"cheio"}
    assert g["resultado"] == "PASS", g.get("motivo")


def test_insert_em_split_segue_o_layout_do_ritmo_e_o_split_vale_por_padrao_sem_layout(oficina):
    q = meio(oficina["split"])
    g = rodar(timeline=tl_com_chave_numerica("split"), plano=plano_com_blocos(tratamento="split"), video="x.mp4",
              leitor=leitor_de(q))
    assert {i["layout"] for i in g["medido"]["faixa_morta"]["instantes"]} == {"split"}
    assert g["resultado"] == "PASS", g.get("motivo")
    g2 = rodar(timeline=tl_com_chave_numerica(None), plano=plano_com_blocos(tratamento="split"), video="x.mp4",
               leitor=leitor_de(q))
    assert {i["layout"] for i in g2["medido"]["faixa_morta"]["instantes"]} == {"split"}


def test_card_da_tela_cheia_ocupa_70_por_cento_do_quadro_na_geometria_do_gate():
    geo = gate_insert.geometria_do_card("cheio", 1280 / 644.0)
    assert geo["base"] - geo["topo"] >= 0.70 * 1920
    assert all(b - a <= 300 for a, b in geo["regioes"])      # o que sobra em volta do card é só a margem


def test_o_caso_da_folha_card_pequeno_no_meio_de_fundo_escuro_reprova(oficina):
    """Os quadros de 5,5 s, 15,5 s e 35 s: um card de ~600 px no meio e o resto preto liso. Medido como cheio, sobra
    uma faixa morta de centenas de px em cima e embaixo do card (geometria nova: o card tem que chegar perto das bordas)."""
    q = np.zeros((960, 540, 3), dtype=np.uint8)
    q[330:630, 20:520, :] = 140                              # um card pequeno no meio (em meia resolução)
    g = rodar(timeline=tl_com_chave_numerica("cheio"), plano=plano_com_blocos(), video="x.mp4", leitor=leitor_de(q))
    assert g["resultado"] == "REPROVA" and "faixa morta" in g["motivo"]
    assert g["medido"]["faixa_morta"]["maior_px"] > 200
