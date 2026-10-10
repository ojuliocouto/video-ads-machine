"""Legenda ASS a partir das palavras com tempo (borda real, não token inflado).

O TEXTO da legenda é o da transcrição JÁ corrigida pelo glossário do aluno (`nucleo.asr` aplica a
troca de grafia na saída). O pipeline de origem trazia um dicionário de correções do cliente
dentro deste arquivo; ele virou o glossário do projeto. Legenda errada é pior que legenda
nenhuma: o espectador lê e ouve ao mesmo tempo, e o ASR chegou a inserir um "não" que INVERTIA o
sentido. Por isso o texto nunca é inventado aqui: só se quebra em linhas, nunca se reescreve.

Regras de linha (medidas no material de origem):
  - no máximo MAX_CHARS caracteres e MAX_PALAVRAS palavras por linha;
  - quebra em pausa maior que QUEBRA_PAUSA_S e depois de fim de frase (. ! ?);
  - a linha fica na tela ATÉ a próxima entrar (teto de SEGURA_MAX_S de sobra), senão a tela fica
    sem texto na pausa entre frases e o gate de legenda reprova; a última segura CAUDA_S;
  - nenhuma legenda dura menos de DUR_MIN_S.

Destaque (cor de ênfase): números, preços e as palavras dos termos de MARCA e PRODUTO do
glossário do aluno. Nome de pessoa não ganha cor. `omitir` tira palavras só da legenda (o áudio
fica); por padrão nada é omitido.

## Relatório fala x roteiro e aprovação (W5.D)

Toda legenda gerada traz `legendas/<peça>.relatorio.json`: o que a peça diz contra o roteiro do
anúncio (`roteiros/<COD>.md`, ou o `roteiro.md` quando o plano tem um anúncio só), com a mesma régua do
gate de entrada (mais de 2% das palavras faltando, ou 3 palavras seguidas sumidas, reprova) e só as
equivalências declaradas no glossário. Sem roteiro o relatório diz `SEM_ROTEIRO`: nunca finge que conferiu.

A legenda só vira filme depois que o DIRETOR a aprova: `aprovar` grava
`legendas/<peça>.aprovacao.json` com o texto do ok e o sha256 do .ass e do relatório. Este módulo é o
ÚNICO que escreve esse arquivo (um teste varre os scripts atrás de quem mais escreve): quem é medido não
assina, então o montador, o gerador e o queimador só LEEM, por `exigir_aprovada`. Mexer 1 byte no .ass
depois do ok, ou gerar a legenda de novo, vence a aprovação.

    python3 scripts/gravado/legendar.py [PECA ...] [--projeto DIR] [--omitir PALAVRA ...]
"""
import argparse
import hashlib
import re
import sys
import unicodedata
from collections import namedtuple
from pathlib import Path

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from contratos.validar import normalizar_palavra  # noqa: E402
from contratos.validar import palavras as palavras_do_texto  # noqa: E402
from entrada import roteiro_md  # noqa: E402
from gates import gate_fala_roteiro  # noqa: E402
from gravado import projeto as gp  # noqa: E402
from gravado.nucleo.asr import ErroDeASR  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402
from projeto import glossario as _glossario  # noqa: E402
from projeto import status as _status  # noqa: E402

LARGURA, ALTURA = 1080, 1920
Y_LEGENDA = 1300               # baseline da legenda, acima da faixa de UI do Reels
MAX_CHARS = 30
MAX_PALAVRAS = 5
QUEBRA_PAUSA_S = 0.45
SEGURA_MAX_S = 1.6
CAUDA_S = 0.5
DUR_MIN_S = 0.3
FONTE = "Inter"
COR_ENFASE = r"&H4E7DE8&"      # terracota (BGR)
COR_BASE = r"&HFFFFFF&"
_RE_NUMERO = re.compile(r"r?\$?\d+[\d.,/]*")
_RE_TAG = re.compile(r"\{[^}]*\}")
RELATORIO_SUFIXO = ".relatorio.json"
APROVACAO_SUFIXO = ".aprovacao.json"
OK_MIN, OK_MAX = 2, 2000
Situacao = namedtuple("Situacao", "vigente motivo")


