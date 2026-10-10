# Fase 3: montagem, auditoria e entrega

## Montar

```
vam montar <slug>              o build com os gates na ordem; prévia e laudo em entrega/
vam montar <slug> --paralelo 2 gates de saída ao mesmo tempo (1 a 4; padrão 4)
```

Entra: tudo das fases anteriores e um ok de plano vigente. Sai: `entrega/final_9x16.mp4`, `entrega/final_whatsapp.mp4` (prévia leve) e `entrega/laudo.json`. Saídas: 0 laudo PASS, 1 algum gate reprovou, 2 insumo inválido ou ferramenta que morreu.

Ordem dos gates (tabela em `gates.md`):

1. **Antes (sem render):** aprovação, fidelidade ao roteiro (e ao Doc, se houver), fala x roteiro, entrada (voz e avatar), look; depois de montar a `timeline.json`: geometria, zona segura, lettering e congelamento sobre o plano. O primeiro que reprova interrompe, com o motivo no `status.json`.
2. **Durante:** tela vazia, congelamento real, relógio, template.
3. **A prévia de WhatsApp sai assim que o render termina**, antes dos gates de saída. Mostre-a ao aluno cedo: ele vê o anúncio enquanto os 16 gates de saída rodam.
4. **Depois, em paralelo (até 4):** os 16 gates sobre o arquivo final. O laudo amarra tudo ao sha256 do final.

## Quando um gate reprova

1. Leia o motivo: `vam status <slug>` e `entrega/laudo.json` (cada gate traz `medido` e `limiar`).
2. Conserte na **origem** (roteiro, projeto, insert, áudio), nunca no arquivo final. Mudou o roteiro, a aprovação vence e o plano se mede de novo.
3. Rode `vam montar` de novo. Os caches de segmento e de overlay aceleram o que não mudou.
4. Exceção a uma regra medida: só em `projeto.json`, `excecoes`, com motivo escrito, e só nas regras que o gate aceita (ver `gates.md`).

Um build de cada vez. No máximo 2 renders pesados na máquina. Não edite o template durante o build (`gate_template` reprova).

## Ler antes de auditar

`entrega/folhas/*.png` são as folhas de contato: leia todas. Confira, com os próprios olhos, o gancho, a fronteira entre inserts, a troca de legenda, os letterings, o CTA e a cauda. Gate mede o que dá para medir; se a imagem combina com a fala é olho.

## Auditar (a segunda cerimônia)

```
vam auditar <slug>                                     o pacote: o que o auditor lê e o sha256 que ele audita
vam auditar <slug> --nota 8.5 --achados achados.json   o auditor registra a nota (entrega/nota.json)
```

Quem monta não assina a nota. O auditor é um subagente com contexto limpo, seguindo `auditoria.md`. Nota 8 ou mais; abaixo disso corrija os achados e rode a rodada 2 (`--rodada 2 --reconfere A1 A3`), que reconfere os mesmos pontos. Montar de novo muda o sha256 e vence a nota.

## Entregar

```
vam entregar <slug> --abrir
```

Libera só quando o laudo é PASS, a aprovação do plano continua vigente e a nota é 8 ou mais, os três amarrados ao mesmo sha256. Bloqueado, nada é montado e a saída é 1. Liberado, `entrega/entrega.json` guarda o sha256 do final, da prévia, do laudo, da nota e das folhas. A entrega do produto é a pasta `entrega/`: Drive e WhatsApp são decisão do aluno.

## Depois de entregar

Apague o que ocupa disco e já está seguro (avatar bruto, renders intermediários) só depois de conferir que o `final_9x16.mp4` foi para onde o aluno o quer. O que o aluno aprovou não se perde em limpeza.
