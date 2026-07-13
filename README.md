# Video Ads Machine

Turn an annotated script plus a real voice recording into short-form AI-avatar video ads, rendered in 9:16 (Stories/Reels) and 1:1 (feed), with word-by-word captions, on-screen lettering, B-roll inserts with a circular picture-in-picture, and a gated build that refuses to ship a broken video.

License: Apache 2.0. Python 3.9+. Runs locally on macOS or Linux (ffmpeg does the rendering; only the avatar generation happens in the cloud, on your HeyGen account).

## What it is

- A command-line pipeline: `vam build build.yaml` takes your config, your annotated script and your raw voice recording, and produces final MP4 files.
- Brand-agnostic and account-agnostic: your HeyGen avatar id, brand color, logo, Drive folder and speed factor all live in a YAML config you own. Nothing brand-specific is hardcoded.
- Built around a real voice. The avatar is lip-synced to a recording of an actual person (HeyGen audio input). Captions show the script text verbatim, never a raw transcription.
- Gated. Eight quality gates (G0 to G7) check every stage and stop the build with a concrete fix-it message on the first failure. A build is only "done" when the JSON manifest says every gate passed.
- Ported from a production-validated engine. The defaults (silence thresholds, caption timing, lettering positions, 1.2x speed-up) are the numbers that were validated in real ad production, not guesses.

## What it is NOT

Set your expectations before you invest time:

- It is not free to run. Avatar generation requires HeyGen **API credits** (pay-as-you-go, roughly US$1 per minute of 1080p as of mid-2026), billed separately from any plan credits. A free HeyGen account already includes one custom avatar slot; a paid plan is optional. Every build spends API credit.
- It is not text-to-speech. There is no TTS mode on purpose: a synthetic voice is the number-one tell of AI content. You must record the script with a real voice, and the quality of the final ad is bounded by the quality of that recording.
- It is not forgiving of bad audio. The silence-trimming step (de-breath) is energy-based; a noisy or echoey recording hides the pauses from the detector and the pipeline will refuse to continue (gate G1). See the recording guide below.
- It is not an editor. There is no timeline, no preview UI, no manual tweaking of individual frames. You control the output through the script annotations and the config file.
- It is not Windows-tested. The code avoids OS-specific tricks and ffmpeg exists on Windows, but the validated environments are macOS and Linux.
- It does not ship music, avatars or voices. You bring your own HeyGen avatar; the repo only bundles open-licensed fonts.

## How it works

Inputs: a config/build YAML, an annotated script (plain text), a raw voice recording (mp3/wav/m4a), and optionally a JSON map of B-roll insert clips.

Pipeline, in order:

1. **Voice hygiene** (`vam.audio`): ffmpeg `silencedetect` finds real pauses by energy; only silences longer than `audio.big_sil` (default 0.55s) are shortened, leaving a natural `keep_pause` (default 0.26s). Words are never cut because cuts happen in the middle of silences, with a micro-fade at each splice.
2. **Avatar generation** (`vam.heygen`): the cleaned voice is uploaded to HeyGen and rendered with the Avatar V engine (realistic lip-sync). The engine is locked in code: requesting any other engine raises an error unless you set an explicit override (see Troubleshooting).
3. **Montage** (`vam.montage`): the script is parsed into scenes, the avatar audio is transcribed (faster-whisper) and the script words are aligned to real word timestamps, so every scene cut lands on a word boundary. Scenes are rendered (full-screen presenter with slow zoom, B-roll inserts over a blurred fill, giant serif letterings, logo card), chained with short dissolves, and the continuous avatar audio is reattached so lip-sync never drifts. Inserts get a circular picture-in-picture of the presenter.
4. **Captions** (`vam.captions`): word-by-word editorial captions, timed from the alignment but showing the script words verbatim. Burned twice: on the 9:16 master and on a 1:1 square composite (blurred cover background, full 9:16 frame fitted, captions scaled proportionally).
5. **Acceleration** (`vam.accelerate`): the finished video is sped up by `accelerate` (default 1.2x) with pitch preserved (setpts + atempo).
6. **Delivery** (`vam.drive`, optional): finals are uploaded to your Google Drive folder with the resumable protocol, then the folder is listed to verify each file actually landed.

