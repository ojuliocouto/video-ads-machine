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
- O transcritor no Windows é o `faster-whisper`. O `parakeet-mlx` só existe no Apple Silicon, e o doctor avisa isso na linha `transcritor`.
- Prove o render antes do primeiro anúncio: `python scripts/vam.py fumaca --saida fumaca.mp4`.

O Python do Homebrew recusa `pip install` fora de ambiente virtual (PEP 668). O `setup.sh` cria um `.venv` próprio no repo; não instale nada no Python do sistema. No Windows, rode o `setup.sh` no Git Bash (o app desktop do Claude já faz isso), nunca no PowerShell.

## 2. Contas e chaves

| Serviço | Quando é necessário | Variável no `.env` | Como obter |
|---|---|---|---|
| HeyGen | só o caminho avatar | `HEYGEN_API_KEY` | conta em app.heygen.com, Settings, API. Paga por uso, em dólar; o doctor mostra o saldo |
| Groq | reserva de transcrição na nuvem, quando a máquina não tem transcritor local (o corte de take recusa a Groq) | `GROQ_API_KEY` | console.groq.com. Paga por uso |
| ElevenLabs | só o caminho gravado, no passo `isolar` (Voice Isolator) | `ELEVENLABS_API_KEY` | conta ElevenLabs. Paga por uso |
| Google (token OAuth próprio) | opcional: roteiro vindo de Google Doc com comentários | `GOOGLE_OAUTH_ACCESS_TOKEN` | sua conta. Só então liga o `gate_fidelidade_doc` |

Os caminhos gravado e one-shot funcionam sem HeyGen. O avatar sem chave fica desligado, com uma linha de conserto no doctor.

Transcritor por sistema, em ordem de preferência:

| Sistema | Transcritor | Onde roda |
|---|---|---|
| Mac Apple Silicon | `parakeet-mlx` | local |
| Mac Intel, Linux e Windows | `faster-whisper`, com o idioma forçado em português | local |
| qualquer um, sem transcritor local | Groq | nuvem, pago por uso, só como reserva |

O `setup.sh` instala o local certo no `.venv`: `parakeet-mlx` no Apple Silicon, `faster-whisper` nos outros. Para instalar à mão, rode dentro do `.venv` (`.venv/bin/python -m pip install faster-whisper`; no Windows, `.venv/Scripts/python -m pip install faster-whisper`). O corte de take (one-shot e gravado) exige tempo de palavra real; a Groq infla o token e é recusada nesses casos.

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

- Régua medida: de 200 a 227 créditos por minuto de avatar; 60 créditos valem US$ 1.
- Um avatar de cerca de 1 minuto (a voz limpa de um anúncio de 42 s a 1 min) custa de 190 a 216 créditos, ou de US$ 3,2 a 3,6 pela régua de créditos. A leitura da carteira em dólar deu cerca de US$ 4,6 por minuto, o que põe um avatar de 57 s em torno de US$ 4,4. Use US$ 3,2 a US$ 4,4 como faixa.
- O motor lê o saldo antes e depois do job (`GET /v3/users/me`) e grava o gasto real em `avatar/custo.json`. O teto padrão é US$ 5,00 por job (`TETO_USD` em `scripts/cli/avatar.py`); passou do teto, para e reporta.
- Custo zero: `vam avatar <slug> --existente avatar.mp4` usa um avatar já gerado da mesma voz limpa. Os caminhos gravado e one-shot não gastam HeyGen.
- Groq e transcrição local: sem custo relevante. ElevenLabs: por uso, só no `isolar`.

Gerar avatar duas vezes por defeito de áudio dobra o gasto: por isso `vam audio` vem antes.

## 6. Se o doctor reprovar

| Linha do doctor | Conserto |
|---|---|
| `node_hyperframes` FAIL | `bash scripts/setup.sh` (instala o HyperFrames em `node_modules`). Sem o Node: Mac `brew install node@22`, Windows `winget install -e --id OpenJS.NodeJS.LTS` |
| `ffmpeg_libass` FAIL | instale um ffmpeg com libass (Mac: `brew install ffmpeg`; Debian ou Ubuntu: `sudo apt install ffmpeg`; Windows: `winget install -e --id Gyan.FFmpeg`, depois feche e abra o app do Claude) |
| `python_deps` FAIL | `bash scripts/setup.sh` (recria o `.venv`). Sem o Python: Mac `brew install python@3.12`, Windows `winget install -e --id Python.Python.3.12` |
| `transcritor` FAIL | instale `faster-whisper` (ou `parakeet-mlx` no Apple Silicon), ou ponha `GROQ_API_KEY` |
| `fontes` FAIL | restaure `fonts/` (vêm no repo) |
| `rede` WARN | `bash scripts/setup.sh` guarda o GSAP local |
| `heygen` WARN | ponha `HEYGEN_API_KEY` no `.env` para usar avatar |

FAIL barra tudo e WARN passa. Rode o doctor de novo até não haver FAIL. Com o doctor limpo, rode `vam fumaca --saida fumaca.mp4`: é a prova rápida do render (2 s de vídeo, 10 a 20 s de espera). Saída 0 quer dizer Node, HyperFrames, Chromium e fontes funcionando; saída 1 é defeito do render; saída 2 é insumo faltando (sem `--saida`, sem ffprobe ou sem HyperFrames).

## 7. Segurança

- Nenhuma chave entra no git: `.env`, `_local/` e `assets/` são ignorados. Antes de publicar um fork, varra o histórico atrás de chave e de nome de cliente.
- Voz, avatar, logo e inserts do aluno ficam em `_local/`. O repo não carrega mídia nem música.
- Captura de tela usada como insert pode mostrar dado de pessoa real: confira antes de publicar o anúncio.
- A skill só roda comandos locais que você pode ler. Chamada paga (HeyGen, ElevenLabs) só acontece quando você roda o comando que a faz, e a de avatar respeita o teto.
