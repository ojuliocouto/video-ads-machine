# Video Ads Machine v2: Aprendizados e Checklist de Auditoria

Motor v2 = HyperFrames (HTML/CSS/GSAP renderizado por Chromium headless), template
`reel-editorial`. Gerador genérico: `_local/gen_ad_v2.py` (lê o roteiro anotado v1
`inputs/adXX_leva.txt` + o mapa de inserts `inputs/adXX_inserts.json` + transcript
Parakeet, e deriva spans, brolls, legendas, letterings, wipes, CTA).

Este arquivo é a **memória viva** do motor: cada regra abaixo nasceu de um defeito real
apontado em produção (uma campanha real, ad2). NÃO regredir nenhuma delas
sem revalidar com auditoria frame a frame.

## Gotchas do HyperFrames 0.7.56 (a raiz de vários bugs)

1. **Clip windowing corta o elemento no fim do `data-duration`.** Segurar opacidade via
   GSAP além do fim do clip NÃO funciona: o elemento some no `data-start+data-duration`
   independentemente do tween. Consequências:
   - o **scrim do broll** tem que ser `gsap.set(opacity:1)` instant-on (cobre o avatar
     100% durante toda a janela); um fade-in transparente vaza o rosto do avatar por
     ~0.2s na entrada do insert. (bug do "rosto entre inserts colados")
   - o **hook** só fica na tela enquanto `data-duration` permitir: pra ficar ~4s, o clip
     do hook precisa de `data-duration >= hook_gone`, não só o tween de opacidade.
2. **Legenda com fade-out que termina DEPOIS do `gEnd` empilha com o próximo grupo.**
   O fade-out do grupo tem que terminar EXATAMENTE em `gEnd` (senão a legenda que sai
   e a que entra ficam sobrepostas horizontalmente por ~2-3 frames).
3. **Lint não pega colisão de layout** (só estrutura). Auditar sempre o MP4 renderizado,
   nunca só o preview nem só o lint.

## Regras de montagem (invioláveis, nasceram de feedback de produção real)

- **Opening em insert, não no avatar.** Se o bloco 0 do roteiro é um insert, o b-roll
  começa em `t=0` (fundo do hook), o avatar só entra no bloco 1. `s2 = 0.0 if i == 0`.
- **Hook cobre o OPENING INSERT inteiro e dissolve no retorno do avatar** (sem invadir o
  rosto). `hook_gone = spans[1][0]+0.1` quando o bloco 0 é insert (senão 3.0), fade de
  0.4s terminando em `hook_gone`, `data-duration = hook_gone+0.1`. Opening longo (ad2,
  4.16s) dá ~4s; opening curto (ad3, 2.88s) dá ~3s. NÃO forçar piso fixo de 4s: forçar
  4s num opening curto joga o hook por cima do avatar. Durante o opening só o hook aparece
  (legenda suprimida até `cap_gate`).
- **Legenda gated:** nenhuma legenda do corpo enquanto o hook está na tela
  (`g["start"] > cap_gate`). Evita dois textos concorrentes no opening.
- **Sem selo / lower-third.** Nada de bolinha do apresentador (removido do template).
- **Scrim instant-on + insert colado por hard-cut.** Zero rosto do avatar entre inserts
  consecutivos (gap <= XFADE_GAP=0.6). Volta pro avatar = fade limpo do broll.
- **Wipes só de ENTRADA** (avatar -> insert), com hold real (fill fecha ~t+0.68, clear
  só em t+0.9). Sem wipe de saída (era o "flash preto" e a "transição dupla").
- **Legenda x lettering: zero sobreposição.** A legenda word-by-word é suprimida dentro
  da janela de cada lettering (o lettering vira o texto principal do trecho).
- **1.15x sem dessincronizar.** Pré-acelerar o avatar.mp4 (`setpts=PTS/1.15` + `atempo=1.15`,
  pitch preservado) ANTES de transcrever; tudo nasce em tempo acelerado. Invalidar cache
  (transcript.json + broll*.mp4) ao re-acelerar. Custo ZERO de HeyGen (só re-timing local).
- **Cauda de áudio nunca cortada.** `total = ceil((dur_real_avatar + 0.20) * 100)/100`.
- **Track band dos brolls = 8+2k / 9+2k** (fica abaixo do #caps=30 e letterings=32/33
  mesmo com 11 inserts). Antes era 10+2k e colidia na track 30.
- **Voz sempre REAL** (nunca TTS). **Zero travessão** em qualquer texto. Acentuação PT-BR.

## Checklist de auditoria pré-entrega (rodar `_local/audit_ad.sh <dir>`)

Ler CADA frame com os próprios olhos (o script extrai; a leitura é obrigatória):

1. **Opening** (t=1.0, 2.5, 3.5): insert de fundo (não avatar), hook legível ~4s, SEM selo.
2. **Hook saindo** (t≈hook_gone): dissolveu; avatar de volta.
3. **Inserts colados** (fronteiras de brolls adjacentes): b-roll fullscreen, NUNCA o rosto
   do avatar entre eles.
4. **Trocas de legenda**: uma legenda por vez, sem empilhar.
5. **Wipes**: transição única e limpa, sem piscar 2x, sem frame preto preso.
6. **Letterings**: ancorados no peito, sem legenda duplicada (check_overlap = 0).
7. **Fim/CTA**: pill + logo no rodapé; cauda do áudio inteira (última palavra sem corte).
8. **Cor da pele**: medir RGB da face vs ad1 aprovado (124,89,91); R/G não pode passar ~1.6.
9. **Velocidade**: ffprobe ~= dur_esperada (1.15x); voz natural sem chipmunk.

