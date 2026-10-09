"""W4.B, C10 + C11 + C12: o mix final do anúncio.

Ordem fixa, porque o contrário já custou caro (27/08): VOZ normalizada primeiro, depois os EFEITOS,
depois a MÚSICA, depois o limiter 0,97. Na ordem inversa o loudnorm "come" a calibragem dos efeitos.

Os testes rápidos olham o grafo de filtros (puro) e as recusas. Os `lento` rodam o ffmpeg de verdade
sobre uma voz sintética com números conhecidos:

  voz     fala de -18 dBFS RMS (o que um áudio a -14 LUFS tem) sobre um piso de -33 dBFS, com pausas
          de verdade (silêncio de fala, o piso continua)
  trilha  ruído rosa de qualquer nível: o mixer a nivela a -20 dBFS

  cama sobe de +1,5 a +8 dB nas pausas e menos de +1,5 dB sob a fala        (régua do gate_mix)
"""
import json
import math
import re
import subprocess
from pathlib import Path

import pytest

from audio import loudness, mix_final, pausas_reais
from cinema import musica, sfx_plano
from tests.fixtures import sinteticos as SIN

RAIZ = Path(__file__).resolve().parents[2]
PAUSAS_DA_VOZ = ((2.0, 2.8), (6.0, 7.2), (9.5, 10.2), (13.0, 14.0))
DUR = 16.0


# --- fixtures -------------------------------------------------------------------------------------

def _ffmpeg(args):
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-400:]


def voz_sintetica(destino, dur=DUR, pausas=PAUSAS_DA_VOZ, fala_db=-18.0, piso_db=-33.0):
    """Fala (seno de 220 Hz, RMS `fala_db`) com silêncio exato nas pausas, sobre um piso de ronco de
    100 Hz a `piso_db`. O ronco tem RMS estável em qualquer janela e não depende da banda medida."""
    ganho_fala = fala_db + 21.07                 # o `sine` do ffmpeg nasce em -21,07 dBFS RMS
    ganho_piso = piso_db + 21.07
    corte = "".join(f",volume=enable='between(t,{a},{b})':volume=0" for a, b in pausas)
    _ffmpeg(["-f", "lavfi", "-i", f"sine=frequency=220:sample_rate=48000:duration={dur},volume={ganho_fala}dB{corte}",
             "-f", "lavfi", "-i", f"sine=frequency=100:sample_rate=48000:duration={dur},volume={ganho_piso}dB",
             "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:normalize=0", "-ac", "1",
             "-c:a", "pcm_s16le", str(destino)])
    return Path(destino)


def trilha_rosa(destino, dur=6.0):
    return SIN.ruido_rosa(destino, dur=dur, amplitude=0.5)


def com_video(voz, destino, dur=DUR):
    """mp4 de verdade (vídeo h264 de cor única + a voz em AAC), como o composite entrega."""
    _ffmpeg(["-f", "lavfi", "-i", f"color=c=black:s=320x240:r=25:d={dur}", "-i", str(voz),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "28",
             "-c:a", "aac", "-b:a", "192k", "-shortest", str(destino)])
    return Path(destino)


def nivel_db(arq, t, d=0.5):
    p = subprocess.run(["ffmpeg", "-v", "info", "-nostdin", "-ss", f"{t:.3f}", "-t", f"{d}", "-i", str(arq), "-vn",
                        "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"mean_volume:\s*(-?[0-9.]+) dB", p.stderr)
    assert m, p.stderr[-300:]
    return float(m.group(1))


def sondar(final, voz, t, d=0.5):
    return nivel_db(final, t, d) - nivel_db(voz, t, d)


def duracao(arq):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 str(arq)], capture_output=True, text=True).stdout.strip())


# --- o grafo de filtros (puro) --------------------------------------------------------------------

def _grafo(n_efeitos=2, tem_trilha=True, canais=1, expr=None):
    return mix_final.construir_grafo(n_efeitos=n_efeitos, tem_trilha=tem_trilha, canais=canais, duracao_s=40.0,
                                     ganho_trilha_db=6.2,
                                     expressao=expr or musica.expressao_volume([(5.0, 5.8), (20.0, 21.0)]))