### The 8 gates

Each gate fails the build immediately with a message that says what broke and how to fix it (`GateFail`, CLI exit code 1). All results are written to `<workdir>/<name>_manifest.json`.

| Gate | Checks |
|---|---|
| G0 preflight | Inputs exist, script parses into scenes, no insert instruction contains a presenter word (parser gotcha), every avatar variant has an avatar_id. |
| G1 audio | The cleaned voice exists and contains zero silences longer than `big_sil`. |
| G2 avatar | Avatar duration matches the cleaned voice duration, proving the avatar was generated from the cleaned audio. |
| G3 montage | The montage timing contains exactly the number of lettering scenes the script announces. |
| G4 captions | Both the 9:16 and the 1:1 captioned outputs exist. |
| G5 accelerate | Final duration equals captioned duration divided by the speed factor, within tolerance. |
| G6 final audit | Zero big silences in the final video, and all avatar variants land on a consistent duration. |
| G7 drive | Only when `drive_folder` is set: uploads the finals and verifies them in the Drive folder listing. |

### Multiple avatar variants

A build file may list several avatar looks under `avatars:`. Each variant runs the full G2 to G6 pipeline sequentially with the same cleaned voice, so you get the same ad rendered by different looks, with G6 checking that all variants end up the same length.

## Requirements: accounts and tools BEFORE you start

| Resource | Cost | Role | Required |
|---|---|---|---|
| HeyGen account with an avatar | Free account works; API credits required (pay-as-you-go) | Generates the lip-synced avatar from your voice. No custom avatar yet? `vam avatars` lists ready-made looks your key can use | Yes |
| `HEYGEN_API_KEY` | Included with the above | API access (app.heygen.com, Space Settings, API) | Yes |
| ffmpeg + ffprobe, built with libass | Free | All local rendering and caption burning | Yes |
| Python 3.9+ | Free | Runs the pipeline | Yes |
| faster-whisper | Free | Word-level alignment for scene cuts and captions | Yes |
| Google OAuth token (Drive scope `drive.file`) | Free | Upload finals to your Drive folder | Optional |

Important about HeyGen: **API credits are separate from plan credits.** A paid plan with plenty of regular credits can still have zero API credits, and then every render fails. `vam doctor` checks your remaining API credit before you record anything.

You also need a way to record a clean voice take: a decent microphone in a quiet, non-echoey room. This is a hard requirement in practice, see the recording guide.

## Install

```bash
git clone https://github.com/YOUR_GITHUB_USER/video-ads-machine.git
cd video-ads-machine
pip install -e .

# alignment backend (used by montage and captions)
pip install '.[whisper]'      # installs faster-whisper
```

ffmpeg:

```bash
# macOS
brew install ffmpeg
# Debian/Ubuntu
sudo apt install ffmpeg
```

The first build downloads the whisper model (about 500 MB for "small"). Set `VAM_WHISPER_MODEL=base` for speed or `medium` for accuracy.

## Quickstart

```bash
# 1) Secrets: put your HeyGen key in .env (gitignored)
cp .env.example .env          # edit: HEYGEN_API_KEY=...

# 2) Config: set your avatar id (everything else has validated defaults)
cp config.example.yaml config.yaml

# 3) Preflight: checks the machine AND your accounts, with a fix for each failure
vam doctor

# 4) Build
vam build build.yaml
```

`vam doctor` validates: Python deps, a real 1-frame ffmpeg render through the libass subtitles filter (catches broken installs that pass `-version` checks), ffprobe, the bundled fonts, the alignment backend, your HeyGen key (including remaining API credit), that your `avatar_id` actually exists in your account (and warns when the look appears landscape), and your Drive token when `drive_folder` is configured. Exit code 0 means you are ready.

### The build file

`vam build` takes the pipeline config plus a `project` section (and optionally `avatars`):

