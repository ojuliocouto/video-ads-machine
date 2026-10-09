"""`vam oneshot`: do take bruto de câmera ao anúncio 9:16.

    vam oneshot <slug> [--bruto take.mov] [--caixa "texto"] [--colorway ambar|branco|preto] [--so-plano]

O projeto tem que existir no modo oneshot (`vam novo <slug> --modo oneshot`). O take mora em
`voz/bruto.<ext>` dentro do projeto: `--bruto` copia o arquivo para lá (a origem nunca é tocada, e um take
diferente do que já está lá não sobrescreve). O comando transcreve com tempo de palavra real, planeja o corte
do ar morto, o enquadre no rosto medido e a luz medida, grava `render/oneshot.json` e MOSTRA o plano; com
`--so-plano` para aí. Sem ele renderiza numa passada só (`entrega/final_9x16.mp4`, loudness normalizado)
e roda os gates de depois: a fala do bruto está inteira, a maior pausa e o técnico.

A aceleração é a do `projeto.json` (padrão 1,2 em take real). `--caixa` põe a caixa de lettering nativa
(PT Serif do repo, três colorways, o texto exatamente o que o apresentador lê).

    exit 0  entregou e todos os gates passaram (ou `--so-plano` mostrou o plano)
    exit 1  algum gate reprovou o anúncio pronto
    exit 2  pedido ou insumo inválido: slug, projeto que não existe ou é de outro modo, take ausente, colorway,
            transcritor sem borda de palavra, ffmpeg que falhou
"""
import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path

if __package__ in (None, ""):      # rodado direto: scripts/cli/oneshot.py (tira scripts/cli do caminho)
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from audio import transcrever  # noqa: E402
from caixa_lettering import COLORWAYS  # noqa: E402
from gravado import compor_caixinha  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402
from oneshot import montar  # noqa: E402
from projeto import pastas  # noqa: E402

NOME = "oneshot"
SAIDA_OK, SAIDA_DEFEITO, SAIDA_USO = 0, 1, 2
CENTRO_Y_PADRAO = 0.786         # a caixa do one-shot aprovado: abaixo do rosto e acima da UI do Reels


def registrar(subparsers):
    """Cadastra o subcomando no `vam.py`."""
    p = subparsers.add_parser(
        NOME, help="do take bruto de câmera ao anúncio 9:16 (corte, enquadre no rosto, luz, caixa, gates)",
        description="Edita um take bruto de câmera num anúncio 9:16. Mostra o plano medido (--so-plano para aí), "
                    "renderiza numa passada só e confere o resultado com gates.")
    p.add_argument("slug", help="o projeto (pasta em _local/projetos/), no modo oneshot")
    p.add_argument("--bruto", help="o take de câmera: é copiado para voz/bruto.<ext> do projeto")
    p.add_argument("--caixa", metavar="TEXTO", help="texto da caixa de lettering nativa (o que o apresentador lê)")
    p.add_argument("--colorway", default="ambar", help="ambar, branco ou preto (padrão ambar)")
    p.add_argument("--centro-y", type=float, default=CENTRO_Y_PADRAO,
                   help="centro vertical da caixa, em fração da altura (padrão %(default)s)")
    p.add_argument("--so-plano", action="store_true", help="grava e mostra o plano e para, sem renderizar")
    p.add_argument("--backend", choices=transcrever.ORDEM, help="transcritor (padrão: o da máquina)")
    p.add_argument("--estado", default=None, help=argparse.SUPPRESS)
    p.set_defaults(func=executar)
    return p


def _erro(texto):
    print("vam oneshot: %s" % texto, file=sys.stderr)


