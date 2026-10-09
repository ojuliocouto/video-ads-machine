"""W4.A: câmera viva (capacidade C3). Punch de ênfase, respiro, push-in e o zoom contínuo do avatar.

Cada número do C3 é uma constante com origem e é conferido aqui:
  zoom contínuo de 16% alternando por plano (já existe, `filtros_avatar.AMPL`);
  punch 1,00 -> 1,22 em 0,28 s na KEY em avatar cheio, segura até 2,4 s, volta seca em 2 quadros;
  respiro 1,10 -> 1,00 em 1 s na entrada de etapa;
  push-in em gravação de tela, alvo 0,75 e teto 1,70 (`push_in.py`).

O punch é capacidade NOVA e só liga quando a timeline traz eventos de câmera: sem `punches` o filtro
do avatar tem que ser BYTE A BYTE o de antes (strings golden gravadas do commit anterior à W4.A).

O que não precisa de render usa o avaliador numérico do zoompan (`camera.avaliar`), que lê a mesma
string que o ffmpeg lê. O render sintético (um quadrado que cresce 22%) é `lento`.
"""
import json
import math
import re
import subprocess
from pathlib import Path

import numpy as np
import pytest

import push_in
from cinema import camera
from footage import filtros_avatar as FA

RAIZ = Path(__file__).resolve().parents[2]

# --- goldens: gravados do filtros_avatar ANTES de aceitar punches (commit ab1337b) ---------------------------
GOLDEN_FILTRO = {
    (132, 0, 1.0): "fps=30,scale=2376:4224:force_original_aspect_ratio=increase,crop=2160:3840:108:652,"
                   "zoompan=z='1.0+0.16*on/131':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920,"
                   "setsar=1,trim=end_frame=132,setpts=N/30/TB",
    (50, 1, 1.14): "fps=30,scale=2376:4224:force_original_aspect_ratio=increase,crop=2160:3840:108:652,"
                   "zoompan=z='1.2999999999999998-0.16*on/49':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                   "s=1080x1920,setsar=1,trim=end_frame=50,setpts=N/30/TB",
    (90, 3, 1.06): "fps=30,scale=2376:4224:force_original_aspect_ratio=increase,crop=2160:3840:108:652,"
                   "zoompan=z='1.22-0.16*on/89':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920,"
                   "setsar=1,trim=end_frame=90,setpts=N/30/TB",
    (1, 0, 1.0): "fps=30,scale=2376:4224:force_original_aspect_ratio=increase,crop=2160:3840:108:652,"
                 "zoompan=z='1.0+0.16*on/1':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920,"
                 "setsar=1,trim=end_frame=1,setpts=N/30/TB",
}
GOLDEN_CMD = ["ffmpeg", "-y", "-ss", "5.6", "-t", "4.800000000000001", "-i", "/AV/a.mp4", "-vf",
              GOLDEN_FILTRO[(132, 0, 1.0)], "-r", "30", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
              "/o/s.mp4"]


def z_do_filtro(filtro):
    """O que está entre aspas em `zoompan=z='...'`: a string que o ffmpeg avalia."""
    m = re.search(r"zoompan=z='(.*?)':d=1:", filtro)
    assert m, filtro
    return m.group(1)


# =================================================================================== constantes do C3

def test_constantes_do_c3_com_os_numeros_do_plano():
    assert (camera.PUNCH_DE, camera.PUNCH_PARA) == (1.00, 1.22)
    assert camera.PUNCH_SOBE_S == 0.28
    assert camera.PUNCH_SEGURA_MAX_S == 2.4
    assert camera.PUNCH_VOLTA_QUADROS == 2
    assert (camera.RESPIRO_DE, camera.RESPIRO_PARA, camera.RESPIRO_DUR_S) == (1.10, 1.00, 1.0)
    assert camera.PUNCH_GANHO_MIN == 0.15            # "punch sem +15% de escala medida"
    assert camera.ESCALA_VARIACAO_MIN == camera.CAIXA_VARIACAO_MIN == 0.08   # "caixa do rosto varia menos de 8%"
    assert camera.PLANO_AVATAR_MIN_S == 2.0          # "num plano de avatar de 2 s ou mais"
    assert camera.PARADO_MAX_S == 20.0               # "mais de 20 s sem movimento"


def test_push_in_usa_o_alvo_e_o_teto_do_push_in_py():
    """Uma verdade só: o alvo 0,75 e o teto 1,70 moram em push_in.py e o C3 os lê de lá."""
    assert (camera.PUSH_IN_ALVO, camera.PUSH_IN_TETO) == (0.75, 1.70)
    assert camera.PUSH_IN_ALVO == push_in.ZOOM_ALVO and camera.PUSH_IN_TETO == push_in.ZOOM_MAX


