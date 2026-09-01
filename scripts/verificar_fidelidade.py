#!/usr/bin/env python3
"""GATE DE FIDELIDADE AO DOC (ordem do Julio, 17/08/2026: "seguir FIELMENTE").

Compara, bloco a bloco, o que o doc manda contra o que o build vai usar:
  1. cada marcador [..] de INSERT da secao do ad no doc
  2. os comentarios da Brigida ancorados naquele marcador (links = assets)
  3. o arquivo que o inserts.json aponta pra aquele bloco

Reprova (exit 1) se um insert usa arquivo diferente do que o doc marca, ou se um
bloco marcado no doc nao tem asset nenhum. Gap legitimo (doc sem comentario, ou
instrucao de GRAVAR) precisa estar declarado em _fidelidade_excecoes.json COM MOTIVO
ESCRITO: assim a decisao fica auditavel em vez de virar substituicao silenciosa.

Por que existe: na versao do jh13 que a Jheni reprovou, 2 de 9 inserts usavam asset
diferente do que a Brigida marcou e 1 comentario com 2 links virou 1 asset so. O
gate-ad.py nao pegava porque ele so checa se o MARCADOR foi usado, nao QUAL arquivo.

Uso:
  python3 verificar_fidelidade.py <ad>          # ex: jh13
  python3 verificar_fidelidade.py <ad> --json   # saida estruturada
"""
import html
import json
import os
import re
import subprocess
import sys
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

from caminhos import V2L  # noqa: E402  (era o proprio dir; agora e o _local, que guarda o estado)
from caminhos import V1  # noqa: E402
MAPA = V2L / "_doc_map.json"
EXCECOES = V2L / "_fidelidade_excecoes.json"

# marcador que descreve captura de tela/asset visual
INSERT_KW = ("inserir", "gravar", "mostra", "adicionar", "insercao", "insercão",
              "insert", "remotion", "video", "filma", "imagem", "imagens",
              "take", "pipoca", "tela dividida", "aula acelerad")


