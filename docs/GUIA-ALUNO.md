# Guia do aluno: do zero ao primeiro anúncio

Este guia leva você da instalação ao primeiro anúncio vertical (9:16) entregue, comando por comando, no caminho do avatar. No fim há as variações para take gravado e para take único. Você conversa com o Claude Code; ele roda os comandos e lê as respostas. Os comandos estão aqui para você entender e conferir o que ele faz.

Todo comando abaixo é rodado na raiz da pasta do repo. `python3 scripts/vam.py` é a CLI única; todo comando termina com um destes códigos: **0** fez, **1** defeito medido no seu material, **2** pedido ou insumo inválido. Quando algo trava, rode `python3 scripts/vam.py status <nome-do-projeto>`: ele diz a etapa e o próximo comando.

## Sumário

1. O que você precisa antes de começar
2. Instalar e conferir a máquina
3. Preparar o que é seu
4. O projeto e o roteiro
5. A voz
6. O avatar
7. O plano e a sua aprovação
8. Montar
9. Auditar e entregar
10. Take gravado e take único
11. Quando algo dá errado

## 1. O que você precisa antes de começar

- Mac (Apple Silicon) ou Linux, com Python 3.9 ou mais novo, Node 22 ou mais novo e ffmpeg com libass (`brew install ffmpeg` no Mac).
- Claude Code instalado.
- Uma conta na HeyGen com a chave de API (só para o avatar). É paga por uso, em dólar: um anúncio de cerca de 1 minuto custa de US$ 3,20 a US$ 4,40 de avatar, e o sistema para sozinho se um job passar de US$ 5,00.
- Um roteiro curto (de 30 a 60 segundos de fala).
- Um gravador de voz (o celular serve), em lugar silencioso, com a sua voz de verdade. Não existe voz sintética aqui.
- O `avatar_id` de um look vertical da HeyGen.

## 2. Instalar e conferir a máquina

```
git clone <url-do-repo> video-ads-machine
cd video-ads-machine
bash scripts/setup.sh
python3 scripts/vam.py doctor
```

O `setup.sh` cria o `.venv`, instala o HyperFrames (que renderiza o texto na tela), guarda uma cópia do GSAP e cria o arquivo `.env`. Abra o `.env` e coloque a chave: `HEYGEN_API_KEY=...`. O arquivo fica fora do git e nunca vai para lugar nenhum.

O `doctor` mostra `OK`, `WARN` ou `FAIL` por item, com a linha do conserto. **`FAIL` para tudo.** Aplique o conserto e rode o doctor de novo até não sobrar nenhum `FAIL`. `WARN` pode ficar.

## 3. Preparar o que é seu

Tudo o que é seu vive em `_local/` (o git ignora):

- `_local/marca/logo.png`: o seu logo, PNG com fundo transparente. Abra a imagem e confira que é um logo mesmo.
- `_local/trilhas/`: uma música royalty-free sua. O repo não traz música. Se não quiser trilha, você escreve o motivo no próximo passo.
- Inserts (as telas que provam o que você fala): gravações de tela suas, ou telas de interface geradas por `python3 scripts/vam.py insert --templates` (WhatsApp, terminal, kanban, dashboard, agenda, contador, fluxo). Antes de usar uma captura de tela real, confira se ela mostra nome, telefone, e-mail ou conversa de outra pessoa. Se mostrar, troque.

## 4. O projeto e o roteiro

1. Escolha um nome curto, em minúsculas, sem acento: `tres-horas`.
2. Crie o projeto (sem trilha, com o motivo escrito, neste exemplo):

```
python3 scripts/vam.py novo tres-horas --look meu-look --sem-trilha "primeiro teste sem música"
```

3. Cole o roteiro no chat e peça ao Claude para gravá-lo. Por trás: `python3 scripts/vam.py roteiro tres-horas --texto "..."` (ou `--de roteiro.md`). Ele grava a fala exatamente como você escreveu.

O roteiro tem uma linha por bloco, com a direção entre colchetes e a fala depois:

```
[insert: painel | hook: VOCÊ PERDE | 3 horas por dia | NISSO AQUI] Você perde três horas por dia nisso aqui.
[apresentador] E eu sei porque eu fazia igual, todo santo dia.
[apresentador | LEAD: o problema não é | KEY: FALTA DE TEMPO] O problema não é falta de *tempo*.
[insert: planilha | split] É que cada tarefa repetida come um pedaço da sua agenda.
[cta | LEAD: toque em | KEY: SAIBA MAIS | logo] Toque em saiba mais e veja como montar a sua.
```

O último bloco é sempre `cta`. Sem nenhum colchete, é roteiro livre: o plano propõe as direções e você aprova. Se o roteiro estiver fora da convenção, o comando sai com 1 e diz a linha e o motivo. A convenção inteira, com exemplos, está em `contratos/roteiro-convencao.md`.

## 5. A voz

Grave a fala do roteiro, na sua voz, e peça ao Claude:

```
python3 scripts/vam.py audio tres-horas --bruto minha-voz.m4a
```

Ele higieniza (encurta só as pausas grandes) e confere quatro coisas: respiração audível dentro de pausa, ritmo achatado, fala comida pelo corte e se a sua fala cobre o roteiro. Se reprovar, ele diz o que e você regrava ou ajusta **antes** do avatar. Esta ordem é fixa porque o áudio fica gravado dentro do avatar: um defeito descoberto depois custa um avatar novo.

## 6. O avatar

Na primeira vez com o look, informe o `avatar_id` e o enquadramento (`fechado`, `medio` ou `aberto`); o comando cadastra, gera e confere:

