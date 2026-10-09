"""W4.C: gate_cor (C5). Mede o vídeo ENTREGUE, nunca o plano: as tags bt709, o quadro 0 contra a
mediana dos quadros, a mediana de luminância de cada plano e a razão R/G na caixa do rosto.

Cada regra tem o controle (passa) e o mutante (reprova), todos com vídeo sintético de cor
chapada de luminância conhecida. O resultado vem no formato de um gate do laudo.
"""
import copy
import json
import subprocess
from pathlib import Path

import pytest

from contratos.validar import validar
from gates import gate_cor
from projeto import modelo, pastas
from tests.fixtures import sinteticos as S

RAIZ = Path(__file__).resolve().parents[2]
TAMANHO = "160x284"
CAIXA = (40, 60, 60, 60)            # x, y, largura, altura do rosto nos vídeos de teste
CINZA = "0x808080"                  # luminância 128
ESCURO = "0x0A0A0A"                 # luminância cerca de 10: abaixo do piso de 20
PELE = "0xC89078"                   # R/G 1,39: pele normal
PELE_VERMELHA = "0xE87850"          # R/G 1,93: rosto vermelho demais
TAGS_BT709 = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
              "-color_range", "tv"]


HLG = "setparams=colorspace=bt2020nc:color_primaries=bt2020:color_trc=arib-std-b67"


def codificar(destino, segmentos, tags=True, fps=10, extra=()):
    """Vídeo mudo de cor chapada. `segmentos` = [(duração, cor de fundo, cor do rosto ou None)].
    `tags=True` codifica como o grade_final (filtro colorspace + as três tags); `False` não
    escreve tag nenhuma (o mutante "sem tags"); `"hlg"` marca como HDR/HLG pelo filtro setparams
    (as flags -color_primaries e -color_trc sozinhas não chegam ao arquivo neste ffmpeg)."""
    S.exigir_ffmpeg()
    entradas, rotulos, partes = [], "", []
    for i, (dur, cor, rosto) in enumerate(segmentos):
        cadeia = "color=c=%s:s=%s:r=%d:d=%s" % (cor, TAMANHO, fps, dur)
        if rosto:
            cadeia += ",drawbox=x=%d:y=%d:w=%d:h=%d:color=%s:t=fill" % (*CAIXA, rosto)
        partes.append("%s[v%d]" % (cadeia, i))
        rotulos += "[v%d]" % i
    fc = ";".join(partes) + ";%sconcat=n=%d:v=1:a=0%s[o]" % (
        rotulos, len(segmentos),
        ",colorspace=all=bt709:iall=bt709:fast=1" if tags is True else ("," + HLG if tags == "hlg" else ""))
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin", "-filter_complex", fc, "-map", "[o]",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "12"]
    cmd += TAGS_BT709 if tags is True else []
    cmd += list(extra) + [str(destino)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-400:]
    return Path(destino)


@pytest.fixture(scope="module")
def limpo(tmp_path_factory):
    """3 s, três planos de 1 s, fundo cinza com rosto de pele normal. Tags bt709."""
    pasta = tmp_path_factory.mktemp("cor")
    return codificar(pasta / "limpo.mp4", [(1, CINZA, PELE)] * 3)


PLANOS_3 = [{"inicio": 0.0, "fim": 1.0, "rosto": CAIXA},
            {"inicio": 1.0, "fim": 2.0, "rosto": CAIXA},
            {"inicio": 2.0, "fim": 3.0, "rosto": CAIXA}]


# --- o controle e o formato do laudo -----------------------------------------------------------

def test_video_limpo_passa_no_formato_do_laudo(limpo):
    g = gate_cor.rodar(limpo, planos=PLANOS_3)
    assert g["nome"] == "gate_cor" and g["etapa"] == "depois"
    assert g["resultado"] == "PASS" and g["saida"] == 0
    assert set(g["limiar"]) >= {"quadro0_razao_min", "mediana_plano_min", "razao_rg_max"}
    assert g["medido"]["cor"] == {"primarias": "bt709", "transferencia": "bt709", "matriz": "bt709"}


def test_os_limiares_sao_os_do_plano():
    assert gate_cor.LIMIAR_QUADRO0 == 0.6
    assert gate_cor.LIMIAR_MEDIANA_PLANO == 20
    assert gate_cor.LIMIAR_RG == 1.6


