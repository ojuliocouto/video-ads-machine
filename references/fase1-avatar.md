# Fase 1: avatar (HeyGen Avatar V)

O rosto vem do HeyGen e a voz é a do aluno. O motor trava o engine em `avatar_v` (`MANDATORY_ENGINE` em `scripts/avatar/heygen_cliente.py`): é o que dá lipsync realista. Outro engine só com `HEYGEN_ENGINE_OVERRIDE` explícito, assumindo a perda de qualidade.

## Antes de gastar

1. `vam doctor` sem FAIL e com a chave do HeyGen em OK (mostra o saldo).
2. `vam audio` passou (existe `voz/limpo.mp3`).
3. O aluno escolheu um look do HeyGen: **vertical e cheio** (look horizontal entra com tarja e o rosto fica com 35% do quadro). O `avatar_id` do look está no painel do HeyGen do aluno. Os looks do aluno ficam em `_local/looks.json`; nunca copie a lista de outra pessoa.

## Comandos

```
vam avatar <slug> --avatar-id <id> --plano medio   cadastra o look do projeto (uma vez), gera e confere
vam avatar <slug> --aprovar-look                   depois de OLHAR avatar/boca.png
vam avatar <slug> --existente avatar.mp4           usa um avatar já gerado desta voz limpa (custo zero)
vam avatar <slug> --teto-usd 9                     teto de gasto do job (padrão 9.0, cobre uma voz de cerca de 70 s)
```

`--plano` é o enquadramento do look: `fechado`, `medio` ou `aberto`.

## O que acontece

- Antes de pedir o job, o motor estima o custo pela duração da voz limpa (cerca de US$ 7 por minuto) e recusa se passar do teto. Nada é gasto e a mensagem diz a duração máxima que cabe.
- O saldo da carteira é lido antes e depois do job (`GET /v3/users/me`) e o gasto vai para `avatar/custo.json`. Passou do teto, a prova para e reporta.
- **Cauda do avatar.** O HeyGen costuma devolver o avatar alguns centésimos de segundo mais curto que a voz, e o transcritor dá o fim da última palavra um pouco depois do áudio. A footage pede o avatar até esse instante. Por isso, ao receber o avatar (download, `--retomar` ou `--existente`) e antes de conferir, o motor completa a cauda (`scripts/avatar/cauda.py`): congela o último quadro, completa o áudio com a voz original e deixa o avatar cobrir a voz com folga de 0,5 s. Ele registra numa linha (`avatar completado: ...`) e em `status.json` (etapa `cauda_avatar`). Isso só vale para falta de até 1,0 s. Mais que isso, a conferência reprova e diz a diferença.
- A conferência (`avatar/conferencia.json` e `avatar/boca.png`) reprova tamanho diferente de 1080x1920, fração útil do quadro abaixo de 0,93 e duração diferente da voz limpa em mais de 1,0 s. Saída 1 se reprova.
- **Olhe a boca.** Abra `avatar/boca.png` em resolução nativa. Só depois rode `--aprovar-look`: a aprovação é amarrada ao sha256 da conferência, e o `vam montar` recusa look sem aprovação vigente (`gate_look`).

## Custo e tempo

Veja a régua em `onboarding.md`. Em resumo: cerca de US$ 7 por minuto de avatar. Um anúncio de 30 s custa cerca de US$ 3,50 e um de 60 s custa cerca de US$ 7. O teto padrão é US$ 9,00 por job. O custo real do seu job fica em `avatar/custo.json`.

## Erros comuns

| Mensagem | Causa | Conserto |
|---|---|---|
| `sem voz/limpo.mp3` | pulou a Fase 0.5 | `vam audio <slug> --bruto voz.m4a` |
| `sem HEYGEN_API_KEY` | chave ausente | ponha no `.env`, ou use `--existente` |
| `o HeyGen recusou: ...` | conta, saldo ou look inválido | leia a mensagem; confirme o `avatar_id` |
| conferência reprovada por duração | avatar de outro áudio, ou mais de 1 s mais curto que a voz | regere a partir do `voz/limpo.mp3` atual (`--sobrescrever`) |
| `a voz tem N s e o avatar custaria cerca de US$ X ... Nada foi gasto` | a voz passa do teto | encurte a fala, ou rode com `--teto-usd` maior |
| `o look ... não está em looks.json` | primeira vez com este look | passe `--avatar-id` e `--plano` |

## Regras

- Gere um avatar por anúncio, depois de o áudio e o roteiro estarem fechados. Mudou a fala, regere.
- Nunca gere avatar e edite ao mesmo tempo: o plano é medido sobre o avatar final.

Próximo: `vam plano <slug>` (`fase2-plano.md`).
