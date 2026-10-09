"""Cadeia de transições (W2.B): do segmento renderizado ao vídeo único.

Os goldens do grafo vêm do `produzir_roteiro.py` ORIGINAL (commit 2ebd1cc) rodado sobre a
fixture de paridade com quatro configurações (padrão, concat puro, whip de 0,20 s e tipo fixo).
As regras que o grafo carrega nasceram de defeitos medidos: juntas secas são CONCAT (xfade
curto amortece o corte e xfade de um quadro colapsa a cadeia), todo segmento é forçado a uma
contagem exata de quadros e todo lado passa por `settb=AVTB`.
"""
import subprocess

import pytest

from footage import cadeia as CA

# blocos e spans da fixture, depois do plano de ritmo: (type, narr)
BLOCOS_FIXTURE = [("insert", "a"), ("insert", "b"), ("orig", "c"), ("lettering", "d"),
                  ("insert", "e"), ("lettering_logo", "f")]
SPANS_FIXTURE = [(0.62, 4.82), (4.82, 5.6), (5.6, 9.6), (9.6, 10.88), (10.88, 15.52), (15.52, 17.68)]

# variante -> {"env": {...}, "fc": "<filter_complex do original>", "saida": "v5"}
GOLDEN_CADEIA = {'padrao': {'env': {},
            'fc': '[0:v]trim=start_frame=0,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame=126,setpts=PTS-STARTPTS,settb=AVTB[n0]; '
                  '[1:v]trim=start_frame=0,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame=25,setpts=PTS-STARTPTS,settb=AVTB[n1]; '
                  '[2:v]trim=start_frame=0,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame=120,setpts=PTS-STARTPTS,settb=AVTB[n2]; '
                  '[3:v]trim=start_frame=0,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame=38,setpts=PTS-STARTPTS,settb=AVTB[n3]; '
                  '[4:v]trim=start_frame=0,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame=139,setpts=PTS-STARTPTS,settb=AVTB[n4]; '
                  '[5:v]trim=start_frame=0,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame=65,setpts=PTS-STARTPTS,settb=AVTB[n5]; '
                  '[n0][n1]concat=n=2:v=1:a=0,settb=AVTB[v1]; '
                  '[v1][n2]xfade=transition=smoothright:duration=0.08:offset=4.9533,settb=AVTB[v2]; '
                  '[v2][n3]concat=n=2:v=1:a=0,settb=AVTB[v3]; '
                  '[v3][n4]concat=n=2:v=1:a=0,settb=AVTB[v4]; '
                  '[v4][n5]concat=n=2:v=1:a=0,settb=AVTB[v5]',
            'saida': 'v5'},
 'concat_puro': {'env': {'VAM_XF': '0', 'VAM_XF_SECO': '0'},
                 'fc': '[0:v][1:v][2:v][3:v][4:v][5:v]concat=n=6:v=1:a=0[vcat]',
                 'saida': 'vcat'},
 'whip_020': {'env': {'VAM_XF': '0.20'},
              'fc': '[0:v]trim=start_frame=0,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame=126,setpts=PTS-STARTPTS,settb=AVTB[n0]; '
                    '[1:v]trim=start_frame=0,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame=29,setpts=PTS-STARTPTS,settb=AVTB[n1]; '
                    '[2:v]trim=start_frame=0,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame=120,setpts=PTS-STARTPTS,settb=AVTB[n2]; '
                    '[3:v]trim=start_frame=0,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame=38,setpts=PTS-STARTPTS,settb=AVTB[n3]; '
                    '[4:v]trim=start_frame=0,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame=139,setpts=PTS-STARTPTS,settb=AVTB[n4]; '
                    '[5:v]trim=start_frame=0,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame=65,setpts=PTS-STARTPTS,settb=AVTB[n5]; '
                    '[n0][n1]concat=n=2:v=1:a=0,settb=AVTB[v1]; '
                    '[v1][n2]xfade=transition=smoothright:duration=0.2:offset=4.9667,settb=AVTB[v2]; '
                    '[v2][n3]concat=n=2:v=1:a=0,settb=AVTB[v3]; '
                    '[v3][n4]concat=n=2:v=1:a=0,settb=AVTB[v4]; '
                    '[v4][n5]concat=n=2:v=1:a=0,settb=AVTB[v5]',
              'saida': 'v5'},
 'tipo_fixo': {'env': {'VAM_XF_TIPO': 'slideleft'},
               'fc': '[0:v]trim=start_frame=0,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame=128,setpts=PTS-STARTPTS,settb=AVTB[n0]; '
                     '[1:v]trim=start_frame=0,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame=25,setpts=PTS-STARTPTS,settb=AVTB[n1]; '
                     '[2:v]trim=start_frame=0,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame=122,setpts=PTS-STARTPTS,settb=AVTB[n2]; '
                     '[3:v]trim=start_frame=0,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame=40,setpts=PTS-STARTPTS,settb=AVTB[n3]; '
                     '[4:v]trim=start_frame=0,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame=141,setpts=PTS-STARTPTS,settb=AVTB[n4]; '
                     '[5:v]trim=start_frame=0,setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration=0.5,trim=end_frame=65,setpts=PTS-STARTPTS,settb=AVTB[n5]; '
                     '[n0][n1]xfade=transition=slideleft:duration=0.08:offset=4.1867,settb=AVTB[v1]; '
                     '[v1][n2]xfade=transition=slideleft:duration=0.08:offset=4.9400,settb=AVTB[v2]; '
                     '[v2][n3]xfade=transition=slideleft:duration=0.08:offset=8.9267,settb=AVTB[v3]; '
                     '[v3][n4]xfade=transition=slideleft:duration=0.08:offset=10.1800,settb=AVTB[v4]; '
                     '[v4][n5]xfade=transition=slideleft:duration=0.08:offset=14.8000,settb=AVTB[v5]',
               'saida': 'v5'}}

