"""Paridade da FOOTAGE (W0.3): o produzir_roteiro sobre a fixture tem que dar o que o golden guardou.

A W2.B quebra `produzir_roteiro.py` (1.730 linhas, executa tudo no import) em 10 módulos.
O que prova que o comportamento não mudou:

  - o argv de TODO subprocess (ffmpeg, ffprobe, o alinhamento), normalizado: os mesmos
    comandos, e na mesma ordem. Cada filtro do ffmpeg é comparado caractere a caractere;
  - o plano de ritmo (`_ritmo.json`) e o `timing.json`;
  - o framemd5 dos quadros decodificados da `footage_1x` e o md5 do áudio decodificado. É o
    que pega a mudança que o argv não mostra (um PNG de moldura, um asset, um arredondamento
    dentro do ffmpeg).

A footage roda como o `build_composite` a roda: CAP=0, BAKE=0, VAM_AVATAR/ROTEIRO/INSERTS_JSON.
Ver o docstring de `capturar.py` para o que o harness fixa (VAM_PARALELO=1, VAM_SPLIT_BIAS,
ASR gravado).

Única diferença aceita da W2.B: o caminho do executável do parakeet (normalizado em
`<PARAKEET>`). A medição de enquadramento NÃO é coberta (VAM_SPLIT_BIAS fixo): consertar o
defeito 2 não mexe neste golden.

W3.A (relógio único): a mesma footage roda também LENDO a timeline.json (`VAM_TIMELINE`). Ela não alinha
mais (o alinhamento mudou de fase: `argv/timeline.jsonl`) e tem que sair IGUAL à do golden: mesmo plano, mesmo
timing, mesmos quadros, mesmo áudio, e os mesmos comandos menos os 3 do alinhamento. O golden é o de
`$VAM_PARIDADE_GOLDEN` (padrão `$VAM_PARIDADE_MIDIA/golden`).

Para iterar na W2.B sem esperar o conjunto todo:
    VAM_PARIDADE_MIDIA=<pasta> bash scripts/dev/testar_limpo.sh --paridade -k footage
"""
import json

import pytest

from tests.paridade import capturar as C

pytestmark = pytest.mark.midia_real


@pytest.fixture(scope="module")
def midia():
    return C.exigir_midia()


@pytest.fixture(scope="module")
def golden(midia):
    arquivos, _hashes, manifesto = C.ler_golden(midia)
    return arquivos, manifesto


@pytest.fixture(scope="module")
def atual(midia):
    """A captura do motor DESTE working tree (uma vez só; o overlay divide o mesmo run)."""
    return C.capturar_memo(C.raiz_do_repo(), midia).arquivos


def _confere(atual, golden, prefixos):
    diffs = C.comparar(atual, golden, prefixos=prefixos)
    assert not diffs, "paridade da footage quebrada:\n" + "\n\n".join(diffs)


def test_a_fixture_exercita_os_tres_renderizadores_da_footage(atual):
    """Avatar (r_orig), tela dividida (r_split_tela) e tela cheia com moldura (r_insert_moldura).

    Se um dia o fixture perder um deles, a paridade deixa de cobrir aquele renderizador.
    """
    argv = atual["argv/footage.jsonl"]
    assert "zoompan=z='1.0+0.16*on/" in argv, "r_orig: zoom do avatar"
    assert "[c2][grad]overlay" in argv, "r_split_tela: degradê da emenda"
    assert "moldura_cheio_" in argv, "r_insert_moldura: moldura da tela cheia"
    assert "noise=alls=7" in argv and "colorspace=all=bt709" in argv, "grade final e tag bt709"
    assert "xfade=transition=" in argv and "concat=n=2" in argv, "cadeia mista: xfade na volta, concat no corte seco"
    ritmo = json.loads(atual["footage/ritmo.json"])
    assert {s.get("layout") for s in ritmo["segs"] if s["tipo"] == "insert"} >= {"split", "cheio"}


