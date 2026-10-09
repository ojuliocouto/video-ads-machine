"""transcrever (W1.C): escolha de backend, cache por conteúdo e glossário.

Nenhum backend real roda aqui: o ambiente (sistema, arquitetura, PATH, módulos, chave) é
injetado e o backend é um espião. Nenhuma chamada paga.
"""
import json
import shutil
from pathlib import Path

import pytest

from audio import transcrever as T
from tests.fixtures import sinteticos as fx


def amb(sistema="Darwin", arquitetura="arm64", executaveis=(), modulos=(), env=None, bins=()):
    """Ambiente falso. `executaveis` e `modulos` são o que EXISTE nessa máquina."""
    return T.Ambiente(
        sistema=sistema, arquitetura=arquitetura, env=dict(env or {}),
        which=lambda nome: (f"/falso/bin/{nome}" if nome in executaveis else None),
        importavel=lambda nome: nome in modulos,
        bins_venv=tuple(bins))


# --- ordem de backend ---------------------------------------------------------------------

def test_ordem_e_parakeet_depois_faster_whisper_depois_groq():
    assert T.ORDEM == ("parakeet", "faster_whisper", "groq")


def test_apple_silicon_com_tudo_instalado_escolhe_parakeet():
    a = amb(executaveis=("parakeet-mlx",), modulos=("faster_whisper",),
            env={"GROQ_API_KEY": "gsk_falsa"})
    assert T.escolher_backend(a).NOME == "parakeet"
    assert T.backends_disponiveis(a) == ["parakeet", "faster_whisper", "groq"]


def test_sem_parakeet_cai_no_faster_whisper_e_depois_no_groq():
    a = amb(modulos=("faster_whisper",), env={"GROQ_API_KEY": "gsk_falsa"})
    assert T.escolher_backend(a).NOME == "faster_whisper"
    b = amb(env={"GROQ_API_KEY": "gsk_falsa"})
    assert T.escolher_backend(b).NOME == "groq"


def test_parakeet_so_vale_no_apple_silicon_mesmo_com_o_executavel_no_path():
    linux = amb(sistema="Linux", arquitetura="x86_64", executaveis=("parakeet-mlx",),
                modulos=("faster_whisper",))
    intel = amb(sistema="Darwin", arquitetura="x86_64", executaveis=("parakeet-mlx",),
                modulos=("faster_whisper",))
    assert T.escolher_backend(linux).NOME == "faster_whisper"
    assert T.escolher_backend(intel).NOME == "faster_whisper"


def test_groq_sem_chave_ou_com_chave_vazia_nao_conta():
    assert T.backends_disponiveis(amb(env={})) == []
    assert T.backends_disponiveis(amb(env={"GROQ_API_KEY": "   "})) == []


def test_backend_pedido_que_nao_existe_na_maquina_falha_citando_o_nome():
    with pytest.raises(T.SemTranscritor, match="faster_whisper"):
        T.escolher_backend(amb(), preferido="faster_whisper")
    with pytest.raises(ValueError, match="nada"):
        T.escolher_backend(amb(), preferido="nada")


def test_backend_pedido_e_respeitado_quando_disponivel():
    a = amb(executaveis=("parakeet-mlx",), env={"GROQ_API_KEY": "gsk_falsa"})
    assert T.escolher_backend(a, preferido="groq").NOME == "groq"


# --- sem nenhum backend: UMA mensagem com o comando de instalação ------------------------

def test_sem_nenhum_backend_levanta_uma_mensagem_com_o_comando_de_instalacao_no_apple():
    with pytest.raises(T.SemTranscritor) as e:
        T.escolher_backend(amb())
    msg = str(e.value)
    assert "pip install parakeet-mlx" in msg
    assert "GROQ_API_KEY" in msg
    assert "\n" not in msg.strip()              # uma mensagem só, em uma linha
    assert "Traceback" not in msg


def test_sem_nenhum_backend_fora_do_apple_manda_instalar_o_faster_whisper():
    with pytest.raises(T.SemTranscritor) as e:
        T.escolher_backend(amb(sistema="Linux", arquitetura="x86_64"))
    assert "pip install faster-whisper" in str(e.value)
    assert "parakeet" not in str(e.value)


def test_transcrever_sem_backend_nao_cria_pasta_de_cache_nem_arquivo(tmp_path):
    audio = fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=())
    cache = tmp_path / "cache"
    with pytest.raises(T.SemTranscritor):
        T.transcrever(audio, cache_dir=cache, amb=amb())
    assert not any(cache.rglob("*.json")) if cache.exists() else True


# --- cache por sha do conteúdo, dentro do projeto -----------------------------------------

