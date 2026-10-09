"""W2.C: cliente HeyGen v3. HTTP, ffmpeg e relógio são injetados: zero rede, zero custo."""
import json
import re
from pathlib import Path

import pytest

from avatar import heygen_cliente as H

RAIZ = Path(__file__).resolve().parent.parent.parent
CHAVE = "hg_chave_secreta_de_teste_987654"
AVATAR_ID = "avatar_fake_0001"


def resp(obj, status=200, headers=None):
    return (status, dict(headers or {}), json.dumps(obj).encode("utf-8"))


class HttpFalso:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    def __call__(self, metodo, url, headers, corpo, timeout):
        self.chamadas.append({"metodo": metodo, "url": url, "headers": dict(headers or {}),
                              "corpo": corpo, "timeout": timeout})
        r = self.respostas.pop(0)
        return r(metodo, url) if callable(r) else r


class Relogio:
    def __init__(self):
        self.t = 0.0
        self.dormidas = []

    def agora(self):
        return self.t

    def dormir(self, s):
        self.dormidas.append(s)
        self.t += s


def cliente(respostas, relogio=None, executar=None):
    relogio = relogio or Relogio()
    http = HttpFalso(respostas)
    c = H.ClienteHeyGen(CHAVE, http=http, dormir=relogio.dormir, agora=relogio.agora,
                        executar=executar)
    return c, http, relogio


# --- engine -------------------------------------------------------------------------------------

def test_engine_padrao_e_avatar_v():
    assert H.resolver_engine(None, {}) == "avatar_v"
    assert H.resolver_engine("avatar_v", {}) == "avatar_v"


def test_engine_diferente_sem_override_e_bloqueado():
    with pytest.raises(H.EngineBloqueado) as e:
        H.resolver_engine("avatar_iv", {})
    assert "HEYGEN_ENGINE_OVERRIDE" in str(e.value)
    # override de outro engine não libera o pedido
    with pytest.raises(H.EngineBloqueado):
        H.resolver_engine("avatar_iv", {"HEYGEN_ENGINE_OVERRIDE": "avatar_iii"})


def test_engine_override_exato_libera_com_aviso_em_tela(capsys):
    assert H.resolver_engine("avatar_iv", {"HEYGEN_ENGINE_OVERRIDE": "avatar_iv"}) == "avatar_iv"
    assert "AVISO" in capsys.readouterr().out


def test_override_sem_pedido_e_ignorado_com_aviso(capsys):
    assert H.resolver_engine(None, {"HEYGEN_ENGINE_OVERRIDE": "avatar_iv"}) == "avatar_v"
    assert "AVISO" in capsys.readouterr().out


def test_payload_do_video_usa_avatar_v_e_o_aspecto_do_projeto():
    c, http, _ = cliente([resp({"data": {"video_id": "vid_1", "status": "waiting"}})])
    assert c.criar_video(AVATAR_ID, "asset_9", aspecto="9:16") == "vid_1"
    ch = http.chamadas[0]
    assert (ch["metodo"], ch["url"]) == ("POST", "https://api.heygen.com/v3/videos")
    corpo = json.loads(ch["corpo"])
    assert corpo == {"type": "avatar", "avatar_id": AVATAR_ID, "audio_asset_id": "asset_9",
                     "aspect_ratio": "9:16", "resolution": "1080p",
                     "engine": {"type": "avatar_v"}}
    assert ch["headers"]["x-api-key"] == CHAVE
    assert ch["headers"]["Content-Type"] == "application/json"


def test_aspecto_vem_do_projeto():
    assert H.aspecto_do_projeto({"formato": "9x16"}) == "9:16"
    assert H.aspecto_do_projeto({"formato": "1x1"}) == "1:1"
    assert H.aspecto_do_projeto({"formato": "4x5"}) == "4:5"
    assert H.aspecto_do_projeto({}) == "9:16"          # padrão
    assert H.aspecto_do_projeto(None) == "9:16"
    with pytest.raises(ValueError):
        H.aspecto_do_projeto({"formato": "21x9"})


def test_aspecto_do_projeto_chega_no_payload():
    c, http, _ = cliente([resp({"data": {"video_id": "v"}})])
    c.criar_video(AVATAR_ID, "a", aspecto=H.aspecto_do_projeto({"formato": "1x1"}))
    assert json.loads(http.chamadas[0]["corpo"])["aspect_ratio"] == "1:1"


# --- áudio e upload -----------------------------------------------------------------------------

