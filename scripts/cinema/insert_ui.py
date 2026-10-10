"""Inserts de UI em HTML (C8): uma tela de app inventada, sem marca nem foto, que o aluno preenche com
um JSON e que vira um mp4 na proporção do painel do anúncio.

    templates/inserts_ui/<template>.html  +  dados.json  ->  inserts/<chave>.mp4

Os sete templates: whatsapp (conversa), terminal (agente rodando), kanban (funil com um cartão que se
move), dashboard (KPIs que sobem e gráfico), agenda (horas ocupadas virando livres), contador (número
grande) e fluxo (caixas ligadas por fios com pulso). `exemplo(<template>)` devolve o JSON completo de
cada um, e é o mesmo que o golden dos testes usa.

## Como o texto entra no HTML

O template é HTML com marcadores `{{campo}}`, `{{#cada lista}}...{{/cada}}` e `{{#se campo}}...{{/se}}`.
O motor de template (`_Modelo`) lê o arquivo UMA vez, monta uma árvore e preenche por ela: o valor de
um campo nunca é relido como template, então `{{...}}` dentro do texto do aluno aparece como está. Todo
valor passa por `html.escape(quote=True)`. Números chegam já formatados em pt-BR (4.380 e 14,90), e a
animação em JavaScript só lê atributos `data-*` com números que o Python formatou.

## Como o tempo funciona

Cada quadro é função só do tempo: a página expõe `window.__vamSeek(t)` e registra em
`window.__timelines.main` um objeto com `seek`, que é o que o HyperFrames chama. Nada de relógio,
aleatório ou rede. A animação é leve: entrada escalonada dos elementos e um push-in de 3% no palco.

## Proporção do painel

O palco é lógico (1920, 1400 ou 1200 de largura, conforme a proporção) e sai escalado para a
largura x altura pedida. `horizontal` (1920x1080) entra inteiro na moldura de navegador, como todo asset
horizontal (`moldura.py`). `painel` (1080x1150) é o painel de cima do split 60/40 e preenche sem moldura.

## O render

`motor_padrao()` escolhe, nesta ordem: o `node_modules/.bin/hyperframes` do repo e, sem ele, um Chrome do sistema dirigido pelo Playwright (screenshot por
quadro e ffmpeg). Sem nenhum dos dois sai UMA linha com `bash scripts/setup.sh`. O motor é um objeto
chamável `motor(pedido)`: nos testes entra um falso, e o render de verdade fica no teste `lento`.
A saída é atômica: o vídeo nasce num temporário ao lado do destino e só então vira o arquivo final.
"""
import copy
import html
import math
import os
import re
import shutil
import subprocess
import tempfile
from collections import namedtuple
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = RAIZ / "templates" / "inserts_ui"
FONTES_DIR = RAIZ / "fonts"

FPS_PADRAO = 30                 # o mesmo do motor (footage/filtros_avatar.FPS)
FPS_MIN, FPS_MAX = 10, 60
DUR_PADRAO = 4.0
DUR_MIN, DUR_MAX = 1.0, 20.0

PROPORCOES = {"horizontal": (1920, 1080), "painel": (1080, 1150),
              "vertical": (1080, 1920), "quadrado": (1080, 1080)}
PROPORCAO_PADRAO = "horizontal"
LADO_MIN, LADO_MAX = 320, 4096

NOMES = ("whatsapp", "terminal", "kanban", "dashboard", "agenda", "contador", "fluxo")
DESTAQUE_PADRAO = "#4c8dff"

# Fontes do repo que o BASE pede (arquivo em fonts/). O render copia só estas.
FONTES = ("inter-400.woff2", "inter-600.woff2", "inter-700.woff2", "montserrat-500.woff2",
          "montserrat-600.woff2", "archivo-800.woff2", "playfair-italic-600.woff2")

MENSAGEM_SEM_MOTOR = ("Sem motor de render para o insert: rode `bash scripts/setup.sh` "
                      "(instala o HyperFrames) e tente de novo.")


class DadosInvalidos(ValueError):
    """O JSON do aluno não serve para o template; a mensagem nomeia o campo."""


class TemplateInexistente(ValueError):
    pass


class ProporcaoInvalida(ValueError):
    pass


class SemMotorDeRender(RuntimeError):
    pass


class RenderFalhou(RuntimeError):
    pass


PedidoRender = namedtuple("PedidoRender", "template html pasta saida largura altura fps quadros dur")
Resultado = namedtuple("Resultado", "saida largura altura fps quadros dur motor")


# ======================================================================================
# Templates e exemplos
# ======================================================================================

def templates():
    """Os nomes dos templates, na ordem em que o mostruário os lista."""
    return NOMES


def _conferir_template(nome):
    if nome not in NOMES:
        raise TemplateInexistente("template desconhecido: %r (existem: %s)" % (nome, ", ".join(NOMES)))
    return nome


