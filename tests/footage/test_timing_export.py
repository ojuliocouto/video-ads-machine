"""Exportação do tempo (W2.B): `<saida>_ritmo.json` e `timing.json`, byte a byte como o original.

Os textos golden vieram do `produzir_roteiro.py` ORIGINAL (commit 2ebd1cc): o ritmo de dois
cenários sintéticos e o `timing.json` da fixture de paridade. O `gen_ad_v2` lê o `_ritmo.json` (o
"relógio da footage") e o mixador de SFX lê o plano: mudar uma vírgula aqui desalinha os dois.
"""
import json

import pytest

from footage import timing_export as TE

# (plano, total, texto do _ritmo.json do original)
GOLDEN_RITMO = [{'nome': 'fixture_like',
  'plano': [{'bloco': 0,
             'crop': None,
             'de': 1,
             'e': 4.82,
             'fonte_off': 0.0,
             'layout': 'split',
             's': 0.62,
             'sub': 0,
             'tipo': 'insert'},
            {'bloco': 0,
             'crop': None,
             'de': 1,
             'e': 5.78,
             'layout': 'cheio',
             's': 4.82,
             'sub': 0,
             'tipo': 'insert'},
            {'base': 1.0,
             'bloco': 1,
             'crop': None,
             'de': 2,
             'e': 8.26,
             'punch': False,
             's': 5.78,
             'sub': 0,
             'tipo': 'orig'},
            {'base': 1.06,
             'bloco': 1,
             'crop': None,
             'de': 2,
             'e': 10.74,
             'punch': True,
             's': 8.26,
             'sub': 1,
             'tipo': 'orig'},
            {'bloco': 2, 'crop': None, 'de': 1, 'e': 12.94, 's': 10.74, 'sub': 0, 'tipo': 'orig'},
            {'bloco': 3, 'crop': None, 'de': 1, 'e': 17.12, 's': 12.94, 'sub': 0, 'tipo': 'insert'},
            {'bloco': 4, 'crop': None, 'de': 1, 'e': 19.466, 's': 17.12, 'sub': 0, 'tipo': 'orig'}],
  'total': 19.466,
  'texto': '{"segs": [{"bloco": 0, "tipo": "insert", "s": 0.62, "e": 4.82, "crop": null, "sub": 0, '
           '"de": 1, "layout": "split", "fonte_off": 0.0}, {"bloco": 0, "tipo": "insert", "s": '
           '4.82, "e": 5.78, "crop": null, "sub": 0, "de": 1, "layout": "cheio"}, {"bloco": 1, '
           '"tipo": "orig", "s": 5.78, "e": 8.26, "crop": null, "sub": 0, "de": 2, "base": 1.0, '
           '"punch": false}, {"bloco": 1, "tipo": "orig", "s": 8.26, "e": 10.74, "crop": null, '
           '"sub": 1, "de": 2, "base": 1.06, "punch": true}, {"bloco": 2, "tipo": "orig", "s": '
           '10.74, "e": 12.94, "crop": null, "sub": 0, "de": 1}, {"bloco": 3, "tipo": "insert", '
           '"s": 12.94, "e": 17.12, "crop": null, "sub": 0, "de": 1}, {"bloco": 4, "tipo": "orig", '
           '"s": 17.12, "e": 19.466, "crop": null, "sub": 0, "de": 1}], "total": 19.466}'},
 {'nome': 'insert_longo',
  'plano': [{'bloco': 0, 'crop': None, 'de': 1, 'e': 1.9, 's': 0.5, 'sub': 0, 'tipo': 'orig'},
            {'bloco': 1,
             'crop': '800:600:10:10',
             'de': 4,
             'e': 4.9,
             'fonte_off': 0.0,
             'layout': 'split',
             's': 1.9,
             'sub': 0,
             'tipo': 'insert'},
            {'base': 1.0,
             'bloco': 1,
             'crop': None,
             'de': 4,
             'e': 8.95,
             's': 4.9,
             'sub': 1,
             'tipo': 'orig'},
            {'bloco': 1,
             'crop': '800:600:10:10',
             'de': 4,
             'e': 11.95,
             'fonte_off': 0.0,
             'layout': 'cheio',
             's': 8.95,
             'sub': 2,
             'tipo': 'insert'},
            {'base': 1.06,
             'bloco': 1,
             'crop': None,
             'de': 4,
             'e': 16.0,
             's': 11.95,
             'sub': 3,
             'tipo': 'orig'},
            {'bloco': 2, 'crop': None, 'de': 1, 'e': 18.0, 's': 16.0, 'sub': 0, 'tipo': 'orig'},
            {'bloco': 3, 'crop': None, 'de': 1, 'e': 19.17, 's': 18.0, 'sub': 0, 'tipo': 'orig'}],
  'total': 19.17,
  'texto': '{"segs": [{"bloco": 0, "tipo": "orig", "s": 0.5, "e": 1.9, "crop": null, "sub": 0, '
           '"de": 1}, {"bloco": 1, "tipo": "insert", "s": 1.9, "e": 4.9, "crop": "800:600:10:10", '
           '"sub": 0, "de": 4, "layout": "split", "fonte_off": 0.0}, {"bloco": 1, "tipo": "orig", '
           '"s": 4.9, "e": 8.95, "crop": null, "sub": 1, "de": 4, "base": 1.0}, {"bloco": 1, '
           '"tipo": "insert", "s": 8.95, "e": 11.95, "crop": "800:600:10:10", "sub": 2, "de": 4, '
           '"layout": "cheio", "fonte_off": 0.0}, {"bloco": 1, "tipo": "orig", "s": 11.95, "e": '
           '16.0, "crop": null, "sub": 3, "de": 4, "base": 1.06}, {"bloco": 2, "tipo": "orig", '
           '"s": 16.0, "e": 18.0, "crop": null, "sub": 0, "de": 1}, {"bloco": 3, "tipo": "orig", '
           '"s": 18.0, "e": 19.17, "crop": null, "sub": 0, "de": 1}], "total": 19.17}'},
 {'nome': 'deitico',
  'plano': [{'bloco': 0, 'crop': None, 'de': 1, 'e': 4.15, 's': 0.0, 'sub': 0, 'tipo': 'insert'},
            {'base': 1.0,
             'bloco': 1,
             'crop': None,
             'de': 2,
             'e': 6.925,
             'punch': False,
             's': 4.15,
             'sub': 0,
             'tipo': 'orig'},
            {'base': 1.06,
             'bloco': 1,
             'crop': None,
             'de': 2,
             'e': 9.7,
             'punch': True,
             's': 6.925,
             'sub': 1,
             'tipo': 'orig'},
            {'bloco': 2, 'crop': None, 'de': 1, 'e': 14.215, 's': 9.7, 'sub': 0, 'tipo': 'orig'}],
  'total': 14.215,
  'texto': '{"segs": [{"bloco": 0, "tipo": "insert", "s": 0.0, "e": 4.15, "crop": null, "sub": 0, '
           '"de": 1}, {"bloco": 1, "tipo": "orig", "s": 4.15, "e": 6.925, "crop": null, "sub": 0, '
           '"de": 2, "base": 1.0, "punch": false}, {"bloco": 1, "tipo": "orig", "s": 6.925, "e": '
           '9.7, "crop": null, "sub": 1, "de": 2, "base": 1.06, "punch": true}, {"bloco": 2, '
           '"tipo": "orig", "s": 9.7, "e": 14.215, "crop": null, "sub": 0, "de": 1}], "total": '
           '14.215}'}]

