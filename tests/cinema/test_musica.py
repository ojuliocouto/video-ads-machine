"""W4.B, C10: a música de fundo respira com a voz por AUTOMAÇÃO de volume, nunca por compressor.

Tudo aqui é regra pura ou ffmpeg de poucos segundos. O mix completo (voz + efeitos + música +
limiter) é de tests/audio/test_mix_final.py.

O que cada teste prende, e de onde vem o número (porte da esteira de VSL, sem nome de cliente):
  - trilha nivelada a -20 dBFS, cama em 0,055 sob a fala e 0,42 nas pausas reais do envelope,
    rampa de 150 ms, fade de 1,2 s na entrada e 2,2 s na saída;
  - a expressão de volume contém EXATAMENTE as pausas de audio.pausas_reais (a mesma função que o
    gate_mix usa para cobrar a subida: as duas leituras não podem discordar);
  - peça sem pausa real recebe lista vazia e a cama fica PARADA, porque forçar respiro vira
    bombeamento ("a música fica aumentando e diminuindo do nada").
"""
import json
import math
import re
import subprocess
from pathlib import Path

import numpy as np
import pytest

from audio import pausas_reais
from cinema import musica
from contratos.validar import validar
from projeto import modelo
from tests.fixtures import sinteticos as SIN

RAIZ = Path(__file__).resolve().parents[2]
PAUSAS = [(1.5, 2.1), (4.0, 4.8), (7.25, 8.0)]


def _timeline_valida():
    return json.loads((RAIZ / "contratos" / "exemplos" / "timeline.valido.json").read_text(encoding="utf-8"))


# --- as constantes do C10 -------------------------------------------------------------------------

def test_constantes_do_c10_batem_com_o_plano():
    assert musica.NIVEL_TRILHA_DBFS == -20.0
    assert musica.CAMA_FALA == 0.055
    assert musica.CAMA_PAUSA == 0.42
    assert musica.RAMPA_S == 0.15
    assert musica.FADE_IN_S == 1.2
    assert musica.FADE_OUT_S == 2.2


def test_pausa_real_e_a_do_envelope_nao_uma_constante_nova():
    """0,5 s e queda de 12 dB vêm do envelope (fonte única); a música não redefine a pausa."""
    assert musica.PAUSA_MIN_S == pausas_reais.DUR_MIN_S == 0.5
    assert musica.QUEDA_DB == pausas_reais.QUEDA_DB == 12.0


def test_o_salto_da_cama_e_de_17_7_dB():
    assert musica.salto_db() == pytest.approx(20 * math.log10(0.42 / 0.055), abs=1e-6)
    assert musica.salto_db() == pytest.approx(17.66, abs=0.01)


# --- a expressão de volume ------------------------------------------------------------------------

def test_a_expressao_contem_exatamente_as_pausas_dadas():
    expr = musica.expressao_volume(PAUSAS)
    # leitura independente da função inversa: a vírgula dentro da expressão vai escapada (\,)
    achadas = [(float(a), float(b)) for a, b in re.findall(r"between\(t\\,([0-9.]+)\\,([0-9.]+)\)", expr)]
    assert achadas == PAUSAS
    assert expr.count("between(") == len(PAUSAS)
    assert musica.pausas_da_expressao(expr) == PAUSAS


def test_a_expressao_contem_exatamente_as_pausas_de_pausas_reais(tmp_path):
    voz = SIN.tom_com_pausas(tmp_path / "voz.wav", dur=14.0, pausas=((1.5, 2.1), (4.0, 4.8), (6.5, 7.7), (9.0, 11.0)))
    reais = pausas_reais.pausas(str(voz))
    assert len(reais) == 4
    expr = musica.expressao_volume(reais)
    assert musica.pausas_da_expressao(expr) == [(round(a, 3), round(b, 3)) for a, b in reais]


def test_sem_pausa_real_a_cama_e_constante():
    expr = musica.expressao_volume([])
    assert expr == "0.055"
    assert "between" not in expr and "if(" not in expr
    assert musica.pausas_da_expressao(expr) == []


