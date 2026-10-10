# Lições: cada regra nasceu de um defeito real

Este arquivo é a memória do motor. Cada item abaixo existe porque um anúncio real saiu com o defeito descrito. Antes de mexer na lógica de tempo, de texto ou de corte, leia a seção que toca no que você vai mexer. Regra que você tirar daqui volta a quebrar. Nome de pessoa e de cliente não entra: o número fica, o nome sai.

## Sumário

1. Armadilhas do render em HTML (HyperFrames)
2. Montagem: o que nunca regride
3. Áudio: o que o avatar grava para sempre
4. Medir o arquivo entregue, não o plano
5. Gate cego e gate com limiar chutado
6. Take gravado: onde o corte erra
7. Histórico de defeitos do primeiro anúncio de produção
8. Checklist de leitura de quadros antes de entregar

## 1. Armadilhas do render em HTML (HyperFrames)

1. **O clipe some no fim do `data-duration`.** Segurar opacidade com animação além do fim do clipe não funciona: o elemento desaparece em `data-start + data-duration`, qualquer que seja a animação. Consequência prática: a camada que cobre o avatar quando um insert entra tem que nascer opaca no primeiro quadro (um fade-in transparente deixa o rosto aparecer por cerca de 0,2 s), e o gancho só fica na tela enquanto o `data-duration` dele permitir.
2. **Legenda cujo fade-out termina depois do fim do grupo empilha com a próxima.** O fade-out tem que acabar exatamente no fim do grupo. Passou disso, as duas legendas ficam sobrepostas por 2 a 3 quadros.
3. **O lint não vê colisão de layout.** Ele valida estrutura (atributos, sintaxe, referências). Texto em cima da boca, dois blocos na mesma área e lettering descolado da fala só aparecem no MP4 renderizado. Lint verde é necessário e não basta.
4. **Centralizar com `left:50%` mais `xPercent:-50` na animação, nunca com `translateX(-50%)` no CSS.** A animação reescreve o `transform` inteiro: o elemento perde a centralização e aparece deslocado e esticado (foi assim que um logo gigante cobriu o rosto num render).
5. **Preview não é prova.** Já houve divergência entre o preview e o render. A auditoria é sempre sobre o MP4 final. Para medir geometria, `getBoundingClientRect()` vale mais que o estado depois de um `seek()`.
6. **Gravação de tela como insert exige `--video-frame-format png`.** Sem isso a compressão do quadro degrada o texto fino da interface.
7. **Tela preta de 0,3 a 0,5 s no meio da entrada de um insert.** Causa: o modo rápido de captura fotografa a área do cartão antes de o `<video>` decodificar o primeiro quadro depois do seek. O modo correto (camadas) corrige, mas pesa tanto em memória que derrubou uma máquina de 18 GB duas vezes, mesmo com um worker só. Já foram descartados como causa: GOP e keyframes (a falha é idêntica com all-intra), número de workers, captura rápida desligada, a flag `--hdr` e o tamanho do arquivo. Também falhou antecipar o `data-start` do vídeo em 1,5 s e em 4 s, com opacidade 0, 0,01 e 1: todas dão os mesmos bytes pretos. Não repita essa investigação; reaplique o modo de camadas só numa máquina com memória livre de sobra.
8. **Um build de cada vez, no máximo 2 renders pesados na máquina.** Mais que isso derruba o computador, não só o render.

## 2. Montagem: o que nunca regride

