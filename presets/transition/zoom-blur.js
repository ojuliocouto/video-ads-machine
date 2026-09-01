/* PRESET transition/zoom-blur | status: unvalidated | base: sobrescreve grid-wipe.js: sem overlay de grid, scale para cima + blur crescente na saída do elemento que sai */
/* Contrato: roda no escopo de `tl` (timeline GSAP) e `gsap`. Placeholders substituídos pelo
   build_timeline.py:
   {{start}} = instante do corte
   {{dur}} = duração do efeito de saída em segundos (sugestão default: 0.32)
   {{fromSelector}} = seletor do elemento que está saindo (ex: "#hook")
   {{toSelector}} = seletor do(s) elemento(s) que estão entrando (ex: "#b1_scrim, #b1_vid, #b1_tag")
   O elemento que entra só recebe fade depois que o blur de saída já cobriu o corte, pra não
   duplicar desfoque em cima da transição. Usa CSS filter:blur, suportado pelo Chromium do
   HyperFrames (o mesmo motor que já roda backdrop-filter em #lt e #cta). */

gsap.set("{{fromSelector}}", { filter: "blur(0px)", scale: 1, transformOrigin: "center center" });
tl.to("{{fromSelector}}",
  { scale: 1.18, filter: "blur(22px)", opacity: 0, duration: {{dur}}, ease: "power2.in" }, {{start}});

gsap.set("{{toSelector}}", { opacity: 0 });
tl.to("{{toSelector}}", { opacity: 1, duration: 0.18, ease: "power1.out" }, {{start}} + {{dur}} - 0.05);
