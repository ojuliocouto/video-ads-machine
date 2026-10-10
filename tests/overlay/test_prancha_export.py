"""overlay.prancha_export: a linha do tempo em dados para o diretor de arte (prancha.json) e as
janelas de split de verdade (janelas_split.json).

Tudo em tempo de ÁUDIO (1x): o arquivo entregue roda ACCEL mais rápido, e quem lê a prancha
converte na hora de rotular. A fala vai junto de cada bloco porque quem reconstrói o plano de
ritmo a partir da prancha (som, medidor) precisa do mesmo critério de deixis que os motores
usaram, senão o plano deles diverge do renderizado.

O `janelas_split.json` existe porque o plano de ritmo cru marca `split` em TODA fatia de insert,
mas a footage só honra isso quando o config do insert tem `split: true`. O gate de colisão lia o
plano cru e acusava 14 colisões em trechos que a tela mostra como insert em tela cheia.
"""
import json

from overlay import prancha_export as P


def args():
    return dict(
        ad="ad99v2", look="look_a", total=18.7, hook_dur=2.2,
        cfg={"hook": {"eyebrow": "MEU CLAUDE", "l1": "virou", "accent": "PRO", "style": "punch"},
             "cta_label": "ver mais"},
        cta_s=14.0, logo_s=13.1,
        blocks=[{"type": "insert", "instr": "demo a", "narr": "olha isso"},
                {"type": "orig", "instr": "apresentador"}],
        spans=[(0.0, 6.123), (6.123, 18.0)],
        brolls=[{"src": "broll01.mp4", "s": 0.0, "d": 6.123, "label": "demo a"}],
        letts=[{"id": "lettA", "lead": "sabe", "key": "O MELHOR", "start": 7.1, "dur": 1.6, "split": True,
                "baixo": 0, "linhas": [{"key": "x", "delay": 0.0}]},
               {"id": "lettB", "lead": "", "key": "K", "start": 9, "dur": 2, "pilha": None}],
        groups=[{"start": 2.3333, "end": 3.9999, "words": []}],
        vao=(2.0456, 14.0))


def test_a_prancha_tem_a_forma_do_original():
    p = P.montar_prancha(**args())
    assert p == {
        "ad": "ad99v2", "look": "look_a", "total": 18.7, "accel": 1.35,
        "hook": {"fim": 2.2, "texto": {"eyebrow": "MEU CLAUDE", "l1": "virou", "accent": "PRO", "style": "punch"}},
        "cta": {"inicio": 14.0, "logo": 13.1, "label": "ver mais"},
        "blocos": [
            {"i": 0, "tipo": "insert", "instr": "demo a", "texto": "olha isso", "s": 0.0, "e": 6.12, "dur": 6.12},
            {"i": 1, "tipo": "orig", "instr": "apresentador", "texto": "", "s": 6.12, "e": 18.0, "dur": 11.88}],
        "inserts": [{"src": "broll01.mp4", "s": 0.0, "d": 6.12, "label": "demo a"}],
        "letterings": [
            {"id": "lettA", "lead": "sabe", "key": "O MELHOR", "s": 7.1, "d": 1.6, "split": True, "baixo": False,
             "pilha": True, "linhas": [{"key": "x", "delay": 0.0}]},
            {"id": "lettB", "lead": "", "key": "K", "s": 9.0, "d": 2.0, "split": False, "baixo": False,
             "pilha": False, "linhas": []}],
        "legendas": [{"s": 2.33, "e": 4.0}],
        "vao_sem_texto": {"maior": 2.05, "em": 14.0}}


def test_accel_da_prancha_e_o_da_entrega():
    assert P.ACCEL == 1.35


def test_hook_ausente_e_cta_sem_rotulo():
    a = args()
    a["cfg"] = {}
    p = P.montar_prancha(**a)
    assert p["hook"] == {"fim": 2.2, "texto": {}}
    assert p["cta"]["label"] == ""


def test_hook_none_tambem_vira_vazio():
    a = args()
    a["cfg"] = {"hook": None}
    assert P.montar_prancha(**a)["hook"]["texto"] == {}


def test_o_texto_do_hook_vai_cru_sem_tirar_emoji():
    a = args()
    a["cfg"] = {"hook": {"eyebrow": "\U0001F680 oi"}}
    assert P.montar_prancha(**a)["hook"]["texto"] == {"eyebrow": "\U0001F680 oi"}


def test_gravar_escreve_prancha_e_janelas_com_indent_2_e_acento(tmp_path):
    p = P.montar_prancha(**args())
    P.gravar(tmp_path, p, [(2.1, 6.14), (10.0, 12.0)])
    texto = (tmp_path / "prancha.json").read_text(encoding="utf-8")
    assert texto == json.dumps(p, ensure_ascii=False, indent=2)
    janelas = (tmp_path / "janelas_split.json").read_text(encoding="utf-8")
    assert janelas == json.dumps({"segs": [{"s": 2.1, "e": 6.14, "layout": "split"},
                                           {"s": 10.0, "e": 12.0, "layout": "split"}]},
                                 ensure_ascii=False, indent=2)


def test_sem_janelas_de_split_o_arquivo_existe_com_lista_vazia(tmp_path):
    P.gravar(tmp_path, P.montar_prancha(**args()), [])
    assert json.loads((tmp_path / "janelas_split.json").read_text(encoding="utf-8")) == {"segs": []}
