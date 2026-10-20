"""One-shot: do take bruto de câmera ao anúncio 9:16, com a medição de cada passo.

Take de câmera, uma tomada só, o apresentador falando direto para o celular. Não passa por HeyGen
nem tem roteiro em blocos: é edição de material cru. "One-shot" é o formato de VEICULAÇÃO (o anúncio
aparece uma vez para quem viu o checkout e não comprou), não licença para entregar material cru:
editar é o trabalho. Cada passo é medido no arquivo, nunca estimado; os erros que mais custaram tempo
no método de origem foram todos valor chutado, e todos se resolveram de primeira quando medidos.

    0  ENTENDER      assistir o bruto e transcrever ANTES de tocar em nada (a CLI mostra o plano e para: --so-plano)
    1  TRANSCREVER   tempo de palavra pela Groq; no corte cada palavra ganha margem (0,30 s antes, 0,15 s depois)
    2  CORTAR        o ar morto sai pelas duas fontes que se corrigem: o vão entre as palavras diz ONDE,
                     a energia da onda diz QUANTO (`ar_morto.py`, cinco bugs reais, cada um um teste). O piso
                     de silêncio é o ruído MEDIDO do take mais 6 dB (`ar_morto.piso_adaptativo`); antes da
                     primeira palavra e depois da última corta pela transcrição (o preâmbulo de quem pega o
                     celular não é silêncio em sala barulhenta)
    2b LIMPAR        falsa partida, fala de quem dirige e outra voz ao fundo saem por sub-bloco lido sozinho
                     (`oneshot.limpeza`); cada retirada vai para o plano com motivo e texto, para conferir
    3  ENQUADRAR     janela 9:16 centrada no rosto MEDIDO (`oneshot.enquadrar`)
    4  LUZ           luminância medida vira brightness e contraste (`oneshot.luz`); HDR do celular vira SDR
    5  LETTERING     caixa nativa (`caixa_lettering`, PT Serif do repo), opcional
    6  RENDER ÚNICO  corte + enquadre + luz + grade + velocidade + caixa numa passada só: nada de arquivo
                     intermediário reencodado entre etapas (perde qualidade à toa)
    7  LOUDNESS      -14 LUFS, true peak -1,5 dBTP, em dois passes (`audio.loudness`)
    8  GATES         a fala do bruto está inteira no final, a maior pausa do final e o técnico

A aceleração é a do `projeto.json` (padrão 1,2 em take real: o 1,35 do avatar foi reprovado de ouvido).
A grade é o preset `estilo.grade` (padrão quente-suave) e fecha com as tags bt709.

    planejar(pj, take, leitor)             o plano (dict): cortes, janela, luz, aceleração, aviso de tudo que não mediu
    filtro_complexo(plano, caixa)          o grafo do ffmpeg, como texto
    renderizar(pj, plano, caixa_png)       entrega/final_9x16.mp4, loudness normalizado
    conferir(pj, plano, leitor, final)     [(gate, ok, motivo)]

Importar este módulo não faz nada: o ffmpeg só roda dentro de `renderizar`.
"""
import subprocess
import tempfile
from pathlib import Path

import ar_morto
from audio import loudness
from audio import transcrever as _asr_t
from cinema import grade as _grade
from gravado import auditar, gate_ar_morto, gate_fala
from gravado import montar as gravado_montar
from gravado.nucleo import asr, energia
from gravado.veredito import InsumoInvalido
from oneshot import enquadrar, limpeza, luz
from projeto import glossario as _glossario
from projeto import modelo, status

FPS = 30
JAN = energia.JANELA_S
ARQUIVO_PLANO = "oneshot.json"


def carregar_projeto(pj):
    """O projeto.json do one-shot, validado. InsumoInvalido se não existe, não vale ou é de outro modo."""
    if not pj.projeto_json.is_file():
        raise InsumoInvalido("não achei o projeto %r (%s): crie com `vam novo %s --modo oneshot`"
                             % (pj.slug, pj.projeto_json, pj.slug))
    try:
        projeto = modelo.carregar(pj.projeto_json)
    except modelo.ContratoInvalido as e:
        raise InsumoInvalido(str(e))
    if projeto["modo"] != "oneshot":
        raise InsumoInvalido("o projeto %r é do modo %r, não oneshot: o take de câmera sem avatar é `vam oneshot`; "
                             "o avatar segue o fluxo dele" % (pj.slug, projeto["modo"]))
    return projeto