- **Dois motores leem a mesma regra de tempo.** O overlay (texto) e a footage (imagem) calculavam spans por conta própria e derivaram até 1,07 s no fim de um anúncio de 2 minutos. Hoje os dois leem a mesma `timeline.json` e o `gate_relogio` confere. Regra nova que mexe em tempo entra na timeline, nunca em um lado só.
- **O gancho nasce com o quadro 0 cheio de texto.** A abertura em insert (a demonstração) começa em t=0; o apresentador só entra no bloco seguinte. O gancho dissolve quando o rosto volta, sem invadir o rosto. Abertura curta gera gancho curto: não force um piso fixo.
- **Nenhuma legenda do corpo enquanto o gancho está na tela.** Dois textos concorrendo na abertura derrubam a leitura.
- **Legenda e lettering nunca juntos.** A legenda some na janela do lettering; o lettering vira o texto principal do trecho.
- **Sem selo, sem pílula de status, sem rótulo que narra o que já está visível.** Enfeite que não carrega informação nova foi banido duas vezes.
- **Inserts colados por corte seco.** Nunca o rosto do apresentador entre dois inserts seguidos (intervalo de até 0,6 s entre eles). A volta ao apresentador é um fade limpo do insert.
- **Transição só de entrada, e curta.** Transição de saída produzia flash escuro e "transição dupla". Apresentador para apresentador é corte seco de 1 quadro: um deslize entre dois planos da mesma pessoa lê como tela rasgando.
- **A cauda do áudio nunca é cortada.** Duração total = duração real do avatar + 0,20 s, arredondada para cima em centésimos.
- **Aceleração de 1,35 com avatar e de 1,2 com take real.** Uma aceleração só, na constante do projeto (`PADRAO_ACELERACAO`). O avatar gerado aguenta mais que a respiração real de uma pessoa: 1,35 em take gravado foi reprovado como "acelerado demais".
- **Máximo de 2 visitas ao mesmo insert por bloco** (`MAX_VISITAS`). A terceira mostra o mesmo quadro e o corte nem registra: metade dos cortes de um anúncio eram invisíveis.
- **Insert horizontal entra inteiro em moldura de navegador.** Recorte declarado em split descartava a medição do arquivo, ampliava de 1,5 a 2,4 vezes e decapitava as linhas da tela.
- **Voz sempre real, zero TTS.** Voz sintética é o primeiro sinal de conteúdo feito por IA.
- **Zero travessão em qualquer texto de tela; acentuação correta.**

## 3. Áudio: o que o avatar grava para sempre

O avatar fala o áudio que recebeu. Defeito no áudio descoberto depois do avatar custa um job novo e um build inteiro.

- **Respiro audível vira boca mexendo no vazio.** O lipsync do avatar acompanha a respiração. Mede-se energia dentro da pausa (acima de -34 dB numa pausa de 0,62 s ou mais reprova), não a duração da pausa.
- **Higienização que corta toda pausa picota a fala.** Voz de mais de 30 s com menos de 4 pausas acima de 0,60 s reprova por ritmo achatado.
- **O corte comeu fala: re-transcreva.** Em um caso o corte tirou 4 palavras e só apareceu no vídeo pronto. O bruto e o limpo são transcritos de novo e comparados; trecho do bruto com menos de 0,60 das letras no limpo reprova.
- **Duração do avatar contra a voz limpa: tolerância de 1,0 s.** Um avatar de 92,8 s gerado de uma voz de 78,0 s era o áudio errado.
- **O silêncio se mede na faixa de voz, não no arquivo final.** A música sobe nas pausas (cama de 0,42) e mascara o silêncio.
- **Transcrição de ASR erra o nome do produto.** Em uma leva, o nome do produto saiu errado em 39 ocorrências de 10 dos 12 anúncios. A legenda vem do roteiro, nunca da transcrição crua, e o glossário do projeto corrige o que o ASR escreve errado.
- **Nunca TTS para consertar áudio.** Mudou o áudio, regera o avatar.

## 4. Medir o arquivo entregue, não o plano