def _laudo_com(gate):
    """O laudo de exemplo com o gate_cor trocado pelo resultado real do gate."""
    exemplo = json.loads((RAIZ / "contratos" / "exemplos" / "laudo.valido.json").read_text("utf-8"))
    l = copy.deepcopy(exemplo)
    l["gates"] = [gate if g["nome"] == "gate_cor" else g for g in l["gates"]]
    if gate["resultado"] != "PASS":
        l["veredito"] = "REPROVA"
        l["capacidades"]["C5"] = {"status": "REPROVA", "gates": ["gate_cor"], "motivo": gate["motivo"]}
    return l


def test_resultado_que_passa_cabe_no_laudo(limpo):
    g = gate_cor.rodar(limpo, planos=PLANOS_3)
    assert validar("laudo", _laudo_com(g)) == []


def test_resultado_que_reprova_cabe_no_laudo(tmp_path):
    v = codificar(tmp_path / "sem_tags.mp4", [(1, CINZA, None)], tags=False)
    g = gate_cor.rodar(v)
    assert g["resultado"] == "REPROVA" and g["saida"] == 1 and g["motivo"]
    assert validar("laudo", _laudo_com(g)) == []


# --- mutante 1: sem tags ---------------------------------------------------------------------------

def test_mutante_sem_tags_reprova(tmp_path):
    v = codificar(tmp_path / "sem_tags.mp4", [(1, CINZA, PELE)] * 3, tags=False)
    g = gate_cor.rodar(v, planos=PLANOS_3)
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert "bt709" in g["motivo"]
    assert g["medido"]["cor"] == {"primarias": None, "transferencia": None, "matriz": None}


def test_mutante_tag_pela_metade_reprova_e_diz_qual_falta(tmp_path):
    v = codificar(tmp_path / "meia.mp4", [(1, CINZA, PELE)] * 3, tags=False,
                  extra=["-colorspace", "bt709"])
    g = gate_cor.rodar(v, planos=PLANOS_3)
    assert g["resultado"] == "REPROVA"
    assert "transferencia" in g["motivo"] and "primarias" in g["motivo"]
    assert "matriz" not in g["motivo"]


def test_tag_hdr_hlg_reprova(tmp_path):
    """O defeito que as tags existem para evitar: o libx264 marcando a saída como HLG."""
    v = codificar(tmp_path / "hlg.mp4", [(1, CINZA, PELE)] * 3, tags="hlg")
    g = gate_cor.rodar(v, planos=PLANOS_3)
    assert g["resultado"] == "REPROVA" and "arib-std-b67" in g["motivo"]


# --- mutante 2: quadro 0 escuro ---------------------------------------------------------------------

def test_mutante_quadro_0_escuro_reprova(tmp_path):
    v = codificar(tmp_path / "abre_escuro.mp4", [(0.4, "0x101010", None), (2.6, CINZA, PELE)])
    g = gate_cor.rodar(v, caixa_rosto=None)
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert "quadro 0" in g["motivo"]
    q0 = g["medido"]["quadro0"]
    assert q0["razao"] < 0.6 and q0["luminancia"] < 0.6 * q0["mediana_dos_quadros"]


def test_controle_quadro_0_claro_passa(tmp_path):
    v = codificar(tmp_path / "abre_claro.mp4", [(0.4, CINZA, None), (2.6, CINZA, PELE)])
    g = gate_cor.rodar(v)
    assert g["resultado"] == "PASS", g.get("motivo")
    assert g["medido"]["quadro0"]["razao"] >= 0.6


# --- mutante 3: plano com mediana abaixo de 20 ----------------------------------------------------

def _tres_planos_um_escuro(tmp_path):
    return codificar(tmp_path / "plano_escuro.mp4",
                     [(1, CINZA, PELE), (1, ESCURO, None), (1, CINZA, PELE)])


PLANOS_ESCURO = [{"inicio": 0.0, "fim": 1.0, "rosto": CAIXA},
                 {"inicio": 1.0, "fim": 2.0},
                 {"inicio": 2.0, "fim": 3.0, "rosto": CAIXA}]