class LegendaNaoAprovada(InsumoInvalido, RuntimeError):
    """A legenda não tem o ok do diretor (ou o ok venceu). Queimar e entregar param aqui."""


def cabecalho():
    return (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\nWrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Base,%s,66,&H00FFFFFF,&H00000000,&H78000000,1,0,0,0,100,100,0.6,0,1,0,3,2,70,70,%d,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        % (LARGURA, ALTURA, FONTE, ALTURA - Y_LEGENDA))


def tempo(t):
    """h:mm:ss.cc do ASS, em centésimos inteiros (59,996 s vira 0:01:00.00, nunca 0:00:60.00)."""
    cs = int(round(float(t) * 100))
    h, resto = divmod(cs, 360000)
    m, cs = divmod(resto, 6000)
    return "%d:%02d:%05.2f" % (h, m, cs / 100.0)


def sem_tags(texto):
    return _RE_TAG.sub("", texto)


def _nucleo(palavra):
    q = unicodedata.normalize("NFD", str(palavra).lower())
    q = "".join(c for c in q if unicodedata.category(c) != "Mn")
    return q.strip(".,!?;:")


def destaques_do_glossario(glossario):
    """Palavras (normalizadas) dos termos de marca e produto do glossário."""
    saida = set()
    for termo in (glossario or {}).get("termos", []):
        if termo.get("tipo") in ("marca", "produto"):
            for palavra in termo["grafia"].split():
                saida.add(_nucleo(palavra))
    return frozenset(x for x in saida if x)


def destaca(palavra, destacar=frozenset()):
    q = _nucleo(palavra)
    return q in destacar or bool(_RE_NUMERO.fullmatch(q))


def omitir_palavras(palavras, omitir):
    omitir = {_nucleo(x) for x in (omitir or ())}
    return [p for p in palavras if _nucleo(p["text"]) not in omitir] if omitir else list(palavras)


def linhas(ps):
    """Agrupa as palavras em linhas de legenda."""
    saida, atual = [], []
    for p in ps:
        cand = atual + [p]
        txt = " ".join(x["text"] for x in cand)
        quebra = (len(txt) > MAX_CHARS or len(cand) > MAX_PALAVRAS
                  or (atual and p["start"] - atual[-1]["end"] > QUEBRA_PAUSA_S)
                  or (atual and re.search(r"[.!?]$", atual[-1]["text"])))
        if quebra and atual:
            saida.append(atual)
            atual = [p]
        else:
            atual = cand
    if atual:
        saida.append(atual)
    return saida


def eventos(ls, destacar=frozenset()):
    """[(início, fim, texto com tags de cor)] de cada linha."""
    saida = []
    for i, ln in enumerate(ls):
        a = ln[0]["start"]
        if i + 1 < len(ls):
            b = min(ls[i + 1][0]["start"], ln[-1]["end"] + SEGURA_MAX_S)
        else:
            b = ln[-1]["end"] + CAUDA_S
        if b - a < DUR_MIN_S:
            b = a + DUR_MIN_S
        txt = " ".join(
            (r"{\c%s}" % COR_ENFASE + p["text"] + r"{\c%s}" % COR_BASE) if destaca(p["text"], destacar) else p["text"]
            for p in ln)
        saida.append((a, b, txt))
    return saida


def ass_texto(palavras, destacar=frozenset(), omitir=()):
    """(texto do arquivo ASS, linhas)."""
    ls = linhas(omitir_palavras(palavras, omitir))
    dialogos = ["Dialogue: 0,%s,%s,Base,,0,0,0,,%s" % (tempo(a), tempo(b), txt)
                for a, b, txt in eventos(ls, destacar)]
    return cabecalho() + "\n".join(dialogos) + "\n", ls


def gerar(palavras, destino, destacar=frozenset(), omitir=()):
    """Escreve o ASS em `destino`. Devolve (número de linhas, amostra das 4 primeiras)."""
    texto, ls = ass_texto(palavras, destacar, omitir)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    return len(ls), " | ".join(" ".join(p["text"] for p in ln) for ln in ls[:4])


