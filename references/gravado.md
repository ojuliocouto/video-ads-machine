# Caminho gravado: vários takes de câmera, escolher frase a frase

Use quando a pessoa foi gravada em evento ou com lapela, errou e retomou, e há gente falando fora de quadro. Aqui o trabalho não é tirar ar morto de uma tomada boa (isso é o one-shot): é **escolher, frase a frase, entre duas ou três tentativas de cada uma**, e ainda separar a voz de quem fala da de quem dirige.

## Sumário

1. Ordem das etapas
2. O plano (`plano_gravado.json`)
3. Etapa por etapa
4. Os gates e como ler uma reprovação
5. Aceleração, cor e caixa
6. A cerimônia: aprovar a legenda

## 1. Ordem das etapas

`vam gravado <slug> <ação> [alvos...] [opções]`. Os alvos (peças, takes) vêm logo depois da ação e as opções por último.

| # | Comando | Entra | Sai | Barra |
|---|---|---|---|---|
| 1 | `vam gravado <slug> criar --brutos <pasta> --sem-trilha "<motivo>"` | pasta com os takes (.MOV) | projeto e `plano_gravado.json` de partida | plano quebrado (saída 2) |
| 2 | `vam gravado <slug> extrair` | brutos | `wav/` (48 kHz) e mp3 leve por take | |
| 3 | `vam gravado <slug> isolar` ou `vam gravado <slug> limpo --de <pasta>` | wav | `limpo/<take>.mp3` | `gate_envelope`, `gate_fala` |
| 4 | `vam gravado <slug> plano --md` | plano preenchido | `PLANO-CORTES.md` | conferência do plano |
| 5 | `vam gravado <slug> montar <AD>` | plano, limpo | `montados/<AD>_normal.mp4` (e `_desconto`) | |
| 6 | `vam gravado <slug> caixinha <PECA> --texto "..."` | peça montada | peça com caixa de lettering | |
| 7 | `vam gravado <slug> legendar` | peça | `legendas/<peça>.ass` e relatório fala x roteiro | `gate_legenda` (depois) |
| 8 | `vam gravado <slug> aprovar-legenda <PECA> --ok "<ok do diretor>"` | ok no chat | `legendas/<peça>.aprovacao.json` | sha256 do `.ass` |
| 9 | `vam gravado <slug> queimar` | `.ass` aprovado | `legendado/` | sem aprovação vigente, nenhum ffmpeg roda |
| 10 | `vam gravado <slug> gates` | tudo | veredito por gate | os 11 gates mais a legenda aprovada |
| 11 | `vam gravado <slug> entregar --abrir` | gates verdes | `entrega/` com sha256 por peça | copia só se TODOS passam |

## 2. O plano

O plano é dado, nunca código: `plano_gravado.json` (versão 1) com `brutos`, `ignorar` e, por anúncio, `corpo`, `cta_normal`, `cta_desconto` (e `corpo_desconto` se o corpo precisar parar antes). Cada trecho é `[take, início, fim]` em segundos, **medidos no áudio higienizado**, **uma frase por trecho**. O CTA é lista separada: trocar a cauda inteira apagaria o argumento.

Antes de preencher o plano, leia o take **inteiro** (`vam gravado <slug> extrair` e a transcrição). Escolher frase sem ouvir o take todo é a causa das reprovações em série.

## 3. Etapa por etapa

