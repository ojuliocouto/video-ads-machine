"""roteiro.md + projeto.json -> os 3 arquivos que o motor atual consome (W1.B).

O motor (gen_ad_v2, produzir_roteiro, build_composite e quem lê o inserts.json) ainda lê o
formato antigo. Este módulo é a ponte: o aluno escreve o roteiro.md e o projeto.json, e daqui
saem, por anúncio (`ad`):

  <ad>_leva.txt        uma linha por bloco, `[instrução] fala`. A fala vai verbatim; a instrução
                       usa as palavras que o `parser_roteiro` do motor classifica:
                         apresentador          apresentador de frente para a câmera        (orig)
                         apresentador + KEY    apresentador + lettering | LEAD: .. | KEY: ..  (lettering)
                         cta                   apresentador + lettering + logo | ..          (lettering_logo)
                         lista                 apresentador de frente para a câmera        (orig; a pilha vai no config)
                         insert                inserção de vídeo: #N#                      (insert)
  <ad>_inserts.json    UMA entrada por bloco de insert, NA ORDEM dos blocos. É assim que
                       build_composite, medir_ritmo, prancha_direcao e analise_inserts leem
                       (o n-ésimo insert é o n-ésimo valor do dict). A chave é `#N#`, N = ordem
                       do insert: o motor acha o insert por "chave contida na instrução", então
                       uma chave com delimitadores nunca está contida na chave de outro bloco
                       (`foo` e `foo-2` se confundiriam) nem em palavra que o parser classifica
                       (`logo` em `catalogo` viraria cartão de logo em tela cheia). O nome que
                       aparece na tela vai em `labels` (rótulo do projeto ou a chave legível).
  <ad>_<look>.json     config do overlay: ad, look, format, avatar, out_dir, hook, cta_label,
                       [cta_sem_lead], kw_phrases, letterings, [labels].

Como o roteiro vira config:
  - hook (só no 1º bloco) -> {eyebrow, l1 = linha, accent = destaque, [style: punch]}; o motor
    antigo exige hook, então roteiro sem hook é recusado aqui.
  - ênfase `*palavra*` -> kw_phrases, na ordem e sem repetir. O motor marca a frase em todo o
    anúncio, não só no trecho onde ela foi escrita.
  - KEY de apresentador, insert e cta -> um lettering {lead, key, anchor, nth, dur}.
  - lista -> uma pilha: um lettering por item, mesmo `pilha` ("lista1", "lista2"...), o LEAD
    só no primeiro. Cada item pousa na primeira palavra DELE, achada pela sequência de palavras
    do item (não pela primeira ocorrência da palavra). Como no anúncio de produção, o LEAD
    nasce junto do 1º item; uma âncora explícita na lista vale para a primeira linha.
  - `nth` é a ocorrência da palavra no ANÚNCIO INTEIRO (o laço do gen_ad_v2 conta todas as
    palavras de todos os blocos), então o `#n` do roteiro, que é por bloco, é somado às
    ocorrências dos blocos anteriores.
    As palavras são as da fala dividida em espaços, como o motor divide a narração; o que o
    parser dele tira da pontuação solta do começo ("... e") não conta, porque pontuação
    sozinha não tem palavra pela norma do motor.
  - layout: split -> "split": true; pip -> "pip": true; cheio e sem preferência -> nada (é o
    padrão do motor). O resto do ajuste do insert vem do `projeto.inserts` (inicio -> start,
    velocidade -> speed, zoom, recorte -> crop, exposicao, dur_max, texto_proprio).

A aceleração não entra no config: quem acelera é o build_composite.

Só biblioteca padrão; sem rede e sem planilha. Os arquivos são determinísticos (mesma entrada,
mesmos bytes), então o sha256 deles serve para amarrar a aprovação do plano.
"""
import copy
import hashlib
import json
import re
import unicodedata
from pathlib import Path

from . import roteiro_md

