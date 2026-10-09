"""Cria o projeto do aluno em ESTADO/projetos/<slug>: pastas, projeto.json e status.json.

Idempotente e sem sobrescrever:
- projeto.json já existe e o pedido combina com ele: nada muda, `criado=False`.
- projeto.json já existe e o pedido diverge (outro modo, look, trilha ou origem): ProjetoJaExiste;
  quem quer mudar edita o projeto.json à mão (o aluno é dono dele).
- projeto.json existe mas está quebrado: ContratoInvalido; o arquivo não é tocado.
- Tudo é validado ANTES de criar qualquer pasta: pedido inválido não deixa rastro.
Só escreve dentro de ESTADO/projetos/<slug>.
"""
from collections import namedtuple

from . import looks, modelo, pastas, status

Resultado = namedtuple("Resultado", "pastas projeto criado avisos")


class ProjetoJaExiste(Exception):
    """O projeto existe com configuração diferente da pedida; nada foi alterado."""


def _diferencas(existente, pedido):
    difs = []
    for campo in ("modo", "look", "trilha", "origem"):
        if campo in pedido and existente.get(campo) != pedido[campo]:
            difs.append("%s: no projeto está %r, o pedido traz %r" % (campo, existente.get(campo), pedido[campo]))
    return difs


def _avisos(projeto, estado):
    avisos = []
    look = projeto.get("look")
    if look and look not in looks.nomes(estado):
        avisos.append("o look %r ainda não está em looks.json: cadastre com projeto.looks.adicionar "
                      "antes de montar" % look)
    arq = projeto.get("trilha", {}).get("arquivo")
    if arq and not pastas.trilha(arq, estado).is_file():
        avisos.append("a trilha %r ainda não está em %s" % (arq, pastas.trilhas_dir(estado)))
    return avisos


def criar(slug, modo, look=None, trilha=None, sem_trilha=None, origem=None, estado=None, agora=None):
    """Cria (ou reconhece) o projeto `slug`. Devolve Resultado(pastas, projeto, criado, avisos).

    `trilha` é o nome de um arquivo em _local/trilhas/; `sem_trilha` é o motivo escrito de rodar
    sem trilha. Um dos dois é obrigatório (o contrato exige). `projeto` volta com os padrões
    aplicados (aceleração, formato, rótulo do CTA).
    """
    p = pastas.projeto(slug, estado)  # ValueError se o slug for ruim
    pedido = modelo.minimo(slug, modo, look=look, trilha=trilha, sem_trilha=sem_trilha, origem=origem)

    if p.projeto_json.exists():
        existente = modelo.carregar(p.projeto_json)
        difs = _diferencas(existente, pedido)
        if difs:
            raise ProjetoJaExiste("o projeto %r já existe com outra configuração (nada foi alterado; "
                                  "edite %s à mão se for isso mesmo):\n  %s"
                                  % (slug, p.projeto_json, "\n  ".join(difs)))
        return Resultado(p, existente, False, _avisos(existente, p.estado))

    pedido["criado_em"] = agora if agora is not None else status.instante()
    completo = modelo.normalizar(pedido)  # reprova antes de criar qualquer pasta
    p.criar()
    modelo.escrever(p.projeto_json, completo)
    status.registrar(p, "novo", "ok", agora=pedido["criado_em"])
    return Resultado(p, completo, True, _avisos(completo, p.estado))
