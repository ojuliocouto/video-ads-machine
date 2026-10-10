#!/usr/bin/env python3
"""`vam montar <slug>`: o ÚNICO jeito de produzir um anúncio. Build e gates numa chamada só.

GUARDRAIL (05/08/2026, pedido do diretor: "nunca trocar o método"). Numa leva, dez anúncios foram montados chamando o
build direto, sem auditar nenhum, e a auditoria depois deu média 5,2: a leva inteira reprovada. Por isso:

  1. build e gates acontecem na MESMA chamada: não existe "montei, depois vejo";
  2. antes e durante o build, o primeiro gate que reprova (saída 1) ou morre (saída 2) INTERROMPE, e o motivo vai
     para o status.json do projeto: "está pronto?" é uma leitura (`vam status`), nunca memória;
  3. o build (`build_composite`) não roda sozinho, e o passo que produz o arquivo final recusa sem a aprovação do
     plano vigente;
  4. quem é medido não assina: este módulo nunca escreve `plano/aprovacao.json` (é do `vam aprovar`) nem
     `entrega/nota.json` (é do auditor, `vam auditar`). Ele escreve o laudo, e o laudo amarra o sha256 do arquivo.

## A ordem (seção 4 do plano)

  antes    gate_aprovacao, gate_fidelidade_roteiro, [gate_fidelidade_doc, só com roteiro vindo de Doc],
           gate_fala_roteiro, gate_entrada, gate_look
  motor    preparar: os arquivos do motor e a timeline.json (relógio único, com o plano de SFX)
  plano    gate_geometria (supressão de legenda aplicada e conferida de novo, quando ele pede), gate_safezone,
           gate_lettering, gate_congelamento (densidade, congelamento e moldura, pelo plano e pela timeline)
  motor    footage (a 1x, pela timeline: o overlay mede o fundo claro nela)
  motor    overlay HTML
  durante  gate_tela_vazia, gate_congelamento_build
  motor    render do overlay
  durante  gate_relogio
  motor    composição, aceleração, loudness e mix -> entrega/final_9x16.mp4
  durante  gate_template (o template e os parciais não mudaram do começo ao fim)
  prévia   entrega/final_whatsapp.mp4, ANTES do primeiro gate de saída, e as folhas de contato
  depois   os 15 gates de saída em paralelo (no máximo 4 por vez): todos rodam, o laudo precisa de todos
  laudo    entrega/laudo.json (contrato), amarrado ao sha256 do final

Saídas: 0 laudo PASS · 1 algum gate reprovou · 2 insumo inválido, gate que morreu ou motor que não rodou.

    python3 scripts/produzir_ad.py <slug> [--estado _local]      (o mesmo que `python3 scripts/vam.py montar <slug>`)
"""
import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_composite as BC  # noqa: E402
from caminhos import CODIGO, GATES  # noqa: E402
from entrega import laudo as LD  # noqa: E402
from entrega import whatsapp_versao  # noqa: E402
from projeto import modelo, pastas, status  # noqa: E402

ETAPA = "montar"
ANTES = ("gate_aprovacao", "gate_fidelidade_roteiro", "gate_fidelidade_doc", "gate_fala_roteiro", "gate_entrada",
         "gate_look")
PLANO = ("gate_geometria", "gate_safezone", "gate_lettering", "gate_congelamento")
DURANTE = ("gate_tela_vazia", "gate_congelamento_build", "gate_relogio", "gate_template")
DEPOIS = ("gate-ad", "medir_ritmo", "gate-colisao-texto", "gate-contraste-legenda", "auditar_ad", "gate_hook_visual",
          "gate_camera", "gate_cor", "gate_mix", "gate_sfx", "gate_insert", "gate_lettering_depois",
          "gate_safezone_depois", "gate_geometria_depois", "gate_texto_atras")
NOMES_DOS_GATES = ANTES + PLANO + DURANTE + DEPOIS
ETAPA_DO_GATE = dict([(n, "antes") for n in ANTES + PLANO] + [(n, "durante") for n in DURANTE]
                     + [(n, "depois") for n in DEPOIS])