def test_ordem_do_grafo_e_voz_depois_efeitos_depois_musica_depois_limiter():
    g = _grafo()
    posicoes = [g.index("adelay"),                      # efeitos
                g.index("amix=inputs=3"),               # voz + 2 efeitos
                g.index("volume=volume='"),             # automação da música
                g.index("amix=inputs=2", g.index("volume=volume='")),   # (voz + efeitos) + música
                g.index("alimiter=limit=0.97")]
    assert posicoes == sorted(posicoes), g
    assert g.rstrip().endswith("[a]")


def test_o_amix_nunca_divide_o_ganho_da_voz():
    """O padrão do amix divide o ganho pelo número de entradas e a voz afundaria a cada efeito."""
    g = _grafo()
    assert g.count("amix=") == 2 and g.count("normalize=0") == 2


def test_o_limiter_nao_mexe_no_ganho_sem_pico():
    """`alimiter` com auto level religado sobe o sinal para encostar no limite: -0,3 dB já mudou o LUFS."""
    g = _grafo()
    assert "alimiter=limit=0.97:level=0" in g


def test_sem_trilha_nao_ha_segundo_amix_nem_automacao():
    g = _grafo(tem_trilha=False)
    assert "volume=volume='" not in g and g.count("amix=") == 1 and "alimiter=limit=0.97" in g


def test_sem_efeitos_nem_trilha_o_grafo_so_limita():
    g = _grafo(n_efeitos=0, tem_trilha=False)
    assert "amix" not in g and "adelay" not in g and "alimiter=limit=0.97" in g


def test_todo_ramo_sai_no_layout_da_voz():
    """Voz mono e efeito mono, trilha estéreo: todo ramo é convertido para o layout da voz antes do amix."""
    assert _grafo(canais=1).count("channel_layouts=mono") >= 3
    assert "channel_layouts=stereo" in _grafo(canais=2)


# --- recusas --------------------------------------------------------------------------------------

def test_sem_trilha_exige_o_motivo_escrito(tmp_path):
    voz = voz_sintetica(tmp_path / "voz.wav", dur=4.0, pausas=())
    with pytest.raises(ValueError) as e:
        mix_final.mixar(voz, tmp_path / "saida.wav")
    assert "motivo" in str(e.value)


def test_trilha_inexistente_diz_o_caminho(tmp_path):
    voz = voz_sintetica(tmp_path / "voz.wav", dur=4.0, pausas=())
    with pytest.raises(mix_final.ErroDeMix) as e:
        mix_final.mixar(voz, tmp_path / "saida.wav", trilha=tmp_path / "nao-existe.mp3")
    assert "nao-existe.mp3" in str(e.value)


def test_efeito_inexistente_diz_o_caminho(tmp_path):
    voz = voz_sintetica(tmp_path / "voz.wav", dur=4.0, pausas=())
    with pytest.raises(mix_final.ErroDeMix) as e:
        mix_final.mixar(voz, tmp_path / "saida.wav", efeitos=[(1.0, tmp_path / "riser-que-sumiu.wav")],
                        motivo_sem_trilha="só voz neste teste")
    assert "riser-que-sumiu.wav" in str(e.value)


def test_saida_igual_a_entrada_e_recusada(tmp_path):
    voz = voz_sintetica(tmp_path / "voz.wav", dur=4.0, pausas=())
    with pytest.raises(ValueError):
        mix_final.mixar(voz, voz, motivo_sem_trilha="só voz neste teste")


def test_caminho_da_voz_de_referencia_mora_no_render_do_projeto(tmp_path):
    from projeto import pastas
    pj = pastas.projeto("anuncio", tmp_path / "_local")
    assert mix_final.caminho_voz_ref(pj) == pj.render_dir / "voz_pre_mix.wav"