def test_wav_vira_mp3_antes_do_upload(tmp_path):
    wav = tmp_path / "voz.wav"
    wav.write_bytes(b"RIFFxxxx")
    argvs = []

    def ffmpeg(argv, **kw):
        argvs.append(list(argv))
        Path(argv[-1]).write_bytes(b"ID3mp3")
        return 0, ""

    c, _, _ = cliente([], executar=ffmpeg)
    mp3 = c.preparar_audio(wav, pasta_tmp=tmp_path / "tmp")
    assert mp3.suffix == ".mp3" and mp3.read_bytes() == b"ID3mp3"
    assert len(argvs) == 1
    a = argvs[0]
    assert a[0] == "ffmpeg" and "-i" in a and str(wav) == a[a.index("-i") + 1]
    assert a[-1] == str(mp3)
    assert CHAVE not in " ".join(a)


def test_mp3_nao_chama_ffmpeg(tmp_path):
    mp3 = tmp_path / "voz.mp3"
    mp3.write_bytes(b"ID3")

    def ffmpeg(argv, **kw):
        raise AssertionError("não devia converter mp3")

    c, _, _ = cliente([], executar=ffmpeg)
    assert c.preparar_audio(mp3, pasta_tmp=tmp_path) == mp3


def test_falha_na_conversao_nao_vaza_nem_segue(tmp_path):
    wav = tmp_path / "voz.wav"
    wav.write_bytes(b"RIFF")
    c, _, _ = cliente([], executar=lambda argv, **kw: (1, "erro do ffmpeg"))
    with pytest.raises(H.HeyGenErro) as e:
        c.preparar_audio(wav, pasta_tmp=tmp_path)
    assert "ffmpeg" in str(e.value)


def test_audio_inexistente(tmp_path):
    c, _, _ = cliente([])
    with pytest.raises(H.HeyGenErro):
        c.preparar_audio(tmp_path / "nao.mp3", pasta_tmp=tmp_path)


def test_upload_e_multipart_em_v3_assets(tmp_path):
    mp3 = tmp_path / "voz.mp3"
    mp3.write_bytes(b"ID3\x00\x01conteudo-de-audio")
    c, http, _ = cliente([resp({"data": {"asset_id": "ast_77", "url": "https://x/a.mp3",
                                         "mime_type": "audio/mpeg", "size_bytes": 17}})])
    assert c.upload_audio(mp3) == "ast_77"
    ch = http.chamadas[0]
    assert (ch["metodo"], ch["url"]) == ("POST", "https://api.heygen.com/v3/assets")
    ct = ch["headers"]["Content-Type"]
    assert ct.startswith("multipart/form-data; boundary=")
    assert ch["headers"]["x-api-key"] == CHAVE
    assert b'name="file"' in ch["corpo"] and b'filename="voz.mp3"' in ch["corpo"]
    assert b"audio/mpeg" in ch["corpo"] and b"conteudo-de-audio" in ch["corpo"]
    assert ct.split("boundary=")[1].encode() in ch["corpo"]


def test_upload_acima_de_32_mb_e_recusado_antes_de_subir(tmp_path):
    grande = tmp_path / "voz.mp3"
    with open(str(grande), "wb") as f:
        f.truncate(H.LIMITE_UPLOAD_BYTES + 1)
    c, http, _ = cliente([])
    with pytest.raises(H.HeyGenErro):
        c.upload_audio(grande)
    assert http.chamadas == []


def test_upload_sem_asset_id_na_resposta(tmp_path):
    mp3 = tmp_path / "voz.mp3"
    mp3.write_bytes(b"x")
    c, _, _ = cliente([resp({"data": {}})])
    with pytest.raises(H.HeyGenErro):
        c.upload_audio(mp3)


# --- poll, teto e 429 ---------------------------------------------------------------------------

def test_poll_a_cada_10_s_ate_completar():
    seq = [resp({"data": {"status": "pending"}}), resp({"data": {"status": "processing"}}),
           resp({"data": {"status": "processing"}}),
           resp({"data": {"status": "completed", "video_url": "https://cdn/x.mp4", "duration": 55.3}})]
    c, http, rel = cliente(seq)
    d = c.aguardar_video("vid_1")
    assert d["video_url"] == "https://cdn/x.mp4" and d["duration"] == 55.3
    assert rel.dormidas == [10, 10, 10]
    assert all(ch["url"] == "https://api.heygen.com/v3/videos/vid_1" and ch["metodo"] == "GET"
               for ch in http.chamadas)


