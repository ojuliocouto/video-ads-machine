"""W4.D: os dois templates (9x16 e 1x1) montados a partir de parciais compartilhados.

Defeito 12 do plano: o JS da timeline era copiado nos dois `index.html`, e o null-guard dos b-rolls já faltou num
deles (o quadrado passou semanas sem ele: legenda, lettering e CTA sumiam). Agora cada template guarda só a
GEOMETRIA do formato (posição, tamanho, recuo) e inclui os parciais de `templates/_parciais/` por marcador
(`/* PARCIAL:<arquivo> */`). Quem resolve os marcadores é `overlay.html_injecao.resolver_parciais`, chamado no
primeiro passo do gerador (`injetar_marcadores`), antes de qualquer troca de texto.

O que estes testes seguram:
  - os dois formatos usam o MESMO timeline.js (hash igual) e nenhum deles carrega JS próprio;
  - toda âncora que os módulos do overlay trocam por texto continua existindo depois de resolver
    (hook, CTA, grade, beat P&B, wipes, b-rolls, marcadores, a linha do `strip_overlay`);
  - o GSAP sai de `templates/_vendor/gsap.min.js` quando existe e cai na CDN só sem ele (defeito 18);
  - (lento, mídia real) o snapshot do overlay do fixture em 6 instantes é IDÊNTICO, pixel a pixel, ao do golden
    anterior à modularização.
"""
import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from overlay import html_injecao as H

RAIZ = Path(__file__).resolve().parents[2]
PARCIAIS = RAIZ / "templates" / "_parciais"
TEMPLATES = {
    "9x16": RAIZ / "templates" / "reel-editorial" / "index.html",
    "1x1": RAIZ / "templates" / "reel-editorial-1x1" / "index.html",
}
ALTURA = {"9x16": 1920, "1x1": 1080}
MARCA = re.compile(r"/\* PARCIAL:([a-z0-9_]+\.(?:css|js)) \*/")


def _bruto(fmt):
    return TEMPLATES[fmt].read_text(encoding="utf-8")


def _resolvido(fmt):
    return H.ler_template(TEMPLATES[fmt])


def _scripts(html):
    """Corpo de cada <script> sem src (o JS da página)."""
    return re.findall(r"<script>(.*?)</script>", html, flags=re.S)


# --- um JS só ------------------------------------------------------------------------------------

@pytest.mark.parametrize("fmt", ["9x16", "1x1"])
def test_o_template_nao_carrega_js_proprio_so_o_marcador(fmt):
    corpos = [c.strip() for c in _scripts(_bruto(fmt))]
    assert corpos == ["/* PARCIAL:timeline.js */"], corpos


def test_os_dois_formatos_usam_o_mesmo_timeline_js():
    js = (PARCIAIS / "timeline.js").read_text(encoding="utf-8")
    hashes = set()
    for fmt in TEMPLATES:
        corpos = _scripts(_resolvido(fmt))
        assert len(corpos) == 1, fmt
        assert corpos[0].strip() == js.strip(), fmt
        hashes.add(hashlib.sha256(corpos[0].strip().encode("utf-8")).hexdigest())
    assert len(hashes) == 1


def test_timeline_js_tem_o_null_guard_dos_brolls():
    # o strip_overlay remove scrim, card e tag: sem a guarda o GSAP recebe null e mata o script inteiro
    js = (PARCIAIS / "timeline.js").read_text(encoding="utf-8")
    assert "if (!scrim || !card || !tag) return;" in js


@pytest.mark.parametrize("fmt", ["9x16", "1x1"])
def test_todo_marcador_aponta_para_um_parcial_que_existe(fmt):
    nomes = MARCA.findall(_bruto(fmt))
    assert nomes, fmt
    for n in nomes:
        assert (PARCIAIS / n).is_file(), n
    res = _resolvido(fmt)
    assert not MARCA.search(res)
    assert res.count("<style>") == 1 and res.count("</style>") == 1   # o hook punch troca o </style>


def test_os_dois_formatos_incluem_os_mesmos_parciais():
    assert MARCA.findall(_bruto("9x16")) == MARCA.findall(_bruto("1x1"))
    for n in ("base.css", "legenda.css", "hook.css", "cta.css", "timeline.js"):
        assert n in MARCA.findall(_bruto("9x16")), n


def test_parcial_ausente_e_erro_que_nomeia_o_arquivo(tmp_path):
    with pytest.raises(FileNotFoundError, match="nao_existe.css"):
        H.resolver_parciais("<style>/* PARCIAL:nao_existe.css */</style>", pasta=tmp_path)


def test_html_sem_marcador_passa_intacto():
    html = "<style>a{}</style><script>var x;</script>"
    assert H.resolver_parciais(html, vendor=Path("/nao/existe")) == html


