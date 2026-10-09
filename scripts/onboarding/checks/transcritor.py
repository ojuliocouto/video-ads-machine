"""Check: existe um transcritor que roda nesta máquina.

Não escolhe nada por conta própria: pergunta ao `audio.transcrever` (a mesma escolha que o
build faz) quais backends estão disponíveis, na ordem dele: parakeet (Apple Silicon),
faster-whisper (qualquer máquina) e Groq (nuvem, precisa de GROQ_API_KEY). O único
acréscimo é rodar o `parakeet-mlx --help`: um launcher órfão (venv apagado) aparece como
"disponível" e só estoura na hora de transcrever.
"""
import importlib
import sys

from ..doctor import FAIL, OK, WARN, Resultado

NOME = "transcritor"


def checar(amb):
    from audio import transcrever as T
    tamb = amb.para_transcritor()
    nomes = list(T.backends_disponiveis(tamb))
    quebrado = None
    if "parakeet" in nomes:
        parakeet = importlib.import_module("audio.backends.parakeet")
        exe = parakeet.achar_executavel(tamb)
        rc, saida = amb.executar([exe, "--help"], timeout=60)
        if rc != 0:
            quebrado = (saida or "").strip()[-160:] or "sem saída"
            nomes.remove("parakeet")
    if not nomes:
        if quebrado is not None:
            return Resultado(NOME, FAIL, "o parakeet-mlx está instalado mas não executa: "
                             + quebrado,
                             "reinstale com `%s -m pip install --force-reinstall parakeet-mlx` "
                             "(ou defina GROQ_API_KEY para usar a Groq)" % sys.executable)
        return Resultado(NOME, FAIL, "nenhum transcritor disponível nesta máquina",
                         T.mensagem_sem_transcritor(tamb))
    principal, reserva = nomes[0], nomes[1:]
    nota = " (nuvem, pago por uso)" if principal == "groq" else ""
    detalhe = "usa %s%s" % (principal, nota)
    if reserva:
        detalhe += "; reserva: " + ", ".join(reserva)
    if quebrado is not None:
        return Resultado(NOME, WARN, "o parakeet-mlx não executa (%s); %s" % (quebrado, detalhe),
                         "reinstale com `%s -m pip install --force-reinstall parakeet-mlx`"
                         % sys.executable)
    return Resultado(NOME, OK, detalhe)
