"""One-shot no produto (W5.D): `vam oneshot <slug>`, o plano, a luz medida e o render único.

Take de câmera, uma tomada só, o apresentador falando direto para o celular. Não passa por HeyGen
nem tem roteiro em blocos: é edição de material cru, e a edição é a medição de cada passo:

  - CORTE: o ar morto sai pelas duas fontes que se corrigem (o vão entre palavras diz ONDE, a
    energia diz QUANTO), nunca por energia sozinha (comeu "você não comprou" de um anúncio inteiro);
  - ENQUADRE: janela 9:16 centrada no rosto medido (`enquadrar`);
  - LUZ: luminância medida vira brightness e contraste, e vira nada quando a imagem já está clara;
  - ACELERAÇÃO: a do `projeto.json` (padrão 1,2 em take real; o 1,35 do avatar foi reprovado de ouvido);
  - RENDER ÚNICO: corte, enquadre, luz, grade, velocidade e a caixa de lettering numa passada só;
  - GATES depois: a fala do bruto está inteira no final, a pausa maior no final e o técnico.
Saídas da CLI: 0 entregou · 1 algum gate reprovou · 2 pedido ou insumo inválido.
"""
import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from audio import loudness
from cinema import grade
from cli import oneshot as cli_oneshot
from gravado import gate_ar_morto
from gravado.veredito import InsumoInvalido
from oneshot import enquadrar, luz, montar
from projeto import modelo, novo, pastas
from tests.fixtures import sinteticos as fx
from tests.gravado import sintese as sx

BLOCOS = [(1.0, -12.0), (2.0, None), (1.5, -12.0)]            # fala, pausa de 2 s, fala: 4,5 s
PALAVRAS = [{"text": "um", "start": 0.05, "end": 0.5}, {"text": "dois", "start": 0.5, "end": 0.95},
            {"text": "três", "start": 3.05, "end": 3.5}, {"text": "quatro", "start": 3.5, "end": 4.4}]
ROSTO = (100, 40, 60, 60)                                     # centro em x = 130


def _take(destino, tamanho="320x180"):
    """Take sintético horizontal: vídeo cinza e o áudio por blocos (fala, pausa, fala)."""
    destino = Path(destino)
    wav = sx.audio_por_blocos(destino.with_name(destino.stem + "-fonte.wav"), BLOCOS)
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
                        "color=c=0x808080:s=%s:r=25:d=4.5" % tamanho, "-i", str(wav), "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-shortest",
                        str(destino)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return Path(destino)


def _projeto(estado, modo="oneshot", slug="take", aceleracao=None):
    if modo == "avatar":
        novo.criar(slug, modo, look="meu-look", sem_trilha="sem trilha no teste", estado=estado)
    else:
        novo.criar(slug, modo, sem_trilha="take único: a voz real segue sem trilha", estado=estado)
    pj = pastas.projeto(slug, estado)
    if aceleracao is not None:
        dados = json.loads(pj.projeto_json.read_text(encoding="utf-8"))
        dados["aceleracao"] = aceleracao
        modelo.escrever(pj.projeto_json, dados)
    return pj


class _Leitor(object):
    def __init__(self, palavras=PALAVRAS, texto_final=None):
        self.palavras_ = palavras
        self.texto_final = texto_final

    def palavras(self, audio, exigir_borda=False):
        return [dict(p) for p in self.palavras_]

    def texto_da_peca(self, arquivo):
        if self.texto_final is not None and "final" in Path(arquivo).name:
            return self.texto_final
        return " ".join(p["text"] for p in self.palavras_)


# --- a aceleração vem do projeto -----------------------------------------------------------------

def test_aceleracao_padrao_do_oneshot_e_1_2_lida_do_projeto_json(estado_vazio):
    pj = _projeto(estado_vazio)
    assert montar.aceleracao(montar.carregar_projeto(pj)) == 1.2
    assert json.loads(pj.projeto_json.read_text(encoding="utf-8"))["aceleracao"] == 1.2


def test_aceleracao_escolhida_no_projeto_json_vale(estado_vazio):
    pj = _projeto(estado_vazio, aceleracao=1.3)
    assert montar.aceleracao(montar.carregar_projeto(pj)) == 1.3


