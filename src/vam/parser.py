"""Annotated-script parser: turns the writer's script into a scene plan.

Script format (one scene per line)::

    [visual instruction] spoken narration...
    [visual instruction | LEAD: small italic line | KEY: BIG WORD] narration...

The text inside ``[...]`` is the visual direction; everything after the
closing bracket is what the presenter actually says (it becomes the
continuous narration sent to the avatar engine and the per-scene captions).

Scene classification (`tipo`), by priority:

1. ``lettering``       — instruction contains "lettering"
   (``lettering_logo`` when it also contains "logo")
2. ``logo``            — instruction contains "logo"
3. ``orig``            — instruction contains a presenter word
   ("avatar", "presenter", "apresentador" by default): full-screen
   talking-head scene, with a slow zoom when "zoom" is mentioned
4. ``insert``          — anything else (b-roll / screen recording),
   matched later against the user's insert map by keyword

GOTCHA (validated behavior, kept on purpose): the presenter check runs
BEFORE the insert fallback, so an insert instruction that mentions the
presenter word (e.g. "b-roll with the avatar on screen") is classified as
a presenter scene. Insert instructions must NOT contain the presenter
keyword — name the footage instead ("product screen", "testimonial").

LEAD/KEY (lettering scenes): ``KEY:`` is the giant serif word rendered in
the brand color; ``LEAD:`` is the small italic line above it. Both are
display text only — the narration is still whatever follows the brackets.
"""
import re

# Words that mark a scene as the on-camera presenter. Extend via the
# `presenter_words` argument if your scripts use another word.
PRESENTER_WORDS = ("avatar", "presenter", "apresentador")

_LINE = re.compile(r"\[(.+?)\]\s*(.*)")
_LEADING_PUNCT = re.compile(r"^[\s,…\.]+")


def classify(instr, presenter_words=PRESENTER_WORDS):
    """Classify one visual instruction into a scene type.

    Priority: lettering > logo > presenter (orig) > insert (fallback).
    See the module docstring for the presenter-word gotcha.
    """
    s = instr.lower()
    if "lettering" in s:
        return "lettering_logo" if "logo" in s else "lettering"
    if "logo" in s:
        return "logo"
    if any(w in s for w in presenter_words):
        return "orig"
    return "insert"


def parse(path, presenter_words=PRESENTER_WORDS):
    """Parse an annotated script file into a list of scene blocks.

    Returns a list of dicts with keys:
        tipo  -- 'orig' | 'insert' | 'lettering' | 'lettering_logo' | 'logo'
        instr -- the visual instruction (LEAD/KEY markers stripped)
        narr  -- the narration spoken over this scene ('' for silent scenes)
        key   -- giant lettering word ('' when absent)
        lead  -- small lead line above the key ('' when absent)
        zoom  -- True when the instruction asks for a zoom-in

    Blank lines and lines without a leading ``[...]`` are ignored, so the
    script can contain notes and spacing freely.
    """
    blocks = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            m = _LINE.match(raw)
            if not m:
                continue
            instr, narr = m.group(1), m.group(2).strip()

            # Extract lettering markers: [... | LEAD: small line | KEY: WORD]
            key = ""
            lead = ""
            if "KEY:" in instr:
                instr, key = instr.split("KEY:", 1)
                key = key.strip()
                if "LEAD:" in instr:
                    instr, lead = instr.split("LEAD:", 1)
                    lead = lead.strip().strip("|").strip()
                instr = instr.rstrip(" |")

            # Drop stray commas/ellipses the writer left at the start of the
            # narration (they belong to the previous sentence, not this one).
            narr = _LEADING_PUNCT.sub("", narr)

            blocks.append({
                "tipo": classify(instr, presenter_words),
                "instr": instr,
                "narr": narr,
                "key": key,
                "lead": lead,
                "zoom": "zoom" in instr.lower(),
            })
    return blocks