_EXEMPLOS = {
    "whatsapp": {
        "busca": "Pesquisar conversa",
        "conversa_nome": "Cliente",
        "contatos": [
            {"nome": "Cliente", "previa": "digitando…", "nao_lidas": 2},
            {"nome": "Lead novo", "previa": "Pode me mandar os valores?"},
            {"nome": "Aluno", "previa": "Consegui! Muito obrigado"},
            {"nome": "Parceiro", "previa": "Perfeito, fechado então"},
        ],
        "mensagens": [
            {"quem": "cliente", "texto": "Boa noite! Comprei hoje e ainda não recebi o acesso, podem verificar?",
             "hora": "22:47"},
            {"quem": "voce", "texto": "Oi! Verifiquei aqui: seu acesso foi reenviado agora para o seu e-mail. "
                                      "Confere a caixa de entrada.", "hora": "22:47"},
            {"quem": "cliente", "texto": "Chegou! Rapidinho, obrigado!", "hora": "22:48"},
        ],
        "digitando": "respondendo…",
    },
    "terminal": {
        "titulo_janela": "agente de prospecção: rodando",
        "linhas": [
            {"tipo": "comando", "texto": 'agente prospectar --nicho "clinicas" --cidade "Curitiba"'},
            {"tipo": "ok", "texto": "38 empresas encontradas no mapa"},
            {"tipo": "passo", "texto": "visitando o site da empresa"},
            {"tipo": "ok", "texto": "contato extraído"},
            {"tipo": "passo", "texto": "lendo a página de serviços…"},
            {"tipo": "ok", "texto": "abordagem personalizada escrita", "nota": "(fisioterapia esportiva)"},
            {"tipo": "ok", "texto": "mensagem enviada e lead salvo no CRM"},
            {"tipo": "passo", "texto": "próxima empresa (5 de 38)…"},
        ],
    },
    "kanban": {
        "titulo": "Funil comercial movido pelo agente",
        "colunas": [
            {"nome": "Novos", "cartoes": [
                {"nome": "Empresa A", "valor": "R$ 4.500", "etiqueta": "chegou pelo site"},
                {"nome": "Empresa B", "valor": "R$ 2.800", "etiqueta": "indicação"}]},
            {"nome": "Qualificados", "cartoes": [
                {"nome": "Empresa C", "valor": "R$ 6.200", "etiqueta": "agente qualificou"},
                {"nome": "Empresa D", "valor": "R$ 3.900", "etiqueta": "respondeu a proposta"}]},
            {"nome": "Proposta", "cartoes": [
                {"nome": "Empresa E", "valor": "R$ 12.000", "etiqueta": "follow-up automático"}]},
            {"nome": "Fechado", "cartoes": [
                {"nome": "Empresa F", "valor": "R$ 5.400", "etiqueta": "ganhou ontem"}]},
        ],
        "movimento": {"da_coluna": "Proposta", "para_coluna": "Fechado", "cartao": "Empresa E",
                      "etiqueta_final": "ganhou agora"},
        "destaque": DESTAQUE_PADRAO,
    },
    "dashboard": {
        "titulo": "Anúncios: resultados",
        "periodo": "últimos 7 dias, atualizado agora pelo agente",
        "kpis": [
            {"rotulo": "Investido", "valor": 4380, "prefixo": "R$ ", "nota": "dentro do orçamento"},
            {"rotulo": "Leads", "valor": 212, "nota": "custo caindo"},
            {"rotulo": "Custo por lead", "valor": 14.9, "casas": 2, "prefixo": "R$ ", "nota": "-18% na semana"},
            {"rotulo": "Retorno", "valor": 4.7, "casas": 1, "sufixo": "x", "nota": "subindo"},
        ],
        "grafico": {"titulo": "Leads por dia",
                    "pontos": [12, 30, 22, 48, 64, 58, 90, 104, 96, 128, 150, 142, 170]},
        "destaque": DESTAQUE_PADRAO,
    },
    "agenda": {
        "titulo": "Sua semana, depois de cada agente",
        "dias": ["SEG", "TER", "QUA", "QUI", "SEX"],
        "horas": ["9h", "11h", "13h", "15h"],
        "ocupados": ["responder mensagens", "fazer proposta", "planilha", "suporte", "relatório",
                     "posts da semana", "cobranças", "triagem de e-mail", "agendar reuniões", "follow-up"],
        "livre_rotulo": "LIVRE",
    },
    "contador": {
        "prefixo": "+",
        "valor": 6000,
        "legenda": "clientes atendidos até hoje",
        "destaque": DESTAQUE_PADRAO,
    },
    "fluxo": {
        "titulo": "Fluxo do agente: rodando",
        "etapas": [
            [{"nome": "Novo lead chegou", "estado": "disparado", "icone": "1"}],
            [{"nome": "Responde no chat", "estado": "enviado", "icone": "2"},
             {"nome": "Registra na planilha", "estado": "salvo", "icone": "3"}],
            [{"nome": "Atualiza o CRM", "estado": "movido", "icone": "4"}],
            [{"nome": "Avisa você", "estado": "resumo pronto", "icone": "5"}],
        ],
        "destaque": DESTAQUE_PADRAO,
    },
}


def exemplo(template):
    """O JSON completo de um template (cópia: quem recebe pode mexer à vontade)."""
    return copy.deepcopy(_EXEMPLOS[_conferir_template(template)])


# ======================================================================================
# Validação dos dados
# ======================================================================================

_RE_COR = re.compile(r"^#[0-9a-fA-F]{6}$")
_LIMITE_NUM = 1e12


def _txt(maximo, opc=False, padrao=None):
    return {"k": "txt", "max": maximo, "opc": opc, "padrao": padrao}


def _num(minimo=-_LIMITE_NUM, maximo=_LIMITE_NUM, inteiro=False, opc=False, padrao=None):
    return {"k": "num", "min": minimo, "max": maximo, "int": inteiro, "opc": opc, "padrao": padrao}


def _esc(valores, padrao=None):
    return {"k": "esc", "valores": tuple(valores), "opc": False, "padrao": padrao}


def _cor():
    return {"k": "cor", "opc": True, "padrao": DESTAQUE_PADRAO}


