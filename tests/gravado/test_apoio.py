"""Módulos de apoio do gravado (W2.D): o projeto, a montagem, a legenda, a caixinha e a entrega.

São os passos VIVOS do pipeline de take gravado, copiados do motor privado e sanitizados:
caminho do projeto por argumento (nada de variável de ambiente nem de plano em Python que
executa), vocabulário do aluno vindo do glossário, e a entrega que consulta os gates antes de
copiar. O que exige a CLI do produto fica para a W5.D; aqui cada módulo é função + `main`.
"""
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from gravado import (area_ad_inteiro, auditar, compor_caixinha, conferir_buracos, cortes_render,
                     entregar, extrair_caixinha, extrair_wav, frases_do_take, gerar_plano_md,
                     isolar, janela, legendar, medir_audio, montar, queimar_legenda,
                     varredura_total)
from gravado import projeto as gp
from gravado.veredito import InsumoInvalido
from projeto import modelo as modelo_projeto
from tests.fixtures import sinteticos as fx
from tests.gravado import sintese as sx


def w(texto, ini, fim):
    return {"text": texto, "start": ini, "end": fim}


ADS = sx.ADS_DE_TESTE


def _projeto(tmp_path, ads=None, com_limpo=True):
    """Projeto com um take limpo de 5,0 s: tom 0-1, pausa 1,5 s, tom 2,5-3,5, pausa 0,5, tom 4-5."""
    return sx.projeto_de_teste(tmp_path, ads, com_limpo)


# --- projeto -------------------------------------------------------------------------------

def test_criar_faz_pastas_e_plano_de_partida_e_nao_sobrescreve(tmp_path):
    p = gp.criar(tmp_path / "leva1", brutos=tmp_path / "brutos")
    assert (p.base / gp.ARQUIVO_PLANO).is_file()
    for pasta in gp.PASTAS:
        assert (p.base / pasta).is_dir(), pasta
    editado = '{"versao": 1, "brutos": "x", "ads": {}}'
    (p.base / gp.ARQUIVO_PLANO).write_text(editado, encoding="utf-8")
    gp.criar(tmp_path / "leva1", brutos=tmp_path / "outros")
    assert (p.base / gp.ARQUIVO_PLANO).read_text(encoding="utf-8") == editado


def test_projeto_so_escreve_dentro_da_propria_pasta(tmp_path):
    p = gp.criar(tmp_path / "leva1", brutos=tmp_path / "brutos")
    for nome in ("wav", "audio", "limpo", "montados", "legendado", "ENTREGA", "cache_asr"):
        assert str(p.pasta(nome).resolve()).startswith(str(p.base.resolve()))
    assert not (tmp_path / "brutos").exists()           # os brutos são só leitura


def test_sem_plano_a_mensagem_diz_como_criar(tmp_path):
    with pytest.raises(gp.PlanoInvalido) as e:
        gp.carregar(tmp_path / "vazio")
    assert gp.ARQUIVO_PLANO in str(e.value) and "criar" in str(e.value)


def test_plano_invalido_lista_todos_os_erros_com_o_caminho_do_campo(tmp_path):
    ruim = {"A1": {"corpo": [["T1", 5.0, 3.0]], "cta_normal": [], "cor": 1}}
    sx.projeto_minimo(tmp_path / "x", ruim)
    with pytest.raises(gp.PlanoInvalido) as e:
        gp.carregar(tmp_path / "x")
    msg = str(e.value)
    assert "$.ads.A1.corpo[0]" in msg and "maior que" in msg
    assert "$.ads.A1.cta_normal" in msg
    assert "$.ads.A1.cor" in msg and "campo desconhecido" in msg


@pytest.mark.parametrize("trecho", [["../fora", 0.0, 1.0], ["T1", -1.0, 1.0], ["T1", "a", 2.0],
                                    ["T1", 1.0], ["T1/x", 0.0, 1.0]])
def test_trecho_com_take_fora_da_pasta_ou_numero_ruim_reprova(tmp_path, trecho):
    sx.projeto_minimo(tmp_path / "x", {"A1": {"corpo": [trecho], "cta_normal": [["T1", 0.0, 1.0]]}})
    with pytest.raises(gp.PlanoInvalido):
        gp.carregar(tmp_path / "x")


def test_desconto_so_existe_com_cta_desconto(tmp_path):
    sx.projeto_minimo(tmp_path / "x", {"A1": {"corpo": [["T1", 0.0, 1.0]], "cta_normal": [["T1", 1.0, 2.0]],
                                              "corpo_desconto": [["T1", 0.0, 0.5]]}})
    with pytest.raises(gp.PlanoInvalido) as e:
        gp.carregar(tmp_path / "x")
    assert "corpo_desconto" in str(e.value)


def test_plano_em_python_do_formato_antigo_nao_e_executado(tmp_path):
    base = tmp_path / "leva"
    base.mkdir()
    (base / "plano.py").write_text("raise SystemExit('executou o plano antigo')\n", encoding="utf-8")
    with pytest.raises(gp.PlanoInvalido):
        gp.carregar(base)


def test_aceleracao_padrao_1_2_e_vem_do_projeto_json_quando_existe(tmp_path):
    p = _projeto(tmp_path, com_limpo=False)
    assert p.accel == 1.2
    dados = modelo_projeto.minimo("leva", "gravado", sem_trilha="sem música neste teste")
    dados["aceleracao"] = 1.3
    modelo_projeto.escrever(p.base / "projeto.json", dados)
    assert gp.carregar(p.base).accel == 1.3


