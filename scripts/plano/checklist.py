"""As 6 seções do plano e a checklist do padrão de edição (8 itens + ritmo).

Uma verdade só para o que torna um plano de edição "um plano": quem mede (`plano.medir`), quem
mostra (`plano.escrever_md`), quem assina (`plano.aprovacao`), quem barra (`gates.gate_aprovacao`)
e o comando legado `fase_gate.py aprovar-plano` leem daqui.

AS 6 SEÇÕES (`SECOES`): mapa de inserts, hook, lettering, densidade, referências, efeitos. Plano sem
qualquer uma reprova CITANDO a seção (`problemas`). Antes elas eram palavras procuradas num texto livre
(fase_gate, com mínimo de 800 caracteres); agora são campos do plano.json, e as palavras-chave ficam só
para conferir o plano_edicao.md escrito à mão (`escrever_md.secoes_ausentes`).

A CHECKLIST (`ITENS`): os 8 itens do padrão de edição mais o ritmo. Cada um é `atendido`,
`nao_se_aplica` ou `pendente` COM motivo; pendente sem motivo reprova (`problemas_do_checklist`).
`avaliar` deriva o status do que o plano mediu (inserts, split, letterings, congelamento, ritmo),
nunca de declaração. "Pendente" não impede a aprovação: ela aparece no plano_edicao.md e o aluno decide
com o motivo na frente; o que a checklist proíbe é a pendência muda.

Os limites de ritmo e de congelamento NÃO são redefinidos aqui: vêm de `medir_ritmo` e
`analise_inserts`, os mesmos que medem o arquivo entregue e o gate de entrada.
"""
import math

import analise_inserts
import medir_ritmo
import ritmo
from contratos.validar import validar

# (chave no plano.json, rótulo da seção no plano_edicao.md, palavras-chave para achar a seção num texto
# livre). `*` no fim da palavra-chave = prefixo ("insert*" casa insert, inserts, inserção).
SECOES = (
    ("mapa_inserts", "Mapa de inserts", ("insert*", "asset*")),
    ("hook", "Hook", ("hook",)),
    ("letterings", "Lettering", ("lettering*",)),
    ("densidade", "Densidade", ("densidade",)),
    ("referencias", "Referências", ("referenc*",)),
    ("efeitos", "Efeitos", ("efeito*", "som", "sons")),
)

# Os itens do padrão de edição (brief do diretor, 17-18/08/2026), na ordem do contrato plano.schema.json.
ITENS = ("efeito_por_insert", "elemento_atras", "atencao", "split_dominante", "degrade_emenda",
         "lettering_legenda", "variacao_contexto", "edicao_por_insert", "ritmo")

ROTULOS = {
    "efeito_por_insert": "Efeito visual e sonoro estratégico nos inserts",
    "elemento_atras": "Elementos (logo, texto) atrás do apresentador, dando dinamicidade ao vídeo",
    "atencao": "Elementos chamativos, como setas, que aparecem para prender a atenção",
    "split_dominante": "Divisão da tela com o insert ocupando mais espaço que o apresentador",
    "degrade_emenda": "Degradê escuro entre o apresentador e o insert",
    "lettering_legenda": "Variação entre lettering e legenda, com fonte agradável em ambas",
    "variacao_contexto": "Variação do tipo de inserção conforme o contexto",
    "edicao_por_insert": "A sensação de que a edição foi pensada em cada insert",
    "ritmo": "Ritmo de paridade com a referência (cortes por minuto e tempo parado)",
}

STATUS = ("atendido", "nao_se_aplica", "pendente")

# Ritmo: os limites do arquivo entregue (medir_ritmo.aprova), aqui só espelhados para o plano e o teste.
LIMITES_RITMO = {"cortes_min": (medir_ritmo.MIN_CORTES_MIN, medir_ritmo.MAX_CORTES_MIN),
                 "frac_lenta": medir_ritmo.MAX_FRAC_LENTA,
                 "maior_plano": medir_ritmo.MAX_PLANO_S}
# Congelamento: acima disto o último quadro do insert é clonado de forma visível (analise_inserts).
LIMITE_CONGELA_S = analise_inserts.LIMITE_S

# O menor trecho de rosto que o ritmo aceita no meio de um bloco de insert (o mesmo piso de scripts/ritmo.py).
PISO_ROSTO_S = ritmo.MIN_PLANO

MOTIVO_MAX = 500            # contratos/plano.schema.json: $defs.motivo
COMO_MAX = 300              # idem: $defs.texto


def numero(x, casas=1):
    """Número em português: ponto vira vírgula ('1,4')."""
    return ("%.*f" % (casas, x)).replace(".", ",")


def _corta(texto, limite):
    texto = " ".join(str(texto).split())
    return texto if len(texto) <= limite else texto[:limite - 3].rstrip() + "..."


# --- as 6 seções -----------------------------------------------------------------------------------------