def _lista(item, minimo, maximo):
    return {"k": "lista", "item": item, "min": minimo, "max": maximo, "opc": False, "padrao": None}


def _obj(campos, opc=False):
    return {"k": "obj", "campos": campos, "opc": opc, "padrao": None}


_SPEC = {
    "whatsapp": _obj({
        "busca": _txt(40, padrao="Pesquisar conversa"),
        "conversa_nome": _txt(40),
        "contatos": _lista(_obj({"nome": _txt(40), "previa": _txt(60), "nao_lidas": _num(1, 99, True, opc=True)}),
                           1, 5),
        "mensagens": _lista(_obj({"quem": _esc(("cliente", "voce")), "texto": _txt(160),
                                  "hora": _txt(12, opc=True)}), 2, 6),
        "digitando": _txt(30, padrao="respondendo…"),
    }),
    "terminal": _obj({
        "titulo_janela": _txt(50),
        "linhas": _lista(_obj({"tipo": _esc(("comando", "ok", "passo")), "texto": _txt(100),
                               "nota": _txt(50, opc=True)}), 2, 10),
        # W7.W: `grande` leva a fonte a 56 px no palco (29 px no card de 1036 px do quadro entregue): legível no celular
        "tamanho": _esc(("normal", "grande"), padrao="normal"),
    }),
    "kanban": _obj({
        "titulo": _txt(60),
        "colunas": _lista(_obj({"nome": _txt(24),
                                "cartoes": _lista(_obj({"nome": _txt(32), "valor": _txt(18, opc=True),
                                                        "etiqueta": _txt(32, opc=True)}), 1, 4)}), 3, 5),
        "movimento": _obj({"da_coluna": _txt(24), "para_coluna": _txt(24), "cartao": _txt(32),
                           "etiqueta_final": _txt(32, opc=True)}, opc=True),
        "destaque": _cor(),
    }),
    "dashboard": _obj({
        "titulo": _txt(50),
        "periodo": _txt(70, opc=True),
        "kpis": _lista(_obj({"rotulo": _txt(28), "valor": _num(), "casas": _num(0, 2, True, padrao=0),
                             "prefixo": _txt(10, opc=True), "sufixo": _txt(10, opc=True),
                             "nota": _txt(36, opc=True)}), 3, 4),
        "grafico": _obj({"titulo": _txt(40), "pontos": _lista(_num(0, _LIMITE_NUM), 5, 16)}),
        "destaque": _cor(),
    }),
    "agenda": _obj({
        "titulo": _txt(60),
        "dias": _lista(_txt(12), 3, 7),
        "horas": _lista(_txt(12), 2, 6),
        "ocupados": _lista(_txt(30), 1, 12),
        "livre_rotulo": _txt(14, padrao="LIVRE"),
    }),
    "contador": _obj({
        "prefixo": _txt(6, opc=True),
        "valor": _num(0, _LIMITE_NUM),
        "casas": _num(0, 2, True, padrao=0),
        "legenda": _txt(70),
        "destaque": _cor(),
    }),
    "fluxo": _obj({
        "titulo": _txt(50),
        "etapas": _lista(_lista(_obj({"nome": _txt(30), "estado": _txt(24), "icone": _txt(6)}), 1, 2), 2, 5),
        "destaque": _cor(),
    }),
}


def _mostrar(valor):
    texto = repr(valor)
    return texto if len(texto) <= 40 else texto[:37] + "..."


def _validar_no(no, valor, caminho):
    k = no["k"]
    if k == "obj":
        if not isinstance(valor, dict):
            raise DadosInvalidos("%s: precisa ser um objeto JSON (veio %s)" % (caminho, _mostrar(valor)))
        for chave in valor:
            if chave not in no["campos"]:
                raise DadosInvalidos("%s.%s: campo desconhecido (valem: %s)"
                                     % (caminho, chave, ", ".join(no["campos"])))
        saida = {}
        for chave, sub in no["campos"].items():
            if chave not in valor:
                if sub["padrao"] is not None:
                    saida[chave] = sub["padrao"]
                    continue
                if sub["opc"]:
                    saida[chave] = None
                    continue
                raise DadosInvalidos("%s.%s: campo obrigatório que falta" % (caminho, chave))
            saida[chave] = _validar_no(sub, valor[chave], "%s.%s" % (caminho, chave))
        return saida
    if k == "lista":
        if not isinstance(valor, list):
            raise DadosInvalidos("%s: precisa ser uma lista (veio %s)" % (caminho, _mostrar(valor)))
        if not no["min"] <= len(valor) <= no["max"]:
            raise DadosInvalidos("%s: tem %d itens; precisa ter de %d a %d"
                                 % (caminho, len(valor), no["min"], no["max"]))
        return [_validar_no(no["item"], v, "%s[%d]" % (caminho, i)) for i, v in enumerate(valor)]
    if k == "txt":
        if not isinstance(valor, str):
            raise DadosInvalidos("%s: precisa ser um texto (veio %s)" % (caminho, _mostrar(valor)))
        if any(ord(c) < 32 or ord(c) == 127 for c in valor):
            raise DadosInvalidos("%s: precisa ser uma linha só, sem quebra nem caractere de controle" % caminho)
        if not valor.strip():
            raise DadosInvalidos("%s: está vazio" % caminho)
        if len(valor) > no["max"]:
            raise DadosInvalidos("%s: tem %d caracteres; o máximo é %d" % (caminho, len(valor), no["max"]))
        return valor
    if k == "num":
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
            raise DadosInvalidos("%s: precisa ser um número finito (veio %s)" % (caminho, _mostrar(valor)))
        if no["int"]:
            if float(valor) != int(valor):
                raise DadosInvalidos("%s: precisa ser um número inteiro (veio %s)" % (caminho, _mostrar(valor)))
            valor = int(valor)
        if not no["min"] <= valor <= no["max"]:
            raise DadosInvalidos("%s: fora da faixa de %s a %s (veio %s)"
                                 % (caminho, no["min"], no["max"], _mostrar(valor)))
        return valor
    if k == "esc":
        if not isinstance(valor, str) or valor not in no["valores"]:
            raise DadosInvalidos("%s: precisa ser um destes: %s (veio %s)"
                                 % (caminho, ", ".join(no["valores"]), _mostrar(valor)))
        return valor
    if k == "cor":
        if not isinstance(valor, str) or not _RE_COR.match(valor):
            raise DadosInvalidos("%s: precisa ser uma cor em hexadecimal de 6 dígitos, como #4c8dff (veio %s)"
                                 % (caminho, _mostrar(valor)))
        return valor
    raise AssertionError(k)


