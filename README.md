# video-ads-machine

A Claude Code skill that turns a script and your real voice into a vertical (9:16) video ad, and refuses to hand it over until it has passed measured quality gates and two human sign-offs.

You paste a script in the chat, record your voice, pick a look (or bring a camera take), and Claude drives a single CLI, `vam`, from the first command to a finished `final_9x16.mp4` plus a lightweight preview for WhatsApp. Every step writes its result to disk, every number that decides "good enough" comes from a constant in the code, and the delivery is blocked by exit code, not by good intentions.

## What it is

- **A production pipeline in three modes**: an AI avatar speaking your voice (HeyGen Avatar V), several camera takes cut sentence by sentence (events, lavalier, retakes), or a single camera take with the dead air removed (one-shot).
- **A set of 14 measured "cinematic" capabilities** (hook in the first 3 seconds, cut rhythm, camera movement, color grade, karaoke captions, lettering, insert density, music ducking, sound effects, loudness, a single clock for footage and overlay, and more). Each one has a number and a gate. See `references/cinematografico.md`.
- **About 30 gates** that measure the delivered file, not the plan: caption contrast, text-over-face collision, safe zone, loudness, silence, frozen frames, speech preserved against the script, and so on. See `references/gates.md`.
- **Two human ceremonies** that cannot be skipped: you approve the edit plan in the chat, and an independent auditor (a sub-agent with a clean context) signs a grade of 8 or more on the exact file that will be delivered. Whoever builds the ad never signs.
- **Script-first and spreadsheet-free**: the script is a plain `roteiro.md` (pasted text, a `.md` or `.txt` file, or optionally a Google Doc with comments through your own OAuth token).

## What it is NOT

- Not a hosted app. Everything runs on your machine.
- Not a generator of voices. The voice is always yours; synthetic voice is the first tell of AI content and the tool refuses it by design.
- Not a replacement for the video's creative idea. It builds, measures and blocks; the script, the offer and the taste are yours.
- Not a long-form tool. VSLs, motion graphics, explainers, static creatives and subtitles-only jobs belong to other tools.
- Not a bundle of third-party software. HyperFrames (the renderer for the overlay) is installed from npm onto your machine by the setup step and is not redistributed here. See `NOTICE`.
- Not shipped with any music, avatar, voice or client asset. All of that is yours and lives in `_local/`, which git ignores.

## How it works

The avatar path runs in six named phases. Each phase is one or two `vam` commands, and each one ends with a gate.

| Phase | Command | Gate |
|---|---|---|
| 0 Entry | `vam novo`, `vam roteiro` | the script follows the convention (`contratos/roteiro-convencao.md`) |
| 0.5 Audio | `vam audio` | breath, flat rhythm, preserved speech, speech against script |
| 1 Avatar | `vam avatar` | 1080x1920, useful fraction, duration within 1.0 s of the voice, look approved |
| 2 Plan | `vam plano`, `vam aprovar` | six sections, checklist, sha256-bound approval |
| 2.5 Board | `vam plano --prancha` | a director reads a still-frame board before any render |
| 3 Build and delivery | `vam montar`, `vam auditar`, `vam entregar` | 29 gates, grade 8 or more, laudo, approval and grade on the same sha256 |

`vam` stands for `python3 scripts/vam.py`, run from the repo root. Every command exits 0 (done), 1 (a measured defect) or 2 (invalid request or missing input), prints what to do next, and `vam status <slug>` reads where a project stopped.

The camera paths are `vam gravado <slug> <action>` (create, extract, isolate, plan, build, caption box, captions, caption approval, burn, gates, deliver) and `vam oneshot`. UI inserts (WhatsApp, terminal, kanban, dashboard, agenda, counter, flow) come from `vam insert`.

The skill itself is `SKILL.md`: a router with the checklists, the numbers and the "never" list. The details live in `references/`, one file per phase.

## Install

Prerequisites:

- macOS (Apple Silicon or Intel), Linux, or Windows 10/11 (native, inside the Claude desktop app, no WSL)
- Python 3.9 or newer (3.12 recommended)
- Node.js 22 or newer
- ffmpeg built with libass
- Claude Code or the Claude desktop app. On Windows both run shell commands through Git Bash, so install Git for Windows

```bash
git clone <repo-url> video-ads-machine      # into your Claude Code skills folder
cd video-ads-machine
bash scripts/setup.sh                       # creates .venv, installs HyperFrames, prepares _local/, writes .env
python3 scripts/vam.py doctor               # must end with no FAIL
```

### Windows (native)

Open a terminal (PowerShell) and install the prerequisites, one command each:

```powershell
winget install -e --id Git.Git
winget install -e --id Python.Python.3.12
winget install -e --id OpenJS.NodeJS.LTS
winget install -e --id Gyan.FFmpeg
```

Then close and reopen the Claude app, so the new PATH applies. Run the same `git clone` and `bash scripts/setup.sh` from the Claude app (it runs commands through Git Bash). On Windows, write `python scripts/vam.py ...` where this README says `python3 scripts/vam.py ...`: the `python3` of Windows may be the Microsoft Store shortcut, which does not run Python. `setup.sh` skips that shortcut on its own.

### Transcriber (the same on Mac, Windows and Linux)

| Transcriber | Where it runs | Needs |
|---|---|---|
| Mistral Voxtral Mini Transcribe (first) | cloud | `MISTRAL_API_KEY` in `.env` (the same key you created in the Curso → Skill lesson) |
| Groq `whisper-large-v3-turbo` (second) | cloud, free plan | `GROQ_API_KEY` in `.env` (create it at console.groq.com) |
| `faster-whisper` `large-v3-turbo` (optional) | local, CPU, offline | `pip install faster-whisper`; downloads about 1.5 GB on first use |

