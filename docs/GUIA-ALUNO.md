# Guia do Aluno: do zero ao seu primeiro anúncio em vídeo

Este guia é um passo a passo completo, pensado pra quem nunca mexeu com terminal.
Siga na ordem. Cada etapa depende da anterior.

---

## 1. O que você vai construir

Um anúncio em vídeo com o **SEU avatar de IA** falando com a **SUA voz de verdade**.

O fluxo é simples:

1. Você escreve um roteiro anotado (texto com instruções visuais entre colchetes).
2. Você grava a própria voz lendo esse roteiro.
3. O sistema gera o avatar sincronizado com a sua voz (lip-sync via HeyGen), monta as cenas, queima a legenda palavra por palavra, aplica os letterings (textos grandes na tela), acelera levemente o vídeo e entrega dois arquivos finais:
   - **9:16** (1080x1920): pra Reels e Stories
   - **1:1** (1080x1080): pra feed

Ponto inegociável do sistema: **a voz é sempre uma gravação real da sua voz**. Nunca voz sintética (TTS). Voz de robô é o maior "entregador" de conteúdo feito por IA, e o pipeline foi desenhado justamente pra fugir disso.

---

## 2. O que você precisa ANTES de começar

### 2.1 Conta HeyGen com crédito de API

O HeyGen é o serviço que transforma sua voz gravada em vídeo do avatar. A boa notícia: o caminho mínimo é mais barato do que parece.

