---
name: video-ads-machine
description: >
  Produce video ads with an AI avatar (HeyGen Avatar V) from an annotated
  script plus a REAL recorded voice: silence cleanup, avatar lip-sync,
  montage with b-roll inserts, brand letterings, verbatim captions,
  speed-up, 9:16 and 1:1 outputs, optional Google Drive delivery.
  Use when the user asks to create a video ad, an ad creative in video,
  an avatar ad, or to assemble a reel/story ad.
  Triggers (en): video ad, avatar ad, video creative, ad video, make a video ad,
  video ads machine. Triggers (pt): anuncio em video, criativo em video,
  video de anuncio, criar anuncio, montar reel de anuncio, video com avatar.
---

# Video Ads Machine

You are operating a gated video-ad production pipeline. The user (often a
student, frequently Brazilian) provides two things: an annotated script and a
real voice recording. The tool does the rest: cleans the voice, renders a
HeyGen avatar with lip-sync, assembles b-roll inserts and brand letterings,
burns verbatim captions, speeds the result up, and outputs 9:16 and 1:1
finals, optionally uploading them to the user's Google Drive folder.

**Always reply in the user's language.** The commands and file contents stay
as-is; your explanations, questions and status updates follow the language the
user is writing in. Sample messages below are given in pt-BR because most
users are Brazilian; translate them naturally when the user writes in another
language. When writing Portuguese, never use the em dash character; use a
colon, comma or period instead, and always use correct Portuguese accents.

## Part 1: First use (onboarding, mandatory)

Detect first use: there is no `config.yaml` in the project root, or the user
says it is their first time. In that case run the onboarding before anything
else. Do not start a production run with a red doctor.

### Step 1: install and run the doctor

```bash
python3 -m pip install --user --upgrade pip   # old pips silently break the install
python3 -m pip install --user -e .            # from the repo root, once
vam doctor        # or: python3 -m vam doctor   (if 'vam' is not on PATH)
```

`vam doctor` prints one line per check, each `[OK]`, `[WARN]` or `[FAIL]`,
with a concrete fix under every non-OK item. Exit code 0 means no FAIL.

Walk the user through EVERY `[FAIL]`, one at a time, in simple language:

| Check | What it means | How you help |
|---|---|---|
| python deps | pyyaml missing | Run `python3 -m pip install --user -e .` for the user |
| ffmpeg | absent, or broken build (no libass, or dyld library error) | Give the exact install/reinstall command for their OS (the doctor prints it) |
| ffprobe | ships with ffmpeg | Same fix as ffmpeg |
| fonts | bundled `fonts/` directory missing its .ttf files | Re-clone the repo or restore `fonts/` |
| caption alignment | WARN only; needed to time captions | Apple Silicon: `pip install parakeet-mlx`; elsewhere: `pip install 'faster-whisper>=1.0'` |
| HEYGEN_API_KEY | key missing or rejected | See the HeyGen notes below |
| avatar_id | id not found in the account, or looks landscape | See the HeyGen notes below |
| drive | only checked when `drive_folder` is set | Fix `GOOGLE_OAUTH_TOKEN_FILE` per `docs/accounts.md`, or remove `drive_folder` |

HeyGen notes you must know when helping:

- The key comes from app.heygen.com under Space Settings > API and goes into
  `.env` as `HEYGEN_API_KEY=...` (copy `.env.example` to `.env` first; it is
  gitignored, never commit it).
- HeyGen **API credits are separate from plan credits**. A paid plan with
  plenty of credits can still have 0 API credits, and every render will fail.
  The doctor reports the remaining API credit; if it is 0, the user must add
  API credit in the HeyGen dashboard before building.
- The `avatar_id` must belong to the same account as the API key. The user
  finds it at app.heygen.com > Avatars, opening THEIR avatar.

**If the user has NO HeyGen account yet**, guide them through it (in their
language) before anything else:

1. Create the account at app.heygen.com. The FREE account already includes
   one custom avatar slot (Digital Twin); a paid plan (Creator, ~US$29/mo as
   of mid-2026) is only needed for the in-app editor and priority processing,
   NOT for this pipeline.
2. Buy API credit (pay-as-you-go, no subscription needed) at Space Settings >
   API. Reference: about US$1 per minute of 1080p avatar video (newer engines
   cost more per minute); US$10-20 is a comfortable start. Tell them to check
   HeyGen's current API pricing page, prices change.

**If the user has an account but NO avatar yet**, offer the two paths:

- **Path A, their own avatar (best for ads)**: at app.heygen.com go to
  Avatars > Create New Avatar > Digital Twin. Recording rules that matter:
  PORTRAIT orientation (phone upright), 2 to 5 minutes of one continuous
  take (no cuts), 1080p30 or better, bright even light, plain static
  background, quiet room, SPEAK during the take (it calibrates lip-sync),
  eyes to camera. HeyGen then asks for a short consent video and processes
  for 10 to 30 minutes: continue the rest of the onboarding while it runs.
