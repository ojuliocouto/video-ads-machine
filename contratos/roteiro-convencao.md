# Convenção do roteiro.md

O `roteiro.md` é a fonte da verdade da fala de um anúncio. Ele mora em
`_local/projetos/<slug>/roteiro.md` e diz duas coisas ao mesmo tempo:

- **o que é falado**, palavra por palavra (vira a legenda verbatim e é o que o gate fala x roteiro confere);
- **como cada trecho aparece na tela**, numa direção curta entre colchetes no começo da linha.

Nenhum caminho do produto lê planilha. Este documento é o contrato: o leitor oficial é
`ler_roteiro` em `scripts/contratos/validar.py`, e `entrada/roteiro_md.py` (W1.B) tem que
produzir exatamente os mesmos blocos para os seis exemplos do fim desta página.

## De onde o roteiro vem

Em ordem de preferência:

1. **Texto colado no chat.** O Claude grava verbatim em `roteiro.md` depois de passar pela normalização abaixo (`entrada/texto_colado.py`).
2. **Arquivo .md ou .txt do aluno**, com a mesma normalização.
3. **Google Doc com comentários** (opcional), pelo token OAuth do próprio aluno. Só nesse caso liga o gate de fidelidade ao doc.

### Normalização do texto colado

A normalização só mexe em aspas, espaços, quebras de linha e rótulos de chat. Ela nunca
troca, junta ou apaga palavra da fala: a sequência de palavras de quem fala sai igual.

1. Quebras `\r\n` e `\r` viram `\n`.
2. Caracteres invisíveis saem: U+200B, U+200C, U+200D, U+2060 e U+FEFF.
3. Aspas curvas viram retas: `“ ” „ ‟` viram `"` e `‘ ’ ‚ ‛` viram `'`.
4. Espaço especial (U+00A0, U+2007, U+202F) e tabulação viram espaço; espaços repetidos viram um; espaço no começo e no fim da linha sai.
5. Rótulo de chat no começo da linha sai, com o nome de quem mandou:
   `[dd/mm/aaaa, hh:mm] Nome: ` e `[dd/mm/aaaa hh:mm:ss] Nome: ` (WhatsApp no iPhone) e
   `dd/mm/aaaa hh:mm - Nome: ` (WhatsApp no Android).
6. Duas ou mais linhas vazias seguidas viram uma.
7. O arquivo termina com exatamente uma quebra de linha.

Sem essa passada, o rótulo `[08/10/2026, 10:32]` do WhatsApp parece uma direção e o
validador reprova (ver `roteiro.invalido.direcao.md`).

## Forma geral

```
[direção] fala
```

- **Roteiro dirigido**: existe pelo menos uma linha que começa com `[`. Cada linha que começa com `[` abre um bloco. Uma linha sem `[` continua a fala do bloco anterior (junta com um espaço). Texto antes do primeiro bloco reprova.
- **Roteiro livre**: nenhuma linha começa com `[`. Cada parágrafo (linhas separadas por linha vazia) vira um bloco do tipo `livre`, e o plano propõe as direções para o aluno aprovar.
- Linha que começa com `#` é título ou comentário e nunca vira fala.
- Linha vazia não muda nada num roteiro dirigido.

## A direção entre colchetes

Os itens são separados por `|`. Palavras-chave aceitam maiúscula ou minúscula, e
`âncora` aceita com ou sem acento. Os valores ficam exatamente como foram escritos.

O **primeiro item** é sempre o tipo do bloco:

| Tipo | O que aparece na tela |
|---|---|
| `apresentador` | a pessoa falando (avatar, take gravado ou one-shot) |
| `insert: <chave>` | o arquivo `inserts/<chave>.*` do projeto; chave em minúsculas, números, `_` ou `-` |
| `lista` | a pessoa falando com uma pilha de lettering, uma linha por item da fala |
| `cta` | o fechamento: a pessoa falando, KEY do botão e logo; sempre o último bloco |

Os **itens seguintes**, em qualquer ordem (menos o hook, que vem por último):

