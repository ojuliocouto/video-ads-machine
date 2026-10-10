# Gates: o que cada um reprova e com qual limiar

Tabela montada a partir do topo de cada gate em `scripts/gates/`, `scripts/gravado/` e `scripts/overlay/`. Quando este texto e o código divergirem, vale o código: o limiar mora na constante citada.

## Sumário

1. Como ler (saídas, laudo, exceções)
2. Modo avatar: antes do build
3. Modo avatar: sobre o plano e durante o build
4. Modo avatar: depois do render
5. Modo avatar: entrega
6. Modo gravado: os 11 gates mais a legenda
7. Modo one-shot

## 1. Como ler

- Toda saída de gate: **0 passa, 1 reprova (defeito medido), 2 insumo inválido (não deu para medir)**. Um gate que não mediu não aprova nem reprova.
- `vam montar` roda os gates na ordem abaixo (seção 2 em diante), escreve `entrega/laudo.json` e amarra o laudo ao sha256 do arquivo final. Mudou 1 byte do final, o laudo vence.
- O laudo agrupa os gates em 14 capacidades, C1 a C14 (ver `cinematografico.md`). Gate que a capacidade cita e não rodou entra como ERRO: ausência nunca aprova.
- Exceção a uma regra medida só existe em `projeto.json`, campo `excecoes`, sempre com `motivo` escrito, e só para as regras que o gate declara aceitar. Nenhuma variável de ambiente desliga gate.

## 2. Modo avatar: antes do build (sem render, barato)

| Gate | Etapa | O que reprova | Limiar |
|---|---|---|---|
| `gate_aprovacao` | antes | plano sem ok vigente do aluno; qualquer um dos 4 arquivos aprovados (`roteiro.md`, `projeto.json`, `plano/plano.json`, `render/inserts.json`) mudou depois do ok | sha256 byte a byte; emissor fixo |
| `gate_fidelidade_roteiro` | antes | insert sem arquivo em `inserts/` (ou arquivo sobrando); KEY, lista, hook, bloco ou fala do roteiro que não chegou ao plano; lettering inventado; âncora ambígua | igualdade exata com o roteiro |
| `gate_fidelidade_doc` | antes | só roda se o roteiro veio de Google Doc: comentário com N links que virou menos de N assets; âncora em mais de um bloco sem `nth`; pipoca com menos de 2 peças | N links = N assets |
| `gate_fala_roteiro` | antes | a voz limpa não cobre o roteiro | mais de 2% das palavras faltando, ou 3 palavras seguidas sumidas |
| `gate_entrada` | antes | respiro audível; ritmo achatado; fala comida pela higienização; avatar de outro áudio | energia acima de -34 dB em pausa de 0,62 s ou mais; voz de mais de 30 s com menos pausas acima de 0,60 s do que 1 a cada 15 s de fala (mínimo 2); trecho do bruto com menos de 0,60 das letras no limpo; avatar e voz limpa diferindo mais de 1,0 s |
| `gate_look` | antes | look inexistente, sem aprovação vigente (a conferência mudou), horizontal ou com conferência reprovada | aprovação amarrada ao sha256 da conferência |

## 3. Modo avatar: sobre o plano e durante o build

| Gate | Etapa | O que reprova | Limiar |
|---|---|---|---|
| `gate_geometria` | antes (plano) | legenda caindo no rosto: a posição é única (a base do quadro, y 1554 a 1682, e nada durante o CTA), então a faixa é cruzada com o núcleo do rosto do avatar cheio e do painel do split | interseção com o núcleo do rosto igual a zero; sem folga, a legenda é suprimida |
| `gate_safezone` | antes (plano) | faixa de legenda abaixo do teto da interface (a base do quadro termina em y 1682, o halo forte desce até ~1686) | y 1690 (`LIMITE_Y`) |
| `gate_lettering` | antes (plano) | menos de 2 ou mais de 3 KEYs no meio, ou sem KEY de CTA; menos de 8 s entregues entre dois letterings; KEY terminando em conector; KEY com mais de 2 linhas; legenda não suprimida na janela do lettering | exceções aceitas: `lettering.contagem`, `lettering.intervalo`, ambas com motivo |
| `gate_congelamento` | antes (plano) | insert cuja fonte acaba antes do bloco (último quadro clonado visível) | `analise_inserts.LIMITE_S` = 0,20 s |
| `gate_tela_vazia` | durante | janela do CTA longa demais; maior vão sem nenhum texto | `MAX_JANELA_CTA` 12,0 s de áudio; `MAX_VAO` 3,3 s de áudio (cerca de 2,4 s de tela) |
| `gate_congelamento_build` | durante | congelamento real medido na footage | 0,20 s |
| `gate_relogio` | durante | footage e overlay não saíram da mesma `timeline.json`: alinhamento, plano, `timing`, janelas de split, blocos, duração ou cauda divergentes | 1 quadro (`1 / fps` da própria timeline) |
| `gate_template` | durante | o template ou um parcial dele mudou no meio do build | assinatura do template antes e depois |