def test_o_fps_da_camera_e_o_da_footage():
    assert camera.FPS == FA.FPS == 30


# =================================================================================== avaliador numérico

@pytest.mark.parametrize("expr,esperado", [
    ("1+2*3", 7.0), ("-2+5", 3.0), ("(1+2)*(3-1)/4", 1.5), ("min(3,2)", 2.0), ("max(3,2)", 3.0),
    ("abs(-4)", 4.0), ("if(lt(1,2),10,20)", 10.0), ("if(gte(1,2),10,20)", 20.0),
    ("between(5,1,5)", 1.0), ("between(5.01,1,5)", 0.0), ("lt(1,1)", 0.0), ("gt(2,1)", 1.0),
    ("1.2999999999999998-0.16*on/49", 1.2999999999999998 - 0.16 * 25 / 49),
])
def test_avaliador_calcula_o_subconjunto_do_ffmpeg(expr, esperado):
    assert camera.avaliar(expr, on=25) == pytest.approx(esperado, abs=1e-12)


@pytest.mark.parametrize("expr", ["__import__('os')", "foo(1)", "1+", "1/0", "on.real", "(1+2", "1 2", ""])
def test_avaliador_recusa_o_que_nao_e_expressao_do_zoompan(expr):
    with pytest.raises(ValueError):
        camera.avaliar(expr, on=1)


def test_avaliador_recusa_variavel_nao_declarada():
    with pytest.raises(ValueError, match="zzz"):
        camera.avaliar("zzz+1")


# =================================================================================== o punch, em números

def ev_punch(t=1.0, segura=2.4):
    return camera.evento_punch(t, segura)


def valor(eventos, t, fps=30):
    """O fator que o filtro aplica no instante t (s), avaliando a MESMA string que vai pro ffmpeg."""
    return camera.avaliar(camera.expr_fator(eventos, fps), on=t * fps)


def test_punch_da_1_00_depois_1_22_em_028s_e_volta_a_1_00_dois_quadros_apos_o_hold():
    t0, segura = 1.0, 2.4
    ev = ev_punch(t0, segura)
    assert (ev["tipo"], ev["de"], ev["para"], ev["dur"], ev["segura"]) == ("punch", 1.0, 1.22, 0.28, 2.4)
    fim_hold = t0 + 0.28 + segura
    volta = 2 / 30.0
    assert valor([ev], 0.0) == pytest.approx(1.00, abs=1e-9)             # antes: neutro
    assert valor([ev], t0 - 0.01) == pytest.approx(1.00, abs=1e-9)
    assert valor([ev], t0) == pytest.approx(1.00, abs=1e-9)              # ponto de partida
    assert valor([ev], t0 + 0.14) == pytest.approx(1.11, abs=1e-6)       # metade da subida
    assert valor([ev], t0 + 0.28) == pytest.approx(1.22, abs=1e-9)       # em +0,28 s: 1,22
    assert valor([ev], t0 + 0.28 + segura / 2) == pytest.approx(1.22, abs=1e-9)   # segura
    assert valor([ev], fim_hold) == pytest.approx(1.22, abs=1e-9)        # último instante do hold
    assert valor([ev], fim_hold + volta / 2) == pytest.approx(1.11, abs=1e-6)     # a volta é seca, em 2 quadros
    assert valor([ev], fim_hold + volta) == pytest.approx(1.00, abs=1e-9)         # dois quadros depois: 1,00
    assert valor([ev], fim_hold + 1.0) == pytest.approx(1.00, abs=1e-9)           # e fica


def test_punch_quadro_a_quadro_sobe_em_8_quadros_e_volta_em_2():
    """O que o ffmpeg avalia são quadros inteiros (`on`): a subida de 0,28 s a 30 fps é 8,4 quadros."""
    ev = ev_punch(1.0, 1.0)
    serie = [camera.avaliar(camera.expr_fator([ev], 30), on=k) for k in range(0, 100)]
    assert serie[30] == pytest.approx(1.00, abs=1e-9)                     # quadro 30 = t 1,0 s
    assert serie[31] > serie[30] and serie[38] < 1.22                     # sobe a cada quadro
    assert serie[39] == pytest.approx(1.22, abs=1e-9)                     # primeiro quadro depois de 1,28 s
    assert max(serie) == pytest.approx(1.22, abs=1e-9)
    fim_hold = (1.0 + 0.28 + 1.0) * 30                                     # 68,4 quadros: o hold acaba entre 68 e 69
    assert serie[68] == pytest.approx(1.22, abs=1e-9)                      # último quadro inteiro dentro do hold
    assert 1.0 < serie[69] < 1.22 and 1.0 < serie[70] < serie[69]          # a volta é rampa de 2 quadros
    k_volta = int(math.ceil(fim_hold + 2))                                 # 71: dois quadros depois do hold
    assert serie[k_volta] == pytest.approx(1.00, abs=1e-9)
    assert all(v == pytest.approx(1.00, abs=1e-9) for v in serie[k_volta:])


