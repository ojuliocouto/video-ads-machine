"""Gate de ENVELOPE: o Voice Isolator comeu fala? Compara a energia do bruto com a do limpo.

É a prova que não depende do ASR: o ASR deduplica e completa frase, a energia não. Onde o bruto
tem VOZ e o limpo está MUDO por 0,5 s ou mais, houve perda.

Os limiares são calibrados POR TAKE, porque o piso de ruído do bruto varia (evento lotado) e um
limiar fixo abaixo desse piso acusaria como perda toda pausa que o isolador limpou:

  voz no bruto   10 dB acima do piso do take (percentil 10), e no máximo 25 dB abaixo do pico
  mudo no limpo  40 dB abaixo do pico do próprio limpo

Duração: o isolador preserva a duração. Um limpo mais curto que o bruto (mais de TOL_DURACAO_S)
é arquivo cortado, e a cauda que faltou conta como mudo: o gate não compara só o trecho em comum,
senão um limpo sem a cauda inteira passaria calado.

    python3 scripts/gravado/gate_envelope.py BRUTO LIMPO
    python3 scripts/gravado/gate_envelope.py --projeto DIR
Saída: 0 passou, 1 fala perdida ou arquivo cortado, 2 insumo inválido.
"""
import argparse
import sys
from pathlib import Path

import numpy as np

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado import projeto as gp  # noqa: E402
from gravado import veredito  # noqa: E402
from gravado.nucleo import energia, segmentos  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402

NOME = "gate_envelope"
JANELA_S = 0.25
MIN_BURACO_S = 0.5
TOL_DURACAO_S = 0.5
ACIMA_DO_PISO_DB = 10.0
ABAIXO_DO_PICO_VOZ_DB = 25.0
ABAIXO_DO_PICO_MUDO_DB = 40.0


def comparar(bruto, limpo, min_buraco_s=MIN_BURACO_S):
    """({buracos, dur_bruto, dur_limpo, ...}) da comparação. Não decide: `verificar` decide."""
    eb, dur_b = energia.curva(bruto, jan=JANELA_S)
    el, dur_l = energia.curva(limpo, jan=JANELA_S)
    if not len(eb):
        raise InsumoInvalido("o bruto %s é curto demais para medir" % Path(str(bruto)).name)
    pico_b = energia.percentil(eb, 0.98)
    if pico_b <= segmentos.SEM_SINAL_DB:
        raise InsumoInvalido("o bruto %s não tem sinal de áudio" % Path(str(bruto)).name)
    pico_l = energia.percentil(el, 0.98)
    piso_b = energia.percentil(eb, 0.10)
    lim_voz = max(piso_b + ACIMA_DO_PISO_DB, pico_b - ABAIXO_DO_PICO_VOZ_DB)
    lim_mudo = 0.0 if pico_l <= segmentos.SEM_SINAL_DB else pico_l - ABAIXO_DO_PICO_MUDO_DB
    n = len(eb)
    el = np.concatenate([el, np.full(n - len(el), energia.PISO_DB)]) if len(el) < n else el[:n]
    perdeu = (eb > lim_voz) & (el < lim_mudo)
    return {"buracos": segmentos.corridas(perdeu, JANELA_S, dur_min=min_buraco_s),
            "dur_bruto": dur_b, "dur_limpo": dur_l, "piso_bruto": piso_b,
            "lim_voz": lim_voz, "lim_mudo": lim_mudo}


def verificar(bruto, limpo, tol_dur_s=TOL_DURACAO_S, min_buraco_s=MIN_BURACO_S):
    """(ok, motivo) de um par bruto/limpo."""
    veredito.exigir_arquivo(bruto, "o áudio bruto")
    veredito.exigir_arquivo(limpo, "o áudio limpo")
    c = comparar(bruto, limpo, min_buraco_s)
    nome = Path(str(limpo)).name
    problemas = []
    dif = c["dur_bruto"] - c["dur_limpo"]
    if abs(dif) > tol_dur_s:
        problemas.append("o limpo é %.2fs %s que o bruto (%.2fs contra %.2fs)%s"
                         % (abs(dif), "mais curto" if dif > 0 else "mais longo", c["dur_limpo"], c["dur_bruto"],
                            ": a cauda foi cortada" if dif > 0 else ""))
    if c["buracos"]:
        problemas.append("buraco(s) de fala perdida: %s" % ", ".join("%.1f-%.1fs" % b for b in c["buracos"][:5]))
    if problemas:
        return False, "%s: %s" % (nome, "; ".join(problemas))
    return True, ("%s: nenhuma fala perdida (piso do bruto %.1f dB, voz acima de %.1f dB, mudo abaixo de %.1f dB)"
                  % (nome, c["piso_bruto"], c["lim_voz"], c["lim_mudo"]))


def takes_para_conferir(proj):
    """Os takes do plano; sem anúncios ainda (fase 1), todos os que já têm áudio limpo."""
    takes = sorted({t for _, _, t, _, _ in proj.todos_os_trechos()})
    if takes:
        return takes
    pasta = proj.pasta("limpo")
    return sorted({p.stem for p in pasta.iterdir() if p.is_file()}) if pasta.is_dir() else []


def verificar_projeto(proj, leitor=None, pecas=None):
    takes = takes_para_conferir(proj)
    if not takes:
        raise InsumoInvalido("nenhum take para conferir: faltam o plano ou os áudios em %s" % proj.pasta("limpo"))
    return veredito.juntar(verificar(proj.wav(t), proj.limpo(t)) for t in takes)


def _parser():
    ap = argparse.ArgumentParser(prog=NOME, description="O isolador comeu fala? Bruto x limpo por envelope.")
    ap.add_argument("arquivos", nargs="*", help="BRUTO LIMPO (sem isso, usa o projeto)")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    return ap


def _verificar(args):
    if args.arquivos:
        if len(args.arquivos) != 2:
            raise InsumoInvalido("passe exatamente BRUTO e LIMPO")
        return verificar(args.arquivos[0], args.arquivos[1])
    return verificar_projeto(gp.carregar(args.projeto))


def main(argv=None):
    return veredito.cli(NOME, _parser(), _verificar, argv)


if __name__ == "__main__":
    sys.exit(main())
