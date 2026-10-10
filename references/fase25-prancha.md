# Fase 2.5: prancha de direção (o anúncio em quadro parado, antes do render)

A pergunta que esta fase responde: o anúncio está bom antes de gastar um render? Os defeitos que reprovam um anúncio quase sempre se julgam em quadro parado e em linha do tempo: enquadramento ilegível, texto decepado, lista que não empilha, faixa preta na costura, legenda dentro da interface do Reels, exposição, vão sem texto, cauda que não existe. Descobrir isso depois de um render de 25 minutos custa quatro renders. A prancha custa cerca de 4 minutos.

## Quem executa

**O executor é o subagente `diretor-arte-video-ads`**, com contexto limpo, lendo a prancha. Quem monta o anúncio não dirige o próprio anúncio. Se a skill `diretor-arte-video-ads` não estiver instalada, o próprio usuário faz o papel de diretor, com este mesmo roteiro de leitura. Use o modelo mais capaz que houver: é julgamento de olho, não braçal.

## Comando e saída

```
vam plano <slug> --prancha
```

Mede o plano (se ainda não mediu) e monta a prancha em `plano/prancha/*.png`, sem renderizar vídeo:

| Painel | O que mostra |
|---|---|
| Gancho | os primeiros segundos, quadro a quadro |
| Inserts | cada insert no enquadramento final, em 4 pontos da própria janela que ele usa |
| Letterings | cada lettering sobre o quadro exato onde pousa |
| Fechamento | CTA e logo |
| Régua | insert x avatar por tempo, vãos sem texto, densidade |

Todo quadro sai com a zona segura do Reels marcada (y 1690, x 940) e é o quadro real: footage mais overlay compostos. Os pontos de amostragem saem da regra (gancho fixo, insert em 4 pontos da janela, lettering na entrada e no fim), nunca da escolha de quem monta. Prancha montada a dedo vira teatro.

## O que o diretor faz (ele dirige, não carimba)

Leia todos os painéis. Para cada um, decida e escreva o porquê. Não confira o que já foi decidido: chegue com o material medido e as opções, e decida enquadramento, posição do lettering, tratamento de lista e o que abre o anúncio. As regras de ouro:

1. Todo claim forte tem um insert que o prova; fala de interface sem tela é fala solta.
2. O gancho tem texto cheio no quadro 0 e pelo menos um evento visual (insert, punch, corte) em 0 a 3 s.
3. De 2 a 3 KEYs no meio e uma de CTA; uma KEY só desperdiça os claims fortes, cinco viram decoração.
4. Texto nunca no rosto, nunca na interface do app.
5. Dado de pessoa real em captura de tela é motivo de trocar o arquivo.

## direcao.json (a saída)

O diretor escreve um `direcao.json` com **só o que o `vam plano` aceita**: `referencias`, `propostas`, `propostos` (e `trechos` no gravado). Exemplo:

```json
{
  "referencias": [{"nome": "demonstração de interface", "tecnicas": ["insert de tela cheia no gancho", "punch na KEY de número"]}],
  "propostas": [{"bloco": 3, "opcoes": ["gravação da planilha rodando", "template de dashboard (vam insert)"]}]
}
```

Depois: `vam plano <slug> --sugestoes direcao.json`. As decisões que mudam o render **não** entram no `direcao.json`: elas são aplicadas em `roteiro.md` (direção, âncora, layout) e em `projeto.json` (`inserts.<chave>`, `estilo`), e o diretor lista cada mudança no relatório dele.

## Regra do retorno

Se a passada final do `vam montar` voltar achando defeito de enquadramento ou de posição de texto, a prancha falhou. Conserte a prancha (a regra de amostragem), não só o anúncio.

Próximo: mostrar o plano ao aluno e `vam aprovar` (`fase2-plano.md`).