def test_bruto_e_achado_pelo_nome_sem_diferenciar_extensao_e_ignorados_ficam_de_fora(tmp_path):
    brutos = tmp_path / "brutos"
    brutos.mkdir()
    for nome in ("IMG_1.MOV", "IMG_2.mp4", "IMG_3.mov", "notas.txt"):
        (brutos / nome).write_bytes(b"x")
    sx.projeto_minimo(tmp_path / "x", ADS, brutos=brutos, ignorar=["IMG_3"])
    p = gp.carregar(tmp_path / "x")
    assert p.bruto("IMG_1").name == "IMG_1.MOV"
    assert [b.stem for b in p.takes_brutos()] == ["IMG_1", "IMG_2"]
    with pytest.raises(FileNotFoundError) as e:
        p.bruto("IMG_9")
    assert "IMG_9" in str(e.value)


def test_trechos_pecas_e_versoes_do_plano(tmp_path):
    p = _projeto(tmp_path, com_limpo=False)
    assert p.trechos_do_ad("A1", False) == [("T1", 0.0, 3.5), ("T1", 4.0, 5.0)]
    assert p.trechos_do_ad("A1", True) == [("T1", 0.0, 3.5), ("T1", 4.2, 5.0)]
    assert p.nomes_das_pecas() == ["A1_normal", "A1_desconto", "B2_normal"]
    with pytest.raises(KeyError):
        p.trechos_do_ad("B2", True)                       # B2 não tem cta_desconto


def test_todos_os_trechos_cobre_as_quatro_chaves_sem_repetir(tmp_path):
    ads = {"A1": {"corpo": [["T1", 0.0, 1.0]], "corpo_desconto": [["T1", 0.0, 0.5]],
                  "cta_normal": [["T1", 5.0, 6.0]], "cta_desconto": [["T2", 0.0, 1.0]]},
           "A2": {"corpo": [["T1", 7.0, 8.0]], "cta_normal": [["T1", 5.0, 6.0]]}}
    sx.projeto_minimo(tmp_path / "x", ads)
    p = gp.carregar(tmp_path / "x")
    todos = p.todos_os_trechos()
    chaves = [(c, k) for c, k, *_ in todos]
    assert ("A1", "corpo_desconto") in chaves and ("A1", "cta_desconto") in chaves
    assert len({(t, i, f) for _, _, t, i, f in todos}) == 5          # (T1,5,6) só uma vez


def test_fonte_da_peca_e_a_com_caixinha_se_existir_senao_a_montada(tmp_path):
    p = _projeto(tmp_path, com_limpo=False)
    assert p.fonte_da_peca("A1_normal") == p.montado("A1_normal")
    (p.base / "com_caixinha").mkdir()
    (p.base / "com_caixinha" / "A1_normal_caixinha.mp4").write_bytes(b"x")
    assert p.fonte_da_peca("A1_normal") == p.com_caixinha("A1_normal")


def test_glossario_do_projeto_vem_do_estado_do_aluno(tmp_path):
    estado = tmp_path / "_local"
    estado.mkdir()
    (estado / "glossario.json").write_text(json.dumps(
        {"versao": 1, "termos": [{"grafia": "Fluxa", "variantes": ["Flucha"], "tipo": "marca"}]}), encoding="utf-8")
    sx.projeto_minimo(tmp_path / "x", ADS)
    assert gp.carregar(tmp_path / "x", estado=estado).glossario()["termos"][0]["grafia"] == "Fluxa"
    assert gp.carregar(tmp_path / "x", estado=tmp_path / "sem_glossario").glossario() == {"versao": 1, "termos": []}


def test_resolver_base_usa_o_argumento_ou_o_diretorio_atual(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert gp.resolver_base(None) == tmp_path.resolve()
    assert gp.resolver_base(str(tmp_path / "a")) == (tmp_path / "a").resolve()


# --- montar --------------------------------------------------------------------------------

def test_segmentos_aplicam_o_cortador_dentro_de_cada_trecho(tmp_path):
    p = _projeto(tmp_path)
    segs = montar.segmentos_do_ad(p, "A1", False)
    assert len(segs) == 3
    assert segs[0][0] == "T1" and segs[0][1] == pytest.approx(0.0, abs=0.03)
    assert segs[0][2] == pytest.approx(1.21, abs=0.04)          # a pausa de 1,5 s encolheu
    assert segs[1][1] == pytest.approx(2.29, abs=0.04)
    assert segs[2][1] == pytest.approx(4.0, abs=0.03) and segs[2][2] == pytest.approx(5.0, abs=0.03)
    desconto = montar.segmentos_do_ad(p, "A1", True)
    assert desconto[-1][1] == pytest.approx(4.2, abs=0.03)       # só a cauda troca


def test_emendas_sao_os_tempos_acumulados_ja_acelerados(tmp_path):
    segs = [("T1", 0.0, 1.2), ("T1", 2.0, 3.2), ("T1", 4.0, 5.0)]
    assert montar.emendas(segs, 1.2) == [1.0, 2.0]
    assert montar.duracao_final(segs, 1.2) == pytest.approx(3.4 / 1.2)


def test_montar_so_plano_lista_os_segmentos_sem_renderizar(tmp_path, capsys):
    p = _projeto(tmp_path)
    assert montar.main(["A1", "--so-plano", "--projeto", str(p.base)]) == 0
    saida = capsys.readouterr().out
    assert "3 segmentos" in saida and "T1" in saida
    assert not (p.base / "montados").exists() or not list((p.base / "montados").glob("*.mp4"))


def test_montar_sem_o_audio_limpo_diz_qual_take_falta(tmp_path, capsys):
    p = _projeto(tmp_path, com_limpo=False)
    assert montar.main(["A1", "--so-plano", "--projeto", str(p.base)]) == 2
    assert "T1" in capsys.readouterr().err


def test_montar_ad_que_nao_existe_no_plano_e_insumo_invalido(tmp_path, capsys):
    p = _projeto(tmp_path)
    assert montar.main(["Z9", "--so-plano", "--projeto", str(p.base)]) == 2
    assert "Z9" in capsys.readouterr().err


@pytest.mark.lento
def test_render_sai_1080x1920_na_duracao_acelerada(tmp_path):
    p = _projeto(tmp_path)
    p.brutos.mkdir(parents=True, exist_ok=True)
    fx.testsrc_com_audio(p.brutos / "T1.mp4", dur=5.0)
    segs = montar.segmentos_do_ad(p, "A1", False)
    saida = montar.render(p, "A1", segs, False)
    assert saida == p.montado("A1_normal") and saida.is_file()
    info = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,sample_rate",
         "-show_entries", "format=duration", "-of", "json", str(saida)], capture_output=True, text=True).stdout)
    v = [s for s in info["streams"] if s["codec_type"] == "video"][0]
    a = [s for s in info["streams"] if s["codec_type"] == "audio"][0]
    assert (v["width"], v["height"]) == (1080, 1920)
    assert a["sample_rate"] == "48000"
    assert float(info["format"]["duration"]) == pytest.approx(montar.duracao_final(segs, p.accel), abs=0.15)
    assert not list(p.pasta("montados").glob("*_semloud*"))          # intermediário apagado


