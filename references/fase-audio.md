# Fase 0.5: áudio (a fase que decide se o avatar vale o dinheiro)

O avatar fala exatamente o áudio que recebe. Um defeito de áudio descoberto depois do avatar custa um job novo do HeyGen e um build inteiro. Por isso o áudio é uma fase própria, antes do avatar.

## Comando

```
vam audio <slug> --bruto voz.m4a       copia para voz/bruto.*, higieniza e confere
vam audio <slug>                       higieniza e confere de novo o voz/bruto.* que já está no projeto
vam audio <slug> --limpo voz_limpa.mp3 usa uma voz já higienizada (sem cortar de novo) e confere
```

Entra: a gravação da voz do aluno (m4a, mp3, wav). Sai: `voz/limpo.mp3` e `voz/auditoria.json`. Saída 1 se alguma conferência reprova: refaça a gravação ou a higienização antes de qualquer avatar.

## O que a higienização faz

Encurta só as pausas grandes (respiração) e preserva o ritmo. Ela não retira palavra. A pausa máxima na tela depois da aceleração é 0,60 s (`PAUSA_MAX_TELA` em `scripts/higienizar_audio.py`).

## As quatro conferências (todas rodam; o motivo junta as que reprovaram)

| Conferência | Reprova quando | Por que existe |
|---|---|---|
| respiro | energia acima de -34 dB dentro de uma pausa de 0,62 s ou mais | o Avatar V faz lipsync da respiração e a boca mexe no vazio |
| ritmo achatado | voz de mais de 30 s com menos de 4 pausas acima de 0,60 s | higienização que corta toda pausa picota a fala |
| fala preservada | trecho do bruto com menos de 0,60 das letras no limpo | o corte já comeu 4 palavras e só apareceu no vídeo pronto |
| fala x roteiro | mais de 2% das palavras do roteiro faltando, ou 3 seguidas sumidas | a voz gravada tem que cobrir o roteiro aprovado |

Pausa longa e limpa é ritmo e é boa: o que se mede é energia dentro da pausa, não duração. Elisão natural ("vamos embora" e "vambora") fica no relatório como suspeita e não reprova; declare-a em `equivalencias` do glossário.

## Quando o transcritor erra

A fala x roteiro usa o transcritor da máquina (parakeet, faster-whisper ou Groq, nessa ordem). Se o nome do produto sai errado ("Cloud" por "Claude"), declare a variante em `_local/glossario.json`. Não edite o roteiro para casar com o erro do ASR.

## Regras

- Voz sempre real. TTS é o primeiro sinal de conteúdo feito por IA.
- Mudou o áudio, regere o avatar: não existe consertar o áudio depois do lipsync pronto.
- Nunca mande o áudio ao HeyGen sem `vam audio` passar.

Próximo: `vam avatar <slug> ...` (`fase1-avatar.md`).