def test_ganho_no_instante_sobe_com_rampa_de_150_ms_e_desce_do_mesmo_jeito():
    g = lambda t: musica.ganho_no_instante(t, PAUSAS)          # noqa: E731
    assert g(0.0) == pytest.approx(0.055)                      # sob a fala
    assert g(1.5) == pytest.approx(0.055)                      # borda da pausa: ainda na fala
    assert g(1.575) == pytest.approx(0.055 + (0.42 - 0.055) * 0.5)   # meio da rampa
    assert g(1.65) == pytest.approx(0.42)                      # rampa de 150 ms completa
    assert g(1.8) == pytest.approx(0.42)                       # no meio da pausa
    assert g(2.025) == pytest.approx(0.055 + (0.42 - 0.055) * 0.5)   # descida: 150 ms antes do fim
    assert g(2.1) == pytest.approx(0.055)
    assert g(3.0) == pytest.approx(0.055)                      # fala de novo
    assert g(7.6) == pytest.approx(0.42)                       # a terceira pausa também sobe


def test_pausa_curta_demais_para_a_rampa_nao_passa_do_meio_da_subida():
    # 0,2 s de pausa com rampa de 0,15: sobe e desce se encontrando no meio, sem passar de 0,42
    g = musica.ganho_no_instante(5.1, [(5.0, 5.2)])
    assert 0.055 < g < 0.42


@pytest.mark.parametrize("pausas", [[], PAUSAS])
def test_a_expressao_do_ffmpeg_faz_o_que_o_ganho_no_instante_diz(pausas, tmp_path):
    """O ffmpeg avalia `expressao_volume` sobre um sinal constante (0,5) e o resultado, amostra a
    amostra, tem que seguir `ganho_no_instante`. Tolerância de um passo de 10 ms da rampa."""
    sr = 48000                         # o sr do pipeline: o passo de 480 amostras é de 10 ms
    expr = musica.expressao_volume(pausas)
    cadeia = f"aevalsrc=0.5:s={sr}:d=9.0,{musica.filtro_automacao(expr)}"
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i", cadeia,
                        "-f", "f32le", "-ac", "1", "-"], capture_output=True)
    assert r.returncode == 0, r.stderr.decode()[-300:]
    x = np.frombuffer(r.stdout, dtype=np.float32).astype(np.float64)
    assert abs(len(x) - 9 * sr) <= 480
    for t in np.arange(0.2, 8.8, 0.025):
        lido = x[int(round(t * sr))] / 0.5
        esperado = musica.ganho_no_instante(float(t), pausas)
        assert lido == pytest.approx(esperado, abs=0.03), f"t={t:.3f}"


# --- nivelamento da trilha e a cadeia de filtros --------------------------------------------------

def test_ganho_para_nivel_leva_a_media_a_menos_20_dbfs():
    assert musica.ganho_para_nivel_db(-27.3) == pytest.approx(7.3)
    assert musica.ganho_para_nivel_db(-14.0) == pytest.approx(-6.0)
    assert musica.ganho_para_nivel_db(-27.3, alvo_db=-23.0) == pytest.approx(4.3)


def test_nivelamento_de_verdade_sai_em_menos_20_dbfs(tmp_path):
    faixa = SIN.ruido_rosa(tmp_path / "faixa.wav", dur=4.0, amplitude=0.12)      # bem mais baixa que -20
    media = musica.medir_media_db(faixa)
    assert media < -28.0
    ganho = musica.ganho_para_nivel_db(media)
    nivelada = tmp_path / "nivelada.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(faixa), "-af", f"volume={ganho:.3f}dB",
                    str(nivelada)], check=True)
    assert musica.medir_media_db(nivelada) == pytest.approx(-20.0, abs=0.15)


def test_medir_media_considera_so_o_trecho_que_vai_ao_ar(tmp_path):
    # 2 s de rosa forte e 4 s mudos: a média do arquivo inteiro cai 4,8 dB; a do trecho usado, não
    forte = SIN.ruido_rosa(tmp_path / "forte.wav", dur=2.0, amplitude=0.5)
    mudo = tmp_path / "mudo.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                    "-t", "4", str(mudo)], check=True)
    junto = tmp_path / "junto.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(forte), "-i", str(mudo), "-filter_complex",
                    "[0:a][1:a]concat=n=2:v=0:a=1", str(junto)], check=True)
    assert musica.medir_media_db(junto, ate_s=2.0) == pytest.approx(musica.medir_media_db(forte), abs=0.3)
    assert musica.medir_media_db(junto) < musica.medir_media_db(forte) - 3.0


