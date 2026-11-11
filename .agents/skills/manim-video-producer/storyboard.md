# Storyboard template (copy to runs/<run>/video/storyboard.md; fill every field)

Explainer: `../explainer.html`, a source: tell one story with less, and different, material; never walk its sections.
Audience: robotics and control researchers and students. Rules: AGENTS.md (Conventions),
`.claude/rules/manim-scenes.md`, `.agents/skills/manim-video-producer/spoken-script.md`.

## Craft plan

- Metaphor (one object, its meaning, scenes and on-screen label; where its value changes in each scene; every refill
  with the sentence that announces it):
- Picture per scene (faithful or schematic):
- Misconception (what a viewer likely believes; where it is voiced and refuted):
- Everyday analogy (by 90 s) and where it returns:
- Picture before formula (each new equation: the picture first, for how long):
- Which object becomes which (path segment -> cost term, bar -> symbol, line -> next line):
- Colours by quantity:
- Think prompts (question, scene, held silence, the block with the answer):
- Beats (`beat()` after the key reveals that are not starred results):
- What moves under each narration block (one line per block: content, not a highlight):
- New terms (the block and picture of each):
- Parameters (one name and convention each, said and shown):
- "So what" after each boxed result:
- Objects carried across each cut:
- Outro callback (the hook's picture, moving) and the teaser as a picture:
- Signposts, re-engagement points, and each required phrase as worded for its scene:

## Pacing plan (check_pacing.py)

- Ideas in order, each with id, scene, bookmark and picture (`plan.json` `ideas`). Series episode: those of
  `video/episode.md` ("Ideas"), no others. Standalone video: its own, with the same kinds and fields
  (`.agents/skills/plan-series/brief.md`, "The idea budget"). Spacing: P1-P3.
- Runtime (series: the range in `video/episode.md`; standalone: `python3 tools/video/idea_budget.py runs/<run>`) and
  the sum of the scene lengths:
- Pretraining segment, if any (P4):
- Roadmap (after the title beat):
- Chapter summaries:
- Restatements (each starred result in plain words, the same in the recap):
- Recap (before the outro, opening with its question):
- Pause plan (each planned pause: after which sentence, how long, how: `[pause S]`, a hold, `beat()`):
- Slow blocks (`[slow]`: each derivation or argument):
- Numbers (which are said, each on screen as it is said; the rest shown only):

## Left out of the explainer, and why

- ...

## Scene 1: <title> (<length> s, role hook) - source: explainer Section <n>

- Idea (one sentence):
- First frame (full, added before the first `play()`; what moves before the first word):
- First line (a claim, a question or a surprise, not set-up):
- Question (at s) and the stakes:
- Thumbnail picture (the episode's end picture; bold at 168 x 94: thick strokes, the key object large, no readouts or
  labels):
- Signature object (`meter()`: its quantity and data):
- Objects carried into the title beat and the body:
- Music mode (bed | low | off):
- Data (`data/<file>.npz` from `code/<script>.py`, or the closed forms used):
- On screen (each item, the words it appears on (`wait_until_word`), how long it stays, the reading time it needs;
  what moves in each block):
- Colours (the palette of `common.py`; every meaning also in text):
- End card (the one equation or sentence to remember):

Voice-over, one block per `with self.voiceover(text="...")`, literal text with `<bookmark mark='x'/>`, `[pause S]` and
`[slow]`:

> 1. [slow] One idea per scene. `<bookmark mark='law'/>`Here is the equation that carries it. [pause 3]
> 2. ...

## Scene 2: ...

## Plan (`video/plan.json`)

- Search term:
- Title:
- Summary (two to four sentences):
- Tags:
- Scenes, each with its explainer section and chapter title:
- Thumbnail (a frame of the hook, one bold picture, its text, layout `picture` or `panel`):

## Shorts (optional, not automated)

A vertical 1080x1920 cut of one scene (`manim -r 1080,1920 ...`), at most 60 s, same palette, burned-in captions.
