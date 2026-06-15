---
name: video-ads-machine
description: Gera video ads com avatar IA a partir de um roteiro anotado + voz real. Use quando o pedido for criar/montar video de anuncio com avatar (HeyGen), legenda, lettering, PiP e trilha, em 9:16 e 1:1. Triggers: video ad, criar anuncio em video, avatar HeyGen, video ads machine, montar reel/criativo de video.
---

# Video Ads Machine

Pipeline: roteiro anotado + voz REAL gravada -> avatar IA -> legenda + lettering + PiP + trilha -> sai em 9:16 (stories/reels) e 1:1 (feed).

## PRIMEIRO DE TUDO: Setup (onboarding obrigatorio)

Antes de gerar qualquer video, RODE o preflight e conduza o usuario a instalar o que falta:

```
vam doctor
```

O `doctor` checa e instrui a instalacao de:

1. **Obrigatorio:** `ffmpeg`, um backend de alinhamento de legenda (`parakeet-mlx` no Apple Silicon ou `faster-whisper` no resto), e a chave `HEYGEN_API_KEY` no `.env`.
2. **Plugins / skill:** confirme que a skill `video-ads-machine` esta instalada (via marketplace ou `git`).
3. **MCPs opcionais:** se o usuario quiser notificacao de progresso no WhatsApp, oriente instalar/conectar o **MCP uazapi**; se o roteiro vier de Google Sheets, oriente o **acesso Google** (OAuth). Sao OPCIONAIS: nao bloqueiam a geracao.

NAO prossiga pra geracao enquanto o `doctor` apontar itens `[FALTA]`. Mostre ao usuario o comando exato de instalacao de cada item pendente e re-rode `vam doctor` ate passar.

## Config

Copie `config.example.yaml` -> `config.yaml` (marca, avatar_id, formatos) e `.env.example` -> `.env` (chaves). Nenhum dos dois vai pro git.

## Fluxo

1. Roteiro anotado (YAML em `examples/roteiro.example.yaml` ou Google Sheet): cada cena tem fala, fase (Hook/Body/CTA), tipo de cena, lettering, b-roll, zoom, PiP.
2. Voz real do Thales/locutor gravada lendo as falas (gera o avatar via HeyGen, audio-input).
3. `vam build <roteiro>` (roadmap) monta tudo nos dois formatos. Hoje ja funciona `vam caption` (engine de legenda validado).

## Regras de qualidade
- Voz SEMPRE real (TTS e o tell de IA).
- Legenda verbatim do roteiro (nunca transcricao crua).
- Auditar o video INTEIRO (varredura frame a frame), nunca frames isolados, antes de entregar.
