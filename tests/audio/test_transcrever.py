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


def amb(sistema="Darwin", arquitetura="arm64", executaveis=(), modulos=(), env=None):
    """Ambiente falso. `executaveis` e `modulos` são o que EXISTE nessa máquina."""
    return T.Ambiente(
        sistema=sistema, arquitetura=arquitetura, env=dict(env or {}),
        which=lambda nome: (f"/falso/bin/{nome}" if nome in executaveis else None),
        importavel=lambda nome: nome in modulos)


# --- ordem de backend ---------------------------------------------------------------------

def test_ordem_da_nuvem_e_uma_constante_mistral_depois_groq():
    assert T.ORDEM_NUVEM == ("mistral", "groq")
    assert T.ORDEM == ("mistral", "groq", "faster_whisper")


CHAVES = {"MISTRAL_API_KEY": "mstrl_falsa", "GROQ_API_KEY": "gsk_falsa"}


@pytest.mark.parametrize("sistema,arquitetura", [("Darwin", "arm64"), ("Darwin", "x86_64"),
                                                 ("Windows", "AMD64"), ("Linux", "x86_64")])
def test_com_as_duas_chaves_a_mistral_vence_e_o_resto_e_reserva(sistema, arquitetura):
    a = amb(sistema=sistema, arquitetura=arquitetura, modulos=("faster_whisper",), env=CHAVES)
    assert T.escolher_backend(a).NOME == "mistral"
    assert T.backends_disponiveis(a) == ["mistral", "groq", "faster_whisper"]


def test_so_vale_o_backend_cuja_chave_existe():
    assert T.escolher_backend(amb(env={"GROQ_API_KEY": "gsk_falsa"})).NOME == "groq"
    assert T.escolher_backend(amb(env={"MISTRAL_API_KEY": "mstrl_falsa"})).NOME == "mistral"
    assert T.escolher_backend(amb(modulos=("faster_whisper",))).NOME == "faster_whisper"
    with pytest.raises(T.SemTranscritor):
        T.escolher_backend(amb())


def test_vam_transcritor_poe_um_da_nuvem_na_frente():
    a = amb(env={**CHAVES, "VAM_TRANSCRITOR": "groq"})
    assert T.ordem_dos_backends(a) == ["groq", "mistral", "faster_whisper"]
    assert T.escolher_backend(a).NOME == "groq"
    b = amb(env={**CHAVES, "VAM_TRANSCRITOR": " MISTRAL "})
    assert T.escolher_backend(b).NOME == "mistral"


def test_vam_transcritor_sem_a_chave_do_escolhido_cai_no_proximo_com_chave():
    a = amb(env={"GROQ_API_KEY": "gsk_falsa", "VAM_TRANSCRITOR": "mistral"})
    assert T.escolher_backend(a).NOME == "groq"


def test_vam_transcritor_invalido_e_erro_claro():
    with pytest.raises(T.SemTranscritor, match="VAM_TRANSCRITOR"):
        T.escolher_backend(amb(env={**CHAVES, "VAM_TRANSCRITOR": "outro"}))


def test_backend_que_nao_existe_na_ordem_e_erro_de_uso():
    with pytest.raises(ValueError, match="outro_motor"):
        T.escolher_backend(amb(modulos=("faster_whisper",)), preferido="outro_motor")


def test_groq_sem_chave_ou_com_chave_vazia_nao_conta():
    assert T.backends_disponiveis(amb(env={})) == []
    assert T.backends_disponiveis(amb(env={"GROQ_API_KEY": "   ", "MISTRAL_API_KEY": ""})) == []


def test_backend_pedido_que_nao_existe_na_maquina_falha_citando_o_nome():
    with pytest.raises(T.SemTranscritor, match="faster_whisper"):
        T.escolher_backend(amb(), preferido="faster_whisper")
    with pytest.raises(ValueError, match="nada"):
        T.escolher_backend(amb(), preferido="nada")


def test_backend_pedido_e_respeitado_quando_disponivel():
    a = amb(modulos=("faster_whisper",), env={"GROQ_API_KEY": "gsk_falsa"})
    assert T.escolher_backend(a, preferido="groq").NOME == "groq"
    assert T.escolher_backend(a, preferido="faster_whisper").NOME == "faster_whisper"


# --- sem nenhum backend: UMA mensagem com o comando de instalação ------------------------

@pytest.mark.parametrize("sistema,arquitetura", [("Darwin", "arm64"), ("Windows", "AMD64"), ("Linux", "x86_64")])
def test_sem_nenhum_backend_levanta_uma_mensagem_que_manda_criar_a_chave_da_groq(sistema, arquitetura):
    with pytest.raises(T.SemTranscritor) as e:
        T.escolher_backend(amb(sistema=sistema, arquitetura=arquitetura))
    msg = str(e.value)
    assert "console.groq.com" in msg and "GROQ_API_KEY" in msg and "MISTRAL_API_KEY" in msg and ".env" in msg
    assert "Curso → Skill" in msg
    assert "GRÁTIS" in msg and "opcional" in msg
    assert "pip install faster-whisper" in msg
    assert "\n" not in msg.strip()              # uma mensagem só, em uma linha
    assert "Traceback" not in msg


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


