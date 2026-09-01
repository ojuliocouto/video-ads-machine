#!/usr/bin/env python3
"""Verifica os assets de um brief e, se faltar o avatar, monta a instrução para
gerar via HeyGen (engine Avatar V).

Este módulo NÃO chama nenhuma API: só detecta arquivos no disco e monta
mensagens/instruções. A geração real do avatar só acontece se o usuário
confirmar, fora deste script, com a própria chave HeyGen.

Uso via import:
    from check_assets import missing, offer_avatar_generation
"""
import os


def missing(brief: dict) -> list:
    """Retorna a lista de caminhos de assets do brief que NÃO existem no disco.

    Espera brief["assets"] com chaves opcionais: avatar (str), voz (str),
    logo (str), brolls (list de str). Uma chave ausente significa que aquele
    asset não foi declarado para este brief (por exemplo, um reel sem
    b-roll), então ela não entra na checagem. Uma chave presente mas com
    caminho que não existe no disco conta como faltando.
    """
    assets = (brief or {}).get("assets") or {}
    result = []

    for key in ("avatar", "voz", "logo"):
        path = assets.get(key)
        if path and not os.path.exists(path):
            result.append(path)

    for path in assets.get("brolls") or []:
        if path and not os.path.exists(path):
            result.append(path)

    return result


def offer_avatar_generation(roteiro_path: str, voz_path: str) -> str:
    """Monta a mensagem/instrução oferecendo gerar o avatar faltante via HeyGen.

    NÃO chama a API HeyGen aqui: apenas monta a instrução. A chamada real só
    deve acontecer com confirmação explícita do usuário, usando a chave
    HEYGEN_API_KEY dele (nunca commitada).
    """
    return (
        "Avatar ausente para este brief.\n"
        f"Roteiro: {roteiro_path}\n"
        f"Voz: {voz_path}\n"
        "Gere um talking-head com lip-sync no HeyGen usando a engine Avatar V "
        "(a que entrega o lip-sync realista) a partir da sua voz, e salve o "
        "resultado como avatar.mp4 na pasta do projeto. Requer sua "
        "HEYGEN_API_KEY e um avatar_id do HeyGen, ambos seus e nunca "
        "commitados. Veja o README para o passo a passo.\n"
        "Esta etapa e OPCIONAL: a skill so oferece a geracao, nunca chama a "
        "API sem a sua confirmacao explicita."
    )