def norm(s):
    s = unicodedata.normalize("NFKD", html.unescape(s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


def sim(a, b):
    """Cobertura do MARCADOR pela ancora, nao Jaccard.

    Jaccard punia a ancora mais longa e escolhia a errada: pro marcador
    '[Adicionar remotion]' ele preferia a ancora '[remotion]' (0.50) em vez de
    '[Adicionar remotion que representa o manual]' (0.33), que e a certa (o asset
    dela e literalmente um manual de instrucoes). Medir quanto do marcador a
    ancora cobre resolve, com desempate pelo tamanho da intersecao.
    """
    A, B = set(norm(a).split()), set(norm(b).split())
    if not A or not B:
        return 0.0
    inter = len(A & B)
    return inter / len(A) + 0.001 * inter


def letras_do_export(doc_id, secao):
    """Blocos da secao do ad, na ordem, com as URLs que o doc ancora em cada um.

    A exportacao em texto do Google numera os comentarios: escreve '[Remotion][p]' no
    corpo e '[p]<url>' numa lista no fim. A API NAO devolve esse vinculo (o marcador vem
    limpo e o comentario vem sem posicao), entao o gate casava por semelhanca de texto e
    errava entre anuncios vizinhos. Aqui o vinculo e exato.

    Devolve [(marcador, [url, ...]), ...] ou [] se o export falhar.
    """
    r = subprocess.run(["bash", os.path.expanduser("~/.claude/scripts/google-api.sh"),
                        "doc", doc_id], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout:
        return []
    linhas = r.stdout.split("\n")
    legenda = {}
    for l in linhas:
        m = re.match(r"^\s*\[([a-z]{1,2})\]\s*(https?://\S+)", l)
        if m:
            legenda[m.group(1)] = m.group(2)
    cabecas = [i for i, l in enumerate(linhas) if re.match(r"^AD\d+", l.strip())]
    ini = next((i for i in cabecas if linhas[i].strip()[:len(secao)] == secao), None)
    if ini is None:
        return []
    fim = next((i for i in cabecas if i > ini), len(linhas))
    saida = []
    for l in linhas[ini:fim]:
        s = l.strip()
        if not s.startswith("["):
            continue
        # o doc tem "[...] [ac]" COM espaco em alguns blocos, e tem marcador com ']'
        # no meio; por isso o marcador sai do primeiro grupo e as letras por regex tolerante.
        letras = re.findall(r"\]\s*\[([a-z]{1,2})\]", s)
        m = re.match(r"\[([^\]]*)\]", s)
        marc = m.group(1) if m else s.strip("[]")
        saida.append((marc, [legenda[x] for x in letras if x in legenda]))
    return saida


def marcadores_da_linha(l):
    """Marcadores [..] de uma linha, tolerando colchete NAO FECHADO.

    O doc tem '[Thales de frente para a câmera' sem o ']' (linha 033 do AD13). Um
    regex estrito perdia esse bloco e a checagem de estrutura acusava 15 blocos no
    doc contra 16 no roteiro: falso positivo por typo de quem escreveu o doc.
    """
    achados = re.findall(r"\[([^\]\n]{3,140})\]", l)
    if not achados:
        m = re.match(r"\s*\[([^\]\n]{3,140})$", l)
        if m:
            achados = [m.group(1).strip()]
    return achados


def eh_insert(marc):
    m = norm(marc)
    if "thales" in m or m.startswith("lettering") or m == "lettering":
        return False
    return any(k in m for k in INSERT_KW)


def tok():
    subprocess.run(["bash", os.path.expanduser("~/.claude/scripts/google-api.sh"), "refresh"],
                   capture_output=True, text=True)
    return json.load(open(os.path.expanduser("~/.claude/google-tokens.json")))["access_token"]


def baixar_doc(doc_id, t):
    u = f"https://docs.googleapis.com/v1/documents/{doc_id}?includeTabsContent=true"
    r = urllib.request.Request(u, headers={"Authorization": f"Bearer {t}"})
    with urllib.request.urlopen(r, timeout=180) as x:
        return json.loads(x.read().decode())


def baixar_comentarios(doc_id, t):
    params = urllib.parse.urlencode({
        "fields": "nextPageToken,comments(id,content,createdTime,quotedFileContent/value,"
                  "resolved,author/displayName,replies(content))", "pageSize": "100"})
    itens, page = [], None
    while True:
        u = f"https://www.googleapis.com/drive/v3/files/{doc_id}/comments?{params}"
        if page:
            u += "&pageToken=" + page
        r = urllib.request.Request(u, headers={"Authorization": f"Bearer {t}"})
        with urllib.request.urlopen(r, timeout=120) as x:
            d = json.loads(x.read().decode())
        itens += d.get("comments", [])
        page = d.get("nextPageToken")
        if not page:
            break
    itens.sort(key=lambda c: c.get("createdTime", ""))
    saida = []
    for c in itens:
        anc = html.unescape((c.get("quotedFileContent") or {}).get("value", "")).strip()
        corpo = c.get("content", "") + " " + " ".join(
            rp.get("content", "") for rp in c.get("replies", []))
        saida.append({"ancora": anc, "n": norm(anc), "texto": c.get("content", "").strip(),
                      "links": [l.rstrip(".,;)") for l in re.findall(r"https?://\S+", corpo)]})
    return saida


def ids_do_link(url):
    """Extrai o identificador do asset a partir do link do comentario."""
    m = re.search(r"share/asset/([0-9a-fA-F]{8})", url)
    if m:
        return ("gal", m.group(1).lower())
    m = re.search(r"/file/d/([A-Za-z0-9_-]{10,})", url)
    if m:
        # 10 chars: e o tamanho que o downloader usa no nome (drv_XXXXXXXXXX).
        # Cortar em 12 dava falso DIVERGE contra o arquivo real no disco.
        return ("drv", m.group(1)[:10])
    return ("web", url)


def secao_do_ad(doc, aba, cabecalho):
    todas, off, alvo = [], None, None
    for tab in doc.get("tabs", []):
        nome = tab.get("tabProperties", {}).get("title", "")
        ls = []
        for el in tab["documentTab"]["body"]["content"]:
            par = el.get("paragraph")
            if not par:
                continue
            txt = "".join(r.get("textRun", {}).get("content", "")
                          for r in par.get("elements", [])).strip()
            if txt:
                ls.append(txt)
        if nome == aba:
            off, alvo = len(todas), ls
        todas += ls
    if alvo is None:
        sys.exit(f"FIDELIDADE: aba '{aba}' nao encontrada no doc")
    idx = [i for i, l in enumerate(alvo) if l.strip().upper() == cabecalho.upper()]
    if not idx:
        sys.exit(f"FIDELIDADE: secao '{cabecalho}' nao encontrada na aba '{aba}'")
    ini = idx[0]
    seg = [i for i, l in enumerate(alvo)
           if i > ini and re.fullmatch(r"AD\s*\d{1,2}", l.strip(), re.I)]
    fim = seg[0] if seg else len(alvo)
    return todas, off + ini, off + fim


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    ad = sys.argv[1]
    como_json = "--json" in sys.argv

    if not MAPA.exists():
        sys.exit(f"FIDELIDADE: falta {MAPA.name} mapeando ad -> doc/aba/secao")
    mapa = json.loads(MAPA.read_text())
    if ad not in mapa:
        sys.exit(f"FIDELIDADE: ad '{ad}' nao esta em {MAPA.name}. "
                 "Sem fonte declarada nao da pra verificar fidelidade.")
    cfg = mapa[ad]

    t = tok()
    doc = baixar_doc(cfg["doc"], t)
    coms = baixar_comentarios(cfg["doc"], t)
    todas, g_ini, g_fim = secao_do_ad(doc, cfg["aba"], cfg["secao"])

    # marcadores da secao, com indice de ocorrencia GLOBAL (ancora repete entre ads)
    # MAPA POR LETRA, vindo da exportacao em texto (ver docstring de letras_do_export).
    por_ordem = letras_do_export(cfg["doc"], cfg["secao"])

    cont, cont_secao, blocos = {}, {}, []
    for gi, l in enumerate(todas):
        for m in marcadores_da_linha(l):
            n = norm(m)
            cont[n] = cont.get(n, 0) + 1
            if g_ini <= gi < g_fim:
                cont_secao[n] = cont_secao.get(n, 0) + 1
                blocos.append({"marcador": m, "n": n, "ocorr": cont[n],
                               "ocorr_secao": cont_secao[n], "letras": []})
    # casamento POSICIONAL com o export, e so quando as duas leituras enxergam o mesmo
    # numero de blocos; qualquer divergencia derruba pro casamento antigo, que e pior
    # mas nao inventa.
    if por_ordem and len(por_ordem) == len(blocos):
        for b, (marc, urls) in zip(blocos, por_ordem):
            if norm(marc)[:18] == b["n"][:18]:
                b["urls_doc"] = urls
    else:
        print(f"  (aviso: export viu {len(por_ordem)} bloco(s) e a API {len(blocos)}; "
              f"caindo pro casamento por ancora)", flush=True)

    pref = "" if str(ad).startswith("jh") else "ad"
    ins_path = V1 / "inputs" / f"{pref}{ad}v2_inserts.json"
    if not ins_path.exists():
        sys.exit(f"FIDELIDADE: inserts.json nao existe: {ins_path}")
    usados = json.loads(ins_path.read_text())

    exc = json.loads(EXCECOES.read_text()) if EXCECOES.exists() else {}
    exc_ad = exc.get(ad, {})

    problemas, relatorio = [], []
    for b in blocos:
        if not eh_insert(b["marcador"]):
            continue
        exatos = [c for c in coms if c["n"] == b["n"]]
        if len(exatos) >= b["ocorr"]:
            esc = exatos[b["ocorr"] - 1]
        elif exatos:
            esc = exatos[0]
        else:
            cands = sorted(coms, key=lambda c: sim(b["marcador"], c["ancora"]), reverse=True)
            esc = cands[0] if cands and sim(b["marcador"], cands[0]["ancora"]) >= 0.5 else None

        if b.get("urls_doc") is not None:
            # a letra do export manda, e nao a semelhanca de texto com a ancora
            esperados = [ids_do_link(L) for L in b["urls_doc"]]
        else:
            esperados = [ids_do_link(L) for L in (esc["links"] if esc else [])]
        # Chave do inserts.json pra este marcador. Quando o MESMO marcador aparece
        # N vezes na secao e o doc marca asset diferente em cada, existem N chaves
        # empatadas (ex: "video acelerado das aulas 1" e "... 2"): a enesima
        # ocorrencia casa com a enesima chave, na ordem do json.
        pontuadas = sorted(
            ((sim(k, b["marcador"]), i, v.get("file"))
             for i, (k, v) in enumerate(usados.items())),
            key=lambda t: (-t[0], t[1]))
        topo = [p for p in pontuadas if p[0] >= 0.45]
        base = None
        if topo:
            melhor_score = topo[0][0]
            empatadas = [p for p in topo if abs(p[0] - melhor_score) < 1e-9]
            idx = b["ocorr_secao"] - 1
            escolha = empatadas[idx] if idx < len(empatadas) else topo[0]
            base = os.path.basename(escolha[2]) if escolha[2] else None

        motivo_exc = exc_ad.get(b["marcador"])
        item = {"marcador": b["marcador"], "esperados": esperados, "usado": base,
                "excecao": motivo_exc}

        if not esperados:
            if motivo_exc:
                item["status"] = "GAP DECLARADO"
            else:
                item["status"] = "GAP NAO DECLARADO"
                problemas.append(f"'{b['marcador']}': doc nao marca asset e nao ha excecao "
                                 f"declarada (build usaria {base})")
        elif not base:
            item["status"] = "SEM INSERT"
            problemas.append(f"'{b['marcador']}': doc marca {len(esperados)} asset(s) "
                             "mas o inserts.json nao tem entrada pra este bloco")
        else:
            # os dois lados em minuscula: o ID do Drive tem maiuscula e o nome do
            # arquivo no disco nao, o que dava falso DIVERGE.
            # PIPOCA: comentario com N links exige que TODOS apareçam. Asset composto
            # (varios clipes num arquivo so) declara as partes no proprio nome, ex:
            # pipoca_gal_21562a04_gal_e4b82c88.mp4. Assim a composicao fica auditavel
            # sem abrir o arquivo.
            ids = [i.lower() for p, i in esperados if p != "web"]
            bate = all(i in base.lower() for i in ids) if ids else False
            web = [i for p, i in esperados if p == "web"]
            if bate:
                item["status"] = "OK"
            elif web and motivo_exc:
                item["status"] = "GAP DECLARADO (instrucao web)"
            elif web:
                item["status"] = "INSTRUCAO NAO CUMPRIDA"
                problemas.append(f"'{b['marcador']}': doc aponta instrucao ({web[0]}) "
                                 f"e o build usa {base} sem excecao declarada")
            else:
                item["status"] = "DIVERGE"
                alvo = ", ".join(f"{p}_{i}" for p, i in esperados)
                problemas.append(f"'{b['marcador']}': doc marca [{alvo}] e o build usa {base}")
            if item["status"] == "DIVERGE" and len(esperados) > 1:
                faltam = [i for i in ids if i not in base.lower()]
                if len(faltam) < len(ids):
                    item["status"] = "PIPOCA INCOMPLETA"
                    problemas[-1] = (f"'{b['marcador']}': doc marca {len(esperados)} assets "
                                     f"(pipoca) e faltam {faltam} no arquivo usado")
        relatorio.append(item)

    # ---- ESTRUTURA: os DIRECIONAMENTOS do doc, nao so os comentarios ----
    # O doc define, bloco a bloco, o TIPO (insert / avatar / lettering) e a ordem.
    # No jh13 a direcao "Enquanto isso:❌ ... ❌ ... ❌ ..." (tres itens marcados)
    # virou um KEY unico no _leva.txt: a direcao visual se perdeu na traducao.
    rot = V1 / "inputs" / f"{pref}{ad}v2_leva.txt"
    estrutura = []
    if rot.exists():
        blocos_rot = [m.group(1) for m in
                      (re.match(r"\[([^\]]+)\]", l) for l in rot.read_text().strip().split("\n"))
                      if m]

        def tipo(marc):
            n = norm(marc)
            if eh_insert(marc):
                return "insert"
            return "lettering" if "lettering" in n else "avatar"

        tipos_doc = [tipo(b["marcador"]) for b in blocos]
        tipos_rot = [tipo(b) for b in blocos_rot]
        if len(tipos_doc) != len(tipos_rot):
            problemas.append(f"estrutura: doc tem {len(tipos_doc)} blocos e o roteiro tem "
                             f"{len(tipos_rot)}")
        else:
            for i, (td, tr) in enumerate(zip(tipos_doc, tipos_rot)):
                # lettering pode vir grudado no bloco de avatar no formato do motor
                if td == tr or {td, tr} == {"lettering", "avatar"}:
                    continue
                # Bloco que o doc pede como insert e o roteiro entrega como avatar POR
                # EXCECAO DECLARADA nao e divergencia escondida: o motivo esta escrito no
                # _fidelidade_excecoes.json (tipico: "filma a tela", gravacao que nao foi
                # feita). Sem isso o gate cobra duas vezes a mesma coisa e trava a leva.
                if td == "insert" and tr == "avatar" and exc_ad.get(blocos[i]["marcador"]):
                    continue
                # SIMETRIA (26/08/2026): o inverso tambem e caso legitimo. A Fase 2 da
                # skill preve PROPOR insert novo onde o doc so tinha avatar, e o Julio
                # autorizou por voz ("se o asset nao tem na galeria, vc precisa criar com
                # o higgsfield") depois do diretor de arte medir 13,3s e 9,9s de rosto
                # continuo, que o gate de ritmo reprova.
                # A trava continua sendo a MESMA: sem motivo escrito no
                # _fidelidade_excecoes.json, reprova. O que muda e so a direcao, nao o
                # rigor. Insert ADITIVO nunca altera a copy do bloco: se a fala mudar, a
                # divergencia aparece na comparacao de texto, que roda em separado.
                # A chave pode ser o marcador do DOC ou `bloco:<i>`. O marcador se
                # repete ("Thales de frente para a camera" aparece varias vezes), entao
                # a chave posicional e a precisa: libera UM bloco, nao a categoria.
                if td == "avatar" and tr == "insert" and (
                        exc_ad.get(blocos[i]["marcador"]) or exc_ad.get(f"bloco:{i}")):
                    continue
                problemas.append(f"estrutura: bloco {i} e '{td}' no doc e '{tr}' no roteiro")
        # direcao visual com marcador de lista (❌ ✅ •) que virou texto corrido
        # o lettering do composite v2 mora no CONFIG (letterings[]), nao no roteiro:
        # procurar a direcao em lista nos dois lugares, senao acusa perda que ja foi
        # corrigida no config.
        # FONTE DE VERDADE e o ads_v2_configs.py, nao o _cfg_*.json: o build REGENERA
        # o json a cada rodada (build_composite escreve por cima), entao ler o json
        # aqui media o arquivo velho e acusava perda que ja tinha sido corrigida.
        alvos_texto = list(blocos_rot)
        try:
            # (migracao 26/08/2026) codigo agora vizinho; import direto resolve
            import ads_v2_configs
            c = ads_v2_configs.ADS.get(f"{ad}v2", {})
        except Exception:
            c = {}
        for lt in c.get("letterings", []):
            alvos_texto.append(f"{lt.get('lead','')} {lt.get('key','')}")
        h = c.get("hook") or {}
        alvos_texto.append(" ".join(str(v) for v in h.values()))

        # LETTERING MARCADO NO ROTEIRO QUE NAO EXISTE NO CONFIG (17/08/2026).
        # Como o defeito passou: o roteiro do jh13 pede lettering em QUATRO blocos e eu
        # escrevi so TRES no ads_v2_configs.py, esquecendo justamente o do CTA. A tela
        # ficou sem nada no pico de intencao e nenhum gate percebeu, porque todos olhavam
        # o que ESTAVA la, nunca o que o roteiro pediu e nao chegou. Reprovou na auditoria
        # do diretor de arte, com nota 4,5.
        blocos_com_lettering = [b for b in blocos_rot if "lettering" in norm(b)]
        n_cfg = len(c.get("letterings", []))
        if blocos_com_lettering and n_cfg < len(blocos_com_lettering):
            problemas.append(
                f"o roteiro marca lettering em {len(blocos_com_lettering)} bloco(s) e o "
                f"config tem {n_cfg}. Algum lettering pedido nao vai aparecer na tela. "
                "Confira ads_v2_configs.py contra os marcadores [.. lettering ..].")

        # ANCORA AMBIGUA DE LETTERING (17/08/2026): o lettering pousa na enesima
        # ocorrencia da palavra `anchor` na fala, e `nth` default e 1. Se a palavra
        # aparece mais de uma vez e ninguem escolheu qual, o lettering cai no lugar
        # errado e aparece com a voz falando outra coisa. Aconteceu com "campanha".
        fala_toda = " ".join(re.sub(r"^\[[^\]]*\]\s*", "", l) for l in
                             rot.read_text().strip().split("\n"))
        for lt in c.get("letterings", []):
            a = norm(lt.get("anchor", "")).strip()
            if not a:
                continue
            n_ocor = len(re.findall(rf"\b{re.escape(a)}\b", norm(fala_toda)))
            if n_ocor > 1 and not lt.get("nth"):
                problemas.append(
                    f"lettering '{lt.get('key','')}': ancora '{a}' aparece {n_ocor}x na "
                    "fala e nao tem 'nth' definido. Sem escolher a ocorrencia o "
                    "lettering pousa na primeira e sai fora de sincronia com a voz.")

        # SINCRONIA DA CADEIA DE CONFIG (17/08/2026, custou um build inteiro):
        # ads_v2_configs.py (fonte) -> `python3 ads_v2_configs.py` -> configs/<ad>_<lk>.json
        # -> build_composite -> _cfg_*.json. O build le o configs/, nao a fonte. Editar a
        # fonte sem regerar deixava o gate medindo a fonte (verde) e o build usando o
        # arquivo velho: hook e letterings sumiam do video com o gate dizendo OK.
        for base_p in (V2L / "configs").glob(f"{pref}{ad}v2_*.json"):
            try:
                gerado = json.loads(base_p.read_text())
            except Exception:
                continue
            for campo in ("hook", "letterings"):
                if c.get(campo) and gerado.get(campo) != c.get(campo):
                    problemas.append(
                        f"config gerado DESATUALIZADO em {base_p.name}: '{campo}' difere "
                        "de ads_v2_configs.py (a fonte). Rode "
                        "'python3 ads_v2_configs.py' antes de buildar, senao o video "
                        "sai com a versao velha e o gate nao ve.")
        for gi in range(g_ini, g_fim):
            l = todas[gi]
            if l.count("❌") >= 2 or l.count("✅") >= 2:
                # cada item da lista precisa aparecer em ALGUM lettering/bloco
                # so o que vem DEPOIS de cada marcador e item; o texto antes do
                # primeiro ❌ e a entrada da frase ("Enquanto isso:"), nao um item.
                itens = [t.strip() for t in re.findall(r"[❌✅]\s*([^❌✅\v\n]+)", l)
                         if len(t.strip()) > 8]
                # cobertura por PALAVRAS, nao por prefixo de 18 chars: um "e" a mais
                # no comeco do item deslocava a fatia e dava falso negativo.
                def coberto(it):
                    palavras = [w for w in norm(it).split() if len(w) > 2]
                    if not palavras:
                        return False
                    return any(
                        sum(1 for w in palavras if w in norm(x)) >= max(2, len(palavras) - 1)
                        for x in alvos_texto)
                cobertos = sum(1 for it in itens if coberto(it))
                if cobertos < len(itens):
                    estrutura.append(f"{l}  [cobertos {cobertos}/{len(itens)}]")
        for l in estrutura:
            n_itens = l.count("❌") + l.count("✅")
            problemas.append(f"direcao visual perdida: '{l[:60]}...' tem {n_itens} itens "
                             "marcados no doc e precisa aparecer como lista na tela")

    if como_json:
        print(json.dumps({"ad": ad, "itens": relatorio, "problemas": problemas,
                          "estrutura_perdida": estrutura}, ensure_ascii=False, indent=2))
    else:
        print(f"\n=== FIDELIDADE AO DOC: {ad} ({cfg['secao']} / {cfg['aba']}) ===")
        for it in relatorio:
            alvo = ", ".join(f"{p}_{i}"[:24] for p, i in it["esperados"]) or "(sem asset no doc)"
            print(f"\n  [{it['marcador']}]")
            print(f"    doc  : {alvo}")
            print(f"    build: {it['usado']}")
            print(f"    {it['status']}" + (f"  motivo: {it['excecao']}" if it["excecao"] else ""))
        if problemas:
            print("\n  >> REPROVA:")
            for p in problemas:
                print("     - " + p)
        else:
            print("\n  >> PASSA: todo insert bate com o doc")
    sys.exit(1 if problemas else 0)


if __name__ == "__main__":
    main()