# --- legendar ------------------------------------------------------------------------------

def test_tempo_ass_em_centesimos_e_sem_estourar_60_segundos():
    assert legendar.tempo(0) == "0:00:00.00"
    assert legendar.tempo(59.996) == "0:01:00.00"
    assert legendar.tempo(3661.5) == "1:01:01.50"
    assert legendar.tempo(1.234) == "0:00:01.23"


def test_cabecalho_tem_a_resolucao_a_fonte_e_a_margem_da_legenda():
    cab = legendar.cabecalho()
    assert "PlayResX: 1080" in cab and "PlayResY: 1920" in cab
    assert "Style: Base,Inter,66," in cab
    assert ",%d,1\n" % (1920 - legendar.Y_LEGENDA) in cab


def test_linhas_quebram_por_caracteres_palavras_pausa_e_fim_de_frase():
    ps = [w("um", 0.0, 0.2), w("dois", 0.2, 0.4), w("tres", 0.4, 0.6), w("quatro", 0.6, 0.8),
          w("cinco", 0.8, 1.0), w("seis", 1.0, 1.2)]
    ls = legendar.linhas(ps)
    assert [len(x) for x in ls] == [5, 1]                                   # no máximo 5 palavras
    longas = [w("abcdefghij", 0, 0.2), w("abcdefghij", 0.2, 0.4), w("abcdefghij", 0.4, 0.6)]
    assert [len(x) for x in legendar.linhas(longas)] == [2, 1]               # 21 + 10 > 30 caracteres
    pausa = [w("antes", 0.0, 0.3), w("depois", 1.0, 1.3)]
    assert len(legendar.linhas(pausa)) == 2                                  # pausa de 0,7 s > 0,45 s
    fim = [w("acabou.", 0.0, 0.3), w("recomeça", 0.31, 0.6)]
    assert len(legendar.linhas(fim)) == 2                                    # ponto final fecha a linha


def test_a_linha_fica_ate_a_proxima_entrar_com_teto_e_a_ultima_segura_meio_segundo():
    ls = [[w("primeira", 0.0, 0.5)], [w("segunda", 1.0, 1.4)], [w("terceira", 9.0, 9.4)]]
    ev = legendar.eventos(ls)
    ini1, fim1 = ev[0][0], ev[0][1]
    assert (ini1, fim1) == (0.0, 1.0)                    # até a próxima entrar
    assert ev[1][1] == pytest.approx(1.4 + 1.6)          # teto de 1,6 s de sobra
    assert ev[2][1] == pytest.approx(9.4 + 0.5)          # a última segura 0,5 s


def test_nenhum_evento_dura_menos_de_0_3_s():
    ev = legendar.eventos([[w("curta", 0.0, 0.05)], [w("outra", 5.0, 5.05)]])
    assert all(fim - ini >= 0.3 - 1e-9 for ini, fim, _ in ev)


def test_destaque_vale_para_numero_preco_e_termo_do_glossario_nao_para_o_resto():
    destacar = legendar.destaques_do_glossario(
        {"versao": 1, "termos": [{"grafia": "Fluxa", "tipo": "marca"}, {"grafia": "Marina", "tipo": "nome"},
                                 {"grafia": "Agenda Pro", "tipo": "produto"}]})
    assert legendar.destaca("Fluxa,", destacar) and legendar.destaca("fluxa", destacar)
    assert legendar.destaca("Agenda", destacar) and legendar.destaca("Pro.", destacar)   # termo composto: cada palavra
    assert not legendar.destaca("Marina", destacar)          # nome de pessoa não ganha cor
    for numero in ("100", "R$39", "24/7", "15"):
        assert legendar.destaca(numero), numero
    assert not legendar.destaca("casa", destacar)


