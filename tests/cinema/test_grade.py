"""W4.C: grade de cor (C5). Os 4 presets geram filtros determinísticos, o padrão (quente-suave) é
IDÊNTICO ao filtro que o motor sempre aplicou (a paridade com o dono depende disso), a saída leva
bt709 nas três tags e o mostruário mostra os 4 presets lado a lado, com o nome escrito.
"""
import json
import subprocess

import pytest
from PIL import Image

from cinema import grade, mostruario_grade
from footage import grade_final as GF
from projeto import modelo
from tests.fixtures import sinteticos as S

TAG_BT709 = "colorspace=all=bt709:iall=bt709:fast=1"

# Strings golden: mudar um preset é decisão consciente, e o teste obriga a mexer aqui também.
GOLDEN = {
    "quente-suave": ("[0:v]noise=alls=7:allf=t+u,eq=contrast=1.03:saturation=0.97,vignette=PI/5.5,"
                     "colorspace=all=bt709:iall=bt709:fast=1[v]"),
    "natural": ("[0:v]noise=alls=5:allf=t+u,eq=contrast=1.01:saturation=1.0,vignette=PI/4,"
                "colorspace=all=bt709:iall=bt709:fast=1[v]"),
    "frio-teal": ("[0:v]noise=alls=7:allf=t+u,eq=contrast=1.04:saturation=0.95,"
                  "colorbalance=rs=-0.05:bs=0.06:rm=-0.04:bm=0.05:rh=-0.03:bh=0.04,vignette=PI/6,"
                  "colorspace=all=bt709:iall=bt709:fast=1[v]"),
    "pb": ("[0:v]noise=alls=7:allf=t+u,hue=s=0,eq=contrast=1.08,vignette=PI/6,"
           "colorspace=all=bt709:iall=bt709:fast=1[v]"),
}

# O filtro de ANTES da W4.C (grade_final.FILTRO_GRADE da W2.B, fixture de paridade 2ebd1cc).
FILTRO_DE_HOJE = ("[0:v]noise=alls=7:allf=t+u,eq=contrast=1.03:saturation=0.97,vignette=PI/5.5,"
                  "colorspace=all=bt709:iall=bt709:fast=1[v]")


# --- filtros determinísticos ---------------------------------------------------------------

def test_os_quatro_presets_existem_na_ordem_do_mostruario():
    assert grade.nomes() == ("quente-suave", "natural", "frio-teal", "pb")
    assert grade.PADRAO == "quente-suave"


@pytest.mark.parametrize("nome", sorted(GOLDEN))
def test_filtro_de_cada_preset_e_o_golden(nome):
    assert grade.filtro(nome) == GOLDEN[nome]


def test_quente_suave_e_identico_ao_filtro_de_hoje():
    assert grade.filtro("quente-suave") == FILTRO_DE_HOJE
    assert GF.FILTRO_GRADE == FILTRO_DE_HOJE


def test_sem_preset_vale_o_padrao():
    assert grade.filtro() == grade.filtro(None) == grade.filtro("quente-suave") == FILTRO_DE_HOJE


@pytest.mark.parametrize("nome", sorted(GOLDEN))
def test_filtro_e_determinista(nome):
    assert grade.filtro(nome) == grade.filtro(nome)
    assert grade.cadeia(nome) == grade.cadeia(nome)


@pytest.mark.parametrize("nome", sorted(GOLDEN))
def test_todo_preset_fecha_com_a_tag_bt709_e_fica_entre_os_rotulos(nome):
    f = grade.filtro(nome)
    assert f.startswith("[0:v]") and f.endswith("[v]")
    assert grade.cadeia(nome).endswith(TAG_BT709)
    assert f == "[0:v]" + grade.cadeia(nome) + "[v]"


def test_presets_sao_todos_diferentes():
    assert len({grade.filtro(n) for n in grade.nomes()}) == 4


def test_preset_desconhecido_diz_quais_existem():
    with pytest.raises(grade.GradeDesconhecida) as e:
        grade.filtro("sepia")
    msg = str(e.value)
    assert "sepia" in msg
    for nome in grade.nomes():
        assert nome in msg
    assert isinstance(e.value, ValueError)


def test_intencao_de_cada_preset_vem_dos_css_antigos():
    # natural: quase neutra, sem empurrar cor, vinheta mais leve (PI maior = vinheta mais fraca)
    assert "colorbalance" not in grade.cadeia("natural") and "saturation=1.0" in grade.cadeia("natural")
    assert "vignette=PI/4" in grade.cadeia("natural")
    # frio-teal: tira vermelho e põe azul nas sombras, nos meios e nas altas
    frio = grade.cadeia("frio-teal")
    assert "rs=-0.05" in frio and "bs=0.06" in frio and "rh=-0.03" in frio and "bh=0.04" in frio
    # pb: dessatura de vez, contraste leve, vinheta um pouco mais forte que a quente
    assert "hue=s=0" in grade.cadeia("pb") and "vignette=PI/6" in grade.cadeia("pb")


