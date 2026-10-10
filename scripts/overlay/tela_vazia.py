"""O gate barato de tela vazia, antes do render.

O gate final mede isto no MOV com alpha e reprovou o build de 17/08 com 13 s de tela vazia, mas custa
13 minutos de render para falar. Aqui a mesma conta sai de graça: a união das janelas de texto (hook,
legenda, lettering, CTA) e o maior buraco. Causa raiz que motivou o gate: cortar a legenda num tempo
e subir o CTA em outro.

Duas travas, nesta ordem:
  - a janela do CTA suprime a legenda do corpo: se for longa, o anúncio roda mudo em feed silencioso
    sem o gate de tela vazia perceber (para o alpha, CTA é texto). Quase sempre a causa é um insert com
    `dur_max` no MEIO do roteiro puxando o `cta_start` para trás;
  - o maior vão sem NENHUM texto. A causa quase sempre é o corte da legenda (`cta_start`)
    desencontrado da subida do CTA (`cta_s`), ou um lettering que não encaixou.
"""
import sys

from overlay.prancha_export import ACCEL

MAX_JANELA_CTA = 12.0   # segundos de áudio (cerca de 8,9 s de tela), no relógio do overlay ANTIGO (ver checar)
MAX_VAO = 3.3           # segundos de áudio; o anúncio é acelerado depois (cerca de 2,4 s de tela)


def maior_vao(janelas, total):
    """(tamanho, onde começa) do maior buraco na união das janelas até `total`. Empate fica com o
    primeiro."""
    _fim, _pior, _quando = 0.0, 0.0, 0.0
    for a, b in sorted(janelas):
        if a - _fim > _pior:
            _pior, _quando = a - _fim, _fim
        _fim = max(_fim, b)
    if total - _fim > _pior:
        _pior, _quando = total - _fim, _fim
    return _pior, _quando


def checar(hook_dur, groups, lett_windows, cta_s, total, fim_janela_cta=None):
    """Devolve (maior vão, onde) ou para o motor com a causa provável.

    `fim_janela_cta` (W3.X M2): onde a janela do CTA acaba NO RELÓGIO EM QUE O TETO FOI CALIBRADO. O MAX_JANELA_CTA
    nasceu no overlay antigo, cujo total era o fim do ÁUDIO mais a folga de cauda (TAIL_PAD); com a timeline o total é
    o fim da fala, e a mesma janela mede menos (no fixture, 3,13 s viraram 2,16 s): o teto ficava mais frouxo sem
    ninguém decidir. O overlay com timeline passa aqui o total do caminho antigo e a conta é a de antes (3,13 s no
    fixture). Sem ele, o próprio `total`. O vão sem texto continua medido sobre o `total`, que é o que a tela mostra."""
    _janelas = [(0.0, float(hook_dur))]
    _janelas += [(float(g["start"]), float(g["end"])) for g in groups]
    _janelas += [(float(a), float(b)) for a, b in lett_windows]
    _janelas += [(float(cta_s), float(total))]
    _pior, _quando = maior_vao(_janelas, total)

    total_cta = float(total if fim_janela_cta is None else fim_janela_cta)
    _janela_cta = total_cta - cta_s
    print(f"   [cta] janela do CTA: {_janela_cta:.2f}s de audio "
          f"({_janela_cta / ACCEL:.2f}s de tela, teto {MAX_JANELA_CTA}s)", flush=True)
    if _janela_cta > MAX_JANELA_CTA:
        sys.exit(
            f"JANELA DE CTA LONGA DEMAIS: {_janela_cta:.2f}s de audio a partir de "
            f"{cta_s:.2f}s, num total de {total_cta:.2f}s. A legenda do corpo e cortada "
            f"nessa janela, entao {100 * _janela_cta / total_cta:.0f}% do anuncio rodaria sem "
            f"legenda. Quase sempre a causa e um insert com dur_max no MEIO do roteiro "
            f"puxando o cta_start pra tras.")

    print(f"   [tela] maior vao sem texto: {_pior:.2f}s de audio em {_quando:.2f}s "
          f"(teto {MAX_VAO}s)", flush=True)
    if _pior > MAX_VAO:
        sys.exit(
            f"TELA VAZIA: {_pior:.2f}s sem nenhum texto a partir de {_quando:.2f}s "
            f"(audio). Quase sempre e o corte da legenda (cta_start) desencontrado da "
            f"subida do CTA (cta_s), ou um lettering que nao encaixou. Conferir os dois "
            f"antes de renderizar.")
    return _pior, _quando
