"""Lista os looks do HeyGen do aluno pela API v3 (GET /v3/avatars/looks), paginada.

Doc (conferida em 09/10/2026): https://developers.heygen.com/reference/list-avatar-looks
Parâmetros usados: limit (até 50), token (cursor opaco da próxima página), ownership
(`private` = do aluno, `public` = presets), group_id. A doc não tem filtro de orientação:
ela vem em cada item (`preferred_orientation`: portrait, landscape ou square), e aqui só os
verticais (portrait) passam por padrão, porque look horizontal vira tarja no 9:16.

Cada item sai normalizado: {id, nome, tipo, orientacao, previa, suporta_avatar_v, grupo}.
`id` é o que vai em `avatar_id` no looks.json do aluno e no POST /v3/videos.

    python3 scripts/avatar/listar.py [--publicos] [--todos] [--grupo ID]
"""
import argparse
import sys
from urllib.parse import urlencode

import os
if __name__ == "__main__":      # rodado direto: scripts/avatar/listar.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from avatar.heygen_cliente import ClienteHeyGen, HeyGenErro

LIMITE_POR_PAGINA = 50
MAX_PAGINAS = 100
ORIENTACOES = {"portrait": "vertical", "landscape": "horizontal", "square": "quadrado"}


def _normalizar(item):
    engines = item.get("supported_api_engines") or []
    return {"id": item.get("id"), "nome": item.get("name"), "tipo": item.get("avatar_type"),
            "orientacao": ORIENTACOES.get(item.get("preferred_orientation"), "desconhecida"),
            "previa": item.get("preview_image_url"), "grupo": item.get("group_id"),
            "suporta_avatar_v": "avatar_v" in engines}


def listar_looks(cliente, ownership="private", apenas_verticais=True, group_id=None):
    """Todos os looks (todas as páginas). Levanta HeyGenErro em resposta fora do formato ou em
    laço de paginação."""
    achados, token = [], None
    for _ in range(MAX_PAGINAS):
        params = [("limit", LIMITE_POR_PAGINA)]
        if ownership:
            params.append(("ownership", ownership))
        if group_id:
            params.append(("group_id", group_id))
        if token:
            params.append(("token", token))
        d = cliente._requisitar("GET", "/v3/avatars/looks?" + urlencode(params))
        if not isinstance(d.get("data"), list):
            raise HeyGenErro("resposta de /v3/avatars/looks sem a lista `data`")
        achados.extend(_normalizar(i) for i in d["data"] if isinstance(i, dict))
        token = d.get("next_token")
        if not d.get("has_more") or not token:
            break
    else:
        raise HeyGenErro("a paginação de looks passou de %d páginas (cursor em laço?)" % MAX_PAGINAS)
    if apenas_verticais:
        achados = [a for a in achados if a["orientacao"] == "vertical"]
    return achados


def formatar(looks):
    if not looks:
        return "nenhum look encontrado."
    linhas = []
    for l in looks:
        aviso = "" if l["suporta_avatar_v"] else "  [sem Avatar V]"
        linhas.append("%s  %s  (%s, %s)%s" % (l["id"], l["nome"], l["tipo"], l["orientacao"], aviso))
    return "\n".join(linhas)


def main(argv=None, cliente=None, env=None, raiz=None):
    ap = argparse.ArgumentParser(description="Lista os looks do HeyGen.")
    ap.add_argument("--publicos", action="store_true", help="presets da HeyGen em vez dos seus")
    ap.add_argument("--todos", action="store_true", help="inclui horizontais e quadrados")
    ap.add_argument("--grupo")
    args = ap.parse_args(argv)
    try:
        c = cliente or ClienteHeyGen.do_ambiente(env, raiz)
        print(formatar(listar_looks(c, "public" if args.publicos else "private",
                                    not args.todos, args.grupo)))
        return 0
    except HeyGenErro as e:
        print(str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