```
python3 scripts/vam.py avatar tres-horas --avatar-id <id-do-look> --plano medio
```

Ele lê o saldo da HeyGen antes e depois e grava o custo real em `_local/projetos/tres-horas/avatar/custo.json`. Depois **abra `avatar/boca.png`** e olhe a boca do avatar. Se estiver boa:

```
python3 scripts/vam.py avatar tres-horas --aprovar-look
```

Se já tem um avatar gerado dessa mesma voz limpa, use `--existente avatar.mp4`: custo zero.

## 7. O plano e a sua aprovação

```
python3 scripts/vam.py plano tres-horas --prancha
```

O comando mede o plano (blocos, inserts, hook, letterings, densidade, ritmo) e monta uma **prancha**: o anúncio em quadros parados, sem renderizar. O Claude chama um diretor de arte (um subagente com contexto limpo) para ler a prancha e sugerir referências e inserts onde a fala ficou só no rosto; ele grava isso em `direcao.json`, e o Claude roda `python3 scripts/vam.py plano tres-horas --sugestoes direcao.json`.

Depois o Claude mostra o `plano/plano_edicao.md`. **Leia.** Ele tem as seis seções (mapa de inserts, hook, lettering, densidade, referências, efeitos) e uma checklist com o que está atendido e o que está pendente, com o motivo. Se está bom, escreva o ok no chat. Só então o Claude roda:

```
python3 scripts/vam.py aprovar tres-horas --ok "<o texto do seu ok>"
```

A aprovação fica amarrada ao conteúdo exato do roteiro, do projeto, do plano e dos inserts. Se qualquer um mudar depois, o ok vence e a montagem recusa: é para você nunca receber um anúncio de um plano que não aprovou.

## 8. Montar

```
python3 scripts/vam.py montar tres-horas
```

Roda o build com os 29 gates na ordem: primeiro os baratos, sem render (aprovação, fidelidade ao roteiro, fala, voz e avatar, geometria, zona segura), depois o render, a prévia de WhatsApp e os gates sobre o arquivo final. A prévia (`entrega/final_whatsapp.mp4`) sai assim que o render termina: assista cedo. Se um gate reprovar, o comando sai com 1, o motivo está em `vam status tres-horas` e no `entrega/laudo.json`. Conserte na origem (roteiro, áudio, insert), não no arquivo final.

Rode um build de cada vez. Em máquina fraca, `--paralelo 2`.

## 9. Auditar e entregar

Quem montou o anúncio não dá a nota dele. O Claude chama um auditor independente (subagente com contexto limpo, seguindo `references/auditoria.md`), que lê as folhas de contato, assiste ao arquivo inteiro e tenta refutar o anúncio, olhando só o que se vê e ouve no celular. Ele registra a nota com `python3 scripts/vam.py auditar tres-horas --nota N --achados achados.json`. Abaixo de 8, o Claude corrige os achados e o auditor reconfere os mesmos pontos (uma segunda rodada, nunca varredura nova). Com 8 ou mais:

```
python3 scripts/vam.py entregar tres-horas --abrir
```

Ele só libera se o laudo é PASS, o seu ok do plano continua vigente e a nota é de 8 ou mais, os três amarrados ao mesmo arquivo. A pasta `_local/projetos/tres-horas/entrega/` abre com:

- `final_9x16.mp4`: o anúncio;
- `final_whatsapp.mp4`: a versão leve para aprovação no celular;
- `laudo.json`, `nota.json`, `entrega.json` e `folhas/`: a prova.

## 10. Take gravado e take único

**Vários takes gravados (evento, lapela, retomada).** O Claude cria o projeto com `python3 scripts/vam.py gravado <nome> criar --brutos <pasta-dos-takes> --sem-trilha "<motivo>"` e segue na ordem: `extrair`, `isolar` (precisa da chave da ElevenLabs) ou `limpo --de <pasta>`, `plano --md`, `montar <anúncio>`, `caixinha`, `legendar`, `aprovar-legenda` (o seu ok à legenda), `queimar`, `gates` e `entregar`. A aceleração padrão é 1,2. Detalhe em `references/gravado.md`.

**Um take só, direto para a câmera.** `python3 scripts/vam.py oneshot <nome> --bruto take.mov --so-plano` mostra o plano medido (corte do ar morto, enquadre no rosto, luz) sem renderizar; sem `--so-plano` ele renderiza numa passada só e confere se a fala ficou inteira. Detalhe em `references/oneshot.md`.

Nenhum dos dois gasta HeyGen.

## 11. Quando algo dá errado

| Sintoma | O que fazer |
|---|---|
| `doctor` com `FAIL` | rode o conserto impresso na linha (quase sempre `bash scripts/setup.sh`) |
| `vam audio` reprovou | regrave ou ajuste a pausa; nunca gere o avatar com áudio reprovado |
| `vam avatar` reprovou | leia o motivo (tamanho, duração, fração útil); regere a partir da voz limpa atual |
| `vam aprovar` recusou | falta seção, tem pendência sem motivo, ou o plano foi medido de outra versão do roteiro: rode `vam plano` de novo |
| `vam montar` recusou "aprovação vencida" | algo mudou depois do ok: rode `vam plano`, leia o plano e aprove de novo |
| um gate reprovou | `vam status <nome>` e `entrega/laudo.json` trazem o que foi medido e o limiar |
| `vam entregar` bloqueou | falta o laudo PASS, o ok do plano ou a nota 8: o motivo diz qual |

Regra de ouro: **pronto é o que o `status.json` diz**, não o que parece. Se o Claude disser "está pronto", peça `vam status <nome>`.
