<div align="center">

# Video Ads Machine

**Turn an annotated script + a real voice recording into AI-avatar video ads — automatically rendered in 9:16 (Stories/Reels) and 1:1 (Feed).**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
![Status](https://img.shields.io/badge/status-v0.1%20(early)-orange.svg)
![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)

</div>

---

## What it is

Video Ads Machine is an open-source pipeline that produces short-form **video ads driven by an AI avatar**. You write a structured script, record the real voice reading it, and the pipeline assembles the avatar, captions, on-screen lettering, a picture-in-picture (PiP) talking-head over B-roll, music, and exports the final cut in multiple aspect ratios.

It is **brand-agnostic**: you bring your own avatar, brand colors, fonts, and music through a config file. Nothing is hardcoded.

### Philosophy (why it looks human, not AI)

- **Real voice, always.** The avatar is lip-synced to a *real recorded voice* (HeyGen audio-input), never TTS. Synthetic voice is the number-one "tell" of AI content.
- **Verbatim captions.** Captions come from the script text, never from raw transcription (which produces wrong words).
- **Audit the whole video.** Every render is reviewed frame-by-frame (full sweep, not cherry-picked frames) before it ships.

---

## Status

**`v0.1` — early.** Working today:

- ✅ **Onboarding / preflight** (`vam doctor`) that checks your machine and guides installation of every dependency, MCP and plugin.
- ✅ **Caption engine** — format-aware (9:16 and 1:1), with per-format font scaling and a fade-safe halo. The 9:16 output is byte-identical to the validated reference.
- ✅ Config system, bundled OFL fonts, docs, CI (secret scan + tests).

In progress (see [Roadmap](#roadmap)): the HeyGen avatar provider, subtitle alignment backend, lettering, PiP, the full compose step (music + speed), and the end-to-end `vam build` command.

---

## How it works

```
  annotated script (YAML or Google Sheet)
            +
  real voice recording (per scene)
            │
            ▼
   ┌─────────────────────────────────────────┐
   │  avatar (HeyGen, audio-input)            │
   │  → captions (verbatim, format-aware)     │
   │  → lettering (serif, key-word emphasis)  │
   │  → PiP talking-head over B-roll          │
   │  → music + ducking + speed               │
   └─────────────────────────────────────────┘
            │
            ▼
     9:16 (1080×1920)   +   1:1 (1080×1080)
```

Each creative can carry **multiple hooks**: one main hook plus alternates. Each alternate hook becomes a *new video* reusing the same body + CTA — so one script with 3 alternate hooks yields **4 videos × 2 formats = 8 files**, ideal for hook testing.

---

## Accounts & tools

| Resource | Cost | Role | Required? |
|---|---|---|---|
| **HeyGen** | Paid | Generates the avatar from the real voice | **Yes** |
| **ffmpeg** | Free | Rendering (local) | **Yes** |
| **parakeet-mlx** *or* **faster-whisper** | Free | Subtitle alignment | **Yes** (one of them) |
| Google Sheets API | Free | Script from a spreadsheet (alternative to YAML) | Optional |
| uazapi | Paid | WhatsApp progress notifications | Optional |
| Google Chrome | Free | Advanced lettering | Optional |
| Music track | Your own | Soundtrack (royalty-free / CC0) | You provide |

> You bring your own keys. **No credentials are stored in this repo.**

---

## Quickstart

```bash
# 1) Install
git clone https://github.com/ojuliocouto/video-ads-machine.git
cd video-ads-machine
pip install -e .

# 2) Install ONE alignment backend
pip install parakeet-mlx     # Apple Silicon (Mac M1+)
# or
pip install '.[whisper]'     # Windows / Linux / Intel Mac

# 3) Configure
cp .env.example .env                  # add your HEYGEN_API_KEY
cp config.example.yaml config.yaml    # set your avatar_id, brand, formats

# 4) Preflight — tells you exactly what is still missing
vam doctor
```

`vam doctor` will not let you generate until the required minimum passes (ffmpeg + one alignment backend + HeyGen key), and it prints the exact install command for anything missing — including optional MCPs/plugins.

---

## Usage (today)

The caption engine is usable standalone:

```bash
vam caption input.mp4 output.mp4 \
  --align words.json \
  --style tay \
  --format 1x1
```

`words.json` is word-level timing in seconds:

```json
[["you", 0.0, 0.35], ["prefer", 0.35, 0.8], ["skills", 0.8, 1.3]]
```

Caption presets live in `src/vam/captions.py` (`tay`, `serif_italic`, and others). Add a new one by adding a single entry — no code changes needed.

---

## Configuration

Everything brand/account specific lives in `config.yaml` and `.env` (both git-ignored). Example:

```yaml
brand:
  primary_color: "#FA4E04"
  caption_font: "Nunito"
  lettering_font_lead: "PlayfairDisplay"
avatar:
  provider: heygen
  avatar_id: "YOUR_AVATAR_ID"
voice:
  mode: real            # real voice only
formats: ["9x16", "1x1"]
speed: 1.2
```

---

## Formats

- **9:16 (1080×1920)** — Stories/Reels. Caption sits over the chest. This is the validated reference layout.
- **1:1 (1080×1080)** — Feed. The full 9:16 frame is fitted into the square with a blurred/darkened fill on the side margins (so the subject keeps its original framing), and the caption + font scale down proportionally. Per-format scaling is automatic.

Adding a new format = one entry in the `FORMATS` table (resolution + caption scale).

---

## The script format

Scripts are annotated line-by-line. Each scene has: the spoken line, the **phase** (Hook / Body / CTA), the **scene type** (avatar, B-roll, lettering, logo, or combinations), an optional **lettering key word**, an optional **B-roll** reference, zoom, and PiP. See [`examples/roteiro.example.yaml`](examples/roteiro.example.yaml).

---

## Onboarding for Claude Code (skill)

This repo ships a [`SKILL.md`](SKILL.md) so it can be driven as a Claude Code skill. On first use the skill runs the preflight (`vam doctor`) and walks the user through installing dependencies, optional MCPs (uazapi, Google), and plugins before any generation.

---

## Roadmap

- [ ] `vam build <script>` — full script → video pipeline.
- [ ] HeyGen avatar provider (audio-input).
- [ ] Pluggable alignment (parakeet / whisper).
- [ ] Lettering, PiP, and compose (music + ducking + speed) for both formats.
- [ ] Script input from Google Sheet or YAML.
- [ ] Per-scene 1:1 composition (B-roll filling the square instead of letterboxed).

---

## Contributing

Issues and PRs welcome. CI runs a secret scan (gitleaks) and tests on every push — please keep credentials out of the repo and add tests for new modules.

## License

[Apache 2.0](LICENSE). Bundled fonts are licensed under the SIL Open Font License (see [NOTICE](NOTICE)).