def test_projeto_que_nao_e_oneshot_ou_nao_existe_e_insumo_invalido(estado_vazio):
    avatar = _projeto(estado_vazio, modo="avatar", slug="com-avatar")
    with pytest.raises(InsumoInvalido) as e:
        montar.carregar_projeto(avatar)
    assert "oneshot" in str(e.value) and "avatar" in str(e.value)
    with pytest.raises(InsumoInvalido):
        montar.carregar_projeto(pastas.projeto("fantasma", estado_vazio))


# --- o plano -------------------------------------------------------------------------------------

def test_plano_corta_a_pausa_longa_enquadra_no_rosto_e_mede_a_luz(estado_vazio, tmp_path):
    pj = _projeto(estado_vazio)
    take = _take(tmp_path / "take.mp4")
    plano = montar.planejar(pj, take, _Leitor(), detector=lambda img: [ROSTO], medidor_luz=lambda t, j: 70.0)
    segs = plano["segmentos"]
    assert len(segs) == 2 and segs[0][0] == pytest.approx(0.0, abs=0.05)
    assert segs[0][1] > 0.95 and segs[1][0] < 3.05 and segs[1][1] == pytest.approx(4.5, abs=0.05)   # a fala inteira fica
    mantido = sum(b - a for a, b in segs)
    assert 2.6 <= mantido <= 3.2                                         # dos 4,5 s saem cerca de 1,7 s de ar morto
    assert plano["aceleracao"] == 1.2 and plano["dur_final"] == pytest.approx(mantido / 1.2, abs=0.01)
    assert plano["dur_bruto"] == pytest.approx(4.5, abs=0.05)
    j = plano["janela"]
    assert abs((j["x"] + j["w"] / 2.0) - 130) <= 10 and j["centrado_no_rosto"] is True
    assert plano["luz"]["brightness"] == pytest.approx(0.161, abs=0.002)
    assert plano["grade"] == grade.PADRAO and plano["avisos"] == []


def test_plano_sem_rosto_detectado_avisa_em_vez_de_chutar_calado(estado_vazio, tmp_path):
    pj = _projeto(estado_vazio)
    take = _take(tmp_path / "take.mp4")
    plano = montar.planejar(pj, take, _Leitor(), detector=lambda img: [], medidor_luz=lambda t, j: 130.0)
    assert plano["janela"]["centrado_no_rosto"] is False
    assert any("rosto" in a for a in plano["avisos"])
    assert plano["luz"]["brightness"] == 0.0


def test_plano_exige_tempo_de_palavra_real_do_transcritor(estado_vazio, tmp_path):
    pj = _projeto(estado_vazio)
    take = _take(tmp_path / "take.mp4")
    pedidos = []

    class Leitor(_Leitor):
        def palavras(self, audio, exigir_borda=False):
            pedidos.append(exigir_borda)
            return super().palavras(audio, exigir_borda)
    montar.planejar(pj, take, Leitor(), detector=lambda img: [ROSTO], medidor_luz=lambda t, j: 130.0)
    assert pedidos == [True]


def test_plano_escreve_o_json_dentro_do_projeto(estado_vazio, tmp_path):
    pj = _projeto(estado_vazio)
    take = _take(tmp_path / "take.mp4")
    plano = montar.planejar(pj, take, _Leitor(), detector=lambda img: [ROSTO], medidor_luz=lambda t, j: 130.0)
    arq = montar.salvar_plano(pj, plano)
    assert arq == pj.render_dir / "oneshot.json" and pj.dentro(arq)
    assert json.loads(arq.read_text(encoding="utf-8"))["aceleracao"] == 1.2


# --- o render único (o grafo, sem ffmpeg) --------------------------------------------------------

def _plano_pronto(luz_=None, janela=None, segmentos=((0.0, 1.2), (2.8, 4.5)), grade_="quente-suave"):
    return {"versao": 1, "take": "/x/bruto.mp4", "aceleracao": 1.2, "segmentos": [list(s) for s in segmentos],
            "janela": janela or enquadrar.janela_9x16(1920, 1080, (1100, 300, 220, 220)),
            "luz": luz_ or luz.calcular(70.0), "grade": grade_, "transferencia": "bt709", "avisos": []}


