/* PRESET transition/grid-wipe | status: validated | base: nenhuma, é o default, extração fiel do reelC v7 (index.html linhas 216-229) */
/* Contrato: roda dentro do <script> do template, no mesmo escopo de `tl` (a timeline GSAP já
   criada) e `gsap`. Espera um elemento #grid-pixelate-overlay vazio no DOM (bloco grid-wipe.html),
   z-index 60, cobrindo o quadro inteiro. Placeholders substituídos pelo build_timeline.py:
   {{start}} = instante em que o grid fecha e cobre o corte (default reelC: 2.05)
   {{outStart}} = instante em que o grid reabre revelando o próximo plano (default reelC: 2.75)
   Gera 9 colunas x 16 linhas de células e anima scale 0->1 (fecha) depois 1->0 (abre). */

(function () {
  var COLS = 9, ROWS = 16;
  var overlay = document.getElementById("grid-pixelate-overlay");
  overlay.style.gridTemplateColumns = "repeat(" + COLS + ",1fr)";
  overlay.style.gridTemplateRows = "repeat(" + ROWS + ",1fr)";
  for (var i = 0; i < COLS * ROWS; i++) {
    var c = document.createElement("div");
    c.className = "grid-cell";
    overlay.appendChild(c);
  }
})();

gsap.set("#grid-pixelate-overlay .grid-cell", { scale: 0 });
tl.to("#grid-pixelate-overlay .grid-cell",
  { scale: 1, duration: 0.4, stagger: { amount: 0.28, from: "start" }, ease: "power2.inOut" }, {{start}});
tl.to("#grid-pixelate-overlay .grid-cell",
  { scale: 0, duration: 0.4, stagger: { amount: 0.28, from: "end" }, ease: "power2.inOut" }, {{outStart}});
