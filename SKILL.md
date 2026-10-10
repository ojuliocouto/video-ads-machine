---
name: video-ads-machine
description: Produz anúncio em vídeo vertical 9:16 a partir de um roteiro e da voz real de quem fala, com avatar de IA, take gravado ou take único de câmera. Use em pedido de anúncio ou criativo em vídeo, reel, avatar HeyGen, lipsync, legenda, lettering ou corte de ar morto de take. VSL, motion e imagem estática ficam em outras skills.
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# Video Ads Machine

Do roteiro ao anúncio 9:16, com gates medidos e duas aprovações humanas. Tudo roda na máquina de quem usa, pela CLI única `vam`. **Toda vez que esta skill diz `vam <comando>`, rode `python3 scripts/vam.py <comando>` na raiz do repo.** Cada comando termina com 0 (fez), 1 (defeito medido) ou 2 (pedido ou insumo inválido) e imprime o próximo passo.

## 1. Quando usar e quando NÃO usar

Use quando o pedido é um anúncio ou criativo em vídeo curto, vertical, com a voz de uma pessoa real: com avatar, com take gravado de evento ou com um take único de câmera.

| Pedido | Vai para | Por quê |
|---|---|---|
| VSL ou peça longa de vendas | `video-vsl-machine` | outra estrutura, outra duração |
| Roteiro ainda não existe | `copywriter-video-ads` antes, depois volta aqui | esta skill não escreve a copy |
| Direção de arte avulsa, ou revisar um anúncio sem insert nem gancho | `diretor-arte-video-ads` | aqui ela entra como subagente da Fase 2.5 |
| Motion, animação, explainer, título animado | `hyperframes` | composição em HTML, sem voz real |
| Gerar imagem, vídeo, 3D ou áudio por IA | `higgsfield-generate` | geração, não montagem |
| Anúncio estático (imagem) | `criativo-imagem-ia` | não há vídeo |
| Vídeo longo (entrevista, podcast) com gráficos por cima, o vídeo intacto | `talking-head-recut` | pacote de gráficos, não anúncio |
| Só legendar um vídeo que não se edita | `embedded-captions` | sem corte, sem plano, sem gates |

Se a skill vizinha não estiver instalada, diga isso ao usuário em vez de improvisar o pedido aqui.

## 2. Passo 0: `vam doctor` barra

Antes de qualquer render ou crédito, rode `vam doctor`. Ele confere ffmpeg com libass, Node e o HyperFrames do repo, as dependências Python, o transcritor (parakeet, faster-whisper ou Groq), as fontes e a chave do HeyGen com o saldo. Cada item sai OK, WARN ou FAIL com uma linha de conserto. **Qualquer FAIL para tudo**: rode o conserto impresso (quase sempre `bash scripts/setup.sh`) e o doctor de novo. WARN passa. Sem chave do HeyGen o modo avatar fica desligado, e o gravado e o one-shot seguem. Contas, chaves e custo em `references/onboarding.md`.

## 3. Escolha o caminho

| Situação | Caminho | Referência |
|---|---|---|
| Rosto gerado por IA falando a voz do usuário | **avatar** | `references/fase0-entrada.md` em diante |
| Vários takes gravados de câmera (evento, lapela, retomada) | **gravado** | `references/gravado.md` |
| Um take só, a pessoa falando direto para a câmera | **one-shot** | `references/oneshot.md` |

A ordem das fases é fixa. Nunca gere avatar antes de o áudio passar.

## 4. Caminho avatar (checklist copiável)

`<slug>` é o nome do projeto (minúsculas, dígitos, `-` e `_`). Estado em `_local/projetos/<slug>/`.

