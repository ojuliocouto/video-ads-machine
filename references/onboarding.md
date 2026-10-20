# Onboarding: contas, chaves, `.env` e custo

Faça isto uma vez, antes do primeiro anúncio. O alvo é o `vam doctor` sem nenhum FAIL.

## Sumário

1. O que você precisa ter
2. Contas e chaves
3. Instalação
4. O arquivo `.env`
5. Custo do HeyGen
6. Se o doctor reprovar
7. Segurança

## 1. O que você precisa ter

| Item | Versão | Para quê |
|---|---|---|
| Sistema | macOS (Apple Silicon ou Intel), Linux, ou Windows 10 ou 11 nativo | o CI testa Linux e Windows |
| Python | 3.9 ou superior (recomendado 3.12) | CLI, gates, áudio |
| Node.js | 22 ou superior | HyperFrames, que renderiza o overlay |
| ffmpeg com libass | qualquer atual | cortes, legenda, loudness |
| Claude (Code ou app desktop) | atual | roda esta skill |
| Git for Windows | só no Windows | traz o Git Bash, que roda os comandos |

Comandos por sistema:

| Sistema | Instalação |
|---|---|
| macOS | `brew install python@3.12 node@22 ffmpeg` |
| Debian ou Ubuntu | `sudo apt install python3 python3-venv nodejs ffmpeg` (confira que o Node é o 22 ou superior) |
| Windows | `winget install -e --id Git.Git`, `winget install -e --id Python.Python.3.12`, `winget install -e --id OpenJS.NodeJS.LTS` e `winget install -e --id Gyan.FFmpeg` |

### Windows: como funciona

- O Windows roda nativo, sem WSL e sem Homebrew. No app desktop do Claude, os comandos passam pelo Git Bash. O Claude Code no Windows também exige o Git for Windows.
- Depois de instalar com o `winget`, feche e abra o app do Claude. Sem isso o PATH novo não vale e o `setup.sh` não acha o Python, o Node nem o ffmpeg.
- Nos comandos desta skill, troque `python3` por `python` (`python scripts/vam.py doctor`). O `python3` do Windows pode ser o atalho da Microsoft Store, que não executa Python. O `setup.sh` ignora esse atalho e procura `python3`, `py -3` e `python`, nessa ordem.
- O `.venv` guarda o Python em `.venv/Scripts/python.exe`. O `vam` já o usa sozinho.
- O transcritor é a nuvem (Mistral ou Groq), igual no Windows, no Mac e no Linux. O doctor confere as chaves na linha `transcritor`.
- Prove o render antes do primeiro anúncio: `python scripts/vam.py fumaca --saida fumaca.mp4`.

O Python do Homebrew recusa `pip install` fora de ambiente virtual (PEP 668). O `setup.sh` cria um `.venv` próprio no repo; não instale nada no Python do sistema. No Windows, rode o `setup.sh` no Git Bash (o app desktop do Claude já faz isso), nunca no PowerShell.

## 2. Contas e chaves

| Serviço | Quando é necessário | Variável no `.env` | Como obter |
|---|---|---|---|
| HeyGen | só o caminho avatar | `HEYGEN_API_KEY` | conta em app.heygen.com, Settings, API. Paga por uso, em dólar; o doctor mostra o saldo |
| Mistral | transcrição, primeira escolha (uma das duas chaves é obrigatória; o doctor dá FAIL sem nenhuma) | `MISTRAL_API_KEY` | a mesma chave que você criou na aula de Curso → Skill (console.mistral.ai) |
| Groq | transcrição, segunda escolha | `GROQ_API_KEY` | console.groq.com, API Keys. O plano é gratuito |
| ElevenLabs | só o caminho gravado, no passo `isolar` (Voice Isolator) | `ELEVENLABS_API_KEY` | conta ElevenLabs. Paga por uso |
| Google (token OAuth próprio) | opcional: roteiro vindo de Google Doc com comentários | `GOOGLE_OAUTH_ACCESS_TOKEN` | sua conta. Só então liga o `gate_fidelidade_doc` |

Os caminhos gravado e one-shot funcionam sem HeyGen. O avatar sem chave fica desligado, com uma linha de conserto no doctor.

