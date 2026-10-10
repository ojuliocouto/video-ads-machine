# Fase 0: entrada (projeto, roteiro, look, trilha)

Objetivo: o projeto existe, o `roteiro.md` é a fonte da verdade da fala e tudo o que o aluno traz (logo, trilha, inserts) está no lugar. Nada de HeyGen e nada de render aqui.

## Layout do que é do aluno

Tudo fica em `_local/`, que o git ignora. O repo não carrega mídia nem segredo.

```
_local/
  looks.json         looks do HeyGen do aluno (o vam avatar cadastra)
  glossario.json     grafias e equivalências do aluno (marca, produto, nomes)
  marca/logo.png     logo do CTA (PNG com fundo transparente)
  trilhas/           trilhas royalty-free do aluno (o repo não embarca música)
  projetos/<slug>/   um projeto por anúncio
```

## Passo a passo

1. **Nome do projeto.** `<slug>`: minúsculas sem acento, dígitos, `-` e `_`, começando por letra. Exemplo: `tres-horas`.
2. **Criar.** `vam novo <slug> --look <look> --sem-trilha "<motivo>"`. A trilha é um arquivo do aluno em `_local/trilhas/` (`--trilha <nome-do-arquivo>`) ou o motivo escrito de rodar sem trilha. Sem um dos dois o comando recusa. Rodar de novo com o mesmo pedido não muda nada; pedido diferente não toca no projeto (saída 2). O look ainda pode não existir em `looks.json`: o comando só avisa, e o `vam avatar` cadastra (ver `fase1-avatar.md`).
3. **Roteiro.** Uma das três entradas, nesta ordem de preferência:
   - texto colado no chat: grave verbatim com `vam roteiro <slug> --texto "<o texto>"`;
   - arquivo `.md` ou `.txt` do aluno: `vam roteiro <slug> --de roteiro.md`;
   - opcional: Google Doc com comentários, pelo token OAuth do próprio aluno (`GOOGLE_OAUTH_ACCESS_TOKEN` no `.env`). Só neste caso liga o `gate_fidelidade_doc`: comentário com N links são N assets, nunca 1.
4. **Conferir.** `vam roteiro <slug>` sem opção só valida o `roteiro.md` que já está no projeto. Roteiro fora da convenção não é gravado e sai com 1, uma linha por problema (`linha N (campo): motivo`). Trocar um roteiro que já existe pede `--sobrescrever`, e a fala nova vence a aprovação do plano.

## O que a normalização faz e o que nunca faz

Ela mexe em aspas curvas, espaços, quebras de linha e rótulos de chat (`[08/10/2026, 10:32] Ana: `). **Nenhuma palavra da fala muda.** Sem essa passada o rótulo do WhatsApp parece uma direção e o validador reprova.

## Escrever a direção

Cada linha é `[direção] fala`. Quem decide a direção é o roteiro (o aluno ou o `copywriter-video-ads`); aqui você só confere que ela está na convenção. Para o roteiro livre (sem nenhum colchete), o plano propõe as direções na Fase 2 e o aluno aprova.

Pontos que mais reprovam:
- KEY de CTA ausente: o último bloco é sempre `cta`, com `KEY`.
- `LEAD` sem `KEY`.
- Âncora ambígua: `âncora: dia` numa fala em que "dia" aparece duas vezes pede `#2`.
- `hook:` com menos de 3 partes ou fora do primeiro bloco.
- Lista com um item só.

Validar um roteiro sem projeto: `python3 scripts/contratos/validar.py <arquivo.md>`. Convenção completa e seis exemplos em `contratos/roteiro-convencao.md`.

## Inserts

Um insert é um arquivo por chave em `_local/projetos/<slug>/inserts/<chave>.*`, casando com `[insert: <chave>]` do roteiro. Fontes, na ordem: gravação de tela do próprio aluno; um template de interface gerado por `vam insert <slug> <chave> --template whatsapp --dados dados.json` (`vam insert --templates` lista os sete: whatsapp, terminal, kanban, dashboard, agenda, contador, fluxo; `vam insert --exemplo whatsapp` imprime o JSON de partida); geração por IA só como último recurso. Antes de usar uma captura de tela real, confira se ela mostra dado de pessoa (nome, telefone, e-mail, conversa) e troque o arquivo se mostrar.

Logo do CTA: `_local/marca/logo.png`. Confira a imagem: um arquivo com nome de logo pode ser uma ilustração qualquer.

## Glossário

`_local/glossario.json` declara o que o transcritor escreve errado (`termos` com `variantes`) e as diferenças de fala aceitas (`equivalencias`, como "para" e "pra"). É a única troca de palavra que os gates aceitam. Modelo em `contratos/exemplos/glossario.valido.json`.

## Sai desta fase

`projeto.json`, `status.json`, `roteiro.md`, inserts e logo no lugar. Próximo: `vam audio <slug> --bruto voz.m4a` (`fase-audio.md`). Se travar, `vam status <slug>` diz o próximo comando.