# --- o mix de verdade -----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mix_completo(tmp_path_factory):
    """Uma peça mixada: voz sintética + trilha + um riser. Serve a vários testes de leitura."""
    pasta = tmp_path_factory.mktemp("mix")
    voz = voz_sintetica(pasta / "voz.wav")
    trilha = trilha_rosa(pasta / "trilha.wav", dur=6.0)            # mais curta que a peça: tem que repetir
    biblioteca = sfx_plano.biblioteca(pasta / "som")
    saida = pasta / "final.wav"
    rel = mix_final.mixar(voz, saida, trilha=trilha, efeitos=[(14.6, biblioteca["riser"])],
                          voz_ref=pasta / "voz_ref.wav")
    return {"pasta": pasta, "voz": voz, "ref": pasta / "voz_ref.wav", "final": saida, "rel": rel, "trilha": trilha}


@pytest.mark.lento
def test_cama_sobe_de_1_5_a_8_dB_nas_pausas_e_menos_de_1_5_dB_sob_a_fala(mix_completo):
    m = mix_completo
    reais = pausas_reais.pausas(str(m["voz"]))
    assert len(reais) == 4
    for a, b in reais:
        centro = (a + b) / 2 - 0.25
        d = sondar(m["final"], m["ref"], centro)
        assert 1.5 <= d <= 8.0, f"pausa {a:.2f}-{b:.2f}: cama {d:+.1f} dB"
    # sob a fala: fora de qualquer pausa e longe do riser (que entra em 14,6 s)
    for t in (0.5, 3.0, 4.5, 8.0, 11.0, 12.0):
        d = sondar(m["final"], m["ref"], t)
        assert d < 1.5, f"t={t}: cama {d:+.2f} dB sob a fala"


@pytest.mark.lento
def test_as_pausas_do_relatorio_sao_as_de_pausas_reais(mix_completo):
    m = mix_completo
    reais = [(round(a, 3), round(b, 3)) for a, b in pausas_reais.pausas(str(m["voz"]))]
    d = m["rel"]["ducking"]
    assert [(p["s"], p["e"]) for p in d["pausas"]] == reais
    assert (d["cama_fala"], d["cama_pausa"], d["rampa_ms"], d["fade_in_s"], d["fade_out_s"]) == \
        (0.055, 0.42, 150.0, 1.2, 2.2)


@pytest.mark.lento
def test_a_voz_de_referencia_e_a_voz_antes_do_mix(mix_completo):
    m = mix_completo
    assert abs(duracao(m["ref"]) - duracao(m["voz"])) < 0.02
    for t in (1.0, 5.0, 12.0):
        assert nivel_db(m["ref"], t) == pytest.approx(nivel_db(m["voz"], t), abs=0.05)


@pytest.mark.lento
def test_fade_de_entrada_de_1_2_s_e_de_saida_de_2_2_s(mix_completo):
    """Sem voz (pausa de verdade no fim do arquivo), o que se ouve é a música com seus fades."""
    pasta = mix_completo["pasta"]
    mudo = pasta / "mudo.wav"
    _ffmpeg(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "10", str(mudo)])
    saida = pasta / "so_musica.wav"
    mix_final.mixar(mudo, saida, trilha=mix_completo["trilha"], pausas=[])
    # cama constante em 0,055 -> -45,2 dBFS; nos fades a música fica bem abaixo disso
    meio = nivel_db(saida, 4.0, 1.0)
    assert meio == pytest.approx(-20.0 + 20 * math.log10(0.055), abs=1.0)
    assert nivel_db(saida, 0.0, 0.2) < meio - 8.0          # primeiros 0,2 s do fade de 1,2 s
    assert nivel_db(saida, 9.8, 0.2) < meio - 8.0          # últimos 0,2 s do fade de 2,2 s
    assert nivel_db(saida, 1.4, 0.4) == pytest.approx(meio, abs=1.0)    # depois de 1,2 s já está cheia


@pytest.mark.lento
def test_riser_entra_na_hora_marcada(tmp_path):
    voz = voz_sintetica(tmp_path / "voz.wav", dur=14.0, pausas=((7.0, 12.0),))
    biblioteca = sfx_plano.biblioteca(tmp_path / "som")
    saida = tmp_path / "final.wav"
    mix_final.mixar(voz, saida, efeitos=[(8.0, biblioteca["riser"])], motivo_sem_trilha="só voz neste teste",
                    voz_ref=tmp_path / "ref.wav")
    antes = sondar(saida, tmp_path / "ref.wav", 7.2, 0.5)             # pausa, sem efeito
    durante = sondar(saida, tmp_path / "ref.wav", 8.3, 0.7)           # dentro do riser de 1,2 s
    # riser a -34,3 dBFS sobre piso de -33: soma 10*log10(1+10^(-0,13)) = +2,6 dB
    assert antes == pytest.approx(0.0, abs=0.15)
    assert 1.5 <= durante <= 4.0