# {"entra", "sai", "xf_dur", "xf_tipo_par", "xf_tipo_impar"}
GOLDEN_XF = [{'entra': 'orig', 'sai': 'orig', 'xf_dur': 0.0, 'xf_tipo_par': 'fade', 'xf_tipo_impar': 'fade'},
 {'entra': 'orig',
  'sai': 'insert',
  'xf_dur': 0.08,
  'xf_tipo_par': 'smoothleft',
  'xf_tipo_impar': 'smoothright'},
 {'entra': 'orig',
  'sai': 'logo',
  'xf_dur': 0.08,
  'xf_tipo_par': 'smoothleft',
  'xf_tipo_impar': 'smoothright'},
 {'entra': 'orig',
  'sai': 'lettering',
  'xf_dur': 0.0,
  'xf_tipo_par': 'fade',
  'xf_tipo_impar': 'fade'},
 {'entra': 'orig',
  'sai': 'lettering_logo',
  'xf_dur': 0.08,
  'xf_tipo_par': 'smoothleft',
  'xf_tipo_impar': 'smoothright'},
 {'entra': 'insert', 'sai': 'orig', 'xf_dur': 0.0, 'xf_tipo_par': 'fade', 'xf_tipo_impar': 'fade'},
 {'entra': 'insert',
  'sai': 'insert',
  'xf_dur': 0.0,
  'xf_tipo_par': 'fade',
  'xf_tipo_impar': 'fade'},
 {'entra': 'insert', 'sai': 'logo', 'xf_dur': 0.0, 'xf_tipo_par': 'fade', 'xf_tipo_impar': 'fade'},
 {'entra': 'insert',
  'sai': 'lettering',
  'xf_dur': 0.0,
  'xf_tipo_par': 'fade',
  'xf_tipo_impar': 'fade'},
 {'entra': 'insert',
  'sai': 'lettering_logo',
  'xf_dur': 0.0,
  'xf_tipo_par': 'fade',
  'xf_tipo_impar': 'fade'},
 {'entra': 'logo', 'sai': 'orig', 'xf_dur': 0.0, 'xf_tipo_par': 'fade', 'xf_tipo_impar': 'fade'},
 {'entra': 'logo', 'sai': 'insert', 'xf_dur': 0.0, 'xf_tipo_par': 'fade', 'xf_tipo_impar': 'fade'},
 {'entra': 'logo', 'sai': 'logo', 'xf_dur': 0.0, 'xf_tipo_par': 'fade', 'xf_tipo_impar': 'fade'},
 {'entra': 'logo',
  'sai': 'lettering',
  'xf_dur': 0.0,
  'xf_tipo_par': 'fade',
  'xf_tipo_impar': 'fade'},
 {'entra': 'logo',
  'sai': 'lettering_logo',
  'xf_dur': 0.0,
  'xf_tipo_par': 'fade',
  'xf_tipo_impar': 'fade'},
 {'entra': 'lettering',
  'sai': 'orig',
  'xf_dur': 0.0,
  'xf_tipo_par': 'fade',
  'xf_tipo_impar': 'fade'},
 {'entra': 'lettering',
  'sai': 'insert',
  'xf_dur': 0.08,
  'xf_tipo_par': 'slideleft',
  'xf_tipo_impar': 'slideright'},
 {'entra': 'lettering',
  'sai': 'logo',
  'xf_dur': 0.08,
  'xf_tipo_par': 'slideleft',
  'xf_tipo_impar': 'slideright'},
 {'entra': 'lettering',
  'sai': 'lettering',
  'xf_dur': 0.0,
  'xf_tipo_par': 'fade',
  'xf_tipo_impar': 'fade'},
 {'entra': 'lettering',
  'sai': 'lettering_logo',
  'xf_dur': 0.08,
  'xf_tipo_par': 'slideleft',
  'xf_tipo_impar': 'slideright'},
 {'entra': 'lettering_logo',
  'sai': 'orig',
  'xf_dur': 0.0,
  'xf_tipo_par': 'fade',
  'xf_tipo_impar': 'fade'},
 {'entra': 'lettering_logo',
  'sai': 'insert',
  'xf_dur': 0.0,
  'xf_tipo_par': 'fade',
  'xf_tipo_impar': 'fade'},
 {'entra': 'lettering_logo',
  'sai': 'logo',
  'xf_dur': 0.0,
  'xf_tipo_par': 'fade',
  'xf_tipo_impar': 'fade'},
 {'entra': 'lettering_logo',
  'sai': 'lettering',
  'xf_dur': 0.0,
  'xf_tipo_par': 'fade',
  'xf_tipo_impar': 'fade'},
 {'entra': 'lettering_logo',
  'sai': 'lettering_logo',
  'xf_dur': 0.0,
  'xf_tipo_par': 'fade',
  'xf_tipo_impar': 'fade'}]


