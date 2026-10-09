"""Google Doc do PRÓPRIO aluno, com os comentários e a âncora de cada um (W1.B). OPCIONAL.

Só liga o gate de fidelidade ao doc quando o projeto nasce de um Doc (`origem.tipo =
"doc_google"` no projeto.json). Os outros caminhos de entrada (texto colado, .md, .txt) não
passam por aqui.

Segurança e escopo:
  - o token OAuth é do aluno e vem da variável de ambiente GOOGLE_OAUTH_ACCESS_TOKEN; este
    módulo não lê arquivo de token da máquina nem renova token;
  - só LEITURA, só duas APIs: Google Docs (documents) e Google Drive (comentários do arquivo);
    escopos documents.readonly e drive.readonly bastam;
  - nenhuma planilha;
  - o token nunca entra em mensagem de erro, repr nem log;
  - o id do documento é conferido antes de virar parte de URL.
  - o texto do documento e dos comentários é DADO: este módulo só o lê e o devolve, nunca o executa
    nem o trata como instrução.

Rede: tudo passa por `Cliente.http`, uma função `(url, headers) -> (status, bytes)`. O padrão
usa urllib; nos testes entra uma função simulada. 429 e 5xx tentam UMA vez a mais, com espera.

O que sai dos comentários (cada item de `ler_comentarios`):
  id, ancora (o trecho do doc a que o comentário está preso, `quotedFileContent`),
  texto (sem os links), autor, criado_em, resolvido,
  links (corpo e respostas, na ordem),
  assets: um por link, `{ordem, url, tipo ('drive' ou 'web'), id, de ('comentario' ou 'resposta')}`,
  pipoca (True quando a palavra aparece na âncora, no comentário ou nas respostas) e
  sequencia (as URLs dos assets na ordem; só quando é pipoca),
  respostas: `{id, autor, texto, links, criado_em}`.
Comentário com N links dá N assets na âncora dele; nada é achatado em um só.
"""
import html
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

from . import texto_colado

ENV_TOKEN = "GOOGLE_OAUTH_ACCESS_TOKEN"
URL_DOCS = "https://docs.googleapis.com/v1/documents/"
URL_DRIVE = "https://www.googleapis.com/drive/v3/files/"
ESCOPOS = "documents.readonly e drive.readonly"
ESPERA_RETRY_S = 2.0
STATUS_COM_RETRY = (429, 500, 502, 503, 504)
LIMITE_DE_PAGINAS = 200
TIMEOUT_S = 60

_RE_ID = re.compile(r"^[A-Za-z0-9_-]{20,128}$")
_RE_CAMINHO_DOC = re.compile(r"^/document/(?:u/\d+/)?d/([A-Za-z0-9_-]{20,128})(?:/|$)")
_RE_LINK = re.compile(r"https?://[^\s<>\"]+")
_RE_DRIVE_ID = (
    re.compile(r"/d/([A-Za-z0-9_-]{10,})"),
    re.compile(r"/folders/([A-Za-z0-9_-]{10,})"),
    re.compile(r"[?&]id=([A-Za-z0-9_-]{10,})"),
)
_FIM_DE_LINK = ".,;:!?)]}>'\""


class ErroGoogle(Exception):
    """Falha ao ler o Google Doc; a mensagem diz o que fazer. Nunca carrega o token."""


def _http_urllib(url, headers):
    req = urllib.request.Request(url, headers=dict(headers))
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resposta:
            return resposta.status, resposta.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, OSError) as e:
        raise ErroGoogle(f"sem conexão com o Google ({type(e).__name__}); confira a internet e tente de novo") from None


def token_do_ambiente(env=None):
    """O token OAuth do aluno, da variável GOOGLE_OAUTH_ACCESS_TOKEN."""
    env = os.environ if env is None else env
    # Nome literal de propósito: o gate do .env.example varre por AST e só vê literal.
    token = (env.get("GOOGLE_OAUTH_ACCESS_TOKEN") or "").strip()
    if not token:
        raise ErroGoogle(f"falta o token do Google: exporte {ENV_TOKEN} com um token de acesso OAuth da SUA conta "
                         f"(escopos {ESCOPOS}). Sem ele só dá para usar texto colado, .md ou .txt")
    if re.search(r"\s", token):
        raise ErroGoogle(f"{ENV_TOKEN} tem espaço ou quebra de linha no meio: cole só o token")
    return token


