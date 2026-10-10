"""Cliente HeyGen v3 para o avatar com VOZ REAL (Avatar V travado).

Endpoints, conferidos em 09/10/2026 na documentação pública (docs.heygen.com redireciona para
developers.heygen.com):
  - Upload Asset   POST /v3/assets            multipart/form-data, campo `file`, até 32 MB
                   https://developers.heygen.com/reference/upload-asset
                   resposta: data.asset_id, data.url, data.mime_type, data.size_bytes
  - Create Video   POST /v3/videos            type=avatar, avatar_id, audio_asset_id (ou audio_url),
                   https://developers.heygen.com/reference/create-video       aspect_ratio, resolution,
                   engine = OBJETO {"type": "avatar_v"}; resposta data.video_id; 429 traz Retry-After
  - Get Video      GET  /v3/videos/{video_id} status pending|processing|completed|failed, video_url
                   https://developers.heygen.com/reference/get-video          (presignada), duration,
                   failure_code, failure_message
  - List Looks     GET  /v3/avatars/looks     ver avatar/listar.py
                   https://developers.heygen.com/reference/list-avatar-looks
  - Current User   GET  /v3/users/me          data.wallet.remaining_balance (ver avatar/custo.py)
                   https://developers.heygen.com/reference/get-current-user

NÃO confirmado na doc (a página buscada não menciona): a data em que o upload antigo e a listagem
de avatares da API v2 saem do ar (o plano fala em 31/10/2026). Por isso o código só usa v3.
O fluxo com audio_asset_id (em vez do audio_url do código antigo) segue a doc, mas nenhuma
chamada real foi feita nesta unidade (custo zero): a primeira geração de verdade é a prova da W6.

Regras que o código garante:
  - engine travado em avatar_v. Outro engine só com HEYGEN_ENGINE_OVERRIDE=<engine> IGUAL ao
    pedido, e sempre com aviso em tela.
  - o aspecto vem do projeto.json (`formato`: 9x16 padrão), nunca cravado.
  - WAV vira mp3 (ffmpeg) antes do upload.
  - poll a cada 10 s no mínimo, teto de 30 min; 429 tem 1 retry, esperando o Retry-After (ou 5 s).
  - o poll sobrevive a um tropeço de rede: falha de rede ou 5xx na consulta tem até 3 tentativas
    (espera 5 s e depois 10 s) antes de desistir. O job já foi pago no submit; por isso quem chama
    recebe o `video_id` em `ao_submeter` LOGO depois do submit e pode retomar sem pagar de novo
    (`status_e_baixar`, ou `vam avatar <slug> --retomar`).
  - a chave vem de HEYGEN_API_KEY ou do .env da RAIZ do repo; nunca de DADOS/.env. Ela vai só no
    header, nunca em argv, log ou exceção (toda mensagem passa por `_limpar`). A URL presignada do
    vídeo é baixada SEM a chave.

Tudo que toca o mundo é injetável (`http`, `executar`, `dormir`, `agora`): os testes não usam
rede nem ffmpeg.

CLI (este arquivo roda direto, e scripts/heygen_av5.py é o mesmo comando; o caminho do aluno é `vam avatar`):
    python3 scripts/avatar/heygen_cliente.py gerar <voz> <avatar_id> <saida> [engine]
    python3 scripts/avatar/heygen_cliente.py status <video_id> [saida]
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

API = "https://api.heygen.com"
MANDATORY_ENGINE = "avatar_v"
RESOLUCAO = "1080p"
POLL_INTERVALO_S = 10
POLL_TETO_S = 30 * 60
REDE_TENTATIVAS = 3          # tentativas de UMA consulta do poll antes de desistir
BACKOFF_REDE_S = 5           # espera antes da 2ª tentativa; dobra a cada falha (5 s, 10 s)
BACKOFF_429_S = 5
BACKOFF_429_MAX_S = 60
LIMITE_UPLOAD_BYTES = 32 * 1024 * 1024
TIMEOUT_HTTP_S = 120
ASPECTOS = {"9x16": "9:16", "1x1": "1:1", "4x5": "4:5"}
MIME_AUDIO = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac"}


class HeyGenErro(Exception):
    def __init__(self, mensagem, status=None, codigo=None):
        super().__init__(mensagem)
        self.status = status
        self.codigo = codigo


class HeyGenSemChave(HeyGenErro):
    pass


class HeyGenRede(HeyGenErro):
    """Falha de rede (sem resposta do HeyGen). O job que já foi aceito continua valendo."""


class EngineBloqueado(HeyGenErro):
    pass


class HeyGenTimeout(HeyGenErro):
    pass


class HeyGenFalhou(HeyGenErro):
    """O job terminou em `failed` do lado da HeyGen."""


# --- engine, aspecto, chave ---------------------------------------------------------------------

def resolver_engine(pedido, env=None):
    """Trava o engine em avatar_v. Só libera outro com HEYGEN_ENGINE_OVERRIDE igual ao pedido."""
    env = os.environ if env is None else env
    override = env.get("HEYGEN_ENGINE_OVERRIDE")
    if pedido and pedido != MANDATORY_ENGINE:
        if override != pedido:
            raise EngineBloqueado(
                "BLOQUEADO: Avatar V (engine '%s') é obrigatório: é o engine que traz realidade "
                "ao avatar (lip-sync). Você pediu '%s'. Se for MESMO necessário (ex: look que não "
                "suporta Avatar V), rode com HEYGEN_ENGINE_OVERRIDE=%s e assuma a perda de "
                "qualidade." % (MANDATORY_ENGINE, pedido, pedido))
        print("*** AVISO: engine '%s' via override explícito. Avatar V é o padrão obrigatório. ***" % pedido)
        return pedido
    if override and override != MANDATORY_ENGINE:
        print("*** AVISO: HEYGEN_ENGINE_OVERRIDE=%s ignorado (nenhum engine pedido; usando Avatar V). ***"
              % override)
    return MANDATORY_ENGINE


def aspecto_do_projeto(projeto):
    """'9x16' do projeto.json vira '9:16' da API. Sem formato: 9:16."""
    formato = (projeto or {}).get("formato", "9x16")
    if formato not in ASPECTOS:
        raise ValueError("formato %r sem aspecto de avatar (aceitos: %s)" % (formato, ", ".join(ASPECTOS)))
    return ASPECTOS[formato]


def carregar_chave(env=None, raiz=None):
    """HEYGEN_API_KEY da variável de ambiente ou do .env da RAIZ do repo. Nunca de DADOS."""
    env = os.environ if env is None else env
    chave = (env.get("HEYGEN_API_KEY") or "").strip()
    if not chave and raiz is not None:
        from onboarding.doctor import carregar_dotenv
        chave = (carregar_dotenv(Path(raiz) / ".env").get("HEYGEN_API_KEY") or "").strip()
    if not chave:
        raise HeyGenSemChave("HEYGEN_API_KEY não encontrada: ponha HEYGEN_API_KEY=... no arquivo .env "
                             "da raiz do repo (chave em app.heygen.com, Settings, API)")
    return chave


# --- HTTP e processo reais ----------------------------------------------------------------------

def http_real(metodo, url, headers, corpo, timeout):
    """(status, headers, bytes). Erro HTTP devolve o status; só falha de rede levanta."""
    pedido = urllib.request.Request(url, data=corpo, headers=dict(headers or {}), method=metodo)
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as r:
            return r.status, dict(r.headers.items()), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers.items()) if e.headers else {}, e.read()
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise HeyGenRede("sem rede ou HeyGen fora do ar (%s)" % getattr(e, "reason", e))


def executar_real(argv, timeout=600):
    try:
        p = subprocess.run([str(a) for a in argv], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           universal_newlines=True, timeout=timeout)
        return p.returncode, p.stdout or ""
    except subprocess.TimeoutExpired:
        return 124, "tempo esgotado"
    except OSError as e:
        return 127, str(e)


def _multipart(campo, nome_arquivo, mime, dados):
    limite = "vam" + uuid.uuid4().hex
    cab = ('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\n'
           'Content-Type: %s\r\n\r\n' % (limite, campo, nome_arquivo, mime)).encode("utf-8")
    return limite, cab + dados + ("\r\n--%s--\r\n" % limite).encode("utf-8")


# --- o cliente ----------------------------------------------------------------------------------

class ClienteHeyGen(object):
    def __init__(self, chave, http=None, executar=None, dormir=None, agora=None):
        if not chave:
            raise HeyGenSemChave("HEYGEN_API_KEY vazia")
        self._chave = chave
        self._http = http or http_real
        self._executar = executar or executar_real
        self._dormir = dormir or time.sleep
        self._agora = agora or time.monotonic

    def __repr__(self):
        return "ClienteHeyGen(chave=***)"

    __str__ = __repr__

    @classmethod
    def do_ambiente(cls, env=None, raiz=None, **kw):
        return cls(carregar_chave(env, raiz), **kw)

    def _limpar(self, texto):
        return str(texto).replace(self._chave, "***")

    def _erro(self, mensagem, status=None, codigo=None, cls=HeyGenErro):
        return cls(self._limpar(mensagem), status=status, codigo=codigo)

    def _requisitar(self, metodo, caminho, corpo=None, headers=None):
        """Chamada com a chave no header. 429: 1 retry depois do Retry-After (ou BACKOFF_429_S)."""
        url = caminho if caminho.startswith("http") else API + caminho
        cab = {"x-api-key": self._chave, "Accept": "application/json"}
        cab.update(headers or {})
        for tentativa in (1, 2):
            status, resp_h, bruto = self._http(metodo, url, cab, corpo, TIMEOUT_HTTP_S)
            if status != 429:
                break
            if tentativa == 2:
                raise self._erro("HeyGen respondeu 429 (limite de requisições) duas vezes em %s %s"
                                 % (metodo, caminho), 429, "rate_limit_exceeded")
            espera = BACKOFF_429_S
            for k, v in (resp_h or {}).items():
                if k.lower() == "retry-after":
                    try:
                        espera = max(1, min(BACKOFF_429_MAX_S, int(float(v))))
                    except ValueError:
                        pass
            self._dormir(espera)
        try:
            dados = json.loads(bruto.decode("utf-8", "replace")) if bruto else {}
        except ValueError:
            dados = {}
        if status >= 400 or (isinstance(dados, dict) and dados.get("error")):
            err = dados.get("error") if isinstance(dados, dict) else None
            err = err if isinstance(err, dict) else {"message": err}
            msg = err.get("message") or bruto[:300].decode("utf-8", "replace")
            raise self._erro("HeyGen HTTP %s em %s %s: %s" % (status, metodo, caminho, str(msg)[:300]),
                             status, err.get("code"))
        return dados if isinstance(dados, dict) else {}

    # --- áudio
    def preparar_audio(self, audio, pasta_tmp=None):
        """mp3/m4a/aac seguem como estão; WAV (e qualquer outro) vira mp3 mono antes do upload."""
        audio = Path(audio)
        if not audio.is_file():
            raise self._erro("áudio não existe: %s" % audio)
        if audio.suffix.lower() in MIME_AUDIO:
            return audio
        pasta = Path(pasta_tmp) if pasta_tmp else Path(tempfile.mkdtemp(prefix="vam-heygen-"))
        pasta.mkdir(parents=True, exist_ok=True)
        mp3 = pasta / (audio.stem + ".mp3")
        rc, saida = self._executar(["ffmpeg", "-y", "-v", "error", "-i", str(audio), "-vn", "-ac", "1",
                                    "-ar", "44100", "-b:a", "128k", str(mp3)])
        if rc != 0 or not mp3.is_file():
            raise self._erro("ffmpeg não converteu %s para mp3: %s" % (audio.name, saida.strip()[-200:]))
        return mp3

    def upload_audio(self, audio):
        """Sobe o áudio (multipart em POST /v3/assets) e devolve o asset_id."""
        audio = Path(audio)
        tamanho = audio.stat().st_size
        if tamanho > LIMITE_UPLOAD_BYTES:
            raise self._erro("áudio de %d MB passa do limite de 32 MB do upload" % (tamanho // (1 << 20)))
        mime = MIME_AUDIO.get(audio.suffix.lower(), "audio/mpeg")
        limite, corpo = _multipart("file", audio.name, mime, audio.read_bytes())
        d = self._requisitar("POST", "/v3/assets", corpo,
                             {"Content-Type": "multipart/form-data; boundary=" + limite})
        asset_id = (d.get("data") or {}).get("asset_id")
        if not asset_id:
            raise self._erro("upload sem asset_id na resposta: %s" % json.dumps(d)[:300])
        return asset_id

    # --- vídeo
    def criar_video(self, avatar_id, audio_asset_id, aspecto="9:16", engine=MANDATORY_ENGINE):
        payload = {"type": "avatar", "avatar_id": avatar_id, "audio_asset_id": audio_asset_id,
                   "aspect_ratio": aspecto, "resolution": RESOLUCAO, "engine": {"type": engine}}
        d = self._requisitar("POST", "/v3/videos", json.dumps(payload).encode("utf-8"),
                             {"Content-Type": "application/json"})
        video_id = (d.get("data") or {}).get("video_id")
        if not video_id:
            raise self._erro("sem video_id na resposta: %s" % json.dumps(d)[:300])
        return video_id

    def _consultar_video(self, video_id):
        """Uma consulta do poll, com até REDE_TENTATIVAS tentativas se a rede cai ou o HeyGen devolve 5xx."""
        for tentativa in range(1, REDE_TENTATIVAS + 1):
            try:
                return self._requisitar("GET", "/v3/videos/" + video_id).get("data") or {}
            except HeyGenErro as e:
                passageiro = isinstance(e, HeyGenRede) or (e.status is not None and e.status >= 500)
                if not passageiro or tentativa == REDE_TENTATIVAS:
                    raise
                espera = BACKOFF_REDE_S * (2 ** (tentativa - 1))
                print("      consulta falhou (%s): tentativa %d de %d, espero %d s"
                      % (self._limpar(e), tentativa, REDE_TENTATIVAS, espera), flush=True)
                self._dormir(espera)

    def aguardar_video(self, video_id, intervalo=POLL_INTERVALO_S, teto=POLL_TETO_S):
        """Consulta GET /v3/videos/{id} até `completed`. Devolve o `data`."""
        if intervalo < POLL_INTERVALO_S:
            raise ValueError("intervalo de poll abaixo de %d s não é aceito (rate limit)" % POLL_INTERVALO_S)
        t0 = self._agora()
        while True:
            data = self._consultar_video(video_id)
            st = data.get("status")
            print("      status=%s" % st, flush=True)
            if st == "completed":
                return data
            if st in ("failed", "error"):
                raise self._erro("job %s falhou: %s %s" % (video_id, data.get("failure_code"),
                                                           data.get("failure_message")),
                                 codigo=data.get("failure_code"), cls=HeyGenFalhou)
            if self._agora() - t0 + intervalo > teto:
                raise self._erro("timeout de %d min esperando o render de %s" % (teto // 60, video_id),
                                 cls=HeyGenTimeout)
            self._dormir(intervalo)

    def baixar(self, url, saida):
        """Baixa a URL presignada SEM a chave e grava por temporário + rename."""
        status, _, bruto = self._http("GET", url, {}, None, 300)
        if status != 200:
            raise self._erro("download do vídeo falhou (HTTP %s)" % status, status)
        saida = Path(saida)
        saida.parent.mkdir(parents=True, exist_ok=True)
        tmp = saida.with_name("." + saida.name + ".parte")
        tmp.write_bytes(bruto)
        os.replace(str(tmp), str(saida))
        return saida

    def usuario(self):
        """data de GET /v3/users/me (conta, plano e carteira)."""
        return self._requisitar("GET", "/v3/users/me").get("data") or {}

    def gerar_avatar(self, audio, avatar_id, saida, engine=None, projeto=None, env=None,
                     engine_resolvido=False, ao_submeter=None):
        """voz -> (mp3) -> upload -> job -> poll -> mp4. Devolve {video_id, saida, duracao_s, engine}.

        `ao_submeter(video_id, engine)` roda LOGO depois do submit (antes do poll): é onde quem chama grava
        o job pago, para uma queda de rede no poll não obrigar a pagar de novo."""
        eng = engine if engine_resolvido else resolver_engine(engine, env)
        aspecto = aspecto_do_projeto(projeto)
        print("[1/3] subindo o áudio...")
        asset_id = self.upload_audio(self.preparar_audio(audio))
        print("[2/3] disparando /v3/videos (avatar %s, engine %s, %s)..." % (avatar_id, eng, aspecto))
        video_id = self.criar_video(avatar_id, asset_id, aspecto, eng)
        print("      video_id = %s" % video_id)
        if ao_submeter is not None:
            ao_submeter(video_id, eng)
        print("[3/3] aguardando o render (checa a cada %d s)..." % POLL_INTERVALO_S)
        return self._finalizar(video_id, saida, eng)

    def _finalizar(self, video_id, saida, engine=MANDATORY_ENGINE):
        data = self.aguardar_video(video_id)
        self.baixar(data.get("video_url"), saida)
        print("BAIXADO %s (dur=%ss)" % (saida, data.get("duration")))
        return {"video_id": video_id, "saida": str(saida), "duracao_s": data.get("duration"),
                "engine": engine}

    def status_e_baixar(self, video_id, saida):
        return self._finalizar(video_id, saida)


# --- CLI ----------------------------------------------------------------------------------------

def main_cli(argv, cliente=None, env=None, raiz=None):
    """Retorna o código de saída: 0 ok, 1 falha, 2 uso."""
    a = list(argv)
    if not a or a[0] not in ("gerar", "status") or (a[0] == "gerar" and len(a) < 3) \
            or (a[0] == "status" and len(a) < 2):
        print(__doc__, file=sys.stderr)
        return 2
    try:
        if a[0] == "gerar":
            eng = resolver_engine(a[4] if len(a) > 4 else None, env)   # antes de chave e de gasto
            saida = a[3] if len(a) > 3 else _saida_padrao("avatar_av5.mp4")
            c = cliente or ClienteHeyGen.do_ambiente(env, raiz)
            c.gerar_avatar(a[1], a[2], saida, engine=eng, env=env, engine_resolvido=True)
        else:
            saida = a[2] if len(a) > 2 else _saida_padrao("avatar_%s.mp4" % a[1][:8])
            c = cliente or ClienteHeyGen.do_ambiente(env, raiz)
            c.status_e_baixar(a[1], saida)
        return 0
    except HeyGenErro as e:
        print(str(e), file=sys.stderr)
        return 1


def _saida_padrao(nome):
    import caminhos
    return str(Path(caminhos.DADOS) / "inputs" / nome)


if __name__ == "__main__":
    _RAIZ = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(_RAIZ / "scripts"))      # rodando o arquivo direto, `scripts/` não está no path
    sys.exit(main_cli(sys.argv[1:], raiz=_RAIZ))
