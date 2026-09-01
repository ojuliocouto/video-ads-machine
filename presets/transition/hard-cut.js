/* PRESET transition/hard-cut | status: unvalidated | base: sobrescreve grid-wipe.js: remove por completo a criação de células e a animação do overlay, corte seco sem transição visual */
/* Contrato: mesmo escopo (tl, gsap) e mesmos nomes de placeholder do grid-wipe pra manter a
   interface do brief.json ({{start}}, {{outStart}}), mas nenhum dos dois é usado aqui: o corte
   acontece exatamente no data-start/data-duration de cada clip, sem overlay #grid-pixelate-overlay
   e sem tween algum. Este arquivo fica intencionalmente vazio de chamadas GSAP: é a documentação
   de que "sem transição" é uma escolha explícita, não um preset esquecido. */