def test_filtro_complexo_faz_corte_enquadre_luz_velocidade_e_grade_numa_passada():
    fc = montar.filtro_complexo(_plano_pronto())
    assert fc.count("[0:v]trim=") == 2 and fc.count("[0:a]atrim=") == 2
    assert "crop=608:1080:" in fc and "scale=1080:1920" in fc
    assert "eq=brightness=0.161:contrast=1.096" in fc
    assert "setpts=PTS/1.2" in fc and "atempo=1.2" in fc
    assert "vignette=PI/5.5" in fc and "colorspace=all=bt709:iall=bt709:fast=1" in fc
    assert fc.index("setpts=PTS/1.2") < fc.index("vignette=PI/5.5")
    assert "overlay" not in fc and "[ao]" in fc and "[vo]" in fc


def test_sem_necessidade_de_luz_o_filtro_nao_mexe_na_imagem():
    fc = montar.filtro_complexo(_plano_pronto(luz_=luz.calcular(140.0)))
    assert "eq=brightness" not in fc


def test_com_caixa_a_sobreposicao_vem_depois_da_grade_numa_segunda_entrada():
    fc = montar.filtro_complexo(_plano_pronto(), caixa=True)
    assert "[1:v]" in fc and "overlay=0:0:format=auto" in fc
    assert fc.index("vignette") < fc.index("overlay")                  # a caixa nativa não leva grão nem vinheta


def test_o_comando_tem_uma_entrada_de_video_e_marca_a_saida_bt709(tmp_path):
    cmd = montar.comando_render(_plano_pronto(), Path("/x/bruto.mp4"), None, Path("/x/saida.mp4"))
    assert cmd.count("-i") == 1 and cmd[cmd.index("-i") + 1] == "/x/bruto.mp4"
    assert cmd[cmd.index("-colorspace") + 1] == "bt709" and cmd[cmd.index("-color_range") + 1] == "tv"
    com_caixa = montar.comando_render(_plano_pronto(), Path("/x/bruto.mp4"), Path("/x/c.png"), Path("/x/s.mp4"))
    assert com_caixa.count("-i") == 2 and "-loop" in com_caixa


def test_preset_de_grade_do_projeto_entra_no_plano(estado_vazio, tmp_path):
    pj = _projeto(estado_vazio)
    dados = json.loads(pj.projeto_json.read_text(encoding="utf-8"))
    dados["estilo"] = {"grade": "natural"}
    modelo.escrever(pj.projeto_json, dados)
    take = _take(tmp_path / "take.mp4")
    plano = montar.planejar(pj, take, _Leitor(), detector=lambda img: [ROSTO], medidor_luz=lambda t, j: 130.0)
    assert plano["grade"] == "natural" and "vignette=PI/4" in montar.filtro_complexo(plano)


# --- a luz medida --------------------------------------------------------------------------------

def test_luz_escura_vira_brightness_e_contraste_proporcionais_ao_que_falta():
    l = luz.calcular(70.0)
    assert l["brightness"] == pytest.approx(0.16, abs=0.005) and l["contrast"] == pytest.approx(1.096, abs=0.004)
    assert l["limitado"] is False
    assert luz.filtro(l) == "eq=brightness=%s:contrast=%s" % (l["brightness"], l["contrast"])


def test_luz_ja_clara_nao_vira_nada_e_o_filtro_e_vazio():
    for media in (111.0, 140.0, 200.0):
        l = luz.calcular(media)
        assert (l["brightness"], l["contrast"]) == (0.0, 1.0) and luz.filtro(l) == ""


def test_luz_muito_escura_tem_teto_e_diz_que_limitou():
    l = luz.calcular(20.0)
    assert l["brightness"] == luz.BRILHO_MAX and l["limitado"] is True


def test_medir_a_luz_usa_o_medidor_dos_quadros_da_janela(tmp_path):
    take = _take(tmp_path / "take.mp4")
    vistos = []
    media = luz.medir(take, enquadrar.janela_9x16(320, 180, None), amostras=3,
                      medidor=lambda quadro: vistos.append(quadro.shape) or 90.0)
    assert media == 90.0 and len(vistos) == 3
    assert all(s[1] < s[0] for s in vistos)                  # o quadro medido já é o recortado (vertical)