PARALELO_MAX = 4
CAMPOS_DO_GATE = ("nome", "etapa", "resultado", "saida", "medido", "limiar", "motivo", "duracao_s")

ErroDoMotor = BC.ErroDoMotor


def ordem(projeto):
    """Os gates na ordem em que o montar os roda. O de fidelidade ao Doc só existe quando o roteiro veio de um Doc."""
    com_doc = (projeto.get("origem") or {}).get("tipo") == "doc_google"
    return [n for n in NOMES_DOS_GATES if n != "gate_fidelidade_doc" or com_doc]


class Contexto(object):
    """O que os gates leem: o projeto, o motor (caminhos do build) e, sob demanda, a timeline e o plano."""

    def __init__(self, pj, projeto, motor):
        self.pj, self.projeto, self.motor = pj, projeto, motor
        self._tl = None

    def timeline(self, reler=False):
        if self._tl is None or reler:
            self._tl = status.ler_json(self.pj.timeline)
        return self._tl

    def plano(self):
        return status.ler_json(self.pj.plano_json)

    @property
    def accel(self):
        return float(self.timeline()["relogio"]["aceleracao"])

    @property
    def a0(self):
        return float(self.timeline()["relogio"]["a0"])


# --- o formato de gate do laudo ---------------------------------------------------------------------------

def _json_ok(v):
    try:
        json.dumps(v)
        return v
    except (TypeError, ValueError):
        return json.loads(json.dumps(v, default=str))


def gate(nome, resultado, saida, motivo=None, medido=None, limiar=None):
    g = {"nome": nome, "etapa": ETAPA_DO_GATE.get(nome, "depois"), "resultado": resultado, "saida": int(saida)}
    if medido:
        g["medido"] = _json_ok(medido)
    if limiar:
        g["limiar"] = _json_ok(limiar)
    if motivo or resultado != "PASS":
        g["motivo"] = (motivo or resultado.lower()).strip()[:1500] or resultado.lower()
    return g


def _normalizar(nome, g):
    """O dict que o gate devolveu, no contrato do laudo: só os campos do contrato, o nome e a etapa do montar."""
    if not isinstance(g, dict) or g.get("resultado") not in ("PASS", "REPROVA", "ERRO", "PULADO"):
        return gate(nome, "ERRO", 2, "o gate devolveu um resultado fora do formato: %r" % (g,))
    d = {k: g[k] for k in CAMPOS_DO_GATE if k in g}
    d["nome"], d["etapa"] = nome, ETAPA_DO_GATE.get(nome, d.get("etapa", "depois"))
    d["saida"] = int(d.get("saida", 0 if d["resultado"] in ("PASS", "PULADO") else 1))
    if d["resultado"] == "REPROVA" and d["saida"] == 0:
        d["saida"] = 1
    if d["resultado"] == "PASS" and d["saida"] != 0:
        d["resultado"] = "ERRO"
    if d["resultado"] != "PASS" and len(str(d.get("motivo", "")).strip()) < 3:
        d["motivo"] = "%s sem motivo escrito pelo gate" % d["resultado"].lower()
    for k in ("medido", "limiar"):
        if k in d:
            d[k] = _json_ok(d[k]) if isinstance(d[k], dict) else {"valor": _json_ok(d[k])}
    return d


def de_resultado(nome, r):
    """Resultado(ok, motivo, detalhes) dos gates de projeto -> formato do laudo."""
    det = dict(r.detalhes or {})
    estado = det.get("estado")
    if estado == "PULADO":
        return gate(nome, "PULADO", 0, r.motivo or "pulado", medido=det)
    if r.ok:
        return gate(nome, "PASS", 0, medido=det)
    return gate(nome, "REPROVA", 1, r.motivo, medido=det)


def falhou(g):
    return g["resultado"] in ("REPROVA", "ERRO")


