"""Mecanica pura de paralelismo pros gates de saida do produzir_ad.py.

MOTIVO (31/08/2026): os gates de saida (gate-ad.py, medir_ritmo.py,
gate-colisao-texto.py, gate-contraste-legenda.py) rodavam em serie dentro de
`gate(ad, fmt)` e juntos levavam uns 4,5 minutos, dentro de um build de 20.
Sao processos independentes: cada um le o MESMO mp4 final ja pronto (o build
ja terminou antes de `gate()` comecar) e nenhum depende do resultado de
outro. Por isso podem rodar ao mesmo tempo em vez de um esperar o outro.

Este modulo so tem a mecanica (rodar comandos em paralelo e devolver os
resultados por nome). A decisao de QUAIS comandos montar, e o que fazer com
cada resultado (mexer em `ok`/`motivos`, imprimir stdout na ordem de sempre),
continua em `produzir_ad.py`, aplicada em ordem apos todos terminarem.
"""
import concurrent.futures
import subprocess


def rodar_em_paralelo(tarefas, max_workers=4):
    """Roda uma lista de (nome, cmd) em paralelo e devolve {nome: CompletedProcess}.

    `cmd` e uma lista pronta pra `subprocess.run` (mesmo formato de sempre).
    Cada comando roda com capture_output=True e text=True, exatamente como
    rodava em serie antes. A ordem de DISPARO nao importa (e paralela); a
    ordem de LEITURA dos resultados fica por conta de quem chama.
    """
    resultados = {}
    if not tarefas:
        return resultados
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futuros = {
            ex.submit(subprocess.run, cmd, capture_output=True, text=True): nome
            for nome, cmd in tarefas
        }
        for fut in concurrent.futures.as_completed(futuros):
            nome = futuros[fut]
            resultados[nome] = fut.result()
    return resultados