Transcritor (igual no Mac, no Windows e no Linux):

| Transcritor | Onde roda | O que precisa |
|---|---|---|
| Mistral Voxtral Mini Transcribe (primeiro) | nuvem | `MISTRAL_API_KEY` no `.env`: a mesma chave que você criou na aula de Curso → Skill |
| Groq `whisper-large-v3-turbo` (segundo) | nuvem, plano gratuito | `GROQ_API_KEY` no `.env` |
| `faster-whisper` `large-v3-turbo` (opcional) | local, CPU, offline | `pip install faster-whisper`; baixa cerca de 1,5 GB no primeiro uso |

Vale a primeira chave que existir (a ordem é a constante `ORDEM_NUVEM`; `VAM_TRANSCRITOR=mistral` ou `groq` no `.env` põe uma na frente). Se essa nuvem falha ou devolve texto sem tempo por palavra, a seguinte assume e uma linha avisa. A Mistral tenta de novo uma vez, após 20 s, quando devolve erro de capacidade. Nos passos que cortam o take, a Groq vai na frente se existir `GROQ_API_KEY`, porque o tempo de palavra dela é mais preciso. O `setup.sh` não instala transcritor nem baixa modelo: nada pesado fica no PC do aluno. Para criar a chave da Groq, abra console.groq.com, entre em API Keys, crie uma chave e cole `GROQ_API_KEY=...` no `.env` da raiz do repo. O faster-whisper é uma reserva offline opcional. Ele só roda se o aluno instalou o pacote (dentro do `.venv`: `.venv/bin/python -m pip install faster-whisper`; no Windows, `.venv/Scripts/python -m pip install faster-whisper`) e nenhuma chave funcionou. Para trocar o modelo local, defina `VAM_WHISPER_MODELO` no `.env` (padrão `large-v3-turbo`).

A nuvem marca o começo de algumas palavras tarde (Groq: 17% mais de 200 ms; Mistral: 39%, em grade de 0,1 s). O corte de take (one-shot e gravado) compensa: guarda uma margem antes de cada palavra (0,30 s para a Groq, 0,40 s para a Mistral) e 0,15 s depois, sem invadir a palavra vizinha, e re-transcreve o corte para conferir que nenhuma palavra sumiu nem encurtou. Os valores mudam com `VAM_CORTE_PRE_ROLL` e `VAM_CORTE_POS_ROLL` no `.env`.

Nome de marca em inglês costuma sair errado: "Claude" sai como "Cloud". Declare a grafia certa em `_local/glossario.json` (`{"versao": 1, "termos": [{"grafia": "Claude", "variantes": ["Cloud"]}]}`). Atenção: a Mistral não recebe o vocabulário do glossário (a API não aceita prompt junto com tempo por palavra), então a correção de grafia do glossário é ainda mais importante com ela.

## 3. Instalação

```
git clone <url-do-repo> video-ads-machine
cd video-ads-machine
bash scripts/setup.sh
python3 scripts/vam.py doctor          # no Windows: python scripts/vam.py doctor
```

O `setup.sh` é idempotente: cada passo só faz o que falta, e nenhum aborta os seguintes. Em ordem: cria o `.venv`; instala o `requirements.txt` nele; confere o Node; instala o HyperFrames na versão fixada no `package.json`; garante o Chromium do render; guarda uma cópia local do GSAP (o render não depende de CDN); cria o `.env` a partir do `.env.example` (nunca sobrescreve); prepara `_local/`; gera os efeitos sonoros. O que falhar vira uma linha de aviso com o comando de conserto e entra no resumo final. `bash scripts/setup.sh --checar` só relata, sem instalar nada.

Para usar como skill do Claude Code, o repo precisa estar dentro da pasta de skills do Claude Code (a pasta `skills` do diretório de configuração do Claude Code). Os comandos desta skill são sempre relativos à raiz do repo.

## 4. O arquivo `.env`

Copie `.env.example` para `.env` (o setup já faz) e preencha só o que usa. O `.env` fica fora do git. Variável já exportada no terminal vale mais que a do `.env`. O que ajusta o dia a dia: `VAM_ESTADO` (a pasta `_local`), `VAM_DADOS` (mídia pesada), `VAM_GATES_PARALELO` e `VAM_PARALELO` (baixe para 2 em máquina fraca). Nada no `.env` desliga um gate.