def test_medir_a_luz_de_verdade_acha_o_cinza_do_take(tmp_path):
    take = _take(tmp_path / "take.mp4")                      # color=0x808080: luminância 128 em 0 a 255
    assert luz.medir(take, enquadrar.janela_9x16(320, 180, None), amostras=3) == pytest.approx(128, abs=4)


# --- HDR: o iPhone grava em HLG ------------------------------------------------------------------

def test_so_hlg_e_pq_sao_hdr():
    assert luz.eh_hdr("arib-std-b67") and luz.eh_hdr("smpte2084")
    assert not luz.eh_hdr("bt709") and not luz.eh_hdr(None) and not luz.eh_hdr("unknown")


def test_hlg_para_sdr_preserva_o_preto_o_cinza_medio_e_mantem_o_neutro_neutro():
    cinzas = np.array([[0.0] * 3, [0.25] * 3, [0.5] * 3, [0.75] * 3, [1.0] * 3])
    saida = luz.hlg_para_sdr(cinzas)
    assert saida[0] == pytest.approx([0, 0, 0], abs=1e-6)
    assert saida[2][0] == pytest.approx(0.49, abs=0.03)             # HLG 0,5 vira meio-tom no SDR
    assert saida[3][0] == pytest.approx(0.95, abs=0.03)             # o branco de referência (75%) fica brilhante sem estourar
    assert saida[4][0] <= 1.0 and saida[4][0] >= 0.99
    assert np.all(np.abs(saida[:, 0] - saida[:, 1]) < 1e-6) and np.all(np.abs(saida[:, 1] - saida[:, 2]) < 1e-6)
    assert np.all(np.diff(saida[:, 0]) > 0)                        # monotônico


def test_a_lut_tem_o_formato_cube_e_e_deterministica(tmp_path):
    a = luz.gerar_lut(tmp_path / "a.cube", tamanho=9)
    b = luz.gerar_lut(tmp_path / "b.cube", tamanho=9)
    linhas = a.read_text().splitlines()
    assert "LUT_3D_SIZE 9" in linhas
    dados = [l for l in linhas if l and l[0] in "0123456789"]
    assert len(dados) == 9 ** 3 and dados[0] == "0.000000 0.000000 0.000000"
    assert a.read_bytes() == b.read_bytes()
    cinza = [float(x) for x in dados[4 + 4 * 9 + 4 * 81].split()]    # índice (4,4,4): o cinza médio
    assert cinza[0] == pytest.approx(cinza[1], abs=1e-5) and cinza[1] == pytest.approx(cinza[2], abs=1e-5)


def test_a_cadeia_hdr_decodifica_em_bt2020_e_codifica_em_bt709_antes_da_grade():
    cadeia = luz.cadeia_hdr_para_sdr("/x/hlg.cube")
    assert "in_color_matrix=bt2020" in cadeia and "lut3d=file=/x/hlg.cube" in cadeia
    assert "interp=tetrahedral" in cadeia and "out_color_matrix=bt709" in cadeia
    assert cadeia.rstrip().endswith("setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv")


# (R', G', B') em HLG: três cinzas e três cores bem saturadas. Cada uma vira uma faixa vertical do quadro.
_FAIXAS_HLG = [(0.25, 0.25, 0.25), (0.5, 0.5, 0.5), (0.75, 0.75, 0.75),
               (0.70, 0.30, 0.25), (0.30, 0.65, 0.30), (0.25, 0.30, 0.70)]


def _ycbcr_2020_10bits(rgb):
    r, g, b = rgb
    y = 0.2627 * r + 0.6780 * g + 0.0593 * b
    return round(64 + 876 * y), round(512 + 896 * (b - y) / 1.8814), round(512 + 896 * (r - y) / 1.4746)


def _ycbcr_709_8bits(rgb):
    r, g, b = [float(v) for v in rgb]
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return 16 + 219 * y, 128 + 224 * (b - y) / 1.8556, 128 + 224 * (r - y) / 1.5748