def test_o_fator_direto_e_a_expressao_do_ffmpeg_dizem_a_mesma_coisa():
    eventos = [camera.evento_respiro(0.0), ev_punch(1.2, 1.5), ev_punch(5.0, 0.8)]
    expr = camera.expr_fator(eventos, 30)
    for k in range(0, 260):
        assert camera.avaliar(expr, on=k) == pytest.approx(camera.fator_total(eventos, k / 30.0, 30), abs=1e-5)


def test_respiro_comeca_em_1_10_e_assenta_em_1_00_em_1s():
    ev = camera.evento_respiro(2.0)
    assert (ev["tipo"], ev["de"], ev["para"], ev["dur"]) == ("respiro", 1.10, 1.00, 1.0)
    assert valor([ev], 2.0) == pytest.approx(1.10, abs=1e-9)
    assert valor([ev], 2.5) == pytest.approx(1.05, abs=1e-9)
    assert valor([ev], 3.0) == pytest.approx(1.00, abs=1e-9)
    assert valor([ev], 4.0) == pytest.approx(1.00, abs=1e-9)


def test_eventos_que_se_sobrepoem_multiplicam():
    resp, pun = camera.evento_respiro(0.0), ev_punch(0.5, 0.4)
    # em t=0,78 o respiro já foi a 1,10 - 0,10*0,78 = 1,022 e o punch acabou de chegar a 1,22
    assert valor([resp, pun], 0.78) == pytest.approx((1.10 - 0.10 * 0.78) * 1.22, abs=1e-6)


def test_so_punch_e_respiro_viram_fator():
    assert camera.expr_fator([{"t": 0, "tipo": "zoom", "de": 1.0, "para": 1.16, "dur": 3.0},
                              {"t": 0, "tipo": "push_in", "de": 1.0, "para": 1.1, "dur": 3.0}], 30) == "1"


def test_evento_punch_valida_o_que_o_c3_proibe():
    with pytest.raises(ValueError, match="segura"):
        camera.evento_punch(1.0, camera.PUNCH_SEGURA_MAX_S + 0.1)          # segura até 2,4 s
    with pytest.raises(ValueError):
        camera.evento_punch(-0.1, 1.0)


# =================================================================================== filtro do avatar

@pytest.mark.parametrize("chave", sorted(GOLDEN_FILTRO))
def test_sem_punches_o_filtro_e_identico_ao_de_antes(chave):
    N, idx, base = chave
    esperado = GOLDEN_FILTRO[chave]
    assert FA.filtro_orig(N, idx, base) == esperado
    assert FA.filtro_orig(N, idx, base, punches=None) == esperado
    assert FA.filtro_orig(N, idx, base, punches=[]) == esperado


def test_sem_punches_o_comando_inteiro_e_identico_ao_de_antes():
    assert FA.cmd_orig("/AV/a.mp4", 5.6, 10.0, "/o/s.mp4", idx=0, base=1.0) == GOLDEN_CMD
    assert FA.cmd_orig("/AV/a.mp4", 5.6, 10.0, "/o/s.mp4", idx=0, base=1.0, punches=None) == GOLDEN_CMD
    assert FA.cmd_orig("/AV/a.mp4", 5.6, 10.0, "/o/s.mp4", 0, 1.0) == GOLDEN_CMD       # posicional, como o r_orig chama


def test_expr_zoom_sem_punches_continua_a_mesma_string():
    assert FA.expr_zoom(100, 0, 1.0) == "1.0+0.16*on/99"
    assert FA.expr_zoom(100, 1, 1.0, punches=None) == "1.16-0.16*on/99"
    assert FA.expr_zoom(50, 1, 1.14, punches=[]) == "1.2999999999999998-0.16*on/49"


def test_com_punches_o_zoom_continuo_e_multiplicado_pelo_fator():
    N, idx, base = 120, 1, 1.0
    ev = ev_punch(0.5, 1.0)
    f = FA.filtro_orig(N, idx, base, punches=[ev])
    z = z_do_filtro(f)
    assert z != z_do_filtro(FA.filtro_orig(N, idx, base))
    lento = FA.expr_zoom(N, idx, base)
    for k in range(0, N):
        esperado = camera.avaliar(lento, on=k) * camera.fator_total([ev], k / 30.0, 30)
        assert camera.avaliar(z, on=k) == pytest.approx(esperado, abs=1e-6)
    # o resto do filtro não muda: só a expressão do zoom
    assert f.replace(z, "Z") == FA.filtro_orig(N, idx, base).replace(z_do_filtro(FA.filtro_orig(N, idx, base)), "Z")


