"""W5.X: o gate de contraste pela CLI, sobre vídeo, com o invariante de legibilidade de todo texto na tela.

Os vídeos têm o quadro inteiro (1080x1920), como o entregue: o texto mora numa faixa e o resto é a imagem. Cada teste
reprova o gate antigo pela causa que ele tinha de não ver o defeito (o docstring de cada um diz qual). O último bloco
roda no render REAL da W5.A, quando a mídia local existe.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from tests.fixtures import texto_tela as T

RAIZ = Path(__file__).resolve().parents[2]
GATE = RAIZ / "scripts" / "gates" / "gate-contraste-legenda.py"
ALT, LARG = 360, 1080
QUADRO_ALT = 1920
FAIXA_Y = {"legenda": 1180, "gancho": 820}
ESCURO = 22
MEIO = 110


def legenda(ov, texto="sem precisar pagar", alfa=1.0, cor=(245, 239, 230), y=180, contorno=3):
    return T.texto(ov, texto, (540, y), corpo=80, cor=cor, alfa=alfa, contorno=contorno, sombra=0.40)


def invertida(ov, texto="disponibilizado", alfa=1.0, y=180):
    return T.texto(ov, texto, (540, y), corpo=80, cor=(18, 20, 26), alfa=alfa, contorno=3,
                   cor_contorno=(255, 255, 255), alfa_contorno=0.90, sombra=0.55, cor_sombra=(255, 255, 255))


# =========================================================== o gate pela CLI, sobre vídeo

FPS = 10


def _inteiro(ov, img, faixa):
    """A faixa de 360 px dentro do quadro inteiro: o resto é imagem escura sem texto."""
    y0 = FAIXA_Y[faixa]
    big_ov = np.zeros((QUADRO_ALT, LARG, 4), dtype=np.uint8)
    big_img = T.fundo(QUADRO_ALT, LARG, ESCURO)
    big_ov[y0:y0 + ALT] = ov
    big_img[y0:y0 + ALT] = img
    return big_ov, big_img


def _quadros(fases):
    """`fases`: [(duração em s, overlay RGBA, imagem RGB[, faixa])] -> (overlays, compostos), no quadro inteiro."""
    ovs, comps = [], []
    for fase in fases:
        dur, ov, img = fase[:3]
        ov, img = _inteiro(ov, img, fase[3] if len(fase) > 3 else "legenda")
        comp = T.compor(img, ov)
        for _ in range(int(round(dur * FPS))):
            ovs.append(ov)
            comps.append(comp)
    return ovs, comps


def _rodar_gate(tmp_path, fases, extra=()):
    ovs, comps = _quadros(fases)
    v = T.gravar_video(comps, tmp_path / "final.mp4", FPS)
    o = T.gravar_overlay(ovs, tmp_path / "overlay.mov", FPS)
    r = subprocess.run([sys.executable, str(GATE), str(v), "--overlay", str(o), "--accel", "1.0", "--a0", "0.0"]
                       + list(extra), capture_output=True, text=True, cwd=str(RAIZ))
    return r


def _legivel():
    return legenda(T.vazio(ALT, LARG)), T.fundo(ALT, LARG, ESCURO)


class TestGateCli:
    def test_trecho_ilegivel_reprova_mesmo_com_a_mediana_boa(self, tmp_path):
        """Causa 3: aprovação pela mediana. 3 s de legenda boa e 1 s da camada apagada sobre meio-tom: o gate
        antigo dava AVISO e PASSA (20% das faixas, mediana alta)."""
        ruim = legenda(T.vazio(ALT, LARG), alfa=0.70)
        r = _rodar_gate(tmp_path, [(3.0,) + _legivel(), (1.0, ruim, T.fundo(ALT, LARG, MEIO))])
        assert r.returncode == 1, r.stdout + r.stderr

    def test_gancho_sob_scrim_e_medido(self, tmp_path):
        """Causa 2 no vídeo: o gancho sob scrim de largura toda era pulado e o resto passava."""
        ov = T.scrim_radial(ALT, LARG, (540, 180), (700, 260), 0.55)
        ov = T.texto(ov, "virou um web designer", (540, 180), fonte=T.FONTE_FINA, corpo=72, cor=(255, 255, 255))
        r = _rodar_gate(tmp_path, [(1.5, ov, T.pagina(ALT, LARG), "gancho"), (2.0,) + _legivel()])
        assert r.returncode == 1, r.stdout + r.stderr

    def test_tudo_legivel_passa(self, tmp_path):
        r = _rodar_gate(tmp_path, [(2.0,) + _legivel(),
                                   (1.0, invertida(T.vazio(ALT, LARG)), T.fundo(ALT, LARG, 236))])
        assert r.returncode == 0, r.stdout + r.stderr

    def test_amostra_densa(self, tmp_path):
        """Causa 4: uma amostra a cada 0,5 s. Um grupo de 0,4 s ilegível entre duas amostras passava em branco."""
        ruim = legenda(T.vazio(ALT, LARG), alfa=0.70)
        r = _rodar_gate(tmp_path, [(0.6,) + _legivel(), (0.4, ruim, T.fundo(ALT, LARG, MEIO)),
                                   (1.0,) + _legivel()])
        assert r.returncode == 1, r.stdout + r.stderr

    def test_saida_seca_nao_reprova_e_entrada_lenta_ilegivel_reprova(self, tmp_path):
        """Transição: o texto que some em 0,1 s (a dissolução de saída) fica de fora; o texto que fica 1 s meio
        apagado sobre o claro não é transição, é defeito."""
        ok = _rodar_gate(tmp_path, [(2.0,) + _legivel(),
                                    (0.1, legenda(T.vazio(ALT, LARG), alfa=0.62), T.fundo(ALT, LARG, ESCURO)),
                                    (1.0, T.vazio(ALT, LARG), T.fundo(ALT, LARG, ESCURO))])
        assert ok.returncode == 0, ok.stdout + ok.stderr
        (tmp_path / "b").mkdir()
        ruim = _rodar_gate(tmp_path / "b", [(1.0, legenda(T.vazio(ALT, LARG), alfa=0.62), T.fundo(ALT, LARG, MEIO)),
                                            (2.0,) + _legivel()])
        assert ruim.returncode == 1, ruim.stdout + ruim.stderr

    def test_sem_texto_nenhum_reprova(self, tmp_path):
        r = _rodar_gate(tmp_path, [(2.0, T.vazio(ALT, LARG), T.fundo(ALT, LARG, ESCURO))])
        assert r.returncode == 1


# =========================================================== o render real da W5.A (vermelho no real, não só sintético)

def _v1():
    base = os.environ.get("VAM_PARIDADE_MIDIA")
    pasta = Path(base) / "regressao" / "w5x_v1" if base else None
    if not pasta or not (pasta / "final_9x16.mp4").is_file() or not (pasta / "overlay.mov").is_file():
        pytest.skip("render real da W5.A ausente ($VAM_PARIDADE_MIDIA/regressao/w5x_v1)")
    return pasta


@pytest.mark.midia_real
class TestRenderRealV1:
    def _medir(self, t):
        from gates import contraste_texto as C
        p = _v1()
        tl = json.loads((p / "timeline.json").read_text(encoding="utf-8"))
        larg, alt, _d, desloc = C.info_video(p / "final_9x16.mp4")
        rel = C.Relogio(tl["relogio"]["aceleracao"], tl["relogio"]["a0"], desloc)
        pedacos, _ = C.medir_instante(p / "final_9x16.mp4", p / "overlay.mov", t, rel, (larg, alt))
        return pedacos

    def test_gancho_aos_0_3_s_reprova(self):
        r = self._medir(0.30)
        assert any(not p["ok"] and p["y1"] < 1200 for p in r), r

    def test_camada_apagada_aos_9_21_s_reprova(self):
        r = self._medir(9.21)
        assert any(not p["ok"] and 0.05 < p["tinta"] < 0.2 for p in r), r

    def test_legenda_sobre_o_avatar_escuro_le(self):
        r = self._medir(3.86)
        assert r and all(p["ok"] for p in r), r

    def test_gate_reprova_o_v1(self):
        p = _v1()
        tl = json.loads((p / "timeline.json").read_text(encoding="utf-8"))
        r = subprocess.run([sys.executable, str(GATE), str(p / "final_9x16.mp4"), "--overlay", str(p / "overlay.mov"),
                            "--accel", str(tl["relogio"]["aceleracao"]), "--a0", str(tl["relogio"]["a0"])],
                           capture_output=True, text=True, cwd=str(RAIZ))
        assert r.returncode == 1, r.stdout + r.stderr