def _executar(funcao, ctx, nome):
    """Roda um gate. Exceção vira ERRO (saída 2): gate que morre nunca aprova."""
    t0 = time.time()
    try:
        g = _normalizar(nome, funcao(ctx))
    except Exception as e:                       # o gate morreu: falha de ferramenta, nunca aprovação
        g = gate(nome, "ERRO", 2, "o gate não conseguiu medir: %s: %s" % (type(e).__name__, e))
    g["duracao_s"] = round(time.time() - t0, 2)
    return g


# --- gates que rodam como processo (CLI) ------------------------------------------------------------------

def _log_dos_gates(ctx):
    pasta = ctx.pj.render_dir / "gates"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _cli(ctx, nome, argv, ler_json=False):
    """Roda um gate pela CLI dele. 0 PASS, 1 REPROVA (motivo das linhas que reprovam), outro ERRO (com o stderr).
    A saída inteira fica em render/gates/<nome>.log para quem for ler."""
    r = subprocess.run([sys.executable] + [str(a) for a in argv], capture_output=True, text=True, cwd=str(CODIGO))
    log = _log_dos_gates(ctx) / ("%s.log" % nome)
    log.write_text("$ %s\n\n%s\n--- stderr ---\n%s" % (" ".join(str(a) for a in argv), r.stdout, r.stderr),
                   encoding="utf-8")
    medido = {"log": ctx.pj.relativo(log)}
    if ler_json:
        for linha in reversed((r.stdout or "").strip().splitlines()):
            if linha.startswith("{"):
                try:
                    return json.loads(linha)
                except ValueError:
                    break
    if r.returncode == 0:
        return gate(nome, "PASS", 0, medido=medido)
    if r.returncode == 1:
        linhas = [l.strip(" -") for l in (r.stdout or "").splitlines()
                  if re.search(r"REPROVA|\[X\]|^\s*-\s|cobre|t=", l)]
        return gate(nome, "REPROVA", 1, "; ".join(linhas[:6]) or (r.stdout or "").strip()[-400:], medido=medido)
    return gate(nome, "ERRO", 2, "saída %d: %s" % (r.returncode, ((r.stderr or r.stdout or "").strip()[-600:]
                                                                 or "sem mensagem")), medido=medido)


# --- antes ------------------------------------------------------------------------------------------------

def _g_aprovacao(ctx):
    from gates import gate_aprovacao
    return de_resultado("gate_aprovacao", gate_aprovacao.rodar(ctx.pj))


def _g_fidelidade_roteiro(ctx):
    from gates import gate_fidelidade_roteiro as G
    try:
        return de_resultado("gate_fidelidade_roteiro", G.rodar(ctx.pj))
    except G.InsumoInvalido as e:
        return gate("gate_fidelidade_roteiro", "ERRO", 2, str(e))


def _g_fidelidade_doc(ctx):
    from entrada import doc_google
    from gates import gate_fidelidade_doc as G
    doc_id = (ctx.projeto.get("origem") or {}).get("doc_id")
    try:
        return de_resultado("gate_fidelidade_doc", G.rodar(ctx.pj, doc_google.importar(doc_id)))
    except G.InsumoInvalido as e:
        return gate("gate_fidelidade_doc", "ERRO", 2, str(e))


def _g_fala_roteiro(ctx):
    from gates import gate_fala_roteiro as G
    try:
        return de_resultado("gate_fala_roteiro", G.rodar(ctx.pj))
    except G.InsumoInvalido as e:
        return gate("gate_fala_roteiro", "ERRO", 2, str(e))


def _g_entrada(ctx):
    from gates import gate_entrada as G
    try:
        return de_resultado("gate_entrada", G.rodar(ctx.pj))
    except G.InsumoInvalido as e:
        return gate("gate_entrada", "ERRO", 2, str(e))


def _g_look(ctx):
    from gates import gate_look as G
    try:
        return de_resultado("gate_look", G.rodar(ctx.pj))
    except G.InsumoInvalido as e:
        return gate("gate_look", "ERRO", 2, str(e))


# --- plano (sobre a timeline, sem render) -----------------------------------------------------------------

