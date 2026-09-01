# blocks.md: catálogo dos blocos

9 blocos parametrizáveis compõem os reels. Cada bloco é um partial HTML/CSS/GSAP com placeholders `{{param}}`, guardado em `blocks/*.html` e instanciado pelo `build_timeline.py` dentro do template escolhido (`reel-editorial` ou `ad-hook`). Os números exatos (CSS, timing, z-index) vêm de `references/style.md`, extraídos e auditados do reelC v7 aprovado.

Regra de ouro (DESIGN.md, seção 4): um bloco só entra na composição depois de renderizado e auditado frame a frame. Nunca confiar só no preview.

## Ordem de z-index (do fundo pro topo)

imagem/a-roll (0) < grade (20) < vignette (21) < broll-scrim (12) < broll-vid (14) < broll-tag (15) < lettering (34) < caption (35) < lower-third (40) < hook (44) < cta (46) < endcard-logo (48) < grid-wipe (60).

Nota: os índices do broll (12/14/15) ficam numa faixa própria, ativa só durante os trechos de b-roll; não colidem com o restante porque o a-roll principal fica coberto nesses momentos.

---

## 1. hook-person

**O que faz:** abertura do reel. A pessoa (avatar) aparece em tela cheia, com um scrim de legibilidade e um bloco de texto (eyebrow + linha + palavra de destaque) posicionado no peito, nunca sobre o rosto.

**Parâmetros:** `{{EYEBROW}}` (rótulo pequeno em caixa alta), `{{L1}}` (linha em Inter regular), `{{ACCENT}}` (palavra/frase de destaque em Playfair itálico), `{{start}}` / `{{dur}}` (timing do bloco).

**z-index:** 44 (`#hook`).

**Timing típico:** `data-start` 0, duração 2.5s (abre o reel). Dentro dele: eyebrow entra com fade + y14->0 aos 0.2s; `l1` aos 0.42s; `accent` aos 0.64s; o bloco inteiro (`hook-inner`) ganha um scale sutil até 1.04 aos 0.8s (duração 1.7s).

**Notas:** `hook-inner` usa `margin-top:150px` pra empurrar o texto pro peito (y ~907-1165), deixando o rosto livre. A variante de preset `tela-preta` (dimensão `hook`) troca o scrim translúcido por fundo opaco e remove o `margin-top`, centralizando o texto: é o hook antigo, descartado na auditoria, mantido só como opção.

---

## 2. caption

**O que faz:** legenda word-by-word, sincronizada com a fala real. É sempre verbatim do roteiro (nunca a transcrição crua); palavras-chave (`kw:true`) ganham destaque em serifa itálica.

**Parâmetros:** lista de grupos `{start, end, words:[{text, start, kw}]}`, gerada pelo `build_timeline.py` (função `group_captions`).

**z-index:** 35 (`#caps`).

**Timing típico:** por grupo, o bloco aparece (`visibility:visible` + opacity 0->1 em 0.12s) no `start` do grupo; cada palavra faz fade + subida (y8->0, 0.16s) no seu próprio timestamp; o grupo some com fade 0.06s antes do fim e escreve `hide` no `end`.

**Notas:** fonte Montserrat 600 60px; palavra-chave usa Playfair 600 itálico 66px. Posição fixa (bottom 330px): não pode colidir com CTA/endcard quando os dois estão em cena ao mesmo tempo.

---

## 3. broll-card

**O que faz:** insere um clipe de b-roll (screen recording, demonstração, etc.) num card com borda e sombra, com uma tag "rec" acima indicando que é uma gravação.

**Parâmetros:** `{{SRC}}` (vídeo do b-roll), `{{LABEL}}` (texto da tag, ex: "tela"), `{{start}}` / `{{dur}}` por instância (pode haver várias no mesmo reel).

**z-index:** faixa 10-19 reservada pro bloco (scrim 12, vídeo 14, tag 15).

**Timing típico:** por b-roll, o scrim aparece (opacity 0->1, 0.28s) no início do trecho; o card (opacity + scale 0.985->1, 0.4s) entra 0.02s depois; a tag sobe (y10->0) 0.12s depois disso; tudo sai com fade de 0.24s no fim do trecho.

**Notas:** sempre renderizar com `--video-frame-format png` quando houver instância desse bloco (o b-roll costuma ser screen recording, que perde qualidade com compressão jpeg). Ver `references/hyperframes-gotchas.md`, item 3.

---

## 4. lettering-leadkey

**O que faz:** o bloco mais usado pra reforçar a fala em texto. Par de linhas ancoradas no peito do apresentador: LEAD (rótulo em Inter, caixa alta) + KEY (frase de destaque em Playfair itálico).

**Parâmetros:** `{{LEAD}}`, `{{KEY}}`, `{{start}}`, `{{dur}}` (um ou mais letterings por reel, cada um com timing casado com a fala via `place_letterings`).

**z-index:** 34 (a faixa 32-34 do DESIGN.md cobre lettering + `stat-countup`, que fica em 32).

**Timing típico:** helper `lettReveal(id, at, dur)`: bloco opacity 0->1 em `at` (0.25s); `.lead` sobe (y16->0) em `at+0.05`; `.key` sobe (y22->0, 0.5s) em `at+0.18`; fade out em `at+dur-0.3`.