# --- escolha automática: Groq primeiro, faster-whisper opcional de reserva ---------------------------

from audio.backends import faster_whisper as FW  # noqa: E402
from audio.backends import groq as G  # noqa: E402
from audio.backends import mistral as M  # noqa: E402

PALAVRAS_LOCAL = [{"text": "local", "start": 0.1, "end": 0.5}]
PALAVRAS_NUVEM = [{"text": "nuvem", "start": 0.2, "end": 0.6}]
PALAVRAS_MISTRAL = [{"text": "mistral", "start": 0.3, "end": 0.7}]


@pytest.fixture
def motores(monkeypatch):
    """Troca o `transcrever` dos dois backends reais por falsos que contam chamadas."""
    chamadas = {"groq": 0, "faster_whisper": 0, "mistral": 0}
    estado = {"groq_falha": None, "mistral_falha": None}

    def mistral(audio, *, amb, workdir, prompt="", idioma="pt", **_):
        chamadas["mistral"] += 1
        if estado["mistral_falha"]:
            raise M.ErroMistral(estado["mistral_falha"])
        return [dict(p) for p in PALAVRAS_MISTRAL]

    def groq(audio, *, amb, workdir, prompt="", idioma="pt", **_):
        chamadas["groq"] += 1
        if estado["groq_falha"]:
            raise G.ErroGroq(estado["groq_falha"])
        return [dict(p) for p in PALAVRAS_NUVEM]

    def local(audio, *, amb, workdir, prompt="", idioma="pt", **_):
        chamadas["faster_whisper"] += 1
        return [dict(p) for p in PALAVRAS_LOCAL]

    monkeypatch.setattr(M, "transcrever", mistral)
    monkeypatch.setattr(G, "transcrever", groq)
    monkeypatch.setattr(FW, "transcrever", local)
    return chamadas, estado


def _wav(tmp_path):
    return fx.tom_com_pausas(tmp_path / "a.wav", dur=1.0, pausas=())


AMBOS = dict(modulos=("faster_whisper",), env={"GROQ_API_KEY": "gsk_falsa"})


def test_automatico_usa_a_groq_e_nao_toca_o_local(tmp_path, motores):
    chamadas, _ = motores
    palavras = T.transcrever(_wav(tmp_path), cache_dir=tmp_path / "c", amb=amb(**AMBOS))
    assert [p["text"] for p in palavras] == ["nuvem"] and chamadas == {"groq": 1, "faster_whisper": 0, "mistral": 0}


def test_groq_que_falha_cai_no_local_com_aviso_no_stderr(tmp_path, motores, capsys):
    chamadas, estado = motores
    estado["groq_falha"] = "sem internet"
    palavras = T.transcrever(_wav(tmp_path), cache_dir=tmp_path / "c", amb=amb(**AMBOS))
    assert [p["text"] for p in palavras] == ["local"] and chamadas == {"groq": 1, "faster_whisper": 1, "mistral": 0}
    err = capsys.readouterr().err
    assert "groq falhou" in err and "sem internet" in err and "faster_whisper" in err
    assert "gsk_falsa" not in err


def test_groq_que_falha_sem_local_vira_uma_mensagem_com_o_conserto(tmp_path, motores):
    _, estado = motores
    estado["groq_falha"] = "sem internet"
    with pytest.raises(T.SemTranscritor) as e:
        T.transcrever(_wav(tmp_path), cache_dir=tmp_path / "c", amb=amb(env={"GROQ_API_KEY": "gsk_falsa"}))
    assert "sem internet" in str(e.value) and "pip install faster-whisper" in str(e.value)
    assert not list((tmp_path / "c").rglob("*.json")), "falha não grava cache"


def test_sem_chave_o_automatico_vai_direto_ao_local(tmp_path, motores):
    chamadas, _ = motores
    palavras = T.transcrever(_wav(tmp_path), cache_dir=tmp_path / "c", amb=amb(modulos=("faster_whisper",)))
    assert [p["text"] for p in palavras] == ["local"] and chamadas["groq"] == 0


def test_backend_pedido_pelo_nome_nao_tem_reserva(tmp_path, motores):
    chamadas, estado = motores
    estado["groq_falha"] = "429"
    with pytest.raises(G.ErroGroq):
        T.transcrever(_wav(tmp_path), cache_dir=tmp_path / "c", amb=amb(**AMBOS), backend="groq")
    assert chamadas["faster_whisper"] == 0


def test_mistral_vence_quando_as_duas_chaves_existem_e_nao_toca_o_resto(tmp_path, motores):
    chamadas, _ = motores
    palavras = T.transcrever(_wav(tmp_path), cache_dir=tmp_path / "c", amb=amb(modulos=("faster_whisper",), env=CHAVES))
    assert [p["text"] for p in palavras] == ["mistral"]
    assert chamadas == {"groq": 0, "faster_whisper": 0, "mistral": 1}


