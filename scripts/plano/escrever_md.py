"""plano/plano_edicao.md: o plano que o aluno LÊ antes de dar o ok.

O md nasce do plano.json (nunca o contrário) e é uma função pura dele: o mesmo plano.json dá o mesmo
texto, byte a byte. Por isso `confere` consegue provar duas coisas antes da aprovação:

  1. o md é o do plano.json atual (o rodapé declara o sha256 do plano.json que ele mostra);
  2. ninguém editou o md à mão (reescrever do plano.json tem que dar o mesmo texto).

Sem isso, o aluno poderia aprovar um texto e o motor montar outro plano.

Estrutura: visão geral, blocos um a um, as 6 seções (mapa de inserts, hook, lettering, densidade,
referências, efeitos), trechos do take (só no gravado), ritmo previsto, checklist do padrão de edição
e como aprovar. Números em português ('45,8%'), tempos no relógio da fala (antes da aceleração) e o
ritmo no arquivo entregue (já dividido pela aceleração).

`secoes_ausentes(texto)` é a conferência por palavra-chave de um plano escrito à mão em texto livre
(o comando legado `fase_gate.py aprovar-plano <leva> --plano <md>` usa); para o plano.json a conferência
é `checklist.problemas`.
"""
import hashlib
import json
import re
import unicodedata

from entrada import roteiro_md
from plano import checklist
from plano.checklist import SECOES, numero

TAMANHO_MIN = 800          # um plano de menos de 800 caracteres é um carimbo, não um plano (regra do fase_gate)
_RE_SHA = re.compile(r"sha256 ([0-9a-f]{64})")
_RE_PALAVRA = re.compile(r"[a-z0-9]+")


class PlanoSemMd(ValueError):
    """Não há plano.json para escrever (ou ele está ilegível)."""


# --- conferência de um md escrito em texto livre ---------------------------------------------------------

def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFKD", texto.lower()) if not unicodedata.combining(c))


def secoes_ausentes(texto):
    """Chaves das seções (`checklist.SECOES`) que o texto não menciona, na ordem delas. Acento e caixa não
    contam; palavra-chave vale como palavra inteira ou, com `*`, como começo de palavra ('som' não casa
    com 'resumo')."""
    palavras = _RE_PALAVRA.findall(_sem_acento(texto))
    conjunto = set(palavras)

    def casa(chave):
        if chave.endswith("*"):
            return any(p.startswith(chave[:-1]) for p in palavras)
        return chave in conjunto

    return [c for c, _, chaves in SECOES if not any(casa(k) for k in chaves)]


def sha_declarado(texto):
    """O sha256 do plano.json que o rodapé do md declara, ou None."""
    achados = _RE_SHA.findall(texto)
    return achados[-1] if achados else None


# --- renderização ----------------------------------------------------------------------------------------

def _t(x):
    return numero(x, 1)


def _celula(texto):
    return str(texto).replace("|", "\\|").replace("\n", " ")


def _tabela(cabecalho, linhas):
    saida = ["| " + " | ".join(cabecalho) + " |", "|" + "|".join("---" for _ in cabecalho) + "|"]
    saida += ["| " + " | ".join(_celula(c) for c in linha) + " |" for linha in linhas]
    return saida


def _visao_geral(p):
    n_ins = len(p["mapa_inserts"])
    abertura = "Modo %s, %d blocos, %d insert(s)." % (p["modo"], len(p["blocos"]), n_ins)
    if p.get("duracao_s"):
        abertura += " A fala dura %s s no relógio da gravação." % _t(p["duracao_s"])
    return [abertura, "",
            "Este plano foi MEDIDO a partir do seu roteiro, da fala gravada e dos arquivos de insert. "
            "Os números abaixo são conta, não palpite. Os tempos estão no relógio da gravação, antes da "
            "aceleração; o ritmo está no arquivo entregue.", "",
            "Gerado em %s." % p["gerado_em"], ""]


def _blocos(p):
    linhas = []
    for b in p["blocos"]:
        tipo = b["tipo"] + (" " + b["insert"] if b["tipo"] == "insert" and b.get("insert") else "")
        if b.get("proposto"):
            tipo += " (proposto pelo plano, depende do seu ok)"
        linhas.append((b["i"], tipo, b.get("layout") or "", "%s a %s" % (_t(b["s"]), _t(b["e"])), b["fala"]))
    return ["## Blocos, um por um", ""] + _tabela(("#", "Tipo", "Layout", "Tempo (s)", "Fala"), linhas) + [""]


def _cab(chave, n, sufixo=""):
    rotulo = dict((c, r) for c, r, _ in SECOES)[chave]
    return "## %d. %s%s" % (n, rotulo, sufixo)


