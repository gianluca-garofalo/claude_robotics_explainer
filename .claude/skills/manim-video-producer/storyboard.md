# Storyboard template (copy to runs/<run>/video/storyboard.md)

Explainer: `../explainer.html` (a source: choose less, and different, material that tells one story; do not walk its
sections). Audience: robotics and control researchers and students. Channel: Remaining Action. The video opens with
the hook (narration from 0 s, no channel card) and ends with the outro scene (15-20 s: `outro(takeaway_card(...))`,
the channel name, the teaser in a series; the right of the frame empty for the end screen).
Pacing: 130-150 spoken words per minute; hold each new equation 2-3 s before speaking over it. Reading time
(config/video.json): text 0.6 s + 0.3 s per word, equations 1 s + 0.6 s per term (at least 2 s), x1.4 while the
narration talks; at most 40 words and terms on screen at once. RAScene enforces the holds; plan the narration so they
fit instead of stretching the scene. Self-contained: the video never names the explainer, code, files, links or other
episodes by equation number and shows no equation numbers; refer back to an equation by showing it again or by its
meaning. Numbers through `fmt()`: 2-3 significant digits, no trailing zeros, one precision per quantity.

## What this video leaves out of the explainer, and why

- ...

## Scene 1: <title> (<length> s, role hook) - source: explainer Section <n>

- Idea (one sentence):
- Hook (first 5 s):
- Data: `data/<file>.npz` from `code/<script>.py` (or: closed forms of equation (<k>))
- On screen (each item, how long it stays, reading time it needs):
- Colours: blue = <...>, amber = <...>, green = <...> (palette in common.py; label every meaning in text too)
- End card: <the one equation or sentence to remember>

Voice-over, one block per `with self.voiceover(text="...")`, literal text, `<bookmark mark='x'/>` where an animation
must start on a word:

> 1. One idea per scene. `<bookmark mark='law'/>` Here is the equation that carries it.
> 2. ...
> 3. (end card) ...

## Scene 2: ...

## Plan (`video/plan.json`)

- Title (at most 90 characters, accurate, no clickbait):
- Summary (two to four sentences for the description):
- Tags:
- Scenes in order, each with the explainer section id it explains and its chapter title for viewers:
- Thumbnail: scene class, time in seconds of a frame that shows the idea with nothing where the title goes (left
  half), text of at most four words
  (tools/video/thumbnail.py composes it with the Remaining Action layout)

## Shorts (optional, not automated)

Vertical 1080x1920 cut of one scene (`manim -r 1080,1920 ...`), at most 60 s, same palette, burned-in captions.
