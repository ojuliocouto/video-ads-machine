#!/usr/bin/env python3
"""Contrato da esteira de testes (W0.1): o clone limpo roda verde, sem setup e sem a máquina do dono.

Cada teste daqui nasce de um defeito medido no clone limpo, com HOME falso e o Python 3.9
do macOS: 5 falhas (os wav de som que só o setup gera) e 2 testes que apontavam para o
scratchpad absoluto de outra sessão. Esta esteira garante que isso não volta:

  1. nenhum arquivo de teste cita caminho absoluto de máquina;
  2. o pytest.ini existe, declara os markers e barra marker inventado;
  3. o scripts/dev/testar_limpo.sh monta o ambiente hermético (HOME temporário, sem VAM_*);
  4. os fixtures sintéticos são determinísticos (mesmo md5 em duas gerações);
  5. o conftest entrega `home_falso` e `estado_vazio`.

Os testes de classe (unittest) rodam com pytest e com o fallback do testar_limpo.sh. As
funções soltas do fim usam fixtures do pytest e só existem no pytest.
"""
import configparser
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from importlib import import_module
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
for _p in (str(RAIZ / "scripts"), str(RAIZ)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SCRIPT = RAIZ / "scripts" / "dev" / "testar_limpo.sh"

# Montados por pedaços para este arquivo não ser o primeiro a violar a própria regra.
PROIBIDOS = ("/private" + "/tmp", "/Us" + "ers/")


def _arquivos_de_teste():
    achados = sorted((RAIZ / "scripts").glob("test_*.py"))
    achados += sorted(p for p in (RAIZ / "tests").rglob("*.py") if "__pycache__" not in p.parts)
    return achados


def _md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def _ler_ini():
    cp = configparser.ConfigParser(interpolation=None)
    ini = RAIZ / "pytest.ini"
    assert ini.is_file(), f"falta {ini}"
    cp.read(ini, encoding="utf-8")
    return cp["pytest"]


class TesteNenhumCaminhoAbsoluto(unittest.TestCase):

    def test_ha_arquivos_de_teste_para_varrer(self):
        nomes = {p.name for p in _arquivos_de_teste()}
        for esperado in ("test_mix_som.py", "test_mixar_sfx.py", "test_nivel_som.py",
                         "test_som_cortes.py", "test_folhas_contato.py",
                         "test_medir_ritmo.py", "test_esteira.py"):
            self.assertIn(esperado, nomes)

    def test_arquivos_de_teste_nao_citam_caminho_absoluto_de_maquina(self):
        ofensas = []
        for arq in _arquivos_de_teste():
            for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
                for proibido in PROIBIDOS:
                    if proibido in linha:
                        ofensas.append(f"{arq.relative_to(RAIZ)}:{n}: {proibido}")
        self.assertEqual(ofensas, [], "caminho absoluto em teste: o clone limpo não tem "
                                      "essa máquina. Gere o fixture em tmp.")

    def test_skip_sempre_diz_o_motivo(self):
        sem_motivo = re.compile(
            r"(skipTest|pytest\.skip|unittest\.skip|skipIf|skipUnless)\(\s*\)")
        ofensas = []
        for arq in _arquivos_de_teste():
            for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
                if sem_motivo.search(linha):
                    ofensas.append(f"{arq.relative_to(RAIZ)}:{n}")
        self.assertEqual(ofensas, [], "skip sem motivo esconde teste que não roda")


class TesteConfigPytest(unittest.TestCase):

    def test_testpaths_cobre_scripts_e_tests(self):
        paths = _ler_ini()["testpaths"].split()
        self.assertEqual(sorted(paths), ["scripts", "tests"])

    def test_modo_de_import_e_importlib_e_marker_inventado_barra(self):
        addopts = _ler_ini()["addopts"]
        self.assertIn("--import-mode=importlib", addopts)
        self.assertIn("--strict-markers", addopts)
        self.assertRegex(addopts, r"(^|\s)-rs(\s|$)", "o relatório de skips tem que vir sempre")

    def test_markers_lento_midia_real_e_rede_declarados(self):
        linhas = [x.strip() for x in _ler_ini()["markers"].splitlines() if x.strip()]
        declarados = {x.split(":")[0].strip() for x in linhas}
        for nome in ("lento", "midia_real", "rede"):
            self.assertIn(nome, declarados)

    def test_todo_marker_usado_nos_testes_esta_declarado(self):
        livres = {"parametrize", "skip", "skipif", "xfail", "usefixtures", "filterwarnings"}
        linhas = [x.strip() for x in _ler_ini()["markers"].splitlines() if x.strip()]
        declarados = {x.split(":")[0].strip().split("(")[0] for x in linhas}
        usados = set()
        for arq in _arquivos_de_teste():
            usados |= set(re.findall(r"pytest\.mark\.([A-Za-z_]+)", arq.read_text(encoding="utf-8")))
        self.assertEqual(sorted(usados - livres - declarados - {"x"}), [])

    def test_pacotes_de_teste_existem(self):
        for rel in ("tests/__init__.py", "tests/conftest.py", "tests/fixtures/__init__.py",
                    "tests/fixtures/sinteticos.py"):
            self.assertTrue((RAIZ / rel).is_file(), f"falta {rel}")


class TesteTestarLimpo(unittest.TestCase):
    """O script é testado pelo `--dry-run`, que mostra o ambiente sem rodar a suíte."""

    def _dry(self, *args, extra_env=None):
        env = dict(os.environ)
        for k in [k for k in env if k.startswith("VAM_")]:
            del env[k]
        env.update(extra_env or {})
        return subprocess.run(["bash", str(SCRIPT), "--dry-run", *args], capture_output=True,
                              text=True, env=env, cwd=str(tempfile.gettempdir()))

    def test_existe_executavel_e_sintaxe_valida(self):
        self.assertTrue(SCRIPT.is_file(), f"falta {SCRIPT}")
        self.assertTrue(os.access(SCRIPT, os.X_OK), "falta chmod +x")
        r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_padrao_exclui_lento_midia_real_e_rede(self):
        r = self._dry()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("not lento and not midia_real and not rede", r.stdout)

    def test_flag_lento_inclui_lento_mas_nao_midia_real(self):
        r = self._dry("--lento")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("not midia_real and not rede", r.stdout)
        self.assertNotIn("not lento", r.stdout)

    def test_flag_tudo_nao_filtra_marker(self):
        r = self._dry("--tudo", extra_env={"VAM_PARIDADE_MIDIA": tempfile.gettempdir()})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("not lento", r.stdout)
        self.assertNotIn("not midia_real", r.stdout)

    def test_paridade_sem_a_variavel_para_com_mensagem_clara(self):
        r = self._dry("--paridade")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("VAM_PARIDADE_MIDIA", r.stdout + r.stderr)

    def test_paridade_com_a_variavel_seleciona_so_midia_real(self):
        r = self._dry("--paridade", extra_env={"VAM_PARIDADE_MIDIA": tempfile.gettempdir()})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("-m midia_real", r.stdout)

    def test_home_e_temporario_e_diferente_do_do_chamador(self):
        chamador = tempfile.mkdtemp(prefix="vam_chamador_")
        self.addCleanup(lambda: os.rmdir(chamador))
        r = self._dry(extra_env={"HOME": chamador})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        m = re.search(r"^HOME=(\S+)$", r.stdout, re.M)
        self.assertIsNotNone(m, r.stdout)
        self.assertNotEqual(m.group(1), chamador)
        self.assertTrue(m.group(1).startswith(os.path.realpath(tempfile.gettempdir()))
                        or m.group(1).startswith(tempfile.gettempdir()), m.group(1))

    def test_user_site_real_sobrevive_ao_home_falso_do_chamador(self):
        """Quem já exporta um HOME falso não pode perder o pytest do user site."""
        chamador = tempfile.mkdtemp(prefix="vam_chamador_")
        self.addCleanup(lambda: os.rmdir(chamador))
        r = self._dry(extra_env={"HOME": chamador})
        m = re.search(r"^PYTHONUSERBASE=(.*)$", r.stdout, re.M)
        self.assertIsNotNone(m, r.stdout)
        self.assertFalse(m.group(1).startswith(chamador),
                         f"user base calculada a partir do HOME falso: {m.group(1)}")

    def test_variaveis_vam_do_chamador_nao_vazam(self):
        r = self._dry(extra_env={"VAM_DADOS": "/nao/existe", "VAM_ESTADO": "/nao/existe"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("VAM_DADOS=/nao/existe", r.stdout)
        self.assertNotIn("VAM_ESTADO=/nao/existe", r.stdout)


def _exige_ffmpeg():
    r = subprocess.run(["ffmpeg", "-version"], capture_output=True)
    if r.returncode != 0:
        raise AssertionError("ffmpeg ausente: o fixture sintético depende dele (rode o setup)")


class TesteFixturesSinteticas(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _exige_ffmpeg()
        cls.SIN = import_module("tests.fixtures.sinteticos")
        cls.A = Path(tempfile.mkdtemp(prefix="vam_sin_a_"))
        cls.B = Path(tempfile.mkdtemp(prefix="vam_sin_b_"))
        import shutil
        cls.addClassCleanup(shutil.rmtree, cls.A, True)
        cls.addClassCleanup(shutil.rmtree, cls.B, True)

    def _gera_duas_vezes(self, nome, ext, **kw):
        fn = getattr(self.SIN, nome)
        a = fn(self.A / f"{nome}{ext}", **kw)
        b = fn(self.B / f"{nome}_outro_nome{ext}", **kw)
        self.assertTrue(Path(a).is_file() and Path(b).is_file())
        return Path(a), Path(b)

    def test_tom_com_pausas_e_deterministico(self):
        a, b = self._gera_duas_vezes("tom_com_pausas", ".wav")
        self.assertEqual(_md5(a), _md5(b))

    def test_ruido_rosa_e_deterministico(self):
        a, b = self._gera_duas_vezes("ruido_rosa", ".wav")
        self.assertEqual(_md5(a), _md5(b))

    def test_testsrc_com_audio_e_deterministico(self):
        a, b = self._gera_duas_vezes("testsrc_com_audio", ".mp4")
        self.assertEqual(_md5(a), _md5(b))

    def test_video_com_rotacao_e_deterministico(self):
        a, b = self._gera_duas_vezes("video_rotacao_menos90", ".mp4")
        self.assertEqual(_md5(a), _md5(b))

    def test_video_por_planos_e_deterministico(self):
        a, b = self._gera_duas_vezes("video_por_planos", ".mp4", duracoes=(2.0, 3.0, 2.5))
        self.assertEqual(_md5(a), _md5(b))

    def test_seed_diferente_gera_ruido_diferente(self):
        a = self.SIN.ruido_rosa(self.A / "r1.wav", seed=1)
        b = self.SIN.ruido_rosa(self.A / "r2.wav", seed=2)
        self.assertNotEqual(_md5(a), _md5(b))

    def test_tom_tem_silencio_exatamente_nas_pausas_declaradas(self):
        import numpy as np
        pausas = ((1.5, 2.1), (4.0, 4.8))
        p = self.SIN.tom_com_pausas(self.A / "tom.wav", dur=6.0, pausas=pausas)
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-f", "s16le", "-ac", "1",
                            "-ar", "48000", "-"], capture_output=True)
        a = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float64) / 32768.0
        self.assertAlmostEqual(len(a) / 48000.0, 6.0, delta=0.05)

        def pico(t0, t1):
            return float(np.abs(a[int(t0 * 48000):int(t1 * 48000)]).max())
        for ini, fim in pausas:
            self.assertLess(pico(ini + 0.02, fim - 0.02), 1e-3, f"pausa {ini}-{fim} não é silêncio")
        for ini, fim in ((0.1, 1.4), (2.2, 3.9), (4.9, 5.9)):
            self.assertGreater(pico(ini, fim), 0.01, f"trecho de fala {ini}-{fim} está mudo")

    def test_testsrc_tem_video_e_audio(self):
        p = self.SIN.testsrc_com_audio(self.A / "ts.mp4", dur=3.0)
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
                            "-of", "csv=p=0", str(p)], capture_output=True, text=True)
        self.assertEqual(sorted(r.stdout.split()), ["audio", "video"])

    def test_video_rotacionado_declara_rotacao_menos_90(self):
        p = self.SIN.video_rotacao_menos90(self.A / "rot.mp4")
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams",
                            "-of", "json", str(p)], capture_output=True, text=True)
        stream = json.loads(r.stdout)["streams"][0]
        rot = [d.get("rotation") for d in stream.get("side_data_list", [])]
        self.assertIn(-90, rot, "o ffprobe tem que enxergar a rotação (o fixture é a prova)")

    def test_planos_tem_os_cortes_declarados(self):
        """Contrato do fixture de ritmo: cada corte do plano aparece no instante certo."""
        import medir_ritmo as MR
        duracoes = (2.0, 2.0, 2.0, 2.0, 2.0)
        p = self.SIN.video_por_planos(self.A / "pl.mp4", duracoes=duracoes)
        esperados = self.SIN.instantes_de_corte(duracoes)
        self.assertEqual(esperados, [2.0, 4.0, 6.0, 8.0])
        vistos = sorted(float(x) for x in MR.cortes_confirmados(p, None))
        self.assertEqual(len(vistos), len(esperados), vistos)
        for e, v in zip(esperados, vistos):
            self.assertAlmostEqual(e, v, delta=0.26)


