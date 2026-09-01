---
name: video-ads-machine-2
description: >-
  Motor de reel e anúncio em vídeo (9:16) sobre HyperFrames, com estilo
  editorial validado (grade quente, legenda grossa, letterings serifados no
  peito, hook com a pessoa na tela, logo no rodapé) e sistema de presets
  configuráveis. Monta a partir de roteiro + voz + avatar + b-rolls; se faltar
  o avatar, oferece gerar via HeyGen. Use quando o pedido for criar reel,
  anúncio em vídeo, criativo editorial, montar reel no estilo tay, ou compor
  vídeo vertical com legenda word-by-word e letterings. Triggers: video ads
  machine 2, reel editorial, criar reel, montar anúncio hyperframes, reel
  hyperframes, legenda word-by-word, lettering serifado, grade quente.
---

# Video Ads Machine 2.0

Motor de composição de reel/anúncio vertical (9:16) sobre o **HyperFrames**. Não gera avatar/voz/b-roll (isso é geração): **monta e edita**. O estilo editorial é o que foi validado no reelC (aprovado frame a frame). Estilos são configuráveis por presets.

## O que É e o que NÃO é
- **É:** montador declarativo (HTML/CSS + GSAP renderizado por Chromium headless), biblioteca de blocos e presets testados, e automação do alinhamento de legenda/lettering pela fala.
- **NÃO é:** gerador de avatar/voz/b-roll (há um passo OPCIONAL que chama o HeyGen quando falta o avatar); não é o video-ads-machine em Python (esse continua pra a linha clássica); não redistribui o HyperFrames (proprietário, instalado à parte).

---

## PASSO 0: Onboarding (primeiro uso, sempre rodar antes)

Antes de qualquer coisa, garanta o ambiente. Rode o bootstrap (idempotente, só faz o que falta):

```bash
bash scripts/setup.sh
```

Ele: instala o HyperFrames pinado (se faltar), roda `hyperframes doctor` (checa Node/ffmpeg/Chrome), `hyperframes browser ensure` (baixa o Chromium do render) e `hyperframes skills` (skills de autoria).

**Pré-requisitos que o usuário precisa ter:**
- Node 18+ e ffmpeg instalados.
- (Opcional) chave HeyGen, só se for gerar o avatar pela skill (`HEYGEN_API_KEY` no ambiente; nunca commitar).
- (Opcional, só no Mac) `parakeet-mlx` pra alinhamento rápido; o padrão usa o transcript do próprio HyperFrames (multiplataforma).

Se o usuário não tem os assets ainda, avise que ele precisa de: `avatar.mp4` (talking-head), a voz (se for gerar avatar), b-rolls, e a logo. Conduza pelo `check_assets`.

---

## Workflow (conduza o usuário por estes passos)

1. **Formato:** pergunte `reel-editorial` (flagship, 9:16), `reel-editorial-1x1` (1:1 quadrado, pro feed) ou `ad-hook` (anúncio, hook mais forte).
2. **Brief + roteiro:** receba o roteiro anotado e os assets. Convenção do roteiro:
   - Fala normal = palavra falada (vira legenda verbatim).
   - `*palavra*` = keyword (sai em itálico serif na legenda). `*abre span fecha*` = várias palavras.
   - `[LEAD: texto]` `[KEY: texto]` `[DUR: seg]` = lettering ancorado na próxima palavra falada (LEAD pequeno + KEY grande no peito).
3. **Conferir assets:** `python3 scripts/check_assets.py` (via import) ou monte o brief e chame `missing(brief)`. Se faltar o avatar, ofereça gerar no HeyGen (`offer_avatar_generation`).
4. **Escolher presets** (ou usar default = look reelC). Uma escolha por dimensão, gravada no `brief.json` em `styles`:
   | Dimensão | Presets | Default |
   |---|---|---|
   | caption | montserrat-grossa, tay-fina, boxed | montserrat-grossa |
   | lettering | serif-editorial, sans-bold, kinetic | serif-editorial |
   | transition | grid-wipe, hard-cut, crossfade, zoom-blur | grid-wipe |
   | grade | quente, natural, frio-teal, pb | quente |
   | hook | pessoa-lettering, tela-preta, card-kinetico | pessoa-lettering |
   | endcard | cta-logo-rodape, logo-fullscreen | cta-logo-rodape |

   Omitir `styles` cai no default. Detalhe em `references/presets.md`.
5. **Montar timeline:** `build_timeline.build(roteiro_path, voz_path, template_path, brief)` gera o `index.html` preenchido (legenda word-by-word + letterings no timestamp da fala + presets). Escreva o resultado no dir de render junto dos assets e fontes.
   - Nota: `get_transcript` é stub. Integre com o transcript word-level do HyperFrames (ou parakeet no Mac) antes de usar fora de teste.
6. **Ajustar blocos** conforme o brief (b-rolls, textos do hook, logo, CTA). Blocos em `blocks/`, números em `references/style.md`.
7. **Lint:** `hyperframes lint <dir>`. Corrija erros de estrutura. `missing_local_asset` = falta copiar o asset pro dir.
8. **Render:** `hyperframes render -o saida.mp4 -f 25 -q standard --video-frame-format png` (o `png` é obrigatório quando há b-roll de screen recording).
9. **Auditoria frame a frame (OBRIGATÓRIA):** `bash scripts/audit_frames.sh saida.mp4 <outdir>` gera contact sheet + frames-chave. LEIA os frames com os próprios olhos. Nunca declare pronto sem isso (existe bug render-vs-preview no HyperFrames; o preview mente). Cheque: lettering no peito (não na boca/rosto), logo pequena no rodapé (não gigante centralizada), legenda legível, sem colisão.
10. **Entrega:** MP4 9:16 + versão leve `_whatsapp` (`ffmpeg -vf scale=720:1280 -crf 28`) pra aprovação no celular.

---

## Regra de ouro dos presets
Só entra na biblioteca preset que foi **renderizado e auditado frame a frame**. As variantes marcadas `unvalidated` nos arquivos de `presets/` ainda precisam passar por isso antes de virar padrão de entrega.

## Gotchas (leia `references/hyperframes-gotchas.md` e `LEARNINGS.md`)
- **Antes de mexer na lógica de montagem/timeline, leia `LEARNINGS.md`.** É a memória viva do motor: cada regra de montagem e cada item do checklist de auditoria pré-entrega nasceu de um defeito real de produção. Não regrida nenhuma sem revalidar frame a frame.
- Logo/elemento centralizado: `left:50%` no CSS + `xPercent:-50` no GSAP em TODO tween. NUNCA `translateX(-50%)` no CSS (o `y` do GSAP estica a logo gigante: foi o bug do v6).
- Legenda usa attrs custom (`data-w-start`, `data-g-start`), não `data-start`, senão o HyperFrames trata cada palavra como clip.
- Nunca escreva o texto literal de um marcador `INJECT:` dentro de um comentário do script (o `build` faz replace de todas as ocorrências e injeta HTML no JS).
- Auditoria frame a frame do RENDER final, sempre. O lint pega estrutura, não pega colisão de layout, texto na boca, nem lettering descolado da fala.

## Estrutura do projeto
- `references/` style.md (números), blocks.md, presets.md, workflow.md, hyperframes-gotchas.md
- `blocks/` partials HTML/CSS/GSAP · `presets/` variantes por dimensão · `templates/` reel-editorial, reel-editorial-1x1, ad-hook
- `scripts/` setup.sh, check_assets.py, build_timeline.py, audit_frames.sh · `fonts/` woff2 · `demo/` pacote genérico
