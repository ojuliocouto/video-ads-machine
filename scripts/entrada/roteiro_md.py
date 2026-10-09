"""Leitor do roteiro.md (W1.B): texto, arquivo .md ou .txt do aluno -> blocos validados.

A gramática (colchete, tipo, KEY, LEAD, âncora, lista, ênfase) tem UM leitor só no produto:
`ler_roteiro`, em scripts/contratos/validar.py. Este módulo não interpreta direção nenhuma.
Ele cuida do que está em volta: ler o arquivo (UTF-8), passar pela normalização do texto
colado e devolver uma `Leitura` que responde as perguntas que o resto do produto faz (tem
erro? precisa de plano? qual é a sequência de palavras da fala?).

    from entrada import roteiro_md
    lei = roteiro_md.ler_arquivo("roteiro.md")      # .md ou .txt, normaliza por padrão
    roteiro_md.exigir(lei)                          # levanta RoteiroInvalido com uma linha por problema
    lei.blocos, lei.precisa_plano, lei.sequencia_de_palavras()

Nenhum caminho do produto lê planilha. Só biblioteca padrão, sem rede.
"""
import importlib.util
import os
import tempfile
from pathlib import Path

from . import texto_colado

_VALIDAR = Path(__file__).resolve().parents[1] / "contratos" / "validar.py"
_CACHE = {}

EXTENSOES = (".md", ".txt")


def contrato():
    """O módulo scripts/contratos/validar.py, carregado pelo caminho (uma vez).

    Pelo caminho e não por `import contratos`: a pasta de contratos na raiz do repo e o
    pacote tests/contratos têm o mesmo nome curto, e o import por nome depende da ordem do
    sys.path de quem executa.
    """
    if "m" not in _CACHE:
        spec = importlib.util.spec_from_file_location("vam_contratos_validar", _VALIDAR)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        _CACHE["m"] = modulo
    return _CACHE["m"]


def formatar_erros(erros):
    """Uma linha por problema: 'linha N (campo): motivo'."""
    return "\n".join(f"  {e}" for e in erros)


class RoteiroInvalido(ValueError):
    """O roteiro não passa na convenção. `.leitura` traz o que foi lido e `.erros` os problemas."""

    def __init__(self, leitura):
        self.leitura = leitura
        self.erros = list(leitura.erros)
        super().__init__(f"roteiro.md fora da convenção ({len(self.erros)} problema(s)):\n"
                         + formatar_erros(self.erros))


class Leitura:
    """O que `ler` devolve.

    texto     o texto lido (já normalizado, quando se pediu)
    livre     True quando o roteiro não tem nenhuma direção entre colchetes
    blocos    a lista de blocos do contrato (11 campos cada); vazia se o roteiro está vazio
    erros     lista de Erro do validador; só vale a leitura quando está vazia
    """

    __slots__ = ("texto", "livre", "blocos", "erros")

    def __init__(self, texto, livre, blocos, erros):
        self.texto = texto
        self.livre = bool(livre)
        self.blocos = blocos
        self.erros = erros

    @property
    def ok(self):
        return not self.erros

    @property
    def precisa_plano(self):
        """True no roteiro livre: o plano propõe as direções e o aluno aprova."""
        return self.livre

    def como_dict(self):
        """O mesmo formato de `ler_roteiro`: {'livre': bool, 'blocos': [...]}."""
        return {"livre": self.livre, "blocos": self.blocos}

    def fala_completa(self):
        return " ".join(b["fala"] for b in self.blocos)

    def sequencia_de_palavras(self):
        """As palavras da fala de todos os blocos, na ordem, na forma de `contratos.palavras`."""
        return contrato().palavras(self.fala_completa())

    @property
    def n_palavras(self):
        return len(self.sequencia_de_palavras())

    def __repr__(self):
        return (f"Leitura(blocos={len(self.blocos)}, livre={self.livre}, erros={len(self.erros)})")


def ler(texto, normalizar=False):
    """Lê um roteiro.md já em memória. `normalizar=True` passa antes pelo texto colado."""
    if normalizar:
        texto = texto_colado.normalizar(texto)
    leitura, erros = contrato().ler_roteiro(texto)
    if leitura is None:
        return Leitura(texto, False, [], list(erros))
    return Leitura(texto, leitura["livre"], leitura["blocos"], list(erros))


def ler_arquivo(caminho, normalizar=True):
    """Lê um .md ou .txt do aluno (UTF-8, com ou sem BOM). Normaliza por padrão."""
    caminho = Path(caminho)
    if caminho.suffix.lower() not in EXTENSOES:
        raise ValueError(f"{caminho.name}: o roteiro tem que ser um arquivo {' ou '.join(EXTENSOES)} "
                         "(Word e PDF não: cole o texto no chat ou exporte como texto)")
    dados = caminho.read_bytes()
    try:
        texto = dados.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise ValueError(f"{caminho.name}: o arquivo não está em UTF-8 (byte {e.start}). "
                         "Salve de novo como UTF-8 no editor de texto, para os acentos não se perderem") from None
    return ler(texto, normalizar=normalizar)


def exigir(leitura):
    """Devolve a própria leitura quando está ok; senão levanta RoteiroInvalido."""
    if leitura.erros:
        raise RoteiroInvalido(leitura)
    return leitura


def escrever_atomico(destino, conteudo):
    """Grava texto (UTF-8) ou bytes por arquivo temporário na mesma pasta + rename."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    dados = conteudo.encode("utf-8") if isinstance(conteudo, str) else conteudo
    fd, tmp = tempfile.mkstemp(prefix=f".{destino.name}.", suffix=".tmp", dir=str(destino.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(dados)
        os.chmod(tmp, 0o644)              # mkstemp cria 0600; arquivo de projeto é legível
        os.replace(tmp, destino)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return destino


def salvar(texto, destino, sobrescrever=False):
    """Normaliza, valida e grava o roteiro.md. Nunca grava roteiro inválido.

    Não sobrescreve um roteiro.md que já existe sem `sobrescrever=True`: trocar a fala vence a
    aprovação do plano, então tem que ser decisão de quem chama. Devolve a Leitura.
    """
    destino = Path(destino)
    if destino.exists() and not sobrescrever:
        raise FileExistsError(f"{destino} já existe; use sobrescrever=True para trocar a fala "
                              "(isso vence a aprovação do plano)")
    leitura = exigir(ler(texto, normalizar=True))
    escrever_atomico(destino, leitura.texto)
    return leitura
