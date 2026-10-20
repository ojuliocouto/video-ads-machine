# Caminho one-shot: um take de câmera, a pessoa falando direto

Use quando há **uma tomada boa** da pessoa falando para o celular, sem avatar, sem roteiro em blocos. Editar é o trabalho: "one-shot" é o formato de veiculação, não licença para entregar material cru. O one-shot tira a falsa partida, a pergunta para quem dirige e a voz baixa ao fundo (ver "Retomada e fala de quem dirige"). Take de evento, com várias tomadas e trechos de vários takes num anúncio, segue em `gravado.md`.

## Comandos

```
vam novo <slug> --modo oneshot ...        cria o projeto no modo oneshot
vam oneshot <slug> --bruto take.mov --so-plano   transcreve, planeja e MOSTRA o plano, sem renderizar
vam oneshot <slug> --caixa "Título"       renderiza numa passada só e roda os gates
```

O take é copiado para `voz/bruto.<ext>` do projeto (a origem nunca é tocada, e um take diferente do que já está lá não sobrescreve). Saídas: 0 entregou e todos os gates passaram, 1 algum gate reprovou o anúncio pronto, 2 pedido ou insumo inválido (projeto inexistente ou de outro modo, take ausente, colorway inválido, sem transcritor (faltam `MISTRAL_API_KEY` e `GROQ_API_KEY`), ffmpeg que falhou).

## Os passos, cada um medido no arquivo

| Passo | O que acontece | Medida |
|---|---|---|
| 0 Entender | assistir o bruto e ver o plano (`--so-plano` para aqui) | |
| 1 Transcrever | tempo de palavra pela nuvem (Groq na frente no corte, senão Mistral); cada palavra ganha margem antes (0,30 s Groq, 0,40 s Mistral) e 0,15 s depois | `VAM_CORTE_PRE_ROLL`, `VAM_CORTE_POS_ROLL` |
| 2 Cortar | o vão entre as palavras diz ONDE, a energia da onda diz QUANTO (`ar_morto.py`); antes da primeira palavra e depois da última corta pela transcrição | piso de silêncio = ruído medido do take (percentil 10) + 6 dB, nunca abaixo de -32 dB do pico (`ar_morto.piso_adaptativo`) |
| 2b Limpar | falsa partida, pergunta para quem dirige e voz baixa ao fundo saem (`oneshot/limpeza.py`) | cada sub-bloco lido sozinho; o plano lista cada retirada com motivo e texto |
| 3 Enquadrar | janela 9:16 centrada no rosto medido, medidas pares | rosto mediano de várias amostras |
| 4 Luz | luminância medida vira brilho e contraste; HDR do celular vira SDR por LUT | alvo de luminância 111; brilho com teto |
| 5 Lettering | caixa nativa (opcional) | |
| 6 Render | corte, enquadre, luz, grade, velocidade e caixa numa só passada | sem arquivo intermediário reencodado |
| 7 Loudness | -14 LUFS, true peak -1,5 dBTP, dois passes, ganho linear | o alvo de LRA acompanha o take (até 20); pico que estouraria o teto passa antes por um limitador (`audio/loudness.py`) |
| 8 Gates | fala do bruto (menos as retiradas declaradas no plano) inteira no final; maior pausa; técnico | |

Se o rosto nunca é achado, a janela centra no quadro e o plano mostra o aviso: nunca finge que mediu.

## Sala barulhenta

O piso de silêncio sai do take. Em sala com ruído (feira, evento, ar-condicionado), o ruído fica acima do piso fixo de -32 dB do pico. Com o piso fixo, o detector não achava pausa nenhuma: o take de 54,7 s do ensaio de 20/10/2026 saía com 1 segmento só. Agora o limiar é o percentil 10 da energia (janelas de 20 ms) mais 6 dB; take limpo continua com -32 dB. O plano mostra o valor (`silêncio: abaixo de X dB do pico`). O trecho antes da primeira palavra e depois da última sai pela transcrição, porque o preâmbulo de quem pega o celular não é silêncio. O plano avisa quando o corte do começo passa de 1,5 s.

## Retomada e fala de quem dirige