def test_descricao_de_cada_preset_existe_para_o_mostruario():
    for nome in grade.nomes():
        assert isinstance(grade.descricao(nome), str) and len(grade.descricao(nome)) > 10


# --- escolha no projeto --------------------------------------------------------------------

def test_do_projeto_sem_estilo_e_o_padrao():
    assert grade.do_projeto({"modo": "avatar"}) == "quente-suave"
    assert grade.do_projeto({"estilo": {}}) == "quente-suave"


def test_do_projeto_usa_estilo_grade():
    assert grade.do_projeto({"estilo": {"grade": "pb"}}) == "pb"


def test_do_projeto_valida_o_nome():
    with pytest.raises(grade.GradeDesconhecida):
        grade.do_projeto({"estilo": {"grade": "sepia"}})


def test_projeto_json_com_estilo_grade_normalizado_alimenta_o_filtro():
    p = modelo.normalizar(modelo.minimo("anuncio", "gravado", sem_trilha="sem trilha no teste")
                          | {"estilo": {"grade": "frio-teal"}})
    assert grade.filtro(grade.do_projeto(p)) == GOLDEN["frio-teal"]


# --- grade_final pede o filtro ao cinema.grade ---------------------------------------------

def test_grade_final_sem_preset_mantem_o_argv_de_hoje():
    cmd = GF.cmd_grade_final("v.mp4", 0.62, 17.68, "a.mp4", "o.mp4")
    assert cmd[cmd.index("-filter_complex") + 1] == FILTRO_DE_HOJE


@pytest.mark.parametrize("nome", ["natural", "frio-teal", "pb"])
def test_grade_final_com_preset_so_troca_o_filtro(nome):
    base = GF.cmd_grade_final("v.mp4", 0.62, 17.68, "a.mp4", "o.mp4")
    outro = GF.cmd_grade_final("v.mp4", 0.62, 17.68, "a.mp4", "o.mp4", preset=nome)
    i = base.index("-filter_complex") + 1
    assert outro[i] == GOLDEN[nome] and outro[i] != base[i]
    assert outro[:i] == base[:i] and outro[i + 1:] == base[i + 1:]


def test_grade_final_recusa_preset_desconhecido_antes_de_rodar_o_ffmpeg(monkeypatch):
    chamado = []
    monkeypatch.setattr(GF, "run", lambda c: chamado.append(c))
    with pytest.raises(grade.GradeDesconhecida):
        GF.aplicar("v.mp4", 0.0, 1.0, "a.mp4", "o.mp4", preset="sepia")
    assert chamado == []


def test_grade_final_aplicar_repassa_o_preset(monkeypatch):
    cmds = []
    monkeypatch.setattr(GF, "run", lambda c: cmds.append([str(x) for x in c]))
    GF.aplicar("v.mp4", 0.0, 1.0, "a.mp4", "o.mp4", preset="pb")
    assert cmds[0][cmds[0].index("-filter_complex") + 1] == GOLDEN["pb"]


# --- render de 1 s ---------------------------------------------------------------------------

def _tags(arq):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=color_space,color_transfer,color_primaries,color_range", "-of", "json",
                        str(arq)], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)["streams"][0]


