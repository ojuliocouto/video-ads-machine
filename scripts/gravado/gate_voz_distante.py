"""Gate de VOZ DISTANTE: acha fala que NÃO é do expert dentro dos trechos escolhidos.

Ele grava no microfone de lapela, então a voz dele chega alta e constante. Quem fala fora de
quadro (quem dirige, gente do evento) chega distante, 6 a 12 dB mais baixo: o nível separa os dois
sem precisar reconhecer quem é. Um bloco de fala cujo pico está 6 dB ou mais abaixo da MEDIANA dos
blocos longos do take (0,5 s ou mais) é voz distante; 5 dB abaixo, não.

Nasceu de um defeito real: o token do ASR ("Quanto", de 1,50 a 9,58 s) abrangia as DUAS vozes, o
corte começou em 1,50 e o anúncio abria com 8 segundos de outra pessoa falando.

    python3 scripts/gravado/gate_voz_distante.py [--projeto DIR]
Saída: 0 passou, 1 voz distante dentro de um trecho, 2 insumo inválido.
"""
import argparse
import statistics
import sys
from pathlib import Path

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado import projeto as gp  # noqa: E402
from gravado import veredito  # noqa: E402
from gravado.nucleo import segmentos  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402

NOME = "gate_voz_distante"
MARGEM_DB = 6.0           # quanto abaixo da voz do expert já conta como distante
MIN_LONGO_S = 0.5         # só blocos longos definem a voz do expert
REF_PADRAO_DB = -10.0     # sem nenhum bloco longo
FOLGA_S = 0.05            # sobreposição mínima com o trecho para contar


def classificar(blocos, margem_db=MARGEM_DB):
    """(nível de referência, [blocos distantes]). `blocos`: [(início, fim, pico_dB)]."""
    longos = [pk for a, b, pk in blocos if b - a >= MIN_LONGO_S]
    ref = float(statistics.median(longos)) if longos else REF_PADRAO_DB
    return ref, [(a, b, pk) for a, b, pk in blocos if pk <= ref - margem_db + 1e-9]


def blocos_do_take(audio):
    return segmentos.blocos_com_pico(audio)


def verificar(trechos, blocos_por_take, margem_db=MARGEM_DB):
    """(ok, motivo). `trechos`: [(rótulo, take, início, fim)]; `blocos_por_take`: {take: [(a, b, pico)]}."""
    suspeitos, achados = {}, []
    for take, blocos in blocos_por_take.items():
        if not blocos:
            raise InsumoInvalido("o take %s não tem nenhum bloco de fala medido: confira o áudio limpo" % take)
        suspeitos[take] = classificar(blocos, margem_db)
    for rotulo, take, ini, fim in trechos:
        if take not in suspeitos:
            raise InsumoInvalido("o take %s do trecho %s não foi medido" % (take, rotulo))
        ref, sus = suspeitos[take]
        dentro = [(a, b, pk) for a, b, pk in sus if b > ini + FOLGA_S and a < fim - FOLGA_S]
        if dentro:
            total = sum(min(b, fim) - max(a, ini) for a, b, _ in dentro)
            amostra = ", ".join("%.1f-%.1fs(%.0fdB)" % (max(a, ini), min(b, fim), pk) for a, b, pk in dentro[:3])
            achados.append("%s %s %.2f a %.2f: %.1fs de voz distante (referência %.0f dB): %s"
                           % (rotulo, take, ini, fim, total, ref, amostra))
    if achados:
        return False, "voz distante dentro de %d trecho(s):\n  %s" % (len(achados), "\n  ".join(achados))
    return True, "nenhuma voz distante dentro de %d trecho(s) de %d take(s)" % (len(trechos), len(blocos_por_take))


def verificar_projeto(proj, leitor=None, pecas=None):
    todos = proj.todos_os_trechos()
    if not todos:
        raise InsumoInvalido("o plano não tem trechos: preencha os anúncios depois de ler os takes")
    trechos = [("%s.%s" % (cod, chave), take, ini, fim) for cod, chave, take, ini, fim in todos]
    blocos = {}
    for take in sorted({t for _, t, _, _ in trechos}):
        blocos[take] = blocos_do_take(veredito.exigir_arquivo(proj.limpo(take), "o áudio limpo do take %s (rode o isolar)" % take))
    return verificar(trechos, blocos)


def _parser():
    ap = argparse.ArgumentParser(prog=NOME, description="Acha fala de outra pessoa dentro dos trechos.")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    return ap


def _verificar(args):
    return verificar_projeto(gp.carregar(args.projeto))


def main(argv=None):
    return veredito.cli(NOME, _parser(), _verificar, argv)


if __name__ == "__main__":
    sys.exit(main())
