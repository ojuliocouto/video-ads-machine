"""Gate de RETOMADA: lê o áudio SUB-BLOCO a SUB-BLOCO e compara os vizinhos por SIMILARIDADE.

Fecha dois furos que a comparação por frase não fecha:

  1. Retomada com pausa CURTA (0,3 s): o separador de frase junta os dois lados num bloco só e o
     ASR entrega o texto já "limpo" (ele deduplica). Por isso o segundo passe, com separador de
     0,14 s (`nucleo.segmentos.subblocos`), e a leitura de cada sub-bloco separado.
  2. Retomada com palavra trocada ("vou te dar UM exemplo" e "vou te dar O exemplo"), que a
     comparação exata de n-grama não pega: por isso a similaridade (SIMIL), não a igualdade.

Compara cada sub-bloco com os dois seguintes. Acusa também FRAGMENTO: sub-bloco curto (menos de
12 letras e 0,7 s) na BORDA de um trecho que tem mais de um sub-bloco, a sobra de uma frase
descartada. Interjeição no meio do trecho, e trecho de uma frase só, não são fragmento.

Fragmento ACEITO (pendência 12.4, W5.A): o curto na borda que o diretor quis (uma vinheta, um "então," de
abertura) é declarado no plano do anúncio, `fragmentos_aceitos: [[take, instante, motivo]]`. O fragmento do mesmo
take que cobre o instante (com TOLERANCIA_ACEITO_S de folga) não reprova e aparece no relatório com o motivo.

Cobre as duas versões de cada anúncio (normal e desconto): o corpo com cada CTA, nas quatro
chaves do plano. Conferir só "os principais" e deixar o CTA para depois deixou passar reprovação.

    python3 scripts/gravado/gate_retomada.py [PECA ...] [--projeto DIR]
Saída: 0 passou, 1 retomada ou fragmento, 2 insumo inválido (ASR falhou, sem áudio limpo).
"""
import argparse
import difflib
import re
import sys
import unicodedata
from collections import namedtuple
from pathlib import Path

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado import projeto as gp  # noqa: E402
from gravado import veredito  # noqa: E402
from gravado.nucleo import segmentos  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402

NOME = "gate_retomada"
SIMIL = 0.55
MIN_CHARS = 12
FRAGMENTO_MAX_S = 0.7
TOLERANCIA_ACEITO_S = 0.15

SubBloco = namedtuple("SubBloco", "ini fim texto na_borda take", defaults=(None,))


def _norm(texto):
    t = unicodedata.normalize("NFD", texto.lower())
    return " ".join(re.findall(r"[a-z0-9]+", "".join(c for c in t if unicodedata.category(c) != "Mn")))


def achar(subs, simil=SIMIL):
    """([(i, j, similaridade)] de retomadas, [i] de fragmentos) numa sequência de SubBloco."""
    retomadas = []
    for i in range(len(subs) - 1):
        for j in (i + 1, i + 2):
            if j >= len(subs):
                continue
            x, y = _norm(subs[i].texto), _norm(subs[j].texto)
            if len(x) < MIN_CHARS or len(y) < MIN_CHARS:
                continue
            r = difflib.SequenceMatcher(None, x, y).ratio()
            if r >= simil:
                retomadas.append((i, j, r))
    fragmentos = [i for i, s in enumerate(subs)
                  if s.na_borda and len(_norm(s.texto)) < MIN_CHARS and s.fim - s.ini < FRAGMENTO_MAX_S]
    return retomadas, fragmentos


def coletar(limpo_de, trechos, leitor):
    """Lê todos os sub-blocos dos `trechos` [(take, ini, fim)], na ordem do anúncio."""
    subs = []
    for take, ini, fim in trechos:
        audio = limpo_de(take)
        pedacos = segmentos.subblocos(audio, ini, fim)
        for k, (a, b) in enumerate(pedacos):
            na_borda = len(pedacos) > 1 and k in (0, len(pedacos) - 1)
            subs.append(SubBloco(a, b, leitor.texto(audio, a, b), na_borda, take))
    return subs


