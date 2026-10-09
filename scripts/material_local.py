#!/usr/bin/env python3
"""Mensagem ÚNICA e clara quando falta o material do anúncio do aluno (o projeto em _local/projetos/<slug>).

O repo traz o motor e os gates. O que NÃO vem nele, porque é do aluno e nunca é versionado: o projeto (roteiro.md,
projeto.json), a voz, o avatar, os inserts, o logo e as trilhas. Quando isso falta, o motor não solta traceback nem uma
lista de "faltam N arquivos": diz uma vez qual é a causa mais a montante e QUAL COMANDO `vam` resolve.

    from material_local import exigir, checar_material
    exigir(caminho, "o roteiro do anúncio")       # sai com código 2 e a mensagem
    if not checar_material(pj): ...               # False e UMA mensagem no stderr (pj: projeto.pastas.PastasProjeto)
"""
import sys
from pathlib import Path

COMANDO_NOVO = "python3 scripts/vam.py novo <slug> --look <look> --sem-trilha \"motivo\""


def mensagem(caminho, o_que):
    """Texto da mensagem de material ausente (um caminho que o motor pediu e não existe)."""
    return ("%s não existe (%s): esse é material do SEU anúncio e não vem no repo.\n"
            "  Os anúncios moram em _local/projetos/<slug>; crie um com:  %s\n"
            "  e siga o vam status <slug> para o próximo passo." % (caminho, o_que, COMANDO_NOVO.replace(
                "python3 scripts/vam.py novo", "vam novo")))


def exigir(caminho, o_que="material do seu anúncio"):
    """Garante que `caminho` existe; senão imprime a mensagem e sai com código 2."""
    if Path(caminho).exists():
        return Path(caminho)
    print(mensagem(caminho, o_que), file=sys.stderr, flush=True)
    raise SystemExit(2)


def faltando(pj):
    """(o que falta, comando que resolve) do material do projeto, na ordem do pipeline; None se nada falta."""
    s = pj.slug
    if not pj.projeto_json.is_file():
        return ("o projeto %s" % s, "vam novo %s --look <look> --sem-trilha \"motivo\"" % s)
    if not pj.roteiro.is_file():
        return ("o roteiro.md", "vam roteiro %s --de roteiro.md" % s)
    if not pj.voz_limpo.is_file():
        return ("a voz limpa (voz/limpo.mp3)", "vam audio %s --bruto voz.m4a" % s)
    if not pj.avatar_mp4.is_file():
        return ("o avatar (avatar/avatar.mp4)", "vam avatar %s" % s)
    if not pj.plano_json.is_file():
        return ("o plano medido (plano/plano.json)", "vam plano %s" % s)
    return None


def checar_material(pj):
    """True se o material do projeto existe; senão UMA mensagem com o comando que resolve, e False."""
    f = faltando(pj)
    if f is None:
        return True
    print("falta %s em %s. Resolva com: %s" % (f[0], pj.raiz, f[1]), file=sys.stderr, flush=True)
    return False
