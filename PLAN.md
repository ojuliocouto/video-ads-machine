# Video Ads Machine 2.0: Implementation Plan (Fase A)

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans pra implementar task a task. Steps usam checkbox (`- [ ]`).

**Goal:** implementar e validar localmente a skill Video Ads Machine 2.0 (motor HyperFrames), provando que ela reproduz o reelC v7 aprovado a partir de roteiro + voz, com sistema de presets.

**Architecture:** repo = a própria skill. Blocos HTML/CSS/GSAP reutilizáveis + presets por dimensão + 2 templates + scripts (bootstrap, alinhamento de legenda/lettering, auditoria de frames). O agente autora a composição a partir dos blocos, guiado por brief + roteiro.

**Tech Stack:** HyperFrames (npm, pinado) · Node 18+ · ffmpeg · Chrome/Chromium (via hyperframes) · Python 3 (scripts) · pytest (testes de lógica) · GSAP · fontes woff2.

## Global Constraints (copiar em toda task)
- ZERO travessão (em dash) em qualquer arquivo (código, md, copy). Usar dois pontos/vírgula/hífen.
- Acentuação PT-BR correta em todo texto PT.
- Assets reais (avatar real, logo do evento, roteiro real, chaves) NUNCA versionados. `.gitignore` cobre. Validação usa eles LOCAL.
- Preset/bloco só é "pronto" após render + auditoria frame a frame (nunca só preview: existe bug render-vs-preview no HyperFrames).
- HyperFrames é proprietário: nunca commitar o pacote nem node_modules.
- Formato v1 é só 9:16 (1080x1920).
- Legenda é verbatim do roteiro (corrige grafia/acento), nunca a transcrição crua.
- Render sempre com `--video-frame-format png` (b-roll é screen recording).

---

## Referência-ouro (fonte da extração)
`~/video-ads-machine/_hyperframes_test/reelC/index.html` = o reel v7 aprovado. Os blocos e o preset default saem DALI (números já auditados). O output `~/video-ads-machine/output/hyperframes_reelC_editorial_v7_hook_9x16.mp4` é o alvo de paridade.

---

## WAVE 0: Fundação (sequencial, faço eu na sessão)

### Task 0.1: Scaffold do repo
**Files:** Create: dir tree completa, `.gitignore`, `LICENSE` (MIT), `package.json`.
- [ ] Criar árvore de `DESIGN.md` seção 3 (references/, blocks/, presets/, templates/, fonts/, scripts/, demo/, examples/).
- [ ] `.gitignore`: `node_modules/`, `*.mp4`, `_local/`, `.env`, `renders/`, `_tmp*`, `*.enc`, assets reais.
- [ ] `LICENSE` MIT (autor Júlio Couto, 2026).
- [ ] `package.json` com `"hyperframes": "0.7.56"` pinado (versão validada).
- [ ] `_local/reelC-reference/` (gitignored) = cópia do reelC real pra validação.
- [ ] Copiar `fonts/` (Inter 300/400/600, Montserrat 500/600, Playfair Italic 500/600/700, Archivo) do reelC.
- [ ] `git init`, primeiro commit com DESIGN.md + PLAN.md + scaffold.

### Task 0.2: `references/style.md` (números validados)
**Files:** Create: `references/style.md`
- [ ] Extrair de reelC os números exatos por bloco/preset default: caption (Montserrat 600 60px, kw Playfair italic 66px, bottom 330px), lettering (.lett flex-end padding 620px, key Playfair italic 88px/104px, chest y~1120-1300), grade (radial soft-light warm + vignette), hook (scrim radial 0.80/0.40, margin-top 150px, texto y~907-1165), endcard (ev-logo 600px bottom 90px, cta bottom 520px), grid-wipe (9x16 cells), B&W beat (--bw 28.5-30.15).

---

## WAVE 1: Unidades independentes (paralelo, subagents)

### Task 1.1: Blocos (9 arquivos)
**Files:** Create: `blocks/{hook-person,caption,broll-card,lettering-leadkey,lower-third,endcard-cta-logo,grade,grid-wipe,stat-countup}.html`
**Interfaces:** cada bloco = partial HTML + `<style scoped>` + trecho GSAP documentado, com placeholders `{{param}}` (ex: `{{LEAD}}`, `{{KEY}}`, `{{start}}`, `{{dur}}`).
- [ ] Extrair cada bloco do reelC (ler linhas correspondentes), parametrizar, salvar. `stat-countup` é novo (deriva do lettering "1%" + count-up GSAP).
- [ ] Verificação: cada bloco tem os data-attrs obrigatórios (data-start/duration/track-index) e class="clip"; documentar params no topo em comentário.

### Task 1.2: Presets (matriz 6 dimensões)
**Files:** Create: `presets/{caption,lettering,transition,grade,hook,endcard}/*.{css,js}`
**Interfaces:** cada preset = só as regras que MUDAM daquela dimensão (o default reproduz o reelC). Nome do arquivo = nome do preset no brief.
- [ ] Default de cada dimensão = extração fiel do reelC (montserrat-grossa, serif-editorial, grid-wipe, quente, pessoa-lettering, cta-logo-rodape).
- [ ] Variantes novas: authored (tay-fina, boxed, sans-bold, kinetic, hard-cut, crossfade, zoom-blur, natural, frio-teal, pb, tela-preta, card-kinetico, logo-fullscreen). Cada uma marcada `# status: unvalidated` até passar no render-audit da Wave 3.

