#!/usr/bin/env python3
"""Validador dos contratos da video-ads-machine. Só biblioteca padrão, Python 3.9 ou mais.

Uso:
  python3 scripts/contratos/validar.py <arquivo|pasta> [<arquivo|pasta> ...]

Saída 0 quando tudo confere; 1 quando algum arquivo falha (cada linha diz o arquivo, o
caminho do campo e o motivo); 2 quando não há nada para validar (caminho ausente ou
pasta sem nenhum arquivo de contrato).

Como cada arquivo é reconhecido, sempre pelo nome (pastas são varridas recursivamente):
  <contrato>.json e <contrato>.<qualquer>.json   contra contratos/<contrato>.schema.json
  roteiro.md e roteiro.<qualquer>.md             contra a gramática de contratos/roteiro-convencao.md
  <nome>.schema.json                             o próprio schema (só palavras suportadas)
  <nome>.blocos.json                             igual à leitura do <nome>.md vizinho
  <...>.invalido.<campo>[-detalhe].<ext>         TEM que reprovar, num erro que nomeie <campo>
Qualquer outro arquivo é ignorado.

O validador implementa um subconjunto do JSON Schema 2020-12 e RECUSA schema que use
palavra-chave fora dele: schema que parece exigir algo que o validador não confere é pior
que schema nenhum. Depois do schema, cada contrato pode ter regras que o JSON Schema não
expressa (ordem de intervalos, referência entre seções, veredito coerente); elas só rodam
quando o schema passou.

API para as outras unidades:
  validar(nome, instancia) -> [Erro]          valida um dict contra o contrato <nome>
  validar_arquivo(caminho) -> [Erro]          reconhece pelo nome e valida
  ler_roteiro(texto) -> (leitura, [Erro])     a gramática do roteiro.md (leitura None se vazio)
  Erro.caminho / Erro.campo / Erro.mensagem   campo = último nome de campo do caminho
"""
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CONTRATOS = RAIZ / "contratos"
NOMES = ("projeto", "looks", "glossario", "plano", "timeline", "laudo", "aprovacao", "nota")
SCHEMA_URL = "https://json-schema.org/draft/2020-12/schema"
EPS = 1e-6


class SchemaInvalido(Exception):
    """O schema usa algo que este validador não sabe conferir, ou está quebrado."""


class Erro:
    """Um problema achado. `campo` é o nome que a mensagem acusa (último campo do caminho)."""

    __slots__ = ("caminho", "mensagem", "campo")

    def __init__(self, caminho, mensagem, campo):
        self.caminho = caminho
        self.mensagem = mensagem
        self.campo = campo

    def __str__(self):
        return f"{self.caminho}: {self.mensagem}"

    def __repr__(self):
        return f"Erro({self.caminho!r}, {self.mensagem!r})"

    def __eq__(self, outro):
        return isinstance(outro, Erro) and str(self) == str(outro)

    def __hash__(self):
        return hash(str(self))


def _fmt(segs):
    out = "$"
    for s in segs:
        if isinstance(s, int):
            out += f"[{s}]"
        elif re.match(r"^[^.\[\]\s\"]+$", s):
            out += f".{s}"
        else:
            out += f"[{json.dumps(s, ensure_ascii=False)}]"
    return out


def _erro(segs, mensagem):
    nomes = [s for s in segs if isinstance(s, str)]
    return Erro(_fmt(segs), mensagem, nomes[-1] if nomes else "$")


def _mostrar(v, limite=60):
    t = json.dumps(v, ensure_ascii=False)
    return t if len(t) <= limite else t[:limite - 3] + "..."


# ------------------------------------------------------------------------------------
# Subconjunto de JSON Schema
# ------------------------------------------------------------------------------------

ANOTACOES = frozenset({"$schema", "$id", "$comment", "title", "description", "default", "examples"})
VALIDACOES = frozenset({
    "$ref", "$defs", "type", "enum", "const",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "minLength", "maxLength", "pattern",
    "items", "minItems", "maxItems", "uniqueItems",
    "properties", "required", "additionalProperties", "propertyNames",
    "minProperties", "maxProperties", "dependentRequired",
    "allOf", "anyOf", "oneOf", "not", "if", "then", "else",
})
TIPOS = ("null", "boolean", "integer", "number", "string", "array", "object")
_REGEX = {}


def _regex(p):
    if p not in _REGEX:
        _REGEX[p] = re.compile(p)
    return _REGEX[p]


def _tipo_ok(tipo, v):
    if tipo == "null":
        return v is None
    if tipo == "boolean":
        return isinstance(v, bool)
    if tipo == "integer":
        if isinstance(v, bool):
            return False
        return isinstance(v, int) or (isinstance(v, float) and v.is_integer())
    if tipo == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if tipo == "string":
        return isinstance(v, str)
    if tipo == "array":
        return isinstance(v, list)
    if tipo == "object":
        return isinstance(v, dict)
    return False


def _tipo_de(v):
    for t in ("null", "boolean", "integer", "number", "string", "array", "object"):
        if _tipo_ok(t, v):
            return t
    return type(v).__name__


