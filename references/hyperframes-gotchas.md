# hyperframes-gotchas.md: armadilhas conhecidas

Armadilhas levantadas na produção real do reelC (Video Ads Machine 1.0) e que valem pra qualquer bloco ou preset desta skill. Ler antes de mexer em qualquer bloco novo ou revisar um render.

## 1. `xPercent:-50` no GSAP, nunca `transform:translateX(-50%)` no CSS

Pra centralizar horizontalmente um elemento posicionado com `left:50%`, o CSS deve ficar só com `left:50%`, e a centralização acontece via GSAP (`xPercent:-50`). Se em vez disso o CSS já tiver `transform:translateX(-50%)`, qualquer animação GSAP que anime `y` (ou outra propriedade que passe por `transform`) SOBRESCREVE o transform inteiro, porque o GSAP reescreve a propriedade `transform` como um todo, não faz merge com o que já está no CSS. O resultado: o elemento perde a centralização e aparece deslocado e esticado.

Foi exatamente esse bug que fez a logo do evento (`#ev-logo`) ficar gigante cobrindo o rosto do apresentador no v6 do reelC. O fix ficou registrado em `references/style.md`:

> `#ev-logo` usa `left:50%` + GSAP `xPercent:-50` pra centralizar. Nunca `transform:translateX(-50%)` no CSS (o GSAP `y` sobrescreve o transform e a logo descentraliza/estica gigante). Foi o bug que quebrou o v6.

**Regra prática:** todo elemento centralizado horizontalmente que também recebe animação GSAP de `y`, `scale` ou qualquer outra propriedade de transform precisa usar `xPercent` (ou `xPercent` + `yPercent`) em vez de transform manual no CSS.

---

## 2. Render diverge do preview: a auditoria é sempre sobre o MP4 final

O preview do HyperFrames (rodando ou com seek no navegador) não é garantia do que sai no render. Já existiu divergência entre os dois: o bug do item 1 só ficou visível de fato no MP4 renderizado, não necessariamente no preview.

**Regra:** a auditoria frame a frame (`scripts/audit_frames.sh` + leitura dos frames pelo agente) é sempre feita em cima do MP4 RENDERIZADO, nunca só no preview. "Rodou bonito no preview" não é prova de nada. Isso é citado como risco explícito no DESIGN.md (seção 13) e está refletido nos passos 8 e 9 de `references/workflow.md`.

---

## 3. B-roll de screen recording exige `--video-frame-format png`

Quando o reel tem b-roll de gravação de tela (bloco `broll-card`), renderizar sem `--video-frame-format png` pode introduzir artefato de compressão (jpeg) que degrada texto e UI fina da gravação. Renderizar sempre com essa flag quando houver qualquer instância de `broll-card` no reel. Sem b-roll de screen recording, manter a flag como padrão continua seguro.

---

## 4. `hyperframes lint` não pega tudo

O `lint` valida estrutura: data-attrs obrigatórios (`data-start`, `data-duration`, `track-index`), sintaxe do HTML/GSAP, referências quebradas. Ele NÃO pega:

- Colisão de layout (dois blocos ocupando a mesma área ao mesmo tempo, ex: CTA sobre a legenda).
- Texto caindo em cima da boca ou do rosto do apresentador. Só a auditoria visual dos frames pega isso, comparando contra as âncoras de layout em `references/style.md` (olhos ~y640, boca ~y820, queixo ~y870).
- Lettering descolado da fala. O `lint` não sabe se o timestamp do bloco bate com o que está sendo dito naquele instante; só o `build_timeline.py` (alinhamento) e a auditoria visual confirmam isso.

Lint verde é necessário, mas não suficiente. Sempre seguir com o render e a auditoria de frames (passos 7, 8 e 9 de `references/workflow.md`).

---

## 5. `hyperframes preview` com `seek()` nem sempre resolve a visibilidade dos clipes

Ao usar `seek()` no preview pra pular pra um timestamp específico, o clipe pode não estar com a visibilidade ou opacidade corretas mesmo que o tempo já tenha passado do `data-start` dele: a timeline nem sempre recalcula 100% do estado visual no seek. Isso pode enganar quem está inspecionando visualmente só pelo preview.

**Prática recomendada:** ao medir a geometria real de um bloco (posição em pixels, pra conferir colisão ou se algo está no lugar certo), usar `getBoundingClientRect()` no elemento (via devtools ou script), em vez de confiar só no que aparece depois de um `seek()`. E, reforçando o item 2, a prova final é sempre o MP4 renderizado, nunca o preview com seek.