def test_intervalo_menor_que_10_s_e_recusado():
    c, _, _ = cliente([])
    with pytest.raises(ValueError):
        c.aguardar_video("vid_1", intervalo=3)


def test_teto_de_30_minutos():
    c, http, rel = cliente([resp({"data": {"status": "processing"}})] * 400)
    with pytest.raises(H.HeyGenTimeout):
        c.aguardar_video("vid_1")
    assert 1790 <= sum(rel.dormidas) <= 1800
    assert min(rel.dormidas) >= 10


def test_job_falho_levanta_com_codigo_e_mensagem():
    c, _, _ = cliente([resp({"data": {"status": "failed", "failure_code": "MOVIO_PAYMENT_INSUFFICIENT_CREDIT",
                                      "failure_message": "sem crédito"}})])
    with pytest.raises(H.HeyGenFalhou) as e:
        c.aguardar_video("vid_1")
    assert e.value.codigo == "MOVIO_PAYMENT_INSUFFICIENT_CREDIT"
    assert "sem crédito" in str(e.value)


def test_429_tem_um_retry_com_backoff_do_retry_after():
    c, http, rel = cliente([resp({"error": {"code": "rate_limit_exceeded"}}, 429, {"Retry-After": "7"}),
                            resp({"data": {"video_id": "v"}})])
    assert c.criar_video(AVATAR_ID, "a") == "v"
    assert len(http.chamadas) == 2
    assert rel.dormidas == [7]


def test_429_sem_retry_after_usa_backoff_padrao():
    c, http, rel = cliente([resp({}, 429), resp({"data": {"video_id": "v"}})])
    c.criar_video(AVATAR_ID, "a")
    assert rel.dormidas == [H.BACKOFF_429_S]


def test_segundo_429_nao_tenta_de_novo():
    c, http, rel = cliente([resp({}, 429), resp({}, 429), resp({"data": {"video_id": "v"}})])
    with pytest.raises(H.HeyGenErro) as e:
        c.criar_video(AVATAR_ID, "a")
    assert e.value.status == 429
    assert len(http.chamadas) == 2


# --- download e fluxo completo ------------------------------------------------------------------

def test_download_nao_manda_a_chave_para_a_url_presignada(tmp_path):
    c, http, _ = cliente([lambda m, u: (200, {}, b"MP4DATA")])
    saida = tmp_path / "pasta" / "av.mp4"
    c.baixar("https://cdn.exemplo/x.mp4?assinatura=abc", saida)
    assert saida.read_bytes() == b"MP4DATA"
    ch = http.chamadas[0]
    assert "x-api-key" not in {k.lower() for k in ch["headers"]}


def test_gerar_avatar_fluxo_completo(tmp_path, capsys):
    wav = tmp_path / "voz.wav"
    wav.write_bytes(b"RIFF")

    def ffmpeg(argv, **kw):
        Path(argv[-1]).write_bytes(b"mp3")
        return 0, ""

    seq = [resp({"data": {"asset_id": "ast_1", "url": "u", "mime_type": "audio/mpeg", "size_bytes": 3}}),
           resp({"data": {"video_id": "vid_9", "status": "waiting"}}),
           resp({"data": {"status": "processing"}}),
           resp({"data": {"status": "completed", "video_url": "https://cdn/a.mp4", "duration": 41.2}}),
           (200, {}, b"VIDEO")]
    c, http, _ = cliente(seq, executar=ffmpeg)
    saida = tmp_path / "out" / "avatar.mp4"
    r = c.gerar_avatar(wav, AVATAR_ID, saida, projeto={"formato": "9x16"})
    assert saida.read_bytes() == b"VIDEO"
    assert r == {"video_id": "vid_9", "saida": str(saida), "duracao_s": 41.2, "engine": "avatar_v"}
    urls = [(ch["metodo"], ch["url"]) for ch in http.chamadas]
    assert urls[0] == ("POST", "https://api.heygen.com/v3/assets")
    assert urls[1] == ("POST", "https://api.heygen.com/v3/videos")
    assert CHAVE not in capsys.readouterr().out


# --- chave nunca vaza ---------------------------------------------------------------------------

def test_erro_http_que_ecoa_a_chave_sai_mascarado():
    c, _, _ = cliente([resp({"error": {"message": "chave %s invalida" % CHAVE}}, 401)])
    with pytest.raises(H.HeyGenErro) as e:
        c.criar_video(AVATAR_ID, "a")
    assert CHAVE not in str(e.value) and CHAVE not in repr(e.value)
    assert "401" in str(e.value)


