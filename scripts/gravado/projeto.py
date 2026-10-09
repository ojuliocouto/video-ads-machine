"""Caminhos e plano de um projeto de take gravado: a fonte única, sem efeito no import.

Um projeto é uma pasta. O CÓDIGO mora no repo; o PROJETO guarda o plano e tudo o que o pipeline
gera; os BRUTOS (os .MOV da câmera) ficam onde estão, só leitura. Nada é gravado dentro do código
nem dentro dos brutos.

O plano é DADO, nunca código: `plano_gravado.json`. (O formato antigo era um `plano.py`
carregado por `exec`: um arquivo qualquer da pasta virava código que roda. Não é mais aceito.)

    {"versao": 1,
     "brutos": "/pasta/dos/brutos",
     "ignorar": ["IMG_0001"],                       takes que não entram na leva (sem extensão)
     "ads": {
       "A1": {"nome": "Primeiro", "tema": "primeiro",
              "corpo":        [["IMG_0002", 9.30, 14.00], ["IMG_0002", 17.85, 29.00]],
              "cta_normal":   [["IMG_0002", 52.16, 53.90]],
              "cta_desconto": [["IMG_0003", 0.30, 13.80]],
              "corpo_desconto": [...]}}}            só se o corpo precisar parar antes

Cada trecho é `[take, início, fim]` em SEGUNDOS, medido no áudio higienizado (`limpo/<take>`),
UMA FRASE por trecho. `corpo` e `cta_*` são listas separadas: trocar a cauda inteira apagaria o
argumento. A aceleração NÃO é do plano: vem do `projeto.json` do aluno (padrão 1,2 em take real)
quando ele existe, senão o padrão do modo gravado.

Plano quebrado é insumo inválido (saída 2 nos gates): a mensagem lista todos os campos errados.

    python3 scripts/gravado/projeto.py criar --brutos PASTA [--projeto DIR]
    python3 scripts/gravado/projeto.py [conferir] [--projeto DIR]
"""
import argparse
import math
import re
import sys
from pathlib import Path

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado.veredito import InsumoInvalido  # noqa: E402
from projeto import glossario as _glossario  # noqa: E402  (o pacote do aluno: scripts/projeto)
from projeto import modelo as _modelo  # noqa: E402
from projeto import status as _status  # noqa: E402

ARQUIVO_PLANO = "plano_gravado.json"
PASTAS = ("wav", "audio", "limpo", "transcricoes", "cache_asr", "montados", "com_caixinha",
          "caixinhas", "legendas", "legendado", "ENTREGA", "_tmp")
CHAVES_DO_PLANO = ("versao", "brutos", "ignorar", "ads")
CHAVES_DO_AD = ("nome", "tema", "corpo", "corpo_desconto", "cta_normal", "cta_desconto")
CHAVES_DE_TRECHOS = ("corpo", "corpo_desconto", "cta_normal", "cta_desconto")
EXTENSOES_DE_BRUTO = (".mov", ".mp4", ".m4v")
EXTENSOES_DE_LIMPO = (".mp3", ".wav", ".m4a", ".flac")
ACEL_PADRAO = _modelo.PADRAO_ACELERACAO["gravado"]

_RE_TAKE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_RE_COD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,31}$")
_RE_TEMA = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class PlanoInvalido(InsumoInvalido, ValueError):
    """O plano não existe ou não cumpre o formato. `erros` lista cada campo errado."""

    def __init__(self, erros, arquivo=None):
        self.erros = [erros] if isinstance(erros, str) else list(erros)
        self.arquivo = str(arquivo) if arquivo else None
        onde = " (%s)" % self.arquivo if self.arquivo else ""
        super(PlanoInvalido, self).__init__("%s inválido%s:\n%s" % (
            ARQUIVO_PLANO, onde, "\n".join("  " + e for e in self.erros)))


# --- validação -----------------------------------------------------------------------------