def _cor_media(arq, t=0.5):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(arq), "-frames:v", "1",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    larg = int(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                               "stream=width", "-of", "csv=p=0", str(arq)], capture_output=True,
                              text=True, check=True).stdout.strip().rstrip(","))
    im = Image.frombytes("RGB", (larg, len(r.stdout) // 3 // larg), r.stdout)
    # centro do quadro: a vinheta escurece só as bordas
    w, h = im.size
    medio = im.crop((w // 3, h // 3, 2 * w // 3, 2 * h // 3)).resize((1, 1), Image.BOX).getpixel((0, 0))
    return medio


@pytest.fixture(scope="module")
def fonte_1s(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("grade")
    # cor de pele chapada (vermelho e verde altos, azul baixo), com áudio, 1 s
    ff = ["ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
          "color=c=0xC89078:s=180x320:r=25:d=1", "-f", "lavfi", "-i",
          "sine=frequency=440:sample_rate=48000:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-shortest", str(pasta / "fonte.mp4")]
    S.exigir_ffmpeg()
    subprocess.run(ff, check=True)
    return pasta / "fonte.mp4"


@pytest.mark.lento
@pytest.mark.parametrize("nome", ["quente-suave", "natural", "frio-teal", "pb"])
def test_render_de_1s_sai_com_bt709_nas_tres_tags(fonte_1s, tmp_path, nome):
    saida = tmp_path / ("saida_%s.mp4" % nome)
    GF.aplicar(str(fonte_1s), 0.0, 1.0, str(fonte_1s), str(saida), preset=nome)
    t = _tags(saida)
    assert t.get("color_space") == "bt709"
    assert t.get("color_transfer") == "bt709"
    assert t.get("color_primaries") == "bt709"
    assert t.get("color_range") == "tv"


@pytest.mark.lento
def test_render_padrao_sem_preset_tambem_sai_bt709(fonte_1s, tmp_path):
    saida = tmp_path / "padrao.mp4"
    GF.aplicar(str(fonte_1s), 0.0, 1.0, str(fonte_1s), str(saida))
    t = _tags(saida)
    assert (t["color_space"], t["color_transfer"], t["color_primaries"]) == ("bt709",) * 3


@pytest.mark.lento
def test_os_presets_mudam_a_imagem_do_jeito_que_dizem(fonte_1s, tmp_path):
    medias = {}
    for nome in grade.nomes():
        saida = tmp_path / ("m_%s.mp4" % nome)
        GF.aplicar(str(fonte_1s), 0.0, 1.0, str(fonte_1s), str(saida), preset=nome)
        medias[nome] = _cor_media(saida)
    r_q, g_q, b_q = medias["quente-suave"]
    r_f, g_f, b_f = medias["frio-teal"]
    # frio-teal puxa para o azul: mais azul e menos vermelho que a quente
    assert b_f > b_q + 3 and r_f < r_q - 3
    # pb: sem cor nenhuma (R, G e B praticamente iguais)
    r_p, g_p, b_p = medias["pb"]
    assert max(r_p, g_p, b_p) - min(r_p, g_p, b_p) <= 4
    # natural fica mais saturada que a quente-suave (saturação 1.0 contra 0,97)
    sat = lambda c: max(c) - min(c)
    assert sat(medias["natural"]) >= sat(medias["quente-suave"])


# --- mostruário ------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def video_qualquer(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("mostruario")
    return S.testsrc_com_audio(pasta / "qualquer.mp4", dur=2.0, tamanho="160x284")


def test_mostruario_gera_png_com_4_paineis_lado_a_lado(video_qualquer, tmp_path):
    saida = tmp_path / "mostruario.png"
    r = mostruario_grade.gerar(video_qualquer, saida, altura=284)
    assert r == saida and saida.exists()
    im = Image.open(saida)
    assert im.format == "PNG"
    pw = mostruario_grade.largura_do_painel(160, 284, 284)
    assert im.width == 4 * pw
    assert im.height == 284 + mostruario_grade.FAIXA_ALTURA


def _painel(im, k, pw, altura):
    return im.convert("RGB").crop((k * pw, 0, (k + 1) * pw, altura))


def test_os_quatro_paineis_sao_graduacoes_diferentes_do_mesmo_quadro(video_qualquer, tmp_path):
    saida = mostruario_grade.gerar(video_qualquer, tmp_path / "m.png", altura=284)
    im = Image.open(saida)
    pw = mostruario_grade.largura_do_painel(160, 284, 284)
    paineis = [_painel(im, k, pw, 284) for k in range(4)]
    bytes_ = {p.tobytes() for p in paineis}
    assert len(bytes_) == 4
    # o pb não tem cor: em todo pixel os três canais são quase iguais
    pb = paineis[grade.nomes().index("pb")]
    desvio = max(max(px) - min(px) for px in pb.getdata())
    assert desvio <= 6


def test_cada_painel_traz_o_nome_do_preset_escrito(video_qualquer, tmp_path):
    saida = mostruario_grade.gerar(video_qualquer, tmp_path / "m.png", altura=284)
    im = Image.open(saida).convert("L")
    pw = mostruario_grade.largura_do_painel(160, 284, 284)
    faixas = []
    for k in range(4):
        faixa = im.crop((k * pw, 284, (k + 1) * pw, 284 + mostruario_grade.FAIXA_ALTURA))
        claros = sum(1 for v in faixa.getdata() if v > 160)
        assert claros >= 15, "painel %d (%s) sem texto na faixa do nome" % (k, grade.nomes()[k])
        faixas.append(faixa.tobytes())
    assert len(set(faixas)) == 4          # cada nome é diferente do outro
    assert mostruario_grade.legendas() == list(grade.nomes())


def test_mostruario_aceita_instante_e_recusa_video_inexistente(video_qualquer, tmp_path):
    ok = mostruario_grade.gerar(video_qualquer, tmp_path / "t.png", t=1.2, altura=284)
    assert ok.exists()
    with pytest.raises(mostruario_grade.MostruarioFalhou):
        mostruario_grade.gerar(tmp_path / "nao_existe.mp4", tmp_path / "x.png")


def test_mostruario_cli(video_qualquer, tmp_path, capsys):
    saida = tmp_path / "cli.png"
    rc = mostruario_grade.main([str(video_qualquer), str(saida), "--altura", "284"])
    assert rc == 0 and saida.exists()
    assert "quente-suave" in capsys.readouterr().out
    assert mostruario_grade.main([str(tmp_path / "nao.mp4"), str(tmp_path / "y.png")]) == 2