def test_repr_e_str_do_cliente_nao_trazem_a_chave():
    c, _, _ = cliente([])
    assert CHAVE not in repr(c) and CHAVE not in str(c)


def test_chave_do_ambiente_e_do_env_da_raiz(tmp_path):
    raiz = tmp_path / "repo"
    raiz.mkdir()
    (raiz / ".env").write_text("HEYGEN_API_KEY=%s\n" % CHAVE, encoding="utf-8")
    assert H.carregar_chave(env={}, raiz=raiz) == CHAVE
    # a variável de ambiente manda sobre o .env
    assert H.carregar_chave(env={"HEYGEN_API_KEY": "outra_chave_de_teste"}, raiz=raiz) == "outra_chave_de_teste"


def test_chave_nunca_vem_de_dados_nem_de_outro_lugar(tmp_path):
    raiz = tmp_path / "repo"
    (raiz / "_local" / "dados").mkdir(parents=True)
    (raiz / "_local" / "dados" / ".env").write_text("HEYGEN_API_KEY=%s\n" % CHAVE, encoding="utf-8")
    with pytest.raises(H.HeyGenSemChave) as e:
        H.carregar_chave(env={}, raiz=raiz)
    assert CHAVE not in str(e.value)
    assert ".env" in str(e.value)


def test_nenhum_argv_do_ffmpeg_leva_a_chave(tmp_path):
    wav = tmp_path / "v.wav"
    wav.write_bytes(b"x")
    vistos = []

    def ffmpeg(argv, **kw):
        vistos.append(" ".join(argv))
        Path(argv[-1]).write_bytes(b"m")
        return 0, ""

    c, _, _ = cliente([], executar=ffmpeg)
    c.preparar_audio(wav, pasta_tmp=tmp_path)
    assert vistos and all(CHAVE not in v for v in vistos)


# --- sem /v2, wrapper e CLI ---------------------------------------------------------------------

def test_nenhum_endpoint_v2_no_codigo():
    alvos = sorted((RAIZ / "scripts" / "avatar").glob("*.py")) + [RAIZ / "scripts" / "heygen_av5.py"]
    assert len(alvos) >= 5
    for arq in alvos:
        assert "/v2" not in arq.read_text(encoding="utf-8"), arq
        assert "v1/asset" not in arq.read_text(encoding="utf-8"), arq


def test_wrapper_tem_ate_40_linhas():
    linhas = (RAIZ / "scripts" / "heygen_av5.py").read_text(encoding="utf-8").splitlines()
    assert len(linhas) <= 40


def test_cli_gerar_com_a_mesma_assinatura(tmp_path):
    mp3 = tmp_path / "v.mp3"
    mp3.write_bytes(b"x")
    seq = [resp({"data": {"asset_id": "a"}}), resp({"data": {"video_id": "v"}}),
           resp({"data": {"status": "completed", "video_url": "https://c/x", "duration": 1}}),
           (200, {}, b"V")]
    c, http, _ = cliente(seq)
    saida = tmp_path / "s.mp4"
    assert H.main_cli(["gerar", str(mp3), AVATAR_ID, str(saida)], cliente=c) == 0
    assert saida.read_bytes() == b"V"
    assert json.loads(http.chamadas[1]["corpo"])["engine"] == {"type": "avatar_v"}


def test_cli_engine_diferente_e_bloqueado_sem_override(tmp_path, capsys):
    mp3 = tmp_path / "v.mp3"
    mp3.write_bytes(b"x")
    c, http, _ = cliente([])
    assert H.main_cli(["gerar", str(mp3), AVATAR_ID, str(tmp_path / "s.mp4"), "avatar_iv"],
                      cliente=c, env={}) == 1
    assert "BLOQUEADO" in capsys.readouterr().err
    assert http.chamadas == []          # nada foi gasto


def test_cli_status_baixa_video_existente(tmp_path):
    seq = [resp({"data": {"status": "completed", "video_url": "https://c/x", "duration": 2}}),
           (200, {}, b"V2")]
    c, _, _ = cliente(seq)
    saida = tmp_path / "st.mp4"
    assert H.main_cli(["status", "vid_abc", str(saida)], cliente=c) == 0
    assert saida.read_bytes() == b"V2"


def test_cli_sem_argumentos_mostra_uso(capsys):
    assert H.main_cli([], cliente=cliente([])[0]) == 2
    assert "gerar" in capsys.readouterr().err
