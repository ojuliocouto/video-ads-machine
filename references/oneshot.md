# Caminho one-shot: um take de câmera, a pessoa falando direto

Use quando há **uma tomada boa** da pessoa falando para o celular, sem avatar, sem roteiro em blocos. Editar é o trabalho: "one-shot" é o formato de veiculação, não licença para entregar material cru. Se o take é de evento, com retomada ou com outra voz no fundo, não use este caminho: vá para `gravado.md`.

## Comandos

```
vam novo <slug> --modo oneshot ...        cria o projeto no modo oneshot
vam oneshot <slug> --bruto take.mov --so-plano   transcreve, planeja e MOSTRA o plano, sem renderizar
vam oneshot <slug> --caixa "Título"       renderiza numa passada só e roda os gates
```

O take é copiado para `voz/bruto.<ext>` do projeto (a origem nunca é tocada, e um take diferente do que já está lá não sobrescreve). Saídas: 0 entregou e todos os gates passaram, 1 algum gate reprovou o anúncio pronto, 2 pedido ou insumo inválido (projeto inexistente ou de outro modo, take ausente, colorway inválido, transcritor sem borda de palavra, ffmpeg que falhou).

## Os passos, cada um medido no arquivo

| Passo | O que acontece | Medida |
|---|---|---|
| 0 Entender | assistir o bruto e ver o plano (`--so-plano` para aqui) | |
| 1 Transcrever | tempo de palavra real (parakeet ou faster-whisper); a Groq infla o token e é recusada | |
| 2 Cortar | o vão entre as palavras diz ONDE, a energia da onda diz QUANTO (`ar_morto.py`) | piso de energia e respiro do `cortar_ar_morto.py` |
| 3 Enquadrar | janela 9:16 centrada no rosto medido, medidas pares | rosto mediano de várias amostras |
| 4 Luz | luminância medida vira brilho e contraste; HDR do celular vira SDR por LUT | alvo de luminância 111; brilho com teto |
| 5 Lettering | caixa nativa (opcional) | |
| 6 Render | corte, enquadre, luz, grade, velocidade e caixa numa só passada | sem arquivo intermediário reencodado |
| 7 Loudness | -14 LUFS, true peak -1,5 dBTP, dois passes | |
| 8 Gates | fala do bruto inteira no final; maior pausa; técnico | |

Se o rosto nunca é achado, a janela centra no quadro e o plano mostra o aviso: nunca finge que mediu.

## Aceleração

`projeto.json` define (padrão 1,2 em take real, `PADRAO_ACELERACAO["oneshot"]`). Não passe de 1,2 sem o ok de quem dirige.

## Ar morto

`scripts/cortar_ar_morto.py` é a peça de baixo do corte: ancora o corte no token do ASR. Limite conhecido: se o transcritor infla um token (um "Mas" de 7,3 s), o detector lê o vão como fala e não corta. É a razão de take de evento não ser one-shot. O corte renderizado traz um gate embutido que re-transcreve o resultado e sai com erro se sumiu palavra. Não desligue (`--sem-gate`) sem motivo escrito.

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