def test_a_footage_nao_chamou_a_medicao_de_enquadramento(atual):
    """VAM_SPLIT_BIAS fixo: o golden não depende do defeito 2 (medir_enquadramento a partir do DADOS)."""
    assert "medir_enquadramento" not in atual["argv/footage.jsonl"]


# --- argv --------------------------------------------------------------------------------

def test_argv_da_footage_mesmos_comandos(atual, golden):
    """Mesmo conjunto de comandos, em qualquer ordem (vale mesmo se a ordem mudar de propósito)."""
    arquivos, _ = golden
    diffs = C.comparar_sem_ordem(atual, arquivos, chaves=["argv/footage.jsonl"])
    assert not diffs, "a footage roda comandos diferentes dos do golden:\n" + "\n\n".join(diffs)


def test_argv_da_footage_mesma_ordem(atual, golden):
    """Mesmos comandos NA MESMA ORDEM. Depende de a footage honrar VAM_PARALELO=1 (pool de 1 worker)."""
    arquivos, _ = golden
    _confere(atual, arquivos, ("argv/footage.jsonl",))


# --- ritmo, tempo, quadros ----------------------------------------------------------------

def test_plano_de_ritmo_e_timing(atual, golden):
    arquivos, _ = golden
    _confere(atual, arquivos, ("footage/ritmo.json", "footage/timing.json"))


def test_quadros_e_audio_da_footage_1x(atual, golden):
    """framemd5 do vídeo decodificado e md5 do áudio decodificado, contra o golden.

    Depende do ffmpeg/libx264 da máquina: com outro ffmpeg que o do golden, os quadros
    podem mudar sem que o motor tenha mudado. Nesse caso PULA dizendo qual é a diferença
    (o argv, que não depende do ffmpeg, continua valendo nos outros testes).
    """
    arquivos, manifesto = golden
    aviso = C.conferir_toolchain(manifesto)
    if aviso:
        pytest.skip(f"toolchain diferente do golden ({aviso}): o framemd5 não é comparável. "
                    "Regenere o golden a partir do commit base nesta máquina.")
    _confere(atual, arquivos, ("footage/video.framemd5", "footage/audio.md5"))


# --- W3.A: a footage pela timeline é a mesma footage ----------------------------------------

ALINHAMENTO_DA_FOOTAGE = 3      # ffmpeg (wav), parakeet e ffprobe: o que a timeline passou a fazer uma vez só


def test_footage_pela_timeline_tem_o_mesmo_plano_e_o_mesmo_timing(atual, golden):
    arquivos, _ = golden
    assert "timeline/footage/ritmo.json" in atual, "a captura não rodou a footage pela timeline"
    for nome in ("ritmo.json", "timing.json"):
        assert atual[f"timeline/footage/{nome}"] == arquivos[f"footage/{nome}"], nome


def test_footage_pela_timeline_tem_os_mesmos_quadros_e_o_mesmo_audio(atual, golden):
    arquivos, manifesto = golden
    aviso = C.conferir_toolchain(manifesto)
    if aviso:
        pytest.skip(f"toolchain diferente do golden ({aviso}): o framemd5 não é comparável")
    for nome in ("video.framemd5", "audio.md5"):
        assert atual[f"timeline/footage/{nome}"] == arquivos[f"footage/{nome}"], nome


def test_footage_pela_timeline_roda_os_mesmos_comandos_menos_o_alinhamento(atual, golden):
    arquivos, _ = golden
    legado = arquivos["argv/footage.jsonl"].splitlines()
    alinhamento, resto = legado[:ALINHAMENTO_DA_FOOTAGE], legado[ALINHAMENTO_DA_FOOTAGE:]
    assert [json.loads(l)["argv"][0] for l in alinhamento] == ["ffmpeg", "<PARAKEET>", "ffprobe"]
    pela_timeline = atual["argv/timeline_footage.jsonl"].replace(C.SUFIXO_FOOTAGE_TIMELINE, "").splitlines()
    assert pela_timeline == resto
    assert "<PARAKEET>" not in atual["argv/timeline_footage.jsonl"]