def test_ass_com_destaque_tem_a_tag_de_cor_e_o_texto_continua_o_mesmo(tmp_path):
    ps = [w("abra", 0.0, 0.2), w("a", 0.2, 0.3), w("Fluxa", 0.3, 0.6), w("por", 0.6, 0.8), w("100", 0.8, 1.0)]
    destacar = legendar.destaques_do_glossario({"versao": 1, "termos": [{"grafia": "Fluxa", "tipo": "marca"}]})
    texto, _ = legendar.ass_texto(ps, destacar=destacar)
    linhas = [l for l in texto.splitlines() if l.startswith("Dialogue")]
    assert len(linhas) == 1
    assert r"{\c&H4E7DE8&}Fluxa{\c&HFFFFFF&}" in linhas[0] and r"{\c&H4E7DE8&}100{\c&HFFFFFF&}" in linhas[0]
    sem_tag = legendar.sem_tags(linhas[0].split(",", 9)[9])
    assert sem_tag == "abra a Fluxa por 100"


def test_omitir_tira_so_as_palavras_pedidas_da_legenda():
    ps = [w("isso", 0.0, 0.2), w("merda,", 0.2, 0.4), w("funciona", 0.4, 0.8)]
    texto, _ = legendar.ass_texto(ps, omitir={"merda"})
    assert "merda" not in texto and "funciona" in texto
    sem_pedido, _ = legendar.ass_texto(ps)
    assert "merda" in sem_pedido                               # por padrão nada é omitido


def test_gerar_escreve_o_ass_e_devolve_numero_de_linhas_e_amostra(tmp_path):
    ps = [w("palavra%d" % i, i * 0.3, i * 0.3 + 0.25) for i in range(12)]
    n, amostra = legendar.gerar(ps, tmp_path / "x.ass")
    assert n >= 3 and "palavra0" in amostra
    assert (tmp_path / "x.ass").read_text(encoding="utf-8").startswith("[Script Info]")


def test_legendar_cli_gera_o_ass_da_peca_pelo_leitor(tmp_path, monkeypatch, capsys):
    p = _projeto(tmp_path, com_limpo=False)
    (p.base / "montados").mkdir()
    (p.base / "montados" / "A1_normal.mp4").write_bytes(b"x")
    leitor = sx.LeitorFalso(palavras_da_peca=[w("ola", 0.0, 0.3), w("mundo", 0.4, 0.8)])
    n = legendar.legendar_pecas(p, ["A1_normal"], leitor)
    assert n == {"A1_normal": 1}
    assert p.legenda_ass("A1_normal").is_file()
    assert (str(p.fonte_da_peca("A1_normal")), "palavras", True) in leitor.chamadas   # tempo de palavra EXIGE borda real


# --- queimar_legenda -----------------------------------------------------------------------

def test_escapar_filtro_protege_os_caracteres_do_filtro_do_ffmpeg():
    assert queimar_legenda.escapar_filtro("/a/b c/legenda.ass") == "/a/b c/legenda.ass"
    assert queimar_legenda.escapar_filtro("C:/x") == "C\\:/x"
    assert queimar_legenda.escapar_filtro("a,b") == "a\\,b"
    assert queimar_legenda.escapar_filtro("d'a") == "d\\'a"
    assert queimar_legenda.escapar_filtro("a\\b") == "a\\\\b"


def test_sem_a_fonte_inter_para_com_uma_mensagem_so(tmp_path):
    vazia = tmp_path / "fontes"
    vazia.mkdir()
    with pytest.raises(queimar_legenda.SemFonte) as e:
        queimar_legenda.achar_fonte(vazia)
    assert "Inter" in str(e.value) and str(e.value).count("\n") <= 1
    (vazia / "Inter-ExtraBold.otf").write_bytes(b"x")
    assert queimar_legenda.achar_fonte(vazia) == vazia


def test_comando_queima_o_ass_com_a_pasta_de_fontes_e_copia_o_audio(tmp_path):
    cmd = queimar_legenda.comando(tmp_path / "in.mp4", tmp_path / "a.ass", tmp_path / "out.mp4", tmp_path / "fontes")
    vf = cmd[cmd.index("-vf") + 1]
    assert vf.startswith("ass=") and "fontsdir=" in vf
    assert cmd[cmd.index("-c:a") + 1] == "copy"
    assert cmd[-1] == str(tmp_path / "out.mp4")


# --- caixinha ------------------------------------------------------------------------------

def _caixinha_fundo_preto(destino, tela=(1080, 1920), caixa=(40, 210, 1040, 557)):
    """Cantos arredondados, sombra suave e texto escuro: o que costuma quebrar o key por cor."""
    from PIL import ImageFilter
    img = Image.new("RGB", tela, (0, 0, 0))
    sombra = Image.new("L", tela, 0)
    x0, y0, x1, y1 = caixa
    ImageDraw.Draw(sombra).rounded_rectangle([x0 + 8, y0 + 14, x1 + 8, y1 + 14], 44, fill=150)
    sombra = sombra.filter(ImageFilter.GaussianBlur(18))
    img.paste(Image.new("RGB", tela, (30, 30, 30)), (0, 0), sombra)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(list(caixa), 44, fill=(248, 246, 242))
    for i in range(3):                                     # "texto" escuro dentro da caixa
        d.rectangle([x0 + 46, y0 + 104 + i * 62, x0 + 600, y0 + 104 + i * 62 + 30], fill=(26, 24, 22))
    img.save(destino)
    return destino


def test_extrair_caixinha_tira_o_fundo_pelas_bordas_e_preserva_o_texto_escuro(tmp_path):
    png = _caixinha_fundo_preto(tmp_path / "preto.png")
    img, caixa, frac = extrair_caixinha.extrair(png)
    a = np.asarray(img)[..., 3]
    assert a[5, 5] == 0 and a[1900, 1070] == 0                         # cantos da tela: fundo
    assert a[400, 900] == 255                                           # miolo da caixa
    assert a[210 + 104 + 15, 40 + 46 + 100] == 255                      # texto escuro NÃO virou buraco
    x0, y0, x1, y1 = caixa
    assert abs(x0 - 40) <= 3 and abs(y0 - 210) <= 3 and abs(x1 - 1040) <= 3 and abs(y1 - 557) <= 3
    assert 0.1 < frac < 0.2


