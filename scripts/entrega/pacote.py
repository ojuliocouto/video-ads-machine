"""O pacote da entrega: `entrega/entrega.json`, o que foi entregue e por que pôde sair.

Só monta com o `gate_entrega` PASS (laudo PASS, aprovação vigente, nota 8 ou mais, os três amarrados ao sha256 do
arquivo final). O manifesto guarda o sha256 de cada peça para quem receber conferir que é a mesma que os gates
mediram: o final, a prévia de WhatsApp, o laudo, a nota e as folhas de contato.

A entrega do produto é a PASTA `entrega/` (não há envio automático para o aluno: Drive e WhatsApp são decisão dele,
seção 9 do plano). `abrir` mostra a pasta no gerenciador de arquivos, quando há um.
"""
import hashlib
import subprocess
import sys
from pathlib import Path

from projeto import status


class EntregaBloqueada(RuntimeError):
    """O gate_entrega não passou: nada foi montado."""


def _sha(caminho):
    h = hashlib.sha256()
    with open(str(caminho), "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _peca(pj, caminho):
    return {"arquivo": pj.relativo(caminho), "sha256": _sha(caminho), "bytes": Path(caminho).stat().st_size}


def manifesto(pj):
    """O caminho do manifesto da entrega."""
    return pj.entrega_dir / "entrega.json"


def montar(pj, gate, agora=None):
    """Grava entrega/entrega.json e devolve o dict. EntregaBloqueada se `gate` (o do gate_entrega) não passou."""
    if gate.get("resultado") != "PASS":
        raise EntregaBloqueada(gate.get("motivo") or "o gate_entrega não passou")
    nota = status.ler_json(pj.nota)
    laudo = status.ler_json(pj.laudo)
    d = {"versao": 1, "projeto": pj.slug, "entregue_em": agora or status.instante(),
         "final": _peca(pj, pj.final_9x16),
         "previa": _peca(pj, pj.final_whatsapp) if pj.final_whatsapp.is_file() else None,
         "laudo": dict(_peca(pj, pj.laudo), veredito=laudo["veredito"]),
         "nota": dict(_peca(pj, pj.nota), nota=nota["nota"], rodada=nota["rodada"]),
         "folhas": [_peca(pj, f) for f in sorted(pj.folhas_dir.glob("*.png"))] if pj.folhas_dir.is_dir() else [],
         "gate_entrega": gate}
    status.escrever_json_atomico(manifesto(pj), d)
    return d


def abrir(pasta):
    """Mostra a pasta no gerenciador de arquivos (macOS `open`, Linux `xdg-open`). Falha é silenciosa: é conveniência."""
    cmd = ["open", str(pasta)] if sys.platform == "darwin" else ["xdg-open", str(pasta)]
    try:
        subprocess.run(cmd, capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        pass