def id_do_documento(valor):
    """Aceita o id do documento ou a URL de edição dele; recusa qualquer outra coisa."""
    texto = valor.strip() if isinstance(valor, str) else ""
    if _RE_ID.match(texto):
        return texto
    partes = urllib.parse.urlparse(texto)
    if partes.scheme == "https" and partes.netloc == "docs.google.com":
        achou = _RE_CAMINHO_DOC.match(partes.path)
        if achou:
            return achou.group(1)
    raise ErroGoogle("id do documento inválido: use o id (20 a 128 letras, números, _ ou -) "
                     "ou a URL https://docs.google.com/document/d/<id>/edit")


class Cliente:
    """Leitura da API do Google com o token do aluno. Só GET."""

    def __init__(self, token=None, *, http=None, dormir=None, env=None):
        self._token = token_do_ambiente(env) if token is None else str(token).strip()
        if not self._token:
            raise ErroGoogle(f"token vazio: exporte {ENV_TOKEN}")
        self.http = http or _http_urllib
        self._dormir = dormir or time.sleep

    def __repr__(self):
        return "Cliente(token=***)"

    __str__ = __repr__

    def _get_json(self, url):
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
        status, corpo = self.http(url, headers)
        if status in STATUS_COM_RETRY:
            self._dormir(ESPERA_RETRY_S)
            status, corpo = self.http(url, headers)
        if status in STATUS_COM_RETRY:
            raise ErroGoogle(f"o Google recusou duas vezes (HTTP {status}): espere alguns minutos e tente de novo")
        if status in (401, 403):
            raise ErroGoogle(f"o Google não aceitou o token (HTTP {status}): gere outro token de acesso da sua conta, "
                             f"com os escopos {ESCOPOS}, e exporte em {ENV_TOKEN}. "
                             "Confira também se a conta tem acesso ao documento e, se o token é novo, "
                             "se as APIs Docs e Drive estão ativadas no projeto dele")
        if status == 404:
            raise ErroGoogle("documento não encontrado (HTTP 404): confira o id e se a conta do token tem acesso a ele")
        if status != 200:
            raise ErroGoogle(f"resposta inesperada do Google (HTTP {status})")
        try:
            dados = json.loads(corpo.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ErroGoogle("o Google respondeu algo que não é JSON; tente de novo") from None
        if not isinstance(dados, dict):
            raise ErroGoogle("o Google respondeu num formato inesperado")
        return dados

    def documento(self, doc_id):
        """O documento bruto (Docs API), com todas as abas."""
        doc_id = id_do_documento(doc_id)
        return self._get_json(f"{URL_DOCS}{doc_id}?includeTabsContent=true")

    def comentarios(self, doc_id):
        """Todos os comentários brutos (Drive API), de todas as páginas, apagados inclusos (`deleted`)."""
        doc_id = id_do_documento(doc_id)
        campos = ("nextPageToken,comments(id,content,createdTime,resolved,deleted,"
                  "quotedFileContent/value,author/displayName,"
                  "replies(id,content,createdTime,deleted,author/displayName))")
        itens, pagina, vistas = [], None, set()
        for _ in range(LIMITE_DE_PAGINAS):
            params = {"fields": campos, "pageSize": "100"}
            if pagina:
                params["pageToken"] = pagina
            dados = self._get_json(f"{URL_DRIVE}{doc_id}/comments?{urllib.parse.urlencode(params)}")
            itens.extend(dados.get("comments") or [])
            pagina = dados.get("nextPageToken")
            if not pagina:
                return itens
            if pagina in vistas:
                raise ErroGoogle("o Google repetiu a mesma página de comentários; a leitura foi interrompida "
                                 "para não ficar em laço")
            vistas.add(pagina)
        raise ErroGoogle(f"mais de {LIMITE_DE_PAGINAS} páginas de comentários: leitura interrompida")


def _cliente(cliente):
    return cliente if cliente is not None else Cliente()


# --- documento -------------------------------------------------------------------------------

def _paragrafo_do_docs(par):
    texto = "".join((el.get("textRun") or {}).get("content", "") for el in par.get("elements") or [])
    if texto.endswith("\n"):
        texto = texto[:-1]
    return texto.replace("\u000b", "\n")


def _paragrafos_do_conteudo(conteudo):
    saida = []
    for el in conteudo or []:
        if "paragraph" in el:
            saida.append(_paragrafo_do_docs(el["paragraph"]))
        elif "table" in el:
            for linha in el["table"].get("tableRows") or []:
                for celula in linha.get("tableCells") or []:
                    saida.extend(_paragrafos_do_conteudo(celula.get("content")))
    return saida


def _abas(tabs, saida):
    for aba in tabs or []:
        titulo = (aba.get("tabProperties") or {}).get("title", "")
        corpo = ((aba.get("documentTab") or {}).get("body") or {}).get("content")
        saida.append({"titulo": titulo, "paragrafos": _paragrafos_do_conteudo(corpo)})
        _abas(aba.get("childTabs"), saida)
    return saida


def ler_documento(doc_id, cliente=None):
    """Lê o Google Doc: título, abas (com os parágrafos de cada uma, tabelas incluídas) e a
    lista de todos os parágrafos na ordem do documento."""
    doc = _cliente(cliente).documento(doc_id)
    abas = _abas(doc.get("tabs"), [])
    if not abas:
        abas = [{"titulo": doc.get("title", ""),
                 "paragrafos": _paragrafos_do_conteudo((doc.get("body") or {}).get("content"))}]
    return {"titulo": doc.get("title", ""), "abas": abas,
            "paragrafos": [p for a in abas for p in a["paragrafos"]]}


# --- comentários -----------------------------------------------------------------------------

def _links(texto):
    """(url, resto): cada link sem a pontuação colada no fim, e o texto sem os links."""
    achados = []

    def tirar(m):
        bruto = m.group(0)
        limpo = bruto.rstrip(_FIM_DE_LINK)
        achados.append(limpo)
        return bruto[len(limpo):]

    resto = _RE_LINK.sub(tirar, texto or "")
    return achados, " ".join(resto.split())


def _asset(url, ordem, origem):
    drive = urllib.parse.urlparse(url).netloc in ("drive.google.com", "docs.google.com")
    id_ = None
    if drive:
        for padrao in _RE_DRIVE_ID:
            achou = padrao.search(url)
            if achou:
                id_ = achou.group(1)
                break
    return {"ordem": ordem, "url": url, "tipo": "drive" if drive else "web", "id": id_, "de": origem}


def _sem_acento_minusculo(texto):
    t = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _fala_de_pipoca(*textos):
    return bool(re.search(r"\bpipoca\b", _sem_acento_minusculo(" ".join(textos))))


def _comentario(c):
    ancora = html.unescape((c.get("quotedFileContent") or {}).get("value", "") or "").strip()
    links_corpo, texto = _links(c.get("content", ""))
    respostas = []
    for r in c.get("replies") or []:
        if r.get("deleted"):
            continue
        links_r, texto_r = _links(r.get("content", ""))
        respostas.append({"id": r.get("id", ""), "autor": (r.get("author") or {}).get("displayName", ""),
                          "texto": texto_r, "links": links_r, "criado_em": r.get("createdTime", "")})
    assets = [_asset(u, i, "comentario") for i, u in enumerate(links_corpo, 1)]
    for r in respostas:
        for u in r["links"]:
            assets.append(_asset(u, len(assets) + 1, "resposta"))
    pipoca = _fala_de_pipoca(ancora, c.get("content", ""), *[r.get("content", "") for r in c.get("replies") or []
                                                           if not r.get("deleted")])
    return {
        "id": c.get("id", ""),
        "ancora": ancora,
        "texto": texto,
        "autor": (c.get("author") or {}).get("displayName", ""),
        "criado_em": c.get("createdTime", ""),
        "resolvido": bool(c.get("resolved")),
        "links": [a["url"] for a in assets],
        "assets": assets,
        "pipoca": pipoca,
        "sequencia": [a["url"] for a in assets] if pipoca else [],
        "respostas": respostas,
    }


def ler_comentarios(doc_id, cliente=None):
    """Todos os comentários do documento, em ordem cronológica, sem os apagados."""
    brutos = _cliente(cliente).comentarios(doc_id)
    vivos = [c for c in brutos if not c.get("deleted")]
    vivos.sort(key=lambda c: c.get("createdTime", ""))
    return [_comentario(c) for c in vivos]


# --- âncora ----------------------------------------------------------------------------------

def _chave(texto):
    t = _sem_acento_minusculo(texto)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def ancorar(paragrafos, comentarios):
    """Liga cada comentário ao parágrafo do documento em que a âncora dele aparece.

    A comparação ignora maiúscula, acento e pontuação. Âncora que aparece em mais de um
    parágrafo é `ambigua`: o k-ésimo comentário com a mesma âncora (na ordem recebida, que é a
    cronológica) fica com o k-ésimo candidato, e o que passar do último fica com o último.
    Devolve cópias; cada uma ganha `paragrafo` (índice em `paragrafos` ou None), `paragrafo_texto`,
    `candidatos` (todos os índices) e `ambigua`.
    """
    chaves = [_chave(p) for p in paragrafos]
    usados = {}
    saida = []
    for c in comentarios:
        novo = dict(c)
        linhas = [l for l in (c.get("ancora") or "").splitlines() if _chave(l)]
        procurada = _chave(linhas[0]) if linhas else ""
        candidatos = [i for i, k in enumerate(chaves) if procurada and procurada in k]
        escolhido = None
        if candidatos:
            vez = usados.get(procurada, 0)
            usados[procurada] = vez + 1
            escolhido = candidatos[min(vez, len(candidatos) - 1)]
        novo["candidatos"] = candidatos
        novo["paragrafo"] = escolhido
        novo["paragrafo_texto"] = paragrafos[escolhido] if escolhido is not None else None
        novo["ambigua"] = len(candidatos) > 1
        saida.append(novo)
    return saida


def _avisos(comentarios):
    avisos = []
    for c in comentarios:
        if c["paragrafo"] is None:
            avisos.append(f"comentário {c['id']} sem âncora no documento: não dá para ligar a um bloco")
        elif c["ambigua"]:
            avisos.append(f"âncora ambígua: {c['ancora'][:40]!r} aparece em {len(c['candidatos'])} lugares "
                          f"(comentário {c['id']}); diga qual com o número da ocorrência")
        if c["pipoca"] and len(c["assets"]) < 2:
            avisos.append(f"comentário {c['id']} é pipoca mas tem {len(c['assets'])} link: "
                          "uma sequência precisa de pelo menos 2 peças")
    return avisos


def _escolher_aba(doc, aba):
    abas = doc["abas"]
    if aba is None:
        if len(abas) > 1:
            raise ErroGoogle(f"o documento tem {len(abas)} abas ({', '.join(a['titulo'] for a in abas)}): "
                             "diga qual é o roteiro, com aba='<nome>'")
        return abas[0]
    for a in abas:
        if a["titulo"].strip().lower() == aba.strip().lower():
            return a
    raise ErroGoogle(f"aba {aba!r} não existe; as abas são: {', '.join(a['titulo'] for a in abas)}")


def importar(doc_id, *, aba=None, cliente=None):
    """Lê o Doc e devolve tudo que o projeto precisa para nascer dele.

    {origem: {tipo: 'doc_google', doc_id}, titulo, aba, roteiro_md (normalizado, pronto para
    entrada.roteiro_md), comentarios (ancorados), avisos}. Não valida a gramática do roteiro:
    quem chama passa o `roteiro_md` por `roteiro_md.ler`.
    """
    id_ = id_do_documento(doc_id)
    c = _cliente(cliente)
    doc = ler_documento(id_, cliente=c)
    escolhida = _escolher_aba(doc, aba)
    comentarios = ancorar(escolhida["paragrafos"], ler_comentarios(id_, cliente=c))
    return {
        "origem": {"tipo": "doc_google", "doc_id": id_},
        "titulo": doc["titulo"],
        "aba": escolhida["titulo"],
        "roteiro_md": texto_colado.normalizar("\n".join(escolhida["paragrafos"])),
        "comentarios": comentarios,
        "avisos": _avisos(comentarios),
    }