def aceito(sub, aceitos, tol=TOLERANCIA_ACEITO_S):
    """O motivo do fragmento aceito que cobre o sub-bloco (mesmo take, instante dentro dele), ou None."""
    for take, t, motivo in aceitos or ():
        if sub.take == take and sub.ini - tol <= float(t) <= sub.fim + tol:
            return motivo
    return None


def verificar_versoes(versoes, aceitos=None):
    """(ok, motivo). `versoes`: {nome da peça: [SubBloco]}. `aceitos`: [(take, instante, motivo)] dos fragmentos
    que o plano declara (vale para todas as versões), ou {nome da peça: [...]}."""
    linhas, total, aceitas = [], 0, []
    for nome, subs in versoes.items():
        if not subs:
            raise InsumoInvalido("a peça %s não tem nenhum sub-bloco de fala: confira os trechos do plano" % nome)
        retomadas, fragmentos = achar(subs)
        do_nome = aceitos.get(nome, []) if isinstance(aceitos, dict) else aceitos
        sobra = []
        for i in fragmentos:
            motivo = aceito(subs[i], do_nome)
            if motivo:
                aceitas.append("%s fragmento em %.2fs %r aceito no plano: %s" % (nome, subs[i].ini, subs[i].texto, motivo))
            else:
                sobra.append(i)
        fragmentos = sobra
        for i, j, r in retomadas:
            total += 1
            linhas.append("%s RETOMADA %.0f%%:\n     [%7.2f] %s\n     [%7.2f] %s"
                          % (nome, 100 * r, subs[i].ini, subs[i].texto, subs[j].ini, subs[j].texto))
        for i in fragmentos:
            total += 1
            linhas.append("%s FRAGMENTO em %.2fs: %r (na borda de um trecho)" % (nome, subs[i].ini, subs[i].texto))
    nota = ("\n  " + "\n  ".join(aceitas)) if aceitas else ""
    if total:
        return False, "%d ocorrência(s):\n  %s%s" % (total, "\n  ".join(linhas), nota)
    return True, "%d versão(ões), %d sub-blocos lidos, nenhuma retomada nem fragmento%s" % (
        len(versoes), sum(len(s) for s in versoes.values()), nota)


def verificar_projeto(proj, leitor=None, pecas=None):
    nomes = list(pecas or proj.nomes_das_pecas())
    if not nomes:
        raise InsumoInvalido("o plano não tem anúncios para conferir")
    versoes_do_plano = proj.versoes()
    leitor = leitor or proj.leitor()
    versoes, aceitos = {}, {}
    for nome in nomes:
        if nome not in versoes_do_plano:
            raise InsumoInvalido("a peça %s não está no plano (tem: %s)" % (nome, ", ".join(versoes_do_plano)))
        cod, desconto = versoes_do_plano[nome]
        for take, _, _ in proj.trechos_do_ad(cod, desconto):
            veredito.exigir_arquivo(proj.limpo(take), "o áudio limpo do take %s (rode o isolar)" % take)
        versoes[nome] = coletar(proj.limpo, proj.trechos_do_ad(cod, desconto), leitor)
        aceitos[nome] = proj.fragmentos_aceitos(cod)
    return verificar_versoes(versoes, aceitos)


def _parser():
    ap = argparse.ArgumentParser(prog=NOME, description="Retomada e fragmento, sub-bloco a sub-bloco.")
    ap.add_argument("pecas", nargs="*", help="nomes das peças, como A1_normal (padrão: todas do plano)")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    return ap


def _verificar(args):
    return verificar_projeto(gp.carregar(args.projeto), pecas=args.pecas or None)


def main(argv=None):
    return veredito.cli(NOME, _parser(), _verificar, argv)


if __name__ == "__main__":
    sys.exit(main())
