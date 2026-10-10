# Fase 2: plano de edição medido e aprovado

O plano não é uma opinião: `vam plano` mede tudo o que dá para medir (voz limpa, roteiro, arquivos de insert) e só aceita do diretor referências e propostas. Depois, o aluno lê e aprova. Nada monta sem esse ok.

## Comandos

```
vam plano <slug>                       mede e escreve plano/plano.json e plano/plano_edicao.md
vam plano <slug> --sugestoes direcao.json   o mesmo, com as referências e propostas do diretor
vam aprovar <slug> --ok "<o ok do aluno>"   o ok, amarrado por sha256
```

## O que é medido (e por isso não se declara)

Blocos e tempos de cada um, mapa de inserts (largura, altura, duração, orientação, tratamento, visitas, congelamento previsto), hook, letterings (KEY, itens de lista e CTA, ancorados na palavra de pouso), densidade de insert, efeitos, ritmo previsto no arquivo entregue e a checklist. Declarar um desses campos no `--sugestoes` é erro. Todo tempo do `plano.json` está no relógio da gravação a 1x (antes da aceleração); só o bloco `ritmo` está em segundos entregues.

## As 6 seções obrigatórias

Plano sem qualquer uma é recusado pelo `vam aprovar`, citando a seção: **mapa de inserts, hook, lettering, densidade, referências, efeitos**.

## Densidade de insert

Alvo de 45 a 55% do tempo com insert na tela (`ALVO_MIN`, `ALVO_MAX`). Abaixo de 40% (`PISO`) ou acima de 65% (`TETO`) reprova mesmo com exceção; entre os limites e a faixa alvo, só com exceção em `projeto.json` com motivo escrito. Abaixo da faixa, o diretor propõe inserts novos para as falas que ficaram só no rosto (`propostas`, com no mínimo uma opção por bloco), e o aluno escolhe. Origem das opções, na ordem: gravação de tela do aluno; template de interface (`vam insert`); acervo próprio; geração por IA só como último recurso.

## A checklist do padrão de edição

Nove itens, cada um `atendido`, `nao_se_aplica` ou `pendente` com motivo. Pendente sem motivo reprova; pendente com motivo não impede a aprovação, mas aparece no `plano_edicao.md` para o aluno decidir com o motivo na frente.

1. Efeito visual e sonoro estratégico nos inserts
2. Elementos (logo, texto) atrás do apresentador, dando dinamicidade
3. Elementos chamativos, como setas, que prendem a atenção
4. Divisão da tela com o insert ocupando mais espaço que o apresentador
5. Degradê escuro entre o apresentador e o insert
6. Variação entre lettering e legenda, com fonte agradável nos dois
7. Variação do tipo de inserção conforme o contexto
8. A sensação de que a edição foi pensada em cada insert
9. Ritmo de paridade com a referência (cortes por minuto e tempo parado)

O status vem do que o plano mediu, nunca de declaração.

## O que é sugestão do diretor

Só quatro campos são aceitos em `--sugestoes`: `referencias` (nome e lista de `tecnicas`), `propostas` (bloco e `opcoes`), `propostos` (blocos cuja direção o plano propôs e que dependem do ok) e, no modo gravado, `trechos`. Campo desconhecido é erro. Modelo de plano que passa: `contratos/exemplos/plano.valido.avatar.json`.

A direção da cópia é do roteiro: sugestão é aditiva, nunca troca o tipo de bloco nem o arquivo que o roteiro marca.

## A cerimônia

1. Rode a Fase 2.5 (`fase25-prancha.md`) antes de mostrar o plano: a prancha acha, em minutos, o que custaria um render inteiro.
2. Mostre `plano/plano_edicao.md` ao aluno, com as pendências da checklist e as propostas de insert.
3. **Pare e espere o ok escrito dele no chat.**
4. `vam aprovar <slug> --ok "<o texto exato que ele escreveu>"`. Recusa plano sem as 6 seções, com pendência muda, medido de outra versão do roteiro, ou cujo `plano_edicao.md` não seja o do `plano.json` (o aluno tem que ter lido ESTE plano).

A aprovação amarra `roteiro.md`, `projeto.json`, `plano/plano.json` e `render/inserts.json`. Mudar 1 byte de qualquer um vence o ok e o `vam montar` recusa. Qualquer ajuste depois do ok volta para `vam plano` e para um ok novo.

Próximo: `vam montar <slug>` (`fase3-montagem-entrega.md`).