```yaml
avatar_id: "YOUR_AVATAR_ID"
accelerate: 1.2
workdir: ./build
# drive_folder: https://drive.google.com/drive/folders/YOUR_FOLDER_ID

project:
  name: my-ad
  raw_voice: inputs/voice.mp3      # REAL recorded voice, never TTS
  script: inputs/script.txt        # annotated script, format below
  inserts: inputs/inserts.json     # optional B-roll map

# optional: several avatar looks, one full pipeline each, same voice
# avatars:
#   - { name: studio, avatar_id: "YOUR_AVATAR_ID" }
#   - { name: casual, avatar_id: "YOUR_OTHER_AVATAR_ID" }
```

Relative paths resolve against the build file's directory.

### The script format

One scene per line: a visual instruction in brackets, then the exact words the presenter speaks.

```
[presenter, slow zoom] Would you rather have access to
[product screen recording] a ready-made library of AI workers?
[lettering | LEAD: a team that | KEY: WORKS] A team that works for you around the clock.
[lettering + logo] Tap the button below and claim your spot.
```

Scene classification, by priority: `lettering` (plus `lettering_logo` when the instruction also mentions "logo"), `logo`, presenter (`orig`, when the instruction contains "avatar", "presenter" or "apresentador"; add "zoom" for a slow zoom-in), and everything else becomes an `insert` (B-roll), matched by keyword against your inserts map.

Known gotcha, enforced by G0: an insert instruction must NOT contain a presenter word ("b-roll with the presenter" would silently become a full-screen presenter scene). Name the footage instead.

For lettering scenes, `KEY:` is the giant serif word rendered in your brand color and `LEAD:` is the small italic line above it. Both are display-only; the narration is still whatever follows the brackets.

### The inserts map

`inserts.json` maps a keyword (matched against the instruction text) to a clip:

```json
{
  "product screen": {"file": "clips/screen.mp4", "start": 2.0, "speed": 1.0, "zoom": 1.05},
  "testimonial": "clips/testimonial.mp4"
}
```

String values are shorthand for `{"file": ...}`. File paths resolve against the JSON's directory.

### Other commands

```bash
vam doctor [--config config.yaml]   # preflight (alias: vam setup)
vam clean-audio in.mp3 out.mp3      # audition the de-breath step by itself
vam caption base.mp4 out.mp4 --align words.json --style tay --format 1x1
vam version
```

`words.json` for standalone captioning is word-level timing: `[["word", start, end], ...]` in seconds. Caption style presets live in `STYLES` in `src/vam/captions.py`; adding a style is adding one dict entry.

## Configuration reference

All fields of `config.example.yaml`. Every field except `avatar_id` has a production-validated default, so a minimal config is a single line.

| Field | Default | Meaning |
|---|---|---|
| `avatar_id` | required | Your HeyGen avatar id (app.heygen.com, Avatars, or `GET /v2/avatars`). |
| `brand.key_color_bgr` | `4AA6FF` | Color of the highlighted KEY word in letterings. **BGR hex** (blue-green-red), because that is what the ASS subtitle format uses, not RGB. |
| `brand.logo_path` | none | PNG logo with transparent background, overlaid on logo scenes. |
| `lettering.style` | `foil` | `foil` (metallic gradient on the key word, validated default) or `solid` (flat brand color). |
| `lettering.y_key` | `1690` | Baseline Y of the key line on the 1080x1920 canvas, tuned to clear the Instagram Reels UI. |
| `lettering.y_key_with_logo` | `1500` | Key line Y when a logo block sits above it. |
| `audio.big_sil` | `0.55` | Silences longer than this (seconds) are shortened. |
| `audio.keep_pause` | `0.26` | Natural pause left in place of each shortened silence (seconds). |
| `audio.sil_db` | `-30` | Silence threshold in dBFS; breaths sit below this level on a clean recording. |
| `accelerate` | `1.2` | Final speed-up factor, pitch preserved. `1.0` disables it. |
| `drive_folder` | none | Google Drive folder URL or id for delivery. Omit to skip upload. |
| `fonts_dir` | bundled `fonts/` | Directory with the .ttf fonts used by captions and letterings. |
| `language` | `pt` | Language hint for captions/letterings (ISO 639-1). |
| `workdir` | `./build` | Directory for intermediate artifacts and the manifest. |