- **Dinâmico virou opinião até haver número.** Medido com o mesmo método nos dois lados (detecção de cena, limiar 0,30): as referências aprovadas fazem de 18,9 a 27,8 cortes por minuto; os anúncios reprovados por "lentos" faziam de 4,7 a 7,6. O gate de ritmo usa a faixa de 16 a 32 (`MIN_CORTES_MIN`, `MAX_CORTES_MIN`) e até 40% do tempo em plano de mais de 6 s. Uma referência de gancho tem 2,1 cortes por minuto e não serve de régua de dinâmica.
- **Câmera parada se mede na imagem, não na caixa do rosto.** O detector de rosto balança 12% sozinho num avatar parado. A escala da imagem (pontos de textura seguidos entre quadros) tem ruído de 1,6%, e o zoom de 16% mede 16 a 17%.
- **Relógio do overlay = relógio do entregue vezes a aceleração, mais o deslocamento inicial.** Medir sem essa conversão desloca todos os cortes conferidos.
- **Número que descreve o material sai de medição.** Enquadramento, recorte, velocidade de insert, qual ocorrência de uma palavra, se um arquivo cabe num painel: tudo medido. Os três defeitos que mais custaram tempo numa produção foram todos valor chutado e todos resolveram de primeira quando medidos.
- **Congelamento é aritmética.** `consome = duração do bloco x velocidade`; `congela = max(0, consome - (duração da fonte - início))`. Quatro inserts congelavam, somando 3,68 s de áudio, e nenhum quadro parado denunciava, porque um quadro congelado parece um quadro normal repetido.
- **Zona segura rígida.** Nenhuma tinta abaixo de y 1690 (teto da interface do Reels) nem à direita de x 940 (coluna de curtir e comentar).

## 5. Gate cego e gate com limiar chutado

- **Gate que não acha o que medir reprova.** Um gate cego já aprovou uma legenda inteira renderizada a 82% de opacidade.
- **Contraste: 28 gates aprovaram dois defeitos que o gate antigo não via.** O gancho branco e fino ficou 2,1 s sobre um insert claro, e a camada apagada do karaokê virou cinza sobre o insert claro. Causas medidas: tinta só com alfa acima de 250 (a camada apagada nunca contava), fundo pela média da faixa horizontal inteira (longe da letra, e pulado em silêncio quando um scrim cobre a largura toda), aprovação pela mediana, e uma amostra a cada 0,5 s com o CTA cortado. Hoje o invariante é um só: em toda amostra (5 por segundo), cada pedaço de texto tem contraste de 4,5:1 ou mais entre a tinta e o anel de fundo local, no quadro entregue.
- **Limiar sai do passo que o gate fiscaliza.** O teto de pausa do gate de ar morto é `RESPIRO + 2 x MARGEM + 1 quadro`; o silêncio do auditor sai de `PAUSA_MAX_TELA` mais 0,10 s. Número redondo escolhido à mão reprova a peça boa ou aprova a ruim.
- **Gate mais duro que a referência reprova a própria referência.** O teto de plano parado foi calibrado entre o que as referências fazem (16% a 31%) e o que os anúncios lentos faziam (87% a 94%).
- **Quem é medido não assina.** O montador escreve o laudo; o auditor escreve a nota; o aluno aprova o plano. Cada assinatura é amarrada por sha256 ao arquivo certo. Um laudo de um build anterior não vale para o arquivo de agora.
- **Exceção só no projeto, sempre com motivo escrito.** Nenhuma variável de ambiente desliga um gate. O motivo vai para o laudo.
- **Auditar por amostra de quadros escolhidos falha.** O defeito está entre os quadros escolhidos: flash escuro de 2 quadros em cada corte, insert congelado por 3,5 s, insert quase preto. Só varredura completa pega.

## 6. Take gravado: onde o corte erra