**Notas:** `padding-bottom:620px` trava o texto em y~1120-1300, sempre abaixo do queixo (y>900). A variante `#lettB` usa KEY maior (104px, letter-spacing -1px) pra frases mais curtas e impactantes.

---

## 5. lower-third

**O que faz:** cartão de identificação (nome + papel do apresentador), com um avatar circular mostrando a inicial. Dá credibilidade, aparece perto do início do reel.

**Parâmetros:** `{{INITIAL}}`, `{{NAME}}`, `{{ROLE}}`, `{{start}}` (entrada), `{{end}}` (saída).

**z-index:** 40 (`#lt`).

**Timing típico:** entra com x-60->0 + fade em 0.55s, tipicamente por volta de 2.8s (logo após o hook); sai com x-40 mais adiante (no reelC, por volta de 6.75s).

**Notas:** posicionado no canto superior esquerdo (left 60, top 70), não interfere no hook nem na legenda, que ficam em outra região da tela.

---

## 6. endcard-cta-logo

**O que faz:** encerramento do reel. CTA (rótulo + pill + seta) empilhado sobre a wordmark/logo no rodapé.

**Parâmetros:** `{{CTA_LABEL}}`, `{{CTA_TEXT}}`, `{{LOGO_SRC}}`, `{{start}}`.

**z-index:** `#cta` 46, `#ev-logo` 48.

**Timing típico:** aparece no fechamento do reel (últimos segundos); CTA em bottom 520px, logo em bottom 90px, largura 600px.

**Notas, GOTCHA CRÍTICO:** `#ev-logo` centraliza com `left:50%` + GSAP `xPercent:-50`. Nunca usar `transform:translateX(-50%)` no CSS: o `y` do GSAP sobrescreve o transform inteiro e a logo descentraliza e estica. Foi o bug que quebrou o v6, cobrindo o rosto do apresentador com a logo gigante. Ver `references/hyperframes-gotchas.md`, item 1.

---

## 7. grade

**O que faz:** camada de cor (grade quente por padrão) + vinheta, entre a imagem e o texto. Dá o tom editorial (aquecimento, contraste) e escurece as bordas pra concentrar o olho no centro.

**Parâmetros:** preset escolhido na dimensão `grade` do brief (`quente`, `natural`, `frio-teal`, `pb`); sem parâmetros de instância, é uma camada fixa do reel inteiro.

**z-index:** `#grade` 20, `#vignette` 21.

**Timing típico:** estático, ativo o reel inteiro (sem entrada/saída animada).

**Notas:** `#grade` usa `mix-blend-mode:soft-light`. O efeito P&B pontual (beat) é separado, controlado por `--bw` no `#a-roll` (sobe de 0 pra 1 e volta), usado pra dessaturar o avatar no pico de uma frase-chave (ex: 28.5s a 30.15s no reelC). Não confundir esse beat com o preset de grade `pb` (que é um look permanente do reel inteiro).

---

## 8. grid-wipe

**O que faz:** transição em grade/pixelate entre o hook e o primeiro b-roll (ou entre outros segmentos). Corta a cena com um mosaico que fecha e reabre, mascarando o corte.

**Parâmetros:** preset da dimensão `transition` (`grid-wipe` é o default; `hard-cut`, `crossfade` e `zoom-blur` substituem esse bloco por lógicas diferentes de transição); `{{start}}` do corte.

**z-index:** 60 (`#grid-pixelate-overlay`), acima de todos os outros blocos.

**Timing típico:** grade de 9 colunas x 16 linhas; células fecham (scale 0->1) a partir de 2.05s (stagger de 0.28s a partir do início); reabrem (scale 1->0) a partir de 2.75s (stagger a partir do fim). Janela total de aproximadamente 0.7s.

**Notas:** é o único bloco que fica por cima de tudo (z60), inclusive do endcard. Por isso só deve estar ativo durante a própria transição, nunca sobrepondo outro bloco fora desse instante.

---

## 9. stat-countup (novo em v1)

**O que faz:** destaca um número que sobe (ex: "1%") como bloco standalone, útil pra reforçar prova/dado numérico sem precisar de um LEAD/KEY completo. Deriva da estrutura do `lettering-leadkey` combinada com uma animação de contagem.

**Parâmetros:** `{{PREFIX}}` (texto antes do número, opcional), `{{VALUE}}` (valor final, ex: 1), `{{SUFFIX}}` (ex: "%", "x"), `{{start}}`, `{{dur}}`.

**z-index:** 32 (faixa reservada, abaixo do lettering-leadkey em 34, pra não colidir se os dois blocos coexistirem no mesmo instante).

**Timing típico:** segue o mesmo padrão de reveal do lettering (fade + subida no início, 0.25 a 0.5s), com a contagem numérica (tween de `innerText`/`textContent` via GSAP) rodando durante o `dur` do bloco. Pode ser casado com o beat P&B (`--bw`) pra reforçar visualmente o pico, como acontecia informalmente no reelC.

**Notas:** é um bloco NOVO em v1, sem extração literal do reelC (lá o "1%" fazia parte do lettering + beat P&B, não era um bloco isolado). Entra na biblioteca como `validated` só depois de renderizado e auditado (regra de ouro do DESIGN.md, seção 4).