| Fase | Comando | Entra | Sai | Gate que barra |
|---|---|---|---|---|
| 0 Entrada | `vam novo <slug> --look <look> --sem-trilha "<motivo>"` (ou `--trilha <arquivo>`) | nome, look, trilha | `projeto.json`, `status.json` | contrato do projeto |
| 0 Entrada | `vam roteiro <slug> --texto "<roteiro colado>"` (ou `--de roteiro.md`; ou `--de-audio voz.m4a`, que transcreve a gravação em um rascunho para revisar) | roteiro | `roteiro.md` | convenção `contratos/roteiro-convencao.md` |
| 0.5 Áudio | `vam audio <slug> --bruto voz.m4a` | voz bruta | `voz/limpo.mp3`, `voz/auditoria.json` | respiro, ritmo, fala preservada, fala x roteiro |
| 1 Avatar | `vam avatar <slug> --avatar-id <id> --plano medio` (1ª vez), depois `vam avatar <slug> --aprovar-look` | voz limpa, look | `avatar/avatar.mp4`, `boca.png`, `custo.json` | conferência: 1080x1920, fração útil 0,93 ou mais, duração da voz mais ou menos 1,0 s |
| 2 Plano | `vam plano <slug>` | roteiro, voz, inserts | `plano/plano.json`, `plano_edicao.md` | 6 seções e checklist |
| 2.5 Prancha | `vam plano <slug> --prancha`, subagente `diretor-arte-video-ads`, `vam plano <slug> --sugestoes direcao.json` | plano | `plano/prancha/*.png`, `direcao.json` | prancha lida pelo diretor |
| 2 Aprovação | `vam aprovar <slug> --ok "<ok do aluno>"` | ok no chat | `plano/aprovacao.json` | sha256 dos 4 arquivos |
| 3 Montagem | `vam montar <slug>` | tudo acima | `entrega/final_9x16.mp4`, `final_whatsapp.mp4`, `laudo.json` | 29 gates na ordem (`references/gates.md`) |
| 3 Auditoria | `vam auditar <slug>`, depois `vam auditar <slug> --nota N --achados achados.json` (só o auditor) | arquivo final | `entrega/nota.json` | nota 8 ou mais |
| 3 Entrega | `vam entregar <slug> --abrir` | laudo, aprovação, nota | `entrega/entrega.json` | `gate_entrega` |

Onde parou: `vam status <slug>` diz a etapa e o próximo comando. Pronto é o que o `status.json` diz, nunca memória.

## 5. Caminhos gravado e one-shot

| Caminho | Comando | Gate que barra |
|---|---|---|
| gravado | `vam gravado <slug> criar --brutos <pasta> --sem-trilha "<motivo>"`, `extrair`, `isolar` (ou `limpo --de <pasta>`), `plano`, `montar <AD>`, `caixinha`, `legendar`, `aprovar-legenda`, `queimar`, `gates`, `entregar` | 11 gates mais `legenda_aprovada` |
| one-shot | `vam novo <slug> --modo oneshot`, depois `vam oneshot <slug> --bruto take.mov --so-plano`, depois sem `--so-plano` | fala inteira, maior pausa, técnico |
| inserts de interface | `vam insert <slug> <chave> --template whatsapp --dados dados.json` | `gate_fidelidade_roteiro` confere que o arquivo existe |

Detalhe de cada etapa em `references/gravado.md` e `references/oneshot.md`.

## 6. As duas cerimônias humanas

1. **Aprovar o plano.** Mostre `plano/plano_edicao.md` ao aluno. Só com o ok dele escrito no chat rode `vam aprovar`, com o texto que ele escreveu. Mudou 1 byte do roteiro, do projeto, do plano ou dos inserts depois do ok, o `vam montar` recusa e o ok se refaz.
2. **Nota 8 do auditor.** Uma rodada, feita por um subagente com contexto limpo seguindo `references/auditoria.md`. Quem monta não dá nota. Abaixo de 8: corrija os achados e reconfira os mesmos pontos (rodada 2, teto de 2); varredura nova, nunca.

No caminho gravado a segunda cerimônia é o ok do diretor à legenda (`vam gravado <slug> aprovar-legenda`).

## 7. Números vigentes (a constante no código vale mais que este texto)

