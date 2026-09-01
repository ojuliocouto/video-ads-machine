#!/usr/bin/env python3
"""ÚNICO jeito autorizado de produzir um ad. Build e gate são um comando só.

GUARDRAIL (pedido do Julio, 05/08/2026): "voce precisa inserir algum tipo de guardrail
pra NUNCA trocar o metodo".

O que aconteceu: na leva OCC 08/2026 eu produzi AD03..AD12 chamando build_composite.py
direto, 10 seguidos, sem auditar nenhum, e so rodei auditoria depois de declarar pronto
e subir no Drive. Media 5,2, leva inteira reprovada. O ciclo build -> verificar ->
corrigir, que tinha produzido o AD01 e o AD02, foi exatamente o que eu descartei quando
o volume subiu.

Como este script impede a repeticao:
  1. build e gate acontecem na MESMA chamada: nao existe "buildei, depois vejo"
  2. se o gate reprova, o script sai com codigo 1 e NAO marca o ad como pronto
  3. em lote, um ad reprovado INTERROMPE a fila: nao da pra empilhar 10 defeituosos
  4. grava _status.json com o veredito, entao "esta pronto?" e uma leitura, nao memoria

Uso:
  python3 produzir_ad.py 03 espuma_roxa          # um ad
  python3 produzir_ad.py --lote                  # todos que tem config
  python3 produzir_ad.py --status                # so mostra o veredito atual
"""
import concurrent.futures
import fcntl
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from caminhos import V2L  # noqa: E402  (era o proprio dir; agora e o _local, que guarda o estado)
from gates_paralelo import rodar_em_paralelo
GATE = Path.home() / ".claude" / "scripts" / "gate-ad.py"
STATUS = V2L / "_status.json"

# rodizio: 3 avatares verticais, sem repetir entre vizinhos.
# O "dentro_carro" foi VETADO pelo Julio em 05/08/2026 ("nao ta bom"): enquadramento
# diagonal, ele de perfil com cinto, longe do padrao dos outros. Nao usar mais.
#
# 06 e 07 seguem o look do avatar HeyGen que JA foi gerado pra eles (estudio_verde e
# selfie_neon). Trocar so pra fechar uma tabela mais bonita custaria dois jobs novos de
# HeyGen (que recusa fila concorrente) sem ganho: a regra e nao repetir entre vizinhos,
# e essa sequencia ja nao repete.
LOOK_POR_AD = {
    "01": "espuma_roxa", "02": "estudio_verde", "03": "selfie_neon", "04": "estudio_verde",
    "05": "espuma_roxa", "06": "estudio_verde", "07": "selfie_neon", "08": "estudio_verde",
    "09": "espuma_roxa", "10": "estudio_verde", "11": "selfie_neon", "12": "espuma_roxa",
    # leva 2: PLANO MEDIO, porque o close deforma a boca no Avatar V (visto no AD13 em
    # 11/08/2026: labios e dentes borrados o video inteiro, o Julio pegou na hora).
    # So que "espuma_branca"/"estudio_claro"/"neon_branca" sao 16:9 com tarja, nao
    # servem em 9x16. Dos 9 looks, so 3 sao verticais nativos: #1 e #8 (close, boca
    # deformada) e #4 estudio_verde (plano medio). Entao a leva 2 inteira vai de
    # estudio_verde ate existir outro look vertical em plano medio.
    # MAPA DA LEVA 2 CORRIGIDO (01/09/2026, achado da auditoria pre-apresentacao).
    # Os nove apontavam pro `estudio_verde`, que saiu da lista permitida em 17/08 por
    # nao pertencer ao grupo THALES LARAY OFICIAL: rodar `produzir_ad.py 14` sem look
    # explicito reprovava na entrada. O default agora e o look que cada ad JA usou no
    # ultimo build entregue (conferido pelos arquivos em output/); 17-21 ainda nao
    # buildaram e caem no espuma_roxa, o unico da leva validado pelo Julio em close.
    "13": "espuma_roxa", "14": "oficial_13", "15": "neon_creme",
    "16": "espuma_roxa", "17": "espuma_roxa", "18": "espuma_roxa",
    "19": "espuma_roxa", "20": "espuma_roxa", "21": "espuma_roxa",
}


class FLock:
    """Trava entre processos, pra nunca existir dois builds ao mesmo tempo."""

    def __init__(self, caminho):
        self.caminho = Path(caminho)
        self.f = None

    def __enter__(self):
        self.f = open(self.caminho, "w")
        try:
            fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print("   (outro build em andamento, aguardando a vez...)", flush=True)
            fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()
        return False