def _conferir_kanban(d):
    mov = d["movimento"]
    if not mov:
        return
    colunas = d["colunas"]
    nomes = [c["nome"] for c in colunas]
    if mov["da_coluna"] not in nomes:
        raise DadosInvalidos("dados.movimento.da_coluna: não há coluna com o nome %r (colunas: %s)"
                             % (mov["da_coluna"], ", ".join(nomes)))
    if mov["para_coluna"] not in nomes:
        raise DadosInvalidos("dados.movimento.para_coluna: não há coluna com o nome %r (colunas: %s)"
                             % (mov["para_coluna"], ", ".join(nomes)))
    if mov["da_coluna"] == mov["para_coluna"]:
        raise DadosInvalidos("dados.movimento.para_coluna: precisa ser outra coluna, diferente de da_coluna")
    origem = colunas[nomes.index(mov["da_coluna"])]
    if mov["cartao"] not in [c["nome"] for c in origem["cartoes"]]:
        raise DadosInvalidos("dados.movimento.cartao: não há cartão %r na coluna %r"
                             % (mov["cartao"], mov["da_coluna"]))


def validar(template, dados):
    """Dados do aluno -> dados normalizados (padrões preenchidos). DadosInvalidos nomeia o campo."""
    _conferir_template(template)
    normal = _validar_no(_SPEC[template], dados, "dados")
    if template == "kanban":
        _conferir_kanban(normal)
    return normal


# ======================================================================================
# Números em pt-BR
# ======================================================================================

def formatar_ptbr(valor, casas=0):
    """4380 -> '4.380'; 14.9 com 2 casas -> '14,90'; -1234.5 com 1 -> '-1.234,5'."""
    corpo = format(abs(valor), ",.%df" % casas)
    corpo = corpo.replace(",", "\0").replace(".", ",").replace("\0", ".")
    if valor < 0 and any(c in "123456789" for c in corpo):
        corpo = "-" + corpo
    return corpo


def _num_js(valor):
    """Número para atributo data-*: repr do float (sem notação que o parseFloat não leia)."""
    return repr(float(valor))


# ======================================================================================
# Proporção, geometria e tempo
# ======================================================================================

def resolver_proporcao(texto):
    """'painel' | '16:9' | '1080x1150' -> (largura, altura) em pixels, ambas pares."""
    if isinstance(texto, str) and texto in PROPORCOES:
        return PROPORCOES[texto]
    if isinstance(texto, str):
        m = re.fullmatch(r"(\d+)x(\d+)", texto.strip())
        if m:
            w, h = int(m.group(1)), int(m.group(2))
            if not (LADO_MIN <= w <= LADO_MAX and LADO_MIN <= h <= LADO_MAX):
                raise ProporcaoInvalida("proporção %r fora da faixa: cada lado de %d a %d pixels"
                                        % (texto, LADO_MIN, LADO_MAX))
            if w % 2 or h % 2:
                raise ProporcaoInvalida("proporção %r: largura e altura precisam ser pares (H.264)" % texto)
            return w, h
        m = re.fullmatch(r"(\d+):(\d+)", texto.strip())
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > 0 and b > 0:
                w = 1920 if a > b else 1080            # horizontal parte de 1920; quadrado e vertical, de 1080
                h = int(round(w * b / a)) // 2 * 2
                if LADO_MIN <= min(w, h) and max(w, h) <= LADO_MAX:
                    return w, h
    raise ProporcaoInvalida("proporção inválida: %r (use %s, 16:9, 4:5 ou 1080x1150)"
                            % (texto, ", ".join(PROPORCOES)))


def _palco(largura, altura):
    """Palco lógico (largura, altura, escala): o template é desenhado nele e sai escalado."""
    razao = largura / altura
    lw = 1920 if razao >= 1.3 else (1400 if razao >= 0.85 else 1200)
    escala = largura / lw
    return lw, int(math.ceil(altura / escala)), escala


def _quadros(dur, fps):
    if isinstance(dur, bool) or not isinstance(dur, (int, float)) or not math.isfinite(dur) \
            or not DUR_MIN <= dur <= DUR_MAX:
        raise ValueError("duração inválida: %s (de %g a %g segundos)" % (_mostrar(dur), DUR_MIN, DUR_MAX))
    if isinstance(fps, bool) or not isinstance(fps, int) or not FPS_MIN <= fps <= FPS_MAX:
        raise ValueError("fps inválido: %s (de %d a %d)" % (_mostrar(fps), FPS_MIN, FPS_MAX))
    return max(1, round(dur * fps))


