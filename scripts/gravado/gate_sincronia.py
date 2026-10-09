"""Gate de SINCRONIA: a peça LEGENDADA veio do corte ATUAL?

Nasceu de um erro real: o anúncio foi re-renderizado e esqueceram de re-legendar, então a pasta
de entrega tinha a versão velha com cara de nova. A comparação só por duração não pega a peça
TROCADA com a mesma duração, então o gate compara também o CONTEÚDO:

  1. duração da legendada contra a da fonte (a com caixinha, se existe; senão a montada), com
     tolerância de TOL_DURACAO_S;
  2. impressão digital de N_QUADROS quadros amostrados nos mesmos instantes: miniatura RGB de
     16 x 28 SEM a faixa da legenda (a legenda queimada é a única diferença esperada). O quadro
     vale se a diferença média de cor fica abaixo de MAX_DIF_COR E o hash de luminância (cada
     pixel acima ou abaixo da média) difere em menos de MAX_DIF_HASH dos bits.

A cor entra porque duas cores chapadas diferentes têm o mesmo hash de luminância; o hash entra
porque duas cenas diferentes podem ter a mesma cor média.

    python3 scripts/gravado/gate_sincronia.py LEGENDADA FONTE
    python3 scripts/gravado/gate_sincronia.py --projeto DIR [--pecas PECA ...]
Saída: 0 sincronizada, 1 desatualizada ou trocada, 2 insumo inválido.
"""
import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado import projeto as gp  # noqa: E402
from gravado import veredito  # noqa: E402
from gravado.nucleo import energia  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402

NOME = "gate_sincronia"
TOL_DURACAO_S = 0.25
N_QUADROS = 8
LARGURA_MINIATURA, ALTURA_MINIATURA = 16, 28
FAIXA_DA_LEGENDA = (0.55, 0.85)      # fração da altura onde a legenda queimada mora (fica de fora)
MAX_DIF_COR = 0.12                   # diferença média por canal, de 0 a 1
MAX_DIF_HASH = 0.25                  # fração de bits de luminância que podem diferir


duracao = energia.duracao_s


def _miniatura(caminho, t):
    """Quadro em t como array (ALTURA, LARGURA, 3) de 0 a 255."""
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-ss", "%.3f" % t, "-i", str(caminho), "-frames:v", "1",
           "-vf", "scale=%d:%d:flags=area,format=rgb24" % (LARGURA_MINIATURA, ALTURA_MINIATURA),
           "-f", "rawvideo", "-"]
    r = subprocess.run(cmd, capture_output=True)
    esperado = LARGURA_MINIATURA * ALTURA_MINIATURA * 3
    if r.returncode != 0 or len(r.stdout) != esperado:
        raise InsumoInvalido("não consegui amostrar o quadro de %.2fs em %s" % (t, caminho))
    return np.frombuffer(r.stdout, dtype=np.uint8).reshape(ALTURA_MINIATURA, LARGURA_MINIATURA, 3)


def _linhas_validas():
    ini, fim = FAIXA_DA_LEGENDA[0] * ALTURA_MINIATURA, FAIXA_DA_LEGENDA[1] * ALTURA_MINIATURA
    return [r for r in range(ALTURA_MINIATURA) if not (ini <= r < fim)]


def impressao(miniatura):
    """(pixels RGB fora da faixa da legenda, bits de luminância contra a média)."""
    v = miniatura[_linhas_validas()].astype(np.float64)
    luma = v @ np.array([0.299, 0.587, 0.114])
    return v, luma > luma.mean()


def distancias(a, b):
    """(diferença média de cor de 0 a 1, fração de bits de luminância que diferem)."""
    va, ba = impressao(a)
    vb, bb = impressao(b)
    return float(np.abs(va - vb).mean() / 255.0), float((ba != bb).mean())


def instantes(dur, n=N_QUADROS):
    return [float(t) for t in np.linspace(0.05 * dur, 0.95 * dur, n)]


def verificar(legendada, fonte, tol_dur_s=TOL_DURACAO_S, n=N_QUADROS):
    veredito.exigir_arquivo(legendada, "a peça legendada")
    veredito.exigir_arquivo(fonte, "a peça de origem (a com caixinha, ou a montada)")
    dl, df = duracao(legendada), duracao(fonte)
    nome = Path(str(legendada)).name
    if abs(dl - df) >= tol_dur_s:
        return False, ("%s: duração %.2fs contra %.2fs da fonte (tolerância %.2fs): a legendada não vem do "
                       "corte atual, legende de novo" % (nome, dl, df, tol_dur_s))
    ruins = []
    for t in instantes(df, n):
        cor, hash_ = distancias(_miniatura(legendada, t), _miniatura(fonte, t))
        if cor > MAX_DIF_COR or hash_ > MAX_DIF_HASH:
            ruins.append((t, cor, hash_))
    if ruins:
        t, cor, hash_ = ruins[0]
        return False, ("%s: %d de %d quadros amostrados não batem com a fonte (primeiro em %.2fs: cor %.0f%%, "
                       "hash %.0f%%): a legendada não é a mesma peça, legende de novo"
                       % (nome, len(ruins), n, t, 100 * cor, 100 * hash_))
    return True, "%s: duração %.2fs e %d quadros amostrados batem com a fonte" % (nome, dl, n)


def verificar_projeto(proj, leitor=None, pecas=None):
    nomes = list(pecas or proj.nomes_das_pecas())
    if not nomes:
        raise InsumoInvalido("o plano não tem anúncios para conferir")
    return veredito.juntar(verificar(proj.legendado(n), proj.fonte_da_peca(n)) for n in nomes)


def _parser():
    ap = argparse.ArgumentParser(prog=NOME, description="A legendada veio do corte atual?")
    ap.add_argument("arquivos", nargs="*", help="LEGENDADA FONTE (sem isso, usa o projeto)")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    ap.add_argument("--pecas", nargs="*", help="nomes das peças do projeto (padrão: todas)")
    return ap


def _verificar(args):
    if args.arquivos:
        if len(args.arquivos) != 2:
            raise InsumoInvalido("passe exatamente LEGENDADA e FONTE")
        return verificar(args.arquivos[0], args.arquivos[1])
    return verificar_projeto(gp.carregar(args.projeto), pecas=args.pecas or None)


def main(argv=None):
    return veredito.cli(NOME, _parser(), _verificar, argv)


if __name__ == "__main__":
    sys.exit(main())