def test_extrair_caixinha_recortar_salva_so_o_retangulo(tmp_path):
    png = _caixinha_fundo_preto(tmp_path / "preto.png")
    saida = tmp_path / "caixa.png"
    assert extrair_caixinha.main([str(png), "--saida", str(saida), "--recortar"]) == 0
    assert abs(Image.open(saida).width - 1000) <= 6


def test_extrair_caixinha_imagem_toda_de_fundo_e_insumo_invalido(tmp_path):
    Image.new("RGB", (200, 200), (0, 0, 0)).save(tmp_path / "preta.png")
    assert extrair_caixinha.main([str(tmp_path / "preta.png"), "--saida", str(tmp_path / "o.png")]) == 2


def test_preparar_posiciona_caixinha_recortada_no_x_y_pedido(tmp_path):
    rgba = Image.new("RGBA", (1000, 347), (255, 255, 255, 255))
    rgba.putpixel((0, 0), (255, 255, 255, 254))               # tem transparência real: não é fundo chapado
    rgba.putpixel((1, 1), (0, 0, 0, 0))
    rgba.save(tmp_path / "c.png")
    tela, topo, base = compor_caixinha.preparar(tmp_path / "c.png", 40, 210, False)
    assert tela.size == (1080, 1920)
    assert (topo, base) == (210, 210 + 347 - 1)


def test_preparar_com_topo_reposiciona_a_arte_de_tela_cheia(tmp_path):
    cheia = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    ImageDraw.Draw(cheia).rectangle([40, 210, 1040, 556], fill=(255, 255, 255, 255))
    cheia.save(tmp_path / "cheia.png")
    _, topo, base = compor_caixinha.preparar(tmp_path / "cheia.png", 40, 210, False)
    assert (topo, base) == (210, 556)
    _, topo2, base2 = compor_caixinha.preparar(tmp_path / "cheia.png", 40, 210, False, topo=200)
    assert (topo2, base2) == (200, 546)


def test_aviso_de_teto_so_aparece_quando_a_caixinha_desce_alem_do_medido():
    assert compor_caixinha.aviso_de_teto(556, 557) == ""
    msg = compor_caixinha.aviso_de_teto(600, 557)
    assert "600" in msg and "557" in msg


def test_area_ad_inteiro_quadro_sem_rosto_nao_tem_topo_e_a_folga_e_de_30_px():
    quadro = np.zeros((1920, 1080, 3), dtype=np.uint8)
    assert area_ad_inteiro.topo_da_cabeca(quadro) is None
    assert area_ad_inteiro.y_ate_onde_a_caixinha_pode_ir(557) == 527
    assert area_ad_inteiro.y_ate_onde_a_caixinha_pode_ir(10) == 0


# --- auditar -------------------------------------------------------------------------------

def test_auditar_tecnico_mede_resolucao_audio_e_loudness(tmp_path):
    arq = fx.testsrc_com_audio(tmp_path / "x.mp4", dur=3.0)
    t = auditar.tecnico(arq)
    assert t["resolucao"] == "320x568" and t["sample_rate"] == "48000"
    assert t["duracao"] == pytest.approx(3.0, abs=0.2)
    assert t["ok"] is False and "resolução" in t["motivo"]          # não é 1080x1920


def test_gerar_falas_grava_o_json_e_marca_a_falha_do_asr(tmp_path):
    p = _projeto(tmp_path, com_limpo=False)
    montados = p.pasta("montados")
    montados.mkdir(exist_ok=True)
    fx.testsrc_com_audio(montados / "A1_normal.mp4", dur=2.0)
    fx.testsrc_com_audio(montados / "B2_normal.mp4", dur=2.0)

    class Misto(object):
        def fala_ou_falha(self, arquivo):
            return "olá mundo" if "A1" in str(arquivo) else "FALHA: sem rede"

    falas = auditar.gerar_falas(p, Misto(), pasta="montados")
    assert falas == {"A1_normal": "olá mundo", "B2_normal": "FALHA: sem rede"}
    assert json.loads(p.falas_json.read_text(encoding="utf-8")) == falas


# --- entregar ------------------------------------------------------------------------------

def _legendados(p, nomes=("A1_normal", "B2_normal")):
    pasta = p.pasta("legendado")
    pasta.mkdir(exist_ok=True)
    for n in nomes:
        (pasta / (n + ".mp4")).write_bytes(("video de " + n).encode() * 100)


def _gate(estado, motivo="m"):
    def rodar():
        if estado == "insumo":
            raise InsumoInvalido(motivo)
        return estado, motivo
    return rodar


def test_entregar_nao_copia_nada_se_qualquer_gate_sai_com_defeito(tmp_path):
    p = _projeto(tmp_path, com_limpo=False)
    _legendados(p)
    r = entregar.entregar(p, gates=[("gate_a", _gate(True)), ("gate_b", _gate(False, "pausa de 0.9s")),
                                    ("gate_c", _gate(True))])
    assert r.entregue is False and r.codigo == 1
    assert not list(p.pasta("ENTREGA").glob("*"))
    assert [(n, e) for n, e, _ in r.gates] == [("gate_a", "ok"), ("gate_b", "defeito"), ("gate_c", "ok")]
    assert "pausa de 0.9s" in r.resumo()


