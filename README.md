# Video Ads Machine

Pipeline open-source pra gerar **video ads com avatar de IA** a partir de um roteiro anotado e da **voz real** do apresentador. Roteiro + voz -> avatar (HeyGen) -> legenda + lettering + PiP + trilha -> saida em **9:16** (stories/reels) e **1:1** (feed).

> Filosofia: voz sempre real (TTS e o "tell" de IA), legenda verbatim do roteiro, e o video e auditado frame a frame antes de sair.

## Status
`v0.1` - engine de legenda (format-aware: 9:16 e 1:1, com escala por formato) + onboarding/preflight prontos e funcionando. Modulos de avatar, alinhamento, lettering, PiP e compose completo em construcao (ver Roadmap).

## Comece aqui (setup)
```bash
pip install -e .            # + um backend de legenda:
pip install parakeet-mlx    # Apple Silicon (mac M1+)
# ou
pip install '.[whisper]'    # Windows / Linux / mac Intel

cp .env.example .env                 # ponha sua HEYGEN_API_KEY
cp config.example.yaml config.yaml   # ponha seu avatar_id / marca

vam doctor                  # preflight: diz exatamente o que falta instalar
```

## Contas / ferramentas
| Recurso | Custo | Papel |
|---|---|---|
| HeyGen | Pago | gera o avatar (voz real) |
| ffmpeg | Gratis | render (local) |
| parakeet-mlx OU faster-whisper | Gratis | alinhar a legenda |
| Google Sheets API | Gratis | opcional, roteiro via planilha |
| uazapi | Pago | opcional, notificacao WhatsApp |

Voce traz suas proprias chaves. Nada de credencial no repo.

## Uso (hoje)
```bash
# queima legenda num video, no formato escolhido
vam caption base.mp4 saida.mp4 --align palavras.json --style tay --format 1x1
```
`palavras.json` = `[["voce",0.0,0.4],["prefere",0.4,0.8], ...]` (palavra, inicio, fim em segundos).

## Formatos
- **9:16** (1080x1920): legenda sobre o peito, padrao validado.
- **1:1** (1080x1080): video encaixado com fundo borrado nas laterais; legenda e fonte escalam proporcional.

## Roadmap
- [ ] `vam build`: pipeline completo roteiro -> video.
- [ ] Provider HeyGen (avatar via audio-input).
- [ ] Alinhamento parakeet/whisper plugavel.
- [ ] Lettering, PiP e compose (trilha + 1.2x) nos dois formatos.
- [ ] Roteiro via Google Sheet ou YAML.
- [ ] Compose por cena no 1:1 (b-roll preenchendo o quadrado).

## Licenca
Apache 2.0. Fontes bundladas sob OFL (ver NOTICE).