def _blocos():
    return [{"type": t, "narr": n} for t, n in BLOCOS_FIXTURE]


# ------------------------------------------------------------------ configuração

def test_transicao_do_ambiente_tem_os_defaults_do_motor():
    tr = CA.Transicao.do_ambiente({})
    assert (tr.xf, tr.xf_seco, tr.tipo) == (0.08, 0.04, "auto")


def test_transicao_le_as_tres_variaveis():
    tr = CA.Transicao.do_ambiente({"VAM_XF": "0.2", "VAM_XF_SECO": "0", "VAM_XF_TIPO": "slideleft"})
    assert (tr.xf, tr.xf_seco, tr.tipo) == (0.2, 0.0, "slideleft")


@pytest.mark.parametrize("tipo", ["fadeblack", "fadewhite"])
def test_transicao_que_apaga_a_tela_e_proibida(tipo):
    with pytest.raises(CA.ErroFootage) as e:
        CA.Transicao.do_ambiente({"VAM_XF_TIPO": tipo})
    assert tipo in str(e.value) and "pisca" in str(e.value)


# ------------------------------------------------------------------ duração e tipo de cada corte

@pytest.mark.parametrize("c", GOLDEN_XF, ids=lambda c: f"{c['sai']}->{c['entra']}")
def test_duracao_e_tipo_da_transicao_batem_com_o_original(c):
    tr = CA.Transicao.do_ambiente({})
    entra, sai = {"type": c["entra"], "narr": "x"}, {"type": c["sai"], "narr": "y"}
    assert CA.xf_dur(entra, sai, tr) == c["xf_dur"]
    assert CA.xf_tipo(entra, 3, sai, tr) == c["xf_tipo_par"]
    assert CA.xf_tipo(entra, 4, sai, tr) == c["xf_tipo_impar"]