- **Isolar (Voice Isolator da ElevenLabs).** Sem a voz isolada nenhuma pausa vira silêncio num evento lotado (piso de ruído medido em -32,7 dB, que vai a -90,3 dB depois). Exige `ELEVENLABS_API_KEY` no `.env`; conta paga por uso. Preserva todas as vozes, inclusive a de quem dirige: o `gate_voz_distante` as separa por nível. Se já houver áudio higienizado, `limpo --de <pasta>` copia e confere o sha256 sem tocar na origem. Sem chave e sem áudio limpo o passo é pulado com aviso, e os gates de envelope ficam sem insumo.
- **Montar.** Seleciona os trechos, tira o ar morto dentro deles (cortador por energia), costura o vídeo com o áudio higienizado, acelera pelo `projeto.json`, passa a grade de cor e normaliza loudness (-14 LUFS, true peak -1,5 dBTP). `--so-plano` lista o que entra sem renderizar. `--desconto` troca a cauda pelo CTA com desconto. Vídeo de celular em pé chega guardado deitado; a rotação é aplicada na entrada do grafo.
- **Caixinha.** Caixa de lettering nativa (canto reto, PT Serif do repo) no topo, abaixo da interface do Reels (padrão `--topo 210`). O texto é exatamente o que o apresentador lê. Três colorways (`ambar`, `branco`, `preto`), nunca um quarto. Teto medido na peça (`--teto-y`) para a caixa não descer sobre a cabeça.
- **Legendar.** O texto vem da transcrição corrigida pelo glossário do aluno; só se quebra em linhas, nunca se reescreve (um ASR chegou a inserir um "não" que invertia o sentido). Destaque de cor em números, preços e termos de marca e produto do glossário; nome de pessoa não ganha cor. `--omitir PALAVRA` tira só da legenda.

## 4. Os gates e como ler uma reprovação

Tabela completa em `gates.md`. Saída 0 passou, 1 defeito medido, 2 não deu para medir. Um gate que sai com 2 não aprova nem reprova: conserte o insumo.

| Reprovou | Leitura | Conserto |
|---|---|---|
| `gate_retomada` | frase repetida entre sub-blocos vizinhos, ou fragmento curto na borda | trocar o trecho; fragmento que o diretor quer vira um item de `fragmentos_aceitos` no plano, no formato `[take, instante, motivo]` |
| `gate_redundancia` | dois trechos limpos que dizem a mesma ideia colados | outro ponto de entrada do CTA |
| `gate_emendas` | palavra cortada ao meio na costura | mover a borda para a pausa |
| `gate_ar_morto` | pausa acima do teto | dividir o trecho na pausa (uma frase por trecho) |
| `gate_voz_distante` | outra voz dentro de um trecho | começar o trecho depois |
| `gate_fala`, `gate_envelope` | o isolador comeu fala | outro take ou áudio limpo diferente |
| `gate_offscript`, `gate_repeticao` | pergunta a quem dirige, hesitação, n-grama repetido | cortar o trecho |
| `gate_sincronia` | legendada que não veio do corte atual | `legendar` e `queimar` de novo |

Os gates `fala` e `redundancia` leem só os trechos usados, não o take inteiro; `retomada` aceita fragmento curto declarado.

## 5. Aceleração, cor e caixa

- **Aceleração 1,2** (`PADRAO_ACELERACAO["gravado"]` em `scripts/projeto/modelo.py`). O 1,35 do avatar foi reprovado de ouvido em take real: a fala gerada aguenta mais que a respiração de uma pessoa.
- **Cor.** A grade é o preset `estilo.grade` do `projeto.json` (padrão `quente-suave`) e fecha com tags bt709. Se o take é HDR (iPhone grava em HLG), a conversão para SDR vem antes da grade, por segmento, com uma LUT: reetiquetar HLG como bt709 mantém o pixel e erra a matriz.
- **Caixa** só para título e lettering, nunca para legenda.

## 6. A cerimônia

A legenda só vira filme depois que o diretor a aprova: `vam gravado <slug> aprovar-legenda <PECA> --ok "<o que ele escreveu>"` grava o ok com o sha256 do `.ass` e do relatório. Mexer 1 byte no `.ass` depois do ok, ou gerar a legenda de novo, vence a aprovação. `--divergencia-aceita` só com a divergência fala x roteiro explicada ao diretor. Quem monta não assina.

## Por que existe

Uma leva de anúncios de evento foi reprovada oito vezes: retomada, meia palavra na emenda, outra voz abrindo o anúncio, legenda velha com cara de nova. Cada gate nasceu de um desses defeitos (`licoes.md`, seção 6).
