"""`vam fumaca --saida fumaca.mp4`: o teste de fumaça do render, em 10 a 20 segundos, sem projeto e sem mídia.

Renderiza um overlay 9:16 de 2 s com o template reel-editorial pelo HyperFrames (Node, Chromium e as fontes do template) e
confere com o ffprobe que o MP4 existe e dura 1,5 s ou mais. Sai com 0 só se o arquivo prova a cadeia inteira.

    vam fumaca --saida fumaca.mp4

Existe para o CI e para o aluno provarem que o render funciona na máquina (sobretudo no Windows) antes de gastar um
anúncio. É um teste de integração da ferramenta, não passa pelo plano, pelos gates nem pelo estado do aluno.
Saídas: 0 fez · 1 defeito medido (o render falhou, a fonte não carregou, o MP4 não presta) · 2 pedido ou insumo inválido
(sem --saida, sem ffprobe, HyperFrames não instalado).
"""
import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import plataforma
from cli import _comum as C

NOME = "fumaca"
RAIZ = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = RAIZ / "templates" / "reel-editorial"          # separado de RAIZ: a pasta do HyperFrames é a que muda nos testes
DURACAO_S = 2.0
MINIMO_S = 1.5
FPS = 30
TIMEOUT_RENDER_S = 900                  # um Chromium frio no CI baixa e abre devagar; o render em si leva segundos
TEXTO_DO_GANCHO = ("teste de", "fumaça do", "render")       # eyebrow, l1 e accent do hook do template
FONTE_URL = re.compile(r'url\("(fonts/[^"]+)"\)')
MAGIA_WOFF2 = b"wOF2"


class SemFfprobe(RuntimeError):
    """O ffprobe não está no PATH (vem junto do ffmpeg)."""


def registrar(subparsers):
    p = subparsers.add_parser(NOME, help="prova o render (Node, HyperFrames, Chromium, fontes) com um MP4 de 2 s",
                              description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--saida", required=True,
                   help="o MP4 que o comando grava (termina em .mp4; as pastas do caminho são criadas)")
    p.set_defaults(func=executar)
    return p


def _ffprobe():
    """O caminho completo do ffprobe, ou None. `shutil.which` aplica o PATHEXT: no Windows acha `ffprobe.exe` e `.cmd`."""
    return shutil.which("ffprobe")


def _formatar_s(segundos):
    return ("%.2f s" % segundos).replace(".", ",")


def duracao(mp4):
    """A duração em segundos que o ffprobe lê no MP4, ou None se ele não devolve um número. SemFfprobe sem o ffprobe."""
    ffprobe = _ffprobe()
    if not ffprobe:
        raise SemFfprobe("ffprobe não encontrado no PATH (vem junto do ffmpeg): instale o ffmpeg completo")
    r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of",
                        "default=noprint_wrappers=1:nokey=1", str(mp4)], capture_output=True, encoding="utf-8",
                       errors="replace", timeout=60)
    if r.returncode != 0:
        raise ValueError("o ffprobe não leu o arquivo: %s" % ((r.stderr or r.stdout or "").strip()[-300:] or "sem mensagem"))
    try:
        return float((r.stdout or "").strip().splitlines()[0])
    except (ValueError, IndexError):
        return None


def conferir_mp4(mp4):
    """(ok, motivo): o arquivo existe, não está vazio e o ffprobe mede MINIMO_S ou mais. SemFfprobe sobe para quem chama."""
    mp4 = Path(mp4)
    if not mp4.is_file():
        return False, "o MP4 não existe: %s" % mp4
    if mp4.stat().st_size == 0:
        return False, "o MP4 está vazio: %s" % mp4
    try:
        segundos = duracao(mp4)
    except ValueError as e:
        return False, str(e)
    if segundos is None:
        return False, "o ffprobe não devolveu a duração do MP4"
    if segundos < MINIMO_S:
        return False, "a duração do MP4 é %s, abaixo do mínimo de %s" % (_formatar_s(segundos), _formatar_s(MINIMO_S))
    return True, _formatar_s(segundos)


def montar_projeto(pasta):
    """O projeto do HyperFrames em `pasta`: o index.html do reel-editorial com 2 s e só o gancho, as fontes e o meta.json.

    Sai do mesmo template e dos mesmos passos do mostruário de lettering (`overlay.html_injecao`): parciais resolvidos, sem
    avatar, logo nem CTA (a fumaça não traz mídia de anúncio) e o gancho no lugar do texto de exemplo."""
    from overlay import html_injecao as H
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    html = H.ler_template(TEMPLATE_DIR / "index.html")
    html = H.injetar_marcadores(html, "", "")
    html = H.injetar_chips(html, "")
    html = H.fixar_duracao(html, DURACAO_S)
    html = H.remover_beat_pb(html)
    html = H.remover_wipes(html)
    html = "\n".join(ln for ln in html.split("\n") if 'id="a-roll' not in ln and 'id="ev-logo"' not in ln)
    html = re.sub(r'\s*<!-- CTA -->\s*<div data-hf-id="hf-bi9a" id="cta".*?</div>\s*</div>', "", html, flags=re.S)
    html = html.replace('id="hook" class="clip" data-start="0" data-duration="2.5"',
                        'id="hook" class="clip" data-start="0" data-duration="%s"' % DURACAO_S)
    for classe, texto in zip(("eyebrow", "l1", "accent"), TEXTO_DO_GANCHO):
        html = re.sub(r'(class="%s">)[^<]*(</div>)' % classe, lambda m: m.group(1) + texto + m.group(2), html, count=1)
    (pasta / "index.html").write_text(html, encoding="utf-8")
    if (pasta / "fonts").exists():
        shutil.rmtree(pasta / "fonts")
    shutil.copytree(str(TEMPLATE_DIR / "fonts"), str(pasta / "fonts"))
    shutil.copy(str(TEMPLATE_DIR / "meta.json"), str(pasta / "meta.json"))
    return pasta