def _plano(video, plano):
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(video), "-frames:v", "1", "-vf",
                        "extractplanes=%s" % plano, "-f", "rawvideo", "-"], capture_output=True)
    assert r.returncode == 0, r.stderr
    return np.frombuffer(r.stdout, dtype=np.uint8)


@pytest.mark.lento
def test_o_ffmpeg_converte_hlg_para_sdr_como_a_conta_em_numpy(tmp_path):
    """Faixas em HLG 10 bits (tags bt2020/HLG): o ffmpeg (decodifica bt2020, LUT, codifica bt709) bate com a conta em
    numpy no Y, no Cb e no Cr de cada faixa, e a saída sai com as tags bt709. Cobre a matriz, a faixa de valores e a
    ordem dos canais da LUT (as cores saturadas denunciam canal trocado; os cinzas, curva errada)."""
    n = len(_FAIXAS_HLG)
    codigos = [_ycbcr_2020_10bits(c) for c in _FAIXAS_HLG]
    def expr(k):
        return "+".join("%d*eq(floor(X*%d/W),%d)" % (c[k], n, i) for i, c in enumerate(codigos))
    src = tmp_path / "hlg.mp4"
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
                        "nullsrc=s=192x64:r=25:d=1,format=yuv420p10le,geq=lum='%s':cb='%s':cr='%s',"
                        "setparams=colorspace=bt2020nc:color_primaries=bt2020:color_trc=arib-std-b67:range=tv"
                        % (expr(0), expr(1), expr(2)),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p10le", "-crf", "3", str(src)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    lut = luz.gerar_lut(tmp_path / "hlg.cube")
    saida = tmp_path / "sdr.mp4"
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", str(src), "-vf", luz.cadeia_hdr_para_sdr(lut),
                        "-c:v", "libx264", "-crf", "3", "-colorspace", "bt709", "-color_primaries", "bt709",
                        "-color_trc", "bt709", "-color_range", "tv", str(saida)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    y = _plano(saida, "y").reshape(64, 192)
    u = _plano(saida, "u").reshape(32, 96)
    v = _plano(saida, "v").reshape(32, 96)
    esperado = luz.hlg_para_sdr(np.array(_FAIXAS_HLG))
    for i, rgb in enumerate(esperado):
        ey, eu, ev = _ycbcr_709_8bits(rgb)
        medido = (float(y[32, i * 32 + 16]), float(u[16, i * 16 + 8]), float(v[16, i * 16 + 8]))
        assert medido == pytest.approx((ey, eu, ev), abs=2.0), (_FAIXAS_HLG[i], medido, (ey, eu, ev))
    tags = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                      "stream=color_space,color_transfer,color_primaries", "-of", "json",
                                      str(saida)], capture_output=True, text=True).stdout)["streams"][0]
    assert tags == {"color_space": "bt709", "color_primaries": "bt709", "color_transfer": "bt709"}


# --- a CLI: vam oneshot <slug> -------------------------------------------------------------------

def _args(*argv):
    ap = argparse.ArgumentParser(prog="vam")
    cli_oneshot.registrar(ap.add_subparsers(dest="comando"))
    return ap.parse_args(["oneshot", *argv])


def _cli(estado, slug, *argv):
    return cli_oneshot.executar(_args(slug, *argv, "--estado", str(estado)))


@pytest.fixture
def ambiente(monkeypatch):
    """Leitor, detector de rosto e medidor de luz falsos (o ASR e o OpenCV não rodam nos testes da CLI)."""
    monkeypatch.setattr(montar, "leitor_do_projeto", lambda pj, backend=None, estado=None: _Leitor())
    monkeypatch.setattr(enquadrar, "medir_rosto", lambda *a, **k: ROSTO)
    monkeypatch.setattr(luz, "medir", lambda *a, **k: 70.0)


def _com_take(estado, tmp_path, slug="take"):
    pj = _projeto(estado, slug=slug)
    pj.voz_dir.mkdir(parents=True, exist_ok=True)
    _take(pj.voz_dir / "bruto.mp4")
    return pj


def test_registrar_cria_o_subcomando_oneshot_e_aponta_para_executar():
    a = _args("take", "--caixa", "Texto da caixa", "--so-plano", "--colorway", "branco")
    assert a.comando == "oneshot" and a.func is cli_oneshot.executar
    assert (a.slug, a.caixa, a.so_plano, a.colorway) == ("take", "Texto da caixa", True, "branco")