class Espiao:
    """Backend falso que conta as chamadas e guarda onde trabalhou."""
    NOME = "espiao"

    def __init__(self, palavras=None):
        self.chamadas, self.workdirs, self.prompts = 0, [], []
        self.palavras = palavras or [{"text": "Olá", "start": 0.0, "end": 0.4},
                                     {"text": "mundo", "start": 0.5, "end": 0.9}]

    def transcrever(self, audio, *, amb, workdir, prompt="", idioma="pt", **_):
        self.chamadas += 1
        self.workdirs.append(Path(workdir))
        self.prompts.append(prompt)
        return [dict(p) for p in self.palavras]


def test_cache_por_conteudo_mesmo_arquivo_em_outro_caminho_nao_retranscreve(tmp_path):
    a = fx.tom_com_pausas(tmp_path / "a" / "avatar.wav", dur=1.0, pausas=())
    b = tmp_path / "b" / "copia.wav"
    b.parent.mkdir()
    shutil.copy(a, b)
    esp, cache = Espiao(), tmp_path / "proj" / "cache"
    r1 = T.transcrever(a, cache_dir=cache, backend=esp, amb=amb())
    r2 = T.transcrever(b, cache_dir=cache, backend=esp, amb=amb())
    assert esp.chamadas == 1
    assert r1 == r2


def test_cache_nao_depende_de_mtime_nem_de_tamanho_so_do_conteudo(tmp_path):
    a = fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=())
    esp, cache = Espiao(), tmp_path / "cache"
    T.transcrever(a, cache_dir=cache, backend=esp, amb=amb())
    import os
    os.utime(a, (1, 1))                                    # mtime muda, bytes não
    T.transcrever(a, cache_dir=cache, backend=esp, amb=amb())
    assert esp.chamadas == 1


def test_conteudo_diferente_com_o_mesmo_tamanho_e_outra_entrada(tmp_path):
    a = fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=(), freq=220.0)
    b = fx.tom_com_pausas(tmp_path / "b.wav", dur=1.0, pausas=(), freq=330.0)
    assert a.stat().st_size == b.stat().st_size
    esp, cache = Espiao(), tmp_path / "cache"
    T.transcrever(a, cache_dir=cache, backend=esp, amb=amb())
    T.transcrever(b, cache_dir=cache, backend=esp, amb=amb())
    assert esp.chamadas == 2


def test_sha_do_conteudo_e_o_sha256_inteiro(tmp_path):
    import hashlib
    p = tmp_path / "x.bin"
    p.write_bytes(b"abc" * 100000)
    assert T.sha_do_conteudo(p) == hashlib.sha256(b"abc" * 100000).hexdigest()


def test_tudo_que_o_cache_escreve_fica_dentro_da_pasta_do_projeto(tmp_path):
    a = fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=())
    esp, cache = Espiao(), tmp_path / "proj" / "cache"
    T.transcrever(a, cache_dir=cache, backend=esp, amb=amb())
    cache_r = cache.resolve()
    assert esp.workdirs and all(cache_r in w.resolve().parents for w in esp.workdirs)
    achados = [p for p in tmp_path.rglob("*") if p.is_file() and p != a]
    assert achados and all(cache_r in p.resolve().parents for p in achados)
    sha = T.sha_do_conteudo(a)
    dados = json.loads((cache / f"{sha}.json").read_text(encoding="utf-8"))
    assert dados["sha256"] == sha and dados["backend"] == "espiao"
    assert dados["palavras"][0]["text"] == "Olá"
    assert not list(cache.glob("*.tmp"))


def test_sem_cache_dir_e_erro_de_uso_nunca_um_padrao_em_tmp(tmp_path):
    a = fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=())
    with pytest.raises(TypeError):
        T.transcrever(a, backend=Espiao(), amb=amb())


def test_o_modulo_nao_cita_tmp_nem_home_cravados():
    fonte = Path(T.__file__).read_text(encoding="utf-8")
    assert "/tmp" not in fonte and "gettempdir" not in fonte
    assert ".local/bin" not in fonte


def test_forcar_ignora_o_cache(tmp_path):
    a = fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=())
    esp, cache = Espiao(), tmp_path / "cache"
    T.transcrever(a, cache_dir=cache, backend=esp, amb=amb())
    T.transcrever(a, cache_dir=cache, backend=esp, amb=amb(), forcar=True)
    assert esp.chamadas == 2


def test_cache_corrompido_e_refeito_em_vez_de_derrubar(tmp_path):
    a = fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=())
    esp, cache = Espiao(), tmp_path / "cache"
    T.transcrever(a, cache_dir=cache, backend=esp, amb=amb())
    (cache / f"{T.sha_do_conteudo(a)}.json").write_text("{quebrado", encoding="utf-8")
    assert T.transcrever(a, cache_dir=cache, backend=esp, amb=amb())[0]["text"] == "Olá"
    assert esp.chamadas == 2


