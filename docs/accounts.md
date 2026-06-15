# Contas e ferramentas

## Obrigatorio
- **HeyGen** (pago): gera o avatar a partir da voz real. Crie seu avatar e pegue a API key em `app.heygen.com` (Settings > API). Ponha em `HEYGEN_API_KEY` no `.env`.
- **ffmpeg** (gratis, local): `brew install ffmpeg` (mac) / `apt install ffmpeg` (linux) / `choco install ffmpeg` (win).
- **Backend de legenda** (gratis, local): `parakeet-mlx` no Apple Silicon, ou `faster-whisper` no resto.

## Opcional
- **Google Sheets API** (gratis): so se o roteiro vier de planilha. OAuth (client id/secret no `.env`). Senao, use roteiro YAML local.
- **uazapi** (pago): notificacao de progresso no WhatsApp. `UAZAPI_*` no `.env`.
- **Chrome** (gratis): lettering avancado.

## Musica
Nao incluimos faixas com direitos. Use a sua (royalty-free / CC0) e aponte em `config.yaml > music.file`.

## HeyGen ToS
O uso do avatar segue os termos da HeyGen. Este projeto nao distribui avatares nem vozes.