# ======================================================================================
# Contexto de cada template (o que o HTML precisa além dos dados)
# ======================================================================================

_PALETA_FLUXO = ("#4c8dff", "#22c55e", "#a855f7", "#f59e0b", "#ef4444", "#14b8a6")


def _inicial(texto):
    for c in texto:
        if c.isalnum():
            return c.upper()
    return "?"


def _ctx_whatsapp(d, geo):
    ativo_marcado = False
    for c in d["contatos"]:
        c["inicial"] = _inicial(c["nome"])
        c["ativo"] = (not ativo_marcado) and c["nome"] == d["conversa_nome"]
        ativo_marcado = ativo_marcado or c["ativo"]
    d["conversa_inicial"] = _inicial(d["conversa_nome"])
    digitou = False
    for i, m in enumerate(d["mensagens"]):
        m["classe"] = "out" if m["quem"] == "voce" else "in"
        m["enviada"] = m["quem"] == "voce"
        m["digita_antes"] = (not digitou) and m["quem"] == "voce" and i > 0
        digitou = digitou or m["digita_antes"]


def _ctx_terminal(d, geo):
    glifos = {"comando": "$", "ok": "✓", "passo": "→"}
    for ln in d["linhas"]:
        ln["glifo"] = glifos[ln["tipo"]]
    d["classe_tamanho"] = " grande" if d.get("tamanho") == "grande" else ""
    d["tamanho_grande"] = "1" if d.get("tamanho") == "grande" else ""


def _ctx_kanban(d, geo):
    mov = d["movimento"]
    de = para = -1
    if mov:
        nomes = [c["nome"] for c in d["colunas"]]
        de, para = nomes.index(mov["da_coluna"]), nomes.index(mov["para_coluna"])
    d["mov_ativo"] = "1" if mov else "0"
    d["mov_de"], d["mov_para"] = str(de), str(para)
    d["mov_etiqueta_final"] = (mov or {}).get("etiqueta_final") or ""
    marcado = False                                   # só o primeiro cartão com esse nome se move
    for i, col in enumerate(d["colunas"]):
        col["qtd"] = str(len(col["cartoes"]))
        for c in col["cartoes"]:
            c["move"] = bool(mov) and not marcado and i == de and c["nome"] == mov["cartao"]
            marcado = marcado or c["move"]
            c["tag_visivel"] = bool(c["etiqueta"]) or (c["move"] and bool(d["mov_etiqueta_final"]))


def _ctx_dashboard(d, geo):
    for k in d["kpis"]:
        k["prefixo"] = k["prefixo"] or ""
        k["sufixo"] = k["sufixo"] or ""
        k["valor_fmt"] = formatar_ptbr(k["valor"], k["casas"])
        k["final"] = k["prefixo"] + k["valor_fmt"] + k["sufixo"]
        k["v"] = _num_js(k["valor"])
        k["c"] = str(k["casas"])
    pontos = d["grafico"]["pontos"]
    topo = max(pontos) or 1.0
    d["pontos_norm"] = ",".join("%.4f" % (p / topo) for p in pontos)
    d["periodo"] = d["periodo"] or ""


def _ctx_agenda(d, geo):
    d["ncol"] = str(len(d["dias"]))
    n = len(d["dias"]) * len(d["horas"])
    passo = next(p for p in (7, 11, 13, 17, 19, 23, 29, 31, 37, 41) if math.gcd(p, n) == 1)
    linhas = []
    for h, hora in enumerate(d["horas"]):
        celulas = []
        for dia in range(len(d["dias"])):
            idx = h * len(d["dias"]) + dia
            celulas.append({"ocupado": d["ocupados"][idx % len(d["ocupados"])], "ord": str((idx * passo) % n)})
        linhas.append({"hora": hora, "celulas": celulas})
    d["linhas"] = linhas
    d["n_celulas"] = str(n)


def _ctx_contador(d, geo):
    d["prefixo"] = d["prefixo"] or ""
    d["valor_fmt"] = formatar_ptbr(d["valor"], d["casas"])
    d["v"] = _num_js(d["valor"])
    d["c"] = str(d["casas"])
    n = len(d["valor_fmt"]) + len(d["prefixo"])
    d["tam"] = str(int(max(90, min(300, 0.9 * geo["lw"] / (0.66 * max(n, 3))))))


def _ctx_fluxo(d, geo):
    lw, lh = geo["lw"], geo["lh"]
    cw, ch = min(1640, int(lw * 0.86)), min(760, int(lh * 0.78))
    pad = 40
    etapas = d["etapas"]
    e = len(etapas)
    caixa_w = int(min(220, (cw - 2 * pad) / (e * 1.55)))
    caixa_h = 150
    dy = int(min(140, (ch - caixa_h - 2 * 60) / 2))
    caixas, conexoes, centros = [], [], []
    cor = 0
    for i, etapa in enumerate(etapas):
        x = pad + i * (cw - 2 * pad - caixa_w) / (e - 1)
        ys = [ch / 2] if len(etapa) == 1 else [ch / 2 - dy, ch / 2 + dy]
        grupo = []
        for caixa, yc in zip(etapa, ys):
            caixas.append({"etapa": str(i), "x": "%.1f" % x, "y": "%.1f" % (yc - caixa_h / 2),
                           "w": str(caixa_w), "h": str(caixa_h), "cor": _PALETA_FLUXO[cor % len(_PALETA_FLUXO)],
                           "icone": caixa["icone"], "nome": caixa["nome"], "estado": caixa["estado"]})
            grupo.append((x, yc))
            cor += 1
        centros.append(grupo)
    for i in range(e - 1):
        for (x0, y0) in centros[i]:
            for (x1, y1) in centros[i + 1]:
                xa, xb = x0 + caixa_w, x1
                meio = (xa + xb) / 2
                conexoes.append({"etapa": str(i), "d": "M %.1f %.1f C %.1f %.1f %.1f %.1f %.1f %.1f"
                                 % (xa, y0, meio, y0, meio, y1, xb, y1)})
    d["cw"], d["ch"] = str(cw), str(ch)
    d["caixas"], d["conexoes"] = caixas, conexoes
    d["n_etapas"] = str(e)


