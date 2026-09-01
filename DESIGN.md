# Video Ads Machine 2.0: Design Spec

Data: 2026-07-14
Autor: Júlio Couto (design conduzido com Claude via brainstorming)
Status: aguardando revisão do Júlio

---

## 1. Visão geral

**Video Ads Machine 2.0** é uma skill (Claude Code) que embrulha o **HyperFrames** pra montar reels e anúncios em vídeo no estilo editorial validado no reelC (grade quente, legenda grossa, letterings serifados no peito, hook com a pessoa na tela, logo no rodapé, transições).

Não é um app monolítico. É um **pacote de conhecimento + blocos + presets + scripts** que conduz o usuário (o autor ou um aluno) da matéria-prima (roteiro + voz + avatar + b-rolls) até o MP4 final, com estilos configuráveis.

### O que É
- Motor de composição de vídeo vertical (9:16) declarativo, sobre HyperFrames.
- Biblioteca de blocos e presets testados frame a frame.
- Automação do trabalho chato: alinhamento de legenda e posicionamento de lettering pela fala.
- Skill autoinstalável (bootstrap do HyperFrames no primeiro uso).

### O que NÃO É
- Não é gerador de avatar/voz/b-roll (isso é geração; HyperFrames e esta skill fazem EDIÇÃO/composição). Há um passo OPCIONAL que chama o HeyGen pra gerar o avatar quando falta.
- Não é o video-ads-machine em Python (esse continua existindo para a linha de anúncio "clássica"). Esta é a versão HyperFrames, mais flexível.
- Não redistribui o HyperFrames (proprietário): o usuário instala na própria máquina.

---

## 2. Objetivos e não-objetivos (v1)

### Objetivos (v1)
- 2 formatos: `reel-editorial` (flagship, = reelC parametrizado) e `ad-hook` (variante ad-tuned).
- 9 blocos reutilizáveis (os 8 validados no reelC + `stat-countup`).
- Sistema de presets em 6 dimensões (default = look reelC).
- `build_timeline`: roteiro + voz → legenda word-by-word + letterings no timestamp certo.
- Bootstrap/onboarding do HyperFrames.
- Publicação no GitHub (repo público, MIT) com demo genérico e README em inglês.

### Não-objetivos (fica pra v2+)
- Formatos 1:1 e 16:9 (v1 é só 9:16).
- Kinetic type puro / carrossel de stats / lyric video.
- Render em nuvem (modo `cloud` pago do HyperFrames).
- Editor visual / UI própria.

---

## 3. Arquitetura (modular, 1 responsabilidade por arquivo)

```
video-ads-machine-2/                 # repo = a própria skill (aluno clona pra .claude/skills/)
  SKILL.md                           # onboarding embutido + roteador do workflow
  README.md                          # inglês: o que é / o que NÃO é, install, onboarding, segurança, licença
  LICENSE                            # MIT
  .gitignore                         # ignora assets reais, chaves, renders, node_modules

  references/
    style.md                         # a assinatura editorial: números exatos de cada preset
    blocks.md                        # catálogo de blocos (o que faz, parâmetros, HTML+GSAP)
    presets.md                       # catálogo de presets por dimensão
    workflow.md                      # passo a passo operacional
    hyperframes-gotchas.md           # xPercent vs CSS transform, render-vs-preview, --video-frame-format png, lint

  blocks/                            # partials HTML/CSS/GSAP reutilizáveis (o agente instancia por reel)
    hook-person.html
    caption.html                     # engine word-by-word (variantes via preset)
    broll-card.html
    lettering-leadkey.html
    lower-third.html
    endcard-cta-logo.html
    grade.html                       # #grade + #vignette (variantes via preset)
    grid-wipe.html
    stat-countup.html                # NOVO

  presets/                           # 1 arquivo por variante, com CSS/GSAP + metadados
    caption/{montserrat-grossa,tay-fina,boxed}.css
    lettering/{serif-editorial,sans-bold,kinetic}.css
    transition/{grid-wipe,hard-cut,crossfade,zoom-blur}.js
    grade/{quente,natural,frio-teal,pb}.css
    hook/{pessoa-lettering,tela-preta,card-kinetico}.css
    endcard/{cta-logo-rodape,logo-fullscreen}.css

  templates/
    reel-editorial/                  # o reelC parametrizado
    ad-hook/                         # variante de anúncio

  fonts/                             # woff2: Inter, Montserrat, Playfair Display Italic, Archivo

  scripts/
    setup.sh                         # bootstrap: instala HyperFrames pinado, doctor, browser install, hyperframes skills
    check_assets.py                  # detecta avatar/voz/b-roll faltando; oferece gerar avatar (HeyGen opcional)
    build_timeline.py                # roteiro + voz -> transcript word-level (HyperFrames) -> caption groups + lettering timestamps -> injeta template + presets
    audit_frames.sh                  # contact sheet + frames-chave (auditoria frame a frame)

  demo/                              # PACOTE DEMO genérico (vai pro repo público)
    avatar_demo.mp4                  # avatar sintético/royalty-free, NÃO o avatar real
    logo_demo.png                    # logo placeholder
    roteiro_demo.txt                 # roteiro genérico
    brief.example.json

  examples/
    brief.schema.json                # schema do brief.json
```