TIMING_FIXTURE = ('{"a0": 0.62, "total": 17.68, "xf": 0.08, "avatar": "/D/inputs/avatar.mp4", "inserts": '
                  '[{"s": 0.62, "e": 4.82}, {"s": 4.82, "e": 5.6}, {"s": 10.88, "e": 15.52}], "letterings": []}')
BLOCOS = [{"type": t} for t in ("insert", "insert", "orig", "lettering", "insert", "lettering_logo")]
SPANS = [(0.62, 4.82), (4.82, 5.6), (5.6, 9.6), (9.6, 10.88), (10.88, 15.52), (15.52, 17.68)]


@pytest.mark.parametrize("caso", GOLDEN_RITMO, ids=lambda c: c["nome"])
def test_ritmo_json_bate_byte_a_byte_com_o_original(caso, tmp_path):
    destino = tmp_path / "x_ritmo.json"
    TE.escrever_ritmo(str(destino), caso["plano"], caso["total"])
    assert destino.read_text(encoding="utf-8") == caso["texto"]


def test_timing_json_bate_byte_a_byte_com_o_original(tmp_path):
    destino = tmp_path / "timing.json"
    TE.escrever_timing(str(destino), a0=0.62, total=17.68, xf=0.08, avatar="/D/inputs/avatar.mp4",
                       spans=SPANS, blocks=BLOCOS)
    assert destino.read_text(encoding="utf-8") == TIMING_FIXTURE


def test_so_os_blocos_de_insert_entram_nos_inserts():
    dados = TE.dados_do_timing(0.0, 5.0, 0.08, "/a.mp4", SPANS, BLOCOS)
    assert [i["s"] for i in dados["inserts"]] == [0.62, 4.82, 10.88]


def test_letterings_ficam_vazios_porque_o_lettering_agora_e_do_overlay():
    dados = TE.dados_do_timing(0.0, 5.0, 0.08, "/a.mp4", SPANS, BLOCOS)
    assert dados["letterings"] == []


def test_ordem_das_chaves_do_timing_e_a_do_original():
    assert list(json.loads(TIMING_FIXTURE)) == list(TE.dados_do_timing(0, 1, 0.08, "a", [], []))