def _igual(a, b):
    """Igualdade do JSON: true não é 1, mas 1 é 1.0."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_igual(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_igual(a[k], b[k]) for k in a)
    return type(a) is type(b) and a == b


def _resolver(raiz, ref):
    if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
        raise SchemaInvalido(f"$ref só aceita '#/$defs/<nome>', veio {ref!r}")
    alvo = raiz
    for parte in ref[2:].split("/"):
        parte = parte.replace("~1", "/").replace("~0", "~")
        if not isinstance(alvo, dict) or parte not in alvo:
            raise SchemaInvalido(f"$ref quebrado: {ref}")
        alvo = alvo[parte]
    return alvo


def conferir_schema(raiz, nome="schema"):
    """Levanta SchemaInvalido se o schema usar algo que o validador não confere."""
    problemas = []

    def numero(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    def andar(s, onde):
        if isinstance(s, bool):
            return
        if not isinstance(s, dict):
            problemas.append(f"{onde}: schema tem que ser objeto ou booleano")
            return
        for k in s:
            if k not in ANOTACOES and k not in VALIDACOES:
                problemas.append(f"{onde}: palavra-chave não suportada pelo validador: {k}")
        if "type" in s:
            tipos = s["type"] if isinstance(s["type"], list) else [s["type"]]
            for t in tipos:
                if t not in TIPOS:
                    problemas.append(f"{onde}: tipo desconhecido {t!r}")
        if "$ref" in s:
            try:
                _resolver(raiz, s["$ref"])
            except SchemaInvalido as e:
                problemas.append(f"{onde}: {e}")
        if "pattern" in s:
            try:
                re.compile(s["pattern"])
            except (re.error, TypeError) as e:
                problemas.append(f"{onde}: pattern inválido {s['pattern']!r} ({e})")
        if "enum" in s and (not isinstance(s["enum"], list) or not s["enum"]):
            problemas.append(f"{onde}: enum tem que ser lista não vazia")
        if "required" in s:
            r = s["required"]
            if not isinstance(r, list) or not all(isinstance(x, str) for x in r) or len(set(r)) != len(r):
                problemas.append(f"{onde}: required tem que ser lista de nomes sem repetição")
        for k in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
            if k in s and not numero(s[k]):
                problemas.append(f"{onde}: {k} tem que ser número")
        for k in ("minLength", "maxLength", "minItems", "maxItems", "minProperties", "maxProperties"):
            if k in s and not (isinstance(s[k], int) and not isinstance(s[k], bool) and s[k] >= 0):
                problemas.append(f"{onde}: {k} tem que ser inteiro >= 0")
        if "uniqueItems" in s and not isinstance(s["uniqueItems"], bool):
            problemas.append(f"{onde}: uniqueItems tem que ser booleano")
        if "dependentRequired" in s:
            d = s["dependentRequired"]
            if not isinstance(d, dict) or not all(isinstance(v, list) for v in d.values()):
                problemas.append(f"{onde}: dependentRequired tem que ser objeto de listas")
        for k in ("properties", "$defs"):
            if k in s:
                if not isinstance(s[k], dict):
                    problemas.append(f"{onde}: {k} tem que ser objeto")
                    continue
                for nome_p, sub in s[k].items():
                    andar(sub, f"{onde}/{k}/{nome_p}")
        for k in ("items", "additionalProperties", "propertyNames", "not", "if", "then", "else"):
            if k in s:
                andar(s[k], f"{onde}/{k}")
        for k in ("allOf", "anyOf", "oneOf"):
            if k in s:
                if not isinstance(s[k], list) or not s[k]:
                    problemas.append(f"{onde}: {k} tem que ser lista não vazia")
                    continue
                for i, sub in enumerate(s[k]):
                    andar(sub, f"{onde}/{k}/{i}")

    andar(raiz, "#")
    if problemas:
        raise SchemaInvalido(f"{nome}: " + "; ".join(problemas))


class Validador:
    """Valida instâncias contra um schema já conferido por conferir_schema."""

    def __init__(self, schema, nome="schema"):
        conferir_schema(schema, nome)
        self.schema = schema
        self.nome = nome

    def erros(self, instancia):
        vistos, saida = set(), []
        for e in self._v(self.schema, instancia, ()):
            if str(e) not in vistos:
                vistos.add(str(e))
                saida.append(e)
        return saida

    def _v(self, s, x, segs):
        if s is True:
            return []
        if s is False:
            return [_erro(segs, "nenhum valor é aceito aqui")]
        erros = []
        if "$ref" in s:
            erros += self._v(_resolver(self.schema, s["$ref"]), x, segs)
        if "type" in s:
            tipos = s["type"] if isinstance(s["type"], list) else [s["type"]]
            if not any(_tipo_ok(t, x) for t in tipos):
                erros.append(_erro(segs, f"tipo errado: esperado {' ou '.join(tipos)}, veio {_tipo_de(x)}"))
                return erros
        if "const" in s and not _igual(x, s["const"]):
            erros.append(_erro(segs, f"valor {_mostrar(x)} diferente do exigido {_mostrar(s['const'])}"))
        if "enum" in s and not any(_igual(x, e) for e in s["enum"]):
            permitidos = ", ".join(_mostrar(e) for e in s["enum"])
            erros.append(_erro(segs, f"valor {_mostrar(x)} fora dos permitidos: {permitidos}"))
        if _tipo_ok("number", x):
            erros += self._numero(s, x, segs)
        if isinstance(x, str):
            erros += self._texto(s, x, segs)
        if isinstance(x, list):
            erros += self._lista(s, x, segs)
        if isinstance(x, dict):
            erros += self._objeto(s, x, segs)
        for sub in s.get("allOf", []):
            erros += self._v(sub, x, segs)
        if "anyOf" in s:
            res = [self._v(sub, x, segs) for sub in s["anyOf"]]
            if all(res):
                erros += self._mais_proxima(res, segs)
        if "oneOf" in s:
            res = [self._v(sub, x, segs) for sub in s["oneOf"]]
            casam = [i for i, r in enumerate(res) if not r]
            if not casam:
                erros += self._mais_proxima(res, segs)
            elif len(casam) > 1:
                erros.append(_erro(segs, f"casa com {len(casam)} formas ao mesmo tempo; tem que casar com uma só"))
        if "not" in s and not self._v(s["not"], x, segs):
            erros.append(_erro(segs, f"valor {_mostrar(x)} proibido aqui"))
        if "if" in s:
            if not self._v(s["if"], x, segs):
                if "then" in s:
                    erros += self._v(s["then"], x, segs)
            elif "else" in s:
                erros += self._v(s["else"], x, segs)
        return erros

    @staticmethod
    def _mais_proxima(resultados, segs):
        """A alternativa que chegou mais perto: primeiro as que aceitam o tipo do valor
        (errar o tipo é o erro menos informativo), depois a que tem menos erros."""
        aqui = _fmt(segs)

        def distancia(erros):
            tipo_errado = any(e.caminho == aqui and e.mensagem.startswith("tipo errado") for e in erros)
            return (tipo_errado, len(erros))

        melhor = min(resultados, key=distancia)
        return [_erro(segs, f"nenhuma das {len(resultados)} formas aceitas serve; a mais próxima falhou assim:")] + melhor

    @staticmethod
    def _numero(s, x, segs):
        erros = []
        if "minimum" in s and x < s["minimum"]:
            erros.append(_erro(segs, f"{x} é menor que o mínimo {s['minimum']}"))
        if "maximum" in s and x > s["maximum"]:
            erros.append(_erro(segs, f"{x} é maior que o máximo {s['maximum']}"))
        if "exclusiveMinimum" in s and x <= s["exclusiveMinimum"]:
            erros.append(_erro(segs, f"{x} tem que ser maior que {s['exclusiveMinimum']}"))
        if "exclusiveMaximum" in s and x >= s["exclusiveMaximum"]:
            erros.append(_erro(segs, f"{x} tem que ser menor que {s['exclusiveMaximum']}"))
        return erros

    @staticmethod
    def _texto(s, x, segs):
        erros = []
        if "minLength" in s and len(x) < s["minLength"]:
            erros.append(_erro(segs, f"texto com {len(x)} caractere(s), mínimo {s['minLength']}"))
        if "maxLength" in s and len(x) > s["maxLength"]:
            erros.append(_erro(segs, f"texto com {len(x)} caracteres, máximo {s['maxLength']}"))
        if "pattern" in s and not _regex(s["pattern"]).search(x):
            erros.append(_erro(segs, f"valor {_mostrar(x)} não casa com o padrão {s['pattern']}"))
        return erros

    def _lista(self, s, x, segs):
        erros = []
        if "minItems" in s and len(x) < s["minItems"]:
            erros.append(_erro(segs, f"lista com {len(x)} item(ns), mínimo {s['minItems']}"))
        if "maxItems" in s and len(x) > s["maxItems"]:
            erros.append(_erro(segs, f"lista com {len(x)} itens, máximo {s['maxItems']}"))
        if s.get("uniqueItems"):
            for j in range(len(x)):
                if any(_igual(x[j], x[k]) for k in range(j)):
                    erros.append(_erro(segs + (j,), f"item repetido {_mostrar(x[j])}"))
        if "items" in s:
            for j, item in enumerate(x):
                erros += self._v(s["items"], item, segs + (j,))
        return erros

    def _objeto(self, s, x, segs):
        erros = []
        props = s.get("properties", {})
        for nome in s.get("required", []):
            if nome not in x:
                erros.append(_erro(segs + (nome,), "obrigatório e ausente"))
        for nome, sub in props.items():
            if nome in x:
                erros += self._v(sub, x[nome], segs + (nome,))
        extra = s.get("additionalProperties", True)
        for nome in x:
            if nome in props:
                continue
            if extra is False:
                aceitos = ", ".join(props) or "nenhum"
                erros.append(_erro(segs + (nome,), f"campo desconhecido (aceitos: {aceitos})"))
            elif isinstance(extra, dict):
                erros += self._v(extra, x[nome], segs + (nome,))
        if "propertyNames" in s:
            for nome in x:
                for e in self._v(s["propertyNames"], nome, segs + (nome,)):
                    erros.append(Erro(e.caminho, f"nome de chave inválido: {e.mensagem}", e.campo))
        if "minProperties" in s and len(x) < s["minProperties"]:
            erros.append(_erro(segs, f"objeto com {len(x)} campo(s), mínimo {s['minProperties']}"))
        if "maxProperties" in s and len(x) > s["maxProperties"]:
            erros.append(_erro(segs, f"objeto com {len(x)} campos, máximo {s['maxProperties']}"))
        for nome, deps in s.get("dependentRequired", {}).items():
            if nome in x:
                for d in deps:
                    if d not in x:
                        erros.append(_erro(segs + (d,), f"obrigatório quando {nome} existe"))
        return erros


# ------------------------------------------------------------------------------------
# Regras que o JSON Schema não expressa (rodam só quando o schema passou)
# ------------------------------------------------------------------------------------

def _sequencia(lista, base, fim=None, contigua=False, quadro=None, ini="s", fim_k="e"):
    """Intervalos em ordem, sem sobrepor, dentro de [0, fim]; contígua = sem buraco > 1 quadro."""
    erros = []
    for k, it in enumerate(lista):
        s, e = it[ini], it[fim_k]
        if not s < e:
            erros.append(_erro(base + (k,), f"início {s} não é menor que o fim {e}"))
        if fim is not None and e > fim + EPS:
            erros.append(_erro(base + (k,), f"termina em {e}s, depois do fim ({fim}s)"))
        if k:
            anterior = lista[k - 1][fim_k]
            if s < anterior - EPS:
                erros.append(_erro(base + (k,), f"começa em {s}s, antes do fim do anterior ({anterior}s)"))
            elif contigua and s - anterior > (quadro or 0) + EPS:
                erros.append(_erro(base + (k,), f"buraco de {s - anterior:.3f}s depois do anterior (máximo 1 quadro)"))
    return erros


def _em_ordem(lista, base, chave="t", fim=None):
    erros = []
    for k, it in enumerate(lista):
        if k and it[chave] < lista[k - 1][chave] - EPS:
            erros.append(_erro(base + (k,), f"fora de ordem: {it[chave]}s vem depois de {lista[k - 1][chave]}s"))
        if fim is not None and it[chave] > fim + EPS:
            erros.append(_erro(base + (k,), f"em {it[chave]}s, depois do fim ({fim}s)"))
    return erros


def _indices(blocos, base):
    return [_erro(base + (k, "i"), f"i = {b['i']}, mas o bloco está na posição {k}")
            for k, b in enumerate(blocos) if b["i"] != k]


def _regras_glossario(g):
    erros, dono = [], {}
    grafias = {}
    for j, t in enumerate(g["termos"]):
        gk = t["grafia"].casefold()
        if gk in grafias:
            erros.append(_erro(("termos", j, "grafia"), f"grafia repetida (já está no termo {grafias[gk]})"))
        grafias.setdefault(gk, j)
    for j, t in enumerate(g["termos"]):
        for k, v in enumerate(t.get("variantes", [])):
            vk = v.casefold()
            if vk == t["grafia"].casefold():
                erros.append(_erro(("termos", j, "variantes", k), "variante igual à própria grafia"))
            elif vk in grafias and grafias[vk] != j:
                erros.append(_erro(("termos", j, "variantes", k), f"{v!r} é a grafia do termo {grafias[vk]}"))
            if vk in dono and dono[vk] != j:
                erros.append(_erro(("termos", j, "variantes", k),
                                   f"variante {v!r} já pertence ao termo {dono[vk]}: uma variante, um termo"))
            dono.setdefault(vk, j)
    return erros


def _regras_plano(p):
    erros = _indices(p["blocos"], ("blocos",))
    fim = p.get("duracao_s")
    erros += _sequencia(p["blocos"], ("blocos",), fim=fim, contigua=True, quadro=1 / 30)
    n = len(p["blocos"])
    mapa = {}
    for k, m in enumerate(p["mapa_inserts"]):
        if m["chave"] in mapa:
            erros.append(_erro(("mapa_inserts", k, "chave"), f"chave {m['chave']!r} repetida no mapa"))
        mapa.setdefault(m["chave"], k)
        for j, b in enumerate(m["blocos"]):
            if b >= n:
                erros.append(_erro(("mapa_inserts", k, "blocos", j), f"bloco {b} não existe ({n} blocos)"))
            elif p["blocos"][b].get("insert") != m["chave"]:
                erros.append(_erro(("mapa_inserts", k, "blocos", j), f"o bloco {b} não usa o insert {m['chave']!r}"))
    for k, b in enumerate(p["blocos"]):
        if b["tipo"] == "insert" and b["insert"] not in mapa:
            erros.append(_erro(("blocos", k, "insert"), f"insert {b['insert']!r} sem entrada no mapa_inserts"))
    for k, l in enumerate(p["letterings"]):
        if l["bloco"] >= n:
            erros.append(_erro(("letterings", k, "bloco"), f"bloco {l['bloco']} não existe ({n} blocos)"))
        if fim is not None and l["s"] + l["d"] > fim + EPS:
            erros.append(_erro(("letterings", k), f"termina em {l['s'] + l['d']:.2f}s, depois do fim ({fim}s)"))
    for k, c in enumerate(p["efeitos"]["camera"]):
        if c["bloco"] >= n:
            erros.append(_erro(("efeitos", "camera", k, "bloco"), f"bloco {c['bloco']} não existe ({n} blocos)"))
    for k, pr in enumerate(p["densidade"].get("propostas", [])):
        if pr["bloco"] >= n:
            erros.append(_erro(("densidade", "propostas", k, "bloco"), f"bloco {pr['bloco']} não existe"))
    d = p["densidade"]
    if not d["piso"] <= d["alvo_min"] <= d["alvo_max"] <= d["teto"]:
        erros.append(_erro(("densidade",), "faixa incoerente: piso <= alvo_min <= alvo_max <= teto"))
    for parte in ("corpo", "cta"):
        for k, t in enumerate(p.get("trechos", {}).get(parte, [])):
            if not t["inicio"] < t["fim"]:
                erros.append(_erro(("trechos", parte, k), f"inicio {t['inicio']} não é menor que o fim {t['fim']}"))
    return erros


# O logo do CTA pode subir até isto antes da pílula: é o `LOGO_LEAD` do overlay (overlay/cta.py), quando o bloco
# anterior ao CTA é o apresentador. O validador não importa o overlay (só biblioteca padrão): um teste amarra os dois.
LOGO_ANTECIPA_MAX_S = 0.9

def _regras_timeline(t):
    erros = []
    dur = t["duracao_s"]
    quadro = 1.0 / t["relogio"]["fps"]
    blocos = t["blocos"]
    erros += _indices(blocos, ("blocos",))
    erros += _sequencia(blocos, ("blocos",), fim=dur, contigua=True, quadro=quadro)
    erros += _sequencia(t["segmentos"], ("segmentos",), fim=dur, contigua=True, quadro=quadro)
    for k, sg in enumerate(t["segmentos"]):
        if sg["bloco"] >= len(blocos):
            erros.append(_erro(("segmentos", k, "bloco"), f"bloco {sg['bloco']} não existe"))
            continue
        b = blocos[sg["bloco"]]
        if sg["s"] < b["s"] - EPS or sg["e"] > b["e"] + EPS:
            erros.append(_erro(("segmentos", k), f"{sg['s']}-{sg['e']}s fora do bloco {sg['bloco']} ({b['s']}-{b['e']}s)"))
        if sg["sub"] >= sg["de"]:
            erros.append(_erro(("segmentos", k, "sub"), f"sub {sg['sub']} não é menor que de {sg['de']}"))
    erros += _sequencia(t["janelas_split"], ("janelas_split",), fim=dur)
    erros += _sequencia(t["legendas"], ("legendas",), fim=dur)
    for k, lg in enumerate(t["legendas"]):
        ws = lg["palavras"]
        for j, w in enumerate(ws):
            if w["s"] < lg["s"] - EPS or w["e"] > lg["e"] + EPS or w["e"] < w["s"]:
                erros.append(_erro(("legendas", k, "palavras", j), f"palavra {w['t']!r} fora da legenda ({lg['s']}-{lg['e']}s)"))
            elif j and w["s"] < ws[j - 1]["s"] - EPS:
                erros.append(_erro(("legendas", k, "palavras", j), "palavras fora de ordem"))
    ids = set()
    for k, l in enumerate(t["letterings"]):
        if l["id"] in ids:
            erros.append(_erro(("letterings", k, "id"), f"id {l['id']!r} repetido"))
        ids.add(l["id"])
        if l["bloco"] >= len(blocos):
            erros.append(_erro(("letterings", k, "bloco"), f"bloco {l['bloco']} não existe"))
        if l["s"] + l["d"] > dur + EPS:
            erros.append(_erro(("letterings", k), f"termina em {l['s'] + l['d']:.2f}s, depois do fim ({dur}s)"))
    h = t["hook"]
    if not h["s"] < h["e"] <= dur + EPS:
        erros.append(_erro(("hook",), f"janela {h['s']}-{h['e']}s inválida para {dur}s"))
    c = t["cta"]
    if not c["inicio"] < dur:
        erros.append(_erro(("cta", "inicio"), f"o CTA começa em {c['inicio']}s, depois do fim ({dur}s)"))
    if c["logo"] < c["inicio"] - LOGO_ANTECIPA_MAX_S - EPS:
        erros.append(_erro(("cta", "logo"), f"o logo entra {c['inicio'] - c['logo']:.2f}s antes do CTA; o máximo é "
                                            f"{LOGO_ANTECIPA_MAX_S}s (o overlay antecipa o logo só quando o bloco "
                                            "anterior é o apresentador)"))
    erros += _em_ordem(t["camera"], ("camera",), fim=dur)
    erros += _em_ordem(t["sfx"], ("sfx",), fim=dur)
    if "pausas" in t["ducking"]:
        erros += _sequencia(t["ducking"]["pausas"], ("ducking", "pausas"), fim=dur)
    return erros


def _regras_laudo(l):
    erros = []
    por_nome = {}
    for k, g in enumerate(l["gates"]):
        if g["nome"] in por_nome:
            erros.append(_erro(("gates", k, "nome"), f"gate {g['nome']!r} repetido no laudo"))
        por_nome.setdefault(g["nome"], g)
        if g["resultado"] == "PASS" and g["saida"] != 0:
            erros.append(_erro(("gates", k, "saida"), f"resultado PASS com saída {g['saida']}"))
        if g["resultado"] == "REPROVA" and g["saida"] == 0:
            erros.append(_erro(("gates", k, "saida"), "resultado REPROVA com saída 0: gate que reprova sai com 1"))
    for c, cap in l["capacidades"].items():
        for j, nome in enumerate(cap["gates"]):
            if nome not in por_nome:
                erros.append(_erro(("capacidades", c, "gates", j), f"gate {nome!r} não aparece em 'gates'"))
        if cap["status"] == "PASS":
            ruins = [n for n in cap["gates"] if n in por_nome and por_nome[n]["resultado"] != "PASS"]
            if ruins:
                erros.append(_erro(("capacidades", c, "status"), f"PASS com gate que não passou: {', '.join(ruins)}"))
    falhas = [g["nome"] for g in l["gates"] if g["resultado"] in ("REPROVA", "ERRO")]
    caps = [c for c, cap in l["capacidades"].items() if cap["status"] == "REPROVA"]
    if l["veredito"] == "PASS" and (falhas or caps):
        erros.append(_erro(("veredito",), f"PASS com reprovação: gates {falhas or '-'}, capacidades {caps or '-'}"))
    if l["veredito"] == "REPROVA" and not (falhas or caps):
        erros.append(_erro(("veredito",), "REPROVA sem nenhum gate ou capacidade reprovada"))
    return erros


def _regras_nota(n):
    erros, ids = [], set()
    for k, a in enumerate(n["achados"]):
        if a["id"] in ids:
            erros.append(_erro(("achados", k, "id"), f"id {a['id']!r} repetido"))
        ids.add(a["id"])
    for k, r in enumerate(n.get("reconfere", [])):
        if r not in ids:
            erros.append(_erro(("reconfere", k), f"{r!r} não está em 'achados': a rodada 2 reconfere os mesmos pontos"))
    return erros


REGRAS = {
    "glossario": _regras_glossario,
    "plano": _regras_plano,
    "timeline": _regras_timeline,
    "laudo": _regras_laudo,
    "nota": _regras_nota,
}

_VALIDADORES = {}


def carregar_schema(nome, pasta=None):
    p = Path(pasta or CONTRATOS) / f"{nome}.schema.json"
    return json.loads(p.read_text(encoding="utf-8"))


def validador(nome):
    if nome not in _VALIDADORES:
        _VALIDADORES[nome] = Validador(carregar_schema(nome), nome)
    return _VALIDADORES[nome]


def validar(nome, instancia):
    """Erros de `instancia` contra o contrato `nome` (schema e, se ele passar, as regras)."""
    if nome not in NOMES:
        raise ValueError(f"contrato desconhecido: {nome!r} (conhecidos: {', '.join(NOMES)})")
    erros = validador(nome).erros(instancia)
    if not erros and nome in REGRAS:
        erros = REGRAS[nome](instancia)
    return erros


# ------------------------------------------------------------------------------------
# Gramática do roteiro.md (ver contratos/roteiro-convencao.md)
# ------------------------------------------------------------------------------------

TIPOS_BLOCO = ("apresentador", "insert", "lista", "cta")
LAYOUTS = ("split", "cheio", "pip")
MARCADORES = "❌✅✔✓✖✗"
_RE_CHAVE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_RE_ENFASE = re.compile(r"\*([^\s*](?:[^*\n]*[^\s*])?)\*")
_RE_MARCADOR = re.compile("[" + MARCADORES + "]️?")
_ALIAS_APRESENTADOR = ("avatar", "especialista", "expert", "pessoa", "rosto", "talking head")
_PREFIXOS_OPCAO = ("lead:", "key:", "âncora:", "ancora:", "hook:", "insert:")


def normalizar_palavra(w):
    """Como palavras são comparadas: minúscula, sem acento, só letras e dígitos."""
    w = unicodedata.normalize("NFD", w.lower())
    w = "".join(c for c in w if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w]", "", w)


def palavras(texto):
    return [p for p in (normalizar_palavra(w) for w in texto.split()) if p]


def _limpar_item(t):
    return re.sub(r"[\s.,;:…]+$", "", t.strip())


def _itens_da_lista(fala):
    """Itens da pilha e a fala sem marcadores. Ver 'Lista' na convenção."""
    if _RE_MARCADOR.search(fala):
        marcas = [m.group(0)[0] for m in _RE_MARCADOR.finditer(fala)]
        pedacos = _RE_MARCADOR.split(fala)[1:]
        itens = [{"texto": _limpar_item(p), "marcador": m} for m, p in zip(marcas, pedacos) if _limpar_item(p)]
        limpa = re.sub(r"\s*(?:" + _RE_MARCADOR.pattern + r")\s*", " ", fala).strip()
        return itens, limpa
    corpo = fala.split(":", 1)[1] if ":" in fala else fala
    pecas = [_limpar_item(p) for p in re.split(r"[,;]", corpo)]
    pecas = [p for p in pecas if p]
    if len(pecas) >= 2:
        k = pecas[-1].rfind(" e ")
        if k > 0:
            pecas[-1:] = [_limpar_item(pecas[-1][:k]), _limpar_item(pecas[-1][k + 3:])]
    return [{"texto": p, "marcador": None} for p in pecas if p], fala


def _bloco_vazio(tipo):
    return {"tipo": tipo, "insert": None, "layout": None, "hook": None, "lead": None, "key": None,
            "ancora": None, "logo": False, "itens": [], "enfase": [], "fala": ""}


def ler_roteiro(texto):
    """Lê um roteiro.md. Devolve ({'livre': bool, 'blocos': [...]}, [Erro]).

    Cada Erro tem caminho 'linha N (elemento)' e campo = o elemento da gramática
    (direcao, insert, layout, hook, lead, key, ancora, logo, lista, cta, enfase,
    colchete, fala). A leitura só vale quando a lista de erros está vazia.
    """
    erros = []

    def erro(n, campo, msg):
        erros.append(Erro(f"linha {n} ({campo})", msg, campo))

    linhas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    dirigido = any(l.lstrip().startswith("[") for l in linhas)
    brutos = []  # [linha, direcao ou None, fala]
    if dirigido:
        for n, l in enumerate(linhas, 1):
            s = l.strip()
            if not s or s.startswith("#"):
                continue
            if s.startswith("["):
                fecha = s.find("]")
                if fecha < 0:
                    erro(n, "colchete", "colchete aberto sem fechar")
                    continue
                brutos.append([n, s[1:fecha], s[fecha + 1:].strip()])
            elif not brutos:
                erro(n, "direcao", "texto antes do primeiro bloco: num roteiro dirigido toda fala começa com [direção]")
            else:
                brutos[-1][2] = (brutos[-1][2] + " " + s).strip()
    else:
        atual = None
        for n, l in enumerate(linhas, 1):
            s = l.strip()
            if s.startswith("#"):
                continue
            if not s:
                atual = None
                continue
            if atual is None:
                atual = [n, None, s]
                brutos.append(atual)
            else:
                atual[2] += " " + s
    if not brutos:
        erro(1, "fala", "roteiro vazio")
        return None, erros

    blocos = []
    for idx, (n, direcao, bruta) in enumerate(brutos):
        b = _bloco_vazio("livre")
        ancora_pedida = None
        if direcao is not None:
            ancora_pedida = _ler_direcao(direcao, b, n, idx, erro)
        if "[" in bruta or "]" in bruta:
            erro(n, "colchete", "colchete no meio da fala: direção só vale no começo da linha e nunca vira legenda")
        b["enfase"] = [m.group(1) for m in _RE_ENFASE.finditer(bruta)]
        fala = _RE_ENFASE.sub(lambda m: m.group(1), bruta)
        if "*" in fala:
            erro(n, "enfase", "asterisco sem par: ênfase é *palavra*, colado na palavra dos dois lados")
        if b["tipo"] == "lista":
            b["itens"], fala = _itens_da_lista(fala)
            if len(b["itens"]) < 2:
                erro(n, "lista", "lista com menos de 2 itens: separe por vírgula ('a, b e c') ou marque cada item com ❌ ou ✅")
        b["fala"] = fala
        if not palavras(fala):
            erro(n, "fala", "bloco sem fala")
        _resolver_lettering(b, ancora_pedida, n, erro)
        blocos.append(b)

    if dirigido:
        for k, ((n, _, _), b) in enumerate(zip(brutos, blocos)):
            if b["tipo"] == "cta" and k != len(blocos) - 1:
                erro(n, "cta", "o bloco cta tem que ser o último")
        if blocos[-1]["tipo"] != "cta":
            erro(brutos[-1][0], "cta", "roteiro dirigido termina sem bloco [cta | KEY: ...]")
    return {"livre": not dirigido, "blocos": blocos}, erros


def _ler_direcao(direcao, b, n, idx, erro):
    """Preenche o bloco a partir do que está entre colchetes. Devolve a âncora pedida."""
    if "[" in direcao:
        erro(n, "colchete", "colchete dentro da direção")
    partes = [p.strip() for p in direcao.split("|")]
    cabeca, sep, arg = partes[0].partition(":")
    tipo, arg = cabeca.strip().lower(), arg.strip()
    if tipo == "insert":
        if not arg:
            erro(n, "insert", "insert sem chave: escreva [insert: <chave>]")
        elif not _RE_CHAVE.match(arg):
            erro(n, "insert", f"chave de insert {arg!r} inválida: minúsculas, números, _ ou -, igual ao nome do arquivo em inserts/")
        else:
            b["insert"] = arg
    elif tipo in TIPOS_BLOCO:
        if sep:
            erro(n, "direcao", f"{tipo} não leva argumento depois de ':'")
    else:
        dica = " (para a pessoa falando, use apresentador)" if tipo in _ALIAS_APRESENTADOR else ""
        erro(n, "direcao", f"tipo de bloco desconhecido {partes[0]!r}: o primeiro item do colchete é "
                           f"apresentador, insert: <chave>, lista ou cta{dica}")
        tipo = "desconhecido"
    b["tipo"] = tipo
    ancora = None
    i = 1
    while i < len(partes):
        p = partes[i]
        chave, sep, valor = p.partition(":")
        k = chave.strip().lower().replace("â", "a")
        valor = valor.strip()
        if k == "hook" and sep:
            resto = [valor] + partes[i + 1:]
            if idx != 0:
                erro(n, "hook", "hook só vale no primeiro bloco")
            elif len(resto) != 3 or not all(resto):
                erro(n, "hook", "hook tem 3 partes e vem por último no colchete: hook: <eyebrow> | <linha> | <destaque>")
            elif any(r.lower() in LAYOUTS + ("logo",) or r.lower().startswith(_PREFIXOS_OPCAO) for r in resto[1:]):
                erro(n, "hook", "uma parte do hook parece opção: o hook vem por último no colchete")
            else:
                b["hook"] = {"eyebrow": resto[0], "linha": resto[1], "destaque": resto[2]}
            break
        if not sep:
            if k in LAYOUTS:
                if tipo != "insert":
                    erro(n, "layout", f"{k} só vale para insert")
                elif b["layout"]:
                    erro(n, "layout", "mais de um layout no mesmo bloco")
                else:
                    b["layout"] = k
            elif k == "logo":
                if tipo != "cta":
                    erro(n, "logo", "logo só vale no bloco cta (o último)")
            elif not k:
                erro(n, "direcao", "item vazio entre barras")
            else:
                erro(n, "direcao", f"opção desconhecida {p!r}")
        elif k in ("lead", "key"):
            if not valor:
                erro(n, k, f"{k.upper()} vazio")
            elif b[k] is not None:
                erro(n, k, f"{k.upper()} repetido no mesmo bloco")
            else:
                b[k] = valor
        elif k == "ancora":
            pal, _, num = valor.rpartition("#") if "#" in valor else (valor, "", "")
            pal = pal.strip()
            if not pal or len(pal.split()) != 1:
                erro(n, "ancora", "âncora é uma palavra só, com #n opcional (por exemplo âncora: dia#2)")
            elif num and (not num.strip().isdigit() or int(num) < 1):
                erro(n, "ancora", "o número depois de # é a ocorrência na fala do bloco, a partir de 1")
            elif ancora is not None:
                erro(n, "ancora", "âncora repetida no mesmo bloco")
            else:
                ancora = (pal, int(num) if num else None)
        else:
            erro(n, "direcao", f"opção desconhecida {chave.strip()!r}")
        i += 1
    return ancora


def _resolver_lettering(b, ancora_pedida, n, erro):
    tipo = b["tipo"]
    if b["lead"] is not None and b["key"] is None and tipo != "lista":
        erro(n, "key", "LEAD sem KEY: o lettering é LEAD + KEY, ou só KEY")
    if tipo == "lista" and b["key"] is not None:
        erro(n, "key", "lista não leva KEY: cada item da fala vira uma linha da pilha")
    if tipo == "cta":
        b["logo"] = True
        if b["key"] is None:
            erro(n, "key", "o bloco cta precisa de KEY (o texto do botão, por exemplo SAIBA MAIS)")
    tem_lettering = b["key"] is not None or (tipo == "lista" and b["lead"] is not None)
    ws = palavras(b["fala"])
    if ancora_pedida is not None:
        pal, nth = ancora_pedida
        if not tem_lettering:
            erro(n, "ancora", "âncora sem lettering: ela marca onde o LEAD/KEY entra")
            return
        alvo = normalizar_palavra(pal)
        ocorre = ws.count(alvo)
        if ocorre == 0:
            erro(n, "ancora", f"a palavra {pal!r} não aparece na fala do bloco")
        elif nth is None and ocorre > 1:
            erro(n, "ancora", f"{pal!r} aparece {ocorre} vezes na fala do bloco; diga qual com {pal}#n")
        elif nth is not None and nth > ocorre:
            erro(n, "ancora", f"{pal}#{nth} pedido, mas {pal!r} aparece {ocorre} vez(es) na fala do bloco")
        else:
            b["ancora"] = {"palavra": pal, "n": nth or 1, "explicita": True}
    elif tem_lettering and ws:
        tokens = [w for w in b["fala"].split() if normalizar_palavra(w)]
        pos = _onde_o_key_comeca(ws, palavras(b["key"])) if tipo == "cta" and b["key"] else None
        i = pos if pos is not None else 0
        b["ancora"] = {"palavra": re.sub(r"^\W+|\W+$", "", tokens[i]), "n": ws[:i + 1].count(ws[i]),
                       "explicita": False}
        if pos is not None:
            b["ancora"]["da_key"] = True


def _onde_o_key_comeca(ws, chave):
    """Índice, nas palavras da fala, da primeira palavra do KEY: onde o KEY inteiro começa; se ele não aparece inteiro,
    a 1ª ocorrência da primeira palavra dele. None se a primeira palavra do KEY não está na fala (âncora padrão do cta,
    W7.X: o botão entra quando a palavra do KEY é dita, e não na primeira palavra do bloco)."""
    if not chave or chave[0] not in ws:
        return None
    for i in range(len(ws) - len(chave) + 1):
        if ws[i:i + len(chave)] == chave:
            return i
    return ws.index(chave[0])


def bloco_do_documento(doc, marca):
    """Conteúdo do bloco cercado (```) logo depois de '<!-- marca -->' no documento."""
    m = re.search(r"<!--\s*" + re.escape(marca) + r"\s*-->\s*\n```[^\n]*\n(.*?)\n```", doc, re.S)
    if not m:
        raise KeyError(f"marca '{marca}' não encontrada no documento")
    return m.group(1) + "\n"


# ------------------------------------------------------------------------------------
# Arquivos e CLI
# ------------------------------------------------------------------------------------

def _json_estrito(texto):
    def pares(ps):
        d = {}
        for k, v in ps:
            if k in d:
                raise ValueError(f"chave duplicada {k!r}")
            d[k] = v
        return d

    def constante(c):
        raise ValueError(f"{c} não é JSON válido")

    return json.loads(texto, object_pairs_hook=pares, parse_constant=constante)


def contrato_do_arquivo(caminho):
    """('schema'|'blocos'|'json'|'roteiro', nome) pelo nome do arquivo, ou None se não é contrato."""
    nome = Path(caminho).name
    if nome.endswith(".schema.json"):
        return ("schema", nome[:-len(".schema.json")])
    if nome.endswith(".blocos.json"):
        return ("blocos", nome[:-len(".blocos.json")])
    base = nome.split(".")[0]
    if nome.endswith(".json") and base in NOMES:
        return ("json", base)
    if nome.endswith(".md") and base == "roteiro":
        return ("roteiro", base)
    return None


def campo_esperado(caminho):
    """Para '<...>.invalido.<campo>[-detalhe].<ext>', o campo que o erro tem que nomear."""
    partes = Path(caminho).name.split(".")
    if "invalido" not in partes[:-1]:
        return None
    i = partes.index("invalido")
    if i + 1 >= len(partes) - 1:
        return ""
    return partes[i + 1].split("-")[0]


def _primeira_diferenca(esperado, lido, segs=()):
    if isinstance(esperado, dict) and isinstance(lido, dict):
        for k in list(esperado) + [k for k in lido if k not in esperado]:
            if k not in esperado or k not in lido:
                return segs + (k,), esperado.get(k, "<ausente>"), lido.get(k, "<ausente>")
            d = _primeira_diferenca(esperado[k], lido[k], segs + (k,))
            if d:
                return d
        return None
    if isinstance(esperado, list) and isinstance(lido, list):
        for j, (a, b) in enumerate(zip(esperado, lido)):
            d = _primeira_diferenca(a, b, segs + (j,))
            if d:
                return d
        if len(esperado) != len(lido):
            return segs, f"{len(esperado)} itens", f"{len(lido)} itens"
        return None
    return None if _igual(esperado, lido) else (segs, esperado, lido)


def validar_arquivo(caminho):
    """Erros do arquivo, reconhecido pelo nome. Arquivo não reconhecido levanta ValueError."""
    caminho = Path(caminho)
    tipo = contrato_do_arquivo(caminho)
    if tipo is None:
        raise ValueError(f"{caminho.name}: nome fora da convenção de contratos")
    try:
        texto = caminho.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return [Erro("$", f"não deu para ler o arquivo: {e}", "$")]
    if tipo[0] == "roteiro":
        return ler_roteiro(texto)[1]
    try:
        dado = _json_estrito(texto)
    except ValueError as e:
        return [Erro("$", f"JSON inválido: {e}", "$")]
    if tipo[0] == "schema":
        try:
            conferir_schema(dado, caminho.name)
        except SchemaInvalido as e:
            return [Erro("$", str(e), "$")]
        return []
    if tipo[0] == "blocos":
        md = caminho.with_name(tipo[1] + ".md")
        if not md.exists():
            return [Erro("$", f"falta o roteiro vizinho {md.name}", "$")]
        lido, erros = ler_roteiro(md.read_text(encoding="utf-8"))
        if erros:
            return [Erro("$", f"{md.name} não passa na gramática: {erros[0]}", "$")]
        d = _primeira_diferenca(dado, lido)
        if d:
            return [_erro(d[0], f"esperado {_mostrar(d[1])}, a leitura deu {_mostrar(d[2])}")]
        return []
    return validar(tipo[1], dado)


def _arquivos(alvos):
    for alvo in alvos:
        p = Path(alvo)
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                partes = f.relative_to(p).parts
                if f.is_file() and not any(x.startswith(".") or x in ("__pycache__", "node_modules") for x in partes):
                    if contrato_do_arquivo(f):
                        yield f
        elif p.is_file() and contrato_do_arquivo(p):
            yield p


def _rotulo(p):
    try:
        return str(p.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(p)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2 if not argv else 0
    ausentes = [a for a in argv if not os.path.exists(a)]
    if ausentes:
        print(f"caminho não existe: {', '.join(ausentes)}")
        return 2
    vistos, falhas = 0, 0
    for f in _arquivos(argv):
        vistos += 1
        esperado = campo_esperado(f)
        erros = validar_arquivo(f)
        nome = _rotulo(f)
        if esperado is None:
            if erros:
                falhas += 1
                for e in erros[:20]:
                    print(f"FALHA {nome}: {e}")
                if len(erros) > 20:
                    print(f"FALHA {nome}: ... e mais {len(erros) - 20} erro(s)")
            else:
                print(f"ok    {nome}")
        elif not esperado:
            falhas += 1
            print(f"FALHA {nome}: exemplo inválido sem o campo no nome (<contrato>.invalido.<campo>.<ext>)")
        elif not erros:
            falhas += 1
            print(f"FALHA {nome}: deveria reprovar em '{esperado}', mas passou")
        elif esperado not in [e.campo for e in erros]:
            falhas += 1
            print(f"FALHA {nome}: deveria reprovar em '{esperado}', mas reprovou em: "
                  + "; ".join(str(e) for e in erros[:5]))
        else:
            certo = next(e for e in erros if e.campo == esperado)
            print(f"ok    {nome} (reprovou como esperado: {certo})")
    if not vistos:
        print("nenhum arquivo de contrato encontrado")
        return 2
    print(f"{vistos} arquivo(s) conferido(s), {falhas} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
