# style.md: números validados (extraídos do reelC v7 aprovado)

Fonte: `_local/reelC-reference/index.html` (reel de referência v7, auditado frame a frame e validado). Canvas: 1080x1920 (9:16). Todo número aqui foi RENDERIZADO e conferido. Não alterar sem re-render + auditoria.

## Fontes (woff2 em `fonts/`, embutidas via @font-face font-display:block)
- Inter 300/400/600/700/800
- Montserrat 500/600
- Playfair Display (italic) 500/600/700
- Archivo 700/800/900
- body: Inter 300.

## Camada base
- `#a-roll` (avatar): `position:absolute; inset:0; width:100%; height:100%; object-fit:cover; filter:grayscale(var(--bw,0));` track-index 0. O `--bw` dirige o beat P&B.
- Ordem de z: imagem (0) < grade (20) < vignette (21) < lett (34) < caps (35) < lower-third (40) < hook (44) < cta (46) < ev-logo (48) < grid-wipe (60).

## Preset grade: `quente` (DEFAULT)
```
#grade { position:absolute; inset:0; z-index:20; pointer-events:none;
  background:
    radial-gradient(130% 100% at 50% 22%, rgba(255,193,128,0.16), rgba(255,150,80,0.05) 45%, transparent 72%),
    linear-gradient(180deg, rgba(255,168,92,0.06) 0%, transparent 38%, rgba(28,14,4,0.16) 100%);
  mix-blend-mode: soft-light; }
#vignette { position:absolute; inset:0; z-index:21; pointer-events:none;
  background: radial-gradient(80% 74% at 50% 42%, transparent 50%, rgba(0,0,0,0.32) 100%); }
```

## Preset hook: `pessoa-lettering` (DEFAULT)
Abre SOBRE o a-roll (pessoa visível), só scrim pra legibilidade. `hook-inner` com `margin-top:150px` empurra o texto pro peito (bloco fica em y~907-1165, rosto livre).
```
#hook { position:absolute; inset:0; z-index:44;
  background:radial-gradient(115% 34% at 50% 57%, rgba(4,5,10,.80) 0%, rgba(4,5,10,.40) 58%, rgba(4,5,10,0) 88%);
  display:flex; flex-direction:column; align-items:center; justify-content:center; gap:4px; padding:0 100px; }
#hook .eyebrow { font-family:"Inter"; font-weight:400; font-size:30px; letter-spacing:8px;
  color:rgba(255,255,255,.7); text-transform:uppercase; margin-bottom:26px; text-shadow:0 2px 14px rgba(0,0,0,.65); }
#hook .l1 { font-family:"Inter"; font-weight:300; color:#fff; font-size:72px; line-height:1.06; letter-spacing:-.5px; text-shadow:0 3px 22px rgba(0,0,0,.6); }
#hook .accent { font-family:"Playfair Display", serif; font-weight:600; font-style:italic; color:#fff; font-size:118px; line-height:1.0; letter-spacing:-1px; text-shadow:0 8px 34px rgba(0,0,0,.5); }
```
GSAP: eyebrow fade y14->0 @0.2s, l1 @0.42s, accent @0.64s, `hook-inner` scale 1.04 @0.8s dur 1.7. Hook data-start 0 dur 2.5.
Variante `tela-preta`: mesmo hook, mas background opaco `radial-gradient(125% 90% at 50% 30%, #12131f, #0a0b14 58%, #05060a)` e sem margin-top (texto centralizado). É o hook ANTIGO (descartado na auditoria, mantido como opção).

## Bloco grid-wipe (transição hook -> b-roll)
```
#grid-pixelate-overlay { position:absolute; inset:0; z-index:60; pointer-events:none; display:grid; }
#grid-pixelate-overlay .grid-cell { background:#05060a; transform-origin:center center; }
```
9 cols x 16 rows. GSAP: cells scale 0->1 @2.05 (stagger 0.28 from start), scale 1->0 @2.75 (stagger from end).

## Bloco broll-card
```
.broll-scrim { inset:0; z-index:12; background:radial-gradient(120% 80% at 50% 42%, #14151f, #0a0b12 55%, #05060a); }
.broll-scrim::after { inset:0; background:radial-gradient(62% 34% at 50% 40%, rgba(255,255,255,.06), transparent 72%); }
.broll-vid { left:36px; width:1008px; top:452px; height:700px; z-index:14; border-radius:24px; object-fit:contain; background:#0b0d14; border:1.5px solid rgba(255,255,255,.16); box-shadow:0 30px 90px rgba(0,0,0,.6); }
.broll-tag { left:36px; top:392px; z-index:15; padding:12px 26px; border-radius:100px; background:rgba(12,13,20,.62); border:1px solid rgba(255,255,255,.18); backdrop-filter:blur(6px); }
.broll-tag .rec { width:11px; height:11px; border-radius:50%; background:rgba(255,180,120,.9); box-shadow:0 0 12px rgba(255,180,120,.55); }
.broll-tag .t { font-family:"Inter"; font-weight:500; font-size:26px; letter-spacing:.5px; color:rgba(255,255,255,.9); }
```
GSAP por b-roll: scrim opacity 0->1 @start dur 0.28; card opacity+scale 0.985->1 @start+0.02 dur 0.4; tag y10->0 @start+0.12; tudo fade out dur 0.24 no fim. Usar `--video-frame-format png` (screen recording).

