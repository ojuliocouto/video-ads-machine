"""W5.B: inserts de UI em HTML (C8). Sete templates genéricos (whatsapp, terminal, kanban, dashboard,
agenda, contador, fluxo) que o aluno preenche com um JSON e viram um mp4 na proporção do painel.

O que fica fixado aqui:
- o texto do JSON entra EXATO no HTML (escape certo, sem injeção, uma passada só);
- nenhum nome real nem marca de terceiro, por hash (igual ao do gravado) e sem recurso externo;
- o render (mockado) recebe a proporção do painel e a duração com no máximo 1 quadro de erro;
- cada template renderiza com o exemplo e o HTML gerado é o golden;
- dado inválido para ANTES do render e nomeia o campo; sem motor de render sai UMA linha com o comando.
O render de verdade só roda no teste `lento` (precisa do HyperFrames ou de um Chrome).
"""
import copy
import hashlib
import html
import os
import re
import shutil
import subprocess
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

import pytest

from cinema import insert_ui

RAIZ = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = RAIZ / "templates" / "inserts_ui"
GOLDEN_DIR = Path(__file__).resolve().parent / "golden_inserts_ui"
DENYLIST_GRAVADO = RAIZ / "tests" / "gravado" / "denylist_local.sha256"
DENYLIST_INSERTS = Path(__file__).resolve().parent / "denylist_inserts_ui.sha256"

NOMES = ("whatsapp", "terminal", "kanban", "dashboard", "agenda", "contador", "fluxo")

# Campo obrigatório de cada template (some do JSON => erro que nomeia o campo).
OBRIGATORIO = {"whatsapp": "mensagens", "terminal": "linhas", "kanban": "colunas", "dashboard": "kpis",
               "agenda": "dias", "contador": "valor", "fluxo": "etapas"}
# Um texto de cada template (estourar o limite => erro que nomeia o campo).
TEXTO = {"whatsapp": "conversa_nome", "terminal": "titulo_janela", "kanban": "titulo",
         "dashboard": "titulo", "agenda": "titulo", "contador": "legenda", "fluxo": "titulo"}
# Chaves cujo valor é escolha ou cor, não texto que aparece na tela.
NAO_TEXTO = {"quem", "tipo", "destaque", "icone"}


# --- denylist por hash (o mesmo método de tests/gravado/test_sem_cliente.py) ---------------------

def _hashes():
    saida = set()
    for arq in (DENYLIST_GRAVADO, DENYLIST_INSERTS):
        for linha in arq.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#"):
                saida.add(linha)
    return saida


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _sha(texto):
    return hashlib.sha256(unicodedata.normalize("NFC", texto).encode("utf-8")).hexdigest()


def achados_no_texto(texto, hashes):
    """Sequências de 1 a 3 palavras (só letras, sem caixa) cujo sha256 está na lista."""
    tokens = re.findall(r"[^\W\d_]+", texto.casefold())
    achados = []
    for n in (1, 2, 3):
        for i in range(len(tokens) - n + 1):
            gram = " ".join(tokens[i:i + n])
            if _sha(gram) in hashes or _sha(_sem_acento(gram)) in hashes:
                achados.append(gram)
    return achados


# Termos plantados em pedaços: juntos dão o termo, separados não casam com nada.
PLANTADOS = [("insta", "gram"), ("ric", "ardo"), ("ver", "tex"), ("chat", "gpt"), ("hot", "mart"),
             ("au", "tonomia"), ("th", "ales"), ("bon", "fim")]


# --- utilitários -------------------------------------------------------------------------------