def test_entregar_nao_copia_se_um_gate_nao_conseguiu_medir(tmp_path):
    p = _projeto(tmp_path, com_limpo=False)
    _legendados(p)
    r = entregar.entregar(p, gates=[("gate_a", _gate(True)), ("gate_b", _gate("insumo", "ASR falhou"))])
    assert r.entregue is False and r.codigo == 2
    assert not list(p.pasta("ENTREGA").glob("*"))


def test_defeito_vale_mais_que_insumo_no_codigo_de_saida(tmp_path):
    p = _projeto(tmp_path, com_limpo=False)
    _legendados(p)
    r = entregar.entregar(p, gates=[("a", _gate("insumo")), ("b", _gate(False))])
    assert r.codigo == 1


def test_entregar_copia_tudo_e_confere_o_sha_quando_todos_passam(tmp_path):
    p = _projeto(tmp_path, com_limpo=False)
    _legendados(p)
    r = entregar.entregar(p, gates=[("gate_a", _gate(True)), ("gate_b", _gate(True))], abrir=False)
    assert r.entregue is True and r.codigo == 0
    assert sorted(x.name for x in p.pasta("ENTREGA").glob("*.mp4")) == ["A1_normal.mp4", "B2_normal.mp4"]
    for nome in r.copiados:
        assert (p.pasta("ENTREGA") / nome).read_bytes() == (p.pasta("legendado") / nome).read_bytes()


def test_entregar_sem_pecas_legendadas_e_insumo_invalido(tmp_path):
    p = _projeto(tmp_path, com_limpo=False)
    r = entregar.entregar(p, gates=[("gate_a", _gate(True))])
    assert r.entregue is False and r.codigo == 2


def test_gates_padrao_sao_os_onze_na_ordem_do_pipeline(tmp_path):
    p = _projeto(tmp_path, com_limpo=False)
    nomes = [n for n, _ in entregar.gates_padrao(p, sx.LeitorFalso(textos="x"))]
    assert nomes == ["gate_envelope", "gate_fala", "gate_voz_distante", "gate_retomada",
                     "gate_emendas", "gate_redundancia", "gate_ar_morto", "gate_legenda",
                     "gate_sincronia", "gate_repeticao", "gate_offscript"]


# --- plano em markdown, janela, folha de contato -------------------------------------------

def test_plano_md_nasce_do_plano_e_tem_uma_tabela_por_versao(tmp_path):
    p = _projeto(tmp_path)
    texto = gerar_plano_md.gerar(p)
    assert texto.startswith("# Plano de cortes")
    assert "## A1: Primeiro" in texto and "## B2: Segundo" in texto
    assert texto.count("| take | entra | sai | dur |") == 3          # A1 normal, A1 desconto, B2 normal
    assert "1.2x" in texto
    assert "\u2014" not in texto and "\u2013" not in texto


def test_janela_lista_as_palavras_que_tocam_a_janela():
    ps = [w("um", 0.0, 0.4), w("dois", 0.5, 0.9), w("três", 1.0, 1.4), w("quatro", 2.0, 2.4)]
    assert [x["text"] for x in janela.palavras_na_janela(ps, 0.45, 1.1)] == ["dois", "três"]


def test_achar_frase_devolve_inicio_e_fim_medidos_sem_diferenciar_acento_nem_pontuacao():
    ps = [w("Você", 0.0, 0.3), w("vai,", 0.3, 0.6), w("ver", 0.6, 0.9), w("isso.", 0.9, 1.3),
          w("você", 2.0, 2.3), w("vai", 2.3, 2.6), w("ver", 2.6, 2.9), w("de novo", 2.9, 3.4)]
    achados = janela.achar(ps, "voce vai ver")
    assert achados == [(0.0, 0.9), (2.0, 2.9)]
    assert janela.achar(ps, "nunca disse") == []


def test_folha_de_contato_tem_o_tamanho_da_grade_e_um_rotulo_por_quadro():
    quadros = [Image.new("RGB", (90, 160), (i * 30, 50, 50)) for i in range(5)]
    folha = cortes_render.montar_folha(quadros, ["1.0s", "2.0s", "3.0s", "4.0s", "5.0s"], colunas=3, altura=80)
    assert folha.size[0] > 3 * 40 and folha.size[1] > 2 * 80          # 3 colunas x 2 linhas
    with pytest.raises(ValueError):
        cortes_render.montar_folha(quadros, ["só um"], colunas=3, altura=80)


def test_medir_audio_reporta_pico_piso_e_fracao_de_silencio(tmp_path):
    arq = sx.audio_por_blocos(tmp_path / "m.wav", [(1.0, -12.0), (1.0, None)])
    r = medir_audio.relatorio(arq)
    assert r["dur"] == pytest.approx(2.0, abs=0.03)
    assert r["pico"] == pytest.approx(-12.0, abs=0.3)
    assert r["janelas<-40dB"] == "50%"


# --- extrair_wav, isolar -------------------------------------------------------------------

def test_extrair_wav_gera_wav_48k_e_mp3_16k_pula_o_feito_e_o_ignorado(tmp_path):
    brutos = tmp_path / "brutos"
    brutos.mkdir()
    fx.testsrc_com_audio(brutos / "IMG_1.mp4", dur=2.0)
    fx.testsrc_com_audio(brutos / "IMG_2.mp4", dur=2.0)
    sx.projeto_minimo(tmp_path / "x", ADS, brutos=brutos, ignorar=["IMG_2"])
    p = gp.carregar(tmp_path / "x")
    feitos, total = extrair_wav.extrair(p)
    assert (feitos, total) == (1, 1)                                  # IMG_2 é ignorado: nem entra na conta
    wav = p.wav("IMG_1")
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate,channels",
                                      "-of", "json", str(wav)], capture_output=True, text=True).stdout)
    assert info["streams"][0]["sample_rate"] == "48000" and info["streams"][0]["channels"] == 1
    mp3info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate",
                                         "-of", "json", str(p.audio_mp3("IMG_1"))], capture_output=True, text=True).stdout)
    assert mp3info["streams"][0]["sample_rate"] == "16000"
    antes = wav.stat().st_mtime_ns
    extrair_wav.extrair(p)
    assert wav.stat().st_mtime_ns == antes                            # já extraído: não refaz
    assert not p.wav("IMG_2").exists()