def test_com_punches_o_punch_chega_a_1_22_vezes_o_zoom_do_plano():
    N = 120
    ev = ev_punch(0.5, 1.0)
    z = z_do_filtro(FA.filtro_orig(N, 0, 1.0, punches=[ev]))
    lento = FA.expr_zoom(N, 0, 1.0)
    k = 30                                       # t = 1,0 s, no meio do hold
    assert camera.avaliar(z, on=k) == pytest.approx(camera.avaliar(lento, on=k) * 1.22, abs=1e-6)


def test_a_expressao_com_punch_nao_tem_aspas_nem_ponto_e_virgula():
    """A string vai dentro de z='...' num -vf: aspas ou ':' quebrariam o filtergraph."""
    z = z_do_filtro(FA.filtro_orig(90, 0, 1.0, punches=[ev_punch(0.5, 1.0), camera.evento_respiro(0.0)]))
    assert "'" not in z and ":" not in z and ";" not in z and " " not in z


def test_cmd_orig_com_punches_so_troca_o_filtro():
    ev = ev_punch(0.5, 1.0)
    cmd = FA.cmd_orig("/AV/a.mp4", 5.6, 10.0, "/o/s.mp4", idx=0, base=1.0, punches=[ev])
    sem = FA.cmd_orig("/AV/a.mp4", 5.6, 10.0, "/o/s.mp4", idx=0, base=1.0)
    assert len(cmd) == len(sem)
    diff = [i for i, (a, b) in enumerate(zip(cmd, sem)) if a != b]
    assert diff == [sem.index("-vf") + 1]


def test_punch_que_comeca_depois_do_fim_do_plano_nao_muda_nem_o_texto_do_filtro():
    N = 60
    ev = ev_punch(10.0, 1.0)                     # depois do fim do segmento de 2 s
    assert FA.filtro_orig(N, 0, 1.0, punches=[ev]) == FA.filtro_orig(N, 0, 1.0)
    assert FA.expr_zoom(N, 1, 1.14, punches=[ev]) == FA.expr_zoom(N, 1, 1.14)


# =================================================================================== planejar a câmera

def timeline_base():
    """Uma timeline com os campos que a câmera lê: blocos, segmentos, letterings, janelas de split."""
    return {
        "relogio": {"base": "footage_1x", "fps": 30, "aceleracao": 1.35, "cauda_s": 0.45, "a0": 0.0},
        "duracao_s": 34.0,
        "blocos": [
            {"i": 0, "tipo": "insert", "insert": "painel", "s": 0.0, "e": 3.0},
            {"i": 1, "tipo": "apresentador", "insert": None, "s": 3.0, "e": 9.0},
            {"i": 2, "tipo": "insert", "insert": "planilha", "s": 9.0, "e": 14.0},
            {"i": 3, "tipo": "lista", "insert": None, "s": 14.0, "e": 20.0},
            {"i": 4, "tipo": "apresentador", "insert": None, "s": 20.0, "e": 26.0},
            {"i": 5, "tipo": "insert", "insert": "imagem", "s": 26.0, "e": 29.0},
            {"i": 6, "tipo": "cta", "insert": None, "s": 29.0, "e": 34.0},
        ],
        "segmentos": [
            {"bloco": 0, "tipo": "insert", "s": 0.0, "e": 3.0, "sub": 0, "de": 1, "layout": "cheio"},
            {"bloco": 1, "tipo": "apresentador", "s": 3.0, "e": 9.0, "sub": 0, "de": 1, "base": 1.0},
            {"bloco": 2, "tipo": "insert", "s": 9.0, "e": 14.0, "sub": 0, "de": 1, "layout": "split"},
            {"bloco": 3, "tipo": "apresentador", "s": 14.0, "e": 20.0, "sub": 0, "de": 1, "base": 1.14},
            {"bloco": 4, "tipo": "apresentador", "s": 20.0, "e": 26.0, "sub": 0, "de": 1, "base": 1.0},
            {"bloco": 5, "tipo": "insert", "s": 26.0, "e": 29.0, "sub": 0, "de": 1, "layout": "cheio"},
            {"bloco": 6, "tipo": "apresentador", "s": 29.0, "e": 34.0, "sub": 0, "de": 1, "base": 1.0},
        ],
        "janelas_split": [{"s": 9.0, "e": 14.0}],
        "legendas": [],
        "letterings": [],
    }


def lettering(id_, bloco, s, d=2.2, **kw):
    base = {"id": id_, "bloco": bloco, "lead": None, "key": "FALTA DE TEMPO", "s": s, "d": d,
            "estilo": "caixa_nativa", "split": False, "baixo": False, "pilha": None, "cta": False}
    base.update(kw)
    return base


def punches_de(eventos):
    return [e for e in eventos if e["tipo"] == "punch"]


def dentro_de(t, janelas):
    return any(j["s"] - 1e-9 <= t <= j["e"] + 1e-9 for j in janelas)