def test_mutante_plano_escuro_sem_excecao_reprova(tmp_path):
    g = gate_cor.rodar(_tres_planos_um_escuro(tmp_path), planos=PLANOS_ESCURO)
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert "plano 1" in g["motivo"] and "mediana" in g["motivo"]
    escuros = [p for p in g["medido"]["planos"] if p["mediana"] < 20]
    assert [p["indice"] for p in escuros] == [1]


def test_plano_escuro_com_excecao_declarada_com_motivo_passa(tmp_path):
    projeto = {"excecoes": [{"regra": "gate_cor", "motivo": "abertura em preto de propósito"}]}
    g = gate_cor.rodar(_tres_planos_um_escuro(tmp_path), projeto=projeto, planos=PLANOS_ESCURO)
    assert g["resultado"] == "PASS", g.get("motivo")
    assert g["medido"]["excecao"] == "abertura em preto de propósito"
    assert [p["indice"] for p in g["medido"]["planos"] if p.get("excecao")] == [1]


def test_excecao_de_outra_regra_nao_vale_para_a_cor(tmp_path):
    projeto = {"excecoes": [{"regra": "densidade", "motivo": "tela cheia no começo todo"}]}
    g = gate_cor.rodar(_tres_planos_um_escuro(tmp_path), projeto=projeto, planos=PLANOS_ESCURO)
    assert g["resultado"] == "REPROVA"


def test_excecao_de_cor_nao_desliga_as_outras_regras(tmp_path):
    projeto = {"excecoes": [{"regra": "gate_cor", "motivo": "abertura em preto de propósito"}]}
    v = codificar(tmp_path / "escuro_e_sem_tags.mp4",
                  [(1, CINZA, PELE), (1, ESCURO, None), (1, CINZA, PELE)], tags=False)
    g = gate_cor.rodar(v, projeto=projeto, planos=PLANOS_ESCURO)
    assert g["resultado"] == "REPROVA" and "bt709" in g["motivo"]


def test_sem_planos_o_video_inteiro_e_um_plano_so(tmp_path):
    v = codificar(tmp_path / "todo_escuro.mp4", [(2, ESCURO, None)])
    g = gate_cor.rodar(v)
    assert g["resultado"] == "REPROVA" and "plano 0" in g["motivo"]
    assert len(g["medido"]["planos"]) == 1


# --- mutante 4: razão R/G acima de 1,6 na caixa do rosto ------------------------------------------------

def test_mutante_rosto_vermelho_demais_reprova(tmp_path):
    v = codificar(tmp_path / "rosto_vermelho.mp4", [(1, CINZA, PELE_VERMELHA)] * 3)
    g = gate_cor.rodar(v, planos=PLANOS_3)
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert "R/G" in g["motivo"] and "plano 0" in g["motivo"]
    assert all(p["rg"] > 1.6 for p in g["medido"]["planos"])


def test_controle_rosto_normal_tem_razao_abaixo_do_limite(limpo):
    g = gate_cor.rodar(limpo, planos=PLANOS_3)
    razoes = [p["rg"] for p in g["medido"]["planos"]]
    assert all(1.1 < r < 1.6 for r in razoes), razoes


def test_caixa_do_rosto_unica_vale_para_o_video_todo(tmp_path):
    v = codificar(tmp_path / "rosto_vermelho.mp4", [(2, CINZA, PELE_VERMELHA)])
    assert gate_cor.rodar(v, caixa_rosto=CAIXA)["resultado"] == "REPROVA"
    assert gate_cor.rodar(v)["resultado"] == "PASS"          # sem caixa não há o que medir


def test_plano_sem_rosto_nao_tem_razao_rg(tmp_path):
    g = gate_cor.rodar(_tres_planos_um_escuro(tmp_path), planos=PLANOS_ESCURO,
                       projeto={"excecoes": [{"regra": "gate_cor", "motivo": "abertura escura de propósito"}]})
    assert g["medido"]["planos"][1]["rg"] is None


# --- erro de insumo, CLI e integração com o projeto ---------------------------------------------------

def test_video_inexistente_e_erro_com_saida_2(tmp_path):
    g = gate_cor.rodar(tmp_path / "nao_existe.mp4")
    assert g["resultado"] == "ERRO" and g["saida"] == 2 and "nao_existe" in g["motivo"]