# --- só pytest: fixtures do conftest ------------------------------------------------

def test_conftest_poe_scripts_no_sys_path():
    assert str(RAIZ / "scripts") in sys.path


def test_home_falso_aponta_para_pasta_vazia_e_isolada(home_falso):
    assert Path.home() == home_falso
    assert os.environ["HOME"] == str(home_falso)
    assert home_falso.is_dir() and list(home_falso.iterdir()) == []
    import pwd
    assert str(home_falso) != pwd.getpwuid(os.getuid()).pw_dir


def test_home_falso_vale_na_hora_da_chamada_do_caminhos(home_falso):
    """`caminhos.gate_script` lê o HOME a cada chamada: o HOME falso tem que ser enxergado."""
    import caminhos
    assert caminhos.gate_script("gate-so-do-teste.py") is None
    pasta = home_falso / ".claude" / "scripts"
    pasta.mkdir(parents=True)
    (pasta / "gate-so-do-teste.py").write_text("# gate de mentira\n", encoding="utf-8")
    assert caminhos.gate_script("gate-so-do-teste.py") == pasta / "gate-so-do-teste.py"


def test_estado_vazio_entrega_estado_e_dados_novos(estado_vazio):
    assert estado_vazio.is_dir() and list(estado_vazio.iterdir()) == []
    assert os.environ["VAM_ESTADO"] == str(estado_vazio)
    assert Path(os.environ["VAM_DADOS"]).parent == estado_vazio


def test_estado_vazio_limpa_variaveis_antigas(estado_vazio):
    for nome in ("VAM_V1_HOME", "VAM_INPUTS", "VAM_OUTPUT", "VAM_ROTEIROS", "VAM_ASSETS",
                 "VAM_FONTS"):
        assert nome not in os.environ, nome
