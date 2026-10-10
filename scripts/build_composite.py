#!/usr/bin/env python3
"""O build de UM anúncio do aluno: footage (avatar + inserts, sem texto) + camada de texto (overlay HTML com alfa),
compostas no relógio único da timeline.json, aceleradas, normalizadas e mixadas.

NÃO É UM COMANDO. Quem roda o build é o `vam montar <slug>` (`produzir_ad.montar`), que chama os passos abaixo um a
um e roda os gates da seção 4 do plano entre eles. Chamado direto, este arquivo sai com 2 e aponta o `vam montar`
(o guardrail de 05/08/2026: o build sem gate entregou dez anúncios reprovados de uma vez). O passo que produz o
arquivo final (`compor`) e o que abre o build (`preparar`) recusam rodar sem a aprovação do plano vigente.

## Os passos (métodos de `Motor`, na ordem)

  preparar             aprovação vigente; arquivos do motor (para_motor); timeline.json com o plano de SFX
  gerar_overlay        overlay/index.html pelo gen_ad_v2 (com a timeline) e o index_overlay.html transparente
  renderizar_overlay   o MOV com alfa (HyperFrames, 1 worker, captura lenta); cache pelo sha do HTML
  montar_footage       a footage a 1x pelo produzir_roteiro (com a mesma timeline)
  compor               composição (overlay deslocado de -a0), aceleração do projeto, loudness pela régua da entrega
                       (`gravado.montar.normalizar_para_entrega`), mix (efeitos do plano de SFX da timeline, trilha do
                       projeto com ducking pelas pausas reais, limiter), timestamp limpo -> entrega/final_9x16.mp4

## Onde mora cada coisa (tudo dentro de `_local/projetos/<slug>/`)

  render/motor/inputs/<slug>_leva.txt e <slug>_inserts.json   o formato que o motor lê (entrada.para_motor)
  render/motor/output/footage_1x.mp4, footage_1x_ritmo.json, timing.json
  render/config_overlay.json   o config do gen_ad_v2, com `timeline`, `look_plano` (do looks.json) e speed 1,0
  render/alinhamento.json, render/timeline.json   o relógio único (timeline.alinhar e timeline.construir)
  render/overlay/              o HTML do overlay, a prancha.json e as janelas de split
  render/overlay_render/       o projeto do HyperFrames e o MOV com alfa (renders/*.mov)
  render/voz_pre_mix.wav, render/mix_final.json                 o que o gate_mix compara
  entrega/final_9x16.mp4       o arquivo final (1x1 é beta: entrega/final_1x1.mp4)

Os dois motores (gen_ad_v2 e produzir_roteiro) rodam em subprocesso com VAM_DADOS apontando para render/motor, então
nada de um projeto encosta em outro (o `output/timing.json` fixo que dois builds dividiam, defeito 11 do plano). O logo
é o da marca do aluno (`_local/marca/logo.png`, via VAM_ASSETS). Não há mais dicionário de looks no código: o look,
a aceleração e a trilha vêm do projeto.json e do looks.json do aluno.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import cache_overlay  # noqa: E402
from caminhos import CODIGO, RAIZ, TEMPLATES  # noqa: E402

# Aceleração PADRÃO do arquivo entregue com avatar (o projeto.json manda: 1,35 com avatar e 1,2 com take real).
# Histórico (04/08/2026): 1,2 -> 1,3 -> 1,56 -> 1,25 -> 1,35. A timeline.construir lê os dois números daqui.
ACCEL = 1.35
# CAUDA CONGELADA no fim do entregue, aplicada DEPOIS da aceleração: a duração do entregue é footage/ACCEL +
# TAIL_FINAL (19/08/2026: dividir a duração total pela da footage dava 1,3421 e parecia que a aceleração estava
# errada; para converter INSTANTE use a aceleração, a cauda só afeta a duração total).
TAIL_FINAL = 0.45
# 1x1 (beta): janela alta recortada da footage 9x16 e encolhida sobre fundo desfocado (calibrada em 20/07).
CROP_Y_1X1 = 250
CROP_H_1X1 = 1500
TEMPLATE = {"9x16": "reel-editorial", "1x1": "reel-editorial-1x1"}
FALHAS_DE_TELA = ("TELA VAZIA", "JANELA DE CTA")      # o gen_ad_v2 para com essas frases: é o gate de tela vazia


class ErroDoMotor(RuntimeError):
    """Um passo do build não rodou (ferramenta, insumo, aprovação). `etapa` diz qual."""

    def __init__(self, etapa, motivo=None):
        if motivo is None:                  # ErroDoMotor("mensagem"): a etapa é a do passo que o montar rodava
            etapa, motivo = "motor", etapa
        self.etapa = etapa
        super().__init__("%s: %s" % (etapa, motivo))


def _rodar(cmd, etapa, **kw):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)
    if r.returncode != 0:
        quem = " ".join(Path(str(c)).name for c in cmd[:2])
        raise ErroDoMotor(etapa, "%s saiu com %d: %s" % (quem, r.returncode,
                                                         ((r.stderr or "") + (r.stdout or "")).strip()[-1200:]))
    return r


def vdur(f):
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(f)], capture_output=True, text=True).stdout.strip()
    return float(o) if o else 0.0


def strip_overlay(idx_html):
    """Remove avatar, b-rolls, grade e vinheta; fundo transparente. Mantém hook, legendas, letterings, CTA e logo.

    O WIPE DE GRADE FICA VIVO (18/08/2026): as células só aparecem durante a animação (o GSAP arma scale:0 no
    repouso), então deixá-las na cor do tema não cobre nada fora do wipe."""
    idx_html = Path(idx_html)
    src = idx_html.read_text(encoding="utf-8")
    kill = ['id="a-roll"', 'id="a-roll-audio"', 'id="grade"', 'id="vignette"',
            'class="broll-scrim', 'class="broll-tag', 'class="broll-vid']
    html = "\n".join(ln for ln in src.split("\n") if not any(s in ln for s in kill))
    for alt in ("1920", "1080"):
        html = html.replace("html, body { width:1080px; height:%spx; overflow:hidden; background:#05060a; }" % alt,
                            "html, body { width:1080px; height:%spx; overflow:hidden; background:transparent; }" % alt)
    dst = idx_html.parent / "index_overlay.html"
    dst.write_text(html, encoding="utf-8")
    return dst


def template(formato):
    return TEMPLATES / TEMPLATE.get(formato, TEMPLATE["9x16"]) / "index.html"


def assinatura_template(formato):
    """sha256 do template E dos parciais que ele inclui (`overlay.html_injecao.assinatura_template`): o gate de
    "template mudou no meio do build" tem que ver a mudança num parcial, não só no index.html (26/08/2026: o overlay
    saiu da versão anterior do template e o log disse PRONTO)."""
    from overlay import html_injecao
    t = template(formato)
    return html_injecao.assinatura_template(t) if t.is_file() else "ausente"


def hyperframes():
    """O binário do HyperFrames do repo (node_modules/.bin, instalado pelo setup.sh na versão pinada)."""
    return RAIZ / "node_modules" / ".bin" / "hyperframes"


class Motor(object):
    """O build de um projeto. Só monta caminhos no __init__; cada passo é um método (ver o docstring do módulo)."""

    def __init__(self, pj, projeto=None):
        from projeto import modelo
        self.pj = pj
        self.projeto = projeto if projeto is not None else modelo.carregar(pj.projeto_json)
        self.slug = pj.slug
        self.formato = self.projeto.get("formato", "9x16")
        self.accel = float(self.projeto.get("aceleracao", ACCEL))
        r = pj.render_dir
        self.dados = r / "motor"
        self.inputs = self.dados / "inputs"
        self.output = self.dados / "output"
        self.leva = self.inputs / ("%s_leva.txt" % self.slug)
        self.inserts = self.inputs / ("%s_inserts.json" % self.slug)
        self.config = r / "config_overlay.json"
        self.overlay_dir = r / "overlay"
        self.overlay_render_dir = r / "overlay_render"
        # o nome que o overlay procura para medir o fundo claro NA footage (overlay.fundo_claro): outro nome e ele cai
        # no arquivo-fonte do insert, que não é o que a tela mostra (contraste 1,1:1 no primeiro e2e)
        nome = "%s_%s_footage_1x" % (self.slug, self.projeto.get("look") or "sem-look")
        self.footage = self.output / (nome + ".mp4")
        self.ritmo = self.output / (nome + "_ritmo.json")
        self.timing = self.output / "timing.json"
        self.composite = r / "composite_1x.mp4"
        self.acelerado = r / "acelerado.mp4"
        self.relatorio_mix = r / "mix_final.json"
        self.final = pj.final_9x16 if self.formato == "9x16" else pj.entrega_dir / "final_1x1.mp4"
        self.overlay_mov = None
        self.saida_overlay = None            # (código, texto) do gen_ad_v2: é o que o gate de tela vazia lê
        self.assinatura_inicial = None

    # --- ambiente dos dois motores -------------------------------------------------------------------------
    def env_motor(self):
        from projeto import pastas
        env = dict(os.environ)
        env.update({"VAM_DADOS": str(self.dados), "VAM_ESTADO": str(self.pj.estado),
                    "VAM_ASSETS": str(pastas.logo(self.pj.estado).parent)})
        env.pop("VAM_V1_HOME", None)
        env.pop("VAM_INPUTS", None)
        env.pop("VAM_OUTPUT", None)
        return env

    def env_footage(self):
        env = self.env_motor()
        env.update({"VAM_AVATAR": str(self.pj.avatar_mp4), "VAM_ROTEIRO": str(self.leva),
                    "VAM_INSERTS_JSON": str(self.inserts), "VAM_OUT": self.footage.name,
                    "VAM_TIMELINE": str(self.pj.timeline), "VAM_BAKE_LETTERING": "0", "CAP": "0"})
        return env

    # --- preparar -------------------------------------------------------------------------------------------
    def exigir_aprovacao(self, etapa):
        from plano import aprovacao
        sit = aprovacao.verificar(self.pj)
        if not sit.vigente:
            raise ErroDoMotor(etapa, "sem aprovação vigente do plano (%s). O build só roda pelo vam montar, depois "
                                     "do ok do aluno ao plano" % sit.motivo)

    def look_plano(self):
        from projeto import looks
        try:
            look = looks.obter(self.projeto.get("look"), self.pj.estado) if self.projeto.get("look") else None
        except looks.LookInvalido:
            look = None
        return (look or {}).get("plano")

    def escrever_arquivos_do_motor(self):
        """A leva, o inserts.json e o config do overlay, a partir do roteiro.md e do projeto.json (entrada.para_motor).
        O inserts.json tem que ser byte a byte o que o aluno aprovou (render/inserts.json)."""
        from entrada import para_motor, roteiro_md
        try:
            motor = para_motor.gerar(roteiro_md.exigir(roteiro_md.ler_arquivo(self.pj.roteiro)), self.pj.projeto_json,
                                     avatar=self.pj.avatar_mp4, out_dir=self.overlay_dir,
                                     inserts_dir=self.pj.inserts_dir, ad=self.slug)
        except (para_motor.ErroParaMotor, roteiro_md.RoteiroInvalido, OSError) as e:
            raise ErroDoMotor("preparar", "o roteiro não vira arquivos do motor: %s" % e)
        inserts = motor.inserts_json().encode("utf-8")
        aprovado = self.pj.render_dir / "inserts.json"
        if aprovado.is_file() and aprovado.read_bytes() != inserts:
            raise ErroDoMotor("preparar", "o mapa de inserts mudou desde a aprovação (render/inserts.json): rode vam "
                                          "plano e vam aprovar de novo")
        cfg = dict(motor.config)
        cfg.update({"out_dir": str(self.overlay_dir), "speed": 1.0, "timeline": str(self.pj.timeline)})
        leitura = roteiro_md.ler_arquivo(self.pj.roteiro)
        cfg = self._cta_como_botao(cfg, leitura)
        cfg["letterings"] = self._com_estilo(cfg.get("letterings", []), leitura)
        plano = self.look_plano()
        if plano:
            cfg["look_plano"] = plano
        roteiro_md.escrever_atomico(self.leva, motor.leva)
        roteiro_md.escrever_atomico(self.inserts, inserts)
        roteiro_md.escrever_atomico(self.config, json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
        return cfg

    @staticmethod
    def _cta_como_botao(cfg, leitura):
        """A KEY do bloco cta é o texto do BOTÃO (contratos/roteiro-convencao.md) e o LEAD é o lead dele.

        Achado do e2e (W5.A): o motor desenhava a KEY do cta como um lettering na faixa do peito, EM CIMA da pílula e
        do logo do CTA, que sobem no mesmo instante: o logo carimbado sobre a KEY, "toque em" e "toca em" juntos, e o
        dim do lettering somado ao scrim do CTA virando tinta opaca (a seta sumia da medida, a tinta ia a x 972). Agora
        o lettering do cta sai da lista e o texto dele vai para o botão; o logo é o do CTA."""
        ultimo = leitura.blocos[-1] if leitura.blocos else {}
        if ultimo.get("tipo") != "cta" or not ultimo.get("key") or not cfg.get("letterings"):
            return cfg
        cfg = dict(cfg)
        cta = cfg["letterings"][-1]
        cfg["letterings"] = cfg["letterings"][:-1]
        cfg["cta_label"] = cta["key"]
        if cta.get("lead"):
            cfg["cta_lead"] = cta["lead"]
        return cfg

    def _com_estilo(self, letterings, leitura):
        """`estilo.lettering` do projeto.json nas KEYs do meio (antes ele nascia inerte: ninguém o passava ao overlay)."""
        estilo = (self.projeto.get("estilo") or {}).get("lettering")
        if not estilo:
            return letterings
        saida = [dict(l) for l in letterings]          # a KEY do cta já saiu da lista (é o botão)
        for l in saida:
            l["estilo"] = estilo
        return saida

    def construir_timeline(self):
        """UMA transcrição, UM alinhamento e a timeline.json (com o plano de SFX), que footage e overlay leem."""
        from cinema import musica
        from cinema import sfx_plano as SP
        from contratos.validar import validar
        from footage import blocos as BL
        from projeto import glossario
        from timeline import alinhar as AL
        from timeline import construir as TC
        cfg = json.loads(self.config.read_text(encoding="utf-8"))
        inserts_map = json.loads(self.inserts.read_text(encoding="utf-8"))
        blocks = BL.ler_blocos(str(self.leva))
        try:
            al = AL.alinhar(self.pj.avatar_mp4, BL.palavras_da_narracao(blocks), cache_dir=self.pj.render_dir / "cache_asr",
                            raiz=self.pj.raiz, glossario=glossario.carregar(self.pj.estado))
            AL.gravar(al, self.pj.alinhamento)
            trilha, motivo = musica.resolver_trilha(self.projeto, self.pj.estado)
            ducking = musica.ducking_desligado(motivo) if trilha is None else musica.ducking_para_timeline([])
            tl = TC.construir(blocks, al, inserts_map=inserts_map, cfg=cfg, caminho_alinhamento=self.pj.alinhamento,
                              raiz=self.pj.raiz, aceleracao=self.accel, cauda_s=TAIL_FINAL, formato=self.formato,
                              projeto=self.slug, ducking=ducking)
        except (AL.ErroAlinhamento, TC.ErroTimeline, musica.TrilhaInvalida) as e:
            raise ErroDoMotor("timeline", str(e))
        tl = TC.com_camera(tl)                      # W5.X: o punch da KEY chega à footage
        tl["sfx"] = SP.plano_de_sfx(tl)
        erros = validar("timeline", tl)
        if erros:
            raise ErroDoMotor("timeline", "a timeline com o plano de SFX não passa no contrato: "
                                          + "; ".join(str(e) for e in erros[:4]))
        TC.gravar(tl, self.pj.timeline)
        return tl

    def preparar(self):
        self.exigir_aprovacao("preparar")
        self.assinatura_inicial = assinatura_template(self.formato)
        self.escrever_arquivos_do_motor()
        return self.construir_timeline()

    # --- overlay --------------------------------------------------------------------------------------------
    def gerar_overlay(self):
        """overlay/index.html (gen_ad_v2 com a timeline) e o index_overlay.html transparente. A parada do gen_ad_v2 por
        tela vazia ou janela de CTA longa NÃO é erro de ferramenta: fica em `saida_overlay` para o gate_tela_vazia."""
        self.overlay_dir.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([sys.executable, str(CODIGO / "gen_ad_v2.py"), str(self.config)], capture_output=True,
                           text=True, env=self.env_motor(), cwd=str(CODIGO))
        texto = (r.stdout or "") + (r.stderr or "")
        self.saida_overlay = (r.returncode, texto)
        if r.returncode != 0:
            if any(f in texto for f in FALHAS_DE_TELA):
                return None
            raise ErroDoMotor("overlay", "o gen_ad_v2 saiu com %d: %s" % (r.returncode, texto.strip()[-1200:]))
        return strip_overlay(self.overlay_dir / "index.html")

    def projeto_do_overlay(self):
        """overlay_render/ com o index.html transparente, fontes, logo e meta.json: o projeto que o HyperFrames lê
        (render e snapshot da prancha). Recriado do zero; os renders anteriores saem junto."""
        only = self.overlay_render_dir
        if only.exists():
            shutil.rmtree(only)
        only.mkdir(parents=True)
        (only / "index.html").write_text((self.overlay_dir / "index_overlay.html").read_text(encoding="utf-8"),
                                         encoding="utf-8")
        os.symlink(self.overlay_dir / "fonts", only / "fonts")
        shutil.copy(self.overlay_dir / "logo.png", only / "logo.png")
        if (self.overlay_dir / "meta.json").exists():
            shutil.copy(self.overlay_dir / "meta.json", only / "meta.json")
        return only

    def renderizar_overlay(self):
        """O MOV com alfa. Cache (31/08/2026): o render só depende do index_overlay.html; HTML igual byte a byte,
        MOV igual. `--workers 1` (a captura paralela misturava dois instantes num quadro) e captura lenta (a rápida
        não via o `visibility` que o GSAP liga: 25% do anúncio sem legenda)."""
        html = self.overlay_dir / "index_overlay.html"
        sig = self.overlay_render_dir / ".assinatura_overlay"
        if os.environ.get("CACHE_OVERLAY") != "0" and (self.overlay_render_dir / "renders").is_dir():
            movs = sorted((self.overlay_render_dir / "renders").glob("*.mov"), key=lambda p: p.stat().st_mtime)
            if movs and cache_overlay.reaproveitavel(html, movs[-1], sig):
                self.overlay_mov = movs[-1]
                return self.overlay_mov
        hf = hyperframes()
        if not hf.exists():
            raise ErroDoMotor("render_overlay", "o HyperFrames não está instalado em %s: rode bash setup.sh" % hf)
        only = self.projeto_do_overlay()
        _rodar([hf, "render", ".", "--format", "mov", "-f", "30", "--workers", "1",
                "--experimental-fast-capture=false"], "render_overlay", cwd=str(only))
        movs = sorted((only / "renders").glob("*.mov"), key=lambda p: p.stat().st_mtime)
        if not movs:
            raise ErroDoMotor("render_overlay", "o HyperFrames não gravou o MOV em %s" % (only / "renders"))
        sig.write_text(cache_overlay.assinatura([html]))
        self.overlay_mov = movs[-1]
        return self.overlay_mov

    # --- footage --------------------------------------------------------------------------------------------
    def montar_footage(self):
        self.output.mkdir(parents=True, exist_ok=True)
        _rodar([sys.executable, CODIGO / "produzir_roteiro.py"], "footage", env=self.env_footage(), cwd=str(self.dados))
        if not self.footage.is_file():
            raise ErroDoMotor("footage", "a footage não foi gravada em %s" % self.footage)
        return self.footage

    def a0(self):
        return float(json.loads(self.timing.read_text(encoding="utf-8"))["a0"])

    # --- compor, acelerar, loudness, mix --------------------------------------------------------------------
    def compor(self):
        """Do composite a 1x ao arquivo final. Recusa sem aprovação vigente (é o passo que produz o que se entrega)."""
        from gravado.montar import normalizar_para_entrega
        from audio import loudness
        self.exigir_aprovacao("compor")
        if self.overlay_mov is None:
            self.renderizar_overlay()
        foot, a0 = self.footage, self.a0()
        if self.formato == "1x1":
            foot = self._reenquadrar_1x1(foot)
        _rodar(["ffmpeg", "-y", "-v", "error", "-i", foot, "-i", self.overlay_mov, "-filter_complex",
                "[1:v]setpts=PTS-%s/TB[ov];[0:v][ov]overlay=0:0:eof_action=pass:shortest=1[v]" % a0,
                "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-crf", "16", "-preset", "medium",
                "-pix_fmt", "yuv420p", "-c:a", "copy", self.composite], "compor")
        _rodar(["ffmpeg", "-y", "-v", "error", "-i", self.composite, "-filter_complex",
                "[0:v]setpts=PTS/%s,tpad=stop_mode=clone:stop_duration=%s[v];[0:a]atempo=%s,apad=pad_dur=%s[a]"
                % (self.accel, TAIL_FINAL, self.accel, TAIL_FINAL),
                "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                "-c:a", "aac", "-ar", "48000", "-b:a", "192k", "-movflags", "+faststart", self.acelerado], "acelerar")
        # LOUDNESS DA VOZ ANTES DO MIX (27/08/2026): na ordem inversa o loudnorm "come" a calibragem dos efeitos. A
        # régua é a da entrega do gravado (W5.D): o AAC do segundo passe estoura o true peak em até 0,1 dB, e ela
        # confere o arquivo gravado e repete o passe com folga.
        voz = self.pj.render_dir / "voz_norm.mp4"
        try:
            normalizar_para_entrega(self.acelerado, voz)
        except loudness.ErroDeLoudness as e:
            raise ErroDoMotor("loudness", str(e))
        mixado = self.pj.render_dir / "mixado.mp4"
        self.mixar(voz, mixado)
        self.final.parent.mkdir(parents=True, exist_ok=True)
        # TIMESTAMP LIMPO NO FIM (31/08/2026): remux em série deixava o 1º quadro em pts negativo e o player do
        # WhatsApp desincronizava. Um remux final zera a linha do tempo, e o arquivo com pts negativo é recusado.
        parcial = self.final.with_name(self.final.stem + ".parcial.mp4")
        _rodar(["ffmpeg", "-y", "-v", "error", "-fflags", "+genpts", "-i", mixado, "-c", "copy",
                "-avoid_negative_ts", "make_zero", "-muxpreload", "0", "-muxdelay", "0", "-movflags", "+faststart",
                parcial], "timestamp")
        pts = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
                              "-of", "csv=p=0", "-read_intervals", "%+0.2", str(parcial)],
                             capture_output=True, text=True).stdout.split()
        if pts and min(float(x) for x in pts if x) < -0.001:
            raise ErroDoMotor("timestamp", "timestamp de vídeo negativo depois do remux (%s): o arquivo "
                                           "desincroniza no player" % pts[:3])
        parcial.replace(self.final)
        return self.final

    def _reenquadrar_1x1(self, foot):
        sq = self.output / "footage_1x_sq.mp4"
        fg_w = round(1080 * 1080 / CROP_H_1X1)
        _rodar(["ffmpeg", "-y", "-v", "error", "-i", foot, "-filter_complex",
                "[0:v]crop=1080:%d:0:%d,scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080,"
                "gblur=sigma=25[bg];[0:v]crop=1080:%d:0:%d,scale=%d:1080[fg];[bg][fg]overlay=(1080-%d)/2:0[v]"
                % (CROP_H_1X1, CROP_Y_1X1, CROP_H_1X1, CROP_Y_1X1, fg_w, fg_w),
                "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-crf", "16", "-preset", "medium",
                "-pix_fmt", "yuv420p", "-c:a", "copy", sq], "reenquadrar_1x1")
        return sq

    def mixar(self, entrada, saida):
        """Efeitos (o plano de SFX da timeline), trilha do projeto com ducking pelas pausas reais e limiter, num AAC.
        Depois do mix, a automação de cama MEDIDA vai para a timeline (o gate_mix compara as duas)."""
        from cinema import musica
        from projeto import status
        from timeline import construir as TC
        tl = TC.ler(self.pj.timeline)
        try:
            trilha, motivo = musica.resolver_trilha(self.projeto, self.pj.estado)
        except musica.TrilhaInvalida as e:
            raise ErroDoMotor("mix", str(e))
        _, rel = mixar_audio(entrada, saida, sfx=tl["sfx"], relogio=tl["relogio"], trilha=trilha,
                             motivo_sem_trilha=motivo, workdir=self.pj.render_dir)
        tl["ducking"] = rel["ducking"]
        TC.gravar(tl, self.pj.timeline)
        status.escrever_json_atomico(self.relatorio_mix, rel)
        return saida


def mixar_audio(entrada, saida, *, sfx, relogio, trilha=None, motivo_sem_trilha=None, workdir, biblioteca=None):
    """Efeitos, música e limiter num grafo e num AAC (audio.mix_final). Devolve (saida, relatório).

    `sfx` e `relogio` são os da timeline (o plano de SFX tem tempos no relógio da footage; o mixer recebe o instante
    do arquivo entregue). A voz pré-mix vai para workdir/voz_pre_mix.wav, onde o gate_mix a lê."""
    from audio import mix_final as MX
    from cinema import sfx_plano as SP
    try:
        eventos = SP.eventos_para_mix(sfx, relogio, biblioteca or SP.biblioteca())
        rel = MX.mixar(entrada, saida, efeitos=eventos, trilha=trilha,
                       motivo_sem_trilha=motivo_sem_trilha or "o projeto não tem trilha",
                       voz_ref=Path(workdir) / "voz_pre_mix.wav")
    except (MX.ErroDeMix, SP.BibliotecaIncompleta, ValueError) as e:
        raise ErroDoMotor("mix", str(e))
    relatorio = {"ducking": rel["ducking"], "sfx": list(sfx), "trilha": rel["trilha"], "loudness": rel["loudness"],
                 "voz_ref": rel["voz_ref"], "aceleracao": relogio["aceleracao"]}
    return Path(saida), relatorio


if __name__ == "__main__":
    print("build_composite.py não roda sozinho: o build de um anúncio passa pelos gates na ordem do plano.\n"
          "Use: vam montar <slug>   (python3 scripts/vam.py montar <slug>, depois de vam plano e vam aprovar)",
          file=sys.stderr)
    sys.exit(2)