| Item | Vale em | Significa |
|---|---|---|
| `split`, `cheio` ou `pip` | insert | preferência de layout; sem ela o plano decide: no modo avatar, insert horizontal vira `split` (insert em cima, rosto embaixo); `cheio` escrito ocupa pelo menos 70% da altura do quadro |
| `LEAD: <texto>` | apresentador, insert, lista, cta | linha pequena que puxa a KEY |
| `KEY: <texto>` | apresentador, insert, cta | o lettering de pico |
| `âncora: <palavra>` ou `âncora: <palavra>#<n>` | bloco com lettering | onde o lettering pousa |
| `logo` | cta | aceito por clareza; o cta sempre tem logo |
| `hook: <eyebrow> \| <linha> \| <destaque>` | só o primeiro bloco | o texto do quadro 0; exatamente 3 partes, e vem por último no colchete |

## Regras

O que está entre colchetes é direção e nunca vira legenda. Quando uma regra quebra, o
validador acusa a linha e o elemento entre parênteses (o "campo" do erro).

| Regra | Campo do erro |
|---|---|
| O primeiro item é um dos 4 tipos (`[avatar]` recebe a dica de usar `apresentador`) | `direcao` |
| Item desconhecido, item vazio entre barras ou texto antes do primeiro bloco | `direcao` |
| `insert:` tem chave válida | `insert` |
| `split`, `cheio` e `pip` só em insert, um por bloco | `layout` |
| `hook:` só no primeiro bloco, com 3 partes não vazias, por último no colchete | `hook` |
| `LEAD` pede `KEY` (menos em lista); lista não leva `KEY`; cta precisa de `KEY` | `key` |
| `logo` só no cta | `logo` |
| Roteiro dirigido termina com um bloco `cta`, e só o último bloco é cta | `cta` |
| Lista tem pelo menos 2 itens | `lista` |
| A âncora é uma palavra da fala do próprio bloco, sem ambiguidade | `ancora` |
| Ênfase é `*palavra*`, colada na palavra dos dois lados; asterisco sem par reprova | `enfase` |
| Colchete no meio da fala reprova (direção só no começo da linha) | `colchete` |
| Todo bloco tem fala | `fala` |

### Âncora

LEAD e KEY pousam, por padrão, na **primeira palavra da fala do bloco**. Para pousar em
outra palavra, use `âncora: palavra`. A palavra é comparada sem maiúscula, sem acento e sem
pontuação, e conta só dentro da fala do próprio bloco:

- aparece uma vez: `âncora: tarde` basta;
- aparece mais de uma vez: diga qual com `#n`, contando a partir de 1 (`âncora: dia#2`); sem o número, reprova como ambígua;
- não aparece, ou `#n` passa do número de ocorrências: reprova.

Quem converte essa contagem dentro do bloco para a ocorrência no anúncio inteiro é o
`entrada/para_motor`.

### Lista

`[lista]` vira pilha de lettering, uma linha por item, e os itens saem da própria fala:

- **Com marcadores** (`❌`, `✅`, `✔`, `✓`, `✖`, `✗`): cada marcador abre um item, que vai até o próximo marcador. O que vem antes do primeiro marcador não é item. Os marcadores não são falados: saem da fala, e cada um (com os espaços em volta) vira um espaço só. O marcador fica guardado no item.
- **Sem marcadores**: se a fala tem `:`, os itens são o que vem depois dos dois pontos; senão, a fala inteira. Separa por vírgula e ponto e vírgula. Quando isso dá 2 pedaços ou mais, o último pedaço ainda se divide no último ` e ` (o "a, b e c" do português). Sem vírgula nenhuma, `a e b` fica um item só e reprova: escreva `a, b` ou use marcadores.
- Cada item perde espaço nas pontas e pontuação final (`. , ; : …`).
- Com `LEAD`, a âncora padrão da pilha é a primeira palavra da fala; cada item pousa na própria primeira palavra.

### Ênfase

`*palavra*` ou `*duas palavras*` marca ênfase. Os asteriscos saem da fala e o trecho vai
para `enfase`, na ordem em que aparece.

## O que a leitura devolve

`ler_roteiro(texto)` devolve `(leitura, erros)`. A leitura é:

```json
{"livre": false, "blocos": [ ... ]}
```

`livre` é `true` quando o roteiro não tem nenhuma direção (o plano precisa propor). Todo
bloco tem sempre os mesmos 11 campos:

| Campo | Valor |
|---|---|
| `tipo` | `apresentador`, `insert`, `lista`, `cta` ou `livre` |
| `insert` | a chave, ou `null` |
| `layout` | `split`, `cheio`, `pip` ou `null` |
| `hook` | `{"eyebrow", "linha", "destaque"}` ou `null` |
| `lead`, `key` | o texto como escrito, ou `null` |
| `ancora` | `{"palavra", "n", "explicita"}` quando o bloco tem lettering (KEY, ou lista com LEAD), senão `null`; na âncora padrão, `palavra` é a primeira palavra da fala sem a pontuação das pontas. No bloco `cta` a âncora padrão é a primeira palavra do KEY, quando ela aparece na fala (onde o KEY inteiro começa, se a palavra se repete): o botão entra quando o KEY é dito, e não na primeira palavra do bloco; essa âncora leva `"da_key": true` (e `explicita` segue `false`). Se a palavra do KEY não está na fala, vale a primeira palavra do bloco |
| `logo` | `true` só no cta |
| `itens` | na lista, `[{"texto", "marcador"}]` (`marcador` é `null` sem marcador); fora dela, `[]` |
| `enfase` | os trechos marcados com asterisco, na ordem |
| `fala` | o texto depois do `]`, sem espaço nas pontas e sem os asteriscos; na lista com marcadores, também sem os marcadores. Linhas de continuação entram juntadas com um espaço. Fora isso, byte a byte igual ao arquivo |

## Os seis exemplos

Cada exemplo abaixo é idêntico ao arquivo `contratos/exemplos/roteiro.valido.<nome>.md`, e
a leitura esperada está em `roteiro.valido.<nome>.blocos.json` ao lado dele. O teste confere
as duas coisas; mudou aqui, muda lá.

### 1. Completo

Hook sobre um insert de demonstração, KEY no meio, split, lista por vírgula, insert sem
layout (o plano decide) e o CTA com logo. O título com `#` é ignorado.

<!-- exemplo:completo -->
```markdown
# Anúncio: três horas por dia
[insert: painel | hook: VOCÊ PERDE | 3 horas por dia | NISSO AQUI] Você perde três horas por dia nisso aqui.
[apresentador] E eu sei porque eu fazia igual, todo santo dia.
[apresentador | LEAD: o problema não é | KEY: FALTA DE TEMPO] O problema não é falta de *tempo*.
[insert: planilha | split] É que cada tarefa repetida come um pedaço da sua agenda.
[lista | LEAD: enquanto isso] Enquanto isso: a proposta atrasa, o cliente esfria e você perde a venda.
[insert: automacao] Com uma automação simples, isso roda sozinho enquanto você atende.
[cta | LEAD: toque em | KEY: SAIBA MAIS | logo] Toque em saiba mais e veja como montar a sua.
```

Leitura: 7 blocos. O bloco 2 ancora em `O` (primeira palavra) e tem `enfase: ["tempo"]`; a
lista sai com 3 itens (`a proposta atrasa`, `o cliente esfria`, `você perde a venda`); o cta
ancora em `saiba` (a primeira palavra do KEY) e tem `logo: true`.

### 2. Só fala

Roteiro livre: nenhum colchete. Cada parágrafo vira um bloco `livre`; a quebra de linha no
meio do parágrafo vira espaço.

<!-- exemplo:so-fala -->
```markdown
Você perde três horas por dia nisso aqui. E eu sei porque eu fazia igual,
todo santo dia.

O problema não é falta de tempo. Com uma automação simples, isso roda sozinho
enquanto você atende. Toque em saiba mais e veja como montar a sua.
```

Leitura: `livre: true`, 2 blocos do tipo `livre`.

### 3. Texto colado sujo

O aluno colou do WhatsApp. A entrada vem com rótulo de chat em toda linha, aspas curvas,
espaços sobrando e linhas vazias a mais:

<!-- exemplo:texto-colado:entrada -->
```text
[08/10/2026, 10:32] Ana: [insert: agenda | hook: SUA AGENDA | cheia de tarefa | QUE NÃO PAGA]   Sua agenda está cheia de tarefa que não paga as contas.
[08/10/2026, 10:33] Ana: [apresentador]  Eu chamo isso de “trabalho invisível”.



[08/10/2026, 10:33] Ana: [apresentador | KEY: TODO DIA] É o e-mail que você responde ‘rapidinho’, todo dia.
[08/10/2026, 10:34] Ana: [cta | LEAD: toque em | KEY: SAIBA MAIS] Toque em saiba mais.
```

Depois da normalização, o `roteiro.md` gravado é:

<!-- exemplo:texto-colado -->
```markdown
[insert: agenda | hook: SUA AGENDA | cheia de tarefa | QUE NÃO PAGA] Sua agenda está cheia de tarefa que não paga as contas.
[apresentador] Eu chamo isso de "trabalho invisível".

[apresentador | KEY: TODO DIA] É o e-mail que você responde 'rapidinho', todo dia.
[cta | LEAD: toque em | KEY: SAIBA MAIS] Toque em saiba mais.
```