def test_mistral_que_falha_cai_na_groq_com_uma_linha_no_stderr(tmp_path, motores, capsys):
    chamadas, estado = motores
    estado["mistral_falha"] = "Mistral respondeu 429: sem capacidade"
    palavras = T.transcrever(_wav(tmp_path), cache_dir=tmp_path / "c", amb=amb(env=CHAVES))
    assert [p["text"] for p in palavras] == ["nuvem"] and chamadas == {"groq": 1, "faster_whisper": 0, "mistral": 1}
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1 and "mistral falhou" in err[0] and "tentando groq" in err[0]
    assert "mstrl_falsa" not in err[0]
    assert json.loads(next((tmp_path / "c").glob("*.json")).read_text(encoding="utf-8"))["backend"] == "groq"


def test_mistral_sem_palavra_com_tempo_cai_na_groq(tmp_path, motores, capsys):
    chamadas, estado = motores
    estado["mistral_falha"] = "a resposta da Mistral tem texto mas não tem palavras com tempo"
    palavras = T.transcrever(_wav(tmp_path), cache_dir=tmp_path / "c", amb=amb(env=CHAVES))
    assert [p["text"] for p in palavras] == ["nuvem"]
    assert "palavras com tempo" in capsys.readouterr().err


def test_as_duas_nuvens_caem_e_o_local_assume(tmp_path, motores):
    chamadas, estado = motores
    estado["mistral_falha"], estado["groq_falha"] = "fora", "fora"
    palavras = T.transcrever(_wav(tmp_path), cache_dir=tmp_path / "c", amb=amb(modulos=("faster_whisper",), env=CHAVES))
    assert [p["text"] for p in palavras] == ["local"] and chamadas == {"groq": 1, "faster_whisper": 1, "mistral": 1}


def test_vam_transcritor_groq_pula_a_mistral(tmp_path, motores):
    chamadas, _ = motores
    T.transcrever(_wav(tmp_path), cache_dir=tmp_path / "c", amb=amb(env={**CHAVES, "VAM_TRANSCRITOR": "groq"}))
    assert chamadas["mistral"] == 0 and chamadas["groq"] == 1


# --- o ambiente real lê o .env do repo (é lá que o aluno põe as chaves) -------------------------

def test_ambiente_real_completa_o_ambiente_com_o_dotenv_da_raiz(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("GROQ_API_KEY=gsk_do_dotenv\nVAM_WHISPER_MODELO=small\n", encoding="utf-8")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("VAM_WHISPER_MODELO", raising=False)
    real = T.Ambiente.real(raiz=tmp_path)
    assert real.env["GROQ_API_KEY"] == "gsk_do_dotenv" and real.env["VAM_WHISPER_MODELO"] == "small"
    assert G.disponivel(real)


def test_variavel_do_ambiente_vence_o_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("GROQ_API_KEY=gsk_do_dotenv\n", encoding="utf-8")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_da_variavel")
    assert T.Ambiente.real(raiz=tmp_path).env["GROQ_API_KEY"] == "gsk_da_variavel"


def test_sem_dotenv_o_ambiente_real_so_tem_o_do_processo(tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert not G.disponivel(T.Ambiente.real(raiz=tmp_path))


# --- passos que CORTAM: a Groq vai na frente da Mistral (tempo de palavra mais preciso) ----------------------

def test_no_corte_a_groq_vai_na_frente_quando_as_duas_chaves_existem():
    a = amb(modulos=("faster_whisper",), env=CHAVES)
    assert T.ordem_dos_backends(a, corte=True) == ["groq", "mistral", "faster_whisper"]
    assert T.escolher_backend(a, corte=True).NOME == "groq"
    assert T.escolher_backend(a).NOME == "mistral", "fora do corte vale a ordem da constante"


def test_no_corte_sem_chave_da_groq_usa_a_mistral():
    assert T.escolher_backend(amb(env={"MISTRAL_API_KEY": "mstrl_falsa"}), corte=True).NOME == "mistral"


def test_vam_transcritor_explicito_vale_tambem_no_corte():
    a = amb(env={**CHAVES, "VAM_TRANSCRITOR": "mistral"})
    assert T.escolher_backend(a, corte=True).NOME == "mistral"


def test_transcrever_com_corte_chama_a_groq_primeiro_e_devolve_o_nome(tmp_path, motores):
    chamadas, _ = motores
    palavras, nome = T.transcrever_detalhado(_wav(tmp_path), cache_dir=tmp_path / "c", amb=amb(env=CHAVES), corte=True)
    assert nome == "groq" and [p["text"] for p in palavras] == ["nuvem"] and chamadas["mistral"] == 0


def test_o_nome_do_backend_sobrevive_ao_cache(tmp_path, motores):
    wav, cache = _wav(tmp_path), tmp_path / "c"
    T.transcrever_detalhado(wav, cache_dir=cache, amb=amb(env=CHAVES))
    palavras, nome = T.transcrever_detalhado(wav, cache_dir=cache, amb=amb(env=CHAVES))
    assert nome == "mistral" and [p["text"] for p in palavras] == ["mistral"]
