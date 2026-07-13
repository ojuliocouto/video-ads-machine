# Contas e ferramentas

Referencia rapida das contas e ferramentas. O passo a passo completo pra iniciante esta no [Guia do Aluno](GUIA-ALUNO.md).

## Obrigatorio

- **HeyGen**: gera o avatar de IA a partir da sua voz real.
  - **Conta:** a gratuita ja inclui 1 avatar proprio (Digital Twin). Um plano pago (Creator e acima) e opcional: serve pro editor do site e processamento prioritario, nao e necessario pra este pipeline.
  - **API key:** em `app.heygen.com`, aba **Space Settings > API**. Cole em `HEYGEN_API_KEY` no `.env`.
  - **Credito de API:** comprado a parte (pay-as-you-go) e SEPARADO do credito do plano. Sem credito de API, todo build falha, mesmo com o plano cheio. O `vam doctor` mostra quanto voce tem.
  - **Sem avatar ainda?** Rode `vam avatars` pra listar os avatares que a sua key enxerga (os seus e os prontos do HeyGen) e use um pronto pra testar. Veja o Guia do Aluno.
- **ffmpeg** (gratis, local): `brew install ffmpeg` (mac) / `sudo apt install ffmpeg` (linux) / `choco install ffmpeg` (windows). Precisa ter suporte a libass (as versoes normais tem: evite builds "minimal"/estaticas enxutas).
- **Backend de legenda** (gratis, local): `parakeet-mlx` no Apple Silicon, ou `faster-whisper` no resto. O `faster-whisper` baixa um modelo (~500 MB no tamanho "small") no primeiro build: e normal, so acontece uma vez.

## Opcional (avancado): upload automatico pro Google Drive

**Isto nao e necessario.** Por padrao, os videos finais ficam na pasta `build/` do seu projeto e voce sobe pro Drive na mao. So configure isto se quiser que o `vam build` suba os finais sozinho, direto pra uma pasta sua.

Pra ligar:
1. No `.env`: `GOOGLE_OAUTH_TOKEN_FILE=/caminho/para/seu_token.json`
2. No `config.yaml`: descomente `drive_folder` apontando pra sua pasta do Drive.

O arquivo de token e um JSON com escopo `drive.file`:

```json
{"access_token": "...", "refresh_token": "...", "client_id": "...", "client_secret": "..."}
```

Voce gera esse token rodando um fluxo OAuth do Google uma vez: criar um projeto no Google Cloud, ativar a Google Drive API, criar credenciais OAuth do tipo "app Desktop" e autorizar a sua conta. E um passo tecnico. **Se voce nao faz isso com conforto, pule o Drive:** deixe `drive_folder` comentado, pegue os finais na pasta `build/` e suba na mao. O `vam doctor` avisa se o token nao estiver utilizavel antes do build.

## Musica

O pipeline nao adiciona trilha sonora. Se quiser musica de fundo, coloque depois no seu editor de video, com faixas que voce tem direito de usar (royalty-free / CC0).

## Termos da HeyGen

O uso do avatar segue os termos da HeyGen. Crie avatar apenas de voce mesmo ou de alguem que consentiu. Este projeto nao distribui avatares nem vozes.