def _sha(caminho):
    h = hashlib.sha256()
    with open(str(caminho), "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def _copiar_bruto(pj, origem):
    """Copia o take para voz/bruto.<ext>. Idempotente; um take DIFERENTE do que já está lá é recusado."""
    origem = Path(origem).expanduser()
    if not origem.is_file():
        raise InsumoInvalido("o take não existe: %s" % origem)
    pj.voz_dir.mkdir(parents=True, exist_ok=True)
    existente = pj.voz_bruto()
    if existente is not None:
        if _sha(existente) == _sha(origem):
            return existente
        raise InsumoInvalido("o projeto já tem um take (%s) diferente de %s: apague o do projeto se é esse "
                             "mesmo que vale, ou use outro projeto" % (existente.name, origem.name))
    destino = pj.voz_dir / ("bruto" + origem.suffix.lower())
    parcial = destino.with_name(destino.name + ".part")
    shutil.copy2(str(origem), str(parcial))
    if _sha(parcial) != _sha(origem):
        parcial.unlink()
        raise InsumoInvalido("a cópia do take não confere com a origem (sha256): tente de novo")
    os.replace(str(parcial), str(destino))
    return destino


def _mostrar_plano(plano):
    j = plano["janela"]
    print("take: %.2fs -> %d segmentos, %.2fs de fala -> %.2fs finais a %sx"
          % (plano["dur_bruto"], len(plano["segmentos"]), plano["dur_cortada"], plano["dur_final"],
             plano["aceleracao"]))
    for a, b in plano["segmentos"]:
        print("   %7.2f > %7.2f   (%5.2fs)" % (a, b, b - a))
    if j["precisa_crop"]:
        print("enquadre: janela %dx%d em x=%d y=%d (%s)" % (j["w"], j["h"], j["x"], j["y"],
              "centrada no rosto medido" if j["centrado_no_rosto"] else "SEM rosto medido: centro do quadro"))
    else:
        print("enquadre: o take já é 9:16, sem recorte")
    l = plano["luz"]
    print("luz: luminância %.0f (alvo %.0f) -> brightness %s, contraste %s" % (l["medida"], l["alvo"],
                                                                              l["brightness"], l["contrast"]))
    print("grade: %s%s" % (plano["grade"], "  (HDR %s convertido para SDR)" % plano["transferencia"]
                           if plano.get("transferencia") in ("arib-std-b67", "smpte2084") else ""))
    for aviso in plano["avisos"]:
        print("AVISO: %s" % aviso)


def executar(args):
    """Roda o subcomando. Devolve o código de saída (0, 1 ou 2)."""
    try:
        estado = Path(args.estado) if args.estado else pastas.estado_padrao()
        try:
            pj = pastas.projeto(args.slug, estado)
        except ValueError as e:
            raise InsumoInvalido("slug inválido: %s" % e)
        if not pj.raiz.is_dir():
            raise InsumoInvalido("o projeto %r não existe em %s: crie antes com `vam novo %s --modo oneshot`"
                                 % (args.slug, pj.raiz.parent, args.slug))
        montar.carregar_projeto(pj)
        if args.colorway not in COLORWAYS:
            raise InsumoInvalido("colorway %r não existe: use um dos três (%s), nunca um quarto"
                                 % (args.colorway, ", ".join(COLORWAYS)))
        if args.bruto:
            _copiar_bruto(pj, args.bruto)
        try:
            take = pj.voz_bruto()
        except ValueError as e:
            raise InsumoInvalido(str(e))
        if take is None:
            raise InsumoInvalido("o projeto não tem o take: passe `--bruto ARQUIVO` (ele vira voz/bruto.<ext> do "
                                 "projeto)")
        leitor = montar.leitor_do_projeto(pj, backend=args.backend, estado=estado)
        plano = montar.planejar(pj, take, leitor)
        arq = montar.salvar_plano(pj, plano)
        _mostrar_plano(plano)
        print("plano gravado em %s" % arq)
        if args.so_plano:
            return SAIDA_OK
        caixa = None
        if args.caixa:
            png = pj.render_dir / "caixa.png"
            compor_caixinha.gerar_png(args.caixa, args.colorway, centro_y=args.centro_y).save(str(png))
            caixa = png
        final = montar.renderizar(pj, plano, caixa)
        resultados = montar.conferir(pj, plano, leitor, final)
    except InsumoInvalido as e:
        _erro(str(e))
        return SAIDA_USO
    for nome, ok, motivo in resultados:
        print("%s %s: %s" % ("APROVADO" if ok else "REPROVADO", nome, motivo))
    if not all(ok for _, ok, _ in resultados):
        print("final com defeito medido: %s" % final)
        return SAIDA_DEFEITO
    print("anúncio pronto: %s" % final)
    return SAIDA_OK


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="oneshot")
    registrar(ap.add_subparsers(dest="comando"))
    sys.exit(executar(ap.parse_args(["oneshot"] + sys.argv[1:])))