The first cloud key that exists wins (`ORDEM_NUVEM` in `scripts/audio/transcrever.py`; `VAM_TRANSCRITOR=mistral|groq` puts one first). If that call fails or returns no word timestamps, the next one takes over and one line says so (Mistral retries once after 20 s on a capacity error). Steps that cut the take put Groq first when `GROQ_API_KEY` exists, because its word timing is more precise. Everything is transcribed in the cloud, so nothing heavy is installed on the student PC. `setup.sh` installs no transcriber and downloads no model. `faster-whisper` is an optional offline fallback: it runs only if you installed the package yourself and no cloud key works. With no key and no `faster-whisper`, the doctor reports FAIL with both fixes.

The cloud marks the start of some words late (Groq: 17% more than 200 ms, measured on 20/10/2026; Mistral rounds times to 0.1 s). Take cutting compensates: each word keeps a pre-roll before it (0.30 s for Groq, 0.40 s for Mistral) and 0.15 s after it (`VAM_CORTE_PRE_ROLL`, `VAM_CORTE_POS_ROLL` in `.env` change them), never overlapping the neighbor word. Then the cut audio is transcribed again, and the gate fails if any word was lost or shortened.

Brand names in English are often heard wrong (for example "Claude" is heard as "Cloud"). Add the right spelling to `_local/glossario.json`: `{"versao": 1, "termos": [{"grafia": "Claude", "variantes": ["Cloud"]}]}`.

### Quick render check

`python3 scripts/vam.py fumaca --saida fumaca.mp4` renders a 2-second overlay in 10 to 20 seconds, with no project and no media. It exits 0 only if Node, HyperFrames, Chromium and the fonts work on this machine. Run it after the doctor, before the first ad.

`setup.sh` is idempotent and no step aborts the next ones; whatever fails becomes one line with the fix command. `bash scripts/setup.sh --checar` only reports. The doctor checks ffmpeg with libass, Node and the repo's HyperFrames, the Python dependencies, the transcriber (a Mistral or Groq key; FAIL if neither exists), the fonts, the local GSAP copy and the HeyGen key with your balance. Any FAIL stops everything.

## Accounts and keys

| Service | Needed for | Variable (`.env`) |
|---|---|---|
| HeyGen | the avatar path only | `HEYGEN_API_KEY` |
| Mistral | transcription, first choice (the key from the Curso → Skill lesson) | `MISTRAL_API_KEY` |
| Groq | transcription, second choice (free plan); one of the two keys is required | `GROQ_API_KEY` |
| ElevenLabs | voice isolation in the camera-takes path | `ELEVENLABS_API_KEY` |
| Google (your own OAuth token) | optional: script from a Google Doc | `GOOGLE_OAUTH_ACCESS_TOKEN` |

The camera paths work without HeyGen. HeyGen is pay-per-use, in dollars, at about US$ 7 per minute of avatar (measured on a real job: US$ 3.25 for 27.6 s of voice). A 30 s ad costs about US$ 3.50 and a 60 s ad costs about US$ 7. Before it asks for a job, the tool estimates the cost from the length of your voice and refuses, with nothing spent, if the estimate passes the US$ 9.00 cap (that covers a voice of about 70 s). It also reads your balance before and after the job and writes the real cost to `avatar/custo.json`. The full onboarding is in `references/onboarding.md`.

## Content of this repo

| Path | What it holds |
|---|---|
| `SKILL.md` | the skill entry point: routing, per-path checklists, numbers, the "never" list |
| `references/` | one file per phase, the 14 capabilities, the gates table, the auditor prompt, onboarding and the lessons behind each rule |
| `contratos/` | JSON schemas for project, plan, approval, grade, laudo, timeline, looks and glossary, the script convention, and valid and invalid examples |
| `scripts/` | the `vam` CLI (`scripts/cli/`), the gates (`scripts/gates/`), the camera-takes pipeline (`scripts/gravado/`), `setup.sh` and the engine modules |
| `templates/` | the HTML overlay templates and the UI insert templates |
| `fonts/` | open-licensed fonts (SIL OFL) |
| `docs/GUIA-ALUNO.md` | a step-by-step guide, in Portuguese, from zero to the first ad |
| `tests/` | the test suite |

Your own material lives in `_local/` (git ignored): `looks.json`, `glossario.json`, `marca/logo.png`, `trilhas/` and `projetos/<slug>/`.

## Security

- **Bring your own keys.** Keys live in `.env`, which git ignores. Nothing in the tool sends a key anywhere except to the service it belongs to.
- **No real assets ship here.** No avatar, voice, logo, music or client script is committed. `_local/`, `assets/`, rendered folders and media files are ignored.
- **Paid calls are explicit.** HeyGen and ElevenLabs are only called when you run the command that does it, and the avatar job respects a dollar cap.
- **No gate is switched off by an environment variable.** An exception to a measured rule lives in the project (`projeto.json`, `excecoes`) with a written reason, and goes to the laudo.
- **Check screen captures before you publish.** An insert made from a real screen recording can show a person's name, phone, e-mail or conversation.
- Before publishing a fork, scan the history for keys and for client names.

## License

MIT, see `LICENSE`. Third-party notices (HyperFrames installed through npm, fonts under the SIL Open Font License) are in `NOTICE`.