def test_slug_invalido_projeto_inexistente_e_modo_errado_saem_2(estado_vazio, capsys):
    assert _cli(estado_vazio, "Take Ruim") == 2 and "slug inválido" in capsys.readouterr().err
    assert _cli(estado_vazio, "fantasma") == 2 and "vam novo" in capsys.readouterr().err
    _projeto(estado_vazio, modo="avatar", slug="com-avatar")
    assert _cli(estado_vazio, "com-avatar") == 2 and "oneshot" in capsys.readouterr().err


def test_sem_o_take_sai_2_e_diz_como_passar(estado_vazio, capsys):
    _projeto(estado_vazio)
    assert _cli(estado_vazio, "take") == 2
    assert "--bruto" in capsys.readouterr().err


def test_bruto_e_copiado_para_dentro_do_projeto_sem_tocar_na_origem(estado_vazio, tmp_path, ambiente):
    pj = _projeto(estado_vazio)
    origem = _take(tmp_path / "gravacao.mov")
    antes = origem.read_bytes()
    assert _cli(estado_vazio, "take", "--bruto", str(origem), "--so-plano") == 0
    assert pj.voz_bruto().suffix == ".mov" and pj.voz_bruto().read_bytes() == antes and origem.read_bytes() == antes
    assert _cli(estado_vazio, "take", "--bruto", str(origem), "--so-plano") == 0          # idempotente


def test_bruto_diferente_do_que_ja_esta_no_projeto_nao_sobrescreve(estado_vazio, tmp_path, ambiente, capsys):
    pj = _com_take(estado_vazio, tmp_path)
    outro = tmp_path / "outro.mp4"
    outro.write_bytes(b"outro take")
    assert _cli(estado_vazio, "take", "--bruto", str(outro), "--so-plano") == 2
    assert "já tem" in capsys.readouterr().err
    assert pj.voz_bruto().name == "bruto.mp4" and pj.voz_bruto().read_bytes() != b"outro take"


def test_bruto_que_nao_existe_sai_2(estado_vazio, tmp_path):
    _projeto(estado_vazio)
    assert _cli(estado_vazio, "take", "--bruto", str(tmp_path / "nada.mov")) == 2


def test_so_plano_escreve_o_plano_e_nao_renderiza(estado_vazio, tmp_path, ambiente, capsys):
    pj = _com_take(estado_vazio, tmp_path)
    assert _cli(estado_vazio, "take", "--so-plano") == 0
    saida = capsys.readouterr().out
    assert "1.2" in saida and "2 segmentos" in saida
    assert json.loads((pj.render_dir / "oneshot.json").read_text(encoding="utf-8"))["aceleracao"] == 1.2
    assert not pj.final_9x16.exists()


def test_colorway_inventado_sai_2_e_nao_renderiza(estado_vazio, tmp_path, ambiente):
    pj = _com_take(estado_vazio, tmp_path)
    assert _cli(estado_vazio, "take", "--caixa", "Oi", "--colorway", "rosa") == 2
    assert not pj.final_9x16.exists()


def _render_falso(monkeypatch):
    def renderizar(pj, plano, caixa_png=None):
        pj.entrega_dir.mkdir(parents=True, exist_ok=True)
        pj.final_9x16.write_bytes(b"final")
        return pj.final_9x16
    monkeypatch.setattr(montar, "renderizar", renderizar)


def test_gate_que_reprova_depois_do_render_sai_1(estado_vazio, tmp_path, ambiente, monkeypatch, capsys):
    _com_take(estado_vazio, tmp_path)
    _render_falso(monkeypatch)
    monkeypatch.setattr(montar, "conferir", lambda pj, plano, leitor, final: [
        ("fala_preservada", False, "3 palavra(s) sumida(s): vou, te, dar"), ("ar_morto", True, "ok")])
    assert _cli(estado_vazio, "take") == 1
    saida = capsys.readouterr().out
    assert "fala_preservada" in saida and "REPROVADO" in saida and "vou, te, dar" in saida