**Assets reais (Apresentador, logo do evento, roteiro real, chaves): NUNCA no repo.** Ficam locais e gitignored. São usados só na validação (Fase A).

---

## 4. Biblioteca de blocos (v1)

Cada bloco carrega os números exatos calibrados no reelC (CSS, z-index, timing). O agente instancia por reel.

| Bloco | Papel | z-index |
|---|---|---|
| `hook-person` | Abertura: pessoa na tela + lettering no peito, scrim de legibilidade | 44 |
| `caption` | Legenda word-by-word (sincronizada pela fala) | 35 |
| `broll-card` | Inserção de b-roll (card com borda) + tag "rec" | 10-19 |
| `lettering-leadkey` | LEAD (Inter) + KEY (Playfair itálico) no peito | 32-34 |
| `lower-third` | Nome + papel do apresentador | 40 |
| `endcard-cta-logo` | CTA (pill + seta) + wordmark no rodapé | 46-48 |
| `grade` | Grade de cor + vinheta (entre imagem e texto) | 20-21 |
| `grid-wipe` | Transição pixelate hook→b-roll | 60 |
| `stat-countup` (novo) | Número que sobe (ex: 1%) como bloco standalone | 32 |

Regra: bloco só entra depois de renderizado e auditado frame a frame.

---

## 5. Sistema de presets

Cada dimensão tem variantes nomeadas. O usuário escolhe uma por dimensão na criação, ou omite e cai no **default = look reelC**. As escolhas ficam no `brief.json`; o `build_timeline.py` injeta o CSS/GSAP do preset escolhido.

```json
{
  "format": "reel-editorial",
  "styles": {
    "caption": "montserrat-grossa",
    "lettering": "serif-editorial",
    "transition": "grid-wipe",
    "grade": "quente",
    "hook": "pessoa-lettering",
    "endcard": "cta-logo-rodape"
  }
}
```

| Dimensão | Presets v1 | Default |
|---|---|---|
| Legenda | montserrat-grossa · tay-fina · boxed | montserrat-grossa |
| Lettering | serif-editorial · sans-bold · kinetic | serif-editorial |
| Transição | grid-wipe · hard-cut · crossfade · zoom-blur | grid-wipe |
| Grade | quente · natural · frio-teal · pb | quente |
| Hook | pessoa-lettering · tela-preta · card-kinetico | pessoa-lettering |
| End-card | cta-logo-rodape · logo-fullscreen | cta-logo-rodape |

Regra de ouro: **só entra na biblioteca preset renderizado e auditado**. A matriz cresce à medida que validamos variantes novas. Números exatos em `references/style.md`.

---

## 6. O "machine": build_timeline

O coração da automação. Substitui o trabalho manual que foi feito no reelC.

Entrada: roteiro anotado (fala + direções em colchetes: LEAD/KEY, b-roll cues) + voz (mp3).
Passos:
1. Gera o transcript word-level via **HyperFrames** (whisper, multiplataforma); parakeet-mlx como atalho opcional só no Mac.
2. Casa o transcript com o roteiro verbatim (corrige grafia/acentos; a legenda é verbatim do roteiro, nunca a transcrição crua).
3. Emite os `caption groups` (agrupamento word-by-word com timestamps) e posiciona os letterings LEAD/KEY no timestamp da fala correspondente.
4. Injeta tudo no template escolhido, aplicando os presets do `brief.json`.

Saída: `index.html` do HyperFrames pronto pra lint + render.

---

## 7. Fronteira de geração (híbrido)

- Padrão: **monta com assets existentes** (avatar.mp4, voz, b-rolls, logo).
- `check_assets.py` detecta o que falta. Se faltar o **avatar**, oferece um passo OPCIONAL de gerar via HeyGen (usa a geração HeyGen (engine Avatar V, lip-sync)). A chave HeyGen é do usuário (nunca commitada).
- Voz: assume gravada (voz real). TTS não é objetivo (é o "tell" de IA).

