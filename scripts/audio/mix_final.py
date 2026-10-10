"""Mix final do anúncio (C10, C11, C12): voz, efeitos, música, limiter, tudo num AAC só.

Ordem fixa. O contrário já custou caro (27/08/2026): o loudnorm normaliza a faixa inteira para -14 LUFS,
então baixar um efeito derrubava o loudness total e o loudnorm subia tudo de volta junto; a calibragem
descrevia um arquivo intermediário que ninguém ouve. Por isso:

    1. VOZ  já normalizada a -14 LUFS (`audio.loudness.normalizar`, passo anterior do pipeline)
    2. EFEITOS  riser, tick e boom nos instantes do plano de SFX, no nível em que foram calibrados
    3. MÚSICA   nivelada a -20 dBFS, cama 0,055 sob a fala e, nas pausas reais, a cama de CADA pausa (até o teto de 0,42),
                rampa 150 ms
    4. LIMITER  alimiter 0,97, sem auto level (o auto level sobe o sinal e muda o LUFS)

O motor antigo fazia isto em três remuxes em série, cada um com um AAC novo. Aqui é UM grafo de
filtros e UM AAC, com o vídeo copiado.

A CAMA DE CADA PAUSA (W7.Z) sai do que foi medido: o nível da voz naquela pausa e o da trilha ali (com o ganho e os fades
dela, antes da automação), para a subida sobre a voz sozinha cair no centro da faixa do `gate_mix` (+4,75 dB). Com um nível
absoluto de 0,42 a subida era a diferença entre o piso da voz isolada (de -36 a -55 dBFS) e a dinâmica da trilha, e media de
+11 a +21 dB na prova. `cama_adaptativa=False` devolve a automação de nível absoluto (o mutante dos testes).

A pausa que decide onde a cama sobe é medida na VOZ (a entrada, antes de qualquer efeito), por
`audio.pausas_reais`, e a MESMA lista vai para a expressão de volume, para o timeline.json e, depois,
para o `gate_mix`. A voz pré-mix é gravada em `voz_ref` (wav) para o gate comparar nível de final contra
nível de voz sozinha, janela a janela. Se o mixer baixar o mix para caber no true peak, a referência
baixa junto (senão o ajuste apareceria no gate como cama negativa).

Conferência da entrega no arquivo FINAL: o mix soma música e efeitos em cima de uma voz que já estava no
teto de true peak, e o AAC ainda pode somar décimos de dB. Se o true peak medido passa de -1,5 dBTP, o
mixer refaz a codificação a partir do PCM (sem segunda geração de AAC) com um ganho negativo que o
leva a -1,6. O LUFS não é "consertado" para cima: voz mal normalizada é erro do passo anterior e o
gate_mix acusa.

Uso:
    from audio import mix_final
    rel = mix_final.mixar("voz_norm.mp4", "final.mp4", trilha="fundo.mp3",
                          efeitos=[(14.6, riser_wav)], voz_ref="render/voz_pre_mix.wav")
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

from audio import loudness, nivel, pausas_reais
from cinema import musica

SR = 48000
BITRATE_AAC = "192k"
LIMITE_LIMITER = 0.97
MARGEM_TP_DB = 0.1               # o AAC soma décimos ao true peak: corrige para -1,6 e fica em -1,5
CORRECOES_MAX = 2


class ErroDeMix(RuntimeError):
    """O mix não pôde ser feito: insumo ausente, ffmpeg falhou ou o arquivo não tem áudio."""


def caminho_voz_ref(pj):
    """Onde mora a voz de referência (pré-mix) de um projeto: o gate_mix lê dali."""
    return Path(pj.render_dir) / "voz_pre_mix.wav"


def _ffprobe(arq, entradas, selecao=None):
    cmd = ["ffprobe", "-v", "error"]
    if selecao:
        cmd += ["-select_streams", selecao]
    cmd += ["-show_entries", entradas, "-of", "csv=p=0", str(arq)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise ErroDeMix("não consegui ler %s: %s" % (arq, r.stderr.strip()[-200:]))
    return r.stdout.split()


def _sondar(entrada):
    """(duração em s, canais do áudio, tem vídeo)."""
    audio = _ffprobe(entrada, "stream=channels", "a:0")
    if not audio:
        raise ErroDeMix("%s não tem faixa de áudio: o mix parte da voz" % entrada)
    dur = _ffprobe(entrada, "format=duration")
    video = _ffprobe(entrada, "stream=codec_type", "v:0")
    return float(dur[0]), int(audio[0].split(",")[0]), bool(video)


def construir_grafo(*, n_efeitos, tem_trilha, canais, duracao_s, ganho_trilha_db, expressao,
                    fade_in_s=musica.FADE_IN_S, fade_out_s=musica.FADE_OUT_S, atrasos_ms=None):
    """O filter_complex do mix. Entradas: 0 = voz, 1..n = efeitos, n+1 = trilha. Saída: [a].

    Ordem no grafo: efeitos sobre a voz (amix #1), depois a música (amix #2), depois o limiter.
    Todo ramo passa para o layout da voz antes de somar (efeito mono, trilha estéreo, voz mono).
    `normalize=0` nos dois amix: o padrão divide o ganho pelo número de entradas e a voz afundaria
    a cada efeito. `dropout_transition=0`: nada é renormalizado quando um efeito termina.
    """
    layout = "mono" if canais == 1 else "stereo"
    fmt = "aformat=sample_rates=%d:sample_fmts=fltp:channel_layouts=%s" % (SR, layout)
    atrasos_ms = list(atrasos_ms) if atrasos_ms is not None else [0] * n_efeitos
    partes = ["[0:a]%s[voz]" % fmt]
    cabeca = "[voz]"
    if n_efeitos:
        rotulos = []
        for k in range(n_efeitos):
            partes.append("[%d:a]%s,adelay=%d:all=1[e%d]" % (k + 1, fmt, atrasos_ms[k], k))
            rotulos.append("[e%d]" % k)
        partes.append("[voz]%samix=inputs=%d:duration=first:normalize=0:dropout_transition=0[vs]"
                      % ("".join(rotulos), n_efeitos + 1))
        cabeca = "[vs]"
    limiter = "alimiter=limit=%g:level=0" % LIMITE_LIMITER
    if tem_trilha:
        k = n_efeitos + 1
        partes.append("[%d:a]%s[mf]" % (k, fmt))
        partes.append(musica.cadeia_da_trilha("[mf]", "[m]", duracao_s, ganho_trilha_db, expressao,
                                              fade_in_s, fade_out_s))
        partes.append("%s[m]amix=inputs=2:duration=first:normalize=0:dropout_transition=0,%s[a]" % (cabeca, limiter))
    else:
        partes.append("%s%s[a]" % (cabeca, limiter))
    return ";\n".join(partes)


def _rodar(cmd, o_que):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise ErroDeMix("o ffmpeg falhou em %s: %s" % (o_que, r.stderr.strip()[-400:]))


def _codec_de_audio(destino):
    ext = Path(destino).suffix.lower()
    if ext == ".wav":
        return ["-c:a", "pcm_s16le"]
    if ext == ".flac":
        return ["-c:a", "flac"]
    return ["-c:a", "aac", "-ar", str(SR), "-b:a", BITRATE_AAC]


def _codificar(pcm, entrada, saida, tem_video, ganho_db):
    """PCM do mix -> `saida`. Com vídeo, o quadro vai copiado de `entrada`. UM codec de áudio só."""
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin"]
    if tem_video:
        cmd += ["-i", str(entrada), "-i", str(pcm), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy"]
    else:
        cmd += ["-i", str(pcm), "-map", "0:a:0"]
    if ganho_db:
        cmd += ["-af", "volume=%.3fdB" % ganho_db]
    cmd += _codec_de_audio(saida)
    if tem_video:
        cmd += ["-movflags", "+faststart", "-shortest"]
    cmd += [str(saida)]
    _rodar(cmd, "a codificação final")


def camas_das_pausas(entrada, trilha, pausas, duracao, ganho_trilha, *, cama_fala, cama_pausa, rampa_s, fade_in_s,
                     fade_out_s):
    """`[(início, fim, cama)]`: o ganho de cada pausa, fechado sobre o nível medido da voz (`entrada`) e da trilha (com o ganho
    e os fades, sem a automação) na janela de 0,5 s do meio da pausa. Pausa que não dá para medir fica com a cama global."""
    if not pausas:
        return []
    try:
        voz = nivel.carregar_mono(entrada)
        filtro = musica.cadeia_da_trilha("", "", duracao, ganho_trilha, None, fade_in_s, fade_out_s)
        som = nivel.carregar_mono(trilha, filtro=filtro, em_loop=True, duracao_s=duracao)
    except nivel.ErroDeNivel as e:
        raise ErroDeMix(str(e))
    saida = []
    for a, b in pausas:
        meio = (a + b) / 2.0 - musica.JANELA_MEDIDA_S / 2.0
        cama = musica.cama_da_pausa(nivel.nivel_db(voz, meio, musica.JANELA_MEDIDA_S),
                                    nivel.nivel_db(som, meio, musica.JANELA_MEDIDA_S),
                                    fator_rampa=musica.fator_de_rampa(a, b, rampa_s), cama_fala=cama_fala,
                                    cama_max=cama_pausa)
        saida.append((a, b, cama))
    return saida


def mixar(entrada, saida, *, efeitos=(), trilha=None, pausas=None, motivo_sem_trilha=None, voz_ref=None,
          cama_fala=musica.CAMA_FALA, cama_pausa=musica.CAMA_PAUSA, rampa_s=musica.RAMPA_S,
          fade_in_s=musica.FADE_IN_S, fade_out_s=musica.FADE_OUT_S, nivel_trilha_dbfs=musica.NIVEL_TRILHA_DBFS,
          cama_adaptativa=True):
    """Mixa `entrada` (vídeo ou áudio, voz já normalizada) em `saida`.

    efeitos          [(instante no arquivo ENTREGUE em s, wav)], do `sfx_plano.eventos_para_mix`
    trilha           arquivo de música do aluno, ou None
    motivo_sem_trilha  obrigatório quando não há trilha: o timeline grava `ducking` desligado com ele
    pausas           [(início, fim)] da cama; por padrão sai da voz (`audio.pausas_reais`). Lista
                     vazia = cama parada. É também como os testes fabricam o mutante "sem ducking".
    voz_ref          onde gravar a voz pré-mix (wav) para o gate_mix comparar (já com o ajuste de true
                     peak que o mixer aplicou ao mix, para a comparação isolar só a música)
    cama_adaptativa  True (padrão): cada pausa recebe a cama que fecha a conta com a voz e a trilha medidas ali (o
                     `cama_pausa` vira o teto); False: a automação de nível absoluto de antes, `cama_pausa` em todas

    Devolve o relatório: ducking (no formato do timeline), sfx mixados, trilha, loudness medido no
    arquivo final e o ajuste de true peak aplicado.
    """
    entrada, saida = Path(entrada), Path(saida)
    if not entrada.is_file():
        raise ErroDeMix("a voz de entrada não existe: %s" % entrada)
    if entrada.resolve() == saida.resolve():
        raise ValueError("a saída tem que ser outro arquivo: o mix não sobrescreve a entrada")
    if trilha is None and not (isinstance(motivo_sem_trilha, str) and len(motivo_sem_trilha.strip()) >= 5):
        raise ValueError("sem trilha, o mix exige o motivo escrito (motivo_sem_trilha): quem desliga a música "
                         "diz por quê, e o timeline grava")
    if trilha is not None and not Path(trilha).is_file():
        raise ErroDeMix("a trilha não existe: %s" % trilha)
    efeitos = [(float(t), Path(w)) for t, w in efeitos]
    for t, w in efeitos:
        if not w.is_file():
            raise ErroDeMix("o efeito não existe: %s" % w)
        if t < 0:
            raise ValueError("instante de efeito negativo: %s" % t)

    duracao, canais, tem_video = _sondar(entrada)

    rel = {"saida": str(saida), "voz_ref": str(voz_ref) if voz_ref else None, "duracao_s": round(duracao, 3),
           "sfx": [{"t": round(t, 3), "arquivo": w.name} for t, w in efeitos]}
    ganho_trilha, expressao = 0.0, ""
    if trilha is not None:
        if pausas is None:
            try:
                pausas = pausas_reais.pausas(str(entrada))
            except pausas_reais.ErroDeAudio as e:
                raise ErroDeMix(str(e))
        pausas = [(float(p[0]), float(p[1])) + ((float(p[2]),) if len(p) > 2 else ()) for p in pausas]
        media = musica.medir_media_db(trilha, ate_s=duracao)
        ganho_trilha = musica.ganho_para_nivel_db(media, nivel_trilha_dbfs)
        if cama_adaptativa and pausas and all(len(p) == 2 for p in pausas):
            pausas = camas_das_pausas(entrada, trilha, pausas, duracao, ganho_trilha, cama_fala=cama_fala,
                                      cama_pausa=cama_pausa, rampa_s=rampa_s, fade_in_s=fade_in_s,
                                      fade_out_s=fade_out_s)
        expressao = musica.expressao_volume(pausas, cama_fala, cama_pausa, rampa_s)
        rel["ducking"] = musica.ducking_para_timeline(pausas, cama_fala, cama_pausa, rampa_s, fade_in_s, fade_out_s)
        rel["trilha"] = {"arquivo": Path(trilha).name, "media_db": round(media, 2), "ganho_db": round(ganho_trilha, 2),
                         "nivel_dbfs": nivel_trilha_dbfs}
    else:
        rel["ducking"] = musica.ducking_desligado(motivo_sem_trilha)
        rel["trilha"] = None

    grafo = construir_grafo(n_efeitos=len(efeitos), tem_trilha=trilha is not None, canais=canais,
                            duracao_s=duracao, ganho_trilha_db=ganho_trilha, expressao=expressao,
                            fade_in_s=fade_in_s, fade_out_s=fade_out_s,
                            atrasos_ms=[int(round(t * 1000)) for t, _ in efeitos])
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", str(entrada)]
    for _, w in efeitos:
        cmd += ["-i", str(w)]
    if trilha is not None:
        cmd += ["-stream_loop", "-1", "-i", str(trilha)]
    pasta = Path(tempfile.mkdtemp(prefix="vam_mix_"))
    try:
        pcm = pasta / "mix.wav"
        _rodar(cmd + ["-filter_complex", grafo, "-map", "[a]", "-t", "%.3f" % duracao, "-c:a", "pcm_f32le",
                      "-ar", str(SR), str(pcm)], "o mix")
        saida.parent.mkdir(parents=True, exist_ok=True)
        ajuste = 0.0
        _codificar(pcm, entrada, saida, tem_video, ajuste)
        try:
            medicao = loudness.medir(saida)
            for _ in range(CORRECOES_MAX):
                if medicao.true_peak_dbtp <= loudness.TP_ALVO + 1e-9:
                    break
                ajuste += (loudness.TP_ALVO - MARGEM_TP_DB) - medicao.true_peak_dbtp
                _codificar(pcm, entrada, saida, tem_video, ajuste)
                medicao = loudness.medir(saida)
        except loudness.ErroDeLoudness as e:
            raise ErroDeMix("o mix saiu sem sinal mensurável: %s" % e)
    finally:
        shutil.rmtree(str(pasta), ignore_errors=True)
    if voz_ref is not None:
        # A voz de referência é a voz COMO ESTÁ NO ARQUIVO FINAL: se o mixer baixou o mix para caber no
        # true peak, a referência baixa junto. Sem isso o gate_mix leria o ajuste como "cama negativa".
        voz_ref = Path(voz_ref)
        voz_ref.parent.mkdir(parents=True, exist_ok=True)
        filtro = ["-af", "volume=%.3fdB" % ajuste] if ajuste else []
        _rodar(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", str(entrada), "-vn", *filtro,
                "-c:a", "pcm_s16le", str(voz_ref)], "a voz de referência")
    rel["loudness"] = {"lufs": round(medicao.integrado_lufs, 2), "true_peak_dbtp": round(medicao.true_peak_dbtp, 2),
                       "ajuste_db": round(ajuste, 3)}
    return rel