A transcrição do take inteiro deduplica: a nuvem lê "Cara, com 100 reais você já começa... Cara, com 100 reais você já consegue" como uma frase só e estica um token por cima da repetição. Por isso o one-shot separa o take em sub-blocos pela energia (pausa de 0,25 s ou mais) e lê cada um sozinho. Três casos saem:

| Caso | Como é achado | Exemplo do ensaio |
|---|---|---|
| Retomada | as últimas palavras antes de um sub-bloco começam com a mesma palavra dele e 60% delas se repetem nele, na ordem; sai a primeira tentativa | "Com cem reais você já começa..." antes de "Cara, com 100 reais você já consegue" |
| Direção | expressão de quem grava ("depois o que é que eu falo?", "quer que eu faça?", os padrões do `gate_offscript`) OU pergunta respondida logo depois por voz baixa | "Depois o que é que ele faz?" (Groq) e "Depois quer que eu faça?" (Mistral) |
| Voz baixa | pico do sub-bloco 10 dB ou mais abaixo do pico típico do apresentador | a resposta de quem dirige, ao fundo |

Cada retirada se alarga até 0,12 s da fala que fica dos dois lados. Ela nunca passa por cima de palavra lida num sub-bloco que fica. Retiradas que se tocam viram uma só. O plano mostra cada uma (`retirado: 28.96 > 38.80 voz baixa + direção + retomada: ...`) e um `AVISO ... confira na prévia`. Assista a prévia antes de entregar.

O gate de fala preservada compara o final com o bruto MENOS as retiradas do plano: fora delas, palavra sumida reprova como antes. O gate não se desliga.

Limites conhecidos (não invente além disso):
- O detector NÃO acha quem dirige quando fala perto do microfone, no mesmo volume, sem pergunta e sem expressão da lista. Confira a prévia.
- O detector NÃO acha retomada que começa com outra palavra ("Então, com 100 reais..." depois de "Cara, com 100 reais...").
- Fala baixa do próprio apresentador (sussurro, aparte) sai como voz baixa: o aviso do plano mostra o texto, confira.
- A nuvem às vezes perde palavra curta como "Tá." na leitura do arquivo inteiro. O gate ignora palavra com menos de 3 letras; leia o trecho sozinho se precisar provar.

Medido no ensaio (IMG_3751, 54,7 s, sala barulhenta, Mistral). O plano corta 0 a 8,78 s, 14,74 a 17,52 s, 28,96 a 38,80 s, 44,90 a 47,98 s e de 54,20 s ao fim. O final tem 24,8 s, -13,8 LUFS e pico -1,5 dBTP, e passa nos três gates sem glossário. O corte à mão do ensaio deixava "O que você precisa saber na..." antes de "O que você precisa saber, na verdade". O one-shot tira essa segunda retomada também.

## Aceleração

`projeto.json` define (padrão 1,2 em take real, `PADRAO_ACELERACAO["oneshot"]`). Não passe de 1,2 sem o ok de quem dirige.

## Ar morto

`scripts/cortar_ar_morto.py` é a peça de baixo do corte: ancora o corte no token do ASR. Limite conhecido: se o transcritor infla um token (um "Mas" de 7,3 s), o detector lê o vão como fala e não corta. É a razão de take de evento não ser one-shot. O corte renderizado traz um gate embutido que re-transcreve o resultado e sai com erro se sumiu ou encurtou palavra. Não desligue (`--sem-gate`) sem motivo escrito.

## Caixa de lettering nativa

Bloco sólido de canto reto com o texto dentro, que lê como o widget de texto nativo do Instagram (lê como post, não como anúncio editado). Para título e headline, nunca para legenda. Três colorways, rodízio entre eles, nunca um quarto:

| Colorway | Fundo | Texto |
|---|---|---|
| `ambar` (padrão) | `#FEC64D` | preto |
| `branco` | `#FFFFFF` | preto |
| `preto` | `#000000` | branco |

`--caixa "texto"` põe o texto exatamente como o apresentador lê; `--centro-y` (padrão 0,786) é o centro vertical em fração da altura. Fonte PT Serif do repo.

## Regras

- Assista e transcreva antes de tocar em nada.
- Número do material (rosto, luz, pausa) sai de medição.
- O gate de fala inteira não se desliga.