def test_arquivo_que_nao_e_video_e_erro(tmp_path):
    lixo = tmp_path / "lixo.mp4"
    lixo.write_text("isto não é vídeo")
    g = gate_cor.rodar(lixo)
    assert g["resultado"] == "ERRO" and g["saida"] == 2


def test_cli_devolve_0_1_e_2(limpo, tmp_path, capsys):
    assert gate_cor.main([str(limpo)]) == 0
    assert "PASSA" in capsys.readouterr().out
    sem_tags = codificar(tmp_path / "s.mp4", [(1, CINZA, None)], tags=False)
    assert gate_cor.main([str(sem_tags)]) == 1
    assert "REPROVA" in capsys.readouterr().out
    assert gate_cor.main([str(tmp_path / "nada.mp4")]) == 2


def test_cli_le_a_excecao_do_projeto_json(tmp_path, capsys):
    v = codificar(tmp_path / "todo_escuro.mp4", [(2, ESCURO, None)])
    assert gate_cor.main([str(v)]) == 1
    pj = tmp_path / "projeto.json"
    pj.write_text(json.dumps(modelo.minimo("anuncio", "gravado", sem_trilha="sem trilha no teste")
                             | {"excecoes": [{"regra": "gate_cor", "motivo": "cena toda em preto de propósito"}]}),
                  encoding="utf-8")
    assert gate_cor.main([str(v), "--projeto", str(pj)]) == 0


def test_cli_rosto_e_planos(tmp_path):
    v = codificar(tmp_path / "rv.mp4", [(2, CINZA, PELE_VERMELHA)])
    assert gate_cor.main([str(v), "--rosto", "40,60,60,60"]) == 1
    planos = tmp_path / "planos.json"
    planos.write_text(json.dumps([{"inicio": 0, "fim": 1, "rosto": [40, 60, 60, 60]}, {"inicio": 1, "fim": 2}]))
    assert gate_cor.main([str(v), "--planos", str(planos)]) == 1


def test_rodar_projeto_le_o_final_e_a_excecao_do_projeto(tmp_path):
    estado = tmp_path / "_local"
    pj = pastas.projeto("anuncio", estado).criar()
    modelo.escrever(pj.projeto_json, modelo.minimo("anuncio", "gravado", sem_trilha="sem trilha no teste")
                    | {"excecoes": [{"regra": "gate_cor", "motivo": "cena toda em preto de propósito"}]})
    pj.entrega_dir.mkdir(parents=True, exist_ok=True)
    codificar(pj.final_9x16, [(2, ESCURO, None)])
    g = gate_cor.rodar_projeto(pj)
    assert g["resultado"] == "PASS" and g["medido"]["excecao"]


def test_planos_da_timeline_convertem_para_o_relogio_da_entrega():
    tl = {"relogio": {"a0": 0.5, "aceleracao": 1.25},
          "segmentos": [{"tipo": "apresentador", "s": 0.5, "e": 3.0},
                        {"tipo": "insert", "s": 3.0, "e": 5.5}]}
    planos = gate_cor.planos_da_timeline(tl, rosto=CAIXA)
    assert planos[0] == {"inicio": 0.0, "fim": 2.0, "rosto": list(CAIXA)}
    assert planos[1] == {"inicio": 2.0, "fim": 4.0}


# --- o laço inteiro: o que o grade_final grava, o gate aprova ------------------------------------------

@pytest.mark.lento
@pytest.mark.parametrize("nome", ["quente-suave", "natural", "frio-teal", "pb"])
def test_saida_do_grade_final_de_cada_preset_passa_no_gate(tmp_path, nome):
    from footage import grade_final as GF
    fonte = tmp_path / "fonte.mp4"
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
                        "color=c=%s:s=%s:r=25:d=1,drawbox=x=%d:y=%d:w=%d:h=%d:color=%s:t=fill"
                        % (CINZA, TAMANHO, *CAIXA, PELE),
                        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=1",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(fonte)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-300:]
    saida = tmp_path / "saida.mp4"
    GF.aplicar(str(fonte), 0.0, 1.0, str(fonte), str(saida), preset=nome)
    g = gate_cor.rodar(saida, caixa_rosto=CAIXA)
    assert g["resultado"] == "PASS", g.get("motivo")
    assert g["medido"]["cor"] == {"primarias": "bt709", "transferencia": "bt709", "matriz": "bt709"}