def test_tipo_fixo_vale_pra_todo_corte_com_a_duracao_xf():
    tr = CA.Transicao.do_ambiente({"VAM_XF_TIPO": "slideleft", "VAM_XF": "0.12"})
    a, b = {"type": "orig"}, {"type": "insert"}
    assert CA.xf_dur(b, a, tr) == 0.12 and CA.xf_dur(a, b, tr) == 0.12
    assert CA.xf_tipo(a, 1, b, tr) == "slideleft"


def test_entrada_de_insert_e_apresentador_com_apresentador_sao_secos():
    tr = CA.Transicao.do_ambiente({})
    assert CA.xf_dur({"type": "insert"}, {"type": "orig"}, tr) == 0.0
    assert CA.xf_dur({"type": "orig"}, {"type": "lettering"}, tr) == 0.0
    assert CA.xf_dur({"type": "orig"}, {"type": "insert"}, tr) == tr.xf       # a volta pro avatar é o whip


# ------------------------------------------------------------------ contagem exata de quadros

def test_cada_segmento_tem_quadros_exatos_do_bloco_mais_a_cauda():
    tr = CA.Transicao.do_ambiente({})
    assert CA.contagem_de_quadros(_blocos(), SPANS_FIXTURE, tr) == [126, 25, 120, 38, 139, 65]


def test_cauda_do_whip_entra_na_contagem():
    tr = CA.Transicao.do_ambiente({"VAM_XF": "0.20"})
    assert CA.contagem_de_quadros(_blocos(), SPANS_FIXTURE, tr) == [126, 29, 120, 38, 139, 65]


def test_o_ultimo_segmento_nao_tem_cauda():
    tr = CA.Transicao.do_ambiente({})
    kf = CA.contagem_de_quadros(_blocos(), SPANS_FIXTURE, tr)
    assert kf[-1] == round((17.68 - 15.52) * 30)


# ------------------------------------------------------------------ grafo

@pytest.mark.parametrize("nome", sorted(GOLDEN_CADEIA))
def test_grafo_bate_com_o_original(nome):
    g = GOLDEN_CADEIA[nome]
    tr = CA.Transicao.do_ambiente(g["env"])
    r = CA.montar_grafo(_blocos(), SPANS_FIXTURE, tr, ini=[0] * 6)
    assert "; ".join(r["fc"]) == g["fc"]
    assert r["saida"] == g["saida"]


def test_xf_e_xf_seco_quase_zero_viram_concat_puro():
    tr = CA.Transicao.do_ambiente({"VAM_XF": "0", "VAM_XF_SECO": "0.005"})
    assert CA.concat_puro(tr) is True
    r = CA.montar_grafo(_blocos(), SPANS_FIXTURE, tr, ini=None)
    assert r["fc"] == ["[0:v][1:v][2:v][3:v][4:v][5:v]concat=n=6:v=1:a=0[vcat]"]
    assert r["secos"] == 5 and r["xf_total"] == 0.0 and r["saida"] == "vcat"
    assert "xfade" not in "".join(r["fc"])


def test_whip_curto_continua_xfade_so_a_duracao_zero_vira_concat():
    """0,03 s é menos que a junção seca padrão mas ainda é transição: xfade. Só zero é corte de verdade."""
    tr = CA.Transicao(xf=0.03, xf_seco=0.04, tipo="auto")
    r = CA.montar_grafo(_blocos(), SPANS_FIXTURE, tr, ini=[0] * 6)
    fc = "; ".join(r["fc"])
    assert "xfade=transition=smoothright:duration=0.03:" in fc
    assert r["secos"] == 4 and r["xf_total"] == pytest.approx(0.03)