@pytest.mark.lento
def test_peca_sem_pausa_real_deixa_a_cama_parada(tmp_path):
    voz = voz_sintetica(tmp_path / "voz.wav", dur=14.0, pausas=())
    assert pausas_reais.pausas(str(voz)) == []
    saida = tmp_path / "final.wav"
    rel = mix_final.mixar(voz, saida, trilha=trilha_rosa(tmp_path / "t.wav"), voz_ref=tmp_path / "ref.wav")
    assert rel["ducking"]["pausas"] == []
    deltas = [sondar(saida, tmp_path / "ref.wav", t) for t in (2.0, 4.0, 6.0, 8.0, 10.0)]
    assert max(deltas) < 1.5
    assert max(deltas) - min(deltas) < 0.3, f"a cama oscilou sem pausa nenhuma: {deltas}"


@pytest.mark.lento
def test_a_saida_em_mp4_vai_com_o_video_copiado_em_aac_48k(tmp_path):
    voz = voz_sintetica(tmp_path / "voz.wav")
    video = com_video(voz, tmp_path / "voz.mp4")
    saida = tmp_path / "final.mp4"
    mix_final.mixar(video, saida, trilha=trilha_rosa(tmp_path / "t.wav"), voz_ref=tmp_path / "ref.wav")
    fluxos = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,sample_rate,codec_type",
                             "-of", "json", str(saida)], capture_output=True, text=True).stdout
    por_tipo = {s["codec_type"]: s for s in json.loads(fluxos)["streams"]}
    assert por_tipo["video"]["codec_name"] == "h264"
    assert por_tipo["audio"]["codec_name"] == "aac" and por_tipo["audio"]["sample_rate"] == "48000"
    assert abs(duracao(saida) - duracao(video)) < 0.1


@pytest.mark.lento
def test_entrega_a_menos_14_lufs_mais_ou_menos_1_2_e_true_peak_ate_menos_1_5(tmp_path):
    bruta = voz_sintetica(tmp_path / "bruta.wav", fala_db=-30.0, piso_db=-45.0)      # voz baixa, como a gravada
    video = com_video(bruta, tmp_path / "bruto.mp4")
    normalizado = loudness.normalizar(video, tmp_path / "voz_norm.mp4")          # passo 1 do pipeline
    biblioteca = sfx_plano.biblioteca(tmp_path / "som")
    saida = tmp_path / "final.mp4"
    rel = mix_final.mixar(normalizado, saida, trilha=trilha_rosa(tmp_path / "t.wav"),
                          efeitos=[(14.6, biblioteca["riser"])], voz_ref=tmp_path / "ref.wav")
    m = loudness.medir(saida)
    assert m.integrado_lufs == pytest.approx(-14.0, abs=1.2)
    assert m.true_peak_dbtp <= -1.5
    assert rel["loudness"]["lufs"] == pytest.approx(m.integrado_lufs, abs=0.15)


def voz_quente(destino, tmp_path, lufs_alvo=-13.3, tp_alvo=-0.3):
    """Voz que chega ao mixer ACIMA do teto de true peak: -13,3 LUFS com picos a -0,3 dBFS. Fala sintética
    mais um pulso gaussiano por 1,3 s (energia desprezível, pico alto), com o ganho posto para cair nos dois
    alvos. O LUFS vem de uma medição, não de uma conta, porque a fala sintética muda com o piso."""
    base = voz_sintetica(tmp_path / "base.wav")
    ganho = lufs_alvo - loudness.medir(base).integrado_lufs
    pico = 10 ** ((tp_alvo - ganho) / 20)                  # antes do ganho; depois dele o pico cai em tp_alvo
    pulso = "aevalsrc=exprs='%g*exp(-pow((mod(t\\,1.3)-0.1)/0.0003\\,2))':s=48000:d=%s" % (pico, DUR)
    _ffmpeg(["-i", str(base), "-f", "lavfi", "-i", pulso, "-filter_complex",
             "[0:a][1:a]amix=inputs=2:duration=first:normalize=0,volume=%.3fdB" % ganho, "-ac", "1",
             "-c:a", "pcm_s16le", str(tmp_path / "quente.wav")])
    return com_video(tmp_path / "quente.wav", destino)