Leitura: 4 blocos; a KEY `TODO DIA` sem âncora pousa na primeira palavra (`É`).

### 4. Lista

As duas formas de lista: com marcadores e por vírgula.

<!-- exemplo:lista -->
```markdown
[apresentador | LEAD: o dia passa | KEY: E NADA ANDA] O dia passa e nada anda.
[lista | LEAD: enquanto isso] Enquanto isso: ❌ a proposta atrasa ❌ o cliente esfria ❌ e você perde a venda.
[lista] Com a automação: a proposta sai na hora, o cliente recebe resposta e a venda fecha.
[cta | LEAD: toque em | KEY: SAIBA MAIS] Toque em saiba mais.
```

Leitura: a primeira lista sai com 3 itens marcados com `❌` (o terceiro é
`e você perde a venda`, com o "e", porque o marcador manda) e a fala sem os marcadores:
`Enquanto isso: a proposta atrasa o cliente esfria e você perde a venda.` A segunda lista
não tem LEAD, então `ancora` é `null`, e os itens são `a proposta sai na hora`,
`o cliente recebe resposta` e `a venda fecha`.

### 5. Split, cheio e pip

As três preferências de layout, um insert sem preferência e o mesmo insert usado duas vezes.

<!-- exemplo:layouts -->
```markdown
[insert: planilha | split] É que cada tarefa repetida come um pedaço da sua agenda.
[insert: pedidos | cheio] Olha o tamanho da fila de pedidos.
[insert: tutorial | pip] E aqui eu te mostro o passo a passo, sem pressa.
[apresentador] Parece muito, mas cabe numa tarde.
[insert: planilha] Repara que é a mesma planilha, agora rodando sozinha.
[cta | KEY: SAIBA MAIS] Toque em saiba mais.
```

Leitura: `layout` vale `split`, `cheio`, `pip`, `null` (apresentador), `null` (o plano
decide) e `null` (cta). O cta sem LEAD é aceito.

### 6. CTA com logo

Âncora explícita com `#n`, âncora explícita sem número, ênfase dentro do cta e o `logo`.

<!-- exemplo:cta-logo -->
```markdown
[apresentador | LEAD: um dia na mão | KEY: NO OUTRO, SOZINHO | âncora: dia#2] Um dia eu fiz tudo na mão, no outro dia já rodava sozinho.
[apresentador | LEAD: tudo isso em | KEY: UMA TARDE | âncora: tarde] Dá pra montar tudo isso em uma tarde.
[cta | LEAD: toque em | KEY: SAIBA MAIS | logo] Toque em *saiba mais* e veja como montar a sua.
```

Leitura: `{"palavra": "dia", "n": 2, "explicita": true}`, depois
`{"palavra": "tarde", "n": 1, "explicita": true}`, e o cta com `enfase: ["saiba mais"]` e a
fala sem os asteriscos.

## Erros comuns

Cada um tem um exemplo em `contratos/exemplos/roteiro.invalido.<campo>.md`:

| Arquivo | O que está errado |
|---|---|
| `roteiro.invalido.hook.md` | hook com 2 partes |
| `roteiro.invalido.cta.md` | cta no começo e o roteiro termina sem cta |
| `roteiro.invalido.ancora.md` | `âncora: dia` com "dia" duas vezes na fala |
| `roteiro.invalido.direcao.md` | colado do WhatsApp sem normalizar |
| `roteiro.invalido.layout.md` | `split` num apresentador |
| `roteiro.invalido.key.md` | LEAD sem KEY |
| `roteiro.invalido.enfase.md` | asterisco sem par |
| `roteiro.invalido.lista.md` | lista com um item só |
| `roteiro.invalido.logo.md` | logo fora do cta |
| `roteiro.invalido.colchete.md` | colchete no meio da fala |
| `roteiro.invalido.insert.md` | chave de insert com maiúscula e espaço |
| `roteiro.invalido.fala.md` | bloco sem fala |

## Como validar

```
python3 scripts/contratos/validar.py _local/projetos/<slug>/roteiro.md
python3 scripts/contratos/validar.py contratos/exemplos
```

Saída 0 quando passa; 1 com uma linha por problema (`linha N (campo): motivo`); 2 quando o
caminho não existe.