DUR_KEY = 2.2             # mesmo padrão do gen_ad_v2 (L.get("dur", 2.2))
DUR_CTA = 2.6             # o lettering do CTA vive um pouco mais (valor ajustado à mão nos anúncios de referência)
DUR_PILHA_ITEM = 1.4      # itens do meio da pilha
DUR_PILHA_ULTIMO = 2.2    # o último segura a pilha na tela

INSTR_APRESENTADOR = "apresentador de frente para a câmera"
INSTR_LETTERING = "apresentador + lettering"
INSTR_CTA = "apresentador + lettering + logo"
INSTR_INSERT = "inserção de vídeo"

_RE_AD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class ErroParaMotor(ValueError):
    """O roteiro ou o projeto não dá para entregar ao motor atual; a mensagem diz o que falta."""


class Motor:
    """Os 3 arquivos do motor atual, em memória.

    ad, look, formato   nomes usados nos arquivos
    leva                texto de <ad>_leva.txt
    inserts             dict de <ad>_inserts.json (ordem = ordem dos blocos de insert)
    config              dict de <ad>_<look>.json
    """

    __slots__ = ("ad", "look", "formato", "leva", "inserts", "config")

    def __init__(self, ad, look, formato, leva, inserts, config):
        self.ad = ad
        self.look = look
        self.formato = formato
        self.leva = leva
        self.inserts = inserts
        self.config = config

    def inserts_json(self):
        return _json(self.inserts)

    def config_json(self):
        return _json(self.config)

    def nomes(self):
        sufixo = "_1x1" if self.formato == "1x1" else ""
        return {"leva": f"{self.ad}_leva.txt",
                "inserts": f"{self.ad}_inserts.json",
                "config": f"{self.ad}_{self.look}{sufixo}.json"}

    def __repr__(self):
        return f"Motor(ad={self.ad!r}, look={self.look!r}, inserts={len(self.inserts)})"