@pytest.mark.lento
def test_voz_que_chega_com_true_peak_alto_sai_dentro_da_entrega(tmp_path):
    """O mix soma a música e os efeitos em cima de uma voz que já encosta no teto: o mixer confere a
    entrega no arquivo FINAL e corrige o ganho a partir do PCM (um AAC só)."""
    quente = voz_quente(tmp_path / "voz_quente.mp4", tmp_path)
    antes = loudness.medir(quente)
    assert antes.true_peak_dbtp > -1.0 and antes.integrado_lufs == pytest.approx(-13.3, abs=0.4)   # a entrada está fora
    saida = tmp_path / "final.mp4"
    rel = mix_final.mixar(quente, saida, trilha=trilha_rosa(tmp_path / "t.wav"), voz_ref=tmp_path / "ref.wav")
    m = loudness.medir(saida)
    assert m.true_peak_dbtp <= -1.5
    assert abs(m.integrado_lufs + 14.0) <= 1.2
    ajuste = rel["loudness"]["ajuste_db"]
    assert -3.0 < ajuste < -0.5                                      # tirou o que sobrava e só isso
    # a voz de referência é a voz como está no final: baixou o mesmo tanto, senão o gate leria "cama negativa"
    assert nivel_db(tmp_path / "ref.wav", 3.0) == pytest.approx(nivel_db(quente, 3.0) + ajuste, abs=0.15)


# --- o bloco de áudio do build_composite ----------------------------------------------------------

@pytest.mark.lento
def test_bloco_de_audio_do_build_composite_mixa_pelo_plano_de_sfx_da_timeline_e_guarda_a_voz(tmp_path, monkeypatch):
    """O build por projeto (W5.A) mixa com o plano de SFX da TIMELINE (relógio único), não mais pela prancha: um
    grafo, um AAC, automação, riser, tick por linha de pilha e limiter."""
    import build_composite as BC
    tl = {"relogio": {"aceleracao": 1.35, "a0": 0.0},
          "segmentos": [{"tipo": "apresentador", "s": 0.0, "e": 8.1}, {"tipo": "insert", "s": 8.1, "e": 13.5},
                        {"tipo": "apresentador", "s": 13.5, "e": 21.6}],
          "letterings": [{"id": "p1a", "s": 4.0, "d": 1.4, "pilha": "p1", "estilo": "serif_editorial"},
                         {"id": "p1b", "s": 5.4, "d": 1.6, "pilha": "p1", "estilo": "serif_editorial"}],
          "cta": {"inicio": 21.0, "logo": 21.0}}
    sfx = sfx_plano.plano_de_sfx(tl)
    voz = voz_sintetica(tmp_path / "voz.wav", dur=16.0)
    video = com_video(voz, tmp_path / "final.mp4", dur=16.0)
    trilha = trilha_rosa(tmp_path / "fundo.wav", dur=8.0)
    monkeypatch.setattr(sfx_plano, "pasta_padrao", lambda: tmp_path / "som")
    saida, rel = BC.mixar_audio(video, tmp_path / "mixado.mp4", sfx=sfx, relogio=tl["relogio"], trilha=trilha,
                                workdir=tmp_path)
    assert saida.is_file()
    assert {e["efeito"] for e in rel["sfx"]} == {"tick", "riser"}
    assert len([e for e in rel["sfx"] if e["efeito"] == "tick"]) == 2
    assert (tmp_path / "voz_pre_mix.wav").exists()
    assert [e["t"] for e in rel["sfx"] if e["efeito"] == "riser"] == [19.65]       # 1,0 s entregue antes do CTA
    assert rel["ducking"]["cama_fala"] == 0.055
    assert loudness.medir(saida).true_peak_dbtp <= -1.5