def test_arquivo_inexistente_da_erro_claro(tmp_path):
    with pytest.raises(FileNotFoundError, match="nao-existe"):
        T.transcrever(tmp_path / "nao-existe.wav", cache_dir=tmp_path / "c",
                      backend=Espiao(), amb=amb())


# --- glossário: prompt e correção de grafia ------------------------------------------------

GLOSSARIO = {
    "versao": 1,
    "termos": [
        {"grafia": "Claude Code", "variantes": ["cloud code", "clod code"], "tipo": "produto"},
        {"grafia": "Claude", "variantes": ["Cloud"], "tipo": "produto"},
        {"grafia": "Hotmart", "variantes": ["rot mart"], "tipo": "marca"},
        {"grafia": "Lia"},
    ],
    "equivalencias": [{"roteiro": "para", "fala": "pra"}],
}


def _p(texto, t0=0.0, passo=0.5):
    return [{"text": w, "start": round(t0 + i * passo, 3), "end": round(t0 + i * passo + 0.4, 3)}
            for i, w in enumerate(texto.split())]


def test_prompt_vem_do_glossario_com_as_grafias_e_sem_as_variantes():
    prompt = T.prompt_do_glossario(GLOSSARIO)
    assert prompt.startswith("Transcrição em português do Brasil.")
    for grafia in ("Claude Code", "Claude", "Hotmart", "Lia"):
        assert grafia in prompt
    assert "cloud" not in prompt.lower().replace("claude", "")
    assert "rot mart" not in prompt


def test_prompt_sem_glossario_e_so_a_frase_base():
    assert T.prompt_do_glossario(None) == "Transcrição em português do Brasil."
    assert T.prompt_do_glossario({"versao": 1, "termos": []}) == "Transcrição em português do Brasil."


def test_prompt_respeita_o_teto_e_nao_corta_termo_no_meio():
    muitos = {"versao": 1, "termos": [{"grafia": f"Termo{i:03d}Longo"} for i in range(200)]}
    prompt = T.prompt_do_glossario(muitos)
    assert len(prompt) <= T.PROMPT_MAX
    ultimo = prompt.rstrip(".").split(", ")[-1]
    assert ultimo.startswith("Termo") and ultimo.endswith("Longo")


def test_o_prompt_do_glossario_chega_ao_backend(tmp_path):
    a = fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=())
    esp = Espiao()
    T.transcrever(a, cache_dir=tmp_path / "c", backend=esp, amb=amb(), glossario=GLOSSARIO)
    assert "Claude Code" in esp.prompts[0] and "Hotmart" in esp.prompts[0]


def test_glossario_troca_so_a_variante_declarada():
    out = T.aplicar_glossario(_p("eu uso o Cloud todo dia"), GLOSSARIO)
    assert [w["text"] for w in out] == ["eu", "uso", "o", "Claude", "todo", "dia"]
    # a palavra "todo" e "dia" nunca foram declaradas: intactas, com o tempo original
    assert out[4] == {"text": "todo", "start": 2.0, "end": 2.4}


def test_variante_de_duas_palavras_prevalece_sobre_a_de_uma():
    out = T.aplicar_glossario(_p("abre o cloud code agora"), GLOSSARIO)
    assert [w["text"] for w in out] == ["abre", "o", "Claude", "Code", "agora"]
    # o tempo das duas palavras novas cobre exatamente o das duas palavras trocadas
    assert out[2]["start"] == 1.0 and out[3]["end"] == 1.9
    assert out[2]["end"] <= out[3]["start"]


def test_variante_de_duas_palavras_numa_so_mantem_o_tempo_total():
    out = T.aplicar_glossario(_p("vendo no rot mart hoje"), GLOSSARIO)
    assert [w["text"] for w in out] == ["vendo", "no", "Hotmart", "hoje"]
    assert out[2]["start"] == 1.0 and out[2]["end"] == 1.9


def test_pontuacao_e_caixa_nao_atrapalham_e_a_pontuacao_e_preservada():
    out = T.aplicar_glossario(_p("Olá, CLOUD! Funciona."), GLOSSARIO)
    assert [w["text"] for w in out] == ["Olá,", "Claude!", "Funciona."]


def test_glossario_nao_toca_a_grafia_ja_certa_nem_reescreve_palavra_nao_declarada():
    entrada = _p("o Claude da Lia cloudy cloudflare")
    assert T.aplicar_glossario(entrada, GLOSSARIO) == entrada


def test_aplicar_glossario_nao_muda_a_lista_de_entrada():
    entrada = _p("eu uso o Cloud")
    copia = [dict(w) for w in entrada]
    T.aplicar_glossario(entrada, GLOSSARIO)
    assert entrada == copia