- **Path B, a ready-made HeyGen avatar (test the pipeline today)**: run
  `vam avatars` (optionally `vam avatars <name>` to filter). It lists every
  look the key can use, including HeyGen public stock avatars. Have the user
  check the look's preview at app.heygen.com > Avatars, prefer PORTRAIT
  looks, and paste the chosen avatar_id into config.yaml. Good for
  validating the whole flow while Path A processes; for the real ad, their
  own avatar is what builds the brand.
- If the doctor warns the avatar preview looks landscape: the pipeline renders
  9:16 vertical. Ask the user to confirm in HeyGen that the avatar look
  supports portrait before burning credits on a long render.

Re-run `vam doctor` after each fix until there are zero FAILs. WARNs do not
block, but explain each one so the user decides consciously.

### Step 2: create config.yaml together

Copy `config.example.yaml` to `config.yaml`, then interview the user. Ask, in
their language, for the three personal values (everything else has validated
defaults):

1. **avatar_id**: "Qual o id do seu avatar na HeyGen? Você encontra em
   app.heygen.com, na aba Avatars, abrindo o SEU avatar."
2. **Brand color**: "Qual a cor da sua marca pra palavra de destaque dos
   letterings? Pode me passar em hex RGB que eu converto." The config stores
   it as `brand.key_color_bgr` in **BGR** hex (ASS subtitle format). Convert
   for the user: RGB `#FFA64A` becomes BGR `4AA6FF` (reverse the byte pairs).
   Never make the user do this conversion by hand.
3. **Logo (optional)**: a transparent-background PNG. If they have one, save
   it in the project and set `brand.logo_path`. If not, leave it commented out.

Also ask whether they want finished videos uploaded to a Google Drive folder.
If yes, set `drive_folder` and help them set up `GOOGLE_OAUTH_TOKEN_FILE`
following `docs/accounts.md`. If no, skip it: Drive is optional.

Do NOT touch the tuned defaults (`audio.big_sil: 0.55`,
`audio.keep_pause: 0.26`, `audio.sil_db: -30`, `accelerate: 1.2`,
`lettering.style: foil`, `y_key: 1690`, `y_key_with_logo: 1500`) unless the
user explicitly asks and understands the trade-off. They are
production-validated numbers.

Finish onboarding by running `vam doctor` one last time WITH the config in
place (it then also validates the avatar_id against the account and the Drive
token). Only declare setup done when the doctor ends with
"All required checks passed."

## Part 2: Producing an ad

### Step 1: collect the two inputs from the user

**Input A: the annotated script** (a plain text file). One scene per line:

```
[visual instruction] spoken narration...
[lettering | LEAD: small italic line | KEY: BIGWORD] narration...
```

Scene types by keyword in the instruction (priority order):
`lettering` (plus `logo` = lettering_logo) > `logo` > a presenter word
(`avatar`, `presenter`, `apresentador`) = full-screen talking head, with slow
zoom when "zoom" is mentioned > anything else = b-roll insert, matched by
keyword against the inserts map.

Known gotcha you must catch while reviewing the script: an INSERT instruction
must never contain a presenter word, otherwise the parser silently turns it
into a talking-head scene. "b-roll com o avatar na tela" is wrong; name the
footage instead, like "gravação de tela do produto". The build's G0 gate also
blocks this, but fix it during review so the user does not lose a cycle.

If the user has no script yet, help write one, then show it and get approval
before recording.

**Input B: the voice recording. This is BLOCKING.**

The narration must be a REAL human recording of the person reading the script
in order. Ask for it explicitly:

> "Agora preciso da sua voz de verdade gravando o roteiro, na ordem, num
> lugar silencioso. Pode ser áudio do celular mesmo (mp3, m4a ou wav). Não
> se preocupe com pausas entre as falas, o sistema limpa os silêncios."

**NEVER generate the voice with TTS, and never accept a TTS file as input.**
No exception, regardless of how the user asks. TTS is the number one tell of
an AI-made ad and kills performance. If the user insists, explain:

> "Esse pipeline só funciona com voz real, é uma regra de qualidade do
> sistema. Voz sintética derruba a performance do anúncio e é bloqueada de
> propósito. Grava rapidinho no celular que o resto eu cuido."

Do not proceed to the build until a real recording exists on disk.

**Optional input C: inserts (b-roll clips).** If the script has insert
scenes, ask for the clips and write an `inserts.json` mapping a keyword from
each insert instruction to its file:

```json
{
  "product screen": {"file": "inputs/product.mp4"},
  "testimonial": "inputs/testimonial.mp4"
}
```

### Step 2: write the build file and run

