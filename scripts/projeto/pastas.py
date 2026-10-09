"""Caminhos do projeto do aluno. Tudo mora em ESTADO/projetos/<slug> (ESTADO é o `_local/`).

    ESTADO/looks.json  glossario.json  marca/logo.png  trilhas/  projetos/<slug>/...

Nada aqui sai de ESTADO: o slug é validado (sem barra, ponto-ponto nem maiúscula) e cada
caminho é montado a partir da raiz do projeto. Para achar o ESTADO usa `caminhos.ESTADO`
lido NA HORA da chamada (respeita VAM_ESTADO); os testes passam `estado=` explícito.
"""
import re
import unicodedata
from pathlib import Path

_RE_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
_RE_CHAVE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_RE_NOME_ARQUIVO = re.compile(r"^[^/\\\x00]+$")


def estado_padrao():
    import caminhos
    return Path(caminhos.ESTADO)


def resolver_estado(estado):
    return Path(estado) if estado is not None else estado_padrao()


def validar_slug(slug):
    """Devolve o slug se for válido; ValueError caso contrário."""
    if not isinstance(slug, str) or not _RE_SLUG.match(slug):
        raise ValueError("slug inválido: %r (minúsculas sem acento, dígitos, - e _; começa com letra "
                         "ou dígito; até 63 caracteres)" % (slug,))
    return slug


def slugificar(texto):
    """Nome livre -> slug ("Três Horas por Dia!" -> "tres-horas-por-dia"). ValueError se sobrar nada."""
    t = unicodedata.normalize("NFD", str(texto).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9_]+", "-", t).strip("-_")[:63].strip("-_")
    if not t:
        raise ValueError("não consegui tirar um slug de %r" % (texto,))
    return t


def projetos_dir(estado=None):
    return resolver_estado(estado) / "projetos"


def looks_json(estado=None):
    return resolver_estado(estado) / "looks.json"


def glossario_json(estado=None):
    return resolver_estado(estado) / "glossario.json"


def trilhas_dir(estado=None):
    return resolver_estado(estado) / "trilhas"


def logo(estado=None):
    return resolver_estado(estado) / "marca" / "logo.png"


def trilha(nome_arquivo, estado=None):
    """Caminho de uma trilha do aluno. Só o NOME do arquivo: pasta ou ../ é ValueError."""
    if not isinstance(nome_arquivo, str) or not nome_arquivo or nome_arquivo in (".", "..") \
            or not _RE_NOME_ARQUIVO.match(nome_arquivo):
        raise ValueError("nome de trilha inválido: %r (só o nome do arquivo, sem pasta)" % (nome_arquivo,))
    return trilhas_dir(estado) / nome_arquivo


def listar(estado=None):
    """Slugs dos projetos existentes, em ordem."""
    base = projetos_dir(estado)
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and _RE_SLUG.match(p.name))