def _g_geometria(ctx):
    return _cli(ctx, "gate_geometria", [GATES / "gate_geometria.py", "antes", "--timeline", ctx.pj.timeline,
                                        "--avatar", ctx.pj.avatar_mp4, "--json"], ler_json=True)


def _aplicar_supressao(ctx, g):
    """O gate_geometria pediu para suprimir legendas (nenhuma posição cabe entre o queixo e a UI): marca na timeline,
    que o overlay lê (legendas.filtrar_suprimidas). Devolve True se mudou algo."""
    from gates import gate_geometria
    from timeline import construir as TC
    tl = TC.ler(ctx.pj.timeline)
    novo = gate_geometria.aplicar_supressao(tl, g)
    if novo == tl:
        return False
    TC.gravar(novo, ctx.pj.timeline)
    ctx.timeline(reler=True)
    return True


def _g_safezone(ctx):
    from cinema import lettering_estilos
    from gates import gate_safezone
    tl = ctx.timeline()
    return gate_safezone.rodar_antes(tl, ctx.projeto, faixas_extra=lettering_estilos.faixas_extra(tl))


def _g_lettering(ctx):
    from gates import gate_lettering
    return gate_lettering.rodar_antes(ctx.timeline(), ctx.projeto)


def _g_congelamento(ctx):
    from gates import gate_insert
    return gate_insert.rodar(plano=ctx.plano(), timeline=ctx.timeline(), projeto=ctx.projeto, video=None,
                             etapa="antes", nome="gate_congelamento")


# --- durante -----------------------------------------------------------------------------------------------

def _g_tela_vazia(ctx):
    codigo, texto = ctx.motor.saida_overlay or (None, "")
    if codigo is None:
        return gate("gate_tela_vazia", "ERRO", 2, "o overlay não foi gerado")
    if codigo != 0:
        linhas = [l for l in texto.splitlines() if any(f in l for f in BC.FALHAS_DE_TELA)]
        return gate("gate_tela_vazia", "REPROVA", 1, " ".join(linhas)[:900] or texto.strip()[-600:])
    pr = status.ler_json(ctx.motor.overlay_dir / "prancha.json")
    from overlay import tela_vazia
    return gate("gate_tela_vazia", "PASS", 0, medido={"vao_sem_texto": pr.get("vao_sem_texto")},
                limiar={"max_vao_s": tela_vazia.MAX_VAO, "max_janela_cta_s": tela_vazia.MAX_JANELA_CTA})


def _g_congelamento_build(ctx):
    """O congelamento com as durações REAIS dos blocos (a prancha do overlay), a conta do `analise_inserts`."""
    import analise_inserts as AI
    import caminhos
    pr = status.ler_json(ctx.motor.overlay_dir / "prancha.json")
    antes = caminhos.INPUTS
    caminhos.INPUTS = ctx.motor.inputs           # o analise_inserts lê o inserts.json pelo caminhos.INPUTS da hora
    try:
        linhas = AI.analisar(ctx.pj.slug, pr)
    finally:
        caminhos.INPUTS = antes
    ruins = [l for l in linhas if l["congela"] > AI.LIMITE_S]
    medido = {"inserts": [{"chave": l.get("chave"), "congela_s": round(l["congela"], 3)} for l in linhas]}
    if ruins:
        return gate("gate_congelamento_build", "REPROVA", 1,
                    "; ".join("%s congela %.2f s (limite %.2f s)" % (l.get("chave"), l["congela"], AI.LIMITE_S)
                              for l in ruins), medido=medido, limiar={"congela_max_s": AI.LIMITE_S})
    return gate("gate_congelamento_build", "PASS", 0, medido=medido, limiar={"congela_max_s": AI.LIMITE_S})


def _g_relogio(ctx):
    m = ctx.motor
    return _cli(ctx, "gate_relogio", [GATES / "gate_relogio.py", "--timeline", ctx.pj.timeline, "--footage-ritmo",
                                      m.ritmo, "--footage-timing", m.timing, "--overlay-dir", m.overlay_dir,
                                      "--footage-mp4", m.footage, "--overlay-mov", m.overlay_mov])


