#!/usr/bin/env python3
"""Cria a pasta _local/ (o material do SEU anuncio) com a estrutura e exemplos.

    python3 scripts/init_local.py

O que e criado (nada e sobrescrito; rodar de novo e seguro):
    _local/README.md                       o que e cada coisa
    _local/configs/                        um config por anuncio e look (+ exemplo)
    _local/roteiros/                       roteiros anotados (+ roteiro_demo.txt)
    _local/dados/inputs/                   <ad>_leva.txt e <ad>_inserts.json (+ ad99 de exemplo)
    _local/dados/output/                   onde saem os renders
    _local/render-reel-editorial/          meta.json (logo.png e seu: ponha aqui)
    _local/gate-excecoes.json              excecoes documentadas do gate (vazio)
    _local/revisor-trocas.json             trocas proprias do revisor de copy (vazio)
    _local/_doc_map.json                   fonte (doc) de cada anuncio, p/ o gate de fidelidade

A pasta _local/ e gitignorada: e sua, nunca vai pro repo. A midia (avatar, voz, inserts)
voce coloca em _local/dados/ ou gera com a HeyGen (veja o README).
"""
import json
import shutil
import sys
from pathlib import Path

from caminhos import ESTADO, INPUTS, OUTPUT, RAIZ, ROTEIROS, TEMPLATES

AD_EXEMPLO = "ad99v2"

LEIA_ME = """# _local: o material do SEU anúncio

Esta pasta é sua e fica fora do git. O repo traz o motor e os gates (scripts/gates/);
aqui mora o que é do anúncio de cada pessoa.

| O que | Onde | Para que serve |
|---|---|---|
| Configs | `configs/<ad>_<look>.json` | hook, letterings, palavras-chave, CTA, caminho do avatar. Veja `configs/ad99v2_espuma.json` |
| Roteiros | `roteiros/<ad>.txt` | roteiro anotado (a fonte que o gate de marcadores confere) |
| Roteiro do build | `dados/inputs/<ad>_leva.txt` | uma linha por bloco: `[instrução visual] fala` |
| Mapa de inserções | `dados/inputs/<ad>_inserts.json` | liga a instrução do bloco ao arquivo de vídeo/imagem do insert |
| Logo | `render-reel-editorial/logo.png` | logo/wordmark que entra no CTA (PNG transparente) |
| meta.json | `render-reel-editorial/meta.json` | metadados do template (já vem pronto) |
| Mídia | `dados/inputs/` | avatar, voz e inserts do seu anúncio |
| Saídas | `dados/output/` | renders e arquivos de timing |
| Exceções do gate | `gate-excecoes.json` | marcadores do roteiro que não são arquivo baixável (com motivo) |
| Trocas do revisor | `revisor-trocas.json` | `[regex, troca, descrição]` para o nome da sua marca/evento |
| Fonte de cada ad | `_doc_map.json` | doc/aba/seção de origem, usado pelo gate de fidelidade |

O anúncio `ad99v2` é só um exemplo de formato: troque pelo seu.
Veja também `demo/` na raiz do repo (`roteiro_demo.txt`, `brief.example.json`).
"""


def _gravar(caminho, conteudo, criados, existentes):
    caminho = Path(caminho)
    if caminho.exists():
        existentes.append(caminho)
        return
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo, encoding="utf-8")
    criados.append(caminho)


def _json(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def _roteiro_demo():
    p = RAIZ / "demo" / "roteiro_demo.txt"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return "esse é o *demo* da video ads machine.\n"


def _meta():
    p = TEMPLATES / "reel-editorial" / "meta.json"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return _json({"id": "reel-editorial", "name": "Reel Editorial"})


def criar():
    criados, existentes = [], []
    for d in (ESTADO / "configs", ROTEIROS, INPUTS, OUTPUT, ESTADO / "render-reel-editorial"):
        Path(d).mkdir(parents=True, exist_ok=True)

    _gravar(ESTADO / "README.md", LEIA_ME, criados, existentes)
    _gravar(ROTEIROS / "roteiro_demo.txt", _roteiro_demo(), criados, existentes)
    _gravar(ESTADO / "render-reel-editorial" / "meta.json", _meta(), criados, existentes)
    _gravar(ESTADO / "gate-excecoes.json", "{}\n", criados, existentes)
    _gravar(ESTADO / "revisor-trocas.json", "[]\n", criados, existentes)
    _gravar(ESTADO / "_doc_map.json", "{}\n", criados, existentes)

    # exemplo de anuncio: mostra o FORMATO de cada arquivo (nao e um anuncio de verdade)
    _gravar(INPUTS / f"{AD_EXEMPLO}_leva.txt",
            "[apresentador de frente para a câmera] esse é o demo da video ads machine.\n"
            "[inserção de vídeo: demo] você escreve o roteiro e a máquina monta o anúncio.\n"
            "[lettering + logo] toque em saiba mais para começar.\n",
            criados, existentes)
    _gravar(INPUTS / f"{AD_EXEMPLO}_inserts.json",
            _json({"demo": {"file": str(INPUTS / "assets" / "ad99_demo.mp4"),
                            "start": 0, "dur_max": 4}}),
            criados, existentes)
    _gravar(ESTADO / "configs" / "ad99v2_espuma.json",
            _json({
                "ad": AD_EXEMPLO,
                "look": "espuma_roxa",
                "format": "9x16",
                "avatar": str(INPUTS / f"{AD_EXEMPLO}_espuma_roxa_avatar.mp4"),
                "out_dir": str(ESTADO / f"render-{AD_EXEMPLO}-espuma"),
                "hook": {"eyebrow": "SEU GANCHO", "l1": "uma frase forte",
                         "accent": "COM DESTAQUE"},
                "cta_label": "saiba mais",
                "kw_phrases": ["demo", "saiba mais"],
                "letterings": [
                    {"lead": "você escreve", "key": "O ROTEIRO", "anchor": "roteiro",
                     "nth": 1, "dur": 2.2}],
            }),
            criados, existentes)
    return criados, existentes


def _rel(p):
    try:
        return str(Path(p).relative_to(ESTADO.parent))
    except ValueError:
        return str(p)


def main():
    criados, existentes = criar()
    print(f"_local pronto em {ESTADO}")
    for p in criados:
        print(f"  criado   {_rel(p)}")
    for p in existentes:
        print(f"  ja existe {_rel(p)} (mantido)")
    print("\nPróximos passos:")
    print("  1. Coloque o seu logo em _local/render-reel-editorial/logo.png")
    print("  2. Substitua os exemplos ad99 pelo seu anúncio (formato em _local/README.md)")
    print("  3. Quer ver o formato do roteiro e do brief antes? Veja demo/ "
          "(roteiro_demo.txt, brief.example.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