def test_injetar_marcadores_resolve_os_parciais_primeiro():
    html = H.injetar_marcadores(_bruto("9x16"), "CAPS", "LETTS")
    assert not MARCA.search(html)
    assert "CAPS" in html and "LETTS" in html


# --- as âncoras que os outros módulos trocam por texto ------------------------------------------

@pytest.mark.parametrize("fmt", ["9x16", "1x1"])
def test_ancoras_dos_modulos_do_overlay_continuam_no_template_resolvido(fmt):
    res = _resolvido(fmt)
    ancoras = [
        # hook.aplicar_html
        'id="hook" class="clip" data-start="0" data-duration="2.5"',
        '<div data-hf-id="hf-bc1a" class="eyebrow">uma skill de</div>',
        '<div data-hf-id="hf-8q5w" class="l1">criação de</div>',
        '<div data-hf-id="hf-ons9" class="accent">páginas</div>',
        '#hook .l1 { font-family:"Inter"; font-weight:300; color:#fff;',
        'tl.to("#hook .hook-inner", { scale: 1.04, duration: 1.7, ease: "sine.inOut" }, 0.8);',
        # cta.aplicar_html (o rótulo e o lead agora são trocáveis nos dois formatos)
        '<div data-hf-id="hf-laqu" class="lead">toca em</div>\n        ',
        '<div data-hf-id="hf-wto1" class="pill" id="cta-pill">saiba mais</div>',
        'id="cta" class="clip"', 'id="ev-logo" class="clip"',
        'data-start="50.4" data-duration="4.96" data-track-index="46"',
        'data-start="46.7" data-duration="8.68" data-track-index="48"',
        "}, 50.5);", "}, 50.6);", "}, 50.75);", "}, 51.0);", "}, 46.9);",
        # html_injecao
        "<!-- INJECT:captions -->", "<!-- INJECT:letterings -->", "/* INJECT:wipes */",
        'data-start="0" data-duration="55.36"',
        "radial-gradient(130% 100% at 50% 22%, rgba(255,193,128,0.16), rgba(255,150,80,0.05) 45%, transparent 72%)",
        "linear-gradient(180deg, rgba(255,168,92,0.06) 0%, transparent 38%, rgba(28,14,4,0.16) 100%)",
        # brolls.injetar_html
        "<!-- B-ROLLS (injected) -->", "<!-- LOWER THIRD -->", "const BROLLS = [",
        # build_composite.strip_overlay (troca por linha inteira)
        "html, body { width:1080px; height:%dpx; overflow:hidden; background:#05060a; }" % ALTURA[fmt],
    ]
    for a in ancoras:
        assert a in res, (fmt, a)
    assert H.remover_beat_pb(res) != res
    assert "BEAT PRETO E BRANCO" not in H.remover_beat_pb(res)


def test_so_o_9x16_tem_o_marcador_de_chips():
    assert "<!-- INJECT:chips -->" in _bruto("9x16")


@pytest.mark.parametrize("fmt", ["9x16", "1x1"])
def test_strip_overlay_nao_mata_linha_dos_parciais(fmt):
    # o strip remove a LINHA inteira que contém estes trechos: nenhum parcial pode ter um deles
    kill = ['id="a-roll"', 'id="a-roll-audio"', 'id="grade"', 'id="vignette"',
            'class="broll-scrim', 'class="broll-tag', 'class="broll-vid']
    for p in PARCIAIS.iterdir():
        texto = p.read_text(encoding="utf-8")
        for k in kill:
            assert k not in texto, (p.name, k)


# --- GSAP local ------------------------------------------------------------------------------------

def test_gsap_local_entra_inline_quando_existe(tmp_path):
    vendor = tmp_path / "gsap.min.js"
    vendor.write_text("/* gsap */ window.gsap={};" + " " * 20000, encoding="utf-8")
    html = H.resolver_parciais(_bruto("9x16"), vendor=vendor)
    assert "cdn.jsdelivr.net/npm/gsap" not in html
    assert "/* gsap */ window.gsap={};" in html


def test_gsap_cai_na_cdn_sem_a_copia_local(tmp_path):
    html = H.resolver_parciais(_bruto("9x16"), vendor=tmp_path / "nao_existe.js")
    assert H.TAG_GSAP_CDN in html


def test_copia_local_truncada_nao_e_usada(tmp_path):
    vendor = tmp_path / "gsap.min.js"
    vendor.write_text("<!doctype html>erro 404", encoding="utf-8")
    assert H.TAG_GSAP_CDN in H.resolver_parciais(_bruto("9x16"), vendor=vendor)


