# Demo pack

A starter pack to render a reel end to end without any of your own content yet.

## What is here
- `roteiro_demo.txt` : a generic sample script using the annotation convention (`*keyword*`, `[LEAD:]`, `[KEY:]`, `[DUR:]`).
- `brief.example.json` : a sample brief with the default presets and the demo asset paths.

## What you need to add
Media files are NOT bundled in this release (to keep the repo small and free of any licensed footage). Drop your own generic/royalty-free media here with these names:
- `avatar_demo.mp4` : any 9:16 talking-head clip (or generate one with HeyGen Avatar V).
- `voz_demo.mp3` : the voice track that matches the script.
- `logo_demo.png` : any wordmark/logo (transparent PNG works best).

If you do not have a talking-head, the skill can offer to generate one via HeyGen (see the main `README.md`).

## Render the demo
After `bash scripts/setup.sh`, follow the workflow in `SKILL.md`:
1. Point `build_timeline` at `demo/roteiro_demo.txt` + your `voz_demo.mp3` + the `reel-editorial` template with `demo/brief.example.json`.
2. Write the built `index.html` into a render folder together with the demo assets and `fonts/`.
3. `hyperframes render -o demo_out.mp4 -f 25 -q standard --video-frame-format png`.
4. `bash scripts/audit_frames.sh demo_out.mp4 demo_frames` and check the frames.

That gives you a full reel in the editorial style, ready to swap for your real assets.
