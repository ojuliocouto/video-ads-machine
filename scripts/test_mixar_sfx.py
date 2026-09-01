#!/usr/bin/env python3
"""Teste do mixador de SFX (contrato antes do código).

O mixador recebe o mp4 final + o plano de ritmo (_ritmo.json) + a aceleração, e devolve
o mp4 com whoosh nas ENTRADAS de insert e um riser antes do último bloco. Regras do
banco: máximo 1 efeito a cada 2,5s, nunca na volta pro avatar, sutil (a voz manda).

Verificável sem ouvido:
  - onde caiu whoosh, o RMS da faixa sobe em relação ao mesmo trecho sem mix
  - onde NÃO caiu efeito, o áudio fica igual (a voz não é tocada)
  - a duração do arquivo não muda
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

SC = Path("/private/tmp/claude-501/-Users-ojuliocouto/"
          "e497af2e-0966-43f0-8898-d733864737e9/scratchpad/mixtest")


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-300:]
    return r


def _rms_db(p, ini, dur):
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-ss", str(ini), "-t", str(dur), "-i", str(p),
         "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    import re
    m = re.search(r"mean_volume:\s*(-?[0-9.]+) dB", r.stderr)
    return float(m.group(1)) if m else -120.0


class TesteMixarSfx(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        SC.mkdir(parents=True, exist_ok=True)
        cls.video = SC / "base.mp4"
        # 12s de tom baixo constante (simula voz) + video preto
        _run(["ffmpeg", "-y", "-v", "error",
              "-f", "lavfi", "-i", "color=black:s=320x240:r=30:d=12",
              "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=12",
              "-af", "volume=-30dB", "-c:v", "libx264", "-c:a", "aac", str(cls.video)])
        plano = {"total": 12.0, "segs": [
            {"bloco": 0, "tipo": "orig", "s": 0.0, "e": 3.0},
            {"bloco": 1, "tipo": "insert", "s": 3.0, "e": 5.0},   # whoosh aqui (3.0)
            {"bloco": 1, "tipo": "orig", "s": 5.0, "e": 7.0},     # volta: SEM efeito
            {"bloco": 1, "tipo": "insert", "s": 7.0, "e": 9.0},   # whoosh aqui (7.0)
            {"bloco": 2, "tipo": "orig", "s": 9.0, "e": 12.0},    # ultimo bloco: riser antes
        ]}
        cls.plano = SC / "base_ritmo.json"
        cls.plano.write_text(json.dumps(plano))
        cls.saida = SC / "mixado.mp4"
        r = subprocess.run([sys.executable,
                            str(__import__("caminhos").CODIGO / "mixar_sfx.py"),
                            str(cls.video), str(cls.plano), "1.0", str(cls.saida)],
                           capture_output=True, text=True)
        cls.rc, cls.err = r.returncode, r.stderr

    def test_roda_sem_erro(self):
        self.assertEqual(self.rc, 0, self.err[-300:])

    def test_whoosh_sobe_rms_na_entrada_do_insert(self):
        antes = _rms_db(self.video, 3.0, 0.4)
        depois = _rms_db(self.saida, 3.0, 0.4)
        self.assertGreater(depois, antes + 2.0,
                           f"sem sinal de whoosh em 3.0s ({antes} -> {depois} dB)")

    def test_riser_tem_prioridade_sobre_whoosh_vizinho(self):
        """O riser reserva a virada (ultimo bloco em 9,0s: riser em 7,8-9,0) e o
        whoosh do insert de 7,0s, a menos de GAP_MIN dele, cede a vez."""
        antes = _rms_db(self.video, 8.0, 0.8)
        depois = _rms_db(self.saida, 8.0, 0.8)
        self.assertGreater(depois, antes + 2.0,
                           f"sem sinal de riser na virada ({antes} -> {depois} dB)")

    def test_voz_intocada_fora_dos_eventos(self):
        antes = _rms_db(self.video, 1.0, 1.5)
        depois = _rms_db(self.saida, 1.0, 1.5)
        self.assertAlmostEqual(depois, antes, delta=1.0,
                               msg="o mix alterou a faixa onde nao ha efeito")

    def test_duracao_nao_muda(self):
        def dur(p):
            r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                "format=duration", "-of", "csv=p=0", str(p)],
                               capture_output=True, text=True)
            return float(r.stdout.strip())
        self.assertAlmostEqual(dur(self.saida), dur(self.video), delta=0.15)


if __name__ == "__main__":
    unittest.main(verbosity=1)
