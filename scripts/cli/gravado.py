"""`vam gravado`: o pipeline de take gravado (evento, lapela, retomada) pela CLI do produto.

    vam gravado <slug> <ação> [alvos...] [opções]

Cada ação é uma etapa do pipeline, na ordem em que se roda. Põe-se os alvos (peças, takes) logo depois
da ação e as opções por último.

    criar --brutos PASTA [--trilha ARQ | --sem-trilha MOTIVO]
                      cria o projeto no modo gravado e o plano de partida (plano_gravado.json); idempotente
    extrair [TAKE...] tira o áudio de cada bruto (wav 48 kHz e mp3 leve): ler o take INTEIRO antes do plano
    isolar [TAKE...]  higieniza pelo Voice Isolator (ELEVENLABS_API_KEY; conta paga por uso)
    limpo --de PASTA [TAKE...]
                      importa o áudio JÁ higienizado de uma pasta (copia, confere o sha256, nunca toca na origem)
    plano [--md]      confere o plano e mostra a aceleração do projeto (padrão 1,2 em take real); --md regera o
                      PLANO-CORTES.md
    montar AD [--desconto] [--so-plano]
                      monta o anúncio do plano: corta o ar morto dentro de cada trecho, grade de cor, 1,2x e loudness
    caixinha PECA --texto "..." [--colorway ambar|branco|preto] [--topo 210] [--teto-y N]
                      a caixa de lettering nativa (canto reto, PT Serif do repo) no topo, sobre a peça montada
    legendar [PECA...] [--omitir PALAVRA...] [--backend NOME]
                      legenda ASS da transcrição corrigida pelo glossário, e o relatório fala x roteiro
    aprovar-legenda PECA --ok "<o ok do diretor>" [--divergencia-aceita]
                      o ok do diretor à legenda, amarrado por sha256 ao .ass (só este comando assina)
    queimar [PECA...] [--fontsdir PASTA]
                      queima a legenda APROVADA (sem aprovação vigente, nenhum ffmpeg roda)
    gates [PECA...]   roda os 11 gates do gravado e a conferência da legenda aprovada, sem copiar nada
    entregar [--abrir]
                      copia as peças legendadas para entrega/, só se TODOS passarem (confere a cópia por sha256)

    exit 0  fez
    exit 1  defeito medido na peça: algum gate reprovou (gates, entregar)
    exit 2  pedido ou insumo inválido: slug, projeto que não existe ou é de outro modo, arquivo ausente, chave da
            API, aprovação que falta, gate que não conseguiu medir

O estado do aluno (`_local`) vem do `caminhos.ESTADO` (a opção escondida `--estado` troca, para os testes).
Quem é medido não assina: a aprovação da legenda é escrita por `legendar.aprovar`, só na ação `aprovar-legenda`,
e só com o texto do ok que o diretor escreveu no chat.
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

if __package__ in (None, ""):      # rodado direto: scripts/cli/gravado.py (tira scripts/cli do caminho)
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from audio import transcrever  # noqa: E402
from gravado import (compor_caixinha, entregar, extrair_wav, gerar_plano_md, isolar,  # noqa: E402
                     legendar, montar, queimar_legenda)
from gravado import projeto as gp  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402
from projeto import modelo, novo, pastas  # noqa: E402

NOME = "gravado"
ACOES = ("criar", "extrair", "isolar", "limpo", "plano", "montar", "caixinha", "legendar", "aprovar-legenda",
         "queimar", "gates", "entregar")
SAIDA_OK, SAIDA_DEFEITO, SAIDA_USO = 0, 1, 2
MOTIVO_SEM_TRILHA = "gravado: a fala real do apresentador segue sem trilha"


class PedidoInvalido(InsumoInvalido):
    """O pedido não dá para atender (saída 2); a mensagem diz o que corrigir."""


def registrar(subparsers):
    """Cadastra o subcomando no `vam.py`."""
    p = subparsers.add_parser(
        NOME, help="o pipeline de take gravado: áudio, plano, montagem, caixa, legenda aprovada, gates e entrega",
        description=__doc__.split("\n\n    exit 0")[0].strip(),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("slug", help="o projeto (pasta em _local/projetos/)")
    p.add_argument("acao", choices=ACOES, help="a etapa do pipeline")
    p.add_argument("alvos", nargs="*", help="peças (A1_normal), takes (IMG_0001) ou o anúncio (A1), conforme a ação")
    p.add_argument("--brutos", help="criar: a pasta com os takes brutos (.MOV)")
    p.add_argument("--trilha", help="criar: arquivo de trilha em _local/trilhas/")
    p.add_argument("--sem-trilha", dest="sem_trilha", metavar="MOTIVO",
                   help="criar: motivo de rodar sem trilha (padrão: a fala real segue sem trilha)")
    p.add_argument("--de", help="limpo: a pasta com o áudio já higienizado")
    p.add_argument("--md", action="store_true", help="plano: regera o PLANO-CORTES.md")
    p.add_argument("--desconto", action="store_true", help="montar: troca a cauda pelo CTA com desconto")
    p.add_argument("--so-plano", action="store_true", dest="so_plano", help="montar: lista o que entra, não renderiza")
    p.add_argument("--texto", help="caixinha: o texto da caixa (o que o apresentador lê)")
    p.add_argument("--colorway", default="ambar", help="caixinha: ambar, branco ou preto (padrão ambar)")
    p.add_argument("--topo", type=int, default=compor_caixinha.POS_PADRAO[1],
                   help="caixinha: y onde a caixa começa (padrão %(default)s, abaixo da UI do Reels)")
    p.add_argument("--teto-y", type=int, default=None, dest="teto_y",
                   help="caixinha: até onde ela pode descer (padrão: medido na peça)")
    p.add_argument("--omitir", nargs="*", default=[], help="legendar: palavras que saem da legenda (o áudio fica)")
    p.add_argument("--backend", choices=transcrever.ORDEM, help="legendar e gates: o transcritor (padrão: o da máquina)")
    p.add_argument("--ok", help="aprovar-legenda: o texto do ok do diretor, como ele escreveu no chat")
    p.add_argument("--divergencia-aceita", action="store_true", dest="divergencia_aceita",
                   help="aprovar-legenda: aprova mesmo com o relatório fala x roteiro REPROVA")
    p.add_argument("--fontsdir", help="queimar: pasta com a Inter (padrão: fonts/ do repo)")
    p.add_argument("--abrir", action="store_true", help="entregar: abre a pasta entrega/ depois de copiar")
    p.add_argument("--estado", default=None, help=argparse.SUPPRESS)
    p.set_defaults(func=executar)
    return p


def _erro(texto):
    print("vam gravado: %s" % texto, file=sys.stderr)


# --- o projeto -----------------------------------------------------------------------------------

def _projeto_existente(args, pj, estado):
    """O Projeto de gravado já validado. PedidoInvalido se o projeto não existe ou é de outro modo."""
    if not pj.projeto_json.is_file():
        raise PedidoInvalido("o projeto %r não existe em %s: crie antes com "
                             "`vam gravado %s criar --brutos PASTA_DOS_BRUTOS`" % (args.slug, pj.raiz, args.slug))
    try:
        projeto = modelo.carregar(pj.projeto_json)
    except modelo.ContratoInvalido as e:
        raise PedidoInvalido(str(e))
    if projeto["modo"] != "gravado":
        raise PedidoInvalido("o projeto %r é do modo %r, não gravado: o take gravado é `vam gravado`; "
                             "o modo %s tem o comando dele" % (args.slug, projeto["modo"], projeto["modo"]))
    return gp.carregar(pj.raiz, estado)


def _peca(nome):
    """`A1` vale `A1_normal`; `A1_desconto` fica como está."""
    return nome if nome.endswith(("_normal", "_desconto")) else nome + "_normal"


def _pecas_pedidas(args, proj, existe):
    """Os alvos como peças, ou todas as do plano em que `existe(nome)` é verdade."""
    if args.alvos:
        return [_peca(a) for a in args.alvos]
    return [n for n in proj.nomes_das_pecas() if existe(n)]


def _um_alvo(args, o_que):
    if len(args.alvos) != 1:
        raise PedidoInvalido("a ação %s pede UMA %s: `vam gravado %s %s <%s>`"
                             % (args.acao, o_que, args.slug, args.acao, o_que))
    return args.alvos[0]


# --- criar ---------------------------------------------------------------------------------------

def _criar(args, pj, estado):
    if not args.brutos:
        raise PedidoInvalido("criar precisa de --brutos PASTA: a pasta com os takes brutos da câmera (.MOV)")
    brutos = Path(args.brutos).expanduser()
    if not brutos.is_dir():
        raise PedidoInvalido("a pasta de brutos não existe: %s" % brutos)
    if args.trilha and args.sem_trilha:
        raise PedidoInvalido("--trilha e --sem-trilha se excluem: ou há trilha, ou há o motivo de não ter")
    sem = None if args.trilha else (args.sem_trilha or MOTIVO_SEM_TRILHA)
    try:
        resultado = novo.criar(args.slug, "gravado", trilha=args.trilha, sem_trilha=sem, estado=estado)
    except (novo.ProjetoJaExiste, modelo.ContratoInvalido) as e:
        raise PedidoInvalido(str(e))
    proj = gp.criar(pj.raiz, brutos, estado)
    print("projeto %s em %s (%s)" % (args.slug, pj.raiz, "criado" if resultado.criado else "já existia"))
    print("aceleração: %sx (a do projeto.json; padrão 1,2 em take real)" % proj.accel)
    print("plano: %s" % (proj.base / gp.ARQUIVO_PLANO))
    for aviso in resultado.avisos:
        print("AVISO: %s" % aviso)
    print("próximo: `vam gravado %s extrair`, leia os takes INTEIROS e preencha os anúncios no plano" % args.slug)
    return SAIDA_OK


# --- áudio ---------------------------------------------------------------------------------------

def _extrair(args, proj):
    feitos, total = extrair_wav.extrair(proj, args.alvos or None)
    print("%d/%d brutos com áudio extraído em %s e %s" % (feitos, total, proj.pasta("wav"), proj.pasta("audio")))
    return SAIDA_OK


def _isolar(args, proj):
    chave = isolar.chave_do_ambiente()
    falhou = []
    for take, estado in isolar.isolar_lote(proj, chave, args.alvos or None).items():
        print("  %s: %s" % (take, estado))
        if not (estado.startswith("ok") or estado == "cache"):
            falhou.append(take)
    if falhou:
        raise PedidoInvalido("não isolou: %s" % ", ".join(falhou))
    return SAIDA_OK


def _sha(caminho):
    return legendar.sha256_arquivo(caminho)


def _limpo(args, proj):
    if not args.de:
        raise PedidoInvalido("limpo precisa de --de PASTA: a pasta com o áudio já higienizado (um arquivo por take, "
                             "com o nome do take)")
    origem = Path(args.de).expanduser()
    if not origem.is_dir():
        raise PedidoInvalido("a pasta do áudio higienizado não existe: %s" % origem)
    takes = list(args.alvos) or sorted({x[2] for x in proj.todos_os_trechos()})
    if not takes:
        takes = [b.stem for b in proj.takes_brutos()]
    if not takes:
        raise PedidoInvalido("não sei quais takes importar: o plano não tem trechos e a pasta de brutos está vazia")
    achados, faltam, conflitos = {}, [], []
    arquivos = [f for f in origem.iterdir() if f.is_file() and f.suffix.lower() in gp.EXTENSOES_DE_LIMPO]
    for take in takes:
        candidatos = [f for f in arquivos if f.stem == take]
        if not candidatos:
            faltam.append(take)
            continue
        fonte = candidatos[0]
        destino = proj.pasta("limpo") / (take + fonte.suffix.lower())
        outros = [x for x in proj.pasta("limpo").glob(take + ".*") if x != destino] if proj.pasta("limpo").is_dir() else []
        if outros:
            conflitos.append("%s: já existe %s com outra extensão; apague um dos dois" % (take, outros[0].name))
        elif destino.is_file() and _sha(destino) != _sha(fonte):
            conflitos.append("%s: o limpo do projeto (%s) é diferente do de %s e não é sobrescrito: apague o do projeto "
                             "se é esse que vale" % (take, destino.name, origem))
        else:
            achados[take] = (fonte, destino)
    if faltam:
        raise PedidoInvalido("não achei o áudio higienizado de %s em %s (nada foi copiado)" % (", ".join(faltam), origem))
    if conflitos:
        raise PedidoInvalido("conflito com o que já está no projeto (nada foi copiado):\n  " + "\n  ".join(conflitos))
    proj.garantir("limpo")
    for take, (fonte, destino) in achados.items():
        if destino.is_file():
            print("  %s: já estava no projeto" % take)
            continue
        parcial = destino.with_name(destino.name + ".part")
        shutil.copy2(str(fonte), str(parcial))
        if _sha(parcial) != _sha(fonte):
            parcial.unlink()
            raise PedidoInvalido("a cópia de %s não confere com a origem (sha256): tente de novo" % fonte.name)
        os.replace(str(parcial), str(destino))
        print("  %s: %s -> limpo/%s (sha256 conferido)" % (take, fonte.name, destino.name))
    print("%d take(s) com áudio higienizado em %s" % (len(achados), proj.pasta("limpo")))
    return SAIDA_OK


# --- plano e montagem ----------------------------------------------------------------------------

def _plano(args, proj):
    print("projeto %s | plano %s" % (proj.base, proj.base / gp.ARQUIVO_PLANO))
    print("aceleração: %sx | grade: %s" % (proj.accel, montar.preset_de_grade(proj)))
    print("brutos: %s %s" % ("ok" if proj.brutos.is_dir() else "AUSENTE", proj.brutos))
    print("anúncios (%d): %s" % (len(proj.ads), ", ".join(proj.ads) or "(vazio: preencha depois de ler os takes)"))
    if args.md:
        proj.plano_md.write_text(gerar_plano_md.gerar(proj), encoding="utf-8")
        print("%s regerado" % proj.plano_md.name)
    return SAIDA_OK


def _montar(args, proj):
    cod = _um_alvo(args, "anúncio")
    if cod not in proj.ads:
        raise PedidoInvalido("o anúncio %s não está no plano (tem: %s)" % (cod, ", ".join(proj.ads) or "nenhum"))
    segs = montar.segmentos_do_ad(proj, cod, args.desconto)
    total = sum(e - s for _, s, e in segs)
    print("%s %s: %d segmentos, %.2fs -> %.2fs acelerado (%sx)"
          % (cod, "(desconto)" if args.desconto else "(normal)", len(segs), total, total / proj.accel, proj.accel))
    for take, s, e in segs:
        print("   %s  %7.2f > %7.2f   (%5.2fs)" % (take, s, e, e - s))
    if args.so_plano:
        return SAIDA_OK
    try:
        destino = montar.render(proj, cod, segs, args.desconto)
    except montar.ErroDeRender as e:
        raise PedidoInvalido(str(e))
    print("\n-> %s  (%.2fs)" % (destino.name, montar.duracao(destino)))
    return SAIDA_OK


def _caixinha(args, proj):
    nome = _peca(_um_alvo(args, "peça"))
    if not args.texto:
        raise PedidoInvalido("caixinha precisa de --texto \"...\": o que o apresentador lê, palavra por palavra")
    destino, aviso = compor_caixinha.compor_texto(proj, nome, args.texto, args.colorway, args.topo, args.teto_y)
    print("%s pronto (caixa %s, topo y=%d)" % (destino.name, args.colorway, args.topo))
    if aviso:
        print("  " + aviso)
    return SAIDA_OK


# --- legenda -------------------------------------------------------------------------------------

def _legendar(args, proj):
    nomes = _pecas_pedidas(args, proj, lambda n: Path(proj.fonte_da_peca(n)).is_file())
    if not nomes:
        raise PedidoInvalido("nenhuma peça montada em %s: rode `vam gravado %s montar AD` antes"
                             % (proj.pasta("montados"), args.slug))
    legendar.legendar_pecas(proj, nomes, proj.leitor(backend=args.backend), omitir=args.omitir, relatorio=print)
    print("próximo: leia legendas/<peça>.ass e o relatório, e só então `vam gravado %s aprovar-legenda PECA --ok ...`"
          % args.slug)
    return SAIDA_OK


def _aprovar_legenda(args, proj):
    nome = _peca(_um_alvo(args, "peça"))
    ap = legendar.aprovar(proj, nome, args.ok, divergencia_aceita=args.divergencia_aceita)
    print("legenda de %s aprovada (sha256 do .ass %s...)" % (nome, ap["ass"]["sha256"][:12]))
    print("  relatório fala x roteiro: %s%s" % (ap["relatorio"]["estado"],
                                               " (divergência aceita por escrito)" if ap["divergencia_aceita"] else ""))
    return SAIDA_OK


def _queimar(args, proj):
    nomes = _pecas_pedidas(args, proj, lambda n: proj.legenda_ass(n).is_file())
    if not nomes:
        raise PedidoInvalido("nenhuma legenda em %s: rode `vam gravado %s legendar` antes" % (proj.pasta("legendas"), args.slug))
    if args.fontsdir:
        fontsdir = Path(args.fontsdir)
    else:
        import caminhos
        fontsdir = Path(caminhos.FONTS)
    for nome in nomes:
        origem = proj.fonte_da_peca(nome)
        queimar_legenda.queimar_peca(proj, nome, fontsdir)
        print("  %s: %s/%s + legenda aprovada -> legendado/%s.mp4" % (nome, origem.parent.name, origem.name, nome))
    return SAIDA_OK


# --- gates e entrega -----------------------------------------------------------------------------

def _gates(args, proj):
    leitor = proj.leitor(backend=args.backend)
    resultados = entregar.rodar_gates(entregar.gates_da_entrega(proj, leitor))
    codigo_de = {"ok": 0, "defeito": 1, "insumo": 2}
    for nome, estado, motivo in resultados:
        print("%-18s saída %d  %-8s %s" % (nome, codigo_de[estado], estado, motivo.replace("\n", "\n" + " " * 40)))
    estados = {e for _, e, _ in resultados}
    return SAIDA_DEFEITO if "defeito" in estados else (SAIDA_USO if "insumo" in estados else SAIDA_OK)


def _entregar(args, proj):
    r = entregar.entregar(proj, abrir=args.abrir, leitor=proj.leitor(backend=args.backend))
    print(r.resumo())
    return r.codigo


_ACOES = {"extrair": _extrair, "isolar": _isolar, "limpo": _limpo, "plano": _plano, "montar": _montar,
          "caixinha": _caixinha, "legendar": _legendar, "aprovar-legenda": _aprovar_legenda, "queimar": _queimar,
          "gates": _gates, "entregar": _entregar}


def executar(args):
    """Roda o subcomando. Devolve o código de saída (0, 1 ou 2)."""
    try:
        estado = Path(args.estado) if args.estado else pastas.estado_padrao()
        try:
            pj = pastas.projeto(args.slug, estado)
        except ValueError as e:
            raise PedidoInvalido("slug inválido: %s" % e)
        if args.acao == "criar":
            return _criar(args, pj, estado)
        proj = _projeto_existente(args, pj, estado)
        return _ACOES[args.acao](args, proj)
    except InsumoInvalido as e:
        _erro(str(e))
        return SAIDA_USO
    except montar.ErroDeRender as e:
        _erro(str(e))
        return SAIDA_USO


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="gravado")
    registrar(ap.add_subparsers(dest="comando"))
    sys.exit(executar(ap.parse_args(["gravado"] + sys.argv[1:])))