def _g_template(ctx):
    antes, depois = ctx.motor.assinatura_inicial, BC.assinatura_template(ctx.motor.formato)
    medido = {"antes": (antes or "")[:16], "depois": depois[:16]}
    if antes != depois:
        return gate("gate_template", "REPROVA", 1, "o template (ou um parcial dele) mudou durante o build: o overlay "
                                                   "foi gerado de outra versão; rode vam montar de novo sem editar o "
                                                   "template no meio", medido=medido)
    return gate("gate_template", "PASS", 0, medido=medido)


# --- depois (sobre o arquivo entregue) ----------------------------------------------------------------------

def ate_do_cta(html_texto, a0, accel):
    """Instante (no relógio do ENTREGUE) em que o CTA sobe, lido do overlay HTML: (data-start - a0) / accel.
    None se o elemento id="cta" não existir (o gate de contraste mede o anúncio inteiro)."""
    m = re.search(r'id="cta"[^>]*data-start="([\d.]+)"', html_texto) or \
        re.search(r'data-start="([\d.]+)"[^>]*id="cta"', html_texto)
    if not m:
        return None
    return (float(m.group(1)) - a0) / accel


def _g_gate_ad(ctx):
    m = ctx.motor
    return _cli(ctx, "gate-ad", [GATES / "gate-ad.py", "--video", m.final, "--overlay", m.overlay_mov,
                                 "--inserts", m.inserts, "--formato", m.formato])


def _g_ritmo(ctx):
    m = ctx.motor
    return _cli(ctx, "medir_ritmo", [CODIGO / "medir_ritmo.py", m.final, "--ritmo-json", m.ritmo, "--accel",
                                     ctx.accel, "--a0", ctx.a0])


def _g_colisao(ctx):
    m = ctx.motor
    return _cli(ctx, "gate-colisao-texto", [GATES / "gate-colisao-texto.py", m.final, "--overlay", m.overlay_mov,
                                            "--ritmo", m.overlay_dir / "janelas_split.json", "--accel", ctx.accel,
                                            "--a0", ctx.a0, "--intervalo", "0.5"])


def _g_contraste(ctx):
    """Todo texto na tela, CTA incluído (W5.X): o corte no CTA (`--ate`) deixava o botão e o logo sem medida."""
    m = ctx.motor
    argv = [GATES / "gate-contraste-legenda.py", m.final, "--overlay", m.overlay_mov, "--accel", ctx.accel,
            "--a0", ctx.a0, "--json", _log_dos_gates(ctx) / "gate-contraste-legenda.json"]
    return _cli(ctx, "gate-contraste-legenda", argv)


def _g_auditar(ctx):
    from audio import mix_final
    return _cli(ctx, "auditar_ad", [GATES / "auditar_ad.py", ctx.motor.final, "--projeto", ctx.pj.slug, "--estado",
                                    ctx.pj.estado, "--voz", mix_final.caminho_voz_ref(ctx.pj)])


def _g_hook_visual(ctx):
    from gates import gate_hook_visual
    return gate_hook_visual.rodar(str(ctx.motor.final), ctx.timeline(), overlay=str(ctx.motor.overlay_mov),
                                  projeto=ctx.projeto)


def _g_camera(ctx):
    from gates import gate_camera
    # o avatar cru (W7.Z): a escala do plano sai do registro contra ele, sem o balanço da pessoa que fala
    return gate_camera.rodar(str(ctx.motor.final), ctx.timeline(), ctx.projeto, overlay=str(ctx.motor.overlay_mov),
                             avatar=str(ctx.pj.avatar_mp4))


def _g_cor(ctx):
    """Com a caixa do rosto medida no entregue (W5.X, pendência c): sem ela o R/G do C5 nunca era medido."""
    from gates import gate_cor
    tl = ctx.timeline()
    rosto = gate_cor.caixa_rosto_entregue(str(ctx.motor.final), tl)
    return gate_cor.rodar(str(ctx.motor.final), projeto=ctx.projeto, planos=gate_cor.planos_da_timeline(tl, rosto))