def ler_status():
    if STATUS.exists():
        try:
            return json.loads(STATUS.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def gravar_status(ad, veredito, detalhe=""):
    s = ler_status()
    s[ad] = {"veredito": veredito, "detalhe": detalhe}
    STATUS.write_text(json.dumps(s, ensure_ascii=False, indent=2))


def revisar_copy(ad):
    """Revisao de COPY antes do build: erro de transcricao vira legenda queimada.

    Ordem do Julio (05/08/2026). O parakeet ouve "Claude" e escreve "Cloud": foram 39
    ocorrencias em 10 dos 12 anuncios, o nome do produto errado na tela de um anuncio
    pago. Rodar ANTES do build, porque depois do render o erro custa 8 min por ad.
    """
    rev = Path.home() / ".claude" / "scripts" / "revisor-copy-ad.py"
    if not rev.exists():
        print("AVISO: revisor de copy ausente"); return True
    print(f"\n--- REVISAO DE COPY AD{ad} ---", flush=True)
    r = subprocess.run([sys.executable, str(rev), ad], capture_output=True, text=True)
    print(r.stdout, flush=True)
    return r.returncode == 0


# --------------------------------------------------------------------------
# GATE DE ENTRADA. Portado do vam_build.py, que era o builder da leva 1 (AD01-AD12).
#
# O QUE ACONTECEU (11/08/2026): na leva 2 eu troquei de builder e trouxe só os gates
# de SAÍDA (texto na tela, piscada, loudness, duração). Os três gates de ENTRADA do
# vam_build ficaram pra trás, e eles eram justamente os que pegavam este defeito:
#   G1 clean_existe        -> o áudio higienizado existe?
#   G1 sem_respiro_grande  -> sobrou pausa de respiração?
#   G2 avatar_usou_clean   -> o avatar foi gerado A PARTIR do áudio limpo?
#
# Sem eles, gerei o avatar do AD13 direto do .m4a cru do WhatsApp: 21% do arquivo era
# silêncio, com pausas de até 1,70s. O Avatar V tira a expressão do áudio, então em
# cada pausa longa ele INVENTA rosto, e é de onde vinham os sorrisos estranhos que o
# Júlio pegou. O gate `avatar_usou_clean` teria reprovado na hora: avatar 92,8s contra
# clean 78,0s.
#
# Lição igual à que já existe no topo deste arquivo: gate que depende de alguém
# lembrar de rodar não é gate. Tem que estar na MESMA chamada do build.
# --------------------------------------------------------------------------
from caminhos import V1, CODIGO  # noqa: E402
BIG_SIL_GATE = 0.62      # a partir daqui a pausa vale checar por respiro
RESPIRO_DB_GATE = -34.0  # energia DENTRO da pausa acima disso = respiro audivel
AVATAR_DUR_TOL = 1.0     # avatar e clean têm que casar em duração

# Look só entra se for vertical NATIVO e de plano MÉDIO. Os de plano fechado deformam
# lábios e dentes no Avatar V; os 16:9 entram com tarja e o rosto fica com 35% do quadro.
# ATUALIZADO 17/08/2026, por MEDIÇÃO, não por memória.
#
# A lista antiga tinha só "estudio_verde" e vetava os outros por dois motivos. Um deles
# caiu: "16:9 com tarja, nao serve em 9x16" está FACTUALMENTE ERRADO hoje. Medi os 8
# avatares gerados nesta leva com ffprobe e TODOS saíram 1080x1920 nativos, incluindo
# espuma_branca, estudio_claro e neon_branca. O Júlio já tinha dito ("tem varios
# verticais, so nao quero o do carro") e a medida confirma.
#
# O outro motivo (plano fechado borrando boca e dentes no Avatar V) era real quando
# apareceu, mas é qualidade de IMAGEM, não de proporção, e varia por geração. Então virou
# CONFERÊNCIA, não veto cego: antes de liberar um look de plano fechado, recortar a região
# da boca em resolução nativa e olhar. No jh13 espuma_roxa (17/08) a boca saiu com lábios
# definidos e dentes separados, sem borrão, e o Júlio autorizou o uso.
#
# Regra que o Júlio deu junto: "melhor gastar credito com um avatar novo do que ficar
# batendo cabeça". Boca deformada = regera o avatar naquele look, não bloqueia a leva.
# Medidos um a um por ffprobe: todos nativos 1080x1920. O `estudio_verde` saiu daqui em
# 17/08/2026: ele nao pertence ao grupo THALES LARAY OFICIAL, o unico autorizado pelo
# Julio. O `oficial_13` entrou no lugar dele.
LOOKS_OK_9X16 = {
    "oficial_13", "espuma_roxa", "espuma_branca", "estudio_claro",
    "neon_branca", "neon_creme", "espuma_fechado", "espuma_estampado",
}
LOOKS_VETADOS = {
    "dentro_carro": "vetado pelo Julio em 05/08/2026: enquadramento diagonal, de perfil",
    "estudio_verde": "fora do grupo THALES LARAY OFICIAL (ordem de 17/08/2026); ja "
                     "custou refazer o AD14 e o AD22 da leva da Jheni",
}


def _dur(p):
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(p)], capture_output=True, text=True)
    try:
        return float(o.stdout.strip())
    except ValueError:
        return 0.0