def aceleracao(projeto):
    """A aceleração do projeto (padrão 1,2 no one-shot, preenchido pelo `projeto.modelo`)."""
    return float(projeto["aceleracao"])


def leitor_do_projeto(pj, backend=None, estado=None):
    """O leitor de ASR do projeto: cache em `render/cache_asr`, glossário do aluno."""
    return asr.Leitor(pj.render_dir / "cache_asr", glossario=_glossario.carregar(estado or pj.estado),
                      backend=backend)


# --- planejar ----------------------------------------------------------------------------------------

def cortes_do_take(palavras, db_relativo, duracao, margens=None, backend=None, retiradas=()):
    """[(início, fim)] a MANTER do take. As palavras ancoram, a energia mede o silêncio.

    O piso de silêncio é o do take (`ar_morto.params_do_piso`: ruído medido mais 6 dB, nunca abaixo do fixo).
    O que vem antes da primeira palavra e depois da última sai pela transcrição, com as margens de palavra:
    em sala barulhenta o preâmbulo não é silêncio e a energia sozinha não o acha. `retiradas` ([{ini, fim}],
    de `oneshot.limpeza`) saem também.

    A nuvem marca o início da palavra tarde: cada palavra ganha margem antes (0,30 s na Groq, 0,40 s na Mistral,
    conforme o `backend` que fez o tempo) e depois (0,15 s), sem invadir a vizinha (`ar_morto.margens_de_palavra`).
    `margens=(pre, pos)` troca o padrão; sem ele valem VAM_CORTE_PRE_ROLL e VAM_CORTE_POS_ROLL."""
    pre, pos = margens if margens is not None else ar_morto.margens_do_ambiente(_asr_t.Ambiente.real().env, backend)
    tokens = ar_morto.margens_de_palavra([(p["start"], p["end"], p["text"]) for p in palavras], pre, pos)
    blocos = ar_morto.blocos_de_fala(tokens)
    if not blocos:
        raise InsumoInvalido("o transcritor não ouviu nenhuma palavra no take: sem saber onde há fala não dá para "
                             "tirar ar morto sem arriscar comer palavra")
    cortes = ar_morto.planejar_cortes(blocos, db_relativo, JAN, duracao, params=ar_morto.params_do_piso(db_relativo))
    cortes += cortes_das_pontas(blocos, duracao)
    cortes += [(r["ini"], r["fim"]) for r in retiradas]
    return ar_morto.segmentos_manter(cortes, duracao)


def cortes_das_pontas(blocos, duracao):
    """[(início, fim)] do preâmbulo e da cauda pela transcrição: antes da primeira palavra (já com a margem) menos
    o respiro de entrada, e depois da última mais o respiro de saída."""
    cortes = []
    if not blocos:
        return cortes
    fim_intro = blocos[0][0] - ar_morto.PADRAO["pre_roll_intro"]
    if fim_intro > 0.05:
        cortes.append((0.0, round(fim_intro, 3)))
    ini_cauda = blocos[-1][1] + ar_morto.PADRAO["pos_roll_fim"]
    if duracao - ini_cauda > 0.05:
        cortes.append((round(ini_cauda, 3), duracao))
    return cortes


def limpar_take(take, leitor, db_relativo, palavras):
    """(retiradas, avisos) de `oneshot.limpeza`: lê cada sub-bloco do take sozinho e acha falsa partida, fala de
    quem dirige e outra voz. Sem leitura por trecho no leitor, não confere e diz isso no plano."""
    if not hasattr(leitor, "palavras_do_trecho"):
        return [], ["o transcritor não lê trecho a trecho: retomada e fala de quem dirige NÃO foram conferidas"]
    blocos = limpeza.ler_blocos(take, leitor, db_relativo, JAN, limpeza.limiar_de_fala(db_relativo))
    return limpeza.retiradas(blocos, palavras)


def _preset(projeto):
    try:
        return _grade.do_projeto(projeto)
    except _grade.GradeDesconhecida as e:
        raise InsumoInvalido(str(e))