def test_extrair_wav_pasta_de_brutos_ausente_e_insumo_invalido(tmp_path):
    sx.projeto_minimo(tmp_path / "x", ADS, brutos=tmp_path / "nao_existe")
    with pytest.raises(InsumoInvalido) as e:
        extrair_wav.extrair(gp.carregar(tmp_path / "x"))
    assert "nao_existe" in str(e.value)


def test_isolar_chave_ausente_ou_errada_e_insumo_invalido():
    for env in ({}, {"ELEVENLABS_API_KEY": "  "}, {"ELEVENLABS_API_KEY": "abc"}):
        with pytest.raises(InsumoInvalido):
            isolar.chave_do_ambiente(env)
    assert isolar.chave_do_ambiente({"ELEVENLABS_API_KEY": " sk_teste "}) == "sk_teste"


def test_isolar_audio_curto_ganha_silencio_no_fim_ate_o_minimo_da_api(tmp_path):
    curto = sx.audio_por_blocos(tmp_path / "curto.wav", [(2.0, -12.0)])
    preparado = isolar.preparar_minimo(curto, tmp_path / "prep")
    assert sx.duracao_do_wav(preparado) >= 4.6 - 1e-3
    longo = sx.audio_por_blocos(tmp_path / "longo.wav", [(6.0, -12.0)])
    assert isolar.preparar_minimo(longo, tmp_path / "prep2") == longo        # não mexe


def test_isolar_grava_o_destino_e_usa_cache_na_segunda_vez(tmp_path):
    src = sx.audio_por_blocos(tmp_path / "t.wav", [(6.0, -12.0)])
    chamadas = []

    def transporte(url, cabecalhos, corpo):
        chamadas.append(url)
        return 200, b"x" * 4096

    dest = tmp_path / "limpo" / "t.mp3"
    assert isolar.isolar(src, dest, "sk_x", transporte=transporte).startswith("ok")
    assert dest.stat().st_size == 4096
    assert isolar.isolar(src, dest, "sk_x", transporte=transporte) == "cache"
    assert len(chamadas) == 1


def test_isolar_resposta_curta_ou_http_ruim_nao_grava_o_destino(tmp_path):
    src = sx.audio_por_blocos(tmp_path / "t.wav", [(6.0, -12.0)])
    dest = tmp_path / "l.mp3"
    assert "curta" in isolar.isolar(src, dest, "sk_x", transporte=lambda u, h, c: (200, b"x" * 10))
    assert "HTTP 401" in isolar.isolar(src, dest, "sk_x", transporte=lambda u, h, c: (401, b"nao autorizado"))
    assert not dest.exists()


def test_isolar_lote_espera_e_tenta_de_novo_so_uma_vez_no_429(tmp_path):
    p = _projeto(tmp_path, com_limpo=False)
    for t in ("T1", "T2"):
        sx.audio_por_blocos(p.wav(t), [(6.0, -12.0)])
    respostas = {"n": 0}
    esperas = []

    def transporte(url, cabecalhos, corpo):
        respostas["n"] += 1
        return (429, b"limite") if respostas["n"] % 2 == 1 else (200, b"y" * 3000)

    linhas = isolar.isolar_lote(p, "sk_x", transporte=transporte, dormir=esperas.append, paralelo=1)
    assert len(linhas) == 2 and all("ok" in l and "backoff" in l for l in linhas.values())
    assert esperas == [20, 20]
    assert respostas["n"] == 4                                  # uma tentativa e UM retry por take


# --- frases do take, varredura, conferir buracos -------------------------------------------

def test_frases_do_take_junta_o_bloco_por_energia_e_o_texto_lido(tmp_path):
    p = _projeto(tmp_path)
    leitor = sx.LeitorFalso(textos=["primeira", "segunda", "terceira"])
    frases = frases_do_take.frases(p, "T1", leitor)
    assert [t for _, _, t in frases] == ["primeira", "segunda", "terceira"]
    assert frases[0][0] == pytest.approx(0.0, abs=0.08) and frases[0][1] == pytest.approx(1.0, abs=0.08)


def test_transcrever_brutos_le_o_audio_de_cada_bruto_e_guarda_o_texto(tmp_path):
    brutos = tmp_path / "brutos"
    brutos.mkdir()
    fx.testsrc_com_audio(brutos / "IMG_1.mp4", dur=2.0)
    sx.projeto_minimo(tmp_path / "x", ADS, brutos=brutos)
    p = gp.carregar(tmp_path / "x")
    extrair_wav.extrair(p)
    textos = frases_do_take.transcrever_brutos(p, sx.LeitorFalso(textos="fala do take"))
    assert textos == {"IMG_1": "fala do take"}
    assert json.loads((p.pasta("transcricoes") / "IMG_1.json").read_text(encoding="utf-8"))["text"] == "fala do take"