_CONTEXTO = {"whatsapp": _ctx_whatsapp, "terminal": _ctx_terminal, "kanban": _ctx_kanban,
             "dashboard": _ctx_dashboard, "agenda": _ctx_agenda, "contador": _ctx_contador, "fluxo": _ctx_fluxo}


# ======================================================================================
# Partes comuns do HTML: BASE (fontes, palco) e RUNTIME (tempo)
# ======================================================================================

_BASE = """<style>
@font-face{font-family:"Inter";font-weight:400;font-style:normal;font-display:block;src:url("fonts/inter-400.woff2") format("woff2")}
@font-face{font-family:"Inter";font-weight:600;font-style:normal;font-display:block;src:url("fonts/inter-600.woff2") format("woff2")}
@font-face{font-family:"Inter";font-weight:700;font-style:normal;font-display:block;src:url("fonts/inter-700.woff2") format("woff2")}
@font-face{font-family:"Montserrat";font-weight:500;font-style:normal;font-display:block;src:url("fonts/montserrat-500.woff2") format("woff2")}
@font-face{font-family:"Montserrat";font-weight:600;font-style:normal;font-display:block;src:url("fonts/montserrat-600.woff2") format("woff2")}
@font-face{font-family:"Archivo";font-weight:800;font-style:normal;font-display:block;src:url("fonts/archivo-800.woff2") format("woff2")}
@font-face{font-family:"Playfair Display";font-weight:600;font-style:italic;font-display:block;src:url("fonts/playfair-italic-600.woff2") format("woff2")}
*{box-sizing:border-box}
html,body{margin:0;width:{{_largura}}px;height:{{_altura}}px;overflow:hidden;background:#0c1116;font-family:"Montserrat","Inter",sans-serif;font-weight:600}
#root{position:absolute;left:0;top:0;width:{{_largura}}px;height:{{_altura}}px;overflow:hidden;background:#0c1116}
#stage{position:absolute;left:0;top:0;width:{{_lw}}px;height:{{_lh}}px;transform-origin:0 0;transform:scale({{_escala}})}
#zoom{position:absolute;left:0;top:0;width:100%;height:100%;display:flex;align-items:center;justify-content:center;transform-origin:50% 50%}
</style>"""

_RUNTIME = """<script>
(function(){
  var raiz=document.getElementById("root");
  var DUR=parseFloat(raiz.getAttribute("data-duration"));
  function clamp(x){return x<0?0:(x>1?1:x)}
  window.VAM={
    clamp:clamp,
    ease:function(x){x=clamp(x);return 1-Math.pow(1-x,3)},
    passo:function(n,ini,fracao,maximo){return Math.min(maximo,(DUR*fracao-ini)/Math.max(1,n))},
    fmt:function(v,c){
      var s=Math.abs(v).toFixed(c).split("."),i=s[0],r="";
      while(i.length>3){r="."+i.slice(-3)+r;i=i.slice(0,-3)}
      r=i+r+(s.length>1?","+s[1]:"");
      return (v<0&&/[1-9]/.test(r))?"-"+r:r;
    }
  };
  function aplicar(t){
    if(!(t>0))t=0; if(t>DUR)t=DUR;
    var z=document.getElementById("zoom");
    if(z)z.style.transform="scale("+(1+0.03*(t/DUR)).toFixed(5)+")";
    if(window.vamQuadro)window.vamQuadro(t,DUR);
  }
  window.__vamSeek=aplicar;
  var tl={_t:0,
    seek:function(t){this._t=t;aplicar(t);return this},
    time:function(t){if(t===undefined)return this._t;return this.seek(t)},
    totalTime:function(t){if(t===undefined)return this._t;return this.seek(t)},
    duration:function(){return DUR},
    totalDuration:function(){return DUR},
    progress:function(){return this._t/DUR},
    pause:function(){return this},
    play:function(){return this},
    paused:function(){return true},
    isActive:function(){return false},
    getChildren:function(){return []},
    eventCallback:function(){return this}
  };
  window.__timelines=window.__timelines||{};
  window.__timelines["main"]=tl;
  var q=new URLSearchParams(location.search);
  aplicar(q.has("t")?parseFloat(q.get("t")):0);
})();
</script>"""


# ======================================================================================
# Motor de template
# ======================================================================================

_RE_TOKEN = re.compile(r"\{\{\s*(?:([#/])\s*(cada|se)\b[ \t]*([A-Za-z_@.][\w.@]*)?|([A-Za-z_@.][\w.@]*))\s*\}\}")


class _ErroDeTemplate(Exception):
    """Defeito no arquivo de template (não é culpa do aluno)."""