## 5. Custo do HeyGen

O avatar é o único gasto relevante de um anúncio.

- Preço medido: cerca de US$ 7 por minuto de voz. Fonte: o job real de 20/10/2026 custou US$ 3,25 para 27,6 s de voz (US$ 7,08 por minuto; saldo de US$ 16,65 para US$ 13,40).
- Um anúncio de 30 s custa cerca de US$ 3,50. Um anúncio de 60 s custa cerca de US$ 7.
- Antes de pedir o job, o motor estima o custo pela duração da voz limpa (`CUSTO_USD_POR_MINUTO` em `scripts/avatar/custo.py`) e recusa se a estimativa passar do teto. Nada é gasto, e a mensagem diz a duração máxima que cabe.
- O teto padrão é US$ 9,00 por job (`TETO_USD` em `scripts/cli/avatar.py`), que cobre uma voz de cerca de 70 s. Para pagar um job maior, rode `vam avatar <slug> --teto-usd <valor>`.
- Depois do job, o motor lê o saldo antes e depois (`GET /v3/users/me`) e grava o gasto real em `avatar/custo.json`. Se o gasto real passar do teto, a prova para e reporta.
- Custo zero: `vam avatar <slug> --existente avatar.mp4` usa um avatar já gerado da mesma voz limpa. Os caminhos gravado e one-shot não gastam HeyGen.
- Mistral: a chave da aula, cobrança por uso. Groq: plano gratuito. Faster-whisper opcional: sem custo. ElevenLabs: por uso, só no `isolar`.

Gerar avatar duas vezes por defeito de áudio dobra o gasto: por isso `vam audio` vem antes.

## 6. Se o doctor reprovar

| Linha do doctor | Conserto |
|---|---|
| `node_hyperframes` FAIL | `bash scripts/setup.sh` (instala o HyperFrames em `node_modules`). Sem o Node: Mac `brew install node@22`, Windows `winget install -e --id OpenJS.NodeJS.LTS` |
| `ffmpeg_libass` FAIL | instale um ffmpeg com libass (Mac: `brew install ffmpeg`; Debian ou Ubuntu: `sudo apt install ffmpeg`; Windows: `winget install -e --id Gyan.FFmpeg`, depois feche e abra o app do Claude) |
| `python_deps` FAIL | `bash scripts/setup.sh` (recria o `.venv`). Sem o Python: Mac `brew install python@3.12`, Windows `winget install -e --id Python.Python.3.12` |
| `transcritor` FAIL | ponha no `.env` a `MISTRAL_API_KEY` (a chave da aula Curso → Skill) ou a `GROQ_API_KEY` (grátis em console.groq.com, API Keys) |
| `fontes` FAIL | restaure `fonts/` (vêm no repo) |
| `rede` WARN | `bash scripts/setup.sh` guarda o GSAP local |
| `heygen` WARN | ponha `HEYGEN_API_KEY` no `.env` para usar avatar |

FAIL barra tudo e WARN passa. Rode o doctor de novo até não haver FAIL. Com o doctor limpo, rode `vam fumaca --saida fumaca.mp4`: é a prova rápida do render (2 s de vídeo, 10 a 20 s de espera). Saída 0 quer dizer Node, HyperFrames, Chromium e fontes funcionando; saída 1 é defeito do render; saída 2 é insumo faltando (sem `--saida`, sem ffprobe ou sem HyperFrames).

## 7. Segurança

- Nenhuma chave entra no git: `.env`, `_local/` e `assets/` são ignorados. Antes de publicar um fork, varra o histórico atrás de chave e de nome de cliente.
- Voz, avatar, logo e inserts do aluno ficam em `_local/`. O repo não carrega mídia nem música.
- Captura de tela usada como insert pode mostrar dado de pessoa real: confira antes de publicar o anúncio.
- A skill só roda comandos locais que você pode ler. Chamada paga (HeyGen, ElevenLabs) só acontece quando você roda o comando que a faz, e a de avatar respeita o teto.