def secoes_ausentes_do_plano(plano):
    """Chaves das seções que o plano não tem (ou tem nulas), na ordem das seções."""
    if not isinstance(plano, dict):
        return [c for c, _, _ in SECOES]
    return [c for c, _, _ in SECOES if plano.get(c) is None]


def problemas_das_secoes(plano):
    """Um problema por seção ausente, citando a seção; mais as exigências de conteúdo que o schema
    não faz (o plano tem que responder o lettering do CTA)."""
    if not isinstance(plano, dict):
        return ["plano.json não é um objeto: gere o plano de novo (vam plano)"]
    rotulos = dict((c, r) for c, r, _ in SECOES)
    probs = ["seção '%s' (%s) ausente do plano: o plano tem que responder as 6 seções antes de ir para o ok"
             % (c, rotulos[c]) for c in secoes_ausentes_do_plano(plano)]
    ls = plano.get("letterings")
    if isinstance(ls, list) and not any(isinstance(l, dict) and l.get("cta") for l in ls):
        probs.append("seção 'letterings' sem o lettering do CTA: o último bloco leva KEY e logo")
    return probs


# --- a checklist -----------------------------------------------------------------------------------------

def problemas_do_checklist(ck):
    """Problemas da checklist: item ausente, status desconhecido, pendente sem motivo."""
    if not isinstance(ck, dict):
        return ["checklist ausente ou fora do formato: os 9 itens (%s) são obrigatórios" % ", ".join(ITENS)]
    probs = []
    for item in ITENS:
        v = ck.get(item)
        if v is None:
            probs.append("checklist: o item '%s' (%s) está ausente" % (item, ROTULOS[item]))
            continue
        st = v.get("status") if isinstance(v, dict) else None
        if st not in STATUS:
            probs.append("checklist: o item '%s' tem status %r; os aceitos são %s"
                         % (item, st, ", ".join(STATUS)))
        elif st == "pendente":
            motivo = v.get("motivo")
            if not (isinstance(motivo, str) and motivo.strip()):
                probs.append("checklist: o item '%s' está pendente sem motivo; pendente sem motivo reprova o "
                             "plano (escreva o que falta)" % item)
    for extra in sorted(set(ck) - set(ITENS)):
        probs.append("checklist: item desconhecido '%s'" % extra)
    return probs


def problemas(plano):
    """Tudo que impede o plano de ser aprovado, em ordem: seções, checklist e contrato. Lista vazia =
    plano completo. Cada mensagem diz a seção, o item ou o campo."""
    probs = problemas_das_secoes(plano)
    if probs:
        return probs
    probs = problemas_do_checklist(plano.get("checklist"))
    contrato = [e for e in validar("plano", plano)
                if not (probs and (e.caminho == "$.checklist" or e.caminho.startswith("$.checklist.")))]
    return probs + ["plano.json fora do contrato: %s" % e for e in contrato]


# --- avaliação: o status de cada item sai da medição -----------------------------------------------------

def _item(status, texto):
    chave = "como" if status == "atendido" else "motivo"
    return {"status": status, chave: _corta(texto, MOTIVO_MAX if chave == "motivo" else COMO_MAX)}


def _inserts(plano):
    return plano.get("mapa_inserts") or []


def _blocos_de_insert(plano):
    return [b for b in plano.get("blocos") or [] if b.get("tipo") == "insert"]


def _atendido(texto):
    return _item("atendido", texto)


def _nao_se_aplica(motivo):
    return _item("nao_se_aplica", motivo)


def _pendente(motivo):
    return _item("pendente", motivo)


def _efeito_por_insert(plano):
    mapa = _inserts(plano)
    if not mapa:
        return _nao_se_aplica("sem insert neste anúncio")
    sem = [m["chave"] for m in mapa if not m.get("tratamento")]
    if sem:
        return _pendente("insert sem tratamento definido: %s" % ", ".join(sem))
    trat = ", ".join(sorted({m["tratamento"] for m in mapa}))
    return _atendido("entrada seca e tratamento por insert (%s); som com função no plano de efeitos" % trat)


def _elemento_atras(projeto):
    if ((projeto or {}).get("estilo") or {}).get("texto_atras"):
        return _atendido("texto atrás da pessoa ligado neste projeto")
    return _nao_se_aplica("texto atrás da pessoa desligado neste projeto")


def _atencao(plano):
    ls = plano.get("letterings") or []
    if any(l.get("cta") and l.get("estilo") == "seta_cta" for l in ls):
        return _atendido("seta animada no CTA")
    if any(l.get("estilo") == "marcador" for l in ls):
        return _atendido("marcador na KEY de peso")
    return _pendente("nenhuma seta no CTA nem marcador em KEY: falta um elemento que prenda a atenção")


def _tem_split(plano):
    return any(b.get("layout") == "split" for b in _blocos_de_insert(plano))


def _split_dominante(plano):
    if not _inserts(plano):
        return _nao_se_aplica("sem insert neste anúncio")
    ns = [str(b["i"]) for b in _blocos_de_insert(plano) if b.get("layout") == "split"]
    if ns:
        return _atendido("split 60/40 com o insert dominante no bloco %s" % ", ".join(ns))
    return _nao_se_aplica("nenhum bloco de insert pede split; os inserts entram em moldura ou tela cheia")