### Task 1.3: `scripts/build_timeline.py` (TDD)
**Files:** Create: `scripts/build_timeline.py`, `tests/test_build_timeline.py`
**Interfaces:** Produces: `build(roteiro_path, voz_path, template_path, brief) -> index_html_str`; `align_words(roteiro, transcript) -> [{text,start,end,kw}]`; `group_captions(words) -> [{start,end,words}]`; `place_letterings(roteiro, words) -> [{id,lead,key,start,dur}]`.
- [ ] TDD `align_words`: teste com roteiro verbatim + transcript mock (com erro de grafia) → retorna palavras com grafia do roteiro e timestamps do transcript.
- [ ] TDD `group_captions`: agrupa em janelas de ~3 palavras respeitando pontuação.
- [ ] TDD `place_letterings`: extrai marcações LEAD/KEY do roteiro e casa com o timestamp da fala.
- [ ] `build`: injeta caption groups + letterings + presets escolhidos no template. Teste de integração com fixture pequena.

### Task 1.4: `scripts/check_assets.py` (TDD)
**Files:** Create: `scripts/check_assets.py`, `tests/test_check_assets.py`
**Interfaces:** Produces: `missing(brief) -> [str]` (lista de assets faltando); `offer_avatar_generation(roteiro, voz)` (usa a geração HeyGen (Avatar V); só se faltar avatar).
- [ ] TDD `missing`: brief apontando arquivos inexistentes → retorna a lista certa.
- [ ] `offer_avatar_generation`: stub que confirma a instrução de geração HeyGen, sem chamar a API no teste.

### Task 1.5: `scripts/setup.sh` + `scripts/audit_frames.sh`
**Files:** Create: `scripts/setup.sh`, `scripts/audit_frames.sh`
- [ ] `setup.sh`: idempotente. Checa `hyperframes` (senão `npm i`), roda `hyperframes doctor`, `hyperframes browser ensure` (na 0.7.56 é `ensure`, não `install`), `hyperframes skills`. Loga o que fez.
- [ ] `audit_frames.sh <mp4> <outdir>`: gera contact sheet (fps=1 tile) + frames-chave (hook, 1% beat, end card). Reusa o que fiz no reelC.

### Task 1.6: References docs
**Files:** Create: `references/{blocks,presets,workflow,hyperframes-gotchas}.md`
- [ ] `blocks.md`: catálogo (o que faz, params, z-index) dos 9 blocos.
- [ ] `presets.md`: catálogo das 6 dimensões + variantes + qual é default.
- [ ] `workflow.md`: os 10 passos do workflow operacional.
- [ ] `hyperframes-gotchas.md`: xPercent vs CSS transform, render-vs-preview (o bug do logo), `--video-frame-format png`, lint pega estrutura mas não colisão de layout.

---

## WAVE 2: Integração (depende da Wave 1)

### Task 2.1: Template `reel-editorial`
**Files:** Create: `templates/reel-editorial/{index.html,meta.json}`
- [ ] Montar o index.html a partir dos blocos, com pontos de injeção (`<!-- INJECT:captions -->`, `<!-- INJECT:letterings -->`, `<!-- INJECT:preset:grade -->` etc.) que o `build_timeline` preenche.
- [ ] Verificação: `hyperframes lint` = 0 erros.

### Task 2.2: Template `ad-hook`
**Files:** Create: `templates/ad-hook/{index.html,meta.json}`
- [ ] Variante ad-tuned (hook mais forte, ritmo mais rápido). Mesmos pontos de injeção.
- [ ] Verificação: lint 0 erros.

---

## WAVE 3: Validação (a prova, depende da Wave 2)

### Task 3.1: Paridade com o reelC
- [ ] Rodar `build_timeline` com o roteiro+voz do reelC (assets em `_local/`) sobre `reel-editorial` com presets default.
- [ ] `hyperframes render --video-frame-format png` → MP4.
- [ ] `audit_frames.sh` + LER os frames. Comparar contact sheet com o reelC v7. Critério: hook com pessoa+lettering, legenda Montserrat, letterings no peito, grade quente, logo rodapé, end card. Diferença aceitável só de timing < ~0.1s.

### Task 3.2: Validar 1 variante por dimensão
- [ ] Pra cada dimensão, trocar o default por 1 variante, renderizar, ler os frames. Marcar preset como `validated` no arquivo se auditar limpo (sem colisão, texto na boca, logo gigante). Se quebrar, corrigir e re-renderizar.

### Task 3.3: `SKILL.md`
**Files:** Create: `SKILL.md`
- [ ] Onboarding embutido (roda setup.sh) + roteador do workflow + tabela de presets + gotchas. Frontmatter com name/description/triggers.

---

## Checkpoints entre waves
- Fim Wave 1: `pytest` verde (scripts) + blocos/presets com lint estrutural ok.
- Fim Wave 2: `hyperframes lint` 0 erros nos 2 templates.
- Fim Wave 3: contact sheet do reel-editorial default batendo com reelC v7 (auditado a olho), presets variantes marcados validated/unvalidated.

## Fase B (plano separado, depois da Fase A validada)
Demo genérico · README inglês · audit-secrets + histórico git · push GitHub · teste de clone limpo.