def test_cache_guarda_o_bruto_e_a_correcao_vale_para_qualquer_glossario(tmp_path):
    a = fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=())
    esp = Espiao(_p("eu uso o Cloud"))
    cache = tmp_path / "c"
    com = T.transcrever(a, cache_dir=cache, backend=esp, amb=amb(), glossario=GLOSSARIO)
    sem = T.transcrever(a, cache_dir=cache, backend=esp, amb=amb())
    assert esp.chamadas == 1
    assert com[3]["text"] == "Claude" and sem[3]["text"] == "Cloud"


# --- monotonizar --------------------------------------------------------------------------

def test_monotonizar_conserta_sobreposicao_regressao_e_fim_antes_do_inicio():
    ruim = [{"text": "a", "start": 1.0, "end": 1.6},
            {"text": "b", "start": 1.4, "end": 1.2},
            {"text": "c", "start": 1.1, "end": 2.0},
            {"text": "", "start": 2.0, "end": 2.1},
            {"text": "d", "start": 3.0, "end": 2.5}]
    out = T.monotonizar(ruim)
    assert [w["text"] for w in out] == ["a", "b", "c", "d"]
    for i, w in enumerate(out):
        assert w["end"] >= w["start"]
        if i:
            assert w["start"] >= out[i - 1]["start"]
            assert out[i - 1]["end"] <= w["start"]
    assert set(out[0]) == {"text", "start", "end"}


def test_monotonizar_aceita_lista_vazia():
    assert T.monotonizar([]) == []


# --- perfil "alinhamento" (W3.X A2) ----------------------------------------------------------
# O relógio do anúncio é transcrito do jeito da footage antiga (parakeet sem chunk, wav 16 kHz): medido no fixture,
# o chunk move fronteira em até 0,16 s. Os outros chamadores (gates, plano) seguem com o perfil padrão. Os dois
# perfis nunca se misturam no cache: a mesma fala transcrita de dois jeitos é guardada em dois arquivos.

class EspiaoComPerfil(Espiao):
    NOME = "espiao_perfil"
    PERFIS = ("padrao", "alinhamento")

    def __init__(self, palavras=None):
        super().__init__(palavras)
        self.perfis = []

    def transcrever(self, audio, *, amb, workdir, prompt="", idioma="pt", perfil="padrao"):
        self.perfis.append(perfil)
        return super().transcrever(audio, amb=amb, workdir=workdir, prompt=prompt, idioma=idioma)


class EspiaoSemPerfil(Espiao):
    """Backend que não distingue perfil (faster-whisper e Groq não fatiam como o parakeet): não recebe o argumento."""
    NOME = "espiao_sem_perfil"

    def transcrever(self, audio, *, amb, workdir, prompt="", idioma="pt"):
        return super().transcrever(audio, amb=amb, workdir=workdir, prompt=prompt, idioma=idioma)


def test_perfil_alinhamento_chega_ao_backend_que_o_declara(tmp_path):
    a = fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=())
    esp = EspiaoComPerfil()
    T.transcrever(a, cache_dir=tmp_path / "c", backend=esp, amb=amb(), perfil="alinhamento")
    T.transcrever(a, cache_dir=tmp_path / "c", backend=esp, amb=amb())
    assert esp.perfis == ["alinhamento", "padrao"]


def test_perfil_alinhamento_e_padrao_tem_caches_separados(tmp_path):
    a = fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=())
    cache = tmp_path / "c"
    sha = T.sha_do_conteudo(a)
    esp = EspiaoComPerfil()
    T.transcrever(a, cache_dir=cache, backend=esp, amb=amb(), perfil="alinhamento")
    T.transcrever(a, cache_dir=cache, backend=esp, amb=amb(), perfil="alinhamento")
    assert esp.chamadas == 1 and (cache / f"{sha}.alinhamento.json").is_file()
    assert not (cache / f"{sha}.json").exists(), "o perfil padrão não pode achar a transcrição do alinhamento"
    T.transcrever(a, cache_dir=cache, backend=esp, amb=amb())
    assert esp.chamadas == 2 and (cache / f"{sha}.json").is_file()


def test_backend_sem_perfil_recebe_a_chamada_de_sempre(tmp_path):
    a = fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=())
    esp = EspiaoSemPerfil()
    assert T.transcrever(a, cache_dir=tmp_path / "c", backend=esp, amb=amb(), perfil="alinhamento")
    assert esp.chamadas == 1


def test_perfil_desconhecido_e_erro_de_uso(tmp_path):
    a = fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=())
    with pytest.raises(ValueError, match="perfil"):
        T.transcrever(a, cache_dir=tmp_path / "c", backend=Espiao(), amb=amb(), perfil="rapido")