---

## 8. Onboarding / bootstrap (primeiro uso)

Embutido no `SKILL.md` (o agente conduz sem depender do README) e em `scripts/setup.sh`. Idempotente:
1. CLI do HyperFrames existe? Se não, `npm i hyperframes@<versão-travada>` no workdir.
2. `hyperframes doctor` → confere Node, ffmpeg, Chrome/Chromium.
3. `hyperframes browser ensure` → baixa/acha o Chromium do render (na 0.7.56 o subcomando é `ensure`, não `install`).
4. `hyperframes skills` → instala as skills de autoria do HyperFrames.

Pré-requisitos declarados no README e no SKILL.md: Node 18+, ffmpeg, (opcional) chave HeyGen pra gerar avatar, (opcional) parakeet-mlx no Mac.

---

## 9. Workflow (como o agente opera)

1. Escolher formato (reel-editorial | ad-hook).
2. Receber brief/roteiro + assets.
3. `check_assets.py` → se faltar avatar, oferecer HeyGen.
4. Escolher presets (ou usar default = reelC).
5. `build_timeline.py` → legenda + letterings alinhados, template montado.
6. Agente ajusta blocos (grade, hook, end-card) conforme o brief.
7. `hyperframes lint`.
8. `hyperframes render --video-frame-format png` (b-roll é screen recording).
9. `audit_frames.sh` → o agente LÊ os frames e corrige (disciplina obrigatória, nunca "pronto" sem auditar).
10. Entrega: MP4 9:16 + versão `_whatsapp` leve.

---

## 10. Publicação (Fase B)

### Sanitização (antes de qualquer push)
- Assets reais (Apresentador, logo do evento, roteiro real) e chaves NUNCA vão. `.gitignore` cobre.
- `~/.claude/scripts/audit-secrets.sh` + varredura no histórico do git antes do push.
- O repo leva só o **demo genérico** (`demo/`): avatar sintético/royalty-free, logo placeholder, roteiro genérico. O aluno roda `render` e vê um reel sair sem ter nada.

### README (inglês, detalhado)
Estrutura: o que é / o que NÃO é (expectativa honesta) · como funciona passo a passo · instalação e pré-requisitos · onboarding · conteúdo · segurança (traga suas chaves, nada commitado) · licença.

### Licença
- Nosso código: **MIT** (`LICENSE`).
- HyperFrames: proprietário, instalado pelo aluno via npm, não redistribuído. Explícito no README.

---

## 11. Entrega em 2 fases

- **Fase A (local):** implementar blocos, presets, scripts e os 2 templates; validar renderizando o reelC real (assets reais) e auditando frame a frame; provar que `build_timeline` reproduz o reelC aprovado.
- **Fase B (publicação):** montar o demo genérico; escrever README em inglês; auditar segredos; `git init` + primeiro commit (DESIGN.md incluso) + push pro GitHub; testar o clone limpo (onboarding do zero numa pasta nova) antes de entregar pro aluno.

---

## 12. Plano de validação (como provamos o v1)

1. `build_timeline` sobre o roteiro+voz do reelC gera legenda/letterings equivalentes ao reelC aprovado (diferença de timestamp < ~0.1s).
2. Render do template `reel-editorial` com presets default bate visualmente com o reelC v7 (contact sheet lado a lado).
3. Trocar 1 preset por dimensão e renderizar → cada variante audita limpa (sem colisão de layout, texto na boca, logo gigante).
4. Clone limpo do repo + `setup.sh` + render do demo → sai um MP4 numa máquina "zerada".

---

## 13. Riscos e mitigação

- **Render-vs-preview do HyperFrames** (bug que pegou o logo no reelC): auditoria frame a frame do render final é obrigatória, nunca confiar só no preview.
- **Portabilidade do alinhamento:** usar o transcript do HyperFrames (whisper) como padrão, não o parakeet (Mac-only).
- **Vazamento de asset/segredo:** fronteira de sanitização + audit-secrets + histórico do git.
- **Licença do HyperFrames:** nunca commitar o pacote; instalar via npm; deixar claro no README.

---

## 14. Futuro (v2+)
Formatos 1:1 e 16:9 · kinetic type puro · carrossel de stats · render em nuvem · mais presets por dimensão · integração com o `video-agent`/`criativo-imagem-ia`.