def _mapa_inserts(p, n):
    saida = [_cab("mapa_inserts", n), ""]
    if not p["mapa_inserts"]:
        return saida + ["Nenhum insert neste anúncio.", ""]
    linhas = [(m["chave"], m["arquivo"], ", ".join(str(b) for b in m["blocos"]),
               "%dx%d" % (m["largura"], m["altura"]),
               "imagem" if not m["duracao_s"] else "%s s" % numero(m["duracao_s"], 2),
               m.get("tratamento", ""), m.get("visitas", ""), "%s s" % _t(m["congela_s"]))
              for m in p["mapa_inserts"]]
    saida += _tabela(("Insert", "Arquivo", "Blocos", "Tamanho", "Duração", "Tratamento", "Visitas", "Congela"),
                     linhas)
    ruins = [m["chave"] for m in p["mapa_inserts"] if m["congela_s"] > checklist.LIMITE_CONGELA_S]
    if ruins:
        saida += ["", "Congelamento acima de %s s em: %s. A fonte acaba antes do bloco e o último quadro é "
                  "repetido." % (numero(checklist.LIMITE_CONGELA_S, 2), ", ".join(ruins))]
    return saida + [""]


def _hook(p, n):
    h = p["hook"]
    linhas = [_cab("hook", n), "",
              "- Eyebrow: %s" % h["eyebrow"], "- Linha: %s" % h["linha"], "- Destaque: %s" % h["destaque"],
              "- Estilo: %s" % h["estilo"],
              "- Fica na tela até %s s (relógio da gravação)." % _t(h["fim_s"])]
    if h.get("evento_visual"):
        linhas.append("- Evento visual nos 3 primeiros segundos entregues: %s." % h["evento_visual"])
    else:
        linhas.append("- Nenhum evento visual (insert, punch ou corte) previsto nos 3 primeiros segundos "
                      "entregues.")
    return linhas + [""]


def _letterings(p, n):
    saida = [_cab("letterings", n), ""]
    linhas = [(l["bloco"], l.get("lead") or "", l["key"], "%s#%d" % (l["ancora"]["palavra"], l["ancora"]["n"]),
               "%s s" % _t(l["s"]), "%s s" % _t(l["d"]), l["estilo"] + (" (CTA)" if l["cta"] else ""),
               l.get("pilha") or "")
              for l in p["letterings"]]
    return saida + _tabela(("Bloco", "LEAD", "KEY", "Âncora", "Entra", "Dura", "Estilo", "Pilha"), linhas) + [""]


def _densidade(p, n):
    d = p["densidade"]
    f = d["fracao_insert"]
    saida = [_cab("densidade", n, " de inserts"), "",
             "Fração do tempo com insert na tela: %s%% (alvo de %s%% a %s%%, piso %s%%, teto %s%%)."
             % (numero(f * 100), numero(d["alvo_min"] * 100, 0), numero(d["alvo_max"] * 100, 0),
                numero(d["piso"] * 100, 0), numero(d["teto"] * 100, 0)), ""]
    if f < d["piso"]:
        saida.append("Situação: abaixo do piso. Só passa com uma exceção declarada em projeto.json "
                     "(excecoes, regra densidade) e o motivo escrito; senão, entre mais insert.")
    elif f < d["alvo_min"]:
        saida.append("Situação: abaixo do alvo. " + (
            "Veja as propostas de insert abaixo, ou aceite a densidade." if d.get("propostas") else
            "Ainda sem propostas de insert: o diretor lista as falas que ficaram no rosto, com 2 ou 3 opções "
            "cada, ou você aceita esta densidade."))
    elif f > d["teto"]:
        saida.append("Situação: acima do teto. Só passa com uma exceção declarada em projeto.json "
                     "(excecoes, regra densidade) e o motivo escrito.")
    elif f > d["alvo_max"]:
        saida.append("Situação: acima do alvo, dentro do teto.")
    else:
        saida.append("Situação: dentro do alvo.")
    props = d.get("propostas") or []
    if props:
        saida += ["", "Propostas de insert para falas que ficaram no rosto:"]
        for pr in props:
            saida.append("- Bloco %d, \"%s\": %s." % (pr["bloco"], pr["fala"], "; ".join(pr["opcoes"])))
    return saida + [""]


def _referencias(p, n):
    saida = [_cab("referencias", n), ""]
    if not p["referencias"]:
        return saida + ["Nenhuma referência escolhida.", ""]
    for r in p["referencias"]:
        saida.append("- %s: %s" % (r["nome"], "; ".join(r["tecnicas"])))
    return saida + [""]


def _efeitos(p, n):
    e = p["efeitos"]
    saida = [_cab("efeitos", n, " (som e câmera)"), "",
             "Som com função: riser antes do CTA, tick por linha de pilha, boom na KEY gigante. Sem whoosh.", ""]
    if e["sfx"]:
        saida += _tabela(("Instante", "Efeito", "Função"),
                         [("%s s" % _t(s["t"]), s["efeito"], s["funcao"]) for s in e["sfx"]]) + [""]
    else:
        saida += ["Nenhum efeito sonoro previsto.", ""]
    if e["camera"]:
        saida += _tabela(("Bloco", "Movimento", "Instante"),
                         [(c["bloco"], c["tipo"], "%s s" % _t(c["t"]) if "t" in c else "") for c in e["camera"]])
        saida.append("")
    return saida


