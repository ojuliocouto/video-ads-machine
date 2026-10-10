"""plano/medir: o plano de edição MEDIDO (plano/plano.json), nunca declarado.

    cd scripts && python3 -m plano.medir --projeto _local/projetos/<slug> [--palavras alinhamento.json]
    cd scripts && python3 -m plano.medir <slug> [--estado _local]

Entradas: o roteiro.md (dirigido), o projeto.json, o alinhamento da fala (as palavras com tempo do
`voz/limpo.mp3`, pelo `audio.transcrever`, ou um json pronto) e os arquivos de `inserts/`. Saída: o
plano.json do contrato `contratos/plano.schema.json` e o plano_edicao.md que o aluno lê.

O QUE É MEDIDO (e por isso não pode ser declarado: `medir(sugestoes=...)` recusa):
  blocos        o tempo de cada bloco, da primeira palavra dele até a primeira do próximo (o bloco 0 começa em 0,
                que é onde está o quadro 0), pelo alinhamento do roteiro com a fala (`build_timeline.align_words`,
                o mesmo do motor); bloco com menos de 0,3 s ganha 0,3 s, como no motor.
  mapa_inserts  largura, altura e duração de cada arquivo (ffprobe), orientação, tratamento, visitas e o
                congelamento previsto: consome = duração do bloco x velocidade; congela = consome - (fonte - início),
                a conta do `analise_inserts`, a mesma do gate de entrada.
  densidade     fração do tempo com insert na tela, pelo plano de ritmo (`ritmo.plano_de_ritmo`) que a footage usa.
  ritmo         cortes por minuto, tempo em plano longo e maior plano do mesmo plano de ritmo, no arquivo entregue
                (tempos divididos pela aceleração), a conta de `medir_ritmo.medir_do_plano`.
  letterings    KEY, itens de lista e CTA, ancorados na palavra de pouso, com o tempo dela.
  hook, efeitos e a checklist saem destas medições (`checklist.avaliar`).

O QUE O DIRETOR PODE ACRESCENTAR (`sugestoes`): `referencias` (além das que o plano já tem pelas técnicas medidas),
`propostas` de insert para falas que ficaram no rosto, `propostos` (blocos cuja direção o plano propôs, e que
dependem do ok) e, no modo gravado, os `trechos` do take. Criativo e escolha, não medida.

RELÓGIOS. Todo tempo do plano.json está no relógio da gravação a 1x (antes da aceleração), como no
timeline.json. As constantes do motor que são "segundos entregues" (hook até 3,2 s, duração da KEY, riser 1,0 s
antes do CTA) são multiplicadas pela aceleração do projeto. O bloco `ritmo` é o único em segundos ENTREGUES
(é o que `medir_ritmo` mede no arquivo final).

Não mexe em nenhum arquivo fora de plano/ (plano.json e plano_edicao.md).
"""
import argparse
import copy
import difflib
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":      # rodado direto: scripts/plano/medir.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build_timeline  # noqa: E402
import medir_ritmo  # noqa: E402
import ritmo as _ritmo  # noqa: E402
from contratos.validar import normalizar_palavra  # noqa: E402
from entrada import roteiro_md  # noqa: E402
from entrada.para_motor import DUR_KEY, DUR_PILHA_ULTIMO, layout_efetivo  # noqa: E402
from plano import checklist, escrever_md  # noqa: E402
from projeto import glossario, modelo, pastas, status  # noqa: E402

# Faixa de densidade (capacidade C8): alvo de 45 a 55% do tempo com insert, piso 40, teto 65. Exceção só com
# motivo, em projeto.json (excecoes, regra densidade).
ALVO_MIN, ALVO_MAX, PISO, TETO = 0.45, 0.55, 0.40, 0.65
# Hook (capacidade C1), em segundos ENTREGUES: dura 3,0 s sobre o rosto; com insert de abertura fica até o rosto
# voltar, com teto de 3,2 s (gen_ad_v2: HOOK_MAX; sem teto o hook segurou 15 s e o anúncio ficou sem legenda).
HOOK_PADRAO_ENTREGUE = 3.0
HOOK_MAX_ENTREGUE = 3.2
HOOK_FOLGA_ENTREGUE = 0.1
JANELA_DO_GANCHO_ENTREGUE = 3.0         # o evento visual do gancho tem que cair nestes primeiros segundos
RISER_ANTES_DO_CTA_ENTREGUE = 1.0       # capacidade C11
BLOCO_MIN_S = 0.3                       # piso de duração do bloco (gen_ad_v2: bounds[-1] + 0.3)
LETTERING_MIN_S = 0.3
# Fração mínima das palavras do roteiro que a fala tem de conter para o alinhamento valer. Abaixo disto o alinhamento
# por posição daria tempo de mentira: o gate_fala_roteiro é quem diz o que faltou.
COBERTURA_MIN = 0.6
IMAGENS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")

