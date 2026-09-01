# presets.md: catálogo de presets por dimensão

## Como funciona

Existem 6 dimensões independentes de estilo. Cada dimensão tem uma ou mais variantes; uma delas é o **default**, que é a extração fiel do reelC v7 aprovado (o "look reelC"). O `brief.json` referencia, dentro de `styles`, o nome do preset escolhido em cada dimensão. Se uma dimensão for omitida no brief, o `build_timeline.py` aplica o default daquela dimensão automaticamente. Um brief sem o campo `styles` inteiro produz sempre o look reelC completo.

Cada preset vive em `presets/<dimensão>/<nome>.css` (ou `.js` no caso da dimensão `transition`, que carrega lógica GSAP, não só estilo estático). O nome do arquivo é exatamente o nome usado no `brief.json`.

Regra de ouro (DESIGN.md, seção 5, e PLAN.md, Wave 3): só entra como preset pronto (`status: validated`) o que foi renderizado e auditado frame a frame. Todo preset novo nasce marcado `status: unvalidated` no cabeçalho do arquivo até passar pela auditoria da Wave 3. A matriz cresce à medida que novas variantes são validadas.

---

## Tabela das 6 dimensões

| Dimensão | Chave no brief | Presets v1 | Default (look reelC) |
|---|---|---|---|
| Legenda | `styles.caption` | `montserrat-grossa` · `tay-fina` · `boxed` | `montserrat-grossa` |
| Lettering | `styles.lettering` | `serif-editorial` · `sans-bold` · `kinetic` | `serif-editorial` |
| Transição | `styles.transition` | `grid-wipe` · `hard-cut` · `crossfade` · `zoom-blur` | `grid-wipe` |
| Grade | `styles.grade` | `quente` · `natural` · `frio-teal` · `pb` | `quente` |
| Hook | `styles.hook` | `pessoa-lettering` · `tela-preta` · `card-kinetico` | `pessoa-lettering` |
| End-card | `styles.endcard` | `cta-logo-rodape` · `logo-fullscreen` | `cta-logo-rodape` |

---

## Detalhe por dimensão

### Legenda (caption)

- **`montserrat-grossa` (DEFAULT, validada na auditoria):** Montserrat 600 60px; palavra-chave em Playfair itálico 66px; grupo ancorado em bottom 330px. Números exatos em `references/style.md`.
- **`tay-fina`:** variante de legenda mais fina, inspirada no estilo "tay". Authored em v1, ainda `unvalidated` até passar por render e auditoria.
- **`boxed`:** legenda dentro de uma caixa/pill (em vez de flutuar solta sobre a imagem). Authored em v1, `unvalidated`.

### Lettering

- **`serif-editorial` (DEFAULT):** LEAD em Inter 400 28px caixa alta; KEY em Playfair 600 itálico 88px (ou 104px na variante `#lettB`); ancorado no peito (padding-bottom 620px).
- **`sans-bold`:** KEY trocado por uma fonte sans bold/black, sem itálico serifado. Authored, `unvalidated`.
- **`kinetic`:** lettering com movimento mais pronunciado (kinetic type aplicado ao bloco). Authored, `unvalidated`. Não confundir com o não-objetivo "kinetic type puro" da v2 (formato inteiro dedicado): aqui é só a variante do bloco `lettering-leadkey`, não um formato novo.

### Transição

- **`grid-wipe` (DEFAULT):** grade 9x16, células fecham e reabrem em mosaico entre o hook e o b-roll. Números em `references/style.md`.
- **`hard-cut`:** corte seco, sem transição visual. Authored, `unvalidated`.
- **`crossfade`:** dissolve entre os dois planos. Authored, `unvalidated`.
- **`zoom-blur`:** zoom com blur de movimento no corte. Authored, `unvalidated`.

### Grade

- **`quente` (DEFAULT):** radial gradient laranja/âmbar em soft-light + vinheta.
- **`natural`:** sem aquecimento forçado, cor mais próxima do captado. Authored, `unvalidated`.
- **`frio-teal`:** grade puxando pro teal/azul. Authored, `unvalidated`.
- **`pb`:** preto e branco permanente (não confundir com o beat P&B pontual do avatar, que é um efeito à parte controlado por `--bw` e existe independente da dimensão grade). Authored, `unvalidated`.

### Hook

- **`pessoa-lettering` (DEFAULT):** abre sobre o a-roll com scrim translúcido (rgba 0.80/0.40/0), pessoa visível, texto empurrado pro peito (margin-top 150px).
- **`tela-preta`:** mesmo hook, mas com fundo opaco (`radial-gradient(125% 90% at 50% 30%, #12131f, #0a0b14 58%, #05060a)`) e texto centralizado (sem margin-top). É o hook antigo, descartado na auditoria, mantido como opção pra quem preferir esse visual.
- **`card-kinetico`:** hook em formato de card com tipografia cinética. Authored, `unvalidated`.

### End-card

- **`cta-logo-rodape` (DEFAULT):** CTA (lead + pill + seta) empilhado sobre a wordmark no rodapé (logo bottom 90px, CTA bottom 520px).
- **`logo-fullscreen`:** fecha só com a logo em tela cheia, sem CTA. Authored, `unvalidated`.

---

## Exemplo de brief.json

Brief completo, com todas as dimensões explícitas (equivalente ao look reelC padrão):

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

Brief mínimo, omitindo `styles` inteiro (produz exatamente o mesmo resultado do exemplo acima, porque cada dimensão cai no próprio default):

```json
{
  "format": "reel-editorial"
}
```

Brief parcial, trocando só a grade e deixando o resto no default:

```json
{
  "format": "reel-editorial",
  "styles": {
    "grade": "frio-teal"
  }
}
```

Nesse último caso, `caption`, `lettering`, `transition`, `hook` e `endcard` caem todos no default (`montserrat-grossa`, `serif-editorial`, `grid-wipe`, `pessoa-lettering`, `cta-logo-rodape`); só a grade muda para `frio-teal`. O schema completo do brief (incluindo campos além de `styles`, como assets e roteiro) fica em `examples/brief.schema.json`.