def test_tudo_verde_sai_0_e_diz_onde_ficou_o_final(estado_vazio, tmp_path, ambiente, monkeypatch, capsys):
    pj = _com_take(estado_vazio, tmp_path)
    _render_falso(monkeypatch)
    monkeypatch.setattr(montar, "conferir", lambda pj, plano, leitor, final: [("fala_preservada", True, "ok")])
    assert _cli(estado_vazio, "take") == 0
    assert str(pj.final_9x16) in capsys.readouterr().out and pj.final_9x16.is_file()


def test_insumo_que_falta_no_render_sai_2(estado_vazio, tmp_path, ambiente, monkeypatch):
    _com_take(estado_vazio, tmp_path)

    def quebra(pj, plano, caixa_png=None):
        raise InsumoInvalido("ffmpeg não encontrado")
    monkeypatch.setattr(montar, "renderizar", quebra)
    assert _cli(estado_vazio, "take") == 2


# --- os gates de depois, unitários ---------------------------------------------------------------

def test_conferir_reprova_fala_que_sumiu_e_aceita_pontuacao_e_acento_diferentes(estado_vazio, tmp_path, monkeypatch):
    pj = _com_take(estado_vazio, tmp_path)
    plano = {"aceleracao": 1.2}
    monkeypatch.setattr(montar.auditar, "tecnico", lambda f: {"ok": True, "motivo": "", "resolucao": "1080x1920",
                                                              "duracao": 2.3, "lufs": -14.0, "true_peak": -2.0})
    monkeypatch.setattr(montar.gate_ar_morto, "verificar", lambda f, accel: (True, "sem pausa"))
    pj.entrega_dir.mkdir(parents=True, exist_ok=True)
    pj.final_9x16.write_bytes(b"x")
    bom = montar.conferir(pj, plano, _Leitor(texto_final="Um, dois! Tres quatro."), pj.final_9x16)
    assert [n for n, _, _ in bom] == ["fala_preservada", "ar_morto", "tecnico"] and all(ok for _, ok, _ in bom)
    ruim = montar.conferir(pj, plano, _Leitor(texto_final="Um"), pj.final_9x16)
    assert dict((n, ok) for n, ok, _ in ruim)["fala_preservada"] is False


# --- render de verdade ---------------------------------------------------------------------------

@pytest.mark.lento
def test_render_real_sai_1080x1920_na_duracao_do_plano_com_a_caixa_e_bt709(estado_vazio, tmp_path):
    from PIL import Image
    pj = _com_take(estado_vazio, tmp_path)
    plano = montar.planejar(pj, pj.voz_bruto(), _Leitor(), detector=lambda img: [ROSTO], medidor_luz=lambda t, j: 90.0)
    png = tmp_path / "caixa.png"
    import caixa_lettering
    caixa_lettering.montar_overlay("Texto de teste da caixa", colorway="ambar", centro_y=0.17).save(png)
    final = montar.renderizar(pj, plano, png)
    assert final == pj.final_9x16 and final.is_file()
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                      "stream=width,height,color_space,color_primaries,color_transfer,r_frame_rate",
                                      "-show_entries", "format=duration", "-of", "json", str(final)],
                                     capture_output=True, text=True).stdout)
    v = info["streams"][0]
    assert (v["width"], v["height"]) == (1080, 1920) and v["r_frame_rate"] == "30/1"
    assert (v["color_space"], v["color_primaries"], v["color_transfer"]) == ("bt709", "bt709", "bt709")
    assert float(info["format"]["duration"]) == pytest.approx(plano["dur_final"], abs=0.2)
    assert loudness.dentro_da_faixa(loudness.medir(final))
    quadro = tmp_path / "q.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1.0", "-i", str(final), "-frames:v", "1", str(quadro)], check=True)
    im = Image.open(quadro).convert("RGB")
    r, g, b = im.getpixel((150, int(0.17 * 1920)))                         # na margem da caixa, longe das letras
    assert abs(r - 254) < 14 and abs(g - 198) < 14 and abs(b - 77) < 18        # o âmbar nativo ficou no lugar
    a = np.asarray(im.convert("L"), dtype=float)
    assert not (a[400:1500].max(axis=1) < 8).any()                          # nenhuma linha inteira preta: sem barra