def test_faixa_muda_e_erro_nao_ganho_de_70_dB(tmp_path):
    mudo = tmp_path / "mudo.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                    "-t", "2", str(mudo)], check=True)
    with pytest.raises(musica.TrilhaInvalida) as e:
        musica.medir_media_db(mudo)
    assert "sem sinal" in str(e.value)


def test_cadeia_da_trilha_tem_loop_nivel_fades_e_automacao_nessa_ordem():
    expr = musica.expressao_volume(PAUSAS)
    c = musica.cadeia_da_trilha("[2:a]", "[m]", duracao_s=42.0, ganho_db=6.5, expressao=expr)
    assert c.startswith("[2:a]") and c.endswith("[m]")
    ordem = ["atrim=0:42.000", "volume=6.500dB", "afade=t=in:st=0:d=1.2",
             "afade=t=out:st=39.800:d=2.2", "volume=volume='"]
    pos = [c.index(trecho) for trecho in ordem]
    assert pos == sorted(pos), f"ordem errada na cadeia: {c}"
    assert "eval=frame" in c
    assert "asetnsamples" in c              # passos curtos: a rampa de 150 ms sai lisa


def test_fade_de_saida_nunca_comeca_antes_de_zero():
    c = musica.cadeia_da_trilha("[1:a]", "[m]", duracao_s=1.5, ganho_db=0.0, expressao="0.055")
    assert "afade=t=out:st=0.000" in c


# --- o que vai para o timeline.json ---------------------------------------------------------------

def test_ducking_do_timeline_cumpre_o_contrato():
    t = _timeline_valida()
    t["ducking"] = musica.ducking_para_timeline(PAUSAS)
    assert t["ducking"] == {"cama_fala": 0.055, "cama_pausa": 0.42, "rampa_ms": 150.0,
                            "fade_in_s": 1.2, "fade_out_s": 2.2,
                            "pausas": [{"s": 1.5, "e": 2.1}, {"s": 4.0, "e": 4.8}, {"s": 7.25, "e": 8.0}]}
    assert validar("timeline", t) == []


def test_ducking_sem_pausa_tem_lista_vazia_e_continua_valido():
    t = _timeline_valida()
    t["ducking"] = musica.ducking_para_timeline([])
    assert t["ducking"]["pausas"] == []
    assert validar("timeline", t) == []


def test_ducking_desligado_exige_motivo_e_cumpre_o_contrato():
    t = _timeline_valida()
    t["ducking"] = musica.ducking_desligado("o aluno não usa trilha neste anúncio")
    assert t["ducking"] == {"desligado": True, "motivo": "o aluno não usa trilha neste anúncio"}
    assert validar("timeline", t) == []
    with pytest.raises(ValueError):
        musica.ducking_desligado("")


# --- a trilha vem do projeto do aluno -------------------------------------------------------------

def test_trilha_do_projeto_resolve_o_arquivo_em_trilhas(tmp_path):
    estado = tmp_path / "_local"
    (estado / "trilhas").mkdir(parents=True)
    arq = estado / "trilhas" / "fundo.mp3"
    arq.write_bytes(b"x")
    projeto = modelo.minimo("anuncio", "avatar", look="meu-look", trilha="fundo.mp3")
    caminho, motivo = musica.resolver_trilha(projeto, estado=estado)
    assert caminho == arq and motivo is None


def test_trilha_desligada_devolve_o_motivo_escrito(tmp_path):
    projeto = modelo.minimo("anuncio", "gravado", sem_trilha="o diretor pediu só a voz")
    caminho, motivo = musica.resolver_trilha(projeto, estado=tmp_path)
    assert caminho is None and motivo == "o diretor pediu só a voz"


def test_trilha_declarada_mas_ausente_diz_o_arquivo_e_a_pasta(tmp_path):
    projeto = modelo.minimo("anuncio", "avatar", look="meu-look", trilha="sumiu.mp3")
    with pytest.raises(musica.TrilhaInvalida) as e:
        musica.resolver_trilha(projeto, estado=tmp_path)
    assert "sumiu.mp3" in str(e.value) and "trilhas" in str(e.value)


def test_projeto_sem_nenhuma_declaracao_de_trilha_e_erro_nao_silencio(tmp_path):
    with pytest.raises(musica.TrilhaInvalida):
        musica.resolver_trilha({"slug": "x", "modo": "avatar"}, estado=tmp_path)