def planejar(pj, take, leitor, detector=None, medidor_luz=None):
    """O plano do one-shot (dict serializável). Nada é renderizado. Mede e anota, e o que NÃO conseguiu medir
    vai em `avisos` em vez de virar número de reserva calado.

    `detector` (rosto) e `medidor_luz(take, janela)` trocam as medidas reais (os testes injetam)."""
    projeto = carregar_projeto(pj)
    accel = aceleracao(projeto)
    preset = _preset(projeto)
    take = Path(take)
    dims = enquadrar.dimensoes_exibidas(take)
    dur = energia.duracao_s(take)
    palavras = leitor.palavras(take, exigir_borda=True)
    db, _ = energia.curva(take, jan=JAN)
    if not len(db):
        raise InsumoInvalido("o take %s é curto demais para medir" % take.name)
    backend = getattr(leitor, "ultimo_backend", None)
    rel = (db - db.max()).tolist()
    retiradas, avisos = limpar_take(take, leitor, rel, palavras)
    segs = cortes_do_take(palavras, rel, dur, backend=backend, retiradas=retiradas)
    if not segs:
        raise InsumoInvalido("o corte não deixou nenhum trecho do take: confira o áudio de %s" % take.name)
    avisos = list(avisos)
    if segs[0][0] >= 1.5:
        avisos.append("preâmbulo de 0 a %.2f s cortado: o transcritor não ouviu palavra ali, confira na prévia"
                      % segs[0][0])
    janela = enquadrar.janela_9x16(dims[0], dims[1], None)
    if janela["precisa_crop"]:
        rosto = enquadrar.medir_rosto(take, detector=detector)
        janela = enquadrar.janela_9x16(dims[0], dims[1], rosto)
        if rosto is None:
            avisos.append("nenhum rosto detectado no take: o recorte 9:16 ficou no centro do quadro, sem "
                          "ancorar no rosto (confira o enquadramento na prévia)")
    transferencia = luz.transferencia_do_video(take)
    with tempfile.TemporaryDirectory(prefix="vam-luz-") as tmp:
        antes = ""
        if luz.eh_hdr(transferencia):
            antes = luz.cadeia_hdr_para_sdr(luz.gerar_lut(Path(tmp) / "hdr.cube", transferencia=transferencia))
        if medidor_luz is not None:
            media = medidor_luz(take, janela)
        else:
            media = luz.medir(take, janela, filtro_antes=antes)
    luz_ = luz.calcular(media)
    if luz_["limitado"]:
        avisos.append("a imagem está escura demais (luminância %.0f, alvo %.0f): a luz foi limitada em %.2f e "
                      "a pós não resolve tudo, melhore a luz da gravação" % (media, luz_["alvo"], luz_["brightness"]))
    mantido = sum(b - a for a, b in segs)
    return {"versao": 1, "take": str(take), "dur_bruto": round(dur, 3), "aceleracao": accel,
            "segmentos": [[round(a, 3), round(b, 3)] for a, b in segs], "dur_cortada": round(mantido, 3),
            "dur_final": round(mantido / accel, 3), "dimensoes": [dims[0], dims[1]], "janela": janela,
            "luz": luz_, "grade": preset, "transferencia": transferencia, "avisos": avisos,
            "piso_db": ar_morto.piso_adaptativo(rel), "retiradas": retiradas,
            "palavras_bruto": [{"text": p["text"], "start": p["start"], "end": p["end"]} for p in palavras]}


def salvar_plano(pj, plano):
    """Grava `render/oneshot.json` (dentro do projeto). Devolve o Path."""
    arq = pj.render_dir / ARQUIVO_PLANO
    status.escrever_json_atomico(arq, plano)
    return arq


# --- o render único ----------------------------------------------------------------------------------

def filtro_complexo(plano, caixa=False, hdr_lut=None):
    """O `-filter_complex` do render único (texto, sem ffmpeg): corte, enquadre, conversão HDR, luz,
    concatenação, velocidade, grade e, se `caixa`, a sobreposição da caixa nativa (entrada 1) DEPOIS da
    grade, para a caixa não levar grão nem vinheta."""
    accel = plano["aceleracao"]
    enquadre = enquadrar.filtro(plano["janela"])
    conversao = (luz.cadeia_hdr_para_sdr(hdr_lut) + ",") if hdr_lut else ""
    ajuste = luz.filtro(plano["luz"])
    ajuste = (ajuste + ",") if ajuste else ""
    fc, vlab, alab = [], [], []
    for i, (s, e) in enumerate(plano["segmentos"]):
        fc.append("[0:v]trim=%s:%s,setpts=PTS-STARTPTS,fps=%d,%s,%s%sformat=yuv420p[v%d]"
                  % (s, e, FPS, enquadre, conversao, ajuste, i))
        fc.append("[0:a]atrim=%s:%s,asetpts=PTS-STARTPTS,aformat=sample_fmts=fltp:sample_rates=48000:"
                  "channel_layouts=mono[a%d]" % (s, e, i))
        vlab.append("[v%d]" % i)
        alab.append("[a%d]" % i)
    pares = "".join(v + a for v, a in zip(vlab, alab))
    n = len(plano["segmentos"])
    fc.append("%sconcat=n=%d:v=1:a=1[vc][ac]" % (pares, n))
    grade_ = _grade.cadeia(plano["grade"])
    if caixa:
        fc.append("[vc]setpts=PTS/%s,%s[vg]" % (accel, grade_))
        fc.append("[vg][1:v]overlay=0:0:format=auto:shortest=1[vo]")
    else:
        fc.append("[vc]setpts=PTS/%s,%s[vo]" % (accel, grade_))
    fc.append("[ac]atempo=%s[ao]" % accel)
    return ";".join(fc)