1. **Crie a conta** em [app.heygen.com](https://app.heygen.com). A conta **gratuita já permite criar 1 avatar próprio** (Digital Twin). Você só precisa de plano pago (Creator, a partir de US$ 29/mês) se quiser também usar o editor do site ou processamento prioritário; pro nosso pipeline, não é obrigatório.
2. **Compre crédito de API**, que é uma coisa SEPARADA e avulsa (pay-as-you-go): você escolhe um valor em dólar e pronto, sem assinatura. Como referência de julho/2026: US$ 1 rende cerca de 1 minuto de vídeo de avatar em 1080p (motores mais novos, como o Avatar IV, custam mais por minuto). Pra começar, US$ 10 a 20 dão bastante margem de testes. Confira os valores atuais na página de preços da API do HeyGen antes de comprar.

**Atenção, isso confunde todo mundo:** o crédito que vem num plano pago (o que você usa dentro do site) **não serve** pra gerar vídeo por API. O crédito de API é comprado à parte, no painel do HeyGen, em **Space Settings > API**. Se o crédito de API estiver zerado, toda geração falha, mesmo com o plano cheio de créditos. O comando `vam doctor` (etapa 4) mostra quanto crédito de API você ainda tem.

### 2.2 Ter um avatar: criar o seu OU usar um pronto

Você tem dois caminhos, e os dois funcionam com o pipeline.

**Caminho A: criar o SEU avatar (recomendado pra anúncio, é a sua cara e a sua marca)**

1. No site, vá em **Avatars > Create New Avatar > Digital Twin**.
2. Grave o vídeo de treino. O que importa:
   - **EM PÉ, formato RETRATO** (celular na vertical). O pipeline gera vídeo 9:16; avatar treinado deitado sai cortado ou com enquadramento errado.
   - **De 2 a 5 minutos** de gravação contínua, sem cortes (5 minutos treina melhor).
   - **1080p a 30fps no mínimo** (4K se der), luz clara e uniforme, fundo simples e parado, ambiente silencioso.
   - **Fale durante a gravação** (a voz do treino é usada pra calibrar o lip-sync), olhe pra câmera, gesticule natural mantendo as mãos no quadro.
3. Grave o **vídeo de consentimento** que o HeyGen pede (é uma frase curta confirmando que você autoriza a criação do avatar).
4. **Aguarde o processamento: de 10 a 30 minutos.** Aproveite pra seguir as etapas 3 e 4 deste guia enquanto espera.
5. Pronto: abra o avatar na área **Avatars** e copie o **id** dele (uma sequência de letras e números). É ele que vai no config na etapa 6.

Pegadinha conhecida: a pré-visualização do avatar no site às vezes aparece em paisagem mesmo quando está tudo certo. O que vale é o vídeo de treino que VOCÊ gravou. Na dúvida, confirme que o avatar suporta retrato/9:16 antes de gastar crédito.

**Caminho B: usar um avatar PRONTO do HeyGen (pra testar o pipeline hoje, sem esperar)**

A sua chave de API já enxerga centenas de avatares públicos do HeyGen. Depois da etapa 4 (instalação), rode:

```bash
vam avatars              # lista os avatares disponíveis
vam avatars studio       # filtra por nome
```

Escolha um, confira o visual dele em app.heygen.com > Avatars (prefira um look em RETRATO) e cole o `avatar_id` no config. Serve demais pra validar o fluxo inteiro antes do seu avatar ficar pronto; pro anúncio de verdade, o caminho A é o que constrói marca.

### 2.3 Pegar a API key do HeyGen

1. Em [app.heygen.com](https://app.heygen.com), vá em **Space Settings > API**.
2. Gere e copie a **API key** (é uma chave longa, tipo uma senha).
3. Guarde ela: você vai colocar no arquivo `.env` na etapa 4. Nunca compartilhe essa chave nem publique em lugar nenhum.

### 2.4 Instalar o ffmpeg e o Python

O ffmpeg é o programa que faz todo o processamento de vídeo local (grátis).

- **Mac:** abra o Terminal e rode `brew install ffmpeg`
  (se não tiver o Homebrew, instale primeiro em [brew.sh](https://brew.sh))
- **Linux (Ubuntu/Debian):** `sudo apt install ffmpeg`
- **Windows:** `choco install ffmpeg` ou `winget install ffmpeg`

Você também precisa do **Python 3.9 ou mais novo**. No Mac ele já vem instalado; confira com `python3 --version`. No Linux: `sudo apt install python3 python3-pip`.

---

## 3. Como gravar a voz (a parte mais importante)

A qualidade do anúncio inteiro depende desta gravação. O avatar, a legenda e a montagem são automáticos; a voz é a única coisa que só você pode fazer bem.

Regras de ouro:

1. **Microfone perto da boca.** Uns 10 a 20 cm. Pode ser o fone com microfone do celular, um lapela ou um microfone USB. O importante é estar perto: voz distante soa "de fundo de sala" e não tem conserto depois.
2. **Ambiente sem eco.** Quarto com cama, cortina, guarda-roupa aberto. Evite sala vazia, banheiro e cozinha (superfícies duras geram eco). Se bater palma e ouvir o som "voltando", troque de lugar.
3. **Silêncio de fundo.** Desligue ventilador e ar-condicionado, feche a janela. Ruído constante de fundo atrapalha inclusive a limpeza automática das pausas.
4. **Leia o roteiro INTEIRO em uma gravação só**, do começo ao fim, na ordem. O sistema usa esse áudio único pra gerar o avatar e cronometrar tudo.
5. **Pause naturalmente entre as frases.** Respire, tome fôlego, erre e repita a frase se quiser dar uma segunda tentativa na mesma hora (depois é só regravar o trecho falando de novo por cima, na sequência). Fale como você fala com um amigo, não como locutor.
6. **Não precisa cortar respiração nem pausa longa: o sistema corta sozinho.** A higienização de áudio detecta toda pausa maior que 0,55 segundo e encurta pra uma pausa natural de 0,26 segundo, preservando o ritmo da fala. Seu único trabalho é gravar com calma.

Salve o arquivo como `.mp3`, `.wav` ou `.m4a` e guarde numa pasta `inputs/` do seu projeto (etapa 7 mostra a estrutura).

Dica: se quiser ouvir como fica a voz depois da limpeza, rode
`vam clean-audio inputs/voz.mp3 /tmp/voz_limpa.mp3` e escute o resultado.

---

## 4. Instalar o sistema e rodar o `vam doctor` até ficar tudo verde

Abra o terminal e rode, linha por linha:

```bash
# 1) Baixar o projeto
git clone https://github.com/ojuliocouto/video-ads-machine.git
cd video-ads-machine

# 2) Atualizar o pip ANTES de instalar (o pip antigo do Mac quebra a instalação)
python3 -m pip install --user --upgrade pip

# 3) Instalar
python3 -m pip install --user -e .

# 4) Instalar UM backend de alinhamento de legenda (escolha o seu caso)
python3 -m pip install --user parakeet-mlx        # Mac com chip Apple (M1, M2, M3...)
python3 -m pip install --user 'faster-whisper>=1.0'  # Windows, Linux ou Mac Intel

# 5) Criar seus arquivos de configuração a partir dos exemplos
cp .env.example .env
cp config.example.yaml config.yaml
```

**Importante (Mac):** use sempre `python3 -m pip` (o comando `pip` sozinho não existe no Mac). E o passo 2 não é opcional: sem atualizar o pip, a instalação termina "com sucesso" mas quebrada.

**Se o comando `vam` não for encontrado** depois de instalar: o instalador colocou ele numa pasta fora do PATH (acontece direto no Mac). Não precisa consertar o PATH: use a forma equivalente `python3 -m vam` em todos os comandos deste guia (ex: `python3 -m vam doctor`).

**Se você instalou o `faster-whisper`** (Windows, Linux ou Mac Intel): no seu PRIMEIRO build, ele baixa um modelo de uns 500 MB. É normal e acontece só uma vez. Se o build parecer parado na etapa da legenda na primeira vez, é o download rodando, deixe terminar.

Agora abra o arquivo `.env` num editor de texto e cole a sua API key:

```
HEYGEN_API_KEY=sua_chave_aqui
```

E rode o médico do sistema:

```bash
vam doctor
```

Ele verifica tudo o que costuma dar problema na primeira vez: dependências do Python, ffmpeg funcionando de verdade (ele faz um mini render de teste), fontes, backend de legenda, sua API key do HeyGen (incluindo o crédito de API restante), se o seu `avatar_id` existe na sua conta e, se você configurou upload pro Drive, se o token está utilizável.

Cada item sai como `[OK]`, `[WARN]` ou `[FAIL]`, e **todo FAIL vem com a correção escrita na linha de baixo** (`fix: ...`). O ciclo é:

1. Rode `vam doctor`.
2. Aplique a correção do primeiro FAIL.
3. Rode de novo.
4. Repita até ver: `All required checks passed.`

Só siga pra próxima etapa com o doctor verde. WARN não bloqueia, mas leia o aviso: o de crédito de API zerado, por exemplo, significa que o build vai falhar na geração do avatar.

---

## 5. Escrever o roteiro anotado

O roteiro é um arquivo de texto simples (ex: `inputs/roteiro.txt`). **Cada linha é uma cena**, neste formato:

```
[instrução visual] o que você fala nessa cena...
```

O que está **entre colchetes** é a direção visual (o que aparece na tela). O que vem **depois** dos colchetes é a fala (exatamente o que você gravou, palavra por palavra, porque a legenda é gerada a partir desse texto).

Tipos de cena, definidos por palavras dentro da instrução:

| Você escreve na instrução | O que acontece na tela |
|---|---|
| `avatar` ou `apresentador` (pode juntar `zoom`) | Você em tela cheia falando, com zoom lento se pedir |
| qualquer outra descrição (ex: `tela do produto`) | Insert de b-roll: entra um vídeo seu por cima, com você em janelinha (PiP) |
| `lettering` | Texto grande estilizado na tela |
| `lettering` + `logo` | Texto grande com o seu logo |
| `logo` | Só o logo |

Nas cenas de lettering, você controla o texto exibido com dois marcadores:

- `KEY:` a palavra GIGANTE, em destaque na cor da sua marca
- `LEAD:` a linha pequena em itálico que fica em cima da palavra gigante

### Exemplo completo (genérico, adapte pro seu produto)

```
[avatar, zoom leve] Você prefere continuar fazendo tudo manualmente
[tela do produto em uso] ou prefere ver isso rodando sozinho, todos os dias?
[avatar] Eu montei um método que resolve isso em três passos.
[lettering | LEAD: um método simples | KEY: 3 PASSOS] E qualquer pessoa consegue aplicar.
[avatar, zoom leve] Sem experiência, sem equipe, sem enrolação.
[lettering + logo | LEAD: toque no botão | KEY: COMEÇA HOJE] Toca no botão aqui embaixo e garante a sua vaga.
```

Repare: a fala de cada linha, lida em sequência, forma o texto corrido que você gravou na etapa 3. Linhas em branco e anotações fora de colchetes são ignoradas, então pode deixar comentários no meio.

### Pegadinha do insert (importante)

Na instrução de um insert (b-roll), **nunca use as palavras `avatar` ou `apresentador`**. Se você escrever algo como `[b-roll com o apresentador na tela]`, o sistema classifica a cena como avatar em tela cheia, e o seu b-roll some. Descreva o CONTEÚDO da imagem: `[gravação de tela do painel]`, `[depoimento de cliente]`, `[unboxing do produto]`. O build detecta esse erro no preflight (gate G0) e avisa a linha exata.

### Os vídeos dos inserts

Cada cena de insert precisa de um arquivo de vídeo seu. Você declara isso num arquivo `inputs/inserts.json`, ligando uma palavra-chave da instrução ao arquivo:

```json
{
  "tela do produto": "broll/painel.mp4",
  "depoimento": "broll/depoimento.mp4"
}
```

Os caminhos são relativos à pasta do próprio `inserts.json`.

---

## 6. Configurar o `config.yaml`

Abra o `config.yaml` que você copiou na etapa 4. O mínimo obrigatório é uma linha:

```yaml
avatar_id: "SEU_AVATAR_ID"   # o id que você copiou no HeyGen (etapa 2.2)
```

Todo o resto tem padrão validado em produção. Os campos que você provavelmente vai querer personalizar:

```yaml
avatar_id: "SEU_AVATAR_ID"

brand:
  # Cor da palavra em destaque (KEY) nos letterings.
  # ATENÇÃO: o formato é BGR (azul-verde-vermelho), NÃO o RGB comum.
  # Ou seja: pegue a sua cor em RGB e inverta os pares.
  # Exemplo: laranja RGB FF A6 4A vira BGR 4AA6FF.
  key_color_bgr: "4AA6FF"
  # Logo em PNG com fundo transparente (opcional, usado nas cenas de logo)
  # logo_path: "./assets/meu-logo.png"

lettering:
  style: foil        # 'foil' = degradê metálico na palavra KEY (padrão validado)
                     # 'solid' = cor chapada da marca

audio:               # limpeza da voz gravada (padrões validados, raramente mude)
  big_sil: 0.55      # pausa maior que isso (segundos) é encurtada
  keep_pause: 0.26   # pausa natural que fica no lugar
  sil_db: -30        # limiar de silêncio; respiração fica abaixo disso

accelerate: 1.2      # aceleração final do vídeo (1.0 = sem acelerar)

# Opcional (avançado): subir os finais sozinho pra uma pasta sua do Google Drive.
# Você NÃO precisa disto: por padrão os vídeos ficam na pasta build/ e você sobe
# na mão. Só ligue se souber gerar um token OAuth do Google (veja docs/accounts.md).
# drive_folder: "https://drive.google.com/drive/folders/SUA_PASTA"

language: pt
workdir: "./build"
```

E, pra rodar o build completo, adicione no MESMO arquivo a seção `project`, apontando pros seus arquivos de entrada:

```yaml
project:
  name: meu-anuncio-01
  raw_voice: inputs/voz.mp3       # sua gravação REAL (etapa 3)
  script: inputs/roteiro.txt      # seu roteiro anotado (etapa 5)
  inserts: inputs/inserts.json    # opcional: só se tiver cenas de insert
```

Os caminhos são relativos à pasta onde o `config.yaml` está.

Dica: dá pra gerar o MESMO anúncio com mais de um visual de avatar (ex: um look estúdio e um casual), adicionando uma lista `avatars:` com `name` e `avatar_id` de cada um. Cada variação vira um par de vídeos finais.

---

## 7. Rodar o `vam build` e ler o manifest

Estrutura esperada da sua pasta neste ponto:

```
meu-anuncio/
├── config.yaml
├── inputs/
│   ├── voz.mp3
│   ├── roteiro.txt
│   └── inserts.json        (opcional)
└── broll/                  (opcional, os vídeos dos inserts)
    └── painel.mp4
```

Rode:

```bash
vam build config.yaml
```

O build passa por uma sequência de **portões de qualidade** (gates), e cada um só deixa passar se estiver certo:

| Gate | O que verifica |
|---|---|
| G0 preflight | Arquivos de entrada existem, roteiro tem cenas, nenhuma pegadinha de insert |
| G1 áudio | Voz limpa gerada, sem nenhuma pausa longa sobrando |
| G2 avatar | O avatar foi gerado com a duração exata da sua voz limpa |
| G3 montagem | Os letterings anunciados no roteiro estão todos na montagem |
| G4 legendas | As duas versões (9:16 e 1:1) foram legendadas |
| G5 aceleração | O vídeo final tem a duração esperada após acelerar |
| G6 auditoria | Vídeo final sem silêncios longos e consistente entre variações |
| G7 Drive | Só se configurado: sobe os finais e CONFIRMA que chegaram na pasta |

Se qualquer gate falhar, o build para com `BUILD BLOCKED:` e uma mensagem dizendo **o que quebrou e como corrigir**. Nada de vídeo pela metade.

No final, os arquivos ficam em `build/`:

- `meu-anuncio-01_default_final_9x16.mp4` (Reels/Stories)
- `meu-anuncio-01_default_final_1x1.mp4` (feed)
- `meu-anuncio-01_manifest.json` (o recibo do build)

### Como ler o manifest

O manifest é um JSON com o resultado de cada gate. As partes que importam:

- **`all_pass`**: tem que ser `true`. Se for `true`, o vídeo passou em TODAS as verificações. É a sua prova de que está pronto.
- **`variants`**: lista de vídeos gerados, com duração de cada um.
- **`gates`**: cada verificação com `ok: true/false`, detalhe e métricas (ex: quantos cortes de silêncio foram feitos, duração do avatar vs. da voz).
- **`drive`**: se você configurou upload, o link da pasta e a confirmação de cada arquivo.

Antes de publicar, **assista aos dois vídeos finais do começo ao fim**. O sistema garante a parte técnica; o olho no resultado é seu.

---

## 8. Erros comuns e o que fazer

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `[FAIL] HEYGEN_API_KEY: ... not set` | O `.env` não tem a chave ou você está rodando de outra pasta | Confira o arquivo `.env` na pasta do projeto e rode os comandos a partir dela |
| `[FAIL] HEYGEN_API_KEY: HeyGen rejected the key` | Chave copiada pela metade, com espaço, ou não é uma API key | Gere uma chave nova em app.heygen.com > Space Settings > API e cole inteira |
| `[WARN] ... remaining API credit is 0` | Crédito de API zerado (é separado do crédito do plano!) | Compre crédito de API no painel do HeyGen (seção API). Crédito do plano NÃO conta |
| `[FAIL] avatar_id ... was not found` | Id errado, ou a chave é de outra conta/espaço | Abra o SEU avatar em app.heygen.com > Avatars e copie o id de novo. Chave e avatar precisam ser da mesma conta |
| `[WARN] avatar ... looks LANDSCAPE` | Vídeo de treino do avatar pode ter sido gravado deitado | Confirme no HeyGen que o avatar suporta retrato/9:16 antes de gastar crédito. Se não suportar, treine um novo em pé |
| `[FAIL] ffmpeg ... dyld Library not loaded` (Mac) | Uma atualização do sistema quebrou o ffmpeg | `brew reinstall ffmpeg` |
| `[FAIL] ffmpeg ... compiled without libass` | Versão "mínima" do ffmpeg, sem suporte a legenda | Instale o ffmpeg completo (brew/apt), não uma versão estática enxuta |
| G1: `big silence(s) still in the cleaned voice` | Ruído de fundo alto escondendo as pausas | Regrave num lugar mais silencioso, ou suba `audio.sil_db` pra `-25` no config |
| G0: `insert instruction contains a presenter word` | Você escreveu `avatar` ou `apresentador` dentro de uma instrução de insert | Reescreva a instrução descrevendo a imagem (ex: `gravação de tela do painel`) |
| G3: número de letterings não bate | Linha de lettering com erro de digitação (ex: sem a palavra `lettering`) | Confira as linhas `[lettering ...]` do roteiro, uma por uma |
| G7: upload pro Drive falhou | Token expirado ou pasta sem permissão de escrita | Confira o `GOOGLE_OAUTH_TOKEN_FILE` (veja `docs/accounts.md`) e se a pasta é sua. Rode o build de novo: o upload não duplica arquivos |
| `BUILD BLOCKED` com outra mensagem | Qualquer gate reprovou | Leia a mensagem: ela sempre diz o que quebrou e a correção. Ajuste e rode `vam build config.yaml` de novo |

Regra geral pra qualquer problema: rode `vam doctor` primeiro. Se ele estiver todo verde, o problema está nos seus arquivos de entrada (roteiro, áudio, config), e a mensagem do gate aponta o lugar exato.

Bom build!