def test_basta_um_dos_dois_ser_maior_pra_voltar_ao_grafo_misto():
    assert CA.concat_puro(CA.Transicao.do_ambiente({"VAM_XF": "0", "VAM_XF_SECO": "0.04"})) is False
    assert CA.concat_puro(CA.Transicao.do_ambiente({"VAM_XF": "0.08", "VAM_XF_SECO": "0"})) is False


def test_grafo_misto_forca_contagem_exata_e_um_timebase_unico():
    tr = CA.Transicao.do_ambiente({})
    r = CA.montar_grafo(_blocos(), SPANS_FIXTURE, tr, ini=[0] * 6)
    fc = "; ".join(r["fc"])
    for k in (126, 25, 120, 38, 139, 65):
        assert f"trim=end_frame={k},setpts=PTS-STARTPTS,settb=AVTB" in fc
    assert fc.count("settb=AVTB") == 6 + 5                    # 6 entradas + 5 juntas
    assert fc.count("concat=n=2") == 4 and fc.count("xfade=transition=") == 1
    assert r["secos"] == 4
    assert r["xf_total"] == pytest.approx(0.08)
    assert r["durs"] == [k / 30 for k in (126, 25, 120, 38, 139, 65)]


def test_segmento_com_primeiro_quadro_preto_perde_esse_quadro():
    tr = CA.Transicao.do_ambiente({})
    r = CA.montar_grafo(_blocos(), SPANS_FIXTURE, tr, ini=[0, 1, 0, 0, 0, 0])
    assert "[1:v]trim=start_frame=1," in "; ".join(r["fc"])
    assert "[0:v]trim=start_frame=0," in "; ".join(r["fc"])
    assert "trim=end_frame=25" in "; ".join(r["fc"])          # a contagem final não muda


# ------------------------------------------------------------------ medidas e gates

def test_lum_do_primeiro_quadro_mede_so_o_painel_de_cima(monkeypatch):
    cmds = []

    def falso(cmd, **kw):
        cmds.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, bytes([10] * 1024 + [50] * 1024 + [100] * 1024), b"")

    monkeypatch.setattr(CA.subprocess, "run", falso)
    assert CA.lum_primeiro_quadro("/t/s.mp4") == pytest.approx(255.0 * 10 / 100)
    assert cmds[0] == ["ffmpeg", "-v", "error", "-i", "/t/s.mp4", "-frames:v", "3", "-vf",
                       "crop=1080:1152:0:0,format=gray,scale=32:32", "-f", "rawvideo", "-pix_fmt", "gray", "-"]


def test_lum_sem_dados_suficientes_ou_sem_luz_devolve_255(monkeypatch):
    monkeypatch.setattr(CA.subprocess, "run", lambda c, **k: subprocess.CompletedProcess(c, 0, b"\x01" * 100, b""))
    assert CA.lum_primeiro_quadro("/t/a.mp4") == 255
    monkeypatch.setattr(CA.subprocess, "run",
                        lambda c, **k: subprocess.CompletedProcess(c, 0, bytes([5] * 2048 + [0] * 1024), b""))
    assert CA.lum_primeiro_quadro("/t/b.mp4") == 255


def test_quadro_preto_e_o_que_tem_menos_da_metade_da_luz_do_terceiro():
    assert CA.lum_primeiro_quadro_e_preto(127.9) is True
    assert CA.lum_primeiro_quadro_e_preto(128.0) is False


def test_duracao_do_video_e_a_contagem_de_quadros_sobre_30(monkeypatch):
    cmds = []

    def falso(cmd, **kw):
        cmds.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "126\n", "")

    monkeypatch.setattr(CA.subprocess, "run", falso)
    assert CA.vdur("/t/s.mp4") == 4.2
    assert cmds[0] == ["ffprobe", "-v", "error", "-select_streams", "v", "-count_frames", "-show_entries",
                       "stream=nb_read_frames", "-of", "default=nw=1:nk=1", "/t/s.mp4"]