Build-file-only keys: `project.name`, `project.raw_voice`, `project.script`, `project.inserts`, `project.expected_lettering_scenes` (defaults to the count announced by the script), and the `avatars` list (`name` + `avatar_id` per variant).

Environment variables (secrets never go in YAML): `HEYGEN_API_KEY` (required), `GOOGLE_OAUTH_TOKEN_FILE` (path to a JSON with `access_token`/`refresh_token`/`client_id`/`client_secret`; expired tokens are refreshed and persisted back), `VAM_WHISPER_MODEL` (alignment model size), `HEYGEN_ENGINE_OVERRIDE` (escape hatch, see Troubleshooting). A `.env` file in the working directory is loaded automatically.

## Recording guide

The pipeline is only as good as the voice take. Rules that come from production use:

- **Quiet room, no echo.** The de-breath step detects pauses by energy at -30 dBFS. Echo and a high noise floor sit above that level, silences are never detected, and gate G1 blocks the build. Soft furniture beats bare walls.
- **Decent microphone, close to the mouth.** A lav or a USB condenser 10 to 20 cm away is enough. Built-in laptop mics in a live room usually are not.
- **Read the script exactly as written.** Captions display the script verbatim and are aligned against what you actually said; improvised words degrade the alignment.
- **Pause naturally between sentences.** Do not try to edit your own pauses while recording; the pipeline shortens the long ones for you and keeps the short natural ones. Breathe normally.
- **One continuous take per ad.** The avatar receives one continuous audio track; scene cuts come from the script annotations, not from separate takes.
- Export as mp3, wav or m4a.

## Troubleshooting

**`vam doctor` fails ffmpeg with "dyld: Library not loaded" (macOS).** Your ffmpeg binary links against a shared library that a Homebrew upgrade removed. `brew reinstall ffmpeg`. This is exactly why the doctor runs a real 1-frame render instead of trusting `ffmpeg -version`.

**ffmpeg present but "cannot use the subtitles filter".** Your build was compiled without libass (common with minimal/static builds). Install a full build.

**HeyGen renders fail although your plan has credits.** API credits and plan credits are billed separately. Check Space Settings, API in the HeyGen dashboard and add API credit. `vam doctor` reports the remaining API credit up front.

**Doctor warns the avatar look appears landscape.** The pipeline renders 9:16 vertical. The HeyGen preview aspect can be misleading, but verify in HeyGen that the look supports portrait before burning credits on a long render.

**G1 fails: "big silences still in the cleaned voice".** The recording is too noisy or echoey for the -30 dB threshold. Best fix: re-record in a quieter setup. Workaround: raise `audio.sil_db` in the config (for example `-25`), accepting a higher risk of clipping soft speech.

**G2 fails: avatar duration does not match the cleaned voice.** The avatar was generated from some other audio. Re-run the build; do not upload audio to HeyGen manually mid-build.

**Captions out of sync or wrong scene cuts.** The alignment model may have struggled with the audio. Try `VAM_WHISPER_MODEL=medium`, and check that the script matches what was actually spoken.

**"faster-whisper is not installed".** `pip install '.[whisper]'`. It is required by the montage and caption steps.

**You genuinely need a non Avatar V engine.** The engine is locked because Avatar V is what delivers realistic lip-sync. If an avatar look provably does not support it, set `HEYGEN_ENGINE_OVERRIDE=<engine>` and request that same engine explicitly, accepting the loss of realism. Without both, the lock holds.

## Security

- No credentials live in this repo or in the config YAML. API keys go in environment variables or a gitignored `.env`; the Google token lives in a JSON file you point to via `GOOGLE_OAUTH_TOKEN_FILE`.
- The Drive integration needs only the `https://www.googleapis.com/auth/drive.file` scope: it can touch files it created, and nothing else in your Drive.
- CI runs a secret scan on every push. Please keep it that way in PRs.
- The project does not distribute avatars or voices; your use of HeyGen is governed by HeyGen's terms.

## License

[Apache 2.0](LICENSE). Bundled fonts (DM Serif Display, Playfair Display, Nunito, Montserrat) are licensed under the SIL Open Font License, see [NOTICE](NOTICE).