| Número | Valor | Constante |
|---|---|---|
| Aceleração | 1,35 com avatar; 1,2 com take real | `PADRAO_ACELERACAO` em `scripts/projeto/modelo.py` |
| Loudness e true peak | -14 LUFS, true peak até -1,5 dBTP | `LUFS_ALVO`, `TP_ALVO` em `scripts/audio/loudness.py` |
| Contraste do texto | 4,5:1 contra o fundo local | `PISO` em `scripts/gates/contraste_texto.py` |
| Densidade de insert | 45 a 55% (piso 40, teto 65) | `ALVO_MIN`, `ALVO_MAX`, `PISO`, `TETO` em `scripts/plano/medir.py` |
| Zona segura (9:16) | nada abaixo de y 1690 nem à direita de x 940 | `LIMITE_Y`, `LIMITE_X` em `scripts/gates/gate_safezone.py` |
| Ritmo de corte | 16 a 32 cortes por minuto | `MIN_CORTES_MIN`, `MAX_CORTES_MIN` em `scripts/medir_ritmo.py` |
| Pausa máxima na tela | 0,60 s | `PAUSA_MAX_TELA` em `scripts/higienizar_audio.py` |
| Nota mínima da auditoria | 8 | `NOTA_MINIMA` em `scripts/fase_gate.py` |
| Teto de gasto do avatar | US$ 5,00 por job | `TETO_USD` em `scripts/cli/avatar.py` |
| Engine do avatar | `avatar_v`, travado | `MANDATORY_ENGINE` em `scripts/avatar/heygen_cliente.py` |

As 14 capacidades cinematográficas, com gate e limiar, estão em `references/cinematografico.md`.

## 8. Nunca

- Nunca use voz sintética (TTS): a voz é sempre a real. Mudou o áudio, regere o avatar.
- Nunca gere o avatar antes de `vam audio` passar: o áudio fica gravado dentro dele.
- Nunca rode `vam aprovar` sem o ok escrito do aluno, nem escreva a nota de um anúncio que você mesmo montou.
- Nunca chame o renderizador nem o `build_composite.py` direto: o build é `vam montar`.
- Nunca declare pronto sem ler `vam status` e os quadros da folha de contato.
- Nunca chute um número do material (enquadramento, recorte, velocidade, ocorrência de palavra): meça.
- Nunca troque palavra da fala: a legenda vem do `roteiro.md`, não da transcrição crua.
- Nunca desligue um gate por variável de ambiente: exceção mora em `projeto.json`, com motivo escrito.
- Nunca suba chave, voz, avatar ou nome de cliente para um repositório. Segredo vive em `.env`, fora do git.
- Nunca use travessão em texto de tela, e nunca deixe de acentuar o português.
- Nunca rode mais de 1 build ao mesmo tempo, nem mais de 2 renders pesados na máquina.

## 9. Roteiro sem planilha

Nenhum caminho lê planilha. O roteiro entra por, em ordem: (1) texto colado no chat, gravado verbatim por `vam roteiro <slug> --texto "..."`; (2) arquivo `.md` ou `.txt` (`--de`); a voz gravada antes do texto entra por `--de-audio voz.m4a` (transcrição verbatim com o glossário do aluno, em parágrafos nas pausas, como RASCUNHO que o aluno revisa); (3) opcional, Google Doc com comentários pelo token OAuth do próprio aluno (`GOOGLE_OAUTH_ACCESS_TOKEN`), e só então liga o `gate_fidelidade_doc`.

Uma linha por bloco, direção entre colchetes e a fala depois: `[insert: painel | hook: VOCÊ PERDE | 3 horas por dia | NISSO AQUI] Você perde...`. Tipos: `apresentador`, `insert: <chave>`, `lista`, `cta` (sempre o último). Sem nenhum colchete é roteiro livre: o plano propõe as direções e o aluno aprova. Convenção completa, âncora e exemplos em `contratos/roteiro-convencao.md`.

## 10. Mapa das referências

Leia só a da fase em que você está.

| Arquivo | Quando |
|---|---|
| `references/onboarding.md` | primeiro uso: contas, chaves, `.env`, custo |
| `references/fase0-entrada.md`, `fase-audio.md` | entrada e voz |
| `references/fase1-avatar.md` | look e avatar |
| `references/fase2-plano.md`, `fase25-prancha.md` | plano, prancha, aprovação |
| `references/fase3-montagem-entrega.md` | montar, auditar, entregar |
| `references/gravado.md`, `oneshot.md` | os outros dois caminhos |
| `references/cinematografico.md`, `gates.md` | capacidades e limiares |
| `references/auditoria.md` | o prompt do auditor |
| `references/licoes.md` | por que cada regra existe |

Modelo: use o modelo mais capaz que você tiver para a direção da Fase 2.5 e para a auditoria; extração, conversão e render de variação já especificada não precisam dele.