def test_punch_pousa_na_key_do_avatar_cheio_e_so_nela():
    tl = timeline_base()
    tl["letterings"] = [
        lettering("ok1", 1, 4.0),                              # avatar cheio, KEY do meio: ganha punch
        lettering("ins", 0, 1.0),                              # cai em insert
        lettering("spl", 2, 10.0, split=True, baixo=True),     # lettering de split, dentro da janela
        lettering("flag", 1, 7.0, split=True),                 # marcado split mesmo fora da janela
        lettering("cta", 6, 29.5, cta=True, estilo="seta_cta"),
        lettering("p1", 3, 15.0, pilha="b3"),                  # item de pilha tem tick, não punch
        lettering("ok2", 4, 21.0),
    ]
    eventos, recusados = camera.planejar_com_motivos(tl)
    ps = punches_de(eventos)
    assert [round(p["t"], 3) for p in ps] == [4.0, 21.0]
    assert {r["lettering"] for r in recusados} == {"ins", "spl", "flag", "cta", "p1"}
    motivos = {r["lettering"]: r["motivo"] for r in recusados}
    assert "insert" in motivos["ins"] and "split" in motivos["spl"] and "split" in motivos["flag"]
    assert "CTA" in motivos["cta"] and "pilha" in motivos["p1"]


def test_punch_nunca_cai_em_insert_split_ou_lettering_de_split_nem_invade_a_janela():
    """Propriedade sobre timelines sorteadas (seed fixa): em nenhuma o punch toca insert, split ou
    lettering de split, e a janela inteira do punch (subida, hold e volta) cabe no plano de avatar."""
    rng = np.random.RandomState(20260709)
    for _ in range(60):
        tl = timeline_base()
        tl["letterings"] = []
        for j in range(int(rng.randint(3, 9))):
            bl = tl["blocos"][int(rng.randint(0, len(tl["blocos"])))]
            s = float(np.round(rng.uniform(bl["s"], bl["e"] - 0.1), 2))
            tl["letterings"].append(lettering("l%d" % j, bl["i"], s,
                                              d=float(np.round(rng.uniform(0.8, 3.0), 2)),
                                              split=bool(rng.randint(0, 4) == 0),
                                              cta=bool(rng.randint(0, 6) == 0),
                                              pilha="b3" if rng.randint(0, 5) == 0 else None))
        eventos = camera.planejar(tl)
        por_id = {l["id"]: l for l in tl["letterings"]}
        for p in punches_de(eventos):
            ini, fim = camera.janela(p)
            seg = [sg for sg in tl["segmentos"] if sg["s"] - 1e-9 <= p["t"] < sg["e"] - 1e-9]
            assert len(seg) == 1 and seg[0]["tipo"] == "apresentador"
            assert ini >= seg[0]["s"] - 1e-9 and fim <= seg[0]["e"] + 1e-9
            assert not dentro_de(ini, tl["janelas_split"]) and not dentro_de(fim, tl["janelas_split"])
            assert not any(j["s"] < fim and ini < j["e"] for j in tl["janelas_split"])
            ls = [l for l in tl["letterings"] if l["bloco"] == seg[0]["bloco"] and l["s"] <= p["t"] < l["s"] + l["d"] + 1e-9]
            assert any(not l["split"] and not l["cta"] and not l["pilha"] for l in ls)
        # dois punches nunca se tocam
        ps = sorted(punches_de(eventos), key=lambda e: e["t"])
        for a, b in zip(ps, ps[1:]):
            assert camera.janela(b)[0] - camera.janela(a)[1] >= camera.PUNCH_ESPACO_MIN_S - 1e-9


def test_punch_respeita_a_subida_o_hold_e_o_fim_da_key():
    tl = timeline_base()
    tl["letterings"] = [lettering("a", 4, 21.0, d=2.2)]       # a KEY dura 2,2 s: o punch solta junto com ela
    (p,) = punches_de(camera.planejar(tl))
    assert p["t"] == 21.0 and p["dur"] == 0.28
    assert p["segura"] == pytest.approx(2.2 - 0.28, abs=1e-6)
    assert p["segura"] <= camera.PUNCH_SEGURA_MAX_S


def test_punch_nunca_segura_mais_que_2_4s():
    tl = timeline_base()
    tl["letterings"] = [lettering("a", 4, 21.0, d=5.0)]
    (p,) = punches_de(camera.planejar(tl))
    assert p["segura"] == camera.PUNCH_SEGURA_MAX_S