class PastasProjeto:
    """Caminhos de um projeto. Só monta caminhos; criar pastas é `criar()`."""

    def __init__(self, slug, estado):
        self.slug = validar_slug(slug)
        self.estado = Path(estado)
        self.raiz = self.estado / "projetos" / self.slug

    def __repr__(self):
        return "PastasProjeto(%r, %s)" % (self.slug, self.raiz)

    # --- arquivos da raiz do projeto
    @property
    def roteiro(self):
        return self.raiz / "roteiro.md"

    @property
    def projeto_json(self):
        return self.raiz / "projeto.json"

    @property
    def status_json(self):
        return self.raiz / "status.json"

    # --- voz
    @property
    def voz_dir(self):
        return self.raiz / "voz"

    @property
    def voz_limpo(self):
        return self.voz_dir / "limpo.mp3"

    @property
    def voz_auditoria(self):
        return self.voz_dir / "auditoria.json"

    def voz_bruto(self):
        """voz/bruto.<qualquer extensão>, ou None. Mais de um é ValueError (qual vale?)."""
        return self._unico(self.voz_dir, "bruto", "voz/bruto.*")

    # --- avatar
    @property
    def avatar_dir(self):
        return self.raiz / "avatar"

    @property
    def avatar_mp4(self):
        return self.avatar_dir / "avatar.mp4"

    @property
    def avatar_conferencia(self):
        return self.avatar_dir / "conferencia.json"

    @property
    def avatar_boca(self):
        return self.avatar_dir / "boca.png"

    # --- inserts
    @property
    def inserts_dir(self):
        return self.raiz / "inserts"

    def insert(self, chave):
        """inserts/<chave>.<ext>, ou None. A chave é validada; mais de um arquivo é ValueError."""
        if not isinstance(chave, str) or not _RE_CHAVE.match(chave):
            raise ValueError("chave de insert inválida: %r" % (chave,))
        return self._unico(self.inserts_dir, chave, "inserts/%s.*" % chave)

    def inserts(self):
        """{chave: caminho} de tudo que há em inserts/ (ignora arquivo oculto)."""
        if not self.inserts_dir.is_dir():
            return {}
        achados = {}
        for f in sorted(self.inserts_dir.iterdir()):
            if f.is_file() and not f.name.startswith(".") and _RE_CHAVE.match(f.stem):
                achados.setdefault(f.stem, f)
        return achados

    # --- plano
    @property
    def plano_dir(self):
        return self.raiz / "plano"

    @property
    def plano_json(self):
        return self.plano_dir / "plano.json"

    @property
    def plano_md(self):
        return self.plano_dir / "plano_edicao.md"

    @property
    def prancha_dir(self):
        return self.plano_dir / "prancha"

    @property
    def aprovacao(self):
        return self.plano_dir / "aprovacao.json"

    # --- render
    @property
    def render_dir(self):
        return self.raiz / "render"

    @property
    def alinhamento(self):
        return self.render_dir / "alinhamento.json"

    @property
    def timeline(self):
        return self.render_dir / "timeline.json"

    # --- entrega
    @property
    def entrega_dir(self):
        return self.raiz / "entrega"

    @property
    def final_9x16(self):
        return self.entrega_dir / "final_9x16.mp4"

    @property
    def final_whatsapp(self):
        return self.entrega_dir / "final_whatsapp.mp4"

    @property
    def laudo(self):
        return self.entrega_dir / "laudo.json"

    @property
    def nota(self):
        return self.entrega_dir / "nota.json"

    @property
    def folhas_dir(self):
        return self.entrega_dir / "folhas"

    # --- utilidades
    def dentro(self, caminho):
        """True se `caminho` (já resolvendo ../ e links) está dentro da raiz do projeto."""
        try:
            Path(caminho).resolve().relative_to(self.raiz.resolve())
            return True
        except ValueError:
            return False

    def relativo(self, caminho):
        """`caminho` relativo à raiz do projeto, com barras. ValueError se está fora dela."""
        if not self.dentro(caminho):
            raise ValueError("%s está fora do projeto %s" % (caminho, self.slug))
        return Path(caminho).resolve().relative_to(self.raiz.resolve()).as_posix()

    def criar(self):
        """Cria as pastas do projeto (idempotente; não apaga nem toca em arquivo)."""
        for sub in (self.voz_dir, self.avatar_dir, self.inserts_dir, self.prancha_dir,
                    self.render_dir, self.folhas_dir):
            sub.mkdir(parents=True, exist_ok=True)
        return self

    def _unico(self, pasta, nome, rotulo):
        if not pasta.is_dir():
            return None
        achados = sorted(f for f in pasta.iterdir()
                         if f.is_file() and f.stem == nome and not f.name.startswith("."))
        if len(achados) > 1:
            raise ValueError("mais de um arquivo para %s: %s" % (rotulo, ", ".join(f.name for f in achados)))
        return achados[0] if achados else None


def projeto(slug, estado=None):
    """PastasProjeto do `slug` (ValueError se o slug for inválido)."""
    return PastasProjeto(slug, resolver_estado(estado))