## 4. Modo avatar: depois do render (em paralelo, até 4 ao mesmo tempo)

| Gate | Etapa | O que reprova | Limiar |
|---|---|---|---|
| `gate-ad` | depois | vão sem texto na tela; primeiro texto tardio; frame solto de outra cena dentro de insert; insert do mapa sem arquivo; loudness | `MAX_SEM_LEGENDA_PCT` 12%; `MAX_BURACO_S` 2,5 s; gancho: no máximo `HOOK_MAX_SEM_TEXTO_S` 1,0 s sem texto em 0 a 3 s |
| `medir_ritmo` | depois | anúncio lento ou picotado | 16 a 32 cortes por minuto (`MIN_CORTES_MIN`, `MAX_CORTES_MIN`); até 40% do tempo em plano de mais de 6 s (`MAX_FRAC_LENTA`); maior plano até 14 s (`MAX_PLANO_S`) |
| `gate-colisao-texto` | depois | tinta de texto no núcleo do rosto | `LIMIAR_COLISAO_PADRAO` 1,5% do núcleo; amostra a cada 0,5 s no build |
| `gate-contraste-legenda` | depois | qualquer texto (gancho, legenda inteira com a camada apagada, lettering, CTA) ilegível contra o fundo local | contraste 4,5:1 (`contraste_texto.PISO`) em toda amostra, 5 por segundo; só a dissolução de entrada e de saída fica de fora |
| `gate_cobertura_legenda` | depois | palavra falada sem texto na tela fora das janelas de lettering (a palavra sob lettering não é contada nem penalizada: legenda e lettering nunca juntos), gancho e CTA (o CTA é lettering e não leva legenda); CTA que entra antes do início do bloco cta | até 3% (`MAX_SEM_TEXTO_PCT`) das palavras avaliadas sem texto; vão entre textos de até 0,5 s (`VAO_PONTE_S`) não conta; folga de 0,35 s em volta do lettering é isenta; a janela do CTA começa no bloco cta |
| `auditar_ad` | depois | flash escuro no corte; frame solto; tela escura; silêncio na faixa de voz | queda de 25 níveis ou mais no corte; tela escura acima de 0,35 s; silêncio acima de `PAUSA_MAX_TELA` (0,60 s) mais `TOLERANCIA_SILENCIO_S` (0,10 s) |
| `gate_hook_visual` | depois | gancho sem texto no quadro 0; nenhum evento visual em 0 a 3 s; abertura escura; texto ilegível | primeiro texto legível em até 0,25 s; no máximo 1,0 s sem texto legível; quadro 0 com luminância de pelo menos 0,6 da mediana |
| `gate_camera` | depois | câmera parada; punch sem ganho; mais de 20 s sem movimento; punch em insert ou em split | escala da imagem varia 8% ou mais num plano de avatar de 2 s ou mais; punch com +15% medido (`PUNCH_GANHO_MIN`) |
| `gate_cor` | depois | sem as 3 tags bt709; quadro 0 escuro; plano escuro demais; rosto vermelho | quadro 0 com pelo menos 0,6 da mediana; mediana de luminância do plano 20 ou mais; razão R/G da pele até 1,6 |
| `gate_mix` | depois | loudness fora; true peak alto; cama que não respira nas pausas ou sobe sob a fala; trilha cantada | -14 LUFS mais ou menos 1,2 (`LUFS_ALVO`); true peak até -1,5 dBTP (`TP_ALVO`); cama sobe de +1,5 a +8 dB em 75% das 8 maiores pausas; trilha com mais de 60 caracteres transcritos reprova |
| `gate_sfx` | depois | efeito fora de riser, tick ou boom; nível errado; densidade; evento na volta ao apresentador; efeito sem a função declarada | -38 a -31 dBFS RMS; no máximo 1 evento a cada 4 s; riser 1,0 s antes do CTA |
| `gate_insert` | depois | densidade de insert fora da faixa; congelamento; faixa morta; insert horizontal sem moldura | 45 a 55% (`ALVO_MIN`, `ALVO_MAX`), nunca abaixo de 40% nem acima de 65% (`PISO`, `TETO`), mesmo com exceção; faixa morta contínua acima de 40 px |
| `gate_lettering_depois` | depois | KEY que não lê em 0,15 s; CTA sem seta que se mexe | tinta da KEY de 90% ou mais até 0,15 s depois da entrada |
| `gate_safezone_depois` | depois | tinta real do overlay fora da zona segura | y acima de 1690 ou x acima de 940 reprova; a faixa de 1250 a 1690 só gera relato |
| `gate_geometria_depois` | depois | tinta real do overlay sobre o rosto no quadro entregue | mesma definição de núcleo do `gate-colisao-texto` |
| `gate_texto_atras` | depois | opcional (C13), desligado por padrão: o build ainda não compõe texto atrás da pessoa | não ligue `estilo.texto_atras` |

