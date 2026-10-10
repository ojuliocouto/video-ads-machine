"""`vam avatar <slug>`: o avatar do HeyGen gerado DA VOZ LIMPA do projeto, e conferido.

    vam avatar <slug> [--teto-usd 5]                gera no HeyGen (Avatar V, API v3) com o look do projeto
    vam avatar <slug> --existente avatar.mp4        usa um avatar JÁ gerado desta voz limpa (custo zero)
    vam avatar <slug> --retomar                     a rede caiu no meio? retoma o job JÁ PAGO (sem pagar de novo)
    vam avatar <slug> --avatar-id ID --plano medio  cadastra o look do projeto em _local/looks.json (uma vez)
    vam avatar <slug> ... --aprovar-look            depois de OLHAR avatar/boca.png: aprova o look, amarrado à conferência

A geração lê o saldo da carteira antes e depois (GET /v3/users/me) e grava o custo em avatar/custo.json; passar do
teto bloqueia a prova. O job pago é gravado em avatar/job.json logo depois do submit: se a rede cair, `vam avatar`
(com ou sem --retomar) retoma o poll em vez de submeter outro. A conferência (avatar/conferencia.json e avatar/boca.png) reprova tamanho que não é 1080x1920,
fração útil do quadro abaixo de 0,93 e duração diferente da voz limpa em mais de 1,0 s. Saída 1 se a conferência
reprova. A aprovação do look é do aluno: o `vam montar` recusa look sem aprovação vigente (gate_look).
"""
import argparse
import sys

from cli import _comum as C

NOME = "avatar"
TETO_USD = 5.0
PLANOS = ("fechado", "medio", "aberto")