## Bloco lower-third `#lt`
```
#lt { left:60px; top:70px; z-index:40; padding:18px 36px 18px 20px; border-radius:22px; background:rgba(12,13,20,.6); border:1px solid rgba(255,255,255,.14); box-shadow:0 20px 50px rgba(0,0,0,.45); backdrop-filter:blur(8px); }
#lt .ava { width:70px; height:70px; border-radius:50%; background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.28); font-family:"Playfair Display",serif; font-style:italic; font-weight:600; font-size:38px; }
#lt .name { font-family:"Inter"; font-weight:600; font-size:46px; color:#fff; }
#lt .role { font-family:"Inter"; font-weight:400; font-size:28px; color:rgba(255,255,255,.62); margin-top:8px; }
```
GSAP: x-60->0 opacity @2.8 dur 0.55; sai x-40 @6.75.

## Preset lettering: `serif-editorial` (DEFAULT)
Ancorado no PEITO (nunca no rosto/boca). Bloco `.lett` z34, justify-end, padding-bottom 620px -> texto em y~1120-1300.
```
.lett { inset:0; z-index:34; pointer-events:none; display:flex; flex-direction:column; align-items:center; justify-content:flex-end; gap:6px; padding:0 100px 620px; background:radial-gradient(58% 18% at 50% 66%, rgba(0,0,0,.5), transparent 74%); }
.lett .lead { font-family:"Inter"; font-weight:400; font-size:28px; letter-spacing:6px; color:rgba(255,255,255,.62); text-transform:uppercase; margin-bottom:12px; text-shadow:0 2px 12px rgba(0,0,0,.6); }
.lett .key { font-family:"Playfair Display",serif; font-weight:600; font-style:italic; font-size:88px; line-height:1.04; letter-spacing:-.5px; text-align:center; color:#fff; text-shadow:0 6px 30px rgba(0,0,0,.55); }
#lettB .key { font-size:104px; letter-spacing:-1px; }
```
GSAP reveal (helper `lettReveal(id, at, dur)`): bloco opacity 0->1 @at dur 0.25; .lead y16->0 @at+0.05; .key y22->0 @at+0.18 dur 0.5; fade out @at+dur-0.3.

## Preset caption: `montserrat-grossa` (DEFAULT, validada na auditoria)
Word-by-word, agrupada. `.cgrp` bottom 330px.
```
#caps { inset:0; z-index:35; pointer-events:none; }
#caps .cgrp { position:absolute; left:0; right:0; bottom:330px; padding:0 130px; display:flex; flex-wrap:wrap; align-items:baseline; justify-content:center; gap:6px 14px; }
#caps .cw { font-family:"Montserrat"; font-weight:600; font-size:60px; color:#fff; letter-spacing:.2px; line-height:1.3; text-shadow:0 2px 8px rgba(0,0,0,.55); }
#caps .cw.kw { font-family:"Playfair Display",serif; font-weight:600; font-style:italic; font-size:66px; letter-spacing:0; color:#fff; }
```
GSAP por grupo: `tl.set(grp,{visibility:visible})` @g.start; grp opacity 0->1 dur 0.12; cada palavra opacity+y8->0 dur 0.16 no w.start; grp fade out @g.end-0.06; hide @g.end. Palavra-chave (`kw:true`) usa `.cw.kw` (serif itálico).

## Preset endcard: `cta-logo-rodape` (DEFAULT)
```
#ev-logo { position:absolute; bottom:90px; left:50%; width:600px; height:auto; z-index:48; filter:drop-shadow(0 8px 30px rgba(0,0,0,.55)); }
#cta { position:absolute; left:0; right:0; bottom:520px; z-index:46; display:flex; flex-direction:column; align-items:center; gap:30px; }
#cta .lead { font-family:"Inter"; font-weight:400; font-size:30px; letter-spacing:6px; color:rgba(255,255,255,.62); text-transform:uppercase; text-shadow:0 2px 12px rgba(0,0,0,.6); }
#cta .pill { padding:26px 64px; border-radius:100px; background:rgba(255,255,255,.06); border:1.5px solid rgba(255,255,255,.38); color:#fff; font-family:"Inter"; font-weight:500; font-size:46px; letter-spacing:2px; backdrop-filter:blur(6px); box-shadow:0 16px 44px rgba(0,0,0,.4); }
#cta .arrow { font-size:58px; color:rgba(255,255,255,.6); }
```
GOTCHA CRÍTICO: `#ev-logo` usa `left:50%` + GSAP `xPercent:-50` pra centralizar. NUNCA `transform:translateX(-50%)` no CSS (o GSAP `y` sobrescreve o transform e a logo descentraliza/estica gigante). Foi o bug que quebrou o v6.

## Beat P&B (ênfase no "1%")
`gsap.set("#a-roll",{"--bw":0})`; sobe pra 1 @28.5 dur 0.35; volta a 0 @30.15 dur 0.45. Dessatura o avatar no pico da frase-chave.

## Âncoras de layout (referência de auditoria)
- Rosto do apresentador (framing reelC): olhos ~y640, boca ~y820, queixo ~y870, colarinho ~y1000, topo do microfone ~y1230.
- Lettering/hook TÊM que ficar abaixo do queixo (y > 900) pra não cair no rosto.
- Legenda em y~1512 (bottom 330 + altura). CTA pill em y~1190-1300. Logo em y~1670-1830. Sem colisão entre eles.