SUGESTOES_ACEITAS = ("referencias", "propostas", "propostos", "trechos")
MEDIDOS = ("blocos", "mapa_inserts", "hook", "letterings", "densidade", "efeitos", "ritmo", "checklist",
           "duracao_s", "fonte", "modo", "projeto", "versao", "gerado_em")


class PlanoNaoMedivel(ValueError):
    """Falta insumo (ou o insumo não serve) para medir o plano; a mensagem diz o que fazer."""


class PlanoInvalido(ValueError):
    """O plano medido não passa nas 6 seções, na checklist ou no contrato; nada foi gravado."""


# --- ffprobe -----------------------------------------------------------------------------------------------

def interpretar_ffprobe(saida, imagem=False):
    """{largura, altura, duracao_s} da saída JSON do ffprobe. Aplica a rotação (celular grava 1920x1080 com
    rotação de 90 graus e o ffprobe mente na largura e na altura). Imagem estática tem duração 0."""
    video = next((s for s in (saida.get("streams") or []) if s.get("width") and s.get("height")), None)
    if video is None:
        raise PlanoNaoMedivel("o arquivo não tem imagem nem vídeo que o ffprobe consiga ler")
    largura, altura = int(video["width"]), int(video["height"])
    rotacao = (video.get("tags") or {}).get("rotate")
    for lado in video.get("side_data_list") or []:
        if "rotation" in lado:
            rotacao = lado["rotation"]
    try:
        if rotacao is not None and int(float(rotacao)) % 180 == 90:
            largura, altura = altura, largura
    except (TypeError, ValueError):
        pass
    formato = saida.get("format") or {}
    nome = str(formato.get("format_name") or "")
    estatica = imagem or "image2" in nome or nome.endswith("_pipe")
    try:
        duracao = 0.0 if estatica else float(formato.get("duration"))
    except (TypeError, ValueError):
        duracao = 0.0
    return {"largura": largura, "altura": altura, "duracao_s": round(duracao, 3)}


def sondar_ffprobe(caminho):
    """Mede um arquivo de insert com o ffprobe. Levanta PlanoNaoMedivel dizendo qual arquivo falhou."""
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
           "stream=width,height,codec_name:stream_side_data=rotation:stream_tags=rotate:format=duration,format_name",
           "-of", "json", str(caminho)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise PlanoNaoMedivel("o ffprobe não está instalado: instale o ffmpeg (brew install ffmpeg) e rode de novo")
    nome = os.path.basename(str(caminho))
    if r.returncode != 0:
        raise PlanoNaoMedivel("o ffprobe não leu %s: %s" % (nome, (r.stderr or "").strip()[:200]))
    try:
        saida = json.loads(r.stdout)
    except ValueError:
        raise PlanoNaoMedivel("o ffprobe devolveu algo ilegível para %s" % nome)
    try:
        return interpretar_ffprobe(saida, imagem=str(caminho).lower().endswith(IMAGENS))
    except PlanoNaoMedivel as e:
        raise PlanoNaoMedivel("%s: %s" % (nome, e))


# --- insumos -----------------------------------------------------------------------------------------------

def _ler_roteiro(pj):
    try:
        lei = roteiro_md.ler_arquivo(pj.roteiro)
    except FileNotFoundError:
        raise PlanoNaoMedivel("roteiro.md não existe em %s: cole o roteiro e grave o projeto antes" % pj.raiz)
    roteiro_md.exigir(lei)
    if lei.livre:
        raise PlanoNaoMedivel(
            "roteiro livre (nenhuma direção entre colchetes): o plano mede o que o roteiro dirige. Escreva as "
            "direções (insert, hook, KEY, lista, cta) no roteiro.md, a partir do rascunho de "
            "entrada.roteiro_livre.esqueleto_dirigido, e meça de novo")
    if not lei.blocos[0]["hook"]:
        raise PlanoNaoMedivel("o primeiro bloco do roteiro precisa de hook: o texto do quadro 0. Exemplo: "
                              "[insert: demo | hook: VOCÊ PERDE | 3 horas por dia | NISSO AQUI]")
    return lei


def _ler_projeto(pj):
    try:
        return modelo.carregar(pj.projeto_json)
    except FileNotFoundError:
        raise PlanoNaoMedivel("projeto.json não existe em %s: crie o projeto antes (vam novo)" % pj.raiz)