def sha256_arquivo(caminho):
    h = hashlib.sha256()
    with open(str(caminho), "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def _codigo(nome):
    return str(nome).rsplit("_", 1)[0]


def caminho_relatorio(proj, nome):
    return proj.pasta("legendas") / (nome + RELATORIO_SUFIXO)


def caminho_aprovacao(proj, nome):
    return proj.pasta("legendas") / (nome + APROVACAO_SUFIXO)


def roteiro_da_peca(proj, nome):
    """O roteiro do anúncio da peça: `roteiros/<COD>.md` (ou .txt), senão o `roteiro.md` do projeto, que só
    vale quando o plano tem UM anúncio (com dois, o roteiro único não diz de qual é). None se não há."""
    cod = _codigo(nome)
    for ext in (".md", ".txt"):
        c = proj.base / "roteiros" / (cod + ext)
        if c.is_file():
            return c
    if len(proj.ads) == 1:
        for ext in (".md", ".txt"):
            c = proj.base / ("roteiro" + ext)
            if c.is_file():
                return c
    return None


def _texto_do_roteiro(caminho):
    try:
        lei = roteiro_md.ler_arquivo(caminho)
    except ValueError as e:
        raise InsumoInvalido(str(e))
    if lei.erros:
        raise InsumoInvalido("o roteiro %s está fora da convenção:\n%s" % (caminho, roteiro_md.formatar_erros(lei.erros)))
    return lei.fala_completa()


def relatorio_fala_roteiro(nome, palavras, roteiro_texto, glossario):
    """Relatório do que a legenda (as `palavras` da peça) diz contra o `roteiro_texto`. Puro.

    `palavras`: textos ou dicts {text,...}. `roteiro_texto` None = sem roteiro (estado SEM_ROTEIRO).
    Mesma régua e mesmo alinhamento do `gate_fala_roteiro`: palavra do roteiro que não aparece conta como
    FALTANDO (mais de 2% reprova, 3 seguidas reprova); palavra a mais é só contada. Troca de palavra: só a
    equivalência declarada no glossário."""
    fala_txt = " ".join(str(p["text"]) if isinstance(p, dict) else str(p) for p in palavras)
    fala = palavras_do_texto(fala_txt)
    if roteiro_texto is None:
        return {"versao": 1, "peca": nome, "estado": "SEM_ROTEIRO", "palavras_fala": len(fala)}
    roteiro = palavras_do_texto(roteiro_texto)
    originais = [w for w in roteiro_texto.split() if normalizar_palavra(w)]
    if len(originais) != len(roteiro):          # palavra composta: mostra o texto já normalizado
        originais = list(roteiro)
    eqs = [(palavras_do_texto(a), palavras_do_texto(b)) for a, b in _glossario.equivalencias(glossario or {})]
    cmp = gate_fala_roteiro.comparar(roteiro, fala, eqs)
    n, perdidas = len(roteiro), len(cmp.faltando_idx)
    fracao = perdidas / float(n) if n else 0.0
    reprova = fracao > gate_fala_roteiro.FALTANDO_MAX or cmp.maior_sequencia >= gate_fala_roteiro.SEQUENCIA_MAX
    return {"versao": 1, "peca": nome, "estado": "REPROVA" if reprova else "PASS", "palavras_roteiro": n,
            "palavras_fala": len(fala), "faltando": perdidas, "fracao_faltando": round(fracao, 4),
            "maior_sequencia": cmp.maior_sequencia, "extras": cmp.extras,
            "trechos_faltando": gate_fala_roteiro._trechos(originais, cmp.faltando_idx)[
                :gate_fala_roteiro.MAX_TRECHOS_NO_RELATORIO],
            "limiares": {"faltando_max": gate_fala_roteiro.FALTANDO_MAX,
                         "sequencia_max": gate_fala_roteiro.SEQUENCIA_MAX}}


def resumo_do_relatorio(rel):
    """Uma linha para o terminal."""
    if rel["estado"] == "SEM_ROTEIRO":
        return "SEM_ROTEIRO (não há roteiro do anúncio: a legenda NÃO foi conferida contra o que se pediu)"
    base = "%s: %d de %d palavras do roteiro faltando (%.1f%%), %d a mais na fala, maior sequência sumida %d" % (
        rel["estado"], rel["faltando"], rel["palavras_roteiro"], 100 * rel["fracao_faltando"], rel["extras"],
        rel["maior_sequencia"])
    return base + ((" | sumiu: " + "; ".join(rel["trechos_faltando"][:3])) if rel["trechos_faltando"] else "")


def gerar_relatorio(proj, nome, palavras):
    """Escreve `legendas/<peça>.relatorio.json` amarrado ao sha do .ass atual. Devolve o relatório."""
    caminho = roteiro_da_peca(proj, nome)
    rel = relatorio_fala_roteiro(nome, palavras, None if caminho is None else _texto_do_roteiro(caminho),
                                 proj.glossario())
    rel["roteiro"] = None if caminho is None else caminho.relative_to(proj.base).as_posix()
    if caminho is not None:
        rel["roteiro_sha256"] = sha256_arquivo(caminho)
    rel["ass_sha256"] = sha256_arquivo(proj.legenda_ass(nome))
    _status.escrever_json_atomico(caminho_relatorio(proj, nome), rel)
    return rel


def legendar_pecas(proj, nomes, leitor, omitir=(), relatorio=None):
    """Gera `legendas/<peça>.ass` e o relatório fala x roteiro de cada peça. Devolve {peça: número de linhas}.

    O tempo de palavra EXIGE backend de borda real (parakeet ou faster-whisper): o leitor recusa
    a Groq. O texto vem da transcrição já corrigida pelo glossário do aluno, e a cor de destaque também."""
    glossario = proj.glossario()
    destacar = destaques_do_glossario(glossario)
    feitos = {}
    for nome in nomes:
        origem = proj.fonte_da_peca(nome)
        if not Path(origem).is_file():
            raise InsumoInvalido("não achei a peça %s para legendar: %s (monte antes)" % (nome, origem))
        palavras = leitor.palavras(origem, exigir_borda=True)
        n, amostra = gerar(palavras, proj.legenda_ass(nome), destacar, omitir)
        rel = gerar_relatorio(proj, nome, omitir_palavras(palavras, omitir))
        feitos[nome] = n
        if relatorio:
            relatorio("%s: %d linhas | %s" % (nome, n, amostra))
            relatorio("   fala x roteiro: %s" % resumo_do_relatorio(rel))
    return feitos


# --- aprovação do diretor ------------------------------------------------------------------------

def _ler_json(caminho):
    try:
        return _status.ler_json(caminho)
    except (ValueError, OSError):
        return None


def aprovar(proj, nome, ok, divergencia_aceita=False, agora=None):
    """Grava o ok do diretor à legenda de `nome`, amarrado por sha256 ao .ass e ao relatório. Devolve o dict.

    Recusa (InsumoInvalido, nada gravado) sem o texto do ok, sem a legenda, sem o relatório, com relatório
    de outra versão do .ass, ou com relatório REPROVA sem `divergencia_aceita`."""
    if not isinstance(ok, str) or len(ok.strip()) < OK_MIN:
        raise InsumoInvalido("sem o ok do diretor não há aprovação: passe o texto do ok, como ele escreveu no "
                             "chat (pelo menos %d caracteres)" % OK_MIN)
    ok = ok.strip()
    if len(ok) > OK_MAX:
        raise InsumoInvalido("o texto do ok tem %d caracteres; o limite é %d" % (len(ok), OK_MAX))
    ass = proj.legenda_ass(nome)
    if not ass.is_file():
        raise InsumoInvalido("não há legenda de %s em %s: rode `vam gravado %s legendar %s` antes de aprovar"
                             % (nome, ass, proj.base.name, nome))
    rel_arq = caminho_relatorio(proj, nome)
    rel = _ler_json(rel_arq) if rel_arq.is_file() else None
    if rel is None:
        raise InsumoInvalido("não há relatório fala x roteiro de %s: gere a legenda de novo (legendar) para ele "
                             "nascer junto" % nome)
    sha_ass = sha256_arquivo(ass)
    if rel.get("ass_sha256") != sha_ass:
        raise InsumoInvalido("o relatório de %s é de outra versão do .ass (a legenda mudou depois dele): gere a "
                             "legenda de novo para o relatório e o .ass voltarem a casar" % nome)
    if rel.get("estado") == "REPROVA" and not divergencia_aceita:
        raise InsumoInvalido("a legenda de %s diverge do roteiro (relatório REPROVA: %s). Leia %s; se a diferença é "
                             "improviso que o diretor aceita, aprove com --divergencia-aceita"
                             % (nome, resumo_do_relatorio(rel), rel_arq))
    aprovacao = {"versao": 1, "emissor": "gravado.legendar", "peca": nome, "ok": ok,
                 "aprovado_em": agora if agora is not None else _status.instante(),
                 "ass": {"arquivo": ass.relative_to(proj.base).as_posix(), "sha256": sha_ass},
                 "relatorio": {"arquivo": rel_arq.relative_to(proj.base).as_posix(),
                               "sha256": sha256_arquivo(rel_arq), "estado": rel.get("estado")},
                 "divergencia_aceita": bool(divergencia_aceita)}
    _status.escrever_json_atomico(caminho_aprovacao(proj, nome), aprovacao)
    return aprovacao


def situacao(proj, nome):
    """Situacao(vigente, motivo): a aprovação existe e é do .ass que está no disco agora?"""
    arq = caminho_aprovacao(proj, nome)
    como = "aprove com `vam gravado %s aprovar-legenda %s --ok \"<o ok do diretor>\"`" % (proj.base.name, nome)
    if not arq.is_file():
        return Situacao(False, "a legenda de %s não tem aprovação: leia %s e o relatório, e %s"
                               % (nome, proj.legenda_ass(nome), como))
    ap = _ler_json(arq)
    if not isinstance(ap, dict) or not isinstance(ap.get("ass"), dict) or not ap["ass"].get("sha256"):
        return Situacao(False, "a aprovação de %s está ilegível (%s): %s" % (nome, arq, como))
    ass = proj.legenda_ass(nome)
    if not ass.is_file():
        return Situacao(False, "a legenda aprovada de %s sumiu (%s): gere de novo e %s" % (nome, ass, como))
    if sha256_arquivo(ass) != ap["ass"]["sha256"]:
        return Situacao(False, "a legenda de %s mudou depois da aprovação (o sha256 do .ass não é o aprovado): "
                               "leia a versão atual e %s" % (nome, como))
    return Situacao(True, "legenda de %s aprovada: %s" % (nome, ap.get("ok", "")))


def exigir_aprovada(proj, nome):
    """A aprovação vigente (dict), ou LegendaNaoAprovada com o que fazer."""
    s = situacao(proj, nome)
    if not s.vigente:
        raise LegendaNaoAprovada(s.motivo)
    return _ler_json(caminho_aprovacao(proj, nome))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gera a legenda ASS das peças montadas.")
    ap.add_argument("pecas", nargs="*", help="nomes das peças, como A1_normal (padrão: todas do plano)")
    ap.add_argument("--projeto")
    ap.add_argument("--omitir", nargs="*", default=[], help="palavras que saem da legenda (o áudio fica)")
    a = ap.parse_args(argv)
    try:
        proj = gp.carregar(a.projeto)
        nomes = a.pecas or [n for n in proj.nomes_das_pecas() if Path(proj.fonte_da_peca(n)).is_file()]
        if not nomes:
            raise InsumoInvalido("nenhuma peça montada em %s: rode o montar antes" % proj.pasta("montados"))
        legendar_pecas(proj, nomes, proj.leitor(), omitir=a.omitir, relatorio=print)
    except InsumoInvalido as e:
        print(str(e), file=sys.stderr)
        return 2
    except ErroDeASR as e:
        print("ASR: %s" % e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