- **Ancorar o corte no token do ASR tem limite.** Quando o transcritor infla um token (um "Mas" de 7,3 s), o vão vira fala e não é cortado, e o token pode abranger duas vozes: o corte começou no meio e o anúncio abriu com 8 s de outra pessoa falando. Em evento, a borda sai de energia e o token só entra para achar a borda da palavra, com um transcritor local de tempo de palavra real.
- **Retomada com pausa curta (0,3 s) passa por cima da comparação por frase.** O ASR deduplica. Por isso a leitura é por sub-bloco, com separador de 0,14 s, comparando por similaridade (a retomada com palavra trocada não é igual).
- **Redundância é defeito de montagem.** Dois trechos limpos que, colados, dizem a mesma coisa (o corpo termina nomeando o produto e o CTA abre nomeando de novo, em 4 s). Mede-se por termos portadores em comum nos 6 s antes e depois da costura.
- **Ouvir a peça inteira ou o sub-bloco isolado não acha meia palavra na emenda.** O tempo de palavra de um transcritor local acha: palavra que atravessa a emenda é palavra cortada.
- **Peça legendada precisa vir do corte atual.** Re-renderizar e esquecer de re-legendar entregou a versão velha com cara de nova. A comparação por duração não pega a troca; a impressão digital de quadros pega.
- **Fala de quem dirige.** Quem fala fora de quadro chega de 6 a 12 dB mais baixo no microfone de lapela. Um bloco com pico 6 dB abaixo da mediana dos blocos longos é voz distante.
- **O corte é feito por trecho usado, não pelo take inteiro.** Medir o take inteiro reprovou uma peça por fala que o plano descartou.

## 7. Histórico de defeitos do primeiro anúncio de produção

| # | Defeito reportado | Causa raiz | Correção |
|---|---|---|---|
| 1 | Cortes secos no áudio | higienização agressiva | higienização proporcional |
| 2 | Legenda duplicada com o lettering | render independente | legenda suprimida na janela do lettering |
| 3 | Cor do apresentador vermelha | variância do avatar e da grade | grade quente a 50%, calibrada contra um anúncio aprovado; razão R/G da pele não passa de 1,6 |
| 4 | Cartão sobre o avatar | deriva de spans não contíguos | contiguidade entre spans |
| 5 | Abertura no avatar | piso do gancho forçando o bloco 0 | bloco 0 insert começa em t=0 |
| 6 | Flash preto numa frase | transição de saída | só transição de entrada |
| 7 | Flash do avatar entre inserts | camada de cobertura com fade transparente | camada opaca no primeiro quadro, corte seco |
| 8 | Transição piscando 2 vezes | espera real de 0,02 s | espera real até t+0,9 |
| 9 | Áudio cortado no fim | duração total menor que a real | cauda de 0,20 s com arredondamento para cima |
| 10 | Selo sobre os inserts | elemento fixo de 2,7 s | selo removido do template |
| 11 | Dois textos na abertura | filtro de legenda pelo fim | porta pelo início (`start` maior que o fim do gancho) |
| 12 | Legendas empilhando na troca | fade-out terminando 0,10 s depois do fim | fade-out termina no fim do grupo |
| 13 | Gancho passando rápido (0,7 s) | duração do clipe e fade curtos | duração do gancho escalada com a abertura |
| 14 | Rosto aparece tarde (2 ou mais inserts na abertura) | referência fixa ao segundo bloco | referência = primeiro bloco que não é insert |
| 15 | Tela preta de 0,3 a 0,5 s na entrada do insert | modo de captura rápido (seção 1, item 7) | ver seção 1 |

## 8. Checklist de leitura de quadros antes de entregar

Leia cada quadro com os próprios olhos; o script extrai, a leitura é sua.

1. Abertura (t = 1,0, 2,5 e 3,5 s): insert de fundo, gancho legível, sem selo.
2. Gancho saindo: dissolveu, rosto de volta.
3. Fronteira entre inserts colados: insert cheio, nunca o rosto entre eles.
4. Troca de legenda: uma por vez, sem empilhar.
5. Transições: uma só, limpa, sem piscar duas vezes e sem quadro preto preso.
6. Letterings: no lugar, sem legenda duplicada.
7. Fim e CTA: botão e logo no rodapé, última palavra sem corte.
8. Cor da pele: razão R/G abaixo de 1,6.
9. Velocidade: a duração medida confere com a esperada para a aceleração do projeto.
10. Insert com captura de tela real: conferir se mostra dado de pessoa (nome, telefone, e-mail, conversa). Se mostrar, troque o arquivo antes de publicar.

Só declare pronto depois de ler os quadros. Nada é entregue sem o ok de quem dirige.