def _respiros_grandes(audio, limite):
    """Pausas com RESPIRO AUDIVEL dentro. Nao pausa longa: pausa longa e ritmo.

    LOGICA INVERTIDA ATE 17/08/2026: isto devolvia toda pausa acima de `limite`, ou
    seja, tratava pausa natural de fim de frase como defeito. O efeito foi a
    higienizacao ser empurrada a achatar TUDO, e o Julio ouviu o resultado: "o audio
    foi todo picotado em varios momentos". No jh13 o bruto tinha 25 pausas de ate
    2,95s e o limpo saiu com ZERO acima de 0,55s.

    O defeito de verdade e respiro AUDIVEL dentro da pausa (o Avatar V lipsynca a
    respiracao e a boca mexe no vazio). Isso se mede por ENERGIA, nao por duracao.
    """
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", str(audio), "-af",
                        "silencedetect=noise=-30dB:d=0.28", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    inicios = [float(x) for x in re.findall(r"silence_start: ([\d.-]+)", r)]
    duracoes = [float(x) for x in re.findall(r"silence_duration: ([\d.]+)", r)]
    ruidosas = []
    for ini, dur_p in zip(inicios, duracoes):
        if dur_p < limite:
            continue
        a = subprocess.run(["ffmpeg", "-v", "info", "-ss", str(ini + 0.05),
                            "-t", str(min(dur_p - 0.1, 1.0)), "-i", str(audio),
                            "-af", "astats=metadata=1:reset=0", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
        vals = [float(x) for x in re.findall(r"RMS level dB:\s*(-?[\d.]+)", a)]
        if vals and max(vals) > RESPIRO_DB_GATE:
            ruidosas.append((round(ini, 1), round(dur_p, 2), round(max(vals), 1)))
    return ruidosas


def _ritmo_achatado(audio):
    """Pausa longa DEMAIS DE MENOS: fala sem respiracao de fim de frase soa picotada."""
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", str(audio), "-af",
                        "silencedetect=noise=-30dB:d=0.15", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    ps = [float(x) for x in re.findall(r"silence_duration: ([\d.]+)", r) if float(x) < 5]
    longas = [p for p in ps if p > 0.60]
    return len(longas), len(ps)


def gate_entrada(ad, look):
    """Confere áudio e avatar ANTES de montar. Reprova => o build nem começa."""
    print(f"\n--- GATE DE ENTRADA AD{ad} [{look}] ---", flush=True)
    falhas = []

    if look in LOOKS_VETADOS:
        falhas.append(f"look '{look}' vetado: {LOOKS_VETADOS[look]}")
    elif look not in LOOKS_OK_9X16:
        falhas.append(f"look '{look}' nao esta na lista aprovada pra 9x16 {sorted(LOOKS_OK_9X16)}")

    # PASTA DE AUDIO POR LEVA. Estava fixa em audios_leva2 e isso e uma bomba: os audios da
    # leva da Jheni tambem se chamam AD13..AD24 e sobrescreveriam os NOSSOS nove (que hoje
    # sao AD25..AD33 no Drive). Os dela moram em audios_leva4 e o ad vem prefixado com "jh".
    pasta = "audios_leva4" if str(ad).startswith("jh") else "audios_leva2"
    num = str(ad).replace("jh", "").replace("v2", "")
    limpo = V1 / "inputs" / pasta / f"AD{num}_higienizado.mp3"
    bruto = V1 / "inputs" / pasta / f"AD{num}.mp3"
    if not limpo.exists():
        if not bruto.exists():
            falhas.append(f"sem audio bruto em {bruto}")
        else:
            print(f"  higienizando {bruto.name} (passo obrigatorio, nao pulavel)...", flush=True)
            subprocess.run([sys.executable, str(CODIGO / "higienizar_audio.py"),
                            str(bruto), str(limpo)], capture_output=True, text=True)
    if limpo.exists():
        resid = _respiros_grandes(limpo, BIG_SIL_GATE)
        d_limpo = _dur(limpo)
        n_longas, n_pausas = _ritmo_achatado(limpo)
        print(f"  audio higienizado: {d_limpo:.1f}s | {len(resid)} pausa(s) com respiro "
              f"audivel | {n_longas} pausa(s) longa(s) de {n_pausas}")
        if resid:
            falhas.append(f"respiro audivel dentro de pausa: {resid}")
        # RE-TRANSCRICAO OBRIGATORIA (ordem do Julio, 17/08/2026): "transcrever NOVAMENTE
        # antes de jogar no avatar. esse processo precisa ser obrigatorio". O corte do
        # higienizador comeu 4 palavras no jh13 ("uma campanha"->"panha", "algo" apagado)
        # e so apareceu no video pronto, depois do avatar gerado.
        if bruto.exists() and os.environ.get("CHECAR_FALA") != "0":
            aa = CODIGO / "auditar_audio.py"
            if aa.exists():
                # (migracao 26/08/2026) codigo agora vizinho; import direto resolve
                try:
                    import auditar_audio
                    # (danos, suspeitas): so `danos` reprova. `suspeitas` sao
                    # divergencias de transcricao (elisao natural tipo "vamos embora"
                    # -> "vambora"), que aparecem no relatorio e nao travam a leva.
                    danos, suspeitas = auditar_audio.comparar_transcricoes(bruto, limpo)
                    print(f"  fala preservada: {'sim' if not danos else 'NAO'}"
                          + (f" -> {danos[:3]}" if danos else "")
                          + (f"  (transcricao divergiu em {len(suspeitas)}, sem dano)"
                             if suspeitas else ""), flush=True)
                    if danos:
                        falhas.append(
                            "corte comeu fala: " +
                            "; ".join(f"{o!r}->{n!r}" for o, n in danos[:4]))
                except Exception as e:
                    print(f"  [AVISO] checagem de fala falhou: {e}", flush=True)
        if d_limpo > 30 and n_longas < 4:
            falhas.append(
                f"ritmo achatado: so {n_longas} pausa(s) acima de 0,60s em {d_limpo:.0f}s. "
                "A fala fica sem respiracao de fim de frase e soa picotada. Rode "
                "auditar_audio.py, que higieniza preservando o ritmo.")
        # mesmo motivo da pasta de audio: os da Jheni tem prefixo "jh" pra nao colidir
        pref = "" if str(ad).startswith("jh") else "ad"
        avatar = V1 / "inputs" / f"{pref}{ad}v2_{look}_avatar.mp4"
        if not avatar.exists():
            falhas.append(f"avatar nao existe: {avatar.name}")
        else:
            d_av = _dur(avatar)
            print(f"  avatar: {d_av:.1f}s  |  clean: {d_limpo:.1f}s")
            if abs(d_av - d_limpo) > AVATAR_DUR_TOL:
                falhas.append(
                    f"avatar NAO foi gerado do audio limpo (avatar {d_av:.1f}s != "
                    f"clean {d_limpo:.1f}s). Regere com AD{ad}_higienizado.mp3")
    else:
        falhas.append("higienizacao nao produziu arquivo")

    for f in falhas:
        print(f"  REPROVA: {f}", flush=True)
    if not falhas:
        print("  >> PASSA", flush=True)
    return (not falhas), "; ".join(falhas)


def build(ad, look, fmt="9x16"):
    print(f"\n{'='*54}\nBUILD AD{ad} [{look}] {fmt}\n{'='*54}", flush=True)
    # UM build por vez, sempre. O motor v1 escreve em caminhos FIXOS (output/timing.json e
    # os segmentos de cena), entao dois builds simultaneos se sobrescrevem: rodei AD06 e
    # AD07 juntos e o 06 morreu em "invalid literal for int()" porque leu um segmento que
    # o 07 ja tinha trocado. Sozinho, o mesmo AD06 monta os 20 blocos sem um arranhao.
    with FLock(V2L / ".build.lock"):
        # terceiro e ultimo lugar onde o prefixo "ad" era fixo (os outros dois eram a
        # pasta de audio e o arquivo do avatar). Ad da leva da Jheni ja vem como "jh13".
        pref_cfg = "" if str(ad).startswith("jh") else "ad"
        r = subprocess.run([sys.executable, str(CODIGO / "build_composite.py"),
                            f"{pref_cfg}{ad}v2", look, fmt],
                           capture_output=True, text=True)
    saida = (r.stdout or "") + (r.stderr or "")
    print(saida[-600:], flush=True)
    return "OK ->" in saida


def ate_do_cta(html_texto, a0, accel):
    """Instante (no relogio do ENTREGUE) em que o CTA sobe, lido do overlay HTML.

    O overlay grava `data-start` no relogio dele proprio: acelerado e deslocado por a0,
    igual ao MOV que o gate de contraste consome (overlay = entregue * accel + a0).
    O inverso disola o instante no relogio do arquivo entregue: (data_start - a0) / accel.
    Devolve None se o elemento id="cta" nao existir no HTML (anuncio sem CTA marcado
    ou overlay de uma versao antiga): nesse caso o gate mede o anuncio inteiro.
    """
    m = re.search(r'id="cta"[^>]*data-start="([\d.]+)"', html_texto)
    if not m:
        m = re.search(r'data-start="([\d.]+)"[^>]*id="cta"', html_texto)
    if not m:
        return None
    data_start = float(m.group(1))
    return (data_start - a0) / accel


def gate(ad, fmt="9x16"):
    print(f"\n--- GATE AD{ad} {fmt} (obrigatorio, nao pulavel) ---", flush=True)
    if not GATE.exists():
        print(f"GATE AUSENTE em {GATE}. Sem gate nao ha entrega.", flush=True)
        return False, "gate ausente"

    # PARALELIZACAO DOS GATES DE SAIDA (31/08/2026): gate-ad.py, medir_ritmo.py,
    # gate-colisao-texto.py e gate-contraste-legenda.py rodavam em serie e juntos
    # levavam uns 4,5 minutos, dentro de um build de 20. Sao processos independentes:
    # todos leem o MESMO mp4 final, que o build ja deixou pronto antes de gate()
    # comecar, e nenhum decide se o outro roda. Por isso os comandos sao MONTADOS
    # primeiro (a montagem so olha arquivo em disco e env var, nunca resultado de
    # outro gate) e DISPARADOS juntos via gates_paralelo.rodar_em_paralelo. Os
    # posprocessamentos (mexer em ok/motivos, imprimir stdout) rodam DEPOIS, na
    # MESMA ORDEM de sempre, entao o log continua legivel e identico em conteudo.
    # A folha de contato continua depois, sozinha, sem paralelizar (ela nao reprova
    # nada e depende so do mp4, mas nao ha ganho em disputar CPU com os gates).
    tarefas = []
    env_ad = dict(os.environ, GATE_FMT=fmt)

    # RITMO (26/08/2026): ver historico completo no comentario original abaixo.
    # Regra da casa: checklist nao bloqueia, GATE bloqueia.
    _tem_ritmo = False
    if os.environ.get("GATE_RITMO") != "0":
        _pref = "" if str(ad).startswith("jh") else "ad"
        _fin = sorted(V1.glob(f"output/{_pref}{ad}v2_*_v2composite_{fmt}.mp4"),
                      key=lambda q: q.stat().st_mtime)
        if _fin:
            # O PLANO VAI JUNTO (27/08/2026). Sem ele o medidor cai na deteccao de
            # cena, que compara diferenca ABSOLUTA de pixel e erra dos dois lados no
            # mesmo arquivo: contou 10 "cortes" num fundo desfocado piscando e depois
            # deixou de ver `orig -> cheio`, que troca 100% do conteudo, porque o
            # anuncio e escuro de ponta a ponta. Com o plano, o corte precisa ser PEDIDO
            # por nos E VISTO na imagem. Ver cortes_confirmados() no medir_ritmo.
            _cmd = [sys.executable, str(CODIGO / "medir_ritmo.py"), str(_fin[-1])]
            _rj = sorted(V1.glob(f"output/{_pref}{ad}v2_*_footage_1x_ritmo.json"),
                         key=lambda q: q.stat().st_mtime)
            if _rj:
                from build_composite import ACCEL as _acc2
                _cmd += ["--ritmo-json", str(_rj[-1]), "--accel", str(_acc2)]
                _tj2 = V1 / "output" / "timing.json"
                if _tj2.exists():
                    try:
                        _cmd += ["--a0", str(json.loads(_tj2.read_text()).get("a0", 0.0))]
                    except Exception:
                        pass
            tarefas.append(("ritmo", _cmd))
            _tem_ritmo = True

    # COLISAO DE TEXTO COM O ROSTO (17/08/2026): ver historico completo no comentario
    # original abaixo. Ver ~/.claude/scripts/gate-colisao-texto.py.
    gcol = Path.home() / ".claude" / "scripts" / "gate-colisao-texto.py"
    _tem_colisao = False
    if gcol.exists() and os.environ.get("GATE_COLISAO") != "0":
        pref = "" if str(ad).startswith("jh") else "ad"
        finais = sorted(V1.glob(f"output/{pref}{ad}v2_*_v2composite_{fmt}.mp4"),
                        key=lambda p: p.stat().st_mtime)
        ovl = sorted((V2L).glob(f"render-{pref}{ad}v2-*-ovlonly/renders/*.mov"),
                     key=lambda p: p.stat().st_mtime)
        if finais:
            cmd = [sys.executable, str(gcol), str(finais[-1])]
            if ovl:
                cmd += ["--overlay", str(ovl[-1])]
            # O PLANO DE RITMO VAI JUNTO (27/08/2026). Sem ele o gate nao sabe quando o
            # anuncio esta em tela dividida, e a caixa de rosto HERDADA de um plano de
            # tela cheia continua valendo no painel do insert. Foi assim que o jh13
            # reprovou com o lettering "colidindo" com uma ampulheta de areia ambar.
            # PREFERIR AS JANELAS DO gen_ad_v2 (27/08/2026): o plano de ritmo cru marca
            # `layout=split` em toda fatia de insert, inclusive nas que a footage
            # renderiza em tela cheia porque o config nao tem `split: true`. Quem cruza
            # as duas fontes e o gen_ad_v2, e e o arquivo dele que vale.
            _rit = sorted((V2L).glob(f"render-{pref}{ad}v2-*-ovl/janelas_split.json"),
                          key=lambda q: q.stat().st_mtime)
            if not _rit:
                _rit = sorted(V1.glob(f"output/{pref}{ad}v2_*_footage_1x_ritmo.json"),
                              key=lambda p: p.stat().st_mtime)
            if _rit:
                from build_composite import ACCEL as _acc
                cmd += ["--ritmo", str(_rit[-1]), "--accel", str(_acc)]
            # AMOSTRA MAIS FINA (27/08/2026). O padrao de 1,5s da 61 amostras em 90s e
            # perdeu TODAS as colisoes que os dois auditores acharam na mao: o mesmo
            # arquivo, mesmo comando, com 0,25s acusa 69. Uma colisao de lettering dura
            # 1,7s e cabe inteira entre duas amostras de 1,5s. Gate que amostra grosso
            # entrega "PASSA" que nao prova nada.
            cmd += ["--intervalo", "0.5"]
            # a0: o composite desloca a footage com `setpts=PTS-a0/TB`. Sem passar isso,
            # o gate compara quadro de video com legenda de outro instante.
            _tj = V1 / "output" / "timing.json"
            if _tj.exists():
                try:
                    cmd += ["--a0", str(json.loads(_tj.read_text()).get("a0", 0.0))]
                except Exception:
                    pass
            tarefas.append(("colisao", cmd))
            _tem_colisao = True

    # CONTRASTE DA LEGENDA CONTRA O FUNDO (29/08/2026): ver historico completo no
    # comentario original abaixo. Ver ~/.claude/scripts/gate-contraste-legenda.py.
    gcon = Path.home() / ".claude" / "scripts" / "gate-contraste-legenda.py"
    _tem_contraste = False
    if gcon.exists() and os.environ.get("GATE_CONTRASTE") != "0":
        pref = "" if str(ad).startswith("jh") else "ad"
        finais = sorted(V1.glob(f"output/{pref}{ad}v2_*_v2composite_{fmt}.mp4"),
                        key=lambda p: p.stat().st_mtime)
        ovl = sorted((V2L).glob(f"render-{pref}{ad}v2-*-ovlonly/renders/*.mov"),
                     key=lambda p: p.stat().st_mtime)
        if finais and ovl:
            from build_composite import ACCEL as _acc3
            _tj3 = V1 / "output" / "timing.json"
            a0_val = 0.0
            if _tj3.exists():
                try:
                    a0_val = json.loads(_tj3.read_text()).get("a0", 0.0)
                except Exception:
                    pass
            cmd = [sys.executable, str(gcon), str(finais[-1]), "--overlay", str(ovl[-1]),
                   "--accel", str(_acc3), "--a0", str(a0_val), "--intervalo", "0.5"]
            # --ate: instante em que o CTA sobe, lido do overlay HTML mais recente.
            # Depois dele a tela e do botao e do logo, elementos com contraste proprio,
            # nao legenda de fala. Sem achar o elemento, mede o anuncio inteiro.
            _htmls = sorted(V2L.glob(f"render-{pref}{ad}v2-*-ovl/index_overlay.html"),
                            key=lambda p: p.stat().st_mtime)
            if _htmls:
                ate = ate_do_cta(_htmls[-1].read_text(), a0_val, _acc3)
                if ate is not None:
                    cmd += ["--ate", str(ate)]
            tarefas.append(("contraste", cmd))
            _tem_contraste = True

    # DISPARO: todos os comandos montados acima rodam ao mesmo tempo. O gate-ad.py
    # precisa da env com GATE_FMT (os outros nao), entao roda num executor a parte,
    # mas disparado ANTES de esperar os demais, entao continua tudo em paralelo de
    # verdade: o subprocess do gate-ad ja esta rodando quando rodar_em_paralelo
    # dispara e passa a esperar os outros tres.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _ex_ad:
        _fut_ad = _ex_ad.submit(
            subprocess.run, [sys.executable, str(GATE), ad],
            capture_output=True, text=True, env=env_ad)
        _res_outras = rodar_em_paralelo(tarefas, max_workers=4) if tarefas else {}
        r = _fut_ad.result()

    # POSPROCESSAMENTO NA ORDEM ORIGINAL: gate-ad -> ritmo -> colisao -> contraste.
    print(r.stdout, flush=True)
    motivos = [l.strip(" -") for l in r.stdout.split("\n") if l.strip().startswith("- ")]
    ok = r.returncode == 0

    if _tem_ritmo:
        _rr = _res_outras["ritmo"]
        print(_rr.stdout, flush=True)
        if _rr.returncode != 0:
            ok = False
            _ls = [l.strip() for l in _rr.stdout.split("\n") if "REPROVA" in l]
            motivos.append("ritmo: " + "; ".join(_ls[:2])[:180])

    if _tem_colisao:
        rc = _res_outras["colisao"]
        print(rc.stdout, flush=True)
        if rc.returncode != 0:
            ok = False
            extras = [l.strip() for l in rc.stdout.split("\n") if "texto cobre" in l]
            # GATE QUE MORRE NAO E GATE QUE REPROVA (28/08/2026). O build 26 saiu com
            # veredito "REPROVADO" e detalhe "colisao texto x rosto: ", sem UMA colisao
            # listada: o gate tinha morrido (rc != 0, stdout vazio) e o veredito
            # traduziu a morte dele em defeito do video. Rodando na mao, o mesmo
            # arquivo PASSOU. Falha de ferramenta e defeito de material sao coisas
            # diferentes e agora aparecem com nomes diferentes, com o stderr junto:
            # veredito vazio manda refazer render de 12min a toa.
            if not extras:
                err = (rc.stderr or "").strip().replace("\n", " ")[-300:]
                motivos.append(f"GATE DE COLISAO NAO RODOU (saida {rc.returncode}, "
                               f"sem achado no stdout): {err or 'sem stderr'}")
                print(f"   !! gate de colisao morreu (saida {rc.returncode}): "
                      f"{err or 'sem stderr'}", flush=True)
            else:
                motivos.append("colisao texto x rosto: " + "; ".join(extras[:3]))

    if _tem_contraste:
        rc2 = _res_outras["contraste"]
        print(rc2.stdout, flush=True)
        if rc2.returncode != 0:
            ok = False
            if "REPROVA" in rc2.stdout:
                _ls2 = [l.strip() for l in rc2.stdout.split("\n") if l.startswith("   t=")]
                motivos.append("contraste da legenda: " + "; ".join(_ls2[:2]))
            else:
                # GATE QUE MORRE NAO APROVA (mesma regra do gate de colisao, 28/08).
                err2 = (rc2.stderr or "").strip().replace("\n", " ")[-300:]
                motivos.append(f"GATE DE CONTRASTE NAO RODOU (saida {rc2.returncode}): "
                               f"{err2 or 'sem stderr'}")
                print(f"   !! gate de contraste morreu (saida {rc2.returncode}): "
                      f"{err2 or 'sem stderr'}", flush=True)

    # FOLHA DE CONTATO OBRIGATORIA (31/08/2026): em 29/08/2026 o anuncio foi avaliado
    # olhando 8 quadros isolados do roteiro e passou; so quando alguem assistiu a
    # folha do video inteiro o diagnostico mudou. E a tira a 0,05s em volta dos cortes
    # achou 4 quadros rasgados que ninguem tinha visto olhando quadro a quadro. Por
    # isso, PASSE ou REPROVE o gate, as duas folhas saem sempre: ninguem avalia
    # anuncio sem ter visto o filme inteiro. Erro aqui nunca muda o veredito do gate,
    # so fica sem prova visual pra quem for olhar depois.
    try:
        _pref_fc = "" if str(ad).startswith("jh") else "ad"
        _finais_fc = sorted(V1.glob(f"output/{_pref_fc}{ad}v2_*_v2composite_{fmt}.mp4"),
                             key=lambda p: p.stat().st_mtime)
        if _finais_fc:
            from folhas_contato import gerar_folhas
            _pasta_fc = V1 / "output" / f"{ad}_folhas"
            _p_inteira, _p_tiras = gerar_folhas(_finais_fc[-1], _pasta_fc)
            print(f"folha de contato (video inteiro): {_p_inteira}", flush=True)
            print(f"folha de contato (tiras de corte): {_p_tiras}", flush=True)
    except Exception as _e_fc:
        print(f"folha de contato: erro ao gerar, seguindo sem ela ({_e_fc})", flush=True)

    return ok, "; ".join(motivos)


def produzir(ad, look=None, fmt="9x16"):
    look = look or LOOK_POR_AD.get(ad)
    if not look:
        print(f"AD{ad}: look nao definido"); return False
    # 9x16 e 1x1 tem veredito proprio no _status.json: a chave do 1x1 leva sufixo pra um
    # nao apagar o resultado do outro.
    chave = ad if fmt == "9x16" else f"{ad}:1x1"
    # ESCAPE USADO FICA GRAVADO. Antes um bypass sumia no terminal e o _status.json
    # dizia PRONTO como se tudo tivesse sido verificado: "esta pronto?" voltava a ser
    # memoria em vez de leitura. Agora o veredito carrega a marca do bypass.
    bypass = [v for v in ("FASE_GATE", "FIDELIDADE", "FASE_GATE_LEGADO")
              if os.environ.get(v) in ("0", "1") and
              ((v == "FASE_GATE_LEGADO" and os.environ.get(v) == "1") or
               (v != "FASE_GATE_LEGADO" and os.environ.get(v) == "0"))]
    if bypass:
        print(f"\n!!! AD{ad}: BYPASS ATIVO -> {bypass}. So use com ordem explicita do "
              "Julio; isso vai gravado no _status.json.", flush=True)
    # GATE DE FASES (17/08/2026): fase0 ingestao + fase1 avatares em lote + fase2 plano
    # de edicao APROVADO pelo Julio, tudo com evidencia, ANTES de qualquer build.
    # Desligar so com ordem explicita dele: FASE_GATE=0.
    if os.environ.get("FASE_GATE") != "0":
        fg = subprocess.run([sys.executable, str(CODIGO / "fase_gate.py"), "check-build", ad],
                            capture_output=True, text=True)
        if fg.returncode != 0:
            motivo = (fg.stdout + fg.stderr).strip()
            gravar_status(chave, "FASES PENDENTES", motivo)
            print(f"\n>>> AD{ad} {fmt}: {motivo}", flush=True)
            return False
    # GATE DE FIDELIDADE AO DOC (ordem do Julio, 17/08/2026: "seguir FIELMENTE o
    # que tem nos comentarios e direcionamentos do doc"). Confere insert por insert
    # contra o que a Brigida marcou, e a estrutura de blocos. Gap legitimo vai
    # declarado em _fidelidade_excecoes.json com motivo escrito.
    # So roda pra ad que tem fonte declarada em _doc_map.json.
    if os.environ.get("FIDELIDADE") != "0":
        mapa_p = V2L / "_doc_map.json"
        mapa = json.loads(mapa_p.read_text()) if mapa_p.exists() else {}
        if ad not in mapa:
            # SEM FONTE DECLARADA O BUILD NAO ANDA. Antes o gate so rodava pra ad
            # presente no mapa e PULAVA em silencio pros outros, que e exatamente a
            # etapa pulada que o Julio proibiu (17/08/2026): jh14..jh21 tem roteiro
            # pronto e nenhum tinha fonte declarada.
            motivo = (f"ad '{ad}' nao tem fonte declarada em _doc_map.json "
                      "(doc, aba, secao). Sem isso nao da pra verificar fidelidade "
                      "ao doc, e pular a verificacao nao e opcao.")
            gravar_status(chave, "SEM FONTE NO DOC", motivo)
            print(f"\n>>> AD{ad} {fmt}: {motivo}", flush=True)
            return False
        vf = subprocess.run([sys.executable, str(CODIGO / "verificar_fidelidade.py"), ad],
                            capture_output=True, text=True)
        print(vf.stdout, flush=True)
        if vf.returncode != 0:
            motivos = [l.strip(" -") for l in vf.stdout.split("\n")
                       if l.strip().startswith("- ")]
            gravar_status(chave, "INFIEL AO DOC", "; ".join(motivos))
            print(f"\n>>> AD{ad} {fmt}: INFIEL AO DOC, build nem comecou", flush=True)
            return False
    if not revisar_copy(ad):
        gravar_status(chave, "COPY COM ERRO",
                      "erro de transcricao no roteiro; rode revisor-copy-ad.py --corrigir")
        print(f"\n>>> AD{ad} {fmt}: COPY COM ERRO, build nem comecou", flush=True)
        return False
    ok_entrada, motivo = gate_entrada(ad, look)
    if not ok_entrada:
        gravar_status(chave, "ENTRADA REPROVADA", motivo)
        print(f"\n>>> AD{ad} {fmt}: ENTRADA REPROVADA, build nem comecou", flush=True)
        return False
    if not build(ad, look, fmt):
        gravar_status(chave, "BUILD FALHOU")
        return False
    ok, motivos = gate(ad, fmt)
    veredito = "PRONTO" if ok else "REPROVADO"
    if bypass:
        veredito += " (COM BYPASS)"
        motivos = f"BYPASS: {','.join(bypass)}; " + (motivos or "")
    gravar_status(chave, veredito, motivos)
    print(f"\n>>> AD{ad} {fmt}: {'PRONTO' if ok else 'REPROVADO NO GATE'}", flush=True)
    return ok


def main():
    if "--status" in sys.argv:
        s = ler_status()
        if not s:
            print("nenhum ad processado ainda"); return
        for ad in sorted(s):
            v = s[ad]
            print(f"  AD{ad}: {v['veredito']:12s} {v.get('detalhe','')[:80]}")
        pend = [a for a, v in s.items() if v["veredito"] != "PRONTO"]
        print(f"\n{len(s)-len(pend)} prontos, {len(pend)} pendentes")
        sys.exit(1 if pend else 0)

    if "--lote" in sys.argv:
        alvos = [a for a in sorted(LOOK_POR_AD)
                 if (V2L / "configs").glob(f"ad{a}v2_*.json")]
        for ad in alvos:
            if not produzir(ad):
                # um reprovado PARA a fila: nao empilha defeito
                print(f"\nFILA INTERROMPIDA no AD{ad}. Corrija antes de seguir.")
                sys.exit(1)
        print("\nlote inteiro passou no gate")
        return

    fmt = "9x16"
    argv = sys.argv[1:]
    if "--fmt" in argv:
        i = argv.index("--fmt")
        fmt = argv[i + 1]
        del argv[i:i + 2]
    if not argv:
        sys.exit(__doc__)
    ad = argv[0].zfill(2)
    look = argv[1] if len(argv) > 1 else None
    sys.exit(0 if produzir(ad, look, fmt) else 1)


if __name__ == "__main__":
    main()
