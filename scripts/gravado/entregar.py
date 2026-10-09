"""FASE 6: monta a pasta entrega/ do projeto, mas só se TODOS os gates passarem.

O pipeline de origem copiava `legendado/` para a pasta de entrega sem consultar gate nenhum: o defeito
passava até o fim e só o olho do diretor o pegava. Agora a entrega consulta os 11 gates, na ordem
do pipeline, mais a conferência `legenda_aprovada`, e não copia NADA se qualquer um sai com defeito (1)
ou não consegue medir (2). Defeito vale mais que insumo no código de saída: o que está errado na peça
aparece primeiro.

`legenda_aprovada` fecha a corrente da legenda (W5.D): o .ass tem a aprovação do diretor com o sha256
dele (`legendar.aprovar`), a queima registrou esse mesmo sha256 (`queimar_legenda.registrar_queima`) e o
arquivo de `legendado/` é o que saiu da queima. Quem editou o .ass depois do ok, ou trocou o arquivo
legendado, trava aqui. `tecnico` mede o arquivo que vai ser entregue (resolução, 48 kHz, loudness e true
peak): o 11 gates leem fala e imagem, e uma peça a -1,4 dBTP passaria por todos eles.

  Resultado.entregue   True só se os gates passaram e a cópia conferiu byte a byte (sha256)
  Resultado.codigo     0 entregue, 1 algum gate reprovou, 2 algum gate não mediu (ou sem peças)
  Resultado.gates      [(nome do gate, "ok" | "defeito" | "insumo", motivo)]

Entregue, fica `entrega/entrega.json`: o sha256 de cada peça e o veredito de cada gate. A pasta é
`entrega/` em minúsculas, a mesma do layout do projeto (`ENTREGA/` e `entrega/` eram a mesma pasta no
macOS e duas no Linux; unificada na W5.A).

`entregar(proj, gates=None, abrir=False, leitor=None)` é a função que a CLI do produto chama; a
lista de gates entra por parâmetro para o teste (e a CLI) poderem trocá-la. `gates_padrao` são os 11
gates; `gates_da_entrega` são eles mais a `legenda_aprovada`: cada item é `(nome, chamável sem argumento
que devolve (ok, motivo))`.

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
                     gate_retomada, gate_sincronia, gate_voz_distante, legendar, queimar_legenda)
from gravado import projeto as gp  # noqa: E402
from gravado.veredito import InsumoInvalido  # noqa: E402
from projeto import status as _status  # noqa: E402

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


def legenda_aprovada(proj):
    """(ok, motivo): para cada peça de `legendado/`, a legenda tem o ok do diretor (sha256 do .ass), a queima
    registrou esse .ass e o arquivo legendado é o que saiu da queima. Defeito (ok False), não insumo: a peça
    foi medida e não cumpre a corrente."""
    origem = proj.pasta("legendado")
    pecas = sorted(origem.glob("*.mp4")) if origem.is_dir() else []
    if not pecas:
        raise InsumoInvalido("nenhuma peça legendada em %s: monte, legende e queime antes" % origem)
    problemas, bons = [], []
    for mp4 in pecas:
        nome = mp4.stem
        s = legendar.situacao(proj, nome)
        if not s.vigente:
            problemas.append(s.motivo)
            continue
        ap = legendar.exigir_aprovada(proj, nome)
        reg_arq = queimar_legenda.caminho_queima(proj, nome)
        try:
            reg = _status.ler_json(reg_arq) if reg_arq.is_file() else None
        except ValueError:
            reg = None
        if not isinstance(reg, dict):
            problemas.append("%s: sem registro de queima (%s): queime a legenda aprovada com `vam gravado %s queimar %s`"
                             % (nome, reg_arq.name, proj.base.name, nome))
        elif reg.get("ass_sha256") != ap["ass"]["sha256"]:
            problemas.append("%s: a peça foi queimada de outro .ass, não do aprovado: queime de novo" % nome)
        elif reg.get("legendado_sha256") != legendar.sha256_arquivo(mp4):
            problemas.append("%s: o arquivo legendado/%s.mp4 não é o que saiu da queima do .ass aprovado: "
                             "queime de novo" % (nome, nome))
        else:
            bons.append(nome)
    if problemas:
        return False, "\n".join(problemas)
    return True, "%d peça(s) queimada(s) do .ass que o diretor aprovou (sha256 conferido)" % len(bons)


def tecnico_da_entrega(proj):
    """(ok, motivo): o técnico MEDIDO de cada peça de `legendado/`, o que o espectador recebe: 1080x1920, 48 kHz,
    -14 LUFS (+- 1,2) e true peak até -1,5 dBTP (`auditar.tecnico`). InsumoInvalido se não consegue medir."""
    origem = proj.pasta("legendado")
    pecas = sorted(origem.glob("*.mp4")) if origem.is_dir() else []
    if not pecas:
        raise InsumoInvalido("nenhuma peça legendada em %s: monte, legende e queime antes" % origem)
    problemas, linhas = [], []
    for mp4 in pecas:
        t = auditar.tecnico(mp4)
        resumo = "%s: %s, %s Hz, %.1fs, %.1f LUFS, pico %.1f dBTP" % (
            mp4.stem, t["resolucao"], t["sample_rate"], t["duracao"], t["lufs"], t["true_peak"])
        (linhas if t["ok"] else problemas).append(resumo if t["ok"] else "%s: %s" % (mp4.stem, t["motivo"]))
    if problemas:
        return False, "\n".join(problemas)
    return True, "\n".join(linhas)


def gates_da_entrega(proj, leitor):
    """Os 11 gates do gravado, a conferência da legenda aprovada e o técnico do arquivo entregue, na ordem em que
    a entrega consulta."""
    return gates_padrao(proj, leitor) + [("legenda_aprovada", lambda: legenda_aprovada(proj)),
                                         ("tecnico", lambda: tecnico_da_entrega(proj))]


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
        gates = gates_da_entrega(proj, leitor or proj.leitor())
    resultados = rodar_gates(gates)
    estados = {e for _, e, _ in resultados}
    if "defeito" in estados:
        return Resultado(False, 1, resultados, [])
    if "insumo" in estados:
        return Resultado(False, 2, resultados, [])
    destino = proj.garantir("entrega")
    copiados = []
    for p in pecas:
        alvo = destino / p.name
        shutil.copy2(str(p), str(alvo))
        if _sha256(p) != _sha256(alvo):
            raise InsumoInvalido("a cópia de %s não confere com a origem (sha256): entrega interrompida" % p.name)
        copiados.append(p.name)
    _status.escrever_json_atomico(destino / "entrega.json", {
        "versao": 1, "projeto": proj.base.name, "entregue_em": _status.instante(), "aceleracao": proj.accel,
        "pecas": [{"nome": n, "sha256": _sha256(destino / n), "bytes": (destino / n).stat().st_size}
                  for n in copiados],
        "gates": [{"nome": n, "estado": e, "motivo": m} for n, e, m in resultados]})
    if abrir:
        _abrir(destino)
    return Resultado(True, 0, resultados, copiados)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Entrega as peças legendadas se TODOS os gates passarem.")
    ap.add_argument("--abrir", action="store_true", help="abre a pasta entrega/ depois de copiar")
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
