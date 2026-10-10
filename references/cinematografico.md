# Cinematográfico: 14 capacidades, cada uma com número e gate

"Cinematográfico" não é adjetivo aqui. É uma lista de 14 capacidades; cada uma tem um padrão, onde mora no código, o gate que a prova e o número que reprova. O laudo (`entrega/laudo.json`) traz o status de cada uma: PASS, REPROVA, DESLIGADA (só a C13) ou NAO_SE_APLICA (todos os gates dela foram pulados com motivo, como no formato 1x1). Tabela de gates e limiares em `gates.md`.

## Sumário

1. Visão geral (C1 a C14)
2. Imagem: C1 a C5
3. Texto: C6, C7, C9
4. Inserts: C8
5. Som: C10 a C12
6. C13 e C14
7. Regras de ouro da direção

## 1. Visão geral

| # | Capacidade | Gate | Reprova quando |
|---|---|---|---|
| C1 | Gancho visual de 0 a 3 s | `gate_hook_visual`, `gate-ad` | primeiro texto legível depois de 0,25 s; mais de 1,0 s sem texto legível; nenhum evento visual; quadro 0 com luminância abaixo de 0,6 da mediana |
| C2 | Ritmo de corte | `medir_ritmo` | fora de 16 a 32 cortes/min; mais de 40% do tempo em plano de mais de 6 s; plano de mais de 14 s |
| C3 | Câmera viva | `gate_camera` | imagem com variação de escala abaixo de 8% num plano de avatar de 2 s ou mais; punch sem +15% medido; mais de 20 s sem movimento |
| C4 | Transição com motivo | `auditar_ad`, `gate-ad` | flash escuro no corte (queda de 25 níveis ou mais); frame solto; tela escura acima de 0,35 s |
| C5 | Grade e cor | `gate_cor` | sem as 3 tags bt709; plano com mediana de luminância abaixo de 20; razão R/G da pele acima de 1,6 |
| C6 | Legenda karaokê | `gate-ad`, `gate-contraste-legenda`, `gate-colisao-texto`, `gate_safezone`, `gate_geometria` | mais de 12% sem texto; vão acima de 2,5 s; contraste abaixo de 4,5:1; texto no núcleo do rosto; tinta abaixo de y 1690 ou à direita de x 940 |
| C7 | Lettering de pico | `gate_lettering` | 2 a 3 KEYs no meio mais a de CTA fora da contagem; menos de 8 s entre letterings; KEY terminando em conector ou com mais de 2 linhas; legenda junto |
| C8 | Insert com tratamento | `gate_insert`, `analise_inserts` | densidade fora de 45 a 55% sem exceção; congelamento acima de 0,20 s; faixa morta; horizontal sem moldura |
| C9 | Elemento de atenção | `gate_lettering_depois` | CTA sem seta em movimento medido |
| C10 | Música com ducking | `gate_mix` | cama não sobe de +1,5 a +8 dB nas pausas reais; sobe +1,5 dB sob a fala; trilha cantada |
| C11 | SFX com função | `gate_sfx` | nível fora de -38 a -31 dBFS RMS; mais de 1 evento a cada 4 s; evento na volta ao apresentador |
| C12 | Som de entrega | `gate-ad`, `gate_mix` | fora de -14 LUFS (mais ou menos 1,2) ou true peak acima de -1,5 dBTP |
| C13 | Texto atrás da pessoa (opcional) | `gate_texto_atras` | não ligar: o build ainda não compõe |
| C14 | Relógio único | `gate_relogio` | footage e overlay divergem da `timeline.json` em mais de 1 quadro |

## 2. Imagem: C1 a C5

- **C1.** O texto cheio nasce no quadro 0. O bloco 0 é uma demonstração (insert) ou uma provocação com KEY. A abertura mais escura que o resto do anúncio foi medida em 57% e é a janela que decide a retenção no Reels. Eventos que contam: corte confirmado (plano e imagem concordam), punch ou insert que entra.
- **C2.** Alvo medido em referências de anúncio de ritmo bom: de 18,9 a 27,8 cortes por minuto; anúncios chamados de lentos faziam de 4,7 a 7,6. Constantes: `MIN_CORTES_MIN`, `MAX_CORTES_MIN`, `MAX_FRAC_LENTA`, `MAX_PLANO_S` em `scripts/medir_ritmo.py`. A régua é o arquivo entregue (tempos divididos pela aceleração).
- **C3.** Zoom contínuo de cerca de 16% alternando por plano; **punch** de ênfase de 1,00 para 1,22 em 0,28 s na KEY em avatar cheio, segurando até 2,4 s e voltando seco em 2 quadros (`PUNCH_*` em `scripts/cinema/camera.py`); respiro de 1,10 para 1,00 na entrada de etapa; push-in em gravação de tela (alvo 0,75, teto 1,70). Nunca punch em insert, em split ou em lettering de split. O gate mede a escala da imagem (pontos de textura entre quadros), não a caixa do rosto: um avatar parado balança 12% na caixa e só 1,6% na escala.
- **C4.** Apresentador para apresentador é corte seco de 1 quadro. Entrada de insert seca; a volta pode ser macia até 0,20 s. `fadeblack` e `fadewhite` são proibidos. Nunca passe pelo preto.
- **C5.** Preset `quente-suave` (`PADRAO` em `scripts/cinema/grade.py`): grão, contraste 1,03, saturação 0,97, vinheta e a camada quente do template. Insert com exposição de piso 105 e página branca intocada. Tags de cor sempre bt709; a tag HDR/HLG que o libx264 grava sozinho faz o WhatsApp e o iPhone decodificarem avermelhado.

