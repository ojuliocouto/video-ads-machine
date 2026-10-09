"""FASE 6: monta a pasta ENTREGA/ do projeto, mas só se TODOS os gates passarem.

O pipeline de origem copiava `legendado/` para `ENTREGA/` sem consultar gate nenhum: o defeito
passava até o fim e só o olho do diretor o pegava. Agora a entrega consulta os 11 gates, na ordem
do pipeline, e não copia NADA se qualquer um sai com defeito (1) ou não consegue medir (2). Defeito
vale mais que insumo no código de saída: o que está errado na peça aparece primeiro.

  Resultado.entregue   True só se os gates passaram e a cópia conferiu byte a byte (sha256)
  Resultado.codigo     0 entregue, 1 algum gate reprovou, 2 algum gate não mediu (ou sem peças)
  Resultado.gates      [(nome do gate, "ok" | "defeito" | "insumo", motivo)]

`entregar(proj, gates=None, abrir=False, leitor=None)` é a função que a CLI do produto chama; a
lista de gates entra por parâmetro para o teste (e a CLI) poderem trocá-la. `gates_padrao` é a
lista real: cada item é `(nome, chamável sem argumento que devolve (ok, motivo))`.

    python3 scripts/gravado/entregar.py [--abrir] [--projeto DIR]
"""
import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):            # rodado como script: tira scripts/gravado do caminho
    _AQUI = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _AQUI]
    sys.path.insert(0, str(_AQUI.parent))

from gravado import (auditar, gate_ar_morto, gate_emendas, gate_envelope, gate_fala,  # noqa: E402
                     gate_legenda, gate_offscript, gate_redundancia, gate_repeticao,
                     gate_retomada, gate_sincronia, gate_voz_distante)
from gravado import projeto as gp  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402

# A ordem do pipeline: fase 1 (áudio), fase 2 (quem fala), fase 4 (a peça montada), fase 5 (legenda).
ORDEM = (gate_envelope, gate_fala, gate_voz_distante, gate_retomada, gate_emendas, gate_redundancia,
         gate_ar_morto, gate_legenda, gate_sincronia, gate_repeticao, gate_offscript)
USAM_FALAS = (gate_repeticao, gate_offscript)


class Resultado(object):
    def __init__(self, entregue, codigo, gates, copiados, aviso=""):
        self.entregue = entregue
        self.codigo = codigo
        self.gates = list(gates)
        self.copiados = list(copiados)
        self.aviso = aviso

    def resumo(self):
        linhas = [self.aviso] if self.aviso else []
        for nome, estado, motivo in self.gates:
            linhas.append("  %-18s %-8s %s" % (nome, estado, motivo.replace("\n", "\n" + " " * 30)))
        linhas.append("ENTREGUE: %d peça(s)" % len(self.copiados) if self.entregue
                      else "NADA FOI COPIADO (saída %d)" % self.codigo)
        return "\n".join(linhas)


def gates_padrao(proj, leitor):
    """Os 11 gates como [(nome, chamável)]. Os de texto leem as falas da peça LEGENDADA, relidas
    na hora: a fala entregue é a do arquivo entregue."""
    def com_falas(gate):
        def rodar():
            if "falas" not in proj.memo:
                auditar.gerar_falas(proj, leitor, pasta="legendado")
                proj.memo["falas"] = True
            return gate.verificar_projeto(proj, leitor)
        return rodar

    def direto(gate):
        return lambda: gate.verificar_projeto(proj, leitor)

    return [(g.NOME, com_falas(g) if g in USAM_FALAS else direto(g)) for g in ORDEM]


def rodar_gates(gates):
    """[(nome, estado, motivo)]; um gate que levanta InsumoInvalido é "insumo", não "defeito"."""
    saida = []
    for nome, rodar in gates:
        try:
            ok, motivo = rodar()
            saida.append((nome, "ok" if ok else "defeito", motivo))
        except InsumoInvalido as e:
            saida.append((nome, "insumo", str(e)))
    return saida


def _sha256(caminho):
    h = hashlib.sha256()
    with open(str(caminho), "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def _abrir(pasta):
    ferramenta = {"darwin": "open", "linux": "xdg-open"}.get(sys.platform)
    if ferramenta and shutil.which(ferramenta):
        subprocess.run([ferramenta, str(pasta)], capture_output=True)


def entregar(proj, gates=None, abrir=False, leitor=None):
    origem = proj.pasta("legendado")
    pecas = sorted(origem.glob("*.mp4")) if origem.is_dir() else []
    if not pecas:
        return Resultado(False, 2, [], [], "nenhuma peça legendada em %s: monte, legende e queime antes" % origem)
    if gates is None:
        gates = gates_padrao(proj, leitor or proj.leitor())
    resultados = rodar_gates(gates)
    estados = {e for _, e, _ in resultados}
    if "defeito" in estados:
        return Resultado(False, 1, resultados, [])
    if "insumo" in estados:
        return Resultado(False, 2, resultados, [])
    destino = proj.garantir("ENTREGA")
    copiados = []
    for p in pecas:
        alvo = destino / p.name
        shutil.copy2(str(p), str(alvo))
        if _sha256(p) != _sha256(alvo):
            raise InsumoInvalido("a cópia de %s não confere com a origem (sha256): entrega interrompida" % p.name)
        copiados.append(p.name)
    if abrir:
        _abrir(destino)
    return Resultado(True, 0, resultados, copiados)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Entrega as peças legendadas se TODOS os gates passarem.")
    ap.add_argument("--abrir", action="store_true", help="abre a pasta ENTREGA depois de copiar")
    ap.add_argument("--projeto", help="pasta do projeto (padrão: o diretório atual)")
    a = ap.parse_args(argv)
    try:
        r = entregar(gp.carregar(a.projeto), abrir=a.abrir)
    except InsumoInvalido as e:
        print(str(e), file=sys.stderr)
        return 2
    print(r.resumo())
    return r.codigo


if __name__ == "__main__":
    sys.exit(main())