def _g_mix(ctx):
    from gates import gate_mix
    try:
        return de_resultado("gate_mix", gate_mix.rodar(ctx.pj, final=ctx.motor.final))
    except gate_mix.InsumoInvalido as e:
        return gate("gate_mix", "ERRO", 2, str(e))


def _g_sfx(ctx):
    from cinema import sfx_plano
    from gates import gate_sfx
    try:
        return de_resultado("gate_sfx", gate_sfx.rodar(ctx.pj, biblioteca=sfx_plano.pasta_padrao()))
    except gate_sfx.InsumoInvalido as e:
        return gate("gate_sfx", "ERRO", 2, str(e))


def _g_insert(ctx):
    from gates import gate_insert
    return gate_insert.rodar(plano=ctx.plano(), timeline=ctx.timeline(), projeto=ctx.projeto,
                             video=str(ctx.motor.final), etapa="depois", nome="gate_insert")


def _g_lettering_depois(ctx):
    from gates import gate_lettering
    return gate_lettering.rodar_depois(str(ctx.motor.overlay_mov), ctx.timeline(), ctx.projeto)


def _g_safezone_depois(ctx):
    from gates import gate_safezone
    return gate_safezone.rodar_depois(str(ctx.motor.overlay_mov), ctx.timeline(), ctx.projeto)


def _g_geometria_depois(ctx):
    m = ctx.motor
    return _cli(ctx, "gate_geometria_depois", [GATES / "gate_geometria.py", "depois", "--timeline", ctx.pj.timeline,
                                               "--video", m.final, "--overlay", m.overlay_mov, "--avatar",
                                               ctx.pj.avatar_mp4, "--json"], ler_json=True)


def _g_texto_atras(ctx):
    """C13 é opcional (`estilo.texto_atras` no projeto.json) e precisa do `bash setup.sh --cinema-plus`."""
    if not (ctx.projeto.get("estilo") or {}).get("texto_atras"):
        return gate("gate_texto_atras", "PULADO", 0, "opcional (C13): o projeto não liga o texto atrás da pessoa")
    try:
        from gates import gate_texto_atras  # noqa: F401
    except ImportError:
        return gate("gate_texto_atras", "ERRO", 2, "o projeto pede texto atrás da pessoa, mas a capacidade não está "
                                                   "instalada nesta versão: rode bash setup.sh --cinema-plus")
    return gate("gate_texto_atras", "ERRO", 2, "o texto atrás da pessoa ainda não é composto pelo build")


GATES_PADRAO = {
    "gate_aprovacao": _g_aprovacao, "gate_fidelidade_roteiro": _g_fidelidade_roteiro,
    "gate_fidelidade_doc": _g_fidelidade_doc, "gate_fala_roteiro": _g_fala_roteiro, "gate_entrada": _g_entrada,
    "gate_look": _g_look, "gate_geometria": _g_geometria, "gate_safezone": _g_safezone,
    "gate_lettering": _g_lettering, "gate_congelamento": _g_congelamento, "gate_tela_vazia": _g_tela_vazia,
    "gate_congelamento_build": _g_congelamento_build, "gate_relogio": _g_relogio, "gate_template": _g_template,
    "gate-ad": _g_gate_ad, "medir_ritmo": _g_ritmo, "gate-colisao-texto": _g_colisao,
    "gate-contraste-legenda": _g_contraste, "auditar_ad": _g_auditar, "gate_hook_visual": _g_hook_visual,
    "gate_camera": _g_camera, "gate_cor": _g_cor, "gate_mix": _g_mix, "gate_sfx": _g_sfx, "gate_insert": _g_insert,
    "gate_lettering_depois": _g_lettering_depois, "gate_safezone_depois": _g_safezone_depois,
    "gate_geometria_depois": _g_geometria_depois, "gate_texto_atras": _g_texto_atras,
}


# --- o montar ------------------------------------------------------------------------------------------------