def test_gate_de_segmento_aborta_quando_a_duracao_foge_de_mais_de_0_1_s():
    tr = CA.Transicao.do_ambiente({})
    esperado = [(e - s) + (CA.xf_dur(_blocos()[i + 1], _blocos()[i], tr) if i < 5 else 0.0)
                for i, (s, e) in enumerate(SPANS_FIXTURE)]
    CA.verificar_segmentos(SPANS_FIXTURE, esperado, _blocos(), tr)                   # igual: passa
    ruim = list(esperado)
    ruim[3] += 0.2
    with pytest.raises(CA.ErroFootage) as e:
        CA.verificar_segmentos(SPANS_FIXTURE, ruim, _blocos(), tr)
    assert "seg 03" in str(e.value) and "dessincronizado" in str(e.value)


def test_gate_da_cadeia_aborta_quando_a_cadeia_colapsa():
    CA.verificar_cadeia(real=17.0, esperado=17.05, spans_total=17.06)                  # dentro de 0,15 s
    with pytest.raises(CA.ErroFootage) as e:
        CA.verificar_cadeia(real=10.0, esperado=17.05, spans_total=17.06)
    assert "colapsou" in str(e.value)


def test_arredondamento_de_quadros_so_vira_aviso(capsys):
    CA.verificar_cadeia(real=17.0, esperado=17.0, spans_total=17.8)                    # grafo difere dos spans em 0,8 s
    out = capsys.readouterr().out
    assert "AVISO cadeia" in out and "ok" in out


# ------------------------------------------------------------------ montagem completa (com ffmpeg falso)

def test_montar_vchain_mede_o_preto_dos_segmentos_e_roda_o_ffmpeg_uma_vez(tmp_path, monkeypatch):
    tr = CA.Transicao.do_ambiente({})
    cmds, medidos = [], []
    monkeypatch.setattr(CA, "run", lambda c: cmds.append([str(x) for x in c]))
    monkeypatch.setattr(CA, "vdur", lambda p: sum(k for k in [0]) or 17.06)

    def lum(p):
        medidos.append(p)
        return 255.0

    segs = [f"/t/s{i:02d}.mp4" for i in range(6)]
    r = CA.montar_vchain(segs, _blocos(), SPANS_FIXTURE, [1.0] * 6, tr, str(tmp_path / "vchain0.mp4"), lum=lum)
    assert medidos == segs
    assert len(cmds) == 1
    cmd = cmds[0]
    assert cmd[:2] == ["ffmpeg", "-y"] and cmd.count("-i") == 6
    assert cmd[cmd.index("-map") + 1] == "[v5]"
    assert cmd[-1] == str(tmp_path / "vchain0.mp4")
    assert r["esperado"] == pytest.approx(sum(k / 30 for k in (126, 25, 120, 38, 139, 65)) - 0.08)


def test_montar_vchain_em_concat_puro_nao_mede_nada(tmp_path, monkeypatch):
    tr = CA.Transicao.do_ambiente({"VAM_XF": "0", "VAM_XF_SECO": "0"})
    cmds = []
    monkeypatch.setattr(CA, "run", lambda c: cmds.append([str(x) for x in c]))
    monkeypatch.setattr(CA, "vdur", lambda p: 17.06)

    def proibido(p):
        raise AssertionError("concat puro não mede o primeiro quadro")

    segs = [f"/t/s{i:02d}.mp4" for i in range(6)]
    r = CA.montar_vchain(segs, _blocos(), SPANS_FIXTURE, [4.2, 0.78, 4.0, 1.28, 4.64, 2.16], tr,
                         str(tmp_path / "v.mp4"), lum=proibido)
    assert cmds[0][cmds[0].index("-filter_complex") + 1] == "[0:v][1:v][2:v][3:v][4:v][5:v]concat=n=6:v=1:a=0[vcat]"
    assert r["esperado"] == pytest.approx(17.06)