Só declarar "pronto" depois de ler os frames e confirmar os 9 itens. Nada é entregue
sem ok explícito do diretor/cliente.

## Histórico de correções (ad2, campanha real)

| # | Defeito reportado | Causa raiz | Fix |
|---|---|---|---|
| 1 | Cortes secos do áudio | de-breath agressivo | higienizar proporcional (v1) |
| 2 | Legenda duplicada (lettering + legenda) | render independente | suprime legenda na janela do lettering |
| 3 | Cor do apresentador vermelha | variância HeyGen / grade | grade quente 50%, calibração vs ad1 |
| 4 | PiP/card sobre avatar | drift de spans não-contíguos (v1) | contiguidade + tpad (v1) |
| 5 | Opening no avatar | clamp `max(s, HOOK_END)` | `s2=0.0` no bloco 0 |
| 6 | Flash preto em "todas essas funções" | wipe de saída (grade preta) | wipes só de entrada |
| 7 | Flash do avatar entre inserts | scrim fade-in transparente + clip windowing | scrim instant-on + hard-cut |
| 8 | Transição piscando 2x (~0:56) | wipe com hold de 0.02s | hold real (clear em t+0.9) |
| 9 | Áudio cortado no fim | total < dur real | tail pad 0.20 + ceil |
| 10 | Selo sobre os inserts | #lt hardcoded em 2.7s | selo removido |
| 11 | Dois textos no opening | filtro de legenda por `end` | gate por `start > cap_gate` |
| 12 | Legendas empilhando na troca | fade-out termina em gEnd+0.10 | fade-out termina em gEnd |
| 13 | Hook passa rápido (~0.7s) | data-duration 2.17 + fade em 1.87 | hook ~4s (data-duration + fade escalados) |
| 14 | Rosto só revela tarde (abertura com 2+ inserts seguidos, ad4) | `hook_gone`/`cap_gate` usavam `spans[1][0]`, só correto quando o bloco 1 já é avatar | referência = primeiro bloco NÃO-insert (`first_avatar_i`), não `spans[1]` |
| 15 | Tela preta ~0.3-0.5s no meio do wipe de entrada de insert (ad07/ad08/ad10, 100% SDR) | HyperFrames usa 2 pipelines de captura: rápido ("beginframe", lê paint records) por padrão, e correto ("layered/screenshot", espera o `<video>` pintar) só quando detecta `hasHdrContent=true`. Em SDR puro cai no modo rápido, que fotografa a área do card antes do `<video>` decodificar o 1º frame do broll pós-seek | forçar cada broll trimado para 10-bit + metadata HDR (`-pix_fmt yuv420p10le -color_primaries bt2020 -color_trc arib-std-b67 -colorspace bt2020nc -profile:v high10`), mesmo vindo de fonte SDR: ativa o modo correto sem alterar as cores na tela |

### Gotcha #15 em detalhe (não repetir a investigação)

**O fix de verdade (10-bit + metadata HDR no broll) FUNCIONA, mas NÃO está mais
aplicado por padrão**: ele força o modo de captura "layered/screenshot", que é
correto porém MUITO mais pesado em CPU/RAM. Numa máquina de produção com pouca RAM
livre (~18GB total, várias outras coisas abertas), esse modo estourou memória e
derrubou o Mac 2x mesmo com `--workers 1` + `--low-memory-mode`. Reaplicar o fix
(ver git log da linha do trim de broll) só numa máquina com bastante RAM livre, ou
via `hyperframes cloudrun` (renderização remota, não configurado ainda).

Testado e DESCARTADO como causa raiz: keyframes esparsos/GOP (falha idêntica com
`-g 1` all-intra e até com o arquivo fonte cru, sem nenhum re-encode), `--workers 1`,
`--experimental-fast-capture=false`, `HF_DE_PARALLEL_ROUTER=false`, flag `--hdr` do
CLI (não força `hasHdrContent`, só afeta profundidade de saída), tamanho/resolução
do arquivo (o ad09 que funcionava tinha um broll HDR *maior e mais pesado* que os
que falhavam).

**Tentativa de contornar no modo leve "beginframe" (preload antecipado do `<video>`)
TAMBÉM FALHOU, não repetir:** estender o `data-start` do `<video>` do broll pra
"decodificar antes" (1.5s, depois 4s de antecedência), com opacity 0 (padrão),
opacity 0.01 (quase invisível, tentando forçar paint sem decodificar visível), e
por fim opacity 1 sempre + um elemento cobridor separado fazendo o fade (garantia
total de que o vídeo estava sendo pintado): todas deram o EXATO MESMO resultado
(tela preta idêntica, mesmos bytes de frame). Conclusão: o modo "beginframe" tem
uma limitação própria com `<video>` nesse cenário de wipe que não é sobre tempo de
decode, é estrutural do próprio pipeline de captura rápido. Só o modo
"layered/screenshot" corrige. Não vale a pena testar mais variações de timing/CSS
no modo leve.

## Pendências / decisões de produção

- **B-rolls com conteúdo sensível.** Se algum insert mostrar dado sensível na tela (texto
  de uma sessão interna, tabela com nomes/telefones, e-mails, qualquer PII), trocar o asset
  antes de publicar. Regra: auditar todo b-roll que seja captura de tela real por PII, e
  substituir por uma versão anonimizada ou por outra tomada.
