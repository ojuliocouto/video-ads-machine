#!/usr/bin/env python3
"""APOSENTADO (12/07/2026). Este script usava o fluxo /v2/video/generate = AVATAR COMUM,
sem o engine Avatar V. O avatar comum tem lip-sync ruim (a boca não bate com a fala).

Avatar V é REGRA OBRIGATÓRIA da skill: é o engine que traz REALIDADE pro avatar.
Todo avatar agora é gerado SÓ por heygen_av5.py (engine avatar_v, endpoint /v3/videos).

Este arquivo virou stub de propósito: qualquer chamada falha alto, pra ninguém (humano
ou agente) gerar avatar comum por engano seguindo doc/memória antiga.
"""
import sys, os

BASE = os.path.dirname(os.path.abspath(__file__))

def main():
    args = sys.argv[1:]
    cmd = " ".join(args) if args else "<sem args>"
    sys.exit(
        "BLOQUEADO: heygen_avatar.py está APOSENTADO (usava avatar comum /v2, sem Avatar V).\n"
        "Avatar V é obrigatório (traz realidade pro avatar). Use o gerador oficial:\n\n"
        f"  python3 {os.path.join(BASE, 'heygen_av5.py')} gerar <audio.mp3> <avatar_id> [saida.mp4]\n"
        f"  python3 {os.path.join(BASE, 'heygen_av5.py')} status <video_id> [saida.mp4]\n\n"
        f"(você chamou: heygen_avatar.py {cmd})")

if __name__ == "__main__":
    main()