def _degrade_emenda(plano):
    if not _inserts(plano):
        return _nao_se_aplica("sem insert neste anúncio")
    if _tem_split(plano):
        return _atendido("degradê de 90 px na emenda do split")
    return _nao_se_aplica("sem split, não há emenda")


def _lettering_legenda(plano):
    meio = [l for l in plano.get("letterings") or [] if not l.get("cta")]
    if not meio:
        return _pendente("nenhuma KEY no meio do anúncio: o lettering só aparece no CTA, sem variação com a legenda")
    estilos = ", ".join(sorted({l["estilo"].replace("_", " ") for l in meio}))
    return _atendido("%d lettering(s) de pico (%s) alternando com a legenda karaokê" % (len(meio), estilos))


def _variacao_contexto(plano):
    mapa = _inserts(plano)
    if len(mapa) < 2:
        return _nao_se_aplica("menos de dois inserts, não há o que variar")
    trat = sorted({m.get("tratamento") for m in mapa})
    if len(trat) < 2:
        return _pendente("os %d inserts têm o mesmo tratamento (%s): varie conforme o que a fala mostra"
                         % (len(mapa), trat[0]))
    return _atendido("tratamentos diferentes conforme o contexto: %s" % ", ".join(trat))


def _edicao_por_insert(plano):
    mapa = _inserts(plano)
    if not mapa:
        return _nao_se_aplica("sem insert neste anúncio")
    ruins = [m for m in mapa if m.get("congela_s", 0) > LIMITE_CONGELA_S]
    if ruins:
        return _pendente("; ".join("o insert '%s' congela %s s (limite %s s): a fonte acaba antes do bloco"
                                   % (m["chave"], numero(m["congela_s"]), numero(LIMITE_CONGELA_S, 2))
                                   for m in ruins))
    return _atendido("cada insert com tratamento próprio e sem congelamento")


def _dur_max_sem_efeito(plano, projeto):
    """Frases dos `dur_max` que NÃO devolvem o rosto no bloco: o teto cabe no bloco com menos de PISO_ROSTO_S de sobra,
    então o ritmo cobre o bloco inteiro com insert em vez de piscar o rosto (W7.Y, medido na prova como aluno: teto de
    4,0 s em blocos de 4,4 e 4,6 s não mudou os cortes/min). Cada frase traz o teto que funcionaria."""
    ajustes = (projeto or {}).get("inserts") or {}
    por_chave = {}
    for b in _blocos_de_insert(plano):
        cap = (ajustes.get(b.get("insert")) or {}).get("dur_max")
        dur = float(b["e"]) - float(b["s"])
        if cap and float(cap) < dur and dur - float(cap) < PISO_ROSTO_S - 1e-6:
            por_chave.setdefault(b["insert"], []).append((b["i"], dur, float(cap)))
    frases = []
    for chave, itens in por_chave.items():
        blocos = ", ".join("%d (%s s)" % (i, numero(d)) for i, d, _ in itens)
        teto = math.floor(round((min(d for _, d, _ in itens) - PISO_ROSTO_S) * 10, 6)) / 10
        frases.append("dur_max de '%s' (%s s) não devolve o rosto no(s) bloco(s) %s, sobra menos de %s s; só funciona "
                      "até %s s" % (chave, numero(itens[0][2]), blocos, numero(PISO_ROSTO_S), numero(max(teto, 0.0))))
    return frases[:3]


def _ritmo(plano, projeto=None):
    r = plano.get("ritmo") or {}
    m = {"cortes_min": r.get("cortes_min", 0.0), "frac_lenta": r.get("frac_acima_6s", 0.0),
         "maior_plano": r.get("maior_plano_s", 0.0), "planos": [r.get("maior_plano_s", 0.0)]}
    ok, motivos = medir_ritmo.aprova(m)
    if ok:
        return _atendido("%s cortes/min previstos, %s%% do tempo em plano longo, maior plano %s s; a medida que "
                         "vale é a do arquivo entregue"
                         % (numero(m["cortes_min"]), numero(m["frac_lenta"] * 100, 0), numero(m["maior_plano"])))
    return _pendente("; ".join(motivos + _dur_max_sem_efeito(plano, projeto)))


def avaliar(plano, projeto=None):
    """A checklist do plano, com o status de cada item derivado da medição. Não muda o plano."""
    return {
        "efeito_por_insert": _efeito_por_insert(plano),
        "elemento_atras": _elemento_atras(projeto),
        "atencao": _atencao(plano),
        "split_dominante": _split_dominante(plano),
        "degrade_emenda": _degrade_emenda(plano),
        "lettering_legenda": _lettering_legenda(plano),
        "variacao_contexto": _variacao_contexto(plano),
        "edicao_por_insert": _edicao_por_insert(plano),
        "ritmo": _ritmo(plano, projeto),
    }