def _numero(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _erros_do_trecho(t, caminho):
    if not isinstance(t, (list, tuple)) or len(t) != 3:
        return ["%s: o trecho é [take, início, fim]" % caminho]
    take, ini, fim = t
    erros = []
    if not isinstance(take, str) or not _RE_TAKE.match(take):
        erros.append("%s: take %r inválido (só letras, números, _ . -, sem pasta)" % (caminho, take))
    if not _numero(ini):
        erros.append("%s: início %r não é número" % (caminho, ini))
    elif ini < 0:
        erros.append("%s: início %s é negativo" % (caminho, ini))
    if not _numero(fim):
        erros.append("%s: fim %r não é número" % (caminho, fim))
    elif _numero(ini) and fim <= ini:
        erros.append("%s: o fim (%s) tem que ser maior que o início (%s)" % (caminho, fim, ini))
    return erros


def _erros_do_ad(cod, ad):
    base = "$.ads.%s" % cod
    if not isinstance(ad, dict):
        return ["%s: o anúncio deve ser um objeto" % base]
    erros = ["%s.%s: campo desconhecido" % (base, k) for k in ad if k not in CHAVES_DO_AD]
    if "nome" in ad and not isinstance(ad["nome"], str):
        erros.append("%s.nome: deve ser texto" % base)
    if "tema" in ad and not (isinstance(ad["tema"], str) and _RE_TEMA.match(ad["tema"])):
        erros.append("%s.tema: minúsculas, números e hífen" % base)
    for chave in CHAVES_DE_TRECHOS:
        obrigatoria = chave in ("corpo", "cta_normal")
        if chave not in ad:
            if obrigatoria:
                erros.append("%s.%s: falta (precisa de pelo menos um trecho)" % (base, chave))
            continue
        lista = ad[chave]
        if not isinstance(lista, list) or not lista:
            erros.append("%s.%s: precisa de pelo menos um trecho" % (base, chave))
            continue
        for i, t in enumerate(lista):
            erros.extend(_erros_do_trecho(t, "%s.%s[%d]" % (base, chave, i)))
    if "corpo_desconto" in ad and "cta_desconto" not in ad:
        erros.append("%s.corpo_desconto: só existe junto com cta_desconto" % base)
    return erros


def validar_plano(dados):
    """Lista de erros (cada um com o caminho do campo). Vazia = plano válido."""
    if not isinstance(dados, dict):
        return ["$: o plano deve ser um objeto JSON"]
    erros = ["$.%s: campo desconhecido" % k for k in dados if k not in CHAVES_DO_PLANO]
    if dados.get("versao") != 1:
        erros.append("$.versao: deve ser 1")
    if not isinstance(dados.get("brutos"), str) or not dados.get("brutos", "").strip():
        erros.append("$.brutos: a pasta dos brutos (texto)")
    ignorar = dados.get("ignorar", [])
    if not isinstance(ignorar, list) or not all(isinstance(x, str) and _RE_TAKE.match(x) for x in ignorar):
        erros.append("$.ignorar: lista de nomes de take, sem extensão")
    ads = dados.get("ads")
    if not isinstance(ads, dict):
        erros.append("$.ads: deve ser um objeto {código: anúncio}")
    else:
        for cod, ad in ads.items():
            if not _RE_COD.match(str(cod)):
                erros.append("$.ads.%s: código inválido (letras, números e hífen, sem _)" % cod)
            erros.extend(_erros_do_ad(cod, ad))
    return erros


def _trechos(lista):
    return [(str(t[0]), float(t[1]), float(t[2])) for t in lista]


def _normalizar(dados):
    ads = {}
    for cod, ad in dados["ads"].items():
        novo = {k: ad[k] for k in ("nome", "tema") if k in ad}
        for chave in CHAVES_DE_TRECHOS:
            if chave in ad:
                novo[chave] = _trechos(ad[chave])
        ads[cod] = novo
    return {"versao": 1, "brutos": dados["brutos"], "ignorar": list(dados.get("ignorar", [])), "ads": ads}


# --- o projeto -----------------------------------------------------------------------------

def resolver_base(arg=None):
    """A pasta do projeto: o argumento, ou o diretório atual. Sem variável de ambiente."""
    return (Path(arg).expanduser() if arg else Path.cwd()).resolve()


class Projeto(object):
    """Um projeto de take gravado já validado. Só leitura: quem grava cria a pasta que precisa."""

    def __init__(self, base, plano, estado=None):
        self.base = Path(base).resolve()
        self.plano = plano
        self.estado = estado
        self.memo = {}                # cache por projeto (nada de estado no módulo)
        self.accel_forcada = None     # a linha de comando pode sobrepor a aceleração do projeto

    # --- plano
    @property
    def ads(self):
        return self.plano["ads"]

    @property
    def ignorar(self):
        return set(self.plano["ignorar"])

    @property
    def accel(self):
        if self.accel_forcada is not None:
            return float(self.accel_forcada)
        arq = self.base / "projeto.json"
        if not arq.is_file():
            return float(ACEL_PADRAO)
        try:
            return float(_modelo.carregar(arq)["aceleracao"])
        except _modelo.ContratoInvalido as e:
            raise PlanoInvalido([str(e)], arq)

    @property
    def brutos(self):
        p = Path(self.plano["brutos"]).expanduser()
        return p if p.is_absolute() else self.base / p

    def glossario(self):
        return _glossario.carregar(self.estado)

    def leitor(self, backend=None, amb=None):
        """Leitor de ASR do projeto: cache em `cache_asr/` e glossário do aluno."""
        from gravado.nucleo import asr
        return asr.Leitor(self.cache_asr, glossario=self.glossario(), backend=backend, amb=amb)

    # --- brutos
    def takes_brutos(self):
        if not self.brutos.is_dir():
            raise InsumoInvalido("a pasta de brutos não existe: %s (campo `brutos` de %s)"
                                 % (self.brutos, ARQUIVO_PLANO))
        achados = [p for p in sorted(self.brutos.iterdir())
                   if p.is_file() and p.suffix.lower() in EXTENSOES_DE_BRUTO and p.stem not in self.ignorar]
        return achados

    def bruto(self, take):
        if self.brutos.is_dir():
            for p in sorted(self.brutos.iterdir()):
                if p.is_file() and p.stem == take and p.suffix.lower() in EXTENSOES_DE_BRUTO:
                    return p
        raise FileNotFoundError("não achei o bruto %s em %s" % (take, self.brutos))

    # --- pastas e arquivos do projeto
    def pasta(self, nome):
        return self.base / nome

    def garantir(self, nome):
        p = self.pasta(nome)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def wav(self, take):
        return self.pasta("wav") / (take + ".wav")

    def audio_mp3(self, take):
        return self.pasta("audio") / (take + ".mp3")

    def limpo(self, take):
        for ext in EXTENSOES_DE_LIMPO:
            cand = self.pasta("limpo") / (take + ext)
            if cand.is_file():
                return cand
        return self.pasta("limpo") / (take + ".mp3")

    def montado(self, nome):
        return self.pasta("montados") / (nome + ".mp4")

    def com_caixinha(self, nome):
        return self.pasta("com_caixinha") / (nome + "_caixinha.mp4")

    def legenda_ass(self, nome):
        return self.pasta("legendas") / (nome + ".ass")

    def legendado(self, nome):
        return self.pasta("legendado") / (nome + ".mp4")

    def fonte_da_peca(self, nome):
        """A peça que vai ser legendada: com caixinha, se existir; senão a montada."""
        c = self.com_caixinha(nome)
        return c if c.is_file() else self.montado(nome)

    @property
    def cache_asr(self):
        return self.pasta("cache_asr")

    @property
    def falas_json(self):
        return self.base / "falas_entregues.json"

    @property
    def plano_md(self):
        return self.base / "PLANO-CORTES.md"

    # --- anúncios e trechos
    def trechos_do_ad(self, cod, desconto=False):
        """[(take, início, fim)] do anúncio: corpo + CTA. Na versão com desconto o corpo é o
        `corpo_desconto` (se houver) e a cauda é a `cta_desconto`."""
        ad = self.ads[cod]
        if desconto:
            if "cta_desconto" not in ad:
                raise KeyError("o anúncio %s não tem cta_desconto" % cod)
            return list(ad.get("corpo_desconto", ad["corpo"])) + list(ad["cta_desconto"])
        return list(ad["corpo"]) + list(ad["cta_normal"])

    def nomes_das_pecas(self):
        nomes = []
        for cod, ad in self.ads.items():
            nomes.append("%s_normal" % cod)
            if "cta_desconto" in ad:
                nomes.append("%s_desconto" % cod)
        return nomes

    def versoes(self):
        """{nome da peça: (cod, desconto)} na ordem do plano."""
        return {n: (n.rsplit("_", 1)[0], n.endswith("_desconto")) for n in self.nomes_das_pecas()}

    def todos_os_trechos(self):
        """[(cod, chave, take, ini, fim)] de TODAS as chaves de TODOS os anúncios, sem repetir o
        mesmo trecho. Conferir só "os principais" e deixar os de CTA para depois é o que deixa o
        defeito passar."""
        vistos, saida = set(), []
        for cod, ad in self.ads.items():
            for chave in CHAVES_DE_TRECHOS:
                for take, ini, fim in ad.get(chave, []):
                    if (take, ini, fim) not in vistos:
                        vistos.add((take, ini, fim))
                        saida.append((cod, chave, take, ini, fim))
        return saida


# --- criar e carregar ----------------------------------------------------------------------

def plano_exemplo(brutos):
    return {"versao": 1, "brutos": str(brutos), "ignorar": [], "ads": {}}


def carregar(base, estado=None):
    base = resolver_base(base)
    arq = base / ARQUIVO_PLANO
    if not arq.is_file():
        raise PlanoInvalido(["não achei %s em %s: crie o projeto com "
                             "`python3 scripts/gravado/projeto.py criar --brutos PASTA_DOS_BRUTOS`"
                             % (ARQUIVO_PLANO, base)])
    try:
        dados = _status.ler_json(arq)
    except ValueError as e:
        raise PlanoInvalido([str(e)], arq)
    erros = validar_plano(dados)
    if erros:
        raise PlanoInvalido(erros, arq)
    return Projeto(base, _normalizar(dados), estado)


def criar(base, brutos, estado=None):
    """Cria as pastas e o plano de partida. Idempotente: nunca sobrescreve um plano que existe."""
    base = resolver_base(base)
    base.mkdir(parents=True, exist_ok=True)
    for pasta in PASTAS:
        (base / pasta).mkdir(exist_ok=True)
    arq = base / ARQUIVO_PLANO
    if not arq.exists():
        _status.escrever_json_atomico(arq, plano_exemplo(brutos))
    return carregar(base, estado)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Confere ou cria o projeto de take gravado.")
    ap.add_argument("acao", nargs="?", choices=("conferir", "criar"), default="conferir")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    ap.add_argument("--brutos", help="pasta dos brutos (só para criar)")
    a = ap.parse_args(argv)
    try:
        if a.acao == "criar":
            if not a.brutos:
                raise InsumoInvalido("criar precisa de --brutos PASTA")
            p = criar(a.projeto, a.brutos)
        else:
            p = carregar(a.projeto)
    except InsumoInvalido as e:
        print(str(e), file=sys.stderr)
        return 2
    print("  PROJETO  %s" % p.base)
    print("  PLANO    %s" % (p.base / ARQUIVO_PLANO))
    print("  BRUTOS   %s %s" % ("ok " if p.brutos.is_dir() else "AUSENTE", p.brutos))
    print("  ACEL     %s" % p.accel)
    print("  ADS      %d: %s" % (len(p.ads), ", ".join(p.ads) or "(vazio: preencha depois da leitura dos takes)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