## 3. Texto: C6, C7, C9

- **C6, legenda.** Inter 800 de 80 px, contorno de 0,078 em, preenchimento linear no tempo real de cada palavra (uma cor que vai preenchendo, sem escala, sem salto: três versões com movimento de palavra foram reprovadas), verbatim do `roteiro.md`. A ênfase é por cor (`#E87D4E`, terracota). A legenda segura até 1,60 s na pausa (`SEGURAR_MAX` em `scripts/build_timeline.py`) para a tela não ficar sem texto entre frases. Posição pelo fundo: avatar cheio usa a padrão; insert cheio manda para o rodapé; tela dividida vai para a costura entre os painéis. Sobre fundo claro a tinta inverte sozinha (preta com halo claro), onde a tinta branca cruzaria o piso de 4,5:1. O contraste é lido no quadro entregue, na camada acesa e na apagada, a 5 amostras por segundo (`PISO` em `scripts/gates/contraste_texto.py`).
- **C7, letterings.** De 2 a 3 KEYs no meio e uma KEY de CTA com logo. Estilos: `caixa_nativa` (3 colorways), `serif_editorial` (padrão), `punch`, `marcador`, `statement`, `lateral`, `seta_cta`, `gigante_atras` (`ESTILOS` em `scripts/cinema/lettering_estilos.py`). Entrada seca e legível em até 0,15 s com 90% da tinta; nunca junto com legenda; nunca atravessa uma troca de layout. Exceções só com motivo: `lettering.contagem` e `lettering.intervalo`.
- **C9.** Seta animada no CTA; marcador na KEY de número ou promessa. Enfeite que não carrega informação nova (pílula de status, rótulo que narra o óbvio) não entra.

## 4. Inserts: C8

Densidade de 45 a 55% do tempo (piso 40, teto 65). Insert horizontal entra **inteiro em moldura de navegador**; recorte declarado em split é proibido. No máximo 2 visitas ao mesmo insert por bloco (`MAX_VISITAS`). Fatia de footage de 3,6 s ou mais (`TELA_MIN`). Fala dêitica ("olha isso aqui") trava o insert na tela. Split com degradê de 90 px na emenda e o insert dominando o painel. Em gravação de tela use `crop` e deixe o `zoom` em 1,0: zoom corta pelas bordas e decapita a primeira letra de cada linha.

## 5. Som: C10 a C12

- **C10.** Trilha do aluno nivelada a -20 dBFS (`NIVEL_TRILHA_DBFS` em `scripts/cinema/musica.py`). Cama de 0,055 sob a fala e de 0,42 nas pausas reais do envelope (queda de 12 dB abaixo da mediana, 0,5 s ou mais), rampa de 150 ms, fade de entrada de 1,2 s e de saída de 2,2 s. Sem pausa real num monólogo denso, a cama fica constante: forçar respiro vira bombeamento ("a música fica aumentando e diminuindo do nada").
- **C11.** Riser 1,0 s antes do CTA; tick por linha de pilha; boom na KEY `gigante_atras`. Whoosh desligado. Nunca na volta ao apresentador. Peça sem efeito nenhum passa: vazio é melhor que inventar.
- **C12.** `LUFS_ALVO` -14 e `TP_ALVO` -1,5 em `scripts/audio/loudness.py`; 48 kHz.

## 6. C13 e C14

- **C13, texto atrás da pessoa.** Opcional (`estilo.texto_atras` no `projeto.json`) e **desligado por padrão**. Hoje o build não compõe essa camada e o gate devolve ERRO se alguém a liga: deixe `texto_atras` em `false`. Quando existir, valerá só em plano de avatar cheio com 300 px ou mais de parede acima da cabeça.
- **C14, relógio único.** O alinhamento da fala acontece uma vez e vira a `timeline.json`. Footage e overlay leem o mesmo arquivo. Dois motores alinhando cada um por si derivaram 1,07 s num anúncio de 2 minutos.

## 7. Regras de ouro da direção

1. Todo claim forte tem um insert que o prova.
2. O gancho mostra, não explica: texto cheio no quadro 0 e um evento visual em até 3 s.
3. De 2 a 3 KEYs no meio mais a de CTA: uma só desperdiça os claims fortes, cinco viram decoração.
4. Texto nunca no rosto e nunca na interface do app.
5. Movimento precisa de motivo: asset que já entra grande não ganha push-in.
