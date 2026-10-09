#!/usr/bin/env python3
"""Cria a pasta _local/ (o material do aluno) com a estrutura do produto. Nada é sobrescrito; rodar de novo é seguro.

    python3 scripts/init_local.py            (o `bash setup.sh` e o `vam novo` chamam sozinhos)

    _local/README.md        o que é cada coisa
    _local/looks.json       os looks do HeyGen do aluno (o `vam avatar` cadastra e aprova)
    _local/glossario.json   grafias e variantes do ASR (marca, produto, nomes)
    _local/marca/           logo.png da marca do aluno (entra no CTA)
    _local/trilhas/         trilhas royalty-free do aluno
    _local/projetos/        um projeto por anúncio (o `vam novo <slug>` cria)

A pasta _local/ é gitignorada: é do aluno, nunca vai para o repo. Quem cria e lê os arquivos de dentro é o pacote
`projeto/` (pastas, looks, glossário, novo); aqui só nasce a estrutura.
"""
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

LEIA_ME = """# _local: o material do aluno

Esta pasta é sua e fica fora do git. O repo traz o motor e os gates; aqui mora o que é de cada anúncio.

| O que | Onde | Quem cria |
|---|---|---|
| Looks do HeyGen | `looks.json` | `vam avatar <slug> --avatar-id ID --plano medio` cadastra; `--aprovar-look` aprova |
| Glossário | `glossario.json` | grafias certas e variantes que o ASR escreve errado (marca, produto, nomes) |
| Logo | `marca/logo.png` | você (PNG transparente; entra no CTA) |
| Trilhas | `trilhas/` | você (royalty-free; ou `--sem-trilha "motivo"` no projeto) |
| Projetos | `projetos/<slug>/` | `vam novo <slug>`: roteiro.md, voz/, avatar/, inserts/, plano/, render/, entrega/ |

Comece por: `python3 scripts/vam.py novo meu-anuncio --look <look> --sem-trilha "motivo"`.
"""


def _gravar(caminho, conteudo, criados, existentes):
    caminho = Path(caminho)
    if caminho.exists():
        existentes.append(caminho)
        return
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo, encoding="utf-8")
    criados.append(caminho)


def criar(estado=None):
    """Cria a estrutura em `estado` (padrão: o _local do repo). Devolve (criados, existentes)."""
    import json
    from projeto import glossario, pastas
    estado = pastas.resolver_estado(estado)
    criados, existentes = [], []
    for d in (pastas.projetos_dir(estado), pastas.trilhas_dir(estado), pastas.logo(estado).parent):
        if d.is_dir():
            existentes.append(d)
        else:
            d.mkdir(parents=True)
            criados.append(d)
    _gravar(estado / "README.md", LEIA_ME, criados, existentes)
    _gravar(pastas.looks_json(estado), json.dumps({"versao": 1, "looks": {}}, indent=2) + "\n", criados, existentes)
    _gravar(pastas.glossario_json(estado), json.dumps(glossario.vazio(), indent=2) + "\n", criados, existentes)
    return criados, existentes


def main():
    from projeto import pastas
    estado = pastas.estado_padrao()
    criados, existentes = criar(estado)
    print("_local pronto em %s" % estado)
    for p in criados:
        print("  criado    %s" % p.relative_to(estado.parent))
    for p in existentes:
        print("  já existe %s (mantido)" % p.relative_to(estado.parent))
    print("\nPróximos passos:\n  1. ponha o logo da sua marca em _local/marca/logo.png\n"
          "  2. crie o anúncio: vam novo <slug> --look <look> --sem-trilha \"motivo\"\n"
          "  3. confira a máquina: vam doctor\n"
          "  (o vam é: python3 scripts/vam.py)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