def _mapear(obj, f, chave=None):
    """Copia `obj` aplicando `f` a cada texto, menos aos valores de escolha e cor."""
    if isinstance(obj, dict):
        return {k: _mapear(v, f, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_mapear(v, f, chave) for v in obj]
    if isinstance(obj, str) and chave not in NAO_TEXTO:
        return f(obj)
    return obj


def _textos(obj, chave=None):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _textos(v, k)
    elif isinstance(obj, list):
        for v in obj:
            yield from _textos(v, chave)
    elif isinstance(obj, str) and chave not in NAO_TEXTO:
        yield obj


class Motor:
    """Motor falso: guarda o pedido e o conteúdo da pasta enquanto ela existe, e escreve o mp4."""

    def __init__(self):
        self.pedidos = []
        self.html = None
        self.fontes = None

    def __call__(self, pedido):
        self.pedidos.append(pedido)
        self.html = (pedido.pasta / "index.html").read_text(encoding="utf-8")
        pasta_fontes = pedido.pasta / "fonts"
        self.fontes = sorted(p.name for p in pasta_fontes.glob("*.woff2")) if pasta_fontes.is_dir() else []
        pedido.saida.write_bytes(b"mp4-falso")


def _gerar(nome, dados=None, **kw):
    """HTML do template com os dados (o exemplo, se não vierem)."""
    dados = copy.deepcopy(insert_ui.exemplo(nome)) if dados is None else dados
    return insert_ui.gerar_html(nome, dados, **kw)


class _Estrutura(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.atributos = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.atributos.extend((tag, k, v) for k, v in attrs)


def _estrutura(texto):
    p = _Estrutura()
    p.feed(texto)
    return p


# --- os sete templates e o exemplo ---------------------------------------------------------------

def test_os_sete_templates_existem_na_ordem():
    assert insert_ui.templates() == NOMES
    for nome in NOMES:
        assert (TEMPLATES_DIR / (nome + ".html")).is_file(), nome


@pytest.mark.parametrize("nome", NOMES)
def test_o_exemplo_de_cada_template_e_valido_e_nao_e_alterado_por_quem_o_pede(nome):
    ex = insert_ui.exemplo(nome)
    assert insert_ui.validar(nome, ex)
    ex["lixo"] = 1
    assert "lixo" not in insert_ui.exemplo(nome)


def test_template_desconhecido_diz_quais_existem():
    with pytest.raises(insert_ui.TemplateInexistente) as e:
        insert_ui.exemplo("planilha")
    for nome in NOMES:
        assert nome in str(e.value)


# --- o texto do JSON entra exato -----------------------------------------------------------------

@pytest.mark.parametrize("nome", NOMES)
def test_cada_texto_do_json_entra_exato_no_html_com_escape(nome):
    marca = lambda s: s + "&<'"       # noqa: E731  (acha o escape e a aspa; o acento já vem nos exemplos)
    dados = _mapear(insert_ui.exemplo(nome), marca)
    texto = _gerar(nome, dados)
    for t in _textos(dados):
        assert html.escape(t, quote=True) in texto, (nome, t)
    assert "&<'" not in texto           # nunca cru


@pytest.mark.parametrize("nome", NOMES)
def test_acentos_e_cedilha_entram_sem_virar_entidade(nome):
    dados = _mapear(insert_ui.exemplo(nome), lambda s: s + " ação")
    texto = _gerar(nome, dados)
    assert "ação" in texto and "&#xe7;" not in texto and "&ccedil;" not in texto


PAYLOADS = ["</script><script>alert(1)", '" onmouseover="alert(1)', "<img src=x onerror=alert(1)>",
            "{{_largura}}", "{{#cada x}}"]


@pytest.mark.parametrize("nome", NOMES)
@pytest.mark.parametrize("payload", PAYLOADS)
def test_texto_do_aluno_nao_injeta_tag_nem_atributo_nem_script(nome, payload):
    base = _estrutura(_gerar(nome))
    dados = copy.deepcopy(insert_ui.exemplo(nome))
    campo = TEXTO[nome]
    dados[campo] = payload
    atacado = _estrutura(_gerar(nome, dados))
    assert atacado.tags.count("script") == base.tags.count("script")
    assert "img" not in atacado.tags
    assert not [a for a in atacado.atributos if a[1].startswith("on")]
    assert len(atacado.tags) == len(base.tags)
    assert html.escape(payload, quote=True) in _gerar(nome, dados)


@pytest.mark.parametrize("nome", NOMES)
def test_o_template_expande_uma_vez_so_e_nao_sobra_marcador(nome):
    texto = _gerar(nome)
    assert "{{" not in texto and "<!--VAM" not in texto


def test_chaves_duplas_no_texto_do_aluno_ficam_como_estao():
    dados = copy.deepcopy(insert_ui.exemplo("contador"))
    dados["legenda"] = "{{_largura}} e {{#cada x}}"
    assert "{{_largura}} e {{#cada x}}" in _gerar("contador", dados)


# --- zero nome real, zero marca, zero recurso externo --------------------------------------------

def test_a_varredura_pega_cada_termo_plantado_e_nao_acusa_texto_comum():
    hs = _hashes()
    for partes in PLANTADOS:
        planta = "".join(partes)
        assert achados_no_texto("trecho " + planta + " e mais", hs), planta
        assert achados_no_texto(planta.upper() + "7", hs), planta
    assert achados_no_texto("a conversa, o funil, a agenda e o painel do agente", hs) == []


def _arquivos_a_varrer():
    base = [RAIZ / "scripts" / "cinema" / "insert_ui.py", RAIZ / "scripts" / "cli" / "insert.py",
            Path(__file__), RAIZ / "tests" / "cli" / "test_insert.py"]
    return sorted(TEMPLATES_DIR.glob("*.html")) + base


def test_ha_arquivos_para_varrer():
    nomes = {p.name for p in _arquivos_a_varrer()}
    assert {"whatsapp.html", "fluxo.html", "insert_ui.py", "insert.py", "test_insert_ui.py"} <= nomes


def test_zero_nome_real_ou_marca_nos_templates_nos_modulos_e_no_html_gerado():
    hs = _hashes()
    sujos = {}
    for p in _arquivos_a_varrer():
        achados = achados_no_texto(p.read_text(encoding="utf-8"), hs)
        if achados:
            sujos[p.name] = sorted(set(achados))
    for nome in NOMES:
        achados = achados_no_texto(_gerar(nome), hs)
        if achados:
            sujos["html:" + nome] = sorted(set(achados))
    assert not sujos, sujos


@pytest.mark.parametrize("nome", NOMES)
def test_o_nome_do_app_de_terceiro_nao_aparece_no_template_nem_no_html(nome):
    marca = "whats" + "app"           # o NOME do template é whatsapp; o app e a marca não aparecem na tela
    for texto in ((TEMPLATES_DIR / (nome + ".html")).read_text(encoding="utf-8"), _gerar(nome)):
        assert marca not in texto.lower(), nome


@pytest.mark.parametrize("nome", NOMES)
def test_template_sem_imagem_logo_link_nem_recurso_de_fora(nome):
    bruto = (TEMPLATES_DIR / (nome + ".html")).read_text(encoding="utf-8")
    gerado = _gerar(nome)
    for texto in (bruto, gerado):
        baixo = texto.lower()
        for proibido in ("<img", "<video", "<audio", "<iframe", "<link", "<a ", "http://", "https://",
                         "//cdn", "data:image", "base64", "@import", "<canvas"):
            assert proibido not in baixo, (nome, proibido)
        # todo url() e relativo e aponta para fonts/
        for url in re.findall(r"url\(([^)]*)\)", baixo):
            assert url.strip("'\" ").startswith("fonts/") or url.strip("'\" ").startswith("#"), (nome, url)


def test_zero_travessao_em_templates_modulos_e_exemplos():
    for p in _arquivos_a_varrer():
        texto = p.read_text(encoding="utf-8")
        assert chr(0x2014) not in texto and chr(0x2013) not in texto, p.name
    for nome in NOMES:
        texto = _gerar(nome)
        assert chr(0x2014) not in texto and chr(0x2013) not in texto, nome


# --- golden --------------------------------------------------------------------------------------

@pytest.mark.parametrize("nome", NOMES)
def test_html_gerado_com_o_exemplo_e_o_golden(nome):
    gerado = _gerar(nome, dur=4.0, proporcao="horizontal", fps=30)
    golden = GOLDEN_DIR / (nome + ".html")
    if os.environ.get("VAM_ATUALIZAR_GOLDEN") == "1":
        GOLDEN_DIR.mkdir(exist_ok=True)
        golden.write_text(gerado, encoding="utf-8")
    assert golden.is_file(), "sem golden: gere com VAM_ATUALIZAR_GOLDEN=1 e confira a diferença à mão"
    assert gerado == golden.read_text(encoding="utf-8")


@pytest.mark.parametrize("nome", NOMES)
def test_o_html_e_deterministico(nome):
    assert _gerar(nome) == _gerar(nome)


@pytest.mark.parametrize("nome", NOMES)
def test_o_html_e_uma_composicao_do_hyperframes_com_a_geometria_pedida(nome):
    texto = _gerar(nome, dur=3.0, proporcao="painel", fps=30)
    assert 'data-composition-id="main"' in texto
    assert 'data-width="1080"' in texto and 'data-height="1150"' in texto
    assert 'data-duration="3.0000"' in texto
    assert "window.__timelines" in texto and "__vamSeek" in texto
    # os quadros dependem só do tempo: nada de relógio, aleatório ou rede
    for proibido in ("Math.random", "Date.now", "performance.now", "setTimeout", "setInterval",
                     "requestAnimationFrame", "fetch(", "XMLHttpRequest"):
        assert proibido not in texto, (nome, proibido)


# --- proporção do painel -------------------------------------------------------------------------

def test_proporcoes_nomeadas():
    assert insert_ui.PROPORCOES == {"horizontal": (1920, 1080), "painel": (1080, 1150),
                                    "vertical": (1080, 1920), "quadrado": (1080, 1080)}
    assert insert_ui.PROPORCAO_PADRAO == "horizontal"


@pytest.mark.parametrize("texto,esperado", [
    ("horizontal", (1920, 1080)), ("painel", (1080, 1150)), ("vertical", (1080, 1920)),
    ("16:9", (1920, 1080)), ("1:1", (1080, 1080)), ("4:5", (1080, 1350)), ("9:16", (1080, 1920)),
    ("1080x1150", (1080, 1150)), ("1280x720", (1280, 720)),
])
def test_resolver_proporcao(texto, esperado):
    assert insert_ui.resolver_proporcao(texto) == esperado


@pytest.mark.parametrize("texto", ["", "abc", "0:5", "16:0", "1081x1150", "100x100", "9000x9000", "3:", None])
def test_proporcao_invalida_e_erro(texto):
    with pytest.raises(insert_ui.ProporcaoInvalida):
        insert_ui.resolver_proporcao(texto)


def test_dimensoes_sao_pares_para_o_h264():
    for texto in ("7:5", "3:2", "5:3", "4:5", "21:9", "13:17"):
        w, h = insert_ui.resolver_proporcao(texto)
        assert w % 2 == 0 and h % 2 == 0, (texto, w, h)


# --- o render (mockado) ----------------------------------------------------------------------------

@pytest.mark.parametrize("nome", NOMES)
@pytest.mark.parametrize("proporcao", sorted(insert_ui.PROPORCOES))
def test_o_motor_recebe_a_proporcao_do_painel(nome, proporcao, tmp_path):
    motor = Motor()
    saida = tmp_path / "inserts" / "x.mp4"
    saida.parent.mkdir()
    insert_ui.renderizar(nome, insert_ui.exemplo(nome), saida, dur=4.0, proporcao=proporcao, motor=motor)
    (pedido,) = motor.pedidos
    w, h = insert_ui.PROPORCOES[proporcao]
    assert (pedido.largura, pedido.altura) == (w, h)
    assert abs(pedido.largura / pedido.altura - w / h) < 0.005
    assert 'data-width="%d"' % w in motor.html and 'data-height="%d"' % h in motor.html
    assert pedido.template == nome


@pytest.mark.parametrize("dur", [1.0, 2.0, 3.3, 4.0, 4.17, 7.5])
@pytest.mark.parametrize("fps", [24, 25, 30])
def test_a_duracao_do_render_erra_no_maximo_um_quadro(dur, fps, tmp_path):
    motor = Motor()
    saida = tmp_path / "a.mp4"
    res = insert_ui.renderizar("contador", insert_ui.exemplo("contador"), saida, dur=dur, fps=fps, motor=motor)
    (pedido,) = motor.pedidos
    assert pedido.fps == fps
    assert abs(pedido.quadros / pedido.fps - dur) <= 1.0 / fps + 1e-9
    assert pedido.quadros == max(1, round(dur * fps))
    # a composição declara a duração dos quadros que vai renderizar
    m = re.search(r'data-duration="([0-9.]+)"', motor.html)
    assert abs(float(m.group(1)) - pedido.quadros / fps) < 1e-3
    assert res.quadros == pedido.quadros and res.fps == fps


def test_fps_padrao_e_o_do_motor_30():
    assert insert_ui.FPS_PADRAO == 30


@pytest.mark.parametrize("dur", [0, 0.2, -1, 99, float("nan"), "4", True, None])
def test_duracao_fora_da_faixa_e_erro_e_nao_chama_o_motor(dur, tmp_path):
    motor = Motor()
    with pytest.raises(ValueError):
        insert_ui.renderizar("contador", insert_ui.exemplo("contador"), tmp_path / "a.mp4", dur=dur, motor=motor)
    assert motor.pedidos == []


def test_o_motor_ve_a_pasta_com_index_e_so_as_fontes_do_repo(tmp_path):
    motor = Motor()
    insert_ui.renderizar("whatsapp", insert_ui.exemplo("whatsapp"), tmp_path / "a.mp4", motor=motor)
    assert motor.fontes, "a pasta do render não tem fontes"
    for f in motor.fontes:
        assert (RAIZ / "fonts" / f).is_file(), f
    # toda fonte que o HTML pede foi copiada
    pedidas = set(re.findall(r'url\("?fonts/([^")]+)"?\)', motor.html))
    assert pedidas and pedidas <= set(motor.fontes), (pedidas, motor.fontes)
    # só Inter, Montserrat, Archivo (e Playfair no contador): as famílias do repo
    familias = set(re.findall(r'font-family:\s*"([^"]+)"', motor.html))
    assert {"Inter", "Montserrat", "Archivo"} <= familias


def test_a_pasta_temporaria_some_depois_do_render(tmp_path):
    motor = Motor()
    insert_ui.renderizar("fluxo", insert_ui.exemplo("fluxo"), tmp_path / "a.mp4", motor=motor)
    assert not motor.pedidos[0].pasta.exists()


def test_o_mp4_final_aparece_inteiro_e_sem_temporario(tmp_path):
    saida = tmp_path / "ins" / "k.mp4"
    saida.parent.mkdir()
    insert_ui.renderizar("kanban", insert_ui.exemplo("kanban"), saida, motor=Motor())
    assert saida.read_bytes() == b"mp4-falso"
    assert sorted(p.name for p in saida.parent.iterdir()) == ["k.mp4"]


def test_motor_que_falha_nao_toca_no_mp4_antigo_e_nao_deixa_temporario(tmp_path):
    saida = tmp_path / "k.mp4"
    saida.write_bytes(b"antigo")

    def quebra(pedido):
        pedido.saida.write_bytes(b"pela metade")
        raise insert_ui.RenderFalhou("o motor caiu")

    with pytest.raises(insert_ui.RenderFalhou):
        insert_ui.renderizar("kanban", insert_ui.exemplo("kanban"), saida, motor=quebra)
    assert saida.read_bytes() == b"antigo"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["k.mp4"]


def test_motor_que_nao_escreve_nada_e_falha_do_render(tmp_path):
    with pytest.raises(insert_ui.RenderFalhou):
        insert_ui.renderizar("kanban", insert_ui.exemplo("kanban"), tmp_path / "k.mp4", motor=lambda p: None)
    assert list(tmp_path.iterdir()) == []


def test_dado_invalido_nao_chega_ao_motor(tmp_path):
    motor = Motor()
    dados = insert_ui.exemplo("terminal")
    dados["linhas"] = []
    with pytest.raises(insert_ui.DadosInvalidos):
        insert_ui.renderizar("terminal", dados, tmp_path / "t.mp4", motor=motor)
    assert motor.pedidos == [] and list(tmp_path.iterdir()) == []


# --- validação dos dados -----------------------------------------------------------------------

@pytest.mark.parametrize("nome", NOMES)
def test_campo_desconhecido_e_erro_que_o_nomeia(nome):
    dados = insert_ui.exemplo(nome)
    dados["campo_inventado"] = "x"
    with pytest.raises(insert_ui.DadosInvalidos) as e:
        insert_ui.validar(nome, dados)
    assert "campo_inventado" in str(e.value)


@pytest.mark.parametrize("nome", NOMES)
def test_campo_obrigatorio_que_falta_e_erro_que_o_nomeia(nome):
    dados = insert_ui.exemplo(nome)
    del dados[OBRIGATORIO[nome]]
    with pytest.raises(insert_ui.DadosInvalidos) as e:
        insert_ui.validar(nome, dados)
    assert OBRIGATORIO[nome] in str(e.value)


@pytest.mark.parametrize("nome", NOMES)
def test_texto_acima_do_limite_e_erro_que_nomeia_o_campo(nome):
    dados = insert_ui.exemplo(nome)
    dados[TEXTO[nome]] = "x" * 500
    with pytest.raises(insert_ui.DadosInvalidos) as e:
        insert_ui.validar(nome, dados)
    assert TEXTO[nome] in str(e.value)


@pytest.mark.parametrize("nome", NOMES)
@pytest.mark.parametrize("ruim", ["", "   ", 7, None, ["a"], "linha 1\nlinha 2"])
def test_texto_vazio_nao_texto_ou_com_quebra_de_linha_e_erro(nome, ruim):
    dados = insert_ui.exemplo(nome)
    dados[TEXTO[nome]] = ruim
    with pytest.raises(insert_ui.DadosInvalidos) as e:
        insert_ui.validar(nome, dados)
    assert TEXTO[nome] in str(e.value)


@pytest.mark.parametrize("nome", NOMES)
def test_dados_que_nao_sao_objeto_sao_erro(nome):
    for ruim in ([], "texto", 3, None):
        with pytest.raises(insert_ui.DadosInvalidos):
            insert_ui.validar(nome, ruim)


@pytest.mark.parametrize("nome", [n for n in NOMES if n != "contador"])
def test_lista_vazia_ou_grande_demais_e_erro(nome):
    campo = OBRIGATORIO[nome]
    dados = insert_ui.exemplo(nome)
    dados[campo] = []
    with pytest.raises(insert_ui.DadosInvalidos) as e:
        insert_ui.validar(nome, dados)
    assert campo in str(e.value)
    dados[campo] = copy.deepcopy(insert_ui.exemplo(nome)[campo]) * 40
    with pytest.raises(insert_ui.DadosInvalidos) as e:
        insert_ui.validar(nome, dados)
    assert campo in str(e.value)


@pytest.mark.parametrize("nome", ["dashboard", "contador", "fluxo", "kanban"])
@pytest.mark.parametrize("cor", ["red", "#fff", "#12345", "#gggggg", "rgb(1,2,3)", 7, "#ffffff;}"])
def test_destaque_so_aceita_hex_de_seis_digitos(nome, cor):
    dados = insert_ui.exemplo(nome)
    dados["destaque"] = cor
    with pytest.raises(insert_ui.DadosInvalidos) as e:
        insert_ui.validar(nome, dados)
    assert "destaque" in str(e.value)


@pytest.mark.parametrize("nome", ["dashboard", "contador", "fluxo", "kanban"])
def test_destaque_valido_entra_no_html(nome):
    dados = insert_ui.exemplo(nome)
    dados["destaque"] = "#12ab34"
    assert "#12ab34" in _gerar(nome, dados)


@pytest.mark.parametrize("ruim", [float("nan"), float("inf"), True, "9", None])
def test_numero_precisa_ser_finito_e_nao_booleano(ruim):
    dados = insert_ui.exemplo("contador")
    dados["valor"] = ruim
    with pytest.raises(insert_ui.DadosInvalidos) as e:
        insert_ui.validar("contador", dados)
    assert "valor" in str(e.value)


def test_kanban_movimento_que_aponta_para_cartao_ou_coluna_inexistente_e_erro():
    base = insert_ui.exemplo("kanban")
    for campo in ("da_coluna", "para_coluna", "cartao"):
        dados = copy.deepcopy(base)
        dados["movimento"][campo] = "não existe"
        with pytest.raises(insert_ui.DadosInvalidos) as e:
            insert_ui.validar("kanban", dados)
        assert campo in str(e.value)
    dados = copy.deepcopy(base)
    dados["movimento"]["para_coluna"] = dados["movimento"]["da_coluna"]
    with pytest.raises(insert_ui.DadosInvalidos):
        insert_ui.validar("kanban", dados)


def test_whatsapp_quem_so_aceita_cliente_ou_voce():
    dados = insert_ui.exemplo("whatsapp")
    dados["mensagens"][0]["quem"] = "robô"
    with pytest.raises(insert_ui.DadosInvalidos) as e:
        insert_ui.validar("whatsapp", dados)
    assert "quem" in str(e.value)


def test_terminal_tipo_so_aceita_comando_ok_ou_passo():
    dados = insert_ui.exemplo("terminal")
    dados["linhas"][0]["tipo"] = "erro"
    with pytest.raises(insert_ui.DadosInvalidos) as e:
        insert_ui.validar("terminal", dados)
    assert "tipo" in str(e.value)


def test_fluxo_aceita_uma_ou_duas_caixas_por_etapa_e_recusa_tres():
    dados = insert_ui.exemplo("fluxo")
    caixa = dados["etapas"][0][0]
    dados["etapas"][1] = [dict(caixa), dict(caixa), dict(caixa)]
    with pytest.raises(insert_ui.DadosInvalidos) as e:
        insert_ui.validar("fluxo", dados)
    assert "etapas" in str(e.value)


def test_dashboard_formata_os_numeros_em_pt_br_no_html():
    dados = insert_ui.exemplo("dashboard")
    dados["kpis"][0].update(valor=1234567.5, casas=1, prefixo="R$ ")
    assert "R$ 1.234.567,5" in _gerar("dashboard", dados)


def test_contador_formata_o_valor_final_em_pt_br_no_html():
    dados = insert_ui.exemplo("contador")
    dados["valor"] = 12500
    assert "12.500" in _gerar("contador", dados)


def test_formatar_pt_br():
    assert insert_ui.formatar_ptbr(4380, 0) == "4.380"
    assert insert_ui.formatar_ptbr(14.9, 2) == "14,90"
    assert insert_ui.formatar_ptbr(0, 0) == "0"
    assert insert_ui.formatar_ptbr(-1234.5, 1) == "-1.234,5"
    assert insert_ui.formatar_ptbr(999.999, 2) == "1.000,00"


# --- escolha do motor --------------------------------------------------------------------------

def _hyperframes_falso(raiz):
    pasta = raiz / "node_modules" / ".bin"
    pasta.mkdir(parents=True)
    hf = pasta / "hyperframes"
    hf.write_text("#!/bin/sh\nexit 0\n")
    hf.chmod(0o755)
    return hf


def test_motor_padrao_prefere_o_hyperframes_do_repo(tmp_path, monkeypatch):
    monkeypatch.delenv("VAM_HYPERFRAMES", raising=False)
    hf = _hyperframes_falso(tmp_path)
    motor = insert_ui.motor_padrao(tmp_path)
    assert motor.nome == "hyperframes" and Path(motor.binario) == hf


def test_motor_padrao_aceita_o_binario_indicado_por_variavel(tmp_path, monkeypatch):
    hf = _hyperframes_falso(tmp_path / "outro")
    monkeypatch.setenv("VAM_HYPERFRAMES", str(hf))
    assert Path(insert_ui.motor_padrao(tmp_path / "vazio").binario) == hf


def test_sem_hyperframes_usa_o_chrome_do_sistema_com_playwright(tmp_path, monkeypatch):
    monkeypatch.delenv("VAM_HYPERFRAMES", raising=False)
    monkeypatch.setattr(insert_ui, "_achar_navegador", lambda: Path("/falso/chrome"))
    monkeypatch.setattr(insert_ui, "_playwright_disponivel", lambda: True)
    motor = insert_ui.motor_padrao(tmp_path)
    assert motor.nome == "navegador" and Path(motor.navegador) == Path("/falso/chrome")


def test_chrome_sem_playwright_nao_serve(tmp_path, monkeypatch):
    monkeypatch.delenv("VAM_HYPERFRAMES", raising=False)
    monkeypatch.setattr(insert_ui, "_achar_navegador", lambda: Path("/falso/chrome"))
    monkeypatch.setattr(insert_ui, "_playwright_disponivel", lambda: False)
    with pytest.raises(insert_ui.SemMotorDeRender):
        insert_ui.motor_padrao(tmp_path)


def test_sem_motor_sai_uma_linha_com_o_comando_que_resolve(tmp_path, monkeypatch):
    monkeypatch.delenv("VAM_HYPERFRAMES", raising=False)
    monkeypatch.setattr(insert_ui, "_achar_navegador", lambda: None)
    monkeypatch.setattr(insert_ui, "_playwright_disponivel", lambda: False)
    with pytest.raises(insert_ui.SemMotorDeRender) as e:
        insert_ui.renderizar("contador", insert_ui.exemplo("contador"), tmp_path / "a.mp4", raiz=tmp_path)
    msg = str(e.value)
    assert "\n" not in msg and "bash scripts/setup.sh" in msg
    assert list(tmp_path.iterdir()) == []


def _pedido(tmp_path):
    pasta = tmp_path / "proj"
    pasta.mkdir()
    return insert_ui.PedidoRender(template="contador", html="<html></html>", pasta=pasta,
                                  saida=tmp_path / "s.mp4", largura=1920, altura=1080, fps=30,
                                  quadros=120, dur=4.0)


def test_comando_do_hyperframes(tmp_path):
    pedido = _pedido(tmp_path)
    chamadas = []

    def executar(cmd, **kw):
        chamadas.append(cmd)
        pedido.saida.write_bytes(b"x")
        return 0, ""

    insert_ui.MotorHyperframes("/x/hyperframes", executar=executar)(pedido)
    (cmd,) = chamadas
    assert cmd[:2] == ["/x/hyperframes", "render"]
    assert str(pedido.pasta) in cmd
    assert cmd[cmd.index("-o") + 1] == str(pedido.saida)
    assert cmd[cmd.index("--fps") + 1] == "30"


def test_hyperframes_que_sai_com_erro_vira_render_falhou_com_o_fim_da_saida(tmp_path):
    pedido = _pedido(tmp_path)
    motor = insert_ui.MotorHyperframes("/x/hf", executar=lambda cmd, **kw: (1, "linha a\nlinha b\nfalhou aqui"))
    with pytest.raises(insert_ui.RenderFalhou) as e:
        motor(pedido)
    assert "falhou aqui" in str(e.value)


def test_hyperframes_que_sai_zero_sem_arquivo_e_render_falhou(tmp_path):
    motor = insert_ui.MotorHyperframes("/x/hf", executar=lambda cmd, **kw: (0, ""))
    with pytest.raises(insert_ui.RenderFalhou):
        motor(_pedido(tmp_path))


# --- render de verdade (lento) -----------------------------------------------------------------

@pytest.mark.lento
@pytest.mark.parametrize("nome", NOMES)
def test_render_real_sai_na_proporcao_e_na_duracao(nome, tmp_path):
    if not shutil.which("ffprobe"):
        pytest.skip("sem ffprobe")
    try:
        insert_ui.motor_padrao()
    except insert_ui.SemMotorDeRender as e:
        pytest.skip(str(e))
    saida = tmp_path / "a.mp4"
    res = insert_ui.renderizar(nome, insert_ui.exemplo(nome), saida, dur=2.0, proporcao="painel", fps=30)
    sonda = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
                            "-show_entries", "stream=width,height,nb_read_frames", "-of", "csv=p=0", str(saida)],
                           capture_output=True, text=True).stdout.strip().split(",")
    largura, altura, quadros = int(sonda[0]), int(sonda[1]), int(sonda[2])
    assert (largura, altura) == (1080, 1150)
    assert abs(quadros - res.quadros) <= 1