def _limpar_entrega_anterior(pj):
    """Final, prévia, laudo e manifesto de um build anterior saem antes de começar: nada velho amarra o build novo.
    A nota do auditor fica (é dele); como ela cita o sha256 do final antigo, deixa de valer sozinha."""
    from entrega import pacote
    for p in (pj.final_9x16, pj.final_whatsapp, pj.laudo, pacote.manifesto(pj)):
        if p.exists():
            p.unlink()


def _gerar_folhas(final, pasta):
    try:
        from folhas_contato import gerar_folhas
        return gerar_folhas(final, pasta)
    except Exception:                 # a folha é prova visual, nunca muda o veredito
        return None


def _registrar_gate(pj, g):
    estado = {"PASS": "ok", "PULADO": "ok", "REPROVA": "falhou"}.get(g["resultado"], "bloqueado")
    status.registrar(pj, g["nome"], estado, motivo=g.get("motivo") if g["resultado"] != "PASS" else None)


def montar(pj, *, motor=None, gates=None, previa=None, medir=None, folhas=None, agora=None, paralelo=None,
           saida=print):
    """Monta o anúncio do projeto `pj` com os gates na ordem. Devolve 0, 1 ou 2 (ver o docstring do módulo).

    Injetáveis (os testes simulam o render): `motor` (padrão `build_composite.Motor(pj)`), `gates` ({nome: f(ctx)}
    que substituem os padrão), `previa` (f(final, destino)), `medir` (f(final) -> medidas do laudo), `folhas`."""
    t0 = time.time()
    try:
        projeto = modelo.carregar(pj.projeto_json)
    except (FileNotFoundError, modelo.ContratoInvalido) as e:
        saida("vam montar: projeto inválido: %s" % e, file=sys.stderr)
        return 2
    paralelo = int(paralelo or os.environ.get("VAM_GATES_PARALELO") or PARALELO_MAX)
    paralelo = max(1, min(paralelo, PARALELO_MAX))
    _limpar_entrega_anterior(pj)
    status.registrar(pj, ETAPA, "em_andamento")
    motor = motor if motor is not None else BC.Motor(pj, projeto)
    funcoes = dict(GATES_PADRAO)
    funcoes.update(gates or {})
    ctx = Contexto(pj, projeto, motor)
    nomes = ordem(projeto)
    resultados = []

    def rodar(nome):
        g = _executar(funcoes[nome], ctx, nome)
        resultados.append(g)
        _registrar_gate(pj, g)
        saida("  %-24s %-7s %s" % (nome, g["resultado"], (g.get("motivo") or "")[:150]))
        return g

    def parar(g):
        motivo = "%s: %s" % (g["nome"], g.get("motivo", g["resultado"]))
        status.registrar(pj, ETAPA, "falhou" if g["resultado"] == "REPROVA" else "bloqueado", motivo=motivo[:900],
                         detalhes={"gates": len(resultados)})
        saida("\n>>> %s %s: %s" % (pj.slug, "REPROVADO" if g["resultado"] == "REPROVA" else "BLOQUEADO", motivo))
        return 1 if g["resultado"] == "REPROVA" else 2

    def passo(nome, f):
        saida("[motor] %s" % nome)
        try:
            return f()
        except ErroDoMotor as e:
            if e.etapa == nome:
                raise
            raise ErroDoMotor(nome, str(e))
        except (OSError, ValueError, subprocess.SubprocessError) as e:     # ferramenta ou arquivo: o passo não rodou
            raise ErroDoMotor(nome, "%s: %s" % (type(e).__name__, e))

    marcas = {}
    try:
        for nome in [n for n in nomes if n in ANTES]:
            g = rodar(nome)
            if falhou(g):
                return parar(g)
        marcas["inicio_build"] = time.time()
        passo("preparar", motor.preparar)
        for nome in PLANO:
            g = rodar(nome)
            if nome == "gate_geometria" and g["resultado"] == "REPROVA" and \
                    (g.get("medido") or {}).get("acao") == "suprimir_legenda" and _aplicar_supressao(ctx, g):
                resultados.pop()
                g = rodar(nome)
            if falhou(g):
                return parar(g)
        # a footage ANTES do overlay: o overlay decide a tinta invertida medindo o fundo NA footage, no relógio da
        # timeline (sem ela, ele cai no arquivo-fonte do insert e inverte a legenda onde a tela é escura)
        passo("footage", motor.montar_footage)
        passo("overlay", motor.gerar_overlay)
        for nome in ("gate_tela_vazia", "gate_congelamento_build"):
            g = rodar(nome)
            if falhou(g):
                return parar(g)
        passo("render_overlay", motor.renderizar_overlay)
        g = rodar("gate_relogio")
        if falhou(g):
            return parar(g)
        final = passo("compor", motor.compor)
        g = rodar("gate_template")
        if falhou(g):
            return parar(g)
        marcas["fim_build"] = time.time()
        passo("previa", lambda: (previa or whatsapp_versao.gerar)(final, pj.final_whatsapp))
        saida("[prévia] %s (antes dos gates de saída)" % pj.final_whatsapp)
        (folhas or _gerar_folhas)(final, pj.folhas_dir)
    except ErroDoMotor as e:
        motivo = "motor %s" % e
        status.registrar(pj, ETAPA, "bloqueado", motivo=motivo[:900])
        saida("\n>>> %s BLOQUEADO: %s" % (pj.slug, motivo), file=sys.stderr)
        return 2

    depois = [n for n in nomes if n in DEPOIS]
    with concurrent.futures.ThreadPoolExecutor(max_workers=paralelo) as ex:
        futuros = {n: ex.submit(_executar, funcoes[n], ctx, n) for n in depois}
        for n in depois:
            g = futuros[n].result()
            resultados.append(g)
            _registrar_gate(pj, g)
            saida("  %-24s %-7s %s" % (n, g["resultado"], (g.get("motivo") or "")[:150]))
    tempos = {"build_s": marcas.get("fim_build", time.time()) - marcas.get("inicio_build", t0),
              "render_s": time.time() - t0}
    try:
        d = LD.montar(pj, resultados, final=final, previa=pj.final_whatsapp, agora=agora,
                      medidas=(medir or LD.medir)(final), tempos=tempos,
                      amb=LD.ambiente() if medir is None else None, projeto=projeto)
        LD.gravar(pj, d)
    except (LD.LaudoInvalido, OSError, ValueError) as e:
        status.registrar(pj, ETAPA, "bloqueado", motivo="o laudo não pôde ser escrito: %s" % e)
        saida("\n>>> laudo não escrito: %s" % e, file=sys.stderr)
        return 2
    if d["veredito"] == "PASS":
        status.registrar(pj, ETAPA, "ok", detalhes={"laudo": "PASS", "build_s": round(tempos["build_s"], 1)})
        saida("\n>>> %s: laudo PASS (%s). Próximo: a auditoria (vam auditar %s)" % (pj.slug, pj.laudo, pj.slug))
        return 0
    ruins = [g for g in d["gates"] if falhou(g)]
    motivo = "; ".join("%s: %s" % (g["nome"], g.get("motivo", "")) for g in ruins)
    status.registrar(pj, ETAPA, "falhou", motivo=motivo[:900], detalhes={"laudo": "REPROVA"})
    saida("\n>>> %s: laudo REPROVA: %s" % (pj.slug, motivo[:600]))
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="produzir_ad", description="Monta o anúncio do projeto com os gates na ordem.")
    ap.add_argument("slug")
    ap.add_argument("--estado", help="pasta _local (padrão: a do repo)")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0)
    try:
        pj = pastas.projeto(a.slug, a.estado)
    except ValueError as e:
        print("vam montar: %s" % e, file=sys.stderr)
        return 2
    if not pj.projeto_json.is_file():
        print("vam montar: o projeto %r não existe em %s: crie com vam novo %s" % (pj.slug, pj.raiz, pj.slug),
              file=sys.stderr)
        return 2
    return montar(pj)


if __name__ == "__main__":
    sys.exit(main())