def _transcrever(pj, asr):
    if not pj.voz_limpo.is_file():
        raise PlanoNaoMedivel("voz/limpo.mp3 não existe em %s: higienize a voz antes de medir o plano (ou passe o "
                              "alinhamento pronto com --palavras)" % pj.raiz)
    if asr is None:
        g = glossario.carregar(pj.estado)

        def asr(caminho):
            from audio import transcrever as T
            try:
                return T.transcrever(caminho, cache_dir=pj.render_dir / "cache_asr", glossario=g)
            except T.SemTranscritor as e:
                raise PlanoNaoMedivel(str(e))
    return list(asr(pj.voz_limpo))


def _validar_sugestoes(sug):
    if sug is None:
        return {}
    if not isinstance(sug, dict):
        raise ValueError("sugestoes tem que ser um dicionário")
    for campo in sorted(sug):
        if campo in MEDIDOS:
            raise ValueError("'%s' é medido a partir do roteiro, da fala e dos arquivos de insert: não se declara "
                             "(sugestões aceitas: %s)" % (campo, ", ".join(SUGESTOES_ACEITAS)))
        if campo not in SUGESTOES_ACEITAS:
            raise ValueError("sugestão desconhecida '%s' (aceitas: %s)" % (campo, ", ".join(SUGESTOES_ACEITAS)))
    return sug


# --- tempo -------------------------------------------------------------------------------------------------

def _tokens_do_bloco(b):
    """As palavras da fala do bloco, como o plano as conta (sem sinal solto)."""
    return [t for t in b["fala"].split() if normalizar_palavra(t)]


