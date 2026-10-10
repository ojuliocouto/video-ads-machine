"""`vam audio <slug>`: a voz do aluno, higienizada e conferida ANTES de gastar o avatar.

    vam audio <slug> --bruto voz.m4a       copia a gravação para voz/bruto.*, higieniza e confere
    vam audio <slug>                       higieniza e confere de novo o voz/bruto.* que já está no projeto
    vam audio <slug> --limpo voz_limpa.mp3 usa uma voz JÁ higienizada (sem cortar de novo) e confere

O áudio fica GRAVADO dentro do avatar: descobrir um defeito depois do avatar custa um job novo do HeyGen e um build
inteiro. A higienização encurta só os silêncios grandes (pausa de respiração) e preserva o ritmo (os parâmetros do
`auditar_audio`); a conferência é a do gate de entrada, sem a parte do avatar:

  respiro          energia acima de -34 dB dentro de pausa de 0,62 s ou mais (o Avatar V lipsynca a respiração)
  ritmo achatado   voz de mais de 30 s com menos pausas acima de 0,60 s do que 1 a cada 15 s de fala (mínimo 2)
  fala preservada  bruto e limpo transcritos de novo: o corte não pode comer palavra
  fala x roteiro   o que se diz cobre o roteiro.md (até 2% de palavra faltando, nenhuma sequência de 3 sumida)

Tudo vai para voz/auditoria.json. Saída 1 se alguma conferência reprova (refaça a gravação ou a higienização antes
do avatar).
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

from cli import _comum as C

NOME = "audio"
EXTENSOES = (".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".mp4", ".mov")


def registrar(subparsers):
    p = subparsers.add_parser(NOME, help="higieniza a voz e confere respiro, ritmo, fala preservada e fala x roteiro",
                              description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("slug")
    p.add_argument("--bruto", help="a gravação da voz (m4a, mp3, wav...)")
    p.add_argument("--limpo", help="uma voz já higienizada: entra como voz/limpo.mp3 sem cortar de novo")
    p.add_argument("--sobrescrever", action="store_true", help="troca a voz que já está no projeto")
    C.opcao_estado(p)
    p.set_defaults(func=executar)
    return p


def higienizar(bruto, limpo, aceleracao):
    """voz/bruto -> voz/limpo.mp3 pelo higienizar_audio, com os parâmetros que preservam o ritmo (auditar_audio)."""
    import auditar_audio
    from caminhos import CODIGO
    env = dict(os.environ)
    env.update(auditar_audio.PARAMS)
    env["ACCEL_FINAL"] = str(aceleracao)
    env["HIGIENIZAR_SEM_CONFERENCIA"] = "1"      # a fala é conferida abaixo (gate_entrada), com o transcritor da máquina
    r = subprocess.run([sys.executable, str(CODIGO / "higienizar_audio.py"), str(bruto), str(limpo)],
                       capture_output=True, text=True, env=env)
    if r.returncode != 0 or not Path(limpo).is_file():
        raise C.PedidoInvalido("a higienização não produziu voz/limpo.mp3: %s" % ((r.stderr or r.stdout).strip()[-400:]))
    return Path(limpo)


def _para_mp3(origem, destino):
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(origem), "-vn", "-ac", "1", "-ar", "48000",
                        "-c:a", "libmp3lame", "-b:a", "192k", str(destino)], capture_output=True, text=True)
    if r.returncode != 0:
        raise C.PedidoInvalido("não consegui converter %s para mp3: %s" % (Path(origem).name, r.stderr.strip()[-300:]))


def _executar(args):
    from gates import gate_entrada, gate_fala_roteiro
    from projeto import status
    pj, projeto = C.projeto_existente(args)
    C.exigir_modo(pj, projeto, "avatar", NOME)
    if args.bruto:
        origem = Path(args.bruto).expanduser()
        if origem.suffix.lower() not in EXTENSOES:
            raise C.PedidoInvalido("formato de áudio não aceito: %s (aceitos: %s)" % (origem.suffix, ", ".join(EXTENSOES)))
        atual = pj.voz_bruto()
        if atual is not None and atual.suffix.lower() != origem.suffix.lower():
            if not args.sobrescrever:
                raise C.PedidoInvalido("o projeto já tem %s: use --sobrescrever para trocar a voz" % pj.relativo(atual))
            atual.unlink()
        trocou = C.copiar_conferido(origem, pj.voz_dir / ("bruto" + origem.suffix.lower()), args.sobrescrever)
        if trocou and pj.voz_limpo.is_file():
            pj.voz_limpo.unlink()                 # a voz mudou: o limpo antigo não vale mais
    if args.limpo:
        origem = Path(args.limpo).expanduser()
        if not origem.is_file():
            raise C.PedidoInvalido("a voz higienizada não existe: %s" % origem)
        if pj.voz_limpo.is_file() and not args.sobrescrever:
            raise C.PedidoInvalido("o projeto já tem voz/limpo.mp3: use --sobrescrever para trocar")
        pj.voz_dir.mkdir(parents=True, exist_ok=True)
        if origem.suffix.lower() == ".mp3":
            C.copiar_conferido(origem, pj.voz_limpo, sobrescrever=True)
        else:
            _para_mp3(origem, pj.voz_limpo)
    if not pj.voz_limpo.is_file() or (args.bruto and not args.limpo):
        bruto = pj.voz_bruto()
        if bruto is None:
            raise C.PedidoInvalido("sem voz no projeto: vam audio %s --bruto voz.m4a" % pj.slug)
        print("higienizando %s (só as pausas de respiração; o ritmo fica)..." % pj.relativo(bruto), flush=True)
        higienizar(bruto, pj.voz_limpo, projeto["aceleracao"])
    try:
        entrada = gate_entrada.rodar(pj, so_voz=True)
    except gate_entrada.InsumoInvalido as e:
        raise C.PedidoInvalido(str(e))
    conferencias = {"entrada": {"ok": entrada.ok, "motivo": entrada.motivo, "detalhes": entrada.detalhes}}
    if pj.roteiro.is_file():
        try:
            fala = gate_fala_roteiro.rodar(pj)
            conferencias["fala_roteiro"] = {"ok": fala.ok, "motivo": fala.motivo, "detalhes": fala.detalhes}
        except gate_fala_roteiro.InsumoInvalido as e:
            raise C.PedidoInvalido(str(e))
    ok = all(c["ok"] for c in conferencias.values())
    det = entrada.detalhes
    rel = {"versao": 1, "limpo": pj.relativo(pj.voz_limpo), "duracao_limpo_s": det.get("duracao_limpo_s"),
           "conferencias": conferencias, "resultado": "PASS" if ok else "REPROVA"}
    status.escrever_json_atomico(pj.voz_auditoria, rel)
    print("voz limpa: %s (%.1f s) | %d pausa(s) acima de 0,60 s | %d respiro(s) | %d dano(s) de corte"
          % (pj.relativo(pj.voz_limpo), det.get("duracao_limpo_s", 0.0), det.get("pausas_acima_de_0_60", 0),
             len(det.get("respiros", [])), len(det.get("danos", []))))
    for aviso in det.get("avisos", []):
        print("AVISO: %s" % aviso)
    if "fala_roteiro" in conferencias:
        f = conferencias["fala_roteiro"]
        print("fala x roteiro: %s%s" % ("PASS" if f["ok"] else "REPROVA", (": " + f["motivo"]) if f["motivo"] else ""))
    if not ok:
        motivos = "; ".join(c["motivo"] for c in conferencias.values() if not c["ok"])
        status.registrar(pj, NOME, "falhou", motivo=motivos[:600], detalhes={"auditoria": pj.relativo(pj.voz_auditoria)})
        C.erro(NOME, "REPROVA: %s" % motivos)
        return C.SAIDA_DEFEITO
    status.registrar(pj, NOME, "ok", detalhes={"duracao_limpo_s": det.get("duracao_limpo_s")})
    print("próximo: vam avatar %s   (o avatar sai DESTA voz limpa: %s)" % (pj.slug, pj.voz_limpo))
    return C.SAIDA_OK


def executar(args):
    return C.rodar(NOME, _executar, args)