def conferir_fontes(projeto):
    """Lista de problemas (vazia = tudo certo) nas fontes que o HTML pede: ausente, ou arquivo que não é woff2.

    Pega o clone em que o symlink do git virou um arquivo de texto com o alvo dentro: o Chromium ignora a fonte sem erro
    e o render sai com a fonte do sistema."""
    projeto = Path(projeto)
    pedidas = sorted(set(FONTE_URL.findall((projeto / "index.html").read_text(encoding="utf-8"))))
    problemas = []
    for rel in pedidas:
        arquivo = projeto / rel
        if not arquivo.is_file():
            problemas.append("fonte ausente no projeto: %s" % rel)
            continue
        inicio = arquivo.read_bytes()[:4]
        if rel.endswith(".woff2") and inicio != MAGIA_WOFF2:
            problemas.append("%s não é uma fonte woff2 (%d bytes, começa com %r): no Windows isso é um symlink do git "
                             "que virou texto" % (rel, arquivo.stat().st_size, inicio))
    return problemas


def renderizar(raiz, projeto, destino, timeout=TIMEOUT_RENDER_S):
    """Roda `hyperframes render` no projeto e devolve (código de saída, texto do log). ErroHyperFrames se não está instalado.

    O comando vem de `plataforma.hf_cmd`: `node <cli.js do pacote>`, o mesmo nos três sistemas."""
    cmd = plataforma.hf_cmd(raiz) + ["render", str(projeto), "-o", str(destino), "--fps", str(FPS), "--workers", "1",
                                     "--quiet"]
    try:
        r = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "tempo esgotado (%d s) no render" % timeout
    except OSError as e:
        return 127, "não consegui rodar %s: %s" % (cmd[0], e)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def executar(args):
    destino = Path(args.saida)
    if destino.suffix.lower() != ".mp4":
        C.erro(NOME, "--saida precisa ser um arquivo .mp4 (veio %s)" % destino)
        return C.SAIDA_USO
    if destino.is_dir():
        C.erro(NOME, "--saida é uma pasta; dê o caminho de um arquivo .mp4 (ex.: %s)" % (destino / "fumaca.mp4"))
        return C.SAIDA_USO
    if not _ffprobe():
        C.erro(NOME, "ffprobe não encontrado no PATH (vem junto do ffmpeg): instale o ffmpeg completo e rode `vam doctor`")
        return C.SAIDA_USO
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists():                    # sobra de uma rodada anterior não pode passar por resultado desta
            destino.unlink()
    except OSError as e:
        C.erro(NOME, "não consegui preparar %s: %s" % (destino, e))
        return C.SAIDA_USO
    trabalho = Path(tempfile.mkdtemp(prefix="vam-fumaca-"))
    try:
        try:
            projeto = montar_projeto(trabalho / "projeto")
        except OSError as e:
            C.erro(NOME, "não consegui montar o projeto do overlay a partir de %s: %s" % (TEMPLATE_DIR, e))
            return C.SAIDA_USO
        problemas = conferir_fontes(projeto)
        if problemas:
            C.erro(NOME, "fonte do template inválida:\n  " + "\n  ".join(problemas)
                   + "\n  conserto: git checkout -- templates fonts   (e confira o `git config core.symlinks`)")
            return C.SAIDA_DEFEITO
        print("vam %s: renderizando %s de overlay 9:16 com o reel-editorial (HyperFrames)..." % (NOME, _formatar_s(DURACAO_S)))
        parcial = trabalho / "fumaca.mp4"
        try:
            rc, texto = renderizar(RAIZ, projeto, parcial)
        except plataforma.ErroHyperFrames as e:
            C.erro(NOME, str(e))
            return C.SAIDA_USO
        if rc != 0:
            C.erro(NOME, "o HyperFrames saiu com %d:\n%s" % (rc, texto.strip()[-1200:]))
            return C.SAIDA_DEFEITO
        try:
            ok, motivo = conferir_mp4(parcial)
        except SemFfprobe as e:
            C.erro(NOME, str(e))
            return C.SAIDA_USO
        if not ok:
            C.erro(NOME, motivo)
            return C.SAIDA_DEFEITO
        shutil.move(str(parcial), str(destino))
    finally:
        shutil.rmtree(str(trabalho), ignore_errors=True)
    print("vam %s: OK. %s (%s)" % (NOME, destino, motivo))
    return C.SAIDA_OK