def test_key_colada_no_corte_ganha_o_punch_um_pouco_depois_para_dar_o_antes_ao_gate():
    """A KEY nasce no começo do plano: o punch espera `PUNCH_ANTES_MIN_S` para que exista um quadro
    sem punch para o gate medir contra (+15% sobre quê?)."""
    tl = timeline_base()
    tl["letterings"] = [lettering("a", 4, 20.0, d=2.6)]       # o plano de avatar começa em 20,0
    (p,) = punches_de(camera.planejar(tl))
    assert p["t"] == pytest.approx(20.0 + camera.PUNCH_ANTES_MIN_S, abs=1e-6)
    assert p["t"] + p["dur"] + p["segura"] <= 20.0 + 2.6 + 1e-6


def test_key_curta_demais_para_a_subida_mais_o_hold_minimo_nao_ganha_punch():
    tl = timeline_base()
    tl["letterings"] = [lettering("a", 4, 21.0, d=0.5)]
    eventos, recusados = camera.planejar_com_motivos(tl)
    assert punches_de(eventos) == []
    assert "curta" in recusados[0]["motivo"]


def test_punch_sem_espaco_antes_do_fim_do_plano_e_recusado():
    tl = timeline_base()
    tl["letterings"] = [lettering("a", 4, 25.5, d=2.2)]       # o plano acaba em 26,0
    eventos, recusados = camera.planejar_com_motivos(tl)
    assert punches_de(eventos) == []
    assert "espaço" in recusados[0]["motivo"]


def test_hold_encolhe_para_caber_no_plano():
    tl = timeline_base()
    tl["letterings"] = [lettering("a", 4, 24.0, d=3.0)]       # o plano acaba em 26,0
    (p,) = punches_de(camera.planejar(tl))
    assert p["t"] + p["dur"] + p["segura"] <= 26.0 - camera.PUNCH_CAUDA_MIN_S + 1e-6
    assert p["segura"] >= camera.PUNCH_SEGURA_MIN_S


def test_dois_punches_colados_ficam_so_com_o_primeiro():
    tl = timeline_base()
    tl["letterings"] = [lettering("a", 4, 21.0, d=1.6), lettering("b", 4, 22.7, d=1.6)]
    eventos, recusados = camera.planejar_com_motivos(tl)
    assert [round(p["t"], 2) for p in punches_de(eventos)] == [21.0]
    assert recusados[0]["lettering"] == "b" and "outro punch" in recusados[0]["motivo"]


def test_zoom_continuo_alterna_pela_posicao_do_segmento_e_usa_a_base():
    tl = timeline_base()
    eventos = camera.planejar(tl)
    zooms = {e["t"]: e for e in eventos if e["tipo"] == "zoom" and e["dur"] > 4}
    seg = tl["segmentos"]
    # segmento 1 (ímpar): puxa pra fora de base+0,16 até base; segmento 3 (ímpar) com base 1,14
    z1 = zooms[seg[1]["s"]]
    assert (z1["de"], z1["para"], z1["dur"]) == (pytest.approx(1.16), 1.0, 6.0)
    z3 = zooms[seg[3]["s"]]
    assert (z3["de"], z3["para"]) == (pytest.approx(1.30), pytest.approx(1.14))
    # segmento 4 (par): empurra pra dentro
    z4 = zooms[seg[4]["s"]]
    assert (z4["de"], z4["para"]) == (1.0, pytest.approx(1.16))
    # a amplitude é a de filtros_avatar, não uma cópia
    assert z4["para"] - z4["de"] == pytest.approx(FA.AMPL)


def test_respiro_na_entrada_da_lista_e_push_in_no_insert_de_video():
    tl = timeline_base()
    eventos = camera.planejar(tl, push_in_por_insert={"painel": 1.27, "planilha": 1.0})
    respiros = [e for e in eventos if e["tipo"] == "respiro"]
    assert [(r["t"], r["de"], r["para"], r["dur"]) for r in respiros] == [(14.0, 1.1, 1.0, 1.0)]
    pushes = [e for e in eventos if e["tipo"] == "push_in"]
    assert len(pushes) == 1                                      # planilha já entra grande (fator 1,0): sem avanço
    assert (pushes[0]["t"], pushes[0]["de"], pushes[0]["para"], pushes[0]["dur"]) == (0.0, 1.0, 1.27, 3.0)


def test_push_in_nunca_passa_do_teto_de_1_70():
    tl = timeline_base()
    eventos = camera.planejar(tl, push_in_por_insert={"painel": 2.4})
    (p,) = [e for e in eventos if e["tipo"] == "push_in"]
    assert p["para"] == camera.PUSH_IN_TETO


def test_imagem_estatica_ganha_zoom_de_ken_burns_e_nao_push_in():
    tl = timeline_base()
    eventos = camera.planejar(tl, imagens={"imagem"})
    kb = [e for e in eventos if e["tipo"] == "zoom" and e["t"] == 26.0]
    assert len(kb) == 1 and (kb[0]["de"], kb[0]["para"]) == (1.0, 1.06)