def test_vam_gsap_cdn_forca_a_cdn(tmp_path, monkeypatch):
    vendor = tmp_path / "gsap.min.js"
    vendor.write_text("window.gsap={};" + " " * 20000, encoding="utf-8")
    monkeypatch.setenv("VAM_GSAP", "cdn")
    assert H.TAG_GSAP_CDN in H.resolver_parciais(_bruto("9x16"), vendor=vendor)


def test_o_setup_ainda_acha_a_versao_do_gsap_no_template():
    # setup.sh faz grep de gsap@X.Y.Z em templates/*/index.html para baixar a cópia local
    for fmt in TEMPLATES:
        assert re.search(r"gsap@[0-9][0-9.]*", _bruto(fmt)), fmt


# --- assinatura do template (o gate "template mudou no meio do build" precisa dos parciais) -------

def test_assinatura_muda_quando_um_parcial_muda(tmp_path):
    pasta = tmp_path / "templates"
    shutil.copytree(RAIZ / "templates" / "_parciais", pasta / "_parciais")
    (pasta / "reel-editorial").mkdir()
    shutil.copy(TEMPLATES["9x16"], pasta / "reel-editorial" / "index.html")
    idx = pasta / "reel-editorial" / "index.html"
    antes = H.assinatura_template(idx, pasta=pasta / "_parciais")
    js = pasta / "_parciais" / "timeline.js"
    js.write_text(js.read_text(encoding="utf-8") + "\n// mudou\n", encoding="utf-8")
    assert H.assinatura_template(idx, pasta=pasta / "_parciais") != antes


# --- sem nome de cliente --------------------------------------------------------------------------

def test_parciais_e_templates_sem_nome_de_cliente():
    from tests.cinema.test_insert_ui import _hashes, achados_no_texto
    hashes = _hashes()
    arquivos = list(PARCIAIS.iterdir()) + list(TEMPLATES.values())
    for p in arquivos:
        assert not achados_no_texto(p.read_text(encoding="utf-8"), hashes), p.name


# --- snapshot: o render não mudou ------------------------------------------------------------------

INSTANTES = "0.5,4.0,8.5,11.5,15.9,17.0"


def _hyperframes():
    c = RAIZ / "node_modules" / ".bin" / "hyperframes"
    if c.exists():
        return str(c)
    pytest.skip("hyperframes ausente em node_modules/.bin (rode bash setup.sh)")


def _snapshot(hf, html, pasta, fmt, midia):
    pasta.mkdir(parents=True)
    (pasta / "index.html").write_text(html, encoding="utf-8")
    tmpl = TEMPLATES[fmt].parent
    shutil.copytree(tmpl / "fonts", pasta / "fonts")
    shutil.copy(tmpl / "meta.json", pasta / "meta.json")
    shutil.copy(midia / "fixture" / "midia" / "logo.png", pasta / "logo.png")
    subprocess.run([hf, "snapshot", str(pasta), "--at", INSTANTES, "--no-end", "--describe", "false",
                    "--no-browser-gpu", "-o", str(pasta / "snaps")], check=True, capture_output=True, timeout=600)
    return sorted((pasta / "snaps").glob("frame-*.png"))


@pytest.mark.lento
@pytest.mark.midia_real
def test_snapshot_do_overlay_9x16_identico_ao_golden_anterior(tmp_path):
    """O golden (`$VAM_PARIDADE_MIDIA/golden`) nasceu ANTES da modularização: o overlay do fixture gerado agora
    renderiza os mesmos pixels nos 6 instantes (hook, legenda de tinta invertida, pilha, lettering em split, CTA,
    lettering com logo sobre o CTA). O HTML muda de forma (parciais, comentários), o render não."""
    import numpy as np
    from PIL import Image

    from tests.paridade import capturar as C
    midia = C.exigir_midia()
    hf = _hyperframes()
    antes_html = (C.pasta_golden(midia) / "overlay" / "index_overlay.html").read_text(encoding="utf-8")
    cap = C.capturar(C.raiz_do_repo(), midia, etapas=("timeline", "overlay"))
    depois_html = cap.arquivos["overlay/index_overlay.html"]
    assert depois_html != antes_html, "o HTML deveria mudar de forma"
    a = _snapshot(hf, antes_html, tmp_path / "antes", "9x16", midia)
    b = _snapshot(hf, depois_html, tmp_path / "depois", "9x16", midia)
    assert len(a) == len(b) == 6
    for pa, pb in zip(a, b):
        ia = np.asarray(Image.open(pa).convert("RGBA"))
        ib = np.asarray(Image.open(pb).convert("RGBA"))
        assert ia.shape == ib.shape, pa.name
        diferentes = int((ia != ib).any(axis=2).sum())
        assert diferentes == 0, "%s: %d pixels diferentes" % (pa.name, diferentes)
