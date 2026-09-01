/* PRESET transition/crossfade | status: unvalidated | base: sobrescreve grid-wipe.js: sem overlay de grid, dissolve por opacidade entre o que sai e o que entra */
/* Contrato: roda no escopo de `tl` (timeline GSAP) e `gsap`. Placeholders substituídos pelo
   build_timeline.py:
   {{start}} = instante do corte (mesmo papel do {{start}} do grid-wipe)
   {{dur}} = duração do dissolve em segundos (sugestão default: 0.35)
   {{fromSelector}} = seletor do elemento que está saindo (ex: "#hook")
   {{toSelector}} = seletor do(s) elemento(s) que estão entrando (ex: "#b1_scrim, #b1_vid, #b1_tag")
   Não usa #grid-pixelate-overlay: os dois lados cruzam opacidade ao mesmo tempo. */

gsap.set("{{toSelector}}", { opacity: 0 });
tl.to("{{fromSelector}}", { opacity: 0, duration: {{dur}}, ease: "power1.inOut" }, {{start}});
tl.to("{{toSelector}}", { opacity: 1, duration: {{dur}}, ease: "power1.inOut" }, {{start}});