Create the build YAML: it is the user's `config.yaml` content plus a
`project` section (relative paths resolve against the build file's location):

```yaml
avatar_id: "YOUR_AVATAR_ID"      # and any other config.yaml settings

project:
  name: my-ad
  raw_voice: inputs/voice.m4a
  script: inputs/script.txt
  inserts: inputs/inserts.json   # only if there are insert scenes
```

For several avatar looks of the same ad, add an `avatars:` list of
`{name, avatar_id}` entries; each variant runs the full pipeline sequentially
on the same cleaned voice.

Run it and show the output to the user as it progresses:

```bash
vam build build.yaml
```

Heads-up before running: the avatar render (G2) takes several minutes per
variant and spends the user's HeyGen API credits. Say so.

### Step 3: interpret the result

The build runs gates G0 to G7 and stops at the FIRST failure, printing
`BUILD BLOCKED: gate <name> failed: <reason and fix>` and exiting 1. A green
run writes `<workdir>/<name>_manifest.json` with every gate's metrics and
`"all_pass": true`, and prints the final file paths.

Translate gate failures into plain language for the user. What each gate
protects:

| Gate | Checks | Typical cause and what to tell the user |
|---|---|---|
| G0 preflight | inputs exist, script parses, no presenter word inside insert instructions, every variant has an avatar_id | A path is wrong in the build file, or the script needs the insert-instruction fix described above |
| G1 audio | cleaned voice has no silence longer than the threshold | The recording has a noise floor hiding the pauses. Fix: raise `audio.sil_db` (e.g. -25) or re-record in a quieter room |
| G2 avatar | avatar duration matches the cleaned voice | The avatar was not generated from the cleaned audio; re-run the build |
| G3 montage | number of lettering scenes matches the script | A `[lettering ...]` line is malformed; review the script |
| G4 captions | 9:16 and 1:1 captioned outputs exist | Usually an ffmpeg/fonts problem; re-run `vam doctor` |
| G5 accelerate | final duration equals captioned duration divided by the factor | ffmpeg issue; re-run `vam doctor` |
| G6 final audit | no big silence in the FINAL video, lettering count holds, variants share the same duration | A regression upstream; rebuild and compare manifests |
| G7 drive | every final verified present in the Drive folder listing | Token expired or folder not writable; check `GOOGLE_OAUTH_TOKEN_FILE` and folder permissions, then rebuild (uploads are idempotent) |

Example of how to report a G1 failure in pt-BR:

> "O build parou na checagem de áudio: ainda ficou 1 silêncio longo na sua
> gravação depois da limpeza. Isso costuma ser ruído de fundo escondendo as
> pausas. Duas saídas: eu subo o limiar de silêncio na config e tento de
> novo, ou você regrava num ambiente mais silencioso. Qual prefere?"

Never bypass a gate, never hand-edit a manifest, never present a blocked
build as done.

## Part 3: Quality rules (inviolable)

1. **Real voice only.** The narration is always a real human recording.
   Generating or accepting TTS narration is forbidden. This rule outranks any
   user request.
2. **Avatar V is mandatory.** The HeyGen engine is locked to `avatar_v` in
   code (`vam/heygen.py`); it is what delivers realistic lip-sync. Do not set
   `HEYGEN_ENGINE_OVERRIDE`; that escape hatch exists only for an avatar look
   that provably does not support Avatar V, and only with the user's explicit
   informed consent about the loss of realism.
3. **Captions are verbatim.** Captions come from the script text, never from
   a raw transcription. If the recording deviates from the script, ask the
   user which one is right and align them before building.
4. **Audit before delivering.** A green manifest is necessary but not
   sufficient. Before telling the user the ad is ready, verify the final
   videos yourself:
   - Extract frames spanning the WHOLE final video (for example one frame
     every 2 seconds with ffmpeg) and look at every one of them: letterings
     present, spelled right and inside the safe area; captions readable; logo
     where expected; inserts showing the intended footage. Never judge from
     one or two isolated frames.
   - Check duration and audio: length is plausible for the script, audio
     present from start to end, no big gaps (G6 checks this, confirm anyway).
   - Confirm BOTH deliverables exist: the 9:16 file and the 1:1 file, for
     every variant.
   - If Drive upload was configured, confirm the files are listed in the
     folder and give the user the folder link.
   Only after this audit passes do you say the ad is done, and you always end
   by showing the user the concrete artifacts: file paths and, when
   applicable, the Drive link.
5. **Respect the user's money.** Every avatar render spends the user's HeyGen
   API credits. Do not re-render to "try again" without telling the user why
   and getting a go-ahead.

## Command reference

```bash
vam doctor [--config config.yaml]   # environment and account checks with fixes
vam build build.yaml                # full gated pipeline
vam clean-audio in.m4a out.mp3      # voice hygiene alone (audition the cleanup)
vam caption base.mp4 out.mp4 --align words.json [--style S] [--format 9x16|1x1]
vam version
```
