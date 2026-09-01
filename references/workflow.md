# workflow.md: passo a passo operacional

Como o agente opera do zero (matéria-prima) até o MP4 final (DESIGN.md, seção 9). Cada passo tem o que fazer e o que checar antes de avançar pro próximo. Nunca pular a auditoria do Passo 9.

## Passo 1: Escolher o formato

- Perguntar (ou inferir do brief) qual template usar: `reel-editorial` (flagship, = reelC parametrizado) ou `ad-hook` (variante ad-tuned, hook mais forte e ritmo mais rápido).
- Confirmar que o formato é 9:16 (1080x1920). A v1 não suporta 1:1 nem 16:9 (DESIGN.md, seção 2, fica pra v2+).

## Passo 2: Receber brief/roteiro + assets

- Coletar: roteiro anotado (fala + marcações LEAD/KEY em colchetes + cues de b-roll), voz gravada (mp3), avatar (mp4), b-rolls, logo.
- Coletar ou confirmar o `brief.json` (formato + `styles` por dimensão; pode ficar omisso pra usar o default).
- Nunca aceitar TTS no lugar da voz gravada: o objetivo do projeto é voz real (TTS é "tell" de IA, DESIGN.md, seção 7).

## Passo 3: `check_assets.py`

- Rodar `scripts/check_assets.py` sobre o brief. Ele retorna a lista do que falta (avatar, voz, b-roll, logo).
- Se faltar o **avatar**: oferecer o passo OPCIONAL de gerar via HeyGen (usa a geração HeyGen (engine Avatar V, lip-sync)). A chave HeyGen é do usuário, nunca commitada.
- Se faltar **voz** ou **b-roll**: parar e pedir pro usuário. Não seguir sem voz real; b-roll insuficiente também bloqueia (o roteiro depende dele pras cues).

## Passo 4: Escolher presets

- Confirmar com o usuário (ou usar direto, se já vier no brief) os 6 presets de `styles`: caption, lettering, transition, grade, hook, endcard.
- Se o usuário não tiver preferência, usar o default de cada dimensão (look reelC). Tabela completa e exemplos de `brief.json` em `references/presets.md`.

## Passo 5: `build_timeline.py`

- Rodar `scripts/build_timeline.py` passando roteiro, voz e o template escolhido.
- Internamente: gera o transcript word-level (whisper via HyperFrames), casa com o roteiro verbatim (corrige grafia/acento; a legenda nunca é a transcrição crua), agrupa em caption groups, posiciona os letterings LEAD/KEY no timestamp certo da fala, e injeta tudo no template junto com os presets do brief.
- Saída: `index.html` do HyperFrames pronto pra lint.

## Passo 6: Ajustar blocos

- Revisar o `index.html` gerado: conferir o timing de grade, hook e end-card contra o roteiro (ex: b-roll cues no lugar certo, CTA e logo do jeito que o brief pediu).
- Ajustes manuais aqui são esperados: o `build_timeline` cobre legenda/lettering automaticamente, mas grade/hook/end-card costumam precisar de calibração fina por reel.

## Passo 7: `hyperframes lint`

- Rodar `hyperframes lint` sobre o `index.html`. Exigir 0 erros antes de renderizar.
- Lembrar: o lint pega só erro estrutural (data-attrs faltando, sintaxe quebrada, referência inválida). NÃO pega colisão de layout nem texto na boca. Ver `references/hyperframes-gotchas.md`, item 4.

## Passo 8: Render com `--video-frame-format png`

- Renderizar com `hyperframes render`, sempre passando `--video-frame-format png` quando o reel tiver b-roll de screen recording (é o caso padrão do bloco `broll-card`). Confirmar a sintaxe exata de flags/saída com `hyperframes render --help` na versão instalada (pinada no `package.json`), já que a CLI pode variar entre versões.
- Não aceitar o resultado do preview como prova de que está pronto: preview e render podem divergir. Ver Passo 9 e `references/hyperframes-gotchas.md`, item 2.

## Passo 9: `audit_frames.sh` + leitura dos frames

- Rodar `scripts/audit_frames.sh <mp4> <outdir>`: gera contact sheet (fps=1 tile) + frames-chave (hook, beat P&B/1%, end card).
- O agente LÊ os frames de verdade (abre e olha), nunca assume que passou. Checar: hook com pessoa + lettering no peito, legenda no lugar certo, sem colisão entre CTA/logo/legenda, sem texto sobre boca/rosto, logo centralizada (nem gigante, nem esticada).
- Disciplina obrigatória: nunca declarar "pronto" sem essa auditoria. Se achar problema, corrigir e voltar ao Passo 6 ou 8 e re-renderizar.

## Passo 10: Entrega

- Entregar o MP4 9:16 final.
- Gerar também uma versão `_whatsapp` leve (bitrate/resolução reduzidos, tipicamente via ffmpeg) pra envio direto sem perda perceptível de qualidade.
- Mostrar a entrega de forma visível pro usuário (arquivo, link ou print dos frames-chave). Nunca dizer que terminou sem mostrar o resultado.
