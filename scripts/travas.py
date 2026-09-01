#!/usr/bin/env python3
"""Registro de TRAVAS: cada defeito real que ja aconteceu e o check que impede a volta.

Ordem do Julio (18/08/2026): "Va aprendendo com seus erros e travas. O processo precisa
ficar SEMPRE sendo auto otimizavel."

O problema de "aprender com o erro" e que anotacao depende de memoria. Aqui a lista e
EXECUTAVEL: cada linha diz o defeito que aconteceu de verdade, o que impede ele hoje, e
se esse impedimento e MECANICO (roda sozinho e reprova) ou ainda DEPENDE DE MIM. A coluna
que interessa e a ultima: tudo que estiver "manual" e uma trava esperando pra falhar de
novo.

    python3 travas.py            lista o registro e o placar
    python3 travas.py --rodar    executa os checks mecanicos e diz quais estao verdes
"""
import subprocess
import sys
from pathlib import Path

from caminhos import V2L  # noqa: E402  (era o proprio dir; agora e o _local, que guarda o estado)
from caminhos import V1  # noqa: E402

# (defeito que ACONTECEU, custo real, o que impede hoje, comando, mecanico?)
TRAVAS = [
    ("Insert usava arquivo diferente do que o doc marca",
     "AD13 reprovado, 4 assets trocados",
     "verificar_fidelidade.py compara com a legenda de letras do export",
     f"python3 {V2L}/verificar_fidelidade.py jh13", True),

    ("Lettering marcado no roteiro nao aparecia na tela",
     "diretor de arte deu 4,5",
     "gate de lettering ausente dentro do verificar_fidelidade",
     f"python3 {V2L}/verificar_fidelidade.py jh13", True),

    ("13s de tela sem nenhum texto (cta_start divergiu de cta_s)",
     "17% do anuncio mudo",
     "gate de tela vazia no gen_ad_v2, calculado antes do render",
     None, True),

    ("Texto em cima do rosto",
     "CTA na boca do apresentador",
     "gate-colisao-texto.py com heranca de rosto e teste de pele",
     None, True),

    ("Zoom cego decepava a primeira letra de cada linha",
     "3 inserts do AD13, reprovado duas vezes",
     "campo crop medido + conferir_recortes.py (folha de contato antes do build)",
     f"python3 {V2L}/conferir_recortes.py jh13", True),

    ("Recorte certo num quadro e errado no resto da janela",
     "4 defeitos que a folha de 1 quadro nao via",
     "conferir_recortes amostra 4 pontos da janela de cada bloco",
     None, True),

    ("Insert congelava o ultimo quadro (fonte acabava antes do bloco)",
     "4,67s somados no AD13, invisivel em quadro parado",
     "analise_inserts.py, aritmetica fonte x consumo, reprova antes do render",
     f"python3 {V2L}/analise_inserts.py jh13 {V2L}/prancha/jh13v2/prancha.json", True),

    ("Edicao 3x mais lenta que a referencia",
     "Jheni: 'poderia ser mais acelerado'",
     "medir_ritmo.py com fixture das 3 referencias",
     f"python3 {V2L}/test_medir_ritmo.py", True),

    ("Gate mais duro que a propria referencia",
     "o medidor de ritmo reprovava a ref1",
     "test_gate_APROVA_as_referencias, dentro do test_medir_ritmo",
     f"python3 {V2L}/test_medir_ritmo.py", True),

    ("Medidor cego no proprio material (deteccao de cena em ad escuro)",
     "reportou 33,9s sem corte onde havia 4 cortes; quase 'consertei' o que ja existia",
     "medir_do_plano(): o ritmo dos NOSSOS ads sai do plano, que e exato",
     f"python3 {V2L}/medir_ritmo.py --plano jh13v2 jh14v2 jh15v2 jh16v2", True),

    ("Efeito sonoro gerado mas INAUDIVEL (-40 dBFS, 26 dB abaixo da voz)",
     "mixagem rodava, log dizia '6 efeitos', delta de energia era 0,0 dB",
     "test_nivel_som.py: todo efeito tem que ficar entre -30 e -20 dBFS",
     "python3 /Users/ojuliocouto/video-ads-machine/test_nivel_som.py", True),

    ("Painel do split cortava o apresentador no NARIZ (boca fora do quadro)",
     "avatar de lipsync sem boca nos 4 splits do AD15",
     "test_enquadramento_split.py: a janela tem que conter o rosto DETECTADO inteiro",
     "python3 /Users/ojuliocouto/video-ads-machine/test_enquadramento_split.py", True),

    ("Patch de texto nao aplicava e passava silencioso",
     "2 ciclos rodando com codigo velho",
     "assert POR troca (alvo antes, resultado depois), nunca so 's != o'",
     None, False),

    ("Entreguei arquivo antes da auditoria, so com gate verde",
     "criativo com defeito grave chegou no Julio",
     "Fase 2.5: diretor dirige na prancha ANTES do render; entrega so com nota > 9",
     None, False),

    ("Prancha com overlay opaco mostrava texto sobre nada",
     "quase mandei o diretor dirigir em quadro falso",
     "alpha recuperado por dois passes (preto e branco) no prancha_direcao",
     None, True),

    ("Medi dimensao do arquivo em vez do CONTEUDO",
     "looks do HeyGen e insert dos robos",
     "medir_enquadramento.py --json, usado pelo motor",
     None, True),

    ("Fase pulada (build sem plano aprovado)",
     "leva inteira refeita",
     "fase_gate.py exige evidencia por fase e bloqueia o build",
     f"python3 {V2L}/fase_gate.py status jheni", True),
]


def listar():
    mec = sum(1 for t in TRAVAS if t[4])
    print(f"\nREGISTRO DE TRAVAS: {len(TRAVAS)} defeitos reais, "
          f"{mec} mecanizados, {len(TRAVAS) - mec} ainda dependendo de mim\n")
    for defeito, custo, impede, _cmd, mecanico in TRAVAS:
        marca = "[MECANICO]" if mecanico else "[MANUAL]  "
        print(f"{marca} {defeito}")
        print(f"           custou: {custo}")
        print(f"           impede: {impede}\n")
    manuais = [t[0] for t in TRAVAS if not t[4]]
    if manuais:
        print("AINDA MANUAL, ou seja esperando pra falhar de novo:")
        for m in manuais:
            print(f"  - {m}")
    print()


def rodar():
    cmds = [(t[0], t[3]) for t in TRAVAS if t[3]]
    print(f"\nrodando {len(cmds)} check(s) mecanico(s)...\n")
    ruim = 0
    for nome, cmd in cmds:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        ok = r.returncode == 0
        print(f"  {'VERDE ' if ok else 'VERMELHO'}  {nome[:64]}")
        if not ok:
            ruim += 1
            for ln in (r.stdout + r.stderr).strip().splitlines()[-3:]:
                print(f"           {ln[:110]}")
    print(f"\n{len(cmds) - ruim} verde(s), {ruim} vermelho(s)\n")
    return 1 if ruim else 0


if __name__ == "__main__":
    if "--rodar" in sys.argv:
        sys.exit(rodar())
    listar()
