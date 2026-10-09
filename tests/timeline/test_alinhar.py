"""timeline.alinhar (W3.A): UMA transcrição e UM alinhamento por avatar.

Antes daqui, o avatar era transcrito três vezes num build (o overlay pelo `hyperframes transcribe`, uma vez
por formato, e a footage pelo parakeet) e cada motor casava o roteiro com a fala por um algoritmo próprio. A
deriva entre os dois relógios chegou a 1,07 s no fim de um anúncio de 2 min (defeito 20 do plano).

O que este arquivo prova:
  - o casamento roteiro x fala é o da FOOTAGE (o relógio que vale), agora num lugar só, e a footage o usa;
  - a transcrição sai do `audio.transcrever` (W1.C), uma chamada por alinhamento, com cache por sha do avatar;
  - o alinhamento gravado guarda o sha do avatar e devolve a grafia do ROTEIRO, nunca a do ASR;
  - o sha do arquivo de alinhamento é o que a timeline cita (`fontes.alinhamento_sha256`).
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from audio import transcrever as T
from audio.backends import parakeet as PK
from footage import blocos as BL
from tests.footage.test_blocos import GOLDEN_ALINHAR
from timeline import alinhar as AL

RAIZ = Path(__file__).resolve().parents[2]
SCRIPTS = RAIZ / "scripts"


def _sha(caminho):
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


# ==================================================================================== o casamento

@pytest.mark.parametrize("nome", sorted(GOLDEN_ALINHAR))
def test_casar_e_o_algoritmo_da_footage_nos_goldens_do_original(nome):
    """Os goldens do produzir_roteiro original passam pelo `casar` (via os tokens juntados da footage)."""
    g = GOLDEN_ALINHAR[nome]
    pk = BL.tokens_do_parakeet(g["json"])
    out = AL.casar(pk, g["narr"], g["audio_dur"])
    assert json.loads(json.dumps(out)) == g["palavras"]


@pytest.mark.parametrize("nome", sorted(GOLDEN_ALINHAR))
def test_a_footage_casa_pelo_alinhar_da_timeline(nome, monkeypatch):
    """Uma implementação só: a footage chama o `casar` daqui (trocar o casar troca a footage)."""
    g = GOLDEN_ALINHAR[nome]
    chamadas = []
    original = AL.casar

    def espia(*a, **k):
        chamadas.append(1)
        return original(*a, **k)

    monkeypatch.setattr(AL, "casar", espia)
    assert json.loads(json.dumps(BL.alinhar_palavras(g["json"], g["narr"], g["audio_dur"]))) == g["palavras"]
    assert chamadas == [1]


def _parakeet(sentencas):
    """JSON no formato do parakeet: [[(texto do token, início, fim), ...] por sentença]."""
    return {"sentences": [{"text": "".join(t for t, _, _ in toks), "start": toks[0][1], "end": toks[-1][2],
                           "tokens": [{"text": t, "start": s, "end": e} for t, s, e in toks]}
                          for toks in sentencas]}


def test_palavras_do_audio_transcrever_dao_o_mesmo_relogio_que_os_tokens_crus():
    """A transcrição única (audio.transcrever) junta os tokens como a footage juntava: mesmo relógio."""
    dados = _parakeet([
        [(" Ag", 5.6, 5.68), ("ora", 5.68, 5.8), (" eu", 5.84, 5.92), (" constru", 5.92, 6.2), ("o", 6.2, 6.3)],
        [(" Sabe", 9.6, 9.9), (" qual", 9.92, 10.0), (" é", 10.08, 10.12), (" o", 10.16, 10.2),
         (" melhor?", 10.24, 10.6)],
    ])
    narr = "Agora eu construo Sabe qual é o melhor?".split()
    cru = BL.alinhar_palavras(dados, narr, 11.0)
    via_transcrever = AL.casar(AL.palavras_do_asr(PK.palavras_da_saida(dados)), narr, 11.0)
    assert via_transcrever == cru


def test_primeira_palavra_sem_par_encosta_na_seguinte():
    """'Minha' que o ASR ouviu como 'My': 0,18 s antes da primeira palavra casada (é o a0 do fixture)."""
    asr = [(0.4, 0.56, "My"), (0.8, 1.12, "skill"), (1.2, 1.36, "de")]
    out = AL.casar(asr, ["Minha", "skill", "de"], 5.0)
    assert out[0] == (pytest.approx(0.62), 0.8, "Minha")
    assert out[1] == (0.8, 1.12, "skill")


def test_cauda_sem_par_ancora_no_fim_real_do_audio():
    asr = [(0.0, 0.3, "um"), (0.4, 0.7, "dois")]
    out = AL.casar(asr, ["um", "dois", "tres"], 9.0)
    assert out[-1] == (pytest.approx(8.95), 9.0, "tres")


def test_palavra_do_meio_sem_par_ocupa_o_vao_entre_as_vizinhas():
    asr = [(0.0, 0.3, "um"), (0.4, 0.7, "xis"), (1.0, 1.2, "tres")]
    out = AL.casar(asr, ["um", "dois", "tres"], 2.0)
    assert out[1] == (0.3, 1.0, "dois")


def test_sem_nenhum_par_cai_no_passo_fixo_e_a_cauda_no_fim():
    out = AL.casar([], ["a", "b"], 3.0)
    assert out[0] == (pytest.approx(2.77), pytest.approx(2.95), "a")
    assert out[1] == (pytest.approx(2.95), 3.0, "b")


def test_a_grafia_e_sempre_a_do_roteiro():
    asr = [(0.0, 0.3, "meu"), (0.4, 0.7, "Cloud")]
    out = AL.casar(asr, ["meu", "Claude."], 1.0)
    assert [p[2] for p in out] == ["meu", "Claude."]


# ==================================================================================== uma transcrição

class _Backend(object):
    """Backend falso no contrato do audio.transcrever: conta quantas vezes transcreveu de verdade."""
    NOME = "falso"

    def __init__(self, palavras):
        self.palavras = palavras
        self.chamadas = []

    def transcrever(self, audio, *, amb, workdir, prompt="", idioma="pt"):
        self.chamadas.append(str(audio))
        return [dict(p) for p in self.palavras]


ASR = [{"text": "Agora", "start": 0.5, "end": 0.8}, {"text": "eu", "start": 0.9, "end": 1.0},
       {"text": "construo", "start": 1.1, "end": 1.5}]
NARR = ["Agora", "eu", "construo."]


@pytest.fixture
def espioes(monkeypatch):
    """Espia o audio.transcrever e o subprocess: transcrição conta, subprocess é proibido."""
    backend = _Backend(ASR)
    chamadas = {"transcrever": [], "subprocess": []}
    original = T.transcrever

    def transcrever(audio, **kw):
        chamadas["transcrever"].append(str(audio))
        kw["backend"] = backend
        return original(audio, **kw)

    def proibido(*a, **k):
        chamadas["subprocess"].append(a[0] if a else k.get("args"))
        raise AssertionError("o alinhamento não chama subprocesso (transcrição e duração vêm injetadas)")

    monkeypatch.setattr(T, "transcrever", transcrever)
    monkeypatch.setattr(subprocess, "run", proibido)
    monkeypatch.setattr(subprocess, "Popen", proibido)
    return backend, chamadas


def _avatar(tmp_path, conteudo=b"avatar-falso"):
    p = tmp_path / "projeto" / "avatar" / "avatar.mp4"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(conteudo)
    return p


def test_um_alinhamento_e_uma_chamada_ao_audio_transcrever(tmp_path, espioes):
    backend, chamadas = espioes
    av = _avatar(tmp_path)
    al = AL.alinhar(av, NARR, cache_dir=tmp_path / "projeto" / "render" / "cache_asr",
                    raiz=tmp_path / "projeto", duracao=lambda p: 2.0)
    assert chamadas["transcrever"] == [str(av)]
    assert backend.chamadas == [str(av)]
    assert chamadas["subprocess"] == []
    assert [p["t"] for p in al["palavras"]] == NARR


def test_o_cache_por_sha_do_avatar_segura_a_segunda_transcricao(tmp_path, espioes):
    """Mesmo avatar = mesma transcrição: o backend roda UMA vez, qualquer que seja o número de builds."""
    backend, chamadas = espioes
    av = _avatar(tmp_path)
    cache = tmp_path / "projeto" / "render" / "cache_asr"
    a = AL.alinhar(av, NARR, cache_dir=cache, raiz=tmp_path / "projeto", duracao=lambda p: 2.0)
    b = AL.alinhar(av, NARR, cache_dir=cache, raiz=tmp_path / "projeto", duracao=lambda p: 2.0)
    assert len(chamadas["transcrever"]) == 2 and len(backend.chamadas) == 1
    assert a == b
    assert (cache / (_sha(av) + ".json")).is_file()


def test_alinhamento_guarda_avatar_relativo_sha_duracao_e_a_transcricao(tmp_path, espioes):
    av = _avatar(tmp_path)
    al = AL.alinhar(av, NARR, cache_dir=tmp_path / "c", raiz=tmp_path / "projeto", duracao=lambda p: 2.0)
    assert al["versao"] == 1
    assert al["avatar"] == "avatar/avatar.mp4"
    assert al["avatar_sha256"] == _sha(av)
    assert al["duracao_audio_s"] == 2.0
    assert [w["text"] for w in al["transcricao"]] == ["Agora", "eu", "construo"]
    assert al["palavras"][0] == {"t": "Agora", "s": 0.5, "e": 0.8}
    assert AL.palavras(al) == [(0.5, 0.8, "Agora"), (0.9, 1.0, "eu"), (1.1, 1.5, "construo.")]


def test_glossario_chega_ao_audio_transcrever(tmp_path, espioes, monkeypatch):
    recebidos = []
    original = T.transcrever

    def transcrever(audio, **kw):
        recebidos.append(kw.get("glossario"))
        return original(audio, **kw)

    monkeypatch.setattr(T, "transcrever", transcrever)
    gl = {"termos": [{"grafia": "Claude", "variantes": ["Cloud"]}]}
    AL.alinhar(_avatar(tmp_path), NARR, cache_dir=tmp_path / "c", raiz=tmp_path / "projeto",
               duracao=lambda p: 2.0, glossario=gl)
    assert recebidos == [gl]


def test_sem_transcritor_a_mensagem_do_audio_transcrever_chega_inteira(tmp_path, monkeypatch):
    def sem(audio, **kw):
        raise T.SemTranscritor("Nenhum transcritor disponível. Instale um com `pip install parakeet-mlx`.")

    monkeypatch.setattr(T, "transcrever", sem)
    with pytest.raises(AL.ErroAlinhamento, match="pip install parakeet-mlx"):
        AL.alinhar(_avatar(tmp_path), NARR, cache_dir=tmp_path / "c", raiz=tmp_path / "projeto",
                   duracao=lambda p: 2.0)


def test_avatar_ausente_e_erro_claro(tmp_path):
    with pytest.raises(AL.ErroAlinhamento, match="avatar"):
        AL.alinhar(tmp_path / "nao_existe.mp4", NARR, cache_dir=tmp_path / "c", duracao=lambda p: 2.0)


# ==================================================================================== arquivo

def test_gravar_devolve_o_sha_do_arquivo_e_ler_confere(tmp_path, espioes):
    al = AL.alinhar(_avatar(tmp_path), NARR, cache_dir=tmp_path / "c", raiz=tmp_path / "projeto",
                    duracao=lambda p: 2.0)
    destino = tmp_path / "projeto" / "render" / "alinhamento.json"
    sha = AL.gravar(al, destino)
    assert sha == _sha(destino)
    assert AL.ler(destino, sha) == al
    with pytest.raises(AL.ErroAlinhamento, match="sha256"):
        AL.ler(destino, "0" * 64)


def test_gravar_e_deterministico_e_atomico(tmp_path, espioes):
    al = AL.alinhar(_avatar(tmp_path), NARR, cache_dir=tmp_path / "c", raiz=tmp_path / "projeto",
                    duracao=lambda p: 2.0)
    a = AL.gravar(al, tmp_path / "a.json")
    b = AL.gravar(json.loads(json.dumps(al)), tmp_path / "b.json")
    assert a == b
    assert not list(tmp_path.glob("*.tmp"))


def test_o_alinhamento_gravado_nao_carrega_caminho_absoluto(tmp_path, espioes):
    """O sha do alinhamento é a prova da mesma transcrição: caminho da máquina não pode mudá-lo."""
    al = AL.alinhar(_avatar(tmp_path), NARR, cache_dir=tmp_path / "c", raiz=tmp_path / "projeto",
                    duracao=lambda p: 2.0)
    AL.gravar(al, tmp_path / "a.json")
    assert str(tmp_path) not in (tmp_path / "a.json").read_text(encoding="utf-8")


# ==================================================================================== higiene

def test_importar_os_modulos_da_timeline_nao_executa_nada(tmp_path):
    codigo = ("import subprocess, sys\n"
              "sys.path.insert(0, %r)\n"
              "def boom(*a, **k):\n"
              "    raise AssertionError('subprocess no import')\n"
              "subprocess.Popen = boom\n"
              "subprocess.run = boom\n"
              "import timeline.alinhar, timeline.construir\n"
              "import os\n"
              "print('IMPORTOU', sorted(os.listdir('.')))\n") % str(SCRIPTS)
    r = subprocess.run([sys.executable, "-c", codigo], cwd=str(tmp_path), capture_output=True, text=True,
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "IMPORTOU []"


ARQUIVOS_DA_UNIDADE = ("scripts/timeline/alinhar.py", "scripts/timeline/construir.py", "scripts/gates/gate_relogio.py",
                       "tests/timeline/test_alinhar.py", "tests/timeline/test_construir.py",
                       "tests/gates/test_gate_relogio.py")


def test_zero_travessao_e_nenhum_nome_de_cliente_nos_arquivos_da_unidade():
    # o padrão é montado em pedaços para este arquivo não se acusar
    termos = ["Tha" + "les", "Jhe" + "ni", "J[uú]" + "lio", r"\bOC" + r"C\b", "Lar" + "ay", "Br[ií]" + "gida",
              "Opera[cç][aã]o Cl" + "aude", "Marco Au" + "r", r"\bjh" + r"1[0-9]\b", "vaib" + "hav", "Sob" + "ral",
              chr(0x2014), chr(0x2013)]
    proibidos = re.compile("|".join(termos), re.IGNORECASE)
    achados = []
    for rel in ARQUIVOS_DA_UNIDADE:
        p = RAIZ / rel
        for n, linha in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if proibidos.search(linha):
                achados.append(f"{rel}:{n}: {linha.strip()[:80]}")
    assert not achados, "\n".join(achados)
