# Video Ads Machine 2.0

A Claude Code skill that turns a script + voice + talking-head + b-rolls into a polished vertical (9:16) reel or video ad, in a validated editorial style, with a configurable **preset system**. It is a composition engine built on top of [HyperFrames](https://hyperframes.heygen.com) (HTML/CSS + GSAP rendered by headless Chromium), not a video generator.

The reel style (warm cinematic grade, bold word-by-word captions, serif letterings anchored to the chest, a hook that opens on the presenter, an end-card logo) comes from a reference reel that was audited frame by frame and approved.

## What it IS
- A declarative composition engine for 9:16 reels and ads (plus a 1:1 square variant for the feed).
- A tested library of **blocks** (hook, captions, b-roll cards, letterings, lower-third, end-card, color grade, transitions, stat count-up) and **presets** across 6 style dimensions.
- Automation for the tedious part: aligning the caption word-by-word to the voice and placing letterings on the exact word they belong to.
- A self-bootstrapping skill: the first run installs and checks HyperFrames for you.

## What it is NOT
- **Not a generator.** It does not create the avatar, the voice, or the b-rolls. It composes and edits assets you provide. There is one OPTIONAL step that offers to generate a talking-head via HeyGen when the avatar is missing, using your own HeyGen key.
- **Not a hosted app.** Everything runs locally. Rendering happens on your machine.
- **HyperFrames is not bundled here.** HyperFrames is proprietary software with its own license. This repo does not redistribute it. The setup step installs it from npm onto your machine. Review the HyperFrames license before commercial use at scale.

## How it works
1. You describe a reel with a **brief** (format + style presets) and an annotated **script**.
2. `build_timeline` aligns the script to the voice (word-level transcript), generates the word-by-word captions and the letterings, and injects them into a template together with the chosen presets.
3. You lint, render, and audit the result frame by frame.
4. You get a 9:16 MP4 plus a lightweight `_whatsapp` version for approval.

The script uses a simple annotation convention:
- normal words become the verbatim caption;
- `*word*` marks a keyword (rendered in italic serif);
- `[LEAD: text]` `[KEY: text]` `[DUR: seconds]` place a lettering anchored to the next spoken word.

## Requirements (onboarding)
Have these BEFORE you start:
- **Node.js 18+** and **ffmpeg** installed.
- A **talking-head video** (`avatar.mp4`), the **voice** track, your **b-rolls**, and a **logo**. If you do not have the avatar, the skill can offer to generate one via HeyGen (Avatar V engine), which needs your own `HEYGEN_API_KEY` and a HeyGen `avatar_id`.
- Optional, macOS only: `parakeet-mlx` for faster alignment. The default uses HyperFrames' own word-level transcript, which is cross-platform.

## Install
Clone this repo into your Claude Code skills directory, then run the bootstrap:
```bash
git clone <this-repo-url> ~/.claude/skills/video-ads-machine-2
cd ~/.claude/skills/video-ads-machine-2
bash scripts/setup.sh
```
`setup.sh` is idempotent: it installs the pinned HyperFrames (if missing), runs `hyperframes doctor` (checks Node/ffmpeg/Chrome), `hyperframes browser ensure` (downloads the render Chromium), and `hyperframes skills` (authoring skills). It only does what is missing.

## Content of this repo
- `SKILL.md` : the skill entry point (embedded onboarding + workflow router).
- `LEARNINGS.md` : the engine's living memory. Every assembly rule and pre-delivery audit check, each one born from a real production defect. Read it before touching the timeline logic.
- `references/` : `style.md` (exact validated numbers), `blocks.md`, `presets.md`, `workflow.md`, `hyperframes-gotchas.md`.
- `blocks/` : reusable HTML/CSS/GSAP partials.
- `presets/` : one file per style variant, grouped by dimension (caption, lettering, transition, grade, hook, endcard).
- `templates/` : `reel-editorial` (flagship, 9:16), `reel-editorial-1x1` (1:1 square, for feed), and `ad-hook`.
- `scripts/` : `setup.sh`, `check_assets.py`, `build_timeline.py`, `audit_frames.sh`.
- `fonts/` : embedded open woff2 fonts (Inter, Montserrat, Playfair Display Italic, Archivo).
- `demo/` : a starter pack so you can render something end to end (see `demo/README.md`).
- `tests/` : pytest suite for the Python scripts.

## Security and privacy
- **Bring your own keys.** `HEYGEN_API_KEY` and any other credential are yours and are never committed. The skill never sends them anywhere.
- **No real client assets are shipped.** Real talking-heads, brand logos, and scripts stay out of the repo (the `.gitignore` keeps local material under `_local/` and render folders out of version control). Use the generic `demo/` pack to try it out, and your own assets for real reels.
- The skill only runs local commands you can inspect. The optional avatar generation step never calls any API without your explicit confirmation.

## Preset system
Pick one preset per dimension in the brief, or omit `styles` to get the validated default look.

| Dimension | Presets | Default |
|---|---|---|
| caption | montserrat-grossa, tay-fina, boxed | montserrat-grossa |
| lettering | serif-editorial, sans-bold, kinetic | serif-editorial |
| transition | grid-wipe, hard-cut, crossfade, zoom-blur | grid-wipe |
| grade | quente, natural, frio-teal, pb | quente |
| hook | pessoa-lettering, tela-preta, card-kinetico | pessoa-lettering |
| endcard | cta-logo-rodape, logo-fullscreen | cta-logo-rodape |

Only presets that were rendered and audited frame by frame are marked `validated`. The rest are marked `unvalidated` and should be verified before you rely on them.

## License
This project is released under the **MIT License** (see `LICENSE`). HyperFrames is proprietary and installed separately by you; it is not covered by this license.