class _Modelo:
    """Árvore de um template: ('t', texto) | ('v', nome) | ('cada', nome, filhos) | ('se', nome, filhos)."""

    def __init__(self, fonte, nome="template"):
        self.nome = nome
        raiz = []
        pilha = [("raiz", None, raiz)]
        pos = 0
        for m in _RE_TOKEN.finditer(fonte):
            if m.start() > pos:
                pilha[-1][2].append(("t", fonte[pos:m.start()]))
            pos = m.end()
            marca, tipo, arg, var = m.groups()
            if var:
                pilha[-1][2].append(("v", var))
            elif marca == "#":
                if not arg:
                    raise _ErroDeTemplate("%s: {{#%s}} sem nome" % (nome, tipo))
                filhos = []
                pilha[-1][2].append((tipo, arg, filhos))
                pilha.append((tipo, arg, filhos))
            else:
                if len(pilha) == 1 or pilha[-1][0] != tipo:
                    raise _ErroDeTemplate("%s: {{/%s}} sem abertura" % (nome, tipo))
                pilha.pop()
        if len(pilha) != 1:
            raise _ErroDeTemplate("%s: {{#%s %s}} sem fechamento" % (nome, pilha[-1][0], pilha[-1][1]))
        if pos < len(fonte):
            raiz.append(("t", fonte[pos:]))
        self.arvore = raiz

    def preencher(self, contexto):
        saida = []
        self._emitir(self.arvore, [contexto], [], saida)
        return "".join(saida)

    def _achar(self, nome, escopos, lacos):
        if nome == ".":
            return escopos[-1]
        if nome == "@i":
            return lacos[-1][0]
        if nome == "@n":
            return lacos[-1][0] + 1
        partes = nome.split(".")
        for escopo in reversed(escopos):
            if isinstance(escopo, dict) and partes[0] in escopo:
                valor = escopo[partes[0]]
                for p in partes[1:]:
                    if not isinstance(valor, dict) or p not in valor:
                        raise _ErroDeTemplate("%s: campo %r não existe" % (self.nome, nome))
                    valor = valor[p]
                return valor
        raise _ErroDeTemplate("%s: campo %r não existe no contexto" % (self.nome, nome))

    def _emitir(self, nos, escopos, lacos, saida):
        for no in nos:
            tipo = no[0]
            if tipo == "t":
                saida.append(no[1])
            elif tipo == "v":
                valor = self._achar(no[1], escopos, lacos)
                if valor is None:
                    continue
                saida.append(html.escape(str(valor), quote=True))
            elif tipo == "se":
                if self._achar(no[1], escopos, lacos):
                    self._emitir(no[2], escopos, lacos, saida)
            elif tipo == "cada":
                lista = self._achar(no[1], escopos, lacos)
                if not isinstance(lista, list):
                    raise _ErroDeTemplate("%s: %r não é lista" % (self.nome, no[1]))
                for i, item in enumerate(lista):
                    self._emitir(no[2], escopos + [item], lacos + [(i, len(lista))], saida)


def _ler_template(nome):
    arq = TEMPLATES_DIR / (nome + ".html")
    try:
        texto = arq.read_text(encoding="utf-8")
    except OSError as e:
        raise _ErroDeTemplate("não consegui ler %s: %s" % (arq, e))
    return texto.replace("<!--VAM:BASE-->", _BASE).replace("<!--VAM:RUNTIME-->", _RUNTIME)


# ======================================================================================
# HTML
# ======================================================================================

def gerar_html(template, dados, dur=DUR_PADRAO, proporcao=PROPORCAO_PADRAO, fps=FPS_PADRAO):
    """O HTML completo (uma composição do HyperFrames) do template com os dados."""
    normal = validar(template, dados)
    largura, altura = resolver_proporcao(proporcao)
    n = _quadros(dur, fps)
    lw, lh, escala = _palco(largura, altura)
    geo = {"lw": lw, "lh": lh}
    ctx = copy.deepcopy(normal)
    _CONTEXTO[template](ctx, geo)
    ctx.update({"_largura": str(largura), "_altura": str(altura), "_lw": str(lw), "_lh": str(lh),
                "_escala": "%.6f" % escala, "_dur": "%.4f" % (n / fps)})
    return _Modelo(_ler_template(template), template).preencher(ctx)


# ======================================================================================
# Motores de render
# ======================================================================================

def _fim(texto, linhas=3):
    ult = [ln.strip() for ln in (texto or "").splitlines() if ln.strip()]
    return " | ".join(ult[-linhas:]) if ult else "sem saída"


def _executar(cmd, cwd=None, timeout=900):
    try:
        r = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           universal_newlines=True, errors="replace", timeout=timeout)
        return r.returncode, r.stdout
    except subprocess.TimeoutExpired:
        return 124, "tempo esgotado (%d s)" % timeout
    except OSError as e:
        return 127, str(e)


class MotorHyperframes:
    """`hyperframes render <pasta> -o <mp4> --fps N`: a composição já é uma pasta de projeto."""
    nome = "hyperframes"

    def __init__(self, binario, executar=None):
        self.binario = str(binario)
        self._executar = executar or _executar

    def __call__(self, pedido):
        cmd = [self.binario, "render", str(pedido.pasta), "-o", str(pedido.saida),
               "--fps", str(pedido.fps), "--workers", "2", "--quiet"]
        rc, saida = self._executar(cmd, cwd=str(pedido.pasta), timeout=900)
        if rc != 0:
            raise RenderFalhou("o HyperFrames saiu com erro %s: %s" % (rc, _fim(saida)))
        if not Path(pedido.saida).is_file():
            raise RenderFalhou("o HyperFrames terminou sem escrever o vídeo: %s" % _fim(saida))