def registrar(subparsers):
    p = subparsers.add_parser(NOME, help="gera (HeyGen) ou importa o avatar e confere tamanho, boca e duração",
                              description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("slug")
    p.add_argument("--existente", help="um avatar já gerado desta voz limpa (mp4 1080x1920)")
    p.add_argument("--avatar-id", dest="avatar_id", help="cadastra o look do projeto com este id do HeyGen")
    p.add_argument("--plano", choices=PLANOS, help="enquadramento do look que está sendo cadastrado")
    p.add_argument("--aprovar-look", dest="aprovar_look", action="store_true",
                   help="aprova o look do projeto, amarrado ao sha256 desta conferência (depois de olhar a boca)")
    p.add_argument("--teto-usd", dest="teto_usd", type=float, default=TETO_USD,
                   help="gasto máximo do job no HeyGen (padrão %(default)s)")
    p.add_argument("--retomar", action="store_true",
                   help="retoma o job do HeyGen que já foi pago (avatar/job.json) e não voltou; não paga de novo")
    p.add_argument("--sobrescrever", action="store_true", help="troca o avatar que já está no projeto")
    C.opcao_estado(p)
    p.set_defaults(func=executar)
    return p


def _look(pj, projeto, args):
    from projeto import looks
    nome = projeto["look"]
    try:
        atual = looks.obter(nome, pj.estado)
    except looks.LookInvalido as e:
        raise C.PedidoInvalido(str(e))
    if atual is None:
        if not (args.avatar_id and args.plano):
            raise C.PedidoInvalido("o look %r não está em _local/looks.json: cadastre com vam avatar %s --avatar-id "
                                   "<id do look no HeyGen> --plano medio" % (nome, pj.slug))
        try:
            atual = looks.adicionar(nome, args.avatar_id, args.plano, estado=pj.estado)
        except looks.LookInvalido as e:
            raise C.PedidoInvalido(str(e))
        print("look %s cadastrado (id %s, plano %s, ainda não aprovado)" % (nome, args.avatar_id, args.plano))
    elif args.avatar_id and args.avatar_id != atual["avatar_id"]:
        raise C.PedidoInvalido("o look %r já está cadastrado com outro id (%s): edite _local/looks.json se for trocar"
                               % (nome, atual["avatar_id"]))
    return nome, atual


def _cliente():
    from avatar import heygen_cliente
    from vam import RAIZ
    try:
        return heygen_cliente.ClienteHeyGen.do_ambiente(raiz=RAIZ)
    except heygen_cliente.HeyGenSemChave:
        raise C.PedidoInvalido("sem HEYGEN_API_KEY (variável de ambiente ou .env da raiz do repo): ponha a chave e rode "
                               "de novo, ou use um avatar já gerado com --existente")


def _erro_do_heygen(pj, e):
    """Traduz o erro do HeyGen em PedidoInvalido. Rede e tempo esgotado deixam o job PENDENTE (já foi pago) e dizem
    como retomar; `failed` do lado deles libera um submit novo."""
    from avatar import heygen_cliente as H, job
    from projeto import status
    if isinstance(e, H.HeyGenFalhou):
        job.marcar(pj, job.FALHOU)
        return C.PedidoInvalido("o HeyGen não conseguiu gerar o avatar (%s): rode vam avatar %s de novo para gerar outro"
                                % (e, pj.slug))
    pendente = job.ler(pj)
    if isinstance(e, (H.HeyGenRede, H.HeyGenTimeout)) and pendente and pendente.get("estado") == job.PENDENTE:
        motivo = ("o job %s já foi pago e continua no HeyGen; a espera foi interrompida (%s). Rode vam avatar %s "
                  "--retomar: NÃO paga de novo" % (pendente["video_id"], e, pj.slug))
        status.registrar(pj, NOME, "falhou", motivo=motivo[:600])
        return C.PedidoInvalido(motivo)
    return C.PedidoInvalido("o HeyGen recusou: %s" % e)


def _gerar(pj, projeto, look, teto, voz_sha):
    from avatar import custo, heygen_cliente, job
    from projeto import status
    cliente = _cliente()
    pj.avatar_dir.mkdir(parents=True, exist_ok=True)

    def guardar_job(video_id, engine):
        job.gravar(pj, video_id, engine, look["avatar_id"], voz_sha)
        print("job pago e guardado em %s (se a rede cair, vam avatar %s --retomar)" % (pj.relativo(job.caminho(pj)),
                                                                                      pj.slug))

    try:
        r = custo.medir_job(cliente, lambda: cliente.gerar_avatar(pj.voz_limpo, look["avatar_id"], pj.avatar_mp4,
                                                                  projeto=projeto, ao_submeter=guardar_job),
                            pj, teto_usd=teto)
    except heygen_cliente.HeyGenErro as e:
        raise _erro_do_heygen(pj, e)
    job.marcar(pj, job.CONCLUIDO)
    status.escrever_json_atomico(pj.avatar_dir / "custo.json", r)
    print("custo do job: %s %s (saldo %s -> %s)" % (r.get("gasto"), r.get("moeda"), r.get("saldo_antes"),
                                                   r.get("saldo_depois")))
    if r.get("excedeu_teto"):
        raise C.PedidoInvalido("o gasto passou do teto de US$ %.2f: a prova para aqui (custo em avatar/custo.json)" % teto)


def _retomar(pj, pendente):
    """Segue o poll do job que já foi pago (avatar/job.json) e baixa o mp4. Não mede custo: foi cobrado no submit."""
    from avatar import heygen_cliente, job
    cliente = _cliente()
    print("retomando o job %s (pago em %s): nada é cobrado de novo" % (pendente["video_id"], pendente.get("criado_em")))
    try:
        cliente.status_e_baixar(pendente["video_id"], pj.avatar_mp4)
    except heygen_cliente.HeyGenErro as e:
        raise _erro_do_heygen(pj, e)
    job.marcar(pj, job.CONCLUIDO)


def _executar(args):
    from avatar import conferir, job
    from projeto import looks, status
    pj, projeto = C.projeto_existente(args)
    C.exigir_modo(pj, projeto, "avatar", NOME)
    nome, look = _look(pj, projeto, args)
    if not pj.voz_limpo.is_file():
        raise C.PedidoInvalido("sem voz/limpo.mp3: o avatar sai da voz limpa; rode vam audio %s antes" % pj.slug)
    voz_sha = C.sha256_arquivo(pj.voz_limpo)
    pendente = job.pendente(pj, voz_sha)
    if args.retomar and args.existente:
        raise C.PedidoInvalido("--retomar e --existente não andam juntos: um segue o job pago, o outro importa um mp4")
    if args.retomar and not pendente:
        raise C.PedidoInvalido("não há job do HeyGen pendente para esta voz em %s: gere com vam avatar %s"
                               % (pj.relativo(job.caminho(pj)), pj.slug))
    if args.existente:
        if C.copiar_conferido(args.existente, pj.avatar_mp4, args.sobrescrever):
            print("avatar importado: %s (nenhum crédito gasto)" % pj.relativo(pj.avatar_mp4))
        if pendente:
            job.marcar(pj, job.SUBSTITUIDO)
    elif pendente:
        _retomar(pj, pendente)
    elif pj.avatar_mp4.is_file() and not args.sobrescrever:
        print("o projeto já tem avatar/avatar.mp4: conferindo (use --sobrescrever para gerar outro)")
    else:
        if job.pendente_de_outra_voz(pj, voz_sha):
            print("aviso: o job pendente em avatar/job.json é de outra voz (a voz limpa mudou): vai um job novo")
        _gerar(pj, projeto, look, args.teto_usd, voz_sha)
    aspecto = {"9x16": "9:16", "1x1": "1:1"}.get(projeto.get("formato", "9x16"), "9:16")
    try:
        c = conferir.conferir(pj, aspecto=aspecto)
    except conferir.InsumoInvalido as e:
        raise C.PedidoInvalido(str(e))
    print("conferência: %s | %dx%d | %.1f s (voz %.1f s, diferença %.2f s) | fração útil %.3f"
          % (c["resultado"], c["avatar"]["largura"], c["avatar"]["altura"], c["avatar"]["duracao_s"],
             c["voz"]["duracao_s"], c["diferenca_duracao_s"], c["fracao_util"]))
    print("  olhe a boca antes de aprovar o look: %s" % pj.avatar_boca)
    if c["resultado"] != "aprovada":
        motivo = "; ".join(c.get("reprovacoes", [])) or "conferência reprovada"
        status.registrar(pj, NOME, "falhou", motivo=motivo[:600])
        C.erro(NOME, "REPROVA: %s" % motivo)
        return C.SAIDA_DEFEITO
    if args.aprovar_look:
        try:
            looks.aprovar(nome, pj.avatar_conferencia, estado=pj.estado)
        except looks.LookInvalido as e:
            raise C.PedidoInvalido(str(e))
        print("look %s aprovado, amarrado ao sha256 de %s" % (nome, pj.relativo(pj.avatar_conferencia)))
    elif not looks.verificar(nome, pj.estado).aprovado:
        print("o look %s ainda não está aprovado: olhe %s e rode vam avatar %s --aprovar-look" % (nome, pj.avatar_boca,
                                                                                               pj.slug))
    status.registrar(pj, NOME, "ok", detalhes={"conferencia": c["resultado"], "look": nome})
    print("próximo: vam plano %s" % pj.slug)
    return C.SAIDA_OK


def executar(args):
    return C.rodar(NOME, _executar, args)