def test_varredura_total_cobre_as_quatro_chaves_e_conta_os_trechos_distintos(tmp_path):
    ads = {"A1": {"corpo": [["T1", 0.0, 1.0]], "corpo_desconto": [["T1", 0.0, 0.9]],
                  "cta_normal": [["T1", 4.0, 5.0]], "cta_desconto": [["T1", 2.5, 3.5]]},
           "A2": {"corpo": [["T1", 0.0, 1.0]], "cta_normal": [["T1", 4.0, 5.0]]}}
    p = _projeto(tmp_path, ads=ads)
    leitor = sx.LeitorFalso(textos="x")
    achados = varredura_total.varrer(p, leitor)
    assert len(achados) == 4                                    # (0-1), (0-0.9), (4-5), (2.5-3.5)
    assert {a["chave"] for a in achados} == {"corpo", "corpo_desconto", "cta_normal", "cta_desconto"}
    assert all(a["subblocos"] for a in achados)


def test_conferir_buracos_le_a_mesma_janela_do_bruto_e_do_limpo(tmp_path):
    p = _projeto(tmp_path)
    sx.audio_por_blocos(p.wav("T1"), [(5.0, -12.0)])
    leitor = sx.LeitorFalso(textos=["texto do bruto", "texto do limpo"])
    bruto, limpo = conferir_buracos.conferir(p, "T1", 1.0, 1.5, leitor)
    assert (bruto, limpo) == ("texto do bruto", "texto do limpo")
    assert Path(leitor.chamadas[0][0]).parent.name == "wav" and Path(leitor.chamadas[1][0]).parent.name == "limpo"
    assert leitor.chamadas[0][1:] == (0.0, 3.5)                  # janela de 2,0 s de margem de cada lado


# --- a entrega de ponta a ponta, com os 11 gates reais -------------------------------------

ADS_UM = {"A1": {"corpo": [["T1", 0.0, 3.5]], "cta_normal": [["T1", 4.0, 5.0]]}}
TEXTO_DA_PECA = "você perde três horas por dia nisso e com uma automação isso roda sozinho"


def _pronto_para_entregar(tmp_path):
    """Projeto de uma peça, com tudo o que o pipeline gera, consistente: wav = limpo, a montada,
    a legenda gerada e a legendada (a montada com a faixa da legenda desenhada)."""
    p = sx.projeto_de_teste(tmp_path, ads=ADS_UM)
    p.garantir("wav")
    p.wav("T1").write_bytes(p.limpo("T1").read_bytes())
    p.garantir("montados")
    fx.testsrc_com_audio(p.montado("A1_normal"), dur=3.0)
    palavras = [w("palavra%d" % i, i * 0.5, i * 0.5 + 0.45) for i in range(6)]
    legendar.gerar(palavras, p.legenda_ass("A1_normal"))
    p.garantir("legendado")
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", str(p.montado("A1_normal")), "-vf",
                        "drawbox=x=0:y=ih*0.62:w=iw:h=ih*0.08:color=white:t=fill", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "20", "-c:a", "copy",
                        str(p.legendado("A1_normal"))], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return p


def _leitor_da_entrega():
    limpas = [w("a", 0.0, 0.9), w("b", 1.15, 1.9), w("c", 2.1, 2.9)]          # nenhuma palavra atravessa as emendas
    return sx.LeitorFalso(textos=sx.textos_em_sequencia(), palavras_da_peca=limpas, texto_peca=TEXTO_DA_PECA)


def test_entregar_de_ponta_a_ponta_roda_os_onze_gates_reais_e_copia(tmp_path):
    p = _pronto_para_entregar(tmp_path)
    r = entregar.entregar(p, leitor=_leitor_da_entrega())
    assert r.entregue, r.resumo()
    assert [n for n, _, _ in r.gates] == ["gate_envelope", "gate_fala", "gate_voz_distante", "gate_retomada",
                                          "gate_emendas", "gate_redundancia", "gate_ar_morto", "gate_legenda",
                                          "gate_sincronia", "gate_repeticao", "gate_offscript"]
    assert {e for _, e, _ in r.gates} == {"ok"}
    assert (p.pasta("ENTREGA") / "A1_normal.mp4").read_bytes() == p.legendado("A1_normal").read_bytes()
    assert json.loads(p.falas_json.read_text(encoding="utf-8")) == {"A1_normal": TEXTO_DA_PECA}


def test_entregar_com_a_legendada_de_outra_peca_trava_no_gate_de_sincronia(tmp_path):
    p = _pronto_para_entregar(tmp_path)
    fx.video_cores(p.legendado("A1_normal"), cores=("red", "green", "blue"), dur_cada=1.0, tamanho="320x568", fps=25)
    r = entregar.entregar(p, leitor=_leitor_da_entrega())
    assert r.entregue is False and r.codigo == 1
    estados = {n: e for n, e, _ in r.gates}
    assert estados["gate_sincronia"] == "defeito"
    assert not list(p.pasta("ENTREGA").glob("*"))


def test_entregar_com_fala_de_direcao_na_peca_trava_no_gate_offscript(tmp_path):
    p = _pronto_para_entregar(tmp_path)
    leitor = _leitor_da_entrega()
    leitor.texto_peca = lambda arquivo: ("tá bom" if Path(arquivo).parent.name == "legendado" else TEXTO_DA_PECA)
    r = entregar.entregar(p, leitor=leitor)
    assert r.entregue is False
    assert {n: e for n, e, _ in r.gates}["gate_offscript"] == "defeito"
    assert not list(p.pasta("ENTREGA").glob("*"))


def test_entregar_com_asr_que_falhou_nao_copia_e_sai_com_2(tmp_path):
    from gravado.nucleo import asr
    p = _pronto_para_entregar(tmp_path)
    r = entregar.entregar(p, leitor=sx.LeitorFalso(falhar=asr.ErroDeASR("sem rede")))
    assert r.entregue is False and r.codigo == 2
    assert not list(p.pasta("ENTREGA").glob("*"))