def _numero(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _alinhar(lei, palavras):
    """[[{start, end} de cada palavra do bloco k]], pelo mesmo alinhador do motor."""
    for p in palavras:
        if not (isinstance(p, dict) and "text" in p and _numero(p.get("start")) and _numero(p.get("end"))):
            raise PlanoNaoMedivel("o alinhamento da fala tem que ser uma lista de {text, start, end} (palavra e "
                                  "tempo em segundos, como o audio.transcrever devolve); recebi %r" % (p,))
    pal = [p for p in palavras if str(p["text"]).strip()]
    if not pal:
        raise PlanoNaoMedivel("a transcrição está vazia: nenhuma palavra ouvida em voz/limpo.mp3 (áudio mudo, "
                              "corrompido ou idioma errado)")
    por_bloco = [_tokens_do_bloco(b) for b in lei.blocos]
    todas = [t for tokens in por_bloco for t in tokens]
    alvo = [normalizar_palavra(t) for t in todas]
    fala = [normalizar_palavra(str(p["text"])) for p in pal]
    casadas = sum(m.size for m in difflib.SequenceMatcher(None, alvo, fala, autojunk=False).get_matching_blocks())
    cobertura = casadas / float(len(alvo))
    if cobertura < COBERTURA_MIN:
        raise PlanoNaoMedivel("a fala gravada não bate com o roteiro (só %d%% das palavras do roteiro aparecem nela, "
                              "o mínimo é %d%%): rode o gate_fala_roteiro para ver o que falta, regrave ou corrija "
                              "o roteiro" % (round(cobertura * 100), round(COBERTURA_MIN * 100)))
    alinhadas = build_timeline.align_words(todas, pal)
    saida, i = [], 0
    for tokens in por_bloco:
        saida.append(alinhadas[i:i + len(tokens)])
        i += len(tokens)
    return saida


def _limites(tempos):
    """Fronteiras dos blocos (len = blocos + 1). O bloco 0 começa em 0; cada seguinte, na primeira palavra dele,
    com piso de BLOCO_MIN_S; o fim é o da última palavra."""
    limites = [0.0]
    for t in tempos[1:]:
        limites.append(round(max(t[0]["start"], limites[-1] + BLOCO_MIN_S), 3))
    limites.append(round(max(tempos[-1][-1]["end"], limites[-1] + BLOCO_MIN_S), 3))
    return limites


# --- blocos e inserts --------------------------------------------------------------------------------------

def _blocos(lei, limites, propostos):
    saida = []
    for i, b in enumerate(lei.blocos):
        item = {"i": i, "tipo": b["tipo"]}
        if b["tipo"] == "insert":
            item["insert"] = b["insert"]
            item["layout"] = b["layout"] or "cheio"
        item["fala"] = b["fala"]
        item["s"], item["e"] = limites[i], limites[i + 1]
        if i in propostos:
            item["proposto"] = True
        saida.append(item)
    return saida


def _tratamento(layout, orientacao, duracao):
    if layout == "split":
        return "split"
    if layout == "pip":
        return "pip"
    if not duracao:
        return "imagem"
    return "moldura" if orientacao == "horizontal" else "cheio"


def _congela_s(dur_bloco, ajuste, duracao_fonte):
    """A conta do analise_inserts: o que o bloco consome da fonte menos o que a fonte tem."""
    if not duracao_fonte:                           # imagem estática não congela: é um quadro só por definição
        return 0.0
    cap = ajuste.get("dur_max")
    if cap:
        dur_bloco = min(dur_bloco, float(cap))
    consome = dur_bloco * float(ajuste.get("velocidade", 1.0) or 1.0)
    sobra = max(duracao_fonte - float(ajuste.get("inicio", 0) or 0), 0.0)
    return max(0.0, consome - sobra)


def _visitas(segmentos, bloco):
    """Trechos SEGUIDOS de insert do bloco: fatias coladas são uma visita só (não há rosto no meio)."""
    visitas, dentro = 0, False
    for sg in segmentos:
        if sg["bloco"] != bloco:
            continue
        if sg["tipo"] == "insert" and not dentro:
            visitas += 1
        dentro = sg["tipo"] == "insert"
    return max(visitas, 1)


def _mapa_inserts(pj, blocos, projeto, segmentos, sondar, declarados=None):
    ajustes = projeto.get("inserts") or {}
    ordem = []
    for b in blocos:
        if b["tipo"] == "insert" and b["insert"] not in ordem:
            ordem.append(b["insert"])
    arquivos, faltam = {}, []
    for chave in ordem:
        try:
            achado = pj.insert(chave)
        except ValueError as e:
            raise PlanoNaoMedivel(str(e))
        if achado is None:
            faltam.append(chave)
        arquivos[chave] = achado
    if faltam:
        raise PlanoNaoMedivel("falta o arquivo de insert %s: coloque inserts/<chave>.mp4 (ou .mov, .png...) em %s"
                              % (", ".join("'%s'" % c for c in faltam), pj.inserts_dir))
    mapa = []
    for chave in ordem:
        med = sondar(arquivos[chave])
        usos = [b for b in blocos if b.get("insert") == chave]
        ajuste = ajustes.get(chave, {})
        largura, altura, dur = med["largura"], med["altura"], med["duracao_s"]
        orient = "horizontal" if largura > altura else ("vertical" if altura > largura else "quadrado")
        for b in usos:
            # O LAYOUT PADRÃO (W7.Z): sem preferência escrita, insert horizontal no modo avatar é split. O bloco carrega o
            # layout que o motor vai usar (o `cortes_previstos` e a lista de técnicas leem dele).
            if (declarados or {}).get(b["i"]) is None:
                b["layout"] = layout_efetivo(None, projeto.get("modo"), largura / float(altura) if dur else None) or "cheio"
        mapa.append({
            "chave": chave, "arquivo": pj.relativo(arquivos[chave]), "blocos": [b["i"] for b in usos],
            "largura": largura, "altura": altura, "duracao_s": dur, "orientacao": orient,
            "tratamento": _tratamento(usos[0]["layout"], orient, dur),
            "visitas": max(_visitas(segmentos, b["i"]) for b in usos),
            "congela_s": round(max(_congela_s(b["e"] - b["s"], ajuste, dur) for b in usos), 2)})
    return mapa


# --- ritmo e densidade -------------------------------------------------------------------------------------

def _plano_de_ritmo(blocos, projeto):
    ajustes = projeto.get("inserts") or {}
    entrada = []
    for b in blocos:
        aj = ajustes.get(b.get("insert") or "", {})
        entrada.append({"tipo": "insert" if b["tipo"] == "insert" else "orig", "s": b["s"], "e": b["e"],
                        "crop": aj.get("recorte"), "dur_max": aj.get("dur_max"), "texto": b["fala"]})
    return _ritmo.plano_de_ritmo(entrada)


def _densidade(segmentos, duracao, propostas):
    insert = sum(sg["e"] - sg["s"] for sg in segmentos if sg["tipo"] == "insert")
    return {"fracao_insert": round(insert / duracao, 3), "alvo_min": ALVO_MIN, "alvo_max": ALVO_MAX,
            "piso": PISO, "teto": TETO, "propostas": propostas}


def _bloco_do(seg, blocos):
    meio = (seg["s"] + seg["e"]) / 2.0
    return next((b for b in blocos or () if b["s"] <= meio < b["e"]), None)


def cortes_previstos(segmentos, blocos):
    """Os instantes (relógio da footage a 1x) das fronteiras de plano que a IMAGEM entrega como corte.

    Corte é onde entra na tela conteúdo que não estava nela (W5.X, pendência a): o plano contava TODA fronteira e
    previa 27,2 cortes/min onde o render entregou 18,1. Ficam de fora o salto de escala entre dois planos de
    apresentador (o zoom alterna a base; é o mesmo plano) e a saída de um insert em tela dividida para o apresentador
    (ele já estava na tela, no painel de baixo). O medidor de ritmo recusou exatamente esses dois no render real."""
    cortes = []
    for a, b in zip(segmentos, segmentos[1:]):
        ba, bb = _bloco_do(a, blocos), _bloco_do(b, blocos)
        if a["tipo"] != "insert" and b["tipo"] != "insert":
            continue
        if a["tipo"] == "insert" and b["tipo"] == "insert" and ba is bb:
            continue
        if a["tipo"] == "insert" and b["tipo"] != "insert" and (ba or {}).get("layout") == "split":
            continue
        cortes.append(round(b["s"], 3))
    return cortes


def _ritmo_entregue(segmentos, duracao, aceleracao, blocos=None):
    dur = duracao / aceleracao
    planos = [(sg["e"] - sg["s"]) / aceleracao for sg in segmentos]
    lentos = sum(p for p in planos if p > medir_ritmo.PLANO_LONGO_S)
    return {"cortes_min": round(len(cortes_previstos(segmentos, blocos)) / (dur / 60), 2),
            "frac_acima_6s": round(lentos / dur, 3), "maior_plano_s": round(max(planos), 2),
            "plano_medio_s": round(dur / len(segmentos), 2)}


# --- letterings --------------------------------------------------------------------------------------------

def _borda(token):
    return re.sub(r"^\W+|\W+$", "", token)


def _posicao(norms, alvo, n, bloco):
    achadas = [i for i, w in enumerate(norms) if w == alvo]
    if len(achadas) < n:
        raise PlanoNaoMedivel("a âncora %s#%d do bloco %d não existe na fala" % (alvo, n, bloco))
    return achadas[n - 1]


def _lettering(bloco, lead, key, tokens, norms, pos, tempos, estilo, pilha, cta):
    alvo = norms[pos]
    return {"bloco": bloco, "lead": lead or None, "key": key,
            "ancora": {"palavra": _borda(tokens[pos]), "n": sum(1 for w in norms[:pos + 1] if w == alvo)},
            "s": round(tempos[pos]["start"], 3), "d": 0.0, "estilo": estilo, "pilha": pilha, "cta": cta}


def _letterings(lei, blocos, tempos, projeto, aceleracao, duracao):
    estilo_key = (projeto.get("estilo") or {}).get("lettering", "caixa_nativa")
    saida = []
    for i, b in enumerate(lei.blocos):
        tokens = _tokens_do_bloco(b)
        norms = [normalizar_palavra(t) for t in tokens]
        fim_bloco = blocos[i]["e"]
        if b["tipo"] == "lista":
            itens, cursor, pilha = [], 0, "b%d" % i
            for k, item in enumerate(b["itens"]):
                alvo = [normalizar_palavra(w) for w in item["texto"].split() if normalizar_palavra(w)]
                ini = next((j for j in range(cursor, len(norms) - len(alvo) + 1) if norms[j:j + len(alvo)] == alvo),
                           None) if alvo else None
                if ini is None:
                    raise PlanoNaoMedivel("não achei o item '%s' da lista do bloco %d na fala, na ordem em que ele "
                                          "aparece" % (item["texto"], i))
                cursor = ini + len(alvo)
                pos = ini
                if k == 0 and b["ancora"] and b["ancora"]["explicita"]:
                    pos = _posicao(norms, normalizar_palavra(b["ancora"]["palavra"]), b["ancora"]["n"], i)
                itens.append(_lettering(i, b["lead"] if k == 0 else None, item["texto"], tokens, norms, pos,
                                        tempos[i], estilo_key, pilha, False))
            fim = min(fim_bloco, itens[-1]["s"] + DUR_PILHA_ULTIMO * aceleracao)
            for L in itens:
                L["d"] = fim - L["s"]
            saida += itens
        elif b["key"]:
            anc = b["ancora"]
            pos = _posicao(norms, normalizar_palavra(anc["palavra"]), anc["n"], i)
            cta = b["tipo"] == "cta"
            L = _lettering(i, b["lead"], b["key"], tokens, norms, pos, tempos[i],
                           "seta_cta" if cta else estilo_key, None, cta)
            L["d"] = (duracao - L["s"]) if cta else min(DUR_KEY * aceleracao, fim_bloco - L["s"])
            saida.append(L)
    for L in saida:
        # trunca (não arredonda) em centésimos: s + d nunca passa do fim do anúncio
        L["d"] = math.floor(min(max(L["d"], LETTERING_MIN_S), duracao - L["s"]) * 100 + 1e-9) / 100.0
        if L["d"] <= 0:
            raise PlanoNaoMedivel("o lettering '%s' (bloco %d) pousa depois do fim do anúncio" % (L["key"], L["bloco"]))
    return saida


# --- hook, efeitos, referências ----------------------------------------------------------------------------

def _hook(lei, blocos, segmentos, letterings, projeto, aceleracao, duracao):
    h = lei.blocos[0]["hook"]
    abertura_insert = blocos[0]["tipo"] == "insert" and len(blocos) > 1
    if abertura_insert:
        primeiro_rosto = next((i for i, b in enumerate(blocos) if b["tipo"] != "insert"), 1)
        retorno = blocos[primeiro_rosto]["s"] if primeiro_rosto < len(blocos) else blocos[1]["s"]
        fim = min(retorno + HOOK_FOLGA_ENTREGUE * aceleracao, HOOK_MAX_ENTREGUE * aceleracao)
    else:
        fim = HOOK_PADRAO_ENTREGUE * aceleracao
    janela = JANELA_DO_GANCHO_ENTREGUE * aceleracao
    saida = {"eyebrow": h["eyebrow"], "linha": h["linha"], "destaque": h["destaque"],
             "estilo": (projeto.get("estilo") or {}).get("hook", "editorial"), "fim_s": round(min(fim, duracao), 2)}
    if abertura_insert:
        saida["evento_visual"] = "insert"
    elif any(not L["cta"] and L["s"] < janela for L in letterings):
        saida["evento_visual"] = "punch"
    elif any(0.01 < sg["s"] < janela for sg in segmentos):
        saida["evento_visual"] = "corte"
    return saida


def _efeitos(blocos, letterings, mapa, aceleracao):
    sfx = [{"t": L["s"], "efeito": "tick", "funcao": "pilha"} for L in letterings if L["pilha"]]
    sfx += [{"t": L["s"], "efeito": "boom", "funcao": "key_gigante"} for L in letterings
            if L["estilo"] == "gigante_atras"]
    cta = next((b for b in reversed(blocos) if b["tipo"] == "cta"), None)
    if cta is not None:
        sfx.append({"t": round(max(0.0, cta["s"] - RISER_ANTES_DO_CTA_ENTREGUE * aceleracao), 2),
                    "efeito": "riser", "funcao": "cta"})
    sfx.sort(key=lambda s: s["t"])
    video = dict((m["chave"], m["duracao_s"] > 0) for m in mapa)
    camera = []
    for b in blocos:
        meios = [L for L in letterings if L["bloco"] == b["i"] and not L["cta"] and not L["pilha"]]
        if b["tipo"] == "insert":
            camera.append({"bloco": b["i"], "tipo": "push_in" if video.get(b["insert"]) else "zoom", "t": b["s"]})
        elif b["tipo"] == "lista":
            camera.append({"bloco": b["i"], "tipo": "respiro", "t": b["s"]})
        elif meios:
            camera.append({"bloco": b["i"], "tipo": "punch", "t": meios[0]["s"]})
        else:
            camera.append({"bloco": b["i"], "tipo": "zoom"})
    return {"sfx": sfx, "camera": camera}


def _referencias(blocos, segmentos, mapa, letterings, efeitos, extras):
    tecnicas = []
    tipos = [sg["tipo"] for sg in segmentos]
    if any(a != b for a, b in zip(tipos, tipos[1:])) and "insert" in tipos:
        tecnicas.append("alternância entre insert e rosto")
    if mapa:
        tecnicas.append("corte seco na entrada do insert")
    if any(b.get("layout") == "split" for b in blocos):
        tecnicas.append("split 60/40 com degradê na emenda")
    if any(m["tratamento"] == "moldura" for m in mapa):
        tecnicas.append("insert horizontal inteiro em moldura")
    meio = sorted({L["estilo"] for L in letterings if not L["cta"]})
    if meio:
        tecnicas.append("KEY de pico (%s) alternando com a legenda" % ", ".join(meio).replace("_", " "))
    if any(L["pilha"] for L in letterings):
        tecnicas.append("pilha de lettering com tick por linha")
    if any(L["cta"] and L["estilo"] == "seta_cta" for L in letterings):
        tecnicas.append("seta animada no CTA")
    if any(c["tipo"] == "punch" for c in efeitos["camera"]):
        tecnicas.append("punch de câmera na KEY")
    if not tecnicas:
        tecnicas.append("corte seco entre planos")
    return [{"nome": "padrão do produto", "tecnicas": tecnicas}] + list(extras)


# --- sugestões do diretor ----------------------------------------------------------------------------------

def _texto(valor, rotulo):
    if not (isinstance(valor, str) and valor.strip() and len(valor.strip()) <= 300):
        raise ValueError("%s tem que ser um texto de 1 a 300 caracteres" % rotulo)
    return valor.strip()


def _referencias_sugeridas(sug):
    saida = []
    for k, r in enumerate(sug.get("referencias") or []):
        if not isinstance(r, dict) or not isinstance(r.get("tecnicas"), list) or not r["tecnicas"]:
            raise ValueError("referencias[%d]: precisa de 'nome' e de ao menos uma técnica em 'tecnicas'" % k)
        saida.append({"nome": _texto(r.get("nome"), "referencias[%d].nome" % k),
                      "tecnicas": [_texto(t, "referencias[%d].tecnicas" % k) for t in r["tecnicas"]]})
    return saida


def _propostas(sug, blocos):
    saida = []
    for k, p in enumerate(sug.get("propostas") or []):
        i = p.get("bloco") if isinstance(p, dict) else None
        if not (isinstance(i, int) and 0 <= i < len(blocos)):
            raise ValueError("propostas[%d].bloco %r não é um bloco do roteiro (0 a %d)" % (k, i, len(blocos) - 1))
        if blocos[i]["tipo"] == "insert":
            raise ValueError("propostas[%d]: o bloco %d já tem insert; a proposta é para fala que ficou no rosto"
                             % (k, i))
        opcoes = p.get("opcoes")
        if not isinstance(opcoes, list) or not opcoes:
            raise ValueError("propostas[%d].opcoes: dê ao menos uma opção de insert" % k)
        saida.append({"bloco": i, "fala": blocos[i]["fala"],
                      "opcoes": [_texto(o, "propostas[%d].opcoes" % k) for o in opcoes]})
    return saida


def _propostos(sug, n):
    saida = set()
    for i in sug.get("propostos") or []:
        if not (isinstance(i, int) and 0 <= i < n):
            raise ValueError("propostos: %r não é um bloco do roteiro (0 a %d)" % (i, n - 1))
        saida.add(i)
    return saida


# --- o plano -----------------------------------------------------------------------------------------------

def medir(pj, *, palavras=None, asr=None, sondar=None, sugestoes=None, agora=None):
    """Mede o plano de edição do projeto `pj` (projeto.pastas.PastasProjeto) e devolve o dict do plano.json.

    palavras    o alinhamento da fala: [{text, start, end}] (padrão: transcreve voz/limpo.mp3 com `asr`)
    asr         função caminho -> palavras (padrão: audio.transcrever com o glossário do aluno)
    sondar      função caminho -> {largura, altura, duracao_s} (padrão: ffprobe)
    sugestoes   o que é do diretor (ver o docstring do módulo); declarar algo medido é ValueError
    agora       instante ISO 8601 (padrão: o da chamada)
    """
    sug = _validar_sugestoes(sugestoes)
    lei = _ler_roteiro(pj)
    projeto = _ler_projeto(pj)
    modo = projeto["modo"]
    if "trechos" in sug and modo != "gravado":
        raise ValueError("'trechos' só vale no modo gravado (este projeto é %s)" % modo)
    if modo == "gravado" and not sug.get("trechos"):
        raise PlanoNaoMedivel("modo gravado: o plano precisa dos trechos do take (sugestoes 'trechos': corpo e cta, "
                              "cada um com take, inicio e fim, medidos no áudio limpo)")
    aceleracao = float(projeto["aceleracao"])
    sondar = sondar or sondar_ffprobe
    propostos = _propostos(sug, len(lei.blocos))
    extras_ref = _referencias_sugeridas(sug)

    tempos = _alinhar(lei, palavras if palavras is not None else _transcrever(pj, asr))
    limites = _limites(tempos)
    duracao = limites[-1]
    blocos = _blocos(lei, limites, propostos)
    propostas = _propostas(sug, blocos)

    segmentos = _plano_de_ritmo(blocos, projeto)
    declarados = {i: b["layout"] for i, b in enumerate(lei.blocos) if b["tipo"] == "insert"}
    mapa = _mapa_inserts(pj, blocos, projeto, segmentos, sondar, declarados)
    letterings = _letterings(lei, blocos, tempos, projeto, aceleracao, duracao)
    efeitos = _efeitos(blocos, letterings, mapa, aceleracao)

    plano = {
        "versao": 1, "projeto": pj.slug, "modo": modo,
        "gerado_em": agora if agora is not None else status.instante(),
        "fonte": {"roteiro_sha256": _sha(pj.roteiro), "projeto_sha256": _sha(pj.projeto_json)},
        "duracao_s": duracao,
        "blocos": blocos,
        "mapa_inserts": mapa,
        "hook": _hook(lei, blocos, segmentos, letterings, projeto, aceleracao, duracao),
        "letterings": letterings,
        "densidade": _densidade(segmentos, duracao, propostas),
        "referencias": _referencias(blocos, segmentos, mapa, letterings, efeitos, extras_ref),
        "efeitos": efeitos,
        "ritmo": _ritmo_entregue(segmentos, duracao, aceleracao, blocos),
    }
    plano["checklist"] = checklist.avaliar(plano, projeto)
    if modo == "gravado":
        plano["trechos"] = copy.deepcopy(sug["trechos"])
    _exigir_valido(plano)
    return plano


def _sha(caminho):
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def _exigir_valido(plano):
    problemas = checklist.problemas(plano)
    if problemas:
        raise PlanoInvalido("o plano não passa:\n" + "\n".join("  %s" % p for p in problemas))


def gravar(pj, plano):
    """Valida e grava plano/plano.json (temporário + rename). Plano inválido: nada é criado."""
    _exigir_valido(plano)
    status.escrever_json_atomico(pj.plano_json, plano)
    return pj.plano_json


# --- CLI ---------------------------------------------------------------------------------------------------

def projeto_da_pasta(caminho):
    """PastasProjeto de uma pasta `<estado>/projetos/<slug>`. ValueError se a pasta não tem esse formato."""
    p = Path(caminho).expanduser().absolute()
    if p.parent.name != "projetos":
        raise ValueError("%s não é a pasta de um projeto (esperado _local/projetos/<slug>)" % p)
    return pastas.projeto(p.name, p.parent.parent)


def main(argv=None, sondar=None, asr=None):
    ap = argparse.ArgumentParser(description="Mede o plano de edição do projeto e escreve plano.json e "
                                             "plano_edicao.md.")
    ap.add_argument("slug", nargs="?", help="nome do projeto (com --estado)")
    ap.add_argument("--estado", help="pasta _local (padrão: a do repo)")
    ap.add_argument("--projeto", help="pasta do projeto (_local/projetos/<slug>), no lugar de slug e --estado")
    ap.add_argument("--palavras", help="json com o alinhamento pronto: [{text, start, end}]")
    ap.add_argument("--sugestoes", help="json com referencias, propostas, propostos e trechos")
    args = ap.parse_args(argv)
    try:
        if args.projeto:
            pj = projeto_da_pasta(args.projeto)
        elif args.slug:
            pj = pastas.projeto(args.slug, args.estado)
        else:
            raise ValueError("diga o projeto: slug (com --estado) ou --projeto <pasta>")
        if not pj.raiz.is_dir():
            raise ValueError("o projeto %r não existe em %s" % (pj.slug, pj.raiz))
    except ValueError as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        return 2
    try:
        palavras = status.ler_json(args.palavras) if args.palavras else None
        sugestoes = status.ler_json(args.sugestoes) if args.sugestoes else None
        plano = medir(pj, palavras=palavras, asr=asr, sondar=sondar, sugestoes=sugestoes)
        gravar(pj, plano)
        escrever_md.escrever(pj)
    except PlanoInvalido as e:
        print("REPROVA: %s" % e, file=sys.stderr)
        status.registrar(pj, "plano", "falhou", motivo=str(e)[:400])
        return 1
    except (ValueError, OSError) as e:
        print("ERRO de insumo: %s" % e, file=sys.stderr)
        status.registrar(pj, "plano", "bloqueado", motivo=str(e)[:400])
        return 2
    d, r = plano["densidade"], plano["ritmo"]
    status.registrar(pj, "plano", "ok", detalhes={"densidade": d["fracao_insert"], "cortes_min": r["cortes_min"],
                                                  "blocos": len(plano["blocos"])})
    pend = [i for i in checklist.ITENS if plano["checklist"][i]["status"] == "pendente"]
    print("PLANO: %d blocos, %d insert(s), densidade %s%%, %s cortes/min no arquivo entregue, %d pendência(s) na "
          "checklist.\n  %s\n  %s" % (len(plano["blocos"]), len(plano["mapa_inserts"]),
                                      checklist.numero(d["fracao_insert"] * 100), checklist.numero(r["cortes_min"]),
                                      len(pend), pj.plano_json, pj.plano_md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