def test_a_lista_da_camera_sai_em_ordem_e_valida_no_contrato():
    from contratos import validar
    exemplo = json.loads((RAIZ / "contratos" / "exemplos" / "timeline.valido.json").read_text(encoding="utf-8"))
    eventos = camera.planejar(exemplo)
    assert [e["t"] for e in eventos] == sorted(e["t"] for e in eventos)
    exemplo["camera"] = eventos
    erros = validar.validar("timeline", exemplo)
    assert erros == [], erros


def test_planejar_nao_muda_a_timeline_de_entrada():
    tl = timeline_base()
    tl["letterings"] = [lettering("a", 4, 21.0)]
    antes = json.dumps(tl, sort_keys=True)
    camera.planejar(tl)
    assert json.dumps(tl, sort_keys=True) == antes


# =================================================================================== do plano para o filtro

def test_eventos_do_segmento_viram_tempo_relativo_ao_inicio_do_plano():
    cam = [camera.evento_punch(21.0, 1.9), camera.evento_respiro(14.0), camera.evento_punch(5.0, 1.0),
           {"t": 20.0, "tipo": "zoom", "de": 1.0, "para": 1.16, "dur": 6.0}]
    rel = camera.eventos_do_segmento(cam, 20.0, 26.0)
    assert [(e["tipo"], round(e["t"], 3)) for e in rel] == [("punch", 1.0)]
    assert rel[0]["segura"] == 1.9 and rel[0]["dur"] == 0.28
    assert camera.eventos_do_segmento(cam, 14.0, 20.0)[0]["tipo"] == "respiro"
    assert camera.eventos_do_segmento([], 0.0, 5.0) == []
    assert camera.eventos_do_segmento(None, 0.0, 5.0) == []


def test_o_evento_relativo_alimenta_o_filtro_e_o_valor_bate_com_o_absoluto():
    cam = [camera.evento_punch(21.0, 1.9)]
    rel = camera.eventos_do_segmento(cam, 20.0, 26.0)
    z = z_do_filtro(FA.filtro_orig(FA.nframes(6.0), 0, 1.0, punches=rel))
    lento = FA.expr_zoom(FA.nframes(6.0), 0, 1.0)
    k = int(round((21.0 - 20.0 + 0.28 + 0.5) * 30))
    assert camera.avaliar(z, on=k) == pytest.approx(camera.avaliar(lento, on=k) * 1.22, abs=1e-6)


# =================================================================================== medidas puras (o que os gates usam)

def test_para_entregue_divide_pela_aceleracao_depois_de_tirar_o_a0():
    rel = {"aceleracao": 1.35, "a0": 0.24, "fps": 30, "cauda_s": 0.45, "base": "footage_1x"}
    assert camera.para_entregue(0.24, rel) == pytest.approx(0.0)
    assert camera.para_entregue(1.59, rel) == pytest.approx(1.0)


def test_variacao_da_escala_e_o_total_que_a_imagem_cresceu_ou_encolheu():
    tempos = [k / 12.0 for k in range(36)]
    dentro = [1.0 + 0.16 * k / 35.0 for k in range(36)]                  # zoom de entrada de 16% em 36 quadros
    fora = [1.16 / (1.0 + 0.16 * k / 35.0) for k in range(36)]           # zoom de saída, mesma amplitude
    assert 0.15 < camera.variacao_da_escala(dentro, tempos) < 0.17
    assert 0.14 < camera.variacao_da_escala(fora, tempos) < 0.17         # o sentido não importa
    rng = np.random.RandomState(3)
    parado = [1.0 + float(rng.uniform(-0.006, 0.006)) for _ in range(36)]  # ruído do rastreador num avatar parado
    assert camera.variacao_da_escala(parado, tempos) < camera.ESCALA_VARIACAO_MIN
    assert camera.variacao_da_escala([1.0, 1.1]) is None                 # poucos quadros: não dá pra medir
    assert camera.variacao_da_escala([None, None, 1.0, None]) is None


def test_variacao_usa_o_tempo_de_cada_medida_e_nao_so_a_ordem():
    tempos = [k / 12.0 for k in range(36)]
    dentro = [1.0 + 0.16 * k / 35.0 for k in range(36)]
    sobra = [k for k in range(36) if k % 3 != 0]                         # quadros que o rastreador perdeu
    v = camera.variacao_da_escala([dentro[k] for k in sobra], [tempos[k] for k in sobra])
    assert v == pytest.approx(camera.variacao_da_escala(dentro, tempos), abs=0.01)


