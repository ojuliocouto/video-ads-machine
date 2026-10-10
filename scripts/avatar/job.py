"""avatar/job.json: o job pago do HeyGen que ainda não voltou, para a rede cair sem custar de novo.

O HeyGen cobra quando o job é ACEITO (o submit), não quando o vídeo chega. Se a rede cai no poll e o
`video_id` só existe na memória do processo, rodar `vam avatar` de novo paga outro job. Por isso o
`video_id` é gravado LOGO depois do submit e o `vam avatar` com job pendente RETOMA o poll.

    {"versao": 1, "video_id": "...", "engine": "avatar_v", "avatar_id": "...",
     "voz_sha256": "<sha da voz/limpo.mp3 que gerou o job>", "criado_em": "<ISO 8601>",
     "estado": "pendente" | "concluido" | "falhou" | "substituido"}

Só `pendente` retoma. `falhou` (o HeyGen respondeu failed) e `substituido` (o aluno importou um avatar
com --existente) liberam um submit novo. Um job de OUTRA voz (a voz limpa mudou) não é retomado: o
avatar daquela voz não serve para esta.
"""
from projeto import status

PENDENTE, CONCLUIDO, FALHOU, SUBSTITUIDO = "pendente", "concluido", "falhou", "substituido"
VERSAO = 1


def caminho(pj):
    return pj.avatar_dir / "job.json"


def ler(pj):
    """O job gravado, ou None se não há (ou se o arquivo está ilegível: nesse caso não adivinha)."""
    try:
        d = status.ler_json(caminho(pj))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and d.get("video_id") else None


def gravar(pj, video_id, engine, avatar_id, voz_sha256, agora=None):
    d = {"versao": VERSAO, "video_id": video_id, "engine": engine, "avatar_id": avatar_id,
         "voz_sha256": voz_sha256, "criado_em": agora or status.instante(), "estado": PENDENTE}
    status.escrever_json_atomico(caminho(pj), d)
    return d


def marcar(pj, estado):
    d = ler(pj)
    if d is None:
        return None
    d["estado"] = estado
    status.escrever_json_atomico(caminho(pj), d)
    return d


def pendente(pj, voz_sha256):
    """O job pendente DESTA voz, ou None. Job de outra voz não conta."""
    d = ler(pj)
    if d and d.get("estado") == PENDENTE and d.get("voz_sha256") == voz_sha256:
        return d
    return None


def pendente_de_outra_voz(pj, voz_sha256):
    d = ler(pj)
    return bool(d and d.get("estado") == PENDENTE and d.get("voz_sha256") != voz_sha256)
