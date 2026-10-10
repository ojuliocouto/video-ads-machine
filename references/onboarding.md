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
| macOS (Apple Silicon é a plataforma oficial) ou Linux | | o CI roda os testes unitários no Linux |
| Python | 3.9 ou superior (o do macOS serve) | CLI, gates, áudio |
| Node.js | 22 ou superior | HyperFrames, que renderiza o overlay |
| ffmpeg com libass | qualquer atual | cortes, legenda, loudness (`brew install ffmpeg` no macOS) |
| Claude Code | atual | roda esta skill |

O Python do Homebrew recusa `pip install` fora de ambiente virtual (PEP 668). O `setup.sh` cria um `.venv` próprio no repo; não instale nada no Python do sistema.

## 2. Contas e chaves

| Serviço | Quando é necessário | Variável no `.env` | Como obter |
|---|---|---|---|
| HeyGen | só o caminho avatar | `HEYGEN_API_KEY` | conta em app.heygen.com, Settings, API. Paga por uso, em dólar; o doctor mostra o saldo |
| Groq | reserva de transcrição na nuvem, quando a máquina não tem parakeet nem faster-whisper | `GROQ_API_KEY` | console.groq.com. Paga por uso |
| ElevenLabs | só o caminho gravado, no passo `isolar` (Voice Isolator) | `ELEVENLABS_API_KEY` | conta ElevenLabs. Paga por uso |
| Google (token OAuth próprio) | opcional: roteiro vindo de Google Doc com comentários | `GOOGLE_OAUTH_ACCESS_TOKEN` | sua conta. Só então liga o `gate_fidelidade_doc` |

Os caminhos gravado e one-shot funcionam sem HeyGen. O avatar sem chave fica desligado, com uma linha de conserto no doctor.

Transcritor, em ordem: `parakeet-mlx` (Apple Silicon), `faster-whisper` (qualquer máquina), Groq (nuvem). Instale um dos dois locais para não depender de rede: `python3 -m pip install parakeet-mlx` ou `python3 -m pip install faster-whisper` dentro do `.venv`. O corte de take (one-shot e gravado) exige tempo de palavra real; a Groq infla o token e é recusada nesses casos.

## 3. Instalação

```
git clone <url-do-repo> video-ads-machine
cd video-ads-machine
bash scripts/setup.sh
python3 scripts/vam.py doctor
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
| `node_hyperframes` FAIL | `bash scripts/setup.sh` (instala o HyperFrames em `node_modules/.bin`) |
| `ffmpeg_libass` FAIL | instale um ffmpeg com libass (`brew install ffmpeg`) |
| `python_deps` FAIL | `bash scripts/setup.sh` (recria o `.venv`) |
| `transcritor` FAIL | instale `parakeet-mlx` ou `faster-whisper`, ou ponha `GROQ_API_KEY` |
| `fontes` FAIL | restaure `fonts/` (vêm no repo) |
| `rede` WARN | `bash scripts/setup.sh` guarda o GSAP local |
| `heygen` WARN | ponha `HEYGEN_API_KEY` no `.env` para usar avatar |

FAIL barra tudo e WARN passa. Rode o doctor de novo até não haver FAIL.

## 7. Segurança

- Nenhuma chave entra no git: `.env`, `_local/` e `assets/` são ignorados. Antes de publicar um fork, varra o histórico atrás de chave e de nome de cliente.
- Voz, avatar, logo e inserts do aluno ficam em `_local/`. O repo não carrega mídia nem música.
- Captura de tela usada como insert pode mostrar dado de pessoa real: confira antes de publicar o anúncio.
- A skill só roda comandos locais que você pode ler. Chamada paga (HeyGen, ElevenLabs) só acontece quando você roda o comando que a faz, e a de avatar respeita o teto.