def test_o_intervalo_da_caixa_acusaria_zoom_num_avatar_parado_e_a_escala_nao():
    """Num avatar real e PARADO a caixa do rosto balança 12% (medido). O intervalo acusaria zoom; a escala da
    imagem, que não vê a pessoa se inclinar, não."""
    t = [k / 12.0 for k in range(72)]
    caixa = [400.0 * (1 + 0.055 * math.sin(2 * math.pi * x / 3.7)) for x in t]
    assert (max(caixa) - min(caixa)) / min(caixa) > camera.ESCALA_VARIACAO_MIN          # a caixa "varia" 11%
    escala = [1.0 for _ in t]                                                            # a câmera não se mexeu
    assert camera.variacao_da_escala(escala, t) == 0.0


def test_ganho_do_punch_e_a_razao_das_medianas():
    assert camera.ganho_do_punch([400, 402, 398], [488, 490, 486]) == pytest.approx(0.22, abs=0.01)
    assert camera.ganho_do_punch([400, 400], [400, 400]) == pytest.approx(0.0)
    assert camera.ganho_do_punch([], [488]) is None
    assert camera.ganho_do_punch([400], [None]) is None


def test_maior_trecho_parado_une_janelas_e_conta_as_pontas():
    assert camera.maior_trecho_parado([(0, 5), (30, 40)], 45) == (25.0, 5.0, 30.0)
    assert camera.maior_trecho_parado([(0, 20), (10, 45)], 45)[0] == 0.0
    assert camera.maior_trecho_parado([(10, 12)], 45) == (33.0, 12.0, 45.0)
    assert camera.maior_trecho_parado([], 30) == (30.0, 0.0, 30.0)


def test_janelas_de_movimento_cobrem_zoom_push_in_respiro_e_punch_inteiro():
    cam = [{"t": 3.0, "tipo": "zoom", "de": 1.0, "para": 1.16, "dur": 3.0},
           {"t": 9.0, "tipo": "push_in", "de": 1.0, "para": 1.2, "dur": 4.0},
           camera.evento_respiro(14.0), ev_punch(20.0, 1.0)]
    j = camera.janelas_de_movimento(cam)
    assert j[0] == (3.0, 6.0) and j[1] == (9.0, 13.0) and j[2] == (14.0, 15.0)
    assert j[3][0] == 20.0 and j[3][1] == pytest.approx(20.0 + 0.28 + 1.0 + 2 / 30.0)


# =================================================================================== render sintético (lento)

def _quadrado(destino, dur=3.4):
    """Cena parada 270x480: fundo escuro e um quadrado branco de 80 px no centro. Nada se mexe: tudo o que
    crescer no render é câmera."""
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
           "color=c=0x141414:s=270x480:r=30:d=%s,drawbox=x=95:y=200:w=80:h=80:color=white:t=fill" % dur,
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "12", str(destino)]
    subprocess.run(cmd, check=True, capture_output=True)
    return destino


def _larguras(video):
    """Largura (px, em 540 de largura) do quadrado branco em cada quadro do vídeo."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(video), "-vf", "scale=540:960,format=gray",
                        "-f", "rawvideo", "-"], capture_output=True, check=True)
    quadros = np.frombuffer(r.stdout, dtype=np.uint8).reshape(-1, 960, 540)
    larguras = []
    for q in quadros:
        colunas = np.where((q > 160).any(axis=0))[0]
        larguras.append(int(colunas[-1] - colunas[0] + 1) if len(colunas) else 0)
    return larguras


@pytest.mark.lento
def test_render_sintetico_o_quadrado_cresce_22_por_cento(tmp_path):
    fonte = _quadrado(tmp_path / "av.mp4")
    ev = camera.evento_punch(0.5, 1.0)                    # sobe de 0,50 a 0,78 s, segura até 1,78 s, volta em 2 quadros
    sem = tmp_path / "sem.mp4"
    com = tmp_path / "com.mp4"
    subprocess.run(FA.cmd_orig(str(fonte), 0.0, 3.0, str(sem), idx=0, base=1.0), check=True, capture_output=True)
    subprocess.run(FA.cmd_orig(str(fonte), 0.0, 3.0, str(com), idx=0, base=1.0, punches=[ev]),
                   check=True, capture_output=True)
    a, b = _larguras(sem), _larguras(com)
    assert len(a) == len(b) == 90
    # antes do punch o render é o mesmo, quadro a quadro
    assert all(abs(a[k] - b[k]) <= 1 for k in range(0, 14))
    # no meio do hold o quadrado está 22% maior do que estaria sem o punch
    for k in (30, 40, 50):
        assert b[k] / float(a[k]) == pytest.approx(1.22, abs=0.02), (k, a[k], b[k])
    # a subida é gradual: a meio caminho cresceu cerca de 11%
    assert 1.07 < b[19] / float(a[19]) < 1.16
    # volta seca: depois do hold + 2 quadros o render volta a ser o mesmo
    k_volta = int(round((0.5 + 0.28 + 1.0) * 30)) + 3
    assert all(abs(a[k] - b[k]) <= 1 for k in range(k_volta, 90))
