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
vam avatar <slug> --teto-usd 5                     teto de gasto do job (padrão 5.0)
```

`--plano` é o enquadramento do look: `fechado`, `medio` ou `aberto`.

## O que acontece

- O saldo da carteira é lido antes e depois do job (`GET /v3/users/me`) e o gasto vai para `avatar/custo.json`. Passou do teto, a prova para e reporta.
- A conferência (`avatar/conferencia.json` e `avatar/boca.png`) reprova tamanho diferente de 1080x1920, fração útil do quadro abaixo de 0,93 e duração diferente da voz limpa em mais de 1,0 s. Saída 1 se reprova.
- **Olhe a boca.** Abra `avatar/boca.png` em resolução nativa. Só depois rode `--aprovar-look`: a aprovação é amarrada ao sha256 da conferência, e o `vam montar` recusa look sem aprovação vigente (`gate_look`).

## Custo e tempo

Veja a régua em `onboarding.md`. Em resumo: cerca de 200 a 227 créditos por minuto de avatar, 60 créditos por dólar. Um avatar de cerca de 1 minuto custa de US$ 3,2 a 4,4. O custo real do seu job fica em `avatar/custo.json`.

## Erros comuns

| Mensagem | Causa | Conserto |
|---|---|---|
| `sem voz/limpo.mp3` | pulou a Fase 0.5 | `vam audio <slug> --bruto voz.m4a` |
| `sem HEYGEN_API_KEY` | chave ausente | ponha no `.env`, ou use `--existente` |
| `o HeyGen recusou: ...` | conta, saldo ou look inválido | leia a mensagem; confirme o `avatar_id` |
| conferência reprovada por duração | avatar de outro áudio | regere a partir do `voz/limpo.mp3` atual (`--sobrescrever`) |
| `o look ... não está em looks.json` | primeira vez com este look | passe `--avatar-id` e `--plano` |

## Regras

- Gere um avatar por anúncio, depois de o áudio e o roteiro estarem fechados. Mudou a fala, regere.
- Nunca gere avatar e edite ao mesmo tempo: o plano é medido sobre o avatar final.

Próximo: `vam plano <slug>` (`fase2-plano.md`).