## 5. Modo avatar: entrega

| Gate | Etapa | O que reprova | Limiar |
|---|---|---|---|
| `gate_entrega` | entrega | laudo que não é PASS ou de outro build; aprovação do plano vencida; nota ausente, de outro arquivo ou baixa | laudo, aprovação e nota amarrados ao mesmo sha256; nota de 8 ou mais (`NOTA_MINIMA`), uma rodada |

## 6. Modo gravado: os 11 gates mais a legenda

Rodam com `vam gravado <slug> gates`; `vam gravado <slug> entregar` não copia nada se qualquer um sair com 1 ou 2.

| Gate | O que reprova | Limiar |
|---|---|---|
| `gate_envelope` | o Voice Isolator comeu fala: bruto com voz e limpo mudo | mudo por 0,5 s ou mais; limpo mais curto que o bruto em mais de 0,5 s |
| `gate_fala` | palavras perdidas entre o bruto e o limpo, só nos trechos usados | mais de max(2, 3% das palavras) |
| `gate_voz_distante` | fala de outra pessoa dentro de um trecho escolhido | bloco com pico 6 dB ou mais abaixo da mediana dos blocos longos |
| `gate_retomada` | frase repetida entre sub-blocos vizinhos; fragmento curto na borda de um trecho | similaridade `SIMIL`; fragmento aceito só se declarado no plano com motivo |
| `gate_redundancia` | dois trechos que dizem a mesma ideia colados | 2 ou mais termos portadores em comum nos 6 s antes e depois da costura |
| `gate_emendas` | palavra cortada ao meio ou resto de retomada na costura | folga `TOL_S` 0,08 s |
| `gate_ar_morto` | pausa acima do que o cortador deixa | `RESPIRO + 2 x MARGEM + 1 quadro` (cerca de 0,42 s mais 1 quadro), na fonte |
| `gate_repeticao` | n-grama repetido perto na peça entregue | 5 palavras, a até 40 palavras de distância |
| `gate_offscript` | pergunta a quem dirige, hesitação ou palavrão na peça | expressão inteira, com contexto |
| `gate_sincronia` | peça legendada que não veio do corte atual | duração dentro de `TOL_DURACAO_S` e impressão digital de quadros |
| `gate_legenda` | vão sem texto; linha longa demais | 12% sem texto, vão de até 2,5 s, linha até `MAX_CHARS` |
| `legenda_aprovada` | `.ass` editado depois do ok, ou arquivo legendado que não saiu da queima aprovada | sha256 do `.ass` igual ao da aprovação e ao da queima |
| `tecnico` | resolução, 48 kHz, loudness ou true peak fora | -14 LUFS, true peak até -1,5 dBTP |

## 7. Modo one-shot

`vam oneshot` roda, depois do render: a fala do bruto está inteira (re-transcrição), a maior pausa (ar morto) e o técnico (resolução, 48 kHz, loudness e true peak). Detalhe em `oneshot.md`.
