"""Testes do resolvedor de gates, do init_local e da mensagem de material ausente.

Prova a simulacao do aluno: HOME falso (sem ~/.claude/scripts), clone limpo, sem _local.
Roda sem midia e sem rede:  python3 -m unittest scripts/test_gate_resolver.py
"""
import json
import os
import site
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CODIGO = Path(__file__).resolve().parent
RAIZ = CODIGO.parent
GATES = ("gate-ad.py", "gate-colisao-texto.py", "gate-contraste-legenda.py",
         "revisor-copy-ad.py", "auditar_ad.py")


def _env_limpo(home):
    """Ambiente de aluno: HOME falso (sem ~/.claude), mas com os pacotes pip ja instalados.

    PYTHONUSERBASE mantem o site-packages do usuario real visivel (cv2, numpy), porque o
    aluno tambem teria feito `pip install -r scripts/gates/requirements.txt`.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("VAM_")}
    env["HOME"] = str(home)
    env["PYTHONUSERBASE"] = site.getuserbase()
    return env


def rodar_py(codigo, home, extra_env=None):
    """Roda `codigo` num python novo com HOME falso (import fresco do caminhos.py)."""
    env = _env_limpo(home)
    env.update(extra_env or {})
    return subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                          env=env, cwd=str(CODIGO))


class TestResolvedorDeGates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)          # HOME falso, vazio: sem ~/.claude/scripts

    def tearDown(self):
        self.tmp.cleanup()

    def test_gates_vem_no_repo(self):
        for nome in GATES:
            self.assertTrue((CODIGO / "gates" / nome).is_file(), nome)

    def test_acha_gates_do_repo_sem_claude_scripts(self):
        for nome in GATES:
            r = rodar_py(f"import caminhos; print(caminhos.gate_script({nome!r}))", self.home)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(Path(r.stdout.strip()), CODIGO / "gates" / nome)

    def test_nao_depende_do_home(self):
        self.assertFalse((self.home / ".claude").exists())

    def test_repo_ganha_do_claude_scripts(self):
        legado = self.home / ".claude" / "scripts"
        legado.mkdir(parents=True)
        (legado / "gate-ad.py").write_text("# versao antiga")
        r = rodar_py("import caminhos; print(caminhos.gate_script('gate-ad.py'))", self.home)
        self.assertEqual(Path(r.stdout.strip()), CODIGO / "gates" / "gate-ad.py")

    def test_fallback_para_claude_scripts_se_nao_esta_no_repo(self):
        legado = self.home / ".claude" / "scripts"
        legado.mkdir(parents=True)
        (legado / "gate-so-do-dono.py").write_text("# so existe no legado")
        r = rodar_py("import caminhos; print(caminhos.gate_script('gate-so-do-dono.py'))",
                     self.home)
        self.assertEqual(Path(r.stdout.strip()), legado / "gate-so-do-dono.py")

    def test_ausente_devolve_none(self):
        r = rodar_py("import caminhos; print(caminhos.gate_script('nao-existe.py'))", self.home)
        self.assertEqual(r.stdout.strip(), "None")

    def test_excecoes_do_repo_e_vazio_e_generico(self):
        r = rodar_py("import caminhos; print(caminhos.gate_excecoes())", self.home,
                     {"VAM_ESTADO": str(self.home / "_local_vazio")})
        self.assertEqual(Path(r.stdout.strip()), CODIGO / "gates" / "gate-excecoes.json")
        self.assertEqual(json.loads((CODIGO / "gates" / "gate-excecoes.json").read_text()), {})

    def test_excecoes_do_usuario_em_local_ganham(self):
        estado = self.home / "meu_local"
        estado.mkdir()
        (estado / "gate-excecoes.json").write_text("{}")
        r = rodar_py("import caminhos; print(caminhos.gate_excecoes())", self.home,
                     {"VAM_ESTADO": str(estado)})
        self.assertEqual(Path(r.stdout.strip()), estado / "gate-excecoes.json")

    def test_dados_sem_legado_ficam_dentro_do_local(self):
        r = rodar_py("import caminhos; print(caminhos.DADOS); print(caminhos.INPUTS)",
                     self.home, {"VAM_ESTADO": str(self.home / "_local")})
        dados, inputs = r.stdout.split()
        self.assertEqual(Path(dados), self.home / "_local" / "dados")
        self.assertEqual(Path(inputs), self.home / "_local" / "dados" / "inputs")

    def test_pasta_antiga_na_home_e_ignorada(self):
        """Repo de aluno nunca escreve na home: ~/video-ads-machine existir nao muda nada."""
        (self.home / "video-ads-machine").mkdir()
        (self.home / "video-ads-machine-2" / "_local").mkdir(parents=True)
        r = rodar_py("import caminhos; print(caminhos.DADOS); print(caminhos.ESTADO)", self.home)
        dados, estado = r.stdout.split()
        self.assertNotIn(str(self.home), dados)
        self.assertNotIn(str(self.home), estado)
        self.assertTrue(estado.endswith("_local"))

    def test_nenhum_script_do_repo_chama_claude_scripts_sem_fallback(self):
        """Toda referencia a ~/.claude/scripts de gate passa pelo resolvedor."""
        proibidos = ("gate-ad.py", "gate-colisao-texto.py", "gate-contraste-legenda.py",
                     "revisor-copy-ad.py", "auditar_ad.py", "gate-excecoes.json")
        for p in sorted(CODIGO.rglob("*.py")):
            if p.name in ("caminhos.py", "test_gate_resolver.py") or "__pycache__" in p.parts:
                continue
            for n, linha in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                cod = linha.split("#", 1)[0]       # comentario nao conta
                if ".claude" in cod and any(x in cod for x in proibidos):
                    self.fail(f"{p.name}:{n} referencia ~/.claude/scripts direto: {linha.strip()}")

    def test_gates_importam_com_home_falso(self):
        """Cada gate sobe (import ok, sem Traceback) num clone limpo, sem midia."""
        env = _env_limpo(self.home)
        env["VAM_ESTADO"] = str(self.home / "_local")
        for nome in GATES:
            r = subprocess.run([sys.executable, str(CODIGO / "gates" / nome), "--help"],
                               capture_output=True, text=True, env=env, timeout=60)
            self.assertNotIn("Traceback", r.stderr, f"{nome}: {r.stderr[-400:]}")
            self.assertNotIn("ModuleNotFoundError", r.stderr, nome)


    def test_sem_dependencia_python_vira_mensagem_nao_traceback(self):
        """Aluno sem opencv/numpy/pillow: o gate manda instalar, nao despeja traceback."""
        env = _env_limpo(self.home)
        env["VAM_ESTADO"] = str(self.home / "_local")
        for nome, modulo in (("gate-colisao-texto.py", "cv2"),
                             ("gate-contraste-legenda.py", "numpy"),
                             ("gate-ad.py", "PIL")):
            codigo = (f"import sys, runpy; sys.modules[{modulo!r}] = None; "
                      f"sys.argv = [{nome!r}, '--help']; "
                      f"runpy.run_path({str(CODIGO / 'gates' / nome)!r}, run_name='__main__')")
            r = subprocess.run([sys.executable, "-c", codigo], capture_output=True,
                               text=True, env=env, timeout=60)
            self.assertNotEqual(r.returncode, 0, nome)
            self.assertNotIn("Traceback", r.stderr, f"{nome}: {r.stderr[-300:]}")
            self.assertIn("requirements.txt", r.stderr, nome)

    def test_gate_ad_sem_pasta_de_output_manda_pro_init(self):
        env = _env_limpo(self.home)
        env["VAM_ESTADO"] = str(self.home / "_local")
        r = subprocess.run([sys.executable, str(CODIGO / "gates" / "gate-ad.py"), "03"],
                           capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("init_local.py", r.stderr)


class TestMaterialLocal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _checar(self, estado, ad="25", look="espuma_roxa"):
        codigo = ("import material_local as m\n"
                  f"print('OK' if m.checar_config({ad!r}, {look!r}, '9x16') else 'FALTA')")
        return rodar_py(codigo, self.home, {"VAM_ESTADO": str(estado)})

    def test_sem_local_mensagem_unica_sem_traceback(self):
        r = self._checar(self.home / "_local")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        self.assertIn("FALTA", r.stdout)
        saida = r.stdout + r.stderr
        self.assertIn("_local", saida)
        self.assertIn("init_local.py", saida)
        self.assertIn("demo/", saida)
        self.assertEqual(saida.count("init_local.py"), 1, "mensagem tem que ser uma so")

    def test_local_existe_mas_sem_config_aponta_pro_config(self):
        estado = self.home / "_local"
        (estado / "configs").mkdir(parents=True)
        r = self._checar(estado)
        saida = r.stdout + r.stderr
        self.assertIn("FALTA", r.stdout)
        self.assertIn("_local/configs", saida)
        self.assertIn("ad25v2_espuma.json", saida)

    def test_config_presente_passa(self):
        estado = self.home / "_local"
        (estado / "configs").mkdir(parents=True)
        (estado / "configs" / "ad25v2_espuma.json").write_text("{}")
        r = self._checar(estado)
        self.assertIn("OK", r.stdout)
        self.assertEqual((r.stdout + r.stderr).count("_local"), 0)

    def test_exigir_sai_com_codigo_2_e_mensagem(self):
        codigo = ("import material_local as m\n"
                  "from pathlib import Path\n"
                  "m.exigir(Path('/nao/existe/x.json'), 'um arquivo do seu anuncio')")
        r = rodar_py(codigo, self.home, {"VAM_ESTADO": str(self.home / "_local")})
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("init_local.py", r.stderr)


class TestInitLocal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.estado = Path(self.tmp.name) / "_local"

    def tearDown(self):
        self.tmp.cleanup()

    def _rodar(self, *args):
        env = _env_limpo(self.tmp.name)
        env["VAM_ESTADO"] = str(self.estado)
        return subprocess.run([sys.executable, str(CODIGO / "init_local.py"), *args],
                              capture_output=True, text=True, env=env)

    def test_cria_a_estrutura(self):
        r = self._rodar()
        self.assertEqual(r.returncode, 0, r.stderr)
        for sub in ("configs", "roteiros", "dados/inputs", "dados/output",
                    "render-reel-editorial"):
            self.assertTrue((self.estado / sub).is_dir(), sub)
        self.assertTrue((self.estado / "README.md").is_file())
        self.assertTrue((self.estado / "render-reel-editorial" / "meta.json").is_file())
        self.assertTrue((self.estado / "roteiros" / "roteiro_demo.txt").is_file())
        self.assertTrue((self.estado / "dados" / "inputs" / "ad99v2_inserts.json").is_file())
        self.assertTrue((self.estado / "dados" / "inputs" / "ad99v2_leva.txt").is_file())
        self.assertTrue((self.estado / "gate-excecoes.json").is_file())

    def test_exemplos_sao_json_valido_e_o_config_aponta_pro_demo(self):
        self._rodar()
        for j in ("gate-excecoes.json", "_doc_map.json",
                  "dados/inputs/ad99v2_inserts.json", "render-reel-editorial/meta.json"):
            json.loads((self.estado / j).read_text())
        cfg = json.loads((self.estado / "configs" / "ad99v2_espuma.json").read_text())
        self.assertEqual(cfg["ad"], "ad99v2")
        self.assertIn("kw_phrases", cfg)

    def test_idempotente_e_nao_sobrescreve_o_que_e_do_usuario(self):
        self._rodar()
        alvo = self.estado / "roteiros" / "roteiro_demo.txt"
        alvo.write_text("MEU ROTEIRO")
        r = self._rodar()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(alvo.read_text(), "MEU ROTEIRO")
        self.assertIn("ja existe", r.stdout)

    def test_nao_escreve_fora_do_local(self):
        self._rodar()
        fora = [p for p in Path(self.tmp.name).iterdir() if p.name != "_local"]
        self.assertEqual(fora, [])

    def test_mensagem_final_diz_o_proximo_passo(self):
        r = self._rodar()
        self.assertIn("demo/", r.stdout)
        self.assertNotIn("\u2014", r.stdout)


if __name__ == "__main__":
    unittest.main()
