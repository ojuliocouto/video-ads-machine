"""W7.Z, item 3: o mix real com a voz ISOLADA da prova (piso de pausa de -36 a -55 dBFS) e uma trilha com dinâmica.

A automação antiga dava à cama o nível absoluto de 0,42 e a subida (cama sobre a voz sozinha) saía de +11 a +21 dB. A nova
fecha a conta pausa a pausa com o nível medido da voz e da trilha ali. O mutante (`cama_adaptativa=False`) é a automação
antiga: reproduz a reprovação do gate_mix da prova."""
import subprocess
from pathlib import Path

import pytest

from audio import loudness, mix_final
from cinema import musica
from gates import gate_mix
from tests.fixtures import sinteticos as SIN

DUR = 18.0
PAUSAS = ((3.0, 3.9), (7.0, 8.2), (11.0, 11.7), (14.0, 15.0))
PISOS_DB = (-38.0, -36.0, -50.0, -55.0)          # o piso da voz isolada em cada pausa (a prova: -38,8, -36,3, -45,7, -55,1)
FALA_DB = -18.0
BOA = loudness.Medicao(-14.0, -2.0, 6.0)


def _ffmpeg(args):
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-400:]


def voz_isolada(destino):
    """Fala (seno de 220 Hz a -18 dBFS) com silêncio exato nas pausas e, em cada uma, um piso de ronco de 100 Hz no nível
    da lista; fora das pausas o ronco fica a -60 dBFS (voz isolada: quase silêncio)."""
    ganho_fala = FALA_DB + 21.07
    corte = "".join(f",volume=enable='between(t,{a},{b})':volume=0" for a, b in PAUSAS)
    niveis = "".join(f"+between(t,{a},{b})*{10 ** ((p + 21.07) / 20):.6f}" for (a, b), p in zip(PAUSAS, PISOS_DB))
    base = 10 ** ((-60.0 + 21.07) / 20)
    _ffmpeg(["-f", "lavfi", "-i", f"sine=frequency=220:sample_rate=48000:duration={DUR},volume={ganho_fala}dB{corte}",
             "-f", "lavfi", "-i", f"sine=frequency=100:sample_rate=48000:duration={DUR},"
                                  f"volume='{base:.8f}{niveis}':eval=frame",
             "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:normalize=0", "-ac", "1",
             "-c:a", "pcm_s16le", str(destino)])
    return Path(destino)


@pytest.fixture(scope="module")
def material(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("adaptativo")
    return {"pasta": pasta, "voz": voz_isolada(pasta / "voz.wav"), "trilha": SIN.ruido_rosa(pasta / "trilha.wav", dur=6.0)}


def mixar(material, nome, **kw):
    saida = material["pasta"] / (nome + ".wav")
    ref = material["pasta"] / (nome + "_ref.wav")
    rel = mix_final.mixar(material["voz"], saida, trilha=material["trilha"], voz_ref=ref, **kw)
    return saida, ref, rel


def gate(material, saida, ref, rel):
    return gate_mix.avaliar(saida, ref, ducking=rel["ducking"], trilha=material["trilha"], transcritor=lambda p: [],
                            loudness_medido=BOA)


def test_a_cama_de_cada_pausa_fecha_a_conta_com_a_voz_isolada_e_o_gate_passa(material):
    saida, ref, rel = mixar(material, "adaptativo")
    r = gate(material, saida, ref, rel)
    assert r.ok, r.motivo
    m = r.detalhes["medido"]
    assert len(m["pausas"]) == 4 and m["pausas_ok"] == 4
    assert all(1.5 <= p["delta_db"] <= 8.0 for p in m["pausas"]), m["pausas"]


def test_o_relatorio_grava_a_cama_de_cada_pausa_dentro_do_teto(material):
    _, _, rel = mixar(material, "relatorio")
    camas = [p["cama"] for p in rel["ducking"]["pausas"]]
    assert len(camas) == 4 and all(musica.CAMA_FALA <= c <= musica.CAMA_PAUSA for c in camas)
    assert len(set(round(c, 3) for c in camas)) > 1             # pisos diferentes pedem camas diferentes
    assert rel["ducking"]["cama_pausa"] == musica.CAMA_PAUSA


def test_mutante_automacao_de_nivel_absoluto_reproduz_a_reprovacao_da_prova(material):
    saida, ref, rel = mixar(material, "absoluto", cama_adaptativa=False)
    assert all("cama" not in p for p in rel["ducking"]["pausas"])
    r = gate(material, saida, ref, rel)
    assert not r.ok and "cama_nas_pausas" in {f["regra"] for f in r.detalhes["falhas"]}
    assert max(p["delta_db"] for p in r.detalhes["medido"]["pausas"]) > 8.0


def test_peca_sem_pausa_real_deixa_a_cama_parada_mesmo_adaptativa(tmp_path):
    mudo = tmp_path / "mudo.wav"
    _ffmpeg(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "8", str(mudo)])
    rel = mix_final.mixar(mudo, tmp_path / "so_musica.wav", trilha=SIN.ruido_rosa(tmp_path / "t.wav", dur=6.0), pausas=[])
    assert rel["ducking"]["pausas"] == []