class MotorNavegador:
    """Chrome do sistema pelo Playwright: um screenshot por quadro (`__vamSeek(t)`) e o ffmpeg junta."""
    nome = "navegador"

    def __init__(self, navegador, executar=None):
        self.navegador = str(navegador)
        self._executar = executar or _executar

    def __call__(self, pedido):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RenderFalhou("ffmpeg não encontrado no PATH (instale: brew install ffmpeg)")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RenderFalhou("playwright não está instalado neste Python (%s)" % MENSAGEM_SEM_MOTOR)
        quadros = Path(pedido.pasta) / "quadros"
        quadros.mkdir()
        try:
            with sync_playwright() as pw:
                nav = pw.chromium.launch(executable_path=self.navegador,
                                         args=["--allow-file-access-from-files", "--hide-scrollbars"])
                try:
                    pg = nav.new_page(viewport={"width": pedido.largura, "height": pedido.altura})
                    pg.goto((Path(pedido.pasta) / "index.html").as_uri(), wait_until="load")
                    pg.evaluate("document.fonts.ready.then(function(){return true})")
                    for i in range(pedido.quadros):
                        pg.evaluate("t=>window.__vamSeek(t)", i / pedido.fps)
                        pg.screenshot(path=str(quadros / ("%05d.png" % i)))
                finally:
                    nav.close()
        except RenderFalhou:
            raise
        except Exception as e:
            raise RenderFalhou("o navegador falhou: %s" % _fim(str(e)))
        cmd = [ffmpeg, "-v", "error", "-y", "-framerate", str(pedido.fps), "-i", str(quadros / "%05d.png"),
               "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
               "-c:v", "libx264", "-crf", "16", "-preset", "medium",
               "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
               "-movflags", "+faststart", str(pedido.saida)]
        rc, saida = self._executar(cmd, timeout=900)
        if rc != 0:
            raise RenderFalhou("o ffmpeg saiu com erro %s: %s" % (rc, _fim(saida)))


def _achar_navegador():
    """Um Chrome, Chromium ou Edge do sistema (ou o headless shell que o HyperFrames baixa), ou None."""
    mac = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
           "/Applications/Chromium.app/Contents/MacOS/Chromium",
           "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
           "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]
    for c in mac:
        if Path(c).is_file():
            return Path(c)
    for nome in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome",
                 "microsoft-edge"):
        achado = shutil.which(nome)
        if achado:
            return Path(achado)
    cache = Path.home() / ".cache" / "hyperframes" / "chrome"
    if cache.is_dir():
        for c in sorted(cache.glob("**/chrome-headless-shell")):
            if c.is_file() and os.access(str(c), os.X_OK):
                return c
    return None


def _playwright_disponivel():
    import importlib.util
    return importlib.util.find_spec("playwright") is not None


def motor_padrao(raiz=None):
    """O motor de render disponível: o HyperFrames do repo e, sem ele, um Chrome do sistema com Playwright."""
    raiz = Path(raiz) if raiz is not None else RAIZ
    binario = raiz / "node_modules" / ".bin" / "hyperframes"
    if binario.is_file() and os.access(str(binario), os.X_OK):
        return MotorHyperframes(binario)
    navegador = _achar_navegador()
    if navegador and _playwright_disponivel():
        return MotorNavegador(navegador)
    raise SemMotorDeRender(MENSAGEM_SEM_MOTOR)


# ======================================================================================
# Render
# ======================================================================================

def renderizar(template, dados, saida, dur=DUR_PADRAO, proporcao=PROPORCAO_PADRAO, fps=FPS_PADRAO,
               motor=None, raiz=None):
    """Template + dados -> `saida` (.mp4) na proporção do painel, com `dur` segundos (erro de até 1 quadro).

    A ordem é a do custo: confere o template e os dados, a proporção e a duração, e só então procura
    o motor. O vídeo nasce num temporário ao lado do destino e vira o arquivo final de uma vez, então
    um render que falha não toca no mp4 que já existia. `motor` (um chamável `motor(pedido)`) substitui
    o motor do sistema: é por onde os testes entram.
    """
    saida = Path(os.path.abspath(str(saida)))      # o motor roda em outra pasta: caminho relativo se perderia
    if saida.suffix.lower() != ".mp4":
        raise ValueError("a saída precisa ser um .mp4 (veio %s)" % saida.name)
    html_final = gerar_html(template, dados, dur=dur, proporcao=proporcao, fps=fps)   # valida tudo
    largura, altura = resolver_proporcao(proporcao)
    n = _quadros(dur, fps)
    if motor is None:
        motor = motor_padrao(raiz)
    saida.parent.mkdir(parents=True, exist_ok=True)
    temporario = saida.parent / ("." + saida.stem + ".render.mp4")
    pasta = Path(tempfile.mkdtemp(prefix="vam-insert-"))
    try:
        (pasta / "index.html").write_text(html_final, encoding="utf-8")
        (pasta / "fonts").mkdir()
        for f in FONTES:
            shutil.copyfile(str(FONTES_DIR / f), str(pasta / "fonts" / f))
        pedido = PedidoRender(template=template, html=html_final, pasta=pasta, saida=temporario,
                              largura=largura, altura=altura, fps=fps, quadros=n, dur=n / fps)
        motor(pedido)
        if not temporario.is_file() or temporario.stat().st_size == 0:
            raise RenderFalhou("o motor terminou sem escrever o vídeo")
        os.replace(str(temporario), str(saida))
    finally:
        if temporario.exists():
            temporario.unlink()
        shutil.rmtree(str(pasta), ignore_errors=True)
    return Resultado(saida=saida, largura=largura, altura=altura, fps=fps, quadros=n, dur=n / fps,
                     motor=getattr(motor, "nome", "personalizado"))
