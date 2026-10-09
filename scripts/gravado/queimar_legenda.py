"""FASE 5c: queima a legenda ASS na peça (com caixinha, se houver; senão a montada).

A fonte da legenda é a Inter (ExtraBold), a do REPO: `fonts/inter-800.ttf` (licença OFL em
`fonts/OFL.txt`), nunca a do sistema. O libass resolve pelo nome do estilo, mas a pasta de fontes é
passada ao filtro (`fontsdir`) para não depender do cache de fontes da máquina. Sem a Inter na pasta
uma fonte de reserva não pode assumir calada: o filme sairia com outra tipografia sem aviso, então
`achar_fonte` para com UMA mensagem.

## Só queima legenda aprovada (W5.D)

`queimar_peca` exige a aprovação do diretor VIGENTE (`legendar.exigir_aprovada`): o sha256 do .ass que
está no disco tem que ser o aprovado, senão nenhum ffmpeg roda. Este módulo nunca escreve a aprovação
(quem é medido não assina: só `legendar.aprovar` escreve). Depois de queimar ele REGISTRA a queima em
`legendado/<peça>.queima.json` (sha256 do .ass queimado e do arquivo gerado), e é esse registro que a
entrega confere: o que está em `legendado/` é o que saiu da queima do .ass aprovado.

Depois de queimar: `gate_legenda` e `gate_sincronia` (a legendada tem que vir do corte ATUAL).

    python3 scripts/gravado/queimar_legenda.py [PECA ...] [--fontsdir PASTA] [--projeto DIR]
Lê `legendas/<peça>.ass` e grava `legendado/<peça>.mp4`. Sem a pasta, usa `fonts/` do repo.
"""
import argparse
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado import legendar, veredito  # noqa: E402
from gravado import projeto as gp  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402
from projeto import status as _status  # noqa: E402

FAMILIA = legendar.FONTE
QUEIMA_SUFIXO = ".queima.json"
_ESPECIAIS_DO_FILTRO = ("\\", ":", ",", "'", "[", "]", ";", "=")


class SemFonte(InsumoInvalido, RuntimeError):
    """A fonte da legenda não está na pasta de fontes."""


def escapar_filtro(caminho):
    """Escapa um caminho para dentro de um filtro do ffmpeg (a barra primeiro, para não dobrar)."""
    texto = str(caminho)
    for c in _ESPECIAIS_DO_FILTRO:
        texto = texto.replace(c, "\\" + c)
    return texto


def achar_fonte(fontsdir):
    """A pasta de fontes, desde que tenha a Inter (.otf ou .ttf)."""
    pasta = Path(fontsdir)
    if pasta.is_dir() and any(p.name.lower().startswith(FAMILIA.lower()) and p.suffix.lower() in (".otf", ".ttf")
                              for p in pasta.iterdir()):
        return pasta
    raise SemFonte("a fonte %s (ExtraBold, .otf ou .ttf, licença OFL) não está em %s: o repo traz "
                   "fonts/inter-800.ttf (recupere com `git checkout -- fonts/`) ou aponte outra pasta com --fontsdir"
                   % (FAMILIA, pasta))


def comando(src, ass, dest, fontsdir):
    vf = "ass=%s:fontsdir=%s" % (escapar_filtro(ass), escapar_filtro(fontsdir))
    return ["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(src), "-vf", vf, "-c:v", "libx264",
            "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy",
            "-movflags", "+faststart", str(dest)]


def queimar(src, ass, dest, fontsdir):
    """Queima `ass` em `src` e grava `dest`. É o ffmpeg e nada mais: NÃO confere aprovação. Quem queima uma
    peça do projeto usa `queimar_peca`, que só roda com a legenda aprovada."""
    veredito.exigir_arquivo(src, "a peça")
    veredito.exigir_arquivo(ass, "a legenda .ass")
    pasta = achar_fonte(fontsdir)
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(comando(src, ass, dest, pasta), capture_output=True, text=True)
    if r.returncode != 0:
        raise InsumoInvalido("o ffmpeg não conseguiu queimar a legenda: %s" % r.stderr.strip()[-300:])
    return Path(dest)


def caminho_queima(proj, nome):
    return proj.pasta("legendado") / (nome + QUEIMA_SUFIXO)


def registrar_queima(proj, nome, agora=None):
    """Grava `legendado/<peça>.queima.json`: o sha256 do .ass que está no disco e o do arquivo legendado.
    Devolve o dict. A entrega confere este registro contra a aprovação."""
    ass, legendado = proj.legenda_ass(nome), proj.legendado(nome)
    veredito.exigir_arquivo(ass, "a legenda .ass")
    veredito.exigir_arquivo(legendado, "a peça legendada")
    reg = {"versao": 1, "peca": nome, "ass_sha256": legendar.sha256_arquivo(ass),
           "legendado_sha256": legendar.sha256_arquivo(legendado),
           "queimado_em": agora if agora is not None else _status.instante()}
    _status.escrever_json_atomico(caminho_queima(proj, nome), reg)
    return reg


def queimar_peca(proj, nome, fontsdir):
    """Queima a legenda de `nome` na peça (com caixinha, se houver; senão a montada), SE a legenda estiver
    aprovada. LegendaNaoAprovada (nenhum ffmpeg roda) se não está, ou se o .ass mudou depois do ok."""
    legendar.exigir_aprovada(proj, nome)
    destino = queimar(proj.fonte_da_peca(nome), proj.legenda_ass(nome), proj.legendado(nome), fontsdir)
    registrar_queima(proj, nome)
    return destino


def main(argv=None):
    ap = argparse.ArgumentParser(description="Queima a legenda ASS na peça.")
    ap.add_argument("pecas", nargs="*", help="nomes das peças, como A1_normal (padrão: toda peça com .ass)")
    ap.add_argument("--fontsdir", help="pasta com a Inter (padrão: fonts/ do repo)")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    a = ap.parse_args(argv)

    def fazer():
        proj = gp.carregar(a.projeto)
        if a.fontsdir:
            fontsdir = Path(a.fontsdir)
        else:
            import caminhos
            fontsdir = Path(caminhos.FONTS)
        nomes = a.pecas or sorted(p.stem for p in proj.pasta("legendas").glob("*.ass"))
        if not nomes:
            raise InsumoInvalido("nenhum .ass em %s: rode o legendar antes" % proj.pasta("legendas"))
        for n in nomes:
            origem = proj.fonte_da_peca(n)
            queimar_peca(proj, n, fontsdir)
            print("  %s: %s/%s + legenda aprovada -> legendado/%s.mp4" % (n, origem.parent.name, origem.name, n))
    return veredito.ferramenta(fazer)


if __name__ == "__main__":
    sys.exit(main())
