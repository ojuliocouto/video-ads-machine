      // ===== timeline.js: a timeline GSAP, UMA para os dois formatos (9x16 e 1x1) =====
      // Defeito 12 do plano: este JS era copiado nos dois index.html e o null-guard dos b-rolls já faltou
      // num deles (o quadrado ficou sem legenda, lettering e CTA). Agora há um arquivo só, incluído pelo
      // marcador PARCIAL em cada template; nada de JS próprio por formato.
      // Os números de tempo que aparecem aqui (55.36, 50.5, 46.9...) são do MODELO: o gerador do overlay
      // troca cada um pelo tempo do anúncio (overlay.cta, overlay.hook, overlay.brolls, overlay.html_injecao).
      // Não reescrever essas linhas sem mudar o módulo que as procura.
      window.__timelines = window.__timelines || {};
      const tl = gsap.timeline({ paused: true });

      // ===== OPENING HOOK =====
      // TEXTO CHEIO NO QUADRO 0 (C1). As linhas nasciam em opacidade 0 e só ficavam legíveis aos 0,63 s: o
      // movimento fica na escala e na posição, nunca na opacidade. A linha de destaque leva uma batida perto
      // de 1 s, senão o gancho fica uns 2 s parado.
      gsap.set(["#hook .eyebrow", "#hook .l1", "#hook .accent"], { opacity: 1, y: 0 });
      // pop por linha: só assentamento de escala, linha a linha, nos primeiros 0,4 s
      ["#hook .eyebrow", "#hook .l1", "#hook .accent"].forEach(function (sel, i) {
        gsap.set(sel, { scale: 1.10, transformOrigin: "50% 50%" });
        tl.to(sel, { scale: 1, duration: 0.22, ease: "power3.out" }, 0.02 + i * 0.11);
      });
      tl.from("#hook .eyebrow", { yPercent: 26, duration: 0.40, ease: "power3.out" }, 0);
      tl.from("#hook .l1", { yPercent: 30, duration: 0.44, ease: "power3.out" }, 0.09);
      tl.from("#hook .accent", { yPercent: 34, duration: 0.50, ease: "power3.out" }, 0.18);
      tl.to("#hook .accent", { scale: 1.045, duration: 0.22, ease: "power2.out" }, 0.95);
      tl.to("#hook .accent", { scale: 1.0, duration: 0.30, ease: "power2.inOut" }, 1.17);
      tl.to("#hook .hook-inner", { scale: 1.04, duration: 1.7, ease: "sine.inOut" }, 0.8);

      // ===== GRID WIPE (abertura para b-roll; desligado no gerador, a maquinaria fica) =====
      (function () {
        const COLS = 9, ROWS = 16;
        const overlay = document.getElementById("grid-pixelate-overlay");
        if (!overlay) return;
        overlay.style.gridTemplateColumns = "repeat(" + COLS + ",1fr)";
        overlay.style.gridTemplateRows = "repeat(" + ROWS + ",1fr)";
        for (let i = 0; i < COLS * ROWS; i++) {
          const c = document.createElement("div"); c.className = "grid-cell"; overlay.appendChild(c);
        }
      })();
      gsap.set("#grid-pixelate-overlay .grid-cell", { scale: 0 });
      /* INJECT:wipes */

      // ===== B-ROLLS: fade + escala na entrada e na saída =====
      // A lista vem do gerador (overlay.brolls troca a constante inteira).
      const BROLLS = [];
      BROLLS.forEach(function (b, i) {
        const scrim = document.getElementById(b.id + "_scrim");
        const card  = document.getElementById(b.id + "_vid");
        const tag   = document.getElementById(b.id + "_tag");
        // NULL-GUARD (não remover). No OVERLAY (camada só de texto, com alfa) o strip_overlay REMOVE scrim,
        // card e tag. Sem esta guarda o GSAP recebia null, lançava "Cannot read properties of null" e MATAVA o
        // script inteiro: legendas, letterings e CTA registrados depois nunca chegavam à timeline.
        if (!scrim || !card || !tag) return;
        const ADJ_GAP = 0.6;
        const prev = BROLLS[i - 1];
        const next = BROLLS[i + 1];
        const isOpening = b.start <= 0.001;
        // vem de um insert colado (ou da abertura): entra por corte seco; vem do avatar: entra com fade
        const fromAdjacent = isOpening || (prev && (b.start - (prev.start + prev.dur)) <= ADJ_GAP);
        const toAdjacent = next && (next.start - (b.start + b.dur)) <= ADJ_GAP;
        // scrim SEMPRE aceso na janela inteira: o HyperFrames corta o clipe no fim do data-duration e um fade
        // segurado por GSAP deixava o rosto vazar por ~0,2 s
        gsap.set(scrim, { opacity: 1 });
        if (fromAdjacent) {
          gsap.set(card, { opacity: 1, scale: 1 });
        } else {
          gsap.set(card, { opacity: 0, scale: 0.985 });
          tl.to(card, { opacity: 1, scale: 1, duration: 0.4, ease: "power2.out" }, b.start + 0.02);
        }
        gsap.set(tag, { opacity: 0, y: 10 });
        tl.to(tag, { opacity: 1, y: 0, duration: 0.32, ease: "power2.out" }, b.start + 0.12);
        const out = b.start + b.dur;
        if (toAdjacent) {
          // o próximo insert cobre no corte seco: só tira a tag
          tl.to(tag, { opacity: 0, duration: 0.2, ease: "power1.in" }, out - 0.18);
        } else {
          // volta pro avatar: fade limpo do b-roll inteiro
          tl.to([scrim, card, tag], { opacity: 0, duration: 0.24, ease: "power1.in" }, out - 0.24);
        }
      });

      // ===== LEGENDAS (data-driven): cada .cgrp tem data-g-start/data-g-end; cada .cw, data-w-start/data-w-end =====
      var _fimAnterior = null;
      document.querySelectorAll("#caps .cgrp").forEach(function (grp) {
        var gStart = parseFloat(grp.dataset.gStart);
        var gEnd = parseFloat(grp.dataset.gEnd);
        grp.style.cssText = "opacity:0;visibility:hidden;";
        // ENTRA ANTES DO ANTERIOR SAIR, mas só depois de pausa (26 e 27/08/2026). Antecipar 0,12 s mata a
        // piscada entre grupos (41 micro-apagões medidos); grupo COLADO no anterior entra na hora, senão os
        // dois ficam na tela ao mesmo tempo.
        var _colado = (_fimAnterior !== null && gStart - _fimAnterior < 0.05);
        // `cgrp-sem-lead`: o grupo nasce a menos de 0,16 s de uma troca de layout; a antecipação apareceria
        // ainda no layout antigo com a posição do novo. Entra na hora.
        var _semLead = grp.classList.contains("cgrp-sem-lead");
        var gIn = (_colado || _semLead) ? gStart : Math.max(0, gStart - 0.12);
        _fimAnterior = gEnd;
        tl.set(grp, { visibility: "visible" }, gIn);
        // pop de grupo: o grupo inteiro chega com escala 1,22 -> 1 rápido; só transform e opacidade
        gsap.set(grp, { scale: 1.22, transformOrigin: "50% 80%" });
        tl.to(grp, { opacity: 1, scale: 1, duration: 0.18, ease: "power3.out" }, gIn);
        grp.querySelectorAll(".cw").forEach(function (span) {
          var wStart = parseFloat(span.dataset.wStart);
          var wEnd = parseFloat(span.dataset.wEnd);
          // dwell mínimo: abaixo de 0,34 s o realce vira estrobo em palavra funcional
          if (!(wEnd > wStart + 0.34)) { wEnd = wStart + 0.34; }
          // PREENCHIMENTO LINEAR (29/08/2026): a camada `fill` é revelada da esquerda para a direita no tempo
          // REAL da palavra, com ease "none" (linear foi o pedido). Nada de y, scale nem filter: movimento de
          // palavra gerou as três reprovações anteriores.
          var _fill = span.querySelector(".fill");
          if (_fill) {
            gsap.set(_fill, { clipPath: "inset(0 100% 0 0)" });
            tl.to(_fill, { clipPath: "inset(0 0% 0 0)",
                           duration: Math.max(wEnd - wStart, 0.12),
                           ease: "none", overwrite: "auto" }, wStart);
          }
        });
        // a saída termina EXATAMENTE em gEnd (antes vazava 0,10 s por cima do próximo grupo)
        tl.to(grp, { opacity: 0, duration: 0.1, ease: "power1.in" }, gEnd - 0.1);
        tl.set(grp, { opacity: 0, visibility: "hidden" }, gEnd);
      });

      // ===== ENTRADAS DOS ESTILOS DE LETTERING (C7; cinema/lettering_estilos) =====
      // Todas com alfa cheio no primeiro quadro: a KEY está legível em até 0,15 s. O movimento é só de escala ou
      // posição e assenta em até 0,14 s. A saída é seca, como a do editorial. O estilo vem em data-estilo.
      function _alvos(lead, keys) { return [lead].concat(Array.prototype.slice.call(keys)).filter(Boolean); }
      var ENTRADAS = {
        caixa_nativa: function (el, at, dur, lead, keys) {      // widget nativo: um pop curto, sem brilho
          var a = _alvos(lead, keys);
          gsap.set(a, { scale: 0.96, transformOrigin: "50% 50%" });
          tl.to(a, { scale: 1, duration: 0.10, ease: "power2.out" }, at);
        },
        punch: function (el, at, dur, lead, keys) {             // carimbo
          gsap.set(keys, { scale: 1.25, transformOrigin: "50% 55%" });
          tl.to(keys, { scale: 1, duration: 0.10, ease: "power4.out" }, at);
        },
        marcador: function (el, at, dur, lead, keys) {          // texto seco, marca-texto se desenha em 0,12 s
          gsap.set(keys, { scale: 1.06, transformOrigin: "50% 60%" });
          tl.to(keys, { scale: 1, duration: 0.10, ease: "power3.out" }, at);
          tl.fromTo(el, { "--hx": 0.02 }, { "--hx": 1, duration: 0.12, ease: "power2.out", immediateRender: false }, at);
        },
        statement: function (el, at, dur, lead, keys) {         // linhas sobem 30 px
          gsap.set(keys, { y: 30 });
          tl.to(keys, { y: 0, duration: 0.14, ease: "power3.out" }, at);
        },
        lateral: function (el, at, dur, lead, keys) {           // entra deslizando da esquerda
          var a = _alvos(lead, keys);
          gsap.set(a, { x: -60 });
          tl.to(a, { x: 0, duration: 0.14, ease: "power3.out" }, at);
        },
        seta_cta: function (el, at, dur, lead, keys) {          // chamada seca + seta que quica (C9)
          gsap.set(keys, { scale: 1.06, transformOrigin: "50% 50%" });
          tl.to(keys, { scale: 1, duration: 0.12, ease: "power3.out" }, at);
          var seta = el.querySelector(".seta");
          if (seta) {
            var voltas = Math.max(1, Math.floor((dur - 0.2) / 0.45));
            tl.fromTo(seta, { y: 0 }, { y: 14, duration: 0.45, ease: "sine.inOut", yoyo: true, repeat: voltas,
                                       immediateRender: false }, at + 0.15);
          }
        },
        gigante_atras: function (el, at, dur, lead, keys) {     // chega grande, assenta e respira
          gsap.set(keys, { scale: 1.14, transformOrigin: "50% 50%" });
          tl.to(keys, { scale: 1, duration: 0.14, ease: "power3.out" }, at);
          if (dur > 0.5) tl.to(keys, { scale: 1.03, duration: dur - 0.2, ease: "sine.inOut" }, at + 0.16);
        }
      };

      // ===== LETTERINGS (data-driven): cada .lett.clip tem data-start/data-duration =====
      // ENTRADA SECA (18/08/2026): o fade de 0,25 s deixava o lettering "surgindo" e o trecho lia como tempo
      // morto. Entrada instantânea com um assentamento de escala de 0,12 s, que o olho lê como CORTE; saída
      // seca também. A KEY fica legível (alfa cheio) já no primeiro quadro (C7: até 0,15 s).
      document.querySelectorAll(".lett.clip").forEach(function (el) {
        var at = parseFloat(el.dataset.start);
        var dur = parseFloat(el.dataset.duration);
        var lead = el.querySelector(".lead");
        var keys = el.querySelectorAll(".key");
        var entrada = ENTRADAS[el.dataset.estilo || ""];
        if (entrada) {
          gsap.set(el, { opacity: 0 });
          tl.set(el, { opacity: 1 }, at);
          entrada(el, at, dur, lead, keys);
          tl.set(el, { opacity: 0 }, at + dur);
          return;
        }
        gsap.set(el, { opacity: 0 });
        if (lead) gsap.set(lead, { opacity: 0 });
        gsap.set(keys, { opacity: 0, scale: 1.08, transformOrigin: "50% 60%" });
        tl.set(el, { opacity: 1 }, at);
        if (lead) tl.set(lead, { opacity: 1 }, at);
        // data-delay: numa PILHA cada linha entra na hora da própria palavra e fica
        keys.forEach(function (k) {
          var dl = parseFloat(k.dataset.delay || 0);
          tl.set(k, { opacity: 1 }, at + dl);
          tl.to(k, { scale: 1, duration: 0.12, ease: "power3.out" }, at + dl);
        });
        tl.set(el, { opacity: 0 }, at + dur);
      });

      // ===== CHIPS (desligados no CSS; a entrada fica para quando voltarem) =====
      document.querySelectorAll(".chip.clip").forEach(function (el) {
        var at = parseFloat(el.dataset.start);
        var dur = parseFloat(el.dataset.duration);
        gsap.set(el, { opacity: 0, scale: 0.88, transformOrigin: "100% 0%" });
        tl.set(el, { opacity: 1 }, at);
        tl.to(el, { scale: 1, duration: 0.16, ease: "back.out(2.2)" }, at);
        tl.set(el, { opacity: 0 }, at + dur);
      });

      // ===== CTA =====
      gsap.set("#cta", { opacity: 0 });
      gsap.set("#cta .lead", { opacity: 0, y: 14 });
      gsap.set("#cta-pill", { opacity: 0, y: 16 });
      tl.to("#cta", { opacity: 1, duration: 0.35 }, 50.5);
      tl.to("#cta .lead", { opacity: 1, y: 0, duration: 0.4, ease: "power2.out" }, 50.6);
      tl.to("#cta-pill", { opacity: 1, y: 0, duration: 0.45, ease: "power2.out" }, 50.75);
      // a seta (pseudo-elemento da pílula) desce e sobe pela variável --arw-y (C9: movimento medido)
      tl.fromTo("#cta-pill", { "--arw-y": "0px" }, { "--arw-y": "8px", duration: 0.9, ease: "sine.inOut", yoyo: true, repeat: 4, immediateRender: false }, 51.0);

      // ===== BEAT PRETO E BRANCO (manifesto) =====
      // Dessatura a imagem pela variável --bw (grayscale) e volta. O gerador remove este bloco.
      gsap.set("#a-roll", { "--bw": 0 });
      tl.to("#a-roll", { "--bw": 1, duration: 0.35, ease: "power2.out" }, 28.5);
      tl.to("#a-roll", { "--bw": 0, duration: 0.45, ease: "power2.in" }, 30.15);

      // ===== LOGO: entra junto com o bloco final =====
      gsap.set("#ev-logo", { xPercent: -50, opacity: 0, y: 18 });
      tl.to("#ev-logo", { xPercent: -50, opacity: 1, y: 0, duration: 0.6, ease: "power2.out" }, 46.9);

      window.__timelines["main"] = tl;

      // ===== DESTAQUE DO GANCHO: encolhe até caber em no máximo duas linhas dentro da caixa =====
      // Sem isso, texto longo quebra em linhas desbalanceadas e passa da margem.
      (function () {
        function ajustar() {
          var a = document.querySelector('#hook .accent');
          if (!a) return;
          var caixa = a.parentElement.clientWidth || 880;
          var px = 118;
          a.style.fontSize = px + 'px';
          var alturaLinha = 1.02;
          for (var i = 0; i < 26 && px > 52; i++) {
            var linhas = Math.round(a.scrollHeight / (px * alturaLinha));
            if (a.scrollWidth <= caixa && linhas <= 2) break;
            px -= 4;
            a.style.fontSize = px + 'px';
          }
        }
        if (document.readyState === 'loading')
          document.addEventListener('DOMContentLoaded', ajustar);
        else ajustar();
        document.fonts && document.fonts.ready && document.fonts.ready.then(ajustar);
      })();

      // ===== KEY DOS ESTILOS NOVOS: no máximo 2 linhas; a gigante numa linha só, até 700 px =====
      // A estimativa do gate (cinema/lettering_estilos.linhas_estimadas) barra a KEY longa antes do render; aqui o
      // corpo encolhe se a fonte real ainda quebrar em 3. Mede a caixa de layout (offset/scroll), que o transform
      // da entrada não altera.
      (function () {
        function caber() {
          document.querySelectorAll(".lett[data-estilo] .key").forEach(function (k) {
            var est = k.parentElement.dataset.estilo;
            var cs = getComputedStyle(k);
            var px = parseFloat(cs.fontSize);
            var lh = parseFloat(cs.lineHeight) / px || 1.1;
            var pad = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
            for (var i = 0; i < 40; i++) {
              var cabe = est === "gigante_atras"
                ? (k.scrollWidth <= 700 || px <= 120)
                : (Math.round((k.offsetHeight - pad) / (px * lh)) <= 2 || px <= 40);
              if (cabe) break;
              px -= 4;
              k.style.fontSize = px + "px";
            }
          });
        }
        if (document.readyState === 'loading')
          document.addEventListener('DOMContentLoaded', caber);
        else caber();
        document.fonts && document.fonts.ready && document.fonts.ready.then(caber);
      })();