def comando_render(plano, take, caixa_png, saida, hdr_lut=None):
    """O comando do ffmpeg (lista): UMA entrada de vídeo (o take) e, se houver, a caixa em loop."""
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(take)]
    if caixa_png:
        cmd += ["-loop", "1", "-framerate", str(FPS), "-i", str(caixa_png)]
    cmd += ["-filter_complex", filtro_complexo(plano, bool(caixa_png), hdr_lut), "-map", "[vo]", "-map", "[ao]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-colorspace", "bt709",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv", "-c:a", "aac", "-b:a", "192k",
            str(saida)]
    return cmd


def renderizar(pj, plano, caixa_png=None):
    """Renderiza o one-shot numa passada e normaliza o loudness. Devolve `entrega/final_9x16.mp4`."""
    take = Path(plano["take"])
    if not take.is_file():
        raise InsumoInvalido("não achei o take do plano: %s" % take)
    pj.entrega_dir.mkdir(parents=True, exist_ok=True)
    pj.render_dir.mkdir(parents=True, exist_ok=True)
    sem_loud = pj.render_dir / "oneshot_semloud.mp4"
    with tempfile.TemporaryDirectory(prefix="vam-hdr-") as tmp:
        lut = None
        if luz.eh_hdr(plano.get("transferencia")):
            lut = str(luz.gerar_lut(Path(tmp) / "hdr.cube", transferencia=plano["transferencia"]))
        try:
            cmd = comando_render(plano, take, caixa_png, sem_loud, lut)
            try:
                r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
            except FileNotFoundError:
                raise InsumoInvalido("ffmpeg não encontrado: instale com `brew install ffmpeg`")
            if r.returncode != 0:
                raise InsumoInvalido("o ffmpeg falhou no render: %s" % r.stderr.strip()[-600:])
            try:
                gravado_montar.normalizar_para_entrega(sem_loud, pj.final_9x16)
            except loudness.ErroDeLoudness as e:
                raise InsumoInvalido(str(e))
        finally:
            if sem_loud.exists():
                sem_loud.unlink()
    return pj.final_9x16


# --- gates de depois ---------------------------------------------------------------------------------

def conferir(pj, plano, leitor, final):
    """[(gate, ok, motivo)] do anúncio pronto: a fala do bruto está inteira no final (re-transcrição palavra
    a palavra, só equivalência declarada no glossário), nenhuma pausa acima do teto do cortador e o técnico
    (1080x1920, 48 kHz, loudness). Quem decide é a medida do ARQUIVO entregue, nunca o plano."""
    take = Path(plano["take"]) if plano.get("take") else pj.voz_bruto()
    glossario = _glossario.carregar(pj.estado)
    retiradas = plano.get("retiradas") or []
    if retiradas and plano.get("palavras_bruto"):
        # o bruto MENOS as retiradas declaradas no plano (retomada, quem dirige, outra voz): fora delas nada some
        esperado = asr.texto_das_palavras(limpeza.palavras_fora(plano["palavras_bruto"], retiradas))
    else:
        esperado = leitor.texto_da_peca(take)
    ok_f, motivo_f = gate_fala.verificar(esperado, leitor.texto_da_peca(final), glossario)
    if retiradas:
        motivo_f += "; %d trecho(s) retirado(s) de propósito, listados no plano" % len(retiradas)
    ok_a, motivo_a = gate_ar_morto.verificar(final, plano["aceleracao"])
    t = auditar.tecnico(final)
    motivo_t = t["motivo"] or "%s, %.1fs, %.1f LUFS, pico %.1f dBTP" % (t["resolucao"], t["duracao"], t["lufs"],
                                                                        t["true_peak"])
    return [("fala_preservada", ok_f, motivo_f), ("ar_morto", ok_a, motivo_a), ("tecnico", bool(t["ok"]), motivo_t)]