def _json(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def _norm_motor(w):
    """A norma de palavra do gen_ad_v2 (`norm`): é com ela que o motor casa a âncora.

    Se o motor mudar a dele, esta tem que mudar junto: o `nth` depende de as duas contarem
    as mesmas ocorrências.
    """
    w = unicodedata.normalize("NFKD", w)
    w = "".join(c for c in w if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", w.lower())


def _palavra_da_ancora(token):
    return re.sub(r"^\W+|\W+$", "", token).lower()


# --- entradas ----------------------------------------------------------------------------------

def _ler_roteiro(roteiro):
    if isinstance(roteiro, str):
        lei = roteiro_md.ler(roteiro)
    elif isinstance(roteiro, roteiro_md.Leitura):
        lei = roteiro
    elif isinstance(roteiro, dict) and "blocos" in roteiro:
        lei = roteiro_md.Leitura("", roteiro.get("livre", False), roteiro["blocos"], [])
    else:
        raise ErroParaMotor("o roteiro tem que ser o texto do roteiro.md, uma Leitura ou o dict da leitura")
    if lei.erros:
        raise ErroParaMotor("o roteiro.md não passa na convenção:\n" + roteiro_md.formatar_erros(lei.erros))
    if lei.livre:
        raise ErroParaMotor("roteiro livre (sem nenhuma direção entre colchetes): o plano propõe as direções "
                            "e o aluno aprova antes de gerar para o motor (entrada.roteiro_livre.esqueleto_dirigido)")
    if not lei.blocos:
        raise ErroParaMotor("roteiro sem nenhum bloco")
    return lei


def _ler_projeto(projeto):
    if isinstance(projeto, (str, Path)):
        try:
            dados = json.loads(Path(projeto).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ErroParaMotor(f"não consegui ler o projeto.json ({projeto}): {e}") from None
    elif isinstance(projeto, dict):
        dados = copy.deepcopy(projeto)
    else:
        raise ErroParaMotor("o projeto tem que ser o dict do projeto.json ou o caminho dele")
    erros = roteiro_md.contrato().validar("projeto", dados)
    if erros:
        raise ErroParaMotor("o projeto.json não passa no contrato:\n"
                            + "\n".join(f"  {e}" for e in erros[:8]))
    if dados["modo"] != "avatar":
        raise ErroParaMotor(f"modo {dados['modo']!r}: este caminho serve o modo avatar; gravado e oneshot "
                            "têm pipeline próprio e não usam leva/inserts/config do overlay")
    return dados


def _nome_do_ad(ad, projeto):
    ad = projeto["slug"] if ad is None else ad
    if not isinstance(ad, str) or not _RE_AD.match(ad):
        raise ErroParaMotor(f"nome do anúncio {ad!r} inválido: letras, números, _ e -, sem espaço nem barra "
                            "(vira nome de arquivo)")
    return ad


def _arquivo_do_insert(inserts_dir, chave):
    pasta = Path(inserts_dir)
    achados = sorted(p for p in pasta.glob(chave + ".*") if p.is_file() and not p.name.startswith("."))
    if not achados:
        raise ErroParaMotor(f"falta o arquivo do insert '{chave}': coloque {pasta.name}/{chave}.mp4 "
                            f"(ou .mov, .png...) em {pasta}")
    if len(achados) > 1:
        raise ErroParaMotor(f"o insert '{chave}' tem mais de um arquivo ({', '.join(p.name for p in achados)}): "
                            "deixe só um")
    return str(achados[0])


# --- instrução e letterings --------------------------------------------------------------------

def _texto_de_direcao(b, campo):
    valor = b[campo]
    if valor and ("KEY:" in valor or "LEAD:" in valor):
        raise ErroParaMotor(f"{campo.upper()} {valor!r} tem 'KEY:' ou 'LEAD:' dentro: o parser do motor "
                            "dividiria a instrução nesse ponto")
    return valor


def _instrucao(b, marca_insert):
    tipo = b["tipo"]
    lead, key = _texto_de_direcao(b, "lead"), _texto_de_direcao(b, "key")
    sufixo = (f" | LEAD: {lead}" if lead and key else "") + (f" | KEY: {key}" if key else "")
    if tipo == "insert":
        return f"{INSTR_INSERT}: {marca_insert}{sufixo}"
    if tipo == "cta":
        return INSTR_CTA + sufixo
    if tipo == "apresentador":
        return (INSTR_LETTERING + sufixo) if key else INSTR_APRESENTADOR
    if tipo == "lista":
        return INSTR_APRESENTADOR
    raise ErroParaMotor(f"tipo de bloco {tipo!r} sem equivalente no motor")


def _tokens_com_palavra(tokens):
    return [(i, _norm_motor(t)) for i, t in enumerate(tokens) if _norm_motor(t)]


def _posicao_padrao(tokens, bloco):
    for i, t in enumerate(tokens):
        if _norm_motor(t):
            return i
    raise ErroParaMotor(f"o bloco {bloco} não tem nenhuma palavra onde ancorar o lettering")


def _posicao_explicita(tokens, palavra, n, bloco):
    alvo, achadas = _norm_motor(palavra), 0
    for i, t in enumerate(tokens):
        if alvo and _norm_motor(t) == alvo:
            achadas += 1
            if achadas == n:
                return i
    raise ErroParaMotor(f"a âncora {palavra}#{n} do bloco {bloco} não existe na fala do jeito que o motor conta")


def _achar_sequencia(com_palavra, item, a_partir_de):
    """Índice (em `com_palavra`) onde a sequência de palavras do item começa, a partir de um ponto."""
    normas = [n for _, n in com_palavra]
    for ini in range(a_partir_de, len(normas) - len(item) + 1):
        if normas[ini:ini + len(item)] == item:
            return ini
    return None


class _Contagem:
    """Quantas vezes cada palavra (pela norma do motor) já passou nos blocos anteriores."""

    def __init__(self):
        self.antes = {}

    def nth(self, tokens, posicao):
        alvo = _norm_motor(tokens[posicao])
        no_bloco = sum(1 for t in tokens[:posicao + 1] if _norm_motor(t) == alvo)
        return self.antes.get(alvo, 0) + no_bloco

    def fechar_bloco(self, tokens):
        for t in tokens:
            n = _norm_motor(t)
            if n:
                self.antes[n] = self.antes.get(n, 0) + 1


def _lettering(lead, key, tokens, posicao, contagem, dur, pilha=None):
    L = {"lead": lead or "", "key": key, "anchor": _palavra_da_ancora(tokens[posicao]),
         "nth": contagem.nth(tokens, posicao), "dur": dur}
    if pilha:
        L["pilha"] = pilha
    return L


def _letterings_do_bloco(b, indice, tokens, contagem, n_lista):
    """Os letterings do config que este bloco gera (lista vazia se não tem lettering)."""
    tipo = b["tipo"]
    if tipo == "lista":
        return _letterings_da_pilha(b, indice, tokens, contagem, n_lista)
    if b["key"] is None:
        return []
    anc = b["ancora"]
    if anc and (anc["explicita"] or anc.get("da_key")):      # da_key: a âncora padrão do cta, a palavra do KEY
        posicao = _posicao_explicita(tokens, anc["palavra"], anc["n"], indice + 1)
    else:
        posicao = _posicao_padrao(tokens, indice + 1)
    return [_lettering(b["lead"], b["key"], tokens, posicao, contagem, DUR_CTA if tipo == "cta" else DUR_KEY)]


def _letterings_da_pilha(b, indice, tokens, contagem, n_lista):
    grupo = f"lista{n_lista}"
    com_palavra = _tokens_com_palavra(tokens)
    itens, saida, cursor = b["itens"], [], 0
    for k, item in enumerate(itens):
        palavras = [n for n in (_norm_motor(t) for t in item["texto"].split()) if n]
        ini = _achar_sequencia(com_palavra, palavras, cursor) if palavras else None
        if ini is None:
            raise ErroParaMotor(f"não achei o item {item['texto']!r} da lista do bloco {indice + 1} na fala, "
                                "na ordem em que ele aparece")
        cursor = ini + len(palavras)
        posicao = com_palavra[ini][0]
        primeira = k == 0
        if primeira and b["ancora"] and b["ancora"]["explicita"]:
            posicao = _posicao_explicita(tokens, b["ancora"]["palavra"], b["ancora"]["n"], indice + 1)
        chave = f"{item['marcador']} {item['texto']}" if item["marcador"] else item["texto"]
        dur = DUR_PILHA_ULTIMO if k == len(itens) - 1 else DUR_PILHA_ITEM
        saida.append(_lettering(b["lead"] if primeira else "", chave, tokens, posicao, contagem, dur, grupo))
    return saida


# --- montagem ----------------------------------------------------------------------------------

def _rotulo(chave, ajuste):
    return ajuste.get("rotulo") or chave.replace("-", " ").replace("_", " ")


def _entrada_do_insert(arquivo, b, ajuste):
    cfg = {"file": arquivo, "start": ajuste.get("inicio", 0), "speed": ajuste.get("velocidade", 1.0)}
    if b["layout"] == "split":
        cfg["split"] = True
    elif b["layout"] == "pip":
        cfg["pip"] = True
    if "zoom" in ajuste:
        cfg["zoom"] = ajuste["zoom"]
    if "recorte" in ajuste:
        cfg["crop"] = ajuste["recorte"]
    if "exposicao" in ajuste:
        cfg["exposicao"] = ajuste["exposicao"]
    if "dur_max" in ajuste:
        cfg["dur_max"] = ajuste["dur_max"]
    if ajuste.get("texto_proprio"):
        cfg["texto_proprio"] = True
    return cfg


def _hook(blocos, projeto):
    h = blocos[0]["hook"]
    if not h:
        raise ErroParaMotor("o primeiro bloco precisa de hook: o motor atual não monta o anúncio sem o texto do "
                            "quadro 0. Exemplo: [insert: demo | hook: VOCÊ PERDE | 3 horas por dia | NISSO AQUI]")
    saida = {"eyebrow": h["eyebrow"], "l1": h["linha"], "accent": h["destaque"]}
    if (projeto.get("estilo") or {}).get("hook") == "punch":
        saida["style"] = "punch"
    return saida


def gerar(roteiro, projeto, *, avatar, out_dir, inserts_dir, ad=None, look=None):
    """Gera os 3 arquivos do motor atual (em memória) a partir do roteiro e do projeto.

    roteiro      texto do roteiro.md, `Leitura` de entrada.roteiro_md ou o dict da leitura
    projeto      dict do projeto.json (ou o caminho dele); tem que passar no contrato
    avatar       caminho do avatar.mp4 que vai no config
    out_dir      pasta de render que vai no config
    inserts_dir  pasta com os arquivos `<chave>.*` dos inserts do roteiro
    ad           nome do anúncio nos arquivos (padrão: slug do projeto)
    look         nome do look (padrão: o do projeto)

    Levanta ErroParaMotor, com a mensagem do que falta, em vez de gerar arquivo que o motor
    não consegue usar. Não escreve nada em disco (ver `gravar`).
    """
    lei = _ler_roteiro(roteiro)
    proj = _ler_projeto(projeto)
    nome_ad = _nome_do_ad(ad, proj)
    nome_look = look or proj["look"]
    ajustes = proj.get("inserts") or {}
    blocos = lei.blocos
    hook = _hook(blocos, proj)

    linhas, inserts, labels, letterings, kw = [], {}, {}, [], []
    contagem = _Contagem()
    n_insert = n_lista = 0
    for i, b in enumerate(blocos):
        marca = None
        if b["tipo"] == "insert":
            n_insert += 1
            marca = f"#{n_insert}#"
            chave = b["insert"]
            ajuste = ajustes.get(chave, {})
            inserts[marca] = _entrada_do_insert(_arquivo_do_insert(inserts_dir, chave), b, ajuste)
            labels[marca] = _rotulo(chave, ajuste)
        if b["tipo"] == "lista":
            n_lista += 1
        tokens = b["fala"].split()
        letterings.extend(_letterings_do_bloco(b, i, tokens, contagem, n_lista))
        contagem.fechar_bloco(tokens)
        linhas.append(f"[{_instrucao(b, marca)}] {b['fala']}")
        for e in b["enfase"]:
            if e not in kw:
                kw.append(e)

    cta = proj.get("cta") or {}
    config = {"ad": nome_ad, "look": nome_look, "format": proj.get("formato", "9x16"),
              "avatar": str(avatar), "out_dir": str(out_dir), "hook": hook,
              "cta_label": cta.get("label", "saiba mais")}
    if cta.get("sem_lead"):
        config["cta_sem_lead"] = True
    config["kw_phrases"] = kw
    config["letterings"] = letterings
    if labels:
        config["labels"] = labels
    return Motor(nome_ad, nome_look, config["format"], "\n".join(linhas) + "\n", inserts, config)


def gravar(motor, pasta_inputs, pasta_configs):
    """Grava os 3 arquivos (por temporário + rename) e devolve o caminho e o sha256 de cada um.

    A leva e o inserts.json vão para `pasta_inputs` (onde o motor procura `<ad>_leva.txt` e
    `<ad>_inserts.json`) e o config para `pasta_configs`. Regravar a mesma coisa dá os mesmos
    bytes, então o sha256 do inserts.json serve para amarrar a aprovação do plano.
    """
    nomes = motor.nomes()
    destinos = {"leva": (Path(pasta_inputs) / nomes["leva"], motor.leva.encode("utf-8")),
                "inserts": (Path(pasta_inputs) / nomes["inserts"], motor.inserts_json().encode("utf-8")),
                "config": (Path(pasta_configs) / nomes["config"], motor.config_json().encode("utf-8"))}
    saida = {}
    for chave, (caminho, dados) in destinos.items():
        roteiro_md.escrever_atomico(caminho, dados)
        saida[chave] = {"caminho": str(caminho), "sha256": hashlib.sha256(dados).hexdigest()}
    return saida