def _trechos(p):
    t = p.get("trechos")
    if not t:
        return []
    linhas = [(parte, x["take"], _t(x["inicio"]), _t(x["fim"])) for parte in ("corpo", "cta") for x in t[parte]]
    return ["## Trechos do take", ""] + _tabela(("Parte", "Take", "Início (s)", "Fim (s)"), linhas) + [""]


def _ritmo(p):
    r = p["ritmo"]
    linhas = ["## Ritmo previsto no arquivo entregue", "",
              "- %s cortes por minuto" % _t(r["cortes_min"]),
              "- %s%% do tempo em plano de mais de 6 s" % numero(r["frac_acima_6s"] * 100, 0),
              "- maior plano: %s s" % _t(r["maior_plano_s"])]
    if "plano_medio_s" in r:
        linhas.append("- plano médio: %s s" % numero(r["plano_medio_s"], 2))
    return linhas + ["", "A régua final é a medição do arquivo entregue; este número é a previsão do plano.", ""]


SITUACAO = {"atendido": "atendido", "nao_se_aplica": "não se aplica", "pendente": "PENDENTE"}


def _checklist(p):
    linhas = []
    for item in checklist.ITENS:
        v = p["checklist"][item]
        linhas.append((checklist.ROTULOS[item], SITUACAO[v["status"]], v.get("como") or v.get("motivo") or ""))
    saida = ["## Checklist do padrão de edição", ""] + _tabela(("Item", "Situação", "Como ou motivo"), linhas)
    pend = [(item, p["checklist"][item]["motivo"]) for item in checklist.ITENS
            if p["checklist"][item]["status"] == "pendente"]
    if pend:
        saida += ["", "Pendências, com o motivo (você decide se aprova assim ou pede ajuste):"]
        saida += ["- %s: %s" % (checklist.ROTULOS[i], m) for i, m in pend]
    return saida + [""]


def _como_aprovar(p):
    slug = p["projeto"]
    return ["## Como aprovar", "",
            "1. Leia o plano acima. As pendências da checklist ficam com você: aprove assim ou peça ajuste.",
            "2. Dê o ok no chat. O diretor registra com `vam aprovar %s --ok \"<o seu ok>\"`." % slug,
            "3. Mudar o roteiro, o projeto, o plano ou os inserts depois do ok vence a aprovação "
            "(\"aprovação vencida\") e o plano volta para o seu ok.", ""]


def renderizar(plano, sha_plano=None):
    """O plano_edicao.md como texto. `sha_plano`: sha256 do plano.json mostrado (vai no rodapé)."""
    linhas = ["# Plano de edição: %s" % plano["projeto"], ""]
    linhas += _visao_geral(plano)
    linhas += _blocos(plano)
    secoes = [_mapa_inserts, _hook, _letterings, _densidade, _referencias, _efeitos]
    for n, fn in enumerate(secoes, 1):
        linhas += fn(plano, n)
    linhas += _trechos(plano)
    linhas += _ritmo(plano)
    linhas += _checklist(plano)
    linhas += _como_aprovar(plano)
    if sha_plano:
        linhas += ["---", "Plano medido: plano.json sha256 %s." % sha_plano]
    return "\n".join(linhas).rstrip("\n") + "\n"


# --- arquivo ---------------------------------------------------------------------------------------------

def _plano_do_disco(pj):
    if not pj.plano_json.is_file():
        raise PlanoSemMd("plano/plano.json não existe em %s: rode vam plano antes" % pj.raiz)
    bruto = pj.plano_json.read_bytes()
    try:
        return json.loads(bruto.decode("utf-8")), hashlib.sha256(bruto).hexdigest()
    except ValueError as e:
        raise PlanoSemMd("plano/plano.json ilegível (%s): rode vam plano de novo" % e)


def escrever(pj):
    """Escreve plano/plano_edicao.md a partir do plano.json que está no disco. Devolve o caminho."""
    plano, sha = _plano_do_disco(pj)
    roteiro_md.escrever_atomico(pj.plano_md, renderizar(plano, sha))
    return pj.plano_md


def confere(pj):
    """(True, "") se o plano_edicao.md é exatamente o que o plano.json atual produz; senão (False, motivo)."""
    if not pj.plano_md.is_file():
        return False, ("plano/plano_edicao.md não existe: o aluno precisa ler o plano antes do ok "
                       "(vam plano escreve o plano_edicao.md)")
    try:
        plano, sha = _plano_do_disco(pj)
    except PlanoSemMd as e:
        return False, str(e)
    texto = pj.plano_md.read_text(encoding="utf-8")
    declarado = sha_declarado(texto)
    if declarado != sha:
        return False, ("o plano_edicao.md é de outro plano.json (o md declara %s e o plano.json atual é %s): "
                       "rode vam plano e mostre o plano novo ao aluno"
                       % ((declarado or "nenhum sha")[:12], sha[:12]))
    if texto != renderizar(plano, sha):
        return False, ("o plano_edicao.md foi editado à mão e não corresponde mais ao plano.json: "
                       "rode vam plano para escrevê-lo de novo (o md é derivado, não se edita)")
    return True, ""
